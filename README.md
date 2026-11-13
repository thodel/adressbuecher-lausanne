# Indicateur vaudois 1896 und 1907: Lausanne

Einträge der Lausanner Adressbücher (Indicateur vaudois), maschinell gelesen. Quelle für
[Vernetzte Schweiz 1860–1914](https://thodel.github.io/vernetzte-schweiz/).

| Band | Seiten | Einwohner | Berufsregister |
|---|---:|---:|---:|
| Indicateur vaudois 1896 | 342 | 18 554 (S. 15–217) | 5 398 (S. 219–290) |
| Indicateur vaudois 1907 | 1 019 | 23 175 (S. 21–294) | 6 576 (S. 311–411) |

Seite = Bildnummer im IIIF-Manifest von Scriptorium (BCU Lausanne): 1896 Objekt 170201, 1907 Objekt 170211
(`data/csv/00_volumes.csv`).

## Dateien

Schema wie [adressbuecher-aarau](https://github.com/thodel/adressbuecher-aarau), dazu `municipality`
(hier immer «Lausanne») und `qa_flags`.

- `data/csv/04_entries.csv`: «Indicateur des adresses», alphabetisch.
- `data/csv/04_berufe.csv`: Berufsregister; der Beruf steht in `heading`.
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

## Nicht übernommen

Strassen- und Häuserverzeichnis (1907 ab S. 422), Behörden, Vereine, Tarife, Inserate, und **die übrigen
Waadtländer Gemeinden** des Bandes 1907 (S. 664–960). Sie wären eine eigene Runde wie der Bezirk Baden 1910.
Die Nutzungsbedingungen der Scans sind noch nicht geklärt; die Bilder liegen darum nicht hier.

## Lizenz

Die Bücher sind vor 1914 erschienen; ihr Inhalt ist gemeinfrei (URG Art. 2 Abs. 1, Art. 29 Abs. 2).
Die Daten in `data/` stehen unter [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/), der Code
unter MIT.
