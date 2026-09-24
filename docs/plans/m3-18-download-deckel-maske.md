# M3-18 — Download-Deckel nach Ausgabegröße und Maske auf die AOI: Umsetzungsplan

**Aufgabe:** M3-18 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B** — Plan-Schritt. Die Session hält nach diesem Plan an; umgesetzt
wird erst nach Ottos Antworten auf §8.
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

### 4.1 Größenprüfung nach der Ausgabe

Neue reine Funktion in `access/download.py` (ersetzt `check_size_cap`), vor
jedem Lesezugriff aufgerufen wie heute:

> **Ausgabe = Σ über die Dateien (Pixel × Bänder × Byte je Band)**

Heute ist eine Datei = ein Asset (eine Gruppe je Anfrage). M3-17 bringt
mehrere Gruppen; die Funktion nimmt deshalb eine Liste geplanter Dateien, und
M3-17 reicht nur mehr Einträge hinein.

- **Pixel** (F1): lange Seite = min(4096, Ausdehnung der AOI / Auflösung des
  Assets), kurze Seite nach dem Seitenverhältnis der AOI-Box in Grad (rio-tiler
  rechnet in EPSG:4326, nachgeprüft: 2772/4096 = Verhältnis der Box). Die
  Auflösung kommt aus dem Item: `gsd` am Asset, sonst `spatial_resolution` in
  `raster:bands`, sonst `gsd` am Item; fehlt alles, 4096 px (obere Schranke).
  Beide Quellen tragen `gsd` je Asset (gemessen, §3).
- **Bänder × Byte** (F2): aus `raster:bands` bzw. `bands` des Item-Assets
  (`data_type`); bei einem Zarr-Komposit (`SR_10m:b04,b03,b02`) die Zahl der
  genannten Variablen. Fehlt der Datentyp, 8 Byte; fehlt die Bandzahl,
  4 Bänder. Earth Search nennt beides (`visual` 3 × uint8, `red` 1 × uint16),
  EOPF nur die Bänder, keinen Datentyp.
- **Abweisung** mit `413` und einer Meldung auf Englisch, in MB gerundet und
  mit einem Ausweg, z. B.: *„This download would be about 403 MB, more than
  the 200 MB limit. Draw a smaller area or download fewer layers.“*

Die 4096 px je Seite bleiben strukturell über `max_size` erzwungen.

### 4.2 Grenze für den Arbeitsspeicher (F4, F5)

- **Nacheinander lesen:** `mosaic_reader(..., threads=1)`. Speicher je Anfrage
  hängt dann nicht mehr an der Item-Zahl (§3 Punkt 1); obere Schranke aus der
  Messung rund 1,6 GB am 200-MB-Deckel, bei `visual` rund 0,45 GB.
- **Höchstens 25 Items je Anfrage** nach dem Vorfilter (gleiche Zahl wie der
  Mosaik-Deckel je Kachel-URL in `adr/0006` §5, „Zu Frage 4“), sonst `413`: *„This download
  covers 31 scenes; at most 25 fit in one download. Select fewer scenes or draw
  a smaller area.“* Grund ist die Laufzeit (nacheinander ≈ 1 s je Item an der
  Quelle), nicht der Speicher.
- **Höchstens 2 Zuschnitte gleichzeitig im `tiler`-Prozess** (F5): ein
  Semaphor ohne Warteschlange; die dritte Anfrage bekommt sofort `503` mit
  `Retry-After: 30` und *„The server is busy preparing other downloads. Please
  try again in a minute.“* Damit liegen Zuschnitte im Prozess bei höchstens
  rund 3,2 GB. Das ist keine Ratenbegrenzung pro IP oder Nutzer (D6, nicht in
  M3), sondern eine feste Obergrenze für den Prozess.

### 4.3 Maske auf die AOI (F3)

- Nach dem Lesen (1 Item) bzw. dem Mosaik (mehrere Items) werden alle
  maskierten Pixel — außerhalb des Polygons **und** ohne Daten — auf einen
  `nodata`-Wert gesetzt, und die Datei trägt diesen Wert als `nodata`-Tag.
  **Kein Alpha-Band mehr**, also dieselbe Bandzahl bei 1 und bei 20 Items.
- Der Wert: das `nodata` der Quelle, sofern das erste gelesene Bild eines hat
  (Sentinel-2 `visual`/`red`: 0); sonst je Datentyp fest: `NaN` bei float,
  0 bei vorzeichenlosen, kleinster Wert bei vorzeichenbehafteten Ganzzahlen.
- Die Ausdehnung bleibt die Box der AOI (Log 23.09.2026). Eine Rechteck-AOI
  ergibt dieselben Pixel wie heute (die Polygon-Maske deckt die ganze Box ab,
  `all_touched=True`).
- Die AOI geht wie heute unverdünnt aus dem Body in die Maske; die Verdünnung
  aus `adr/0004` §3.4 betrifft nur die URL der Coverage-Anfrage und bleibt
  unverändert. Stützpunkt-Deckel im Download: F6.

### 4.4 Frontend

- Die Meldungen kommen fertig formuliert aus dem Backend (`detail`), das
  Frontend zeigt sie wie heute über `Download failed: …` (F8). Am Frontend-Code
  ändert sich damit nichts; ein Vitest hält fest, dass der Text unverändert beim
  Nutzer ankommt.

### 4.5 Nicht anfassen

`readers`, `decomp.py`, Kachel-Pfad, `gateway` (außer der Nutzung von
`gdal_options` in `api/tiler.py`, F7), Gruppierung je Überflug und „Download
folgt der Ansicht“ (M3-17), Registry-Felder (F2 Option 1 braucht keine).

---

## 5. Tests

Alle ohne Netz; COGs synthetisch per `tests/earthx/readers/mini_cog.py` im
`tmp_path`.

| Abnahmepunkt | Test |
|---|---|
| 6 Items unter dem Ausgabe-Deckel → 200 | Route-Test: 6 Items, 1 Asset, AOI groß genug für 4096 px; früher 413, jetzt 200 mit ZIP |
| Ausgabe über dem Deckel → Abweisung mit klarer Meldung | Route-Test: viele Assets bzw. float64-Asset → 413; `detail` nennt MB und Grenze, enthält keine Byte-Rohzahlen und keine Koordinaten |
| Speichergrenze greift | (a) 26 Items nach Vorfilter → 413 mit Text; (b) `mosaic_reader` wird mit `threads=1` aufgerufen; (c) Stapel aus 6 Fake-Readern mit voller Deckung: nur der erste wird gelesen; (d) drittes gleichzeitiges Zuschnitt-Request → 503 mit `Retry-After` |
| schräges Polygon | echte synthetische COG, rautenförmiges Polygon: Pixel außerhalb = `nodata`, innerhalb gefüllt; gleich bei 1 und 2 Items (Bandzahl, `nodata`, Werte) |
| Rechteck-AOI unverändert | gleiche COG, Rechteck-AOI: keine maskierten Pixel in der Datei, Werte wie beim Lesen ohne Maske |
| Ausgabeschätzung | reine Funktion: Werte aus `raster:bands`, aus `bands` ohne Datentyp, Zarr-Komposit, fehlende Angaben (Rückfall); die Schätzung ist nie kleiner als die tatsächliche Größe, die rio-tiler für dieselbe AOI liefert |
| zweckfremde Nutzung | `gsd` 0, negativ, Text oder `NaN` im Item → Rückfall statt Division durch 0; unbekannter `data_type` → 8 Byte |
| keine Koordinaten im Log | Route-Test mit Polygon und `caplog`: keine Koordinate der AOI in Nachricht oder `extra`, auch nicht bei 413/503 |
| Frontend | Vitest: `confirmDownload` zeigt bei 413 und 503 den `detail`-Text unverändert hinter `Download failed:` |

`test_download.py::TestCheckSizeCap` wird durch Tests der neuen Funktion
ersetzt.

---

## 6. Ablauf und Nachweise

1. Commits klein und getrennt: Ausgabeschätzung; `threads=1` und Item-Deckel;
   Semaphor; Maske; GDAL-Umgebung (F7); Vitest; Log-Zeilen.
2. Vor „fertig“: `pytest`, `ruff check backend`, `lint-imports --config
   .importlinter`, `npm run lint`, `npx tsc -b --pretty false`, Vitest; `main`
   in den Branch holen.
3. **Otto prüft lokal:** ein Zuschnitt über 6 Szenen eines Überflugs (früher
   413); ein schräges Polygon in QGIS öffnen (außen transparent, 3 Bänder); ein
   EOPF-Zuschnitt: Datentyp der Datei im ZIP ablesen (`gdalinfo`), damit die
   8-Byte-Annahme aus F2 durch den gemessenen Wert ersetzt werden kann.

Geschätzter Umfang: rund 350–450 geänderte Zeilen, davon gut die Hälfte Tests.

---

## 7. Log-Zeilen (am Ende von `ENTSCHEIDUNGSLOG.md`, nach der Freigabe)

- M3-18: Ausgabegröße vor dem Lesen = Σ Dateien (Pixel × Bänder × Byte), Werte
  laut F1/F2; 200 MB bleiben.
- M3-18: Speichergrenze laut F4/F5, mit den Zahlen aus §3.
- M3-18: `nodata` außerhalb der AOI laut F3, kein Alpha-Band.
- M3-18, Nebenbefund: Download-Route ohne GDAL-Umgebung von `gateway` (F7);
  AOI > 4096 px wird verkleinert (Antwort auf §1.3 „Lokal prüfen“).

---

## 8. Fragen an Otto

**F1 — Woher kommt die Pixelzahl der Ausgabe?**
1. **Aus AOI und Auflösung im Item, gedeckelt auf 4096 px (Empfehlung).** Kein
   Kontakt zur Quelle vor der Prüfung, wie in M2-06. Die dritte Quelle
   materialisiert ihre Items selbst (M3-11) und kann `gsd` mitschreiben.
2. Kopf des ersten Items je Asset öffnen und rio-tiler die exakte Größe und den
   Datentyp rechnen lassen. Exakt und quellenunabhängig, kostet aber vor der
   Prüfung eine Anfrage je Asset an die Quelle, auch bei einer Abweisung.
3. Immer 4096 px an der langen Seite. Am einfachsten, weist aber kleine AOIs
   mit mehreren Bändern ab, die heute durchgehen.

**F2 — Bänder und Byte je Pixel?**
1. **Aus `raster:bands`/`bands` im Item, Zarr-Komposit nach Variablen,
   Rückfall 8 Byte und 4 Bänder (Empfehlung).** Folge bis zu Ottos
   Nachmessung: EOPF-Zuschnitte (3 × 8 Byte angenommen) gehen bis etwa
   2900 × 2900 px (≈ 29 km im Quadrat bei 10 m) statt 4096 × 4096.
2. Neues Registry-Feld je Asset (Bänder, Datentyp), ohne Vorgabewert (B10).
   Genau, aber ein Pflichtfeld mehr bei jedem Onboarding.

**F3 — Welcher Wert steht außerhalb der AOI?**
1. **`nodata` der Quelle, sonst fest je Datentyp (`NaN`, 0, Minimum); kein
   Alpha-Band (Empfehlung).** Ein Format für 1 und viele Items, wie im Log
   „nodata außerhalb“. Schwäche: Hat eine Quelle kein `nodata` und ist 0 ein
   gültiger Wert, wird 0 mehrdeutig.
2. Immer eine interne Maske (TIFF-Maskenband) und 0 als Füllwert, `nodata`-Tag
   nur, wenn die Quelle einen hat. Eindeutig für jeden Datentyp, aber Werkzeuge
   ohne Masken-Unterstützung sehen 0 statt „leer“.
3. Immer Alpha-Band, wie heute beim Mosaik. Ändert die Bandzahl (RGB → RGBA,
   ein Band → zwei).

**F4 — Speichergrenze je Anfrage?**
1. **Nacheinander lesen (`threads=1`) und höchstens 25 Items je Anfrage
   (Empfehlung).** Gemessen: Speicher unabhängig von der Item-Zahl, rund
   0,45 GB bei `visual`, höchstens rund 1,6 GB am 200-MB-Deckel. Laufzeit
   wächst mit der Zahl der Items, die wirklich gebraucht werden.
2. Wie 1, zusätzlich ein Budget von 1 GB je Anfrage nach der Faustformel aus
   §3 (größte Datei höchstens rund 120 MB roh). Hält den Speicher enger, weist
   aber z. B. 3-Band-float32 über etwa 4096 × 2400 px ab.
3. Zwei Reads gleichzeitig (`threads=2`): halbe Laufzeit im Raster-Fall,
   doppelter Speicher (722 MB bei 20 Items `visual`).

**F5 — Grenze für gleichzeitige Zuschnitte im Prozess?**
1. **Höchstens 2, die dritte Anfrage sofort `503` mit `Retry-After`
   (Empfehlung).** Zuschnitte kosten im Prozess dann höchstens rund 3,2 GB.
2. Keine in M3; der Prozess-Speicher wird mit dem Deployment (M6) begrenzt.

**F6 — Stützpunkt-Deckel für die AOI im Download?**
1. **Ja, 1000 Stützpunkte wie in M3-08 für die Suche, sonst `400` (Empfehlung).**
   Solange M3-08 nicht gemergt ist, eine eigene Konstante; danach eine
   gemeinsame.
2. Nein; die Größe des Bodys begrenzt die AOI weiter nur indirekt.

**F7 — Nebenbefund: Download-Route ohne GDAL-Umgebung von `gateway`.**
1. **In M3-18 beheben (Empfehlung).** Die Messung in §3 lief mit dieser
   Umgebung; ohne sie gilt die Speichergrenze nur ungefähr, und Timeouts aus
   `gateway` greifen beim Zuschnitt nicht. Etwa 5 Zeilen in `api/tiler.py`.
2. Als eigene kleine Aufgabe (Stufe A) nach M3-18.

**F8 — Wer formuliert die Meldung?**
1. **Das Backend im `detail`, auf Englisch mit MB und Ausweg; das Frontend
   zeigt sie unverändert (Empfehlung).** Eine Stelle für den Text.
2. Das Backend liefert einen Code und Zahlen, das Frontend baut den Text.
   Mehr Struktur, aber zwei Stellen, die zusammenpassen müssen.

**Von Otto auszuführen:** nach der Umsetzung die lokalen Prüfungen aus §6
Punkt 3.
