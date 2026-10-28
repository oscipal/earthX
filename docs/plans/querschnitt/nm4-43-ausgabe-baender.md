# NM4-43 — Ausgabe-Bänder statt Bandauswahl; Band-Math-Ergebnisse als eigene Bänder; keine Bandgrenze

**Stand:** 27.10.2026, beauftragt von Otto (Backlog-Punkt 43 in `docs/plans/nach-m4-backlog.md`). Nimmt NM4-10 (Schritt-Namen und Chips) in sich auf.
**Stufe C:** nur Entscheidungsvorlage als ADR-Entwurf `docs/adr/0020-ausgabe-baender.md`, kein Produktivcode. Die Umsetzung bekommt nach Ottos Entscheidung eigene Aufgaben.
**Ergebnis (28.10.2026):** `docs/adr/0020-ausgabe-baender.md` ist von Otto angenommen (Draft-PR #219). Die Umsetzung steht in §6 als fünf Aufgaben NM4-43a bis NM4-43e, je mit eigenem Startsatz. §1 bis §5 sind der Auftrag der Entscheidungsvorlage und bleiben unverändert.
**Modell:** Opus, Effort hoch.
**Start:** sofort möglich (nur Doku, Messung, Recherche).
**Startsatz:** „Führe Aufgabe NM4-43 aus `docs/plans/querschnitt/nm4-43-ausgabe-baender.md` aus.“

## 1. Wunsch (Otto, 27.10.2026, wörtlich)

> ich will keine obergrenze für anzahl der bänder. Außerdem will ich dass ich ein band math ergebnis, als eigenes band hinzufügen kann. (die auswahl oben soll dann zur gänze verschwinden und nur noch zur info vorhanden sein. Die auswahl soll dann am ende stehen (alle bänder und zusätzlich neu gerechnete, welche ich anclicken kann um sie zum output hinzuzufügen).

Hintergrund (NM4-07, #216): Heute bestimmt die Bandauswahl oben im Panel die Eingabe. Ohne `band_math` ist sie die Ausgabe; mit `band_math` ist die Ausgabe nur das eine Ergebnisband, zusätzlich gewählte Bänder kosten Laufzeit und zählen gegen die Grenze von 16 Assets (M4-07b F5, Startwert vom 07.10.2026, nie gemessen).

## 2. Soll (Otto)

1. **Keine Obergrenze für die Zahl der Bänder** je Auftrag.
2. **Band-Math-Ergebnisse sind eigene Bänder.** Ein `band_math`-Schritt fügt ein neues Band hinzu, statt die Bänder zu ersetzen. Mehrere Schritte ergeben mehrere neue Bänder.
3. **Oben keine Auswahl mehr.** Die Bänder des Datensatzes stehen oben nur zur Information (und als Namenshilfe: Klick fügt den Namen in einen Ausdruck ein).
4. **Ausgabe am Ende.** Am Ende des Panels stehen alle Bänder des Datensatzes und alle neu gerechneten; ein Klick nimmt ein Band in die Ausgabe auf oder heraus.
5. **Vorgabe der Ausgabe** (Otto, 27.10.2026): Standardmäßig ist nur das Band-Math-Ergebnis (bzw. sind nur die Band-Math-Ergebnisse) in der Ausgabe. Andere Bänder kommen nur hinzu, wenn der Benutzer sie anklickt.
6. **Mehrere Band-Math-Schritte** (Otto, 27.10.2026): Es können mehrere `band_math`-Schritte hintereinander laufen, jeder mit anderen Bändern (etwa NDVI aus B04/B08 und NDWI aus B03/B08). Jeder Schritt sieht die Bänder des Datensatzes und die vorher neu gerechneten.

Zusatz Otto (27.10.2026, wörtlich): „ich will auch das standardmäßig ausgewählt ist band math result (also beim rechnen vom result und nur wenn der benutzer will werden andere bänder hinzugefügt). und: es können somit auch mehrere band math schritte hintereinander mit unterschiedlichen bändern durchgeführt werden.“

## 3. Im ADR klären (je Optionen, Empfehlung, bei Rechenrelevanz Quellen und Messung)

1. **Rezeptmodell:** Heute ist die Kette linear (ein Schritt sieht nur das Ergebnis des vorigen). Neu: ein Vorrat an Bändern, in den `band_math` Bänder hinzufügt. Worauf wirken `reproject`, `mask`, `normalize` (auf alle Bänder des Vorrats, auf gewählte, auf die Ausgabe)? Spielt die Reihenfolge der Schritte noch eine Rolle?
2. **Ausgabe im Rezept:** z. B. eine Liste `outputs`. Die Eingabe ergibt sich daraus: Ausgabe-Bänder plus alle Bänder, die Ausdrücke und Maske brauchen. Nur diese werden gelesen.
3. **Namen neu gerechneter Bänder** (aus NM4-10): Vorgabe `Band_Math_1` usw., eigener Name je Schritt (etwa `ndvi`), erlaubte Zeichen, keine Doppel, keine Kollision mit Bandnamen des Datensatzes, Umbenennen bei späterer Nutzung.
4. **Schutz ohne Bandgrenze:** Die Grenze 16 entfällt (Otto). Was schützt dann Worker, Speicher und Quellen? Messung (Laufzeit, Spitzenspeicher, gelesene Bytes) für Sentinel-2 L2A mit 2, 16 und allen Bändern, bei 1 und 25 Szenen, mit und ohne `band_math`. Recherche, wie andere Plattformen das begrenzen (etwa openEO-Backends, Sentinel Hub, Google Earth Engine), mit Quellen. Empfehlung, ob die bestehenden Grenzen (25 Items, Exportgröße, Deckel gleichzeitiger Jobs, Kostenschätzung) genügen oder eine Grenze nach Datenmenge (Pixel × Bänder × Szenen) statt nach Bandzahl nötig ist.
5. **Ausgabedatei:** Neu gerechnete Bänder sind meist `float32`, Quellbänder etwa `uint16`. Eine Datei mit gemeinsamem Typ, eine Datei je Typ oder je Band? Banddeskriptionen, Einheiten (M4-19b), nodata, Größe.
6. **Vorgabe der Ausgabe ohne `band_math`:** Mit `band_math` ist sie entschieden (§2 Punkt 5). Was ist angehakt, wenn das Rezept kein `band_math` hat (nur `reproject`, `mask`, `normalize` oder gar kein Schritt): keines oder alle? Ein leerer Auftrag wird nicht gestartet.
7. **Vorschau und Kacheln:** Welches Band zeigt die Vorschau bei mehreren Ausgaben? Auswahl im Layer-Manager je Band, RGB aus drei Ausgaben? Zusammenhang mit M4-18b und NM4-04 (Mosaik mit Operator, #215).
8. **Hash, Version, Runner, alte Rezepte:** Änderung an `resolved`, `earthx.__version__`, `adr/0014`, `adr/0016`. Werden gespeicherte Rezepte und Permalinks im alten Format weiter angenommen (umgedeutet) oder mit Grund abgewiesen?
9. **Folgen für andere Aufgaben:** NM4-10 geht hierin auf. NM4-11 (Normalize), NM4-14 (Index-Knöpfe: ein Knopf fügt ein neues Band hinzu?), NM4-20 (Panel-Gliederung), NM4-05b (Ergebnis als Eingabe mit mehreren Bändern), DS-06 (Maske nach Werten), `auxiliary_assets` aus NM4-07. Der ADR sagt je Aufgabe, was sich ändert.
10. **Schnitt der Umsetzung:** Vorschlag für Aufgaben (etwa Backend/Rezept, dann Frontend) mit Reihenfolge.

## 4. Grenzen

- Stufe C: nur ADR-Entwurf, Messskripte unter `scripts/` (im PR begründet), keine Änderung an Produktivcode.
- Oberflächentexte im ADR (Knopfnamen, Tooltips) nur Englisch; wenig Text, Erklärungen im Tooltip; nicht Mögliches ausblenden statt ausgrauen.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 5. Abnahme

- `docs/adr/0020-ausgabe-baender.md` als Entwurf mit Fragen F1 … Fn an Otto, je Optionen und Empfehlung.
- Messung reproduzierbar (Skripte und Aufrufe im ADR), Recherche mit Quellen.
- Skizze des Panels (Text oder Bild) für die empfohlene Variante.
- Log-Zeile mit PR-Nummer, Status „offen“. `docs/plans/nach-m4-backlog.md` nicht ändern (pflegt der Planungs-Chat).
- Vor „fertig“ ist main geholt.

## 6. Umsetzung nach Annahme von `adr/0020` (28.10.2026)

Fünf Aufgaben, alle **Stufe A** (Plan und Entscheidung stehen im ADR; ein Draft-PR je Aufgabe, bei den größeren zwei). Jeder Abschnitt ist ohne das Gespräch zu NM4-43 verständlich; maßgeblich ist `docs/adr/0020-ausgabe-baender.md` (angenommen), dort besonders §3 (Befunde), §4 bis §11 (Entscheidungen), §13 (Schnitt), §15 und §15a (Antworten Ottos).

**Reihenfolge.** NM4-43a und NM4-43b sind unabhängig voneinander und vom Rest und starten sofort. NM4-43a muss vor NM4-43c gemergt sein. Danach NM4-43c, NM4-43d, NM4-43e nacheinander. NM4-11, NM4-14, DS-06 und NM4-20 folgen erst danach.

**Für alle fünf Aufgaben** (zusätzlich zu `CLAUDE.md`):

- Branch von `main`, ein Draft-PR je Aufgabe (bei zwei PRs je Teil einer); nie mergen, nie force-pushen. Vor „fertig“ `main` holen.
- Tests decken Fehlerfälle, fehlerhafte Eingaben und zweckfremde Nutzung ab; **Gegenprobe:** Mit dem Code vor der Änderung scheitern die neuen Tests (im PR beschrieben).
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierte URLs in Logs, URLs, Tests oder Fixtures; Fixtures nur synthetisch. BIOMASS und MAAP kommen nicht vor.
- Oberflächentexte nur Englisch, wenig Text, Erklärungen im Tooltip (UI-01 §4); was grundsätzlich nicht geht, wird ausgeblendet, was nur im Moment nicht geht, bleibt gesperrt mit Grund im Tooltip.
- Keine neue Abhängigkeit ohne Frage an Otto. `CLAUDE.md`, `.github/`, `.claude/`, `CODEOWNERS` und `docs/plans/nach-m4-backlog.md` bleiben unverändert.
- Backend: `ruff check backend`, `pytest`, `lint-imports --config .importlinter` (mit `PYTHONPATH=backend`); Frontend aus `frontend/`: `npm run lint`, `npx tsc -b --pretty false`, `npm test`. Alle Pflicht-Checks der CI grün; das Ergebnis im PR zusammenfassen.
- Jede Aufgabe trägt eine Log-Zeile in `docs/ENTSCHEIDUNGSLOG.md` mit der PR-Nummer und die Nachträge in den ADRs, die sie nennt. Der PR nennt, was Otto im Browser oder in PowerShell 5.1 selbst prüfen kann.
- Unter etwa 400 geänderten Zeilen ohne generierte Dateien je PR; wird es mehr, teilt die Aufgabe den PR so, wie sie es vorsieht.

### 6.1 NM4-43a — Schätzung nach dem feinsten Asset

**Stufe A**, nur Backend. **Modell:** Sonnet, Effort mittel. **Start:** sofort; unabhängig von NM4-43b; vor NM4-43c zu mergen (beide ändern `backend/earthx/processing/plan.py`).
**Startsatz:** „Führe Aufgabe NM4-43a aus `docs/plans/querschnitt/nm4-43-ausgabe-baender.md` §6.1 aus.“

**Ausgangslage (`adr/0020` §3.3).** Der Kern liest alle Assets eines Auftrags auf das feinste Raster (`processing/source.py: common_grid`). Die Schätzung vor dem Lauf bemisst das Ausgaberaster dagegen nach dem **ersten** Asset des Auftrags: `plan._input_meta(sized=True)` nimmt `resolved[0]` und `_input_grid` dessen `gsd`. Steht ein Asset mit grober Pixelgröße vorn (Sentinel-2: `coastal` mit 60 m vor `red` mit 10 m), liegen Ausgabepixel, Ausgabebytes, die Prüfung auf `MAX_JOB_BYTES` (5 GB, `JobTooLarge`, `413`) und `units` um bis zum Faktor 36 zu niedrig. `plan.disk_needed` bemisst den `float64`-Durchgang je Asset mit dessen eigenem `gsd`, obwohl der Durchgang auf dem feinsten Raster über alle Bänder läuft. Das Panel ordnet die Assets nach dem Item (`red` zuerst), über die API ist die Reihenfolge frei.

**Umfang.**

1. `plan._input_meta` und `_input_grid`: Das Raster der Schätzung ist die AOI-Box im CRS des Assets mit dem **kleinsten `gsd`** (bei Gleichstand das erste), mit dessen Pixelgröße. Fehlt bei einem Asset das `gsd`, bleibt die Abweisung wie heute (`UnsupportedRecipe`, „no gsd“).
2. `plan.disk_needed`: Der Durchgang in `float64` wird auf dem feinsten Raster über **alle** Bänder aller Assets bemessen (Zeilen × Spalten des feinsten Rasters, aufgefüllt auf ganze Blöcke, mal Zahl der Bänder mal 8), nicht je Asset mit dessen Raster.
3. Unverändert bleibt, was ein Asset auf seinem eigenen Raster liest (`input_pixels`, `input_bytes`, Sekunden aus den Eingabebytes): Das ist das Leseaufkommen und stimmte schon.
4. Die Reihenfolge der Assets im Auftrag ändert keinen Wert der Schätzung (`output_pixels`, `output_bytes`, `units`, `disk_needed`).
5. Kein Eingriff in `core.py`, `source.py` und die Operatoren. `earthx.__version__` bleibt (kein Byte des Ergebnisses ändert sich); ändern sich die Zahlen vorhandener Tests, steht der Grund im PR.
6. Nachtrag `adr/0014` §15u (kurz: was falsch war, was jetzt gilt, Messung aus `adr/0020` §3.3).

**Abnahme.**

- Tests (`backend/tests/earthx/processing/test_plan.py`, bei geographischem CRS `test_estimate_geographic.py`): ein Auftrag mit einem 60-m- und einem 10-m-Asset (synthetisch) gibt für `[grob, fein]` und `[fein, grob]` dieselbe Schätzung; `output_pixels` liegt bei den Pixeln des feinsten Rasters (höchstens ein Pixel je Seite Unterschied zum Rand, den der Kern nach außen rundet); `JobTooLarge` greift für eine Fläche, die nur auf dem feinsten Raster über 5 GB liegt, in beiden Reihenfolgen; `disk_needed` wächst mit dem feinsten Raster und nicht mit der Summe der Raster; ein Auftrag mit einem Pixelmaß bleibt bitgleich bei allen Zahlen (bestehende Tests unverändert grün).
- Vergleich mit dem Kern: Ein Test lässt `processing.core.run` auf einer kleinen synthetischen Quelle mit zwei Pixelgrößen laufen (die vorhandenen Fixtures für verschachtelte Raster in `test_source.py`/`test_band_math_run.py`, falls geeignet) und prüft, dass die geschätzten Ausgabepixel zum Ergebnis passen.
- Gegenprobe, die üblichen Prüfungen, Log-Zeile, Nachtrag `adr/0014` §15u, `main` geholt.

### 6.2 NM4-43b — `reproject` Version 4, je Band ein Warp

**Stufe A**, nur Backend. **Modell:** Sonnet, Effort hoch (Numerik, Bitgleichheit). **Start:** sofort; unabhängig von NM4-43a; nicht gleichzeitig mit NM4-43c (beide ändern `operators/registry.py`, eine Zeile).
**Startsatz:** „Führe Aufgabe NM4-43b aus `docs/plans/querschnitt/nm4-43-ausgabe-baender.md` §6.2 aus.“

**Ausgangslage (`adr/0020` §3.4).** `reproject` warpt je Block alle Bänder der Zwischendatei in einem `WarpedVRT` (`operators/reproject.py: _run`). GDAL teilt den Warp nach `warp_mem_limit` (64 MB) auf, und diese Teilung hängt an der Zahl der Bänder. Gemessen (`scripts/nm4-43-bands/warp_bands.py`, synthetisch, 2048², `float64`, `bilinear` nach EPSG:3035): Band 1 ist bei 1, 2 und 3 Bändern bitgleich; ab 4 Bändern weichen 4 136 158 von 4 303 544 Pixeln ab (größte Abweichung 0,0077 bei Werten bis 0,5), zwölf Randpixel wechseln zwischen gültig und NaN; 4, 18 und 34 Bänder ergeben dieselben Werte. Folge: Derselbe Auftrag gibt für dasselbe Band andere Werte, je nachdem, wie viele andere Bänder in der Datei stehen. Mit dem Streichen ungenutzter Bänder (NM4-43c) hinge der Wert an dem, was die Ausgabe sonst enthält.

**Umfang.**

1. **`reproject` `op_version` 4:** Dieselben Parameter wie Version 3 (`crs`, `resolution`, `resampling`, `align`). Jedes Band bekommt einen **eigenen Warp** mit dem festen Plan der Version 3 (Blöcke 1024 px, `tolerance` 0,125, `warp_mem_limit` 64 MB). Wie ein Band einzeln gelesen wird (etwa eine Einband-Sicht auf die Zwischendatei), ist Sache der Umsetzung; sie wählt den Weg mit der Messung und beschreibt ihn im PR. Der Wert eines Bandes hängt dann nur noch an ihm selbst.
2. **Version 3 bleibt angenommen und rechnet wie bisher**, wird aber nicht mehr gelistet (wie Version 2 heute: `REPROJECT_V2` in `operators/reproject.py`; `api/processing_docs.py` listet nur die höchste Version). Version 4 ist die gelistete.
3. **Messung im PR** (Skript im PR, `scripts/nm4-43-bands/warp_bands.py` bekommt dazu einen Schalter `--op-version 3|4`, damit die Zahlen aus `adr/0020` §3.4 reproduzierbar bleiben): Laufzeit und Spitzenspeicher von Version 3 und 4 bei 1, 4 und 17 Bändern, 4096², `bilinear`. Der Kostenfaktor in `_METHODS` wird danach angepasst, falls Version 4 spürbar mehr braucht. Ist der Mehraufwand deutlich, fragt der PR Otto, bevor er „fertig“ meldet.
4. `earthx.__version__` 0.4.3 → 0.4.4 (ein Ergebnis kann sich ändern, `adr/0016` §9). Nachtrag `adr/0014` §15v (zu §3.4, §6.3); der Methodentext von `reproject` bleibt, der Cache-Schlüssel ändert sich über `op_version`.

**Abnahme.**

- Tests (`test_reproject.py`, `test_reproject_tolerance.py`, `test_memory_reproject.py`): Band 1 hat bei 1, 2, 3, 4, 18 und 34 Bändern **dieselben Bytes** (Version 4); Version 4 gibt für 1 bis 3 Bänder dieselben Bytes wie Version 3 (damit ändert sich für bestehende Einband- und Dreibandaufträge nichts); Version 3 gibt für 4 Bänder weiter die bisherigen Bytes (angenommene Version unverändert); die Maske (NaN) ist je Band dieselbe wie im Einbandlauf; die Toleranz T2 ↔ T2L aus `adr/0014` §6.3 hält; der Speichertest (Grenze 500 MB, Wachstum höchstens 120 MB) hält auch mit 17 Bändern.
- Gegenprobe, die üblichen Prüfungen, Log-Zeile, Nachtrag `adr/0014` §15v, `main` geholt.

### 6.3 NM4-43c — Rezept und Kern: Bandvorrat, `output.bands`, Schutz ohne Bandgrenze

**Stufe A**, nur Backend, **zwei PRs** (über 400 Zeilen). **Modell:** Opus, Effort hoch, für PR 1 (Rezept, Hash, Kern, Bitgleichheit); Sonnet, Effort hoch, für PR 2. **Start:** nach dem Merge von NM4-43a; NM4-43b sollte gemergt sein (sonst ändert das Streichen die Werte nach `reproject`, `adr/0020` §4); nicht gleichzeitig mit anderen Aufgaben an `api/intake.py`, `processing/recipe.py` und `processing/plan.py`.
**Startsatz:** „Führe Aufgabe NM4-43c aus `docs/plans/querschnitt/nm4-43-ausgabe-baender.md` §6.3 aus.“

**Ausgangslage.** Heute bestimmt die Bandauswahl im Panel die Eingabe; `band_math` ersetzt alle Bänder durch eines (`operators/band_math.py`, `OUTPUT_BAND`); `mask` entfernt die Schicht; `normalize` wirkt auf alle Bänder; ein Auftrag nimmt höchstens 16 Assets (`api/intake.py: MAX_ORDER_ASSETS`, M4-07b F5). Beschlossen ist das Modell des Bandvorrats (`adr/0020` §4 bis §8, §11): Der Vorrat beginnt mit den Bändern des Datensatzes, `band_math` fügt ein benanntes Band hinzu, `output.bands` wählt am Ende aus, der Planer streicht, was nicht gebraucht wird, und die Grenze von 16 Assets entfällt.

**PR 1 — Rezept und Kern.**

1. **`processing/recipe.py`:** `RECIPE_VERSION = 2`. `RasterOutput.bands`: Liste von Namen (Form wie `Name`), mindestens einer, jeder einmal, ohne Rücksicht auf Groß-/Kleinschreibung eindeutig; jeder muss am Ende der Kette im Vorrat stehen. Im **Auftrag** (`RecipeRequest`) ist `inputs[].assets` für die Ausgabe `raster` nicht mehr nötig (Version 2 nennt es nicht); die Ausgabe `crop` bleibt, wie sie ist. Im **Rezept** (`Recipe`) stehen die abgeleiteten `assets` und `resolved` weiter (Form unverändert, `adr/0020` §11).
2. **Operatoren:** `band_math` `op_version` 2 mit den Parametern `expression` und `name` (keine Vorgabe im Rezept, B10); fügt das Band hinzu, ersetzt nichts. Namensregeln aus `adr/0020` §6: `^[A-Za-z][A-Za-z0-9_]{0,31}$`, kein Python-Schlüsselwort, kein Funktionsname aus R5, eindeutig ohne Rücksicht auf Groß-/Kleinschreibung über alle Ergebnisse der Kette und gegen alle Bänder des Datensatzes (auch die nicht gelesenen); der Text der Abweisung nennt den Namen und den Grund. `mask` `op_version` 2: Die Schicht bleibt im Vorrat und wird, wie alle Bänder, an den ausgeblendeten Klassen maskiert. `normalize` `op_version` 2 mit dem Feld `bands` (Pflicht, die Bänder, die der Schritt umrechnet; Auslegung `adr/0020` §15a, die Methoden kommen mit NM4-11). Die Versionen 1 bleiben registriert und angenommen (Umdeutung, bis dahin die Kachel), **gelistet wird weiter Version 1**: ein Feld am Operator steuert die Auflistung (`api/processing_docs.py`, heute „nur die höchste Version“), damit das heutige Panel bis NM4-43e funktioniert.
3. **Planer (`processing/plan.py`):** Streichen von hinten (`adr/0020` §4): Ein Band bleibt, solange es in `output.bands` steht oder ein späterer Schritt es braucht (Ausdruck, Schicht von `mask`, `normalize.bands`); sonst fällt es nach seiner letzten Nutzung weg; was nie gebraucht wird, wird nicht gelesen. Test: je Operator „mit Streichen“ gegen „ohne Streichen“ bitgleich (mit `reproject` ab Version 4 aus NM4-43b).
4. **`api/intake.py`:** leitet aus `output.bands` und den Schritten die Assets ab (Zuordnung Bandname → Asset über `describe_bands`/`expected_band_names`), schreibt sie ins Rezept, weist einen Namen ohne Asset mit `422` und dem Namen ab, prüft die Namensregeln gegen die Bänder der Collection. Die Prozessbeschreibung (`processing_docs.py`) bekommt das Schema von `output.bands`.
5. **`processing/core.py`:** gibt nur `output.bands` aus (in der Reihenfolge der Liste); **Banddeskription** (der Name) und **Einheit** je Band in `result.tif` (`adr/0020` §8) und in den STAC-Eigenschaften; Datentyp und nodata nach den heutigen Regeln.
6. **Umdeutung von Version 1** (`adr/0020` §11): ein Modul in `processing`, das ein Rezept oder einen Auftrag der Version 1 als Version 2 schreibt (Namen der `band_math`-Schritte, `normalize.bands`, `output.bands`). Benutzt von `api` (Aufträge, Permalink anlegen; **bis 30 Tage nach dem Deploy von NM4-43e**, Konstante mit Datum, die NM4-43e setzt; danach `422` „recipe_version 1 is no longer accepted; send version 2“), vom Worker (gespeicherte Rezepte der Warteschlange und der Wiederherstellung) und vom **Runner dauerhaft** (`runner/recipe_file.py`; heruntergeladene `recipe.json` bleiben lesbar; der Runner sagt, dass das Rezept umgedeutet wurde). **Offen (F14, `adr/0020` §15a):** Wie das bei Version-1-Rezepten mit `reproject` geschieht; **bis Otto antwortet, bleibt dieser Teil unbearbeitet** (kein Raten, Frage an Otto im PR mit den Optionen aus §15a), alles andere läuft.
7. `earthx.__version__` 0.5.0; Nachtrag `adr/0014` §15w, Nachtrag `adr/0016` §12d; Methodentext und `recipe.json` tragen die neuen Felder; `docs/`-Verweise auf „16 Assets“ bleiben bis PR 2.

**PR 2 — Schutz ohne Bandgrenze** (`adr/0020` §7).

1. `MAX_ORDER_ASSETS` und die `maxItems` der Assets in der Prozessbeschreibung entfallen (`api/intake.py`, `api/processing_docs.py`). Das heutige Panel fällt bei fehlendem Wert auf 16 zurück (`frontend/src/processingOrder.ts`) und bleibt bis NM4-43e funktionsfähig; die Grenzen der Kachel (`api/tiler.py`: 16 Assets, `api/mosaic_tiles.py`: 4) bleiben.
2. **Speicherschätzung je Lauf** gegen eine Grenze je Kindprozess, Startwert **1,5 GB**, als Konstante mit Verweis auf das ADR; darüber `413` mit Grund und Zahl, z. B. „This job would need about 2.4 GB of memory, more than the 1.5 GB a job may use. Put fewer bands in the output.“ Die Formel nimmt den Befund aus `adr/0020` §3.2 (rund 300 MB + 21 MB je Band im breitesten Durchgang bei 9,5 Mio. Pixeln) und **misst neu**: mit dem echten Anhängen von `band_math` (nicht dem naiven Anhängen des Messskripts), bis zur 5-GB-Grenze (rund 72 Mio. Pixel bei 17 Bändern) und für ein Mosaik von 25 Szenen in einem Lauf, was `adr/0020` nicht gemessen hat. `scripts/nm4-43-bands/measure.py` ist der Ausgangspunkt.
3. **Zeitschätzung** zählt die Ausgabebänder (`adr/0020` §3.2 Befund 9: bei 30 km und 17 Bändern 21 s geschätzt, 115 s gemessen), mit einem gemessenen Wert je Band; die Laufzeitgrenze (2 × Schätzung, mindestens 600 s) hält damit auch für viele Bänder. `units` zählt Ausgabepixel mal Bänder mal Faktor.
4. Die Speichertests (`test_memory_*`) bekommen einen Lauf mit 17 Bändern; die Messung bleibt unter der Schätzung.

**Abnahme.**

- Tests: Version 2 rechnet NDVI und NDWI als zwei Ergebnisse neben den Eingaben, nur `output.bands` im Ergebnis (Reihenfolge, Banddeskription, Einheit, nodata); ein Name doppelt, in anderer Schreibweise doppelt, gleich einem Band des Datensatzes, ein Schlüsselwort, zu lang, unbekannt in `output.bands` → `422` mit dem Namen; leere `output.bands`; Streichen bitgleich zum Lauf ohne Streichen; ein nicht gelesenes Asset wird nicht geöffnet (Test über die Zahl der Öffnungen); Auftrag von Version 1 → umgedeutet, Werte **bitgleich** zum Lauf von vorher für Ketten ohne `reproject` (Fixtures der Version 1 aus den vorhandenen Tests); `api` nimmt Version 1 vor und weist sie nach der Frist ab (Uhr festgesetzt); der Runner liest ein Rezept der Version 1; der Hash ändert sich einmal, ein zweiter gleicher Auftrag ist ein Cache-Treffer.
- PR 2: 17 Bänder ohne Schritt werden angenommen (vorher `422`); eine Ausgabe über der Speichergrenze wird mit `413` und dem Grund abgewiesen; die Zeitschätzung wächst mit den Ausgabebändern.
- Gegenprobe, die üblichen Prüfungen, Log-Zeilen, Nachträge in `adr/0014` (§15w) und `adr/0016` (§12d), `main` geholt.

### 6.4 NM4-43d — Kachel: ein Band, Schritte der Version 2

**Stufe A**, nur Backend. **Modell:** Sonnet, Effort hoch. **Start:** nach dem Merge von NM4-43c (PR 1); nicht gleichzeitig mit anderen Aufgaben an `api/tiler.py` und `api/mosaic_tiles.py`.
**Startsatz:** „Führe Aufgabe NM4-43d aus `docs/plans/querschnitt/nm4-43-ausgabe-baender.md` §6.4 aus.“

**Ausgangslage.** Die Kachel (`GET /collections/{dataset}/items/{item}/tiles/…?asset=…&op=…&op_version=…&params=…`, `api/tiler.py`, `processing/tile.py`) und die Mosaik-Kachel mit Schritten (NM4-04, `api/mosaic_tiles.py`) rechnen dieselben Kerne wie der Job (T1 gleich T2, bitgleich auf der nativen Ebene). Mit dem Bandvorrat (NM4-43c) liefert eine Kette mehr als ein Band; ein Bild zeigt aber eines (`adr/0020` §10, Empfehlung P1).

**Umfang.**

1. Die Kachel und die Mosaik-Kachel rechnen `band_math` Version 2 (mit `name`), `mask` Version 2 und `normalize` Version 2; Version 1 bleibt für die Dauer der Übergangsfrist angenommen (die Kerne gibt es noch).
2. **Neuer Parameter `band=<Name>`:** Welches Band des Vorrats nach der Kette die Kachel zeigt. Vorgabe ohne Angabe: das letzte von einem `band_math`-Schritt hinzugefügte Band, sonst das erste. Ein unbekannter Name wird mit `4xx` und dem Namen **vor dem Abruf einer Datei** abgewiesen.
3. **Streichen wie der Planer** (`adr/0020` §4): Die Kachel liest nur die Assets, die das gezeigte Band braucht. Die Grenzen der Kachel (16 Assets, bei der Mosaik-Kachel 4) werden **nach dem Streichen** geprüft, damit NDVI mit Maske (3 Assets) auch bei einem Auftrag mit 17 Bändern passt. Die Längengrenze der Mosaik-Kachel (7 168 Byte) bleibt.
4. **Statistik je Band:** Die Route `…/statistics` mit Schritten liefert die Statistik des gezeigten Bandes (für die Farbskala „Auto stretch“); das TileJSON trägt `band` und `unit` dieses Bandes.
5. **Ergebnis-Kachel** (`api/result_tiles.py`, `result.tif` mit mehreren Bändern): Prüfen, dass die Kachel ein Band über `bidx` wählen lässt und die Farbskala je Band aus `properties.bands[].statistics` (M4-32) kommt; fehlt etwas, kommt es hier dazu. Das Frontend (NM4-43e) wählt das Band über den Namen.
6. Nachtrag `adr/0014` (kurz, zu §6.1, §15m, §15t) und `adr/0006`, falls dessen Kachel-Pfad beschrieben ist.

**Abnahme.**

- Tests: bitgleich Kachel ↔ Job auf der nativen Ebene für das gezeigte Band (Kette `mask → band_math` mit Namen; zwei `band_math`-Schritte, `band=` wählt je eines); ohne `band=` das letzte Ergebnis; unbekanntes `band=` → `4xx` vor dem Abruf (kein Datei-Zugriff, über den Zähler der Öffnungen); die Grenzen greifen nach dem Streichen (17 Assets im Auftrag, 3 gelesen → angenommen); Mosaik-Kachel mit `band=`; Statistik und TileJSON eines Bandes; Ergebnis-Kachel mit `bidx` auf einer synthetischen `result.tif` mit drei Bändern; keine Kennung und kein Hash in einer URL.
- Gegenprobe, die üblichen Prüfungen, Log-Zeile, Nachträge, `main` geholt.

### 6.5 NM4-43e — Frontend: Ausgabe am Ende, Namen, Vorschau je Band

**Stufe A**, nur Frontend (eine einzige Zeile im Backend: die Auflistung der Operatoren auf Version 2, im PR begründet), **zwei PRs** (über 400 Zeilen): (1) Auftrag und Panel, (2) Vorschau und Ergebnis-Layer. **Modell:** Sonnet, Effort hoch. **Start:** nach dem Merge von NM4-43c und NM4-43d. Höchstens zwei Frontend-Sessions gleichzeitig; nicht gleichzeitig mit NM4-20, NM4-45 oder NM4-14 (alle ändern den Bandbereich des Panels). NM4-45 (Band in der Ansicht) sollte davor fertig sein, dann übernimmt NM4-43e dessen Dropdown „Band“.
**Startsatz:** „Führe Aufgabe NM4-43e aus `docs/plans/querschnitt/nm4-43-ausgabe-baender.md` §6.5 aus.“

**Ausgangslage.** Das Panel (`frontend/src/components/ProcessingPanel.tsx`, `processingOrder.ts`, `processingStore.ts`, `processingPreview.ts`) hat oben „Bands“ als Auswahl (Chips, „Select all bands“, „Clear“, Grenze 16), dann „Processing steps“, „Output“ (Datentyp) und „Preview“. Nach `adr/0020` §14 wird oben nur noch Information, und die Ausgabe wird am Ende des Panels gewählt.

**PR 1 — Auftrag und Panel.**

1. **Bands (oben):** nur Information und Namenshilfe; Klick fügt den Namen in das Ausdrucksfeld mit Fokus ein, sonst nichts. „Select all bands“, „Clear“, die Grenze von 16 und ihre Texte entfallen; Hilfs-Assets erscheinen nicht.
2. **Schritte:** Titel „<n>. <Name>“; `band_math` hat das Feld „Name“ (Vorgabe `Band_Math_<n>`); die Namensregeln aus `adr/0020` §6 prüft das Panel selbst, ein Konflikt zeigt den Rahmen in der Fehlerfarbe und den Grund im Tooltip; Umbenennen zieht alle Verweise (Ausdrücke späterer Schritte, `normalize.bands`, `output.bands`) token-genau mit. Chips an einem Schritt: nur die Ergebnisse früherer Schritte.
3. **Output (am Ende):** „New“ (Ergebnisse) und „Data“ (Bänder des Datensatzes) als Chips zum An- und Abhaken; „All“ und „None“ nur, wenn sie etwas ändern; Kopfzeile mit Zahl der Bänder und Datentyp. **Vorgabe nach `adr/0020` §9 (F7, Option 2):** ohne `band_math` im Rezept alle wählbaren Bänder angehakt (ohne Hilfs-Assets und ohne Maskenschicht), mit `band_math` nur die Ergebnisse; die Vorgabe wechselt mit dem ersten hinzugefügten und dem letzten entfernten `band_math`-Schritt, **solange der Benutzer nicht selbst geklickt hat** (Zustand „automatisch“ oder „vom Benutzer gesetzt“, nicht im Rezept); ein neues Ergebnis wird immer angehakt, ein entferntes verschwindet. Leere Ausgabe: „Start“ gesperrt, Tooltip „Pick at least one band for the output.“; Speichergrenze überschritten: „Start“ gesperrt, Grund im Tooltip aus der Schätzung des Servers (kein Satz im Panel).
4. **Auftrag:** Das Panel schickt Version 2 (`output.bands`, `band_math` mit `name`, `normalize` mit `bands`, keine Asset-Liste); `processingOrder.ts` leitet nichts mehr aus einer Bandauswahl ab. Die Auflistung der Operatoren im Backend wird auf Version 2 umgeschaltet (eine Zeile) und beginnt damit die **Übergangsfrist** von 30 Tagen; die Konstante in `api` mit dem Datum, ab dem Aufträge der Version 1 abgewiesen werden, wird gesetzt (`adr/0020` §11: 30 Tage nach dem Deploy; Otto nennt das Deploy-Datum im PR), Log-Zeile mit dem Datum.
5. **Umdeutung von Version 1** in `recipeFile.ts` (hochgeladene `recipe.json`), beim Öffnen eines Permalinks und bei der Ablage im Browser (`jobShelf.ts`: Kopien des Auftrags), mit dem Hinweis „Converted from recipe version 1.“ im Tooltip der Meldung; dieselbe Regel wie in Python (`adr/0020` §11), Test mit denselben Fällen.
6. Panel-Gliederung nach `adr/0020` §14; die weitere Gestaltung (Abstände, Einklappen) bleibt NM4-20.

**PR 2 — Vorschau und Ergebnis-Layer.**

1. **Preview:** Bei mehr als einem Band in der Ausgabe erscheint das Dropdown „Show“ (Vorgabe: letztes Ergebnis von `band_math`, sonst erstes Band); die Kachel bekommt `band=<Name>` und nur die Assets, die das Band braucht. Der Hinweis „The map shows the first N steps“ bleibt.
2. **Ergebnis-Layer** im Layer-Manager: dasselbe Dropdown „Band“ in der Zeile, nur bei mehr als einem Band; wählt den Band über den Namen der Banddeskription (`bidx` der Ergebnis-Kachel), Farbskala je Band aus `properties.bands[].statistics`. Mit NM4-45 teilt es sich den Baustein.
3. Keine Kennung in einer URL; Texte Englisch.

**Abnahme.**

- `vitest`: Vorgabe der Ausgabe ohne und mit `band_math` (Hilfs-Assets und Maskenschicht nicht angehakt), Wechsel beim Hinzufügen und Entfernen eines Schritts nur im Zustand „automatisch“, nicht nach einem Klick; neues Ergebnis immer angehakt, entferntes verschwindet; zwei `band_math`-Schritte, der zweite sieht das Ergebnis des ersten als Chip; Umbenennen zieht Verweise mit; Namenskonflikte (doppelt, andere Schreibweise, gleich einem Band des Datensatzes, Schlüsselwort) mit Grund; leere Ausgabe sperrt „Start“; mehr als 16 Bänder werden nicht mehr abgewiesen; Version 1 (Datei, Permalink, Ablage) wird mit Hinweis umgedeutet, mit denselben Fällen wie die Python-Tests; der gebaute Auftrag hat `output.bands` und keine Asset-Liste; Preview mit `band=`, Dropdown nur bei mehr als einem Band; Ergebnis-Layer wählt ein Band.
- Gegenprobe: Die neuen Tests scheitern gegen den Code vor der Änderung.
- Prüfung im echten Browser (Chromium/Playwright der Sitzung) mit nachgestellten Antworten, nicht nur jsdom: hell und dunkel, schmales Fenster; im PR beschrieben.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR; die vier Pflicht-Checks der CI grün; Log-Zeile(n) mit PR-Nummer; `main` geholt.
