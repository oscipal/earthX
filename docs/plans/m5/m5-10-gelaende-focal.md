# M5-10 — Geländeoperator `terrain` und Operator-Art `focal`

**Stand:** 14.11.2026, freigegeben von Otto (Antworten in §9a); PR A umgesetzt (§9b), Rückfragen beantwortet (§9c), PR B wartet auf M5-30b Teil 9.
**Stufe B.** Erst Plan mit Fragen im Draft-PR, Umsetzung nach Ottos Antworten im selben PR (höchstens zwei PRs, F1).
**Aufgabe:** M5-10 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2.
**Grundlage:** `adr/0030` F3 (Operator-Art `focal`), §3 B4, §5.3, §5.4, §7, §8, §11; `adr/0023` F5 (Capability `terrain`, zwei Pflichtpunkte); `adr/0014` §5, §6, F10; `adr/0026` Q34/Q35; Plan M5-22 F5 (`capability_terms.yaml`); M5-Plan §2 Punkte 8 und 9.
**Vorgaben Otto zu dieser Aufgabe (14.11.2026):** ein PR, höchstens zwei; nichts verschwindet beim Herauszoomen; keine Hinweise oder Marken im Frontend; Einheiten nur, wo physikalisch.

## 1. Ziel

Ein generischer Geländeoperator `terrain` (Hangneigung, Exposition, Schummerung), freigeschaltet über die neue Capability `terrain`, die nur Höhenmodelle setzen (B10): heute `cop-dem-glo-30` und `swissalti3d`, später BEV (M5-09). Dafür die Operator-Art `focal` allgemein, so dass DS-05b (Speckle-Filter) nur noch die Filter bauen muss.

Schon entschieden (`adr/0030` F3 = 1, `adr/0023` F5 = 1):

- Rand h als Eigenschaft des Operators; Job und Runner exakt und bitgleich.
- Die Kachel rechnet im Kachelraster und ist immer Vorschau; in der Kachel steht `focal` nur als erster Schritt.
- Fenster in fester Reihenfolge rechnen, damit das Ergebnis nicht vom Blockstart abhängt.
- Pflichtpunkte aus `adr/0023` F5: Nachbarpixel am Blockrand (§4.2) und Schummerung als `tiler`-Algorithmus prüfen (§5).

Nicht Teil: TRI, TPI, Rauheit, Krümmung (P3, klein nach M5-10); Knöpfe „Slope“ und „Hillshade“ unter „Quick processing“ (kommen mit M5-14, `step_presets`); BEV (M5-09).

## 2. Befund im Code (Stand `main`, 324ef3c)

Gelesen; [L] = in dieser Sitzung laufen lassen.

| Stelle | Heute | Folge für `focal` |
|---|---|---|
| `processing/operators/base.py` `Operator.kind` | `pixel` (Kernel `ImageData → ImageData`, T1 und T2) oder `grid` (nur T2, liest die Arbeitsdatei des vorigen Durchgangs) | dritte Art `focal` mit Rand `halo` |
| `processing/core.py` `_blocks`, `_read_block`, `_run_pass` | Blöcke zu `BLOCK_SIZE` ohne Rand; erster Durchgang liest die Quellen im Fenster `bbox(AOI ∩ Raster)`, spätere lesen die Arbeitsdatei | Block mit Rand lesen, Kernel gibt den inneren Block zurück |
| `processing/plan.py` `segments`, `split_tiers` | Durchgänge an `grid`- und messenden Schritten; Kachel = längster Anfang aus `pixel`-Schritten mit T1 | `focal` bleibt im `pixel`-Durchgang (§4.2); Kachel nimmt `focal` nur als ersten Schritt |
| `processing/core.py` `area_statistics` | Statistik der AOI ohne Job (Vorschau-Messung), Blöcke wie oben | gleicher Rand wie im Job |
| `processing/tile.py` `_tile_options`, `OperatorTileReader`, `MosaicOperatorTileReader` | liest mit `nearest`; nimmt `buffer` aus der Anfrage an | Rand der Kachel über `buffer` von rio-tiler 9.4.6 |
| `api/tiler.py` `_operator_step` | lehnt jede Art außer `pixel` als Kachel ab (`422`) | `focal` an erster Stelle zulassen |
| `api/processing_docs.py` | meldet `x-earthx-kind` je Operator | meldet `focal` ohne Änderung |
| `frontend/src/processingPreview.ts` `tileStep` | Vorschau nur für `pixel` mit T1 | `focal` nur als erster Schritt |
| `catalog/registry.py` `Capabilities` | elf Flags ohne Vorgabe (B10) | Flag `terrain`; jeder Eintrag setzt es ausdrücklich |
| `backend/catalog/capability_terms.yaml` | `terms: {}`; Kommentar: „M5-10 adds `terrain`“ | Begriffe de/en eintragen; macht Q34/Q35 aktiv |
| `titiler.core.algorithm.dem.HillShade` [L] | `numpy.gradient` ohne Pixelgröße, `uint8`, Rand 3 | Ergebnis hängt von der Zoomstufe ab, keine Physik (§5) |
| `gdaldem`, `osgeo` | in der Umgebung nicht installiert [L] | Tests gegen unabhängige Rechnung und Ebenen mit bekannter Lösung (§8) |

Datensätze: `cop-dem-glo-30` (EPSG:4326, `float32`, Einheit `m`, `min_zoom` 0, Übersicht `pyramid`), `swissalti3d` (LV95, `float32`, nodata −9999, `min_zoom` 13, Übersicht `substitute` → GLO-30).

## 3. Stand der Technik (aus `adr/0030` Q29, `gdaldem`)

- Gradient nach **Horn** (Vorgabe von `gdaldem`, 8 Nachbarn gewichtet) oder **Zevenbergen-Thorne** (4 Nachbarn, glatter bei glattem Gelände).
- Neigung in Grad oder Prozent; Exposition 0° = Nord, im Uhrzeigersinn; flache Pixel ohne Exposition (`gdaldem`: nodata, mit `-zero_for_flat` 0).
- Schummerung: Azimut 315°, Höhe 45°, z-Faktor 1; Variante „multidirectional“ (gewichtete Summe aus vier Azimuten, USGS).
- Ränder: `gdaldem` maskiert ohne `-compute_edges` jedes Pixel, dessen 3×3-Fenster nodata oder den Rasterrand berührt; mit `-compute_edges` rechnet es aus den vorhandenen Nachbarn.
- Geographische CRS: `gdaldem` braucht bis GDAL 3.10 einen Faktor (`-s 111120`) und empfiehlt fern vom Äquator eine Reprojektion; ab 3.11 bestimmt es die Skala aus dem CRS.

## 4. Vorschlag

### 4.1 Operator-Art `focal` (allgemein)

- `Operator.kind` bekommt `focal`; neues Feld `halo: int` (h ≥ 1 bei `focal`, sonst 0; geprüft in `__post_init__`).
- **Kernel:** `run(image, params) -> ImageData`. `image` ist der Block **mit** Rand h ringsum, das Ergebnis der innere Block ohne Rand, mit angepassten `bounds`. Damit rufen Kachel und Job dieselbe Funktion (`adr/0014` §6.2), wie bei `pixel`.
- Ein `focal`-Schritt darf messen (`measures`) nicht; T1 und T2 erlaubt; `grid` bleibt unverändert.
- Der Kernel rechnet jedes Pixel aus seinen Nachbarn in fester Reihenfolge (keine gleitenden Summen), in `float64`, dann `float32`. Ergebnis hängt nicht vom Blockstart ab → Job und Runner bitgleich bei jeder Blockgröße.

### 4.2 Job: Rand am Blockrand (Pflichtpunkt `adr/0023` F5)

- Ein `focal`-Schritt bleibt im `pixel`-Durchgang; er erzwingt keinen eigenen Durchgang. Pixel-Schritte sind punktweise und rechnen auf dem größeren Block genauso.
- Der Durchgang liest jeden Block um H größer, H = Summe der `halo` seiner `focal`-Schritte. Jeder `focal`-Schritt gibt h ab; am Ende hat der Block wieder `BLOCK_SIZE`.
- **Erster Durchgang (liest die Quellen):** Der Rand kommt aus den Daten, auch außerhalb des Fensters `bbox(AOI ∩ Raster)`. Pixel am Rand der AOI rechnen also mit ihren echten Nachbarn. Außerhalb des Rasters liest die Quelle maskiert (`boundless`).
- **Spätere Durchgänge (lesen die Arbeitsdatei, z. B. nach `reproject`):** Die Datei deckt nur das Fenster; der Rand außerhalb ist maskiert. Ein `focal` nach einem `grid`-Schritt verliert am Fensterrand einen Ring von h Pixeln (Regel F2).
- Kosten: 3×3 bei Blöcken zu 1024 px: (1026/1024)² ≈ +0,4 % Lesen. Kostenfaktor `terrain` 1 (`adr/0030` §7), gemessen in der Umsetzung.
- `area_statistics` liest mit demselben Rand.

### 4.3 Kachel (Vorschau)

- `_operator_step` nimmt `focal` an erster Stelle an, sonst `422` wie heute („does not run as a tile“).
- Ist der erste Schritt `focal`, liest der Leser mit `buffer = h` (rio-tiler), der Kernel gibt die Kachel in Kachelgröße zurück. Ein `buffer` in der Anfrage zusammen mit `focal` → `422`.
- Mosaik mit Schritten (`MosaicOperatorTileReader`): jede Szene mit Rand, dann „erstes gültiges Pixel“, dann Kernel; Nähte zwischen Szenen haben damit Nachbarn.
- `preview()` (Farbskala über die ganze Ausdehnung): ohne Rand gelesen, Ring maskiert.
- **Leseart:** Operator-Kacheln lesen heute mit `nearest`. Für eine Nachbarschaft zieht `nearest` unterhalb der nativen Ebene einzelne Zeilen doppelt; die Schummerung zeigt dann Streifen (`adr/0030` §3 B4). Frage F4.
- Vorschau endet vor der Auflösung der Daten (`previewMaxZoom`); darüber vergrößert MapLibre die letzte Stufe. Kein Überzoomen im Kachelraster, also keine Treppen.

### 4.4 Operator `terrain`, Version 1

| Feld | Wert |
|---|---|
| `kind`, `halo`, `tiers` | `focal`, 1, T1 und T2 |
| `requires` | Capability `terrain`, Stufe Processing |
| `passes_values` | nein (neu gerechnet → Ausgabe `float32`, bei Quelle `float64` auch `float64`; Regel #333) |
| `bands_used` | liest `band`, fügt `name` hinzu, ändert keine vorhandenen |
| `dataset_check` | `band` gibt es und seine Einheit ist `m` (sonst Grund) |
| Zitat, Methodensatz | Horn 1981 bzw. Zevenbergen & Thorne 1987; Methodensatz je Produkt mit Parametern |

Parameter (streng, `extra=forbid`):

| Parameter | Werte | Vorgabe | gilt für |
|---|---|---|---|
| `band` | Name des Höhenbands | Pflicht | alle |
| `name` | Name des neuen Bands (wie `band_math` v2) | Pflicht | alle |
| `product` | `slope`, `aspect`, `hillshade` | Pflicht | — |
| `method` | `horn`, `zevenbergen_thorne` | `horn` | alle |
| `slope_unit` | `degrees`, `percent` | `degrees` | nur `slope` |
| `azimuth` | 0–360 | 315 | nur `hillshade` |
| `altitude` | 0–90 | 45 | nur `hillshade` |
| `z_factor` | > 0 | 1 | `slope`, `hillshade` |
| `multidirectional` | ja/nein | nein | nur `hillshade`; dann ohne `azimuth` |

Ein Parameter, der zum gewählten Produkt nicht passt, wird abgewiesen (keine stillen Felder).

**Werte und Einheiten (Vorgabe „Einheiten nur, wo physikalisch“):**

| Produkt | Werte | Einheit des Bands |
|---|---|---|
| `slope` | 0–90 bzw. ≥ 0 | `deg` bzw. `%` |
| `aspect` | 0 bis < 360, 0 = Nord, im Uhrzeigersinn; flach → maskiert | `deg` |
| `hillshade` | 0–255 wie `gdaldem`, als `float32` ohne Runden | keine |

**Pixelgröße in Metern** (Pflichtpunkt aus `adr/0030` §5.3), Frage F3. Vorschlag: je Zeile aus CRS und Lage des Pixels, nicht aus dem Block; damit bitgleich bei jeder Blockgröße.

- geographisch (GLO-30): Δλ · N(φ) · cos φ und Δφ · M(φ) auf dem Ellipsoid des CRS;
- Web Mercator (Kachel): Kachelpixel · cos φ;
- andere projizierte CRS (LV95, EPSG:3035, UTM): Längeneinheit des CRS in Metern, wie `gdaldem`.

**Ränder und Lücken** (Regel aus `adr/0030` §3 B4), Frage F2. Vorschlag wie `gdaldem` ohne `-compute_edges`: Ein Pixel, dessen 3×3-Fenster ein maskiertes Pixel oder den Rasterrand berührt, wird maskiert.

### 4.5 Registry, Suche, Onboarding

- `Capabilities.terrain: bool`, ohne Vorgabe (B10). `true` für `cop-dem-glo-30` und `swissalti3d`, `false` für alle anderen YAML-Einträge; Prototyp-Einträge gibt es heute keine.
- Das Flag geht in die Collection (`earthx:capabilities`) wie die anderen; Frontend-Fixtures und Tests, die alle Flags aufzählen, bekommen die Zeile (mechanisch, getrennt gezählt).
- `capability_terms.yaml`: `terrain: [slope, aspect, hillshade, terrain analysis, Hangneigung, Neigung, Exposition, Schummerung, Geländeanalyse]`. Damit werden Q34 („Hangneigung berechnen“) und Q35 („hillshade“) im Bewertungs-Set aktiv; erwartet DEM und swissALTI3D (BEV erst mit M5-09).
- `adr/0031` Profil `elevation` nennt `terrain` schon (nach M5-10); keine Änderung.

### 4.6 Frontend

- `processingPreview.ts` `tileStep`: `focal` mit T1 nur als erster Schritt; danach bleibt es beim heutigen Verhalten („Nothing after a step that cannot be drawn is shown“).
- Formular aus dem JSON Schema wie bei jedem Operator; keine neuen Texte, Hinweise oder Marken. Die vorhandene Marke „Preview“ bleibt, wie sie ist (gilt für jede Vorschau).
- Einheit am Band nur bei `deg` und `%` (Regel vom 14.11.2026, Log).

## 5. Schummerung als `tiler`-Algorithmus (Pflichtpunkt `adr/0023` F5)

Geprüft:

- TiTilers `hillshade` rechnet den Gradienten ohne Pixelgröße (`numpy.gradient` auf Rohwerten). Die gleiche Landschaft wird mit jeder Zoomstufe steiler oder flacher; das widerspricht Prinzip 9 und der Regel „Ergebnis = Vorschau“.
- Ein eigener benannter Weg im `tiler` wäre eine zweite Rechnung derselben Schummerung neben dem Operator, ohne Hash, Download und Provenienz.
- Die Operator-Kachel (`op=terrain`) ist schon eine Darstellung über den `tiler`, mit derselben Rechnung wie der Job.
- Das Relief der Basiskarte (NM4-35, `relief.ts`) und die 3D-Ansicht (UI-06) bleiben unberührt; sie zeichnen MapLibre aus den AWS Terrain Tiles.

Vorschlag: kein eigener `tiler`-Algorithmus; die Ansicht bedient die Operator-Kachel; ein Klick auf „Hillshade“ kommt mit M5-14 als `step_preset`. TiTilers `algorithm` bleibt abgewiesen. Frage F5.

## 6. Kleiner Zoom (Vorgabe „nichts verschwindet beim Herauszoomen“)

Heute für **jede** Vorschau mit Schritten, nicht nur `terrain`:

- Sie beginnt bei `min_zoom` des Datensatzes (`processingPreview.ts`, `firstLevel`).
- Darunter zeigt die Karte die Übersicht des Datensatzes (Pyramide GLO-30, Ersatz GLO-30 bei swissALTI3D, `adr/0032`), die Vorschau selbst aber nicht. Bei swissALTI3D unter z13 verschwindet die Vorschau also.
- Auf kleinen Stufen liest das Mosaik mit Schritten höchstens 32 Dateien je Kachel (M5-30b); bei GLO-30 auf z0–z6 bleibt die Vorschau deshalb lückenhaft (Teilkachel).

Weg dafür (Vorschlag F6 = 1): Die Übersichts-Routen (Pyramide, Ersatz) nehmen die Kette der Vorschau und rechnen sie auf den Kacheln der Übersicht, mit derselben Regel wie die Operator-Kachel (`focal` nur als erster Schritt, Rand über `buffer`). Die Kernel sind reine Funktionen; gerechnet wird in `api` auf den Pixeln, die `access` liest, ohne dass `processing` den Objektspeicher berührt (B9). Statistik, Zuschnitt, Download und Jobs bleiben bei den Originalen. Das Frontend zeichnet die Vorschau unter dem ersten Level des Mosaiks aus dieser Route. Bei swissALTI3D unter z13 zeigt die Vorschau dann die Kette auf GLO-30 (Quellenzeile wie beim Ersatz, keine Marke).

## 7. Umsetzung nach Freigabe

Bei F1 = 1 in zwei PRs, gestapelt:

**PR A (dieser PR, mit Plan):** Job und Runner.
1. `base.py`: Art `focal`, `halo`, Prüfungen.
2. `core.py`/`plan.py`: Block mit Rand im `pixel`-Durchgang, Quelle `boundless`, Arbeitsdatei maskiert außerhalb; `area_statistics`; `split_tiers` mit `focal` nur an erster Stelle; Kosten und Speicher.
3. `operators/terrain.py`: Kernel, Parameter, Pixelgröße, Ränder, Methodensatz, Zitat; Registrierung.
4. `Capabilities.terrain`, YAML-Einträge, Collection, Fixtures; `capability_terms.yaml`; Q34/Q35.
5. Entscheidungslog; `adr/0030` §11 und M5-Plan §6 nur im Log nachgetragen.

**PR B (gestapelt auf A):** Kachel und Frontend.
6. `processing/tile.py`, `api/tiler.py`: `focal` an erster Stelle, `buffer`, Mosaik, `preview()`, Leseart nach F4.
7. Übersichts-Routen mit Kette nach F6.
8. `processingPreview.ts`: `focal` nur als erster Schritt; Vorschau unter `min_zoom` nach F6.
9. Browserprüfung (GLO-30 und swissALTI3D: Neigung, Exposition, Schummerung, Herauszoomen bis z0), Bilder nicht ins Repo.

Commits klein und thematisch; vor „fertig“ `main` holen, Lint, Typprüfung, Importregeln, Tests.

## 8. Tests

- **Ebenen mit bekannter Lösung** (synthetisch): z = a·x + b·y in metrischem CRS → Neigung `atan(√(a²+b²))`, Exposition aus `atan2`, Schummerung aus der Formel; für Horn und Zevenbergen-Thorne exakt bis Rundung.
- **Unabhängige Rechnung:** zweite, schleifenbasierte Umsetzung der `gdaldem`-Formeln im Test (nicht der Kernel), Vergleich auf einem zufälligen DEM mit Lücken.
- **Geographisch:** Ebene in Metern auf 47° N und 60° N in EPSG:4326 abgetastet → gleiche Neigung wie metrisch (Toleranz aus der Ellipsoid-Näherung); Web Mercator gleich.
- **Blockrand:** gleiches Ergebnis bei `BLOCK_SIZE` 1024, 7 und 1 (bitgleich); Job ↔ Runner bitgleich; Rand der AOI rechnet mit Daten außerhalb der AOI.
- **Ränder und Lücken:** nodata im Fenster, Rasterrand, Ring nach `reproject` → maskiert nach F2; Exposition flach → maskiert.
- **Fehlerfälle und zweckfremde Nutzung:** ohne Capability `terrain` (WorldCover, Sentinel-2) → Grund; Band ohne Einheit `m`; Band fehlt; Parameter zum falschen Produkt; `azimuth` mit `multidirectional`; `z_factor` ≤ 0; Name schon vergeben; Ganzzahl-Ausgabe angeboten nur nach Regel #333; `focal` an zweiter Stelle der Kachel → `422`; `buffer` mit `focal` → `422`; Art `focal` ohne `halo` und `halo` ohne `focal` → `ValueError`.
- **Kachel (PR B):** Kachel mit Rand gleich dem inneren Ausschnitt einer größeren Rechnung; Mosaiknaht ohne Ring; Frontend `planPreview` mit `focal` an erster und zweiter Stelle.
- **Suche:** Q34/Q35 bestehen im Bewertungs-Set; Test `capability_terms` ↔ Operator-Registry.

## 9. Fragen an Otto

**F1 — Schnitt in PRs?**
1. Zwei PRs: A (dieser, mit Plan) Job, Runner, Operator, Capability, Suche; B gestapelt: Kachel, Übersicht, Frontend **(Empfehlung)**
2. Ein PR für alles (geschätzt 1 000–1 300 Zeilen mit Tests, dazu rund 40 mechanische Zeilen für das neue Flag)
3. A nur `focal` mit einem Testoperator; B `terrain`, Kachel, Frontend

**F2 — Pixel am Rand der Daten (nodata, Rasterrand, Fensterrand nach `reproject`)?**
1. Maskieren wie `gdaldem` ohne `-compute_edges`; am Rand der AOI rechnet der Job mit den Daten außerhalb der AOI **(Empfehlung)**
2. Aus den vorhandenen Nachbarn rechnen wie `gdaldem -compute_edges`
3. Wie 1, aber nach `reproject` den Arbeitsbereich um h vergrößern, damit auch dort kein Ring fehlt (`reproject` liest dann mehr)

**F3 — Pixelgröße in Metern bei EPSG:4326 (GLO-30) und in der Kachel?**
1. Je Zeile aus dem CRS: Ellipsoid bei geographischen CRS, cos φ in Web Mercator, Längeneinheit bei anderen projizierten CRS wie `gdaldem` **(Empfehlung)**
2. Je Pixel aus den Maßstabsfaktoren des CRS (pyproj) für alle CRS; genauer bei flächentreuen Projektionen, teurer
3. Nur metrische CRS; GLO-30 braucht vorher `reproject`, die Kachel rechnet mit cos φ

**F4 — Leseart der Kachel vor einem `focal`-Schritt?**
1. `bilinear`: keine Streifen in der Schummerung; die Kachel ist ohnehin Vorschau **(Empfehlung)**
2. `nearest` wie alle Operator-Kacheln; Streifen unterhalb der nativen Ebene möglich

**F5 — Schummerung im `tiler` (§5)?**
1. Kein eigener `tiler`-Algorithmus; die Ansicht zeigt die Operator-Kachel; „Hillshade“ als Knopf mit M5-14 **(Empfehlung)**
2. Zusätzlich eine benannte Route zur reinen Darstellung, ohne Rezeptschritt
3. TiTilers `hillshade` freigeben (ohne Pixelgröße, ändert sich mit dem Zoom)

**F6 — Vorschau unter `min_zoom` und auf kleinen Stufen (§6)?**
1. In PR B für jede Vorschau mit Schritten: Pyramide bzw. Ersatz nehmen die Kette, die Vorschau verschwindet beim Herauszoomen nie **(Empfehlung)**
2. Eigene Aufgabe danach (gilt für alle Operatoren, nicht nur `terrain`); in M5-10 endet die Vorschau wie heute bei `min_zoom`
3. Nur für `terrain` in PR B

**F7 — Einheit der Neigung in Prozent?**
1. `%` als Einheit am Band (wie `deg` bei Grad) **(Empfehlung)**
2. keine Einheit; nur Grad trägt eine

## 9a. Antworten von Otto (14.11.2026)

F1 bis F7 jeweils Option 1 (Empfehlung).

- **Reihenfolge (Otto):** PR A (dieser PR, [#350](https://github.com/oscipal/earthX/pull/350): Job, Runner, Operator, Capability, Suche) jetzt. PR B (Kachel, Frontend, Vorschau unter `min_zoom` nach F6) startet erst, wenn M5-30b Teil 9 (Kachelroute aus der Pyramide) auf `main` ist, weil er dieselben Stellen ändert; Otto gibt Bescheid.
- **Folge für PR A:** `terrain` ist in der Registry schon T1 und T2, die Kachel weist `focal` aber bis PR B ab (`422`, wie heute jede Art außer `pixel`); das Panel zeigt dafür keine Vorschau, weil es nur `pixel` zeichnet. `split_tiers` bleibt bis PR B unverändert: Ein `focal`-Schritt gehört zum Job.

## 9b. Umsetzung PR A (14.11.2026)

Umgesetzt wie §4.1, §4.2, §4.4, §4.5 mit F1–F7 = 1. Auslegungen, gelten bis Widerspruch:

- **`terrain` angenommen, aber noch nicht angeboten (`listed=False`).** Das Panel baut Formulare nur aus einfachen Feldern; die Felder von `terrain` hängen vom Produkt ab (optionale Felder als `anyOf`, wie bei `normalize` v4, das deshalb ein eigenes Formular hat). Bis PR B nimmt die API Rezepte mit `terrain` an, das Panel zeigt den Operator nicht; so erscheint kein Eintrag „not supported by this panel“. PR B baut das Formular und setzt `listed=True`.
- **z-Faktor nur bei der Schummerung**, nicht bei der Neigung (wie `gdaldem`; die Höhe ist ohnehin in Metern, `dataset_check` verlangt `m`). §4.4 nannte ihn auch für `slope`.
- **Schummerung 1–255 wie `gdaldem`**: 1, wo das Licht nicht hinkommt, als `float32` ohne Runden; Fehlstellen sind NaN.
- **Exposition mit Pixelgröße:** `gdaldem` rechnet die Exposition ohne Pixelgröße (nur bei quadratischen Pixeln richtig); hier mit den Metern je Zeile, damit sie bei GLO-30 (rund 21 × 31 m in den Alpen) stimmt. Bei quadratischen Pixeln gleich `gdaldem` (Test).
- **Einheit am Band** aus der Vorgabe: Neigung `deg` bzw. `%`, Exposition `deg`, Schummerung keine. Eine Höhe, die eine Formel verändert hat (`band_math` `dem * 2`), hat keine Einheit mehr und wird abgewiesen.
- **Bitgleich bei jeder Blockgröße und auf jeder Maschine** (Befund der Prüfung): Die Lage einer Zeile kommt nicht aus den Grenzen des Blocks, sondern aus ganzen Zeilennummern und der Phase des Gitters (Pixelgröße auf 10 Stellen, Phase auf 3 Stellen; die Mitte einer Zeile verschiebt sich um weniger als 1 mm). Winkelfunktionen (`arctan`, `arctan2`, `sin`, `cos`) rechnet der Operator selbst mit `+ − × ÷ √`, weil numpy und libm je nach Lage im Array (SIMD) und CPU in der letzten Stelle abweichen (wie `band_math`, `adr/0014` §15c); Abweichung zu numpy höchstens 2·10⁻¹⁵. Getestet für UTM (Blöcke 1024, 48, 16) und das Gitter von GLO-30 (Blöcke 37, 64). Nur die Kachel in Web Mercator (Vorschau, PR B) nutzt numpy für die Breite.
- **Grobe Flächenstatistik:** Der Block selbst wird immer gelesen, nur der Rand außerhalb des Rasters ist maskiert; so fehlt die letzte angeschnittene Grobspalte nicht.
- **Frontend unverändert:** Der Typ `Capabilities` in `frontend/src/types.ts` bekommt `terrain` erst in PR B, wenn das Frontend das Flag liest.
- **Skalierbarkeit (Vorgabe Otto vom 14.11.2026, M5-35):** `focal` hält keinen Zustand und liest je Block (1 024 px) einen Rand von einem Pixel mit, rund 0,4 % mehr; Kosten und Speicher wachsen linear mit den Pixeln wie bei `band_math`. Keine neue Tabelle, kein neuer Dienst, keine Grenze je Host.
- **Untergrenze der Suche:** Mit Q34 und Q35 steigt Deutsch auf 9 von 12 (Recall@5 und MRR@10 0,750, vorher 0,727); die Untergrenze im Integrationstest folgt.

## 9c. Rückfragen von Otto vor dem Merge (15.11.2026)

Otto: Auslegungen 1–4 aus §9b in Ordnung. Zwei Rückfragen:

**1. Ausgabetyp.** Ja, die Regel aus #333 gilt: `terrain` gibt neu gerechnete Werte aus (`passes_values` = nein, in der Prozessbeschreibung `x-earthx-passes-values: false`). Das Panel bietet deshalb nur `float32` an (bei einer Quelle in `float64` auch `float64`). Die Schummerung hat Werte von 1 bis 255 als `float32`, ohne Runden, nicht `uint8` wie bei `gdaldem`. Ein Test hält das im Job fest (Typ der Datei, Bereich, Werte mit Nachkommastellen). Wie bei jedem Operator nimmt die Job-Route einen ausdrücklich verlangten Ganzzahltyp weiter an (M5-28, #333: Rezept und Job-Route unverändert).

**2. Eigene Winkelfunktionen: Abweichungen**, gemessen am 15.11.2026 und mit Toleranz in `test_terrain.py` festgehalten:

| Vergleich | gemessen | Toleranz im Test |
|---|---|---|
| `arctan` gegen numpy (0 bis 50, dazu 1e-300 und 1e300) | 3,3·10⁻¹⁶ rad | 5·10⁻¹⁶ |
| `arctan2` gegen numpy (20 000 Zufallspaare) | 4,4·10⁻¹⁶ rad | 5·10⁻¹⁶ |
| `sin`, `cos` gegen numpy (−720° bis 720°) | 1,1·10⁻¹⁵ | 1,2·10⁻¹⁵ |
| Operator mit eigenen Funktionen gegen denselben Operator mit numpy, alle 7 Varianten auf dem Referenzmodell | 0 (alle `float32`-Werte gleich) | 1 Schritt von `float32` |

Gegen `gdaldem`: Ein echter DEM-Ausschnitt geht nicht ins Repo (Fixtures nur synthetisch oder eindeutig offen lizenziert; die Lizenz-Einstufung der DEMs liegt bei Otto), und aus der Sitzung gibt es keine Live-Abrufe. Deshalb ein synthetisches alpines Modell: fraktal, 80 × 80 Pixel zu 2 m (wie swissALTI3D), 1 800–1 960 m, Neigungen von 2° bis 83°, mit einer Lücke. `gdaldem` 3.8.4 (Ubuntu-Paket, nur in der Sitzung installiert) rechnete daraus die Referenz `backend/tests/fixtures/terrain/gdaldem_reference.npz` (130 KB). Das Skript dazu ist `scripts/m5-10/gdaldem_reference.py`. Die CI vergleicht ohne `gdaldem`.

| Variante | gemessen (größte Abweichung) | Toleranz im Test | Ursache |
|---|---|---|---|
| Neigung, Horn, Grad | 0,0034° | 0,004° | `gdaldem` summiert das Fenster in `float32`, der Operator in `float64` (mit `float32`-Summen nachgerechnet: 100 % bitgleich) |
| Neigung, Zevenbergen-Thorne, Prozent | 0 | 10⁻⁴ % | nur Differenzen zweier Höhen, in `float32` exakt |
| Exposition, Horn | 0,016° | 0,02° | wie Neigung Horn |
| Exposition, Zevenbergen-Thorne | 3,1·10⁻⁵° | 10⁻⁴° | Rundung |
| Schummerung, Horn, 315°/45° | 0,5 | 0,5 | `gdaldem` schreibt 8 Bit, der Operator `float32` |
| Schummerung, Zevenbergen-Thorne, 30°/60°, z 2,5 | 0,5 | 0,5 | wie oben |
| Schummerung, vier Lichter | 0,501 | 0,51 | wie oben, dazu die `float32`-Summen |

Leere Pixel (Rand, Lücke) sind in allen Varianten dieselben wie bei `gdaldem`.

## 10. Grenzen

- Modulgrenzen laut `architekturplan.md` 3.1; `processing` liest keinen Objektspeicher (B9), Kernel bleiben reine Funktionen.
- Keine Live-Abrufe aus der Sitzung; Fixtures nur synthetisch.
- Keine neuen Texte, Hinweise oder Marken im Frontend; Erklärungen höchstens im Tooltip.
- `.github/`, `.claude/`, `CLAUDE.md`, `CODEOWNERS` unverändert.

## 11. PR B: Kachel, Frontend, Bild unter `min_zoom` (Entwurf 15.11.2026)

**Auftrag (Otto, 15.11.2026):** neuer Branch von `main` nach M5-30b (Pyramiden und Ersatz gemergt). Inhalt: die Kachel mit `focal` (`bilinear`, F4), das Frontend für `terrain`, und erweitert: **Vorschau mit Rechenschritten und Index-Darstellungen unter `min_zoom` in allen Ansichten** (Vorschau, Suchergebnisse, Szenenansicht, Crop and merge, angeheftete Ebene), sodass nie ein Bild verschwindet. Zuerst die Plan-Frage, wie unter `min_zoom` gerechnet wird und wie das ehrlich bleibt (G1–G6), dann die Umsetzung.

### 11.1 Befund (Stand `main`, 45614d9)

**Backend:**
- **Route der Übersicht:** `GET /collections/{dataset}/overview/tiles/WebMercatorQuad/{z}/{x}/{y}` (Pyramide oder Ersatz) und die maskierte Fassung für Suchtreffer `…/overview/{selection}/tiles/…` (#355).
  - Beide nehmen TiTilers Darstellung (`rescale`, `colormap_name`, `bidx`) und keine Schritte: `overview_post_process` ist leer (`api/tiler.py:1469`). `expression` und `algorithm` weist sie ab.
  - `op`, `op_version` und `params` sind dort weder erklärt noch abgewiesen.
- **Inhalt der Pyramide** (`processing/overview.py`):
  - nur das **erste Band** des ersten Assets der Standardansicht, als **Rohwerte** im Typ der Quelle;
  - 512 px, WebMercatorQuad, `average` bei GLO-30 (`data`, z0–z6) und `mode` bei WorldCover (`map`, z0–z4).
  - Eine Kachel ist ein Objekt; über ihren Rand hinaus enthält sie nichts.
- **Ersatz:** swissALTI3D unter z13 zeichnet GLO-30. Von z7 bis z12 liest es dessen Dateien (Budget 32 Dateien / 4 s), unter z7 dessen Pyramide, zugeschnitten auf die Ausdehnung.
- **Schritte in Kacheln:** gibt es nur auf der Item- und der Mosaik-Route (`operator_post_process`). Index-Presets sind dort `band_math` v2.
- **`focal` als Kachel:** Die Kachel weist `focal` ab (`kind != "pixel"`) und liest mit `nearest`.
- **Importregeln:** `access` darf weder `processing` noch `objectstore` importieren, `processing` nie `objectstore`. `api` darf beides (lazy für `processing`). Die Kernel auf Übersichtspixeln kann also nur `api` aufrufen, als Nachbearbeitung der Kachel, wie heute bei den Operator-Kacheln.

**Frontend:**

| Ansicht | einfaches Bild unter `min_zoom` | gerechnetes Bild unter `min_zoom` |
|---|---|---|
| Vorschau (Panel) | Ansicht darunter bleibt | **nichts** (`minZoom = dataset.zoom.min`, `processingPreview.ts`) |
| Suchergebnisse | Übersicht, maskiert auf die Treffer (#355) | gibt es dort nicht (keine Schritte, kein Index) |
| Szenenansicht | Übersicht (`syncFocusRaster`) | Index: **nichts** (`!s.render.index`, `mapLayers.ts:1246`) |
| Crop and merge | Übersicht, auf die AOI geschnitten | Index: **nichts** (gleicher Weg) |
| angeheftete Ebene | Übersicht (`overviewOverlaysOf`) | angeheftete Vorschau und angehefteter Index: **nichts** (`searchLayers.ts:36`, `processingStore.ts` `pinPreview`) |

**Datensätze:**
- Unter `min_zoom` liegt heute nur etwas bei GLO-30 (unter z7), WorldCover (z5) und swissALTI3D (z13). Keiner der drei hat Index-Presets; Quick processing für Gelände kommt mit M5-14 (`step_presets`).
- Sentinel-1 und -2 haben `min_zoom` 0 (`overview: scenes`). Bei ihnen gibt es kein „unter `min_zoom`“. Auf kleinen Stufen ist ihr Index aber eine Teilkachel (32 Dateien je Kachel, `adr/0032` §6.2, S1).
- Der Weg für Indizes unter `min_zoom` wird also allgemein gebaut und mit einem synthetischen Eintrag getestet. Sichtbar wird er heute bei Vorschauen und angehefteten Vorschauen (jeder Operator auf GLO-30, WorldCover und swissALTI3D, auch `terrain`).

### 11.2 Wie unter `min_zoom` gerechnet wird (G1)

| | Weg | Werte | Kosten | Bewertung |
|---|---|---|---|---|
| **A** | Die Kette rechnet auf den Pixeln der Übersicht (Pyramide bzw. Ersatz), dieselben Kernel wie die Kachel und der Job | aus vergröberten Eingaben: bei linearen Schritten gleich dem Mittel der feinen Werte, bei nichtlinearen nicht (Neigung aus gemittelten Höhen ist flacher als die mittlere Neigung; Klassen nach `mode`) | ein Objekt je Kachel (bei `focal` bis zu vier, G4); kein Bau | **Empfehlung**: jede Kette, sofort, ohne Speicher; dieselbe Regel wie die Vorschau über Overviews heute (`adr/0014` §0 Punkt 7) |
| B | Erst fein rechnen, dann vergröbern: eigene Pyramiden der Ergebnisse fester Darstellungen (Presets, später Hillshade/Slope), gebaut wie die Pyramide der Höhen | für diese Presets das Mittel der feinen Ergebnisse | je Preset und Datensatz ein Bau (GLO-30 rund 6–7 h) und Speicher; freie Ketten trotzdem wie A | später möglich, wenn A bei einem Preset irreführt; heute gibt es auf diesen Datensätzen kein Preset |
| C | Unter `min_zoom` auf den Originalen rechnen | exakt | genau das, wovor `min_zoom` schützt (`adr/0032` §4: Hunderte bis Tausende Dateien je Kachel) | nicht machbar |
| D | Unter `min_zoom` nur das einfache Bild, das gerechnete endet | — | — | widerspricht Ottos Vorgabe |

### 11.3 Wie es ehrlich bleibt (G2)

Vorschlag: wie die Übersicht heute, ohne neue Marke.
- **Kopf:** `X-EarthX-Source: overview` bzw. `substitute` an jeder Kachel, wie heute.
- **Tooltip:** ein Satz in dem Tooltip, den der Layer schon hat. Bei einer angehefteten Ebene ist das `note`, beim Panel die Marke „Preview“, die es für jede Vorschau schon gibt. Wortlaut: „Below zoom 7 this is computed from an overview of Copernicus DEM GLO-30, resampled from the original files; zoom in to 7 for values from the originals.“
- **Quellenzeile:** nennt `attribution_modified`, wie bei der Übersicht heute.
- **Farbskala:** dieselbe wie über `min_zoom`, also gemessen auf den Originalen bzw. die feste des Presets. So hat dieselbe Farbe bei jedem Zoom dieselbe Bedeutung. Eine flache Neigung bei kleinem Zoom ist dann dunkel, weil sie auf 1 km flach ist, nicht weil das Bild fehlt.
- **Was nie aus der Übersicht kommt:** Statistik, Messung der Vorschau, Zuschnitt, Download, Jobs (wie `adr/0032` §5.2, F12).

### 11.4 Weitere Punkte

**Bänder beim Ersatz (G3):** Eine Kette auf swissALTI3D nennt `dtm` oder `dtm_2m`; der Ersatz GLO-30 hat `data`. Vorschlag: Jedes Band des Datensatzes mit der Einheit des Standardbands des Ersatzes (`m`) steht unter `min_zoom` für dessen Band. Ketten, die andere Bänder lesen, enden dort wie heute.

**Bänder bei der Pyramide:** Sie hält nur das erste Band. Eine Kette, die ein anderes Band liest, hat dort kein Bild. Heute betrifft das keinen Datensatz (GLO-30 und WorldCover haben je ein Band). Die Route antwortet dann `404` ohne Bild, die Karte zeigt darunter die Übersicht.

**Rohwerte:** Die Route wendet die Skalierung des Datensatzes an, bevor die Kette rechnet, wie `processing.source.Source` es für die Kachel tut (heute ohne Wirkung: GLO-30 und WorldCover sind unskaliert).

**`focal` auf der Pyramide (G4):** Eine Kachel mit Neigung braucht einen Pixel über ihren Rand. Liegt der Rand außerhalb des Objekts, muss das Nachbarobjekt gelesen werden.
- Kachel von 256 px: bis zu 3 Objekte zusätzlich;
- Kachel von 512 px: bis zu 8.

**Kachel mit `focal` (über `min_zoom`):** wie §4.3 mit F4 = 1 (`bilinear`, Rand über `buffer`, `focal` nur als erster Schritt, ein `buffer` in der Anfrage zusammen mit `focal` → `422`). Für Mosaik-Kacheln ebenso.

**Frontend für `terrain`:**
- Ein eigenes Formular wie bei `normalize` v4: erst `product`, dann nur dessen Felder. Bei der Schummerung sind Azimut 315°, Höhe 45° und z-Faktor 1 vorausgefüllt, die Werte von `gdaldem`.
- `listed=True`, `Capabilities.terrain` in `types.ts`.
- `tileStep` nimmt `focal` an erster Stelle.
- Keine neuen Texte außer den Feldnamen; Erklärungen nur im Tooltip.

**Wo das gerechnete Bild unter `min_zoom` entsteht** (alles über dieselbe Route mit der Kette):
- Vorschau im Panel: eine zweite Rasterquelle von z0 bis `min_zoom` − 1, wie `overviewRasterOf` für das einfache Bild;
- Index in Szenenansicht und Crop and merge (`syncFocusRaster`, heute `!s.render.index`);
- angeheftete Vorschau und angehefteter Index (`pinPreview`, `overviewOverlaysOf`);
- Suchergebnisse: dort gibt es weder Schritte noch Index; bleibt wie #355.

**Sentinel-1 und -2 auf kleinen Stufen (G5):** Dort ist es kein „unter `min_zoom`“, sondern das Budget je Kachel. Nach `adr/0032` F7 (S1) bleibt die Teilkachel; eine Übersicht der Auswahl als Job wäre S2 dort.

**Umfang:** M5-10 hat höchstens zwei PRs; das hier ist der zweite. Geschätzt 700–900 Zeilen mit Tests, also über dem Richtwert von 400 (G6).

### 11.5 Fragen an Otto

**G1 — Rechenweg unter `min_zoom` (§11.2)?**
1. A: Die Kette rechnet auf den Pixeln der Übersicht (Pyramide bzw. Ersatz), für jede Kette, ohne Bau und Speicher **(Empfehlung)**
2. A jetzt, dazu B für Presets, sobald es auf Datensätzen mit Pyramide welche gibt (nach M5-14)
3. B für Presets, freie Ketten enden bei `min_zoom`

**G2 — Ehrlichkeit (§11.3)?**
1. Wie die Übersicht: Kopf, ein Satz im vorhandenen Tooltip, Quellenzeile „modified“, Farbskala aus den Originalen, keine Marke **(Empfehlung)**
2. Wie 1, aber unter `min_zoom` eine eigene Farbskala aus der Übersicht (mehr Kontrast, die Farben springen am Übergang)

**G3 — Bänder beim Ersatz (swissALTI3D `dtm`, `dtm_2m` → GLO-30 `data`)?**
1. Jedes Band mit der Einheit des Ersatzbands steht für dieses **(Empfehlung)**
2. Nur das Standardband (`dtm`); Ketten auf `dtm_2m` enden bei `min_zoom`

**G4 — `focal` auf der Pyramide über Objektgrenzen?**
1. Nachbarobjekte lesen, wo der Rand es verlangt (bis zu 3 bzw. 8 zusätzliche GETs); keine Nähte **(Empfehlung)**
2. Ohne Nachbarn: An den Objektgrenzen bleibt ein Ring leer (sichtbare Linien alle 512 px)

**G5 — Sentinel-1 und -2 auf kleinen Stufen (Teilkacheln bei Index und Vorschau)?**
1. Bleibt nach `adr/0032` F7 (S1), nicht Teil von M5-10 **(Empfehlung)**
2. Eigene Aufgabe: Übersicht der Auswahl als Job (`adr/0032` S2)

**G6 — Schnitt?**
1. Ein PR B, über dem Richtwert, in thematischen Commits **(Empfehlung, M5-10 hat höchstens zwei PRs)**
2. Zwei PRs: B1 Kachel und Formular für `terrain`, B2 Bild unter `min_zoom` (dann drei PRs für M5-10)
