"""90_seite.py — die Einträge als durchsuchbare statische Seite (GitHub Pages), Oberfläche französisch.

    python scripts/90_seite.py --out _site

Schreibt `index.html` und je Band `data/<Band>.json` nach --out; die Seite lädt einen Band erst, wenn er gebraucht
wird (zuerst 1907), weil beide zusammen rund 12 MB wären.

Quellen: data/csv/04_entries.csv, 04_berufe.csv, data/review/flags.csv (falls vorhanden) und die Verknüpfungen in
web/ (80_telefon.py, 81_baende.py, 82_normdaten.py, 10_geo.py). `page` ist die Bildnummer im IIIF-Manifest von
Scriptorium (BCU Lausanne); jede Zeile verlinkt den Viewer auf dieser Seite. Bilder werden nicht eingebettet, weil die
Nutzungsbedingungen der Scans nicht geklärt sind.

Reiter, Suche, Filter und Flagging je Zeile wie bei Aarau, Basel, Baden und Bern.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
_geo = importlib.import_module("10_geo")
norm_street, loose, manual_points = _geo.norm_street, _geo.loose, _geo.manual_points
import site_nav  # noqa: E402  gemeinsame Navigation und Feldsuche aller Adressbuch-Seiten

CSV_DIR = Path("data/csv")
REVIEW = Path("data/review/flags.csv")
TELEFON = Path("web/telefon.csv")  # aus scripts/80_telefon.py
REPO_URL = "https://github.com/thodel/adressbuecher-lausanne"
VOLUMES = {"1907": "Indicateur vaudois 1907", "1896": "Indicateur vaudois 1896"}
SCRIPTORIUM = {"1896": "170201", "1907": "170211"}

TABS = [
    ("einwohner", "Habitants", "04_entries.csv",
     ["entry_id", "volume", "page", "surname", "alliance_name", "forename", "title", "civil_status",
      "occupation_raw", "street_raw", "building_no", "phone_flag", "telefon", "other_volume", "authority", "zeitreise", "entry_type",
      "parse_confidence", "qa_flags", "text", "street_key"]),
    ("berufe", "Registre professionnel", "04_berufe.csv",
     ["entry_id", "volume", "page", "heading", "surname", "alliance_name", "forename", "title", "civil_status",
      "occupation_raw", "origin_raw", "street_raw", "building_no", "phone_flag", "telefon", "other_volume", "authority", "zeitreise", "entry_type",
      "parse_confidence", "qa_flags", "text", "street_key"]),
    ("gemeinden", "Communes vaudoises", "04_gemeinden.csv",
     ["entry_id", "volume", "page", "municipality", "heading", "surname", "alliance_name", "forename", "title",
      "civil_status", "occupation_raw", "street_raw", "building_no", "phone_flag", "telefon", "other_volume", "authority",
      "zeitreise", "entry_type", "parse_confidence", "qa_flags", "text", "street_key"]),
]

LABELS = {"entry_id": "ID", "volume": "Vol.", "page": "Page", "surname": "Nom", "alliance_name": "Alliance",
          "forename": "Prénom", "title": "Titre", "civil_status": "État", "occupation_raw": "Profession",
          "origin_raw": "Complément", "street_raw": "Rue", "building_no": "N°", "phone_flag": "Tél.",
          "entry_type": "Type", "parse_confidence": "Confiance", "qa_flags": "Indices", "heading": "Rubrique",
          "text": "Ligne lue", "municipality": "Commune", "telefon": "Annuaire téléphonique",
          "other_volume": "Autre volume", "authority": "Notices d'autorité (non vérifiées)", "zeitreise": "Carte d'époque"}

QA = {"street_rare": "rue présente une seule fois dans le volume",
      "dehyphen": "coupure de fin de ligne rejointe",
      "hyphen": "trait d'union au milieu d'un mot",
      "surname_split": "nom séparé du nom d'alliance",
      "triple": "lettre triple réduite",
      "alliance_from_forename": "nom d'alliance lu dans le prénom",
      "alliance_from_text": "nom d'alliance complété d'après le texte",
      "unreadable": "passage illisible [?]",
      "aus_liste": "repris d'une liste"}

REASONS = ["Erreur de lecture", "Champ erroné", "Entrée mal découpée", "Rubrique erronée", "Source : faute d'impression",
           "Doublon", "Autre"]


def load_phone() -> dict[str, str]:
    """entry_id → «Stufe|Jahr|Name|Strasse|Nummer|Einheit|Bild» aus web/telefon.csv."""
    if not TELEFON.exists():
        return {}
    with TELEFON.open(encoding="utf-8") as fh:
        return {r["entry_id"]: "|".join(r[k].replace("|", "/") for k in ("how", "ptt_year", "ptt_name", "ptt_street",
                                                                        "ptt_phone", "entity_id", "image"))
                for r in csv.DictReader(fh)}


PHONE = load_phone()


def load_simple(path: str, fields: tuple[str, ...]) -> dict[str, str]:
    p = Path(path)
    if not p.exists():
        return {}
    with p.open(encoding="utf-8") as fh:
        return {r["entry_id"]: "|".join(r[k].replace("|", "/") for k in fields) for r in csv.DictReader(fh)}


OTHER = load_simple("web/baende.csv", ("tier", "other_volume", "other_id", "other_text", "evidence"))  # 81_baende.py
AUTH = load_simple("web/normdaten.csv", ("tier", "label", "life", "hls_id", "qid", "gnd", "field", "note"))  # 82_normdaten.py


def lv95(lat: float, lon: float) -> tuple[int, int]:
    """WGS84 → LV95 (Näherung von swisstopo, auf ~1 m genau)."""
    p, l = (lat * 3600 - 169028.66) / 10000, (lon * 3600 - 26782.5) / 10000
    e = 2600072.37 + 211455.93 * l - 10938.51 * l * p - 0.36 * l * p * p - 44.54 * l ** 3
    n = 1200147.07 + 308807.95 * p + 3745.25 * l * l + 76.63 * p * p - 194.56 * l * l * p + 119.79 * p ** 3
    return round(e), round(n)


def load_geo() -> dict[str, list[int]]:
    """«Gemeinde|Strassenschlüssel» bzw. «Gemeinde|» → [E, N] für den Link auf die Zeitreise von swisstopo."""
    out = {}
    out["Lausanne|"] = list(lv95(46.5226, 6.6332))  # place de la Palud
    for name, key in (("municipalities.csv", lambda r: r["municipality"] + "|"), ("streets.csv", lambda r: r["municipality"] + "|" + r["street_norm"]),
                      ("streets_manual.csv", lambda r: r["municipality"] + "|" + r["street_norm"])):
        p = Path("web/geo") / name
        if p.exists():
            for r in csv.DictReader(p.open(encoding="utf-8")):
                if r["lat"]:
                    out[key(r)] = list(lv95(float(r["lat"]), float(r["lon"])))
    manual = manual_points()  # von Hand gesetzt: gilt für alle Schreibvarianten
    p = Path("web/geo/streets.csv")
    if manual and p.exists():
        for r in csv.DictReader(p.open(encoding="utf-8")):
            pt = manual.get((r["municipality"], loose(r["street_norm"])))
            if pt:
                out[r["municipality"] + "|" + r["street_norm"]] = list(lv95(*pt))
    return out


GEO = load_geo()


def load_rows() -> dict[str, dict[str, list[list[str]]]]:
    """Band → Reiter → Zeilen."""
    out: dict[str, dict[str, list]] = defaultdict(lambda: {k: [] for k, *_ in TABS})
    for key, _label, fname, cols in TABS:
        with (CSV_DIR / fname).open(encoding="utf-8") as fh:
            reader = csv.DictReader(fh)
            csv_rows = list(reader)
        cols += site_nav.extra_columns(csv_rows, reader.fieldnames, cols)  # alle CSV-Angaben durchsuchbar
        for r in csv_rows:
            r["qa_flags"] = " ".join(r.get("qa_flags", "").replace(";", " ").split())
            r["telefon"] = PHONE.get(r["entry_id"], "")
            r["street_key"] = norm_street(r["street_raw"]) if r.get("street_raw") else ""
            r["other_volume"] = OTHER.get(r["entry_id"], "")
            r["authority"] = AUTH.get(r["entry_id"], "")
            r["zeitreise"] = ""  # im Browser aus GEO
            out[r["volume"]][key].append([r.get(c, "") for c in cols])
    return out


def load_pages() -> dict[str, dict[str, list[str]]]:
    """Pas de table: `page` est déjà le numéro d'image chez Scriptorium."""
    return defaultdict(dict)


def load_flags() -> list[dict]:
    if not REVIEW.exists():
        return []
    with REVIEW.open(encoding="utf-8") as fh:
        return [{"table": r["table"], "id": r["id"], "reason": r["reason"], "note": r["note"]}
                for r in csv.DictReader(fh) if r.get("status", "open") != "fixed"]


TEMPLATE = r"""<!doctype html>
<html lang="fr">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Indicateur vaudois 1896–1907</title>
<meta name="description" content="Les adresses de Lausanne de l'Indicateur vaudois 1896 et 1907, lues par machine (qwen3.8), avec recherche par nom, profession et rue, et lien vers la page chez Scriptorium.">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Source+Sans+3:wght@400;600;700&family=Source+Code+Pro:wght@400;600&display=swap">
<style>
/* Layout: Werkzeug wie Aarau/Basel/Baden — Kopf mit Hinweis und Filtern, darunter eine Tabelle, die den Rest füllt. */
:root {
  --bg: #f6f5f1; --paper: #ffffff; --fg: #1d2129; --muted: #5c6370; --line: #d9d7cf;
  --accent: #7a2e2e; --accent-soft: #f1e3e1; --ok: #2f6f4e; --warn: #9a6b11; --bad: #a33a2a; --flag: #fff3c4;
  --note-bg: #fbf4e2; --note-line: #e2cf9c;
  --font-body: "Source Sans 3", "Segoe UI", system-ui, sans-serif;
  --font-data: "Source Code Pro", ui-monospace, Menlo, monospace;
}
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg: #15171b; --paper: #1d2026; --fg: #e8e6df; --muted: #a39f94; --line: #353942;
  --accent: #d08a84; --accent-soft: #3a2626; --ok: #7fc39d; --warn: #d9b35a; --bad: #e08a79; --flag: #3b3418;
  --note-bg: #2a2619; --note-line: #5a4d2a; color-scheme: dark } }
:root[data-theme="dark"] {
  --bg: #15171b; --paper: #1d2026; --fg: #e8e6df; --muted: #a39f94; --line: #353942;
  --accent: #d08a84; --accent-soft: #3a2626; --ok: #7fc39d; --warn: #d9b35a; --bad: #e08a79; --flag: #3b3418;
  --note-bg: #2a2619; --note-line: #5a4d2a; color-scheme: dark }
[hidden] { display: none !important; }
html, body { height: 100%; }
body { background: var(--bg); color: var(--fg); font-family: var(--font-body); font-size: 15px; line-height: 1.4;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 16px; display: flex; flex-direction: column; gap: 10px; box-sizing: border-box; margin: 0; }
header { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 20px; }
.nav { font-size: 0.9rem; color: var(--muted); }
.nav a, td a, .note a, .sub a, footer a { color: var(--accent); }
.nav a { font-weight: 600; text-decoration: none; }
.nav a:hover, .nav a:focus-visible { text-decoration: underline; }
h1 { font-size: 1.3rem; margin: 0; font-weight: 700; letter-spacing: -0.01em; text-wrap: balance; }
.sub { color: var(--muted); font-size: 0.88rem; margin: 0; }
.note { background: var(--note-bg); border: 1px solid var(--note-line); border-radius: 8px; padding: 8px 12px; font-size: 0.9rem; }
.note p { margin: 0; }
.note details { margin-top: 4px; }
.note summary { cursor: pointer; color: var(--accent); font-weight: 600; }
.note .cols { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 4px 24px; margin-top: 6px; }
.note h2 { font-size: 0.95rem; margin: 6px 0 2px; }
.note ul { margin: 0; padding-left: 1.2em; }
.note li { margin: 2px 0; }
.toolbar { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; }
.tabs { display: flex; gap: 4px; flex-wrap: wrap; }
button { font: inherit; cursor: pointer; }
.tabs button { font-weight: 600; background: transparent; color: var(--muted); border: 1px solid var(--line); border-radius: 999px; padding: 4px 12px; }
.tabs button[aria-selected="true"] { background: var(--accent); border-color: var(--accent); color: #fff; }
button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
input[type="search"], select, input[type="text"] { font: inherit; padding: 5px 9px; border: 1px solid var(--line); border-radius: 6px; background: var(--paper); color: var(--fg); min-width: 0; max-width: 100%; }
input#q { flex: 1 1 220px; }
input#street { flex: 0 1 180px; }
.chip { display: inline-flex; gap: 6px; align-items: center; background: var(--accent-soft); border: 1px solid var(--accent); border-radius: 999px; padding: 2px 4px 2px 10px; font-size: 0.88rem; }
.chip button { border: 0; background: transparent; color: var(--accent); font-weight: 700; padding: 0 6px; }
.count { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 0.9rem; }
.flagbar { display: flex; flex-wrap: wrap; gap: 8px 12px; align-items: center; padding: 8px 12px; border: 1px solid var(--line); border-radius: 8px; background: var(--paper); font-size: 0.9rem; }
.flagbar .n { font-weight: 700; color: var(--accent); font-variant-numeric: tabular-nums; }
.btn { border: 1px solid var(--line); background: var(--paper); color: var(--fg); border-radius: 6px; padding: 4px 10px; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.wrap { flex: 1 1 auto; min-height: 320px; overflow: auto; border: 1px solid var(--line); border-radius: 8px; background: var(--paper); }
table { border-collapse: collapse; width: max-content; min-width: 100%; font-size: 13.5px; }
th, td { text-align: left; padding: 4px 8px; border-bottom: 1px solid var(--line); vertical-align: top; white-space: nowrap; max-width: 32ch; overflow: hidden; text-overflow: ellipsis; }
td.wide { white-space: normal; max-width: 48ch; }
th { position: sticky; top: 0; background: var(--paper); font-size: 0.76rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); z-index: 1; }
td.num, td.id { font-family: var(--font-data); font-variant-numeric: tabular-nums; font-size: 12.5px; }
td button.gm { border: 0; background: none; padding: 0; color: var(--accent); text-decoration: underline dotted; text-underline-offset: 2px; }
td button.st { border: 0; background: none; padding: 0; color: var(--fg); text-decoration: underline dotted; text-underline-offset: 2px; text-decoration-color: var(--muted); }
tr.flagged td { background: var(--flag); }
tr.reported td:first-child::before { content: "✓ "; color: var(--ok); font-weight: 700; }
.pill { display: inline-block; border-radius: 999px; padding: 0 8px; font-size: 0.74rem; font-weight: 600; line-height: 1.5; }
.pill.high { background: color-mix(in srgb, var(--ok) 18%, transparent); color: var(--ok); }
.pill.medium { background: color-mix(in srgb, var(--warn) 18%, transparent); color: var(--warn); }
.qa { display: inline-block; border: 1px solid var(--line); border-radius: 4px; padding: 0 5px; margin-right: 3px; font-size: 0.74rem; color: var(--muted); }
.star { color: var(--accent); font-weight: 700; }
td.act { white-space: nowrap; }
td.act select, td.act input { font-size: 12.5px; padding: 2px 5px; }
td.act input[type="text"] { width: 14ch; }
td.act a { color: var(--muted); font-size: 12px; margin-left: 6px; }
.more { display: block; width: 100%; padding: 8px; background: var(--accent-soft); color: var(--fg); border: 0; }
.legend { color: var(--muted); font-size: 0.84rem; margin: 0; }
.legend b { color: var(--fg); }
.loading { padding: 16px; color: var(--muted); }
footer { color: var(--muted); font-size: 0.8rem; }
#toast { position: fixed; bottom: calc(12px + env(safe-area-inset-bottom, 0px)); right: calc(12px + env(safe-area-inset-right, 0px)); background: var(--fg); color: var(--bg); padding: 8px 14px; border-radius: 8px; font-size: 0.9rem; }
@media (max-width: 600px) { body { font-size: 14px; } th, td { max-width: 22ch; } td.act input[type="text"] { width: 9ch; } .flagbar .sub { display: none; } .wrap { min-height: 70vh; } input#street { flex: 1 1 140px; } }
__NAVCSS__
@media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>
__CITYBAR__
<header>
  __CITYNAV__
  <h1>Indicateur vaudois 1896 et 1907 : Lausanne et communes vaudoises</h1>
  <p class="sub">État au __DATE__ · Indicateur des adresses et registre professionnel de la ville de Lausanne ; en 1907 aussi les autres communes du canton.</p>
</header>
<section class="note" aria-label="Remarque sur les données">
  <p><b>Lu par machine, sans correction manuelle.</b> Le texte provient du modèle de langue qwen3.8 (Université de Berne) et n'a pas été corrigé. Un petit sondage (30 entrées, 1896 p. 100 et 1907 p. 150) n'a trouvé aucune erreur ; ce sondage est trop petit pour chiffrer le taux d'erreurs. <b>En cas de doute, voir la page chez Scriptorium</b> (lien dans la colonne « Page »).</p>
  <details id="about">
    <summary>À propos des données : contenu, lacunes, licence</summary>
    <div class="cols">
      <div>
        <h2>Volumes</h2>
        <ul>
          <li><b>1896</b> · __N1896__ habitants (images 15–217), __B1896__ entrées au registre professionnel (images 219–290). <a href="https://www.scriptorium.ch/zoom/170201/view?page=1&amp;p=separate">Scriptorium</a></li>
          <li><b>1907</b> · __N1907__ habitants (images 21–294), __B1907__ entrées au registre professionnel (images 311–411) et __G1907__ entrées des <b>autres communes vaudoises</b> (images 670–962, onglet « Communes vaudoises », commune de 1914). <a href="https://www.scriptorium.ch/zoom/170211/view?page=1&amp;p=separate">Scriptorium</a></li>
        </ul>
        <h2>Lecture</h2>
        <ul>
          <li>Images en pleine résolution (1600 × 2500 px) via IIIF de Scriptorium (BCU Lausanne), agrandies 2×.</li>
          <li>« m. a. » (même adresse) reprend l'adresse de l'entrée précédente ; la colonne « Rue » montre l'adresse reprise, la « Ligne lue » le texte imprimé.</li>
          <li>Les « indices » sont des marques automatiques, pas des corrections ; confiance « medium » : un indice invite à vérifier.</li>
        </ul>
        <h2>Pas inclus</h2>
        <ul>
          <li>Répertoire des rues et des maisons (1907 dès l'image 422), autorités, sociétés, tarifs, annonces.</li>
        </ul>
      </div>
      <div>
        <h2>Annuaire téléphonique</h2>
        <ul><li>Les entrées avec téléphone sont reliées, si possible, à l'annuaire des PTT : d'abord par le numéro imprimé et le nom de famille (5 ans d'écart au plus), sinon par les liens de <a href="https://thodel.github.io/vernetzte-schweiz/">Vernetzte Schweiz</a>, sinon si l'annuaire de la commune ne compte qu'une personne de ce nom et prénom. Les annuaires de Lausanne conservés datent de 1885, 1890 et 1911–1914. __TELSTAT__</li></ul>
        <h2>Liens</h2>
        <ul>
          <li><b>Autre volume :</b> __NOTHER__ entrées sont reliées automatiquement à la même personne dans l'autre volume (même nom, prénom compatible, puis profession, rue, nom d'alliance) ; les cas ambigus restent ouverts.</li>
          <li><b>Notices d'autorité :</b> __NAUTH__ entrées ont un candidat <b>non vérifié</b> du Dictionnaire historique de la Suisse (DHS) ou de Wikidata (personne liée à Lausanne, vivante l'année du volume, nom et prénom compatibles, profession conforme ou nom rare).</li>
          <li><b>Carte d'époque :</b> lien vers la carte Siegfried de l'année (swisstopo, voyage dans le temps) à la rue (position OpenStreetMap), sinon au centre-ville. Voir aussi la <a href="karte.html">carte</a> de toutes les entrées.</li>
        </ul>
        <h2>Images des pages</h2>
        <ul><li>Les numérisations sont chez <a href="https://www.scriptorium.ch/">Scriptorium</a> (BCU Lausanne, cote 1C 478) et ne sont que liées : les conditions de réutilisation ne sont pas encore clarifiées. « Page » est le numéro d'image chez Scriptorium.</li></ul>
        <h2>Licence</h2>
        <ul><li>Les livres sont parus avant 1914 ; leur contenu est dans le domaine public. Données <a href="https://creativecommons.org/publicdomain/zero/1.0/deed.fr">CC0 1.0</a>, code <a href="__REPO__/blob/main/LICENSE">MIT</a>. CSV dans le <a href="__REPO__/tree/main/data/csv">dépôt</a>.</li></ul>
      </div>
    </div>
  </details>
</section>
<div class="toolbar">
  <div class="tabs" role="tablist" id="tabs"></div>
  <select id="vol" aria-label="Volume"><option value="1907">1907</option><option value="1896">1896</option><option value="">les deux volumes</option></select>
  <select id="conf" aria-label="Confiance"><option value="">toute confiance</option><option value="high">high</option><option value="medium">medium</option></select>
  <select id="qa" aria-label="Indice"><option value="">tous les indices</option><option value="-">sans indice</option></select>
  <select id="gem" aria-label="Commune" hidden><option value="">toutes les communes</option></select>
  <input id="street" type="search" list="streets" placeholder="Rue …" aria-label="Rue (début)">
  <datalist id="streets"></datalist>
  <select id="tel" aria-label="Téléphone"><option value="">Téléphone : tous</option><option value="1">avec ☏</option><option value="link">avec entrée à l'annuaire</option><option value="none">☏, entrée non trouvée</option></select>
  <span class="chip" id="skchip" hidden>Rue (carte) = <b id="sklabel"></b><button type="button" id="skclear" aria-label="Retirer le filtre de rue">✕</button></span>
  <label><input type="checkbox" id="onlyflag"> seulement signalées</label>
  <input id="q" type="search" placeholder="Chercher : nom, profession, rue, rubrique, ID …" aria-label="Chercher">
  <span class="count" id="count" aria-live="polite"></span>
</div>
__FSPANEL__
<div class="flagbar">
  <span><span class="n" id="nflags">0</span> signalements dans ce navigateur · <span id="nreported">0</span> déjà annoncés au dépôt</span>
  <button class="btn primary" id="dl">Télécharger les signalements (CSV)</button>
  <button class="btn" id="copy">Copier le CSV</button>
  <button class="btn" id="clear">Effacer les signalements</button>
  <span class="sub">Ensuite : <code>python scripts/91_merge_flags.py &lt;fichier.csv&gt;</code> et commit.</span>
</div>
<p class="legend"><b>Page</b> = numéro d'image, le lien ouvre la page chez Scriptorium · cliquer sur une <b>rue</b> filtre · <b>Confiance</b> : high = rien de suspect, medium = un indice invite à vérifier · <b>Indices</b> : survoler pour l'explication · <b>☏</b> = téléphone indiqué · <b>Annuaire</b> : entrée correspondante dans l'annuaire des PTT, lien vers la personne chez Vernetzte Schweiz et vers l'image de la page ; « numéro » = même numéro et même nom, « nom » = seule personne de ce nom et prénom, sinon le degré du lien de Vernetzte Schweiz · <b>Autre volume</b> : la même personne dans l'autre volume (automatique) · <b>Notices</b> : candidats non vérifiés du DHS et de Wikidata · <b>Carte d'époque</b> : carte Siegfried de l'année chez swisstopo · <b>✓</b> = déjà annoncé</p>
<div class="wrap"><table id="t"><thead></thead><tbody></tbody></table><div class="loading" id="loading" hidden>Chargement du volume …</div><button class="more" id="more" hidden>afficher plus de lignes</button></div>
<footer>Données CC0 1.0 · code MIT · images : Scriptorium, BCU Lausanne · source pour <a href="https://thodel.github.io/vernetzte-schweiz/">Vernetzte Schweiz 1860–1914</a></footer>
<div id="toast" hidden></div>
<script>
__FSJS__
const FSTX = __FSTX__;
const META = __META__;
const LABELS = __LABELS__;
const QA = __QA__;
const GEO = __GEO__;
const HOW = {nummer: 'même numéro et même nom', sicher: 'Vernetzte Schweiz : sûr', wahrscheinlich: 'Vernetzte Schweiz : probable', möglich: 'Vernetzte Schweiz : possible (nom seul)', name: 'seule personne de ce nom et prénom dans l\'annuaire de la commune'};
const TIER = {nummer: 'numéro', sicher: 'sûr', wahrscheinlich: 'probable', möglich: 'possible', name: 'nom'};
const SCRIPTORIUM = __SCRIPTORIUM__;
const REASONS = __REASONS__;
const REPORTED = __REPORTED__;
const REPO = "__REPO__";
const PAGE = 300;
const KEY = 'lausanne.flags.v1';
const VOLS = {};   // Band → {einwohner: [...], berufe: [...], pages: {...}}
const P = new URLSearchParams(location.search);
let tab = P.get('tab') && META.tabs[P.get('tab')] ? P.get('tab') : 'einwohner';
let shown = PAGE;
let skF = P.get('sk') || '';
let flags = {};
try { flags = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { flags = {}; }
const reported = {}; for (const f of REPORTED) reported[f.table + '|' + f.id] = f;
const $ = id => document.getElementById(id);
const tabsEl = $('tabs'), q = $('q'), vol = $('vol'), conf = $('conf'), qa = $('qa'), street = $('street'), gem = $('gem'), tel = $('tel'), onlyflag = $('onlyflag');
const thead = document.querySelector('#t thead'), tbody = document.querySelector('#t tbody'), more = $('more'), count = $('count');
for (const k in QA) { const o = document.createElement('option'); o.value = k; o.textContent = QA[k]; qa.appendChild(o); }
for (const k in META.tabs) { const b = document.createElement('button'); b.setAttribute('role', 'tab'); b.textContent = `${META.tabs[k].label} (${META.tabs[k].n.toLocaleString('fr-CH')})`; b.dataset.k = k; b.onclick = () => { tab = k; shown = PAGE; render(); }; tabsEl.appendChild(b); }
function esc(s) { return String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }
function save() { try { localStorage.setItem(KEY, JSON.stringify(flags)); } catch (e) {} }
function toast(msg) { const t = $('toast'); t.textContent = msg; t.hidden = false; setTimeout(() => { t.hidden = true; }, 2500); }
function loadPart(v, t) {
  VOLS[v] = VOLS[v] || {};
  if (VOLS[v][t]) return Promise.resolve(VOLS[v][t]);
  return fetch(`data/${v}-${t}.json`).then(r => { if (!r.ok) throw new Error(r.status); return r.json(); }).then(d => (VOLS[v][t] = d));
}
function wanted() { const tv = META.tabs[tab].vols; return vol.value ? tv.filter(v => v === vol.value) : tv; }
function scan(v, page) {
  return `<a href="https://www.scriptorium.ch/zoom/${SCRIPTORIUM[v]}/view?page=${esc(page)}&p=separate" target="_blank" rel="noopener" title="Image ${esc(page)} chez Scriptorium">p. ${esc(page)} ↗</a>`;
}
function issueUrl(r) {
  const cols = META.tabs[tab].cols, id = r[0];
  const body = `Tableau : ${META.tabs[tab].label}\nID : ${id}\nVolume ${r[1]}, image ${r[2]}, Scriptorium https://www.scriptorium.ch/zoom/${SCRIPTORIUM[r[1]]}/view?page=${r[2]}&p=separate\n\nLigne lue :\n${r[cols.indexOf('text')] ?? ''}\n\nProblème :\n`;
  return `${REPO}/issues/new?title=${encodeURIComponent('Signalement ' + id)}&labels=${encodeURIComponent('review')}&body=${encodeURIComponent(body)}`;
}
function muniOf(r) { const i = META.tabs[tab].cols.indexOf('municipality'); return i >= 0 ? r[i] : 'Lausanne'; }
function cell(col, v, r) {
  if (col === 'other_volume') {
    if (!v) return '<td></td>';
    const [tier, ov, oid, otext, ev] = v.split('|');
    return `<td><a href="?tab=einwohner&vol=${esc(ov)}&q=${encodeURIComponent(oid)}" title="${esc(otext + ' · ' + ev)}">${esc(ov)} ↗</a> <span class="pill ${tier === 'sicher' ? 'high' : 'medium'}">${esc(TIER[tier] || tier)}</span></td>`;
  }
  if (col === 'authority') {
    if (!v) return '<td></td>';
    const [tier, label, life, hls, qid, gnd, field, note] = v.split('|');
    const links = [hls ? `<a href="https://hls-dhs-dss.ch/fr/articles/${esc(hls)}/" target="_blank" rel="noopener">DHS</a>` : '',
      qid ? `<a href="https://www.wikidata.org/wiki/${esc(qid)}" target="_blank" rel="noopener">Wikidata</a>` : '',
      gnd ? `<a href="https://d-nb.info/gnd/${esc(gnd)}" target="_blank" rel="noopener">GND</a>` : ''].filter(Boolean).join(' · ');
    return `<td class="wide" title="${esc(field + (note ? ' · ' + note : ''))}">${esc(label)} <small>${esc(life)}</small> · ${links} <span class="pill ${tier === 'wahrscheinlich' ? 'high' : 'medium'}" title="candidat non vérifié">${esc(TIER[tier] || tier)}</span></td>`;
  }
  if (col === 'zeitreise') {
    const g = GEO[muniOf(r) + '|' + r[META.tabs[tab].cols.indexOf('street_key')]] || GEO[muniOf(r) + '|'];
    if (!g) return '<td></td>';
    const exact = !!r[META.tabs[tab].cols.indexOf('street_key')] && !!GEO[muniOf(r) + '|' + r[META.tabs[tab].cols.indexOf('street_key')]];
    return `<td><a href="https://map.geo.admin.ch/#/map?lang=fr&center=${g[0]},${g[1]}&z=${exact ? 11 : 9}&crosshair=marker&bgLayer=void&layers=ch.swisstopo.zeitreihen@year=${esc(r[1])}" target="_blank" rel="noopener" title="${exact ? 'Rue' : 'Ville'} sur la carte Siegfried ${esc(r[1])} (swisstopo, voyage dans le temps)">${exact ? 'rue' : 'ville'} ${esc(r[1])} ↗</a></td>`;
  }

  if (col === 'municipality') return `<td><button type="button" class="gm" data-g="${esc(v)}" title="filtrer par ${esc(v)}">${esc(v)}</button></td>`;
  if (col === 'page') return `<td class="num">${scan(r[1], v)}</td>`;
  if (col === 'parse_confidence') return `<td><span class="pill ${esc(v)}">${esc(v)}</span></td>`;
  if (col === 'phone_flag') return `<td class="num">${v === '1' ? '<span class="star" title="Téléphone">☏</span>' : ''}</td>`;
  if (col === 'street_raw') return `<td>${v ? `<button type="button" class="st" data-s="${esc(v)}" title="filtrer par ${esc(v)}">${esc(v)}</button>` : ''}</td>`;
  if (col === 'telefon') {
    if (!v) return r[META.tabs[tab].cols.indexOf('phone_flag')] === '1' ? '<td class="sub">non trouvé</td>' : '<td></td>';
    const [how, year, name, st, phone, eid, img] = v.split('|');
    const tip = `Annuaire ${year} : ${name}${st ? ', ' + st : ''}${phone ? ', n° ' + phone : ''} · lien : ${HOW[how] || how}`;
    const main = eid ? `<a href="https://thodel.github.io/vernetzte-schweiz/#/e/${esc(eid)}" target="_blank" rel="noopener" title="${esc(tip)}">${esc(year)}${phone ? ' · n° ' + esc(phone) : ''}</a>` : `<span title="${esc(tip)}">${esc(year)}</span>`;
    return `<td>${main}${img ? ` · <a href="${esc(img)}" target="_blank" rel="noopener" title="Page de l'annuaire (Archives PTT)">image</a>` : ''} <span class="pill ${how === 'nummer' || how === 'sicher' ? 'high' : 'medium'}" title="${esc(HOW[how] || how)}">${esc(TIER[how] || how)}</span></td>`;
  }
  if (col === 'qa_flags') return `<td>${v ? v.split(' ').map(x => `<span class="qa" title="${esc(QA[x] || x)}">${esc(x)}</span>`).join('') : ''}</td>`;
  if (col === 'entry_id') return `<td class="id">${esc(v)}</td>`;
  if (['building_no','volume'].includes(col)) return `<td class="num">${esc(v)}</td>`;
  if (['occupation_raw','text'].includes(col)) return `<td class="wide">${esc(v)}</td>`;
  return `<td>${esc(v)}</td>`;
}
function actCell(r) {
  const key = tab + '|' + r[0], f = flags[key] || {};
  const opts = ['<option value="">— Signaler —</option>'].concat(REASONS.map(x => `<option value="${esc(x)}" ${f.reason === x ? 'selected' : ''}>${esc(x)}</option>`)).join('');
  return `<td class="act"><select data-key="${esc(key)}" data-f="reason" aria-label="Motif">${opts}</select> <input type="text" data-key="${esc(key)}" data-f="note" placeholder="Note" value="${esc(f.note || '')}" aria-label="Note"><a href="${issueUrl(r)}" target="_blank" rel="noopener">Issue</a></td>`;
}
let gemKey = '';
function gemOptions(all, mi) {
  if (gemKey === tab + '|' + vol.value) return; gemKey = tab + '|' + vol.value;
  const n = {}, cur = gem.value; for (const r of all) n[r[mi]] = (n[r[mi]] || 0) + 1;
  gem.innerHTML = '<option value="">toutes les communes</option>' + Object.keys(n).sort((a, b) => a.localeCompare(b, 'fr')).map(x => `<option value="${esc(x)}">${esc(x)} (${n[x].toLocaleString('fr-CH')})</option>`).join('');
  gem.value = cur in n ? cur : '';
}
let streetKey = '';
function streetList(rows, si) {
  const key = tab + '|' + vol.value; if (key === streetKey) return; streetKey = key;
  const n = {}; for (const r of rows) if (r[si]) n[r[si]] = (n[r[si]] || 0) + 1;
  $('streets').innerHTML = Object.entries(n).sort((a, b) => b[1] - a[1]).slice(0, 500).map(([s, c]) => `<option value="${esc(s)}">${c}</option>`).join('');
}
function syncUrl() {
  const p = new URLSearchParams();
  p.set('tab', tab); p.set('vol', vol.value || 'alle');
  if (conf.value) p.set('conf', conf.value); if (qa.value) p.set('qa', qa.value); if (tel.value) p.set('tel', tel.value); if (!gem.hidden && gem.value) p.set('gem', gem.value); if (skF) p.set('sk', skF);
  if (street.value.trim()) p.set('str', street.value.trim());
  if (q.value.trim()) p.set('q', q.value.trim());
  FS.toParams(p);
  history.replaceState(null, '', location.pathname + '?' + p.toString() + (location.hash === '#suche' ? '#suche' : ''));
}
let seq = 0, fsTab = '';
function render() {
  for (const b of tabsEl.children) b.setAttribute('aria-selected', b.dataset.k === tab);
  const vs = wanted(), my = ++seq;
  if (vs.some(v => !(VOLS[v] && VOLS[v][tab]))) {
    $('loading').hidden = false; $('loading').textContent = 'Chargement du volume …';
    Promise.all(vs.map(v => loadPart(v, tab))).then(() => { if (my === seq) render(); }, e => { $('loading').textContent = 'Impossible de charger le volume (' + e.message + ').'; });
    return;
  }
  $('loading').hidden = true;
  if (tab !== fsTab) { fsTab = tab; FS.refresh(); }
  const hide = META.tabs[tab].hide;
  const cols = META.tabs[tab].cols, oi = META.tabs[tab].cols.indexOf('other_volume'), all = vs.flatMap(v => VOLS[v][tab]);
  const mi = cols.indexOf('municipality'), g = gem.value;
  gem.hidden = mi < 0;
  if (mi >= 0) gemOptions(all, mi);
  const needle = q.value.trim().toLowerCase(), c = conf.value, h = qa.value, s = street.value.trim().toLowerCase();
  const ci = cols.indexOf('parse_confidence'), hi = cols.indexOf('qa_flags'), si = cols.indexOf('street_raw');
  const pi = cols.indexOf('phone_flag'), ti = cols.indexOf('telefon'), t = tel.value, ki = cols.indexOf('street_key');
  $('skchip').hidden = !skF; if (skF) $('sklabel').textContent = skF;
  streetList(all, si);
  const rows = all.filter(r => (mi < 0 || !g || r[mi] === g) && (!c || r[ci] === c)
    && (!h || (h === '-' ? !r[hi] : (' ' + r[hi] + ' ').includes(' ' + h + ' ')))
    && (!s || r[si].toLowerCase().startsWith(s))
    && (!skF || r[ki] === skF)
    && (!t || (t === '1' ? r[pi] === '1' : t === 'link' ? !!r[ti] : r[pi] === '1' && !r[ti]))
    && (!onlyflag.checked || flags[tab + '|' + r[0]] || reported[tab + '|' + r[0]])
    && (!needle || r.filter((_, i) => i !== oi).join(' ').toLowerCase().includes(needle))
    && FS.test(r, cols));
  thead.innerHTML = '<tr><th>Signaler</th>' + cols.filter(cc => !hide.includes(cc)).map(cc => `<th>${esc(LABELS[cc] || cc)}</th>`).join('') + '</tr>';
  tbody.innerHTML = rows.slice(0, shown).map(r => {
    const key = tab + '|' + r[0];
    const cls = (flags[key] && flags[key].reason ? 'flagged ' : '') + (reported[key] ? 'reported' : '');
    return `<tr class="${cls}" title="${reported[key] ? esc('annoncé : ' + reported[key].reason + ' ' + reported[key].note) : ''}">${actCell(r)}${r.map((vv, i) => hide.includes(cols[i]) ? '' : cell(cols[i], vv, r)).join('')}</tr>`;
  }).join('');
  more.hidden = rows.length <= shown;
  count.textContent = `${Math.min(shown, rows.length).toLocaleString('fr-CH')} sur ${rows.length.toLocaleString('fr-CH')} lignes`;
  $('nflags').textContent = Object.values(flags).filter(f => f.reason).length;
  $('nreported').textContent = REPORTED.length;
  syncUrl();
}
tbody.addEventListener('change', e => {
  const el = e.target, key = el.dataset.key; if (!key) return;
  flags[key] = flags[key] || {}; flags[key][el.dataset.f] = el.value;
  if (!flags[key].reason && !flags[key].note) delete flags[key];
  save(); const tr = el.closest('tr'); tr.classList.toggle('flagged', !!(flags[key] && flags[key].reason)); $('nflags').textContent = Object.values(flags).filter(f => f.reason).length;
});
tbody.addEventListener('click', e => {
  const g = e.target.closest('button.gm');
  if (g) { gemKey = ''; gem.innerHTML = `<option value="${esc(g.dataset.g)}"></option>`; gem.value = g.dataset.g; shown = PAGE; render(); return; }
  const b = e.target.closest('button.st'); if (!b) return;
  street.value = b.dataset.s; shown = PAGE; render();
});
function flagsCsv() {
  const q2 = s => '"' + String(s ?? '').replace(/"/g, '""') + '"';
  const lines = ['table,id,reason,note,by,date'];
  const today = new Date().toISOString().slice(0, 10);
  for (const key in flags) { const f = flags[key]; if (!f.reason) continue; const [t, id] = key.split('|'); lines.push([t, id, f.reason, f.note || '', '', today].map(q2).join(',')); }
  return lines.join('\n') + '\n';
}
$('dl').onclick = () => {
  const blob = new Blob(['﻿' + flagsCsv()], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `flags_lausanne_${new Date().toISOString().slice(0, 10)}.csv`; document.body.appendChild(a); a.click(); a.remove();
  toast('Téléchargement du CSV (si bloqué : copier)');
};
$('copy').onclick = () => {
  const text = flagsCsv();
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(() => toast('CSV copié'), () => fallbackCopy(text)); else fallbackCopy(text);
};
function fallbackCopy(text) { const ta = document.createElement('textarea'); ta.value = text; document.body.appendChild(ta); ta.select(); try { document.execCommand('copy'); toast('CSV copié'); } catch (e) { toast('Copie impossible : le texte est sélectionné'); } ta.remove(); }
$('clear').onclick = () => { if (!Object.keys(flags).length) return; flags = {}; save(); render(); toast('Signalements effacés'); };
more.onclick = () => { shown += PAGE; render(); };
for (const el of [q, street]) el.addEventListener('input', () => { shown = PAGE; render(); });
for (const el of [vol, gem, conf, qa, tel, onlyflag]) el.addEventListener('change', () => { shown = PAGE; render(); });
if (P.get('vol')) vol.value = P.get('vol') === 'alle' ? '' : P.get('vol');
if (P.get('conf')) conf.value = P.get('conf');
if (P.get('qa')) qa.value = P.get('qa');
if (P.get('tel')) tel.value = P.get('tel');
if (P.get('gem')) { const o = document.createElement('option'); o.value = P.get('gem'); gem.appendChild(o); gem.value = P.get('gem'); }
$('skclear').onclick = () => { skF = ''; shown = PAGE; render(); };
if (P.get('str')) street.value = P.get('str');
if (P.get('q')) q.value = P.get('q');
FS.init({ cols: () => META.tabs[tab].cols, skip: ['street_key', 'zeitreise', 'telefon', 'other_volume', 'authority'], labels: LABELS, tx: FSTX, first: 'surname', onChange: () => { shown = PAGE; render(); } });
render();
</script>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="Zielordner")
    args = ap.parse_args()
    rows, pages = load_rows(), load_pages()
    (args.out / "data").mkdir(parents=True, exist_ok=True)
    for v in VOLUMES:
        for k in rows[v]:
            if not rows[v][k]:
                continue
            p = args.out / "data" / f"{v}-{k}.json"  # je Band und Reiter, damit die Gemeinden nur bei Bedarf laden
            p.write_text(json.dumps(rows[v][k], ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            print(f"{v} {k}: {len(rows[v][k])} → {p} ({p.stat().st_size / 1e6:.1f} MB)")
    n = {k: Counter() for k, *_ in TABS}
    for v in rows:
        for k in rows[v]:
            n[k][v] = len(rows[v][k])
    meta = {"volumes": VOLUMES,
            "tabs": {k: {"label": label, "cols": cols, "n": sum(n[k].values()),
                         "vols": [v for v in VOLUMES if n[k][v]], "hide": cols[cols.index("street_key"):]} for k, label, _f, cols in TABS}}
    ti = {k: cols.index("phone_flag") for k, _l, _f, cols in TABS}
    n_tel = sum(1 for v in rows for k in rows[v] for r in rows[v][k] if r[ti[k]] == "1")
    fmt = lambda x: f"{x:,}".replace(",", " ")
    reported = load_flags()
    html = (TEMPLATE.replace("__CITYBAR__", site_nav.city_bar('lausanne', 'fr')).replace("__CITYNAV__", site_nav.city_nav('Lausanne 1896–1907', REPO_URL, "entries", 'fr')).replace("__NAVCSS__", site_nav.CSS).replace("__FSPANEL__", site_nav.search_panel('fr')).replace("__FSJS__", site_nav.FIELD_SEARCH_JS).replace("__FSTX__", json.dumps(site_nav.fs_texts('fr'), ensure_ascii=False)).replace("__META__", json.dumps(meta, ensure_ascii=False))
            .replace("__LABELS__", json.dumps(LABELS, ensure_ascii=False))
            .replace("__QA__", json.dumps(QA, ensure_ascii=False))
            .replace("__GEO__", json.dumps(GEO, ensure_ascii=False, separators=(",", ":")))
            .replace("__NOTHER__", f"{len(OTHER):,}".replace(",", "\u202f"))
            .replace("__NAUTH__", f"{len(AUTH):,}".replace(",", "\u202f"))
            .replace("__REASONS__", json.dumps(REASONS, ensure_ascii=False))
            .replace("__REPORTED__", json.dumps(reported, ensure_ascii=False))
            .replace("__N1896__", fmt(n["einwohner"]["1896"])).replace("__N1907__", fmt(n["einwohner"]["1907"]))
            .replace("__B1896__", fmt(n["berufe"]["1896"])).replace("__G1907__", fmt(n["gemeinden"]["1907"])).replace("__B1907__", fmt(n["berufe"]["1907"]))
            .replace("__SCRIPTORIUM__", json.dumps(SCRIPTORIUM))
            .replace("__TELSTAT__", f"{len(PHONE):,} des {n_tel:,} entrées avec téléphone ont une correspondance.".replace(",", "\u202f"))
            .replace("__REPO__", REPO_URL)
            .replace("__DATE__", date.today().strftime("%d.%m.%Y")))
    (args.out / "index.html").write_text(html, encoding="utf-8")
    print(f"{len(reported)} gemeldete Flags → {args.out / 'index.html'}")


if __name__ == "__main__":
    main()
