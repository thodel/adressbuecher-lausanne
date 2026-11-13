# Indicateur vaudois 1896 und 1907: Lausanne

Einträge der Lausanner Adressbücher (Indicateur vaudois), maschinell gelesen. Quelle für
[Vernetzte Schweiz 1860–1914](https://thodel.github.io/vernetzte-schweiz/).

| Band | Seiten | Einwohner | Berufsregister |
|---|---:|---:|---:|
| Indicateur vaudois 1896 | 342 | 18 554 (S. 15–217) | 5 398 (S. 219–290) |
| Indicateur vaudois 1907 | 1 019 | 23 175 (S. 21–294) | 6 578 (S. 311–411) |

Dazu aus dem Band 1907 **die übrigen Waadtländer Gemeinden** (S. 670–962): 29 122 Einträge in 386 Gemeinden
(`data/csv/04_gemeinden.csv`, siehe unten).

Seite = Bildnummer im IIIF-Manifest von Scriptorium (BCU Lausanne): 1896 Objekt 170201, 1907 Objekt 170211
(`data/csv/00_volumes.csv`).

## Dateien

Schema wie [adressbuecher-aarau](https://github.com/thodel/adressbuecher-aarau), dazu `municipality`
(hier immer «Lausanne») und `qa_flags`.

- `data/csv/04_entries.csv`: «Indicateur des adresses», alphabetisch.
- `data/csv/04_berufe.csv`: Berufsregister; der Beruf steht in `heading`.
- `data/csv/04_gemeinden.csv`: die übrigen Waadtländer Gemeinden 1907, mit `municipality` (Gemeinde 1914).
- `data/csv/03_sections.csv`, `data/csv/00_volumes.csv`: Seitenbereiche und Bände.
- `data/csv/10_authority_links.csv`: leer; Normdaten verknüpft «Vernetzte Schweiz» über die Personen.
- `data/qwen/<Jahr>/`: die Lesung, wie sie vom Modell kam.

`python scripts/convert.py` erzeugt `data/csv/` aus `data/qwen/`; `python -m unittest discover -s tests`.

## Wie gelesen

- **Modell:** `qwen3.8-27b` auf GPUStack der Universität Bern, Seitenbild 2× vergrössert. Die Bilder
  kommen in voller Auflösung (1 600 × 2 500 px) über IIIF von Scriptorium.
- **Stichprobe, von Hand am Seitenbild:** je ein Drittel einer Spalte, 1896 S. 100 (13 Einträge) und 1907
  S. 150 (17 Einträge): alle 30 zeichengenau. Das ist eine kleine Stichprobe; die Scans sind deutlich
  besser als die e-rara-PDFs der Deutschschweizer Bände.
- **«m. a.»** (même adresse) übernimmt die Adresse des vorigen Eintrags (1896: 1 001-mal, 1907: 1 350-mal).
- Keine Nachkorrektur; `qa_flags` markiert Verdachtsfälle.

## Die Waadtländer Gemeinden (1907)

- **Aufbau im Buch:** Bezirk für Bezirk, darin die Gemeinden alphabetisch; jede beginnt mit ihrem Namen in
  Versalien und «… habitants — Altitude …». Darunter Behörden (Syndic, Municipaux …) und Berufe, oft mehrere
  Personen in einer Zeile: «Charrons. — Péclard Emile — Rouilly Constant».
- **Gemeinde:** `scripts/communes.py` sucht den Namen im Buch unter den Gemeinden von 1914 des laufenden Bezirks
  (`data/ref/municipalities_vd_1914.csv`, BFS): «ROMANEL» im Bezirk Lausanne → Romanel-sur-Lausanne, im Bezirk
  Morges → Romanel-sur-Morges. Gefunden: 386 von 388 Gemeinden; Lausanne steht im ersten Teil, Dully fehlt im Buch.
  Ortsteile der Vallée und von Montreux (Le Pont, Orient, 2° Les Planches) zählen für ihre Gemeinde.
- **Montreux:** Nach den Köpfen von Le Châtelard, Les Planches und Veytaux folgt ein Berufsverzeichnis für den
  ganzen Kreis (S. 920–938). Die Gemeinde kommt dort aus dem Ortsteil in der Adresse (Clarens → Le Châtelard,
  Territet → Les Planches); 1 066 Einträge ohne Ortsteil bleiben weg.
- **Listen:** Hat die Lesung von «— Chevalley Louis — Wagnière Gustave» nur den ersten Namen als Zeile ausgegeben,
  werden die übrigen aus dem Text ergänzt (2947 Einträge, `qa_flags` = `aus_liste`). Eine Zeile mit zwei
  Namen in einem Feld («Bovay, Burdet») wird geteilt.
- **Geprüft:** S. 958 (Orzens, Pomy) am Seitenbild: alle Namen richtig gelesen; die Liste der Municipaux
  fehlte vor der Ergänzung bis auf den ersten Namen.

## Nicht übernommen

Strassen- und Häuserverzeichnis (1907 ab S. 422), das Ortsverzeichnis (S. 664–669), Behörden des Kantons und
der Bezirke, Vereine, Tarife, Inserate.
Die Nutzungsbedingungen der Scans sind noch nicht geklärt; die Bilder liegen darum nicht hier.

## Lizenz

Die Bücher sind vor 1914 erschienen; ihr Inhalt ist gemeinfrei (URG Art. 2 Abs. 1, Art. 29 Abs. 2).
Die Daten in `data/` stehen unter [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/), der Code
unter MIT.
