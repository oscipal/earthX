# M4-24 — Weitere Resampling-Methoden für `reproject`

**Stand:** 12.10.2026, beauftragt von Otto.
**Stufe B:** Erst kommt der Plan mit Messung in den Draft-PR, Otto gibt ihn frei, dann folgt der Code.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** Erst nach dem Merge von M4-21. Die Aufgabe zählt als Stufe-B-Session; gleichzeitig laufen höchstens zwei.
**Startsatz:** „Führe Aufgabe M4-24 aus `docs/plans/m4/m4-24-resampling-methoden.md` aus.“

## 1. Anlass und Grundlage

- **M4-10, Entscheidung Otto vom 07.10.2026 (Log):** Resampling gibt es bisher nur mit `nearest`, `bilinear` und `cubic`, weil nur diese gemessen und gegen `adr/0014` §6.3 belegt sind.
- **Log vom 07.10.2026, Status „offen“:** Die Methoden `cubicspline`, `lanczos` und `average` folgen jeweils mit eigener Messung gegen §6.3. Weil sie das Ergebnis ändern, bekommen sie eine neue `op_version`.
- **Otto, 12.10.2026:** Er will die zusätzlichen Methoden. Neu dazu kommt `mode` für Klassendaten.
- **Weitere Grundlagen:**
  - `adr/0014`: §3.4 (Messaufbau Reprojektion), §5.2 (Parameter), §5.3 (Capabilities `reprojection` und `interpolation`), §5.5 (Faktoren der Schätzung), §6.3 (Toleranzen), §7.2 und §7.3 (Speicher).
  - Plan `plans/m4/m4-processing-kern.md`: M4-10 und M4-10b.

**Ziel:** Der Operator `reproject` bietet zusätzlich `average`, `mode`, `cubicspline` und `lanczos` an. Jede Methode ist gemessen und gegen eine Toleranz belegt, und jede hat einen Faktor in der Schätzung.

## 2. Plan im PR (vor jedem Produktivcode)

### 2.1 Stand der Technik, mit Quellen

- **GDAL-Dokumentation zu `gdalwarp -r`:** Wie behandeln `average` und `mode` Nodata, wie gewichten sie Pixelanteile, wie verhält sich `mode` bei float-Daten? Maßgeblich ist die GDAL-Version im Image.
- **Namen der Methoden:** in openEO `resample_spatial` und im rasterio-Enum `Resampling`. Die Parameter bleiben bei den Namen wie in openEO (`adr/0014` §5.2).
- **Bekannte Unterschiede zwischen ganzem `reproject` und blockweisem `WarpedVRT`:** Das betrifft besonders `average` und `mode`, die viele Quellpixel je Zielpixel lesen.

### 2.2 Messung [M], Aufbau wie `adr/0014` §3.4 und M4-10b

- **Daten:**
  - synthetisches DEM (float32),
  - synthetisches NDVI (float32),
  - für `mode` zusätzlich ein synthetisches Klassenraster (uint8, wenige Klassen, mit Nodata).
- **Was je neuer Methode gemessen wird:**
  - Vergleich ganz gegen blockweise: Anteil identischer Pixel, p99 und max |Δ|.
  - Vergleich 1 gegen 4 Threads, ob bitgleich.
  - Zeit je Megapixel, daraus der Faktor für §5.5.
  - Spitzenspeicher (`VmHWM`) im Aufbau von `test_memory_reproject.py`, bei 2048² und 4096², gegen die Grenze von 500 MB.
- **Zwei Fälle getrennt:** Ziel gröber als die Quelle (Vergröbern) und Ziel feiner als die Quelle.
- **Blockplan:** Er bleibt fest (`tolerance` 0,125, `warp_mem_limit` 64 MB, Blöcke 1024 px). Wenn eine Methode ihn ändern müsste, ist das eine Frage an Otto und keine Änderung im Alleingang.

### 2.3 Vorschlag für die Toleranzen

- Je Methode eine neue Zeile für `adr/0014` §6.3 (T2 gegen ein ganzes `reproject`), mit den Messwerten.
- Methoden, die keine sinnvolle Toleranz halten oder die Speichergrenze reißen, werden nicht aufgenommen. Das kommt mit Beleg in den Plan.

### 2.4 Fragen an Otto, je mit Optionen und Empfehlung

1. **Versionierung:** Bekommt der Operator die `op_version` 3? Nimmt er die Version 2 danach weiter an (die alten Methoden liefern dasselbe Ergebnis) oder nur noch 3 (K7, `422`)?
2. **Capabilities:** Welche neuen Methoden verlangen `interpolation`? Vorschlag zum Prüfen: alle außer `mode`; `mode` braucht wie `nearest` nur `reprojection`.
3. **`mode` auf float-Daten:** erlauben, abweisen oder nur warnen?
4. **`average` beim Verfeinern** (Ziel feiner als die Quelle): erlauben, abweisen oder warnen?
5. **Panel:** Liest das Frontend die Methoden aus dem Parameterschema von `/processing/processes`? Falls die Liste fest im Frontend steht: im Frontend ergänzen oder auf das Schema umstellen?

## 3. Umsetzung nach Freigabe

- **Operator:** `processing/operators/reproject.py` bekommt die erweiterte Methodenliste, die `op_version` und das Verhalten alter Versionen nach Ottos Antwort zu Frage 1, und die Capability-Regeln nach Frage 2.
- **Schätzung:** Faktoren je Methode aus der Messung.
- **Panel:** Die Methoden sind wählbar. Oberflächentexte nur auf Englisch.
- **Keine Vorbelegung im Panel:** Resampling bleibt im Panel ohne Vorbelegung und ohne Empfehlung (Otto, 12.10.2026, M4-13b zweite Fassung). Die Hilfetexte unter dem Feld erklären jede Methode in einem Satz (Englisch). Ein Beispiel: „average: mean of all source pixels per target pixel; for coarsening continuous data“.
- **Tests:**
  - Plausibilitätstest je neuer Methode gegen ein ganzes `reproject`, mit den Grenzen aus der neuen Zeile in §6.3.
  - T2 zweimal gerechnet ist bitgleich.
  - Speichertest 2048² und 4096² unter 500 MB für die speicherhungrigste neue Methode.
  - Abweisung ohne Capability.
  - Verhalten alter `op_version` nach Ottos Entscheidung.
  - Frontend-Test für die Auswahl.
- **Fixtures:** nur synthetisch.

## 4. Grenzen

- Geändert werden nur `reproject`, die Faktoren der Schätzung, die Tests und, falls nötig, die Methodenauswahl im Panel.
- Kein neuer Operator, keine Änderung an `band_math`.
- Keine neue Abhängigkeit ohne Frage an Otto.
- Die Modulgrenzen bleiben, wie sie sind (Import-Linter grün).
- Keine Anfragen an echte Quellen.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Dokumentation

- **`adr/0014`:** datierter Nachtrag als nächster freier Abschnitt nach §15d, mit den neuen Zeilen für §6.3 und den Faktoren für §5.5. Der Originaltext bleibt unverändert.
- **`docs/plans/m4/m4-processing-kern.md`:** Zeile M4-24 in §3 (nach M4-21, Stufe B). Zeilenenden so lassen, wie die Datei sie dann hat.
- **`docs/ENTSCHEIDUNGSLOG.md`:**
  - Die Zeile vom 07.10.2026 „Weitere Resampling-Methoden für `reproject` nach Messung“ bekommt den Status „aufgenommen als M4-24 (2026-10-12)“.
  - Neue Zeilen für Ottos Antworten zu §2.4 und für die Umsetzung.

## 6. Abnahme

- Jede aufgenommene Methode hat:
  - eine Messung,
  - eine Zeile in §6.3,
  - einen Faktor in §5.5,
  - einen grünen Plausibilitätstest,
  - eine bitgleiche Wiederholung.
- Der Speichertest liegt unter 500 MB.
- Die Methoden sind im Panel wählbar.
- Alle vier Pflicht-Checks der CI sind grün.
- Vor „fertig“ ist main geholt.

---

## 7. Plan mit Messung (19.10.2026, zur Freigabe durch Otto)

Stufe B: Bis zur Freigabe ist kein Produktivcode geändert. Belegstufen wie in `adr/0014`: [P] Primärquelle gelesen, [M] gemessen, [S] Sekundärquelle, [A] eigene Ableitung.

**Kurzfassung.**

- Alle vier Methoden lassen sich mit dem festen Blockplan aufnehmen. Gemessen wurden 48 Läufe (DEM, NDVI, Klassenraster; Vergröbern, etwa gleich, Verfeinern). Jeder Lauf war bitgleich, mit 1 wie mit 4 Threads und bei der Wiederholung, ganz wie blockweise gerechnet. `XSCALE`/`YSCALE` oder andere Änderungen am Plan sind nicht nötig.
- `cubicspline` liegt überall unter `bilinear`. `lanczos` liegt wie `cubic`. Beim Verfeinern des DEM reißen beide die heutige Grenze der Höhen (p99 ≤ 0,3 m, max ≤ 1 m) knapp, das bestehende `cubic` also auch (Frage 7).
- `average` beim Vergröbern: ganz und blockweise sind beim DEM bitgleich, beim NDVI ist p99 0,00024. Beim Verfeinern weicht es stärker ab als jede andere Methode (DEM p99 0,66 m, max 2,85 m). Siehe Frage 4.
- `mode` auf Klassen: 99,995–99,998 % der Pixel sind ganz wie blockweise gleich. Auf stetigen Daten verhält sich `mode` wie `nearest`, weil jeder Wert nur einmal vorkommt und der erste gewinnt (Frage 3).
- Speicher (`VmHWM`, 4096²): Jede neue Methode liegt gleichauf mit `bilinear`, bei gleicher Pixelgröße 422–426 MB. Den höchsten Wert liefert `lanczos` beim Vergröbern mit 443 MB, 57 MB unter der Grenze (§7.5).
- Faktoren für §5.5 (gegenüber `bilinear` = 1,0): `cubicspline` 1,6, `lanczos` 2,2, `average` 1,2, `mode` 1,1.

### 7.1 Stand der Technik (§2.1)

GDAL im Image ist **3.12.2** (rasterio 1.5.2 aus `requirements.lock`, `rasterio.__gdal_version__`). Gelesen am 19.10.2026 im Tag `v3.12.2` von `OSGeo/gdal` [P]: `doc/source/programs/gdalwarp.rst`, `alg/gdalwarpkernel.cpp` (im Folgenden `kernel`), `alg/gdalwarpoperation.cpp` (`operation`), `frmts/vrt/vrtwarped.cpp`. Die Adressen stehen in §7.10.

| Methode | Nodata | Gewichtung | float-Daten | Ziel feiner als Quelle | Kernel |
|---|---|---|---|---|---|
| `average` | ungültige Quellpixel fallen weg; nodata nur, wenn keins gültig bleibt (Doku Z. 293; `kernel` Z. 7580 ff.) | Flächenanteil: innere Pixel 1, Randpixel der Bruchteil des Footprints (`COMPUTE_WEIGHT_Y`, Z. 6690; „Weighted incremental algorithm mean“, Z. 7703) | wie ganzzahlig; NaN ist über `src_nodata=nan` ungültig | Fenster 1–2 Quellpixel je Achse, ein flächengewichtetes Mittel aus 1–4 Pixeln: treppig, kein Glätten [A] | Radius 0 (`anGWKFilterRadius`, Z. 84) |
| `mode` | wie `average` | Zähler sind Flächengewichte (`pafCounts[i] += dfWeight`, Z. 7023) | eigener Weg `GWKModeRealType<T>` (Z. 6886) für Float32/64 und 32/64-bit-Ganzzahlen: Liste der Werte, exakter Vergleich (`IsSame`); Puffer **so groß wie das ganze Quellfenster des Abschnitts**, `nSrcX·nSrcY·(sizeof(T)+4)` Byte je Thread (Z. 6900–6904) | das Quellpixel mit dem größten Flächenanteil [A] | Radius 0 |
| `cubicspline` | Zielpixel nodata, wenn das Quellpixel unter seinem Zentrum ungültig ist; ungültige Nachbarn bekommen Gewicht 0 (Doku; `kernel` `GWKGeneralCaseThread`) | B-Spline, Gewichte ≥ 0 | kein Klemmen | normaler Kernel | Radius 2 (`GWKBSpline`, Z. 107) |
| `lanczos` | wie `cubicspline`; zusätzlich kein Wert, wenn weniger als die Hälfte des Fensters gültig ist (Z. 4569) | Lanczos-Sinc, negative Lappen | kein Klemmen: Über- und Unterschwinger möglich | normaler Kernel | Radius 3 (`GWKLanczosSinc`) |

**Gleichstand bei `mode`:** gewinnt der erste erkannte Wert (Doku Z. 297; Standard `GWKTS_First`, `kernel` Z. 991). „Erster“ heißt in der Reihenfolge, in der der Kernel das Quellfenster abtastet: Zeile für Zeile, links nach rechts.

**Vergröbern verbreitert den Kernel, und der Maßstab gilt je Abschnitt.** `kernel` Z. 1038–1068: `dfXScale = nDstXSize / (nSrcXSize − dfSrcXExtraSize)`, berechnet für **jeden Warp-Abschnitt** aus dessen Quell- und Zielfenster; liegt `1/dfXScale` nahe einer ganzen Zahl (±0,05), rastet er dort ein. Bei Maßstab < 0,95 wird das Quellfenster um `ceil(Radius/Maßstab)` erweitert (`operation` Z. 3254–3263) und der Kernel um den Maßstab gestreckt. Das betrifft `bilinear`, `cubic`, `cubicspline` und `lanczos`; die Vier-Punkte-Formeln von `bilinear`/`cubic` gelten nur bei Maßstab ≥ 0,95 (Z. 1163). `XSCALE`/`YSCALE` können den Maßstab festsetzen; die Doku nennt sie nicht („undocumented for now“, Z. 1061). Ein Beleg, dass derselbe Ausschnitt mit anderem Quellfenster anders ausfällt: OSGeo/gdal#2810 (offen; Rouault nennt die Maßstabs-Heuristik als Ursache) [S].
`average` und `mode` haben Radius 0; bei ihnen wirkt der Maßstab nur auf den Rand der Zeilenkoordinaten (`nXMargin`, Z. 6942), nicht auf die Gewichte.

**Approximation (`tolerance` 0,125):** Die Footprints von `average` und `mode` entstehen aus den genäherten Ecken der Zielpixel (`GWKAverageOrModeComputeLineCoords`); ein Fehler bis 0,125 Quellpixel verschiebt die Randgewichte. Beim Verfeinern ist der Footprint kleiner als ein Quellpixel, der Fehler wiegt dort relativ schwerer [A].

**Wie `WarpedVRT` das Fenster des Operators warpt** (`vrtwarped.cpp`):
- Ein Fenster, das alle Bänder liest und größer als ein VRT-Block ist, warpt GDAL 3.12 direkt als einen Abschnitt (`IRasterIO`, Z. 1900–1913). Das gilt für die 1024er-Fenster des Operators.
- Übersteigt der Speicherbedarf `warp_mem_limit`, teilt GDAL das Fenster weiter (Z. 2050–2054).
- Kleinere Fenster am Rand gehen über die VRT-Blöcke (höchstens 512 px breit, Z. 447).
- Ein ganzes `reproject` teilt dagegen das ganze Raster nach seinem eigenen Speicherbedarf. Beide Wege rechnen also verschiedene Abschnitte, jeder mit eigenem Maßstab.

**Bekannte Fehler in der Nähe** [S]: OSGeo/gdal#13539 (`-r sum` mit Streifen an Abschnittsgrenzen, behoben in 3.12.1, also im Image enthalten); #2665 (`average` mit `-te`/`-t_srs`, behoben in 3.1.1). Ein Issue zu `average` oder `mode` speziell zwischen ganzem Warp und `WarpedVRT` ist nicht bekannt. `NEWS.md` (Z. 575–576) nennt für 3.12.0 „make mode resampling NaN aware“ [P].

**Namen** [P]:
- openEO `resample_spatial`, `method`: `average`, `bilinear`, `cubic`, `cubicspline`, `lanczos`, `max`, `med`, `min`, `mode`, `near`, `q1`, `q3`, `rms`, `sum` (`Open-EO/openeo-processes`, `resample_spatial.json`, Stand `master` am 19.10.2026).
- rasterio 1.5.2 `Resampling`: `cubic_spline` (Wert 3) für GDALs und openEOs `cubicspline`; `average`, `mode`, `lanczos` heißen gleich.
- Folge: Der Parameter heißt wie in openEO `cubicspline`; der Operator bildet ihn auf `Resampling.cubic_spline` ab. `nearest` bleibt wie bisher (openEO: `near`); das entscheidet M4-24 nicht neu.

### 7.2 Messaufbau (§2.2) [M]

- **Rechner:** Cloud-Sitzung, x86_64, 4 Kerne, 16 GB. GDAL 3.12.2, rasterio 1.5.2, numpy 2.5.3, wie im Lock.
- **Daten** (synthetisch, `make_data.py`, §7.10). Jede Quelle liegt so vor, wie der Kern sie dem Operator gibt: als float64-Zwischendatei mit NaN für Maskiertes (`core._INTERMEDIATE_DTYPE`), Blöcke 1024, Deflate.
  - **DEM:** 3600² px, EPSG:4326, 1″, glattes Gelände (Werte rund 360 bis 2940 m) mit Rauschen σ 2 m, aufgebaut wie `adr/0014` §17.6.
  - **NDVI:** 4096² px, EPSG:32632, 10 m, glattes Feld von −0,2 bis 0,9 mit Rauschen σ 0,02. Dazu ein Nodata-Streifen (40 px) und eine Nodata-Ecke (512²).
  - **Klassen:** 4096² px, EPSG:32632, 10 m, sechs Klassen (1–6) als Voronoi-Flächen, Nodata wie beim NDVI. Für den Typvergleich liegt dasselbe Raster zusätzlich als `uint8` mit Nodata 255 vor.
- **Fälle** (Ziel-CRS, Pixelgröße; Faktor = Quellpixel je Zielpixel und Achse):

| Datensatz | Vergröbern | etwa gleich | Verfeinern |
|---|---|---|---|
| DEM (1″ ≈ 20,7 × 30,9 m) | EPSG:32632, 90 m (x 4,3, y 2,9) | EPSG:32632, 30 m (x 1,45, y 0,97), wie §3.4 | EPSG:32632, 10 m (x 0,48, y 0,32) |
| NDVI, Klassen (10 m) | EPSG:3035, 30 m (3) | EPSG:3035, 10 m (1) | EPSG:3035, 5 m (0,5) |

- **Blockweise** heißt die Funktion `_run` des Operators: `WarpedVRT`, `tolerance` 0,125, `warp_mem_limit` 64 MB, Fenster 1024 px, `GDAL_CACHEMAX` 64 MB. Die vier neuen Methoden sind dafür nur im Messskript in `_RESAMPLING` eingetragen.
- **Ganz** heißt ein `rasterio.warp.reproject` über das ganze float64-Array auf dasselbe Zielraster, wie `test_reproject._reference`.
- **Verglichen** wird das Ergebnis als float32, wie es geschrieben wird:
  - Anteil identischer Pixel, p99 und max |Δ| dort, wo beide gültig sind.
  - die Pixel, die nur eine Seite maskiert: „nur blockweise / nur ganz“.
  - bitgleich: SHA-256 der float32-Bytes und gleiche Maske, je für 1 gegen 4 Threads, blockweise (`NUM_THREADS` im VRT) wie ganz, und für eine Wiederholung.
- **Zeit:** blockweise, 1 Thread, Sekunden je Megapixel der Ausgabe.

### 7.3 Ganz gegen blockweise, Threads [M]

**Bitgleichheit:** In allen 48 Läufen sind ganz wie blockweise 1 gegen 4 Threads bitgleich, die Masken eingeschlossen. Blockweise ist auch die Wiederholung bitgleich. Die Zusage T2 ↔ T2L (§6.3 Zeile 1) hält damit für alle vier Methoden.

**Ganz gegen blockweise.** Spalten: identisch / p99 / max |Δ| / Pixel nur blockweise bzw. nur ganz maskiert. Einheit: DEM in m, NDVI ohne Einheit, Klassen in Klassennummern. Die bestehenden Methoden sind zum Vergleich mitgemessen; DEM „etwa gleich“ trifft §3.4 (nearest 97,7 %, bilinear p99 0,21/max 0,68 m gegen 0,20/0,70 m dort).

| Methode | DEM vergröbern | DEM etwa gleich | DEM verfeinern |
|---|---|---|---|
| nearest | 100 % / 0 / 0 / 0, 0 | 97,7 % / 2,36 / 14,3 / 8, 66 | 97,4 % / 2,58 / 13,8 / 319, 248 |
| bilinear | 1,8 % / 0,044 / 0,10 / 0, 0 | 0,25 % / 0,21 / 0,68 / 8, 66 | 0,48 % / 0,27 / 0,88 / 319, 248 |
| cubic | 1,8 % / 0,031 / 0,068 / 0, 0 | 0,19 % / 0,25 / 0,94 / 8, 66 | 0,45 % / **0,33** / **1,19** / 319, 248 |
| **cubicspline** | 3,5 % / 0,015 / 0,034 / 0, 0 | 0,36 % / 0,13 / 0,36 / 8, 66 | 0,80 % / 0,16 / 0,48 / 319, 248 |
| **lanczos** | 2,1 % / 0,040 / 0,092 / 0, 0 | 0,16 % / 0,28 / 0,99 / 8, 66 | 0,39 % / **0,34** / **1,20** / 319, 248 |
| **average** | 100 % / 0 / 0 / 0, 0 | 0,69 % / 0,21 / 0,59 / 78, 67 | 37 % / **0,66** / **2,85** / 608, 573 |
| **mode** | 100 % / 0 / 0 / 0, 0 | 97,7 % / 2,36 / 13,2 / 78, 67 | 97,4 % / 2,58 / 15,6 / 608, 573 |

| Methode | NDVI vergröbern | NDVI etwa gleich | NDVI verfeinern |
|---|---|---|---|
| nearest | 98,8 % / 0,0063 / 0,12 / 7, 8 | 99,1 % / 0 / 0,14 / 1, 9 | 99,7 % / 0 / 0,13 / 1, 23 |
| bilinear | 0,02 % / 0,00057 / 0,0013 / 7, 8 | 0,13 % / 0,00075 / 0,0024 / 1, 9 | 0,08 % / 0,00020 / 0,00080 / 1, 23 |
| cubic | 0,02 % / 0,00072 / 0,0016 / 7, 8 | 0,12 % / 0,00093 / 0,0069 / 1, 9 | 0,07 % / 0,00025 / 0,0068 / 1, 23 |
| **cubicspline** | 0,03 % / 0,00036 / 0,00078 / 7, 8 | 0,25 % / 0,00037 / 0,0012 / 1, 9 | 0,16 % / 0,00010 / 0,00031 / 1, 23 |
| **lanczos** | 0,01 % / 0,00094 / 0,0020 / 7, 8 | 0,10 % / 0,00099 / 0,0033 / 1, 9 | 0,06 % / 0,00027 / 0,00091 / 1, 23 |
| **average** | 0,07 % / 0,00024 / 0,0010 / 8, 8 | 0,13 % / 0,00075 / 0,0024 / 28, 12 | 25 % / 0,00038 / 0,0015 / 26, 15 |
| **mode** | 98,8 % / 0,0062 / 0,12 / 8, 8 | 99,1 % / 0 / 0,12 / 28, 12 | 99,7 % / 0 / 0,14 / 26, 15 |

| Methode | Klassen vergröbern | Klassen etwa gleich | Klassen verfeinern |
|---|---|---|---|
| nearest | 99,995 % / max 5 / 7, 8 | 99,995 % / max 5 / 1, 9 | 99,998 % / max 5 / 1, 23 |
| **mode** | 99,996 % / max 5 / 8, 8 | 99,995 % / max 5 / 28, 12 | 99,998 % / max 5 / 26, 15 |

**Was daraus folgt.**
- **`cubicspline`:** Die Abweichung ist in jedem Fall kleiner als bei `bilinear`. Der B-Spline glättet, deshalb ist auch der Wertebereich schmaler (NDVI etwa gleich: −0,136 bis 0,834 gegen −0,169 bis 0,854 bei `bilinear`).
- **`lanczos`:** wie `cubic`. Beim Verfeinern des DEM liegen beide über der heutigen Grenze für Höhen (p99 ≤ 0,3 m, max ≤ 1 m). §6.3 ist bisher nur bei etwa gleicher Pixelgröße gemessen (§3.4); das bestehende `cubic` reißt die eigene Zeile also auch (Frage 7). Über- oder Unterschwinger über den Wertebereich der Quelle hinaus traten auf diesen glatten Daten nicht auf. An harten Kanten sind sie nach §7.1 möglich [A].
- **`average`:** Beim Vergröbern ist der Footprint gleich, ob ganz oder blockweise gerechnet wird. Das DEM ist dann bitgleich, das NDVI weicht kaum ab. Beim Verfeinern ist der Footprint kleiner als ein Quellpixel. Der Näherungsfehler von bis zu 0,125 Quellpixeln verschiebt dann die Randgewichte, und die Abweichung wird größer als bei jeder Interpolation [A, aus §7.1]: DEM p99 0,66 m, max 2,85 m.
- **`mode`:** Auf Klassen ist `mode` so stabil wie `nearest`. Wo es abweicht, liegt dort die Nachbarklasse (max |Δ| = 5 ist nur der Abstand der Klassennummern 1 und 6, kein Fehler im Wert). Auf DEM und NDVI liefert `mode` fast dasselbe wie `nearest`: Jeder float-Wert kommt einmal vor, alle Zähler sind gleich, und nach der Regel „erster Wert gewinnt“ (§7.1) bleibt das erste abgetastete Quellpixel. Beim Vergröbern ist das die linke obere Ecke des Footprints, nicht seine Mitte [A].
- **Masken:** Nur wenige Pixel sind nur auf einer Seite maskiert, höchstens 608 von 84,9 Mio. (DEM verfeinern, `average`/`mode`), alle am Rand der Daten.
- **`mode` auf `uint8` gegen float64** (ganz, nur zur Einordnung): 99,92 % (10 m), 99,98 % (30 m) und 99,83 % (5 m) der Pixel sind gleich; 672, 78 bzw. 2824 Pixel sind anders maskiert. Die Gleichstandsregel ist in beiden Wegen dieselbe (`GWKTS_First`, `kernel` Z. 7988 und 7033). Vermutlich teilt GDAL den Warp je Datentyp anders in Abschnitte, und die Näherung je Abschnitt verschiebt die Footprints [A]. Für die Plattform zählt nur der float64-Weg, weil der Kern jede Quelle so übergibt. Ein `gdalwarp -r mode` auf dem `uint8`-Original kann sich davon in 0,1–0,2 % der Pixel unterscheiden.

### 7.4 Zeit und Faktoren für §5.5 [M]

Sekunden je Megapixel Ausgabe, blockweise, 1 Thread; in Klammern relativ zu `bilinear` im selben Fall:

| Methode | DEM verg. | DEM gleich | DEM verf. | NDVI verg. | NDVI gleich | NDVI verf. |
|---|---|---|---|---|---|---|
| nearest | 0,51 (0,74) | 0,086 (0,53) | 0,027 (0,45) | 0,40 (0,72) | 0,065 (0,67) | 0,032 (0,55) |
| bilinear | 0,69 (1) | 0,161 (1) | 0,060 (1) | 0,55 (1) | 0,097 (1) | 0,058 (1) |
| cubic | 0,91 (1,33) | 0,168 (1,04) | 0,102 (1,70) | 0,84 (1,52) | 0,134 (1,37) | 0,105 (1,80) |
| **cubicspline** | 0,92 (1,33) | 0,173 (1,07) | 0,105 (1,74) | 0,81 (1,46) | 0,158 (1,62) | 0,114 (1,96) |
| **lanczos** | 0,93 (1,35) | 0,240 (1,49) | 0,155 (2,57) | 1,16 (2,09) | 0,212 (2,18) | 0,158 (2,71) |
| **average** | 0,73 (1,06) | 0,126 (0,78) | 0,068 (1,13) | 0,43 (0,78) | 0,115 (1,18) | 0,070 (1,21) |
| **mode** | 0,77 (1,12) | 0,133 (0,82) | 0,059 (0,99) | 0,50 (0,90) | 0,103 (1,05) | 0,061 (1,05) |
| mode, Klassen | 0,19 | 0,079 | 0,058 | | | |

**Vorschlag:** Die Faktoren stehen wie die bestehenden auf dem Fall „etwa gleich“, gegenüber `bilinear` = 1,0. Genommen wird der größere Wert aus DEM und NDVI, aufgerundet auf eine Nachkommastelle:

| Operator | Faktor |
|---|---|
| Reprojektion `cubicspline` | **1,6** |
| Reprojektion `lanczos` | **2,2** |
| Reprojektion `average` | **1,2** |
| Reprojektion `mode` | **1,1** |

**Beobachtung außerhalb von M4-24:**
- Die Zeit je Megapixel Ausgabe hängt stark vom Maßstab ab. Beim Vergröbern um 3 kostet jede Methode 4–8-mal so viel je Ausgabepixel wie bei gleicher Pixelgröße, weil sie 9 Quellpixel liest.
- Das Kostenmodell (§5.5, Ausgabe-MP × Faktor) unterschätzt das Vergröbern deshalb für alle Methoden, die heutigen eingeschlossen.
- Das gehört zur Kalibrierung des Laufzeitdeckels, die nach M4 vorgemerkt ist (Log 10.10.2026, S3). M4-24 ändert das Modell nicht.
- Die eigene Messung von `nearest` (0,53–0,67) und `cubic` (1,04–1,37) liegt über den Faktoren 0,4 und 1,1 von §5.5. Auch das gehört zur Kalibrierung.

### 7.5 Speicher [M]

Aufbau wie `test_memory_reproject.py`: dieselbe Szene (zwei Bänder `uint16`), Pixel-Durchgang und Warp-Durchgang, nach EPSG:3035, `GDAL_CACHEMAX` 64 MB, `worker_environment()`, `VmHWM` des Kindprozesses. Nur der Parametertyp ist für die neuen Methoden erweitert (`memory_method.py`, §7.10). Zwei Läufe je Zeile.

| Methode | 2048², 10 m | 4096², 10 m | Wachstum | 4096², 30 m (vergröbern 3) | 4096², 5 m (verfeinern 2, Ausgabe 8305²) |
|---|---|---|---|---|---|
| bilinear (Bezug, M4-10b: 346/425) | 345,9–346,1 | 425,0–425,2 | 79 | 442,6 | 420,8 |
| **cubicspline** | 346,0–346,3 | 425,1 | 79 | 443,0 | 420,8 |
| **lanczos** | 346,2–346,5 | 425,5 | 79 | **443,2** | 420,8 |
| **average** | 345,9–346,0 | 425,2 | 79 | 442,2 | 420,4 |
| **mode** | 343,0–343,2 | 421,8–421,9 | 79 | 439,6 | 414,6 |

- Keine neue Methode braucht mehr als `bilinear`. Der Unterschied liegt unter 1 MB. Den größten Wert liefert `lanczos` beim Vergröbern: 443,2 MB, also 57 MB unter der Grenze. In der CI lag `bilinear` 8 MB über der Sitzung (M4-10b).
- Das Vergröbern um 3 kostet bei jeder Methode rund 17 MB mehr als die gleiche Pixelgröße, auch bei `bilinear`. Die Quellfenster je Abschnitt sind dabei neunmal so groß [A]. Den Blockplan berührt das nicht.
- Der eigene Puffer von `mode` auf float (§7.1: `nSrcX·nSrcY·12` Byte je Abschnitt) fällt nicht auf: `mode` liegt in jedem Fall am niedrigsten. GDAL rechnet den Puffer vermutlich nicht in `warp_mem_limit` ein. Er wächst aber mit dem Quellfenster des Abschnitts, und das Quellfenster begrenzt `warp_mem_limit`. Mit float64 (8 Byte je Quellpixel) bleibt der Puffer deshalb höchstens etwa anderthalbmal so groß wie der Quellpuffer [A].
- **Vorschlag für den Speichertest:** `test_memory_reproject.py` rechnet 2048² und 4096² zusätzlich mit `lanczos` bei 30 m. Das ist der höchste gemessene Wert, und der Lauf ist mit 9,6 s für 4096² schneller als bei 10 m (19–22 s). Die Wachstumsgrenze für 30 m messe ich bei der Umsetzung in Sitzung und CI. Der bestehende Lauf `bilinear` bei 10 m bleibt.

### 7.6 Vorschlag für §6.3 (§2.3)

Neue Zeilen für „T2 ↔ unabhängige Referenz (ganzes `reproject`)“. Die Grenzen enthalten die Messwerte mit Abstand; sie sind aus synthetischen Daten abgeleitet [A], wie die bestehende Zeile.

| Methode | Bedingung | Toleranz | gemessen (max über die Fälle) |
|---|---|---|---|
| `cubicspline` | Höhen | p99 ≤ 0,3 m, max ≤ 1 m (wie `bilinear`/`cubic`) | p99 0,16 m, max 0,48 m |
| `cubicspline` | NDVI | p99 ≤ 0,01 | p99 0,00037 |
| `lanczos` | Höhen | p99 ≤ 0,4 m, max ≤ 1,5 m | p99 0,34 m, max 1,20 m (verfeinern; gleich 0,28/0,99) |
| `lanczos` | NDVI | p99 ≤ 0,01 | p99 0,00099 |
| `average` | Ziel nicht feiner als die Quelle, Höhen | p99 ≤ 0,3 m, max ≤ 1 m | p99 0,21 m, max 0,59 m; vergröbern bitgleich |
| `average` | Ziel nicht feiner, NDVI | p99 ≤ 0,01 | p99 0,00075 |
| `average` | Ziel feiner als die Quelle (nur falls Frage 4 = erlauben) | Höhen p99 ≤ 1 m, max ≤ 4 m; NDVI p99 ≤ 0,01 | p99 0,66 m, max 2,85 m; NDVI p99 0,00038 |
| `mode` | Klassen | ≥ 99,9 % identisch | 99,995–99,998 % |
| `mode` | stetige Daten (falls Frage 3 = erlauben) | ≥ 97 % identisch (wie `nearest`) | 97,4–99,7 % |

**Nicht aufgenommen:** keine der vier Methoden. Alle halten eine sinnvolle Grenze und bleiben unter der Speichergrenze.

### 7.7 Fragen an Otto (§2.4)

**Frage 1 – Versionierung.** Die neuen Methoden kommen mit `op_version` 3 (Log 07.10.2026). Für `nearest`, `bilinear` und `cubic` liefert Version 3 Byte für Byte dasselbe wie Version 2, denn Blockplan und Code bleiben gleich. Ein Hinweis: Das Panel listet jede Version, die `/processing/processes` nennt, als eigenen Eintrag (`processingOrder.ts::processInfo`).
1. **Version 3 angeboten; Version 2 wird weiter angenommen, aber nicht mehr gelistet (Empfehlung).** Rezepte und `recipe.json` von Version 2 lassen sich weiter rechnen und liefern dasselbe Ergebnis. Ihr Hash und ihr Cache bleiben gültig. Das Panel zeigt einen Eintrag. Dafür braucht es eine kleine Regel in `processing_docs`: je Operator nur die höchste Version listen. Grundlage ist das Prinzip, dass sich Ergebnisse wiederholen lassen. M4-10b hat Version 1 nur abgewiesen, weil sich deren Ergebnis änderte.
2. Nur noch Version 3. Version 2 wird mit `422` abgewiesen (K7, wie Version 1 in M4-10b). Das ist am einfachsten, aber jedes bisherige Rezept mit `reproject` lässt sich danach nicht mehr rechnen, obwohl sein Ergebnis gleich bliebe.
3. Keine neue Version, die Methoden kommen in Version 2 dazu. Kein Ergebnis von Version 2 ändert sich, aber ein Rezept mit `lanczos` würde dann von einer älteren Plattform abgewiesen, obwohl es dieselbe Version trägt. Das widerspricht der Log-Zeile vom 07.10.2026.

**Frage 2 – Capabilities.** Welche neuen Methoden verlangen `interpolation`?
1. **Alle außer `mode` (Empfehlung).** `average`, `cubicspline` und `lanczos` erzeugen Werte, die in der Quelle nicht vorkommen. `mode` wählt wie `nearest` immer einen Quellwert und braucht nur `reprojection`.
2. Alle vier verlangen `interpolation`.

**Frage 3 – `mode` auf float-Daten.**
- Auf stetigen Daten ist `mode` ein `nearest` mit Versatz: Beim Vergröbern liefert es das linke obere Quellpixel des Footprints (§7.3).
- Der Operator sieht nur float64. Erkennen ließen sich float-Daten nur am `data_type` oder an `scale`/`offset` des Bandes in den Metadaten.
- Ein Band-Math-Schritt vor `reproject` liefert immer float32, auch wenn er Klassen bildet (etwa `where(ndvi > 0.3, 1, 0)`). Dort ist `mode` sinnvoll.
1. **Erlauben; der Hilfetext sagt „for class data“ (Empfehlung).** Kein neuer Prüfweg, und `mode` nach einer Klassenbildung bleibt möglich.
2. Abweisen (`422`), wenn ein Band float ist oder skaliert wird. Das trifft auch Klassen aus Band-Math.
3. Erlauben und warnen. Dafür gibt es bisher keinen Weg für Warnungen in Annahme oder Panel; er wäre neu.

**Frage 4 – `average` beim Verfeinern.** Bei einem Ziel feiner als die Quelle ist `average` ein flächengewichtetes Mittel aus 1–4 Quellpixeln: treppig, ohne Glättung, kein Mittel im üblichen Sinn (§7.1). Ganz gegen blockweise weicht es dort am stärksten ab: DEM p99 0,66 m, max 2,85 m (§7.3).
1. **Erlauben; der Hilfetext sagt „for coarsening“, §6.3 bekommt eine eigene Zeile für das Verfeinern (Empfehlung).** T2 ↔ T2L bleibt bitgleich, die Abweichung betrifft nur die Plausibilitätsprüfung. Eine Prüfung „feiner als die Quelle“ hätte Grenzfälle: Beim DEM (§7.2) wird x vergröbert, während y gleich bleibt.
2. Abweisen (`422`), wenn das Zielpixel in einer Achse kleiner ist als das Quellpixel. Das braucht eine neue Prüfung in `transform` mit einer Regel für gemischte Achsen.
3. Erlauben und warnen. Es gibt keinen Weg für Warnungen (siehe Frage 3).

**Frage 5 – Panel.** Das Panel liest die Methoden schon aus dem Parameterschema von `/processing/processes`, als `enum` (`schemaForm.ts`, `processingOrder.ts::processInfo`). Neue Methoden erscheinen also ohne Änderung im Frontend. Offen ist, woher die Hilfetexte je Methode kommen:
1. **Aus dem Schema (Empfehlung).** `resampling` beschreibt jede Methode als `oneOf` mit `const`, `title` und `description` (JSON Schema 2020-12). `schemaForm.ts` liest das als Auswahl mit Texten, und `StepForm` zeigt sie unter dem Feld. Die Texte stehen dann an einer Stelle beim Operator und gelten auch für API-Nutzer. Das braucht eine Änderung in `schemaForm.ts` und `StepForm.tsx` (etwa 60 Zeilen mit Tests).
2. Im Frontend, eine Tabelle Methode → Satz. Das ist kleiner, aber eine zweite Quelle: Eine spätere Methode käme ohne Text an.
3. Ein Text für alle Methoden in der `description` des Feldes. Das braucht keine Änderung im Frontend, aber es wird ein langer Absatz für alle sieben Methoden.

**Frage 6 – Datentyp im Panel.** Das Panel setzt den Ausgabe-Datentyp für jede Methode außer `nearest` auf float32 (`processingDefaults.ts`, „Interpolating gives fractional values“). `mode` liefert aber nur Quellwerte.
1. **`mode` zählt wie `nearest`: Eine ganzzahlige Quelle darf ihren Typ behalten (Empfehlung).** Für Klassen ist das der passende Typ.
2. `mode` zählt wie die Interpolationen und wird float32.

**Frage 7 – Bestehende Zeile von §6.3 für `cubic`.** Beim Verfeinern des DEM liegt `cubic` bei p99 0,33 m und max 1,19 m. Die Zeile von §6.3 nennt p99 ≤ 0,3 m und max ≤ 1 m. Gemessen war sie nur bei etwa gleicher Pixelgröße. Die Tests rechnen heute nur dort und sind grün.
1. **Die Zeile im Nachtrag mit der Bedingung „gemessen bei etwa gleicher Pixelgröße“ versehen und für das Verfeinern `cubic` wie `lanczos` führen (p99 ≤ 0,4 m, max ≤ 1,5 m); keine Codeänderung (Empfehlung).**
2. Unverändert lassen und nur im Plan vermerken.

### 7.8 Umsetzung nach Freigabe (§3)

Annahme: die Empfehlungen. Bei anderen Antworten passe ich den Plan vor dem Code an.

| Commit | Was | Dateien | Zeilen (ca.) |
|---|---|---|---|
| 1 | Methoden, `op_version` 3, Version 2 weiter angenommen (nur die drei alten Methoden), `interpolation` außer bei `nearest`/`mode`, Faktoren | `processing/operators/reproject.py`, `operators/__init__.py` bzw. `registry` | 50 |
| 2 | `/processing/processes` listet je Operator nur die höchste Version | `api/processing_docs.py` | 15 |
| 3 | Hilfetexte als `oneOf` im Schema | `reproject.py` | 25 |
| 4 | Tests Backend: Plausibilität je Methode gegen ganzes `reproject` mit den Grenzen aus §7.6 (Vergröbern und gleich; `mode` auf einem synthetischen Klassenraster), Wiederholung bitgleich, Abweisung ohne `interpolation` (und `mode` ohne), Version 2 mit den alten Methoden gleich Version 3, Version 2 mit `lanczos` abgewiesen, Schema listet eine Version; Speichertest zusätzlich mit `lanczos` bei 30 m, 2048² und 4096² (§7.5) | `tests/earthx/processing/test_reproject.py`, `test_memory_reproject.py`, `tests/earthx/api/test_processing_docs.py`, Fixtures der Prozessbeschreibung | 150 |
| 5 | Panel: `oneOf` mit Texten in `schemaForm`/`StepForm`, `mode` wie `nearest` beim Datentyp, Frontend-Tests für Auswahl und Text | `frontend/src/schemaForm.ts`, `components/StepForm.tsx`, `processingDefaults.ts`, Tests, `fixtures/processes/*.json` | 90 |
| 6 | Doku: `adr/0014` Nachtrag §15j (§6.3-Zeilen, §5.5-Faktoren, Frage 7), Log-Zeilen, §3 von `plans/m4/m4-processing-kern.md` | `docs/` | 60 |

Zusammen etwa 390 Zeilen ohne die generierten Fixtures, also am Richtwert. Wird es mehr, teile ich das Frontend (Commit 5) in einen eigenen PR.

**Hilfetexte (Englisch, Entwurf):**
- `nearest`: value of the nearest source pixel; for class data and masks.
- `bilinear`: distance-weighted mean of the 2×2 nearest pixels; smooth, for continuous data.
- `cubic`: cubic convolution over 4×4 pixels; sharper than bilinear, for continuous data.
- `cubicspline`: cubic B-spline over 4×4 pixels; smoothest, for continuous data.
- `lanczos`: Lanczos windowed sinc over 6×6 pixels; sharpest, may overshoot at edges.
- `average`: mean of all source pixels per target pixel; for coarsening continuous data.
- `mode`: most frequent source value per target pixel; for coarsening class data.

**Bleibt wie es ist:** Blockplan (`TOLERANCE`, `WARP_MEM_LIMIT_MB`, `BLOCK_SIZE`); das Mosaik (§15g) warpt weiter mit `nearest` und den Konstanten des Operators; keine neue Abhängigkeit; Importregeln unberührt.

### 7.9 Abnahme gegen §6

| Punkt | Stand |
|---|---|
| Messung je Methode | §7.3–§7.5 |
| Zeile in §6.3 | Vorschlag §7.6, Nachtrag nach Freigabe |
| Faktor in §5.5 | Vorschlag §7.4 |
| Plausibilitätstest, bitgleiche Wiederholung, Speichertest, Panel | nach Freigabe (§7.8) |

### 7.10 Messanhang

Die Skripte liegen nicht im Repo. Wie in `adr/0014` §17 sind sie hier beschrieben. Alle laufen aus `backend/` mit `PYTHONPATH=.`.
- `make_data.py <dir>`: die drei Zwischendateien und `classes_u8.tif` aus §7.2 (Seeds 20261019–20261021).
- `warp_compare.py <dir> <dem|ndvi|classes> <coarse|same|fine> <methode>`: eine JSON-Zeile mit den Werten aus §7.3 und §7.4. Blockweise ruft `reproject._run`, die neuen Methoden sind dafür in `_RESAMPLING` eingetragen. Ganz ist `rasterio.warp.reproject` über das float64-Array. Gezählt wird nur, wo beide Seiten gültig sind.
- `mode_types.py <dir>`: `mode` ganz auf `classes_u8.tif` (Nodata 255) gegen `classes.tif` (NaN).
- `memory_method.py <cog> <workdir> <size> <methode> <auflösung>`: `tests/earthx/processing/memory_run.py` mit erweitertem Parametertyp (Unterklasse von `ReprojectParams`) und `dataclasses.replace` des Operators. Szenen aus `test_memory_8192.build_scene`.
- GDAL-Quellen, gelesen am 19.10.2026 [P]:
  - `https://raw.githubusercontent.com/OSGeo/gdal/v3.12.2/alg/gdalwarpkernel.cpp`
  - `…/v3.12.2/alg/gdalwarpoperation.cpp`
  - `…/v3.12.2/frmts/vrt/vrtwarped.cpp`
  - `…/v3.12.2/doc/source/programs/gdalwarp.rst`
  - `…/v3.12.2/NEWS.md`
- Weitere Quellen:
  - `https://raw.githubusercontent.com/Open-EO/openeo-processes/master/resample_spatial.json` [P]
  - `https://raw.githubusercontent.com/rasterio/rasterio/1.5.2/rasterio/enums.py` [P]
  - Issues [S]: `https://github.com/OSGeo/gdal/issues/2810`, `…/13539`, `…/2665`

---

## 8. Umsetzung (20.10.2026)

**Freigabe:** Otto, 20.10.2026: Fragen 1–7 je wie empfohlen (§7.7). Dazu die Auflage zu den Tests: Jede Methode, alt und neu, wird in allen drei Fällen gegen ihre eigene Zeile geprüft, und eine zu enge Zeile lässt den Test scheitern.

**Frage 8 (aus der Umsetzung), Toleranzen für Höhen.**
- **Befund [M]:** Mit kleineren Testrastern rissen `bilinear`, `cubic` und `lanczos` auf dem DEM ihre Zeile. `bilinear` lag bei p99 0,41 m gegen die Grenze von 0,3 m.
- **Gegenprüfung:** 13 DEM-Größen über die drei Fälle. Der Abstand von ganz zu blockweise hängt von der Größe des Rasters ab, weil das ganze `reproject` als Referenz je nach Größe andere Abschnitte mit eigenem Maßstab rechnet (§7.1). Der Operator selbst bleibt bitgleich.
- **Schlechtester Wert:** p99 0,57 m (`lanczos`) und 0,92 m (`average` beim Verfeinern), max 3,74 m.
- **NDVI** hält p99 ≤ 0,01 in allen 12 geprüften Größen (höchstens 0,006).
- **Antwort Otto (20.10.2026), Option 1:** Höhen p99 ≤ 0,6 m und max ≤ 4 m für `bilinear`, `cubic`, `cubicspline`, `lanczos` und `average` (Ziel nicht feiner); `average` beim Verfeinern p99 ≤ 1 m, max ≤ 4 m. Die bisherigen 0,3 m und 1 m für `bilinear`/`cubic` sind damit ersetzt. Die Werte über alle 13 Größen und die Begründung stehen in `adr/0014` §15j.
- **Damit überholt:** die Höhenzeilen in §7.6 und Antwort 7, also die Zeile für `cubic` beim Verfeinern.

**Faktor für `cubicspline` (Otto, 20.10.2026, nach dem Review):** 1,7 statt 1,6. Gemessen waren 1,62 (NDVI, etwa gleich); die Regel von §7.4 rundet auf, 1,6 war ein Rundungsfehler im Vorschlag. Die Zahlen in §7 bleiben als Vorschlag stehen.

**Was gebaut ist:**

| Teil | Dateien |
|---|---|
| `reproject` `op_version` 3 mit sieben Methoden, je Faktor und Hilfetext im Schema (`oneOf` mit `const`, `title`, `description`); `interpolation` außer bei `nearest` und `mode`; Version 2 bleibt registriert (nur die drei alten Methoden, gleiches Ergebnis) | `processing/operators/reproject.py`, `registry.py`, `__init__.py` |
| Das Auftragsschema listet je Operator nur die höchste Version | `api/processing_docs.py` |
| Panel: `oneOf` mit Texten als Auswahl, ein Satz je Methode unter dem Feld, keine Vorbelegung; `mode` behält wie `nearest` einen ganzzahligen Typ | `frontend/src/schemaForm.ts`, `components/StepForm.tsx`, `processingDefaults.ts`, `index.css` |
| Fixtures der Prozessbeschreibung und der Aufträge neu geschrieben (`scripts/write-process-fixtures.py`, `vitest -u`) | `frontend/src/fixtures/` |

**Tests:**
- `test_reproject_tolerance.py`:
  - je Methode und Fall, auf Höhen, NDVI und Klassen (`mode`, `nearest`), gegen die eigene Zeile: 48 Fälle;
  - dazu je Fall die Gegenprobe mit einer Zeile, die halb so weit reicht wie gemessen: 48 Fälle;
  - jeder Fall spannt mehr als einen Block des Kerns.
- `test_reproject.py`:
  - ein ganzer Lauf je Methode gegen die eigene Zeile;
  - zwei Läufe bitgleich je Methode, Maske je Methode;
  - Version 2 gleich Version 3 für die alten Methoden, Version 2 weist die neuen ab;
  - `interpolation` und `mode`, Faktoren, Schema mit einem Satz je Methode.
- `test_processing_docs.py`: Nur die höchste Version wird gelistet; der Diskriminator bleibt.
- `test_memory_reproject.py`: zusätzlich `lanczos` bei 30 m mit 2048² und 4096². Gemessen 302 / 437 MB, Wachstum 135 MB, Grenze 180 MB.
- Frontend:
  - `schemaForm` liest dokumentiertes `oneOf` und weist anderes `oneOf` ab;
  - das Panel zeigt sieben Methoden mit ihrem Satz und schickt `op_version` 3;
  - Datentyp bei `mode` und `average`.
