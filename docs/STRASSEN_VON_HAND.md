# Strassen von Hand verorten

Rund ein Drittel der Lausanner Einträge steht an Strassen, die OpenStreetMap heute nicht mehr unter dem gedruckten Namen kennt (Martheray, Halle, Pré, Bugnion …). Für sie gibt es die Hand-Liste `web/geo/streets_manual.csv`.

## Die Datei

| Spalte | Inhalt |
|---|---|
| `municipality` | immer `Lausanne` |
| `street_norm` | Name, wie das Skript ihn liest (Abkürzungen ausgeschrieben) |
| `entries` | Einträge 1896 + 1907 an dieser Strasse, alle Schreibvarianten zusammen |
| `variants` | die häufigsten Schreibweisen mit Anzahl, zur Kontrolle |
| `lat`, `lon` | **von Hand**: Punkt in WGS84, Dezimalgrad (z. B. `46.52310`, `6.63480`) |
| `source` | **von Hand**: woher der Punkt kommt, z. B. `Siegfried 1904` oder `Plan de Lausanne 1896` |
| `note` | **von Hand**, frei: z. B. «heute Rue Centrale», «abgerissen 1930er» |

Die Zeilen sind nach `entries` sortiert: die ersten 50 decken rund 40 % der Einträge ohne Punkt.

## Ablauf

1. Strasse auf einer Karte der Zeit suchen. Am einfachsten ist die Zeitreise von swisstopo, wo die Siegfriedkarte um 1900 mit den Strassennamen von Lausanne steht: <https://map.geo.admin.ch/#/map?lang=fr&center=2538000,1152500&z=9&bgLayer=void&layers=ch.swisstopo.zeitreihen@year=1904>
2. Rechtsklick auf die Mitte der Strasse: map.geo.admin zeigt die Koordinaten, darunter «WGS 84 (lat/lon)». Diese zwei Zahlen in `lat` und `lon` eintragen.
3. `source` ausfüllen. Unsichere Punkte nicht setzen, sondern in `note` beschreiben.
4. Commit und Push genügen. Die Seite und die Karte lesen die Datei direkt, und der Punkt gilt für alle Schreibvarianten der Zeile.

Ist ein Name offensichtlich eine Fehllesung oder gar keine Strasse («Hôtel Terminus», «Gare du Flon»), dann in `note` vermerken und `lat`/`lon` trotzdem setzen, wenn der Ort klar ist.

## Liste neu erzeugen

Nach neuen Daten oder einem neuen Lauf von `10_geo.py streets`:

```bash
python scripts/10_geo.py todo --min 10
```

Schon gesetzte Zeilen bleiben dabei erhalten. Strassen, die inzwischen automatisch verortet sind, fallen heraus, sofern sie noch keinen Punkt von Hand haben.
