"""Gemeinden des Kantons Waadt im Indicateur vaudois 1907 (S. 670–962): welche Gemeinde ab welcher Zeile gilt.

Jede Gemeinde beginnt mit ihrem Namen in Versalien und einer Zeile «… habitants — Altitude …».
Davor stehen die Bezirke («DISTRICT D'AUBONNE»), in jedem Bezirk die Gemeinden alphabetisch.
Der Name im Buch ist oft kürzer als der amtliche von 1914 («ROMANEL» → Romanel-sur-Lausanne);
gesucht wird darum nur unter den Gemeinden des laufenden Bezirks.
"""

from __future__ import annotations

import csv
import difflib
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT / "data" / "ref" / "municipalities_vd_1914.csv"

PAGES = (670, 962)
HABITANTS = re.compile(r"\d[\d' ]*\s*hab(?:itants|\.)")
# auch als Kolumnentitel: «DISTRICT DE MORGES: ÉCHICHENS, ÉCUBLENS», «DISTRICT D'AVENCHES : VILLE D'AVENCHES»
DISTRICT = re.compile(r"^DISTRICT\s+(?:DE\s+LA\s+|DU\s+|DE\s+|D')([^:.]+?)\s*(?:[:.].*)?$", re.I)
# Ortsteile und Kreise, die als eigene Überschrift erscheinen, mit ihrer Gemeinde von 1914
PARTS = {
    "lesbioux": "L'Abbaye", "bioux": "L'Abbaye", "lepont": "L'Abbaye", "pont": "L'Abbaye",
    "orient": "Le Chenit", "lesentier": "Le Chenit", "sentier": "Le Chenit", "lebrassus": "Le Chenit",
    "brassus": "Le Chenit", "lecharbonnieres": "Le Lieu", "lescharbonnieres": "Le Lieu", "charbonnieres": "Le Lieu",
    "cuves": "Rossinière", "lechatelard": "Le Châtelard-Montreux", "chatelard": "Le Châtelard-Montreux",
    "lesplanches": "Les Planches", "planches": "Les Planches", "veytaux": "Veytaux",
    "montlegrand": "Mont-sur-Rolle", "montlepetit": "Mont-sur-Rolle",
    "chardonnay": "Chardonney-sur-Morges", "oulenssurmoudon": "Oulens-sur-Lucens",
}
STOP = {"de", "des", "du", "la", "le", "les", "l", "d", "sur", "pres", "sous", "ville", "village", "cercle"}


def key(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.replace("œ", "oe").replace("Œ", "OE").lower()).encode("ascii", "ignore").decode()
    s = re.sub(r"\bste?\b-?", lambda m: "sainte" if m.group(0).startswith("ste") else "saint", s)
    return re.sub(r"[^a-z]", "", s)


def core(s: str) -> str:
    """Name ohne Zusatz, Klammer und Kreis-Nummer: «1° Le Châtelard.» → «lechatelard», «ROMANEL» → «romanel»."""
    s = re.sub(r"^\s*\d+\s*[°o.]\s*", "", s)
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"^(VILLE|CERCLE|VILLAGE)\s+(DE\s+|D'|DU\s+)?", "", s, flags=re.I)
    s = re.sub(r"^(Village|Hameau)\s+", "", s)
    s = re.split(r" — |,| et ", s)[0]
    return key(s.strip(" ."))


def load_ref() -> dict[str, list[str]]:
    by_district: dict[str, list[str]] = {}
    for r in csv.DictReader(open(REF, encoding="utf-8")):
        by_district.setdefault(r["district"], []).append(r["name"])
    return by_district


def match(name: str, district: str, ref: dict[str, list[str]]) -> str:
    """Amtlicher Name 1914 der Gemeinde «name» im Bezirk «district» (leer, wenn keiner passt)."""
    k = core(name)
    if not k:
        return ""
    if k in PARTS:
        return PARTS[k]
    pool = ref.get(district) or [n for ns in ref.values() for n in ns]
    keys = {key(re.sub(r"\s*\(.*?\)", "", n)): n for n in pool}
    if k in keys:
        return keys[k]
    # der Reihe nach: «Romanel» → «Romanel-sur-Lausanne» (Anfang), «Tour-de-Peilz» → «La Tour-de-Peilz»
    # (ganzes Schlusswort, nicht «Oulens» → «Boulens»), dann ähnliche Schreibung («Roopraz» → «Ropraz»)
    tails = {key(re.sub(r"\s*\(.*?\)", "", n).split(" ", 1)[-1]): n for n in pool if " " in n}
    for found in ([n for kk, n in keys.items() if kk.startswith(k)], [n for kk, n in tails.items() if kk == k],
                  [n for kk, n in keys.items() if k.startswith(kk) and len(kk) > 4]):
        if len(found) == 1:
            return found[0]
    close = difflib.get_close_matches(k, list(keys), n=1, cutoff=0.8)
    return keys[close[0]] if close else ""


def starts(rows: list[dict], ref: dict[str, list[str]]) -> list[tuple[int, int, str, str]]:
    """[(Seite, Laufnummer, Gemeinde 1914, Name im Buch)] in Leserichtung; Gemeinde leer = Bezirkskopf."""
    dkeys = {key(re.sub(r"^District (de la |du |de |d')", "", d)): d for d in ref}  # «vallee», «echallens»
    out, district = [], "District d'Aigle"
    rows = [r for r in rows if PAGES[0] <= int(r["page"]) <= PAGES[1]]
    for i, r in enumerate(rows):
        for cell in (r["heading"], r["text"]):
            m = DISTRICT.match(cell.strip())
            if m and key(m.group(1)) in dkeys:
                district = dkeys[key(m.group(1))]
        for cell in (r["text"], r["heading"]):
            part = re.match(r"^\s*(?:\d\s*°\s*)?(Le Châtelard|Les Planches|Veytaux|Village [\wÀ-ÿ' -]+|Le Pont|Orient|"
                            r"Le Sentier|Le Brassus|Les Charbonnières|Cuves)\.?\s*$", cell)
            muni = PARTS.get(core(part.group(1)), "") if part else ""
            if muni and not (out and out[-1][2] == muni):
                out.append((int(r["page"]), int(r["seq"]), muni, part.group(1)))
                break
        if not HABITANTS.search(r["text"]):
            continue
        cands = [r["heading"]] + [rows[j]["text"] for j in range(i - 1, max(i - 4, -1), -1)] \
            + [rows[j]["heading"] for j in range(i - 1, max(i - 4, -1), -1)]
        villes = [m.group(0) for c in cands[:2] if c for m in [re.search(r"VILLE\s+(?:DE\s+|D')[^,:]+", c)] if m]
        if villes:  # «DISTRICT D'AVENCHES : VILLE D'AVENCHES»
            out.append((int(r["page"]), int(r["seq"]), match(villes[0], district, ref), villes[0]))
            continue
        if any(DISTRICT.match((c or "").strip()) for c in cands[:2]):
            out.append((int(r["page"]), int(r["seq"]), "", district))  # Bezirkskopf: keine Gemeinde
            continue
        # Gemeindename: Versalien am Anfang («BUSSY-sur-MOUDON», «St-SAPHORIN») oder ein bekannter Ortsteil
        caps = [c for c in cands if c and (re.match(r"^\s*(?:\d\s*°\s*)?(?:St-|Ste-|LE |LA |LES |L')?[A-ZÀ-ÖØ-Þ]{2,}", c)
                                           or core(c) in PARTS)]
        caps = [c for c in caps if not re.match(r"^(HORLOGERIE|NOTICE|DISTRICT)\b", c)]
        name = caps[0] if caps else ""
        muni = match(name, district, ref) if name else ""
        out.append((int(r["page"]), int(r["seq"]), muni, name or "?"))
    return out
