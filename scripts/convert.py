"""Lesungen von qwen3.8 (data/qwen/<Jahr>/entries.csv) → Eintragsdateien im Schema von adressbuecher-aarau.

    python scripts/convert.py

Schreibt data/csv/04_entries.csv (Einwohner), 04_berufe.csv (Berufsregister), 03_sections.csv
(welche Seiten in welchen Teil gehen) und 10_authority_links.csv (leer: Normdaten verknüpft
«Vernetzte Schweiz» über die Einheiten, nicht dieses Repo).

Übernommen werden nur das Einwohnerverzeichnis und das Berufsregister der Stadt; Inserate (Seiten mit
weniger als zehn Einträgen), Vorspann, Behörden, Häuserverzeichnisse und Querverweise nicht.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QWEN = ROOT / "data" / "qwen"
CSV = ROOT / "data" / "csv"

FIELDS = [
    "entry_id", "volume", "page", "section", "line_from", "line_to", "entry_type", "citizen_flag",
    "dash_prefix", "surname", "surname_inherited", "alliance_name", "maiden_name", "forename", "title",
    "civil_status", "relation", "occupation_raw", "origin_raw", "origin_canton", "address_seq",
    "address_role", "street_raw", "building_no", "phone_flag", "heading", "parse_method",
    "parse_confidence", "residual", "text", "municipality", "qa_flags",
]
AUTH_FIELDS = [
    "entry_id", "kind", "volume", "surname", "forename", "occupation", "origin", "qid", "label", "birth",
    "death", "hls_id", "gnd", "wd_description", "wd_occupations", "evidence", "score", "n_candidates",
    "tier", "hls_origins", "hls_head", "hls_check",
]
METHOD = "qwen3.8-27b, Bild 2x"

# ── Aufbau der Bände ─────────────────────────────────────────────────────
# Seite = Seite im PDF bzw. Bildnummer der Lesung. Geprüft an den ersten und letzten Einträgen.
MUNICIPALITY = "Lausanne"
SECTIONS = {
    "1896": [("einwohner", 15, 217), ("berufe", 219, 290)],
    "1907": [("einwohner", 21, 294), ("berufe", 311, 411)],
}

MIN_ENTRIES = 10  # weniger Einträge auf einer Seite: Inserat oder Zwischenseite
NOT_ENTRY = re.compile(r"siehe auch|voir aussi|^\(?(?:Siehe|Voir)\b|Abkürzungen|Abréviations|"
                       r"alphabetischen Reihenfolge|Telephonzeichen|La lettre R\.", re.I)
FIRM = re.compile(r"&|\bCie\b|\bC°|\bGebr(?:\.|üder)|\bfrères\b|A\.-?G\.|\bAG\b|S\. ?A\.|Aktiengesellschaft|"
                  r"Société|Genossenschaft|Verein\b|Gesellschaft|Fabri(?:k|que)\b|Kasse\b|Caisse\b|Banque\b|"
                  r"Bank\b|Werke?\b|Erben\b|hoirie\b", re.I)
WIDOW = re.compile(r"\bWwe\.?|\bWitwe\b|\bWittwe\b|\bveuve\b", re.I)
DASH = re.compile(r"^\s*[—–-]")
LEAD = re.compile(r"^[\s*†§☎„\"'«»(]+")
SAME = re.compile(r"^(?:m\. ?a\.?|même adresse|dito|ditto|do\.?|id\.?|ebenda|ebd\.?)$", re.I)


def section_of(volume: str, page: int) -> str:
    for name, a, b in SECTIONS[volume]:
        if a <= page <= b:
            return name
    return ""


def own_surname(r: dict) -> str:
    """Familienname; ein vom Vorgänger geerbter Name, der zum Text nicht passt, wird ersetzt."""
    sn = LEAD.sub("", r["surname"]).strip()
    text = LEAD.sub("", r["text"])
    if r["dash_prefix"] == "1" and not DASH.match(text) and sn and sn not in text:
        return re.split(r"[,(]", text)[0].strip(" .")
    return sn


def clean_street(street: str, number: str) -> tuple[str, str]:
    """Strasse ohne Telefonzeichen und ohne doppelte Hausnummer; «Bärenplatz 29» → («Bärenplatz», «29»)."""
    for _ in range(2):  # «… R T 180»: erst die Telefonnummer, dann das R.
        street = re.sub(r"\s*(?:\bH\.|☎.*|\bT\s?\d+.*|\bR\.?\s*$|\bR?\s?T\.?\s*$)", "", street).strip(" ,.")
    number = number.strip(" ,.")
    if number:
        street = re.sub(rf"[\s,]+{re.escape(number)}\s*$", "", street)
    else:
        m = re.match(r"^(.*\D)[\s,]+(\d+\s?[a-z]?)$", street)
        if m:
            street, number = m.group(1).strip(" ,"), m.group(2).replace(" ", "")
    return street, number


def convert(volume: str) -> tuple[list[dict], Counter]:
    rows = list(csv.DictReader(open(QWEN / volume / "entries.csv", encoding="utf-8")))
    pages = Counter(int(r["page"]) for r in rows)
    out, stats = [], Counter()
    last = ("", "")  # Adresse des vorigen Eintrags, für «m. a.» (même adresse)
    for r in rows:
        page, seq = int(r["page"]), int(r["seq"])
        sec = section_of(volume, page)
        if not sec:
            stats["ausserhalb der Verzeichnisse"] += 1
            continue
        if pages[page] < MIN_ENTRIES:
            stats["Inserat- oder Zwischenseite"] += 1
            continue
        if NOT_ENTRY.search(r["text"]):
            stats["Querverweis oder Vorbemerkung"] += 1
            continue
        surname = own_surname(r)
        if not surname or len(surname.split()) > 4:
            stats["ohne Familienname"] += 1
            continue
        street, number = clean_street(r["street"], r["building_no"])
        if SAME.match(street):
            street, number = last
            stats["Adresse vom vorigen Eintrag"] += 1
        last = (street, number)
        flags = [f for f in r["qa_flags"].split(";") if f]
        firm = bool(FIRM.search(f"{surname} {r['forename']} {r['text'][:60]}")) and not WIDOW.search(r["text"])
        out.append({
            "entry_id": f"{volume}-{sec}-{page:03d}-{seq:03d}", "volume": volume, "page": page,
            "section": sec, "line_from": seq, "line_to": seq,
            "entry_type": "firma" if firm else "person", "citizen_flag": "",
            "dash_prefix": r["dash_prefix"], "surname": surname,
            "surname_inherited": "1" if r["dash_prefix"] == "1" and DASH.match(r["text"]) else "",
            "alliance_name": r["alliance_name"], "maiden_name": "", "forename": r["forename"].strip(" .,"),
            "title": r["title"], "civil_status": r["civil_status"], "relation": "",
            "occupation_raw": r["occupation"], "origin_raw": r["origin"], "origin_canton": "",
            "address_seq": "1", "address_role": "", "street_raw": street, "building_no": number,
            "phone_flag": "1" if r["phone"].strip() or "☎" in r["text"] else "", "heading": r["heading"],
            "parse_method": METHOD,
            "parse_confidence": "medium" if {"street_rare", "hyphen", "unreadable", "surname_split"} & set(flags)
            else "high",
            "residual": "", "text": r["text"], "municipality": MUNICIPALITY, "qa_flags": ";".join(flags),
        })
        stats[sec] += 1
    return out, stats


def main() -> None:
    entries, berufe, sections = [], [], []
    for volume in SECTIONS:
        rows, stats = convert(volume)
        entries += [r for r in rows if r["section"] == "einwohner"]
        berufe += [r for r in rows if r["section"] == "berufe"]
        sections += [{"volume": volume, "section": n, "page_from": a, "page_to": b} for n, a, b in SECTIONS[volume]]
        print(volume, dict(sorted(stats.items())))
    CSV.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (("04_entries.csv", entries, FIELDS), ("04_berufe.csv", berufe, FIELDS),
                               ("03_sections.csv", sections, ["volume", "section", "page_from", "page_to"]),
                               ("10_authority_links.csv", [], AUTH_FIELDS)):
        with open(CSV / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
