# NM4-23 — Backend-Tests schneller

**Stand:** 24.10.2026, beauftragt von Otto (Backlog-Punkt 23 in `docs/plans/nach-m4-backlog.md`).
**Stufe B:** Erst kommt der Plan im Draft-PR (Optionen, Empfehlung, bei Rechenrelevanz Quellen), Otto gibt ihn frei, dann folgt der Code in derselben Session.
**Modell:** Opus für Messung und Plan, Sonnet (Effort hoch) für die Umsetzung.
**Start:** sofort möglich; höchstens zwei Stufe-B-Sessions gleichzeitig.
**Startsatz:** „Führe Aufgabe NM4-23 aus `docs/plans/querschnitt/nm4-23-backend-tests-schneller.md` aus.“

## 1. Anlass

CI-Lauf auf `main` (24.10.2026): Job „Backend — lint and tests“ 14,2 min, davon `pytest` 13,2 min; Installation 0,5 min. Frontend 0,7 min, Modulgrenzen 0,7 min, compose-topology 1,9 min.

## 2. Soll

- Die Backend-Tests laufen deutlich schneller, ohne an Aussage zu verlieren.

## 3. Umfang

- **Schritt 1 – messen:** `pytest --durations=30` in der Session; Tabelle der langsamsten Tests im PR.
- **Abhilfe ohne Verlust:** kleinere synthetische Raster, wo die Größe nicht der Prüfgegenstand ist; teure Fixtures mit Geltungsbereich `module`/`session`; doppelte Prüfungen zusammenlegen. Speicher- und Bitgleich-Tests bleiben in voller Größe.

## 4. Im Plan klären (mit Optionen und Empfehlung)

- **Schritt 2 – parallel (nur nach Ottos Freigabe):** `pytest-xdist` ist eine neue Abhängigkeit. Mit Quellen klären: Verträglichkeit mit `spawn`-Kindprozessen und Speichermessung (`VmHWM` je Prozess), eigene Datenbank je xdist-Worker, Zahl der Kerne der GitHub-Runner für öffentliche Repos. Einstellung über die pytest-Konfiguration.

## 5. Grenzen

- Keine Tests streichen oder überspringen, um Zeit zu sparen.
- Oberflächentexte nur auf Englisch; wenig Text, Erklärungen im Tooltip (UI-01 §4).
- Keine neue Abhängigkeit ohne Frage an Otto.
- Keine AOI, Job-, Rezept- oder Permalink-Kennungen, Hashes, `href` oder signierten URLs in Logs oder URLs.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.

## 6. Abnahme

- Laufzeit vorher/nachher (Session und CI) im PR; Zahl der Tests unverändert oder höher.
- Prüfanleitung für Otto (Browser und/oder PowerShell 5.1) im PR.
- Alle vier Pflicht-Checks der CI sind grün.
- Log-Zeile(n); Backlog-Punkt in `docs/plans/nach-m4-backlog.md` als erledigt markieren (mit PR-Nummer).
- Vor „fertig“ ist main geholt.

## 7. Kurzfassung

- **Messung (26.10.2026):** In der Session laufen 5939 Tests in 989–1009 s (4 Kerne, 16 GB). In der CI auf `main` waren es heute 551 s (9:11 min); am 24.10. waren es 13,2 min. Die Zeit verteilt sich breit: 1015 Tests über 0,1 s kosten zusammen 641 s.
- **Speichertests:** Die acht Speichertests (`test_memory_*`) brauchen 221 s, gut ein Fünftel. Sie bleiben in voller Größe (§3).
- **Schritt 1 ohne Verlust: rund −10 %.** Der größte Hebel ist `boto3`. Es liegt nur im Dev-Lock (über `moto`). Damit legt rasterio bei jedem `rasterio.Env` eine AWS-Sitzung an, das Image tut das nicht (NM4-26 B9). Ohne `boto3` in rasterio laufen die Tests in 894 statt 989 s, alle grün. Andere Hebel bringen je unter 10 s (§10.1). Kleinere Raster habe ich nicht gefunden, wo die Größe nicht Prüfgegenstand ist.
- **Schritt 2 parallel: Faktor 3,4.** Probelauf mit `pytest-xdist` und 4 Workern, eigene Datenbank je Worker: 290 s statt 989 s, zweimal alles grün. Speicherspitze des Rechners 5,5 von 15 GB. Für die CI erwarte ich 3–4 min statt 9 min; gemessen wird das im PR.
- **Zwei Tests verhindern `xdist` heute:** Ihre Kennungen enthalten eine Speicheradresse bzw. eine Zufalls-ID. Jeder Worker sammelt dann andere Tests, und `xdist` bricht ab. Das lässt sich ohne Verlust beheben (§10.1 M2).
- **Fragen an Otto in §12.** Kern ist Frage 1: neue Dev-Abhängigkeit `pytest-xdist` (MIT, mit `execnet`, MIT), nur im Dev-Lock, nicht im Image.

## 8. Messung

### 8.1 Methode

- **Session:** 4 Kerne, 16 GB, Postgres 16 lokal, Stand `main` 459358e. Gemessen mit `pytest --durations=0 --durations-min=0`, ohne Cache-Plugin; dazu `time` für die Wandzeit.
- **CI:** Lauf 806 auf `main` (6a7b9c0, 26.10.2026), Job „Backend — lint and tests“, Schritt `pytest`. In der CI gibt es keine `--durations`, weil `.github/` unverändert bleibt. Die Zahl stammt aus der Schlusszeile des Logs.
- **Probeläufe:** Ein Plugin im Scratchpad der Session, über `-p` geladen. Das Repo und das Lock bleiben unverändert. `pytest-xdist` 3.8.0 und `execnet` 2.1.2 lagen dafür nur in einem Ordner außerhalb des venv.

### 8.2 Ergebnis

| Lauf | Wo | Tests | Wandzeit |
|---|---|---|---|
| heute | CI (Lauf 806) | 5939 bestanden | **551 s** (Job 10:05 min) |
| heute, `--durations=60` | Session | 5931 bestanden, 8 übersprungen¹ | **1009 s** |
| heute, `--durations=0` | Session | 5931 / 8¹ | **989 s** |
| rasterio ohne `boto3` (M1) | Session | 5931 / 8¹ | **894 s** |
| M1 + `xdist -n 4`, `--dist load` | Session | 5931 / 8¹ | **353 s** |
| M1 + `xdist -n 4`, `--dist worksteal` | Session | 5931 / 8¹ | **290 s** |

¹ Die PowerShell-Tests in `test_try_job_search.py`: `pwsh` gibt es nur im CI-Image. Mit ihnen sind es 5939 wie in der CI.

**Verteilung (Session, 989 s):**
- Nach Phase: Aufruf 692 s, Aufbau 228 s, Abbau 56 s, Sammeln rund 13 s.
- Nach Verzeichnis: `api` 394 s, `processing` 339 s, `jobs` 118 s, `integration` 44 s, Rest 64 s.
- Nach Dauer:

| Tests ab … | Anzahl | zusammen |
|---|---|---|
| 5 s | 11 | 207 s |
| 1 s | 120 | 416 s |
| 0,1 s | 1015 | 641 s |
| 0,01 s | 2393 | 692 s |

**Die 25 langsamsten Tests** (Session; Summe aus Aufbau, Aufruf und Abbau, in s). Der Aufbau einer Fixture mit Geltungsbereich `module` zählt beim ersten Test des Moduls.

| gesamt | Aufbau | Aufruf | Test (unter `backend/tests/`) |
|---|---|---|---|
| 72,0 | 17,7 | 54,3 | `earthx/processing/test_memory_8192.py::test_the_peak_stays_below_the_limit_and_does_not_follow_the_scene_size` |
| 30,7 | 4,7 | 26,0 | `earthx/processing/test_memory_export.py::test_two_items_stay_below_the_limit_and_cost_about_what_one_costs` |
| 28,8 | 4,0 | 24,9 | `earthx/processing/test_memory_reproject.py::…[bilinear]` |
| 24,4 | 2,1 | 22,2 | `earthx/processing/test_memory_mosaic.py::test_further_scenes_stay_below_the_limit_and_cost_about_what_one_costs` |
| 17,7 | 5,2 | 12,5 | `earthx/processing/test_memory_mask_normalize.py::…[mask]` |
| 16,8 | 0,0 | 16,8 | `earthx/processing/test_memory_mask_normalize.py::…[normalize]` |
| 15,6 | 0,9 | 14,7 | `earthx/processing/test_memory_mosaic.py::test_a_warped_scene_stays_below_the_limit_too` |
| 15,4 | 0,0 | 15,4 | `earthx/processing/test_memory_reproject.py::…[lanczos]` |
| 7,9 | 0,0 | 7,9 | `earthx/processing/test_estimate_geographic.py::…[1.0-EPSG:3857]` |
| 7,1 | 0,0 | 7,1 | `earthx/access/test_download_stress.py::test_repeated_downloads_always_read_back` |
| 6,8 | 6,6 | 0,2 | `earthx/processing/test_reproject_tolerance.py::…[nearest-heights-coarse]` |
| 4,6 | 0,0 | 4,6 | `earthx/processing/test_reproject.py::TestAWholeRun::test_v2_and_v3_give_the_same_bytes_for_the_methods_of_version_2` |
| 4,1 | 0,1 | 3,4 | `earthx/jobs/test_worker.py::TestLeaseAndAttempts::test_an_upload_longer_than_the_lease_does_not_lose_the_run` |
| 3,8 | 0,0 | 3,8 | `earthx/processing/test_estimate_geographic.py::…[1.0-EPSG:3035]` |
| 3,6 | 3,5 | 0,2 | `earthx/api/test_tiler_statistics_operator.py::TestHowMuchIsRead::test_a_smaller_max_size_reads_fewer_pixels_over_the_same_extent` |
| 3,6 | 0,0 | 3,6 | `earthx/processing/test_reproject.py::TestAWholeRun::test_a_whole_run_stays_inside_the_row_of_its_method[bilinear]` |
| 3,5 | 0,1 | 3,0 | `earthx/jobs/test_worker.py::TestFailures::test_a_second_attempt_can_succeed_and_clears_the_error` |
| 3,5 | 3,4 | 0,1 | `earthx/api/test_tiler_zarr.py::TestWhatTheSourceGetsWrong::test_no_answer_repeats_the_address` |
| 3,5 | 0,1 | 3,0 | `earthx/jobs/test_worker.py::TestTwoSupervisorsOneCap::test_the_cap_holds_whatever_the_number_of_supervisors` |
| 3,4 | 0,1 | 3,1 | `earthx/api/test_processing_events.py::TestManyClients::test_fifty_streams_are_one_connection_of_this_process` |
| 3,3 | 0,1 | 2,3 | `earthx/jobs/test_worker.py::TestTwoSupervisorsOneCap::test_the_limit_per_host_holds_across_supervisors_too` |
| 3,3 | 0,3 | 3,0 | `earthx/api/test_tiler_mask_normalize.py::TestTheTileEqualsTheJobOnTheNativeLevel::…[mask]` |
| 3,2 | 0,0 | 3,2 | `earthx/api/test_tiler_mosaic.py::TestWhatTheUrlMayCarry::test_an_item_id_that_is_no_id_is_a_400_…` |
| 3,2 | 0,0 | 3,2 | `earthx/api/test_tiler_mosaic.py::TestNothingIsFetchedForARequestThatIsRefused::…` |
| 3,2 | 0,1 | 3,1 | `earthx/api/test_processing_route.py::TestTheQueueIsNotThere::test_an_unreachable_database_is_a_503_that_names_nothing` |

**Die langsamsten Dateien** (Session, in s; ohne die Speichertests):

| s | Tests | Datei | woran es liegt |
|---|---|---|---|
| 73,9 | 53 | `earthx/jobs/test_worker.py` | Abbau 31 s: `Supervisor.stop` wartet bis 1 s auf den Listener (`conn.notifies(timeout=1.0)` in `jobs/worker.py`) |
| 64,7 | 333 | `earthx/api/test_processing_route.py` | Aufbau 94 ms je Test: zwei botocore-Clients (`Store.from_environ`), Pool, Leeren der Tabellen |
| 43,5 | 98 | `earthx/api/test_tiler_mosaic.py` | App und COGs je Test; mit `boto3` −6,5 s |
| 30,3 | 96 | `earthx/processing/test_reproject_tolerance.py` | Rechnung je Methode und Fall, Raster schon klein (Docstring) |
| 28,5 | 66 | `earthx/api/test_tiler_operator.py` | mit `boto3` −8,3 s |
| 27,4 | 81 | `earthx/processing/test_reproject.py` | Bitgleich- und Toleranzläufe |
| 24,2 | 36 | `earthx/api/test_tiler_chain.py` | mit `boto3` −9,3 s |

### 8.3 Was die Zahlen sagen

- **B1 Ein breiter Schwanz, kein einzelner Ausreißer.** Ohne die Speichertests braucht kein Test mehr als 8 s. Die 120 Tests über 1 s sind zusammen 416 s, die übrigen 5800 zusammen rund 560 s. Mit Schritt 1 allein (Kürzen einzelner Tests) kommt man deshalb nicht weit.
- **B2 Die Speichertests sind ein Fünftel und bleiben.** 221 s für acht Tests. Sie messen `VmHWM` in einem eigenen Prozess und bauen ihre Szenen in voller Größe, das ist ihr Prüfgegenstand (§3).
- **B3 `boto3` kostet 10 %.** rasterio 1.5.2 baut in `rasterio.Env` eine `AWSSession`, wenn `boto3` importierbar ist (`rasterio/session.py`, `Session.aws_or_dummy`). `boto3` kommt mit `moto[s3]` nur ins Dev-Lock. Das Image hat es nicht, `test_backend_lock.py` prüft das. Die Kindprozesse der Tests verstecken `boto3` schon (`child_targets.py`, `runner/targets.py`), der Testprozess selbst nicht. Ohne es im Testprozess: 894 statt 989 s, keine Abweichung im Ergebnis. Am meisten gewinnen `test_tiler_*` und `test_reproject.py`.
- **B4 Der Worker-Abbau wartet je Test bis 1 s.** Der Listener-Thread blockiert in `conn.notifies(timeout=1.0)`, `stop()` wartet auf ihn. Das sind 31 s Abbau in `test_worker.py`. Es lässt sich nur im Produktcode ändern (`jobs/worker.py`), das ist außerhalb von „nur Tests und Testkonfiguration“ (Frage 4).
- **B5 Parallel trägt.** Die Tests hängen kaum aneinander. Mit eigener Datenbank je Worker liefen beide Probeläufe grün. `worksteal` ist 18 % schneller als `load`, weil die langen Speichertests sonst am Ende auf einem Worker stehen.
- **B6 CI und Session unterscheiden sich um den Faktor 1,8** (551 s gegen 989 s). Die Verhältnisse sind dieselben. Die CI-Zahl nach der Umsetzung wird im PR gemessen, nicht hochgerechnet.

## 9. Recherche

Abgerufen am 26.10.2026. Die Doku-Seiten von GitHub und `pytest-xdist` waren über den Proxy der Session nicht erreichbar. Gelesen wurde deshalb ihr Quelltext auf `raw.githubusercontent.com` (Primärquelle). [P] = Primärquelle, [M] = in der Session gemessen, [A] = abgeleitet.

| # | Aussage | Quelle | Beleg |
|---|---|---|---|
| R1 | `ubuntu-latest` hat für öffentliche Repos 4 vCPU und 16 GB RAM, für private 2 und 8. `ubuntu-latest` ist Ubuntu 24.04. | `github/docs`, `data/reusables/actions/supported-github-runners.md`; Blog „GitHub-hosted runners: Double the power for open source“ (17.01.2024); `actions/runner-images` README | [P] |
| R2 | `pytest-xdist` 3.8.0 (01.07.2025) ist der neueste Stand, Lizenz MIT. Es braucht `execnet>=2.1` (MIT) und `pytest>=7`; `psutil` ist ein optionales Extra. | PyPI-JSON `pytest-xdist`; `pyproject.toml` im Repo `pytest-dev/pytest-xdist` | [P] |
| R3 | `-n auto` nimmt die physischen Kerne über `psutil`. Ohne `psutil` nimmt es `os.sched_getaffinity` bzw. `os.cpu_count`, auf dem Runner also 4. `PYTEST_XDIST_AUTO_NUM_WORKERS` geht vor. `-n logical` braucht Python ≥ 3.13 oder `psutil`. | `src/xdist/plugin.py` (Funktion `auto_detect_cpus`), `docs/distribution.rst` | [P] |
| R4 | Verteilmodi: `load` (Standard), `loadscope`, `loadfile`, `loadgroup` (`@pytest.mark.xdist_group`), `worksteal` (Leerlaufende Worker übernehmen Tests). | `docs/distribution.rst` | [P] |
| R5 | Jeder Worker ist ein eigener Interpreter, gestartet mit `subprocess.Popen([sys.executable, "-u", "-c", …])`, kein `fork`. Sein `__main__` kommt aus `-c`, `spawn` lädt im Kind deshalb kein `__main__` nach. `sys.path` geht an `spawn`-Kinder über. | `execnet` `gateway_io.py`, `gateway_bootstrap.py`; CPython `Lib/multiprocessing/spawn.py` (`get_preparation_data`) | [P], [A] |
| R6 | Bekanntes Problem nur mit `fork` in Tests (Warnung wegen eines `execnet`-Threads); der Maintainer empfiehlt `spawn`. Alle Kindprozesse dieser Tests starten mit `spawn`. | pytest-xdist Issue #1186 (offen), PR #1336 | [P] |
| R7 | `VmHWM` ist der Spitzenwert des RSS **dieses** Prozesses und steht in `/proc/<pid>/status`. Andere Prozesse ändern ihn nicht; sie wirken nur über den Gesamtspeicher (Swap → `VmSwap`). | Linux `Documentation/filesystems/proc.rst` | [P], [A] |
| R8 | Fixture `worker_id` und Umgebungsvariable `PYTEST_XDIST_WORKER` (`gw0`, `gw1`, …), ohne `xdist` `"master"` bzw. nicht gesetzt. Session-Fixtures laufen je Worker einmal. | `docs/how-to.rst`, `plugin.py` | [P] |
| R9 | `addopts = "-n auto"` in der pytest-Konfiguration ist das dokumentierte Muster. `-n 0` auf der Befehlszeile schaltet ab und läuft im Hauptprozess. `-p no:xdist` geht dann nicht mehr, weil `-n` unbekannt wäre. | `docs/distribution.rst`; pytest `how-to/plugins.rst` | [P], [A] |
| R10 | `--durations` und `-ra` funktionieren unter `xdist`: Beide Berichte kamen im Probelauf vollständig (40 Dauern, 8 übersprungene Tests). | Probelauf §8.2 | [M] |
| R11 | Das Sammeln muss in allen Workern dieselben Kennungen liefern, sonst bricht `xdist` mit „Different tests were collected“ ab. | Probelauf §8.2 | [M] |

## 10. Optionen und Empfehlung

### 10.1 Schritt 1: ohne Verlust an Aussage

| # | Maßnahme | gemessen bzw. geschätzt | Verlust? |
|---|---|---|---|
| M1 | **rasterio ohne `boto3` im Testprozess**, wie im Image: In `backend/tests/conftest.py` steht `rasterio.session.boto3 = None`, mit Begründung und Verweis auf `test_backend_lock.py`. Die Kindprozesse machen das schon. | **−95 s** (989 → 894) [M] | Nein. Die Tests laufen näher am Image. Kein Test braucht eine `AWSSession`, der Lauf blieb grün. |
| M2 | **Feste Testkennungen** in `objectstore/test_client.py` (Kennung = Name statt `repr` der Funktion) und `objectstore/test_results.py` (Zufalls-ID im Test statt in `parametrize`, weiter 3 Fälle). | ±0 s; Voraussetzung für Schritt 2 | Nein. Gleiche Zahl an Tests, gleiche Prüfung. `--lf` und das Vergleichen zweier Läufe gehen damit auch. |
| M3 | **`Store` für die API-Tests einmal je Modul** statt je Test (`tests/earthx/api/conftest.py`). Der Store signiert nur, er öffnet keine Verbindung (`adr/0015` §3.2). | geschätzt −5 s | Nein. Nur wenn die Messung in der Umsetzung ≥ 3 s ergibt, sonst bleibt es. |
| — | **Kleinere Raster:** nicht vorgeschlagen. Die Raster der langsamen Nicht-Speichertests sind schon klein (`test_reproject_tolerance.py`) oder ihre Größe ist der Prüfgegenstand (`test_estimate_geographic.py`: eine ganze Kachel; Bitgleich-Tests). | — | — |
| — | **Doppelte Prüfungen zusammenlegen:** keine gefunden, die mehr als eine Sekunde bringt. | — | — |

**Empfehlung:** M1 und M2 umsetzen, M3 nur bei messbarem Gewinn. Das bringt allein etwa 10 %. Der Abbau in `test_worker.py` (B4) ist Frage 4.

### 10.2 Schritt 2: parallel mit `pytest-xdist` (nur nach Freigabe)

**Verträglichkeit, im Probelauf geprüft:**
- **`spawn`-Kinder:** Die Worker sind eigene Interpreter (R5). Die Kinder der Speicher-, Runner-, Worker- und Vergleichstests liefen unverändert, beide Läufe grün.
- **Speichermessung:** `VmHWM` gilt je Prozess (R7). Die Speichertests brauchten parallel so lange wie seriell und bestanden; die Grenzen (500 MB je Kind, Wachstum ≤ 200 MB) sind unverändert. Der Gesamtspeicher des Rechners lag höchstens bei 5,5 von 15 GB, ohne Swap. Der Runner hat 16 GB (R1).
- **Postgres:** Die T-C-Tests teilen sich heute eine Datenbank. Darin legen sie in Transaktionen Tabellen an und löschen sie wieder (`test_migrations.py`, `DROP SCHEMA pgstac` in `test_pgstac_load.py`), und `earthx.catalog.load` committet. Parallel würden sie sich blockieren oder stören. Deshalb bekommt jeder Worker eine eigene Datenbank (Frage 3). Der Datenbank-Fixture von `jobs` legt schon heute je Sitzung eine eigene an und ist damit je Worker getrennt.
- **Kerne:** 4 auf dem Runner für öffentliche Repos (R1), 4 in der Session. `-n auto` ergibt ohne `psutil` an beiden Orten 4 (R3).

**Einstellung, nur in `pyproject.toml`; `.github/` bleibt unverändert:**

```toml
addopts = "-ra --strict-markers --strict-config -n auto --dist worksteal"
```

- Seriell läuft es mit `pytest -n 0`, etwa zum Debuggen mit `--pdb` oder `-s` (R9; beides geht unter `xdist` nicht).
- Die CI ruft weiter nur `pytest` auf, ebenso die Session (`adr/0002` §6).

**Eigene Datenbank je Worker:** Ein Hook `pytest_configure` in `backend/tests/conftest.py` greift nur, wenn `PYTEST_XDIST_WORKER` gesetzt ist.
1. Er liest `.env.test` wie heute.
2. Er prüft dieselbe Regel wie `require_postgres_env`: nur lokaler Host.
3. Er legt `<PGDATABASE>_<worker>` an und setzt `PGDATABASE` für diesen Worker darauf.
4. In `pytest_unconfigure` löscht er sie wieder (`DROP … WITH (FORCE)`, wie beim `jobs`-Fixture).

Seriell (`-n 0`) bleibt alles wie heute. Wie die Datenbank entsteht, ist Frage 3.

**Neue Abhängigkeit (Frage 1):**
- `pytest-xdist>=3.8` in `backend/requirements-dev.txt`, mit Kommentar.
- Das Lock schreibt `scripts/lock-backend.sh` neu, mit Hashes; dazu kommt `execnet`.
- Nur im Dev-Lock, nicht im Image. `test_backend_lock.py` prüft das schon heute.
- Kein `psutil` (Frage 2).

**Erwartung:**
- Session: 290–350 s statt 989 s.
- CI: geschätzt 3–4 min statt 9 min [A]. Der Postgres-Container teilt sich dort die 4 Kerne mit den Tests.
- Die längste Einzeldauer begrenzt nach unten: `test_memory_8192` mit 70 s.

**Risiko:** Zeitabhängige Tests (`jobs`: Lease 3 s, Heartbeat 0,3 s) laufen unter Last. Zwei Läufe waren grün, das beweist keine Stabilität. In der Umsetzung kommen deshalb drei weitere volle Läufe in der Session und zwei in der CI dazu. Wird ein Test unter Last rot, wird er robust gemacht, nie übersprungen. Gelingt das nicht, Rückfrage.

## 11. Was nicht geändert wird

- Kein Test wird gestrichen, übersprungen oder als `local_only` markiert. Die Zahl der Tests bleibt 5939.
- Die Speicher- und Bitgleich-Tests bleiben in voller Größe und mit unveränderten Grenzen.
- `.github/`, `CLAUDE.md`, `.claude/`, `CODEOWNERS` bleiben unverändert. Der Befehl `pytest` bleibt derselbe.

## 12. Fragen an Otto

Kurz beantwortbar: je Frage eine Nummer.

**Frage 1 — `pytest-xdist` als neue Dev-Abhängigkeit (Schritt 2)?**
1. Ja, `pytest-xdist` 3.8 (MIT) mit `execnet` (MIT), nur Dev-Lock; eingestellt in `pyproject.toml`. **(Empfehlung: Faktor 3,4 in der Session)**
2. Nein, nur Schritt 1 (rund −10 %).

**Frage 2 — Wie viele Worker?**
1. `-n auto`: 4 auf dem Runner und in der Session, bei dir lokal so viele wie Kerne. Kein `psutil` nötig. **(Empfehlung)**
2. Fest `-n 4` überall.
3. `-n logical`: braucht `psutil` als weitere Abhängigkeit, auf dem Runner kein Unterschied.

**Frage 3 — Wie entsteht die Datenbank je Worker?**
1. Leer anlegen, darin PostGIS und `pypgstac migrate`: rund 2 s je Worker, einmal je Lauf [M]. Unabhängig davon, ob gerade jemand mit der konfigurierten Datenbank verbunden ist (etwa dein lokales `docker compose`). Wie in der CI frisch. **(Empfehlung)**
2. Als Kopie der konfigurierten Datenbank (`CREATE DATABASE … TEMPLATE`): 0,2 s [M], im Probelauf so gemacht. Scheitert aber, sobald eine andere Verbindung auf der Vorlage offen ist.

**Frage 4 — Wartezeit beim Stoppen des Workers (B4, 31 s seriell, unter `xdist` rund 8 s)?**
1. Nicht in dieser Aufgabe. Es ist Produktcode in `jobs/worker.py`; ich trage es als Backlog-Hinweis ein. **(Empfehlung)**
2. Mitnehmen: neues Feld `WorkerConfig.listen_seconds` (Standard 1,0 wie heute, Tests 0,2). Kleine Änderung, Verhalten im Betrieb unverändert.

## 13. Umsetzung nach Freigabe

Ein Branch, dieser Draft-PR, kleine Commits; Richtwert unter 400 Zeilen ohne das Lock.

1. **M2:** feste Kennungen in den zwei `objectstore`-Tests. Gegenprobe: zweimal sammeln mit `PYTHONHASHSEED=random`, beide Listen gleich.
2. **M1:** `boto3` in rasterio im Testprozess aus, in `backend/tests/conftest.py`. Ein Test belegt, dass `rasterio.Env()` im Testprozess eine `DummySession` hat. Er wird rot, sobald jemand die Zeile entfernt.
3. **M3:** nur bei messbarem Gewinn.
4. **Schritt 2 (bei Frage 1 = 1):**
   - Abhängigkeit und Lock.
   - Hook für die Datenbank je Worker, mit Tests:
     - Name je Worker
     - nicht lokaler Host bricht ab
     - seriell bleibt die konfigurierte Datenbank
   - `addopts` in `pyproject.toml`.
5. **Doku:**
   - Nachtrag in `adr/0002` §6: parallel und `-n 0`.
   - Zeile im Entscheidungslog.
   - Backlog-Punkt 23 erledigt.
6. **Messung nachher:**
   - Session seriell (`-n 0`) und parallel, je mit `--durations=30`.
   - CI-Zeit des PR-Laufs.
   - Zahl der Tests vorher und nachher.

## 14. Prüfanleitung für Otto (nach der Umsetzung)

In PowerShell 5.1, aus dem Repo-Wurzelverzeichnis, mit Python-venv und lokalem Postgres wie in `README.md`:

```powershell
Measure-Command { pytest | Out-Host }
Measure-Command { pytest -n 0 | Out-Host }
```

- Erwartet: Beide enden mit „5939 passed“ (oder 5931 passed, 8 skipped ohne `pwsh`). Der erste Lauf meldet oben „bringing up nodes...“ und ist deutlich kürzer.
- Danach ist keine Datenbank `<PGDATABASE>_gw…` übrig: `psql -c "\l"`.
- Im Browser unter **Actions → CI → Backend — lint and tests → Tests (pytest)**: die Dauer des PR-Laufs gegen die eines Laufs auf `main` vom 26.10.

## 15. Freigabe (Otto, 26.10.2026)

1. **Frage 1 = 1:** `pytest-xdist` als Dev-Abhängigkeit, nur im Dev-Lock.
2. **Frage 2 = 1:** `-n auto`, eingestellt über die pytest-Konfiguration; `.github/` bleibt unverändert.
3. **Frage 3 = 1:** Die Datenbank je Worker wird leer angelegt und migriert.
4. **Frage 4 = 1:** Die Wartezeit beim Worker-Stopp gehört nicht in diese Aufgabe. Statt eines Backlog-Eintrags kommt eine Zeile ins Entscheidungslog; das Backlog pflegt der Planungs-Chat.

Auflagen:
- **`boto3`/rasterio:** Genau beschreiben, wie rasterio ohne AWS-Sitzung läuft, ohne die `moto`-Tests des Objektspeichers zu schwächen. Belegen, dass diese Tests weiter dasselbe prüfen.
- **Testkennungen:** Die zwei Tests mit Speicheradresse bzw. Zufalls-ID in der Kennung werden stabil, ohne dass sie an Aussage verlieren.
- **Stabilität:**
  - Die volle Suite läuft in der Session mindestens dreimal hintereinander mit `xdist` grün.
  - Seriell (`-n 0`) läuft sie weiter.
  - Die Zeiten vorher und nachher (Session und CI) stehen im PR.

## 16. Umsetzung (26.10.2026)

### 16.1 Was sich geändert hat

- **Feste Testkennungen (M2):**
  - `objectstore/test_client.py`: Kennung ist der Name der Funktion (`pytest.param(…, id=name)`), nicht ihr `repr` mit Adresse.
  - `objectstore/test_results.py`: Die drei Fälle laufen über `range(3)`, jeder macht seine Zufalls-ID im Test.
  - Prüfgegenstand und Zahl der Fälle bleiben gleich. Zweimal sammeln mit verschiedenem `PYTHONHASHSEED` ergibt dieselbe Liste.
- **rasterio ohne AWS-Sitzung (M1), genau so:**
  - `backend/tests/conftest.py` setzt beim Import `rasterio.session.boto3 = None`.
  - rasterio prüft `boto3` nur einmal beim Import und merkt sich das Ergebnis in genau diesem Namen. `Session.aws_or_dummy` (`rasterio/session.py`) baut eine `AWSSession` nur, wenn er auf ein Modul zeigt. Sonst nimmt rasterio seinen eigenen Weg für ein fehlendes `boto3`, `DummySession`, wie im Image.
  - `sys.modules`, `boto3` und `botocore` bleiben unberührt. `moto` patcht `botocore`, der Client des Objektspeichers nutzt nur `botocore`, und `earthx/objectstore` importiert rasterio nicht.
  - **Beleg, dass die `moto`-Tests dasselbe prüfen:**
    - Die 735 Tests der Dateien, die `moto` oder den Objektspeicher nutzen, liefen mit und ohne die Zeile:
      - `tests/earthx/objectstore/`
      - `jobs/test_cleanup.py`, `test_worker.py`, `test_startup.py`
      - `processing/test_import_is_pure.py`
      - `api/test_result_zip_route.py`, `test_result_zip_files.py`, `test_result_tiles.py`, `test_bundle_route.py`
      - `test_objectstore_boundary.py`
    - Ergebnis: dieselben Kennungen, dasselbe Ergebnis je Test. Einzige Ausnahme ist der neue Wächtertest, der ohne die Zeile rot wird.
    - `objectstore/test_rasterio_session.py` hält beide Hälften fest:
      - Im Testprozess gibt es keine `AWSSession`.
      - `boto3` und `botocore` bleiben importierbar.
      - Der Store erreicht den `moto`-Bucket auch innerhalb von `rasterio.Env()`.
      - Ein frischer Prozess auf demselben Interpreter baut ohne die Zeile weiter eine `AWSSession` (Gegenprobe).
- **`pytest-xdist`:**
  - `pytest-xdist>=3.8` in `backend/requirements-dev.txt`.
  - Das Dev-Lock bekommt `pytest-xdist` 3.8.0 und `execnet` 2.1.2. Lock des Images und Lock des Smoke-Tests sind unverändert.
  - `addopts` in `pyproject.toml`: `-n auto --dist worksteal`.
- **Datenbank je Worker:**
  - `backend/tests/worker_database.py`, angestoßen über `pytest_configure`/`pytest_unconfigure` in `backend/tests/conftest.py`.
  - Unter `xdist` legt jeder Worker `<PGDATABASE>_gw<n>` leer an, mit PostGIS und den pgstac-Migrationen aus dem gepinnten `pypgstac`, und löscht sie am Ende.
  - Auf einem nicht lokalen Host und ohne Konfiguration wird keine angelegt; seriell bleibt alles wie vorher.
  - Tests: `integration/test_worker_database.py`.
- **Zeitabhängige Tests:** gefunden unter Last (4 Kopien von `test_worker.py` parallel) und in den `xdist`-Läufen.

| Test | Ursache | Abhilfe | Gegenprobe |
|---|---|---|---|
| `test_worker.py::TestShutdown::test_a_stopped_supervisor_ends_its_children_and_gives_the_runs_back` (der Fehlschlag aus der anderen Session, hier 1 von 20 Läufen) | Ein Lauf steht ab dem Abholen auf `running`, das Kind startet der Slot erst danach. `len(children) == 2` kam zu früh. | Warten, bis beide Kinder laufen (`_wait_for_children`) | — |
| `test_worker.py`, zwei Tests zu fremdem Besitz | dieselbe Ursache: „kein Kind“ war wahr, bevor das Kind lief; die Tests prüften dann nichts | ebenso | — |
| `test_worker.py::…::test_an_upload_longer_than_the_lease_does_not_lose_the_run` | 0,7 s zwischen Heartbeat und Lease | Lease 3 s, Upload 3,5 s: 2,7 s Spielraum, Upload weiter länger als die Lease | ohne Erneuerung während des Uploads rot |
| `test_worker.py::…::test_a_supervisor_that_is_killed_…` | Der Nachfolger hatte ohne Grund eine Lease von 1 s | Nachfolger mit den üblichen 3 s; die ablaufende Lease (des getöteten, 1 s) bleibt | — |
| `api/test_mosaic_item_fetches.py`, 2 Tests | „gleichzeitig“ hing an 30 ms Verzögerung; ohne Item-Cache holte eine späte Kachel neu | Die Quelle antwortet erst, wenn jede Kachel bei `ItemFetches.get` war | ohne Bündelung in `ItemFetches` rot |
| `gateway/test_gdal_tile_cache.py`, 2 Tests | Der `/vsicurl/`-Cache ist prozessweit; unter `xdist` laufen davor wechselnde Tests im selben Worker | Lesen in einem frischen `spawn`-Prozess wie beim `tiler`; der Server zählt vor dem Senden | mit dem Basisprofil rot |

Unter derselben Last wie beim Fehlschlag liefen danach 20 von 20 Läufen von `test_worker.py` grün.

- **Doku:**
  - Nachtrag in `adr/0002` §6.
  - Zwei Zeilen im Entscheidungslog: die Umsetzung, und Frage 4 als Hinweis.
  - Das Backlog bleibt unverändert, es pflegt der Planungs-Chat (Otto, 26.10.2026).

### 16.2 Messung nachher

Session wie in §8.1, Stand nach dem Merge von `main` (1e961e0). Die Zahl der Tests: `main` 6026, dieser Branch 6037 (+4 rasterio, +7 Datenbank je Worker).

| Lauf | Wo | Tests | Wandzeit |
|---|---|---|---|
| vorher, seriell | Session (`main` 459358e) | 5931 / 8 übersprungen | 989–1009 s |
| nachher, `xdist` Lauf 1 | Session | 6029 / 8 | **283 s** |
| nachher, `xdist` Lauf 2 | Session | 6029 / 8 | **285 s** |
| nachher, `xdist` Lauf 3 | Session | 6029 / 8 | **293 s** |
| nachher, seriell `-n 0` | Session | 6029 / 8 | 888 s |
| vorher | CI, `main` Lauf 806 (13:36) | 5939 | Schritt `pytest` 9:24 min |
| vorher | CI, `main` 1e961e0 (15:42) | 6026 | Schritt `pytest` 14:26 min |
| nachher | CI, PR, erster Lauf (15:40) | 6037 | Schritt `pytest` 4:10 min (Job 5:00) |
| nachher | CI, PR nach Merge von `main` (16:13) | 6037 | Schritt `pytest` 5:41 min (Job 6:35) |

- Speicherspitze des Rechners in den drei `xdist`-Läufen: 5,7 von 15 GB. Danach war keine Datenbank `…_gw<n>` übrig.
- Die CI-Runner schwanken stark: `main` brauchte heute 9:24 bis 14:26 min, am 24.10. waren es 13,2 min. Zur selben Uhrzeit (15:40/15:42) lagen PR und `main` bei 4:10 und 14:26 min.
- Die längste Einzeldauer bleibt `test_memory_8192` mit rund 61 s (Aufbau 13 s, Aufruf 48 s).
