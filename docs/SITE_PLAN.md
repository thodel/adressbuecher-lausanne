# Plan: Seite für den Indicateur vaudois 1896 und 1907 (Lausanne)

Stand 13.11.2026. Vorlage ist die Seite von Baden (https://thodel.github.io/adressbuecher-baden/,
`scripts/90_seite.py`, `.github/workflows/pages.yml` in thodel/adressbuecher-baden): eine statische Seite,
die GitHub Actions aus `data/csv/` baut. Sie hat Reiter, Suche, Filter, Flagging je Zeile und eine
Hinweisbox zur maschinellen Lesung, im Aussehen von Aarau und Basel.

`data/csv`, `data/qwen` und `scripts/convert.py` bleiben für die Seite unberührt, weil Vernetzte Schweiz
diese Daten per Commit pinnt. Neue Konvertierungen (Punkte 4 und 5) brauchen einen neuen Pin.

## Umfang

53 723 Zeilen: 1896 hat 18 554 Einwohner und 5 398 Einträge im Berufsregister, 1907 hat 23 175 und
6 576. Alles eingebettet wären es rund 10 MB. Darum JSON je Band als eigene Datei
(`_site/data/1896.json`, `1907.json`): ein Band wird zuerst geladen, der andere beim Bandwechsel.

## Was die Seite zeigt

1. **Französische Oberfläche** (`<html lang="fr">`): Reiter, Spalten, Legende, Hinweisbox und Gründe
   für Flags auf Französisch, etwa Habitants, Registre professionnel, Volume, Rue, N°, Profession, und
   «Texte lu par machine (qwen3.8), sans correction manuelle». Die Texte in einer Wörtertabelle im Skript
   halten; dann bauen Baden, Bern und Lausanne mit demselben Generator. Ein Umschalter DE/FR ist
   optional (Vernetzte Schweiz ist deutsch).
2. **«m. a.» (même adresse):** `convert.py` übernimmt die Adresse vom vorigen Eintrag (1896: 1 001-mal,
   1907: 1 350-mal). Die Seite soll das kennzeichnen (Markierung «m. a.» an der Adresse), damit niemand
   die übernommene Adresse für gelesenen Text hält. Falls die Kennung nicht in einer Spalte steht, beim
   Bau aus `text` ableiten: «m. a.» steht dort.
3. **Seitenbilder: Link je Zeile möglich (geprüft).** Der Viewer von Scriptorium nimmt die Bildnummer:
   - `https://www.scriptorium.ch/zoom/170201/view?page=<n>&p=separate` für 1896, mit 170211 für 1907.
   - `page` in `data/csv` ist schon die Bildnummer im IIIF-Manifest; eine Umrechnung braucht es nicht.
   - Die IIIF-Bilder selbst (`https://www.scriptorium.ch/api/iiif-img/v3/<bild-id>/…`, Level 1) liefern
     die ganze Seite nur bis 450 px, die volle Auflösung nur über Kacheln.
   - Die Nutzungsbedingungen sind ungeklärt (das Manifest hat keine `rights`-Angabe). Darum nur auf
     Scriptorium verlinken und nichts einbetten oder spiegeln, bis die BCU Lausanne antwortet. Danach
     wäre eine Vorschau beim Darüberfahren möglich.
4. **Rues et places / répertoire des rues** (1907 ab S. 422): nicht konvertiert. Der Teil würde ein
   Reiter «Rues» (Strasse → Hausnummer → Bewohner bzw. Eigentümer) wie «Gebäude/Bewohner» bei Aarau.
   Das ist eine Datenänderung mit neuem Pin. Bis dahin gibt es einen Filter Strasse aus `street_raw`.
5. **Communes vaudoises** (1907 S. 664–960, rund 300 Seiten): noch nicht übernommen. Wenn sie
   übernommen werden, wie der Bezirk Baden 1910: die Gemeinde je Abschnitt am Kopf festmachen, Spalte
   `municipality`, und auf der Seite den Filter Gemeinde von Baden verwenden. Bis dahin sagt die
   Hinweisbox, dass nur die Stadt Lausanne enthalten ist.
6. **Hinweisbox:** Die Stichprobe umfasst nur 30 Einträge (alle zeichengenau). Das als kleine Stichprobe
   benennen; die Scans von Scriptorium sind deutlich besser als die e-rara-PDFs.

## Aufwand

- Grundseite auf Französisch mit Links auf Scriptorium und Nachladen je Band: rund 3 h.
- Reiter Rues: weitere 3–4 h.
- Communes vaudoises 1907: Lesung von rund 300 Seiten auf GPUStack (ein Nachtlauf), dann Konvertierung
  mit Gemeindeköpfen in 4–6 h.
