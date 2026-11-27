# M5-64 — QGIS-Stil bei jedem Export

**Stand:** 27.11.2026, Plan mit Fragen F1–F7 an Otto; Umsetzung nach den Empfehlungen in zwei Draft-PRs (§9).
**Stufe B.** Höchstens zwei PRs (M5-Plan §2 Punkt 11).
**Aufgabe (Otto, 20.11.2026; Auftrag 27.11.2026):**

> Neben jeder Rasterdatei im Export-ZIP liegt eine QGIS-Stildatei `.qml` gleichen Namens, damit QGIS sie beim Öffnen automatisch lädt und die Daten aussehen wie in der App:
> - ein Band: dieselbe Farbskala mit demselben Min/Max (physikalische Werte, bei skalierten Bändern passend zu den gespeicherten Werten der Datei umgerechnet);
> - RGB: dieselbe Streckung je Kanal;
> - Klassenband: Werte, Farben und Namen aus `band_classes` (paletted renderer), passend zur Farbtabelle in der GeoTIFF.
>
> Gilt für alle Exporte mit Rasterdateien („Download crop“, Export-Job, Processing-Ergebnisse), für „per band“ und „One multi-band file“. Die Darstellung ist die, die der Nutzer beim Export gerade eingestellt hat (Look der Ebene), sonst der Look aus der Collection. Farbskalen als Farbrampe mit genügend Stützstellen, keine Abhängigkeit von QGIS-eigenen Rampen-Namen. Der Worker-Kern bleibt zustandslos: Der Look kommt mit dem Auftrag, nicht aus einer Ablage.

**Grundlagen:** `adr/0028` §6, `plans/m5/m5-60-darstellung-je-band.md` §3.2, §11, §13–§15, `plans/m5/m5-62-klassenlegende.md` §5, §10, §13, `adr/0035`, `KLAERUNGEN.md` B9, `architekturplan.md` 3.1 und `.importlinter`, Entscheidungslog bis 27.11.2026.

Belegstufen: **M** in dieser Session gemessen (QGIS 3.34.4 LTR, für die Messung in die Cloud-Sitzung installiert, nicht Teil des Repos), **P** am Quelltext gelesen (Stand `main` nach #424), **A** eigene Ableitung.

---

## 1. Ziel

Jede Datendatei eines Export-ZIPs bekommt eine `<name>.qml` daneben. QGIS lädt sie beim Öffnen von `<name>.tif` von selbst [M], und die Datei sieht aus wie die Ebene in der App: dieselbe Farbskala mit denselben Enden, dieselbe Streckung je Kanal, dieselben Klassenfarben und -namen. Was die `.qml` zeigt, kommt aus dem Look, den die Ebene beim Export trägt; trägt sie keinen passenden, aus dem Look der Collection (M5-60).

**Nicht Teil:** neue Texte oder Felder im Frontend, eine Legende als eigene Datei, eine `.qml` für Masken (A1), die ganze Szene „per band“ aus dem Browser (F5).

---

## 2. Ausgangslage

### 2.1 Wege, die Rasterdateien in ein ZIP legen [P]

| Weg | Wo das ZIP entsteht | Rasterdateien | Was dort über die Bänder bekannt ist |
|---|---|---|---|
| „Download crop“ (synchron) | `api` → `access/download.py::build_crop_zip` (im Speicher) | `exports/<name>.tif` je Datei des Plans, dazu `<name>_mask.tif` | `BandMeta` je Band (Einheit, Klassen, `scale`/`offset`), aus Items und Registry |
| Export-Job (zu großer Zuschnitt, ganze Szene `per_resolution`/`multi_band`) | Worker, `processing/export.py::export` (auf Platte) | dieselben Namen | `Attachments.bands` (`BandMeta`), von `api` beim Annehmen gebaut |
| Processing-Ergebnis (Raster-Job, Index-Download #264) | `api`, `processing_route.py::_job_members` (lazy aus dem Store) | `result.tif`, `mask.tif` | `status.result.properties.bands` (Name, Typ, Klassen, `earthx:source_values`, Statistik mit 2./98. Perzentil) |
| Bündel mehrerer Ergebnisse | `api`, `read_bundle` | je Teil wie oben | wie oben |
| Ganze Szene `per_band` | Browser (`originalsZip.ts`, NM4-33) | Originaldateien der Quelle | Items im Browser; kein Byte über die Plattform |

Klassen tragen heute schon die Farbtabelle in der GeoTIFF und Namen/RAT in `<datei>.tif.aux.xml` (M5-62). Den Look eines Bands veröffentlicht die Collection (`earthx:look`, M5-60); im Backend liefert ihn `DatasetConfig.look_of(band)`. Die Bereiche im Frontend sind seit M5-68 überall physikalisch (Ausnahme: `stored` am Standardbild der Registry, das die Ansicht beim Öffnen hebt).

### 2.2 Was QGIS tut [M]

Gemessen mit QGIS 3.34.4 (PyQGIS, synthetische GeoTIFF `uint16` mit `scale` 0.0001, `offset` −0.1):

1. **QGIS wendet `scale`/`offset` der GeoTIFF an.** Der Provider meldet den Datentyp `Float32` statt `UInt16`, Blockwerte und Statistik sind physikalisch (gespeichert 100 → −0.09). Ein Min/Max in gespeicherten Werten (z. B. 1200–3400) läge in QGIS also neben den Daten. → F1.
2. **`<name>.qml` neben `<name>.tif` wird beim Öffnen geladen**, ohne Zutun.
3. **QGIS rechnet Min/Max beim Laden nicht neu**, auch nicht bei `<limits>CumulativeCut</limits>`: Die Zahlen der Datei gelten. Ein „gemessener“ Look braucht also Zahlen in der `.qml`; QGIS misst nicht selbst.
4. **Kein Schema:** Für `.qml` gibt es kein veröffentlichtes Schema; der `DOCTYPE` verweist auf eine DTD, die es nicht gibt. Prüfbar ist die Form gegen das, was QGIS selbst schreibt: QGIS liest eine `.qml` und schreibt sie mit „Symbologie“ wieder aus (`saveNamedStyle`). Diese Ausgabe ist die Referenzdatei (§7).

Die Renderer, die QGIS dafür schreibt: `singlebandpseudocolor` (Farbskala: `colorrampshader` mit `item`s, interpoliert, und `colorramp` vom Typ `gradient` mit Stopps), `singlebandgray` (Streckung `StretchToMinimumMaximum`), `multibandcolor` (je Kanal eine Streckung), `paletted` (`paletteEntry` mit Wert, Farbe, Name).

---

## 3. Form: der Stil des Auftrags

Ein Auftrag trägt höchstens **einen** gezeichneten Look, den der Ebene, in physikalischen Werten (M5-68), in einer Form für alle Wege:

```json
{"band": "red", "colormap": "viridis", "range": [0.02, 0.24]}
{"band": "dtm", "colormap": null, "range": [400, 1200]}
{"rgb": ["nir", "red", "green"], "ranges": [[0, 0.5], [0, 0.3], [0, 0.3]]}
```

- `band`: Asset-Schlüssel (Zuschnitt, Export) bzw. Bandname des Ergebnisses (`properties.bands[].name`). `colormap` aus der Liste des Tilers (`GET /colormaps`, ohne Klassentabellen) oder `null` für Grau. `range`: endlich, unten < oben.
- `rgb`: drei Bänder und je Kanal ein Bereich.
- Ein Klassenband braucht keinen Look: Seine Farben und Namen kommen immer aus `band_classes` (M5-62).

**Transport (der Look kommt mit dem Auftrag):**

| Weg | wo der Stil steht |
|---|---|
| „Download crop“ | Feld `style` im Body von `POST /collections/{dataset}/download` |
| Export-Job | Eingabe `exportStyle` neben `aoiProvenance` im Umschlag des Auftrags; `api` prüft sie und legt sie in die `Attachments` (nicht ins Rezept: Hash und `recipe.json` bleiben) |
| Ergebnis, Bündel | Query-Parameter `style` (JSON) an `result.zip` bzw. `bundles/{id}`; `api` baut `result.qml` beim Zusammenstellen; das ETag des ZIPs folgt dem Inhalt |

Der **Look der Collection** je Band (`look_of`, M5-60) reist ebenso mit: `api` legt ihn in `BandMeta.look` (neu, optional; JSON ohne Feld gilt als „kein Look“), so dass der Export-Job nichts aus der Registry liest (B9). Dazu das Echtfarbbild der Collection (`true_color`, F3).

**Wo der Stil herkommt (Frontend, PR 2):** aus dem angewandten Look der Ebene, für die der Dialog offen ist (`restore.appliedRender`), bzw. der Ansicht (`appliedRender`); nur Angewandtes zählt, nicht ungespeicherte Felder (A5):

| Ebene zeigt | Stil |
|---|---|
| ein Band (`band`), mit oder ohne Farbskala | `{band, colormap, range}` |
| das Standardbild aus einem Band mit Farbskala (DEM, MeteoSchweiz) | `{band: Asset des Standardbilds, colormap, range}` |
| eine Komposit-Vorgabe (`false_colour_ir`, `swir`) | `{rgb: Bänder der Vorgabe, ranges}` |
| Index (heruntergeladen als Index-Ergebnis) | `{band: Name des Ergebnisbands, colormap, range}` an `result.zip` |
| Ergebnis-Ebene | `{band: Name des Bands an bidx, …}` bzw. `{rgb: …}` |
| Echtfarbbild aus einem Hilfsbild (Sentinel-2 `visual`), Klassen-Standardbild, sonst nichts | kein Stil (Rückfall §4) |

---

## 4. Regel: welcher Renderer für welche Datei

Je Datendatei, die erste passende Zeile gilt [A]:

| # | Fall | Renderer |
|---|---|---|
| 1 | Stil `rgb`, alle drei Bänder in dieser Datei | `multibandcolor` mit den Bandnummern der Datei und den Bereichen je Kanal |
| 2 | Stil `band`, das Band liegt in dieser Datei | Klassenband → `paletted`; sonst `singlebandpseudocolor` mit Farbskala und Bereich (ohne Farbskala `singlebandgray`) auf dieser Bandnummer |
| 3 | Datei aus einem Band, das ein Kanal des Stils `rgb` ist | `singlebandgray` mit der Streckung dieses Kanals (F2) |
| 4 | die drei Bänder des Echtfarbbilds der Collection liegen in dieser Datei | `multibandcolor`, je Kanal 2.–98. Perzentil gemessen (F3) |
| 5 | sonst: das erste Band der Datei (F4) | Klassenband → `paletted`; Look der Collection → `singlebandpseudocolor` (fest: seine Zahlen; gemessen/Perzentile: gemessen); kein Look → `singlebandgray`, 2.–98. Perzentil |

**Zahlen:** immer physikalisch, ohne Umrechnung, weil QGIS `scale`/`offset` der Datei anwendet [M, §2.2] (F1). Wo der Look „gemessen“ ist, misst der Export einmal die geschriebene Datei, bei Zuschnitt und Export-Job aus der Übersicht bzw. verkleinert auf höchstens 1024 Pixel Kantenlänge, und rechnet die Perzentile mit `scale`/`offset` in physikalische Werte (A3). Ergebnisse messen nichts: Ihre Statistik steht im Item (2. und 98. Perzentil).

**Ergebnisse ohne Stil** (Processing-Manager, Bündel; F6): Klassenband → `paletted`; Band mit `earthx:source_values` → Look dieses Bands aus der Collection (fest, sonst 2./98. Perzentil der Statistik); sonst `singlebandgray` mit 2./98. Perzentil der Statistik.

---

## 5. Form der `.qml` [M]

Wie QGIS 3.34 sie mit der Kategorie „Symbologie“ schreibt: `<qgis version="3.34.4" styleCategories="Symbology">` mit `pipe` → `rasterrenderer` und den Stufen danach (`brightnesscontrast`, `huesaturation`, `rasterresampler`), `minMaxOrigin` mit `limits` `None` (die Zahlen gelten, §2.2 Punkt 3).

- **Farbskala:** dieselbe Tabelle mit 256 Farben, die der Tiler zeichnet (`access/colormaps.py::COLORMAPS`, rio-tiler und `colormap_data/`, `_r` umgekehrt), als 256 `item`s gleichmäßig von Min bis Max, interpoliert, `clip="0"` (außerhalb die Endfarben, wie der Tiler). Dieselben 256 Farben als `colorramp` (`gradient`, `color1`, `color2`, 254 `stops`), damit QGIS beim Neu-Einteilen dieselbe Rampe nutzt; kein Rampen-Name von QGIS. Legende stetig (`useContinuousLegend`).
- **Klassen:** `paletted`, je Klasse `paletteEntry` mit Wert, Farbe (`#rrggbb`), `alpha="255"` und Name, aus derselben Liste wie Farbtabelle und `.aux.xml` (`band_classes`). Nodata zeigt QGIS durchsichtig, wie der Tiler.
- **Grau/RGB:** `singlebandgray` bzw. `multibandcolor` mit `StretchToMinimumMaximum` je Kanal.
- Zahlen in kürzester exakter Schreibweise (`repr`), Texte XML-maskiert.

Name: `<name>.qml` zu `<name>.tif` (`B04_red_10m.qml`, `bands_10m.qml`, `result.qml`), im selben Ordner.

---

## 6. Umsetzung [A]

**PR 1 (Backend und dieser Plan):**

| Teil | Stelle |
|---|---|
| Stil des Auftrags (`ExportStyle`, Prüfung, JSON), Regel §4, Messung, Schreiben der `.qml` | `backend/earthx/access/qgis_style.py` (neu) |
| `BandMeta.look` (Look der Collection, optional im JSON) | `backend/earthx/access/band_export.py` |
| Zuschnitt: `.qml` je Datei im ZIP; Feld `style` | `access/download.py`, `api/tiler.py` |
| Export-Job: Eingabe `exportStyle`, `Attachments.style`, `.qml` je Datei | `api/processing_route.py`, `api/intake.py`, `processing/export.py` |
| Ergebnis und Bündel: Query `style`, `result.qml` | `api/processing_route.py` |
| Nachträge | `adr/0028` §6, Entscheidungslog |

**PR 2 (Frontend):** Stil aus dem angewandten Look (§3, eine Funktion), mitgeschickt in `downloadCrop`, im Export-Auftrag (Zuschnitt zu groß, ganze Szene als Job), an `result.zip` der Ergebnis-Ebene und des Index-Downloads; Browser-Check `band-download.cjs` erweitert (der Body trägt den Stil).

Importgrenzen: `qgis_style` liegt in `access` (wie `band_export`) und liest nur `access.colormaps` und `catalog.registry` (`Look`); `processing` und `api` importieren es (erlaubt). Keine Lockerung.

---

## 7. Tests und Checks

- **Referenzdateien:** Für vier synthetische Fälle (Farbskala auf einem skalierten Band, Grau, RGB, Klassen) liegt unter `backend/tests/fixtures/qgis/` die `.qml`, die QGIS 3.34.4 aus der erzeugten Datei liest und wieder schreibt, samt dem Skript, das sie erzeugt (nur mit PyQGIS lauffähig, nicht in CI). Der Test erzeugt dieselben Fälle und vergleicht `pipe` Element für Element (Namen, Attribute, Zahlen) mit der Referenz: Was QGIS liest und zurückschreibt, ist genau das Erzeugte.
- **Regel und Fehlerfälle:** jede Zeile von §4; Stil mit unbekanntem Band, unbekannter oder Klassen-Farbskala, `NaN`, umgekehrtem Bereich, zwei statt drei Bändern, falschen Typen, zu langem Text → 422 bzw. Abweisung; JSON ohne `look` (ältere Aufträge) liest sich; Messung auf skaliertem Band, leerem und konstantem Band.
- **Wege:** Zuschnitt `per_band` und `multi_band` (je Datei eine `.qml`, keine für Masken), Export-Job schreibt dieselben `.qml` wie der Zuschnitt (Byte für Byte, wie bei `.aux.xml`), Ergebnis mit und ohne `style`, Bündel, ETag ändert sich mit dem Stil.
- **In der Session [M], nicht in CI:** QGIS 3.34 öffnet erzeugte Dateien mit ihrer `.qml`; Renderer und Zahlen wie erwartet; ein gerendertes Pixel hat die Farbe, die der Tiler für denselben Wert zeichnet.
- **Frontend:** Stil je Fall der Tabelle §3 (Vitest), Body von `downloadCrop` und Export-Auftrag, Query an `result.zip`; Browser-Check `band-download.cjs`.

---

## 8. Fragen an Otto

**F1 — Min/Max bei skalierten Bändern**
QGIS 3.34 wendet `scale`/`offset` der GeoTIFF an und zeigt physikalische Werte [M, §2.2]. „Umgerechnet in gespeicherte Werte“ läge dort neben den Daten.
1. Min/Max physikalisch in die `.qml`, ohne Umrechnung; sie passen zu dem, was QGIS aus der Datei liest. **(Empfehlung)**
2. Gespeicherte Werte in die `.qml` und `scale`/`offset` nicht mehr als Tags in die Datei (änderte `adr/0028` §1 „Skalierung und Offset als Dateitags“).

**F2 — RGB und „per band“**
Bei „per band“ liegen die drei Kanäle in drei Dateien; ein Farbbild über mehrere Dateien kann eine `.qml` nicht beschreiben.
1. Jede Kanal-Datei grau mit der Streckung ihres Kanals; ein Farbbild gibt es nur, wenn alle drei in einer Datei liegen. **(Empfehlung)**
2. Jede Kanal-Datei mit dem Look ihres Bands aus der Collection (Farbskala).
3. Wie 1, dazu eine `.vrt`, die die drei Dateien als Farbbild zusammenfasst.

**F3 — Echtfarbbild aus einem Hilfsbild (Sentinel-2 `visual`)**
Die Ansicht zeigt bei Sentinel-2 als „RGB“ das fertige Bild der Quelle (TCI, `uint8`, 0–255); es ist nicht exportierbar, und seine Streckung gilt nicht für die Reflexionsbänder.
1. Liegen `red`, `green`, `blue` (`true_color` der Registry) in einer Datei, zeigt sie die `.qml` als Farbbild, je Kanal 2.–98. Perzentil der Datei (wie „Enhance contrast“). **(Empfehlung)**
2. Kein Farbbild; die Datei zeigt ihr erstes Band mit dessen Look.

**F4 — Mehrbandige Datei ohne Farbbild**
Eine `.qml` zeichnet ein Band (außer RGB).
1. Das Band, das die Ebene zeigt, wenn es in der Datei liegt; sonst das erste Band der Datei mit seinem Look. **(Empfehlung)**
2. Immer das erste Band.

**F5 — Ganze Szene „per band“ aus dem Browser (NM4-33)**
Die Dateien kommen direkt von der Quelle; die Plattform sieht kein Byte und kann gemessene Looks nicht messen.
1. Eigene Folgeaufgabe: Der Browser holt die `.qml` bei der Plattform (ohne Daten), gemessene Looks mit dem Bereich der Ansicht. **(Empfehlung)**
2. Hier mit erledigen (geschätzt +150 Zeilen, dritter Weg der Stilbildung).
3. Diese ZIPs bleiben ohne `.qml` (Originaldateien der Quelle).

**F6 — Ergebnis ohne Look der Ebene** (Download aus dem Processing-Manager, Bündel)
1. Klassen → paletted; unverändertes Band der Quelle → dessen Look; sonst grau mit 2./98. Perzentil aus der Statistik des Ergebnisses. **(Empfehlung)**
2. Wie 1, zusätzlich der Look des letzten Operators (`x-earthx-looks`, `adr/0035`), wo er einen hat.

**F7 — Schnitt**
1. Zwei PRs: Plan und Backend, dann Frontend. **(Empfehlung)**
2. Ein PR (geschätzt über 400 Zeilen ohne Tests).

### 8.1 Auslegungen (gelten, wenn du nicht widersprichst)

- **A1 — Masken:** `<name>_mask.tif` und `mask.tif` bekommen keine `.qml`; sie werden in der App nicht gezeigt, QGIS zeigt 0/1 grau.
- **A2 — Exporte ohne `layout`** (gespeicherte Rezepte von vor NM4-75, flache Dateien in EPSG:4326): ohne `.qml`; ihnen fehlen die Bandangaben (`Attachments.bands`).
- **A3 — Messung:** auf der Übersicht bzw. verkleinert auf höchstens 1024 Pixel Kantenlänge, damit ein Export von 5 GB nicht zweimal gelesen wird; Abweichung zur Messung der Ansicht (über die AOI, festes Histogramm) im Bereich weniger Promille der Spanne. Ein Band ohne gültigen Wert bekommt 0–1, ein konstantes Band seinen Wert bis Wert + 1 (wie das Histogramm, `statistics.py`).
- **A4 — Rampe:** 256 Stützstellen, wie der Tiler sie hat; QGIS interpoliert linear dazwischen, der Tiler wählt die Stufe. Der Unterschied ist höchstens ein halber Schritt der Tabelle.
- **A5 — „Gerade eingestellt“** heißt angewandt (Grundsatz „Apply“, ENTSCHEIDUNGEN §2): getippte, nicht angewandte Felder zählen nicht.
- **A6 — Nicht im Rezept:** Der Stil steht nicht im Rezept und nicht in `recipe.json`; Hash und Wiederholbarkeit des Rezepts bleiben. Ein und derselbe Job kann so mit verschiedenen Stilen heruntergeladen werden.
- **A7 — Version:** Die `.qml` trägt `version="3.34.4"` (geprüft gegen QGIS 3.34 LTR). Ältere QGIS 3.x lesen dieselben Elemente; nicht gemessen.

---

## 9. Was Otto in QGIS prüft (nach PR 2)

Je Fall: Export starten, ZIP entpacken, die `.tif` in QGIS per Ziehen öffnen (die `.qml` lädt von selbst), dann *Layer-Eigenschaften → Symbologie* ansehen.

1. **Sentinel-2-Einzelband:** Szene öffnen, Band `red` wählen (viridis, gemessen), „Download crop“, „per band“. `B04_red_10m.tif` in QGIS: „Singleband pseudocolor“, Min/Max wie die Legende der App (z. B. 0,02–0,24), dieselben Farben. Dann eine Farbskala und einen Bereich von Hand anwenden, nochmals exportieren: QGIS zeigt diese.
2. **RGB:** Quick processing „False colour (IR)“ wählen, Bänder `nir`, `red`, `green`, „One multi-band file“ (oder „per resolution“, alle 10 m). `bands_10m.tif`: „Multiband color“, Rot/Grün/Blau = die drei Bänder, Min/Max je Kanal wie in „Scale“ der App. Mit „per band“: jede der drei Dateien grau mit der Streckung ihres Kanals (F2).
3. **WorldCover:** Zuschnitt, „per band“. `Map_10m.tif` (Name nach Band): „Paletted/Unique values“, Klassen mit Namen und Farben wie in der Legende der App; Werte ohne Klasse durchsichtig.
4. **Processing-Ergebnis:** z. B. NDVI als Index herunterladen (Ebene mit Index, „Download“ → „Index“) oder ein Ergebnis-Layer über ⇩. `result.tif` mit `result.qml`: Farbskala und Bereich wie die Ebene in der App. Ohne Ebene (Processing-Manager, „Download (ZIP)“): grau 2.–98. Perzentil (F6).
