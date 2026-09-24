# M3-18 — Download-Deckel nach Ausgabegröße und Maske auf die AOI: Umsetzungsplan

**Aufgabe:** M3-18 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B** — **von Otto am 24.09.2026 freigegeben** mit F1 (1), F2 (1), F3
(2), F4 (1), F5 (2), F6 (2), F7 (1), F8 (1) (§8) und **umgesetzt**. Zwei
Punkte sind noch offen und halten den nächsten Umsetzungsschritt an: F9
(§9, Kompression des maskierten Zuschnitts, Nebenfund) und die native
Auflösung (§10, Ottos Erweiterung vom 23.09.2026 — Nummerierung nach dem
Datum ihres Eingangs, nicht der Chronologie). **Der Code im Repo entspricht
noch §1–§9** (4096 px Deckel, 200 MB); §10 ist Plan, keine Umsetzung, bis
Otto die Fragen dort beantwortet.
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

### 10.5 Ergänzter Umfang (geplant, nicht umgesetzt)

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
- **Dateiname/Metadaten (Punkt 3):** Die gewählte Auflösung steht im
  ZIP-Dateinamen (z. B. `visual_10m.tif` gegenüber `visual_60m.tif`,
  `crop_filename` bekommt einen Suffix) und ist in der geschriebenen Datei
  selbst durch die Pixelgröße im Geotransform bereits enthalten — ein Blick
  mit `gdalinfo` zeigt sie, ohne dass ein eigenes Tag nötig wäre. Zusätzlich
  in `ATTRIBUTION.txt` genannt (`build_notice_text`).
- **`DownloadDialog.tsx`:** ein Auswahlfeld (nativ voreingestellt) mit
  wenigen groben Stufen (z. B. „Native“, „2× coarser“, „4× coarser“,
  „10× coarser“) — eine je Datensatz genau passende Liste (Sentinel-2s
  10/20/60 m) wäre genauer, ist aber ein Registry-Feld und für M3 nicht
  vorgesehen (F2 (1) braucht ebenfalls keins); ein generischer Faktor reicht
  für den ersten Schritt.
- **`plan_outputs`/`check_output_size_cap`:** Meldungstext um den zweiten Weg
  ergänzt (§10.2).

### 10.6 Ergänzte Abnahme (geplant)

| Abnahmepunkt | geplanter Test |
|---|---|
| groß, aber unter der Grenze → nativ | Route-Test: eine AOI, die nativ z. B. 6000×6000 px ergäbe (unter dem neuen Deckel), ohne Auflösungsfeld → `200`, die Datei hat die native Pixelgröße, nicht 4096 |
| über der Grenze → Abweisung mit Meldung | Route-Test: eine AOI, die nativ über der Grenze aus §10.4 liegt → `413`, `detail` nennt die geschätzte Größe und beide Auswege (AOI verkleinern, gröbere Auflösung) |
| gewählte Auflösung wird eingehalten | Route-Test: dieselbe große AOI mit einer ausdrücklich gewählten gröberen Auflösung → `200`, die Datei hat die erwartete (gröbere) Pixelgröße, nicht die native; Dateiname trägt den Auflösungswert |
| fensterweises Lesen liefert dasselbe Ergebnis wie der bisherige Weg | Modul-Test: dieselbe AOI/COG einmal naiv, einmal fensterweise gelesen → identische Pixelwerte und Maske (Regressionsschutz für den Umbau aus §10.3) |

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
