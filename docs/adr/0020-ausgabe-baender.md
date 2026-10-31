# ADR 0020 — Ausgabe-Bänder statt Bandauswahl

- **Status:** **Angenommen** von Otto am 2026-10-28 (Entscheidungsvorlage
  Draft-PR #219).
  - F1–F13 sind beantwortet, jeweils mit Option 1; **F7** gilt mit
    Ausnahmen (Otto hat seine erste Antwort, Option 2, am selben Tag durch
    „Option 1 mit Ausnahmen“ ersetzt). Ergänzungen zu F7, F9, F11 und F13 und
    die neue Aufgabenfolge stehen in §15 und §15a.
  - **F14** (§15a, Rezepte der Version 1 mit `reproject` im Runner) ist mit
    Option 1 beantwortet.
  - Die Aufgaben NM4-43a bis NM4-43e sind in
    `plans/querschnitt/nm4-43-ausgabe-baender.md` §6 beschrieben, je mit
    Startsatz.
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

**Warum `curl` für die Suche (Grenze der Cloud-Sitzung, `adr/0002` Nachtrag
2026-09-20, M2-13).** `gateway` verbindet absichtlich die von `check_url`
geprüfte Adresse; die Egress-Freigabe der Sitzung arbeitet namensbasiert und
weist `CONNECT` auf eine Adresse mit `403` ab. Die Suche über die Plattform
scheiterte hier mit „could not be reached“ **[M]**; `curl` (Name) kommt durch.
Der Aufruf ist ein einmaliger, dokumentierter Schritt (§17), kein Teil der
Skripte.

**Die Skripte machen keine eigenen HTTP-Aufrufe.** `measure.py` und
`warp_bands.py` importieren keinen HTTP-Client (Prüfung in §17). `measure.py`
liest die Items aus der Datei, die `curl` geschrieben hat, und baut die Rezepte
über `api.intake.estimate_order`; die Dateien der Szenen liest allein der
Processing-Kern über `readers`, und jede Adresse passiert dabei `check_url` wie
im Worker. `warp_bands.py` liest keine Quelle.

---

## 0. Kurzfassung

Entschieden am 2026-10-28: Die Empfehlungen unten gelten, mit einer
Abweichung und zwei Ergänzungen (Otto): **F7** gilt als Option 1 mit
Ausnahmen (Punkt 7), **F9** lässt den Runner Version 1 dauerhaft lesen
(Punkt 9), **F11** und **F13** sind je eine eigene kleine Aufgabe (Punkt 10).

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
7. **Vorgabe der Ausgabe (F7, Option 1 mit Ausnahmen, Otto):**
   Band-Math-Ergebnisse sind immer vorausgewählt, auch nach Eingriffen des
   Benutzers. Hat der Datensatz genau ein wählbares Band, ist es angehakt (wie
   NM4-07). Sonst ist kein Band angehakt, auch nicht ohne `band_math`. Am Ende
   des Panels stehen alle wählbaren Bänder unter der festen Überschrift
   „Select Bands that are processed“ (immer sichtbar). „Start“ ist gesperrt,
   solange die Ausgabe leer ist; der Grund steht im Tooltip (§9).
8. **Vorschau (F8):** eine Auswahl „Show“ über die Bänder der Ausgabe, Vorgabe
   ist das letzte Band-Math-Ergebnis. Die Kachel rechnet nur dieses eine Band
   und liest nur, was es braucht. Derselbe Baustein dient am Ergebnis-Layer und
   in der Ansicht aus NM4-45. RGB aus drei Bändern kommt später.
9. **Versionen (F9):** `recipe_version` 2, `band_math` Version 2, `normalize`
   Version 2 (mit NM4-11), `earthx.__version__` 0.5.0, Nachträge in
   `adr/0014` und `adr/0016`. Rezepte der Version 1 deutet das Frontend um
   (Datei, Permalink, Ablage), mit Hinweis. `api` deutet sie 30 Tage nach
   dem Umbau des Frontends noch um, danach weist sie sie mit Grund ab. **Der
   Runner liest Version 1 dauerhaft** (heruntergeladene `recipe.json` bleiben
   lesbar, `adr/0016`); nach `reproject` Version 3 können die Werte dabei
   abweichen, der Runner meldet es und nennt den Runner-Tag für bitgleiche
   Werte (F14, §15a).
10. **Schnitt (F10, F11, F13):** zuerst zwei kleine, voneinander und vom Rest
    unabhängige Aufgaben: **NM4-43a** Schätzung nach dem feinsten Asset und
    **NM4-43b** `reproject` Version 4 je Band. Danach **NM4-43c** Rezept und
    Kern, **NM4-43d** Kachel, **NM4-43e** Frontend. NM4-11, NM4-14, DS-06 und
    NM4-20 folgen danach (§12, §13).

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
   ein Band“ liegen **[A]**; das misst NM4-43c.
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
   Bändern rund 72 Mio. Pixel. Wie die Spitze dorthin wächst, misst NM4-43c
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
  eine kleine Änderung mit Test, unabhängig von diesem ADR (F11): Aufgabe
  NM4-43a.

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
  Kosten und Bitgleichheit misst die Umsetzung, Aufgabe NM4-43b (F13).

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
| trifft Sentinel-2 (≤ 33 Bänder im Vorrat) | — | bis 9,5 Mio. Pixel nicht (rund 1,0 GB); große Flächen und Mosaik misst NM4-43c | je nach Wert |
| trifft Hyperspektral (etwa 224 Bänder in einem Asset) | — | ja, mit Zahl im Grund | ja |
| neue Zahl, die gepflegt werden muss | keine | ein Wert je Band, gemessen, im Speichertest geprüft | eine Grenze ohne gemessenen Bezug |

**Empfehlung: G2,** dazu die Behebung aus §3.3 (F11).

- **Formel:** 300 MB plus 21 MB je Band im breitesten Durchgang (Befund 8),
  dazu ein Flächenanteil, den NM4-43c bis zur 5-GB-Grenze und für ein Mosaik
  misst. Der Planer kennt den breitesten
  Durchgang nach dem Streichen (§4). Die Werte misst NM4-43c mit dem echten
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

## 9. Vorgabe der Ausgabe (Punkt 6)

**Mit `band_math`** ist entschieden (Vorab fest 5): Angehakt sind die
Band-Math-Ergebnisse. Offen war, was ohne `band_math` im Rezept angehakt ist
(nur `reproject`, `mask`, `normalize` oder gar kein Schritt):

| | O1 keines angehakt | O2 alle angehakt |
|---|---|---|
| Kosten der Vorgabe | null; der Benutzer wählt | 17 Bänder bei Sentinel-2 je Szene und 1 Mio. Pixel: 19 s, 536 MB Spitze, 37 MB gelesen, 39 MB Datei (§3.2) |
| typischer Fall „wolkenfreies RGB“ (`mask`) | drei Klicks | „None“ und drei Klicks |
| Einband-Datensatz (DEM) | das eine Band ist angehakt (Regel aus NM4-07) | gleich |
| leerer Auftrag | „Start“ gesperrt, Tooltip „Pick at least one band for the output.“ | kommt zunächst nicht vor |

**Empfehlung war O1. Otto hat zuerst O2 gewählt und das am selben Tag (2026-10-28)
durch „O1 mit Ausnahmen“ ersetzt** (F7). Es gilt:

1. **Band-Math-Ergebnisse sind immer vorausgewählt.** Ein neues Ergebnis wird
   angehakt, auch nach Eingriffen des Benutzers (Auslegung §15a, von Otto
   angenommen); der Benutzer kann es danach abwählen. Wird ein Schritt
   entfernt, verschwindet sein Band aus der Ausgabe.
2. **Hat der Datensatz genau ein wählbares Band, ist es angehakt**, einmal je
   Öffnen des Panels (Regel aus NM4-07: ein späteres „None“ bleibt stehen). Kommt
   ein Ergebnis dazu, sind beide angehakt; das Quellband lässt sich abwählen
   (Auslegung, §15a). „Wählbar“ ist, was „Select all bands“ heute nimmt (NM4-07,
   `adr/0014` §15s): nicht die Hilfs-Assets aus `auxiliary_assets`
   (`visual`, `preview`) und nicht die Maskenschicht (`scl`).
3. **Sonst ist kein Band angehakt, auch nicht ohne `band_math`** (nur
   `reproject`, `mask`, `normalize` oder kein Schritt). Die Wechselregel der
   ersten Antwort (Vorgabe nach Schritten, Zustand „automatisch“ oder „vom
   Benutzer gesetzt“) entfällt: Es gibt nur noch die Auswahl des Benutzers, das
   automatische Anhaken eines neuen Ergebnisses und die Regel für das eine Band.
4. **Feste Überschrift.** Am Ende des Panels stehen alle wählbaren Bänder des
   Datensatzes unter der festen Überschrift „Select Bands that are processed“,
   **immer sichtbar, unabhängig von der Auswahl.** Kein weiterer Hinweissatz im
   Panel. Die Hilfs-Assets erscheinen dort nicht; die Maskenschicht steht in
   der Liste, nicht angehakt (§12).
5. **Leere Ausgabe:** „Start“ (bzw. „Run“) ist gesperrt, solange die Ausgabe
   leer ist; der Grund steht im Tooltip: „Pick at least one band for the
   output.“ Ein leerer Auftrag wird nicht gestartet (Plan §3 Punkt 6).
6. **Breite Datensätze:** Es ist nichts vorausgewählt, die Vorgabe ist also nie
   zu groß. „All“ wählt alle wählbaren Bänder; liegt die Auswahl über der
   Speichergrenze (§7), ist „Start“ gesperrt und der Grund steht im Tooltip.
   Es gibt keine stille Teilmenge.

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
| `band_math` | `op_version` 2: Parameter `expression` und `name`, fügt hinzu. Version 1 bleibt registriert und angenommen (Umdeutung, Kachel bis NM4-43d) und wird mit NM4-43e nicht mehr gelistet |
| `normalize` | `op_version` 2 mit `bands` (F4). Das Feld kommt schon mit NM4-43c, weil das Vorratsmodell es braucht (§15a); NM4-11 setzt die Methoden darauf |
| `mask` | `op_version` 2: Die Schicht bleibt im Vorrat |
| `reproject` | `op_version` 4: jedes Band ein eigener Warp (F13, NM4-43b, vor der Rezeptversion 2 und von ihr unabhängig). Version 3 bleibt angenommen, wird aber nicht mehr gelistet (wie Version 2 heute) |
| `resolved` | Form unverändert (`ResolvedInput`, `adr/0011` §6.4); es hält genau einen Eintrag je Item und **abgeleitetem** Asset, also nur die Assets, die nach dem Streichen gelesen werden (`recipe.py:Input._complete` prüft das weiter gegen `assets`) |
| Hash | ändert sich für jedes Rezept (neue Felder); einmal kein Cache-Treffer |
| `earthx.__version__` | 0.4.3 → 0.4.4 mit NM4-43b (`reproject` Version 4 ändert Werte); → 0.5.0 mit NM4-43c (`result.tif` trägt Banddeskriptionen und Einheiten, die Bytes ändern sich). NM4-43a ändert keine Bytes und hebt nichts an |
| `adr/0014` | drei Nachträge: §15v (NM4-43a, Schätzung nach dem feinsten Asset, zu §5.5), §15w (NM4-43b, `reproject` Version 4, zu §3.4, §6.3), §15x (NM4-43c, Bandvorrat, Streichen, `output.bands`, Namen, Speicherschätzung) |
| `adr/0016` | Nachtrag §12d: Der Runner nimmt `recipe_version` 2 und liest Version 1 **dauerhaft** über die Umdeutung; ältere Runner-Tags rechnen Version 1 weiter wie bisher (§9 dort, fester Tag) |
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

**Wo die Umdeutung läuft (F9, Otto).**

| Ort | wie lange | Aufgabe |
|---|---|---|
| Frontend (`recipeFile.ts`, Permalink, Ablage im Browser) | dauerhaft | NM4-43e |
| Runner (`recipe.json` einer älteren Fassung) | **dauerhaft**: heruntergeladene Rezepte bleiben lesbar | NM4-43c |
| `api` (Aufträge, Permalinks anlegen) | Übergang, siehe unten | NM4-43c |
| Worker (gespeicherte Rezepte der Warteschlange und der Wiederherstellung, NM4-27) | wie `api` | NM4-43c |

Die Python-Umdeutung (`processing`, ein Modul, von `api`, Worker und Runner
gemeinsam benutzt) bleibt wegen des Runners dauerhaft. Sie läuft dabei vor der
Prüfung des Rezepts; der Kern selbst rechnet nur Version 2.

**Übergangsfrist für `api` (Otto: mindestens so lange wie gespeicherte Rezepte
und Permalinks gelten).** Bestimmend ist der Permalink mit 30 Tagen ab
Erstellung (Log 24.10.2026, M4-19e); ein Job und sein Rezept gelten 7 Tage
(Q10), ein gelöschter Job bleibt bis zu einen Tag wiederherstellbar (NM4-27).
Ein Dokument der Version 1 kann also bis zu 30 Tage nach dem letzten Schreiben
im alten Format noch gültig sein. Festgelegt wird:

- **`api` nimmt Aufträge der Version 1 an und deutet sie um** ab dem Deploy von
  NM4-43c bis **30 Tage nach dem Deploy von NM4-43e.** Mit NM4-43e schreibt das
  Frontend nur noch Version 2. Ein Browser-Tab mit der alten Fassung kann
  weiter Version 1 schicken, solange er offen ist; ein Permalink der Version 1
  gilt 30 Tage. Beides deckt die Frist.
- **Danach** (U1): `422` „recipe_version 1 is no longer accepted; send
  version 2“. Gespeicherte Permalinks der Version 1 liest `api` weiter aus
  (`read_permalink` prüft nicht neu, `processing_route.py:1421`), das Frontend
  deutet sie um.
- **Ein Datum steht erst fest, wenn NM4-43e deployt ist.** Der PR von NM4-43e
  trägt es als Konstante in `api` und als Log-Zeile ein; eine Zeile im Code
  schaltet die Annahme ab, ein Test hält sie fest.
- **Bis NM4-43e** listet die Prozessbeschreibung weiter Version 1 der Schritte
  (`processing_docs.py:205` nennt nur die jeweils höchste Version), damit das
  heutige Panel funktioniert; NM4-43e schaltet die Liste auf Version 2 um
  (Vorschlag, Umsetzung in NM4-43c, §13).

**Optionen für alte Rezepte:**

| | U1 Frontend deutet um, `api` weist ab | U2 `api` deutet auch um | U3 überall abweisen |
|---|---|---|---|
| Datei (`recipe.json`), Permalink, Ablage im Browser | öffnen mit Hinweis „Converted from recipe version 1.“ | wie U1 | nicht mehr lesbar |
| API-Clients, Chatbot | `422` „recipe_version 1 is no longer accepted; send version 2“ nach der Frist | weiter angenommen | wie U1 |
| Permalinks der letzten 30 Tage | gespeichert als Version 1, beim Öffnen umgedeutet | gleich | verloren |
| Runner | **dauerhaft** (Otto, F9) | gleich | nur Version 2 |
| Code | Umdeutung in `recipeFile.ts` und, wegen des Runners, in Python | gleich, dauerhaft in `api` | keine |

**Empfehlung war U1; entschieden hat Otto U1 mit der Ergänzung, dass der Runner
Version 1 dauerhaft liest (F9).** Rezepte laufen nach 7 Tagen ab (Q10),
Permalinks nach 30. Es gibt keine fremden API-Clients.

**Grenze der Umdeutung für `reproject` (F14, §15a).** Jedes Rezept ohne
`reproject` gibt nach der Umdeutung dieselben Werte wie vorher, bitgleich. Mit
`reproject` Version 3 hängen die Werte an der Zahl der Bänder, die der Warp
sieht (§3.4); nach der Umdeutung sieht er nach dem Streichen unter Umständen
weniger Bänder als in Version 1, und `reproject` Version 3 bleibt dabei die
Version des Rezepts. Dann können sich die Werte ändern (bei Bilinear gemessen
bis 1,5 % des Wertebereichs, §3.4). **Entschieden (Otto, F14, Option 1):**
Hat ein Rezept der Version 1 einen Schritt `reproject` Version 3, meldet der
Runner das kurz auf dem Bildschirm und schreibt dieselbe Meldung als Eintrag
`notes` in `provenance.json` des Laufs. Sie sagt, dass Werte nach `reproject`
abweichen können, und nennt den Runner-Tag für bitgleiche Werte, den der
frühere Lauf benutzte: `earthx-runner:<Version aus source_engine.earthx>`
(`adr/0016` §9; trägt das Rezept keine Version, steht „an older runner tag“).
Beispiel: „Converted from recipe version 1. Values after reproject can differ;
for identical values use earthx-runner:0.4.3.“ Die Umdeutung selbst bleibt wie
oben.

---

## 12. Folgen für andere Aufgaben (Punkt 9)

| Aufgabe | Was sich ändert |
|---|---|
| **NM4-10** Schritt-Namen und Chips | geht hierin auf. Titel „1. Band_Math_1“, Name im Rezept (§6). Chips: Die Bänder des Datensatzes stehen oben (Info, Klick fügt ein); am Schritt stehen nur die Ergebnisse früherer Schritte als Chips, weil nach V1 nichts mehr wegfällt. Die Regel „Datensatz + frühere Ergebnisse“ ist so einfach, dass das Panel sie selbst kennt; `api` prüft sie (abweichend von NM4-10 §2, letzter Punkt) |
| **NM4-11** Normalize | `normalize` v2 bekommt `bands` (Pflicht; das Panel schlägt das letzte Ergebnis vor) zusammen mit den Methoden. Statistik je Band, falls Perzentile kommen |
| **NM4-14** Index-Knöpfe | ein Knopf = ein `band_math`-Schritt mit Namen aus dem Preset (`NDVI`), sein Ergebnis angehakt. Zwei Knöpfe = zwei Schritte, zwei Bänder. Trägt der Datensatz schon ein Band dieses Namens, hängt das Panel eine Zahl an (`NDVI_2`) |
| **NM4-20** Panel-Gliederung | neue Reihenfolge: Bands (Info) · Steps · Output · Preview (§14). Erst nach NM4-43e |
| **NM4-05b** ⚙ am Ergebnis | Die gesperrten Schritte der Eltern bringen ihre Namen mit; neue Schritte sehen sie als Chips. Die Ausgabe der Eltern ist die Vorgabe, neue Ergebnisse kommen angehakt dazu. Eltern in Version 1 werden umgedeutet (§11) |
| **NM4-45** Band in der Ansicht | teilt das Dropdown „Band“ mit Vorschau und Ergebnis-Layer (§10). Am besten vor NM4-43e bauen, dann übernimmt NM4-43e den Baustein |
| **DS-06** Maske nach Werten | die Bedingung nennt ein Band des Vorrats, auch ein Ergebnis (`NDVI < 0.2`). Wirkt wie `mask` auf alle Bänder |
| **`auxiliary_assets`** (NM4-07, `adr/0014` §15s) | bleiben in Info und Ausgabe ausgeblendet. Die Maskenschicht steht in der Ausgabe wie jedes andere Band, nicht angehakt |
| **NM4-07** Bandauswahl | „Select all bands“ und „Clear“ wandern in die Ausgabe als „All“ und „None“, je nur sichtbar, wenn sie etwas ändern. Die Grenze 16 und ihr Tooltip entfallen |

---

## 13. Schnitt der Umsetzung (Punkt 10)

Entschieden am 2026-10-28 (F10, F11, F13). Jede Aufgabe ist in
`plans/querschnitt/nm4-43-ausgabe-baender.md` §6 mit Stufe, Modell, Start,
Startsatz, Umfang und Abnahme beschrieben, ohne dieses Gespräch verständlich.

| Reihenfolge | Aufgabe | Stufe | Inhalt | Richtwert |
|---|---|---|---|---|
| unabhängig, sofort | **NM4-43a** Schätzung nach feinstem Asset (F11) | A | §3.3; Test mit 60-m-Asset vorn | < 100 Zeilen |
| unabhängig, sofort | **NM4-43b** `reproject` Version 4 je Band (F13) | A | §3.4; je Band ein Warp, Version 3 bleibt angenommen | < 250 Zeilen |
| 1 | **NM4-43c** Rezept und Kern | A | `recipe_version` 2, `band_math` v2 (`name`), `mask` v2, `normalize` v2 (`bands`), Streichen im Planer, `output.bands`, Ableitung der Assets in `api`, Namen, Banddeskription und Einheit, Umdeutung von Version 1 in Python (`api`, Worker, Runner), Prozessbeschreibung, Nachtrag `adr/0014` §15x und `adr/0016` §12d, `__version__` 0.5.0; in einem zweiten PR der Schutz ohne Bandgrenze (G2, Zeitschätzung, `units`, Grenze 16 entfällt) | über 400 Zeilen; deshalb zwei PRs |
| 2 | **NM4-43d** Kachel | A | Parameter `band` für Kachel und Mosaik-Kachel, Streichen dort, Statistik je Band, `band_math` Version 2 in der Kachel | < 250 Zeilen |
| 3 | **NM4-43e** Frontend | A | Panel nach §14, Namen und Umbenennen, Ausgabe mit der Vorgabe aus §9, Vorschau „Show“, Ergebnis-Layer je Band, Umdeutung von Version 1, Prozessbeschreibung auf Version 2 umschalten | über 400 Zeilen; zwei PRs: Auftrag und Panel, dann Vorschau und Layer |
| danach | NM4-11, NM4-14, DS-06, NM4-20 | wie geplant | §12 | — |

- **NM4-43a und NM4-43b** sind unabhängig voneinander und vom Rest. NM4-43a
  muss vor NM4-43c fertig sein (beide ändern `processing/plan.py`). NM4-43b
  ändert `operators/reproject.py` und ist nur Voraussetzung dafür, dass das
  Streichen von Bändern in NM4-43c die Werte nach `reproject` nicht ändert.
- **NM4-43c und NM4-43d** sind Backend und laufen nacheinander. NM4-43e ist
  Frontend und läuft nicht gleichzeitig mit NM4-20, NM4-45 oder NM4-14
  (Bandbereich des Panels), höchstens zwei Frontend-Sessions zugleich.
- **`main` hat nie ein Panel, das die API ablehnt.** Bis NM4-43e nimmt `api`
  Aufträge der Version 1 an und deutet sie um (§11). Dafür listet die
  Prozessbeschreibung bis dahin weiter Version 1 der Schritte (Vorschlag für
  NM4-43c: ein Feld am Operator, das die Auflistung steuert); NM4-43e schaltet
  auf Version 2 um und beginnt damit die Frist aus §11.

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

  Select Bands that are processed  ⓘ          2 bands · float32
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
- **Select Bands that are processed:** die feste Überschrift des Abschnitts am
  Ende (immer sichtbar, kein Hinweissatz). „New“ zeigt die Ergebnisse, „Data“ die
  Bänder des Datensatzes.
  Angehakte Bänder sind gefüllt (Stil der heutigen Chips). „All“ erscheint nur,
  wenn nicht alle angehakt sind, „None“ nur, wenn mindestens eines angehakt ist.
  Die Kopfzeile nennt Zahl und Typ.
- **Vorgabe der Ausgabe (F7, §9):** Neue Ergebnisse sind angehakt. Hat der
  Datensatz genau ein wählbares Band, ist es angehakt. Sonst ist nichts
  angehakt, auch nicht ohne `band_math`; „New“ ist ohne Ergebnis leer und
  erscheint nicht.
- **Start ohne Ausgabe:** gesperrt, Tooltip „Pick at least one band for the
  output.“
- **Speichergrenze (G2):** Würde der Auftrag sie überschreiten, ist „Start“
  gesperrt; der Tooltip nennt den Grund aus der Schätzung, etwa „About 2.4 GB of
  memory – a job may use 1.5 GB“. Kein Satz im Panel.
- **Preview:** „Show“ erscheint nur bei mehr als einem Band in der Ausgabe.
- **Ergebnis-Layer (Layer-Manager):** dasselbe Dropdown „Band“ in der Zeile,
  nur bei mehr als einem Band.

---

## 15. Fragen an Otto — beantwortet am 2026-10-28

Otto hat F1 bis F13 mit Option 1 beantwortet, mit Ausnahmen bei **F7**, und
vier Ergänzungen gemacht (F7, F9, F11/F13, Messskripte). Die erste Antwort zu
F7 (Option 2) hat er am selben Tag ersetzt; es gilt die Antwort unten. Die Fragen stehen mit
ihrem ursprünglichen Wortlaut da; die Antwort folgt je Frage. Die Nummer der
Antwort ist die Nummer in der Liste der Frage.

**F1 — Rezeptmodell?**
1. Bandvorrat, lineare Kette; `band_math` fügt hinzu, `mask` und `reproject` wirken auf alle Bänder, der Planer streicht Ungenutztes (§4, V1) **(Empfehlung)**
2. Zwei Phasen: erst alle `band_math`-Schritte, dann `mask`, `normalize`, `reproject` (V2)
3. Graph wie openEO (V3)

**Antwort F1: (1)** Bandvorrat, lineare Kette; `band_math` fügt hinzu, `mask` und `reproject` wirken auf alle Bänder, der Planer streicht Ungenutztes.

**F2 — Ausgabe im Rezept?**
1. `output.bands`; der Auftrag nennt keine Assets mehr, `api` leitet sie ab und schreibt sie ins Rezept (§5, A1) **(Empfehlung)**
2. Der Auftrag nennt weiter `assets`, `api` prüft sie gegen die Ableitung (A2)

**Antwort F2: (1)** `output.bands`; der Auftrag nennt keine Assets mehr, `api` leitet sie ab und schreibt sie ins Rezept.

**F3 — Namen neu gerechneter Bänder?**
1. Vorgabe `Band_Math_<n>`; Zeichen und Regeln aus §6; eindeutig ohne Groß-/Kleinschreibung; Umbenennen zieht alle Verweise automatisch mit **(Empfehlung)**
2. Wie 1, aber Groß-/Kleinschreibung unterscheidet (`NDVI` ≠ `ndvi`)
3. Wie 1, aber Umbenennen ändert nur den Schritt, spätere Verweise zeigen einen Fehler

**Antwort F3: (1)** Vorgabe `Band_Math_<n>`, Regeln aus §6, eindeutig ohne Groß-/Kleinschreibung, Umbenennen zieht alle Verweise mit.

**F4 — Worauf wirkt `normalize`?**
1. Auf die Bänder, die der Schritt nennt (`bands`, Pflicht; das Panel schlägt das letzte Ergebnis vor); umgesetzt mit NM4-11 **(Empfehlung)**
2. Auf alle Bänder des Vorrats wie heute

**Antwort F4: (1)** `normalize` v2 mit `bands`. Auslegung (§15a): Das Feld kommt schon mit NM4-43c, die Methoden mit NM4-11.

**F5 — Schutz ohne Bandgrenze?**
1. Grenze 16 entfällt; neu eine Speicherschätzung je Lauf gegen eine Grenze je Kindprozess, Startwert 1,5 GB; Zeitschätzung und `units` zählen die Bänder der Ausgabe (§7, G2) **(Empfehlung)**
2. Grenze 16 entfällt, nur die bestehenden Grenzen (G1)
3. Grenze 16 entfällt; neu eine Grenze für Pixel × Bänder × Szenen der Eingabe (G3)

**Antwort F5: (1)** Grenze 16 entfällt; Speicherschätzung je Lauf gegen 1,5 GB, Zeitschätzung und `units` zählen die Bänder.

**F6 — Ausgabedatei?**
1. Eine COG, ein Typ für alle Bänder nach den heutigen Regeln, Banddeskription und Einheit je Band (§8, D1) **(Empfehlung)**
2. Eine COG je Datentyp (D2)
3. Eine COG je Band (D3)

**Antwort F6: (1)** Eine COG, ein Typ, Banddeskription und Einheit je Band.

**F7 — Was ist ohne `band_math` angehakt?**
1. Nichts, außer der Datensatz hat genau ein Band; „Start“ gesperrt mit Grund (§9, O1) **(Empfehlung)**
2. Alle Bänder (O2) — Ottos erste Antwort, am selben Tag ersetzt

**Antwort F7: (1) mit Ausnahmen** (Otto, ersetzt seine erste Antwort „Option 2“ vom selben Tag): Band-Math-Ergebnisse sind immer vorausgewählt (auch nach Eingriffen des Benutzers). Hat der Datensatz genau ein wählbares Band, ist es angehakt (wie NM4-07). Sonst ist kein Band angehakt, auch nicht ohne `band_math` (`reproject`, `mask`, `normalize` oder kein Schritt). Am Ende des Panels stehen alle wählbaren Bänder unter der festen Überschrift „Select Bands that are processed“ (immer sichtbar, unabhängig von der Auswahl). „Run“ bzw. der Start-Knopf ist gesperrt, solange die Ausgabe leer ist; der Grund steht im Tooltip. Die Wechselregel entfällt. Einzelheiten: §9.

**F8 — Vorschau bei mehreren Bändern?**
1. Ein Band, Auswahl „Show“ (Vorgabe letztes Ergebnis); dasselbe Dropdown am Ergebnis-Layer und in NM4-45; RGB später als eigene Aufgabe (§10, P1) **(Empfehlung)**
2. Wie 1, dazu RGB aus drei Bändern der Ausgabe jetzt (P2)
3. Immer das erste Band der Ausgabe (P3)

**Antwort F8: (1)** Ein Band, Auswahl „Show“; RGB später als eigene Aufgabe.

**F9 — Rezepte der Version 1?**
1. Das Frontend deutet Datei, Permalink und Ablage um, mit Hinweis; `api` und der neue Runner weisen Version 1 mit Grund ab, sobald NM4-43c fertig ist (§11, U1) **(Empfehlung)**
2. Auch `api` deutet Version 1 um (U2)
3. Version 1 überall abweisen (U3)

**Antwort F9: (1)** mit Ergänzung (Otto): Der **Runner liest das alte Rezeptformat dauerhaft** (heruntergeladene `recipe.json` bleiben lesbar, `adr/0016`). Die Übergangsfrist für `api` nennt §11: 30 Tage nach dem Deploy von NM4-43e (mindestens so lange wie gespeicherte Rezepte und Permalinks gelten).

**F10 — Schnitt der Umsetzung?**
1. Erst die Schätzung (Nebenbefund), dann Rezept und Kern, Kachel, Frontend wie in §13; danach NM4-11, NM4-14, DS-06, NM4-20 **(Empfehlung)**
2. Ein Backend-PR (Schätzung, Rezept und Kern, Kachel zusammen), dann das Frontend

**Antwort F10: (1)** Reihenfolge wie in §13 mit der neuen Nummerierung: NM4-43a und NM4-43b (unabhängig), danach NM4-43c Kern, NM4-43d Kachel, NM4-43e Frontend; dann NM4-11, NM4-14, DS-06, NM4-20.

**F11 — Nebenbefund Schätzung (§3.3)?**
1. Sofort als eigene kleine Aufgabe (Stufe A), unabhängig von den übrigen Antworten **(Empfehlung)**
2. Mit dem Rezept und dem Kern

**Antwort F11: (1)** (Otto) Eigene kleine Aufgabe, Stufe A, sofort und unabhängig startbar: **NM4-43a** „Schätzung nach feinstem Asset“.

**F12 — Chips der Ergebnisse (aus NM4-10)?**
1. Bänder des Datensatzes oben (Info), Ergebnisse früherer Schritte als Chips am Schritt; das Panel kennt die Regel selbst, `api` prüft sie (§12) **(Empfehlung)**
2. Alles oben in einer Liste, Ergebnisse dort ab ihrem Schritt
3. Wie in NM4-10 geplant: Die Regel kommt aus dem Backend (eigene Route)

**Antwort F12: (1)** Bänder des Datensatzes oben, frühere Ergebnisse als Chips am Schritt; das Panel kennt die Regel, `api` prüft sie.

**F13 — `reproject` und die Zahl der Bänder (§3.4)?**
1. `reproject` Version 4 warpt jedes Band für sich; Kosten und Speicher misst NM4-43b, Version 3 wird danach nicht mehr gelistet **(Empfehlung)**
2. So lassen; im Methodentext steht nichts dazu, das Streichen ändert dann die Werte nach `reproject`

**Antwort F13: (1)** (Otto) Eigene kleine Aufgabe, Stufe A, sofort und unabhängig startbar: **NM4-43b** „`reproject` Version 4 je Band“.

---

## 15a. Auflagen, Auslegungen und Antwort zu F14 (2026-10-28)

**Von Otto:**

- **F7:** Option 1 mit Ausnahmen (§9): Ergebnisse immer vorausgewählt, ein
  wählbares Band angehakt, sonst nichts; feste Überschrift „Select Bands that
  are processed“; „Start“ gesperrt bei leerer Ausgabe. Ersetzt Option 2.
- **F9:** Der Runner liest das alte Format dauerhaft; die Frist für `api` nennt
  dieses ADR (§11).
- **F11, F13:** je eine eigene kleine Aufgabe, sofort startbar; danach
  NM4-43c, NM4-43d, NM4-43e (§13).
- **Messskripte:** Sie enthalten keine eigenen HTTP-Aufrufe außerhalb von
  `gateway`; der `curl`-Schritt steht nur als dokumentierter Einmal-Schritt im
  ADR (Grenze der Cloud-Sitzung, `adr/0002`). Eingearbeitet in „Methode“ und §17.
- **Status:** angenommen; Log-Zeile „entschieden“.

**Auslegungen von Claude (von Otto am 2026-10-28 angenommen):**

1. **F4:** `normalize` v2 bekommt das Feld `bands` schon mit NM4-43c, nicht erst
   mit NM4-11. Grund: Im Vorratsmodell würde `normalize` Version 1 sonst alle
   Bänder des Vorrats, auch die rohen Eingaben, mitrechnen und das Streichen
   verhindern. NM4-11 setzt die Methoden auf dasselbe Feld.
2. **F7, „wählbar“:** Gemeint ist, was „Select all bands“ heute nimmt (ohne
   Hilfs-Assets und ohne Maskenschicht). Die Maskenschicht `scl` ist also nie
   vorausgewählt, aber in der Liste anklickbar (§9 Punkt 2 und 4).
3. **F7, Eingriff des Benutzers:** Ein neues Band-Math-Ergebnis wird auch nach
   Eingriffen des Benutzers angehakt, ein entferntes verschwindet (§9 Punkt 1).
4. **F9, Dauer der Python-Umdeutung:** Sie bleibt wegen des Runners dauerhaft in
   `processing`; nur die Annahme in `api` endet mit der Frist.
5. **Auflistung bis NM4-43e:** Die Prozessbeschreibung listet bis dahin weiter
   Version 1 der Schritte; NM4-43e schaltet auf Version 2 um und beginnt die
   Frist (§11, §13).

**Auslegung von Claude zur neuen F7-Antwort (Vorschlag, gilt bis Otto
widerspricht):** Bei einem Datensatz mit einem wählbaren Band sind das Band
(einmal beim Öffnen) und ein neues Ergebnis zusammen angehakt; das Quellband
lässt sich abwählen (§9 Punkt 2).

**F14 — Rezepte der Version 1 mit `reproject` im Runner (beantwortet).** Die
Umdeutung gibt bitgleiche Werte, außer nach `reproject` Version 3: Dessen Werte
hängen an der Zahl der Bänder, die der Warp sieht (§3.4), und die Umdeutung
streicht Bänder. Otto will, dass heruntergeladene Rezepte reproduzierbar bleiben
(F9). Wie genau, war offen:
1. Umdeutung wie oben; der Runner sagt, dass Werte nach `reproject` abweichen
   können; die bitgleichen Werte gibt der Runner-Tag der Zeit, der Version 1
   weiter rechnet (`adr/0016` §9) **(Empfehlung)**
2. Der Kern führt Rezepte der Version 1 dauerhaft mit der alten Semantik aus
   (`band_math` ersetzt, `reproject` Version 3 sieht alle Bänder): bitgleich im
   neuen Runner, aber ein zweiter Rechenweg mit eigenen Tests, der bleibt
3. Version-1-Rezepte mit `reproject` im neuen Runner abweisen, mit Grund und
   dem Hinweis auf den alten Runner-Tag

**Antwort F14: (1)** (Otto) Umdeutung. Bei Rezepten mit `reproject` Version 3
meldet der Runner kurz, dass Werte nach `reproject` abweichen können, und nennt
den Runner-Tag für bitgleiche Werte (`adr/0016` §9). Die Meldung steht auch in
`provenance.json` des Laufs (§11).

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

**Aufrufe** (Repo-Wurzel, Projekt-venv). Der erste ist ein `curl` und
einmalig (Grenze der Cloud-Sitzung, „Methode“); er schreibt nur `items.json`,
die Skripte machen keinen eigenen HTTP-Aufruf:

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

**Keine eigenen HTTP-Aufrufe in den Skripten** (Erwartung: keine Ausgabe):

```bash
grep -nE "^\s*(import|from) (httpx|requests|urllib|aiohttp|http\.client|socket|botocore|boto3)" scripts/nm4-43-bands/*.py
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

---

## 18. Nachtrag NM4-43e: Panel und Auftrag (2026-10-30; zu §6, §9, §11, §12, §14, §15a)

Umgesetzt ist PR 1 von NM4-43e (Auftrag und Panel); die Vorschau je Band und der Ergebnis-Layer (PR 2) folgen in einer eigenen Session. Der Text von §6 bis §14
bleibt maßgeblich; dieser Nachtrag nennt, was daraus im Panel geworden ist, und die Auslegungen, die der Plan offen ließ.

- **Rezeptversion 2 im Panel.** Das Panel schickt `recipe_version` 2: `output.bands`, `band_math` Version 2 mit `name`, `mask` Version 2, `normalize` Version 2 mit
  `bands`, keine Asset-Liste für ein Raster. Die Mosaik-Aufträge des Download-Dialogs (`buildMosaicOrder`) nennen ihre Bänder, der Export (`crop`) behält `assets`
  und trägt Version 2. `processingOrder.ts` leitet nichts mehr aus einer Bandauswahl ab; die Grenze von 16 Bändern und ihre Texte sind aus dem Panel entfernt.
- **Auflistung.** Die Prozessbeschreibung listet `band_math`, `mask` und `normalize` in Version 2 (`Operator.listed`); Version 1 bleibt angenommen, nicht gelistet.
- **Bands (oben)** sind Information und Namenshilfe: Ein Klick fügt den Namen in das Ausdrucksfeld mit Fokus ein, sonst tut er nichts. Hilfs-Assets erscheinen nicht.
- **Schritte.** Titel „<n>. <Name>“; bei `band_math` ist der Name das Feld „Name“ (Vorgabe `Band_Math_<n>`, bei Belegung die nächste freie Zahl), bei den übrigen
  Schritten „Mask_1“, „Normalize_3“. Die Namensregeln aus §6 prüft das Panel selbst (`processingBands.ts: nameProblem`); ein Verstoß zeigt den Rahmen in der
  Fehlerfarbe und den Grund im Tooltip des Feldes, ohne Zeile darunter. Chips am Schritt: die Ergebnisse früherer Schritte.
- **Ausgabe („Select Bands that are processed“)** am Ende des Panels, wie §9 und §14: Ergebnisse von `band_math` sind angehakt (auch ein neues nach Eingriffen der Person),
  ein einziges wählbares Band einmal je Öffnen, sonst nichts. „Start job“ ist bei leerer Ausgabe gesperrt (Tooltip „Pick at least one band for the output.“).
- **Auslegungen (Vorschlag, gelten bis Otto widerspricht).**
  1. **Reihenfolge von `output.bands`:** erst die Ergebnisse in Schrittfolge, dann die Bänder des Datensatzes in der Reihenfolge des Items, danach Unbekanntes (ein geladenes
     Rezept kann ein Band nennen, das die Auswahl nicht hat; der Server sagt es). Nicht die Klickfolge, damit eine Wahl genau einen Auftrag und einen Hash ergibt (K4).
  2. **„All“** nimmt alle Ergebnisse und alle wählbaren Bänder (ohne Maskenschicht und Hilfs-Assets), **„None“** leert die ganze Ausgabe, auch die Ergebnisse.
  3. **Datentyp (§8):** `band_math` und `normalize` erzwingen `float32` nur, wenn ihr Ergebnis in der Ausgabe steht; ein Schritt, dessen Ergebnis die Person abgewählt hat,
     verhindert keinen ganzzahligen Typ.
  4. **Umbenennen:** Ein Name, der die Regeln verletzt (leer, doppelt, …), wird nur angezeigt; die Verweise bleiben beim letzten gültigen Namen und ziehen erst mit, wenn
     der Name wieder gültig ist. Ein Schritt, der ein Ergebnis eines späteren Schritts liest, bekommt den Fehler „<Name> is added by a later step.“.
  5. **Namen, die zwei Assets tragen** (zwei Zarr-Gruppen mit derselben Variable, H2) werden in der Ausgabe nicht angeboten; der Auftrag kann sie nicht nennen.
  6. **Speichergrenze:** Eine Antwort `413` der Schätzung mit „of memory“ sperrt „Start job“; der Grund steht nur im Tooltip des Knopfes (§14: kein Satz im Panel), nicht
     als Zeile. Ein anderes `413` behält den Hinweis zur ganzen Szene.
  7. **`normalize.bands`** wählt das Panel als Chips (Vorschlag: das letzte Ergebnis), bis NM4-11b das Formular der Methoden bringt.
- **Umdeutung von Version 1 im Browser** (`recipeUpgrade.ts`, dieselbe Regel und dieselben Fälle wie `processing/upgrade.py`): hochgeladene `recipe.json` (Meldung „Recipe loaded.“
  mit dem Tooltip „Converted from recipe version 1.“), Permalink (Hinweis „Converted from recipe version 1.“ nur, wenn sonst nichts zu sagen ist; eine Meldung dieser Art
  hat keinen Tooltip) und Kopien der Aufträge in der Ablage des Browsers (`jobShelf.orderCopy`). Der Name eines Assets mit mehreren Bändern (`visual` → `visual_1` …) ist
  im Browser nur bei „Load recipe…“ bekannt, wo die Auswahl die Bänder kennt; ein Zarr-Schlüssel in einem Permalink der Version 1 nennt die Variable nicht (wie S1 und H2 in
  `adr/0014` §15, NM4-43c).
- **Hinweis „Resampled to a common grid“ (Backlog 51).** Das Backend unterscheidet beide Fälle seit NM4-43c (`BandMeta.resampled`, `test_stock_run.py`); das Frontend liest
  `earthx:resampled` unverändert und zeigt den Hinweis nur im Tooltip. Eine gröbere Maskenschicht allein markiert nichts, ein umgerechnetes Wertband schon.
- **Übergangsfrist (Otto, 2026-10-30, fest).** `intake.VERSION_1_ACCEPTED_UNTIL` bleibt ungesetzt, `api` nimmt Version 1 weiter an. Gesetzt wird die Konstante beim ersten
  öffentlichen Deploy (M6) auf 30 Tage danach (§11); vorher gibt es keine Frist, die ablaufen könnte.
- **Annahme der Auslegungen (Otto, 2026-10-30).** Die Auslegungen 1 bis 7 oben sind angenommen.

### 18.1 Änderungen nach dem Review zu #250 (Otto, 2026-10-30)

- **Vorgabename `result`** (ersetzt `Band_Math_<n>` aus §6 und §14): `result`, ist der Name belegt (Band des Datensatzes oder anderes Ergebnis, ohne Rücksicht auf Groß- und
  Kleinschreibung), dann `result_1`, `result_2`, … Eindeutig bleibt es über „der erste freie Name dieser Folge“ unabhängig von der Stelle des Schritts, so dass Verschieben und Entfernen
  keinen Namen kollidieren lässt. Die Umdeutung von Version 1 (§11) nennt weiter `band_math` und `band_math_<n>`.
- **Name ändern:** Ein Name wird erst beim Verlassen des Feldes (oder mit Enter) übernommen, und nur wenn er keine Regel aus §6 verletzt. Ein Name gegen die Regeln wird **nie** übernommen:
  Das Feld bleibt mit dem Getippten stehen, der Rahmen wird rot und ein kleiner Hinweis steht sofort darunter (`'red' is already a band name`). Solange das so ist, sind „Add step“,
  „Review“ und „Start job“ gesperrt (Grund im Tooltip, `OrderView.nameBlock`). Das ersetzt die Auslegung 4 oben (Verweise bleiben beim letzten gültigen Namen).
- **Erklärtexte** in den Schritten stehen im Tooltip eines ⓘ neben der Beschriftung (Tooltip-Komponente aus NM4-52), nicht im Kasten. Bei „Resolution“ steht die Einheit klein darunter (`in m`, `in °`); die Zellgröße steht im Tooltip.
- **Vorschau und Felder** zeigen immer dieselbe Skala: Wird ein Bild gezeichnet, während seine Messung noch unterwegs ist (länger als 5 s), tragen die Felder jetzt die Startskala des Bildes
  und nicht mehr die Werte der Formel davor.
- **Zweite Runde des Reviews (Otto, 2026-10-30).** (1) Die Ergebnis-Chips an einem Schritt fügen wie die Band-Chips oben nur ein, wenn der Cursor in einem Ausdrucksfeld steht, sonst nichts
  (kein Fokuswechsel). (2) Die Einheit der Auflösung steht klein **neben** der Beschriftung „Resolution“ (`in m`, `in °`), nicht darunter. (3) Ein EPSG-Code im falschen Format meldet
  `Needs to be in the format "EPSG:3035"` statt des Musters. (4) Ein Ausdruck darf nur Bänder des Datensatzes und Ergebnisse früherer Schritte nennen: Alles andere meldet sofort am Feld
  `'re' is not a band name` und sperrt wie ein ungültiger Name „Add step“, „Review“ und „Start job“ (Grund im Tooltip); ein Ergebnis eines späteren Schritts meldet `'x' is added by a later step`.
  Wo der Datensatz keine Bänder nennt, wird nichts verglichen.
- **Letzte Runde des Reviews (Otto, 2026-10-30).** (1) Hat der Datensatz genau ein wählbares Band, ist es nur so lange angehakt, wie die Person die Wahl nicht angefasst hat: Das erste Ergebnis
  eines `band_math`-Schritts nimmt seinen Platz ein, die Ausgabe sind dann die Ergebnisse. Das ersetzt den Satz in §9 Punkt 2, nach dem beide angehakt sind. Hat die Person das Band selbst
  angehakt, bleibt es. Ein Entwurf, der schon Ergebnisse mitbringt (Rezept, Permalink), bekommt das Band beim Öffnen nicht. (2) Im Tooltip der Auflösungsmethoden stehen die Methoden untereinander,
  mit einer Leerzeile dazwischen (Zeilenumbrüche im Tooltip bleiben erhalten). (3) Das ⓘ ist klein geschrieben (die Beschriftungen sind in Großbuchstaben, das große ⓘ ist ein anderes Zeichen).
  (4) „Align“ ist beschrieben: Das Raster liegt auf ganzen Vielfachen der Auflösung, Ergebnisse verschiedener Flächen oder Tage passen dann Pixel auf Pixel, und das Ergebnis kann bis zu ein
  Pixel an jeder Seite weiter reichen (Text in der Prozessbeschreibung, `reproject`).
- **Ausdruck muss ein Ausdruck sein (Otto, 2026-10-30).** Ein Text, der kein Ausdruck ist (etwa `red red` oder `nir -`), meldet sofort am Feld `Enter a valid expression` und sperrt wie ein
  ungültiger Name „Add step“, „Review“ und „Start job“. Das Panel prüft nur die Form (Zahlen, Bänder, `+ - * / **`, Vergleiche, `& | ~`, Aufrufe wie `where(c, a, b)`, Klammern; `processingBands.ts:
  isExpression`); welche Namen Bänder sind, prüft `readProblem` danach, die Typen der Server. Ein leerer Ausdruck bleibt beim „Required.“ des Formulars.


---

## 19. Nachtrag NM4-43e PR 2: Vorschau „Show“ und Ergebnis-Layer je Band (2026-10-30; zu §10, §14, §18)

Umgesetzt ist PR 2 von NM4-43e (nur Frontend): ein Dropdown, das Band der Ausgabe wählt, das die Vorschau zeigt, und dasselbe für den Ergebnis-Layer. §10 (P1) bleibt maßgeblich;
dieser Nachtrag nennt, was daraus geworden ist, und die Auslegungen, die der Plan offen ließ. Der Baustein des Dropdowns (`BandSelect.tsx`) steht bereit, NM4-45 (Band in der Ansicht) war
noch nicht gemergt und kann ihn übernehmen.

- **„Show“ in der Vorschau** (Wunsch Otto, Review zu #250): links neben min und max; die Felder min und max sind schmaler (`9ch + 36px` statt `11ch + 44px`; ein Wert wie `-0.123456`,
  `8848.86` oder `-11000` passt noch ganz, geprüft mit `e2e/range-layout.cjs`). Das Dropdown erscheint nur bei mehr als einem Band in der Ausgabe. Es listet die Bänder der Ausgabe, die
  Ergebnisse der `band_math`-Schritte oben, darunter die Bänder des Datensatzes in der Reihenfolge des Items. Vorgabe: das zuletzt **angelegte** Ergebnis (höchster Schrittschlüssel, nicht
  der letzte der Kette), sonst das erste Band der Ausgabe.
- **Was die Kachel bekommt.** `band=<Name>` an Item-Kachel, Mosaik-Kachel, TileJSON und Statistik (der Name kodiert über `URLSearchParams`), und nur die Assets, die das Band braucht
  (`processingPreview.ts: namesNeeded`, `previewRead`; die Spur des Planers von hinten, `processing/plan.py: _trace`, mit der Schicht von `mask` für jedes Band). `MAX_PREVIEW_ASSETS` und
  der Hinweis „No preview: the map takes at most 16 bands.“ gelten damit für die gelesenen Assets: NDVI mit Maske aus einer Ausgabe von 20 Bändern liest drei Assets und hat eine Vorschau.
- **Eine Skala je Band.** Die Messung, ihr Schlüssel und der Hinweis „Index oder nicht“ gehören zum gezeigten Band: Nur ein Ergebnis von `band_math` gilt als Index (−1…1, `rdylgn`), ein Band des
  Datensatzes nie, auch wenn seine Werte in −1…1 liegen. Bei „AOI only“ liest das Panel die Statistik der ganzen Ausgabe einmal (`areaStatistics`, je Auftrag gemerkt) und nimmt das Band über seinen
  Namen; nennt die Antwort das Band nicht, fällt die Messung wie bisher auf die erste ganze Szene zurück.
- **Ergebnis-Layer.** In der Zeile des Layer-Managers das Dropdown „Band“, nur bei mehr als einem Band in `result.tif` (Namen aus `properties.bands[].name`, Reihenfolge der Datei). Es wählt über
  `bidx` (Platz + 1), die Farbskala je Band kommt aus `properties.bands[].statistics`; ein Wechsel fragt den Server nichts. Die Route der Kachel brauchte nichts (`bidx` und die Statistik je Band
  gab es seit NM4-43d und M4-32), das Backend bleibt unberührt. „Apply“ behält das Band (`restyledTileUrl` hält `bidx`), „Save“ gilt je Band: `ShelfJob.bandRanges` (Name → Bereich, im Browser
  gehalten, ohne neue Version der Ablage, weil das Feld optional ist); ein Ergebnis mit einem Band behält `range` wie bisher.
- **Auslegungen (Vorschlag, gelten bis Otto widerspricht).**
  1. **Ein Bereich von Hand gilt für das Band, für das er gesetzt wurde.** Wechselt „Show“, kehrt die Vorschau zur Messung des neuen Bandes zurück (wie „Auto stretch“); der Bereich von Hand geht
     nicht mit. Beim Start eines Auftrags mit mehreren Bändern hält das Panel ihn unter dem Namen des gezeigten Bandes (`bandRanges`), nicht als `range` des Auftrags.
  2. **Was die Karte nicht zeichnen kann, steht nicht im Dropdown:** das Ergebnis eines Schritts hinter einem Schritt, der keine Kachel ist (etwa `reproject`), und ein Name, den der Datensatz nicht
     hat. Das ist grundsätzlich, nicht nur im Moment (UI-01 §4: ausblenden). Die Ausgabe selbst ändert das nicht.
  3. **Ist die Ausgabe leer**, zeigt die Vorschau wie bisher, was die Kachel allein wählt (letztes Ergebnis, sonst erstes Band) und liest die Assets des Auftrags; kein Dropdown.
  4. **Name der Vorschau als Ebene:** Bei mehr als einem Band trägt „Add preview to layers“ den Namen des Bandes („Preview · Band math · ndvi“), damit zwei Ebenen nicht gleich heißen.
  5. ~~Das Band eines Ergebnis-Layers beginnt mit dem ersten Band der Datei.~~ Ersetzt durch die Antwort Ottos unten.
  6. **Ein Ergebnis gilt je Band als Index**, wenn ein `band_math`-Schritt der Kopie des Auftrags es angelegt hat; ohne die Kopie gilt wie bisher die Eigenschaft `processing:expression` des
     Ergebnisses für alle Bänder.

### 19.1 Antworten Ottos zu #255 (2026-10-31)

- **Angenommen:** die Auslegungen 1, 2, 3, 5 und 6; Ottos Abweichung („Auslegung 4“) meint den Beginn des Ergebnis-Layers, den die Liste oben als Nummer 5 führt (nächster Punkt); der Name der
  Vorschau-Ebene mit dem Bandnamen (Nummer 4) ist angenommen.
- **Der Ergebnis-Layer beginnt mit demselben Band wie die Vorschau.** Die Regel für beide (`processingBands.ts: startBand`): das zuletzt angelegte Ergebnis, sonst das erste Band. Beim Start eines
  Auftrags aus dem Panel merkt sich das Panel das Band, das die Vorschau zeigte (`ShelfJob.shownBand`, nur bei mehr als einem Band in der Ausgabe); der Layer beginnt damit
  (`resultLayer.ts: startPlaceOf`). Kennt der Auftrag es nicht (Download-Dialog, Kopie aus der Zeit davor), gilt das letzte Ergebnis eines `band_math`-Schritts der Kopie des Auftrags in der Reihenfolge der
  Kette — die Reihenfolge des Anlegens steht nicht in der Datei —, sonst das erste Band.
- **RGB ist aus diesem PR herausgenommen** (Otto, 2026-10-31) und eine eigene Aufgabe, NM4-64: Registry-Feld `earthx:true_color`, bis zu drei `band=` an den Kachel-Routen, Frontend. Dieser PR enthält davon nichts.
