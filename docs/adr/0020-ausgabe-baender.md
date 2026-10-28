# ADR 0020 — Ausgabe-Bänder statt Bandauswahl

- **Status:** **Entwurf**, wartet auf Ottos Antworten zu §15 (F1–F13).
- **Datum:** 2026-10-28
- **Aufgabe:** NM4-43 laut `docs/plans/querschnitt/nm4-43-ausgabe-baender.md`
  (Backlog-Punkt 43 in `docs/plans/nach-m4-backlog.md`). Nimmt NM4-10 in sich
  auf.
- **Autonomiestufe:** C. Kein Produktivcode, keine Änderung an `backend/`,
  `frontend/`, Fixtures, `.github/`, `.claude/`, `CLAUDE.md` oder den
  Lock-Dateien. Neu sind nur die Messskripte `scripts/nm4-43-bands/measure.py`
  und `warp_bands.py` (§17). Die Umsetzung bekommt nach Ottos Entscheidung eigene Aufgaben (§13).
- **Vorab fest (Otto, 27.10.2026, Plan §2):**
  1. Keine Obergrenze für die Zahl der Bänder je Auftrag.
  2. Ein `band_math`-Schritt fügt ein neues Band hinzu, statt die Bänder zu
     ersetzen. Mehrere Schritte ergeben mehrere neue Bänder.
  3. Oben im Panel keine Auswahl mehr. Die Bänder des Datensatzes stehen dort
     nur zur Information und als Namenshilfe.
  4. Am Ende des Panels stehen alle Bänder des Datensatzes und alle neu
     gerechneten. Ein Klick nimmt ein Band in die Ausgabe auf oder heraus.
  5. Vorgabe: Nur die Band-Math-Ergebnisse sind in der Ausgabe. Andere Bänder
     kommen nur dazu, wenn der Benutzer sie anklickt.
  6. Mehrere `band_math`-Schritte laufen hintereinander, jeder mit anderen
     Bändern. Jeder sieht die Bänder des Datensatzes und die vorher neu
     gerechneten.
- **Grundlage:**
  - `KLAERUNGEN.md` B8, B9, B10; Regel vom 26.10.2026 (nicht Mögliches
    ausblenden, nur im Moment nicht Mögliches sperren mit Grund im Tooltip).
  - `architekturplan.md` 3.1, 7.1–7.3, 7.7.
  - `adr/0013` §5.2, §5.6, §5.7; `adr/0014` §4.1–§4.5, §5.5, §6.1–§6.3, §15c,
    §15k, §15m, §15n, §15s, §15t; `adr/0016` §6.1, §9; `adr/0019`.
  - Pläne NM4-07, NM4-10, NM4-11, NM4-14, NM4-20, NM4-05b, NM4-45, DS-06.
  - Entscheidungslog bis 27.10.2026 (M4-07b F5, M4-07a F11, M4-10b, NM4-07).
- **Betroffen:** `processing/recipe.py`, `processing/plan.py`,
  `processing/core.py`, `processing/operators/band_math.py` und
  `normalize.py`, `processing/tile.py`, `api/intake.py`, `api/tiler.py`,
  `api/processing_docs.py`, Runner; im Frontend Panel, Auftrag, Vorschau,
  Ergebnis-Layer, `recipeFile.ts`, `permalink.ts`, `jobShelf.ts`.

---

## Methode und Belegstufen

Gelesen und gemessen am 28.10.2026 auf dem Stand von `main` nach PR #214.
Belegstufen wie in `adr/0014`:

- **M:** in dieser Sitzung gemessen; Skript und Aufrufe in §17.
- **P:** am Primärtext gelesen: im Repo mit Pfad und Zeile, sonst die Datei im
  Repo des Herausgebers (`raw.githubusercontent.com`).
- **S:** Zusammenfassung einer Quelle, deren Wortlaut nicht geprüft ist (die
  Seite war aus der Sitzung nicht erreichbar).
- **F:** Forum oder Blog, kein Primärtext.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Werkzeuge.** Python 3.12.3 und das Projekt-venv (rasterio mit GDAL 3.12,
numexpr, numpy). Die Recherche lief in einem Hilfsagenten. Gesperrt bzw. nicht
auflösbar waren `docs.sentinel-hub.com`, `developers.google.com`,
`api.openeo.org`, `documentation.dataspace.copernicus.eu`,
`openeo.dataspace.copernicus.eu` und `forum.dataspace.copernicus.eu`. Primärtexte
kamen deshalb aus den Doku- und Spezifikations-Repos auf GitHub.

**Anfragen an Datenquellen.** Fünf Suchen an `earth-search.aws.element84.com`
(die letzte, maßgebliche nach einer MGRS-Kachel von rund 110 km, keine
Nutzer-AOI; sie ergibt dieselben 25 Szenen wie die Suchen davor) und die
Lesezugriffe von GDAL auf `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`,
deren Zahl §3.2 je Lauf nennt. Die Kachel steht im Aufruf (§17), wie die grobe
Kachelfläche in `scripts/tile-bench/run_tiler.py`. Koordinaten des
Messquadrats, Item-Kennungen und Adressen stehen weder hier noch in den
Ausgaben des Skripts.

**Warum `curl` für die Suche.** Der Client von `gateway` verbindet sich selbst
mit der aufgelösten Adresse und nutzt den HTTPS-Proxy der Cloud-Sitzung nicht;
die Suche über die Plattform scheiterte in dieser Sitzung mit
„could not be reached“ **[M]**. GDAL liest über den Proxy. Das Skript nimmt die
Items deshalb aus einer Datei, die `curl` geholt hat, und baut die Rezepte über
`api.intake.estimate_order` wie die Plattform; jede Adresse passiert dabei
`check_url` in `readers` wie im Worker.

---

## 0. Kurzfassung

1. **Rezeptmodell (F1): ein Vorrat an benannten Bändern, weiter eine lineare
   Kette.** Am Anfang enthält der Vorrat die Bänder des Datensatzes,
   `band_math` (Version 2) fügt ein Band mit eigenem Namen hinzu. `mask` und
   `reproject` wirken auf den ganzen Vorrat, `normalize` auf die Bänder, die
   der Schritt nennt (F4). Die Reihenfolge bleibt bedeutsam. Am Ende wählt
   `output.bands` aus, was in die Datei kommt.
2. **Gelesen wird nur, was gebraucht wird.** Der Planer streicht jedes Band,
   das weder in der Ausgabe steht noch von einem späteren Schritt gebraucht
   wird. Die Werte der übrigen Bänder ändern sich dadurch nicht, weil jeder
   Schritt je Band bzw. je Pixel rechnet **[A]**; nur `reproject` hängt heute
   an der Zahl der Bänder (Nebenbefund, §3.4, F13). Die Eingabe-Assets leitet
   `api` daraus ab; der Auftrag nennt sie nicht mehr (F2).
3. **Namen (F3):** Vorgabe `Band_Math_<n>` mit der Stelle des Schritts,
   umbenennbar (`NDVI`). Erlaubt sind `^[A-Za-z][A-Za-z0-9_]{0,31}$`, kein
   Python-Schlüsselwort und kein Funktionsname aus R5. Eindeutig ohne Rücksicht
   auf Groß- und Kleinschreibung, über alle Ergebnisse und alle Bänder des
   Datensatzes. Umbenennen zieht alle Verweise mit.
4. **Schutz ohne Bandgrenze (F5):** Gemessen wächst der Spitzenspeicher eines
   Laufs um rund 21 MB je Band im breitesten Durchgang und weniger mit der
   Fläche; 16 Bänder liegen schon über den 500 MB der Speichertests (§3.2).
   Laufzeit und gelesene Bytes wachsen mit Bändern mal Fläche, und die
   Zeitschätzung zählt die Ausgabebänder nicht (bei 30 km und 17 Bändern 21 s
   geschätzt, 115 s gemessen). Die bestehenden Grenzen (25 Items, 5 GB
   Ausgabe, Laufzeit 2 × Schätzung, Deckel 4 bzw. 2 Läufe) decken Fläche,
   Platte und Quellen, den Speicher deckt keine davon. Vorschlag: Die Grenze
   von 16 Assets entfällt; neu ist eine **Speicherschätzung je Lauf** gegen
   1,5 GB, gemessen statt gezählt, und die Zeitschätzung zählt die
   Ausgabebänder. Andere Plattformen begrenzen ebenso nach Datenmenge, Kosten
   und Zeit, keine nach Bandzahl als Hauptregel (§3.5).
5. **Nebenbefunde (F11, F13):** Die Schätzung bemisst das Ausgaberaster nach der
   Pixelgröße des **ersten** Assets, der Kern rechnet auf dem **feinsten**.
   Steht ein 60-m-Band vorn, liegen Ausgabegröße, die 5-GB-Prüfung und der
   Plattenbedarf um bis zu den Faktor 36 zu niedrig (§3.3). Das gilt schon
   heute und ist unabhängig von dieser Entscheidung zu beheben. Außerdem gibt
   `reproject` für dasselbe Band andere Werte, sobald die Zwischendatei 4 statt
   3 Bänder hat (GDAL teilt den Warp nach Speicher, §3.4).
6. **Ausgabedatei (F6):** eine COG, ein Datentyp für alle Bänder nach den
   heutigen Regeln (meist `float32`, weil der Kern physikalische Werte liefert),
   mit Banddeskription, Einheit und nodata je Band.
7. **Vorgabe ohne `band_math` (F7):** keines angehakt, außer der Datensatz hat
   nur ein Band. „Start“ ist dann gesperrt mit Grund im Tooltip.
8. **Vorschau (F8):** eine Auswahl „Show“ über die Bänder der Ausgabe, Vorgabe
   ist das letzte Band-Math-Ergebnis. Die Kachel rechnet nur dieses eine Band
   und liest nur, was es braucht. Derselbe Baustein dient am Ergebnis-Layer und
   in der Ansicht aus NM4-45. RGB aus drei Bändern kommt später.
9. **Versionen (F9):** `recipe_version` 2, `band_math` Version 2, `normalize`
   Version 2 (mit NM4-11), `earthx.__version__` 0.5.0, Nachträge in
   `adr/0014` und `adr/0016`. Rezepte der Version 1 deutet das Frontend um
   (Datei, Permalink, Ablage), mit Hinweis. `api` und der neue Runner weisen
   Version 1 mit Grund ab; bis 7 Tage nach dem Frontend-Umbau deutet `api`
   sie übergangsweise selbst um (§11).
10. **Schnitt (F10):** zuerst der Nebenbefund (Stufe A), dann NM4-43a
    Rezept und Kern, NM4-43b Kachel und Vorschau-Route, NM4-43c Frontend.
    NM4-11, NM4-14, DS-06 und NM4-20 folgen danach (§12, §13).

---

## 1. Kontext und Frage

Heute bestimmt die Bandauswahl oben im Panel die Eingabe **[P]**
(`frontend/src/processingOrder.ts:249–264`, `orderAssets`): gewählte Bänder,
dazu die Bänder aus Ausdrücken und die Maskenschicht. Ohne `band_math` ist die
Eingabe zugleich die Ausgabe. Mit `band_math` ersetzt der Schritt alle Bänder
durch das eine Ergebnisband `band_math`
(`backend/earthx/processing/operators/band_math.py:61`, `:221`). Weitere
gewählte Bänder kosten dann Laufzeit und erscheinen nicht in der Datei. Die
Grenze von 16 Assets (`api/intake.py:153`, M4-07b F5) war ein Startwert vom
07.10.2026 und ist nie gemessen worden.

Otto will das umdrehen (Vorab fest 1–6): Die Ausgabe wird am Ende gewählt, die
Eingabe folgt daraus, und Band-Math-Ergebnisse sind Bänder wie die des
Datensatzes. Dieses ADR legt die zehn Punkte aus Plan §3 vor.

## 2. Kriterien

| # | Kriterium | Quelle |
|---|---|---|
| K1 | Das Rezept beschreibt Eingabe, Schritte und Ausgabe vollständig und eindeutig | `adr/0014` K1 |
| K2 | Gelesen und gerechnet wird nur, was die Ausgabe braucht | Plan §3.2 |
| K3 | Kachel (T1), Job (T2) und Runner (T2L) bleiben bitgleich | `adr/0014` F9, §15c |
| K4 | Worker, Speicher und Quellen bleiben geschützt, auch ohne Bandgrenze | Plan §3.4; `adr/0013` §5.7 |
| K5 | Nichts gilt still: Namen, Vorgaben und Umdeutungen sind ausdrücklich | B10; `adr/0014` K7 |
| K6 | Wenige bewegliche Teile; keine neue Abhängigkeit | `adr/0014` K9 |
| K7 | Wenig Text im Panel; nicht Mögliches ausblenden, nur im Moment nicht Mögliches sperren | Regel vom 26.10.2026; UI-01 §4 |
| K8 | Anschlussfähig an openEO und STAC | `adr/0014` K10 |

---

## 3. Befunde

### 3.1 Das heutige Modell — [P]

- **Kette:** `steps` ist eine lineare Folge; jeder Schritt bekommt die Bänder,
  die der vorige lässt (`processing/plan.py:126`, `core.py:_pixel_kernels`).
- **`band_math`** ersetzt alle Bänder durch eines (`band_math.py:221`,
  `_transform` `:224`).
- **`mask`** entfernt die Klassifizierungsschicht aus dem Ergebnis
  (`mask.py:90–96`); **`normalize`** wirkt auf alle Bänder
  (`normalize.py:55–74`); **`reproject`** auf das ganze Raster.
- **Gelesen** wird jedes Asset des Auftrags in jedem Block
  (`core.py:_open_sources`, `merge_images`), auch wenn ein Ausdruck es nicht
  braucht.
- **`result.tif`** trägt keine Banddeskriptionen; Namen, Einheiten und
  Statistik stehen nur in den STAC-Eigenschaften (`core.py:_properties`).
- **Grenzen:**

| Grenze | Wert | Stelle |
|---|---|---|
| Items je Auftrag | 25 | `api/intake.py:152`; Batch `frontend/src/processingBatch.ts:12` |
| Assets je Auftrag | 16 | `api/intake.py:153`; Panel `processingOrder.ts:86`, `:500` |
| Schritte je Auftrag | 16 | `api/intake.py:154` |
| Ausgabe je Job (Daten + Maske) | 5 GB | `access/crop_rules.py:121`; Prüfung `processing/plan.py:360` |
| Laufzeit je Job | 2 × Schätzung, mindestens 600 s | `jobs/submit.py:60–61` |
| Gleichzeitige Läufe | 4 gesamt, 2 je Quell-Host | `catalog/migrations/006_jobs.sql:37` |
| Slots je Worker-Container | 2 | `jobs/config.py:33` |
| Platz im Arbeitsverzeichnis | Schätzung `disk_needed` | `jobs/worker.py:280` |
| Kachel mit Schritten | 16 Assets, 4 Schritte, 2048 Zeichen Parameter | `api/tiler.py:420–422` |
| Mosaik-Kachel mit Schritten | 4 Assets, 7168 Byte | `api/mosaic_tiles.py:80`, `:83` |
| Vorschau im Panel | 16 Assets, 4 Schritte, 40 Szenen | `frontend/src/processingPreview.ts:18–22` |

- **Speicher:** Es gibt keine harte Grenze je Kindprozess; `setrlimit` kommt
  in `jobs` nicht vor. Die Tests begrenzen `VmHWM` eines Laufs auf 500 MB
  (M4-07a F11, Log 06.10.2026), gemessen mit einem oder zwei Bändern.
- **Kosten:** Die Schätzung zählt `units` als Ausgabepixel mal
  Operatorfaktor, **ohne die Zahl der Bänder** (`plan.py:373`). Die Sekunden
  enthalten die Eingabebytes und wachsen also mit den Bändern (`plan.py:372`).

### 3.2 Messung: Bänder, Szenen, Band-Math — [M]

**Aufbau.** Sentinel-2 L2A (`sentinel-2-c1-l2a`), eine MGRS-Kachel, 25 ganze
Szenen verschiedener Tage, ein Quadrat von 10 km (rund 1,06 Mio. Pixel bei 10 m)
mitten in der gemeinsamen Fläche. Je Szene ein Lauf von `processing.core.run`
in einem eigenen Kindprozess mit `worker_environment()`, wie im Worker.
Ausgabe `float32`. Gemessen: Wandzeit des Laufs, Spitzen-RSS (`ru_maxrss`)
des Kindprozesses, Bytes und Anfragen von GDAL
(`CPL_VSIL_SHOW_NETWORK_STATS`), Größe von `result.tif`. Daneben die Schätzung
der Plattform für dasselbe Rezept.

**Konfigurationen.** Bänder: 2 (`red`, `nir`); 16 (alle Daten-Assets ohne
`scl`, das nimmt „Select all bands“ heute); 17 (alle Daten-Assets). Schritte:
keiner; `band_math` wie heute (NDVI, eine Ausgabe); `band_math_append`, ein
Operator nur im Skript, der das NDVI als weiteres Band anhängt, also das Modell
dieses ADR. „25 Szenen“ heißt 25 Läufe, so wie „Run as: one per scene“ einen
Batch von 25 Jobs macht (`processingBatch.ts:12`); ein Lauf mit 25 Szenen in
einer Gruppe ist ein Mosaik eines Überflugs, bei dem je Block nur die Szenen
gelesen werden, die ihn berühren (`processing/mosaic.py`, Kopf).

Je Konfiguration 25 Läufe (25 Szenen), keiner fehlgeschlagen. Median je Lauf,
Spitze als Höchstwert über die 25 Läufe, Summe über alle 25:

| Konfiguration | Bänder gelesen → in der Datei | s je Lauf | s für 25 Szenen | Spitzen-RSS MB | gelesen MB je Lauf | gelesen MB, 25 Szenen | GETs je Lauf | `result.tif` MB | Schätzung s | Schätzung Ausgabe MB |
|---|---|---|---|---|---|---|---|---|---|---|
| 2, kein Schritt | 2 → 2 | 3,5 | 94 | 275 | 12,7 | 319 | 4 | 6,5 | 2,1 | 8,5 |
| 2, `band_math` heute | 2 → 1 | 2,8 | 70 | 248 | 12,7 | 319 | 4 | 4,8 | 2,1 | 4,2 |
| 2, `band_math` anhängen | 2 → 3 | 3,9 | 104 | 297 | 12,7 | 319 | 4 | 11,9 | 2,1 | 12,7 |
| 16, kein Schritt | 16 → 16 | 19,3 | 497 | 518 | 37,1 | 933 | 32 | 32,4 | 16,4 | 1,9 |
| 16, `band_math` heute | 16 → 1 | 11,9 | 305 | 387 | 37,1 | 933 | 32 | 4,8 | 16,4 | 0,1 |
| 16, `band_math` anhängen | 16 → 17 | 20,7 | 546 | 624 | 37,1 | 933 | 32 | 44,4 | 16,4 | 2,0 |
| 17, kein Schritt | 17 → 17 | 19,4 | 520 | 536 | 37,2 | 935 | 34 | 38,7 | 17,4 | 2,0 |
| 17, `band_math` heute | 17 → 1 | 11,0 | 291 | 395 | 37,2 | 935 | 34 | 4,8 | 17,4 | 0,1 |
| 17, `band_math` anhängen | 17 → 18 | 22,3 | 570 | 648 | 37,2 | 935 | 34 | 45,0 | 17,4 | 2,1 |

Der Sockel des Kindprozesses nach den Imports liegt bei 166 MB. Die Spitze
streut über die 25 Szenen um höchstens 6 MB, die Laufzeit stärker (Netz:
16 Bänder 11,0–22,3 s mit `band_math`). Die Schätzung der Ausgabe ist bei 16 und
17 Bändern falsch, siehe §3.3.

**Befunde.**

1. **Speicher wächst mit den Bändern im Durchgang**, rund 17–18 MB je Band
   (2 → 17 Bänder ohne Schritt: 275 → 536 MB). Das sind etwa zwei Kopien
   eines Blocks von 1024² in `float64` je Band. Schon 16 Bänder liegen über
   den 500 MB, die die Speichertests für einen Lauf erlauben (§3.1).
2. **`band_math` wie heute liest alle gewählten Bänder** und schreibt eines:
   16 Bänder kosten 387 statt 248 MB und 11,9 statt 2,8 s für dasselbe NDVI.
   Das Streichen aus §4 spart genau das.
3. **Anhängen kostet ein Band mehr** in Datei und Statistik. Das Skript hängt
   naiv an (`numpy.ma.concatenate` kopiert den Vorrat je Block); daher
   +112 MB gegenüber „kein Schritt“. Eine Umsetzung, die das Ergebnis neben
   den Vorrat legt statt ihn zu kopieren, sollte nahe an „kein Schritt +
   ein Band“ liegen **[A]**; das misst NM4-43a.
4. **Laufzeit:** Bei 1 Mio. Pixeln bestimmen Öffnen, Lesen, Schreiben und
   Statistik je Band die Zeit. 17 statt 2 Bänder kosten das 5,5-Fache
   (19,4 statt 3,5 s). Die Schätzung trifft die Größenordnung (17,4 bzw. 2,1 s).
5. **Gelesene Bytes:** 12,7 MB für 2 Bänder, 37 MB für 16 oder 17. Das ist nur
   das 2,9-Fache, weil die 20- und 60-m-Bänder ein Viertel bzw. ein Neuntel der
   Pixel haben. Je Band zwei Anfragen (Kopf und Daten). 25 Szenen sind 25-mal
   so viel; der Deckel je Host (2) bestimmt, wie viel davon gleichzeitig läuft.
6. **Ausgabe:** 17 Bänder in `float32` mit deflate sind 38,7 MB je 1 Mio.
   Pixel, gegenüber 6,5 MB für zwei. Die Klassenschicht `scl` als `float32`
   kostet 6,3 MB (32,4 → 38,7 MB).
7. **Nicht gemessen:** ein Mosaik von 25 Szenen in einem Lauf. Je Block liest
   der Kern nur die Szenen, die ihn berühren, und hört auf, sobald alle Pixel
   gefüllt sind (`processing/mosaic.py`, Kopf); `api` lässt Szenen weg, die die
   AOI nicht berühren. Die Spitze hängt dort wie hier an den Bändern je Block;
   Laufzeit und Bytes wachsen mit der Fläche.

**Flächenreihe.** Eine Szene (die erste der 25), Quadrate von 3, 10 und 30 km
um die Mitte dieser Szene (0,1, 1,1 und 9,5 Mio. Pixel), je ein Lauf. Das
10-km-Quadrat liegt damit an anderer Stelle als in der Tabelle oben:

| Konfiguration | 3 km: s / Spitze MB | 10 km: s / Spitze MB | 30 km: s / Spitze MB | 30 km: gelesen MB | 30 km: `result.tif` MB | 30 km: Schätzung s |
|---|---|---|---|---|---|---|
| 2, kein Schritt | 2,1 / 216 | 3,5 / 276 | 12,2 / 338 | 59 | 60 | 3,2 |
| 2, `band_math` heute | 1,3 / 198 | 2,9 / 250 | 9,3 / 314 | 59 | 44 | 3,2 |
| 17, kein Schritt | 9,3 / 406 | 22,1 / 536 | 114,7 / 651 | 266 | 346 | 21,0 |
| 17, `band_math` heute | 7,7 / 217 | 12,8 / 396 | 49,4 / 426 | 266 | 44 | 21,0 |
| 17, `band_math` anhängen | 8,7 / 418 | 23,4 / 649 | 141,9 / 911 | 266 | 403 | 21,0 |

8. **Die Spitze hängt vor allem an den Bändern, aber auch an der Fläche.**
   Unter 1024 px Seitenlänge sind die Blöcke kleiner (3 km). Von 1,1 auf
   9,5 Mio. Pixel wächst sie bei 17 Bändern um 115 MB, bei 2 Bändern um 62 MB.
   Bei 9,5 Mio. Pixeln gilt etwa **300 MB + 21 MB je Band** im breitesten
   Durchgang (Gerade durch 2 und 17 Bänder, kein Schritt: 296 MB Sockel,
   20,9 MB je Band). Einen Teil des Flächenanteils trägt vermutlich der
   COG-Schritt am Ende, den `adr/0014` §3.5 mit rund 100 MB nennt **[A]**.
   Gemessen ist nur bis 9,5 Mio. Pixel; die 5-GB-Grenze erlaubt bei 17
   Bändern rund 72 Mio. Pixel. Wie die Spitze dorthin wächst, misst NM4-43a
   (§7.2).
9. **Die Zeitschätzung wächst nicht mit den Bändern der Ausgabe.** Bei 30 km
   und 17 Bändern schätzt die Plattform 21 s, gemessen sind 115 s (Faktor 5,5;
   bei 2 Bändern 3,2 gegen 12,2 s). `SECONDS_PER_INPUT_MB` stammt aus einem
   Band-Math-Lauf mit 2 Bändern und einem Band Ausgabe (`plan.py:71`).
   Schreiben, Statistik und COG je Ausgabeband fehlen. Heute fängt die
   Untergrenze von 600 s das auf. Linear hochgerechnet **[A]** braucht ein
   Job mit 17 Bändern an der 5-GB-Grenze (rund 72 Mio. Pixel in `float32`) etwa
   870 s; die Grenze wäre 2 × 47 s, also die Untergrenze von 600 s, und der
   Job bräche ab.

### 3.3 Nebenbefund: Die Schätzung nimmt das Raster des ersten Assets — [M] [P]

`_input_meta(sized=True)` bemisst das Raster der Schätzung mit dem `gsd` des
ersten Eintrags (`processing/plan.py:298`). Der Kern liest alle Assets auf das
**feinste** Raster (`processing/source.py:common_grid`). Die Folge in der
Messung: Bei 17 Bändern mit `coastal` (60 m) vorn schätzt die Plattform die
Ausgabe auf 2,0 MB roh, geschrieben werden 38,7 MB nach deflate, roh
rund 72 MB (§3.2). Das ist ein Faktor 36, weil 60 m statt 10 m. Bei `red` vorn stimmt die
Schätzung.

- Betroffen sind `estimate` (Ausgabebytes, die 5-GB-Prüfung `JobTooLarge`,
  `units`) und `disk_needed` (der Durchgang in `float64` wird je Asset mit
  dessen eigenem `gsd` bemessen, `plan.py:478–486`).
- Das Panel ordnet die Assets nach dem Item (`red` zuerst), über die API ist
  die Reihenfolge frei. Ein Auftrag `["coastal", "red"]` über eine große Fläche
  kommt also an der 5-GB-Prüfung vorbei und scheitert erst im Lauf **[A]**.
- Behebung: das Raster aus dem kleinsten `gsd` aller Assets bemessen. Das ist
  eine kleine Änderung mit Test, unabhängig von diesem ADR (F11).

### 3.4 Nebenbefund: `reproject` hängt an der Zahl der Bänder — [M]

Der Durchgang von `reproject` liest je Block aus einem `WarpedVRT` über **alle**
Bänder der Zwischendatei (`processing/operators/reproject.py:_run`). GDAL teilt
den Warp nach `warp_mem_limit` (64 MB) auf, und diese Teilung hängt an der Zahl
der Bänder. Gemessen mit `scripts/nm4-43-bands/warp_bands.py` (synthetisch,
2048², `float64` wie die Zwischendatei, `bilinear` nach EPSG:3035): Band 1 ist
bei 1, 2 und 3 Bändern bitgleich; ab 4 Bändern weichen 96 % seiner Pixel ab
(4 136 158 von 4 303 544, größte Abweichung 0,0077 bei Werten bis 0,5; zwölf
Randpixel wechseln zwischen gültig und NaN). 4, 18 und 34 Bänder ergeben
untereinander dieselben Werte.

- **Heute schon:** Dasselbe Band hat nach `reproject` andere Werte, je nachdem,
  ob der Auftrag 3 oder 4 Bänder trägt. Bitgleichheit Job ↔ Runner gilt weiter
  (dasselbe Rezept, dieselben Bänder); die Kachel rechnet `reproject` nicht.
- **Für dieses ADR:** Das Streichen ungenutzter Bänder (§4) ändert die Zahl der
  Bänder vor `reproject` und damit dessen Werte. Es bleibt deterministisch, weil
  das Rezept die Bänder festlegt, aber der Wert eines Bandes hinge an seinen
  Nachbarn in der Ausgabe.
- **Abhilfe [A]:** `reproject` Version 4 warpt jedes Band für sich (je Band ein
  Warp mit festem Plan). Dann hängt der Wert eines Bandes nur noch an ihm selbst.
  Kosten und Bitgleichheit misst die Umsetzung (F13).

### 3.5 Wie andere Plattformen begrenzen — [P] [S] [F]

| Plattform | Art der Grenze | Wert | Beleg |
|---|---|---|---|
| openEO API | Budget je Nutzer und je Auftrag, Schätzung `GET /jobs/{id}/estimate` mit `costs`, `duration`, `size`; Fehler `ProcessGraphComplexity`, `PaymentRequired`, `StorageQuotaExceeded` | keine Zahlen in der Spezifikation | [P] openeo-api `openapi.yaml`, `errors.json` |
| openEO `filter_bands` | Auswahl nach Name, Common Name oder Wellenlänge | keine Obergrenze für Bänder | [P] openeo-processes `filter_bands.json` |
| CDSE openEO | Credits: synchron fest 6 je Anfrage; Batch nach CPU-Sekunden, GB-Sekunden Speicher und Speichertagen | Beispiel 5099 CPU-s = 2,12 Credits | [P] eu-cdse `credit_usage.qmd` |
| CDSE openEO | Kontingente | 2 parallele Verarbeitungen, 10 000 Credits/Monat; synchron 5 min Timeout | [P] eu-cdse `Quotas.qmd`, `federation/backends/api.qmd` |
| CDSE/VITO openEO | Speicher je Executor als Auftragsparameter, Höchstwert je Instanz | Fehlermeldung nennt etwa 24 G | [S] `processing_parameters`; [P] openeo-python-driver Issue 468 |
| Sentinel Hub | Processing Units: 1 PU = 512 × 512 px, 3 Eingabebänder; **Faktor Eingabebänder / 3**; `FLOAT32` × 2 | — | [P] eu-cdse `ProcessingUnit.qmd` |
| Sentinel Hub Process API | Ausgabe höchstens 2500 × 2500 px je Anfrage; größer nur Batch | — | [F] Forum |
| Sentinel Hub Batch | Processing Units mit Faktor 1/3 gegenüber der Process API | — | [P] eu-cdse `Batch.qmd` |
| Sentinel Hub | Ausgabebänder | keine Obergrenze gefunden; `sampleType` gilt je Ausgabeobjekt, nicht je Band | [P] sentinelhub-py `evalscript.py`; [S] Evalscript V3 |
| Earth Engine `getDownloadURL` | Anfragegröße | 32 MB, höchstens 10 000 px je Seite | [P] earthengine-api `image.py` |
| Earth Engine `computePixels` | Pixel × Bänder × Bytes; Bänder | 48 MB; **höchstens 1024 Bänder** | [S] REST-Referenz |
| Earth Engine Export | `maxPixels` | Vorgabe 1e8 | [P] earthengine-api `batch.py` |
| Earth Engine | Speicher je Anfrage, Rechenzeit (EECU) | fest, ohne veröffentlichte Zahl; Quoten je Tarif | [S] `guides/usage`, `noncommercial_tiers` |
| Earth Engine Export | gemischte Typen | Export verlangt einen gemeinsamen Typ, üblich `toFloat()` | [F] Blogs |
| TiTiler | Vorschau | `max_size` 1024 | [P] titiler `endpoints/cog.md` |

**Fazit [A].** Keine dieser Plattformen hat „höchstens N Bänder je Auftrag“ als
Hauptregel. Es gibt zwei Stufen: harte Grenzen für synchrone, interaktive
Anfragen (Pixel, Bytes oder Zeit) und Kosten oder Kontingente für
Batch-Aufträge. Die Bandzahl geht als Kostenfaktor ein (Sentinel Hub) oder als
Teil der Bytegröße (Earth Engine). Die einzige harte Bandgrenze (1024 bei
`computePixels`) ist eine Plausibilitätsgrenze. Für gemischte Typen verlangen
Sentinel Hub und Earth Engine einen gemeinsamen Typ je Ausgabe.

---

## 4. Rezeptmodell (Punkt 1)

**Optionen:**

| | V1 Bandvorrat, lineare Kette | V2 zwei Phasen | V3 Graph |
|---|---|---|---|
| Idee | Der Vorrat beginnt mit den Bändern des Datensatzes. Jeder Schritt wirkt an seiner Stelle; `band_math` fügt ein Band hinzu. Am Ende wählt `output.bands` | erst alle `band_math`-Schritte (jeder fügt hinzu), dann `mask`, `normalize`, `reproject` auf die Ausgabe | jeder Schritt nennt seine Eingaben und seinen Ausgang (openEO-Prozessgraph) |
| Vorab fest 2, 6 | ✓ | ✓ | ✓ |
| Reihenfolge | bedeutsam wie heute; „NDVI aus maskierten Bändern“ und „maskiertes NDVI“ sind dasselbe, „NDVI nach Reprojektion“ ist ein anderes | fest vorgegeben; NDVI nach einer Reprojektion geht nicht | frei |
| K2 nur Nötiges | ✓ mit Streichen ungenutzter Bänder (unten) | ✓ | ✓ |
| K3 bitgleich | ✓ wie heute | ✓ | ✓ |
| K6 einfach | ✓ kleine Änderung an Kette, Planer und `band_math` | ~ zweite Regel für das Panel | ✗ DAG, Verweise, Validierung (`adr/0014` R3 verworfen) |
| K8 openEO | ✓ mechanisch übersetzbar | ✓ | ✓ direkt |

**Empfehlung: V1.** Sie ändert am wenigsten: Die Kette bleibt linear, nur
`band_math` ersetzt nicht mehr, sondern fügt hinzu.

**Worauf die Schritte wirken (V1):**

| Schritt | wirkt auf | Änderung zu heute |
|---|---|---|
| `band_math` v2 | liest die Bänder, die der Ausdruck nennt; fügt ein Band `name` hinzu | ersetzt nicht mehr |
| `mask` | blendet in allen Bändern des Vorrats aus, auch in der Schicht selbst | die Schicht bleibt im Vorrat; ob sie in die Datei kommt, entscheidet `output.bands`. Steht sie in der Ausgabe, sind ihre ausgeblendeten Klassen dort nodata |
| `normalize` v2 | die Bänder in `bands` (F4) | heute alle Bänder |
| `reproject` | alle Bänder des Vorrats | keine |

**Streichen ungenutzter Bänder.** Der Planer geht die Kette von hinten durch.
Ein Band bleibt, solange es in `output.bands` steht oder ein späterer Schritt es
braucht: ein Ausdruck, die Schicht von `mask`, ein Band in `normalize.bands`.
Alles andere fällt nach seiner letzten Nutzung weg, und was nie gebraucht wird,
wird nicht gelesen. Die Werte der übrigen Bänder ändern sich dadurch nicht,
weil `band_math` und `normalize` je Band und `mask` je Pixel aus der Schicht
rechnen **[A]**. **Ausnahme `reproject`:** Seine Werte hängen heute an der Zahl
der Bänder (§3.4). Mit `reproject` Version 4, die jedes Band einzeln warpt,
gilt die Regel auch dort (F13). Ein Test vergleicht je Operator „mit Streichen“
gegen „ohne Streichen“ bitgleich.

**Beispiel.** Ottos Fall: NDVI aus B04/B08, NDWI aus B03/B08, Ausgabe beide:

```json
"steps": [
  {"op": "mask", "op_version": 2, "params": {"source": "scl", "classes": [3, 8, 9, 10]}},
  {"op": "band_math", "op_version": 2, "params": {"expression": "(nir-red)/(nir+red)", "name": "NDVI"}},
  {"op": "band_math", "op_version": 2, "params": {"expression": "(green-nir)/(green+nir)", "name": "NDWI"}}
],
"output": {"kind": "raster", "format": "cog", "dtype": "float32", "bands": ["NDVI", "NDWI"]}
```

Gelesen werden `scl`, `red`, `nir`, `green`. Nach dem dritten Schritt bleiben
nur `NDVI` und `NDWI`.

---

## 5. Ausgabe im Rezept (Punkt 2)

| | A1 `output.bands`, Assets abgeleitet | A2 `output.bands` und `assets` im Auftrag | A3 eigene Liste `outputs` neben `output` |
|---|---|---|---|
| Form | `output.bands: ["NDVI", "red"]`, Reihenfolge = Bandfolge der Datei; `inputs[].assets` setzt `api` | wie A1, der Auftrag nennt zusätzlich `assets`; `api` prüft, dass sie genau die abgeleiteten sind | `outputs: [...]` auf oberster Ebene |
| K1 eindeutig | ✓ eine Quelle der Wahrheit | ~ zwei Angaben, die sich widersprechen können | ✓ |
| Rezept (angenommen) | `assets` steht weiter drin, abgeleitet; Hash und Runner sehen alles | gleich | gleich |
| Panel | einfacher: Es schickt die Ausgabe, keine Asset-Liste | muss die Ableitung nachbauen | wie A1 |
| `output` gehört zur Ausgabe | ✓ | ✓ | ✗ zwei Stellen für die Ausgabe |

**Empfehlung: A1.**

- `output.bands`: mindestens ein Name, jeder einmal, jeder steht am Ende der
  Kette im Vorrat. Ein leerer Auftrag wird mit `422` abgewiesen.
- `inputs[].assets` fällt aus dem **Auftrag** für die Ausgabe `raster` weg.
  `api` leitet die Assets aus dem Streichen (§4) ab und schreibt sie ins
  **Rezept**. `recipe.json`, Hash und Runner bleiben damit vollständig.
- Die Zuordnung Bandname → Asset kennt `api` schon (`describe_bands`,
  `processing/source.py:expected_band_names`). Ein Name, der zu keinem Asset
  gehört, wird mit `422` und dem Namen abgewiesen.
- Die Ausgabe `crop` (Export, M4-11a) bleibt, wie sie ist: Sie hat keine
  Schritte und nennt ihre Assets.

---

## 6. Namen neu gerechneter Bänder (Punkt 3, aus NM4-10)

**Vorgabe.** `Band_Math_<n>`, `n` ist die Stelle des Schritts in der Kette,
ab 1. Schritt 1 heißt im Panel „1. Band_Math_1“. Die Vorgabe setzt das Panel.
Im Rezept steht der Name immer ausdrücklich (B10); `band_math` v2 hat keinen
Default für `name`.

**Eigener Name.** Je Schritt umbenennbar, etwa `NDVI`. Er steht im Rezept, im
Schritt-Titel, auf dem Chip, als Banddeskription in `result.tif` und in den
STAC-Eigenschaften.

**Regeln (Vorschlag):**

| Regel | Grund |
|---|---|
| `^[A-Za-z][A-Za-z0-9_]{0,31}$` | gleiche Zeichen wie `Name` im Rezept (`recipe.py:99`) und wie ein Bandname in R5; 32 Zeichen passen auf einen Chip |
| kein Python-Schlüsselwort (`in`, `and`, `not`, `if`, `True` …) | `ast.parse` liest es nicht als Namen (`band_math.py:check_expression`) |
| kein Funktionsname aus R5 (`where`, `abs`, `minimum`, `maximum`, `sqrt`) | wird heute schon als Bandname abgewiesen (`band_math.py:113`) |
| eindeutig ohne Rücksicht auf Groß- und Kleinschreibung über alle Ergebnisse der Kette | `NDVI` und `ndvi` nebeneinander wären verwechselbar; numexpr unterscheidet sie |
| keine Kollision mit einem Band des Datensatzes, ebenfalls ohne Groß- und Kleinschreibung, auch mit Bändern, die nicht gelesen werden | sonst würde ein später angehaktes Quellband das Ergebnis verdecken |

`api` prüft die Kollision gegen die Bänder, die die Collection beschreibt;
der Kern prüft sie zusätzlich am Vorrat (`_transform`). Der Text der
Abweisung nennt den Namen und den Grund, etwa „NDVI is used twice“.

**Umbenennen.** Das Panel ersetzt den alten Namen in allen späteren
Ausdrücken, in `normalize.bands`, in der Maske (DS-06) und in `output.bands`,
token-genau über denselben Zerleger wie die Chips. Kein Hinweis nötig, weil
nichts verloren geht. Ein Name, der einen Konflikt ergäbe, wird nicht
übernommen; das Feld zeigt den Grund im Tooltip.

---

## 7. Schutz ohne Bandgrenze (Punkt 4)

### 7.1 Was die Messung sagt

- **Speicher:** Keine bestehende Grenze schützt ihn. Die Spitze wächst um
  rund 21 MB je Band im breitesten Durchgang und weniger mit der Fläche
  (Befund 8); schon 16 Bänder liegen über den 500 MB der Speichertests. Bei
  Sentinel-2 kann der Vorrat höchstens 17 Bänder plus ein Band je
  `band_math`-Schritt haben, also 33; das ergibt nach der Formel bei
  9,5 Mio. Pixeln rund 1,0 GB. Ein Datensatz mit vielen Bändern in einem Asset
  (hyperspektral, etwa 224) käme auf rund 5 GB **[A]**. Gestrichen wird je
  Band, gelesen aber je Asset: Ein Asset mit vielen Bändern wird ganz gelesen,
  auch wenn nur eines gebraucht wird.
- **Laufzeit:** Die Grenze (2 × Schätzung, mindestens 600 s) schützt den
  Worker, ist aber für viele Ausgabebänder zu knapp, weil die Schätzung sie
  nicht zählt (Befund 9). Das gilt schon heute mit 16 Bändern: Ein gültiger
  großer Job bräche ab.
- **Platte und Ausgabe:** Die 5-GB-Grenze zählt Pixel × Bänder × Typ, wächst
  also mit den Bändern; `disk_needed` ebenso. Beide sind heute durch den
  Nebenbefund §3.3 zu niedrig.
- **Quellen:** Je Band zwei Anfragen. 17 Bänder sind 34 Anfragen je Szene, ein
  Batch von 25 Szenen 850; der Deckel je Host (2 gleichzeitige Läufe) und die
  Wiederholung mit Backoff in `gateway` begrenzen die Rate. Eine eigene Grenze
  braucht es dafür nicht **[A]**.
- **Zahl der Szenen:** Die 25 Items je Auftrag bzw. 25 Jobs je Batch bleiben;
  25 Szenen sind 25-mal ein Lauf (§3.2).

### 7.2 Optionen

| | G1 nur die bestehenden Grenzen | G2 Speicherschätzung je Lauf | G3 Datenmenge der Eingabe |
|---|---|---|---|
| Regel | 16 Assets entfällt, sonst nichts | 16 Assets entfällt; neu: geschätzter Spitzenspeicher ≤ Grenze je Kindprozess | 16 Assets entfällt; neu: Pixel × Bänder × Szenen der Eingabe ≤ Grenze |
| schützt Speicher | ✗ | ✓ unmittelbar | ~ nur mittelbar; der Speicher hängt vor allem an den Bändern je Block, weniger an der Fläche |
| schützt Laufzeit, Platte, Quellen | ✓ Laufzeitgrenze, 5 GB, `disk_needed`, Deckel je Host | ✓ wie G1 | ✓ doppelt zu G1 |
| trifft Sentinel-2 (≤ 33 Bänder im Vorrat) | — | bis 9,5 Mio. Pixel nicht (rund 1,0 GB); große Flächen und Mosaik misst NM4-43a | je nach Wert |
| trifft Hyperspektral (etwa 224 Bänder in einem Asset) | — | ja, mit Zahl im Grund | ja |
| neue Zahl, die gepflegt werden muss | keine | ein Wert je Band, gemessen, im Speichertest geprüft | eine Grenze ohne gemessenen Bezug |

**Empfehlung: G2,** dazu die Behebung aus §3.3 (F11).

- **Formel:** 300 MB plus 21 MB je Band im breitesten Durchgang (Befund 8),
  dazu ein Flächenanteil, den NM4-43a bis zur 5-GB-Grenze und für ein Mosaik
  misst. Der Planer kennt den breitesten
  Durchgang nach dem Streichen (§4). Die Werte misst NM4-43a mit dem echten
  Anhängen neu.
- **Grenze:** ein Wert je Kindprozess (F5), Startwert **1,5 GB**: Sentinel-2
  mit 17 Bändern und 16 `band_math`-Schritten (rund 1,0 GB bei 9,5 Mio. Pixeln)
  passt, ein
  hyperspektrales Asset nicht. Ein Worker mit 2 Slots braucht dann bis zu
  3 GB. Darüber `413` mit Grund, etwa
  „This job would need about 2.4 GB of memory, more than the 1.5 GB a job may
  use. Put fewer bands in the output.“
- **Test:** Der bestehende Speichertest bekommt einen Lauf mit 17 Bändern; er
  prüft, dass die Messung unter der Schätzung bleibt.
- **Zeitschätzung:** Die Sekunden zählen künftig Ausgabepixel mal
  Ausgabebänder mit einem gemessenen Wert je Band (Befund 9), damit die
  Laufzeitgrenze (2 × Schätzung) auch für viele Bänder hält.
- **Kosten:** `units` zählt künftig die Bänder mit (Ausgabepixel × Bänder der
  Ausgabe × Faktor), damit die Einheiten für M6 (Quoten) mit der Last wachsen,
  wie bei Sentinel Hub **[A]**.
- **Bleibt:** 25 Items, 16 Schritte, 5 GB Ausgabe, Laufzeit, Deckel, Platte.
  Mehr Bänder als `16 + Bänder des Datensatzes` kann es ohnehin nicht geben.
- **Kachel:** Die Grenzen der synchronen Wege bleiben (16 Assets je Kachel,
  4 je Mosaik-Kachel). Sie greifen seltener, weil die Kachel nur das gezeigte
  Band rechnet (§10).

---

## 8. Ausgabedatei (Punkt 5)

**Befund.** Der Kern liefert physikalische Werte. Skalierte Bänder wie die
Reflexion von Sentinel-2 sind schon heute `float32`, bevor ein Schritt läuft
(`core.py:_source_meta`). Ganzzahlig bleiben nur unskalierte Bänder
(`scl`, `cloud`, `snow`: `uint8`). „Quellband `uint16` neben Ergebnis `float32`“
gibt es bei Sentinel-2 also nicht; „`uint8`-Klassen neben `float32`“ schon.

| | D1 eine COG, ein Typ | D2 eine COG je Typ | D3 eine COG je Band |
|---|---|---|---|
| Datei | `result.tif` mit allen Bändern | `result_float32.tif`, `result_uint8.tif` | je Band eine Datei im ZIP |
| Typ | nach den heutigen Regeln (`processingDefaults.ts:chooseDtype`): `float32`, sobald ein Band Bruchzahlen hat; ganzzahlig nur bei einem Typ, einem nodata, unskaliert | je Datei der eigene Typ | je Band der eigene Typ |
| Klassen in `float32` | exakt (jede Ganzzahl bis 2²⁴) | — | — |
| Größe | Klassenbänder roh vierfach (`uint8` → `float32`); gemessen kostet `scl` 6,3 MB je 1 Mio. Pixel nach deflate (§3.2, Befund 6) | kleinste | kleinste |
| Ergebnis-Layer, Kachel, Statistik, Runner | wie heute | zwei Dateien je Job, Route und Layer müssen wählen | viele Dateien, viele Routen |
| GIS-Programme | ein Stapel | zwei Stapel | einzeln |
| andere Plattformen | Sentinel Hub und Earth Engine: ein Typ je Ausgabe (§3.5) | Sentinel Hub: mehrere Ausgabeobjekte | — |

**Empfehlung: D1.**

- **Banddeskription:** der Bandname in `result.tif`
  (`set_band_description`); heute fehlt er (§3.1).
- **Einheit je Band:** `set_band_unit` aus der Einheit der STAC-Eigenschaften
  (M4-19b). Ein Ergebnis hat keine Einheit, außer der Ausdruck ist ein
  einzelnes Band (`band_math.py:_transform`).
- **nodata:** bei `float32` NaN; bei ganzzahligem Typ der gemeinsame Wert,
  sonst ist der ganzzahlige Typ nicht wählbar (wie heute, `core.py:_nodata_for`).
- **Größe:** die 5-GB-Prüfung zählt wie heute Pixel × Bänder × Typ.

---

## 9. Vorgabe der Ausgabe ohne `band_math` (Punkt 6)

| | O1 keines angehakt | O2 alle angehakt |
|---|---|---|
| Kosten der Vorgabe | null; der Benutzer wählt | 17 Bänder bei Sentinel-2 je Szene und 1 Mio. Pixel: 19 s, 536 MB Spitze, 37 MB gelesen, 39 MB Datei (§3.2) |
| typischer Fall „wolkenfreies RGB“ (`mask`) | drei Klicks | 14 Klicks zum Abwählen oder „None“ und drei Klicks |
| Einband-Datensatz (DEM) | das eine Band ist angehakt (Regel aus NM4-07) | gleich |
| leerer Auftrag | „Start“ gesperrt, Tooltip „Pick at least one band for the output.“ | kommt nicht vor |

**Empfehlung: O1.** Hat ein Datensatz genau ein Band, ist es angehakt. Die
Regel für mehrere Band-Math-Schritte steht schon fest (Vorab fest 5):

- Ein neuer `band_math`-Schritt hakt sein Ergebnis an.
- Wird ein Schritt entfernt, verschwindet sein Band aus der Ausgabe.
- Alles andere bleibt, wie der Benutzer es gesetzt hat.

---

## 10. Vorschau und Kacheln (Punkt 7)

**Befund [P].** Die Vorschau schickt alle Assets des Auftrags an die Kachel
(`frontend/src/processingPreview.ts:231–280`), und die Kachel liefert die
Bänder, die die Schritte lassen (`processing/tile.py:judge_steps`). Ein Bild
zeigt aber nur ein Band mit Farbskala oder drei als RGB. Eine Bandwahl im
Layer-Manager gibt es nicht. NM4-45 plant ein Dropdown „Band“ für die Ansicht.

| | P1 ein Band, Auswahl „Show“ | P2 wie P1, dazu RGB aus drei Bändern der Ausgabe | P3 immer das erste Band der Ausgabe |
|---|---|---|---|
| Panel | Dropdown über die Bänder der Ausgabe; Vorgabe das letzte Band-Math-Ergebnis, sonst das erste Band | dazu ein Eintrag „RGB…“ mit drei Feldern | keine Wahl |
| Kachel | ein Parameter `band=<Name>`; die Kachel streicht wie der Planer und liest nur, was dieses Band braucht | bis zu drei Namen | wie P1 |
| Grenzen der Kachel (16, Mosaik 4) | greifen selten; NDVI braucht 2 Assets | bis zu dreimal so viel | wie P1 |
| Ergebnis-Layer | dasselbe Dropdown, `bidx` auf `result.tif`, Statistik je Band aus den Eigenschaften (M4-32) | dazu RGB | — |
| Zusammenhang | gleicher Baustein wie NM4-45 | NM4-45 schließt RGB ausdrücklich aus | — |

**Empfehlung: P1.** RGB aus drei Bändern ist eine eigene Aufgabe für Ansicht,
Vorschau und Ergebnis zugleich (§12).

- **M4-18b (Kachel-Kette):** bleibt; die Kachel rechnet den längsten Anfang
  aus `T1`-Schritten. Ein `band_math`-Schritt nach `reproject` ist nicht in der
  Vorschau; der Hinweis „The map shows the first N steps“ gibt es schon.
- **NM4-04 (Mosaik mit Operator, #215):** Die Mosaik-Kachel nimmt `band` ebenso.
  Weil sie nur noch die Assets des gezeigten Bandes liest, passt NDVI mit Maske
  (3 Assets) weiter unter die Grenze von 4.

---

## 11. Hash, Version, Runner, alte Rezepte (Punkt 8)

**Was sich ändert.**

| Stelle | Änderung |
|---|---|
| `recipe_version` | 2: `output.bands`; im Auftrag kein `assets` für `raster`; `RECIPE_VERSION = 2` (`recipe.py:85`) |
| `band_math` | `op_version` 2: Parameter `expression` und `name`, fügt hinzu. Version 1 wird nicht mehr gelistet; angenommen nur in der Übergangszeit über die Umdeutung (unten) |
| `normalize` | `op_version` 2 mit `bands` (F4), in NM4-11 zusammen mit den Methoden |
| `mask` | `op_version` 2: Die Schicht bleibt im Vorrat |
| `reproject` | `op_version` 4: jedes Band ein eigener Warp (F13) |
| `resolved` | Form unverändert (`ResolvedInput`, `adr/0011` §6.4); es hält genau einen Eintrag je Item und **abgeleitetem** Asset, also nur die Assets, die nach dem Streichen gelesen werden (`recipe.py:Input._complete` prüft das weiter gegen `assets`) |
| Hash | ändert sich für jedes Rezept (neue Felder); einmal kein Cache-Treffer |
| `earthx.__version__` | 0.4.3 → 0.5.0: `result.tif` trägt Banddeskriptionen und Einheiten, die Bytes ändern sich |
| `adr/0014` | Nachtrag §15u: Bandvorrat, Streichen, `output.bands`, Namen, Speicherschätzung |
| `adr/0016` | Nachtrag §12d: Der Runner nimmt `recipe_version` 2; ältere Runner-Tags rechnen weiter Version 1 (§9 dort, fester Tag) |
| Prozessbeschreibung | `inputs.assets.maxItems` entfällt (`api/processing_docs.py:299`); `output.bands` mit Schema |

**Umdeutung von Version 1 [A].** Jedes gültige Rezept der Version 1 lässt
sich als Version 2 schreiben, ohne Wertänderung außer nach `reproject`:

1. Jeder `band_math`-Schritt bekommt einen Namen. Der letzte heißt
   `band_math` wie heute; frühere bekommen `band_math_<n>`. Jeder Ausdruck,
   der `band_math` nennt, wird auf den Namen des vorigen Ergebnisses
   umgeschrieben, über denselben Zerleger.
2. `normalize` bekommt als `bands` die Bänder, die er in Version 1 sah.
3. `mask` entfernte die Schicht; `output.bands` nennt sie nicht.
4. `output.bands` ist der Vorrat, den Version 1 am Ende hatte.

Ein Test führt jede Rezept-Fixture der Version 1 umgedeutet aus und vergleicht
die Werte mit dem alten Ergebnis: bitgleich für Ketten ohne `reproject`. Nach
`reproject` ändern sich die Werte, weil das Streichen die Zahl der Bänder
ändert (§3.4) und weil `reproject` Version 4 jedes Band einzeln warpt (F13);
dort prüft der Test die Toleranz von `adr/0014` §6.3.

**Übergang [A].** Bis das Frontend Version 2 schickt (NM4-43c), muss `api`
Aufträge der Version 1 weiter annehmen, und Jobs der Version 1 können beim
Deploy von NM4-43a noch in der Warteschlange stehen oder wiederhergestellt
werden (NM4-27). Deshalb bringt NM4-43a dieselbe Umdeutung auch in Python
(`processing/recipe.py`): `api` deutet Aufträge der Version 1 um, der Worker
gespeicherte Rezepte der Version 1 beim Lesen. Der Kern rechnet nur noch
Version 2. Die Python-Umdeutung entfällt 7 Tage nach NM4-43c (Ablauf Q10);
danach gilt U1.

**Optionen für alte Rezepte:**

| | U1 Frontend deutet um, `api` weist ab | U2 `api` deutet auch um | U3 überall abweisen |
|---|---|---|---|
| Datei (`recipe.json`), Permalink, Ablage im Browser | öffnen mit Hinweis „Converted from recipe version 1.“ | wie U1 | nicht mehr lesbar |
| API-Clients, Chatbot | `422` „recipe_version 1 is no longer accepted; send version 2“ | weiter angenommen | wie U1 |
| Permalinks der letzten 30 Tage | gespeichert als Version 1, beim Öffnen umgedeutet | gleich | verloren |
| Runner | nur Version 2; alte Tags für alte Dateien | gleich | gleich |
| Code | dauerhaft eine Umdeutung in `recipeFile.ts`; die in Python nur im Übergang | dauerhaft zwei (TS und Python) | keine |

**Empfehlung: U1.** Rezepte laufen nach 7 Tagen ab (Q10), Permalinks nach
30. Es gibt keine fremden API-Clients. Auf Dauer genügt eine Umdeutung an
einer Stelle.

---

## 12. Folgen für andere Aufgaben (Punkt 9)

| Aufgabe | Was sich ändert |
|---|---|
| **NM4-10** Schritt-Namen und Chips | geht hierin auf. Titel „1. Band_Math_1“, Name im Rezept (§6). Chips: Die Bänder des Datensatzes stehen oben (Info, Klick fügt ein); am Schritt stehen nur die Ergebnisse früherer Schritte als Chips, weil nach V1 nichts mehr wegfällt. Die Regel „Datensatz + frühere Ergebnisse“ ist so einfach, dass das Panel sie selbst kennt; `api` prüft sie (abweichend von NM4-10 §2, letzter Punkt) |
| **NM4-11** Normalize | `normalize` v2 bekommt `bands` (Pflicht; das Panel schlägt das letzte Ergebnis vor) zusammen mit den Methoden. Statistik je Band, falls Perzentile kommen |
| **NM4-14** Index-Knöpfe | ein Knopf = ein `band_math`-Schritt mit Namen aus dem Preset (`NDVI`), sein Ergebnis angehakt. Zwei Knöpfe = zwei Schritte, zwei Bänder. Trägt der Datensatz schon ein Band dieses Namens, hängt das Panel eine Zahl an (`NDVI_2`) |
| **NM4-20** Panel-Gliederung | neue Reihenfolge: Bands (Info) · Steps · Output · Preview (§14). Erst nach NM4-43c |
| **NM4-05b** ⚙ am Ergebnis | Die gesperrten Schritte der Eltern bringen ihre Namen mit; neue Schritte sehen sie als Chips. Die Ausgabe der Eltern ist die Vorgabe, neue Ergebnisse kommen angehakt dazu. Eltern in Version 1 werden umgedeutet (§11) |
| **NM4-45** Band in der Ansicht | teilt das Dropdown „Band“ mit Vorschau und Ergebnis-Layer (§10). Am besten vor NM4-43c bauen, dann übernimmt NM4-43c den Baustein |
| **DS-06** Maske nach Werten | die Bedingung nennt ein Band des Vorrats, auch ein Ergebnis (`NDVI < 0.2`). Wirkt wie `mask` auf alle Bänder |
| **`auxiliary_assets`** (NM4-07, `adr/0014` §15s) | bleiben in Info und Ausgabe ausgeblendet. Die Maskenschicht steht in der Ausgabe wie jedes andere Band, nicht angehakt |
| **NM4-07** Bandauswahl | „Select all bands“ und „Clear“ wandern in die Ausgabe als „All“ und „None“, je nur sichtbar, wenn sie etwas ändern. Die Grenze 16 und ihr Tooltip entfallen |

---

## 13. Schnitt der Umsetzung (Punkt 10)

| Reihenfolge | Aufgabe | Stufe | Inhalt | Richtwert |
|---|---|---|---|---|
| 0 | **NM4-43-0** Schätzung auf feinstem Raster | A | §3.3; Test mit 60-m-Asset vorn | < 100 Zeilen |
| 1 | **NM4-43a** Rezept und Kern | A | `recipe_version` 2, `band_math` v2, `mask` v2, `reproject` v4 (F13), Streichen im Planer, `output.bands`, Ableitung der Assets in `api`, Namen, Banddeskription und Einheit, Speicherschätzung (G2), `units` mit Bändern, Prozessbeschreibung, Runner, Nachträge `adr/0014` und `adr/0016`, `__version__` | etwa 400 Zeilen; sonst Speicherschätzung als eigener PR |
| 2 | **NM4-43b** Kachel | A | Parameter `band` für Kachel und Mosaik-Kachel, Streichen dort, Statistik je Band | < 250 Zeilen |
| 3 | **NM4-43c** Frontend | A | Panel nach §14, Namen und Umbenennen, Ausgabe, Vorschau „Show“, Ergebnis-Layer je Band, Umdeutung von Version 1 | über 400 Zeilen; in zwei PRs: Auftrag und Panel, dann Vorschau und Layer |
| danach | NM4-11, NM4-14, DS-06, NM4-20 | wie geplant | §12 | — |

NM4-43a und NM4-43b sind Backend und können nacheinander in einer Session
laufen; NM4-43c ist Frontend und nicht gleichzeitig mit NM4-20, NM4-45 oder
NM4-14 (Bandbereich des Panels). Bis NM4-43c fertig ist, nimmt `api` neben
Version 2 auch Version 1 an und deutet sie um (§11, Übergang), damit `main`
nie ein Panel hat, das die API ablehnt. 7 Tage nach NM4-43c endet die Annahme
von Version 1 (U1).

---

## 14. Panel-Skizze (empfohlene Variante; kein Code)

Texte Englisch, kurz; Erklärungen im Tooltip (UI-01 §4).

```
PROCESSING                                   sentinel-2-c1-l2a · 1 scene
  Bands  ⓘ
    (coastal) (blue) (green) (red) (rededge1) … (scl) (cloud) (snow)
    └ ⓘ tooltip: "Bands of the data. Click one to put its name into an expression."

  Steps
    1. Mask_1        mask
       Layer scl · Hide: cloud, shadow …                          ▲ ▼ ✕
    2. NDVI          band math
       Expression [ (nir-red)/(nir+red)            ]               ▲ ▼ ✕
       Name       [ NDVI         ]
    3. NDWI          band math
       Expression [ (green-nir)/(green+nir)        ]               ▲ ▼ ✕
       Name       [ NDWI         ]
       (NDVI)                       ← Chips: Ergebnisse früherer Schritte
    Add step:  ＋ Band math   ＋ Mask   ＋ Normalize   ＋ Reproject

  Output  ⓘ                                   2 bands · float32
    New    [✓ NDVI] [✓ NDWI]
    Data   [ coastal ] [ blue ] [ green ] [ red ] … [ scl ] [ cloud ] [ snow ]
           All
    Data type: float32 (chosen automatically)   ▸ Change the data type

  Preview on the map    Show [ NDWI ▾ ]   Range …   Auto stretch
                        ＋ Add preview to layers

  [ Review ]  [ Start ]      about 25 s · 9.6 MB
```

- **Bands (oben):** nur Information. Ein Klick fügt den Namen in das Ausdrucksfeld
  mit Fokus ein; ohne Fokus tut er nichts (kein Auswahlzustand mehr). Kein
  Satz im Panel; die Erklärung steht im ⓘ. Hilfs-Assets erscheinen nicht.
- **Schritt-Titel:** „<n>. <Name>“; bei `band_math` ist der Name das Feld
  „Name“, bei anderen Schritten „Mask_1“, „Normalize_4“ (nur Titel, kein
  Band). Ein Name mit Konflikt zeigt den Rahmen in der Fehlerfarbe und den
  Grund im Tooltip, etwa „NDVI is used twice“.
- **Chips am Schritt:** nur Ergebnisse früherer Schritte; gibt es keine, steht
  dort nichts.
- **Output:** „New“ zeigt die Ergebnisse, „Data“ die Bänder des Datensatzes.
  Angehakte Bänder sind gefüllt (Stil der heutigen Chips). „All“ erscheint nur,
  wenn nicht alle angehakt sind, „None“ nur, wenn mindestens eines angehakt ist.
  Die Kopfzeile nennt Zahl und Typ.
- **Start ohne Ausgabe:** gesperrt, Tooltip „Pick at least one band for the
  output.“
- **Speichergrenze (G2):** Würde der Auftrag sie überschreiten, ist „Start“
  gesperrt; der Tooltip nennt den Grund aus der Schätzung, etwa „About 2.4 GB of
  memory – a job may use 1.5 GB“. Kein Satz im Panel.
- **Preview:** „Show“ erscheint nur bei mehr als einem Band in der Ausgabe.
- **Ergebnis-Layer (Layer-Manager):** dasselbe Dropdown „Band“ in der Zeile,
  nur bei mehr als einem Band.

---

## 15. Fragen an Otto

Antwort je Frage mit der Nummer der Option, etwa „F1: 1“. Empfehlung ist
jeweils Option 1.

**F1 — Rezeptmodell?**
1. Bandvorrat, lineare Kette; `band_math` fügt hinzu, `mask` und `reproject` wirken auf alle Bänder, der Planer streicht Ungenutztes (§4, V1) **(Empfehlung)**
2. Zwei Phasen: erst alle `band_math`-Schritte, dann `mask`, `normalize`, `reproject` (V2)
3. Graph wie openEO (V3)

**F2 — Ausgabe im Rezept?**
1. `output.bands`; der Auftrag nennt keine Assets mehr, `api` leitet sie ab und schreibt sie ins Rezept (§5, A1) **(Empfehlung)**
2. Der Auftrag nennt weiter `assets`, `api` prüft sie gegen die Ableitung (A2)

**F3 — Namen neu gerechneter Bänder?**
1. Vorgabe `Band_Math_<n>`; Zeichen und Regeln aus §6; eindeutig ohne Groß-/Kleinschreibung; Umbenennen zieht alle Verweise automatisch mit **(Empfehlung)**
2. Wie 1, aber Groß-/Kleinschreibung unterscheidet (`NDVI` ≠ `ndvi`)
3. Wie 1, aber Umbenennen ändert nur den Schritt, spätere Verweise zeigen einen Fehler

**F4 — Worauf wirkt `normalize`?**
1. Auf die Bänder, die der Schritt nennt (`bands`, Pflicht; das Panel schlägt das letzte Ergebnis vor); umgesetzt mit NM4-11 **(Empfehlung)**
2. Auf alle Bänder des Vorrats wie heute

**F5 — Schutz ohne Bandgrenze?**
1. Grenze 16 entfällt; neu eine Speicherschätzung je Lauf gegen eine Grenze je Kindprozess, Startwert 1,5 GB; Zeitschätzung und `units` zählen die Bänder der Ausgabe (§7, G2) **(Empfehlung)**
2. Grenze 16 entfällt, nur die bestehenden Grenzen (G1)
3. Grenze 16 entfällt; neu eine Grenze für Pixel × Bänder × Szenen der Eingabe (G3)

**F6 — Ausgabedatei?**
1. Eine COG, ein Typ für alle Bänder nach den heutigen Regeln, Banddeskription und Einheit je Band (§8, D1) **(Empfehlung)**
2. Eine COG je Datentyp (D2)
3. Eine COG je Band (D3)

**F7 — Was ist ohne `band_math` angehakt?**
1. Nichts, außer der Datensatz hat genau ein Band; „Start“ gesperrt mit Grund (§9, O1) **(Empfehlung)**
2. Alle Bänder (O2)

**F8 — Vorschau bei mehreren Bändern?**
1. Ein Band, Auswahl „Show“ (Vorgabe letztes Ergebnis); dasselbe Dropdown am Ergebnis-Layer und in NM4-45; RGB später als eigene Aufgabe (§10, P1) **(Empfehlung)**
2. Wie 1, dazu RGB aus drei Bändern der Ausgabe jetzt (P2)
3. Immer das erste Band der Ausgabe (P3)

**F9 — Rezepte der Version 1?**
1. Das Frontend deutet Datei, Permalink und Ablage um, mit Hinweis; `api` und der neue Runner weisen Version 1 mit Grund ab, sobald NM4-43c fertig ist (§11, U1) **(Empfehlung)**
2. Auch `api` deutet Version 1 um (U2)
3. Version 1 überall abweisen (U3)

**F10 — Schnitt der Umsetzung?**
1. NM4-43-0, dann NM4-43a, NM4-43b, NM4-43c wie in §13; danach NM4-11, NM4-14, DS-06, NM4-20 **(Empfehlung)**
2. Ein Backend-PR (0, a, b zusammen), dann das Frontend

**F11 — Nebenbefund Schätzung (§3.3)?**
1. Sofort als eigene kleine Aufgabe (Stufe A), unabhängig von den übrigen Antworten **(Empfehlung)**
2. Mit NM4-43a

**F12 — Chips der Ergebnisse (aus NM4-10)?**
1. Bänder des Datensatzes oben (Info), Ergebnisse früherer Schritte als Chips am Schritt; das Panel kennt die Regel selbst, `api` prüft sie (§12) **(Empfehlung)**
2. Alles oben in einer Liste, Ergebnisse dort ab ihrem Schritt
3. Wie in NM4-10 geplant: Die Regel kommt aus dem Backend (eigene Route)

**F13 — `reproject` und die Zahl der Bänder (§3.4)?**
1. `reproject` Version 4 warpt jedes Band für sich; Kosten und Speicher misst NM4-43a, Version 3 wird danach nicht mehr gelistet **(Empfehlung)**
2. So lassen; im Methodentext steht nichts dazu, das Streichen ändert dann die Werte nach `reproject`

---

## 16. Quellen

Abgerufen am 28.10.2026.

**[P], gelesen:**
- openEO API, Entwurf: https://raw.githubusercontent.com/Open-EO/openeo-api/draft/openapi.yaml
- openEO API, Fehlercodes: https://raw.githubusercontent.com/Open-EO/openeo-api/draft/errors.json
- openEO `filter_bands`: https://raw.githubusercontent.com/Open-EO/openeo-processes/draft/filter_bands.json
- CDSE Processing Units: https://raw.githubusercontent.com/eu-cdse/documentation/main/APIs/SentinelHub/Overview/ProcessingUnit.qmd
- CDSE Batch: https://raw.githubusercontent.com/eu-cdse/documentation/main/APIs/SentinelHub/Batch.qmd
- CDSE openEO Credits: https://raw.githubusercontent.com/eu-cdse/documentation/main/APIs/openEO/credit_usage.qmd
- CDSE openEO Föderation: https://raw.githubusercontent.com/eu-cdse/documentation/main/APIs/openEO/federation/backends/api.qmd
- CDSE Kontingente: https://raw.githubusercontent.com/eu-cdse/documentation/main/Quotas.qmd
- sentinelhub-py `evalscript.py`: https://raw.githubusercontent.com/sentinel-hub/sentinelhub-py/master/sentinelhub/evalscript.py
- Earth Engine `image.py`: https://raw.githubusercontent.com/google/earthengine-api/master/python/ee/image.py
- Earth Engine `batch.py`: https://raw.githubusercontent.com/google/earthengine-api/master/python/ee/batch.py
- TiTiler COG-Endpunkte: https://raw.githubusercontent.com/developmentseed/titiler/main/docs/src/endpoints/cog.md
- openeo-python-driver Issue 468: https://github.com/Open-EO/openeo-python-driver/issues/468

**[S], nur Zusammenfassung:**
- Earth Engine `computePixels`: https://developers.google.com/earth-engine/reference/rest/v1/projects.image/computePixels
- Earth Engine Nutzung und Quoten: https://developers.google.com/earth-engine/guides/usage
- Earth Engine Tarife: https://developers.google.com/earth-engine/guides/noncommercial_tiers
- Sentinel Hub Evalscript V3: https://docs.sentinel-hub.com/api/latest/evalscript/v3/
- CDSE openEO Parameter: https://openeo.dataspace.copernicus.eu/openeo/1.2/processing_parameters

**[F], Forum oder Blog:**
- Sentinel Hub, Größe der Ausgabe: https://forum.sentinel-hub.com/t/size-limit-of-downloaded-raster/9022
- Sentinel Hub, Größe der Box: https://community.planet.com/analysis-apis-81/is-there-a-limit-to-the-bounding-box-size-when-making-requests-using-the-sentinel-hub-api-6207
- Earth Engine, gemischte Typen beim Export: https://gisqas.blogspot.com/2016/08/javascript-exporting-data-with.html

---

## 17. Messanhang

**Skript:** `scripts/nm4-43-bands/measure.py` (Kopf des Skripts beschreibt
Aufbau und Ausgaben). Im Repo, weil die Messung reproduzierbar sein soll
(Plan §5); es ist kein Produktivcode, wird von keinem Test und keiner Route
geladen und registriert seinen Operator `band_math_append` nur im eigenen
Prozess.

**Aufrufe** (Repo-Wurzel, Projekt-venv):

```bash
curl -sS -X POST https://earth-search.aws.element84.com/v1/search -H 'Content-Type: application/json' \
  -d '{"collections":["sentinel-2-c1-l2a"],"datetime":"2026-04-01T00:00:00Z/2026-10-01T00:00:00Z","limit":200,"query":{"grid:code":{"eq":"MGRS-32TPT"},"eo:cloud_cover":{"lt":80}}}' \
  -o items.json
```

```bash
PYTHONPATH=backend python scripts/nm4-43-bands/measure.py prepare m10 --items items.json --km 10 --scenes 25
```

```bash
PYTHONPATH=backend python scripts/nm4-43-bands/measure.py run m10 --scenes 25
```

```bash
PYTHONPATH=backend python scripts/nm4-43-bands/measure.py summary m10
```

Für die Flächenreihe (§3.2) dasselbe mit `--scenes 1` und `--km 3`, `--km 10`,
`--km 30`, jeweils mit
`--configs 2-none 2-bm 17-none 17-bm 17-append`.

**Ergebnisse** der Läufe lagen als `results.jsonl` im Kratzverzeichnis der
Sitzung; die Tabellen in §3.2 sind daraus mit `summary` gebildet (Median je
Lauf, Höchstwert der Spitze, Summe über 25 Szenen). Die Laufzeit hängt am Netz
der Sitzung (Proxy, Quelle in us-west-2); Spitze, Bytes und Anfragen hängen
nicht daran.

**`reproject` und die Zahl der Bänder (§3.4):**

```bash
PYTHONPATH=backend python scripts/nm4-43-bands/warp_bands.py --counts 1,2,3,4,18,34
```

Erwartung: 1 bis 3 Bänder „differs in 0“, ab 4 Bändern „differs in 4136158 of
4303544 pixels“.
