# M3-22 — Gelegentlich unlesbare Download-Dateien: Plan

**Aufgabe:** M3-22 aus `docs/plans/m3-dritte-quelle-und-interface.md` §4.
**Stufe B** — Plan-Schritt. Wartet auf Ottos Freigabe (§7); bis dahin kein
Produktivcode.
**Ort im Repo:** `docs/plans/m3-22-unlesbare-downloads.md`
**Grundlagen:** `plans/m3-dritte-quelle-und-interface.md` (§1.2, M3-22, P20,
P21); `plans/m3-18-download-deckel-maske.md` §9 (F9), §12.1 mit Update vom
26.09.2026; `ENTSCHEIDUNGSLOG.md`, Zeilen vom 24.09.2026 („M3-18, Nebenfund …
ZSTD statt DEFLATE“, „M3-18 §9, Aktualisierung/Verschärfung …“) und vom
26.09.2026 („CI-Rot auf PR #86 behoben …“); Code in
`backend/earthx/access/download.py`, `backend/earthx/api/tiler.py`
(`download_crop`), `backend/tests/earthx/access/test_download_mask.py`.

---

## 1. Ergebnis in drei Sätzen

Die Ursache ist belegt: Es war nie eine defekte Datei, sondern ein Lesefehler
**beim Prüfen** — ein Use-after-free im Test-Leseweg, weil rasterio
`MemoryFile(bytes)` den `/vsimem/`-Puffer auf den Speicher des Python-`bytes`-
Objekts legt, ohne ihn zu besitzen. Der Produktivpfad erzeugte in 2 800
vollständig zurückgelesenen Dateien (DEFLATE und ZSTD, seriell und mit 8
Threads) keinen einzigen Fehler, und der alte Test-Helfer erzeugt genau die
gemeldeten Meldungen („ZIPDecode“, „ZSTDDecode: Unknown frame descriptor“,
„Computed scanline size is zero“) mit beiden Kompressionen. Vorgeschlagen
werden trotzdem der Sofortschutz aus der Aufgabe, ein statischer Wächter gegen
das Muster und die Rückkehr zu DEFLATE, weil der Grund für ZSTD entfällt.

---

## 2. Stand vor dieser Aufgabe (gelesen und nachgeprüft, 26.09.2026)

- **Schreibweg.** `download.py` erzeugt jede Datei in leeren
  `MemoryFile()`-Objekten (GDAL besitzt den Puffer) und gibt nur fertige
  `bytes` zurück (`mem.read()` innerhalb des `with`). Zwei Wege:
  `_write_native_windowed_cog` (ein COG-Item, native Auflösung, blockweise)
  und `_masked_array_to_cog_bytes` (Mosaik, Zarr, gröbere Auflösung). Beide
  rufen `cog_translate(..., in_memory=True)` mit `_MASKED_COG_PROFILE` (ZSTD).
  Die Maskendatei (`_mask_profile`) ist ein einfaches, gekacheltes GeoTIFF,
  ebenfalls ZSTD. Nirgends im Produktivcode steht `MemoryFile(<bytes>)`.
- **Threads.** Kein `NUM_THREADS`/`GDAL_NUM_THREADS` gesetzt; `rio-cogeo`
  schreibt einfädig. Die Route ruft `build_download_zip` über
  `run_in_threadpool`, mehrere Downloads laufen also gleichzeitig in
  verschiedenen Threads.
- **Versionen** (Cloud-Session, wie CI aus `requirements*.txt`): Python 3.12,
  rasterio 1.5.1 mit GDAL 3.12.4 (Wheel), rio-cogeo 7.0.3, rio-tiler 9.4.6.
- **Der Fix vom 26.09.2026** (`5cf8a6d`, Log-Zeile „CI-Rot auf PR #86
  behoben“) hat `_open_zip_member` in `test_download_mask.py` auf
  verschachtelte `with` umgestellt. Die Log-Zeile beschreibt den Mechanismus
  aber ungenau („`MemoryFile.__del__` löst den `/vsimem/`-Puffer auf“) und
  lässt offen, ob die Meldungen aus F9 (§9 von M3-18, gemessen außerhalb von
  `pytest`) dieselbe Ursache haben. Deshalb steht M3-22 noch auf „Ursache
  offen“.

---

## 3. Ursache

### 3.1 Mechanismus (Quelltext rasterio 1.5.1, `rasterio/_io.pyx`, `MemoryFileBase.__init__`)

```text
self._initial_bytes = initial_bytes
cdef unsigned char *buffer = self._initial_bytes
self._vsif = VSIFileFromMemBuffer(self._path, buffer, len(self._initial_bytes), 0)
```

Der letzte Parameter `0` ist `bTakeOwnership = FALSE`: GDAL legt die
`/vsimem/`-Datei direkt auf den Speicher des Python-`bytes`-Objekts, ohne
Kopie und ohne ihn zu besitzen. Nur `MemoryFile._initial_bytes` hält dieses
Objekt am Leben. `MemoryFileBase` hat weder `__del__` noch `__dealloc__`;
`close()` (über `__exit__`) entfernt die `/vsimem/`-Datei.

Das alte Muster im Test

```python
member = archive.read(name)
memfile = MemoryFile(member)
return memfile.open()
```

gibt ein offenes Dataset zurück, während `memfile` und `member` beim
Rücksprung unerreichbar werden. Python gibt das `bytes`-Objekt frei; die
`/vsimem/`-Datei bleibt bestehen und zeigt auf freigegebenen Speicher. Liest
das Dataset danach eine Kachel oder den IFD, liest es, was dort inzwischen
liegt. Je nach Inhalt ergibt das einen Dekodierfehler der jeweiligen
Kompression, einen unsinnigen IFD („missing required ImageLength field“,
„Computed scanline size is zero“) oder — unkomprimiert, ohne Prüfsumme — einen
Absturz. Das ist ein Use-after-free, kein Schreibfehler.

**Warum nur in `pytest`:** Ob der freigegebene Speicher schon überschrieben
ist, hängt davon ab, was der Prozess danach anlegt. In einer vollen
`pytest`-Sitzung (Assertion-Rewriting, erfasste Ausgaben, viele Objekte) wird
er schnell wiederverwendet; in einem kleinen Skript bleibt er oft zufällig
unverändert, und das Lesen gelingt trotzdem.

### 3.2 Messungen (26.09.2026, Cloud-Session, 4 CPUs; 0 Anfragen an echte Quellen, alles synthetisch)

Synthetische Quelle: 3 Bänder uint8, 700 × 700 px, UTM 32N, nodata 0 mit
einem nodata-Streifen, als COG (DEFLATE, Overviews). AOI: schräges Quadrat
(„Diamant“) wie in `test_download_mask.py`. „Vollständig zurückgelesen“ heißt:
jedes Band in voller Auflösung, die Datensatzmaske und jede Overview-Stufe,
über das sichere Muster (`with MemoryFile(b) as mf, mf.open() as ds`).

| # | Messung | Ergebnis |
|---|---|---|
| M1 | Produktivpfad seriell: 500 Durchläufe × 2 Wege (fensterweise, Ganzarray) × 2 Kompressionen (DEFLATE, ZSTD), jede Datei vollständig zurückgelesen | **0 Fehler in 2 000 Dateien** (DEFLATE 43,7 s, ZSTD 42,0 s) |
| M2 | Produktivpfad nebenläufig: fensterweiser Weg, 8 Threads, 400 Dateien je Kompression | **0 Fehler in 800 Dateien** |
| M3 | Der Test aus der CI von #86 (`test_a_slanted_aoi_masks_agree_and_values_are_near_identical`) auf `main`, 50 × als eigener `pytest`-Prozess | **50/50 grün** |
| M4 | Derselbe Testmodul-Stand **vor** `5cf8a6d` (alter Helfer), 30 `pytest`-Läufe je Kompression | DEFLATE **22/30 Läufe rot**, ZSTD **18/30 rot**. Meldungen: „ZIPDecode: Decoding error at scanline 0“ (48×), „… unknown compression method“ (4×), „ZSTDDecode: Error in ZSTD_decompressStream(): Unknown frame descriptor“ (8×), „Computed scanline size is zero“ (38×) |
| M5 | Mechanismus isoliert: **gültige** Bytes (in M1 fehlerfrei gelesen) über das alte Muster öffnen, danach `gc.collect()` und neuen Speicher belegen, dann lesen | **50/50 Lesefehler**; dieselben Bytes mit gehaltener Referenz: **0/50** |

Die Messskripte liegen nicht im Repo (Scratchpad der Session); die Umsetzung
übernimmt M1/M2 als begrenzten Stresstest und M5 als Regressionsprüfung in die
Tests (§5).

### 3.3 Einordnung der früheren Beobachtungen

| Beobachtung | Einordnung |
|---|---|
| CI von #86, „TIFF directory is missing required ImageLength field“ | belegt: alter Helfer (M4, M5); seit `5cf8a6d` weg (M3) |
| „ZSTDDecode: Unknown frame descriptor“ in `pytest` (M3-18 §12.1) | belegt: derselbe Helfer (M4) |
| F9 (M3-18 §9): DEFLATE 4–15/100, LZW 14/100, unkomprimiert Absturz, ZSTD 0/550, **außerhalb** von `pytest` | **eingegrenzt, nicht nachgemessen:** Die damaligen Skripte sind nicht erhalten. Der heutige Produktivpfad zeigt außerhalb von `pytest` mit DEFLATE 0/1 000 (M1) und 0/400 nebenläufig (M2). Das Fehlerbild (Dekodierfehler bei komprimierten Varianten, Absturz ohne Kompression) ist genau das des Use-after-free (§3.1) und passt nicht zu einem Schreibfehler, der auch unkomprimiert eine lesbare, nur falsche Datei ergäbe. Wahrscheinlichste Erklärung: dieselbe Lesefalle in den Messskripten |
| „nachträglich gepatchter `nodata`-Tag beschädigt die Datei“ (F9) | gegenstandslos: der Patch-Weg ist seit M3-18 Bug B nicht mehr im Code |
| „Wechselwirkung mit `pytest`“ (Log 24.09.2026) | erklärt: Speicherwiederverwendung, §3.1 letzter Absatz |
| GDAL/libtiff 3.12, `NUM_THREADS`, fensterweises Schreiben | ausgeschlossen, soweit messbar: M1/M2 decken beide Schreibwege, beide Kompressionen und Nebenläufigkeit ab; ein Versionswechsel ist nicht nötig |

**Folge:** Es gibt nach heutigem Stand keinen Produktivfehler, der je eine
defekte Datei ausgeliefert hätte. Der Sofortschutz (§4) bleibt trotzdem
Pflicht laut Aufgabe; er sichert gegen einen Fehler ab, den wir nicht kennen,
und nicht gegen diesen.

---

## 4. Sofortschutz

### 4.1 Form (Vorschlag, F1)

1. **Prüfen jeder erzeugten TIFF-Datei** (Datendatei und Maske je Asset)
   direkt nach dem Schreiben, im selben Worker-Thread, neue Funktion
   `_verify_tiff_bytes(data, expected)` in `access/download.py`:
   - öffnen über das sichere Muster (verschachtelte `with`);
   - Kopf gegen Erwartung: Breite, Höhe, Bandzahl, Datentyp, Transform, CRS,
     nodata (Daten) bzw. uint8/1 Band (Maske) — fängt „ImageLength fehlt“ und
     jede Verwechslung;
   - **jeden Block jedes Bandes** in voller Auflösung lesen
     (`block_windows`), bei der Datendatei zusätzlich jede Overview-Stufe —
     fängt jeden Dekodierfehler; blockweise, damit nie mehr als ein Block im
     Speicher liegt (passt zum fensterweisen Pfad aus M3-18 §10).
   - Ergebnis: nichts oder `CorruptOutput` (neue Ausnahme, eigene Klasse, kein
     `RasterioError`, damit sie nicht in die bestehenden Handler rutscht).
2. **Einmal neu erzeugen.** Scheitert die Prüfung eines Assets, erzeugt
   `build_download_zip` dieses Asset genau einmal neu (derselbe Aufruf von
   `crop_asset_to_cog_bytes`) und prüft wieder. Log `warning` mit Datensatz,
   Asset und Fehlermeldung, **ohne AOI und ohne Koordinaten** (M3-16).
3. **Sonst `500`.** Scheitert auch der zweite Versuch, wirft
   `build_download_zip` `CorruptOutput`; `download_crop` antwortet `500` mit
   `{"detail": "a generated file did not pass verification. Please try again;
   if it keeps failing, report request ID <id>."}`. Das Frontend setzt schon
   heute „Download failed: “ davor (`store.ts`, Fehler aus `api.ts`), der
   Dialog zeigt also die ganze Meldung ohne Änderung. Die Request-ID kommt
   aus `earthx.logging.get_request_id()` und steht wie bisher auch im Header
   `x-request-id`; Log `error` mit Traceback.
4. **Das ZIP selbst** wird nach dem Bauen einmal über `ZipFile.testzip()`
   (CRC jedes Eintrags) geprüft; ein Fehler dort ist ein Python-seitiger Bug,
   daher ohne Neuversuch direkt `CorruptOutput` → `500`.

**Warum nicht nur `cog_validate`:** Es prüft Aufbau und Reihenfolge der
IFDs, dekodiert aber keine Kachel — ein „ZIPDecode“-Fehler wäre
durchgerutscht.

**Neuversuch des ganzen Assets statt nur des Schreibschritts:** Der
fensterweise Pfad verschränkt Lesen und Schreiben; nur `cog_translate` zu
wiederholen, bräuchte eine zweite Code-Struktur für einen Fall, der nach §3
nicht vorkommt. Kosten: im Fehlerfall wird die Quelle für dieses eine Asset
noch einmal gelesen (über `gateway`, mit VSI-Cache).

### 4.2 Kosten (gemessen, 26.09.2026)

Worst Case am Deckel: 500 MB roh (3 × 12 900 × 12 900 uint8, schlecht
komprimierbar), eine Datei, Ganzarray-Weg.

| | DEFLATE | ZSTD |
|---|---|---|
| Schreiben (`cog_translate`) | 26,2 s | 18,3 s |
| Vollständiges Zurücklesen inkl. Overviews | **2,2 s (9 %)** | **1,0 s (5 %)** |
| Spitzenspeicher des Prozesses | unverändert | unverändert |

`ZipFile.testzip()` über einen 600-MB-Eintrag: 0,4 s. Speicher: `MemoryFile`
mit Anfangs-Bytes kopiert nicht (§3.1), blockweises Lesen hält einen Block;
dazu kommt der GDAL-Block-Cache, der ohnehin begrenzt ist (`GDAL_CACHEMAX`).
Ein Neuversuch verdoppelt im Fehlerfall die Zeit für dieses eine Asset. Bei
kleinen Downloads (M1: 700 × 700 px) kostet die Prüfung rund 3–6 ms je Datei.

---

## 5. Umfang der Umsetzung (nach Freigabe)

**Code**
- `access/download.py`: `CorruptOutput`, `_verify_tiff_bytes`, Neuversuch
  und ZIP-Prüfung in `build_download_zip`; Kompression laut F2 in
  `_MASKED_COG_PROFILE` und `_mask_profile`, der Kommentar zur ZSTD-Wahl wird
  durch den Befund aus §3 ersetzt.
- `api/tiler.py`: `except CorruptOutput` in `download_crop` → `500` wie in
  §4.1 Punkt 3.

**Tests** (neue Datei `tests/earthx/access/test_download_verification.py`,
alles synthetisch)
- Prüfung erkennt: abgeschnittene Bytes, gekippte Bytes in einer Kachel
  (Dekodierfehler), falsche Größe/Bandzahl gegenüber der Erwartung, leere
  Bytes, Nicht-TIFF-Bytes (JSON, PNG) — zweckfremde Eingaben; akzeptiert eine
  gültige Datei samt Overviews.
- Neuversuch: Schreiber per `monkeypatch` einmal defekt → zweiter Versuch
  gelingt, ZIP enthält eine lesbare Datei, genau eine Warnung im Log, ohne
  AOI-Koordinaten.
- Immer defekt → `CorruptOutput`; über die Route `500` mit Request-ID in Body
  und Header, englische Meldung, `error` im Log.
- ZIP mit falscher CRC → `CorruptOutput`.
- **Stresstest mit begrenzter Laufzeit** (läuft in jeder CI): beide
  Schreibwege, je 25 Durchläufe, jede Datei vollständig zurückgelesen, dazu
  das Szenario des CI-Tests von #86 50 × im selben Prozess; Deckel ≈ 10 s,
  gemessen und im PR genannt. Lokal einmal mit 500 Durchläufen (Zahl über
  eine Umgebungsvariable, Vorgabe klein).
- **Kein Test „das alte Muster muss scheitern“:** Der Use-after-free (M5)
  scheitert nur, wenn der Speicher schon überschrieben ist — ein solcher Test
  wäre selbst unzuverlässig. Gegen einen Rückfall wirkt der Wächter aus F3.

**Doku**
- `ENTSCHEIDUNGSLOG.md`: neue Zeile „M3-22: Ursache …“ ans Ende; Status der
  zwei Zeilen vom 24.09.2026 zur Korruption auf „ersetzt am 2026-09-xx
  (M3-22)“; Text stehen lassen. Die Zeile vom 26.09.2026 („CI-Rot …“) bleibt
  unverändert; die neue Zeile berichtigt deren Mechanismus-Satz.
- `plans/m3-18-download-deckel-maske.md` §9: ein Satz, dass F9 durch M3-22
  beantwortet ist, mit Verweis; Originaltext stehen lassen.

**Nicht anfassen:** `readers`, `decomp.py`, `.github/`, Frontend (zeigt
`detail` einer `500` schon heute an, §4.1 Punkt 3).

**Größe:** geschätzt rund 120 Zeilen Code, 250 Zeilen Tests, 30 Zeilen Doku.

---

## 6. Abnahme (aus der Aufgabe, konkret)

1. Ursache belegt (§3) — im PR mit den Zahlen aus M1–M5.
2. Sofortschutz mit Tests: defekte Datei → Neuversuch → Erfolg; zweimal
   defekt → `500` mit Request-ID.
3. Der Test aus der CI von #86 in 50 Wiederholungen grün: lokal als 50
   eigene `pytest`-Prozesse nach der Umsetzung, in der CI über den Stresstest.
4. Die zwei Log-Zeilen zur Korruption auf „ersetzt“.
5. `ruff check backend`, `pytest`, `lint-imports --config .importlinter`
   grün; `main` vor dem Fertigmelden eingeholt.

---

## 7. Fragen an Otto

**F1 — Form des Sofortschutzes**
1. **Wie §4.1: jeden Block und jede Overview zurücklesen, einmal neu
   erzeugen, sonst `500`; ZIP-CRC prüfen (Empfehlung).** 5–9 % Mehrzeit am
   Deckel, kein Mehrspeicher.
2. Nur Kopf und `cog_validate` — billiger, fängt aber keine
   Dekodierfehler, also genau die gemeldete Fehlerart nicht.
3. Wie 1, aber ohne Neuversuch, sofort `500` — einfacher; die Aufgabe
   verlangt den Neuversuch ausdrücklich.

**F2 — Kompression von Datendatei und Maske**
1. **Zurück auf DEFLATE für beide (Empfehlung).** Der einzige Grund für
   ZSTD (F9) ist durch §3 widerlegt; DEFLATE liest praktisch jede
   GeoTIFF-Software (Belege §8). Datei etwas größer, Zurücklesen 2,2 s statt
   1,0 s am Deckel.
2. ZSTD bleibt — schneller und oft kleiner, aber mit den Lücken aus §8.

**F3 — Wächter gegen das Muster aus §3.1**
1. **Statischer Test (AST) über `backend/` (Empfehlung):** jeder Aufruf
   `MemoryFile(<Argument>)` muss direkt in einem `with` stehen; eine
   Kette `MemoryFile(…).open()` ist verboten. `MemoryFile()` ohne Argument
   (GDAL besitzt den Puffer) bleibt frei. Heute erfüllt der ganze Code die
   Regel; rund 40 Zeilen.
2. Nur ein Absatz in `adr/0002` bzw. im Docstring — ohne Durchsetzung.

**F4 — Meldung an rasterio**
1. **Kein Issue (Empfehlung):** Das Verhalten ist dokumentierbar gewollt
   (keine Kopie), die Falle ist unsere Verwendung.
2. Ein Issue im rasterio-Repo vorschlagen, das die Lebensdauer in der Doku
   von `MemoryFile` nennt — nur mit Ottos Zustimmung, weil es nach außen geht.

---

## 8. Kompression: Lesbarkeit mit Beleg

Recherche vom 26.09.2026 (Web, keine Messung). Mehrere Herstellerseiten
waren aus der Cloud-Umgebung gesperrt; was nur aus Suchergebnissen stammt, ist
als „nicht direkt gelesen“ markiert, was gar nicht zu finden war, als
„unbelegt“.

| Programm | ZSTD (TIFF-Tag 50000) | DEFLATE | Beleg |
|---|---|---|---|
| libtiff | ab 4.0.10 (11/2018), **optional beim Build** (nur mit libzstd) | fest eingebaut (zlib) | [libtiff 4.0.10](http://www.simplesystems.org/libtiff/releases/v4.0.10.html) (nicht direkt gelesen); [CMakeLists.txt](https://github.com/rouault/libtiff/blob/master/CMakeLists.txt) |
| GDAL | ab 2.3.0 (2018), optional; der Tag-Wert wurde in 2.3.3/2.4.0 geändert, mit 2.3.0 geschriebene Dateien sind später unlesbar | seit jeher | [GDAL NEWS-2.x.md](https://github.com/OSGeo/gdal/blob/master/NEWS-2.x.md) |
| rasterio-Wheels | zuverlässig erst nach Build-Fixes vom August 2022 | ja | [rasterio-wheels CHANGES.md](https://github.com/rasterio/rasterio-wheels/blob/main/CHANGES.md); [rasterio#2542](https://github.com/rasterio/rasterio/issues/2542) |
| QGIS macOS | **nein** in 3.44.8 (libtiff ohne ZSTD gebaut; 3.40.5 konnte es), offen seit 14.03.2026 | ja | [QGIS#65409](https://github.com/qgis/QGIS/issues/65409) |
| QGIS allgemein | Paketierungsfrage, vom Projekt als „not planned“ geschlossen | ja | [QGIS#51244](https://github.com/qgis/QGIS/issues/51244) |
| QGIS Windows (OSGeo4W) | in aktuellen Builds vermutlich ja | ja | unbelegt im Detail |
| QGIS Debian/Ubuntu | unbelegt | ja | — |
| ArcGIS Pro / ArcMap | in der Doku nicht als Kompression genannt (nur LZ77, PackBits, CCITT, JPEG, JPEG2000) | ja (LZ77) | nicht direkt gelesen |
| ESA SNAP | unbelegt; Reader delegiert an ImageIO-Ext | vermutlich ja | [GeoTiffProductReader.java](https://github.com/senbox-org/snap-engine/blob/master/snap-geotiff/src/main/java/org/esa/snap/dataio/geotiff/GeoTiffProductReader.java) |
| ENVI, ERDAS | unbelegt | unbelegt | — |
| MATLAB `geotiffread` | kein belegter Support | ja | [MathWorks](https://www.mathworks.com/help/map/ref/geotiffread.html) |
| Pillow | nur mit ZSTD-fähigem libtiff | ja | [TiffImagePlugin.py](https://github.com/python-pillow/Pillow/blob/main/src/PIL/TiffImagePlugin.py) |
| tifffile | braucht `imagecodecs` (ab Python 3.14 Stdlib-Fallback) | ja | [tifffile CHANGES.rst](https://github.com/cgohlke/tifffile/blob/master/CHANGES.rst) |
| geotiff.js | ab 3.0.0 (01/2024) | ja | [geotiff.js#451](https://github.com/geotiffjs/geotiff.js/pull/451) |
| rio-cogeo selbst | warnt bei ZSTD, WebP, LERC: „Non-standard compression schema … might not be fully supported by software not build against latest libtiff“ | keine Warnung | `rio_cogeo/profiles.py` Zeile 181–183 (7.0.3, lokal gelesen) |

**Fazit:** DEFLATE hängt an keiner optionalen Build-Abhängigkeit und fehlt in
keinem der gefundenen Programme. ZSTD fehlt nachweislich in mindestens einem
aktuellen QGIS-Installer und ist bei ArcGIS, SNAP und MATLAB nicht belegt.
Für eine Datei, die Nutzer in beliebiger Software öffnen, spricht das für F2
(1). Der Kachel-Pfad ist davon nicht berührt; er liefert PNG/WebP-Kacheln,
keine TIFF-Dateien.
