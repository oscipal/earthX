# M5-61 — Tests aufräumen: Plan-Schritt

**Status (19.11.2026):** Plan angenommen (Otto, 19.11.2026: F1–F8 je Option 1, §6a), **Stufe B**. Umsetzung in PR 1 (§3.1) und PR 2 (§3.2).
**Aufgabe:** M5-61 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2, Auftrag von Otto vom 19.11.2026.
**Grundlagen:** `adr/0002` (Testaufteilung, T-C nie überspringen), NM4-23 (eine Datenbank je xdist-Worker), #336 (Logger-Fix im Test), #338 (CI in vier Teilen), Befunde aus #299, #341, #347, #365 (M5-36), #381.

Belegstufen: **M** in dieser Sitzung gemessen, **P** am Quelltext gelesen (Stand `main` 5b45034), **A** eigene Ableitung. Gegen Quellen lief nichts.

---

## 1. Ziel und Grenzen

- Volle Backend-Suite in der Session **deutlich unter 20 min**.
- **Keine Abbrüche bei parallelen Läufen** (zwei Checkouts oder zwei Läufe auf demselben Postgres).
- **Keine Abdeckung verlieren:** Zusammenlegen nur, wo zwei Tests denselben Aufruf mit denselben Eingaben prüfen. Gelöscht wird nur, was Otto in §5 freigibt.
- Nicht Teil: `.github/` und die Aufteilung in `scripts/ci-backend-shard.sh` (CI-Struktur, nur mit Ottos Erlaubnis); Zahl der xdist-Worker (`-n auto` gilt auch in der CI); Frontend-Tests (`vitest`).

---

## 2. Messung (M)

Ein voller Lauf `pytest --durations=100 --junitxml=…` aus der Repo-Wurzel, 19.11.2026, Cloud-Session mit 4 Kernen und 15 GB RAM, `-n auto --dist worksteal` (4 Worker), nichts anderes lief gleichzeitig.

| | |
|---|---|
| Ergebnis | 14 149 Tests: 14 124 bestanden, 25 übersprungen (alle `pwsh` fehlt), 0 Fehler, 0 Teardown-Fehler |
| Wandzeit | **20:17 min** (pytest selbst 20:10) |
| CPU | 53:02 min user, 3:53 min sys (≈ 70 % von 4 Kernen) |
| Summe der Testzeiten (Setup + Aufruf + Teardown) | **4 678 s = 78 min** ≈ 4 × Wandzeit |
| `/tmp/pytest-of-root` nach dem Lauf | **9,6 GB** (Platz frei: 29 GB vorher, 19 GB nachher) |
| Postgres | kein Neustart; am Ende 4 Worker-DBs mit offenen Verbindungen per `WITH (FORCE)` gelöscht |

Die vier Worker waren die ganze Zeit belegt (Summe ≈ 4 × Wandzeit). Schneller wird die Suite also nur, wenn die **Summe der Testzeiten** sinkt; Umsortieren allein bringt nichts.

### 2.1 Je Modul

| Modul | Tests | Summe | Anteil |
|---|---:|---:|---:|
| `integration` | 1 037 | 1 935 s | 41 % |
| `earthx/processing` | 2 191 | 1 027 s | 22 % |
| `earthx/api` | 3 453 | 997 s | 21 % |
| `earthx/jobs` | 614 | 376 s | 8 % |
| `catalog` | 2 357 | 73 s | 2 % |
| `earthx/runner` | 125 | 69 s | 1 % |
| `tests/*.py` (Wurzel) | 984 | 52 s | 1 % |
| übrige 9 Module | 3 388 | 149 s | 3 % |

### 2.2 Die teuersten Dateien

| Datei | Tests | Summe | je Test |
|---|---:|---:|---:|
| `integration/test_api_listed.py` | 109 | 461 s | 4,2 s |
| `integration/test_api_aoi_cloud_filter.py` | 91 | 432 s | 4,8 s |
| `processing/test_memory_mask_normalize.py` | 11 | 285 s | 26 s |
| `integration/test_api_collection_search.py` | 55 | 232 s | 4,2 s |
| `integration/test_api_federating.py` | 47 | 215 s | 4,6 s |
| `jobs/test_overview_builder.py` | 76 | 151 s | 2,0 s |
| `integration/test_api_pass_search.py` | 31 | 151 s | 4,9 s |
| `processing/test_memory_reproject.py` | 4 | 124 s | 31 s |
| `api/test_processing_route.py` | 396 | 123 s | 0,3 s |
| `processing/test_reproject.py` | 109 | 99 s | 0,9 s |
| `jobs/test_worker.py` | 56 | 93 s | 1,7 s |

Verteilung: 940 Tests ≥ 1 s brauchen zusammen 3 599 s (77 % der Summe); 27 Tests ≥ 10 s brauchen 739 s.

### 2.3 Befund L1: Katalog je Test neu geladen (M, P)

Sieben Integrationsdateien laden den ganzen Katalog **in einer Fixture je Test** mit `earthx.catalog.load.main()` (`test_api_listed`, `test_api_aoi_cloud_filter`, `test_api_collection_search`, `test_api_federating`, `test_api_pass_search`, `test_api_search_filters`, `test_coverage_local_sql`; dazu kleinere in `test_access_log`, `test_api_one_registry`, `test_try_job_search`). Zusammen **364 Tests, 1 617 s**. Das Setup allein kostet unter Last 4,3–5,1 s je Test (`--durations`: 37 der 100 langsamsten Phasen sind dieses Setup). Auch reine 400-Prüfungen zahlen es: `test_is_400_before_any_source_is_asked_and_names_no_value` hat 28 Fälle, zusammen 128 s.

`catalog-load` einzeln in einer eigenen Datenbank, ohne Last, zweiter Lauf (nichts zu tun): 2,6–3,0 s. Davon `write_hand_entries` 1,6 s (Warten auf Postgres), `write_search_index` 1,06 s, davon 1,03 s in `places.place_terms` (geodätische Flächen mit `pyproj`, reine Rechnung, bei gleichem Eintrag immer gleich), `write_regions` 0,23 s.

### 2.4 Befund L2: Speicher-Tests (M, P)

`test_memory_*.py`: 22 Tests, **≈ 600 s**. Jeder misst den Spitzenwert eines eigenen Kindprozesses (`memory_run.py`) und baut dafür COGs bis 8192². Doppelt gemessen wird mindestens ein Aufruf: `test_the_estimate_of_the_memory_of_a_step_that_measures_is_not_below_the_measured_peak[4]` (42 s) startet dasselbe Kind (`normalize-v4-percentile`, dieselbe Szene 4096² mit vier Bändern, `GDAL_CACHEMAX` 64) wie der große Fall von `test_normalize_version_4_over_four_bands…[normalize-v4-percentile]`. Szenen mit vier Bändern zu 2048² und 4096² bauen `test_memory_reproject.py` und `test_memory_mask_normalize.py` je für sich (`build_scene(…, bands=4)`).

### 2.5 Befund T: pytest-Temp-Verzeichnisse (M)

Ein voller Lauf schreibt **9,6 GB** nach `/tmp/pytest-of-root/pytest-N`; pytest behält die **letzten drei** Läufe (Vorgabe `tmp_path_retention_count = 3`, `policy = all`). Die größten: `test_band_1_has_the_same_bytes…[34]` 1,1 GB, `[18]` 0,6 GB, Szenen der Speicher-Tests je 0,2–0,5 GB. In dieser Session waren vorher 29 GB frei: **Der dritte volle Lauf einer Session füllt die Platte** (A). Teilläufe zählen mit, weil jeder Lauf ein eigenes `pytest-N` anlegt.

Das passt zu drei Befunden, die bisher getrennt standen (A, nicht nachgestellt): Postgres beendet sich bei vollem Plattenplatz beim Schreiben des WAL und startet neu (**„startet mitten im Lauf neu“**), und Teardowns, die schreiben oder Postgres brauchen, scheitern (**Teardown-Fehler nur im gemeinsamen Lauf**: #347 drei in `test_worker.py`, #341 zwei in `test_memory_*`). Im Messlauf trat keiner der drei auf.

### 2.6 Befund D: Namen der Test-Datenbanken (P, M)

- Worker-DB: `<PGDATABASE>_<worker>`, also `earthx_gw0` … `earthx_gw3` (`tests/worker_database.py`). `create_worker_database` löscht vorher `DROP DATABASE … WITH (FORCE)`. **Ein zweiter Lauf auf demselben Postgres beendet die Verbindungen des ersten** und baut dessen Datenbank neu, aus den Migrationen seines eigenen Checkouts (A: das sind die Abbrüche und Migrationskonflikte zwischen Checkouts).
- Ebenso `earthx_gw1_probe` und `earthx_gw1_empty` aus `integration/test_worker_database.py`.
- Nur die Jobs-Datenbank ist eindeutig (`earthx_jobs_<zufall>`, `jobs/conftest.py`).
- Ein serieller Lauf (`-n 0`) arbeitet direkt in der konfigurierten Datenbank; `catalog-load` und `_search_index_of_the_app` committen dort. Liegt in derselben Datenbank der Stand eines anderen Checkouts (andere Migration unter derselben Nummer), bricht `apply_migrations` mit „geändert nach dem Anwenden“ ab.
- Jeder Worker migriert pgstac und earthx einzeln (`test_worker_database` misst für zwei solche Anlagen 10,6 s).

### 2.7 Befund G: verstellte Logger (M, P)

`earthx/jobs/main.py` ruft `configure_logging()` **beim Import** auf: Root-Logger auf INFO, ein eigener `StreamHandler(sys.stdout)` ersetzt alle Root-Handler, `httpx`/`botocore`/`urllib3` auf WARNING, `uvicorn.access` ohne Propagation. Fünf Testmodule importieren es schon beim Sammeln (`test_logging.py`, `test_gdal_log_addresses.py`, `jobs/test_startup.py`, `jobs/test_uvicorn.py`, `jobs/test_child.py`). Damit gilt dieser Zustand im ganzen Worker für alle späteren Tests. Gemessen: vor dem Import Root auf WARNING ohne Handler, danach INFO mit stdout-Handler; im Messlauf stehen die JSON-Zeilen dieses Handlers nach der Zusammenfassung im Protokoll. `TestConfigureLogging` setzt danach nur den Level zurück, nicht die Handler. Der Fall aus #336 (`rasterio.propagate = False` aus `measure_tiles.py`) ist behoben; einen Wächter, der so etwas allgemein findet, gibt es nicht.

### 2.8 Befund Z: Zeitmessung im Pyramidenbau (P)

`jobs/test_overview_builder.py::TestTheSupervisorGivesTheTurns::test_a_build_reads_its_files_an_interval_apart_and_leaves_no_place_behind` prüft `min(Abstand) > 0.4` bei 0,5 s Intervall. Gemessen wird im Kind **nach** dem `("go",)`. Die Zusage des Systems betrifft aber die **vergebenen** Zeitpunkte: `SourceHosts.reserve` rechnet den nächsten Zeitpunkt vom vorigen vergebenen, nicht vom tatsächlich gesendeten. Kommt ein `go` unter Last um d zu spät und das nächste pünktlich, misst das Kind 0,5 − d (Befund M5-11: 0,31 s). Der Code ist richtig, der Test misst das Falsche. Derselbe Fall steckt in `test_the_requests_of_each_file_count_towards_the_spacing` (`> 0.45` bei 3 × 0,2 s).

### 2.9 Befund B: Skripte (M, P)

- `scripts/tile-bench/job_bench.py` importiert `REGISTRY` aus `earthx.catalog.datasets`, das es seit M5-13 nicht mehr gibt (`registry()`); weil die Importe im `__main__`-Block stehen, fällt das erst beim Start auf. Die übrigen Aufrufe (`accept_order`, `check_recipe_hosts`, `submit`, `Supervisor._start_child/_watch/_upload_and_finish`) passen zum heutigen Stand (P).
- Browser-Skripte (Dev-Server, keine Quelle), Stand `main` 5b45034: siehe Tabelle.

| Skript | Befund | heute |
|---|---|---|
| `advanced-search.cjs` | #299 | grün (61 s) |
| `evaluate-coverage.cjs` | #299 | grün (29 s) |
| `narrow-windows.cjs` | #299 | grün (84 s) |
| `settings-panel.cjs` | #299 | grün (50 s) |
| `tooltips.cjs` | #299 | grün (10 s) |
| `selection-block.cjs` | #299 | grün (24 s) |
| `within-aoi.cjs` | #299 | grün (56 s) |
| `pyramid-every-level.cjs` | #381 | grün (139 s) |
| `pyramid-every-level.cjs` mit `MANAGER=open` | #381: erwartet die Ladeanzeige in der Zeile, die UI-09 entfernt hat | **rot** in beiden Varianten: „no row shows the mark while the overview tiles load“; in „normal“ zusätzlich „z8: no tile of the mosaic was asked for“ (Ursache offen: offene Verwaltung über der Karte oder echter Fehler) |

Die sieben Skripte aus #299 sind seither nebenbei repariert worden; zu tun bleibt nur `MANAGER=open`.

---

## 3. Maßnahmen

### 3.1 Stabilität (PR 1)

1. **Temp (T):** in `pyproject.toml` `tmp_path_retention_policy = "failed"` und `tmp_path_retention_count = 1`. `tmp_path` eines bestandenen Tests wird gleich nach dem Test gelöscht; Verzeichnisse fehlgeschlagener Tests bleiben zum Nachsehen, vom letzten Lauf. Gilt auch in der CI (dort ohne Wirkung auf das Ergebnis). Dazu beim Start des Laufs eine Warnung, wenn unter `tempfile.gettempdir()` weniger als 12 GB frei sind (Zahl aus §2: ein voller Lauf heute 9,6 GB, nach der Regel weniger).
2. **Datenbanken (D):** Jeder Lauf bekommt eine Lauf-Kennung (8 Hex-Zeichen), die der xdist-Controller an die Worker gibt (`pytest_configure_node`). Namen: `earthx_t<lauf>_tpl` (Vorlage), `earthx_t<lauf>_gw0` …, im seriellen Lauf `earthx_t<lauf>_main`; die Proben in `test_worker_database.py` ebenso mit Kennung. Die Vorlage wird **einmal je Lauf** migriert (PostGIS, pgstac, earthx), die Worker kopieren sie mit `CREATE DATABASE … TEMPLATE` (A: spart je Worker die Migration). Die konfigurierte Datenbank wird nur noch als Verwaltungsverbindung benutzt, nie beschrieben. Der Controller hält für die Dauer des Laufs eine Advisory-Sperre auf seine Kennung; beim Start löscht jeder Lauf nur Datenbanken `earthx_t*`, deren Sperre niemand hält (Reste abgebrochener Läufe), nie die eines laufenden. Prüfungen von `require_postgres_env` (nur lokal) bleiben vorne.
3. **Logger (G):** Ein Wächter in `tests/conftest.py` hält den Zustand des Logging **vor dem Sammeln** fest (Root-Level und -Handler ohne die von pytest, Level/Propagation/`disabled` jedes Loggers, `logging.disable`) und stellt ihn **nach jedem Test** wieder her. Wer ihn verändert hat, steht am Ende des Laufs in einer Zeile je Test (F5). Die Tests, die `configure_logging` prüfen, rufen es weiter selbst auf.
4. **Pyramidenbau (Z):** Der Test zeichnet im Supervisor (läuft im Testprozess) die **vergebenen** Zeitpunkte auf (Rückgabe von `SourceHosts.reserve`, umgerechnet auf `time.time()`) und prüft: (a) Abstand der vergebenen Zeitpunkte ≥ Intervall (bis auf Rundung), (b) das Kind liest nie **vor** seinem Zeitpunkt. Beides wackelt unter Last nicht, weil Verspätung keine der beiden Aussagen verletzt. Gleich für `…count_towards_the_spacing`.
5. **Teardown `test_worker.py`:** nicht nachgestellt (§2.5). Nach F3 = 1 kamen alle Fälle aus Cloud-Sessions; Ursache ist der Plattenplatz, behoben mit Punkt 1. `test_worker.py` bleibt unverändert.
6. **`job_bench.py`:** `registry()` statt `REGISTRY`, einmal gegen `slow_source.py` laufen lassen; ein kleiner Test startet `job_bench.py --help`, damit ein veralteter Import künftig in der CI auffällt (F7).
7. **Browser-Skript (Zusatz Otto 19.11.: z8 untersuchen, Befund im Bericht; ein Fehler im Produktivcode wird nicht hier behoben, sondern als eigene Fehleraufgabe vorgeschlagen):** `pyramid-every-level.cjs` mit `MANAGER=open` an den heutigen Stand anpassen: Prüfung 4 erwartet keine Marke in der Zeile mehr, sondern den Toast „Loading data“ auch bei offener Verwaltung (entschieden: Plan M5 §2 Punkt 9, Otto 16.11., UI-09). Den Fehlschlag bei z8 erst klären: Liegt es an der offenen Verwaltung über der Karte, wird der Prüfausschnitt angepasst; ist es ein echter Fehler, kommt er als Befund in den PR und wird nicht im Skript verdeckt.

### 3.2 Laufzeit (PR 2)

1. **Katalog einmal je Worker (L1):** eine Session-Fixture in `integration/conftest.py` lädt den Katalog einmal; nach jedem Test prüft ein billiger Fingerabdruck (Collections mit `updated`, Zahl der gelisteten Zeilen, Suchindex), ob jemand ihn verändert hat, und lädt nur dann neu. Die sieben Dateien nutzen sie statt ihrer eigenen Fixture; Tests, die gelistete Zeilen schreiben, räumen wie heute auf. Erwartet (A): von 364 × ≈ 4,4 s auf einmal je Worker plus Neuladen nach den wenigen ändernden Tests, **≈ −1 400 s Summe**.
2. **Speicher-Tests (L2), nur Zusammenlegen:** gleiche Kind-Aufrufe einmal je Lauf messen und das Ergebnis in beiden Tests prüfen (heute ein Fall, 42 s); gleiche Szenen einmal je Lauf bauen (Session-Fixture nach Größe und Bändern). Erwartet ≈ −60 bis −100 s.
3. **Kürzungen nach §5**, nur mit Ottos Freigabe.

Erwartet zusammen (A): Summe von 4 678 s auf etwa 3 100 s, Wandzeit in der Session **etwa 13 min** statt 20. Die Integration (Teil 1 der CI) wird dabei deutlich kürzer als die anderen drei Teile; die Aufteilung in `scripts/ci-backend-shard.sh` bleibt trotzdem, wie sie ist, bis Otto anders entscheidet (F8).

### 3.3 Was nicht vorgeschlagen wird

- Mehr xdist-Worker als Kerne: Die Integration wartet auf Postgres (≈ 30 % CPU frei), aber `-n` steht in `addopts` und gilt damit auch in der CI; die Speicher-Tests messen Spitzen und brauchen RAM.
- Langsame Tests per Marker aus dem Standardlauf nehmen: Dann liefen sie in der CI nicht mehr, ohne `.github/` zu ändern.
- `catalog-load` selbst beschleunigen (`place_terms` zwischenspeichern): Produktivcode; mit §3.2 Punkt 1 nicht nötig.

---

## 4. Schnitt: höchstens zwei PRs

| PR | Inhalt | Umfang (A) |
|---|---|---|
| **1** (dieser) | Plan; §3.1 Punkte 1–7 | ≈ 300 Zeilen ohne Plan |
| **2** | §3.2; Messung vorher/nachher (F8) | ≈ 250 Zeilen |

Jeder PR läuft vor dem Push: die Tests der geänderten Module, `ruff check backend`, `lint-imports`, bei Frontend-Änderungen `npm run lint` und `npx tsc -b`, die geänderten Browser-Skripte. Die volle Suite prüft die CI.

---

## 5. Kürzungsliste (Löschen nur mit Freigabe)

Nach §3.2 Punkt 1 sind die Integrationstests billig (≈ 0,3–0,5 s); dort wird **nichts** gelöscht. Echte Dopplungen (gleicher Aufruf, gleiche Eingaben) werden zusammengelegt, nicht gelöscht (§3.2 Punkt 2). Zum Löschen bleibt ein Kandidat:

| # | Test | Zeit | Warum | Was verloren ginge |
|---|---|---:|---|---|
| K1 | `processing/test_reproject.py::TestEachBandIsWarpedForItself::test_band_1_has_the_same_bytes_with_any_number_of_bands[18]` | 26 s, 0,6 GB Temp | 34 Bänder prüfen dieselbe Aussage über die Teilung des Warps nach `warp_mem_limit` mit mehr Bändern | der Zwischenwert 18; `adr/0020` §3.4 und NM4-43 nennen 1, 2, 3, 4, 18 und 34 als Prüfpunkte, der Plan NM4-43 wäre nachzuführen |

Sonst keiner: Die übrigen langsamen Tests prüfen je eine eigene Aussage (Speicher je Operator und Methode, je Bänderzahl, je Szenengröße).

---

## 6. Fragen an Otto

**F1 — Katalog in den Integrationstests (§3.2 Punkt 1)?**
1. Einmal je Worker laden, nach jedem Test Fingerabdruck, bei Abweichung neu laden **(Empfehlung)**
2. Einmal je Modul laden, ohne Fingerabdruck
3. Wie heute

**F2 — Test-Datenbanken (§3.1 Punkt 2)?**
1. Lauf-Kennung in jedem Namen, Vorlage je Lauf, auch seriell nie die konfigurierte Datenbank, Reste toter Läufe über die Advisory-Sperre löschen **(Empfehlung)**
2. Wie 1, seriell aber weiter in der konfigurierten Datenbank
3. Nur die Lauf-Kennung im Namen, sonst wie heute

**F3 — Wo traten Neustart, Migrationskonflikte und Teardown-Fehler auf?**
1. In Cloud-Sessions: Ursache vermutlich voller Plattenplatz (§2.5), behoben mit §3.1 Punkt 1; keine weitere Änderung an `test_worker.py` **(Empfehlung, wenn zutreffend)**
2. Lokal mit mehreren Checkouts auf einem Postgres: behoben mit F2; bitte den Fehlertext der Teardowns, falls vorhanden
3. Beides

**F4 — Temp-Verzeichnisse (§3.1 Punkt 1)?**
1. `retention_policy = "failed"`, `retention_count = 1`, Warnung unter 12 GB frei **(Empfehlung)**
2. Nur `retention_count = 1`
3. Nur die Warnung

**F5 — Wächter für Logger (§3.1 Punkt 3)?**
1. Wiederherstellen nach jedem Test, Verursacher am Ende des Laufs nennen **(Empfehlung)**
2. Wiederherstellen und den verursachenden Test fehlschlagen lassen
3. Wie 1, zusätzlich `configure_logging()` in `jobs/main.py` vom Import in den Start verlegen (Produktivcode, eigene Prüfung des Zugriffsprotokolls nötig)

**F6 — Zeitmessung im Pyramidenbau (§3.1 Punkt 4)?**
1. Vergebene Zeitpunkte prüfen, dazu „nie vor dem Zeitpunkt gelesen“ **(Empfehlung)**
2. Schwelle auf 0,3 s senken
3. Test bei Fehlschlag wiederholen

**F7 — `job_bench.py`?**
1. Reparieren, einmal laufen lassen, Test mit `--help` **(Empfehlung)**
2. Nur reparieren
3. Löschen (die Messung NM4-62 ist abgeschlossen)

**F8 — Kürzung, Beleg und CI-Aufteilung?**
1. K1 nicht löschen; am Ende von PR 2 ein zweiter voller Lauf in der Session für vorher/nachher; `ci-backend-shard.sh` bleibt **(Empfehlung)**
2. K1 löschen (mit Nachtrag in NM4-43), sonst wie 1
3. Wie 1, dazu Vorschlag einer neuen Aufteilung der CI-Teile nach den CI-Zeiten von PR 2 (Änderung erst mit deiner Erlaubnis)

## 6a. Antworten Otto (19.11.2026)

F1 bis F8 jeweils Option 1:

- F1: Katalog einmal je Worker, Fingerabdruck nach jedem Test, bei Abweichung neu laden.
- F2: Lauf-Kennung, Vorlage je Lauf, nie die konfigurierte Datenbank, Reste über die Advisory-Sperre.
- F3: Alle Abbrüche, Neustarts und Teardown-Fehler kamen aus Cloud-Sessions; lokal laufen keine Tests. Ursache Plattenplatz (§2.5), keine Änderung an `test_worker.py`.
- F4: `tmp_path_retention_policy = "failed"`, `tmp_path_retention_count = 1`, Warnung unter 12 GB frei.
- F5: Logger nach jedem Test wiederherstellen, Verursacher am Ende des Laufs nennen.
- F6: vergebene Zeitpunkte prüfen, dazu „nie vor dem Zeitpunkt gelesen“.
- F7: `job_bench.py` reparieren, einmal laufen lassen, Test mit `--help`.
- F8: K1 bleibt; am Ende von PR 2 ein voller Lauf für vorher/nachher; `scripts/ci-backend-shard.sh` bleibt.

Zusatz: Die fehlende Mosaik-Kachel bei z8 in `pyramid-every-level.cjs` (Variante „normal“, `MANAGER=open`) kurz untersuchen; ist es ein Fehler im Produktivcode, nicht in M5-61 beheben, sondern als eigene Fehleraufgabe vorschlagen.

## 7. Umsetzung PR 1 (#387, 19.11.2026)

§3.1 Punkte 1–7, je ein Commit:

1. **Temp:** `tmp_path_retention_policy = "failed"`, `tmp_path_retention_count = 1`; Warnung im Kopf des Laufs unter 12 GB frei. Nach dem Lauf unten blieb 1 MB unter `/tmp/pytest-of-root` (vorher 9,6 GB nach dem vollen Lauf).
2. **Datenbanken:** wie §3.1 Punkt 2. Dabei gefunden: `pypgstac` gibt nach der Migration seine Verbindung nicht an den Pool zurück, `close()` schließt sie deshalb nicht. Eine Vorlage mit offener Sitzung lässt sich nicht kopieren; `create_worker_database` gibt die Verbindung jetzt zurück. Daher kamen auch die Meldungen „terminating connection due to administrator command“ beim Löschen der Worker-DBs am Ende jedes Laufs. Die Jobs-Datenbank heißt jetzt nach der Datenbank des Laufs (`…_gw0_jobs`), damit ein späterer Lauf auch sie als Rest erkennt. Ein Lauf, der zwei andere simuliert (einer tot, einer hält seine Sperre), steht in `test_worker_database.py`. Zwei echte Läufe gleichzeitig habe ich nach der Regel der Session nicht gestartet.
3. **Logger:** Wächter wie §3.1 Punkt 3 (`tests/logging_guard.py`). Was beim Sammeln verstellt wird (der Import von `earthx.jobs.main`), setzt er vor dem ersten Test zurück und nennt es einmal als „while collecting“. Tests, die `configure_logging` absichtlich aufrufen (drei Klassen in `test_logging.py`, `objectstore/test_logs.py`), tragen den Marker `changes_logging` und werden ohne Meldung zurückgesetzt. Weitere Verursacher im Lauf unten: `integration/test_api_job_lifespan.py::TestStart` (neun Tests; der Start von `api` richtet das Logging ein) und `jobs/test_overview_child_detail.py::test_a_child_that_cannot_read_its_job_says_the_step_it_never_got_to`. Beide setzt der Wächter zurück; geändert sind sie nicht.
4. **Pyramidenbau:** wie §3.1 Punkt 4. Gegenprobe: Halbes Intervall in `TurnKeeper._reserve` oder ein `go` 0,1 s zu früh machen den Test rot. **Befund:** Der Supervisor liest seine Uhr vor dem Aufruf von `reserve`; ein `go` kann deshalb um die Dauer dieses einen Datenbank-Aufrufs (wenige ms) vor dem vergebenen Zeitpunkt kommen. Der Test lässt genau diese Dauer zu. Gegen Intervalle ab 0,2 s ist das unerheblich; ich schlage keine Aufgabe vor.
5. **Teardown `test_worker.py`:** unverändert (F3 = 1).
6. **`job_bench.py`:** `registry()` statt `REGISTRY`. Gelaufen gegen `slow_source.py` mit synthetischen COGs: `reproject` (2 Läufe), `ndvi_mask`, `--sequence`, alle `successful`. Neuer Test `test_job_bench_script.py` (`--help` führt alle Importe aus), gegen den alten Stand rot.
7. **`pyramid-every-level.cjs`:** Bei offener Verwaltung prüft es jetzt, dass **keine** Zeile eine Ladeanzeige trägt (UI-09); den Toast prüft es wie bisher. **z8 ist kein Fehler im Produktivcode:** Bei vier Läufen mit Protokoll je Schritt kamen bis 0,5 s nach dem Sprung auf z8 zwischen 2 und 8 Mosaik-Anfragen. Die Kacheln werden also angefragt, auf der belasteten Seite aber teils erst nach 0,5 s. Das Skript wartet jetzt bis zu 3 s auf die erwartete Route, bevor es scheitert. Beide Varianten grün.

**Geprüft:** `pytest backend/tests/integration backend/tests/earthx/jobs backend/tests/earthx/objectstore backend/tests/test_*.py`: 2 878 bestanden, 25 übersprungen (`pwsh`), 9:45 min; danach keine Test-Datenbank übrig. `ruff check backend` grün, `lint-imports` 17 Verträge eingehalten, `npx tsc -b` und `npm run lint` ohne Befund. Browser: `pyramid-every-level.cjs` mit und ohne `MANAGER=open` grün.
