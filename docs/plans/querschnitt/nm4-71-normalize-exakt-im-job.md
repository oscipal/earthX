# NM4-71 — Normalize: Vorschau ohne AOI geschätzt, Job immer mit exakten Werten

**Stand:** 01.11.2026, beauftragt von Otto (Backlog-Punkt 71 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, Quellen, Messung), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Recherche, Messung und Plan; Sonnet (Effort hoch) für die Umsetzung.
**Start:** nach dem Merge von NM4-11b (#269). Backend und Frontend in einer Session. Höchstens zwei Stufe-B-Sessions und zwei Frontend-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-71 aus `docs/plans/querschnitt/nm4-71-normalize-exakt-im-job.md` aus.“

## 1. Wunsch (Otto, 01.11.2026, wörtlich)

> von mir aus kann das in der vorschau so sein aber bei einem gestarteten job sollen dann schon die echten werte hergenommen werden. (Auch wenn die AOI grösser als 2048px ist)

„Das“ meint: Die messenden Methoden von `normalize` (Percentile, Z-score, Robust) messen für die Vorschau ohne AOI bzw. bei großer Fläche über eine verkleinerte Fassung (Overview).

## 2. Heute (NM4-11, #244; NM4-11b, #269)

- `normalize` Version 3 mit `method`; die gemessenen Werte stehen vor dem Start im Rezept (`measured`), gemessen über die Statistik-Route aus NM4-19 (exakt bis 2048², darüber nicht exakt).
- Die messenden Methoden sind ohne AOI gesperrt; „Fixed range“ geht immer.
- Normalize wirkt im Bandvorrat an Ort und Stelle (Otto, 01.11.2026: danach ist z. B. „red“ das normalisierte Band).
- ⚙ am Ergebnis: gesperrte Schritte behalten ihre gespeicherten `measured`-Werte (Antwort Otto zu #269).

## 3. Soll (Otto)

1. **Vorschau:** Die messenden Methoden gehen auch ohne AOI (ganze Szene) und bei Flächen über 2048²; gemessen wird für die Vorschau auf einer Overview. Hinweis hinter (i): Vorschau geschätzt, der Job misst exakt.
2. **Job:** Ein gestarteter Job nimmt immer die **exakten** Werte über die ganze Fläche des Auftrags, unabhängig von ihrer Größe.

## 4. Im Plan klären (je Optionen, Empfehlung, bei Rechenrelevanz Quellen und Messung)

1. **Wo exakt gemessen wird:**
   - (a) im Job: erster Durchgang misst über die Fläche, zweiter normalisiert (Worker-Kern bleibt zustandslos: beide Durchgänge im selben Job, nichts zwischen Jobs gemerkt);
   - (b) vor dem Start in `api` über eine erweiterte Statistik-Route ohne Größengrenze (Start wartet);
   - (c) andere.
   Speicher, Laufzeit und gelesene Bytes für Sentinel-2 (eine Szene, ganze Szene und große AOI, ein und mehrere Bänder) messen.
2. **Rezept und Hash:** Bei (a) stehen im Rezept Methode und Parameter, nicht die Zahlen; die exakten Zahlen gehören in Herkunft und Metadaten des Ergebnisses. Folgen für `normalize`-Version, `resolved`, Hash, Cache, Runner (Runner rechnet gleich), alte Rezepte mit `measured` (weiter angenommen?), Permalink und Ablage. Bezug `adr/0014`, `adr/0016`, `adr/0020`.
3. **⚙ am Ergebnis (NM4-05b):** Die gesperrten Schritte behalten die Werte des Ergebnisses (Antwort Otto zu #269). Wie das mit (a) zusammengeht (z. B. die exakten Zahlen aus den Metadaten des Ergebnisses als feste Werte übernehmen).
4. **Stapel:** Jeder Auftrag misst für sich (wie heute); gleiche Werte für alle Aufträge bleibt Backlog-Punkt 60.
5. **Exaktheit:** Perzentile exakt (vollständige Sortierung bzw. Histogramm mit ausreichender Auflösung?) gegen Kosten; Recherche, wie andere es machen (etwa Google Earth Engine `reduceRegion` mit `scale`/`bestEffort`, openEO `quantiles`, rasterio/GDAL-Statistik), mit Quellen.
6. **Vorschau-Schätzung:** Overview-Stufe, Abweichung zur exakten Messung belegen (Tabelle für typische Bänder und Indizes).

## 5. Grenzen

- Modulgrenzen laut `architekturplan.md` 3.1; ausgehend nur über `gateway`; Worker-Kern zustandslos; `decomp.py` nicht anfassen.
- Oberflächentexte nur Englisch; wenig Text, Erklärungen hinter (i) bzw. im Tooltip.
- Keine AOI, Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- Nachträge in ADRs heißen nach der Aufgabe („Nachtrag NM4-71“).
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Plan im Draft-PR mit Optionen, Empfehlung, Quellen und Messung; Otto gibt frei.
- Danach: Tests mit Gegenprobe (Job exakt auch über 2048², Vorschau ohne AOI, alte Rezepte, ⚙), bitgleich Job/Runner; Browserprüfung in Hell/Dunkel und schmalem Fenster; Prüfanleitung für Otto (Browser und PowerShell 5.1).
- Alle vier Pflicht-Checks grün; Log-Zeile mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.

---

# Plan (01.11.2026)

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung. Gelesen auf `main` = `6634d93` (nach NM4-11b, #269).

## 7. Kurzfassung

- **Empfehlung Frage 1: (a) im Job, mit einer Arbeitsdatei.** Der Planer schneidet die Kette vor einem messenden `normalize`: Der erste Durchgang rechnet die Schritte davor in eine `float64`-Arbeitsdatei und zählt dabei die Bänder des Schritts über die AOI (wie der letzte Durchgang heute die Statistik des Ergebnisses zählt); ein kurzer lokaler Durchgang über diese Datei macht die Perzentile exakt; der zweite Durchgang liest die Arbeitsdatei und rechnet `normalize` und den Rest. Die Quellen werden **einmal** gelesen, wie heute. Das ist dieselbe Mechanik wie ein `grid`-Schritt (`reproject`), nur ohne Warp. Der Worker-Kern bleibt zustandslos: alles im selben Lauf, nichts zwischen Jobs.
- **Gemessen [M]:** Der Job wird um 27–52 % länger (ganze Szene: 1 Band 63 → 94 s, 4 Bänder 269 → 409 s), Speicher bis 483 MB, die Quellen-Bytes bleiben gleich. Die Alternativen (Messung vorab in `api` oder zweites Lesen im Job) kosten in dieser Sitzung etwa dieselbe Zeit, lesen aber doppelt so viele Bytes, brauchen für exakte Perzentile ein drittes Lesen und lassen bei (b) den Start bis ~2 min warten (§8.3).
- **Die Vorschau weicht** bei der ganzen Szene (k = 6) für Perzentil-Enden bis 6 %, für Median und Quartile bis 7 % der Spanne ab; für Z-Score eines Index über große Flächen um Größenordnungen (Ausreißer, §8.4). Auch die heutige „exakte“ Messung liegt durch das Histogramm bis knapp 1 % daneben; die Verfeinerung trifft den sortierten Wert bitgenau (§8.5).
- **Rezept (Frage 2): `normalize` Version 4** mit Methode und Parametern, **ohne Zahlen**; die exakten Zahlen stehen im Ergebnis (Eigenschaften `earthx:normalize`, Methodentext, Lineage). Das Ergebnis ist eine reine Funktion des Rezepts; Hash, Cache, Permalink, Ablage und Runner gelten unverändert. Version 3 (Zahlen im Rezept) bleibt angenommen: für die Kachel der Vorschau, für alte Rezepte und für ⚙.
- **Vorschau (Frage 5):** Die Route von NM4-19 nimmt einen Auftrag auch ohne AOI an (dann gilt wie beim Job die Vereinigung der Footprints) und misst wie heute höchstens 2048² Pixel, für eine ganze Sentinel-2-Szene also auf einem 6-fach gröberen Raster. Die Kachel bekommt die geschätzten Zahlen als Version 3. Hinweis hinter (i): „Preview estimated on a coarser read; the job measures exactly.“
- **⚙ (Frage 3):** Ein gesperrter Schritt Version 4 wird zu Version 3 mit den exakten Zahlen aus den Eigenschaften des Ergebnisses (`factor` 1); bitgleich zum Eltern-Ergebnis über derselben Fläche.
- **Stapel (§4 Punkt 4, keine Frage):** Jeder Auftrag misst im eigenen Lauf; das Panel misst beim „Review“ nicht mehr je Auftrag, „Review“ und „Start“ warten nicht mehr auf eine Messung.
- **Exaktheit (Frage 4):** Perzentile exakt als *nearest rank* über alle Pixel der AOI auf dem Raster des Ergebnisses (zweistufiges Histogramm, Verfeinerung aus der Arbeitsdatei); Mittelwert exakt (wie M4-32), Standardabweichung wie GDAL. Kein Werkzeug des Vergleichs liefert exakte Perzentile über 120 Mio. Pixel in begrenztem Speicher ohne einen solchen zweiten Blick auf die Daten (§8.2).
- **Schnitt (Frage 6):** ein PR, Backend und Frontend in getrennten Commits (wie NM4-11b), oder zwei gestapelte PRs.

## 8. Befunde

### 8.1 Heute im Code [P]

- `normalize` Version 3 (`processing/operators/normalize.py`): vier Methoden, die statistischen mit `measured` (`factor`, Zahlen je Band) im Rezept; Kern `_line`/`_centred` in `float64`, Ergebnis `float32`; `T1` und `T2`. Der Runner rechnet die Zahlen des Rezepts und misst nichts (`adr/0016` §12 Nachtrag NM4-11).
- Die Route `POST /collections/{dataset}/statistics` (`api/area_statistics.py`) lehnt einen Auftrag ohne `aoi` ab (`_check_order`, `422`, Otto F6 zu NM4-19) und Schritte der Art `grid`; sie misst über `core.area_statistics` höchstens `MAX_AREA_PIXELS` = 2048², darüber auf einem um `area_factor` k gröberen Raster (GDAL wählt die Übersicht). Die Annahme eines Jobs ohne AOI setzt die Vereinigung der Footprints als AOI ein (`RecipeRequest.aoi`, `api/intake.py`); dieselbe Annahme läuft in der Route (`estimate_order`), es fehlt nur die Prüfung in `_check_order`.
- Der Kern rechnet schon in Durchgängen (`plan.segments`): eine Folge von `pixel`-Schritten oder ein `grid`-Schritt; zwischen zwei Durchgängen liegt eine `float64`-Arbeitsdatei, bandweise gespeichert (`_Run.write_pass`, `interleave="band"`). Der letzte Durchgang zählt beim Schreiben die Statistik über die Maske (M4-32); die Maske ist vorher geschrieben. Ein Zähl-Durchgang „beim Schreiben“ ist also vorhanden, nur nicht vor einem Schritt.
- `disk_needed` (`plan.py`) rechnet für jeden Rasterjob schon mit zweimal dem rohen `float64`-Durchgang über den breitesten Vorrat; der Speicher hängt nur an der Blockgröße (1024²), nicht an der Fläche.
- Perzentile (`processing/statistics.py`): festes Histogramm; Ganzzahlen bis 16 bit exakt, sonst 65 536 Fächer der relativen Breite 2⁻⁷, Fachkante nach außen. Reflexion nach `scale`/`offset` und `band_math` sind `float32`, das Histogramm ist für sie also **nicht** exakt (§8.5).
- ⚙ (NM4-05b, `adr/0019` Nachtrag NM4-05b): ein gewöhnlicher Auftrag, von der Quelle neu gerechnet, die Schritte des Eltern-Jobs gesperrt vorn; seit NM4-11b behält ein gesperrter `normalize` die `measured`-Werte der Auftragskopie (`adr/0019` Nachtrag NM4-11b). Die Fläche des neuen Auftrags kann eine andere sein.
- Frontend: Messung je Auftrag in `processingOrder.ts::measureSteps` (Sperre ohne AOI `NO_AOI`, nach `reproject` `AFTER_REPROJECT`), Pool in `processingStore.ts::ensureMeasures`, Zahlen in die Kachel über `processingPreview.ts::planPreview`; „Review“/„Start“ gesperrt über `measureBlock` (`ProcessingPanel.tsx`).

### 8.2 Stand der Technik [P] [S]

Abgerufen am 01.11.2026, nur `raw.githubusercontent.com` war aus der Sitzung erreichbar; Seiten von Google, Sentinel Hub und Spark nur als Suchtreffer [S]. Die Lesung [P] lief über das Abrufwerkzeug der Sitzung.

| Werkzeug | Schätzung | Exakt | Perzentile |
|---|---|---|---|
| Earth Engine `reduceRegion` | `scale` gröber; `bestEffort` wählt selbst ein gröberes Raster, wenn `maxPixels` (Vorgabe 10⁷) nicht reicht [S] | auf dem Raster von `scale` | `Reducer.percentile`: bis `maxRaw` Werte direkt, darüber aus einem Histogramm (`maxBuckets`, `minBucketWidth`) [S] |
| openEO `quantiles` | nicht vorgesehen | Typ 7 (Hyndman–Fan, linear interpoliert); die Referenz `openeo-processes-dask` rechnet `numpy.quantile` im Speicher [P] | linear interpoliert |
| GDAL `gdalinfo -approx_stats`, `ComputeStatistics(approx)` | Übersicht oder jeder n-te Block, markiert `STATISTICS_APPROXIMATE=YES` [P] | `-stats` | keine; `GetHistogram` mit festen Fächern [P] |
| rio-tiler / TiTiler `/statistics` | `max_size` Vorgabe 1024: gezählt auf einer verkleinerten Lesung [P] | nur über das Gelesene | sortiert, gibt einen Datenwert ohne Interpolation [P] |
| dask | `dask.array.percentile` „approximate“: Perzentile je Chunk, gemischt [P] | `dask.array.quantile` legt alles in einen Chunk, `numpy.quantile` [P] | — |
| Spark `approxQuantile` | Greenwald–Khanna, Rangfehler `err·N` [P] | `relativeError=0`, „could be very expensive“ [P] | — |
| KLL-Sketch (DataSketches) | k = 200: ±1,65 % des Rangs, 99 % Konfidenz [P] | nein | — |

- **Schätzung auf einer Übersicht ist üblich** (GDAL `approx`, rio-tiler `max_size`, Earth Engine `bestEffort`), und sie wird **gekennzeichnet** (GDAL `STATISTICS_APPROXIMATE`). Das stützt Soll 1 und den Hinweis hinter (i).
- **Exakte Perzentile großer Flächen** halten bei den verglichenen Werkzeugen alle Werte im Speicher (openEO-dask, dask `quantile`, Spark mit Fehler 0). Für eine ganze Szene sind das ~480 MB je Band in `float32`, über der Grenze eines Jobs bei mehreren Bändern. Ein Histogramm mit Verfeinerung im getroffenen Fach (Radix-/Bucket-Auswahl) braucht wenig Speicher und einen zweiten Blick auf die Daten; eine zitierbare Implementierung dafür wurde nicht gefunden [A]; der klassische Rahmen ist die Auswahl in mehreren Durchgängen bei kleinem Speicher (Munro & Paterson 1980 [S]).
- **Nearest rank** (wie heute und wie rio-tiler: ein Wert, der vorkommt) bleibt; openEO und numpy interpolieren (Typ 7). Der Unterschied liegt zwischen zwei benachbarten Werten der Fläche.

### 8.3 Kosten der exakten Messung [M]

Sentinel-2 C1 L2A, Kachel 32UPU, August 2025, eine wolkenfreie ganze Szene (offene Copernicus-Lizenz; nichts davon liegt im Repo). Flächen: Quadrate in der Mitte der Szene und die ganze Szene ohne AOI (Vereinigung der Footprints). „1 Band“: `normalize` Perzentil 2–98 % auf `red`; „4 Bänder“: auf `blue`, `green`, `red`, `nir`. Je Lauf ein eigener Prozess (kalt, wie ein Worker), GDAL-Optionen von `readers`; Werte: Laufzeit, gelesene MB aus dem Netz, Spitzen-RSS.

| Fläche | Bänder | Job heute (Version 3) | (a1) im Job, Arbeitsdatei | davon 2. Durchgang + Verfeinerung | Arbeitsdatei | (a2)/(b): Messung + Job | Messung allein (Wartezeit bei (b)) |
|---|---|---|---|---|---|---|---|
| 20 km (2048²) | 1 | 5 s, 14 MB, 271 MB | 5 s, 14 MB, 309 MB | 1 s | 10 MB | 8 s, 28 MB | 3 s, 277 MB |
| 20 km (2048²) | 4 | 30 s¹, 57 MB, 383 MB | 19 s, 57 MB, 453 MB | 4 s | 42 MB | 39 s, 114 MB | 9 s, 379 MB |
| 41 km (4096²) | 1 | 11 s, 39 MB, 312 MB | 16 s (+43 %), 39 MB, 359 MB | 4 s | 40 MB | 18 s, 79 MB | 7 s, 321 MB |
| 41 km (4096²) | 4 | 51 s, 248 MB, 400 MB | 66 s (+27 %), 248 MB, 481 MB | 15 s | 167 MB | 77 s, 481 MB | 26 s, 365 MB |
| 82 km (8192²) | 1 | 40 s, 121 MB, 344 MB | 57 s (+43 %), 121 MB, 390 MB | 14 s | 158 MB | 59 s, 241 MB | 19 s, 334 MB |
| 82 km (8192²) | 4 | 181 s, 884 MB, 409 MB | 264 s (+46 %), 884 MB, 482 MB | 56 s | 658 MB | 273 s, 1 768 MB | 92 s, 365 MB |
| ganze Szene (10980²) | 1 | 63 s, 159 MB, 345 MB | 94 s (+49 %), 159 MB, 391 MB | 25 s | 266 MB | 91 s, 319 MB | 28 s, 334 MB |
| ganze Szene (10980²) | 4 | 269 s, 681 MB, 411 MB | 409 s (+52 %), 681 MB, 483 MB | 98 s | 1 112 MB | 385 s, 1 362 MB | 117 s, 382 MB |

¹ Ausreißer (Netz); die übrigen Wiederholungen (ganze Szene 1 Band, 82 km 4 Bänder) lagen innerhalb von ±7 %.

- **(a1) liest die Quellen genau einmal** (gleiche MB und Anfragen wie der Job heute); (a2) und (b) lesen sie zweimal.
- **Die Laufzeit ist bei (a1) und (a2)/(b) etwa gleich, +27 bis +52 %.** In dieser Sitzung liegt der Bucket nah, das Lesen ist schnell; der zweite Durchgang über die lokale `float64`-Datei (lesen, `normalize`, schreiben, Statistik) kostet ungefähr so viel wie ein zweites Lesen aus dem Netz. Ohne Kompression der Arbeitsdatei wurde es nicht schneller (ganze Szene, 1 Band: 97 s statt 94–99 s; 82 km, 4 Bänder: 276 s statt 247–264 s), es kostet nur Platz (1 015 MB statt 266 MB). Über eine langsamere Leitung (lokaler Runner beim Benutzer, Cloud-Worker in einer anderen Region) wiegt das doppelte Lesen schwerer [A]: 681 MB mehr sind bei 10 MB/s gut eine Minute.
- **Speicher:** Spitze bis 483 MB, blockweise, unabhängig von der Fläche (Wachstum von 20 km auf die ganze Szene: 1 Band +82 MB, 4 Bänder +30 MB); weit unter `MAX_JOB_MEMORY_BYTES` (1,5 GB). (b) hält den Speicher im Prozess von `api` (bis 382 MB je Messung).
- **Platz:** Die Arbeitsdatei (deflate) ist kleiner als der rohe `float64`-Durchgang, den `disk_needed` schon zweimal einplant (ganze Szene, 4 Bänder: 1,1 GB gegen 2 × 3,9 GB).
- **Wartezeit bei (b):** bis ~2 min vor dem Start für eine ganze Szene mit 4 Bändern, synchron in `api`; ein Stapel von 25 Szenen wären bis ~50 min.

### 8.4 Wie weit die Vorschau danebenliegt [M]

Gleiche Szene, `core.area_statistics` mit Grenze 2048² (die Vorschau, k wie die Route) gegen dieselbe Messung ohne Grenze (das Raster des Ergebnisses). Abweichung in Prozent der exakten Spanne: Perzentil-Enden in `p98 − p2`, Quartile und Median in `p75 − p25`, Mittel und Streuung in der exakten Streuung.

| Fläche | k | Band | p2 | p98 | p25 | Median | p75 | Mittel | Streuung |
|---|---|---|---|---|---|---|---|---|---|
| 20 km | 2 | blue | 0,5 | 1,4 | 0,2 | 2,2 | 1,8 | 0,0 | 3,0 |
| 20 km | 2 | red | 0,2 | 0,5 | 0,3 | 2,2 | 2,7 | 0,0 | 1,7 |
| 20 km | 2 | nir | 1,9 | 1,1 | 1,4 | 0 | 1,4 | 0,0 | 2,7 |
| 20 km | 2 | swir16 (20 m) | 0 | 0 | 0 | 0 | 0 | 0,0 | 0 |
| 20 km | 2 | NDVI | 0,3 | 0 | 2,7 | 2,1 | 0,7 | 0,1 | 1,5 |
| 41 km | 3 | blue | 0,5 | 2,2 | 0,8 | 2,5 | 2,0 | 0,0 | 3,9 |
| 41 km | 3 | red | 0,1 | 0,5 | 0,3 | 2,3 | 2,3 | 0,0 | 2,2 |
| 41 km | 3 | nir | 2,3 | 1,0 | 1,4 | 0 | 1,4 | 0,0 | 3,0 |
| 41 km | 3 | NDVI | 0,6 | 0,5 | 3,4 | 2,2 | 0,8 | 0,2 | 1,7 |
| 82 km | 5 | blue | 1,0 | 6,4 | 2,0 | 5,4 | 0 | 0,0 | 10,3 |
| 82 km | 5 | red | 0,4 | 3,2 | 1,3 | 7,2 | 0,8 | 0,0 | 6,7 |
| 82 km | 5 | nir | 6,1 | 2,7 | 5,5 | 0 | 5,5 | 0,0 | 7,9 |
| 82 km | 5 | swir16 | 0,8 | 1,2 | 1,7 | 0,9 | 1,7 | 0,0 | 2,7 |
| 82 km | 5 | NDVI | 1,6 | 0,5 | 5,4 | 3,9 | 2,0 | (s. u.) | (s. u.) |
| ganze Szene | 6 | blue | 1,0 | 6,0 | 2,6 | 5,6 | 1,5 | 0,0 | 10,4 |
| ganze Szene | 6 | green | 1,3 | 4,5 | 2,7 | 3,8 | 1,1 | 0,0 | 8,8 |
| ganze Szene | 6 | red | 0,4 | 3,2 | 1,7 | 6,8 | 0,9 | 0,0 | 6,8 |
| ganze Szene | 6 | nir | 5,3 | 2,8 | 4,7 | 0 | 6,7 | 0,0 | 7,8 |
| ganze Szene | 6 | swir16 | 0,8 | 1,2 | 0,9 | 0,9 | 1,8 | 0,0 | 2,8 |
| ganze Szene | 6 | NDVI | 1,6 | 0,5 | 3,4 | 3,4 | 1,1 | (s. u.) | (s. u.) |

- **Perzentil-Stretch:** Bis k = 3 (Flächen bis ~40 km) liegen die Enden innerhalb von 2,3 % der Spanne, bei der ganzen Szene (k = 6) bis 6 %, am oberen Ende der sichtbaren Bänder am meisten. Das passt zu NM4-19 §7.6 (bis 6,5 % bei 1 Mi Pixeln).
- **Robust:** Median und Quartile bis 7 % des Interquartilsabstands daneben.
- **Z-Score:** Das Mittel trifft fast genau (die Übersicht ist ein Mittel), die Streuung ist bei k ≥ 5 um 7–10 % zu klein, weil die Übersicht glättet.
- **NDVI über große Flächen:** Exakt reicht NDVI über die ganze Szene von −1,3·10⁷ bis 6,1 (Pixel mit `nir + red` nahe 0 nach dem `offset` −0,1), die exakte Streuung ist 1 203, das exakte Mittel 0,557; die Vorschau (k = 6) sieht −0,71 bis 0,96, Streuung 0,24, Mittel 0,668. Für Z-Score eines Index über eine große Fläche liegt die Vorschau also **um Größenordnungen** daneben, und der exakte Z-Score ist von Ausreißern beherrscht. Die Perzentile und Quartile trifft die Vorschau auch dort gut. Für Indizes ist „Robust“ oder „Percentile stretch“ die bessere Wahl; das gehört in den Tooltip von „Z-score“ (KE10).

### 8.5 Wie weit das Histogramm von heute danebenliegt [M]

Das heutige Histogramm (`float32` auf 65 536 Fächer, Fachkante nach außen, `exact: true` der Route) gegen alle Werte der Fläche sortiert (nearest rank), in Prozent der exakten Spanne `p98 − p2`:

| Fläche | Werte | größte Abweichung (p2, p25, Median, p75, p98; alle Bänder) |
|---|---|---|
| 20 km | 4,2 Mio. | 0,92 % (nir p98) |
| 41 km | 16,8 Mio. | 0,61 % (swir16 p98) |
| 82 km | 67,2 Mio. | 0,65 % (green p98) |
| ganze Szene | 120,6 Mio. | 0,62 % (nir p98) |

- Auch „exakt“ gemessen sind die Perzentile von heute bis knapp 1 % der Spanne daneben, immer nach außen (die Fachbreite 2⁻⁷ relativ). Bei Ganzzahlen bis 16 bit (Rohwerte ohne `scale`) wären sie exakt; Sentinel-2 kommt mit `scale`/`offset` als `float32` an.
- **Die Verfeinerung (§9.5 Option 1) trifft den sortierten Wert in allen 20 geprüften Fällen bitgenau** (4 Flächen, 1 und 4 Bänder, p2, p25, Median, p75, p98), mit einem lokalen Lesedurchgang über die Bänder des Schritts (Spalte „Verfeinerung“ in §8.3 ist darin enthalten).

## 9. Optionen und Empfehlung

### 9.1 Wo exakt gemessen wird (Frage 1)

| | (a1) im Job, Arbeitsdatei | (a2) im Job, Quellen zweimal | (b) vor dem Start in `api` | (c) eigener Messjob davor |
|---|---|---|---|---|
| Ablauf | Durchgang 1: Schritte vor `normalize` → `float64`-Datei, dabei zählen; Verfeinerung aus der Datei; Durchgang 2: Rest aus der Datei | zuerst `area_statistics` ohne Grenze, dann der Lauf mit den Zahlen | Route ohne Grenze, Start wartet, Zahlen ins Rezept | Job misst, schreibt die Zahlen ins Rezept eines zweiten Jobs |
| Quellen gelesen | einmal | zweimal die Eingänge des Schritts | zweimal (`api` und Job) | zweimal |
| exakte Perzentile | ja, Verfeinerung lokal | nur mit drittem Lesen | nur mit zweitem Lesen in `api` | wie (a2) |
| Platz im Arbeitsordner | eine `float64`-Datei der Bänder am Schnitt (in `disk_needed` schon enthalten) | nichts dazu | nichts dazu | nichts dazu |
| Speicher | blockweise wie heute; Histogramme 0,5 MB je Band | wie heute | blockweise, aber im Prozess von `api` | wie heute |
| Laufzeit [M] (ganze Szene, 1 / 4 Bänder; Job heute 63 / 269 s) | 94 / 409 s | ≈ 91 / 385 s | Job wie heute, davor 28 / 117 s Messung | wie (a2) plus Warteschlange |
| Wartezeit vor dem Start | keine | keine | 28 / 117 s, synchron (Stapel bis 25) | keine, aber zwei Jobs in der Warteschlange |
| Rezept | Methode und Parameter (Version 4) | wie (a1) | Zahlen im Rezept (Version 3 wie heute) | Zahlen im zweiten Rezept |
| Runner gleich Job | ja, derselbe Kern misst | ja | ja, Zahlen im Rezept | — |
| Grenzen (B9, Module) | Kern bleibt zustandslos | ebenso | `api` rechnet Pixel ganzer Szenen | Zustand zwischen Jobs (verletzt die Vorgabe der Aufgabe) |

**Empfehlung (a1).** Sie liest die Quellen einmal, wartet vor dem Start nicht, hält den Speicher und macht die Perzentile ohne zusätzliches Lesen der Quellen exakt. In der Laufzeit gewinnt sie in dieser Sitzung nicht (§8.3: (a1) und (a2)/(b) beide +27 bis +52 %); sie gewinnt bei den Bytes (halb so viele), bei exakten Perzentilen (kein drittes Lesen) und überall, wo die Leitung zur Quelle langsamer ist als hier (Runner beim Benutzer). (a2) ist die einfachere Alternative ohne Arbeitsdatei, wenn exakte Perzentile nicht verlangt sind (Frage 4, Option 2). (b) macht `api` zum Rechenknecht für ganze Szenen und den Start langsam; (c) widerspricht dem Auftrag (nichts zwischen Jobs).

**Wie der Kern es macht [A].** Ein Operator sagt, dass er misst (`measures`: die Bänder, die er vor sich gezählt braucht). `plan.segments` beendet vor einem messenden Schritt den Durchgang; ein neuer Segmenttyp `measure` trägt den Schritt. `_Run.write_pass` zählt im Durchgang davor die Bänder des Schritts über die Maske (dieselbe `BandStatistics` wie M4-32), dann verfeinert ein lokaler Lesedurchgang die Perzentile (§9.5), dann bekommt der Schritt seine Zahlen (`resolve_measured`, intern) und läuft wie Version 3. Nach einem `reproject` geht das ebenso (der Durchgang davor ist der `grid`-Durchgang). Zwei messende Schritte in einer Kette sind zwei Schnitte. Die Messung zählt die Pixel der Maske (AOI-Polygon, `all_touched`), wie die Statistik des Ergebnisses.

### 9.2 Rezept, Version und Hash (Frage 2)

1. **`normalize` Version 4 ohne Zahlen (Empfehlung).** Felder wie Version 3 ohne `measured`: `method`, `bands`, bei `linear` `in_min`/`in_max`, bei `percentile` `low`/`high`, bei `linear` und `percentile` `out_min`, `out_max`, `clip`. Nur `T2` (eine Kachel kann nicht über die Fläche messen); `linear` rechnet wie Version 3. Version 3 bleibt registriert und angenommen, nicht gelistet.
2. Version 3 behält `measured`, der Job überschreibt die Zahlen mit den exakten: Das Rezept stünde mit falschen Zahlen im Hash und in `recipe.json`; verworfen.
3. Version 3 mit `measured` freiwillig: Ein `op_version` bekommt keine neuen Formen (`adr/0014` §4.3, „Felder kommen nur mit Version hinzu“); verworfen.

Folgen von Option 1:

| Was | Folge |
|---|---|
| Hash (`c1`) und Cache-Schlüssel | unverändert gebildet; das Ergebnis ist eine reine Funktion des Rezepts (die Zahlen folgen aus Eingängen, AOI und Schritten), ein Cache-Treffer gibt dieselben Bytes |
| `resolved` | unberührt (Eingänge, nicht Schritte) |
| `earthx.__version__`, `recipe_version` | bleiben; kein bestehendes Rezept ändert seine Bytes |
| Runner | rechnet `core.run` und misst damit selbst; bitgleich zum Job-Kind (`runner/test_compare.py`) |
| alte Rezepte mit `measured` (Version 3) | weiter angenommen und bitgleich; Permalink und Ablage alter Aufträge gelten |
| Laden im Panel (Datei, Permalink, Ablage) | ein statistischer Schritt Version 3 wird zu Version 4 (der Job misst neu, wie KE3 heute „misst neu“); Version 2 und 3 `linear` werden Version 4 `linear` (bitgleich) |
| Ergebnis | Eigenschaft `earthx:normalize` (Liste je messendem Schritt: Methode, Bänder mit ihren Zahlen, `exact: true`); Methodentext „measured in the run over the AOI at the resolution of the result“; Lineage wie Version 3 |
| Kachel | Version 4 ist kein `T1`; das Panel schickt der Kachel Version 3 mit den geschätzten Zahlen |
| Kosten (`estimate`) | Sekunden um den zweiten Durchgang erhöht (Faktor aus §8.3), Speicher unverändert, `disk_needed` unverändert (§8.1) |
| Log | nichts Neues; keine Zahlen im Log |

### 9.3 ⚙ am Ergebnis (Frage 3)

1. **Ein gesperrter Schritt Version 4 wird Version 3 mit den Zahlen des Ergebnisses (Empfehlung).** Das Panel nimmt sie aus `earthx:normalize` der Eigenschaften des Eltern-Ergebnisses, `factor` 1; die Auftragskopie bleibt, wie sie ist. Über derselben Fläche gibt das dieselben Bytes wie das Eltern-Ergebnis (Test); über einer anderen Fläche gelten die Zahlen des Ergebnisses, wie Otto zu #269 entschieden hat.
2. Der gesperrte Schritt bleibt Version 4 und misst im neuen Lauf über die neue Fläche: widerspricht der Antwort zu #269.

Fehlt `earthx:normalize` (Ergebnis vor dieser Aufgabe), gilt der heutige Weg (Version 3 aus der Auftragskopie).

### 9.4 Stapel (§4 Punkt 4)

Jeder Auftrag misst im eigenen Lauf über seine Fläche (wie heute, Frage 6 von NM4-11). Das Panel misst nicht mehr je Auftrag beim „Review“; die Vorschau misst nur für die gezeigte Fläche. „Review“ und „Start“ warten nicht mehr auf eine Messung (KE2 von NM4-11 entfällt für den Job). Gleiche Werte für alle Aufträge bleibt Backlog-Punkt 60.

### 9.5 Exaktheit (Frage 4)

1. **Zweistufig exakt (Empfehlung).** Beim Schreiben der Arbeitsdatei das Histogramm von heute; danach für jedes gebrauchte Perzentil das getroffene Fach mit den unteren 16 Bit des `float32`-Musters ein zweites Mal zählen (65 536 Fächer, aus der Arbeitsdatei, nur die Bänder des Schritts). Ergebnis: der nearest-rank-Wert, exakt für jeden Wert, den `float32` hält (Reflexion, Indizes aus `band_math`, Ganzzahlen); für Werte, die erst `float64` hält, die `float32`-Stufe darunter (relativ 2⁻²⁴). Ganzzahlen bis 16 bit sind schon heute exakt und brauchen den zweiten Blick nicht.
2. Histogramm wie heute: kein zweiter Blick, aber für `float32` bis eine Fachbreite (relativ 2⁻⁷) daneben (§8.5), nach außen gerundet.
3. Alle Werte halten und sortieren: ~480 MB je Band und ganze Szene; nicht im Speicher eines Jobs.

Mittelwert bleibt exakt (M4-32), die Standardabweichung wie GDAL (Chan über die Blöcke, ÷ N), Perzentile nearest rank (nicht Typ 7, §8.2). Die Route der Vorschau bleibt bei Option 2.

### 9.6 Vorschau-Schätzung (Frage 5)

1. **Grenze bleibt 2048²** (Otto F2 zu NM4-19); ohne AOI misst die Route die Vereinigung der Footprints, für eine ganze Sentinel-2-Szene mit k = 6 **(Empfehlung)**. Abweichung siehe §8.4.
2. 1024² (k = 11 für eine ganze Szene): schneller, ungenauer.
3. Für die ganze Szene die gespeicherte Statistik der Quelle (GET `/statistics` der ersten Szene, wie die Farbskala bei „Whole scene“): geht nur ohne Schritte davor.

Panel: Die drei messenden Methoden gehen auch ohne AOI; der Tooltip am Schritt sagt „Preview estimated on a coarser read; the job measures exactly.“ Nach einem `reproject` bleiben sie gesperrt (die Route misst keinen `grid`-Schritt, die Vorschau hätte keine Zahl); Freigabe dort wäre eine eigene Frage.

### 9.7 Schnitt (Frage 6)

Schätzung [A]: Backend ~250 Zeilen Code, ~400 Tests (Version 4, Segment `measure`, Verfeinerung, Eigenschaften, Methodentext, Route ohne AOI, Kosten); Frontend ~150 Code, ~250 Tests (Version 4 im Auftrag, Version 3 in der Kachel, Freigabe ohne AOI, (i), ⚙ aus den Eigenschaften, kein Messen beim Review).

1. **Ein PR, Backend und Frontend in getrennten Commits (Empfehlung)**, wie NM4-11b; über dem Richtwert.
2. Zwei gestapelte PRs in dieser Session: Backend, dann Frontend.

## 10. Kleinentscheidungen

Gelten, sofern du nicht widersprichst:

- **KE1 Linear in Version 4:** ja, damit das Panel nur noch eine Version schickt; rechnet bitgleich zu Version 2 und 3 `linear`. Ein Rezept nur mit `linear` misst nichts und schneidet die Kette nicht.
- **KE2 Version 3 bleibt:** registriert, angenommen, nicht gelistet; `T1` und `T2`. Sie ist die Form der Kachel und von ⚙.
- **KE3 Eigenschaft im Ergebnis:** `earthx:normalize`, eine Liste je messendem Schritt in der Reihenfolge der Kette: `{"method", "bands": {Band: Zahlen wie `measured`}, "exact": true}`. Nur Bänder, die der Planer nicht streicht (`restrict`).
- **KE4 Methodentext** (NM4-08), z. B.: „The band NDVI was stretched from the 2nd to the 98th percentile (NDVI: 0.1270 to 0.9023; measured in the run over the AOI at the resolution of the result) onto the range 0 to 1, values outside limited to the target range, in 32-bit floating point.“
- **KE5 Vorschau-Hinweis:** am Schritt hinter (i) „Preview estimated on a coarser read; the job measures exactly.“, bei `exact: true` der Route „Preview measured exactly over the AOI.“ Keine Zeile Text im Panel dazu.
- **KE6 Route ohne AOI:** nimmt den Auftrag ohne `aoi` an (Vereinigung der Footprints wie beim Job); alle übrigen Grenzen bleiben (16 Dateien, 1 MB, `grid`-Schritte `422`). Der Cache-Schlüssel enthält die eingesetzte AOI über den Rezept-Hash; das Log nennt weiter keine Fläche.
- **KE7 Kosten:** `estimate` zählt den zweiten Durchgang mit 0,2 s je Mi Pixel und Band am Schnitt (gemessen 0,20–0,21 s, §8.3: ganze Szene 25 s für 1 Band, 98 s für 4); `memory_needed` und `disk_needed` bleiben.
- **KE8 Leere Fläche:** Hat ein Band des Schritts in der AOI keinen gültigen Wert, scheitert der Lauf mit `RecipeInvalid` „normalize: band X has no valid value over the AOI“ (vorher gab es kein Rezept); der Job zeigt den Grund.
- **KE9 Zahlenformat im Ergebnis:** `float` wie gemessen (`repr`, verlustfrei), damit ⚙ bitgleich rechnet.
- **KE10 Z-Score und Ausreißer:** Der Tooltip von „Z-score“ bekommt den Satz „Sensitive to outliers; for indices prefer Robust or Percentile stretch.“ (§8.4: NDVI über die ganze Szene). Sonst keine Änderung der Methode.

## 11. Tests (Abnahme)

Backend (`pytest`, synthetische Raster):

1. **Job exakt über 2048²:** eine synthetische Fläche 3000² (`float32`, Werte mit bekannter Verteilung) als Job mit Version 4: Perzentile, Mittel, Streuung gleich `numpy` über alle Pixel der Maske (nearest rank: `numpy.percentile(method="inverted_cdf")`); die Route hätte dort `factor` 2 gemeldet (Gegenprobe gegen Version 3 mit den Zahlen der Route: Bytes verschieden).
2. **Verfeinerung:** `float32` mit vielen Werten in einem Fach (exakt gegen `numpy`), Ganzzahl 16 bit, Ganzzahl 32 bit, negative Werte, NaN/Maske, ein Band ohne gültigen Wert (KE8), ein konstantes Band (Spanne 0, Teiler 1).
3. **Version 4 gegen Version 3:** Version 4 bitgleich zu Version 3 mit den Zahlen aus `earthx:normalize` desselben Ergebnisses (Grundlage von ⚙); `linear` bitgleich über die Versionen 1–4.
4. **Bitgleich:** zweimal derselbe Lauf; Einstellungen A und D von `adr/0016` §3.3; Runner gegen Job-Kind je Methode (`runner/test_compare.py`).
5. **Kette:** `normalize` nach `band_math`, nach `mask`, nach `reproject`, zwei messende Schritte hintereinander; ein gestrichenes Band fehlt in `earthx:normalize`.
6. **Alte Rezepte:** Version 3 mit `measured` weiter angenommen und bitgleich zu vorher (Hash eines festen Rezepts unverändert).
7. **Speicher und Platz:** 4096², vier Bänder, Version 4 unter der Grenze; Arbeitsordner nach dem Lauf leer bis auf Ergebnis und Maske, auch bei Abbruch.
8. **Fehleingaben (`422`):** Version 4 mit `measured`; unbekannte Methode; Felder einer anderen Methode; Version 4 als Kachel (`400`, nicht `T1`).
9. **Route ohne AOI:** Auftrag ohne `aoi` → Messung über die Footprints, `exact: false`, `factor` > 1 für eine große Szene; `grid`-Schritt weiter `422`; keine Fläche im Log.
10. **Gegenprobe:** Die neuen Tests scheitern gegen `6634d93`; Ergebnis im PR.

Frontend (`vitest`):

11. Auftrag schickt Version 4 ohne `measured`; Kachel bekommt Version 3 mit den geschätzten Zahlen; Methoden ohne AOI frei, nach `reproject` gesperrt; Tooltip (i) je Zustand; „Review“/„Start“ warten nicht auf eine Messung; Stapel misst nur die gezeigte Fläche; Laden von Version 3 statistisch → Version 4; ⚙ baut Version 3 aus `earthx:normalize`, ohne die Eigenschaft wie heute; keine AOI in einer URL.
12. Browser (Chromium der Sitzung): hell/dunkel, 1280/360 px, ohne AOI, mit großer AOI, ⚙; im PR beschrieben, Bilder nicht ins Repo.
13. Prüfanleitung für Otto: Browser und PowerShell 5.1 (Job ganze Szene mit Perzentil-Stretch, `earthx:normalize` gegen die Vorschau-Zahlen der Route).

## 12. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Wo exakt gemessen wird**
1. Im Job über eine Arbeitsdatei (a1). **(Empfehlung)**
2. Im Job, Quellen zweimal gelesen (a2).
3. Vor dem Start in `api` (b).

**Frage 2 — Rezept**
1. `normalize` Version 4 ohne Zahlen; Zahlen im Ergebnis; Version 3 bleibt für Kachel, alte Rezepte und ⚙. **(Empfehlung)**
2. Version 3 behält die Zahlen, der Job ersetzt sie.

**Frage 3 — ⚙**
1. Gesperrter Schritt wird Version 3 mit den exakten Zahlen des Ergebnisses. **(Empfehlung)**
2. Gesperrter Schritt misst im neuen Job neu.

**Frage 4 — Exaktheit der Perzentile**
1. Zweistufig exakt (nearest rank). **(Empfehlung)**
2. Histogramm wie heute (gemessen bis knapp 1 % der Spanne daneben, nach außen); dann ginge auch (a2) ohne Arbeitsdatei.

**Frage 5 — Vorschau**
1. Grenze 2048² auch ohne AOI. **(Empfehlung)**
2. 1024².

**Frage 6 — Schnitt**
1. Ein PR, Backend und Frontend in getrennten Commits. **(Empfehlung)**
2. Zwei gestapelte PRs.

## 13. Quellen

- openEO `quantiles`: https://raw.githubusercontent.com/Open-EO/openeo-processes/draft/quantiles.json [P]
- openEO-dask, `quantiles`: https://raw.githubusercontent.com/Open-EO/openeo-processes-dask/main/openeo_processes_dask/process_implementations/math.py [P]
- openEO Geotrellis, Quantile in `aggregate_spatial`: https://github.com/Open-EO/openeo-geopyspark-driver/issues/714 [S]
- GDAL `gdalinfo` (`-stats`, `-approx_stats`): https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/programs/gdalinfo.rst [P]
- GDAL `gdal raster info`: https://raw.githubusercontent.com/OSGeo/gdal/master/doc/source/programs/gdal_raster_info.rst [P]
- GDAL `ComputeStatistics`, `GetHistogram`: https://raw.githubusercontent.com/OSGeo/gdal/master/gcore/gdalrasterband.cpp [P]
- rasterio `statistics(approx)`: https://raw.githubusercontent.com/rasterio/rasterio/main/rasterio/_io.pyx [P]
- rio-tiler `Reader.statistics(max_size=1024)`: https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/io/rasterio.py [P]
- rio-tiler `get_array_statistics`: https://raw.githubusercontent.com/cogeotiff/rio-tiler/main/rio_tiler/utils.py [P]
- TiTiler `/cog/statistics`: https://raw.githubusercontent.com/developmentseed/titiler/main/docs/src/endpoints/cog.md [P]
- dask `percentile`: https://raw.githubusercontent.com/dask/dask/main/dask/array/percentile.py [P]
- dask `quantile`: https://raw.githubusercontent.com/dask/dask/main/dask/array/reductions.py [P]
- xarray `quantile`: https://raw.githubusercontent.com/pydata/xarray/main/xarray/core/dataarray.py [P]
- Spark `approxQuantile`: https://raw.githubusercontent.com/apache/spark/master/sql/api/src/main/scala/org/apache/spark/sql/DataFrameStatFunctions.scala [P]
- DataSketches KLL: https://raw.githubusercontent.com/apache/datasketches-java/master/src/main/java/org/apache/datasketches/kll/KllSketch.java [P]
- Munro & Paterson 1980, Selection and sorting with limited storage: https://wrap.warwick.ac.uk/46321 [S]
- Earth Engine `reduceRegion`: https://developers.google.cn/earth-engine/apidocs/ee-image-reduceregion [S]
- Earth Engine `Reducer.percentile`: https://developers.google.cn/earth-engine/apidocs/ee-reducer-percentile [S]
- Sentinel Hub Statistical API: https://docs.sentinel-hub.com/api/latest/api/statistical [S]
- Intern: `plans/querschnitt/nm4-11-normalize-methoden.md` §7–§16; `plans/querschnitt/nm4-19-auto-stretch-ueber-aoi.md` §7.5, §7.6, §14; `adr/0014` §4.3, §4.4, §4.5, §15 Nachtrag NM4-11/NM4-11b; `adr/0016` §3.3, §12; `adr/0019` Nachtrag NM4-05b/NM4-11b; `adr/0020` §4.

## 14. Messanhang

`scripts/nm4-71-normalize/measure.py` (Kopf des Skripts). Suche über eine MGRS-Kachel (kein Ort eines Benutzers), dann:

```bash
PYTHONPATH=backend python -W ignore scripts/nm4-71-normalize/measure.py prepare <ordner> --items items.json
```

```bash
PYTHONPATH=backend python -W ignore scripts/nm4-71-normalize/measure.py run <ordner>
```

```bash
PYTHONPATH=backend python -W ignore scripts/nm4-71-normalize/measure.py summary <ordner>
```

Gemessen am 01.11.2026 in der Cloud-Sitzung (4 Kerne, 15 GB), je Fall einmal; ganze Szene 1 Band und 82 km 4 Bänder (Job und (a1)) zweimal, ohne Kompression der Arbeitsdatei (`NM4_71_WORK_COMPRESS=none`) ganze Szene 1 Band und 82 km 4 Bänder einmal. Die Variante `truth` hält alle Werte der Fläche (bis 3,9 GB RSS bei der ganzen Szene mit sechs Bändern) und ist nur für den Vergleich da. Der Prototyp (a1) nutzt interne Funktionen von `processing.core` und ist kein Entwurf des Codes.

## 15. Freigabe (Otto, 01.11.2026, zu #273)

| Frage | Antwort |
|---|---|
| 1 Wo exakt gemessen wird | **1:** im Job über eine Arbeitsdatei (a1) |
| 2 Rezept | **1:** `normalize` Version 4 ohne Zahlen; Zahlen im Ergebnis |
| 3 ⚙ | **1:** der gesperrte Schritt behält die exakten Zahlen des Ergebnisses |
| 4 Exaktheit | **1:** Perzentile exakt, zweistufig |
| 5 Vorschau | **1:** bis 2048², auch ohne AOI |
| 6 Schnitt | **1:** ein PR |

KE1–KE10 wie vorgeschlagen. **Auflagen:**

1. Den Plattenplatz der Arbeitsdatei je Auftrag messen und im PR nennen; die Grenze in die Kostenschätzung bzw. die Annahme aufnehmen; die Arbeitsdatei auch bei Abbruch, Fehler und `DELETE` löschen (Test).
2. Der Runner liest `normalize` Version 4 und rechnet bitgleich zum Job (Test).
3. Tooltip „Z-score“: Hinweis auf Ausreißer bei Indizes, Verweis auf „Robust“ (KE10).

## 16. Umsetzung (01.11.2026)

Draft-PR [#273](https://github.com/oscipal/earthX/pull/273) trägt Plan und Umsetzung (Frage 6: ein PR). Umfang: Backend-Code +690/−90, Backend-Tests +2 188/−25, Frontend-Code +490/−217, Frontend-Tests +637/−265, Browser-Skript +236/−56, Prozess-Fixtures neu erzeugt (+20/−442), Skripte (Messung, Prüfanleitung) +1 019, Dokumente +337. Weit über dem Richtwert, wie in §9.7 angekündigt.

**Auslegungen von Claude** (gelten, bis Otto widerspricht):

1. **Messen vor einem `reproject`** geht: gezählt wird auf dem Raster des Durchgangs, der die Arbeitsdatei schreibt (vor dem Warp das des Vorrats), so wie die Route den Anfang der Kette vor NM4-71 gemessen hat. Der Methodentext sagt deshalb „measured in the run over the AOI at full resolution“ statt „at the resolution of the result“.
2. **Methodentext ohne Zahlen.** `provenance.methods` entsteht bei der Annahme, vor dem Lauf; er nennt für Version 4 keine Zahlen (Abweichung von KE4). Die Zahlen stehen in `earthx:normalize`. Die Lineage hat die Form von Version 3.
3. **`earthx:normalize` fehlt**, wenn kein messender Schritt läuft (keine leere Liste); alte Ergebnisse bleiben byte-gleich.
4. **Kachel mit Version 4: `422`** „does not run as a tile“ wie jeder Operator ohne `T1` (die Freigabe-ADR nannte `400`; korrigiert).
5. **Speicher:** Der Messdurchgang hält mehr (synthetisch 4096², 4 Bänder: 516 statt 425 MB; echte ganze Szene, 4 Bänder: 486 statt 413 MB RSS). `memory_needed` zählt 60 MB je gemessenem Band des größten Schnitts (`MEMORY_BYTES_PER_MEASURED_BAND`).
6. **Arbeitsdateien** werden gelöscht, sobald der Durchgang, der sie liest, fertig ist (auch in Ketten mit `reproject`); höchstens zwei Durchgangsdateien liegen zugleich im Arbeitsordner. Die Namen zählen weiter hoch (`pass-1.tif`, …).
7. **KE8:** zwei Gründe, „has no valid value over the AOI“ und (Z-Score) „has no finite standard deviation over the AOI“. In der Vorschau ist ein Band ohne gültigen Wert nur ein Hinweis am Schritt; der Auftrag geht raus, der Job scheitert mit dem Grund.
8. **⚙:** Zahlen aus `earthx:normalize` je `step`; fehlt dort ein Eintrag, gelten die Zahlen der Auftragskopie (ein Schritt Version 3, der nichts maß); fehlen beide oder ein Band (z. B. ein Band, das der Planer im Eltern-Job gestrichen hat, weil die Ausgabe es nicht brauchte), bleibt der Schritt Version 4 und misst im neuen Lauf. Fehlt die Eigenschaft am Eintrag des Jobs, lädt das Panel das Ergebnisdokument einmal nach.
9. **Vorschau:** Gemessen wird nur für die gezeigte Einheit (bei mehreren Aufträgen der erste); die Messung des Bildbereichs (NM4-19) bekommt die Kette als Version 3.

**Plattenplatz (Auflage 1)** [M], echter Kern, dieselbe Sentinel-2-Szene wie §8.3, Höchststand aller Dateien im Arbeitsordner (alle 0,2 s und je Block gemessen) gegen `disk_needed`:

| Fläche, Bänder | Version 3 heute | Version 4 | Arbeitsdatei allein (§8.3) | `disk_needed` |
|---|---|---|---|---|
| 41 km, 1 | 201 MB | 198 MB | 40 MB | 806 MB |
| 41 km, 4 | 814 MB | 888 MB | 167 MB | 2 347 MB |
| 82 km, 4 | 2 942 MB | 3 235 MB | 658 MB | 7 309 MB |
| ganze Szene, 1 | 1 182 MB | 1 167 MB | 266 MB | 3 488 MB |
| ganze Szene, 4 | 4 813 MB | 5 327 MB | 1 112 MB | 12 665 MB |

Der Höchststand liegt beim Schreiben des COG, nicht beim Messen; die Arbeitsdatei ist dann schon gelöscht. Version 4 braucht bis 11 % mehr Platz als Version 3 und bleibt überall unter 45 % von `disk_needed`. Die Annahme rechnet `disk_needed` wie bisher, `worker` prüft den freien Platz vor dem Start (`disk_space`); eine feste Obergrenze bei der Annahme gibt es weiter nicht (Frage A unten). Gelöscht wird die Arbeitsdatei bei Erfolg, Fehler und Abbruch im Kern (`_Run.cleanup`, Tests in `test_normalize_exact.py`), der Arbeitsordner nach jedem Lauf von `worker`, auch nach `DELETE`, Beenden und Tod des Kindes (`jobs/test_worker.py`).

**Offene Fragen an Otto:**

- **A — Platz bei der Annahme.** 1. Wie bisher: `disk_needed` geht mit dem Auftrag, `worker` lehnt vor dem Start ab, wenn der Platz fehlt. **(Empfehlung)** 2. Zusätzlich eine feste Obergrenze bei der Annahme (Wert wäre festzulegen, z. B. 20 GB).
- **B — Methodentext mit Zahlen.** 1. So lassen: Zahlen in `earthx:normalize`, der Text sagt, wie gemessen wurde. **(Empfehlung)** 2. Methodentext nach dem Lauf neu schreiben.
