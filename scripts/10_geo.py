"""10_geo.py — Strassen und Gemeinden für die Karte verorten.

    python scripts/10_geo.py streets      # Nominatim, 1 Anfrage/s, Cache in web/geo/
    python scripts/10_geo.py municipalities --ptt ~/Repos/vernetzte-schweiz/data/norm/ptt_entries.csv.gz

Lausanne: die Strassen stehen meist ohne «Rue»/«Avenue» («Martheray», «Bourg»); Nominatim findet sie frei
(«Martheray, Lausanne, Vaud»). Schreibvarianten derselben Strasse («Ch. de Bourg», «Chemin de Bourg») teilen einen Punkt.

`streets` normalisiert die gedruckten Strassennamen (ß → ss, «str.» → «strasse», «g.» → «gasse»,
«pl.» → «platz») und sucht jede Strasse einmal je Gemeinde in OpenStreetMap: zuerst als Strasse
(`street=…&city=…`), dann frei («Name, Lausanne, Vaud»). Treffer ausserhalb der Gemeinde Lausanne
werden verworfen. Ergebnis: web/geo/streets.csv; jede Antwort liegt in web/geo/nominatim_cache.json,
sodass ein zweiter Lauf nur neue Namen kostet. Strassennamen von 1900/1910 sind nicht immer die
heutigen; was OSM nicht kennt, bleibt ohne Punkt (`method = none`) und kann in
web/geo/streets_manual.csv (municipality, street_norm, lat, lon, note) von Hand gesetzt werden.

`todo` schreibt die Hand-Liste web/geo/streets_manual.csv: jede Strasse ohne Punkt mit ≥ 10 Einträgen,
Schreibvarianten zusammen, nach Einträgen sortiert. lat/lon (WGS84), source und note von Hand füllen
(Anleitung: docs/STRASSEN_VON_HAND.md); 90_seite.py und 92_karte.py lesen die Datei direkt, für alle Varianten.

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
          (r"(?i)^pt\.?\s+", "Petit "), (r"(?i)^prom\.?\s+", "Promenade "), (r"(?i)^ro(ute)?\.?\s+", "Route "),
          (r"(?i)^p\.\s*(?=(ch[eê]ne|rocher)\b)", "Petit "), (r"(?i)^p\.\s*", "Place "),
          (r"^(b|[Bb]oul|[Bb]d)\.\s*", "Boulevard "),  # «B. Palud» (Bureau?) gross geschrieben: nicht  # «q. Tunnel»: quai oder quartier? offen gelassen, bleibt für die Hand-Liste
          (r"(?i)^aven?\.?\s+", "Avenue "), (r"(?i)^rte\.?\s+", "Route "),
          (r"(?i)^sq\.?\s+", "Square "), (r"(?i)^gd\.?\s+", "Grand "), (r"(?i)^che[mn]\.?\s+", "Chemin "),
          (r"(?i)^esc\.?\s+", "Escaliers "), (r"(?i)^cité derr\.?$", "Cité Derrière")]


def norm_street(s: str) -> str:
    """Gedruckte Strasse → Schlüssel. Lausanne: Abkürzungen ausschreiben («r.» → Rue, «av.» → Avenue,
    «pl.» → Place, «Gr.» → Grand), Bindestriche wie Leerzeichen («Pré-du-Marché» = «Pré du Marché»)."""
    s = re.sub(r"\s+", " ", s.replace("ß", "ss")).strip(" ,;.")
    if "," in s:  # «Les Rossinières, av. Ruchonnet»: Hausname, Strasse → der Teil mit Strassen-Vorsatz, sonst der letzte
        parts = [p.strip(" .") for p in s.split(",") if p.strip(" .")]
        road = [p for p in parts if any(re.match(pat, p) for pat, _ in PREFIX[:-1])]
        s = (road or parts or [s])[-1]
    s = re.sub(r"^(\w{1,5})\.-", r"\1. ", s)  # «Esc.-du-Marché», «Ch.-de-Bourg»
    for pat, rep in PREFIX:
        s = re.sub(pat, rep, s)
    s = re.sub(r"(?i)\b(gr\.|gd\b\.?)\s*", "Grand ", s)
    s = re.sub(r"(?<!St)-(?!\d)", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" .")
    return s[:1].upper() + s[1:]


def loose(st: str) -> str:
    """Schlüssel für Schreibvarianten derselben Strasse: ohne Akzente, Artikel und Bindestriche
    («Square de Georgette» = «Square Georgette», «Avenue du Simplon» = «Avenue Simplon»)."""
    return re.sub(r"\b(de la|de l|des|du|de|d|la|le|les)\b ?", "", _f(st)).strip()


MANUAL = Path("web/geo/streets_manual.csv")


def manual_points() -> dict[tuple[str, str], tuple[float, float]]:
    """Von Hand gesetzte Punkte (web/geo/streets_manual.csv) → (Gemeinde, loose(Strasse)) → (lat, lon).
    Gilt für alle Schreibvarianten der Strasse."""
    if not MANUAL.exists():
        return {}
    return {(r["municipality"], loose(r["street_norm"])): (float(r["lat"]), float(r["lon"]))
            for r in csv.DictReader(MANUAL.open(encoding="utf-8")) if r.get("lat", "").strip()}


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
PREFIX_TRIES = ("Rue du", "Rue de", "Rue de la", "Avenue de", "Avenue du", "Chemin de", "Place de la")


def bare(st: str) -> str:
    return re.sub("^" + ROAD + r" ((de la|de l|des|du|de|d) )?", "", _f(st))


def lookup(muni: str, st: str, n: int, cache: dict) -> tuple[dict | None, str]:
    """Eine Schreibweise bei Nominatim suchen; nur Treffer in der Gemeinde mit passendem Strassennamen."""
    tries = [("free", {"q": f"{st}, {city_name(muni)}, Vaud"}), ("street", {"street": st, "city": city_name(muni)})]
    if n >= 20 and not re.match("(?i)" + ROAD + " ", st):  # häufige Namen ohne Vorsatz: Vorsätze ausprobieren
        tries += [("prefix", {"street": f"{pre} {st}", "city": city_name(muni)}) for pre in PREFIX_TRIES]
    for method, params in tries:  # Lausanne: Namen ohne «Rue», frei zuerst
        try:
            res = query(params, cache)
        except Exception as e:  # Netz: Eintrag bleibt offen, nächster Lauf versucht es wieder
            print(f"  Fehler {muni} / {st}: {e}")
            res = []
        res = [r for r in res if inside(float(r["lat"]), float(r["lon"])) and in_muni(r, muni)]
        ok = [r for r in res if road_matches(r, st)]
        if ok:
            return ok[0], method
    return None, "none"


def other_type(muni: str, st: str, taken: set[str], cache: dict) -> dict | None:
    """«Avenue Simplon» heute «Rue du Simplon»: derselbe Name mit anderem Vorsatz, aus den schon gestellten
    Anfragen. Nur wenn der Name eindeutig ist (kein anderer Vorsatz desselben Namens in den Adressbüchern)
    und nur eine Strasse dieses Namens in der Gemeinde liegt."""
    b = bare(st)
    if len(b) < 4 or b in taken:
        return None
    name = re.sub(r"(?i)^" + ROAD + r" ((de la|de l'|des|du|de|d') ?)?", "", st).strip()
    roads = {}
    for params in ({"q": f"{st}, {city_name(muni)}, Vaud"}, {"q": f"{name}, {city_name(muni)}, Vaud"}):
        try:
            res = query(params, cache)
        except Exception as e:
            print(f"  Fehler {muni} / {name}: {e}")
            res = []
        for r in res:
            if inside(float(r["lat"]), float(r["lon"])) and in_muni(r, muni):
                road = _f(r.get("display_name", "").split(",")[0])
                if re.fullmatch(ROAD + r" ((de la|de l|des|du|de|d) )?" + re.escape(b), road):
                    roads.setdefault(road, r)
    return next(iter(roads.values())) if len(roads) == 1 else None


def streets(limit: int | None) -> None:
    """Je Strasse (Schreibvarianten zusammen, siehe loose) einen Punkt: von Hand (streets_manual.csv),
    sonst Nominatim mit der häufigsten Schreibweise, dann den anderen, zuletzt derselbe Name mit anderem Vorsatz."""
    GEO.mkdir(parents=True, exist_ok=True)
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    manual = manual_points()
    todo = streets_in_data()
    groups: dict[tuple[str, str], list[tuple[str, int]]] = {}
    for (muni, st), n in todo.most_common():
        groups.setdefault((muni, loose(st)), []).append((st, n))
    # Namen, die in den Adressbüchern mit mehr als einem Vorsatz vorkommen («Rue de Bourg», «Chemin de Bourg»)
    types: dict[tuple[str, str], set] = {}
    for (muni, st), n in todo.items():
        if n >= MIN_ENTRIES and re.match("(?i)" + ROAD + " ", st):
            types.setdefault((muni, bare(st)), set()).add(_f(st).split(" ")[0])
    ambiguous = {k for k, v in types.items() if len(v) > 1}
    out = []
    order = sorted(groups.items(), key=lambda kv: -sum(n for _, n in kv[1]))
    for i, ((muni, key), members) in enumerate(order):
        if limit and i >= limit:
            break
        total = sum(n for _, n in members)
        hit, method = None, "selten"
        if (muni, key) in manual:
            lat, lon = manual[(muni, key)]
            hit, method = {"lat": lat, "lon": lon, "display_name": "à la main (streets_manual.csv)"}, "manual"
        elif total >= MIN_ENTRIES:
            method = "none"
            for st, n in members:
                if n < MIN_ENTRIES and st != members[0][0]:
                    continue
                hit, method = lookup(muni, st, max(n, total), cache)
                if hit:
                    break
            if not hit and total >= 20:
                st = members[0][0]
                taken = {b for (m, b) in ambiguous if m == muni}
                hit = other_type(muni, st, taken, cache)
                method = "autre_vorsatz" if hit else "none"
        for st, n in members:
            out.append({"municipality": muni, "street_norm": st, "entries": n, "method": method,
                        "lat": f"{float(hit['lat']):.6f}" if hit else "", "lon": f"{float(hit['lon']):.6f}" if hit else "",
                        "osm_name": hit.get("display_name", "")[:120] if hit else ""})
        if i % 50 == 0:
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"{i}/{len(order)}", flush=True)
    CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    with (GEO / "streets.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(sorted(out, key=lambda r: (r["municipality"], r["street_norm"])))
    found = sum(1 for r in out if r["lat"])
    print(f"{found}/{len(out)} Strassen verortet ({sum(r['entries'] for r in out if r['lat'])} von "
          f"{sum(r['entries'] for r in out)} Einträgen) → {GEO / 'streets.csv'}")


def todo(min_entries: int) -> None:
    """Hand-Liste: web/geo/streets_manual.csv mit jeder Strasse ohne Punkt (≥ min_entries Einträge, Varianten
    zusammen), nach Einträgen sortiert. Schon gesetzte Zeilen (lat/lon, source, note) bleiben erhalten."""
    keep = {}
    if MANUAL.exists():
        for r in csv.DictReader(MANUAL.open(encoding="utf-8")):
            keep[(r["municipality"], loose(r["street_norm"]))] = r
    groups: dict[tuple[str, str], list] = {}
    for r in csv.DictReader((GEO / "streets.csv").open(encoding="utf-8")):
        groups.setdefault((r["municipality"], loose(r["street_norm"])), []).append(r)
    rows = []
    for k, members in groups.items():
        members.sort(key=lambda r: -int(r["entries"]))
        total = sum(int(r["entries"]) for r in members)
        old = keep.pop(k, None)
        if old is None and (total < min_entries or any(r["lat"] and r["method"] != "manual" for r in members)):
            continue
        rows.append({"municipality": k[0], "street_norm": old["street_norm"] if old else members[0]["street_norm"],
                     "entries": total, "variants": " | ".join(f"{r['street_norm']} ({r['entries']})" for r in members[:5]),
                     "lat": old["lat"] if old else "", "lon": old["lon"] if old else "",
                     "source": old["source"] if old else "", "note": old["note"] if old else ""})
    rows += [{**r, "entries": 0} for r in keep.values()]  # gesetzte Zeilen, deren Strasse nicht mehr vorkommt
    rows.sort(key=lambda r: (-int(r["entries"]), r["street_norm"]))
    with MANUAL.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["municipality", "street_norm", "entries", "variants", "lat", "lon", "source", "note"],
                           extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} Strassen in {MANUAL} ({sum(1 for r in rows if r['lat'])} mit Punkt; "
          f"{sum(int(r['entries']) for r in rows if not r['lat'])} Einträge warten)")


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
    t = sub.add_parser("todo")
    t.add_argument("--min", type=int, default=10)
    m = sub.add_parser("municipalities")
    m.add_argument("--ptt", type=Path, required=True)
    args = ap.parse_args()
    if args.cmd == "streets":
        streets(args.limit)
    elif args.cmd == "todo":
        todo(args.min)
    else:
        municipalities(args.ptt)


if __name__ == "__main__":
    main()
