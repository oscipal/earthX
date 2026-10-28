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

Ergänzt durch §14 (Freigabe), §15 (NM4-19b Frontend) und §16 (Frage 8). Laut Frage 7, Option 3 setzt diese Session nur das Backend um.

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

## 14. Freigabe (Otto, 28.10.2026, zu #218)

1. Option 1: `POST /collections/{dataset}/statistics` im `tiler`, Body = der Auftrag, `estimate_order` und die Zählung des Jobs.
2. Option 1: exakt bis 4 Mi Pixel, darüber gröber auf 4 Mi, `exact: false`, Hinweis im Tooltip.
3. Option 1: 1 MB Body, 20 000 Positionen, Prüfungen von `recipe.Aoi`, ohne `aoi` `422`; die Annahme des Jobs bleibt ohne Punktgrenze.
4. Option 1: SHA-256 über das Rezept im bestehenden Statistik-Cache, nie geloggt. **Zusatz:** Der Schlüssel hängt am Rezept und damit an der AOI. Ein Eintrag lebt höchstens so lange wie ein Rezept (7 Tage, Q10); der Schlüssel steht nie in Logs oder URLs. Wo der Cache liegt und wie er abläuft: §14.1.
5. Option 1: den ersten Auftrag messen.
6. Option 1: „Whole scene“ bleibt wie heute.
7. Option 3: Diese Session setzt nur das Backend um (#218). Das Frontend folgt nach dem Merge als neue Aufgabe in einer neuen Session (§15).

KE1–KE8 angenommen. **Zusatz Modulgrenzen:** Die Route nutzt `estimate_order` und die Zählung des Jobs; `lint-imports` bleibt ohne Lockerung grün, ein Vertrag im Weg wäre zuerst eine Frage an Otto (§14.2). **Neue Frage 8** vor dem Code zur Index-Regel (§16); bis zur Antwort nur, was nicht davon abhängt. Das Backlog pflegt der Planungs-Chat.

### 14.1 Wo der Cache liegt und wie er abläuft [P]

- **Ort:** die Tabelle `public.earthx_stats_cache` in der Postgres-Datenbank der Plattform (`catalog/migrations/003_stats_cache.sql`), dieselbe wie für die GET-Statistik. Der `tiler` erreicht sie über `statistics_cache` (`api/tiler.py`, eine Verbindung aus dem Pool je Anfrage); ohne Pool gibt es keinen Cache, die Messung wird dann jedes Mal gelesen (E5).
- **Inhalt einer Zeile:** `cache_key` (SHA-256, 64 Hexzeichen), `dataset_id`, `payload` (nur die Statistik je Band, `exact`, `factor`; keine AOI, keine Item-ID, kein Rezept), `expires_at`, `created_at`.
- **Schlüssel:** SHA-256 über `{"kind": "area-statistics/v1", "earthx": <Version>, "recipe": <Hash des Rezepts ohne recipe_id>}` (`recipe_hash`), kanonisch (sortierte Schlüssel, ohne Leerzeichen); die Version, weil eine neue Version anders zählen kann. Das Rezept trägt AOI, Items, Assets mit Skalierung, Schritte und Ausgabetyp; der Hash ist aus der AOI zurückrechenbar (Q8) und gilt deshalb wie ein Rezept als personenbezogen.
- **Ablauf heute:** `PostgresStatsCache.set` setzt `expires_at = now() + ttl_s` (Vorgabe 30 Tage); `get` liest nur Zeilen mit `expires_at > now()`. **Gelöscht wird eine abgelaufene Zeile heute nie**; der Index `earthx_stats_cache_expires_at_idx` ist für ein späteres Aufräumen vorbereitet.
- **Ablauf neu (KE9):**
  1. Die Messung über die AOI schreibt mit `ttl_s` = 7 Tage (`AREA_STATISTICS_TTL_S`, aus derselben Zahl wie die Frist der Läufe, Q10).
  2. Der stündliche Aufräumer der Jobs (`jobs/cleanup.py::cleanup_batch`, dieselbe Transaktion und dieselbe Sperre wie für Läufe, Rezepte, Permalinks und Bundles) löscht abgelaufene Zeilen von `earthx_stats_cache` in Portionen von 5 000. Das betrifft auch die abgelaufenen Zeilen der GET-Statistik (30 Tage); sie werden heute schon nicht mehr gelesen. Ein Eintrag lebt damit höchstens 7 Tage und eine Stunde, wie ein Rezept, dessen letzter Lauf abläuft.
  3. `CleanupResult` zählt die gelöschten Zeilen (`statistics`).
- **Nie in Logs oder URLs:** Der Schlüssel entsteht und bleibt im `tiler`. Ein Fehler des Caches wird auf dieser Route nur mit der Art der Ausnahme geloggt, ohne Text und ohne Traceback, weil der Text einer Datenbank-Ausnahme Werte der Anweisung wiedergeben kann (Test mit einem Cache, der mit dem Schlüssel im Text wirft). Der Aufräumer loggt nur Zahlen. Die Antwort trägt den Schlüssel nicht, die URL auch nicht.

### 14.2 Modulgrenzen [P]

- Neu ist `api/tiler.py → api/intake.py` (`estimate_order`) und `api/tiler.py → processing.core` (`area_statistics`). Beides liegt innerhalb der erlaubten Richtungen (`api` darf alles außer `datasets`, architekturplan 3.1); `api/tiler.py` importiert `processing` schon heute.
- `processing.core.area_statistics` liest wie `run` über `access.open_asset_ref`; kein neuer Import in `processing`.
- `jobs/cleanup.py` löscht mit SQL, ohne `catalog` zu importieren (der Vertrag `jobs` verbietet `catalog`), wie bei den übrigen Tabellen.
- `lint-imports --config .importlinter` läuft vor dem Push; an `.importlinter` ändert sich nichts.

## 15. NM4-19b Frontend (Folgeaufgabe, neue Session)

**Stufe A**, nur Frontend, nach dem Merge von #218. Branch von `main`, ein Draft-PR. Der Abschnitt ist ohne das Gespräch zu NM4-19 verständlich; maßgeblich sind §14, §16 (falls entschieden) und `adr/0006`, Nachtrag NM4-19.

### 15.1 Ausgangslage

- Das Backend (#218) misst die Farbskala über die AOI wie der Job: `POST /collections/{dataset}/statistics` im `tiler`, Body = der Auftrag, wie ihn das Panel für den Job baut (`processingOrder.ts::buildOrder`, das `order` selbst, **ohne** die Hülle `{"inputs": {"recipe": …}}` der Job-Route und ohne `aoiProvenance`), `Content-Type: application/json`, höchstens 1 048 576 Byte, AOI höchstens 20 000 Positionen.
- Antwort `200`: `{"bands": [{"name", "unit"?, "statistics": {minimum, maximum, mean, stddev?, count, valid_percent, percentile_2, percentile_98}}], "exact": bool, "factor": int}`; `statistics` ist genau das Objekt des Ergebnisdokuments eines Jobs (`properties.bands[].statistics`). `exact: false` heißt: gröber gelesen (Fenster über 4 Mi Pixel), die Werte können vom Ergebnis abweichen.
- Ablehnungen: `413` (Body, Positionen, mehr als 16 Dateien), `415`, `422` (Auftrag ungültig, ohne `aoi`, Datensatz im Pfad ≠ Auftrag, `grid`-Schritt, AOI außerhalb), `403` (Lizenz), `502`–`504` (Quelle). Ein abgelehnter Schritt nennt ab zwei Schritten den Platz („step 1: …“).
- Heute misst die Vorschau `GET …/items/{erste Szene}/statistics?op=…` über die ganze erste Szene (`processingPreview.ts::previewSpec` → `measure`, `processingStore.ts::measureFor`, `MEASURE_WAIT_MS` 5 s).

### 15.2 Umfang

1. **Messung über die AOI:** Bei „AOI only“ und vollständigem Auftrag des ersten Jobs (`orderView(...).parts[0].order` ist nicht `null`) misst die Vorschau mit `POST …/statistics` und diesem Auftrag. Bei „One job per pass“ oder „per scene“ gilt `parts[0]` (Frage 5).
2. **Schlüssel der Messung:** der kanonische Auftragstext (`canonicalJson`), nur im Speicher (die bestehende Abbildung der Messungen); er steht in keiner URL, keinem `localStorage`, keinem Log und keiner Fehlermeldung.
3. **Farbskala:** aus `bands[].statistics` mit derselben Abbildung, die ein Ergebnis-Layer nimmt (`resultLayer.ts`/`render.ts::scaleOf`), damit Vorschau und Ergebnis dieselbe Regel haben; die Einheit aus `bands[].unit` (`shownUnit`).
4. **Rückfall (KE1):** ohne vollständigen Auftrag, bei einer abgeschnittenen Kette (die Vorschau zeigt nur die ersten Schritte), bei `413`, `5xx` oder einem Netzfehler misst die Vorschau wie heute (GET, erste Szene). Tooltip der Vorschau dann: „Range measured over the first whole scene“. Eine Ablehnung eines Schritts (`422` mit Platz) zeigt das Panel wie bisher.
5. **Gröbere Messung:** bei `exact: false` im Tooltip der Vorschau „Range measured on a coarser read; the result may differ“. Kein Text im Panel (UI-01 §4).
6. **„Whole scene“** bleibt unverändert (Frage 6). `MEASURE_WAIT_MS` und das spätere Übernehmen bleiben (KE8).
7. Frage 8 (§16) nur, wenn sie bis dahin für NM4-19b entschieden ist.

### 15.3 Abnahme

- `vitest`: „AOI only“ mit vollständigem Auftrag → genau ein POST mit dem Auftrag von `parts[0]`, keine GET-Messung; die Farbskala aus der Antwort ist dieselbe wie die eines Ergebnis-Layers mit denselben `statistics`. Keine AOI, keine Koordinate, kein Auftragstext in einer gebauten URL (Test über alle URLs der Vorschau). Rückfälle aus 15.2 Nr. 4 mit dem Tooltip; `exact: false` mit dem Tooltip; „Whole scene“ unverändert; eine ältere Messung wird verworfen.
- Gegenprobe: Die neuen Tests scheitern gegen den Code vor der Änderung.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung) mit nachgestellten Antworten, hell und dunkel, schmales Fenster; im PR beschrieben.
- `npm run lint`, `npx tsc -b --pretty false`, `npm test` grün; Prüfanleitung für Otto im PR; Log-Zeile mit PR-Nummer; `docs/plans/nach-m4-backlog.md` nicht ändern; vor „fertig“ `main` holen.

## 16. Frage 8 — Index-Regel bei gröberer Messung

### 16.1 Befund [M, P]

- `render.ts::scaleOf` (eine Regel für Vorschau und Ergebnis, M4-32b): Kommen die Werte aus einem Band-math-Schritt und liegen **Minimum und Maximum** aller Bänder in −1…1, gilt −1…1 in `rdylgn` (Index); sonst 2–98 % in `viridis`.
- Gemessen (§7.6): NDVI über eine echte Szene hat exakt Minimum −0,97 und Maximum 1,48 (negative Reflexion nach `offset` −0,1 an wenigen Pixeln), gröber gelesen in jedem Fall unter 0,95. Exakt (also im Job): kein Index, `viridis` 0,0016…0,914. Grob: Index, `rdylgn` −1…1.
- Die neue Route ist bis 4 Mi Pixel exakt; dort tritt der Unterschied nicht auf. Er bleibt über der Grenze und bei der heutigen Messung (GET, „Whole scene“ und Rückfall).
- Die Regel liegt nur im Frontend; das Backend liefert in jedem Fall Minimum, Maximum und die Perzentile. **Das Backend dieses PRs hängt von Frage 8 nicht ab.**

### 16.2 Optionen

| | Regel | Folge |
|---|---|---|
| **R1** | Index, wenn Band math und **p2 ≥ −1 und p98 ≤ 1** (Perzentile statt Minimum/Maximum), für Vorschau und Ergebnis | Einzelne Ausreißer schalten nicht mehr um; das NDVI oben ist dann überall ein Index. Perzentile liegen auch grob nah am Job (≤ 3 % der Spanne, §7.6); nur knapp an der Grenze kann es noch kippen. Ändert die Farbskala bestehender Ergebnis-Layer mit Ausreißern (von `viridis` zu −1…1). |
| R2 | Index nur aus einer exakten Messung; grob immer 2–98 % | Grob nie „Index“; der Job kann aber „Index“ wählen, dann weicht die Vorschau in die andere Richtung ab. |
| R3 | bei grober Messung die Regel aussetzen und −1…1 nehmen, wenn Band math | Grob immer „Index“, auch wo der Job `viridis` zeigt. |
| R4 | Index aus dem Rezept (Index-Knopf, NM4-14, oder Form des Ausdrucks) | Ein Ausdruck sagt nicht verlässlich, ob seine Werte in −1…1 liegen (das NDVI oben tut es nicht); braucht ein neues Feld im Rezept. |
| R5 | bleibt wie heute | Über der Grenze kann die Vorschau eine ganz andere Farbskala zeigen. |

**Empfehlung R1.** Eine Regel, die an den Werten hängt, die auch grob stabil sind, und für Vorschau und Ergebnis dieselbe bleibt (M4-32b). Dass ein NDVI mit wenigen Pixeln über 1 als Index gezeigt wird, ist eher richtig als falsch.

**Wo:** Die Regel ist eine Zeile in `render.ts::scaleOf` mit Tests, nur Frontend. **Empfehlung:** in NM4-19b (dort wird `scaleOf` für die Vorschau ohnehin angefasst), mit Gegenprobe für das NDVI-Beispiel und einem Test, dass ein Ergebnis-Layer dieselbe Regel nimmt. Alternative: eigene Stufe-A-Aufgabe, unabhängig von NM4-19b.

**Frage 8**
1. R1, in NM4-19b. **(Empfehlung)**
2. R1 als eigene Aufgabe.
3. R2.
4. R3.
5. R5, bleibt.

## 17. Umsetzung des Backends (28.10.2026)

- `processing/core.py`: `area_statistics`, `area_factor`, `AreaStatistics`, `MAX_AREA_PIXELS`. Das Zählen je Block (`_written`, `_count`), die Maske je Block (`_mask_block`) und das Lesen je Block (`_read_block`) teilen sich `write_pass`, `_write_mask` und `_run_pass` mit der Messung; die Bytes eines Jobs ändern sich nicht, die Version bleibt.
- `processing/mosaic.py`: `MosaicSource._piece` beschneidet den Teil eines verzerrten Mitglieds auf seinen `WarpedVRT`. Ohne das schlug die gröbere Messung eines Mosaiks mit einer Szene der anderen UTM-Zone fehl (Breite 25 statt 26); auf dem eigenen Raster des Mosaiks liegt jeder Teil schon im VRT.
- `api/area_statistics.py` (neu): die Route, Body roh gelesen (KE3), Grenzen vor dem Abruf, `estimate_order(..., announce=False)`, 16 Dateien, Cache (`area_statistics_cache_key`, 7 Tage), eine Logzeile (KE2), Lese- und Cache-Fehler ohne Text im Log. `api/tiler.py` hängt sie in `build_app` ein.
- `api/intake.py`: `estimate_order` mit `announce` (KE2).
- `access/tiles.py`: `StatsCache.set` nimmt `ttl_s` wie `PostgresStatsCache`.
- `jobs/cleanup.py`: löscht abgelaufene Zeilen von `earthx_stats_cache` (KE9), zählt sie in `CleanupResult.statistics`.
- Tests: `processing/test_area_statistics.py` (24), `api/test_tiler_area_statistics.py` (46), `jobs/test_cleanup.py` (+3), `integration/test_stats_cache.py` (+1), `api/test_tiler.py` (die Route ist die zweite ohne Item im Pfad, wie der Download).
- **Abweichungen von §10:** Nr. 7 nannte `test_tiler_start_is_light`; den Test gibt es im Repo nicht mehr (nur noch ein Verweis im Docstring von `_operator_support`). Stattdessen: Die Route importiert `processing` erst beim ersten Aufruf, wie die Operator-Kachel. Nr. 5 läuft über die ASGI-App mit dem echten `RequestIdMiddleware` und dem echten `JsonFormatter`, wie `tests/integration/test_access_log.py`, nicht über einen uvicorn-Prozess. Ganzzahlige Ausgabe (Nr. 1) mit `mask` allein: Mit `band_math` oder `normalize` hat jede Ausgabe nodata NaN, und eine Ganzzahl-Ausgabe weist der Job dann ab (`_nodata_for`).
- **Gegenprobe:** Gegen `main` scheitern alle neuen Tests der Route und des Kerns, schon beim Import (`earthx.api.area_statistics`, `area_statistics` fehlen); die Route antwortet dort `405`. Die drei Tests des Aufräumers scheitern an `CleanupResult.statistics`.
- **Echte Quelle [M]:** Sentinel-2 C1 L2A, eine Szene vom August 2025, NDVI. Die Item-Quelle ist im Prozess eingesetzt, weil das `gateway` der Sitzung Earth Search nicht erreicht (wie M4-19c §14 (d)); die COG-Lesezugriffe gehen echt über `readers`. AOI 0,08° × 0,08° (0,53 Mi Pixel): kalt 2,6 s, warm 0,13 s; `statistics` **gleich** denen eines Laufs des Kerns auf demselben Rezept. AOI 0,24° × 0,24° (4,8 Mi Pixel): `exact: false`, `factor` 2, kalt 2,8 s; 2–98 % liegen 0,4 bzw. 0,5 % der Spanne neben dem Job, das Maximum grob 0,94 statt 1,48 (Frage 8).
- `ruff check backend`, `lint-imports` (16 Verträge, `.importlinter` unverändert), `pytest` grün; Ergebnis im PR.

### 17.1 Prüfanleitung für Otto (PowerShell 5.1)

Gegen den Stack aus `docker compose`. Die AOI ist ein kleines Quadrat in der Mitte der ersten gefundenen Szene; sie steht nur in dieser Sitzung von PowerShell.

```powershell
docker compose up -d --build
$api = 'http://localhost:8000'; $tiler = 'http://localhost:8001'

# Eine Sentinel-2-Szene und ein Quadrat von 0,08 Grad in ihrer Mitte
$search = @{ collections = @('sentinel-2-c1-l2a'); bbox = @(10.0, 47.0, 10.5, 47.5); limit = 1 } | ConvertTo-Json -Depth 5
$scene = (Invoke-RestMethod -Method Post -Uri "${api}/stac/search" -ContentType application/json -Body $search).features[0]
$x = ($scene.bbox[0] + $scene.bbox[2]) / 2; $y = ($scene.bbox[1] + $scene.bbox[3]) / 2; $h = 0.04
$aoi = @{ type = 'Polygon'; coordinates = @(,@(@(($x-$h),($y-$h)), @(($x+$h),($y-$h)), @(($x+$h),($y+$h)), @(($x-$h),($y+$h)), @(($x-$h),($y-$h)))) }
function New-Order($aoi) {
    @{ recipe_version = 1
       inputs = @(@{ name = 'input'; dataset = 'sentinel-2-c1-l2a'; groups = @(,@($scene.id)); assets = @('red', 'nir') })
       aoi = $aoi
       steps = @(@{ op = 'band_math'; op_version = 1; params = @{ expression = '(nir - red) / (nir + red)' } })
       output = @{ kind = 'raster'; format = 'cog'; dtype = 'float32' } }
}
$order = New-Order $aoi | ConvertTo-Json -Depth 10 -Compress

# 1) Die Messung über die AOI: exact = True, factor = 1; beim zweiten Mal schneller (Cache)
$area = Invoke-RestMethod -Method Post -Uri "${tiler}/collections/sentinel-2-c1-l2a/statistics" -ContentType application/json -Body $order
$area.exact; $area.factor; $area.bands[0].statistics | Format-List

# 2) Derselbe Auftrag als Job: dieselben Zahlen, Feld für Feld (Ausgabe: True)
$job = Invoke-RestMethod -Method Post -Uri "${api}/processing/jobs" -ContentType application/json -Body ("{""inputs"":{""recipe"":$order}}")
do { Start-Sleep 5; $status = (Invoke-RestMethod "${api}/processing/jobs/$($job.jobID)").status } while ($status -in 'accepted', 'running')
$results = Invoke-RestMethod "${api}/processing/jobs/$($job.jobID)/results"
($results.result.properties.bands[0].statistics | ConvertTo-Json -Compress) -eq ($area.bands[0].statistics | ConvertTo-Json -Compress)

# 3) Ein Quadrat von 0,3 Grad: über 2048² Pixel, also gröber gelesen (exact = False, factor >= 2)
$h = 0.15; $big = @{ type = 'Polygon'; coordinates = @(,@(@(($x-$h),($y-$h)), @(($x+$h),($y-$h)), @(($x+$h),($y+$h)), @(($x-$h),($y+$h)), @(($x-$h),($y-$h)))) }
$coarse = Invoke-RestMethod -Method Post -Uri "${tiler}/collections/sentinel-2-c1-l2a/statistics" -ContentType application/json -Body (New-Order $big | ConvertTo-Json -Depth 10 -Compress)
$coarse.exact; $coarse.factor

# 4) Ablehnungen: ohne AOI 422, als GET 405
$whole = New-Order $null; $whole.Remove('aoi')
try { Invoke-RestMethod -Method Post -Uri "${tiler}/collections/sentinel-2-c1-l2a/statistics" -ContentType application/json -Body ($whole | ConvertTo-Json -Depth 10) } catch { $_.Exception.Response.StatusCode.value__ }
try { Invoke-RestMethod "${tiler}/collections/sentinel-2-c1-l2a/statistics" } catch { $_.Exception.Response.StatusCode.value__ }

# 5) Keine AOI im Log: die Zeilen der Messung nennen Pfad, Zahlen und Dauer, keine Koordinate
docker compose logs tiler | Select-String 'area statistics measured|/statistics' | Select-Object -Last 4
docker compose logs tiler | Select-String ([string]::Format('{0:F4}', $x).Replace(',', '.'))   # keine Ausgabe
```

Die Vorschau im Panel ändert sich mit diesem PR noch nicht; das kommt mit NM4-19b (§15).

### 17.2 Review vor dem PR (Subagent `reviewer`, 28.10.2026)

Eingearbeitet:
- Ein `RasterioError`, der kein Lesefehler ist, ging an den Handler des `tiler`, der ihn mit Traceback loggt; GDALs Text kann die Adresse nennen. Die Route fängt ihn jetzt selbst ab: `500`, im Log nur die Art (Test mit einer `WarpOperationError`, deren Text die Adresse trägt; ebenso der Lesefehler mit Wiederholung und `502`).
- Ein Body mit tief verschachteltem `coordinates` gab `500` (`RecursionError`). Jetzt zählt `_positions` ohne Rekursion, und `json.loads` antwortet bei zu tiefer Schachtelung `400` (Tests mit Tiefe 600, 5 000, 200 000).
- Die Cache-Abhängigkeit hielt eine Verbindung des kleinen Pools (5) über die ganze Messung, während der Item-Abruf derselben Anfrage eine zweite braucht: Fünf gleichzeitige Messungen hätten den Pool erschöpft. Neu `catalog.stats_cache.PooledStatsCache` mit einer Verbindung je `get`/`set` (`api.tiler.area_statistics_cache`), Test gegen Postgres.
- Tests ergänzt: Body ohne Länge (gestreamt, `413` beim Lesen), Positionen über ein MultiPolygon, genau 20 000 Positionen.
- Docstrings: am Rand einer Einzelszene liest das grobe Raster den Randwert (`valid_percent` dort etwas höher als im Job); der VRT eines Mosaik-Mitglieds gilt je Mitglied, nicht je Raster.

**Item-IDs im Log, eingeordnet statt geändert:** §10 Nr. 5 des Plans versprach mehr als die Vorgabe: „in keiner Logzeile … eine Item-ID“. Die Grenze der Aufgabe (§4) nennt AOI, Job-, Rezept- und Permalink-Kennungen, Hashes, `href` und signierte URLs, keine Item-IDs. Item-IDs stehen heute im Zugriffslog jeder Kachel-Route (`/collections/{dataset}/items/{item}/…`), in der Zeile „order refused“ der Annahme (`no item '…' in '…'`) und im Pfad der `gateway`-Zeile eines Item-Abrufs. Für diese Route gilt dasselbe: Ihre eigene Zeile nennt kein Item; eine Ablehnung der Annahme und der Item-Abruf schreiben die ID wie bei einem Job. Der Test prüft das so (keine AOI, kein Schlüssel, kein Item in der Zeile der Route). Sollen Item-IDs auch dort heraus, ist das eine eigene Entscheidung über alle Routen.

Nicht geändert: Bei einer gleichzeitigen Erneuerung kann der Aufräumer einen gerade erneuerten Eintrag löschen; die Folge ist ein Cache-Fehlschuss.
