# M4-08a — Queue und Worker-Hülle in `jobs`: Plan

**Aufgabe:** M4-08a aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 07.10.2026 freigegeben:** F1–F7 je Option 1, außer
**F4 Option 3**; K1–K6 angenommen. Dazu Auflagen zu F2, F4 und zum Speicher (§8,
„Antworten“). Umsetzung in PR #124.
**Ort im Repo:** `docs/plans/m4-08a-jobs-queue.md`
**Grundlagen:** `adr/0013` §5, §6, §8, §9, §10, §10a; `adr/0015` §7, §8,
§12 Punkt 9, §13, §14a (F13); `adr/0014` §4.4–§4.7, §5.5, §7.2, §9, §15b;
`plans/m4-processing-kern.md` §1.1 (Q4, Q8–Q11), §1.1b (R1, R2), §1.2, §1.3;
`plans/m4-06-objectstore.md` §3.5; `plans/m4-07a-processing-kern.md` §9.6;
`KLAERUNGEN.md` B8, B9 (Nachträge 02.10. und 05.10.2026);
`architekturplan.md` 3.1, 7.5; Log-Zeile vom 06.10.2026 zu `VmHWM`.

---

## 1. Ergebnis in drei Sätzen

Der Dienst `worker` holt Läufe aus drei neuen Tabellen in Postgres, mit einem
globalen Deckel von 4 und einer Grenze von 2 je Quell-Host aus einer Zeile der
Datenbank, und rechnet jeden Lauf in einem frisch gestarteten Kindprozess
(`spawn`), der nur `processing` kennt. Der Aufseher hält die Lease, schreibt
Fortschritt mit `NOTIFY`, bricht ab, wiederholt nur vorübergehende Fehler,
lädt das Ergebnis über `objectstore` unter `results/{result_id}/` hoch,
schließt nur mit der eigenen Versuchsnummer ab und räumt stündlich erst
Objekte, dann Zeilen auf. `api` bekommt eine Nahtstelle zum Einreihen, Lesen
und Verwerfen (`jobs/submit.py`), die M4-08b nur noch an Routen hängt.

---

## 2. Stand vor dieser Aufgabe (gelesen, 07.10.2026, `main` nach PR #122)

- **Ausgangslage grün:** `pytest` aus der Repo-Wurzel 2580 bestanden (mit
  Postgres der Sitzung), `ruff check backend` sauber, `lint-imports`
  14 Verträge gehalten (1 ignorierter Import).
- **Abhängigkeiten erfüllt:** M4-06 (#119, `earthx.objectstore`) und M4-07a
  (#120, `processing.run`, `worker_environment`, `cache_key`, `estimate`) sind
  gemergt.
- **`backend/earthx/jobs/`:** `__init__.py` (nur Docstring), `main.py`: FastAPI
  mit `/health`; der `lifespan` öffnet seit M4-06 den Objektspeicher und
  startet ohne die Regel `results/` nicht. Kein Datenbankzugang.
- **`docker-compose.yml`, Dienst `worker`:** keine `PG*`-Variablen, hängt nicht
  an `catalog-load` (das die Migrationen anwendet). Healthcheck `curl /health`.
- **`processing`:**
  - `run(recipe, *, workdir, progress, operators=REGISTRY) -> RunResult`;
    `progress(done, total)` je Block, Abbruch durch `RunCancelled` aus dem
    Rückruf; bei jedem Fehler räumt `run` seine Dateien weg.
  - `worker_environment()` ist ein Kontextmanager und verlangt den Hauptthread.
  - `cache_key(recipe)` gibt `None`, wenn eine Eingabe keine Fassung trägt
    (Q11); `estimate(recipe, operators).seconds` ist die Kostenschätzung.
  - Die Allowlist baut `processing` selbst aus `recipe.hrefs()` über
    `readers.read_access_for` (B9).
  - Fehlerklassen in `processing/errors.py`; **keine** Zuordnung zu „wiederholen
    ja/nein“. GDAL-Fehler kommen als `RasterioIOError`, Fehler der Quelle im
    Zarr-Pfad als `gateway`-Klassen (`UpstreamTimeout`, `UpstreamError`).
- **Verträge:** `no-database-in-worker-core` hat noch `earthx.jobs` und
  `earthx.processing` als Quelle und verbietet nur `psycopg`
  (`test_module_boundaries.py` prüft `{"jobs", "processing"}`). Vertrag `jobs`:
  nur `processing` und `objectstore`. `jobs` und `processing` dürfen
  `gateway` nicht importieren, und `urllib` ist ihnen über
  `http-only-in-gateway` verboten.
- **Migrationen:** `catalog/migrations/002`–`005`; der Läufer in
  `catalog/schema.py`, angewandt von `catalog.load` (compose-Dienst
  `catalog-load`). `tests/integration/conftest.py` führt `SHIPPED_TABLES`.
- **Datenbank der Sitzung und der CI:** PostgreSQL 16, Rolle mit
  Superuser-Recht, `transaction_isolation = read committed`.

---

## 3. Umsetzung

### 3.1 Migration `catalog/migrations/006_jobs.sql` (`adr/0013` §5.1, §6.3)

Die vier Tabellen aus §5.1, `public.`-qualifiziert wie 002–005, mit dem
Kommentar, dass sie `jobs` gehören und nur `jobs` sie mit SQL anfasst:

- `earthx_recipe`, `earthx_job_limits`, `earthx_run`, `earthx_job` wie in der
  Skizze, alle Fremdschlüssel `ON DELETE RESTRICT`, **ein Index auf jedem
  Fremdschlüssel** (`earthx_run.recipe_id`, `earthx_job.run_id`,
  `earthx_job.recipe_id`), dazu die Teilindizes für Abholen, Lease, aktive
  und fertige Läufe.
- `INSERT INTO earthx_job_limits VALUES (true, 4, 2)` — Deckel und Grenze je
  Host als Zeile (F4 aus `adr/0013`).
- **Zwei Spalten mehr als die Skizze** (Kleinentscheidung K1):
  - `max_seconds int NOT NULL` — Laufzeitdeckel max(2 × Schätzung, 600 s),
    berechnet beim Einreihen (§5.6). So braucht der Aufseher die Schätzung
    und damit `processing` nicht (K3).
  - `result jsonb` — was das Kind über das Ergebnis meldet (`properties`,
    `scaling`, `blocks`, `valid_pixels`, `engine`, Größe in Bytes); das
    Ergebnisdokument von M4-08b liest es von dort. Keine `href`, keine AOI.
- `tests/integration/conftest.py`: die vier Tabellen in `SHIPPED_TABLES`.

### 3.2 Verträge (`adr/0013` §6.1, F2, R2)

- `no-database-in-worker-core`: Quelle nur `earthx.processing`; verboten
  `psycopg`, `psycopg_pool`, `asyncpg`; ohne `allow_indirect_imports`. Name
  ergänzt um „M4 Q4“.
- `no-object-store-in-worker-core` bleibt, wie M4-06 ihn gesetzt hat (R2).
- Vertrag `jobs` bleibt („jobs import only processing and objectstore“).
- `test_module_boundaries.py`: `test_the_worker_core_reaches_no_database` prüft
  `{"processing"}` und alle drei Treiber.
- `architekturplan.md` 3.1, Zeile `jobs`: „Queue, Aufseher und Kindprozesse der
  Worker, Fortschritt, Abbruch, Ablauf, Ergebnisse | `processing`,
  `objectstore`; psycopg (Q4, `adr/0013`)“ — als Nachtrag mit Datum, der
  Originaltext bleibt.

### 3.3 Nahtstelle für `api`: `jobs/submit.py` (`JobRunner` aus 7.5)

`api` reiht über `jobs` ein und liest über `jobs` (`adr/0013` §5). Synchron mit
`psycopg`; die Verbindung gibt der Aufrufer. Die Funktionen:

- `submit(conn, recipe) -> str` — in **einer** Transaktion nach §5.1
  „Annahme“:
  1. Rezeptzeile (`recipe.recipe_id`, Körper als JSON).
  2. Treffer: fertiger Lauf mit gleichem `cache_key`, `cacheable` und
     `expires_at ≥ now() + 24 h` → Job darauf, fertig.
  3. Sonst `INSERT … ON CONFLICT (cache_key) WHERE status IN
     ('accepted','running') DO NOTHING`, bei Konflikt den aktiven Lauf lesen.
     `cacheable = cache_key(recipe) is not None`; ohne Fassung ist der
     Schlüssel derselbe Hash ohne die Prüfung auf Fassung (Kleinentscheidung
     K2), damit gleichzeitige gleiche Aufträge sich trotzdem anhängen (§5.1).
  4. Jobzeile mit neuer `jobID` (`secrets.token_urlsafe(16)`), `NOTIFY
     earthx_jobs_wake`.
  - `hosts` aus `read_access_for(recipe.hrefs()).policy.allowed_hosts`
    über eine kleine Funktion in `processing` (K2); `max_seconds` aus
    `processing.estimate` (K1).
- `job_status(conn, job_id) -> JobStatus | None` — Status (OGC-Werte; ein
  verworfener Job liest `dismissed`, auch wenn der Lauf weiterrechnet),
  `progress`, Zeiten, `error_kind`, `result_id`, `result`, `expires_at`.
  `None` für eine unbekannte oder falsch geformte Kennung. **Nur lesend.**
- `dismiss(conn, job_id) -> JobStatus | None` — §5.5: setzt `dismissed`; hängt
  kein anderer nicht verworfener Job am Lauf, wird ein wartender Lauf sofort
  `dismissed`, ein laufender bekommt `cancel_requested` und einen Weckruf. Für
  einen fertigen Job siehe F5.

`submit.py` importiert `processing`; der Aufseher importiert `submit.py`
nicht (K3).

### 3.4 Aufseher: `jobs/worker.py` (`adr/0013` §5.2, §5.3, §5.5, §5.6, §5.7)

- **Ein Aufseher je Container** mit `WORKER_SLOTS` Slots (Vorgabe 2). Jeder Slot
  ist ein Thread mit eigener Verbindung; dazu eine `LISTEN`-Verbindung für
  `earthx_jobs_wake` und eine für Aufräumer und Lease-Prüfung. Vier
  Verbindungen je Container.
- **Abholen** nach §5.2: zwei Anweisungen in einer Transaktion,
  `pg_advisory_xact_lock(<fester Schlüssel>)` **in einer eigenen Anweisung**
  vor dem Zählen, Isolationsstufe ausdrücklich `READ COMMITTED`. Deckel und
  Grenze je Host aus `earthx_job_limits`. Nichts zu tun → warten auf den
  Weckruf, spätestens nach 5 s erneut.
- **Je Lauf:** frischer Arbeitsordner unter `WORKER_WORKDIR`
  (`<tmp>/earthx-runs/<run_id>-<attempt>`), `recipe.json` hinein, Kind über
  `multiprocessing.get_context("spawn")` mit einer `Pipe`; nie eine globale
  Startmethode.
- **Slot-Schleife** liest die Pipe mit 1 s Takt:
  - Fortschritt: höchstens 1 Meldung je Sekunde und Lauf, außer bei
    Statuswechsel; `UPDATE … SET progress … RETURNING cancel_requested` und
    `pg_notify('earthx_job_progress', '{"run":…,"p":…,"s":…}')` in derselben
    Transaktion. Nur `run_id`, nie `jobID`, Hash oder AOI.
  - Heartbeat alle 15 s: `lease_until = now() + 60 s` nur mit eigener
    Versuchsnummer. Der Heartbeat hängt an der Slot-Schleife, nicht an einem
    eigenen Thread: Hängt der Slot, läuft die Lease ab (§5.6).
  - `cancel_requested` → Abbruchsignal in die Pipe; der Rückruf im Kind wirft
    `RunCancelled`. Endet das Kind nicht binnen 30 s: `SIGKILL`. Lauf
    `dismissed`, ohne Wiederholung.
  - Laufzeitdeckel `max_seconds` überschritten → `SIGKILL`, `failed` mit
    `runtime_exceeded`.
  - Exit des Kindes ohne Abschlussmeldung (Signal, OOM) → `failed` mit
    `child_crashed`, ohne Wiederholung.
- **Abschluss** (§5.6): nur `WHERE run_id = … AND attempt = :mein_versuch AND
  status = 'running'`. 0 Zeilen → das eigene Ergebnis gehört keinem Lauf; der
  Aufseher löscht den eigenen Upload sofort mit `delete_result` (Fehler
  ignoriert, die Bucket-Regel ist das Netz; K4). Erfolg setzt `successful`,
  `result_id`, `result`, `progress = 100`, `finished_at`, `expires_at =
  finished_at + 7 Tage`, dazu `NOTIFY` auf beiden Kanälen.
- **Wiederholung** nach der Tabelle in §5.6: nur `source_timeout`,
  `source_5xx`, `lease_lost` und nur, solange `attempt < max_attempts` (3);
  dann `accepted` mit `not_before = now() + 30 s × 2^(attempt−1) ± 20 %`.
  Alles andere `failed` mit `error_kind`.
- **Lease-Prüfung** alle 15 s: `running` mit `lease_until < now()` → wie
  `lease_lost` oben.
- **Herunterfahren** (SIGTERM über uvicorn, Auflage F2): kein neues Abholen;
  laufende Kinder werden beendet (`terminate`, nach 5 s `SIGKILL`); die Läufe
  des Aufsehers werden sofort wie `lease_lost` behandelt (K5): wieder
  `accepted`, wenn Versuche übrig sind, `Lease` freigegeben, statt 60 s auf
  den Ablauf zu warten. Der Aufseher löscht die Arbeitsordner seiner Läufe.
  Test: Aufseher mit laufendem Kind herunterfahren → Kind tot, Zeile
  `accepted` ohne `worker` und `lease_until`, Weckruf gesendet.
- **Mehrere Aufseher (Auflage F2):** Der Deckel hängt nur an der Zeile in
  `earthx_job_limits` und an der Sperre, nicht an der Zahl der Aufseher.
  Test: zwei Aufseher mit je 4 Slots gegen dieselbe Datenbank, Deckel 4,
  viele Läufe → nie mehr als 4 gleichzeitig (aus den Zeiten der Zeilen
  gerechnet, nicht durch Stichproben), und 4 werden erreicht.
- **Speicherabbruch des Kindes (Auflage):**
  - Das Kind liest bei jeder Fortschrittsmeldung `VmHWM` aus
    `/proc/self/status` (nicht `ru_maxrss`; Log 06.10.2026, M4-07a §9.3) und
    schickt es mit. Der Aufseher behält den letzten Wert und schreibt ihn bei
    jedem Ende ins Log (`peak_mb`). Die Zahl, an der M4-07a misst, ist
    500 MB je Kind für einen T2-Lauf über 8192² (F11, M4-07a §9.5); der
    Aufseher setzt keine eigene Grenze, er meldet nur.
  - **Erkannt** wird ein Speicherabbruch auf zwei Wegen, beide ohne
    Wiederholung (`adr/0013` §5.6, Zeile „Speicherabbruch“):
    1. Das Kind fängt `MemoryError` an seiner Grenze und meldet
       `("failed", "out_of_memory")`.
    2. Das Kind endet durch ein Signal, das der Aufseher nicht selbst
       geschickt hat (Exit-Code < 0, meist `SIGKILL` des OOM-Killers):
       `error_kind = child_crashed`. Ein Signal, das der Aufseher selbst
       schickte (Abbruch, Laufzeitdeckel, Herunterfahren), zählt als das,
       was ihn ausgelöst hat.
  - Der OOM-Killer ist von einem anderen `SIGKILL` nicht zu unterscheiden
    (`adr/0013` §5.6, Anmerkung); die Log-Zeile trägt deshalb `peak_mb` und
    Signalnummer, damit ein Mensch die Lesart prüfen kann.
  - Tests: ein Kind, das unter `RLIMIT_AS` mehr anfordert → `out_of_memory`;
    ein Kind, das sich selbst `SIGKILL` schickt → `child_crashed` mit dem
    letzten `peak_mb` im Log; ein echter Lauf über `jobs/child.py` meldet
    `peak_mb` > 0 und unter 500.
- **Logs:** `run_id`, Versuch, Status, `error_kind`, Sekunden, Spitze des
  Kindes in MB (`VmHWM`, vom Kind gemeldet; Log-Zeile vom 06.10.2026); nie
  Rezept, Hash, AOI, `href` oder `jobID`. Beim Start eine Zeile „worker
  started with 2 slots“.
- **Umgebung** (je Container, `adr/0013` §5.7): `WORKER_SLOTS` (2),
  `WORKER_LEASE_SECONDS` (60), `WORKER_HEARTBEAT_SECONDS` (15),
  `WORKER_POLL_SECONDS` (5), `WORKER_WORKDIR` (Temp-Verzeichnis). compose setzt
  keine davon; Tests setzen kurze Werte.
- **Kein `processing` im Aufseher:** `jobs/worker.py` importiert weder
  `earthx.processing` noch `submit.py` (K3). Der Aufseher braucht kein GDAL
  (§5.3); `fork`-Argumente fallen damit gar nicht erst an.

### 3.5 Kind: `jobs/child.py` und Zuordnung der Fehler

- `jobs/__init__.py` bleibt ohne Importe. `child.py` importiert nur
  `earthx.processing` und die Standardbibliothek.
- `main(workdir, conn)`: liest `recipe.json`, `parse_recipe(raw, REGISTRY)`,
  `with worker_environment(): run(recipe, workdir=…, progress=…)`. Der
  Rückruf schickt `("progress", done, total)` und prüft ohne Warten auf ein
  Abbruchsignal. Am Ende `("done", …)` mit der Beschreibung aus `RunResult`
  und `VmHWM`, bei einem Fehler `("failed", kind)`.
- **Zuordnung** (F1): `processing.failure_kind(exc) -> str`, gebaut in
  `readers` (darf `gateway` und rasterio sehen) und von `processing`
  weitergereicht — dasselbe Muster wie `AssetRejected`. Sie kennt:
  - `UpstreamTimeout` → `source_timeout`; `UpstreamError` mit Status ≥ 500 →
    `source_5xx`, `429` → `source_429`, sonst `source_4xx`;
    `UpstreamUnreachable` → `source_unreachable`;
  - `RasterioIOError` mit `HTTP response code: 5xx` → `source_5xx`, mit
    `CURL error: Operation timed out` → `source_timeout`, mit `HTTP response
    code: 4xx` (429 eigens) → `source_4xx`/`source_429`;
  - Abweisungen von `gateway` → `rejected`; `RecipeInvalid` und
    `UnknownOperator` → `recipe_invalid`; `ScalingMismatch`,
    `GridMismatch`, `AoiOutsideInputs`, `UnsupportedRecipe` → eigener Name;
  - alles andere → `unknown`.
  Wiederholt wird nur, was §5.6 freigibt (oben). `error_kind` ist immer einer
  dieser Namen, nie ein Text.

### 3.6 Ergebnis und Cache (`adr/0015` §8, Q11)

- Upload nach dem Ende des Kindes, im Aufseher: `new_result_id()` je Versuch,
  `upload_result` für `result.tif` und `mask.tif` (F4 Option 3, wie M3-18,
  M4-07a F9). `mask.tif` kommt als Name in `objectstore.RESULT_NAMES`
  (`image/tiff; application=geotiff`). `recipe.json` liegt **nicht** im
  Speicher: `api` erzeugt sie in M4-08b je Job aus dessen eigenem Rezept, damit
  kein Auftrag die `recipe_id` eines anderen sieht.
- Ein Cache-Eintrag entsteht, indem ein `cacheable` Lauf `successful` wird;
  ein Treffer gilt nur mit mindestens 24 h Restlaufzeit (§3.3, Schritt 2).
  Lauf ohne Fassung: Ergebnis wird gespeichert, 7 Tage, nie Treffer
  (`adr/0015` §8.2).

### 3.7 Aufräumer (`adr/0013` §5.8, `adr/0015` §7.1, §7.2 A1, F13)

- Stündlich in jedem Aufseher, erster Lauf 5 min nach dem Start; nur einer
  arbeitet, geschützt durch `pg_try_advisory_xact_lock` in der Transaktion
  des Stapels.
- Stapel von 5000: abgelaufene Läufe (`expires_at < now()`) lesen → erst
  `delete_result` für jede `result_id`, dann ihre Jobs, dann die Läufe, dann
  Rezepte ohne Job und ohne Lauf. Ein Fehler des Objektspeichers lässt die
  Zeilen des Stapels stehen (nächste Stunde erneut).
- **F13:** Die Frist eines Rezepts ist abgeleitet: Es lebt, solange ein Job
  oder Lauf darauf verweist (§5.8). Ändern kann sie nur `submit` (neuer Lauf
  oder Treffer) und der Abschluss eines Laufs; `job_status` und alles Lesende
  schreiben nichts (Test, §3.9).

### 3.8 Start: `jobs/main.py`, compose

- Der `lifespan` öffnet wie bisher den Objektspeicher, dann die Verbindungen
  und startet den Aufseher (F2); beim Herunterfahren stoppt er ihn (§3.4).
- `/health`: `200`, wenn der Aufseher in den letzten 30 s die Datenbank
  erreicht hat, sonst `503` (§5.3).
- `docker-compose.yml`, Dienst `worker`: `PG*` wie `api`; `depends_on`
  zusätzlich `catalog-load: service_completed_successfully` (Migration 006).
  Keine `WORKER_*`-Variable.

### 3.9 Tests

Neu unter `backend/tests/earthx/jobs/`, gegen echtes Postgres in CI und
Sitzung (`adr/0002` §2), ohne Netz:

- **Datenbank je Testsitzung** (F6): eine frische Wegwerf-Datenbank
  `earthx_jobs_<zufall>` mit den Migrationen; Mehrprozess-Tests brauchen
  festgeschriebene Zeilen, die Rollback-Fixture der T-C-Tests trägt das nicht.
  Dieselbe Prüfung auf einen lokalen Host wie in `tests/integration`.
- Kinder in Mechanik-Tests mit einem Testziel (schläft, meldet Fortschritt,
  stirbt, hängt); ein Ende-zu-Ende-Test mit `jobs/child.py` über ein Testziel,
  das die Nähte aus `tests/earthx/processing/sources.py` setzt und dann
  `child.main` ruft.

### 3.10 Doku und Log

- `architekturplan.md` 3.1 (§3.2), `backend/earthx/catalog/migrations/README.md`
  (006), `README.md` (Start von `worker`: Datenbank, Migration, Slots).
- `ENTSCHEIDUNGSLOG.md`: Freigabe, Umsetzung, offene Punkte aus §5; Stand in
  `m4-processing-kern.md` §3.
- Kein neues ADR: alles Grundsätzliche steht in `adr/0013`; die Abweichungen
  K1–K5 stehen hier und im Log.

---

## 4. Abnahme: `adr/0013` §8 und `adr/0015` §12

| Punkt | Test |
|---|---|
| 1 Deckel | 8 Prozesse, Deckel 3, Beobachter zählt nie mehr als 3 `running`. **Gegentest deterministisch:** Variante mit der Sperre in derselben Anweisung; Verbindung B hält Sperre und Abholung offen, A startet (Schnappschuss vor der Sperre), B schreibt fest → A zählt veraltet, Deckel 1 wird mit 2 überschritten |
| 2 Grenze je Host | 3 Läufe auf Host a, 1 auf b, Grenze 2 → a höchstens 2, b läuft sofort |
| 3 Abschirmung | Versuch 1 abgeholt, Lease abgelaufen, neu eingereiht und abgeholt → Abschluss von Versuch 1 ändert 0 Zeilen, sein Upload wird gelöscht |
| 4 Toter Worker | Kind mit `SIGKILL` → `failed`/`child_crashed`, Versuch bleibt 1; Aufseher-Prozess mit `SIGKILL` → nach Lease (2 s im Test) neu eingereiht |
| 5 Gleiche Aufträge | 8 gleichzeitige `submit` → 1 Lauf, 8 Jobs; `dismiss` eines Jobs lässt den Lauf weiterlaufen; der letzte bricht ab |
| 7 Abbruch | wartend sofort `dismissed`; laufend im nächsten Block; hängendes Kind nach der Frist (im Test kurz) mit `SIGKILL` |
| 8 Ablauf | abgelaufene Zeilen und Objekte (moto) verschwinden, nicht abgelaufene bleiben; Reihenfolge Objekte vor Zeilen; Treffer mit 23 h Rest gilt nicht, mit 25 h schon |
| 10 Kettenregel | `lint-imports`; `test_module_boundaries.py` angepasst |
| 11 Startmethode | Kind meldet `get_start_method() == "spawn"`; `psycopg`, `psycopg_pool`, `asyncpg`, `earthx.jobs.worker`, `earthx.objectstore` nicht in `sys.modules` (`boto3` vorher ausgeblendet wie in M4-07a §9.6); Gegenprobe mit `fork` sieht `psycopg` |
| 13 Wiederholung | je Zeile der Tabelle §5.6 eine Prüfung; GDAL-Texte gegen einen lokalen `http.server` mit `503`, `404` und ohne Antwort (Muster M10); unbekannter Fehler scheitert ohne Wiederholung; Backoff in den Grenzen ±20 % |
| `adr/0015` §12 Punkt 9 | `submit` (Lauf, Treffer) und Abschluss ändern die Lebensdauer eines Rezepts; `job_status` über alle Zustände schreibt nichts (`xmin` der Zeilen unverändert) |
| Auflage F2 | zwei Aufseher mit je 4 Slots gegen dieselbe Datenbank, Deckel 4 nie überschritten und erreicht; Herunterfahren beendet die Kinder und gibt die Leases frei |
| Auflage Speicher | `MemoryError` im Kind → `out_of_memory`; Signal von außen → `child_crashed`, beide ohne Wiederholung, `peak_mb` im Log |
| zusätzlich | Fortschritt: `NOTIFY` bei Commit, keins bei Rollback, Drosselung; Logs ohne Hash, AOI, `href`, `jobID`; `/health` 503 ohne Datenbank; Ende-zu-Ende über `child.py` mit Upload in moto |

Punkt 6, 9 und 12 gehören zu M4-08b (Routen und SSE).

---

## 5. Nicht in dieser Aufgabe

- Routen, Statusdokument in OGC-Form, signierte Links, SSE und die eine
  `LISTEN`-Verbindung je `api`-Prozess: M4-08b.
- Annahme in `api` (Auftrag → Rezept, Fassung, Host-Prüfung): M4-07b.
- **Kalibrieren des Laufzeitdeckels an echten Läufen** (§5.6): `gateway`
  erreicht die Quellen aus der Sitzung nicht (§1.2 des M4-Plans). Startwert
  max(2 × Schätzung, 600 s); Log-Zeile „offen“.
- **Zähler der Verbindungen je Lauf im Test-Gateway** (§5.7 „Grenze der
  Grenze“): steht nicht in §8; Log-Zeile „offen“, gehört zum Egress-Proxy (M6).
- Fairness, Prioritäten, Pools außer `default` (§5.9); Quad-Pol-Operator
  (§6.2).

---

## 6. Umfang und Commits

Geschätzt rund 2 300 geänderte Zeilen, davon rund 1 300 Tests — weit über dem
Richtwert von 400 (F7). Geplante Commits, je eine Sache:

1. Migration 006 und `SHIPPED_TABLES`.
2. Vertrag `no-database-in-worker-core` nur für `processing`; Grenztest; 3.1.
3. `processing`: `failure_kind` (über `readers`), Schlüssel ohne Fassung,
   Hosts eines Rezepts — mit Tests.
4. `jobs/submit.py` mit Tests (Punkte 5, 7 wartend, §12 Punkt 9).
5. `jobs/child.py` mit Tests (Punkt 11).
6. `jobs/worker.py`: Abholen, Slots, Lease, Abbruch, Wiederholung, Abschluss,
   Upload, mit Tests (Punkte 1–4, 7, 13).
7. Aufräumer mit Tests (Punkt 8).
8. `jobs/main.py`, `/health`, compose.
9. Doku und Log.

---

## 7. Risiken

- **Nebenläufigkeit:** Die Tests mit mehreren Prozessen sind zeitabhängig.
  Wo es geht, steuern Sperren und Ereignisse die Reihenfolge statt
  `sleep`; Zeitgrenzen großzügig, damit ein langsamer Runner nicht flackert.
- **compose-topology nur in der CI** (kein Docker-Daemon in der Sitzung). Der
  Worker wird erst gesund, wenn Datenbank, Migration 006 und Objektspeicher
  stehen; ein Fehler zeigt sich dort, dann folgt ein Fix-Commit. `.github/`
  ändert sich nicht.
- **`spawn` unter uvicorn:** Das Kind importiert den Hauptmodul des Elternteils
  als `__mp_main__` (bei compose das Skript `uvicorn`). Punkt 11 prüft
  `sys.modules` deshalb auch in einem Kind, das aus einem mit uvicorn
  gestarteten Aufseher kommt.
- **GDAL-Texte** hängen an der Version (gemessen 3.12.2); der Test aus Punkt 13
  bricht bei einer Änderung, das ist gewollt.
- **Startkosten** rund 1,2 s und rund 160 MB je Kind (`adr/0013` M9, M4-07a
  §9.1); in Tests mit vielen Kindern merklich, deshalb Mechanik-Tests mit
  schlanken Testzielen.

---

## 8. Fragen an Otto

**F1 — Wo werden Fehler zu `error_kind` (§3.5)?**
1. `failure_kind` in `readers` (darf `gateway` und rasterio sehen), von
   `processing` weitergereicht; das Kind ruft sie an seiner Grenze. Keine
   Vertragsänderung, Muster wie `AssetRejected` **(Empfehlung)**
2. Im Kind über Klassennamen (`type(exc).__mro__`), ohne Import; bricht still,
   wenn eine Klasse umbenannt wird
3. `processing.run` übersetzt selbst in eigene Fehlerklassen; ändert den Kern
   aus M4-07a an jeder Lesestelle

**F2 — Wo läuft der Aufseher (§3.8, `adr/0013` §6.2 „Neben `/health`“)?**
1. Im Prozess der FastAPI-App, gestartet im `lifespan`, Slots als Threads;
   compose-Befehl bleibt, `/health` sieht den Aufseher direkt
   **(Empfehlung)**
2. Eigener Prozess `python -m earthx.jobs.worker`; `/health` braucht dann
   einen eigenen kleinen HTTP-Server, der compose-Befehl ändert sich

**F3 — Nahtstelle zum Einreihen (§3.3)?**
1. In M4-08a: `jobs/submit.py` mit `submit`, `job_status`, `dismiss`, getestet
   gegen Postgres; M4-08b hängt nur Routen daran. Punkte 5 und 7 aus §8 sind
   so hier prüfbar **(Empfehlung)**
2. In M4-08b; M4-08a reiht in Tests mit rohem SQL ein

**F4 — Was liegt neben dem Ergebnis unter `results/{result_id}/` (§3.6)?**
1. Nur `result.tif`. `recipe.json`, `citation.bib`, `attribution.txt` kommen,
   wenn ihr Inhalt für Jobs feststeht (M4-11, M4-14) **(Empfehlung)**
2. Dazu `recipe.json`, **ohne** `recipe_id`: Ein Cache-Treffer gibt dasselbe
   Präfix an einen zweiten Auftraggeber, der sonst die `recipe_id` des ersten
   sähe
3. Dazu `mask.tif` (braucht einen Eintrag in `objectstore.RESULT_NAMES`)

**F5 — `dismiss` eines fertigen Jobs (`adr/0015` §13)?**
1. Der Job zählt als verworfen (M4-08b antwortet dann `404`); das Ergebnis
   bleibt bis zum Ablauf, weil es Treffer anderer Jobs sein kann
   **(Empfehlung)**
2. Ergebnis sofort löschen, wenn kein anderer Job am Lauf hängt; der Lauf
   wird dann nicht mehr `cacheable`

**F6 — Datenbank der Tests (§3.9)?**
1. Je Testsitzung eine frische Wegwerf-Datenbank mit den Migrationen, am Ende
   gelöscht; braucht `CREATEDB` (Sitzung und CI haben es) **(Empfehlung)**
2. Die Tabellen in der Datenbank der Sitzung, festgeschrieben und vor und
   nach jedem Test geleert

**F7 — Größe des PR (§6)?**
1. Ein PR mit neun thematischen Commits, rund 2 300 Zeilen, gut die Hälfte
   Tests; die Sitzung ist an einen Branch gebunden **(Empfehlung)**
2. Teilen: M4-08a-1 (Migration, Verträge, `submit.py`, `processing`-Teil) und
   M4-08a-2 (Kind, Aufseher, Aufräumer, compose) als zwei Sitzungen

**Kleinentscheidungen** (gelten, wenn Otto nicht widerspricht):

- **K1** Zwei Spalten über die Skizze hinaus: `max_seconds` und `result`
  (§3.1).
- **K2** Drei kleine öffentliche Funktionen in `processing`: `failure_kind`
  (F1), ein Lauf-Schlüssel, der auch ohne Fassung entsteht (für das Anhängen
  gleichzeitiger Aufträge; nie Cache-Schlüssel), und die Hosts eines Rezepts.
- **K3** Der Aufseher importiert `processing` nicht (Test: `import
  earthx.jobs.worker` lädt weder `earthx.processing` noch `rasterio`).
- **K4** Ein abgeschirmter Versuch löscht seinen Upload sofort; die
  Bucket-Regel bleibt das Netz.
- **K5** Beim Herunterfahren gelten die eigenen Läufe sofort als
  `lease_lost` (Wiederholung, wenn Versuche übrig sind).
- **K6** Der Arbeitsordner-Stamm des Containers wird beim Start geleert
  (Reste nach einem Absturz).
- **K7** (aus der Auflage zum Speicher) Neuer `error_kind` `out_of_memory`
  für ein `MemoryError` im Kind; `child_crashed` bleibt für Signale. Beide
  ohne Wiederholung.

---

**Antworten (Otto, 07.10.2026):** F1 (1), F2 (1), F3 (1), **F4 (3)**, F5 (1),
F6 (1), F7 (1); K1–K6 angenommen. Auflagen:

- **F4:** Neben dem Ergebnis liegen `result.tif` und `mask.tif` (wie M3-18,
  Auflage F9 aus M4-07a). `recipe.json` liegt nicht im Speicher; `api` erzeugt
  sie in M4-08b je Job aus dessen eigenem Rezept, damit kein Auftrag die
  `recipe_id` eines anderen sieht. Vermerk bei M4-08b in
  `m4-processing-kern.md`.
- **F2:** Der Deckel hält unabhängig von der Zahl der Aufseher (Test mit zwei
  Aufsehern gegen dieselbe Datenbank). Beim Herunterfahren werden laufende
  Kinder beendet und ihre Leases freigegeben (Test).
- **Speicher:** Erkennung eines Speicherabbruchs des Kindes und
  `error_kind` ohne Wiederholung stehen in §3.4; Messungen mit `VmHWM`
  (Log 06.10. und 07.10.2026, M4-07a).
- **Offen im Log** (wie vorgeschlagen, §5): Laufzeitdeckel an echten Läufen
  kalibrieren; Verbindungen je Lauf zählen.

---

## 9. Prüfanleitung für Otto (nach dem Merge, PowerShell)

```powershell
docker compose up -d --build
docker compose ps                  # worker: healthy
docker compose logs worker         # erwartet: "worker started with 2 slots", keine Fehler
```

`.env` bleibt, wie sie ist. Die Migration 006 wendet `catalog-load` beim Start
an.
