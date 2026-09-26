# M3-18 — Download-Deckel nach Ausgabegröße und Maske auf die AOI: Umsetzungsplan

**Aufgabe:** M3-18 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B** — **von Otto am 24.09.2026 freigegeben** mit F1 (1), F2 (1), F3
(2), F4 (1), F5 (2), F6 (2), F7 (1), F8 (1) (§8) und **umgesetzt**. Die
native Auflösung (§10, Ottos Erweiterung vom 23.09.2026) ist mit Ottos
Antworten auf F10a–c (§10.8) **ebenfalls umgesetzt** — Code, Tests und
ENTSCHEIDUNGSLOG.md-Zeile stehen. **Maske statt nodata** (§11, Ottos weitere
Vorgabe vom 23.09.2026, ohne Rückfrage direkt umgesetzt) ist **ebenfalls
umgesetzt**: die Datendatei ist immer ein reiner Bounding-Box-Zuschnitt, das
AOI-Polygon lebt in einer eigenen Maskendatei je Asset plus einer
`aoi.geojson` je ZIP. F9 (§9, Kompression des maskierten Zuschnitts,
Nebenfund) bleibt offen, unabhängig von §10/§11.
**Ort im Repo:** `docs/plans/m3-18-download-deckel-maske.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` (§1.2, §1.3, M3-17,
M3-18, P19); `ENTSCHEIDUNGSLOG.md`, Zeilen vom 20.09.2026 (M2-06, Deckel) und
23.09.2026 („Download-Deckel: 200 MB gelten für die Ausgabe …“, „Zuschnitt auf
die AOI-Geometrie …“); `adr/0006` §3.4, §3.5; `adr/0004` §3.4; `KLAERUNGEN.md`
B8, B10; heutiger Code in `backend/earthx/access/download.py` und
`backend/earthx/api/tiler.py` (`download_crop`).

---

## 1. Ziel in einem Satz

Ein Zuschnitt über viele Szenen wird nach der Größe der Datei geprüft, die
tatsächlich entsteht, der Arbeitsspeicher des `tiler` hat eine gemessene
Grenze, und beim Polygon-AOI enthält jede Datei nur Pixel innerhalb des
Polygons — für jeden Datensatz und jede Item-Zahl im selben Format.

---

## 2. Heutiger Stand (gelesen und nachgeprüft, 24.09.2026)

| Stelle | heute | Folge |
|---|---|---|
| `check_size_cap` | Items × Assets × 4096 × 4096 × 4 Byte ≤ 200 MB | 1 Item × 1 Asset = 67 MB; **ab 3 Items ist jeder Zuschnitt abgewiesen**, auch wenn das Mosaik eine einzige 4096-px-Datei ergibt |
| Rechnung je Pixel | 1 Band × 4 Byte | unterschätzt ein 3-Band-float32-Asset um den Faktor 3 |
| `mosaic_reader` | ohne `threads`, also rio-tilers `MAX_THREADS` = Kerne × 5 (hier 20) | alle Items einer Anfrage werden **gleichzeitig** gelesen, siehe §3 |
| Maske, 1 Item | rio-tiler setzt die Maske außerhalb des Polygons, `ImageData.to_raster` schreibt aber die Rohdaten plus `nodata`-Tag | **Pixel außerhalb des Polygons behalten ihre Werte** (nachgeprüft: Ecke `[134, 105, 91]`, Maske 255) |
| Maske, ≥ 2 Items | Mosaik-Ergebnis ohne `nodata` → `to_raster` schreibt ein Alpha-Band | außerhalb richtig leer, aber **4 statt 3 Bänder** und kein `nodata`; das Format hängt also von der Item-Zahl ab |
| GDAL-Umgebung | die Download-Route läuft **ohne** `rasterio.Env(**gdal_options(...))`; nur der Kachel-Pfad setzt sie | Timeouts, VSI-Cache und `GDAL_DISABLE_READDIR_ON_OPEN` aus `gateway` gelten beim Zuschnitt nicht (Nebenbefund, F7) |
| Punktanzahl der AOI | im Download **kein** Deckel; der Stützpunkt-Deckel 1000 kommt mit M3-08 (Draft-PR #76, nicht gemergt) nur für die Suche | F6 |
| Meldung im Frontend | `Download failed: ` + `detail`; `detail` ist heute z. B. „6 item(s) x 1 asset(s) at up to 4096x4096 px could reach 402653184 bytes, over the 200000000 byte cap“ | für Nutzer unverständlich |

**Antwort auf die offene Frage aus M2 (§1.3 „Lokal prüfen“):** Eine AOI größer
als 4096 px je Seite wird **verkleinert, nicht abgewiesen**. rio-tiler rechnet
die lange Seite auf 4096 px herunter (gemessen: AOI über 280 km × 110 km bei
10 m → 4096 × 1057 px). Daran ändert M3-18 nichts.

---

## 3. Messung: Spitzenverbrauch von `mosaic_reader` (24.09.2026)

**Aufbau.** Synthetische COGs, im Scratchpad erzeugt, nicht im Repo: 6000 ×
6000 px, 10 m, EPSG:32632, deflate, 512er-Kacheln mit Overviews, `nodata` 0.
Zwei Anordnungen zu je 20 Dateien: **Stapel** (20 × dieselbe Fläche, wie 20
Überflüge einer Kachel) und **Raster** (5 × 4 nebeneinander, wie ein Überflug
über viele Kacheln). Ausgeliefert über einen lokalen HTTP-Server mit
Range-Requests, gelesen über `/vsicurl/` mit `CogReader`/`AssetPath` und der
GDAL-Umgebung aus `gateway.gdal_options`, also wie im `tiler`. AOI in WGS84 so
groß, dass die Ausgabe an 4096 px stößt. Jede Messung in einem eigenen
Prozess; Wert = `ru_maxrss` nach dem Aufruf minus davor (Basis nach Imports
181 MB). Maschine: 4 Kerne, 16 GB.

**3 Bänder uint8 (wie `visual`), Ausgabe 34 MB roh:**

| Anordnung | Items | Threads | Spitze über Basis | Zeit | gelesene Items |
|---|---|---|---|---|---|
| Stapel | 1 | – | 327 MB | 2,2 s | 1 |
| Stapel | 6 | 20 (heute) | 1502 MB | 6,4 s | 1 |
| Stapel | 6 | 4 | 998 MB | 4,9 s | 1 |
| Stapel | 6 | **1** | **327 MB** | 2,0 s | 1 |
| Stapel | 20 | 20 (heute) | **4489 MB** | 25,6 s | 1 |
| Stapel | 20 | 4 | 1038 MB | 4,4 s | 1 |
| Stapel | 20 | **1** | **327 MB** | 2,0 s | 1 |
| Raster | 6 | 20 (heute) | 504 MB | 2,0 s | 6 |
| Raster | 6 | **1** | **199 MB** | 2,8 s | 6 |
| Raster | 20 | 20 (heute) | 3022 MB | 15,0 s | 20 |
| Raster | 20 | 4 | 1335 MB | 14,8 s | 20 |
| Raster | 20 | 2 | 722 MB | 17,4 s | 20 |
| Raster | 20 | **1** | **373 MB** | 19,1 s | 20 |

**Ganzer Weg bis zum ZIP** (`build_download_zip`: Mosaik, COG-Kodierung, ZIP):

| Fall | Threads | Spitze über Basis | Zeit | ZIP |
|---|---|---|---|---|
| uint8, Stapel, 1 Item | 20 | 436 MB | 6,3 s | 38 MB |
| uint8, Stapel, 6 Items | 20 | 1454 MB | 9,5 s | 44 MB |
| uint8, Raster, 20 Items | 20 | 3000 MB | 18,9 s | 33 MB |
| float32 3 Bänder, 4096 × 2772 (136 MB roh), 1 Item | 1 | 1145 MB | 19,4 s | 57 MB |
| float32 3 Bänder, 4096 × 4003 (**197 MB roh, knapp am Deckel**), 1 Item | 1 | **1578 MB** | 26,7 s | 82 MB |

Ein einzelner Read bei float32: 762 MB (136 MB roh) und 1075 MB (197 MB roh);
mit 6 Items im Stapel und 1 Thread unverändert 762 MB.

**Was daraus folgt:**

1. **Heute wächst der Speicher mit der Item-Zahl,** weil `mosaic_reader` alle
   Items gleichzeitig liest; 20 Items kosten 3–4,5 GB. Mit `threads=1` liest er
   nacheinander und bricht ab, sobald alle Pixel innerhalb der AOI gefüllt sind
   (`FirstMethod.exit_when_filled`, beachtet die Polygon-Maske): im Stapel wird
   nach dem ersten Item aufgehört, der Speicher bleibt bei 1, 6 und 20 Items
   gleich. Der Preis ist Zeit im Raster-Fall (19 statt 15 s lokal; an echten
   Quellen je Item etwa 1 s, `adr/0006` §3.4 `part()`).
2. **Ein Read kostet ein Vielfaches seiner Ausgabe.** Faustformel aus den fünf
   ZIP-Messungen: **Spitze ≈ 150 MB + 7 × Rohgröße der größten Datei** (uint8
   34 MB → 388 geschätzt / 436 gemessen; float32 197 MB → 1529 / 1578). Der
   Deckel von 200 MB je Ausgabe begrenzt eine Anfrage damit auf **rund 1,6 GB**.
3. **GDAL-Block-Cache verkleinern hilft nicht:** `GDAL_CACHEMAX=64` senkt einen
   Read von 327 auf 237 MB, dauert aber **613 s statt 2 s** (der Warp liest
   dieselben Blöcke immer wieder). Ausgeschieden.

**Gezählte Anfragen an echte Quellen: 5**, gedrosselt auf höchstens 1 pro
Sekunde: je ein Item von Earth Search und EOPF STAC (Metadaten für §4.1) und
drei vergebliche Versuche, die Zarr-Metadaten eines EOPF-Speichers zu lesen
(404). Keine Pixel gelesen.

---

## 4. Umfang

### 4.1 Größenprüfung nach der Ausgabe — **umgesetzt wie geplant (F1 (1), F2 (1))**

`check_size_cap` ist ersetzt durch `plan_outputs` (eine `PlannedOutput` je
Asset: Breite, Höhe, Byte je Pixel) und `check_output_size_cap` (Summe der
`total_bytes`, `413` darüber). Aufgerufen in `api.tiler.download_crop`, vor
jedem Lesezugriff, mit den Items nach dem AOI-Vorfilter (`matched`) und den
angefragten Assets.

- **Pixel** (F1): `estimate_output_dims` — lange Seite = min(4096, Ausdehnung
  der AOI / Auflösung), kurze Seite nach dem Seitenverhältnis, mit einer
  bewusst zu großzügigen (nie zu kleinen) Meter-je-Grad-Näherung, damit die
  Schätzung nie unter der tatsächlichen rio-tiler-Ausgabe liegt (Test:
  Vergleich gegen einen echten Lese-Zugriff auf eine synthetische COG). Die
  Auflösung kommt aus dem Item (`_asset_gsd`): `gsd` am Asset, sonst
  `spatial_resolution` in `raster:bands`, sonst `gsd` in `properties`; fehlt
  alles, 4096 px.
- **Bänder × Byte** (F2): `_asset_bytes_per_pixel`, aus `raster:bands` bzw.
  `bands` des Item-Assets (`data_type`); bei einem Zarr-Komposit
  (`SR_10m:b04,b03,b02`) die Zahl der Variablen im Asset-Schlüssel. Fehlt der
  Datentyp, 8 Byte je Band; fehlt beides, 4 Bänder × 8 Byte.
- **Abweisung** mit `413` und einer Meldung auf Englisch, in MB gerundet, mit
  Ausweg: *„This download would be about 403 MB, more than the 200 MB limit.
  Draw a smaller area or download fewer layers.“*

Die 4096 px je Seite bleiben strukturell über `max_size` erzwungen.

**Nachtrag beim Testen:** Die Fixture `item_asset_hosts.json`
(Earth-Search-Lesepfad, M2-04) trug weder `gsd` noch `raster:bands`; ergänzt
um genau diese beiden Felder mit den am 24.09.2026 gemessenen echten Werten
(`visual` 3 × uint8, `red` 1 × uint16), siehe README der Fixture. Ebenso trägt
das generische Chain-Item aus `tests/catalog/synthetic_chain.py` (Onboarding-
Checkliste, Punkt 9, beide Formate) jetzt `gsd`, aus der jeweiligen Format-
Fixture (`mini_cog.RESOLUTION` / `mini_zarr_composite.RESOLUTION_M`) — ohne
das fiel jeder Zuschnitt in diesen Tests auf den Rückfallwert und damit
`413`.

### 4.2 Grenze für den Arbeitsspeicher — **F4 (1) umgesetzt, F5 (2): keine Grenze in M3**

- **Nacheinander lesen:** `crop_asset` ruft `mosaic_reader(..., threads=1)`.
  Speicher je Anfrage hängt dann nicht mehr an der Item-Zahl (§3 Punkt 1);
  obere Schranke aus der Messung rund 1,6 GB am 200-MB-Deckel, bei `visual`
  rund 0,45 GB. Gemessener Nebeneffekt: rio-tiler liest dabei nur so viele
  Items, wie es zum Füllen der AOI braucht (`FirstMethod.exit_when_filled`),
  nicht mehr alle — ein eigener Test deckt beide Fälle ab (ein Item füllt
  schon alles; ein zweites wird erst gelesen, wenn das erste nicht reicht).
- **Höchstens 25 Items je Anfrage** (`check_item_count_cap`,
  `MAX_DOWNLOAD_ITEMS`) nach dem Vorfilter, sonst `413`: *„This download
  covers 26 scenes; at most 25 fit in one download. Select fewer scenes or
  draw a smaller area.“*
- **F5 (2), von Otto entschieden:** keine Grenze für gleichzeitige Zuschnitte
  im `tiler`-Prozess in M3; der Prozess-Speicher wird mit dem Deployment (M6)
  begrenzt. Kein Semaphor, kein `503`.

### 4.3 Maske auf die AOI — **F3 (2) umgesetzt, mit einem Nebenfund (§9)**

- `_image_to_cog_bytes` schreibt die Maske als **GDAL-interne Maskenband**
  (`dst.write_mask(...)`, `cog_translate(..., add_mask=True)`), nicht als
  `nodata`-Wert und nicht als Alpha-Band: dieselbe Bandzahl bei 1 und bei
  20 Items, unabhängig vom Datentyp. Maskierte Pixel (außerhalb des Polygons
  **oder** ohne Quelldaten) werden als `0` geschrieben.
- **Abweichung von F3 (2):** Ottos Wortlaut sah zusätzlich einen `nodata`-Tag
  vor, wenn die Quelle einen hat. Das ist **nicht** umgesetzt — siehe §9: Ein
  `nodata`-Tag auf demselben Schreibvorgang lässt GDAL die Maske fallen, und
  ein nachträgliches Patchen hat sich als eigene Quelle derselben Beschädigung
  erwiesen (gemessen). Die Maske allein ist das Signal, dem ein Leser trauen
  muss; ein zusätzlicher `nodata`-Tag war ohnehin nur ergänzende Information.
- Die Ausdehnung bleibt die Box der AOI (Log 23.09.2026). Eine Rechteck-AOI
  ergibt dieselben Pixel wie heute (die Polygon-Maske deckt die ganze Box ab,
  `all_touched=True`) — Test mit einer echten synthetischen COG.
- **F6 (2), von Otto entschieden:** kein Stützpunkt-Deckel für die AOI im
  Download.

### 4.4 Frontend — **F8 (1) umgesetzt**

- Die Meldungen kommen fertig formuliert aus dem Backend (`detail`), das
  Frontend zeigt sie wie heute über `Download failed: …`. Am Frontend-Code
  ändert sich nichts; drei neue Vitest-Fälle (`api.test.ts`) halten fest, dass
  ein `413` (Ausgabe- und Item-Deckel) und ein Fehler ohne JSON-Body
  (z. B. `503`) unverändert bzw. lesbar ankommen.

### 4.5 Nicht anfassen

`readers`, `decomp.py`, Kachel-Pfad, `gateway` (außer der Nutzung von
`gdal_options` in `api/tiler.py`, F7), Gruppierung je Überflug und „Download
folgt der Ansicht“ (M3-17), Registry-Felder (F2 Option 1 braucht keine).

---

## 5. Tests — **umgesetzt**

Alle ohne Netz; COGs synthetisch per `tests/earthx/readers/mini_cog.py`, in
`backend/tests/earthx/access/test_download_mask.py` neu gegen eine echte
synthetische COG (die anderen Fälle mit einem Fake-Reader in
`test_download.py`).

| Abnahmepunkt | Test |
|---|---|
| 6 Items unter dem Ausgabe-Deckel → 200 | `test_a_successful_crop_is_a_zip_with_the_notice_file` u. a. (Route) |
| Ausgabe über dem Deckel → Abweisung mit klarer Meldung | `test_an_asset_without_size_metadata_falls_back_…` (Route, 413), `TestPlanOutputsAndCheckOutputSizeCap` (Modul) |
| Item-Deckel greift | `test_more_than_the_item_cap_is_413` (Route), `TestCheckItemCountCap` (Modul) |
| `threads=1`, liest nur so viel wie nötig | `TestCropAsset`: ein füllendes Item wird allein gelesen; ein zweites nur, wenn das erste nicht reicht (Modul) |
| schräges Polygon | `test_a_slanted_polygon_masks_outside_and_keeps_inside`: echte COG, rautenförmiges Polygon — außerhalb `0` und aus der Maske, innerhalb echte Werte und in der Maske; keine `nodata`-Tag, kein Alpha-Band |
| Rechteck-AOI unverändert | `test_a_rectangle_aoi_is_unchanged_no_pixel_is_masked_by_the_cutline`: dieselbe COG, keine maskierten Pixel |
| Ausgabeschätzung | `TestAssetGsd`, `TestAssetBytesPerPixel`, `TestEstimateOutputDims`: Werte aus `raster:bands`, aus `bands` ohne Datentyp, Zarr-Komposit, fehlende Angaben (Rückfall); Vergleich gegen eine echte rio-tiler-Ausgabe für dieselbe AOI |
| zweckfremde Nutzung | `test_a_malformed_gsd_is_treated_as_unknown_not_divided_by`: `gsd` 0, negativ, Text, `NaN`, `inf`, falscher Typ → Rückfall statt Division durch 0; unbekannter `data_type` → 8 Byte |
| keine Koordinaten im Log | `test_no_aoi_coordinate_reaches_the_log` (Route, unverändert von M2-06) |
| Frontend | `describe('downloadCrop', …)` in `api.test.ts`: ein `413` (Ausgabe- und Item-Deckel) und ein Fehler ohne JSON-Body kommen unverändert bzw. lesbar durch |

`test_download.py::TestCheckSizeCap` ist ersetzt durch `TestCheckItemCountCap`,
`TestAssetGsd`, `TestAssetBytesPerPixel`, `TestEstimateOutputDims`,
`TestPlanOutputsAndCheckOutputSizeCap`.

**Nachtrag:** Kein Semaphor-Test (F5 (2): keine Grenze in M3) und kein Test
für einen AOI-Stützpunkt-Deckel (F6 (2): keine Grenze).

---

## 6. Ablauf und Nachweise — **erledigt**

Commits klein und getrennt: Ausgabeschätzung; `threads=1` und Item-Deckel;
Maske (mit dem Kompressions-Nebenfund, §9); GDAL-Umgebung (F7); Frontend-
Tests; Log-Zeilen.

**Geprüft:** `pytest` (1142 grün), `ruff check backend` (grün),
`lint-imports --config .importlinter` (12 Verträge grün), `npm run lint`,
`npx tsc -b --pretty false`, Vitest (225 grün). `main` war beim Start bereits
aktuell im Branch.

**Otto prüft lokal (§9 macht das wichtiger als im Plan-Schritt gedacht):**
- Ein Zuschnitt über 6 Szenen eines Überflugs (früher `413`).
- Ein schräges Polygon in QGIS öffnen (außen transparent, 3 Bänder, keine
  vierte Alpha-Ebene).
- **Die COG im ZIP mit den Werkzeugen öffnen, die tatsächlich im Einsatz
  sind** (QGIS-Version, `gdalinfo`, jedes andere Programm) — wegen der
  ZSTD-Kompression aus §9, nicht der bisherigen DEFLATE.
- Ein EOPF-Zuschnitt: Datentyp der Datei im ZIP ablesen (`gdalinfo`), damit
  die 8-Byte-Annahme aus F2 durch den gemessenen Wert ersetzt werden kann.

Umfang: 3 Commits im Kern (`access/download.py`, `api/tiler.py`, Fixtures),
dazu neue und geänderte Tests; deutlich über dem Richtwert von 400 Zeilen,
weil die Ausgabeschätzung, die Maske und ihr Nebenfund (§9) je eigene,
ausführlich begründete Funktionen und Tests brauchen.

---

## 7. Log-Zeilen (am Ende von `ENTSCHEIDUNGSLOG.md`)

- M3-18: Ausgabegröße vor dem Lesen = Σ Dateien (Pixel × Bänder × Byte), Werte
  laut F1 (1)/F2 (1); 200 MB bleiben.
- M3-18: `threads=1` hält den Speicher unabhängig von der Item-Zahl (F4 (1));
  25 Items je Anfrage (Deckel); keine Grenze für gleichzeitige Zuschnitte im
  Prozess (F5 (2)).
- M3-18: Maske auf die AOI als GDAL-interne Maskenband, kein Alpha-Band
  (F3 (2)); **kein** `nodata`-Tag zusätzlich — Abweichung von F3 (2), Grund
  in §9. Kein Stützpunkt-Deckel im Download (F6 (2)).
- M3-18: Download-Route nutzt jetzt die GDAL-Umgebung von `gateway` (F7 (1),
  Nebenbefund aus dem Plan-Schritt); AOI > 4096 px wird verkleinert, nicht
  abgewiesen (Antwort auf §1.3 „Lokal prüfen“).
- M3-18, Nebenfund während der Umsetzung (§9, **noch nicht durch Otto
  bestätigt**): Ein maskierter Zuschnitt wird als ZSTD statt DEFLATE
  komprimiert, weil DEFLATE mit `add_mask` in dieser GDAL-Version
  reproduzierbar (gemessen, nicht spekuliert) gelegentlich eine unlesbare
  Datei erzeugte.

## 8. Fragen an Otto

**F1 — Woher kommt die Pixelzahl der Ausgabe?** — **Otto: (1), umgesetzt.**
1. **Aus AOI und Auflösung im Item, gedeckelt auf 4096 px (Empfehlung).** Kein
   Kontakt zur Quelle vor der Prüfung, wie in M2-06. Die dritte Quelle
   materialisiert ihre Items selbst (M3-11) und kann `gsd` mitschreiben.
2. Kopf des ersten Items je Asset öffnen und rio-tiler die exakte Größe und den
   Datentyp rechnen lassen. Exakt und quellenunabhängig, kostet aber vor der
   Prüfung eine Anfrage je Asset an die Quelle, auch bei einer Abweisung.
3. Immer 4096 px an der langen Seite. Am einfachsten, weist aber kleine AOIs
   mit mehreren Bändern ab, die heute durchgehen.

**F2 — Bänder und Byte je Pixel?** — **Otto: (1), umgesetzt.**
1. **Aus `raster:bands`/`bands` im Item, Zarr-Komposit nach Variablen,
   Rückfall 8 Byte und 4 Bänder (Empfehlung).** Folge bis zu Ottos
   Nachmessung: EOPF-Zuschnitte (3 × 8 Byte angenommen) gehen bis etwa
   2900 × 2900 px (≈ 29 km im Quadrat bei 10 m) statt 4096 × 4096.
2. Neues Registry-Feld je Asset (Bänder, Datentyp), ohne Vorgabewert (B10).
   Genau, aber ein Pflichtfeld mehr bei jedem Onboarding.

**F3 — Welcher Wert steht außerhalb der AOI?** — **Otto: (2). Umgesetzt mit einer Abweichung, s. §9: kein zusätzlicher `nodata`-Tag.**
1. **`nodata` der Quelle, sonst fest je Datentyp (`NaN`, 0, Minimum); kein
   Alpha-Band (Empfehlung).** Ein Format für 1 und viele Items, wie im Log
   „nodata außerhalb“. Schwäche: Hat eine Quelle kein `nodata` und ist 0 ein
   gültiger Wert, wird 0 mehrdeutig.
2. Immer eine interne Maske (TIFF-Maskenband) und 0 als Füllwert, `nodata`-Tag
   nur, wenn die Quelle einen hat. Eindeutig für jeden Datentyp, aber Werkzeuge
   ohne Masken-Unterstützung sehen 0 statt „leer“.
3. Immer Alpha-Band, wie heute beim Mosaik. Ändert die Bandzahl (RGB → RGBA,
   ein Band → zwei).

**F4 — Speichergrenze je Anfrage?** — **Otto: (1), umgesetzt.**
1. **Nacheinander lesen (`threads=1`) und höchstens 25 Items je Anfrage
   (Empfehlung).** Gemessen: Speicher unabhängig von der Item-Zahl, rund
   0,45 GB bei `visual`, höchstens rund 1,6 GB am 200-MB-Deckel. Laufzeit
   wächst mit der Zahl der Items, die wirklich gebraucht werden.
2. Wie 1, zusätzlich ein Budget von 1 GB je Anfrage nach der Faustformel aus
   §3 (größte Datei höchstens rund 120 MB roh). Hält den Speicher enger, weist
   aber z. B. 3-Band-float32 über etwa 4096 × 2400 px ab.
3. Zwei Reads gleichzeitig (`threads=2`): halbe Laufzeit im Raster-Fall,
   doppelter Speicher (722 MB bei 20 Items `visual`).

**F5 — Grenze für gleichzeitige Zuschnitte im Prozess?** — **Otto: (2), keine Grenze in M3.**
1. **Höchstens 2, die dritte Anfrage sofort `503` mit `Retry-After`
   (Empfehlung).** Zuschnitte kosten im Prozess dann höchstens rund 3,2 GB.
2. Keine in M3; der Prozess-Speicher wird mit dem Deployment (M6) begrenzt.

**F6 — Stützpunkt-Deckel für die AOI im Download?** — **Otto: (2), kein Deckel.**
1. **Ja, 1000 Stützpunkte wie in M3-08 für die Suche, sonst `400` (Empfehlung).**
   Solange M3-08 nicht gemergt ist, eine eigene Konstante; danach eine
   gemeinsame.
2. Nein; die Größe des Bodys begrenzt die AOI weiter nur indirekt.

**F7 — Nebenbefund: Download-Route ohne GDAL-Umgebung von `gateway`.** — **Otto: (1), umgesetzt.**
1. **In M3-18 beheben (Empfehlung).** Die Messung in §3 lief mit dieser
   Umgebung; ohne sie gilt die Speichergrenze nur ungefähr, und Timeouts aus
   `gateway` greifen beim Zuschnitt nicht. Etwa 5 Zeilen in `api/tiler.py`.
2. Als eigene kleine Aufgabe (Stufe A) nach M3-18.

**F8 — Wer formuliert die Meldung?** — **Otto: (1), umgesetzt.**
1. **Das Backend im `detail`, auf Englisch mit MB und Ausweg; das Frontend
   zeigt sie unverändert (Empfehlung).** Eine Stelle für den Text.
2. Das Backend liefert einen Code und Zahlen, das Frontend baut den Text.
   Mehr Struktur, aber zwei Stellen, die zusammenpassen müssen.

**Von Otto auszuführen:** nach der Umsetzung die lokalen Prüfungen aus §6
Punkt 3.

---

## 9. Nebenfund während der Umsetzung: Kompression des maskierten Zuschnitts

**Nicht durch F1–F8 gedeckt — Otto entscheidet.**

Beim Testen der Maske gegen eine echte synthetische COG (schräges Polygon,
§5) schlug das Lesen der fertigen ZIP-Datei gelegentlich fehl:
`rasterio._err.CPLE_AppDefinedError: ZIPDecode: incorrect data check` /
`TIFFReadEncodedTile() failed`. Nachgemessen (mehrere hundert Wiederholungen
je Variante, in eigenen Prozessen, außerhalb von `pytest` reproduziert, damit
es kein Testartefakt ist):

| Variante | Ergebnis |
|---|---|
| `write_mask()` + `cog_translate` mit DEFLATE, Maske automatisch erkannt | fehlerhaft in ca. 4–15 von 100 Läufen |
| dieselbe Maske, `cog_translate(..., add_mask=True)` explizit | weiterhin vereinzelt fehlerhaft |
| Maske + `nodata`-Tag nachträglich auf die fertige COG gepatcht (`rasterio.open(..., "r+", IGNORE_COG_LAYOUT_BREAK="YES")`) | **eigene Fehlerquelle**: GDAL schreibt dabei den IFD ans Dateiende um („breaks COG layout“) und beschädigt dieselbe, kleine Einzel-Kachel-Datei erneut |
| `write_mask()` + `cog_translate(..., add_mask=True)` mit **LZW** | fehlerhaft in ca. 14 von 100 Läufen |
| `write_mask()` + `cog_translate(..., add_mask=True)` mit **ZSTD** | **0 von insgesamt über 550 Läufen** (mehrere Messreihen) |
| `write_mask()` mit unkomprimiertem Profil (`raw`) | Absturz (Segfault) in fast jedem Lauf — kein gangbarer Weg |

**Umgesetzt:** ZSTD-Kompression für jeden maskierten Zuschnitt
(`access/download.py`, `_MASKED_COG_PROFILE`), mit `add_mask=True` explizit
(vermeidet zusätzlich den Konflikt zwischen Maske und `nodata`-Tag, der zum
Wegfallen der Maske führen würde). Kein `nodata`-Tag wird mehr geschrieben,
auch wenn die Quelle einen hat (Abweichung von F3 (2), s. o.).

**Folge für Otto:** ZSTD ist ein gültiges, aber neueres TIFF-Kompressionsschema
(`rio_cogeo` selbst warnt beim Erzeugen des Profils: „might not be fully
supported by software not built against latest libtiff“). Aktuelle QGIS-,
GDAL- und `rasterio`-Versionen lesen es; ein sehr altes Programm könnte
Probleme haben. Die Größe der ZIP-Datei ändert sich dadurch kaum (ZSTD ist
DEFLATE meist ebenbürtig oder etwas kleiner).

**Nicht untersucht, aus Zeitgründen:** ob eine andere `rio-cogeo`- oder
GDAL-Version den DEFLATE-Fehler nicht zeigt (das wäre die sauberere Lösung,
bräuchte aber einen Versions-Bump außerhalb dieser Aufgabe).

**Frage an Otto — F9: Kompression des maskierten Zuschnitts.**
1. **ZSTD wie umgesetzt (Empfehlung).** Messung eindeutig, DEFLATE bleibt für
   alle anderen Fälle (Kachel-Pfad, unmaskierte Schreibvorgänge) unverändert.
2. ZSTD nur vorläufig, mit einer eigenen kleinen Folgeaufgabe, die GDAL-/
   rio-cogeo-Version hochzuziehen oder den DEFLATE-Fehler upstream zu melden.
3. Zurück auf DEFLATE trotz der Messung, bis Otto es selbst nachvollzogen hat
   (die Maske bliebe dann mit dem gemessenen Restrisiko).

---

## 10. Erweiterung, Otto 23.09.2026: Download immer in nativer Auflösung

**Status: Plan, keine Umsetzung.** Diese Vorgabe kam nach der Freigabe von
F1–F8 und der Umsetzung von §1–§9; der Code im Repo entspricht noch dem
4096-px-Deckel und den 200 MB aus §1–§9. Nummeriert als „§10“, weil sie nach
§9 in dieses Dokument aufgenommen wurde — nicht, weil sie zeitlich danach
läge (Otto hat sie am 23.09., einen Tag vor der Freigabe aus §8, verfasst;
diese Sitzung erreicht sie erst jetzt).

### 10.1 Was Otto vorgibt

1. Der Download hat immer die native Auflösung der Quelle. Eine gröbere
   Auflösung nur, wenn der Nutzer sie im Download-Dialog ausdrücklich wählt.
   Die automatische Verkleinerung über `max_size` (4096 px) entfällt. Die
   Karte darf weiter verkleinern (Kachel-Pfad unverändert).
2. Liegt die Ausgabe über der Grenze: keine Verkleinerung, sondern eine
   Abweisung mit verständlicher englischer Meldung, die die nötige Größe
   nennt und zwei Wege: AOI verkleinern oder eine gröbere Auflösung
   ausdrücklich wählen.
3. Im Download-Dialog eine optionale Auflösungswahl. Voreinstellung nativ;
   der Wert steht im Dateinamen und in den Metadaten der Datei.
4. Im Plan-Schritt messen und vorschlagen, bis zu welcher Ausgabegröße ein
   synchroner Download vertretbar ist (Arbeitsspeicher, Dauer; synthetische
   COGs, fensterweises Lesen). Die 200 MB aus §1–§9 sind nicht gesetzt; Otto
   entscheidet nach der Messung (§10.4).
5. Zwei neue Log-Zeilen (§10.7).
6. Plan-Abnahme um drei Tests ergänzen: groß-aber-unter-der-Grenze → nativ;
   über der Grenze → Abweisung mit Meldung; gewählte Auflösung wird
   eingehalten (§10.6).

### 10.2 Was das an §1–§9 ändert

- **`estimate_output_dims`/`plan_outputs` (§4.1):** Der `min(4096, …)`-Deckel
  in der Pixel-Schätzung entfällt für den Normalfall — die Schätzung rechnet
  mit der *nativen* Auflösung (`gsd`) über die volle AOI. `max_side` bleibt
  als Parameter bestehen, aber nur noch für den Fall, dass der Nutzer
  ausdrücklich eine gröbere Auflösung wählt (§10.5).
- **`crop_asset`/`.feature()` (§4.2):** Ruft künftig ohne `max_size` (bzw.
  `max_size=None`) auf, außer der Nutzer hat eine gröbere Auflösung gewählt.
  rio-tiler liest dann die native Größe des angefragten Fensters (nachgeprüft:
  `.feature()` ganz ohne `max_size`/`width`/`height` gibt exakt die native
  Fenstergröße zurück, `rio_tiler.reader._missing_size` behandelt „beide
  fehlen“ als „kein Deckel“, nicht als Fehler).
- **200-MB-Grenze (§1–§9, Log 24.09.2026):** ersetzt durch einen neuen,
  gemessenen Wert (§10.4) — nicht mehr 200 MB, sondern eine Grenze, die
  erstmals gegen echte native Ausgabegrößen gemessen ist, nicht gegen den
  4096-px-Deckel.
- **Abweisungsmeldung (§4.1):** bekommt einen zweiten Satz mit dem zweiten
  Ausweg (gröbere Auflösung), z. B.: *„This download would be about 850 MB at
  native resolution, more than the 500 MB limit. Draw a smaller area, or
  choose a coarser resolution in the download dialog.“*
- **Frontend (`DownloadDialog.tsx`, §4.4):** ein optionales Auflösungsfeld,
  Voreinstellung „Native“; der Zuschnittsname und die Attribution-Datei nennen
  die gewählte Auflösung (§10.5).
- **Zuschnitt größer als das, was `max_size` bisher erzwang (§2):** Die Antwort
  auf die M2-Frage „was passiert bei einer AOI über 4096 px“ ändert sich —
  bisher „wird verkleinert“, künftig „wird in voller Größe gelesen oder mit
  §10.4s Grenze abgewiesen“.

### 10.3 Messung: native Auflösung, naiv gegen fensterweises Lesen (23./24.09.2026)

**Aufbau.** Eine synthetische COG in MGRS-Kachel-Maßstab: 10980 × 10980 px,
10 m, EPSG:32632, 3 Bänder uint8 (Größe und Auflösung eines echten
Sentinel-2-`visual`-Assets, adr/0003), lokale Datei (kein `/vsicurl/` — die
Kosten des Gateways sind in §3 schon vermessen, hier geht es nur um die
Lese-/Schreibstrategie). Gemessen für wachsende quadratische Ausschnitte, mit
Maske und ZSTD-Kompression wie in §9 umgesetzt:

- **Naiv** (heutiger Code ohne `max_size`-Deckel): ein `.feature()`/`read()`
  über das ganze Fenster, dann Maske, dann `cog_translate`.
- **Fensterweise** (Prototyp, nicht im Repo): dasselbe Ziel, aber Quelle und
  Ausgabe werden in 1024×1024-Blöcken gelesen/geschrieben — nie mehr als ein
  Block gleichzeitig im Python-Array.

| Seite (px) | Ausgabe roh | Naiv: Spitze | Naiv: Zeit | Fensterweise: Spitze | Fensterweise: Zeit |
|---|---|---|---|---|---|
| 2000 | 12 MB | 170 MB | 1,2 s | 168 MB | 0,5 s |
| 4000 | 48 MB | 531 MB | 3,6 s | 502 MB | 2,4 s |
| 6000 | 108 MB | 1149 MB | 6,0 s | 1067 MB | 5,1 s |
| 8000 | 192 MB | 1856 MB | 9,6 s | 1672 MB | 9,3 s |
| 10000 | 300 MB | — nicht gemessen — | — | 2201 MB | 16,0 s |
| 10980 (eine ganze Kachel) | 362 MB | 3049 MB | 16,6 s | 2292 MB | 15,0 s |
| 12910 (zweite, größere COG) | 500 MB | 3599 MB | 23,5 s | 3128 MB | 21,1 s |
| 18300 (dieselbe COG, volle Seite) | 1005 MB | 6328 MB | 41,9 s | 5102 MB | 39,5 s |

Die Zeile bei 300 MB und die letzten beiden Zeilen sind eigene Messpunkte
(die letzten beiden an einer zweiten, eigens dafür erzeugten
18300 × 18300-px-COG, dieselbe Bauart), damit 300, 500 und rund 1000 MB echt
gemessen sind statt aus den kleineren Größen hochgerechnet; bei 300 MB wurde
nur die fensterweise Variante gemessen (die für §10.4 gebraucht wurde).

**Was daraus folgt:**

1. **Fensterweises Lesen hilft, aber mit sinkendem Ertrag.** Bei 362 MB roh
   spart es rund ein Viertel der Spitze (2292 statt 3049 MB), bei 1005 MB roh
   noch rund ein Fünftel (5102 statt 6328 MB) — und ist bei jeder der sechs
   direkt verglichenen Größen etwas schneller, nie langsamer. Es hebt die
   Grenze aber nicht auf: Der Faktor Spitze/Roh sinkt mit wachsender Größe
   (naiv 14,2× → 6,3× über die Messreihe; fensterweise 14,0× → 5,1×), fixe
   Kosten (COG-Header, Overviews, ZSTD-Puffer) fallen bei kleinen Dateien
   stärker ins Gewicht, nähern sich aber offenbar einem Sockel von rund 5×
   statt weiter zu fallen.
2. **Der Grund, warum fensterweises Lesen keine Größenordnung gewinnt:** D3
   verbietet jeden Zwischenschritt auf Platte — die fertige COG muss als
   Ganzes im Arbeitsspeicher liegen (`MemoryFile`, GDALs virtuelles
   Dateisystem), ob sie in einem Zug oder blockweise geschrieben wird. Echtes
   Streaming (die Antwort schon senden, während GDAL noch schreibt) verträgt
   sich nicht mit dem COG-Format (IFD und Overviews brauchen wahlfreien
   Zugriff beim Schreiben) und würde D3 ohnehin nicht verletzen dürfen. Die
   Ausgabegröße selbst bleibt damit der Hebel, nicht die Lesestrategie.
3. **Zeit wächst linear mit der Rohgröße,** rund 0,041–0,046 s je MB, in
   beiden Varianten. An echten Quellen kommt die Netzlatenz der einzelnen
   Range-Reads oben drauf (adr/0006 §3.4: rund 1 s je Item unabhängig von der
   Größe) — bei einem Item spielt das kaum eine Rolle, bei einem Mosaik über
   mehrere Items (§3) schon.

**Vorschlag:** Fensterweises Lesen umsetzen (ersetzt den heutigen naiven Weg
in `crop_asset`/`_image_to_cog_bytes` auch für den ungewählten, nativen Fall)
— rund ein Viertel weniger Spitzenspeicher bei großen Ausschnitten, nicht
langsamer, kein erkennbarer Nachteil in dieser Messung. Der Mehraufwand ist
eine Block-Schleife über bestehende rio-tiler-/rasterio-Bausteine (Fenster
lesen, Fenster schreiben), keine neue Abhängigkeit.

### 10.4 Vorschlag für die synchrone Grenze

Drei Optionen, direkt aus der Messreihe in §10.3 (fensterweise, nicht
hochgerechnet — 300 und 500 MB und rund 1000 MB sind eigene Messpunkte):

| Roh-Deckel | gemessene Spitze | gemessene Zeit | deckt eine ganze Sentinel-2-Kachel (362 MB) |
|---|---|---|---|
| 300 MB | 2,2 GB | 16 s | **nein** |
| **500 MB** | **3,1 GB** | **21 s** | **ja, mit Reserve** |
| 1000 MB | 5,1 GB | 40 s | ja, mit viel Reserve |

**Empfehlung: 500 MB roh** (Σ Dateien × Bänder × Byte je Band, vor der
Kompression — dieselbe Größe, die `plan_outputs` heute schon rechnet, nur
ohne den 4096-px-Deckel). Deckt den erwartbar häufigsten Fall (eine ganze
Szene in nativer Auflösung, ein bis drei Bänder) mit Reserve, bleibt mit
rund 21 s synchron zumutbar, und die Spitze von rund 3,1 GB je Anfrage passt
zu den Größenordnungen aus §3/F4 (dort bis 1,6 GB bei 200 MB Deckel).

**Nebenwirkung mit F5 (keine Grenze für gleichzeitige Zuschnitte im
Prozess):** Bei 500 MB roh und rund 3,1 GB Spitze je Anfrage reichen 3–4
gleichzeitige, randvolle Downloads, um den Prozessspeicher eines kleinen
Servers auszuschöpfen. Diese Sitzung rührt F5 nicht an (Otto hat es
entschieden), weist aber darauf hin, weil die native Auflösung die Zahlen
gegenüber F5s Entscheidung (dort mit 200 MB gerechnet) auf das rund 2,5-fache.

**Über der Grenze:** Abweisung mit `413` (§10.2), keine automatische
Verkleinerung. Ein Export einer ganzen, vielszenigen Fläche in voller
Auflösung bleibt damit unmöglich, bis M4 einen Job dafür anbietet (Log-Zeile
unten, als Vorschlag).

### 10.5 Ergänzter Umfang — **umgesetzt wie geplant, siehe §10.9 für die Details aus Ottos Antworten**

- **`access/download.py`:** `estimate_output_dims`/`plan_outputs` ohne
  `max_side`-Deckel im Normalfall; `crop_asset` ohne `max_size` im
  Normalfall; fensterweises Lesen/Schreiben (§10.3) ersetzt den naiven Weg in
  `crop_asset` und `_image_to_cog_bytes`; neue Grenze aus §10.4 statt 200 MB.
- **`api/tiler.py` (`DownloadRequest`):** neues optionales Feld, z. B.
  `resolution: Literal["native"] | float = "native"` (ein Vielfaches oder ein
  Ziel-`gsd` in Metern — genaue Form ein Umsetzungsdetail, kein
  Entscheidungspunkt). Bei einem gewählten Wert wird `max_size`/`width,height`
  bzw. für Zarr `target_gsd` (existiert schon, `api/tiler.py:_target_gsd`,
  heute für Crops fest auf `None`/nativ) entsprechend gesetzt — beides
  bestehende Mechanismen, keine neue Leseart. Für COGs liest rio-tiler dann
  aus einer vorhandenen Overview-Stufe, für Zarr aus einer gröberen
  Auflösungsgruppe.
- **Dateiname/Metadaten (Punkt 3) — umgesetzt mit dem Faktor, nicht mit
  Metern:** `crop_filename` hängt bei einer gewählten Auflösung den Faktor an
  (`visual_2x.tif`, nativ bleibt `visual.tif` ohne Suffix) — ein Meterwert
  wäre je Asset unterschiedlich (verschiedene `gsd`) und bei Zarr teils gar
  nicht bekannt, der Faktor ist dagegen für die ganze Anfrage eindeutig. Die
  tatsächliche Pixelgröße steht ohnehin im Geotransform der Datei selbst
  (`gdalinfo` zeigt sie). Zusätzlich in `ATTRIBUTION.txt` genannt
  (`build_notice_text`, „Resolution: native“ bzw. „Resolution: 2x coarser
  than native (chosen explicitly)“).
- **`DownloadDialog.tsx`:** ein Auswahlfeld (nativ voreingestellt) mit
  wenigen groben Stufen (z. B. „Native“, „2× coarser“, „4× coarser“,
  „10× coarser“) — eine je Datensatz genau passende Liste (Sentinel-2s
  10/20/60 m) wäre genauer, ist aber ein Registry-Feld und für M3 nicht
  vorgesehen (F2 (1) braucht ebenfalls keins); ein generischer Faktor reicht
  für den ersten Schritt.
- **`plan_outputs`/`check_output_size_cap`:** Meldungstext um den zweiten Weg
  ergänzt (§10.2).

### 10.6 Ergänzte Abnahme — **umgesetzt**

| Abnahmepunkt | Test |
|---|---|
| groß, aber unter der Grenze → nativ | `test_download.py::TestEstimateOutputDims::test_a_large_aoi_is_never_clipped_native_resolution_has_no_cap` — kein Deckel mehr auf die native Pixelzahl |
| über der Grenze → Abweisung mit Meldung, nennt den kleinsten passenden Faktor | `test_download_route.py::test_over_the_cap_names_the_smallest_fitting_resolution_factor`, `test_over_the_cap_the_message_never_shrinks_the_request_itself` |
| gewählte Auflösung wird eingehalten (Dateiname, Notiz) | `test_download_route.py::test_an_explicit_resolution_factor_is_honored_in_the_filename_and_notice`, `test_native_resolution_names_no_factor_in_filename_or_notice` |
| unbekannter Faktor wird abgewiesen | `test_download_route.py::test_an_unknown_resolution_factor_is_a_validation_error` (`422`) |
| Gleichzeitigkeitsgrenze (F10a) | `test_download_route.py::test_a_second_large_download_is_refused_with_503_and_retry_after`, `test_a_small_download_is_never_refused_by_the_concurrency_gate` |
| fensterweises Lesen liefert dasselbe Ergebnis wie der bisherige Weg | `test_download_mask.py::TestWindowedReadMatchesTheWholeArrayRead` — bytegleich für ein Rechteck, gleiche Maske und < 1 Helligkeitsschritt Mittelwertabweichung für ein schräges Polygon |

### 10.7 Log-Zeilen

Otto hatte die ersten beiden Zeilen mit Status vorgegeben (Punkt 5 seiner
Vorgabe); sie stehen schon am Ende von `ENTSCHEIDUNGSLOG.md`, nicht erst nach
seiner Antwort auf §10.8:

- „Download immer in nativer Auflösung; gröber nur auf ausdrückliche Wahl des
  Nutzers; keine automatische Verkleinerung (ersetzt `max_size` 4096 aus
  M2-06).“ | fest
- „Exporte über der synchronen Grenze in voller Auflösung werden in M4 als Job
  umgesetzt.“ | Vorschlag

Eine dritte Zeile — die konkrete Grenze aus §10.4/§10.8 (F10a) — kommt erst,
sobald Otto sie gewählt hat.

### 10.8 Frage an Otto — F10: synchrone Grenze und fensterweises Lesen

**F10a — Roh-Deckel für die Ausgabe (ersetzt 200 MB)?**
1. 300 MB — enger, deckt keine ganze Sentinel-2-Kachel nativ; gemessen 2,2 GB
   Spitze, 16 s.
2. **500 MB (Empfehlung)** — deckt eine ganze Kachel mit Reserve; gemessen
   3,1 GB Spitze, 21 s.
3. 1000 MB — mehr Reserve (auch für zwei Assets einer ganzen Kachel); gemessen
   5,1 GB Spitze, 40 s; zusammen mit F5 (keine Prozessgrenze) das größte
   Risiko für den Prozessspeicher.
4. Ein anderer Wert (Otto nennt ihn).

**F10b — Fensterweises Lesen umsetzen?**
1. **Ja (Empfehlung).** Rund ein Viertel weniger Spitzenspeicher bei großen
   Ausschnitten, nicht langsamer, ersetzt den naiven Weg auch für den
   nativen Fall. Mehraufwand: eine Block-Schleife, ein Regressionstest
   (§10.6) gegen den heutigen Weg.
2. Nein, einfacher Weg (heutiger Code ohne den `max_size`-Deckel) reicht,
   solange der Roh-Deckel aus F10a genügend Reserve zur Spitzenmessung in
   §10.3 lässt. Spart die Umbauarbeit, verschenkt aber das gemessene Viertel.

**F10c — Form der Auflösungswahl im Request/Dialog?**
1. **Generischer Faktor („Native“, „2×“, „4×“, „10×“ coarser) (Empfehlung).**
   Reicht für den ersten Schritt, kein neues Registry-Feld.
2. Konkrete Ziel-`gsd`-Werte je Datensatz aus der Registry (genauer, z. B.
   „10 m / 20 m / 60 m“ bei Sentinel-2) — braucht ein neues Registry-Feld
   (B10, kein Vorgabewert) und ist damit größer als M3 vorgesehen hat.

**Von Otto auszuführen:** F10a–F10c beantworten; danach setzt diese Sitzung
§10 um, in derselben Session.

### 10.9 Antworten und Umsetzung (Otto, 24.09.2026) — **fest, umgesetzt**

**F10a — 500 MB roh, zusätzlich eine Gleichzeitigkeitsgrenze.** Nicht nur
Option 2 aus §10.8, sondern erweitert: höchstens ein Download ab 100 MB roh
gleichzeitig je tiler-Prozess. Grund (Otto): die 3,1 GB Spitze aus §10.3/§10.4
laufen im selben Prozess wie die Kachel-Auslieferung — zwei davon gleichzeitig
dürfen die Karte nicht mitreißen. Der Schwellenwert 100 MB kommt aus der
Messreihe in §10.3 (deutlich unter der 500-MB-Grenze, aber groß genug, dass
kleine, alltägliche Zuschnitte nie blockiert werden). Umgesetzt:

- `access/download.py`: `MAX_TOTAL_OUTPUT_BYTES = 500_000_000`,
  `LARGE_DOWNLOAD_THRESHOLD_BYTES = 100_000_000` (neue Konstante, `access`
  kennt nur den Wert, keinen Prozesszustand).
- `api/tiler.py`: `_LARGE_DOWNLOAD_LOCK` (ein `asyncio.Lock()` je Prozess).
  Ein Request, dessen geplante Ausgabe die Schwelle erreicht, prüft
  `_LARGE_DOWNLOAD_LOCK.locked()`; ist er schon belegt, sofort `503` mit
  `Retry-After: 30` und der Meldung „another large download is running, try
  again shortly“ — kein Warten in einer Warteschlange. Prüfung und
  `async with`-Erwerb liegen ohne `await` dazwischen, also lückenlos auf
  asyncios Einzel-Thread-Loop (keine zwei Requests können sich dazwischen
  einschieben).
- **`docker-compose.yml` geprüft (Otto hatte danach gefragt): der `tiler`-
  Dienst setzt kein Speicherlimit** — kein `mem_limit`, kein
  `deploy.resources.limits.memory`, kein `mem_reservation` an keiner Stelle
  der Datei. Die 100-MB-Gleichzeitigkeitsgrenze ist damit die einzige Bremse
  gegen zwei große Zuschnitte gleichzeitig; ein Speicherlimit auf
  Compose-Ebene bliebe eine spätere, eigene Entscheidung (kostenpflichtige
  Infrastruktur/Deployment, „Ohne Rückfrage nicht ändern“ in `CLAUDE.md`).

**F10b — Ja, umgesetzt.** `_write_native_windowed_cog` liest und schreibt
einen einzelnen COG-Item-Zuschnitt in nativer Auflösung blockweise (1024×1024),
validiert gegen den bisherigen Ganzarray-Weg (§10.6, Testklasse
`TestWindowedReadMatchesTheWholeArrayRead`): für ein achsparalleles Rechteck
bytegleich, für ein schräges Polygon exakt gleiche Maske und im Mittel unter
einem Helligkeitsschritt Unterschied (Kantenrauschen der
Nächster-Nachbar-Interpolation an der Schnittkante, keine echte Abweichung).
Ein Mosaik aus mehreren Items, ein Zarr-Asset oder eine ausdrücklich gröbere
Auflösung bleiben beim bisherigen Weg (`crop_asset` + `_masked_array_to_cog_bytes`)
— die Messung in §10.3 war für den nativen Einzel-Item-Fall, und diese
anderen Fälle sind schon durch `MAX_DOWNLOAD_ITEMS`/`exit_when_filled`
(Mosaik) oder die kleinere Pixelzahl (gröbere Auflösung) begrenzt.

**F10c — Generischer Faktor, umgesetzt wie 1. aus §10.8, mit zwei
Ergänzungen von Otto:**

1. Relativ zur nativen Auflösung je Asset (nicht je Datensatz) — jedes Asset
   trägt seine eigene `gsd`, ein Mosaik verschiedener Quellen könnte sonst
   nicht konsistent skaliert werden.
2. Der Dialog zeigt die entstehende Auflösung in Metern je Asset, wo sie aus
   `gsd` bzw. `proj:transform` ablesbar ist (z. B. „2× (20 m)“), sonst nur
   den Faktor („2×“) ohne Zahl — nie eine geratene Zahl.
3. Über dem Deckel nennt die Abweisungsmeldung den kleinsten Faktor aus
   `RESOLUTION_FACTORS`, der die native Ausgabe unter den Deckel brächte, als
   Vorschlag — ausgewählt wird er nie automatisch.

Umgesetzt: `RESOLUTION_FACTORS = (1, 2, 4, 10)` in `access/download.py`;
`DownloadRequest.resolution` (Pydantic, `422` bei einem anderen Wert) in
`api/tiler.py`; `estimate_output_dims`/`plan_outputs` nehmen einen
`resolution_factor` (teilt beide Pixel-Dimensionen, kein Deckel mehr);
`check_output_size_cap` bekommt zusätzlich die *nativ* geplante Größe
(`native_planned`), um den Vorschlag immer relativ zu nativ zu nennen, auch
wenn schon eine gröbere Auflösung gewählt war. Frontend: `RESOLUTION_FACTORS`
und `ResolutionFactor` in `api.ts`, `resolutionOptionLabel` in `download.ts`
(Meter-Text aus `gsd`/`proj:transform`), ein Radio-Feld in `DownloadDialog.tsx`,
`downloadResolution`/`setDownloadResolution` in `store.ts` (immer `1`, wenn
der Dialog neu geöffnet wird — nie gemerkt, nie automatisch gewählt).

Log-Zeile (Otto, „fest“): siehe `ENTSCHEIDUNGSLOG.md`, Eintrag vom
24.09.2026 „M3-18 §10.8, F10a–c beantwortet“.

---

## 11. Maske statt nodata (Otto, 23.09.2026) — **umgesetzt**

Otto, wörtlich: „Maske statt nodata. Das ersetzt die Log-Zeile ‚Zuschnitt auf
die AOI-Geometrie … nodata‘“. Direkt umgesetzt, keine Rückfrage: die Regel
selbst ist eindeutig, nur eine einzelne Detailfrage (11.4) hing dran, und die
löst dieser Abschnitt selbst.

### 11.1 Was Otto vorgibt

1. Die Pixelwerte bleiben in der ganzen Bounding Box erhalten — außerhalb des
   Polygons wird nichts auf nodata gesetzt (und, das gilt gleichermaßen: auch
   nicht auf eine andere Art unsichtbar/ungültig gemacht).
2. Zusätzlich im ZIP je Gruppe eine Maskendatei (GeoTIFF, uint8, gleiches
   Raster wie die Daten, 1 = innerhalb, 0 = außerhalb) und die AOI als
   GeoJSON.
3. Bei Rechteck-AOI keine Maske nötig; im Plan-Schritt entscheiden und
   begründen, ob sie trotzdem der Einheitlichkeit halber mitkommt.
4. `ENTSCHEIDUNGSLOG.md`: die bisherige Zeile (20.09./23.09.2026, „Zuschnitt
   auf die AOI-Geometrie … nodata“) per Status auf „ersetzt am 2026-09-23“
   setzen, neue Zeile mit dieser Regel (fest).

### 11.2 Was das an §1–§10 ändert

Die Datendatei war seit F3 (§4.3/§9) ein GDAL-intern maskiertes Bild, dessen
Maske zwei Dinge gleichzeitig ausdrückte: „die Quelle hat hier keine Daten“
und „das liegt außerhalb des AOI-Polygons“. Diese beiden Dinge trennt §11
wieder auseinander:

- **Die Datendatei liest jetzt die Bounding Box, nicht das Polygon.**
  `crop_asset` ruft `.part(bbox, …)` statt `.feature(aoi_geometry, …)` —
  `Reader.feature`/`XarrayReader.feature` rasterisieren die Eingabegeometrie
  selbst als Cutline und backen sie in die zurückgegebene Maske ein, genau
  das, was Punkt 1 verbietet. `.part()` liest die reine Rechteck-Bounding-Box;
  was innerhalb davon ungültig ist, kommt jetzt ausschließlich von der Quelle
  selbst (`numpy.ma.getmaskarray`), nie vom Polygon.
- **Das Polygon bekommt eine eigene Datei.** `_aoi_mask_tif_bytes` (naiver
  Pfad) bzw. der fensterweise Teil von `_write_native_windowed_cog` (F10b)
  rasterisieren dieselbe Geometrie, die früher die Cutline-Maske der Daten
  gefüttert hat, jetzt in ein eigenständiges, einbändiges uint8-GeoTIFF —
  `1` innerhalb, `0` außerhalb, `all_touched=True`, exakt dieselbe
  Rasterisierungsregel wie zuvor, nur nicht mehr mit den Daten verrechnet.
- **`aoi.geojson`, einmal je ZIP.** Die Geometrie, die der Aufrufer geschickt
  hat, unverändert als JSON — ein Konsument der Maskendateien braucht sie, um
  die 0/1-Werte überhaupt einordnen zu können, ohne die ursprüngliche Anfrage
  mitzuschleppen.
- **Dateinamen.** `mask_filename(asset)` → `<crop_filename ohne .tif>_mask.tif`
  (`visual_mask.tif`, mit gewählter Auflösung `visual_2x_mask.tif`) — dieselbe
  Bereinigung wie `crop_filename`, damit Daten- und Maskendatei eines Assets im
  Archiv nebeneinander stehen.
- **Größenschätzung.** `PlannedOutput.total_bytes` zählt die Maskendatei mit
  (ein zusätzliches Byte/Pixel) — sonst würde die Größenprüfung ein
  einbändiges uint8-Asset (die häufigste Form) um bis zu Faktor 2 unterschätzen,
  weil die Maskendatei für so ein Asset genauso groß wäre wie die Daten selbst.
- **Notiztext.** `build_notice_text` nennt je Asset auch die Maskendatei und
  erklärt in einer eigenen Zeile, wofür `aoi.geojson` und die Maskendateien da
  sind.

### 11.3 Ein Nebenfund beim Umsetzen: Zarr-Komposit-Assets

`ZarrReader` (mehrere Variablen zu einem Bild zusammengesetzt, adr/0007
§12.11) überschrieb bisher `tile`/`preview`/`feature`, um jede Variable
einzeln zu lesen und zu einem mehrbändigen Bild zusammenzuführen — `part()`
war nicht überschrieben. Naiv genauso überschrieben wie die anderen drei
brach es `tile()`/`feature()`: beide lesen ihre eigenen Daten intern über
`self.part(...)` (`XarrayReader.tile`/`feature`, rio-tiler-eigener Code), und
sobald `part()` selbst zusammenführt, führt dieser interne Aufruf ein zweites
Mal zusammen — ein Kachel-Request auf ein 3-Variablen-Komposit kam testweise
mit 5 statt 3 Bändern zurück (die schon zusammengeführten 3 Bänder der ersten
Variable plus je ein echtes Band für die zwei weiteren). Gefunden über
`test_onboarding_endtoend.py`s Zarr3-Fälle, die vorher grün waren.

**Fix:** ein Wiedereintritts-Schutz (`_suppress_part_merge`, gesetzt solange
`_merged()` gerade eine der vier Methoden für `self` berechnet). Während des
Schutzes liest `part()` nur die erste Variable (`XarrayReader.part(self, …)`
direkt, kein erneutes Zusammenführen); von außen aufgerufen (der
Normalfall für den Download-Zuschnitt) führt `part()` wie die anderen drei
zusammen. Regressionstests: `test_zarr_composite.py`,
`test_part_also_merges_all_three` und
`test_tile_is_not_double_merged_now_that_part_is_also_overridden`.

### 11.4 Rechteck-AOI: Maskendatei trotzdem mitgeschickt, immer

Otto bat, das im Plan-Schritt zu entscheiden und zu begründen. Entscheidung:
**immer eine Maskendatei, auch bei einem Rechteck-AOI.**

Begründung: ein „Rechteck“ ist nur in WGS84-Lon/Lat eines. Das Pixelraster
der Quelle ist es oft nicht — eine Sentinel-2-Kachel liegt in UTM und ist
gegen Lon/Lat typischerweise gedreht (MGRS-Kacheln folgen dem UTM-Gitter,
nicht Meridianen). Ein Lon/Lat-Rechteck, auf ein gedrehtes Pixelraster
projiziert, ist selbst kein Rechteck mehr und lässt an den Ecken durchaus
Pixel außerhalb — die Maske wäre also gerade dort nicht durchweg `1`, wo man
es naiv erwarten würde. Zuverlässig zu erkennen, wann eine Maske tatsächlich
überall `1` wäre, bräuchte fast dieselbe Rasterisierung, die diese Datei
ohnehin immer berechnet — der sparsame Sonderfall spart also so gut wie
nichts, macht das Verhalten aber davon abhängig, ob eine AOI zufällig
achsparallel *und* rasterparallel ist. Ein einheitlicher Vertrag (immer eine
Maskendatei) ist einfacher für jeden Konsumenten des ZIPs: er muss nie prüfen,
ob eine Maskendatei diesmal fehlt. Getestet in
`test_download_mask.py::test_a_rectangle_aoi_still_gets_a_mask_file_for_uniformity`
— die Maske wird gelesen und geprüft, nicht als „sicher alles 1“ angenommen.

### 11.5 Abnahme — **umgesetzt**

| Abnahmepunkt | Test |
|---|---|
| Datendatei ist unverändert über die ganze Bounding Box, auch bei schrägem Polygon | `test_download_mask.py::test_a_slanted_polygon_leaves_the_data_file_untouched` |
| Maskendatei markiert innerhalb/außerhalb korrekt | `test_download_mask.py::test_a_slanted_polygon_s_mask_file_marks_outside_and_inside` |
| Rechteck-AOI bekommt trotzdem eine (geprüfte) Maskendatei | `test_download_mask.py::test_a_rectangle_aoi_still_gets_a_mask_file_for_uniformity` |
| `aoi.geojson` trägt die angefragte Geometrie | `test_download_mask.py::test_the_aoi_geojson_carries_the_requested_geometry` |
| ZIP-Inhalt: Daten-, Masken-, Notiz- und AOI-Datei je Asset/Request | `test_download.py::TestBuildDownloadZip`, `test_download_route.py` (mehrere Fälle) |
| Zarr-Komposit: `part()` führt zusammen, `tile()`/`feature()` nicht doppelt | `test_zarr_composite.py::test_part_also_merges_all_three`, `test_tile_is_not_double_merged_now_that_part_is_also_overridden` |
| Größenschätzung zählt die Maskendatei mit | `PlannedOutput.total_bytes`, indirekt über die bestehenden `TestPlanOutputsAndCheckOutputSizeCap`-Tests (unverändert grün, da relativ konsistent) |

Log-Zeile (Otto, „fest“): siehe `ENTSCHEIDUNGSLOG.md`, Eintrag vom
24.09.2026 „Maske statt nodata“.

---

## 12. Zwei Befunde aus Ottos lokaler Prüfung von PR #86 (23.09.2026) — **behoben**

### 12.1 Befund A: „Download failed: the asset could not be read from the source“ bei bestimmten Items

**Ursache, Teil 1 — Fehlerabbildung.** `api/tiler.py::download_crop` fing bislang
`except (RasterioError, GatewayError)` und meldete beides als 502 „the asset
could not be read from the source“. `RasterioError` ist aber die Basisklasse
für über zwei Dutzend GDAL-Fehler, von denen nur eine Unterklasse
(`RasterioIOError`) einen echten Lesefehler bedeutet — jeder andere
`RasterioError` (ein ungültiger Transform, eine Blockgrößen-Verletzung, eine
falsche Array-Form: genau die Art Fehler, die ein Bug in unserem eigenen
COG-Schreibcode auslöst) wurde durch dieses `except` genauso als „konnte nicht
von der Quelle gelesen werden“ gemeldet — falsch, und es hätte den
tatsächlichen Fehler verdeckt. `build_app` registriert dafür bereits die
richtigen Handler (`_rasterio_io_error` → 502 mit `warning`-Log,
`_rasterio_error` → 500 „the asset could not be processed“ mit `error`-Log
und vollem Traceback, beide mit Request-ID über `logging.py`s Formatter) —
sie kamen bei der Download-Route nur nie zum Zug, weil das lokale `except`
alles vorher abfing. **Fix:** das lokale `except` fängt nur noch
`RasterioIOError` (plus `GatewayError`, dessen Unterklassen alle echte
Netzwerk-/Host-Fehler sind); alles andere propagiert zu den schon
vorhandenen App-Handlern. Test:
`test_download_route.py::test_a_genuine_read_failure_is_502_with_the_source_message`
(unverändert 502) und
`test_an_internal_bug_is_500_not_mislabelled_as_a_read_failure` (jetzt 500,
mit Nachweis, dass der echte Fehler geloggt wird — wird ohne den Fix rot,
mit `RasterBlockError` als Fall für „ein Bug, keine Quelle“).

**Ursache, Teil 2 — echte Randfälle.** Fünf von Otto benannte Fälle,
nachgestellt mit synthetischen COGs (`test_download_edge_cases.py`, keine
Gateway-/Netzwerk-Anbindung nötig — `open_reader` öffnet einen echten
`rio_tiler.io.rasterio.Reader` direkt gegen einen `/vsimem/`-Pfad):

1. **Polygon ragt teilweise über den Rand des Assets** — funktionierte
   bereits richtig (`.part()` liefert für den überhängenden Teil `nodata`,
   für den übrigen Teil echte Daten), kein Fund, jetzt mit Test abgesichert.
2. **Polygon trifft nur den nodata-Teil einer Randszene** und
   **Polygon schneidet das Asset nicht, obwohl der Footprint es tut** sind
   im Code dieselbe Lücke: `.part()` wirft — anders als `.feature()`s
   Cutline-Lesart — **nie** eine Exception, wenn die angefragte Bounding Box
   die Daten überhaupt nicht trifft; es kommt einfach ein vollständig
   maskiertes Array zurück. Der fensterweise Pfad
   (`_write_native_windowed_cog`) prüft das schon selbst (`any_valid_in_aoi`)
   und meldet `AoiOutsideItems`; der naive/Mosaik-Pfad (`crop_asset` +
   `_image_to_asset_crop_bytes`) tat das **nicht** — eine AOI, die die echten
   (oft gedrehten) Daten eines Mosaiks verfehlt, wäre als scheinbar
   erfolgreicher, aber vollständig leerer Download durchgegangen, statt als
   `AoiOutsideItems`/400. **Fix:** `_image_to_asset_crop_bytes` rasterisiert
   die AOI einmal (ohnehin für die Maskendatei nötig) und prüft vor dem
   Schreiben, ob irgendein Pixel innerhalb der AOI in irgendeinem Band gültig
   ist — sonst `AoiOutsideItems`, wie beim fensterweisen Pfad. Tests:
   `TestPolygonOnlyTouchesNodata`, `TestPolygonMissesTheFootprintDespiteTheBbox`
   (Mosaik aus zwei Items und Einzel-Item mit expliziter gröberer Auflösung,
   die beide den naiven Pfad nehmen) — alle rot ohne den Fix.
3. **Zwei Szenen einer Gruppe in verschiedenen UTM-Zonen** — funktionierte
   bereits richtig: `.part()`s `dst_crs` ist immer die AOI-eigene (WGS84),
   nie die native CRS eines Items, also reprojiziert jedes Mosaik-Item
   unabhängig von seiner eigenen Zone auf dasselbe Ausgaberaster. Kein Fund,
   jetzt mit Test (`TestMosaicAcrossUtmZones`) abgesichert.
4. Siehe Punkt 2.
5. **Maske bei Bändern mit unterschiedlicher Auflösung (10/20/60 m)** —
   funktionierte bereits richtig: jede Maskendatei wird aus dem eigenen
   `image.transform`/`image.array.shape` ihres Assets gebaut, nie aus einem
   fremden. Test (`TestMaskMatchesEachAssetsOwnResolution`) prüft das explizit
   mit zwei Assets unterschiedlicher nativer Auflösung im selben Request statt
   es nur anzunehmen.

**Warum die bisherigen Tests das nicht fanden:** `test_download_mask.py`s
einziges synthetisches COG (`mini_cog.py`) deckt jedes Pixel mit Werten
1..255 ab — es enthält **nirgends** echten Quellen-nodata innerhalb seiner
Ausdehnung, nur außerhalb (der reservierte Tag-Wert, den niemand liest). Kein
bestehender Test hat je eine AOI gebaut, die eine Szene *nur* an ihrem
nodata-Rand trifft oder eine Bounding Box anfragt, die ein Item komplett
verfehlt — die Randfälle, um die es hier geht, brauchten eigens dafür gebaute
Geometrien und Nodata-Muster.

**Nebenfund während der Investigation (nicht behoben, an Otto eskaliert):**
`test_download_mask.py` wiederholt ausgeführt (`pytest` mehrfach als eigener
Prozess gestartet) zeigt eine bereits im letzten Push vorhandene, intermittierende
GDAL/libtiff-Korruption beim Schreiben komprimierter COGs
(„ZSTDDecode: Unknown frame descriptor“, „TIFFReadEncodedTile() failed“) —
dieselbe Fehlerart wie F9 (§9), aber **auch bei ZSTD**, nicht nur bei DEFLATE
wie F9s Messung (200/200 sauber) nahelegte. Bestätigt reproduzierbar auf dem
Stand *vor* dieser Sitzung (`git stash` auf Commit `2b2e5e1`, 20 Wiederholungen,
mehrfach 1-3 von 6 Tests rot) — **kein neuer Fehler dieser Sitzung**, sondern
vermutlich die eigentliche Ursache hinter Befund A: ein COG-Schreibfehler in
unserem eigenen Code, der ohne den Fehlerabbildungs-Fix aus §12.1 als
„could not be read from the source“ mislabelt wurde. Mit dem Fehlerabbildungs-Fix
kommt er jetzt korrekt als 500 mit echtem Traceback im Log an — die Korruption
selbst bleibt offen, F9 muss also auf „auch bei ZSTD reproduzierbar, wahrscheinlich
Ursache von Befund A“ aktualisiert werden. Isolierte Stress-Skripte außerhalb
von `pytest` konnten es nicht reproduzieren (0/220 über mehrere Varianten);
es trat nur beim Ausführen der echten `pytest`-Testdatei auf, was auf eine
Interaktion mit `pytest` selbst hindeutet (Output-Capturing, Assertion-Rewriting-
Importhook), nicht auf einen reinen GDAL-Race. Otto muss über das weitere
Vorgehen entscheiden (GDAL/libtiff-Version, `NUM_THREADS`-Erzwingung,
Schreibstrategie) — außerhalb des Umfangs dieser Aufgabe.

**Update (26.09.2026): Ursache gefunden — ein Test-Helfer, nicht der
Produktivcode.** CI meldete `TestWindowedReadMatchesTheWholeArrayRead::
test_a_slanted_aoi_masks_agree_and_values_are_near_identical` rot mit
„TIFF directory is missing required ImageLength field“ / „Computed scanline
size is zero“ beim Lesen von `visual.tif`. Lokal 20× und in voller Suite
reproduziert (ca. 50–65 % Fehlerquote je Lauf).

*Gefunden:* `test_download_mask.py::_open_zip_member` gab bislang nur
`memfile.open()` zurück, ohne `memfile` selbst am Leben zu halten:
```python
def _open_zip_member(zip_bytes, name):
    ...
    memfile = MemoryFile(member)
    return memfile.open()
```
Da nichts außer der lokalen Variable `memfile` auf das `MemoryFile`-Objekt
verweist, ist es beim Rücksprung aus der Funktion sofort für den
Garbage Collector freigegeben — `MemoryFile.__del__` löst dabei den
zugehörigen `/vsimem/`-Puffer auf, während der zurückgegebene, noch offene
`DatasetReader` genau diesen Puffer weiter braucht. Ob das rechtzeitig vor
dem nächsten Lesezugriff passiert, hängt vom genauen GC-Zeitpunkt ab — nicht
deterministisch über verschiedene `pytest`-Läufe hinweg (derselbe Grund,
warum ein isoliertes 200-Lauf-Stress-Skript außerhalb von `pytest` es nie
zeigte, siehe oben: andere Objekt-/Referenzlast, anderer GC-Zeitpunkt). Am
zweiten, baugleichen Aufruf `MemoryFile(naive_bytes).open() as naive` — dort
ganz ohne Namen für das `MemoryFile`-Objekt, also noch anfälliger — bestätigt:
mit einem `keepalive`-Verweis auf beide `MemoryFile`-Objekte liefen 60/60
Wiederholungen fehlerfrei; ohne ihn schlugen in derselben Konfiguration
29/60 fehl.

*Nachweis, dass es der Test-Helfer war, nicht `_write_native_windowed_cog`:*
`_open_zip_member` allein, 60× wiederholt ohne die zweite (`naive`) Datei zu
öffnen, schlug **nie** fehl. Erst das gleichzeitige Offenhalten zweier so
erzeugter Datasets deckte die fehlende Referenz auf. Die Produktionsfunktionen
selbst (`_write_native_windowed_cog`, `_masked_array_to_cog_bytes`,
`crop_asset_to_cog_bytes`) verwenden durchweg `with MemoryFile() as mem: ...
mem.read()` — das `MemoryFile`-Objekt bleibt dort immer bis nach dem
`.read()` in Bytes am Leben, derselbe Fehler kann dort nicht auftreten
(geprüft: alle Vorkommen in `download.py` durchsucht, keine weitere Stelle
mit demselben Muster).

*Fix:* `_open_zip_member` zu einem `@contextmanager` gemacht, der `memfile`
und das offene Dataset im selben verschachtelten `with` hält
(`with MemoryFile(member) as memfile, memfile.open() as dataset: yield
dataset`) — dasselbe Muster, das `test_download.py` an den entsprechenden
Stellen schon immer verwendet hat. Neuer Helfer `_open_bytes` für den
zweiten, baugleichen Fall (`naive_bytes`, nicht aus einem ZIP). Beide Stellen
in `TestWindowedReadMatchesTheWholeArrayRead` umgestellt.

*Beiläufig gefunden:* die `> 0.99`-Toleranz in
`test_a_rectangle_aoi_is_pixel_identical` (Kommentar: „GDALs Block-Cache
disagreed mit sich selbst") war selbst ein Symptom desselben Bugs, nicht
eine echte Resampling-Eigenschaft — mit dem Fix stimmen Maske und Pixelwerte
für ein achsenparalleles Rechteck jetzt exakt überein (`.all()` statt
`.mean() > 0.99`), über 150 Wiederholungen bestätigt. Die verbleibende
Toleranz in `test_a_slanted_aoi_masks_agree_and_values_are_near_identical`
bleibt: dort bauen der fensterweise und der naive Pfad ihr Ausgaberaster über
zwei unabhängige Berechnungen (`_native_crop_grid` vs. `.part()`s eigene
Transformation), was am Rand einer schrägen AOI-Kante bei Nearest-Neighbor-
Resampling zu einzelnen Pixeln mit einer Quellpixelbreite Versatz führen
kann — unabhängig vom hier gefundenen Bug, über 150 Wiederholungen weiter
beobachtet, nie mehr als eine Handvoll der ~1000 Pixel des Rasters.

*Beantwortet Ottos Frage, ob derselbe Fehler Befund A erklärt:* **Nein.**
Befund A entstand aus einem zu breiten `except (RasterioError, ...)` in der
Route (§12.1 oben) und ist unabhängig davon bereits behoben. Dieser Bug hier
lebt ausschließlich im Test-Helfer (`_open_zip_member`) und betrifft keinen
Pfad, den ein echter Download durchläuft — die Produktionsfunktionen geben
immer bereits vollständig gelesene Bytes zurück, nie ein offenes, an ein
`MemoryFile`-Objekt gebundenes Dataset.

*Validierung:* jede der 50 in einem 25-Iterationen-Stresslauf erzeugten
`visual.tif`-Dateien (Diamant- und Rechteck-AOI) einzeln mit
`rio cogeo validate` geprüft — alle 50 gültig. Volle Suite danach 4× hintereinander
grün (1246/1246 je Lauf), `test_download_mask.py` allein 20× hintereinander
grün, der ursprünglich rote Test 30× hintereinander grün.

### 12.2 Befund B: Weiße Pixel im Zuschnitt (S2B_T32TNT_20260922T102300_L2A)

**Direkt am echten Item geprüft** (curl/`rasterio` gegen
`e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`, Lesepfad der
Download-Route, außerhalb von `gateway`, wie von Otto verlangt):

1. **Ja, echte nodata=0-Werte, aber pro Band sehr unterschiedlich.** Ein
   1024×1024-Fenster nahe der Bildmitte (Bergschatten/Wald-Region) hat
   8600/686/2437 nodata-Pixel je Band (von rund einer Million), aber nur
   **23** Pixel sind in **allen drei** Bändern gleichzeitig nodata. Die
   übrigen ~11 000 „irgendein Band ist nodata“-Pixel sind zu 99,8 % echte,
   sehr dunkle Daten (Schattenhang, Wasser), keine fehlende Abdeckung.
2. **Ja — genau das war der Fehler.** `numpy.ma.getmaskarray(block).any(axis=0)`
   in `_write_native_windowed_cog`/`_masked_array_to_cog_bytes` kombinierte
   die Bandmasken zu einer einzigen, für alle Bänder gemeinsamen
   GDAL-Maskenband: sobald *irgendein* Band an einem Pixel bei seinem eigenen
   nodata-Wert lag, wurde das Pixel in **allen** Bändern als ungültig markiert
   — genau das Muster, das ein Betrachter als verstreute weiße Pixel über
   Schattenhängen, dunklem Wald und Wasser zeigt.
3. **Werte selbst wurden nicht verändert** — `numpy.ma.filled(array, 0)`
   respektiert die eigene (bandweise) Maske jedes Bands, verändert also nie
   ein gültiges Pixel eines anderen Bands. Betroffen war ausschließlich die
   zusätzliche, kombinierte **Gültigkeits**-Information (die Maskenband), nicht
   die Pixelwerte der Datendatei selbst — die „Maske statt nodata“-Regel für
   das AOI-Polygon (§11) war davon nicht verletzt.

**Fix:** kein internes Maskenband mehr für die Quellen-Gültigkeit. Stattdessen
trägt die Datendatei den `nodata`-Wert der Quelle als reinen Tag weiter
(`vrt.nodata`/`image.nodata`) — GDALs eigener nodata-Vergleich ist bereits pro
Band, also braucht es dafür keine eigene Buchführung mehr. Kein `add_mask=True`
mehr auf der Datendatei. Tests (rot ohne den Fix, siehe Diff-Historie dieser
Sitzung):
`test_download.py::TestPerBandNodataNeverCombinedAcrossBands`,
`TestWindowedPerBandNodata` (synthetisch, unit-nah, kein Netz nötig) sowie
die reale Messung oben (nicht automatisiert, im PR dokumentiert).

Log-Zeile (Otto, „fest“ vorgeschlagen): siehe `ENTSCHEIDUNGSLOG.md`, Eintrag
vom 24.09.2026 „Bug A/B aus Ottos Review von PR #86 behoben“.

## 13. Präzisierung zur Maske (Otto, 23.09.2026) — **umgesetzt**

§11 legte fest, dass die Datendatei ein reiner Bounding-Box-Zuschnitt bleibt
und das AOI-Polygon nur in einer separaten Maskendatei lebt — offen blieb,
*welche* Bounding Box das ist, wenn eine Gruppe aus mehreren Szenen besteht
und nicht jede davon die ganze AOI abdeckt. Diese Präzisierung beantwortet
genau das.

### 13.1 Was Otto vorgibt

1. **ZIP-Inhalt je Gruppe unverändert:** Datendatei und Maske je Asset
   (eindeutig benannt, `mask_filename`), dazu einmal je ZIP die AOI als
   GeoJSON (`aoi.geojson`) — immer die *Original-AOI*, wie gezeichnet oder
   hochgeladen, nie beschnitten.
2. **Neu: die Ausdehnung von Datendatei und Maske** ist die Bounding Box von
   *(AOI ∩ Vereinigung der Footprints der Szenen dieser Gruppe)*, nicht mehr
   die Bounding Box der ganzen AOI. Deckt eine Szene nur einen Teil der AOI
   ab, reichen Datei und Maske nur so weit wie die Szene; deckt sie die AOI
   ganz ab, bleibt es die Bounding Box der AOI, unverändert gegenüber §11.
   Dieselbe Geometrie wie die gelbe Umrandung aus PR #84 (`groupOutline.ts`,
   Log-Zeile vom 24.09.2026 zu M3-09 §10).
3. **Maske unverändert:** gleiches Raster wie die Datendatei, `1` innerhalb
   des AOI-Polygons, `0` außerhalb. Das Nodata der Szene bleibt Sache der
   Datendatei; die Maske markiert nur die AOI, nie den (womöglich kleineren)
   Footprint.

### 13.2 Umsetzung

Zwei Geometrien statt einer, überall dort, wo bisher nur die AOI durchgereicht
wurde — jede neue Stelle bekommt einen *optionalen* Parameter, der ohne Angabe
auf die bisherige Geometrie zurückfällt, damit kein bestehender Aufrufer (Tests
eingeschlossen) sich ändern muss:

- **`compute_crop_region(items, aoi)`** (neu, `backend/earthx/access/download.py`):
  die AOI geschnitten mit der Vereinigung (`shapely.ops.unary_union`) der
  `geometry`-Felder der übergebenen Items. Fehlt einem Item die `geometry`
  oder ist sie unbrauchbar, wird es übersprungen (dieselbe Toleranz, die
  `filter_items_intersecting_aoi` schon für eine kaputte `bbox` hat); tragen
  gar keine Items eine `geometry`, fällt die Funktion auf die unveränderte AOI
  zurück. Ist der Schnitt leer, wird `AoiOutsideItems` geworfen — das nutzt
  denselben Fehlerpfad wie Befund A (§12.1): eine Bbox-Vorauswahl, deren echter
  (oft gedrehter) Footprint die AOI gar nicht berührt, fliegt schon hier raus,
  vor jedem Öffnen eines Readers.
- **`api/tiler.py`, `download_crop`:** ruft `compute_crop_region` nach dem
  bestehenden Bbox-Vorfilter auf, bevor `plan_outputs` die Ausgabegröße
  schätzt — die Größenschätzung (§4.1/§10.8) läuft jetzt gegen die engere
  `region`, nicht mehr gegen die volle AOI, damit ein AOI-Eck, das keine Szene
  erreicht, den Größendeckel nicht künstlich aufbläht.
- **`build_download_zip`** bekommt einen neuen optionalen Parameter
  `region_geometry` (Default: `aoi_geometry`, also unverändertes Verhalten für
  jeden Aufrufer, der ihn nicht setzt). `aoi_geometry` bleibt, was es immer
  war: die Original-AOI, für `aoi.geojson` und für die Maskenwerte. Nur das
  Raster von Datendatei und Maske wird jetzt aus `region_geometry` berechnet —
  quer durch `crop_asset_to_cog_bytes` → `_write_native_windowed_cog`/
  `crop_asset` (Größe/Fenster) und `_image_to_asset_crop_bytes`/
  `_rasterize_aoi_mask` (Maskenwerte weiterhin aus der Original-AOI).

**Bewusste Vereinfachung gegenüber dem Frontend:** `groupOutline.ts` bricht
die Vereinigung einer Gruppe ab und zeigt stattdessen die Pro-Szene-Umrandung,
wenn die kombinierte Lon-Spanne 180° übersteigt (Datumsgrenzen-Risiko,
„Prinzip 9 — nie etwas zeigen, wofür wir nicht geradestehen können“,
`groupOutline.ts`). `compute_crop_region` repliziert diesen Schutz nicht: bei
einem Fehler in `shapely` (inkl. eines entarteten Schnitts über die
Datumsgrenze) fällt die Funktion einfach auf die unveränderte AOI zurück,
ohne die Gruppe eigens zu erkennen oder abzulehnen. Das ist eine bewusste
Einschränkung des Umfangs dieser Präzisierung, kein Versehen — die Datumsgrenze
selbst ist in M3-18 an keiner anderen Stelle behandelt (§8 nennt sie nicht),
und Otto hat sie hier nicht angefragt. Sollte sie relevant werden, gehört sie
als eigene Frage vor die nächste Änderung an dieser Funktion.

### 13.3 Tests — **umgesetzt, rot ohne den Fix**

Alle drei in `test_download_edge_cases.py`,
Klasse `TestCropExtentIsTheGroupsOwnFootprintNotTheWholeAoi` — jeder Test war
vor dieser Änderung rot (fehlendes `compute_crop_region`), geprüft per
`git stash` auf `backend/earthx/access/download.py`/`api/tiler.py`:

| Fall | Erwartung |
|---|---|
| Eine Szene deckt die AOI nur teilweise ab | Datendatei *und* Maske enden an der Szene, nicht am AOI-Rand; `aoi.geojson` enthält trotzdem die ganze, unbeschnittene AOI |
| Zwei Szenen einer Gruppe, AOI deutlich größer als beide zusammen | Ausdehnung = Bounding Box der Vereinigung beider Footprints, nicht die (größere) AOI |
| Eine Szene deckt die AOI vollständig ab | `aoi.geojson` bleibt exakt die Eingabe-AOI (Kontrollfall zu den beiden obigen, isoliert nach Ottos Aufzählung) |

Volle Suite nach der Änderung: `ruff check backend` sauber,
`lint-imports --config .importlinter` unverändert 12/12 Contracts,
`pytest` grün bis auf den bereits unter §12.1 dokumentierten, vorbestehenden
COG-Schreibfehler (nicht neu, nicht Gegenstand dieser Präzisierung).

### 13.4 Log-Zeile

Siehe `ENTSCHEIDUNGSLOG.md`: die Zeile „Maske statt nodata“ (24.09.2026) ist
jetzt „präzisiert am 2026-09-23“; neue Zeile vom 2026-09-23 „Präzisierung zur
Maske (Otto), M3-18 §13“, Status „fest“.
