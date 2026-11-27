"""89_suche.py — Startseite mit Suche über alle Bände und Eintragsseiten (scripts/site_search.py), Oberfläche französisch.

    python scripts/89_suche.py --out _site

Nimmt die Tabellen der Kontrollseite (scripts/90_seite.py: TABS und load_rows(), mit Telefon, anderen Bänden und
Normdaten) und die Strassen- und Gemeindepunkte aus web/geo/ (WGS84, wie 10_geo.py sie schreibt). Die Kontrollseite
selbst liegt unter korrektur/.

Die Zellformate von Lausanne weichen von site_search.std_links() ab (other_volume «Stufe|Band|entry_id|…», authority
«Stufe|Label|Lebensdaten|HLS|QID|GND|…»); Links und andere Bände baut darum dieses Skript, mit französischen Texten.
Im Teil «Communes vaudoises» ist die Gemeinde das Gebiet; Strassen dort tragen die Gemeinde im Namen («Grand'Rue
(Vevey)»), damit gleichnamige Strassen verschiedener Gemeinden nicht zusammenfallen, und liegen auf dem Gemeindepunkt.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import site_nav  # noqa: E402
import site_search  # noqa: E402

K = importlib.import_module("90_seite")

CITY = {
    "key": "lausanne", "name": "Lausanne", "span": "1896–1907", "lang": "fr",
    "title": "Indicateur vaudois 1896 et 1907 : Lausanne et communes vaudoises",
    "lead": "Habitants, registre professionnel et autres communes du canton de Vaud, d'après l'Indicateur vaudois 1896 "
            "et 1907, lus par machine et découpés en champs. La recherche porte sur tous les volumes.",
    "tagline": "Indicateur vaudois · Habitants · Professions · Communes",
    "repo": K.REPO_URL, "center": [46.5226, 6.6332],
    "korr": "korrektur/?tab={part}&vol={vol}&q={id}",
    "nav": [["karte.html", "Carte : communes et rues"]],
    "note": "Source : Indicateur vaudois 1896 et 1907 (BCU Lausanne, cote 1C 478, numérisé chez Scriptorium). Texte lu "
            "par qwen3.8 (Université de Berne), sans correction manuelle. En 1907, les communes vaudoises "
            "(images 670–962) ; la commune sert de « quartier ».",
    "page_note": "Les images ne sont que liées (conditions de réutilisation non clarifiées) ; « page » est le numéro "
                 "d'image chez Scriptorium.",
    "parts": {k: label for k, label, *_ in K.TABS},
    "volumes": K.VOLUMES,
}
CORE = {"entry_id", "volume", "page", "surname", "forename", "alliance_name", "maiden_name", "occupation_raw",
        "street_raw", "building_no", "text", "telefon", "other_volume", "authority", "zeitreise", "street_key",
        "municipality", "title", "heading", "origin_raw"}
HOW = {"nummer": "même numéro et même nom", "sicher": "Vernetzte Schweiz : sûr",
       "wahrscheinlich": "Vernetzte Schweiz : probable", "möglich": "Vernetzte Schweiz : possible (nom seul)",
       "name": "seule personne de ce nom et prénom dans l'annuaire de la commune"}
TIER = {"nummer": "numéro", "sicher": "sûr", "wahrscheinlich": "probable", "möglich": "possible", "name": "nom"}


def geo() -> tuple[dict[tuple[str, str], tuple[float, float]], dict[str, tuple[float, float]]]:
    """(Gemeinde, Strassenschlüssel) → (lat, lon) und Gemeinde → (lat, lon), wie load_geo() in 90_seite.py, aber WGS84."""
    streets, munis = {}, {}
    p = Path("web/geo/municipalities.csv")
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            if r["lat"]:
                munis[r["municipality"]] = (float(r["lat"]), float(r["lon"]))
    manual = K.manual_points()
    p = Path("web/geo/streets.csv")
    if p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            pt = manual.get((r["municipality"], K.loose(r["street_norm"])))
            if pt:
                streets[(r["municipality"], r["street_norm"])] = pt
            elif r["lat"]:
                streets[(r["municipality"], r["street_norm"])] = (float(r["lat"]), float(r["lon"]))
    return streets, munis


def links_of(r: dict, vol: str) -> tuple[list, list]:
    links, related = [], []
    tel = r.get("telefon", "")
    if tel:
        how, year, name, st, phone, eid, img = (tel.split("|") + [""] * 7)[:7]
        note = ", ".join(x for x in (name, st, f"n° {phone}" if phone else "") if x)
        note = f"{note} · lien : {HOW.get(how, how)}"
        links.append(["tel", f"Annuaire téléphonique {year}", f"{site_search.VS}#/e/{eid}" if eid else "", note])
        if img:
            links.append(["img", f"Page de l'annuaire téléphonique {year}", img, "Archives PTT"])
    auth = r.get("authority", "")
    if auth:
        tier, label, life, hls, qid, gnd, field, note = (auth.split("|") + [""] * 8)[:8]
        cand = f"candidat {TIER.get(tier, tier)}, non vérifié"
        if qid:
            links.append(["wd", label or qid, f"https://www.wikidata.org/wiki/{qid}", f"{life} · Wikidata · {cand}"])
        if hls:
            links.append(["hls", f"DHS {hls}", f"https://hls-dhs-dss.ch/fr/articles/{hls}/",
                          f"Dictionnaire historique de la Suisse · {cand}"])
        if gnd:
            links.append(["ext", f"GND {gnd}", f"https://d-nb.info/gnd/{gnd}", cand])
    ov = r.get("other_volume", "")
    if ov:
        tier, other, oid = (ov.split("|") + [""] * 3)[:3]
        if oid:
            related.append([other, tier, oid])
    return links, related


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    streets, munis = geo()
    labels = {**site_nav.LABELS["fr"], **K.LABELS, "street_raw": "Rue (imprimée)"}
    rows = K.load_rows()  # erweitert die Spalten in K.TABS um weitere CSV-Spalten
    recs = []
    for key, _label, _f, cols in K.TABS:
        for vol in sorted(rows):
            for row in rows[vol][key]:
                r = dict(zip(cols, row))
                muni = r.get("municipality") or "Lausanne"
                sk = r.get("street_key", "")
                g = streets.get((muni, sk)) if sk else None
                street = sk or r.get("street_raw", "")
                if key == "gemeinden":
                    if street:
                        street = f"{street} ({muni})"
                    g = g or munis.get(muni)
                links, related = links_of(r, vol)
                page = r.get("page", "")
                fields = [(c, r.get(c, "")) for c in cols if c not in CORE]
                if r.get("street_raw") and r["street_raw"] != sk:
                    fields.insert(0, ("street_raw", r["street_raw"]))
                if key == "berufe" and r.get("origin_raw"):  # hier «Complément», keine Herkunft
                    fields.insert(0, ("origin_raw", r["origin_raw"]))
                recs.append({
                    "id": r["entry_id"], "vol": vol, "year": int(vol), "part": key,
                    "name": r.get("surname", ""), "forename": r.get("forename", ""), "alliance": r.get("alliance_name", ""),
                    "maiden": r.get("maiden_name", ""), "occupation": r.get("occupation_raw", ""),
                    "street": street, "no": r.get("building_no", ""),
                    "area": muni if key == "gemeinden" else "",
                    "origin": "" if key == "berufe" else r.get("origin_raw", ""), "title": r.get("title", ""), "heading": r.get("heading", ""),
                    "text": r.get("text", ""), "page": page,
                    "page_url": (f"https://www.scriptorium.ch/zoom/{K.SCRIPTORIUM[vol]}/view?page={page}&p=separate"
                                 if page and vol in K.SCRIPTORIUM else ""),
                    "lat": g[0] if g else None, "lon": g[1] if g else None,
                    "fields": fields, "links": links, "related": related,
                })
    site_search.build(args.out, city=CITY, records=recs, labels=labels)


if __name__ == "__main__":
    main()
