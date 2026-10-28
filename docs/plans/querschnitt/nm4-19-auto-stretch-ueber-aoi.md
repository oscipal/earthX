# NM4-19 — Auto stretch der Vorschau über die AOI

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 19 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** nicht gleichzeitig mit NM4-04 (`tiler`-Routen); höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-19 aus `docs/plans/querschnitt/nm4-19-auto-stretch-ueber-aoi.md` aus.“

## 1. Anlass

Seit M4-19c misst die Vorschau ihre Farbskala über die erste Szene, auch bei „AOI only“ über die ganze Szene. Das Job-Ergebnis nimmt die Statistik über die AOI-Maske (M4-32). Vorschau und Ergebnis können sich deshalb unterscheiden.

## 2. Soll

- Bei „AOI only“ misst auch die Vorschau über die AOI; Vorschau und Ergebnis zeigen dieselbe Farbskala.
- **Harte Grenze:** keine AOI in URLs oder Logs. Die AOI geht nur im Body an den `tiler` (etwa `POST /statistics` mit GeoJSON, wie rio-tiler es kennt), nie als Query.

## 3. Im Plan klären (mit Optionen und Empfehlung)

- Schnittstelle: POST-Route, Größen- und Punktgrenze der Geometrie wie bei der Annahme; Cache-Schlüssel ohne AOI im Klartext und ohne Logging.
- Gleiche Methode wie im Job (festes Histogramm, M4-32a), damit die Werte übereinstimmen – mit Test Vorschau-Statistik gleich Job-Statistik.
- Mehrere Szenen bzw. Mosaik eines Überflugs.
- Kosten und Zeitlimit (Höchstwartezeit aus M4-19c bleibt).

## 4. Grenzen

- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- Tests: Statistik über AOI gleich Job-Statistik; AOI erscheint in keinem Log und keiner URL (Test auf Zugriffslog); Grenzen der Geometrie.
- Nachtrag in `adr/0006` bzw. `adr/0014`.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung), nicht nur jsdom, in Hell- und Dunkelmodus und bei schmalem Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n) mit PR-Nummer. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat, siehe Kopf des Backlogs).
- Vor „fertig“ ist main geholt.

---

# Plan (28.10.2026)

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im Code gelesen, [S] Zusammenfassung oder Suchtreffer, [A] eigene Ableitung. Das Messskript liegt unter `scripts/tile-bench/aoi_statistics.py`, die Aufrufe stehen in §13.

## 6. Kurzfassung

- **Gleiche Werte gibt es nur mit denselben Pixeln.** Der Job zählt auf dem nativen Raster, über `bbox(AOI ∩ Szenen)`, nach dem Umwandeln in den Ausgabetyp, innerhalb der Maske (`rasterize`, `all_touched`), mit dem festen Histogramm von M4-32a [P]. Die Vorschau misst heute auf höchstens 1024 px über die ganze erste Szene, in `float32`, mit den Perzentilen von numpy (rio-tiler) [P]. Ein anderes Verfahren über dieselben groben Pixel reicht nicht.
- **Vorschlag:** eine neue Route `POST /collections/{dataset}/statistics` im `tiler`. Der Body ist **der Auftrag, wie ihn das Panel für den Job baut** (mit AOI, Schritten und Ausgabetyp). Der `tiler` macht daraus mit der Annahme des Jobs (`intake.estimate_order`, ohne `HEAD`) das Rezept und zählt mit dem Code des Jobs: dieselben Quellen und dasselbe Mosaik, dieselben Blöcke, dieselbe Umwandlung, dieselbe Maske, dieselbe `BandStatistics`. Nur die Dateien werden nicht geschrieben. Bis zu einer Grenze ist die Antwort damit **dieselbe Statistik wie im Ergebnisdokument**, Feld für Feld.
- **Grenze:** exakt bis 4 194 304 Pixel (2048²) im Fenster des Jobs; das sind 20 × 20 km bei 10 m. Kalt kostet das 3,3–4,5 s für zwei Assets [M]. Darüber liest die Route dasselbe Fenster auf einem um eine ganze Zahl k gröberen Raster (höchstens wieder 4 Mi Pixel) und sagt `exact: false`. Der 2–98-%-Bereich liegt dann bis 3 % der Spanne daneben [M], Minimum und Maximum deutlich mehr (Frage 2).
- **Mosaik eines Überflugs:** kommt von selbst richtig, weil das Rezept dasselbe ist (`open_mosaic`, erstes gültiges Element je Band und Pixel, Reihenfolge `mosaic_order`). Bei „One job per pass“ bzw. „per scene“ misst die Vorschau den ersten Auftrag (Frage 5).
- **Keine AOI in URL oder Log:** die AOI steht nur im Body; der Pfad trägt nur den Datensatz. Das Zugriffslog schreibt Methode, Pfad, Status und Dauer (`RequestIdMiddleware`). Die Route schreibt eine eigene Zeile ohne AOI, Item-IDs und Hash. Der Cache-Schlüssel ist ein SHA-256 über das Rezept ohne `recipe_id` (Frage 4).
- **Frontend:** bei „AOI only“ und vollständigem Auftrag misst die Vorschau über diese Route, sonst wie heute. Die Wartezeit von 5 s (`MEASURE_WAIT_MS`) bleibt. Rückfall mit kurzem Hinweis im Tooltip.
- **Schnitt:** Backend und Frontend getrennt (Frage 7).

## 7. Befunde

### 7.1 Wie der Job die Statistik der AOI zählt [P]

1. `processing/core.py` `run` (Z. 405ff.): `crop_window` legt das Fenster `bbox(AOI ∩ Raster)` auf dem feinsten Raster fest, nach außen auf ganze Pixel gerundet (`plan.py` Z. 168).
2. `_write_mask` (Z. 388) rasterisiert die AOI je Block mit `all_touched=True` auf das Raster des letzten Durchgangs.
3. `_Run.write_pass` (Z. 274): je Block von 1024² `_cast` in den Ausgabetyp (runden und begrenzen wie GDAL), `written` ohne Werte, die auf das ganzzahlige nodata fallen, dann `_count`: innen in die Statistik der AOI.
4. `processing/statistics.py`: `minimum`, `maximum`, `count` und `mean` sind exakt; `percentile_2`/`percentile_98` kommen aus einem festen Histogramm (je Wert ein Fach bis 16 Bit, sonst 65 536 Fächer des `float32`-Musters, relative Breite 2⁻⁷) und sind von der Reihenfolge der Werte unabhängig. `stddev` hängt von der Reihenfolge der Blöcke ab, ist für eine feste Folge aber gleich.
5. Die Farbskala liest davon nur `minimum`, `maximum`, `percentile_2`, `percentile_98` (`render.ts::scaleOf`): Index, wenn eine Band-math-Ausgabe ganz in −1…1 liegt (Minimum und Maximum), sonst 2–98 %.

### 7.2 Was die Vorschau heute misst (M4-19c) [P]

- `processingPreview.ts::previewSpec` baut `GET …/items/{erste Szene}/statistics?op=…` für die **erste Szene der Auswahl**, bei „AOI only“ für die **ganze** Szene (Otto, 24.10.2026, Frage 7 Option 1).
- `OperatorTileReader.preview` liest höchstens 1024 px an der langen Seite (Übersichten, `nearest`), danach die Kerne, danach `ImageData.statistics` von rio-tiler: numpy-Perzentile, kein Ausgabetyp, keine Maske.
- Abweichungen vom Job also: andere Pixel (Übersicht statt nativ), andere Fläche (Szene statt AOI), andere Szenen (eine statt Mosaik), anderer Typ (`float32` statt z. B. `uint8`), anderes Verfahren für die Perzentile.

### 7.3 TiTilers POST-Statistik reicht nicht [P]

titiler.core 2.3.0 `TilerFactory.statistics` registriert neben GET auch `POST /statistics` mit GeoJSON-`Feature` im Body (`postStatisticsForGeoJSON`). Es liest mit `Reader.feature` (rio-tiler 9.4.6) höchstens `max_size` Pixel, gewichtet mit einem Bedeckungsanteil (`get_coverage_array`, `cover_scale`) und rechnet numpy-Perzentile. Es kennt ein Item, kein Mosaik, keinen Ausgabetyp. Die Werte wären damit **nicht** die des Jobs. Den Weg „AOI im Body, nie in der Query“ nehmen wir von dort; das Lesen und Zählen nicht.

### 7.4 Die Annahme des Jobs im `tiler` [P]

- `api/intake.py::estimate_order` macht aus dem Auftrag das Rezept, ohne eine Anfrage an ein Asset (Stufen 1–6): Form, Grenzen, Lizenzstufe *processing*, Schritte `applicable`, Items über die Item-Quelle, Gruppen, die die AOI nicht berührt, fallen weg, Reihenfolge des Mosaiks, Hosts. Die Texte der Ablehnungen nennen Felder, Datensätze, Items und Operatoren, nie die AOI (Modulkopf).
- Der `tiler` hat dieselbe Item-Quelle (`app.state.earthx_item_source`) und kennt `OrderRefused` schon (`_fetch_item`). `api → api` und `api → processing` sind erlaubt (architekturplan 3.1); der Worker-Kern `processing` bleibt ohne `gateway`, Datenbank und Queue (B9), er bekommt nur das Rezept.
- `estimate_order` schreibt eine Zeile „order estimated“ (Datensatz, Anzahl Items und Assets, Operatoren). Für diese Route wäre die Zeile irreführend (KE2).

### 7.5 Kosten [M, A]

Gemessen in der Sitzung gegen eine echte Szene (Sentinel-2 C1 L2A, Kachel 32UPU, August 2025, offene Copernicus-Lizenz; nichts davon liegt im Repo), `B04` und `B08`, Fenster in der Mitte der Szene, GDAL wie die Kachel-Routen (NM4-26), je Aufruf ein Prozess, also kalt:

| Fenster (10 m) | gelesene Pixel je Asset | Lesen | Öffnen + Lesen |
|---|---|---|---|
| 1024² nativ (10 km) | 1 Mi | 1,5–2,2 s | 2,5–3,7 s |
| 2048² nativ (20 km) | 4 Mi | 2,7–3,8 s | 3,3–4,5 s |
| 4096² nativ (41 km) | 16 Mi | 10,6 s | 11,6 s |
| 8192² nativ (82 km) | 64 Mi | 25,2 s | 26,3 s |
| 8192², k = 4 | 4 Mi | 2,1–2,5 s | 2,7–3,2 s |
| 8192², k = 8 | 1 Mi | 0,8 s | 1,4 s |

- Die heutige Messung liest 1 Mi Pixel je Asset aus den Übersichten. Exakt bis 4 Mi kostet etwa eine Sekunde mehr und bleibt unter der Wartezeit von 5 s.
- Jede weitere Datei kostet kalt rund 0,6–1 s für den Kopf; `open_mosaic` öffnet nacheinander. Eine Kette mit `mask` (drei Assets) über zwei Szenen öffnet 6 Dateien [A: 4–7 s]. Deshalb eine Grenze für die Dateien (KE4).
- Speicher: der Job zählt blockweise (1024²), die Route auch; höchstens ein Block je Asset im Speicher [P].
- Mit Cache (Frage 4) kostet eine Wiederholung eine Datenbankabfrage.

### 7.6 Wie weit eine gröbere Messung danebenliegt [M]

Gleiches Verfahren (festes Histogramm, Maske auf dem groben Raster), AOI ein Kreis im Fenster. Abweichung des 2- und 98-%-Werts in Prozent der exakten Spanne `p98 − p2`:

| Fenster | k | gelesen | `red` p2 / p98 | NDVI p2 / p98 |
|---|---|---|---|---|
| 2048² | 2 | 1 Mi | 0,2 / 1,0 | 0,3 / 0 |
| 4096² | 2 | 4 Mi | 0,2 / 1,0 | 0,6 / 0 |
| 4096² | 4 | 1 Mi | 0,5 / 2,4 | 1,4 / 0,5 |
| 8192² | 2 | 16 Mi | 0,1 / 1,0 | 0,9 / 0,4 |
| 8192² | 4 | 4 Mi | 0,3 / 2,9 | 2,6 / 0,4 |
| 8192² | 8 | 1 Mi | 0,5 / 6,4 | 6,5 / 1,3 |

- Mit 4 Mi Pixeln bleibt der Bereich der Farbskala in allen Fällen innerhalb von 3 % der Spanne; mit 1 Mi (der Größe von heute) bis 6,5 %.
- **Minimum und Maximum glätten die Übersichten weg:** NDVI exakt bis 1,35 (negative Reflexion nach `offset` −0,1), grob in jedem Fall unter 0,95. Die Regel „Index, wenn ganz in −1…1“ (`scaleOf`) entscheidet dann grob „Index, −1…1 `rdylgn`“, beim Job „2–98 %, `viridis`“. Eine gröbere Messung kann also eine **ganz andere** Farbskala wählen. Das gilt heute schon für die Messung von M4-19c. Exakt gemessen kann es das nicht.

### 7.7 Grenzen der Geometrie bei der Annahme [P]

- Auftrag: höchstens 1 048 576 Byte Body (`processing_route.MAX_BODY_BYTES`, `413`), AOI `Polygon` oder `MultiPolygon`, Ringe geschlossen, gültig (`recipe.Aoi`, `422`). Eine Grenze der Punkte hat die Annahme **nicht**.
- Hochladen einer AOI: höchstens 20 000 Positionen (`aoi_upload.MAX_AOI_POINTS`). Jede AOI aus einer Datei ist also schon darunter; gezeichnete haben wenige Punkte.
- Der Download des Zuschnitts (`POST /collections/{dataset}/download`) liest den Body ohne eigene Grenze (FastAPI). Für die neue Route nicht übernehmen (KE3).

### 7.8 Log und URL heute [P]

- uvicorn läuft ohne eigenes Zugriffslog; `RequestIdMiddleware` schreibt Methode, Pfad (`loggable_path`), Status, Dauer, nie die Query (`earthx/logging.py`). `tests/integration/test_access_log.py` prüft das am echten Server.
- Die Statistik-Cache-Schlüssel sind SHA-256 und stehen in keinem Log (`access/tiles.py::statistics_cache_key`, `_cache_get`/`_cache_set` loggen nur „unreadable“/„not writable“).
- Ein Body mit Validierungsfehler kann in der **Antwort** von FastAPI wiederkommen (`input`). Die Route nimmt den Body roh und gibt ihn an `estimate_order`, dessen Texte keine AOI nennen [P]; die Antwort bleibt damit ohne Koordinaten (Test).

## 8. Optionen und Empfehlung

### 8.1 Schnittstelle (Frage 1)

| | Weg | gleich dem Job | Aufwand |
|---|---|---|---|
| **S1** | `POST /collections/{dataset}/statistics` im `tiler`, Body = Auftrag; `estimate_order`, dann die Zählung des Jobs ohne Schreiben | ja, bis zur Grenze, für Item und Mosaik | mittel |
| S2 | TiTilers `POST …/items/{item}/statistics` mit GeoJSON-`Feature` (§7.3) | nein (anderes Lesen und Verfahren, ein Item) | klein |
| S3 | eigener schmaler Body (`items`, `assets`, `steps`, `aoi`) | ja, aber die Annahme doppelt gebaut | groß |

**Empfehlung S1.** Der Weg vom Auftrag zum Rezept ist dann einer, und die Gleichheit folgt aus dem Code, nicht aus einem Nachbau. Im Kern kommt eine Funktion `area_statistics(recipe, operators, max_pixels)` dazu; `write_pass` und sie teilen sich das Zählen je Block (Umwandlung, `written`, Maske, `_count`), damit beide nicht auseinanderlaufen. `dataset` im Pfad muss dem des Auftrags gleichen (`422`), damit Lizenz und Fehlerseite wie bei den übrigen Routen am Pfad hängen.

**Antwort** (KE5): je Band `name`, `unit` und `statistics` genau wie im Ergebnisdokument (STAC 1.1 plus Perzentile), dazu `exact` (bool) und `factor` (k). Das Frontend liest sie mit derselben Abbildung wie die Statistik eines Ergebnisses.

### 8.2 Grenze und Lesen darüber (Frage 2)

| | bis wann exakt | darüber |
|---|---|---|
| **G1** | 4 Mi Pixel im Fenster des Jobs (2048²) | gröber um ganzzahliges k auf höchstens 4 Mi, `exact: false` |
| G2 | 1 Mi (1024², wie heute) | gröber auf 1 Mi |
| G3 | 16 Mi (4096²) | gröber auf 16 Mi; kalt rund 12 s, länger als die Wartezeit |
| G4 | 4 Mi | `413`, Rückfall auf die Messung von heute |

**Empfehlung G1.** Bis 20 × 20 km (Sentinel-2) ist die Farbskala die des Ergebnisses, im Rahmen von 5 s. Darüber ist sie besser als heute (AOI statt Szene, gleiches Verfahren), aber nicht gleich: ein kurzer Hinweis im Tooltip („Range measured on a coarser read; the result may differ“). k ist eine ganze Zahl, damit das grobe Raster auf dem Raster des Jobs liegt; gelesen wird mit `Source.read` auf dem groben Raster (`nearest`, GDAL nimmt die Übersicht, wie bei der Vorschau heute).

### 8.3 Grenzen der Geometrie und des Bodys (Frage 3)

**Empfehlung:** wie bei der Annahme und beim Hochladen zusammen:

1. Body höchstens 1 048 576 Byte (`413` vor dem Lesen des Rests, wie `_read_body`), nur `application/json` (`415`);
2. AOI höchstens 20 000 Positionen (`413`), sonst die Prüfungen von `recipe.Aoi` (`422`);
3. ohne `aoi` (`Whole scene`) `422`: diese Route misst eine Fläche (Frage 6);
4. alle Prüfungen vor dem ersten Item-Abruf; die Grenze der Dateien (KE4) nach dem Item-Abruf, vor dem Öffnen der ersten Datei.

Die Annahme des Jobs bekommt keine Punktgrenze dazu; das wäre eine eigene Entscheidung.

### 8.4 Cache (Frage 4)

| | Schlüssel | wo |
|---|---|---|
| **C1** | SHA-256 über das kanonische Rezept ohne `recipe_id` (mit AOI, Schritten, Typ, aufgelösten Assets), Präfix `area-statistics/v1` | bestehender Statistik-Cache (Postgres, `adr/0006` §4.3), dazu im Browser die letzten Messungen je Auftragstext |
| C2 | kein Server-Cache | nur im Browser, je Sitzung |

**Empfehlung C1.** Der Schlüssel enthält die AOI nicht im Klartext und steht in keinem Log, keiner URL und keiner Antwort. Ohne Versionen (die Schätzung macht kein `HEAD`) kann ein Eintrag veralten, wenn die Quelle ein Asset ersetzt. Das gilt heute ebenso für den Statistik-Cache der GET-Route, und die Dauer des Caches bleibt dieselbe. Ein Cache-Fehler macht langsamer, nie falsch (E5).

### 8.5 Mehrere Aufträge (Frage 5)

„One job“ ist ein Auftrag: das Mosaik des Überflugs (oder eine Szene). „One job per pass“ und „per scene“ sind mehrere Aufträge mit je eigener Statistik; die Vorschau hat eine Farbskala.

1. **Den ersten Auftrag messen** (`parts[0]`), wie heute die erste Szene. Für dieses Ergebnis ist die Farbskala gleich, für die anderen nicht. **(Empfehlung)**
2. Alle messen und die Bereiche vereinigen: gleich keinem Ergebnis, Kosten × Aufträge.

### 8.6 „Whole scene“ (Frage 6)

1. **Bleibt wie heute** (GET, erste Szene, 1024 px). Die Aufgabe nennt nur „AOI only“. **(Empfehlung)**
2. Auch über die neue Route (die Fläche ist dann die Vereinigung der Footprints, wie im Job). Eine ganze Szene sind 120 Mi Pixel, also immer gröber (k = 6); das Verfahren wäre aber dasselbe.

### 8.7 Schnitt (Frage 7)

Schätzung: Backend ~220 Zeilen Code, ~320 Tests; Frontend ~110 Code, ~150 Tests; Doku ~60.

1. Zwei PRs in dieser Session: NM4-19a Backend, danach NM4-19b Frontend auf a gestapelt.
2. Ein PR mit rund 850 Zeilen.
3. **Diese Session nur das Backend (NM4-19a); das Frontend als NM4-19b nach dem Merge in neuer Session**, wie bei NM4-04. **(Empfehlung)** Die Prüfung im echten Browser gehört dann zu NM4-19b; NM4-19a prüft die Route mit PowerShell.

## 9. Kleinentscheidungen

Gelten, sofern du nicht widersprichst:

- **KE1 Rückfall im Panel:** Ohne vollständigen Auftrag (`parts[0].order` ist `null`), bei einer abgeschnittenen Kette (die Vorschau zeigt nur die ersten Schritte), bei `413` oder einem Fehler der Route misst die Vorschau wie heute (GET, erste Szene). Dann steht im Tooltip der Vorschau „Range measured over the first whole scene“. Kein Text im Panel (UI-01 §4). Eine Ablehnung eines Schritts (`422` mit Platz) zeigt das Panel wie bisher.
- **KE2 Log:** Die Route schreibt genau eine Zeile „area statistics measured“ mit Datensatz, Anzahl Szenen, Anzahl Assets, k, gelesenen Pixeln und Sekunden; keine AOI, keine Item-ID, kein Hash, kein Ausdruck. `estimate_order` bekommt dafür einen Schalter, damit „order estimated“ hier nicht erscheint. Abgelehnte Aufträge loggt `_log_refused` wie bei der Annahme (Stufe, Status, Grund; die Gründe nennen keine AOI).
- **KE3 Body roh lesen:** wie `processing_route._read_body` (Grenze beim Lesen, nicht erst danach); kein Pydantic-Modell am Body, damit eine fehlerhafte AOI nicht in einer `422` von FastAPI zurückkommt.
- **KE4 Dateien:** höchstens 16 Dateien je Messung (Szenen × Assets), `413` vor dem Öffnen. Darüber Rückfall (KE1).
- **KE5 Antwort:** wie §8.1; `Cache-Control: no-store`, weil die Antwort zu einem Body gehört, den kein Zwischenspeicher kennt.
- **KE6 Schritte:** nur Schritte der Art `pixel` (wie die Kachel, T1); ein `grid`-Schritt (`reproject`) → `422`, im Panel Rückfall. Der Ausgabetyp des Auftrags gilt (die Umwandlung des Jobs, `_cast`).
- **KE7 GDAL und Faden:** Profil der Kachel-Routen (`tile_gdal_options`), Lesen in `run_in_threadpool` wie die GET-Statistik; ein Lesefehler (`RasterioIOError`) wird einmal wiederholt wie dort.
- **KE8 Wartezeit:** `MEASURE_WAIT_MS` (5 s) bleibt; kommt die Messung später, wird sie wie heute übernommen (ein Neuzeichnen, nur wenn sich der Bereich ändert). Keine neue Zeitgrenze im Server.

## 10. Tests (Abnahme)

Backend (`pytest`, synthetische COGs wie `processing/test_core_statistics.py`, `api/test_tiler_statistics_operator.py`):

1. **Gleich dem Job:** dieselbe Bestellung einmal über die Route, einmal als Job (`run`): `statistics` je Band gleich (Dict-Gleichheit, auch `stddev`). Fälle: eine Szene mit NDVI; Mosaik aus zwei Szenen auf einem Raster; Kette `mask → band_math`; Ausgabetyp `uint8` (Runden, nodata-Kollision); eine AOI, deren Bounding Box deutlich andere Werte hat als die AOI (wie M4-32).
2. **Über der Grenze:** `exact: false`, `factor` > 1, Werte aus dem groben Lesen; die Grenze selbst (2048² exakt, 2049 × 2048 nicht).
3. **Grenzen vor dem Abruf:** Body 1 048 577 Byte → `413`, 20 001 Positionen → `413`, falscher `content-type` → `415`, Punkt oder Linie, offener Ring, Selbstschnitt → `422`, ohne `aoi` → `422`, `dataset` im Pfad ≠ Auftrag → `422`, Export statt Raster → `422`, `reproject` → `422`; jeweils 0 Item-Abrufe. 17 Dateien → `413` mit 0 geöffneten Dateien.
4. **Lizenz und Fremdes:** Datensatz unter *processing* → `403`; unbekanntes Item → `422`; AOI außerhalb aller Szenen → `422`.
5. **Kein Leck:** am echten Server (uvicorn, wie `test_access_log.py`): eine Messung und eine abgelehnte Messung; in keiner Logzeile eine Koordinate der AOI, eine Item-ID oder der Cache-Schlüssel; der Pfad im Zugriffslog ist `/collections/{dataset}/statistics` ohne Query; die Antwort einer `422` nennt keine Koordinate.
6. **Cache:** zweite Anfrage ohne Lesen (0 geöffnete Dateien); andere AOI → anderer Schlüssel; der Schlüssel enthält keine Zahl der AOI; ein Cache, der wirft, gibt trotzdem die Antwort.
7. **Zustandslos und Start:** zwei frische Apps, gleicher Body → gleiche Antwort; `test_tiler_start_is_light` grün; OpenAPI ohne `url`, `bbox`.
8. **Gegenprobe:** Die Tests 1–6 scheitern gegen `main` (die Route fehlt dort, `405`/`404`).

Frontend (`vitest`, in NM4-19b):

9. „AOI only“ mit vollständigem Auftrag → POST mit dem Auftrag von `parts[0]`, keine GET-Messung, keine AOI in einer URL (Test über alle gebauten URLs); die Farbskala aus der Antwort ist die von `resultRender` für dasselbe Dokument.
10. Rückfälle (KE1): kein Auftrag, abgeschnittene Kette, `413`, `500` → GET wie heute und Hinweis im Tooltip; `exact: false` → Hinweis im Tooltip; „Whole scene“ unverändert.
11. Prüfung im echten Browser (Chromium/Playwright der Sitzung) mit nachgestellten Antworten, hell und dunkel, schmales Fenster; im PR beschrieben.

## 11. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — Schnittstelle**
1. `POST /collections/{dataset}/statistics` im `tiler`, Body = der Auftrag, Annahme und Zählung des Jobs (S1). **(Empfehlung)**
2. TiTilers POST mit GeoJSON am Item (S2): anderes Verfahren, ein Item.
3. Eigener schmaler Body (S3).

**Frage 2 — Grenze**
1. Exakt bis 4 Mi Pixel (2048²), darüber gröber auf 4 Mi mit Hinweis im Tooltip (G1). **(Empfehlung)**
2. 1 Mi wie heute (G2).
3. 16 Mi (G3).
4. Darüber keine AOI-Messung, Rückfall (G4).

**Frage 3 — Grenzen der Geometrie**
1. 1 MB Body, 20 000 Positionen, Prüfungen von `recipe.Aoi`, ohne `aoi` `422`; die Annahme des Jobs bleibt ohne Punktgrenze (§8.3). **(Empfehlung)**
2. Wie 1, und die Annahme des Jobs bekommt dieselbe Punktgrenze (eigene Zeile im Log).

**Frage 4 — Cache**
1. SHA-256 über das Rezept im bestehenden Statistik-Cache, nie geloggt (C1). **(Empfehlung)**
2. Nur im Browser (C2).

**Frage 5 — Mehrere Aufträge**
1. Den ersten Auftrag messen. **(Empfehlung)**
2. Alle messen, Bereiche vereinigen.

**Frage 6 — „Whole scene“**
1. Bleibt wie heute. **(Empfehlung)**
2. Auch über die neue Route.

**Frage 7 — Schnitt**
1. Zwei PRs in dieser Session, gestapelt.
2. Ein PR (~850 Zeilen).
3. Diese Session nur das Backend (NM4-19a); Frontend NM4-19b nach dem Merge in neuer Session. **(Empfehlung)**

## 12. Umsetzung nach Freigabe

Nach den Antworten in dieser Session, je nach Frage 7:

- **NM4-19a (Backend):** `processing/core.py` (`area_statistics`, gemeinsames Zählen je Block mit `write_pass`), `api/intake.py` (Schalter für die Logzeile), `api/tiler.py` (Route, Body, Grenzen, Cache, Log), `access/tiles.py` (Schlüssel `area-statistics/v1`). Tests §10 Nr. 1–8. Nachtrag `adr/0006` (Route, Grenzen, Datenschutz) und `adr/0014` (die Statistik der AOI gibt es jetzt auch ohne Job, aus demselben Code; §15k gilt weiter). Prüfanleitung in PowerShell 5.1. Log-Zeile mit PR-Nummer.
- **NM4-19b (Frontend):** `processingPreview.ts` (Art der Messung: GET oder POST mit Auftrag), `processingStore.ts` (`measureFor` mit Body, Schlüssel = Auftragstext, nur im Speicher), `api.ts` (`postAreaStatistics`), Tooltip. Tests §10 Nr. 9–11.
- `docs/plans/nach-m4-backlog.md`, `CLAUDE.md`, `.github/`, `.claude/`, `CODEOWNERS` bleiben unverändert. Keine neue Abhängigkeit.

## 13. Messanhang

`scripts/tile-bench/aoi_statistics.py` (Kopf des Skripts): `B04` und `B08` einer Szene, Fenster in der Mitte, AOI ein Kreis darin, NDVI in `float32`, Zählung mit `earthx.processing.statistics`. Je Aufruf ein Prozess (kalt):

```bash
PYTHONPATH=backend python -W ignore scripts/tile-bench/aoi_statistics.py <ordner-der-szene> exact 2048
```

```bash
PYTHONPATH=backend python -W ignore scripts/tile-bench/aoi_statistics.py <ordner-der-szene> coarse 8192 4
```

Gemessen am 28.10.2026; 1024², 2048² und 8192² mit k = 4 zweimal (in §7.5 als Spanne), die übrigen einmal. Exakte Werte, aus denen §7.6 rechnet (p2 / p98): `red` 2048² 0,018799 / 0,221680; 4096² 0,017822 / 0,217773; 8192² 0,015381 / 0,214844. NDVI 2048² 0,126953 / 0,902344; 4096² 0,115234 / 0,906250; 8192² 0,001595 / 0,914062. Die Fächer des Histogramms haben die relative Breite 2⁻⁷; ein Fach ist bei `red` um 0,02 rund 0,06 % der Spanne breit.
