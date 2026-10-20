# M4-32 — Statistik je Ergebnis als Vorgabe für die Farbskala

**Stand:** 20.10.2026, beauftragt von Otto. Die Aufgabe kommt vor der M4-Abnahme.
**Stufe B:** Erst kommt der Plan im Draft-PR, Otto gibt ihn frei, dann folgt der Code. Der Grund: Die Aufgabe ändert Ergebnis-Bytes, betrifft also die Version, und sie berührt Rechenzeit und Bitgleichheit.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Nach dem Merge von M4-13c-5 (#166).
**Startsatz:** „Führe Aufgabe M4-32 aus `docs/plans/m4-32-ergebnis-statistik.md` aus.“

## 1. Anlass

M4-13c-5 zeigt Job-Ergebnisse als Layer. Jedes Gleitkomma-Ergebnis wird dabei mit dem Wertebereich des Panels gezeichnet (−1 bis 1, `rdylgn`). Für NDVI passt das. Ein DEM nach Reproject erscheint dagegen einfarbig, eine Reflexion dunkel.

**Otto (20.10.2026):** Das soll vor der M4-Abnahme behoben sein.

## 2. Ziel

- Jedes Raster-Ergebnis trägt eine kleine Statistik je Band: min, max, Mittelwert, 2- und 98-Perzentil, Anteil gültiger Pixel.
- Karte und Panel nehmen sie als Vorgabe für die Farbskala (2–98 %). Der Nutzer kann sie wie bisher von Hand ändern.

## 3. Im Plan mit Optionen, Empfehlung und Quellen klären

1. **Berechnung:**
   - Im Kern während der Blockschleife, ohne zweiten Lesedurchgang.
   - Min, max und Mittelwert sind exakt.
   - Perzentile über ein festes Histogramm oder einen anderen deterministischen Weg. Stand der Technik mit Quellen: GDAL `ComputeStatistics` und `GetHistogram`, rio-tiler `statistics`, übliche Verfahren für Perzentile auf Datenströmen.
   - Das Ergebnis muss bitgleich sein: zweimal gerechnet und Cloud gegen Runner (`adr/0014` §6.3).
2. **Ablage:**
   - (a) als Metadaten in `result.tif` (GDAL-Tags `STATISTICS_*`, dazu Perzentile), lesbar für den `tiler` ohne Datenbank, oder
   - (b) im Ergebnisdokument bzw. im STAC-Item des Ergebnisses (`raster:bands` `statistics`), oder
   - beides.

   Der Plan klärt auch, wie Frontend und `tiler` an die Werte kommen.
3. **Kosten:** Messung der Zusatzzeit und des Spitzenspeichers bei 4096² (Grenze 500 MB, `VmHWM`). Der Faktor in der Schätzung ändert sich nur, wenn die Messung es verlangt.
4. **Version:** Ändern sich die Bytes von `result.tif` durch die Tags, muss der Cache-Schlüssel das abbilden (`earthx.__version__`, wie bei M4-26). Bestehende gecachte Ergebnisse ohne Statistik: Das Frontend fällt auf den heutigen Bereich zurück.
5. **Vorgabe im Frontend:**
   - 2–98 % für Gleitkomma.
   - Ganzzahl unverändert.
   - Colormap-Vorgabe je Ergebnis: einfarbig-graue Skala oder `viridis` für unbekannte Größen, `rdylgn` nur bei NDVI-artigen Ausdrücken. Der Plan schlägt die Regel vor.
   - Die T1-Vorschau (Band math) bleibt bei ihrem bisherigen Verhalten, außer der Plan begründet etwas anderes.
6. **Runner:** Der Runner schreibt dieselbe Statistik, denn derselbe Kern liefert dieselben Bytes.

## 4. Grenzen

- Der Worker-Kern bleibt zustandslos. Es gibt keine Datenbank, keinen Objektspeicher und kein `gateway` im Kern.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Oberflächentexte nur auf Englisch.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- **Tests:**
  - Statistik gegen eine unabhängige Rechnung auf synthetischen Rastern: Gleitkomma mit NaN, Ganzzahl mit nodata, DEM-artig, NDVI-artig.
  - Zweimal gerechnet bitgleich.
  - Runner gleich Kern.
  - Speichertest unter 500 MB.
  - Das Frontend nimmt die Vorgabe aus der Statistik und fällt ohne Statistik zurück.
  - Gegenprobe: Mit dem alten Code scheitern die neuen Tests.
- **Prüfanleitung für Otto:**
  - DEM-Reproject-Job: Das Ergebnis erscheint auf der Karte mit sichtbarem Relief.
  - NDVI-Job: Das Ergebnis erscheint wie bisher.
- Alle vier Pflicht-Checks der CI sind grün.
- **Doku:**
  - Nachtrag in `adr/0014`, falls die Bytes des Ergebnisses oder §6.3 berührt sind.
  - Log-Zeilen.
  - Zeile M4-32 in `docs/plans/m4-processing-kern.md` §3.
- Vor „fertig“ ist main geholt.

## 6. Plan mit Messung (20.10.2026, zur Freigabe durch Otto)

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Belegstufen wie in `adr/0014`: [P] Primärquelle gelesen, [M] gemessen, [S] Sekundärquelle, [A] eigene Ableitung. Gemessen wurde mit einem Prototyp im Kratzverzeichnis der Sitzung, auf `main` nach #166 (earthx 0.4.1, GDAL 3.12.2, rasterio 1.5.2, rio-cogeo 7.0.3, rio-tiler 9.4.6, numpy 2.5.3, Python 3.12.3, x86_64).

**Kurzfassung.**

- **Rechnen:** im letzten Durchgang des Kerns, auf den Werten, die in `result.tif` landen, Block für Block, ohne zweiten Lesedurchgang. Min, Max und Anzahl sind exakt. Der Mittelwert ist exakt gerundet: Die Summe läuft ganzzahlig über die Bitmuster, unabhängig von Reihenfolge und Rechner. Die Perzentile kommen aus einem festen Histogramm über das Bitmuster (65 536 Fächer je Band): bei Ganzzahl bis 16 bit exakt, sonst auf höchstens 0,8 % des Werts genau. Die Standardabweichung rechnet der Kern blockweise wie GDAL (Welford/Chan); sie ist nötig, damit GDAL die gespeicherten Werte überhaupt liest [M].
- **Bitgleich [M]:** gleiche Statistik bei anderer Blockung und umgekehrter Blockfolge, `result.tif` bei Wiederholung Byte für Byte gleich, die numpy-Summen gleich über die SIMD-Stufen X86_V4, X86_V3 und X86_V2.
- **Ablage (Empfehlung: beides):** als GDAL-Tags `STATISTICS_*` je Band in `result.tif` und als STAC-`statistics` an den `bands` der Eigenschaften. Das Frontend liest sie aus dem Ergebnisdokument, das es heute schon liest. Der `tiler` braucht nichts Neues.
- **Kosten bei 4096² [M]:** Spitzenspeicher (`VmHWM`) +0 bis +1,8 MB, weit unter 500 MB. Zeit im Prototyp +3 % (`reproject`) bis +22 % (Band-Math). Optimiert sind es 35–50 ms je Megapixel und Band, beim Band-Math also etwa +10 bis +13 % (§6.5). Vorschlag: Der Faktor der Schätzung bleibt (Frage 8).
- **Version:** Die Tags ändern die Bytes von `result.tif`, deshalb 0.4.1 → 0.4.2. Ergebnisse ohne Statistik zeichnet das Frontend wie heute.
- **Frontend:** Ein Gleitkomma-Ergebnis bekommt 2–98 % mit `viridis`. Ein index-artiges Ergebnis (Band-Math, alle Werte in −1…1) bleibt wie heute bei −1…1 und `rdylgn`. Ganzzahl bleibt unverändert, ebenso die T1-Vorschau.
- **Fragen an Otto:** acht, je mit Empfehlung (§6.9).

### 6.1 Stand der Technik (§3 Punkt 1)

**GDAL `ComputeStatistics` [P]** (`gcore/gdalrasterband.cpp`, Tag `v3.12.2`, über `raw.githubusercontent.com`, gelesen am 20.10.2026):
- Ein Lesedurchgang mit Welford je Block. Die Blöcke werden mit dem parallelen Verfahren von Chan zusammengeführt (Z. 6938–6947, 7480–7520). Für x86_64 gibt es einen eigenen SSE2-Pfad (Z. 6700ff., 7520ff.). Mit `bApproxOK` rechnet GDAL auf einer Übersicht.
- Es schreibt `STATISTICS_MINIMUM`, `_MAXIMUM`, `_MEAN`, `_STDDEV` und `_VALID_PERCENT`. `SetStatistics` formatiert mit `%.14g` (Z. 7886–7903).
- Perzentile gibt es nicht.

**GDAL `GetStatistics` [P][M]** (Z. 5214–5243):
- Es nimmt die gespeicherten Werte nur, wenn jedes angefragte Feld als Tag vorliegt.
- rasterio fragt alle vier an. Gemessen: Ohne `STATISTICS_STDDEV` rechnet `statistics()` neu und übergeht die Tags. Mit `STATISTICS_STDDEV` liefert es die Tags.
- rio-cogeo 7.0.3 reicht Band-Tags mit `forward_band_tags=True` in die COG weiter (`cogeo.py` Z. 401–404) [P]. Gemessen kommen sie in `result.tif` an; eine `.aux.xml` entsteht nicht [M].

**GDAL `GetHistogram` [P]** (Z. 4189ff.):
- Es braucht Minimum, Maximum und Zahl der Fächer vorab, also einen zweiten Durchgang oder eine Schätzung.
- Mit `bApproxOK` nimmt es die kleinste Übersicht.

**rio-tiler `statistics` [P]** (`rio_tiler/utils.py::get_array_statistics` Z. 87–230, `io/rasterio.py` Z. 227–255, Version 9.4.6 im venv):
- Es arbeitet auf dem ganzen Array im Speicher: `numpy.unique` je Band, Sortieren für gewichtete Quantile, `numpy.histogram` mit 10 Fächern.
- Gelesen wird mit `max_size=1024`, also auf einer Übersicht. Bei großen Rastern ist das eine Näherung.
- Feldnamen: `percentile_2`, `percentile_98`. Das Frontend liest sie schon bei der Ansicht einer Quelle (`render.ts::autoRescale`).

**STAC 1.1 Statistics Object [P]** (`commons/common-metadata.md`, Tag `v1.1.0`, Z. 258–312):
- Ein Band trägt `statistics` mit `minimum`, `maximum`, `mean`, `stddev`, `count` und `valid_percent`.
- Das Objekt darf um weitere Größen erweitert werden („can also be extended with other statistical sizes“).
- Die Raster-Erweiterung kennt zusätzlich `raster:histogram` (`stac-extensions/raster`, README Z. 46, 144ff.) [P].

**Perzentile auf Datenströmen:**
- **DDSketch** [P] (README von `DataDog/sketches-py`; Paper Masson, Rim, Lee, VLDB 2019, nicht erreichbar):
  - Logarithmische Fächer mit fester relativer Genauigkeit.
  - Zusammenführbar, also unabhängig von der Reihenfolge.
- **HdrHistogram** [P] (README von `HdrHistogram/HdrHistogram`): dieselbe Idee mit fester Zahl signifikanter Stellen.
- **t-digest** (Dunning), **P²** (Jain/Chlamtac 1985) und **Greenwald-Khanna** [S]:
  - Das Ergebnis hängt von der Reihenfolge der Werte ab, beim t-digest auch von der Art der Zusammenführung.
  - t-digest und KLL bräuchten eine neue Abhängigkeit oder eigenen Code mit mehr Zustand.

**Folgerung [A]:**
- Das obere Stück des Bitmusters eines `float32` ist schon ein logarithmisches Histogramm wie bei DDSketch und HdrHistogram: Vorzeichen, 8 Bit Exponent und 7 Bit Mantisse ergeben 65 536 Fächer, relative Breite 2⁻⁷.
- Es braucht keinen Wertebereich vorab und keinen zweiten Durchgang.
- Die Zählungen sind ganze Zahlen. Damit ist das Ergebnis unabhängig von Blockung, Reihenfolge und Rechner.

### 6.2 Berechnung (Vorschlag)

**Ort.**
- `_Run.write_pass` mit `count_valid=True`, also der letzte Durchgang. Gerechnet wird auf `data` nach `_cast`, das sind genau die Werte, die geschrieben werden.
- Ein neues Modul `processing/statistics.py` ohne Abhängigkeit außer numpy und der Standardbibliothek. `.importlinter` bleibt unverändert.
- Export (`crop`) und die T1-Kacheln berührt es nicht.

**Grundgesamtheit:**
- Je Band die nicht maskierten, endlichen Werte der ganzen `result.tif` (Bounding Box, Frage 2).
- `±inf` kann nur ein Überlauf beim Schreiben nach `float32` sein; Band-Math maskiert Nicht-Endliches schon selbst. Solche Werte zählen nicht mit.
- `valid_percent` = `count` / (Breite × Höhe) × 100.

**Größen je Band:**

| Größe | Weg | Eigenschaft |
|---|---|---|
| `minimum`, `maximum`, `count` | `min`/`max`/Anzahl je Block, dann über die Blöcke | exakt |
| `mean` | Gleitkomma: Summe je Vorzeichen und Exponent über die ganzzahligen Mantissen (`bincount` mit Gewichten; jede Teilsumme < 2⁴⁴, also exakt in float64), am Ende als Python-`int`/`Fraction` → `float`. Ganzzahl: `int64`-Summe je Block (< 2⁵² bei 2²⁰ Werten) | exakt gerundet, unabhängig von Reihenfolge und Rechner [M] |
| `stddev` | Welford/Chan wie GDAL: Mittel und Quadratsumme der Abweichungen je Block in float64 (numpy), die Blöcke in fester Folge zusammengeführt; Grundgesamtheit (geteilt durch `count`) wie GDAL | deterministisch, nicht exakt (Frage 4) |
| `percentile_2`, `percentile_98` | Histogramm: Ganzzahl bis 16 bit mit einem Fach je Wert; sonst Schlüssel aus dem ordnungserhaltenden Bitmuster von `float32` (Werte anderer Typen vorher nach `float32`, monoton), obere 16 Bit, 65 536 Fächer zu `int64` je Band (512 KB). Rang nach „nearest rank“, `ceil(p/100 · count)`. `percentile_2` ist die untere Kante seines Fachs, `percentile_98` die obere, beide geklemmt auf [`minimum`, `maximum`] | Ganzzahl ≤ 16 bit exakt; sonst höchstens 2⁻⁷ ≈ 0,8 % des Betrags vom wahren Wert, nach außen gerundet: [p2, p98] enthält stets den wahren Bereich (Frage 3) |

- **Kein gültiger Wert:** `statistics` = `{"count": 0, "valid_percent": 0.0}`, ohne Lagemaße und ohne Tags außer `STATISTICS_VALID_PERCENT`. So kommt nie NaN in JSON oder `jsonb`.
- **Speicher:** je Band 512 KB Histogramm, bei 48 Bändern (16 Assets, `MAX_ORDER_ASSETS`, zu je drei) 24 MB. Feinere Fächer (2²⁰, 8 MB je Band) wären dort zu groß.
- **`int32`, `uint32`, `float64`:** Der Schlüssel entsteht über `float32`. Zur Grenze von 0,8 % kommt dort eine Rundung nach `float32`; bei 32-bit-Ganzzahl rundet der Kern p2 ab und p98 auf ganze Zahlen. Diese Typen sind als Ausgabe selten.
- **Format der Tags:** `repr(float)`, die kürzeste Form, die denselben `float` ergibt, statt GDALs `%.14g`. Tag und Eigenschaft tragen dann dieselbe Zahl.

### 6.3 Ablage und Weg zu Frontend und `tiler` (§3 Punkt 2)

| | (a) nur Tags in `result.tif` | (b) nur Ergebnisdokument / STAC | **(c) beides (Empfehlung)** |
|---|---|---|---|
| Bytes von `result.tif` | ändern sich → Version | unverändert | ändern sich → Version |
| Download in GDAL-Werkzeugen | `statistics()` liest die Werte ohne Rechnung [M] | rechnen selbst | lesen die Werte |
| Frontend | bräuchte eine neue Route im `tiler` | liest `result.properties` wie heute | liest `result.properties` wie heute |
| `tiler` | könnte die Tags lesen (ohne Datenbank) | — | braucht nichts; das Frontend gibt `rescale` und `colormap_name` in die Kachel-URL wie heute |
| Runner | Tags in seiner `result.tif` | in `provenance.json` (`properties`) | beides |

**Weg der Werte:**
- `RunResult.properties["bands"][i]["statistics"]` geht über die Pipe des Kindes (`info["properties"]`) in die Spalte `result` des Laufs.
- Daraus entsteht der Link `result` des Ergebnisdokuments (`processing_route._results_document` reicht `properties` schon durch).
- Das Frontend liest `processingStore.readResults`.
- Der Runner schreibt dieselben `properties` in `provenance.json`.

**Tags je Band:**
- `STATISTICS_MINIMUM`, `_MAXIMUM`, `_MEAN`, `_STDDEV` und `_VALID_PERCENT` mit den Namen von GDAL.
- Dazu `EARTHX_PERCENTILE_2` und `EARTHX_PERCENTILE_98`. Ein eigenes Präfix, weil GDAL keine Namen für Perzentile hat (Vorschlag).
- Der Kern setzt sie auf die Datei des letzten Durchgangs; `cog_translate` bekommt `forward_band_tags=True`.

### 6.4 Bitgleichheit (§3 Punkt 1, `adr/0014` §6.3) [M]

| Prüfung | Ergebnis |
|---|---|
| Prototyp gegen unabhängige Rechnung (2048², `Fraction` für den Mittelwert, `numpy.percentile(method="inverted_cdf")`): DEM-artig float32, NDVI-artig mit 10 % NaN, `uint16` mit 20 % nodata 0, `int32` | Min/Max/Mittel exakt gleich. Perzentile: `uint16` exakt; DEM p2 −0,36 %, p98 +0,37 %; NDVI −0,16 % / +0,11 %; `int32` ±0,1 %; stets nach außen |
| Gleiche Raster, Blöcke 1024 gegen 512 in umgekehrter Folge | alle Felder gleich. `stddev` war in diesen vier Fällen auch gleich, hängt aber grundsätzlich von der Blockung ab; die ist fest (`BLOCK_SIZE`) |
| Lauf über den echten Kern (Prototyp eingehängt), dreimal je Fall | SHA-256 von `result.tif` jedes Mal gleich: 2048² und 4096² mit `scale` und `reproject`, 4096² mit Band-Math |
| numpy-Summen, Quadratsummen, Min/Max, `bincount` mit `NPY_DISABLE_CPU_FEATURES` auf X86_V4, X86_V3, X86_V2 (wie `adr/0016` §14.4 B/D) | Hash der Ergebnisse gleich auf allen drei Stufen |
| Echter Kern mit Statistik, `reproject` und Band-Math 4096², dieselben drei SIMD-Stufen | SHA-256 von `result.tif` je Fall gleich auf allen drei Stufen |

Für `stddev` ist die Reihenfolge der Summen fest; numpy summiert paarweise und gemessen gleich über die SIMD-Stufen. `sqrt` kommt aus Pythons `math` und ist nach IEEE 754 korrekt gerundet. Damit gilt für die Statistik dieselbe Zusage wie für die Pixel: bitgleich T2 ↔ T2L auf derselben Maschine und über Maschinen hinweg für das, was M4 erlaubt (`adr/0014` §15c).

### 6.5 Kosten (§3 Punkt 3) [M]

Aufbau wie `memory_run.py` (M4-07a, M4-10b): synthetisches COG, zwei Bänder `uint16`, Kindprozess mit `worker_environment()`, `GDAL_CACHEMAX` 64 MB, ohne `boto3`, `VmHWM`; Schritt `scale` (Testoperator, beide Bänder), `reproject` nach EPSG:3035, 10 m, `bilinear` (beide Bänder) oder Band-Math über die zwei Bänder (ein Band); Ausgabe `float32`. Je Fall drei Läufe abwechselnd ohne und mit Statistik (Prototyp mit `stddev`).

| Fall | Bänder mit Statistik | ohne: `VmHWM` / Zeit (Mittel) | mit: `VmHWM` / Zeit (Mittel) | Δ Zeit |
|---|---|---|---|---|
| `scale` 2048² | 2 | 288,1–288,3 MB / 2,38–2,81 s (2,54) | 288,2–288,5 MB / 2,91–2,98 s (2,96) | +0,42 s (+17 %) |
| `scale` 4096² | 2 | 369,7–370,0 MB / 10,26–11,04 s (10,69) | 370,3–370,4 MB / 12,08–13,23 s (12,52) | +1,83 s (+17 %) |
| `reproject` 2048² | 2 | 338,2–338,7 MB / 4,66–4,81 s (4,74) | 339,6–339,9 MB / 4,89–5,21 s (5,06) | +0,32 s (+7 %) |
| `reproject` 4096² | 2 | 417,3–417,6 MB / 19,11–20,81 s (19,92) | 418,8–419,1 MB / 19,75–20,95 s (20,44) | +0,52 s (+3 %) |
| Band-Math `(big_2 - big_1) / (big_2 + big_1)` 4096² | 1 | 348,8–348,9 MB / 5,76–6,50 s (6,06) | 348,8–349,1 MB / 7,16–7,73 s (7,41) | +1,35 s (+22 %) |

- **SIMD:** `result.tif` von `reproject` 4096² und von Band-Math 4096² mit Statistik hat mit `NPY_DISABLE_CPU_FEATURES` auf X86_V4, X86_V3 und X86_V2 je denselben SHA-256 (`5685b292…` bzw. `5c2a8afd…`).
- **Wiederholung:** Jeder Fall lieferte in allen drei Läufen denselben SHA-256. Mit Statistik unterscheidet er sich von dem ohne Statistik, weil die Tags hinzukommen.
- Der Prototyp ist nicht auf Tempo gebaut. Er kostet rund 80 ms je Megapixel und Band (Band-Math: 1,35 s für 16,7 MP).

**Aufschlüsselung je Block von 1024² und Band** (float32, 10 % maskiert, Mittel aus 20 Aufrufen, Schlüssel per XOR statt `where`, Exponent direkt aus `bits >> 23`):
- gültige Werte herausziehen 3–4 ms
- Histogramm 4–7 ms
- exakte Summe 15–16 ms
- Welford/Chan 7–10 ms
- Min/Max < 1 ms

Zusammen 35–50 ms je Megapixel und Band, etwa die Hälfte des Prototyps. Für Band-Math bei 4096² heißt das etwa +0,6 bis +0,8 s auf rund 6 s, also +10 bis +13 % [A]. Die Umsetzung misst das nach und nennt die Zahl im PR.

**Folgen:**
- **Speicher:** Die Grenze von 500 MB bleibt weit entfernt; der Zuwachs liegt bei höchstens 1,8 MB. `test_memory_8192.py` und `test_memory_reproject.py` laufen über den echten Kern und messen die Statistik danach mit. Ein eigener Speichertest ist nicht nötig.
- **Zeit:** Der Aufschlag hängt an Megapixel und Band der Ausgabe, nicht am Operator. Relativ wiegt er am meisten bei schnellen Operatoren (Band-Math, `scale`) und am wenigsten bei `reproject`.
- **Faktor (`adr/0014` §5.5):**
  - Die Faktoren sind relativ zu Band-Math = 1,0. Der Aufschlag ist je Megapixel und Band für jeden Operator gleich. Als Anteil wöge er deshalb bei `nearest` (0,4) am meisten.
  - Die Dauer ist aber eine Anzeige „etwa“, und die Kalibrierung gegen echte Läufe steht noch aus.
  - Vorschlag: der Faktor bleibt (Frage 8).
- **Einsparung:** Wer die Zeit drücken will, lässt den exakten Mittelwert weg (Frage 4, Option 2). Das spart etwa 15 ms je Megapixel und Band.

### 6.6 Version (§3 Punkt 4)

- Die Tags ändern die Bytes von `result.tif`. Das deckt `earthx.__version__` im Block `engine` des Cache-Schlüssels: 0.4.1 → **0.4.2**, wie bei M4-26 (`adr/0014` §15h).
- `recipe_version` und `op_version` bleiben, denn kein Operator und kein Feld des Rezepts ändert sich.
- Ergebnisse unter 0.4.1 bleiben unter ihrem alten Schlüssel stehen und werden nicht mehr getroffen.
- Jobs, die schon vor dem Deployment fertig waren, haben keine Statistik. Das Frontend zeichnet sie wie heute.
- Mit der Version ziehen nach:
  - `README.md` (Tag `earthx-runner:0.4.1`, Z. 423, 431)
  - `tests/fixtures/runner/recipe-ci.json` (`engine.earthx`)
  - für Ottos lokalen Beleg (Log 20.10.2026) ein neu gebautes Runner-Image 0.4.2; Cloud und Runner müssen dieselbe Version tragen.

### 6.7 Vorgabe im Frontend (§3 Punkt 5)

**Regel**, in `resultLayer.ts::resultRender`, der Reihe nach:

1. Ganzzahl-Ergebnis: unverändert (`{}`), wie heute.
2. Der Nutzer hat im Panel „Range and colormap“ einen Bereich angewandt, der von der Vorgabe (−1…1, `rdylgn`) abweicht: Dieser Bereich und seine Colormap gelten, wie heute (Frage 7).
3. Index-artig, also eine Band-Math-Eigenschaft `processing:expression` am Ergebnis und alle Bänder mit `minimum` ≥ −1 und `maximum` ≤ 1: −1…1 mit `rdylgn`, wie heute (Frage 6). Die Prüfung läuft über die Werte, nicht über den Ausdruck. Ein Ausdruck wie `(a-b)/(a+b)` lässt sich in vielen Schreibweisen schreiben, ein Wertebereich nicht.
4. Statistik vorhanden und brauchbar: `rescale` = kleinstes `percentile_2` bis größtes `percentile_98` über die Bänder, dieselbe Regel wie `render.ts::autoRescale`, mit `viridis` (Frage 5). Ist p2 = p98, dann `minimum`…`maximum`; ist auch das gleich, gilt Regel 5.
5. Keine Statistik (älteres Ergebnis, `count` 0): wie heute der Bereich des Panels.

- **Daten:** `readResults` legt am Jobeintrag die Bandstatistiken und `processing:expression` ab. Sie sind schon im Ergebnisdokument und brauchen keine neue Anfrage.
- **„Panel“ in §2:** Gemeint ist die Darstellung, die das Panel einem Ergebnis gibt (`resultRender`). Die Felder der Vorschau ändern sich nicht.
- **T1-Vorschau: bleibt, wie sie ist:**
  - Die Kachel der Vorschau rechnet den Operator auf der Kachel; eine Statistik des Ergebnisses gibt es dann noch nicht.
  - Die Statistik-Route nimmt keinen Operator (`AUTO_STRETCH_REASON`).
  - Eine Statistik je Kachel ließe benachbarte Kacheln verschieden aussehen.
- **Oberflächentexte:** keine neuen nötig. Wird ein Hinweis gewünscht, dann englisch, etwa „Range 2–98 % of the result“.

### 6.8 Runner (§3 Punkt 6)

- Der Runner ruft denselben Kern auf. Seine `result.tif` trägt dieselben Tags, seine `provenance.json` dieselben `properties` mit `statistics`.
- `tests/earthx/runner/test_compare.py` vergleicht schon die Bytes von `result.tif` zwischen Job-Kind und Runner. Damit sind die Tags mitgeprüft.
- Dazu kommt ein Vergleich der `statistics` beider Seiten.

### 6.9 Fragen an Otto

**Frage 1 – Ablage.**
1. **Beides: Tags in `result.tif` und `statistics` an den Bändern im Ergebnisdokument und in `provenance.json` (Empfehlung).** Die heruntergeladene Datei beschreibt sich selbst, und das Frontend braucht keinen neuen Weg. Kostet eine Version (0.4.2).
2. Nur im Ergebnisdokument. `result.tif` bleibt Byte für Byte gleich, keine neue Version nötig. GDAL-Werkzeuge rechnen dann selbst.
3. Nur Tags. Das Frontend bräuchte eine neue Route im `tiler`.

**Frage 2 – Über welche Pixel.**
1. **Die ganze `result.tif`, also die Bounding Box (Empfehlung).** Das entspricht der Bedeutung der GDAL-Tags in der Datei. Der Unterschied zur AOI betrifft nur den Rand, und 2–98 % fängt Ausreißer dort ab.
2. Nur Pixel innerhalb von `mask.tif`, also was die Karte zeigt. Die Tags in der Datei beschrieben dann nicht die ganze Datei; dafür bräuchte es eigene Namen statt `STATISTICS_*`.

**Frage 3 – Genauigkeit der Perzentile.**
1. **65 536 Fächer je Band; ≤ 16 bit Ganzzahl exakt, sonst ≤ 0,8 % des Werts, nach außen gerundet (Empfehlung).** 512 KB je Band. Für eine Farbskala genügt das: Bei einem DEM um 1000 m ist ein Fach 4 m breit.
2. 2²⁰ Fächer (≤ 0,05 %), 8 MB je Band. Bei vielen Bändern sind das über 100 MB.
3. Exakt über einen zweiten Lesedurchgang auf `result.tif`. Widerspricht §3 Punkt 1.

**Frage 4 – Mittelwert und Standardabweichung.**
1. **Mittelwert exakt (ganzzahlige Summe), `stddev` blockweise wie GDAL (deterministisch, nicht exakt) (Empfehlung).** So steht es in §3 Punkt 1, und `stddev` braucht es, damit GDAL die Tags liest [M].
2. Beides blockweise wie GDAL. Das spart etwa 16 ms je Megapixel und Band, aber der Mittelwert ist dann nur fast exakt (Abweichung ≈ 10⁻¹⁵ relativ), entgegen §3 Punkt 1.
3. Ohne `stddev`. Dann übergeht GDAL die gespeicherten Werte (§6.1).

**Frage 5 – Colormap für unbekannte Größen.**
1. **`viridis` (Empfehlung).** Wahrnehmungsgleichmäßig und farbenblindtauglich. Hebt sich vom Satellitenbild ab.
2. `greys`. Neutral, aber leicht mit einem Graustufenbild der Quelle zu verwechseln.

**Frage 6 – Index-artige Ergebnisse (NDVI).**
1. **Wie heute: −1…1 mit `rdylgn` (Empfehlung).** Die Abnahme verlangt „erscheint wie bisher“. Eine feste Skala macht Jobs untereinander vergleichbar.
2. 2–98 % mit `rdylgn`. Mehr Kontrast, aber jedes NDVI-Ergebnis sieht anders skaliert aus.

Bekannte Grenze von Regel 3 (§6.7): Ein Band-Math-Ergebnis mit Werten in 0…1, das kein Index ist (etwa `B04 * 1` auf Reflexion), bekommt `rdylgn`. Der Nutzer kann das über Frage 7 ändern.

**Frage 7 – Hand vor Statistik.**
1. **Ein im Panel von Hand angewandter Bereich, der von der Vorgabe abweicht, gilt für jedes danach hinzugefügte Gleitkomma-Ergebnis; sonst die Statistik (Empfehlung).** Das ist „wie bisher von Hand ändern“. Ein schon angelegter Layer ändert sich nicht; zum Ändern entfernen und neu hinzufügen, wie heute.
2. Die Statistik geht immer vor; der Bereich im Panel gilt nur für die Vorschau und für index-artige Ergebnisse.
3. Eigene Felder für Bereich und Colormap am Ergebnis-Layer im Layer-Manager. Das wäre neue Oberfläche und eine eigene Aufgabe.

**Frage 8 – Faktor der Schätzung.** Die Statistik kostet je Megapixel und Band der Ausgabe etwa 35–50 ms (§6.5). Bei Band-Math sind das +10 bis +13 %, bei `reproject` wenige Prozent.
1. **Faktoren unverändert (Empfehlung).** Sie sind relativ zu Band-Math und grob (`adr/0014` §5.5). Die Dauer ist eine Anzeige „etwa“, und die Kalibrierung gegen echte Läufe steht aus. Die Umsetzung misst nach und nennt die Zahl im PR.
2. Ein fester Zuschlag je Megapixel und Band der Ausgabe in der Schätzung. Genauer, aber die Schätzung bekommt dafür eine neue Größe: die Zahl der Bänder der Ausgabe.

### 6.10 Umsetzung nach Freigabe

**Schnitt (Vorschlag):** zwei PRs, damit jeder unter etwa 400 Zeilen bleibt.

**M4-32a, Backend:**
- `processing/statistics.py`.
- Einhängen in `core._Run.write_pass` und `_properties`, `forward_band_tags=True`.
- `__version__` 0.4.2, README, Fixture.
- Tests.
- Nachtrag `adr/0014` §15k; dort steht, dass die Bytes von `result.tif` sich ändern und §6.3 gilt wie bisher.
- Log und §3.

**M4-32b, Frontend** (nach dem Merge von a; die Form des Dokuments steht nach a fest):
- `resultRender` nach §6.7.
- Ablage am Jobeintrag in `processingStore`.
- Tests, Prüfanleitung.

**Tests (§5):**
- `tests/earthx/processing/test_statistics.py`:
  - Unabhängige Rechnung (`Fraction` für den Mittelwert, `numpy.percentile(method="inverted_cdf")` und Fachbreite für die Perzentile, `numpy.std` mit Toleranz für `stddev`) auf vier synthetischen Rastern: float32 mit NaN, `uint16` mit nodata, DEM-artig, NDVI-artig. Dazu jede Ausgabe-Art aus `RasterOutput.dtype`.
  - Andere Blockung und Reihenfolge ergeben dieselben Werte.
  - Fehler und zweckfremde Nutzung: ein Band ohne gültige Werte, ein konstantes Band, nur negative Werte, `±inf`, Subnormale, ein nicht unterstützter Typ.
- `test_core_run.py`:
  - Die Tags von `result.tif` sind gleich den `statistics` der Eigenschaften.
  - Eine unabhängige Rechnung über die zurückgelesene `result.tif` stimmt überein, auch für eine Ganzzahl-Ausgabe mit nodata.
  - Zweimal gerechnet ist `result.tif` Byte für Byte gleich.
- `runner/test_compare.py`: `statistics` Job-Kind gleich Runner.
- Speicher: die bestehenden Tests `test_memory_8192.py` (8192², < 500 MB) und `test_memory_reproject.py` (4096²) laufen mit Statistik.
- Frontend (b):
  - `resultLayer.test.ts` für die Regeln 1–5.
  - Ein Test in `processingStore`, dass die Statistik aus dem Ergebnisdokument übernommen wird, und dass ein Dokument ohne sie den heutigen Bereich ergibt.
- Gegenprobe: Mit dem Kern ohne Statistik (bzw. dem alten `resultRender`) scheitern die neuen Tests; Nachweis im PR.

**Prüfanleitung für Otto (in b):**
- `cop-dem-glo-30`, `reproject` nach EPSG:3035, 30 m, `bilinear`, Ausgabe `float32`, dann „Add to layers“: Relief sichtbar in `viridis`.
- Ein NDVI-Band-Math-Job auf `sentinel-2-c1-l2a`: Er erscheint wie bisher, −1…1 mit `rdylgn`.

### 6.11 Messanhang

Die Skripte liegen nur im Kratzverzeichnis der Sitzung, nicht im Repo:
- `stats.py`: der Prototyp der Statistik.
- `check.py`: Vergleich mit der unabhängigen Rechnung.
- `tags.py`: Tags durch `cog_translate` und `statistics()` mit und ohne `STDDEV`.
- `simd.py`: numpy-Summen über die SIMD-Stufen.
- `measure.py`: `memory_run.py` mit dem Prototyp in `core._Run.write_pass` und `forward_band_tags=True`.
- `bench2.py`, `bench3.py`: Aufschlüsselung je Block, ohne und mit den Abkürzungen.
- `series.sh`, `series2.sh`: die Läufe der Tabelle in §6.5, je Lauf ein Kindprozess.

```bash
# Szenen wie test_memory_8192.build_scene, 2048² und 4096²
python measure.py data/scene-4096.tif <workdir> 4096 scale|reproject 0|1   # aus backend/, Kindprozess je Lauf
NPY_DISABLE_CPU_FEATURES=X86_V4,AVX512_ICL,AVX512_SPR python simd.py          # B
NPY_DISABLE_CPU_FEATURES=X86_V3,X86_V4,AVX512_ICL,AVX512_SPR python simd.py   # nur X86_V2
```
