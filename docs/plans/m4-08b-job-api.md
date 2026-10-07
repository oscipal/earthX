# M4-08b — Job-API (OGC-Form), Ergebnis-Links, SSE: Plan

**Aufgabe:** M4-08b aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 07.10.2026 freigegeben:** F1–F3 und F5–F8 je
Option 1, **F4 Option 2**; K1–K10 angenommen. Wo §3 und §8 („Antworten“)
sich widersprechen, gilt §8. Umsetzung in PR #128.
**Ort im Repo:** `docs/plans/m4-08b-job-api.md`
**Grundlagen:** `adr/0014` §4.1, §4.7, §9, §10.1, §15b; `adr/0013` §5.4, §5.5,
§5.8, §8 (Punkte 6, 9, 12), §9; `adr/0015` §6, §7.1, §8.1, §13, §14 (F4–F6),
§14a (F13); `plans/m4-processing-kern.md` §1.1 (Q8, Q9, Q10), §1.2, M4-08b;
`plans/m4-07b-annahme.md` §4, §6, §8; `plans/m4-08a-jobs-queue.md` §3.3, §8
(F4, F5), §10; `architekturplan.md` 3.1, 7.5 (Z. 543); `KLAERUNGEN.md` B8, B9;
OGC API Processes 1.0, Commit `7a6bad0` (wie `adr/0014` §3.10).

---

## 1. Ergebnis in drei Sätzen

Der Dienst `api` bekommt unter einem eigenen Präfix die Job-Schnittstelle in der
Form von OGC API Processes 1.0: Landing Page, `/conformance`, API-Definition,
`/processes`, `/processes/recipe` mit dem Schema des Auftrags als Discriminated
Union über die Operatoren (je Datensatz filterbar), `POST
/processes/recipe/execution` nur asynchron, `GET`/`DELETE /jobs/{jobID}` und
`/jobs/{jobID}/results`. Die Ergebnis-Links zeigen auf `api` und antworten mit
`303` auf eine frisch signierte URL (`no-store`, 15 min, `410` am Ende der
Frist); `recipe.json` erzeugt `api` je Job aus dessen eigenem Rezept. Der
Fortschritt kommt per SSE aus genau einer `LISTEN`-Verbindung je `api`-Prozess,
beim Verbinden zuerst mit dem Stand der Zeile.

---

## 2. Stand vor dieser Aufgabe (gelesen, 07.10.2026, `main` nach PR #124)

- **Ausgangslage:** `pytest` aus der Repo-Wurzel, `ruff check backend` und
  `lint-imports` — Ergebnis im PR-Text.
- **Abhängigkeiten erfüllt:** M4-07b (#123) und M4-08a (#124) sind gemergt.
- **Annahme (M4-07b):** `api/intake.py::accept_order(raw, *, registry,
  operators, item_source, gateway) -> AcceptedOrder` (Rezept mit `recipe_id`,
  `cacheable`, `skipped_items`); Abweisung als `OrderRefused(status_code,
  detail, stage)` (`api/item_source.py`); `check_recipe_hosts(recipe,
  registry)` als Gegenprobe vor dem Einreihen. Routen gibt es keine. Die
  Item-Quelle (`build_item_source`) hängt bisher nur am `tiler`.
- **Nahtstelle zur Queue (M4-08a):** `jobs/submit.py` mit `submit(conn, recipe)
  -> job_id`, `job_status(conn, job_id) -> JobStatus | None` (nur lesend;
  `None` für unbekannt oder falsch geformt; ein verworfener Job liest
  `dismissed`), `dismiss(conn, job_id)`. Synchrones `psycopg`, die Verbindung
  gibt der Aufrufer. `JobStatus` trägt `recipe_id`, Status, `progress`, Zeiten,
  `expires_at`, `error_kind`, `result_id` und `result` (`properties`, `scaling`,
  `engine`, Größe; keine Adresse). Eine `run_id` gibt keine Funktion heraus.
- **Fortschritt:** Der Aufseher sendet `pg_notify('earthx_job_progress',
  '{"run":…,"p":…,"s":…}')` in der Transaktion der Zeile, gedrosselt auf 1/s
  je Lauf außer bei Statuswechseln (`jobs/queue.py::notify_progress`).
- **Objektspeicher (M4-06):** `objectstore.results.signed_download(store,
  result_id, name, *, not_after, filename)` signiert für den öffentlichen
  Endpunkt, 15 min, nie über `not_after`, und wirft `ResultExpiring` bei
  weniger als 60 s Rest. Unter `results/{result_id}/` liegen nur `result.tif`
  und `mask.tif` (M4-08a F4). compose gibt `api` schon `S3_*` mit dem
  Leseschlüssel; `api/main.py` öffnet den Speicher noch nicht.
- **Operatoren:** `REGISTRY` hält `reproject` (op_version 2); Band-Math kommt
  mit M4-09. `Step.params` ist im Modell ein freies Objekt; das Schema je
  Operator liefert `OperatorRegistry.params_schema`. `applicable(operator,
  config)` prüft Flags, Datenklasse und Lizenzstufe.
- **Kern:** `processing.core._check_scope` weist mehrere Items, mehrere Gruppen
  und `crop` erst im Kind ab (`UnsupportedRecipe`) — also nach dem Warten in
  der Queue.
- **Zugriffslog:** `RequestIdMiddleware` (`earthx/logging.py`) schreibt je
  Anfrage Methode, **Pfad**, Status und Dauer, ohne Query. Eine `jobID` im Pfad
  stünde damit im Log.
- **FastAPI 0.142** bringt SSE selbst mit (`fastapi.sse.EventSourceResponse`,
  `ServerSentEvent`), mit einem Kommentar `: ping` alle 15 s
  (`fastapi/sse.py` `_PING_INTERVAL = 15.0`) [P]. Das ist genau das
  Lebenszeichen aus `adr/0013` §5.4; keine neue Abhängigkeit.
- **OGC API Processes 1.0, Core** [P, Commit `7a6bad0`, `core/requirements/`]:
  - Landing Page mit Links `service-desc` oder `service-doc`, `conformance`,
    `processes` (`REQ_landingpage-success`).
  - Ausführung: Rumpf nach `execute.yaml` (`inputs`, `outputs`, `response`);
    nur asynchron → `201`, `Location`, Rumpf `statusInfo.yaml`
    (`REQ_process-execute-success-async`, `…-default-execution-mode`).
  - Eingaben „by reference“ (Link) und als „qualified value“ muss ein Server
    unterstützen (`REQ_process-execute-inputs`, `…-input-inline-object`).
  - `GET /jobs/{jobID}`: `200` mit `statusInfo`; unbekannt → `404`, Typ
    `…/no-such-job` (`REQ_job-success`, `REQ_job-exception-no-such-job`).
  - `GET /jobs/{jobID}/results`: läuft noch → `404`, Typ `…/result-not-ready`;
    gescheitert → ein Fehlercode, „that corresponds to the reason of the
    failure“, Rumpf `exception.yaml` (`REQ_job-results-exception-results-not-ready`,
    `REQ_job-results-failed`); fertig als Dokument → `200`, `results.yaml`.
  - `DELETE /jobs/{jobID}`: `200` mit `statusInfo`, Status `dismissed`
    (`REQ_job-dismiss-success`).
  - `GET /processes` hat einen Parameter `limit` (1–10000, Vorgabe 10,
    `REQ_process-list-limit-def`).

---

## 3. Umsetzung

### 3.1 Wo und unter welchem Präfix (F1, F2)

- **Dienst `api`** (`earthx.api.main`), nicht `tiler` (F2). `api` ist die
  HTTP-Schicht mit Datenbank, `gateway` und Registry; `tiler` bleibt für
  Kacheln und Zuschnitt. Die Item-Quelle baut `api` in seinem `lifespan` aus
  dem Gateway und dem Pool, die er schon hat (`build_item_source`).
- **Präfix `/processing`** (F1), außerhalb von `/stac` wie Coverage, AOI und
  Ortssuche. Pfade:

| Methode | Pfad | Antwort |
|---|---|---|
| GET | `/processing/` | Landing Page: Links `self`, `service-desc` (`/processing/api`), `conformance`, `processes`; Text: „follows the form of OGC API – Processes, no conformance claimed“ (F4) |
| GET | `/processing/api` | OpenAPI nur der Routen unter `/processing` |
| GET | `/processing/conformance` | `{"conformsTo": []}`: keine Klasse erklärt, auch nicht `json` oder `dismiss` (F4) |
| GET | `/processing/processes` | ein Prozess `recipe` (Zusammenfassung), `limit` angenommen |
| GET | `/processing/processes/recipe` | Prozessbeschreibung, Schema des Auftrags (§3.3); `?dataset=` filtert |
| POST | `/processing/processes/recipe/execution` | `201`, `Location`, `statusInfo` |
| GET | `/processing/jobs/{jobID}` | `statusInfo` |
| DELETE | `/processing/jobs/{jobID}` | `statusInfo` mit `dismissed` |
| GET | `/processing/jobs/{jobID}/results` | Ergebnisdokument mit Links (§3.5) |
| GET | `/processing/jobs/{jobID}/results/{name}` | `303` (`result.tif`, `mask.tif`) bzw. `200` (`recipe.json`) |
| GET | `/processing/jobs/{jobID}/events` | SSE (§3.6), kein Teil von OGC |

- Keine Job-Liste (`GET /jobs`), kein Callback, kein HTML (`adr/0014` F12).
- **Neue Module:** `api/processing_route.py` (Router, Antwortmodelle,
  Fehlerabbildung) und `api/job_events.py` (die eine `LISTEN`-Verbindung und
  das Verteilen). `api/main.py` hängt den Router ein und erweitert den
  `lifespan`.

### 3.2 Was der `lifespan` von `api` zusätzlich öffnet

- **Speicher:** `Store.from_environ()` mit dem Leseschlüssel von `api`; nur
  Signieren, keine Verbindung (`adr/0015` §3.2). Fehlt die Konfiguration,
  startet `api` nicht (F7).
- **Ein kleiner synchroner Pool** (`psycopg_pool.ConnectionPool`, 1–4
  Verbindungen, `READ COMMITTED`) für `jobs/submit.py`, das synchron ist. Die
  Routen rufen es über `run_in_threadpool`. Den asynchronen Such-Cache-Pool
  (`autocommit`) für die Queue umzubauen hieße, getesteten Code aus M4-08a
  umzuschreiben (K1).
- **Die Item-Quelle** aus `app.state.earthx_gateway` und dem Cache-Pool.
- **Der Verteiler** aus §3.6 als Aufgabe im Prozess; beim Herunterfahren
  beendet, die SSE-Verbindungen schließen.

### 3.3 Prozessbeschreibung und Schema (`adr/0014` §9, K8)

- **Ein Prozess `recipe`**, `version` = `RECIPE_VERSION`,
  `jobControlOptions: ["async-execute", "dismiss"]`,
  `outputTransmission: ["reference"]`.
- **Eingang** nach F3: genau ein Eingang `recipe`, dessen `schema` das Schema
  des Auftrags (`RecipeRequest`) ist, JSON Schema 2020-12.
  - `steps.items` ist ein `oneOf` mit einem Eintrag je registriertem Operator:
    `op` und `op_version` als `const`, `params` als Verweis auf das Schema des
    Operators unter `$defs` (`params_schema`). Dazu `discriminator:
    {propertyName: "op"}`, solange jeder Operator in genau einer Version
    registriert ist; sonst ohne (ein OpenAPI-Diskriminator braucht eindeutige
    Werte).
  - `?dataset=<id>`: nur Operatoren, für die `applicable(operator, config)`
    leer ist (ohne Parameter; Flags, die erst Parameter verlangen, prüft die
    Annahme). Unbekannter Datensatz → `400`. Ein Datensatz unter der
    Lizenzstufe *Processing* bekommt eine leere Liste, kein Fehler.
- **Ausgänge:** `result` (COG), `mask` (GeoTIFF), `recipe` (JSON), je mit
  `contentMediaType` aus `objectstore.RESULT_NAMES`.
- Das Schema entsteht beim Start aus `REGISTRY`, nie aus einer Anfrage; ein Test
  vergleicht es mit dem, was `parse_request` annimmt (ein gültiger Auftrag aus
  dem Schema wird angenommen, ein Operator, der dort fehlt, abgewiesen).

### 3.4 Ausführen: `POST /processing/processes/recipe/execution`

1. **Rumpf lesen**, höchstens 1 MiB (wie `MAX_UPLOAD_BYTES` der AOI-Datei,
   K2), sonst `413`. Kein Rumpf, kein JSON-Objekt → `400`.
2. **OGC-Hülle prüfen** (F3, F4): nur die Schlüssel `inputs`, `outputs`,
   `response`; `inputs` hat genau den Schlüssel `recipe`, dessen Wert ein
   Objekt ist. Eine Eingabe als Link (`href`) oder als `{"value": …}` →
   `400`; der Text sagt, dass Eingaben nur inline angenommen werden (F4,
   B8). Es folgt keine Anfrage an die Adresse. `response` fehlt oder
   ist `document`; `outputs` fehlt oder nennt nur bekannte Ausgänge mit
   `transmissionMode: reference`. Sonst `400`.
3. **Annahme:** `accept_order(<recipe als Bytes>, …)`; `OrderRefused` → Status
   und Text in einer Zeile, Rumpf im Format `exception.yaml` (`type`, `title`,
   `status`, `detail`).
4. **Gegenprobe:** `check_recipe_hosts(recipe, registry)` (M4-07b §3.3).
5. **Kann der Kern das?** `processing.check_scope(recipe)` — die heutige
   private Prüfung `_check_scope`, öffentlich (K3). `UnsupportedRecipe` →
   `422`, bevor der Auftrag in der Queue wartet und dann scheitert.
6. **Einreihen:** `submit(conn, recipe)` im Threadpool. `RecipeIdTaken` kann
   nicht vorkommen (`recipe_id` neu je Annahme) und wird zu `500` ohne Wert.
7. **Antwort `201`**, `Location: /processing/jobs/{jobID}`, `Cache-Control:
   no-store`, bei `Prefer: respond-async` zusätzlich `Preference-Applied:
   respond-async`. Rumpf: `statusInfo` (§3.7) und zusätzlich `skippedItems`,
   wenn die AOI Items nicht berührt (M4-07b §6: „Die Antwort muss das
   zeigen“). Ein Cache-Treffer antwortet ebenso `201`, schon mit
   `successful`.

Ohne `Prefer` und mit `Prefer: respond-sync` oder `wait` ebenso asynchron: Der
Prozess kennt nur `async-execute` (`REQ_process-execute-default-execution-mode`).

### 3.5 Status, Ergebnisse, Links, Abbruch

- **Gemeinsame Regel für jede Route mit `{jobID}`:** falsch geformt, unbekannt,
  verworfen oder **abgelaufen** (`expires_at ≤ now`, auch wenn der Aufräumer
  die Zeilen noch nicht gelöscht hat) → `404`, Typ `…/no-such-job`, ein
  einziger fester Text. So unterscheidet niemand „gab es nie“ von „ist
  abgelaufen“ oder „verworfen“. Ausnahme: die Links (unten), die nach F5 aus
  `adr/0015` `410` antworten.
- **`GET /jobs/{jobID}`:** `statusInfo` aus `job_status`. Liest nur
  (`adr/0015` F13).
- **`DELETE /jobs/{jobID}`:** `dismiss`; `200` mit `status: dismissed`. Danach
  `404` auf allen Routen dieses Jobs. **Fertiger Job** (`adr/0015` §13, im
  Plan-Schritt zu entscheiden): entschieden mit M4-08a F5 Option 1 — der Job
  zählt als verworfen, das Ergebnis bleibt bis zum Ablauf, weil es Treffer
  anderer Jobs sein kann. Hier ist nichts mehr offen; `dismiss` macht es schon
  so.
- **`GET /jobs/{jobID}/results`:**
  - `accepted`/`running` → `404`, Typ `…/result-not-ready`.
  - `failed` → Status nach `error_kind` (K4), Rumpf `exception.yaml` mit
    `type: urn:earthx:job-failed:<error_kind>`, festem englischem Titel je
    Art, nie einem Text aus der Ausnahme.
  - `successful` → `200`, Dokument nach `results.yaml`:
    `{"result": {"href": "/processing/jobs/{jobID}/results/result.tif",
    "type": …}, "mask": {…}, "recipe": {…}}`. Die Links zeigen auf `api`
    (`adr/0015` F4), nie auf den Speicher.
- **`GET /jobs/{jobID}/results/{name}`:**
  - `name` nicht in `{result.tif, mask.tif, recipe.json}` → `404`.
  - Job nicht `successful` → wie oben (`404`).
  - **`result.tif`, `mask.tif`:** `signed_download(store, result_id, name,
    not_after=expires_at, filename=…)` → `303 See Other`, `Location` = die
    signierte URL, `Cache-Control: no-store`, kein Rumpf. `ResultExpiring`
    (weniger als 60 s Rest) und `expires_at` vorbei → `410 Gone`, solange die
    Zeile noch da ist; danach `404`.
  - **`recipe.json`:** `200`, `application/json`, `Cache-Control: no-store`,
    `Content-Disposition: attachment` (§3.8). Inhalt: das eigene Rezept des
    Jobs (mit seiner `recipe_id`, ohne Hash) und ein Block `provenance`
    (`execution: "cloud"`, `kind: "job"`, `self_attested: false`, `engine`
    und `scaling` aus `result`, `started`/`finished` des Laufs, Attribution
    wie `access.download.attribution_text`). Format wie `crop_recipe_json`:
    UTF-8, zwei Leerzeichen, Schlüssel sortiert. Bei einem Cache-Treffer nennt
    die Provenienz die Zeiten des Laufs, der gerechnet hat, nie dessen
    `recipe_id`. Gleiche Frist wie die anderen Links (`410`).
- **`Cache-Control: no-store`** auf jeder Antwort unter `/processing/jobs/`
  (Pflicht auf dem `303`, `adr/0015` §6.1; das Rezept enthält die AOI).
- **Neu in `jobs/submit.py`, nur lesend:**
  - `job_recipe(conn, job_id) -> dict | None` — der gespeicherte
    Rezeptkörper des Jobs, für `recipe.json`.
  - `job_run(conn, job_id) -> int | None` und `run_jobs(conn, run_id, job_ids)
    -> list[JobStatus]` — für den Verteiler (§3.6). Die `run_id` bleibt im
    Prozess und geht nie hinaus.
  Alle drei schreiben nichts (Test über `xmin` wie in M4-08a).

### 3.6 SSE: `GET /processing/jobs/{jobID}/events` (`adr/0013` §5.4, F7)

- **Genau eine `LISTEN`-Verbindung je `api`-Prozess** (`api/job_events.py`):
  eine eigene `psycopg.AsyncConnection` mit `autocommit`, außerhalb jedes Pools,
  `application_name = earthx-api-listen`, `LISTEN earthx_job_progress`. Sie
  gehört dem Prozess, nicht einem Client, und wird beim Start geöffnet.
- **Verteilen:** Eine Aufgabe liest `notifies()`. Je Meldung liest sie die
  Zeilen **einmal je Lauf** (`run_jobs` mit allen verbundenen `jobID` dieses
  Laufs), nicht einmal je Client, und legt jedem Client den neuesten Stand ab.
  Jeder Client hat einen Platz für genau einen Stand („der neueste gewinnt“):
  Ein langsamer Client bremst niemanden und bekommt nie einen veralteten
  Zwischenstand nach einem neueren.
- **Verbinden eines Clients:** Prüfen wie §3.5 (`404` vor dem Öffnen des
  Streams), `run_id` lesen, beim Verteiler eintragen, **dann** die Zeile lesen
  und als erstes Ereignis senden. Weil `LISTEN` schon steht, geht dazwischen
  nichts verloren (`adr/0013` §5.4).
- **Ereignis:** `event: status`, `data:` das `statusInfo` wie bei `GET
  /jobs/{jobID}` (eine Form, ein Modell). Nach einem Endstatus (`successful`,
  `failed`, `dismissed`) sendet der Server das letzte Ereignis und schließt.
  Lebenszeichen: `: ping` alle 15 s durch FastAPI.
- **Abbruch der Verbindung:** Der Verteiler verbindet neu (1 s, verdoppelt bis
  30 s), setzt `LISTEN` zuerst und liest dann für jeden verbundenen Client die
  Zeile. Was dazwischen gesendet wurde, kommt nicht nach; die Zeile hat den
  Stand.
- **Deckel** je Prozess: höchstens 500 gleichzeitige SSE-Clients (K5); darüber
  `503` mit `Retry-After`. Ohne Konten kann jeder Streams öffnen; der Deckel
  schützt Speicher und Dateideskriptoren, nicht die Datenbank (die sieht eine
  Verbindung).
- **Pooler (M6):** Die Verbindung muss am Pooler im Transaktionsmodus vorbei
  (`adr/0013` §5.4). Sie liest dieselben `PG*`-Variablen; ein eigener Endpunkt
  dafür kommt erst mit M6.
- **Logs:** Zahl der Clients, Neuverbindungen; nie `jobID`, `run_id` nur als
  Zahl.

### 3.7 `statusInfo` und Fehler

- **`statusInfo`:** `processID: "recipe"`, `type: "process"`, `jobID`,
  `status` (OGC-Werte), `message` (fest je Status bzw. `error_kind`),
  `created`, `started`, `finished`, `progress`, `links` (`self`; `results`
  bei `successful`; `monitor` auf `/events`). Zusätzlich `recipeID` (Rezept-ID
  nach Q15, `adr/0014` F15) und `expires` (`expires_at`, damit das Panel die
  Frist zeigen kann). Kein Hash, keine AOI, kein Datensatz-`href`, keine
  `run_id`, keine `result_id`.
- Das Antwortmodell bleibt dünn (`adr/0014` §9: Version 2 heißt `id` statt
  `jobID`).
- **Fehler** im Format `exception.yaml` (`type`, `title`, `status`, `detail`),
  `application/problem+json`. FastAPI-Validierungsfehler der Routen selbst
  (Pfad, Query) gehen durch dieselbe Abbildung; ihr Text nennt Felder, nie
  Werte.

### 3.8 Dateiname (`adr/0015` §6.5)

`{dataset}_{ops}_{YYYYMMDD}{suffix}`: `ops` die Operatoren der Schritte mit `-`
verbunden, `export` ohne Schritte; Datum = `finished_at` des Laufs (UTC);
`suffix` `.tif`, `_mask.tif`, `_recipe.json`. Beispiel:
`cop-dem-glo-30_reproject_20261007.tif`. Nur Zeichen, die `signed_download`
erlaubt; nie AOI, Hash, `jobID` oder `result_id` (K6).

### 3.9 Zugriffslog (F6)

`RequestIdMiddleware` schreibt unter `/processing/jobs/` statt der `jobID` den
Platzhalter `{jobID}` (`/processing/jobs/{jobID}/results/result.tif`). Die
`jobID` ist der Zugang zum Ergebnis (Q9) und steht in keinem anderen Log
(M4-08a: „nie … `jobID`“). Ein Test prüft die Zeile über alle Job-Routen.

### 3.10 Tests

Gegen echtes Postgres mit der Wegwerf-Datenbank aus M4-08a (Fixture geteilt,
nicht kopiert), ohne Netz; Speicher als `Store` mit fester Test-Konfiguration
(Signieren braucht keinen Server). Neu unter `backend/tests/earthx/api/`:

- `test_processing_route.py` — Landing Page, Konformität, API-Definition,
  Prozessliste mit `limit`, Prozessbeschreibung (Schema je Operator, Filter je
  Datensatz, unbekannter Datensatz), Ausführung (Hülle, `Prefer`, `413`,
  Abweisungen der Annahme mit Status und Stufe, `check_scope`, Cache-Treffer
  sofort `successful`, `skippedItems`), Status, `DELETE` (wartend, laufend,
  fertig, zweimal), Ergebnisse je Status, Links (`303`, `410`, `404`,
  `no-store`, Dateiname, Ablauf der signierten URL ≤ 900 s und ≤ Restfrist),
  `recipe.json` (eigene `recipe_id`, bei zwei Jobs auf einem Lauf je die
  eigene; kein Hash).
- `test_job_events.py` — Verteiler direkt und über einen echten `uvicorn` in
  einem Thread (der `ASGITransport` von `httpx` puffert die Antwort und taugt
  für einen Stream nicht [A], beim Bauen zu prüfen).
- **Zweckfremd:** fremde, falsch geformte (zu kurz, zu lang, fremde Zeichen,
  Pfad-Tricks), verworfene und abgelaufene `jobID` → `404` auf jeder Route;
  `name` mit `../`; Eingaben als Link und als `value`; `response: raw`;
  `outputs` mit `value`; Auftrag mit `resolved` (F1 aus M4-07b); falscher
  Content-Type; leerer Rumpf; doppelte Schlüssel.
- **Logs und Antworten:** `caplog` über Ausführen, Status, Ergebnisse, Links
  und SSE — kein Eintrag und keine Antwort enthält eine AOI-Koordinate, einen
  `href` der Quelle, `c1:` oder (im Log) eine `jobID`.

---

## 4. Abnahme

| Punkt | Test |
|---|---|
| `adr/0013` §8 Punkt 6 Fortschritt | SSE liefert beim Verbinden den Stand der Zeile, danach Ereignisse; eine Meldung in einer Transaktion mit Rollback erzeugt keins, mit Commit eins; nach einem Endstatus schließt der Stream |
| Punkt 9 zweckfremd | fremde, falsch geformte, abgelaufene `jobID` → `404` auf jeder Route; keine Antwort und kein Log nennt Hash, AOI oder `href` |
| Punkt 12 eine `LISTEN`-Verbindung | 50 SSE-Clients an einem Prozess → genau eine Verbindung mit `application_name = earthx-api-listen` in `pg_stat_activity`; nach `pg_terminate_backend` stellt der Prozess sie wieder her, und jeder der 50 bekommt den Stand der Zeile |
| `303` | Link auf `result.tif`/`mask.tif` → `303`, `Location` auf den öffentlichen Endpunkt, `X-Amz-Expires` ≤ 900 und ≤ Restfrist |
| `410` | `expires_at` vorbei bzw. weniger als 60 s Rest → `410`; nach dem Löschen der Zeilen `404` |
| `no-store` | auf `303`, Ergebnisdokument, `recipe.json` und jedem Status |
| Dateiname | aus Datensatz, Operator und Datum, in `response-content-disposition` der signierten URL und in `recipe.json`; nie AOI, Hash, `jobID` |
| `recipe.json` | aus dem eigenen Rezept des Jobs, eigene `recipe_id`, kein Objekt im Speicher |
| OGC-Form | `201` + `Location`; `statusInfo`; `result-not-ready`; `no-such-job`; `dismiss` → `dismissed` |
| F4 (2) | `conformsTo` leer; Landing Page, API-Definition und Prozessbeschreibung sagen „no conformance claimed“; ein Eingang als Link (Objekt mit `href`) → `400` mit dem Hinweis „inline only“, und weder Item-Quelle noch `gateway` werden gerufen; `adr/0014` §15d |

---

## 5. Nicht in dieser Aufgabe

- Frontend: Processing-Panel, Job-Status, Proxy-Eintrag für `/processing` in
  `vite.config.ts`: M4-13.
- `citation.bib` und `attribution.txt` neben dem Ergebnis: M4-11, M4-14.
- Erneuter Start über eine `recipe_id` (Permalink) und dessen Frist: M4-19
  (`adr/0015` §13).
- Kostenschätzung als eigene Route vor dem Auftrag: M4-13 (Plan-Schritt dort).
- Quotas, Ratenbegrenzung je Nutzer oder IP: M6 (Q9).
- Anzeige eines Ergebnisses auf der Karte: nicht in M4a (`adr/0015` §13).

---

## 6. Umfang und Commits

Geschätzt rund 750 Zeilen Code (`processing_route.py` 400, `job_events.py` 180,
`jobs/submit.py` 50, `main.py` 50, `logging.py` 20, `processing` 10) und rund
950 Zeilen Tests, also deutlich über dem Richtwert von 400 Zeilen (F8).
Geplante Commits, je eine Sache:

1. `processing`: `check_scope` öffentlich.
2. `jobs/submit.py`: `job_recipe`, `job_run`, `run_jobs` (nur lesend) mit Tests.
3. `api`: Landing Page, Konformität, API-Definition, Prozesse und Schema.
4. `api`: Ausführen, Status, `DELETE`, Ergebnisse, Fehlerabbildung.
5. `api`: Ergebnis-Links (`303`, `410`), `recipe.json`, Dateiname.
6. `api`: Verteiler und SSE.
7. `api/main.py`: `lifespan` (Speicher, Pool, Item-Quelle, Verteiler).
8. `logging`: `jobID` im Zugriffslog als Platzhalter.
9. Zweckfremde Nutzung und Logs über alle Routen.
10. Doku und Log.

Vor dem Fertigmelden: `main` holen, `pytest`, `ruff check backend`,
`PYTHONPATH=backend lint-imports --config .importlinter`; Ergebnisse im PR.

---

## 7. Risiken

- **Streams im Test:** SSE braucht einen echten Server; Tests mit `uvicorn` in
  einem Thread sind zeitabhängig. Zeitgrenzen großzügig, Reihenfolge über
  Ereignisse statt `sleep`.
- **Threadpool:** Jede Route mit Datenbank belegt einen Thread des Pools von
  AnyIO (Vorgabe 40) und eine von 4 Verbindungen. Bei Last warten Anfragen auf
  eine Verbindung; das ist gewollt (kleiner Pool, wie der Such-Cache).
- **Fluten ohne Konten:** Jeder kann Aufträge stellen. Der Deckel von 4 Läufen
  schützt die Rechenleistung, die Frist von 7 Tagen die Zeilen; eine Grenze je
  Absender gibt es erst mit M6 (Q9). Der Rumpfdeckel von 1 MiB und die Deckel
  der Annahme (25 Items, 16 Assets, 16 Schritte) begrenzen eine einzelne
  Anfrage.
- **compose-topology nur in der CI:** `api` öffnet beim Start jetzt den
  Speicher und die `LISTEN`-Verbindung; ein Fehler zeigt sich dort.
- **Integrationstests von `api`:** Sie starten den `lifespan` heute ohne `S3_*`.
  Mit F7 Option 1 setzen sie eine Test-Konfiguration (Signieren braucht keinen
  Server); `.github/` ändert sich nicht.

---

## 8. Fragen an Otto

**F1 — Präfix der Job-Schnittstelle (§3.1)**
1. `/processing` — sagt, was dort geschieht; daneben `/stac`, `/coverage`,
   `/aoi`, `/geocode` **(Empfehlung)**
2. `/ogcapi` — nennt den Standard statt der Sache
3. `/jobs-api`

**F2 — Welcher Dienst trägt sie (§3.1, M4-07b §4)**
1. `api`, mit eigener Item-Quelle aus Gateway und Pool, die er schon hat;
   `tiler` bleibt Kacheln und Zuschnitt **(Empfehlung)**
2. `tiler`, der die Item-Quelle schon hat; dafür bekäme der Kachel-Prozess
   Queue, Speicher und `LISTEN`

**F3 — Form des Ausführungsrumpfs (§3.3, §3.4)**
1. Ein Eingang `recipe`, dessen Wert der Auftrag ist:
   `{"inputs": {"recipe": {…Auftrag…}}}`; die Operator-Schemas stehen in
   seinem Schema („in seiner Eingabe“, `adr/0014` §9) **(Empfehlung)**
2. Die Felder des Auftrags als einzelne Eingänge: `{"inputs":
   {"recipe_version": 1, "inputs": [...], "aoi": {...}, "steps": [...],
   "output": {...}}}`; generische OGC-Clients bauen je Feld ein Formular, dafür
   steht `inputs` in `inputs`
3. Der Auftrag ohne OGC-Hülle als Rumpf

**F4 — Konformität trotz Abweichungen (§3.4)**
OGC Core verlangt Eingaben auch per Referenz (Link) und als „qualified
value“; die Plattform holt keine fremde Adresse (B8) und nimmt den Auftrag nur
inline. Ergebnisse gibt es nur als Dokument mit Referenzen (`response:
document`). `adr/0014` F12 hat `core`, `json`, `dismiss` beschlossen, ohne diese
Punkte zu nennen.
1. `core`, `json`, `dismiss` erklären wie F12; die Abweichungen weisen mit
   `400` und klarem Text ab (nicht still) und stehen in der API-Definition und
   im Log **(Empfehlung)**
2. Keine Klasse erklären (`conformsTo: []`), bis die Abweichungen weg sind —
   so wie M3-13 `query` und `fields` abgeschaltet hat
3. Eingaben per Referenz über `gateway` zulassen (nur Hosts der Registry); die
   Annahme läse dann einen Auftrag von außen

**F5 — Statuscode für die Ergebnisse eines gescheiterten Jobs (§3.5, K4)**
OGC verlangt einen Code „that corresponds to the reason of the failure“.
1. Nach `error_kind`: Rezept (`recipe_invalid`, `unsupported_recipe`,
   `scaling_mismatch`, `grid_mismatch`, `aoi_outside_inputs`) → `422`; Quelle
   (`source_4xx`, `source_429`, `source_5xx`, `source_unreachable`,
   `rejected`) → `502`; `source_timeout` → `504`; alles andere
   (`out_of_memory`, `child_crashed`, `runtime_exceeded`, `upload_failed`,
   `lease_lost`, `cancelled`, `unknown`) → `500` **(Empfehlung)**
2. Immer `500`; die Art steht nur im `type`

**F6 — `jobID` im Zugriffslog von `api` (§3.9)**
1. Platzhalter `{jobID}` statt des Werts unter `/processing/jobs/`; die `jobID`
   ist der Zugang zum Ergebnis (Q9) und steht auch im Log des Workers nie
   **(Empfehlung)**
2. Pfad wie bisher; die Logs gelten als intern

**F7 — `api` ohne Konfiguration des Objektspeichers (§3.2)**
1. `api` startet nicht, wie `worker` ohne Ablaufregel; Integrationstests setzen
   eine Test-Konfiguration **(Empfehlung)**
2. `api` startet, die Job-Routen antworten `503`, eine Warnung steht im Log
   (wie die Ortssuche ohne `EARTHX_GEOCODER_URL`)

**F8 — Größe des PR (§6)**
1. Ein PR mit zehn thematischen Commits, rund 1 700 Zeilen, gut die Hälfte
   Tests; die Sitzung ist an einen Branch gebunden **(Empfehlung)**
2. Teilen: M4-08b-1 (Routen, Links, `recipe.json`) und M4-08b-2 (SSE) als zwei
   Sitzungen

**Kleinentscheidungen** (gelten, wenn Otto nicht widerspricht; angenommen am 07.10.2026):

- **K1** Ein eigener synchroner Pool (1–4) in `api` für `jobs/submit.py`,
  Aufrufe im Threadpool; `submit.py` bleibt synchron.
- **K2** Rumpf von `POST …/execution` höchstens 1 MiB (`413`), wie die
  AOI-Datei.
- **K3** `processing.check_scope(recipe)` öffentlich; `api` ruft es vor dem
  Einreihen (`422` statt eines Jobs, der nach dem Warten scheitert).
- **K4** Fehler als `exception.yaml` mit `type`
  `urn:earthx:job-failed:<error_kind>` und festem Titel je Art; Statuscode nach
  F5.
- **K5** Höchstens 500 gleichzeitige SSE-Clients je Prozess, darüber `503`
  mit `Retry-After: 5`. Startwert [A], ohne Messung; er begrenzt Speicher und
  Dateideskriptoren des Prozesses.
- **K6** Dateiname `{dataset}_{ops}_{YYYYMMDD}` mit dem Datum des
  Abschlusses (UTC); `export` ohne Schritte.
- **K7** Hrefs, `Location` und Links relativ zum Wurzelpfad
  (`/processing/…`), damit sie hinter dem Proxy des Frontends stimmen.
- **K8** Eine abgelaufene `jobID` (`expires_at` vorbei) ist auf den Job-Routen
  `404`, auch bevor der Aufräumer die Zeilen löscht; die Links antworten bis
  dahin `410`.
- **K9** `statusInfo` trägt zusätzlich `recipeID` und `expires`; die Antwort
  auf `POST` zusätzlich `skippedItems`.
- **K10** Ein unbekannter Datensatz in `?dataset=` ist `400`; ein Datensatz
  unter *Processing* bekommt eine leere Operatorliste.

---

## 9. Prüfanleitung für Otto (nach dem Merge, PowerShell)

```powershell
docker compose up -d --build
docker compose ps                                     # api, worker: healthy
Invoke-RestMethod http://localhost:8000/processing/   # Landing Page mit vier Links
Invoke-RestMethod "http://localhost:8000/processing/processes/recipe?dataset=cop-dem-glo-30"
```

Einen Auftrag mit echter AOI stellt das Panel aus M4-13. Bis dahin spielt
`scripts/try-job.ps1` einen kleinen echten Job durch (ein Item, Reprojektion über
eine ausgedachte Fläche von höchstens 2 × 2 km, Ergebnisse nach
`.\try-job-output\`, Cache-Treffer, `DELETE`, Suche der `jobID` im Log von `api`).
Vorgabe ist Sentinel-2 im Juli 2025 und braucht nichts weiter; `-Dataset`,
`-Bbox` und `-Datetime` ändern es (`Get-Help .\scripts\try-job.ps1 -Full`):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\try-job.ps1
```

`.env` bleibt, wie sie ist.

---

## 10. Antworten (Otto, 07.10.2026)

F1 (1), F2 (1), F3 (1), **F4 (2)**, F5 (1), F6 (1), F7 (1), F8 (1); K1–K10
angenommen.

**F4 (2), Begründung (Otto):** OGC API Processes Part 1, `/req/core/process-execute-inputs`
Teil B (Requirement 18) verlangt Eingaben per Referenz; das verbietet B8. Daher:

- Die Form nach OGC bleibt (Landing Page unter `/processing`,
  `/processing/conformance`, `/processes`, Job-Routen), aber `/conformance`
  antwortet mit leerer `conformsTo`-Liste. Keine Klasse wird erklärt, auch
  nicht `json` oder `dismiss`.
- Eine Eingabe als Link (Objekt mit `href`) wird mit `400` abgewiesen. Der
  Text sagt, dass Eingaben nur inline angenommen werden. Ein Test belegt es.
- Nachtrag in `adr/0014` zu F12 (§15d): keine Konformität erklärt, Grund
  Requirement 18 B und B8; erklärt werden kann sie erst, wenn Eingaben per
  Referenz unter einer eigenen Netzwerk-Policy möglich sind.
- Landing Page und Doku nennen das Verhältnis zu OGC offen („follows the form
  of OGC API – Processes, no conformance claimed“).

---

## 11. Umsetzung (07.10.2026)

Umgesetzt wie freigegeben, in thematischen Commits in PR #128. `main` per Merge
geholt. Keine neue Abhängigkeit, keine Lock-Datei geändert, keine Importregel
gelockert; `.github/`, `.claude/` und `CLAUDE.md` unberührt. Geändert hat sich
`docker-compose.yml` (Startbefehl von `api`, siehe 8).

**Neu:** `api/processing_route.py` (Routen, Fehlerform, Ergebnis-Links),
`api/processing_docs.py` (Landing Page, `conformsTo`, Prozess, Schema des
Auftrags), `api/job_events.py` (die eine `LISTEN`-Verbindung und das Verteilen),
`intake.job_recipe_json`, in `jobs/submit.py` `job_recipe`, `job_run`,
`run_jobs`, in `processing` `check_scope` und `loads_i_json`,
`logging.loggable_path`.

**Abweichungen und Befunde beim Bauen:**

1. **F4 (2) wie beschlossen.** `/processing/conformance` ist `{"conformsTo": []}`;
   Landing Page, API-Definition und Prozess tragen „follows the form of OGC
   API – Processes, no conformance claimed“. Ein Eingang als Objekt mit `href`,
   als Text oder als `{"value": …}` ist `400` („inputs are accepted inline only
   …“), **bevor** Item-Quelle, `gateway` oder Datenbank etwas sehen; Tests
   belegen, dass dabei weder eine Quelle gefragt noch etwas eingereiht noch die
   Adresse wiederholt wird. `adr/0014` §15d trägt den Nachtrag.
2. **`submit(…, operators=)`.** `submit` schätzte den Laufzeitdeckel mit der
   Registry der Plattform; `api` validiert aber mit der, die es bekommen hat
   (Tests: mit Testoperatoren). Der Parameter hat die Plattform als Vorgabe, `api`
   gibt seine eigene hinein.
3. **`dismiss` sendet immer eine Meldung** auf dem Kanal des Laufs, auch wenn der
   Lauf für andere Jobs weiterläuft. Sonst erführe ein Strom, der den verworfenen
   Job verfolgt, nichts davon. (Änderung an M4-08a-Code, mit Test.)
4. **OpenAPI aus einer eigenen App.** Diese FastAPI-Version hält eingebundene
   Router als Ganzes (`_IncludedRouter`); `app.routes` zählt sie nicht einzeln
   auf. `/processing/api` baut das Dokument deshalb aus dem Router allein, einmal
   und zwischengespeichert.
5. **Der Hub liest auch den ersten Stand.** Erste Fassung: die Route las die Zeile
   selbst. Der Reviewer fand die Lücke: Ein Fan-out konnte einen älteren Stand
   nach dem neueren in den Platz legen. Jetzt trägt `subscribe` den Lauf als
   geändert ein, und der eine Leser liefert auch den ersten Stand; Tests prüfen,
   dass Stände nie rückwärts laufen.
6. **Weitere Abweisungen, die der Plan nicht nannte:** `415` für alles außer
   `application/json`; ein Pfad unter `/jobs/`, der keine Route ist (`a/b`,
   `//id`), antwortet wie ein unbekannter Job (`404`, `no-store`); eine einzelne
   Surrogat-Escape-Folge (`"\ud800"`) im Auftrag ist `400`, nicht `500`.
7. **`410` vor „noch nicht fertig“.** Ein gescheiterter oder wartender Job nach
   dem Ende seiner Frist meldet auf den Links `410`, nicht noch einmal seinen
   Fehler.
8. **Herunterfahren.** uvicorn wartet vor dem Shutdown des `lifespan` auf alle
   offenen Verbindungen; ein Strom eines wartenden Jobs endet nie von selbst
   (am Minimalbeispiel belegt). `api` startet deshalb mit
   `--timeout-graceful-shutdown 5` (kleiner als die 10 s von compose); danach
   laufen `events.stop()` und das Schließen der Pools. Der Browser verbindet
   über `EventSource` neu. Ein Test fährt einen echten Server mit offenem Strom
   herunter, ohne den Hub vorher anzuhalten; `tests/compose/test_compose_api.py`
   hält den Befehl fest.
9. **Dateiname nur ASCII.** Ein Test mit einem Umlaut im Datensatznamen fand,
   dass `str.isalnum()` Nicht-ASCII durchlässt, das der Speicher abweist. Die
   Registry-IDs sind ASCII; gesichert ist es jetzt trotzdem im Namen selbst.
10. **Befunde des `reviewer`, behoben:** `LISTEN`-Verbindung mit
    TCP-Keepalives (still abgerissene Verbindung nach rund 90 s statt 2 h);
    Wartezeit auf eine Pool-Verbindung 5 s statt 30 s und `/health` als `async`
    (der Check teilt die Threads mit den Routen); Kennungen mit `\Z` statt `$`
    (kein Zeilenumbruch am Ende); das Zugriffslog ersetzt die `jobID` auch hinter
    einem `root_path` und bei mehreren Schrägstrichen; `RecipeIdTaken` und
    Fehlschläge beim Signieren und Einreihen antworten in der Form der API;
    der `lifespan` schließt, was er geöffnet hat, auch wenn der Start halb
    scheitert; Tests, die weniger bewiesen als sie sagten (Wert der
    `result_id` im Log, lose `or`-Prüfungen), geschärft.
11. **Bewusst nicht geändert:** `check_recipe_hosts` läuft in `accept_order` und
    noch einmal in der Route; das zweite Mal ist billig und hält die Zusage des
    Plans, dass jedes Rezept vor dem Einreihen geprüft wird, auch wenn
    `accept_order` später anders gebaut wird.

**Messung [M]** (`import earthx.api.main`, `VmHWM`, 3 Läufe, Sitzung): vorher
102 MB und 1,1–1,6 s, nachher **189 MB und 2,6–3,1 s**. Grund: `api` lädt jetzt
`processing` (rasterio, numpy, numexpr), um Aufträge anzunehmen und
`check_scope` zu fragen. Das ist die Grundlast des Prozesses, nicht die eines
Auftrags. Wer die Job-Schnittstelle in einen eigenen Prozess legen will
(Log: offen), findet die Stelle in `api/main.py`.

**Nicht gebaut (Plan §5):** Proxy-Eintrag `/processing` in `frontend/vite.config.ts`
und alles im Frontend (M4-13), `citation.bib` und `attribution.txt` (M4-11,
M4-14), Permalinks (M4-19).

**Prüfungen im PR:** siehe PR-Text (pytest, ruff, `lint-imports`, CI-Lauf).

**Skript `scripts/try-job.ps1`** (auf Ottos Wunsch, nach der Umsetzung): ein
kleiner echter Job gegen `http://localhost:8000`, sechs Schritte mit `OK` oder
`FEHLER`, Zusammenfassung, Exit-Code `1` bei einem Fehler. Windows PowerShell
5.1, nur `Invoke-WebRequest`, keine Module. In der Sitzung unter PowerShell
7.4.6 gegen eine Attrappe der Plattform durchgespielt (guter Lauf, kein
Cache-Treffer, gescheiterter Job, `jobID` im Log, Plattform nicht erreichbar);
Windows PowerShell 5.1 selbst und die echten Quellen sind aus der Sitzung nicht
erreichbar, dort läuft es zum ersten Mal bei Otto.

Änderung nach Ottos Rückmeldung (der DEM hatte im Testgebiet kein Item):
Vorgabe jetzt `sentinel-2-c1-l2a`; Parameter `-Dataset`, `-Bbox`, `-Datetime`
(dazu `-Asset`, `-Resolution`, `-TargetCrs`); höchstens 2 × 2 km, sonst bricht
das Skript vor dem Senden ab; der Auftrag nimmt genau ein Item (das neueste im
Zeitraum). Die Vorgabe ist gegen die echte Quelle geprüft: 18 Szenen im Juli 2025
über der Vorgabefläche, Asset `red` vorhanden (eine Anfrage an Earth Search). Beim
DEM ohne Item nennt das Skript die Kachel und, was `materialize` lädt: immer die
ganze Welt (26 450 Items, kein Gebietsfilter), rund 30 Anfragen, Listing etwa 45 s
(Messung vom 26.09.2026), **Schreiben der 26 450 Items 235 s [M]** (neu gemessen in
der Postgres der Sitzung, in einer Transaktion zurückgerollt). Gefunden beim
Prüfen: `-File` reicht `-Bbox 9.5,47.5,…` als einen Text durch, den PowerShell nicht
in eine Zahlenliste wandelt; `-Bbox` ist deshalb ein Text, den das Skript mit
Dezimalpunkt selbst liest.

**Zweite Rückmeldung (Zürich: „kein Item“, obwohl der Viewer Szenen zeigt).**
Ursache **belegt**: Die Plattform antwortet auf die Suche mit
`application/geo+json`. PowerShell reicht `.Content` für diesen Typ als
`byte[]` durch (gemessen unter 7.4.6: `application/json` und `text/plain` als
Text, `application/geo+json` und `application/octet-stream` als Bytes); das
Skript machte daraus nie ein JSON und meldete „kein Item“. Mit der alten Fassung
gegen einen Server, der die Form einer echten Antwort mit diesem Typ liefert,
ist genau das zu sehen. Gegen die echte Plattform (App, Postgres, pgstac) mit
einer Quelle in der Form einer echten Antwort liefern sowohl `POST /stac/search`
als auch die alte `GET`-Route die Szene: Route, Reihenfolge der Bbox
(West, Süd, Ost, Nord) und Datumsformat waren richtig. Geändert: das Skript liest
die Bytes der Antwort selbst (UTF-8), sucht wie der Viewer mit `POST
/stac/search` (JSON mit `collections`, `bbox` als vier Zahlen, `datetime` mit
Zeiten, `limit`), unterscheidet „Antwort nicht lesbar“ von „kein Item“, gibt mit
`-Verbose` Anfrage, Rumpf, Größe und Typ jeder Antwort aus und kennt `-SearchOnly`
und `-BaseUrl`. Vorgabefläche jetzt freies Land im Inland (rund 0,7 × 1,1 km,
18 Szenen im Juli 2025, gegen die Quelle geprüft). Nebenbefund: Antwortet die Quelle
mit 200 und HTML statt JSON, antwortet die Plattform `500` (`JSONDecodeError` im
Adapter) statt `502`; nicht Teil dieser Aufgabe.

