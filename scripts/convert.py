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

import communes

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
    "1907": [("einwohner", 21, 294), ("berufe", 311, 411), ("gemeinden", 670, 962)],
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


# Kopfzeilen einer Gemeinde: Einwohnerzahl, Post, Bahn, Bezirksbehörden ohne Person
COMMUNE_HEAD = re.compile(r"\d[\d' ]*\s*hab(?:itants|\.)|^(?:Gare|Dépôt de poste|Bureau de poste|Altitude|Poste,|"
                          r"Cercles\s*:|Monuments|Hameau de)", re.I)


def split_persons(r: dict) -> list[dict]:
    """«Bovay, Burdet» / «Sylvain, Octave»: eine Zeile der Lesung mit mehreren Personen wird geteilt."""
    sn, fn = r["surname"].split(", "), r["forename"].split(", ")
    if len(sn) < 2 or len(sn) != len(fn):
        return [r]
    return [{**r, "surname": a, "forename": b, "seq": f"{r['seq']}.{i}"} for i, (a, b) in enumerate(zip(sn, fn), 1)]


# «Municipaux, Perey Auguste — Chevalley Louis — Wagnière Gustave»: Namen nach Gedankenstrich, die die Lesung
# nicht als eigene Zeile ausgibt. Nur Teile der Form «Name[-Allianz] Vorname[, Adresse]».
DASH_NAME = re.compile(r"^(?:(?:à|au|aux)\s+)?([A-ZÉÈ][\w'’éèêàâüöäçï]+(?:-[A-ZÉÈ][\w'’éèêàâüöäçï]+)?)\s+"
                       r"([A-ZÉÈ][\w'’éèêàâüöäçï.]*(?:-[A-ZÉÈ][\w'’éèêàâüöäçï.]*)?\.?)(?:\s*,\s*(.*))?$")


def dash_persons(rows: list[dict]) -> list[dict]:
    """Ergänzt Personen aus Gedankenstrich-Listen, die in den folgenden Zeilen der Lesung fehlen."""
    out = []
    for i, r in enumerate(rows):
        out.append(r)
        parts = [x.strip(" .") for x in re.split(r"\s+[—–]\s+", r["text"])]
        if len(parts) < 3:
            continue
        # Familienname und Vornamen-Anfang ohne Zeichen und Marken («Ch. T» = «Ch»): Perey Auguste ≠ Perey Albert
        who = lambda sur, fn: (sur.split("-")[0].lower(), re.sub(r"\b[RT]\b|\W", "", fn)[:3].lower())
        near = {who(x["surname"], x["forename"]) for x in rows[i:i + len(parts) + 2]}
        for k, part in enumerate(parts[1:], 1):
            m = DASH_NAME.match(re.sub(r"\.?\s*\bR\b\.?\s*T?\b.*$|\s+T\s*\d*$", "", part))
            if not m or who(m.group(1), m.group(2)) in near:
                continue
            sur, fn, rest = m.group(1), m.group(2), (m.group(3) or "")
            out.append({**r, "seq": f"{r['seq']}.d{k}", "text": part, "surname": sur.split("-")[0],
                        "alliance_name": sur.split("-", 1)[1] if "-" in sur else "", "forename": fn,
                        "street": rest, "building_no": "", "phone": "", "dash_prefix": "0",
                        "qa_flags": "aus_liste"})
            near.add(who(sur, fn))
    return out


def muni_finder(volume: str, rows: list[dict]):
    """Gemeinde einer Zeile im Teil «gemeinden» (nur 1907): die letzte Überschrift davor."""
    if not any(n == "gemeinden" for n, _, _ in SECTIONS[volume]):
        return lambda page, seq: MUNICIPALITY
    st = communes.starts(rows, communes.load_ref())

    def find(page: int, seq: int) -> str:
        cur = ""
        for p, s, m, _ in st:
            if (p, s) <= (page, seq):
                cur = m
        return cur
    return find


# Cercle de Montreux 1907: nach den Köpfen der drei Gemeinden (S. 919) folgt EIN Berufsverzeichnis für
# den ganzen Kreis (S. 920–938). Die Gemeinde kommt dort aus dem Ortsteil in der Adresse; ohne Ortsteil
# («Grand'Rue», «av. du Kursaal») bleibt der Eintrag ohne Gemeinde.
MONTREUX_TRADES = ((920, 1), (939, 46))
MONTREUX_PARTS = {
    "Le Châtelard-Montreux": r"Clarens|Vernex|Chailly|Brent|Tavel|Baugy|Chernex|Sonzier|Pertit|Les Avants|Sâles|"
                             r"Burier|Châtelard|Rouvenaz|Tavel",
    "Les Planches": r"Territet|Glion|Collonges?|Planches|Bon[- ]Port|Caux|Veraye",
    "Veytaux": r"Veytaux|Chillon|Grandchamp",
}


def montreux(text: str) -> str:
    found = {m for m, rx in MONTREUX_PARTS.items() if re.search(rf"\b(?:{rx})\b", text)}
    return found.pop() if len(found) == 1 else ""


def convert(volume: str) -> tuple[list[dict], Counter]:
    rows = list(csv.DictReader(open(QWEN / volume / "entries.csv", encoding="utf-8")))
    pages = Counter(int(r["page"]) for r in rows)
    muni_of = muni_finder(volume, rows)
    rows = [x for r in rows for x in split_persons(r)]
    if any(n == "gemeinden" for n, _, _ in SECTIONS[volume]):
        rows = dash_persons(rows)
    out, stats = [], Counter()
    last = ("", "")  # Adresse des vorigen Eintrags, für «m. a.» (même adresse)
    for r in rows:
        page, seq = int(r["page"]), int(r["seq"].split(".")[0])
        sec = section_of(volume, page)
        muni = MUNICIPALITY
        if sec == "gemeinden":
            muni = muni_of(page, seq)
            if MONTREUX_TRADES[0] <= (page, seq) <= MONTREUX_TRADES[1]:
                muni = montreux(r["text"])
                if not muni:
                    stats["Montreux ohne Ortsteil"] += 1
                    continue
            if not muni or COMMUNE_HEAD.search(r["text"]):
                stats["Bezirkskopf oder Gemeindekopf"] += 1
                continue
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
            "entry_id": f"{volume}-{sec}-{page:03d}-{seq:03d}" + ("-" + r["seq"].split(".", 1)[1].replace(".", "-") if "." in r["seq"] else ""),
            "volume": volume, "page": page,
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
            "residual": "", "text": r["text"], "municipality": muni, "qa_flags": ";".join(flags),
        })
        stats[sec] += 1
    return out, stats


def main() -> None:
    entries, berufe, gemeinden, sections = [], [], [], []
    for volume in SECTIONS:
        rows, stats = convert(volume)
        entries += [r for r in rows if r["section"] == "einwohner"]
        berufe += [r for r in rows if r["section"] == "berufe"]
        gemeinden += [r for r in rows if r["section"] == "gemeinden"]
        sections += [{"volume": volume, "section": n, "page_from": a, "page_to": b} for n, a, b in SECTIONS[volume]]
        print(volume, dict(sorted(stats.items())))
    CSV.mkdir(parents=True, exist_ok=True)
    for name, rows, fields in (("04_entries.csv", entries, FIELDS), ("04_berufe.csv", berufe, FIELDS),
                               ("04_gemeinden.csv", gemeinden, FIELDS),
                               ("03_sections.csv", sections, ["volume", "section", "page_from", "page_to"]),
                               ("10_authority_links.csv", [], AUTH_FIELDS)):
        with open(CSV / name, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
