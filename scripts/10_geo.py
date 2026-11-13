"""10_geo.py — Strassen und Gemeinden für die Karte verorten.

    python scripts/10_geo.py streets      # Nominatim, 1 Anfrage/s, Cache in web/geo/
    python scripts/10_geo.py municipalities --ptt ~/Repos/vernetzte-schweiz/data/norm/ptt_entries.csv.gz

Lausanne: die Strassen stehen meist ohne «Rue»/«Avenue» («Martheray», «Bourg»); Nominatim findet sie frei
(«Martheray, Lausanne, Vaud»). Die Tabelle der Berner Hausnummern (table_1882) bleibt hier ohne Datei wirkungslos.

`streets` normalisiert die gedruckten Strassennamen (ß → ss, «str.» → «strasse», «g.» → «gasse»,
«pl.» → «platz») und sucht jede Strasse einmal je Gemeinde in OpenStreetMap: zuerst als Strasse
(`street=…&city=…`), dann frei («Name, Lausanne, Vaud»). Treffer ausserhalb der Gemeinde Lausanne
werden verworfen. Ergebnis: web/geo/streets.csv; jede Antwort liegt in web/geo/nominatim_cache.json,
sodass ein zweiter Lauf nur neue Namen kostet. Strassennamen von 1900/1910 sind nicht immer die
heutigen; was OSM nicht kennt, bleibt ohne Punkt (`method = none`) und kann in
web/geo/streets_manual.csv (municipality, street_norm, lat, lon, note) von Hand gesetzt werden.

`municipalities` nimmt den Punkt jeder Gemeinde 1914 aus den Telefonbuch-Daten von Vernetzte Schweiz
(dort aus dem amtlichen Ortsregister) → web/geo/municipalities.csv.

Die Daten in data/csv bleiben unverändert.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import re
import time
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path

CSV_DIR = Path("data/csv")
GEO = Path("web/geo")
CACHE = GEO / "nominatim_cache.json"
UA = "adressbuch-geocoder/0.1 (historical address books, low volume)"
BASE = "https://nominatim.openstreetmap.org/search"
BOX = (6.55, 46.49, 6.72, 46.60)  # Gemeinde Lausanne, grosszügig: lon_min, lat_min, lon_max, lat_max

PREFIX = [(r"(?i)^r(ue)?\.?\s+", "Rue "), (r"(?i)^av(enue)?\.?\s+", "Avenue "), (r"(?i)^ch(emin)?\.?\s+", "Chemin "),
          (r"(?i)^pl(ace)?\.?\s+", "Place "), (r"(?i)^b(oulevar)?d\.?\s+", "Boulevard "), (r"(?i)^gr\.?\s+", "Grand "),
          (r"(?i)^pt\.?\s+", "Petit "), (r"(?i)^prom\.?\s+", "Promenade "), (r"(?i)^ro\.?\s+", "Rue "),
          (r"(?i)^sq\.?\s+", "Square "), (r"(?i)^gd\.?\s+", "Grand "), (r"(?i)^che[mn]\.?\s+", "Chemin "),
          (r"(?i)^esc\.?\s+", "Escaliers "), (r"(?i)^cité derr\.?$", "Cité Derrière")]


def norm_street(s: str) -> str:
    """Gedruckte Strasse → Schlüssel. Lausanne: Abkürzungen ausschreiben («r.» → Rue, «av.» → Avenue,
    «pl.» → Place, «Gr.» → Grand), Bindestriche wie Leerzeichen («Pré-du-Marché» = «Pré du Marché»)."""
    s = re.sub(r"\s+", " ", s.replace("ß", "ss")).strip(" ,;.")
    for pat, rep in PREFIX:
        s = re.sub(pat, rep, s)
    s = re.sub(r"(?i)\bgr\.\s*", "Grand ", s)
    s = re.sub(r"(?<!St)-(?!\d)", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:1].upper() + s[1:]


def city_name(m: str) -> str:
    return re.sub(r"\s*\(.*\)$", "", m)


def streets_in_data() -> Counter:
    c: Counter = Counter()
    for f in ("04_entries.csv", "04_berufe.csv"):
        with (CSV_DIR / f).open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["street_raw"] and r["municipality"]:
                    c[(r["municipality"], norm_street(r["street_raw"]))] += 1
    return c


DISTRICT = ("Bezirk", "District", "Verwaltungskreis", "Verwaltungsregion", "Arrondissement")


def in_muni(res: dict, muni: str) -> bool:
    """Liegt der Treffer in der Gemeinde? Nominatims display_name: «Strasse, …, Gemeinde, Bezirk …, Kanton, PLZ, Land»;
    die Gemeinde muss vor dem ersten Bezirks-Teil stehen (Dättwil: «Dättwil AG» zählt)."""
    name = city_name(muni)
    for c in (c.strip() for c in res.get("display_name", "").split(",")):
        if c.startswith(DISTRICT):
            return False
        if c == name or c.startswith(name + " "):
            return True
    return False


ROAD = r"(rue|avenue|chemin|place|route|boulevard|escaliers?|square|ruelle|passage|quai|promenade|montee|pont|cite|allee|sentier|petit chene|grand chene)"


def _f(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\bsaint\b", "st", re.sub(r"[-'’]", " ", s))
    return re.sub(r"\s+", " ", s).strip()


def road_matches(res: dict, st: str) -> bool:
    """Lausanne: der Strassenname des Treffers muss der gedruckte Name sein, höchstens mit Vorsatz
    («Martheray» = «Rue du Martheray», nicht «Promenade Derrière-Bourg» für «Bourg»)."""
    road = _f(res.get("display_name", "").split(",")[0])
    name = _f(st)
    bare = re.sub("^" + ROAD + r" ", "", name)
    pat = "(" + ROAD + " )?((de la|de l|des|du|de|d) )?"
    if re.fullmatch(pat + re.escape(bare), road):
        return True
    # heute mit Vorname der Person: «Haldimand» = «Rue William-Haldimand», «Enning» = «Rue Jenny-Enning»
    return bool(re.fullmatch(ROAD + r" [a-z]+ " + re.escape(bare), road)) and " " not in bare


def inside(lat: float, lon: float) -> bool:
    return BOX[0] <= lon <= BOX[2] and BOX[1] <= lat <= BOX[3]


def query(params: dict, cache: dict) -> list:
    key = urllib.parse.urlencode(sorted(params.items()))
    if key not in cache:
        url = BASE + "?" + urllib.parse.urlencode({**params, "format": "jsonv2", "countrycodes": "ch", "limit": 5})
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            cache[key] = json.load(resp)
        time.sleep(1.1)
    return cache[key]


MIN_ENTRIES = 3  # seltenere Schreibweisen sind meist Lesefehler: nicht bei Nominatim nachfragen
HN1882 = Path("web/geo/hausnummern_1882_strassen.csv")


def table_1882(src: Path | None) -> dict[str, tuple[float, float, int]]:
    """Strasse (klein) → Mittelpunkt der Häuser aus «Die Häuser-Nummerirung in Bern» 1882 (bern-frueh).
    Beim ersten Lauf aus --hn1882 gelesen und als kleine Tabelle in web/geo/ abgelegt."""
    if src:
        pts: dict[str, list] = {}
        with src.open(encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                if r["lat"] and r["street"]:
                    pts.setdefault(r["street"], []).append((float(r["lat"]), float(r["lon"])))
        with HN1882.open("w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["street", "lat", "lon", "houses"])
            for st, ps in sorted(pts.items()):
                w.writerow([st, f"{sum(p[0] for p in ps) / len(ps):.6f}", f"{sum(p[1] for p in ps) / len(ps):.6f}", len(ps)])
    if not HN1882.exists():
        return {}
    return {r["street"].lower().replace("ß", "ss"): (float(r["lat"]), float(r["lon"]), int(r["houses"]))
            for r in csv.DictReader(HN1882.open(encoding="utf-8"))}


def streets(limit: int | None, hn1882: Path | None = None) -> None:
    GEO.mkdir(parents=True, exist_ok=True)
    table = table_1882(hn1882)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    todo = streets_in_data()
    out = []
    for i, ((muni, st), n) in enumerate(todo.most_common()):
        if limit and i >= limit:
            break
        if n < MIN_ENTRIES and not (st.lower() in table or (st.endswith("g") and (st + "asse").lower() in table)):
            out.append({"municipality": muni, "street_norm": st, "entries": n, "method": "selten", "lat": "", "lon": "", "osm_name": ""})
            continue
        hit, method = None, "none"
        for cand in (st, st + "asse" if st.endswith("g") else None):
            if cand and cand.lower() in table:
                lat, lon, _n = table[cand.lower()]
                hit, method = {"lat": lat, "lon": lon, "display_name": f"Hausnummern 1882: {cand}"}, "hn1882"
                break
        tries = [("free", {"q": f"{st}, {city_name(muni)}, Vaud"}), ("street", {"street": st, "city": city_name(muni)})]
        if n >= 20 and not re.match("(?i)" + ROAD + " ", st):  # häufige Namen ohne Vorsatz: Vorsätze ausprobieren
            tries += [("prefix", {"street": f"{pre} {st}", "city": city_name(muni)})
                      for pre in ("Rue du", "Rue de", "Rue de la", "Avenue de", "Avenue du", "Chemin de", "Place de la")]
        for method_name, params in tries:  # Lausanne: Namen ohne «Rue», frei zuerst
            if hit:
                break
            try:
                res = query(params, cache)
            except Exception as e:  # Netz: Eintrag bleibt offen, nächster Lauf versucht es wieder
                print(f"  Fehler {muni} / {st}: {e}")
                res = []
            res = [r for r in res if inside(float(r["lat"]), float(r["lon"])) and in_muni(r, muni) and road_matches(r, st)]
            if res:
                hit, method = res[0], method_name
                break
        out.append({"municipality": muni, "street_norm": st, "entries": n, "method": method,
                    "lat": f"{float(hit['lat']):.6f}" if hit else "", "lon": f"{float(hit['lon']):.6f}" if hit else "",
                    "osm_name": hit.get("display_name", "")[:120] if hit else ""})
        if i % 50 == 0:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"{i}/{len(todo)}")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    with (GEO / "streets.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(sorted(out, key=lambda r: (r["municipality"], r["street_norm"])))
    found = sum(1 for r in out if r["lat"])
    print(f"{found}/{len(out)} Strassen verortet ({sum(r['entries'] for r in out if r['lat'])} von "
          f"{sum(r['entries'] for r in out)} Einträgen) → {GEO / 'streets.csv'}")


def municipalities(ptt: Path) -> None:
    GEO.mkdir(parents=True, exist_ok=True)
    wanted = {r for f in sorted(p.name for p in CSV_DIR.glob("04_*.csv"))
              for r in (x["municipality"] for x in csv.DictReader((CSV_DIR / f).open(encoding="utf-8"))) if r}
    pts: dict[str, tuple[str, str]] = {}
    with gzip.open(ptt, "rt", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            m = r["municipality_1914"]
            if m in wanted and r["lat"] and (m not in pts or r["place_kind"] == "gemeinde_1914" and pts[m][2] != "gemeinde_1914"):
                pts[m] = (r["lat"], r["lon"], r["place_kind"])
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    for m in sorted(wanted - set(pts)):  # nicht im Telefonbuch: Nominatim
        res = [r for r in query({"q": f"{city_name(m)}, Vaud"}, cache)
               if 6.0 <= float(r["lon"]) <= 7.3 and 46.15 <= float(r["lat"]) <= 47.0]  # Gemeinden: ganzer Kanton Waadt
        if res:
            pts[m] = (f"{float(res[0]['lat']):.6f}", f"{float(res[0]['lon']):.6f}", "nominatim")
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    with (GEO / "municipalities.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["municipality", "lat", "lon"])
        for m in sorted(wanted):
            w.writerow([m, *pts.get(m, ("", ""))[:2]])
    print(f"{len(pts)}/{len(wanted)} Gemeinden mit Punkt; ohne: {sorted(wanted - set(pts))}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("streets")
    s.add_argument("--limit", type=int)
    s.add_argument("--hn1882", type=Path, help="bern-frueh/data/csv/07_hausnummern_1882.csv (erster Lauf)")
    m = sub.add_parser("municipalities")
    m.add_argument("--ptt", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "streets":
        streets(args.limit, args.hn1882)
    else:
        municipalities(args.ptt)


if __name__ == "__main__":
    main()
