# M4-06 — Modul `objectstore`: Client, signierte URLs, Schlüssel, Ablaufregel: Plan

**Aufgabe:** M4-06 aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 06.10.2026 freigegeben:** F1–F7 je Option 1,
Kleinentscheidungen angenommen, Befund zu `smoke.py` (§2) angenommen. Dazu
Auflagen zu F2 und F4 (§8, „Antworten“). Umsetzung in PR #119.
**Ort im Repo:** `docs/plans/m4-06-objectstore.md`
**Grundlagen:** `adr/0015` §3–§9, §12 Punkte 1–8, §14 (F1–F13), §14a;
`plans/m4-processing-kern.md` §1.1b (R2, R4), §1.2, §1.3, M4-06;
`KLAERUNGEN.md` B8 (Nachtrag 2026-10-05), B9; `architekturplan.md` 3.1 (Nachtrag
2026-10-05); `adr/0012` §9 Punkt 5 (Nachtrag 2026-10-05);
`plans/m4-00b-lock-datei.md` (Muster der Lock-Datei); `plans/m3-23-garage.md`;
Log-Zeilen vom 02.10.2026 (offene Zeile `requirements-smoke.txt`) und vom
05.10.2026 („M4 R4“).

---

## 1. Ergebnis in drei Sätzen

`jobs` und `api` erreichen den eigenen Objektspeicher über das neue Modul
`earthx.objectstore`, das als einzige Stelle im Paket `botocore` importiert,
seinen Endpunkt nur aus `S3_*`-Variablen kennt und nur Kennungen
(`result_id`, `name`) entgegennimmt. `objectstore-init` legt zwei
Dienstschlüssel an (Worker schreibt, `api` liest) und setzt die Regel
`results/` über Garages Admin-API; der Worker startet nur, wenn er sie lesend
findet. Die Importverträge bekommen genau eine ignorierte Zeile
(`earthx.objectstore.client -> botocore`), die Verbotsliste wird verschärft, und
der Objektspeicher-Smoke installiert aus einer eigenen Lock-Datei.

---

## 2. Stand vor dieser Aufgabe (gelesen, 05.10.2026, `main` nach PR #118)

- **Ausgangslage grün:** `pytest` aus der Repo-Wurzel 1918 bestanden (mit
  Postgres der Sitzung), `ruff check backend` sauber, `lint-imports`
  12 Verträge gehalten.
- **`backend/earthx/jobs/`:** nur `main.py`, ein FastAPI-Stub mit `/health`.
  `backend/tests/test_logging.py` startet ihn einmal mit `uvicorn.Server`
  (Z. 90) — eine Startprüfung im `lifespan` liefe dort mit.
- **Kein `earthx.objectstore`**; `botocore`, `urllib3`, `jmespath`, `boto3`,
  `s3transfer` und `moto` stehen in keiner Lock-Datei.
- **`.importlinter`:** `http-only-in-gateway` verbietet `httpx`, `httpx2`,
  `requests`, `urllib`, `pystac_client`, `aiohttp`, `boto3`, `obstore`;
  `botocore` und `urllib3` fehlen (`adr/0015` §3.6).
- **`compose/objectstore/bootstrap.py`:** `secrets` erzeugt RPC-Secret,
  Admin-Token und **einen** Schlüssel `earthx-platform` (oder nimmt ihn aus
  `.env`), `init` importiert ihn mit Lesen/Schreiben/Besitzer und legt den
  Bucket an. Keine Regel, keine Dienstschlüssel.
- **`compose/objectstore/smoke.py`:** nutzt `boto3` mit dem Besitzerschlüssel
  (aus `show`), und **überschreibt die Lebenszyklus-Konfiguration** des Buckets
  mit einer eigenen Regel `smoke/` (`put_bucket_lifecycle_configuration`
  ersetzt die ganze Konfiguration). Mit M4-06 würde das die Regel `results/`
  löschen; der anschließende Schritt „Restart one service“ startet `worker` neu,
  und dessen Startprüfung schlüge fehl. Der Smoke muss deshalb umgebaut werden
  (§3.6).
- **`requirements-smoke.txt`:** `boto3==1.43.103`, `rasterio==1.5.1`,
  `numpy>=1.26,<3`, in `ci.yml` mit `pip install -r` ohne Hashes installiert.
- **Garage v2.4.1, Admin-API** (`src/api/admin/api.rs` Z. 971–979, nachgelesen
  am Tag v2.4.1) **[P]:** `UpdateBucketRequestBody.lifecycleRules` ist eine
  Liste von `xml::lifecycle::LifecycleRule` (`src/api/common/xml/lifecycle.rs`
  Z. 21–74: `ID`, `Status`, `Filter.Prefix`, `Expiration.Days`,
  `AbortIncompleteMultipartUpload.DaysAfterInitiation`). Die genaue JSON-Form
  der Werte klärt die Umsetzung am Quelltext und hält sie im Test von
  `bootstrap.py` fest.
- PyPI ist aus der Sitzung erreichbar (`botocore` 1.43.108, `moto` 5.2.3),
  `uv` 0.8.17 liegt bereit.

---

## 3. Umsetzung

### 3.1 Modul `backend/earthx/objectstore/`

Zuschnitt nach `adr/0015` §4.1:

| Datei | Inhalt |
|---|---|
| `__init__.py` | nur Docstring; nichts re-exportiert, damit `botocore` nicht über das Paket geladen wird |
| `config.py` | `StoreConfig` (frozen dataclass) und `StoreConfig.from_environ(environ=os.environ)`. Liest `S3_ENDPOINT`, `S3_PUBLIC_ENDPOINT`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY`/`S3_ACCESS_KEY_FILE`, `S3_SECRET_KEY`/`S3_SECRET_KEY_FILE`, `S3_ADDRESSING_STYLE` (Vorgabe `path`), `S3_LIFECYCLE_CHECK` (`required`, Vorgabe, oder `off`). Prüft: Schema `http`/`https`, kein Pfad, keine Query, kein Benutzerteil in den Endpunkten; `S3_PUBLIC_ENDPOINT` nur `https`, außer `localhost`/`127.0.0.1`; Bucket-Muster wie `bootstrap.py`; je Schlüssel genau eine der beiden Formen. Fehler (`StoreConfigError`) nennen den Variablennamen, nie den Wert. `__repr__` ohne Schlüssel. Kein `AWS_*` wird gelesen. |
| `client.py` | die **einzige** Datei mit `botocore`. `build_clients(config) -> Clients`: ein Client für `S3_ENDPOINT` (Upload, Löschen, Regel lesen) und ein zweiter nur zum Signieren für `S3_PUBLIC_ENDPOINT` (öffnet keine Verbindung, `adr/0015` §3.2). `botocore.session.Session()` ohne Profil, Schlüssel ausdrücklich übergeben; `Config(signature_version="s3v4", s3={"addressing_style": …}, request_checksum_calculation="when_required", response_checksum_validation="when_required", connect_timeout=…, read_timeout=…, retries={"mode": "standard", "max_attempts": 3}, proxies={})` (§5, Werte F6) |
| `results.py` | die öffentlichen Funktionen, alle mit `Store` als erstem Argument (Store = Konfiguration + Clients, entsteht nur über `Store.from_environ()`): `upload_result(store, result_id, name, path)` (einfach bis zur Schwelle, darüber Multipart; bei Fehler `AbortMultipartUpload`), `signed_download(store, result_id, name, *, not_after, filename) -> str`, `delete_result(store, result_id)` (alle Objekte unter dem Präfix, offene Multipart-Uploads dort abbrechen), `lifecycle_ok(store) -> bool`. Konstanten: `RESULT_TTL = 7 Tage`, `SIGNED_URL_TTL = 15 min`, `MIN_REMAINING = 60 s`, `RESULT_PREFIX = "results/"`, `RESULT_NAMES = {"result.tif", "recipe.json", "citation.bib", "attribution.txt"}`. `result_id` gegen `^[A-Za-z0-9_-]{22}$` (Form von `secrets.token_urlsafe(16)`), `filename` gegen `^[A-Za-z0-9._-]{1,128}$`. `signed_download` signiert für `min(15 min, not_after − jetzt)` und wirft `ResultExpiring`, wenn weniger als 60 s bleiben — die `410` daraus baut M4-08b. Uhr injizierbar (`now=`) für Tests. |
| `errors.py` | `ObjectStoreError` und Unterklassen (`StoreConfigError`, `StoreUnavailable`, `StoreDenied`, `ResultNotFound`, `ResultExpiring`, `LifecycleMissing`). Jede `botocore`-Ausnahme wird in `results.py` in eine davon übersetzt, **ohne Originaltext** (`raise … from None`); nur Fehlercode und Status bleiben. Zusätzlich `redact(text, *secrets)` als Kopie der vier Zeilen aus `compose/objectstore/redact.py` (§9.2) für jede Nachricht, die aus einer Antwort gebaut wird. |

**Keine öffentliche Funktion** nimmt Endpunkt, Host, Bucket oder URL entgegen
(Auflage F2). Ein Test liest die Signaturen aller öffentlichen Funktionen in
`earthx.objectstore` über `inspect` und lehnt Parameter mit `endpoint`, `host`,
`bucket`, `url` im Namen ab; ein zweiter belegt, dass `build_clients` nur aus
`StoreConfig` aufgerufen wird und `StoreConfig` nur aus der Umgebung entsteht.

### 3.2 Verträge (`.importlinter`) nach `adr/0015` §4.2 und R2

1. Neuer Vertrag `objectstore` („imports nothing domain-specific“), Muster
   `gateway`, `allow_indirect_imports = True`, verbietet die übrigen elf
   Module.
2. `earthx.objectstore` in die `forbidden_modules` aller übrigen
   Modulverträge außer `jobs`; `jobs` heißt dann „jobs import only processing
   and objectstore“.
3. `datasets-isolated`: `earthx.objectstore` als Quelle.
4. **Neuer Kettenvertrag `no-object-store-in-worker-core`** (R2): Quelle
   `earthx.processing`, verboten `earthx.objectstore` und `botocore`, **ohne**
   `allow_indirect_imports`. `no-database-in-worker-core` bleibt unverändert
   (den ändert M4-08a).
5. `http-only-in-gateway`: `earthx.objectstore` als Quelle; `botocore`,
   `urllib3`, `s3transfer`, `aiobotocore`, `aioboto3`, `minio` zu den
   verbotenen; `ignore_imports = earthx.objectstore.client -> botocore`;
   Kommentar nennt die Ausnahme und B8-Nachtrag. Der Vertragsname bleibt.

Erwartet: 14 Verträge gehalten, „1 ignored import“.

**Tests:**

- `test_module_boundaries.py`: `objectstore: set()` und
  `jobs: {"processing", "objectstore"}` in `ALLOWED_IMPORTS`; der neue
  Kettenvertrag in die Parameterliste von
  `test_the_two_chain_sensitive_contracts_keep_counting_chains` (der Name wird
  „…_chain_sensitive_contracts…“ ohne Zahl); neuer Test, dass
  `no-object-store-in-worker-core` genau `processing` als Quelle hat und
  `earthx.objectstore` und `botocore` verbietet; neuer Test, dass
  `http-only-in-gateway` **genau eine** `ignore_imports`-Zeile hat und sie
  `earthx.objectstore.client -> botocore` lautet.
- `test_no_outbound_outside_gateway.py`: `CORE` um `botocore` und `urllib3`;
  `objectstore/client.py` wird für genau `botocore` ausgenommen und sonst nicht
  (`adr/0015` §4.3, letzter Absatz).
- **Neu `backend/tests/earthx/test_objectstore_boundary.py`** (§4.3, ohne
  Netz): (1) nur `jobs`, `api` und `objectstore` importieren
  `earthx.objectstore`, über den Syntaxbaum inklusive Importen in Funktionen,
  `from earthx import objectstore` und relativen Importen (aufgelöst gegen den
  Paketpfad); (2) `botocore` nur in `objectstore/client.py`; (3) `objectstore`
  importiert keinen anderen Client der Verbotsliste; (4) `boto3` und
  `s3transfer` stehen nicht in `backend/requirements.lock` — mit einem Satz,
  warum (rasterio öffnet sonst `AWSSession` und fragt `169.254.169.254`,
  `adr/0015` §3.1); (5) je eine Gegenprobe an einem Quelltext-Schnipsel.
- `test_import_linter_catches_violations.py` (besteht schon, prüft Verstöße an
  einer Kopie): um zwei Fälle ergänzt, wenn die vorhandene Mechanik das
  hergibt — `earthx.objectstore.other -> botocore` und
  `earthx.processing.bad -> earthx.objectstore` brechen. Sonst steht die
  Gegenprobe nur im PR (Abnahme).

### 3.3 Abhängigkeiten

- `backend/requirements.txt`: `botocore` mit Begründungskommentar (kein
  `boto3`, `adr/0015` F3); keine Kappe auf die Hauptversion (§5).
- `backend/requirements-dev.txt`: `moto[s3]` (bringt `boto3` nur in die
  Dev-Umgebung, §3.1).
- `scripts/lock-backend.sh` ohne `--upgrade`: neu im Image erwartet
  `botocore`, `jmespath`, `urllib3` (dazu `python-dateutil`, falls nicht schon
  im Lock); im Dev-Lock zusätzlich `moto` mit Abhängigkeiten.
- `backend/Dockerfile`: `ENV AWS_EC2_METADATA_DISABLED=true` mit Kommentar.
- Öffnet `botocore` selbst Verbindungen? Ja, aber nur gegen den übergebenen
  Endpunkt (§3.2 des ADR); es steht deshalb auf der Verbotsliste mit genau
  einer Ausnahme (M4-Plan §1.2, B8). `urllib3` ebenso auf der Liste.

### 3.4 Logs (`backend/earthx/logging.py`)

`botocore` und `urllib3` in `_URL_LOGGING_LIBRARIES`; Test nach dem Muster der
vorhandenen für `httpx`: bei `configure_logging(DEBUG)` stehen beide auf
`WARNING`. Dazu ein Test mit `moto`, dass nach `signed_download` und
`upload_result` bei Root-Level `DEBUG` weder Schlüssel-ID, Secret noch
`X-Amz-Signature` im erfassten Log steht.

### 3.5 `jobs`-Start (`backend/earthx/jobs/main.py`)

- `lifespan`: `Store.from_environ()`; bei `S3_LIFECYCLE_CHECK=required`
  `lifecycle_ok(store)` — falsch oder `ObjectStoreError` → Logzeile ohne
  Konfigurationswerte, dann Abbruch (uvicorn beendet den Prozess, der
  Container wird nicht `healthy`). Bei `off` **genau eine** Warnung, ohne
  Werte, und kein Abruf der Regel (Auflage F8).
- „Passende Regel“ (F4, Auflage): am Inhalt erkannt, nicht am Namen —
  aktiviert, Präfix `results/`, `Expiration.Days = 7`,
  `AbortIncompleteMultipartUpload.DaysAfterInitiation = 1`. Weitere Regeln am
  Bucket stören nicht.
- Tests (`backend/tests/earthx/jobs/test_startup.py`, mit `moto`): startet
  mit Regel; startet nicht ohne Regel, mit falscher Frist, mit anderem Präfix,
  mit deaktivierter Regel; startet nicht ohne Konfiguration und nennt dabei
  den Variablennamen, nicht den Wert; `off` schreibt genau eine Warnung ohne
  Endpunkt, Bucket oder Schlüssel; `docker-compose.yml` setzt
  `S3_LIFECYCLE_CHECK` nirgends (als Text und als YAML gelesen).
- `test_logging.py` Z. 90 startet die Worker-App über `uvicorn.Server`: dort
  kommt `lifespan="off"` in die `uvicorn.Config`, weil der Test die Zugriffslog-
  Zeile prüft, nicht den Start; der Start ist oben eigens getestet.

### 3.6 compose

**`compose/objectstore/bootstrap.py`:**

- `secrets` erzeugt zusätzlich zwei Dienstschlüssel (immer erzeugt, nie aus
  `.env`, §9.1): `earthx-jobs` und `earthx-api`, Form nach F3. Idempotent, wie
  bisher; keine Kennung in der Ausgabe.
- `init` importiert beide Schlüssel (`ImportKey`), gewährt `earthx-jobs`
  `read`+`write` und `earthx-api` nur `read` (`AllowBucketKey`; einem schon
  vorhandenen `earthx-api` werden `write` und `owner` per `DenyBucketKey`
  entzogen, damit ein früherer Stand nicht mehr Rechte behält) und setzt
  die Regel per `POST /v2/UpdateBucket` mit `lifecycleRules`:
  `ID results-7d`, `Enabled`, Präfix `results/`, `Expiration.Days 7`,
  `AbortIncompleteMultipartUpload.DaysAfterInitiation 1` (§7.3). Danach liest
  es die Regel über `GetBucketInfo` zurück und schreibt **eine** Zeile wie
  `objectstore-init: lifecycle rule results-7d set (prefix results/, expire after 7 days, abort multipart after 1 day)`
  — das ist, was Otto in `docker compose logs objectstore-init` sieht.
- `show` bleibt für den Besitzerschlüssel; mit F2 (1) druckt es zusätzlich die
  zwei Dienstschlüssel unter eigenen Namen.
- Tests in `backend/tests/compose/test_objectstore_bootstrap.py` (gegen eine
  nachgebaute Admin-API, wie heute): zwei Schlüssel erzeugt, idempotent; Rechte
  je Schlüssel; Regel im Körper von `UpdateBucket`; die Logzeile; in keinem
  Fall eine Kennung oder ein Secret in der Ausgabe (erster Lauf, zweiter Lauf,
  Fehler).

**`docker-compose.yml`:**

- `api` und `worker` bekommen `S3_ENDPOINT: http://objectstore:3900`,
  `S3_PUBLIC_ENDPOINT: http://localhost:3900`, `S3_REGION: garage`,
  `S3_BUCKET: ${S3_BUCKET:-earthx}`, `S3_ACCESS_KEY_FILE`/`S3_SECRET_KEY_FILE`
  auf ihr eigenes Volume (read-only, F3). `tiler` und `harvester` bekommen
  nichts. Das Volume `objectstore-secrets` mit Admin-Token und RPC-Secret
  erreicht weder `api` noch `worker`.
- `S3_LIFECYCLE_CHECK` steht nirgends (Auflage F8).
- `.env` überschreibt weiter nur den Besitzerschlüssel; `.env.example` bekommt
  einen Satz dazu.

**`compose/objectstore/smoke.py`** (läuft auf dem CI-Runner, nicht im Image):

- Client `botocore` statt `boto3` (F1), gleiche Einstellungen wie
  `objectstore/client.py`.
- **Schreibt keine Lebenszyklus-Konfiguration mehr** (§2); stattdessen: Regel
  `results-7d` mit dem Leseschlüssel zurücklesen und vergleichen.
- Neu: Leseschlüssel kann `PutObject` und `DeleteObject` nicht (`403`), auch
  nicht über eine mit ihm signierte PUT-URL; mit ihm für den öffentlichen
  Endpunkt (`http://localhost:3900`) signierte GET-URL mit
  `response-content-disposition` → `200` und der Kopf ist da; für
  `http://objectstore:3900` signiert und über `localhost:3900` abgerufen →
  `403`.
- Schreibschlüssel: `PutObject` unter `results/` geht.
- Die bisherigen Prüfungen (Multipart, Range, Ablauf der URL, GDAL über
  `/vsicurl/`) bleiben, mit dem Besitzerschlüssel.

### 3.7 R4: Lock-Datei für den Smoke

- `compose/objectstore/requirements-smoke.txt` wird Eingabe wie die
  Backend-`.txt` (`botocore`, `rasterio`, `numpy`, ohne eigene Pins);
  `scripts/lock-backend.sh` schreibt daraus
  `compose/objectstore/requirements-smoke.lock` **mit
  `--constraint backend/requirements.lock`**, sodass der Smoke dieselben
  Versionen von `botocore`, `rasterio` und `numpy` nutzt wie das Image (F1).
- `ci.yml`, Job `compose-topology`: `cache-dependency-path` auf die `.lock`,
  Installation `pip install --require-hashes --only-binary :all: -r
  compose/objectstore/requirements-smoke.lock` (Zeilen 204 und 207). Mit
  F2 (1) zusätzlich der Schritt „Object store credentials …“: zwei weitere
  Schlüsselpaare aus `show` lesen, maskieren, an den Smoke-Schritt reichen
  (rund zehn Zeilen). Sonst nichts an `.github/`.
- `test_backend_lock.py`: der Smoke als drittes Paar in `LOCKS`, `ci.yml`
  installiert ihn mit Hashes (eigene Prüfung, weil der Install-Befehl dort
  nicht die Backend-Optionen mit `--no-binary version-parser` braucht).

### 3.8 Doku und Log

- `architekturplan.md` 3.1: Zeile `objectstore` in die Tabelle; Zeile `jobs`
  „`processing`, `objectstore`“; Zeile `gateway` „alle ausgehenden Zugriffe auf
  Datenquellen; der eigene Objektspeicher über `objectstore`“ (der Nachtrag vom
  05.10.2026 bleibt stehen).
- `README.md`: compose-Abschnitt — zwei Dienstschlüssel, die Regel, die neue
  Prüfanleitung; Fehlerbild „worker wird nicht healthy, weil die Regel fehlt“.
- `ENTSCHEIDUNGSLOG.md` am Ende: Antworten auf §8; Umsetzung M4-06; die offene
  Zeile vom 02.10.2026 bekommt in der Statusspalte den Verweis (nichts
  gelöscht).
- Dieser Plan bekommt §9 „Umsetzung“.

---

## 4. Abnahme gegen `adr/0015` §12

| § 12 | Beleg |
|---|---|
| 1 Modul, Verträge, Tests, Gegenprobe | `lint-imports` 14 gehalten, 1 ignoriert; §3.2; Gegenprobe im PR-Text (zweiter `botocore`-Import in `objectstore/other.py` und in `processing` → gebrochen) |
| 2 kein `boto3`/`s3transfer` im Image | `test_objectstore_boundary.py` (4) |
| 3 `bootstrap.py`: Schlüssel, Regel, Volumes, keine Kennung | Tests §3.6; compose-topology |
| 4 Smoke: Leseschlüssel, Regel, Endpunkte | `smoke.py` in compose-topology |
| 5 `moto`: Upload, Multipart, Signieren mit Dateinamen, Löschen, Schwärzung, Konfigurationsfehler | `backend/tests/earthx/objectstore/`. **Aufräumer und `410` nicht hier** (M4-08a/b, M4-Plan „Nicht in dieser Aufgabe“); vorbereitet durch `ResultExpiring` |
| 6 `proxies={}`, `HTTP_PROXY` leitet nicht um | Test: `HTTP_PROXY`/`HTTPS_PROXY` auf einen lokalen Port, Endpunkt auf einen lokalen Lausch-Socket; die Anfrage kommt am Endpunkt an, nicht am Proxy (nur `127.0.0.1`, erlaubt von `conftest.no_network`) |
| 7 Auflage F2 | Signaturtest und Herkunftstest §3.1 |
| 8 Auflage F8 | Tests §3.5 |

Punkt 9 (Rezeptfrist) gehört zu M4-08.

---

## 5. Nicht in dieser Aufgabe

Aufräumer und `410` (M4-08a/M4-08b), Job-Tabellen, Routen, Ergebnisdokument;
`no-database-in-worker-core` (M4-08a); `gateway`, `processing`; CORS am Bucket;
weitere Präfixe; Produktion mit verwaltetem S3 (nur: keine Codeänderung nötig).
An `.github/` nur die in §3.7 genannten Zeilen.

---

## 6. Umfang und Commits

Geschätzt rund 1 500 geänderte Zeilen ohne Lock-Dateien, davon gut die Hälfte
Tests — deutlich über dem Richtwert von 400 (F7). Geplante Commits, je eine
Sache:

1. Abhängigkeiten: `botocore`, `moto[s3]`, Lock-Dateien, Dockerfile.
2. Modul `objectstore` mit Tests (`moto`).
3. Verträge und Grenztests (`.importlinter`, drei Testdateien).
4. Logs: `botocore`/`urllib3` auf `WARNING`.
5. `jobs`-Start mit Regelprüfung.
6. `bootstrap.py`: Dienstschlüssel und Regel; `docker-compose.yml`, `.env.example`.
7. `smoke.py` auf `botocore`, neue Prüfungen; Smoke-Lock und `ci.yml` (R4).
8. Doku und Log.

---

## 7. Risiken

- **compose-topology ist nur in der CI prüfbar** (kein Docker-Daemon in der
  Sitzung, `adr/0002` §1). Ein Fehler in `bootstrap.py` oder `smoke.py` zeigt
  sich erst dort; die Admin-API-Aufrufe sind gegen den nachgebauten Server
  getestet und die JSON-Form am Garage-Quelltext gelesen, nicht gemessen.
  Falls der erste CI-Lauf rot ist, folgt ein Fix-Commit.
- **`moto` ist nicht Garage:** Regel-Lesen, Rechte je Schlüssel und Host-Bindung
  prüft nur der Smoke am echten Image. `moto` prüft Signaturen standardmäßig
  nicht; Tests zu Signaturen lesen die URL (Host, Ablauf, Kopf) statt sie
  abzurufen.
- **Bestehende Volumes:** Ein lokales `objectstore-secrets` aus M3-23 bekommt
  beim nächsten Start die neuen Schlüssel dazu; nichts wird überschrieben. Ein
  alter Smoke-Lauf kann eine Regel `expire-results` hinterlassen haben —
  `init` setzt die Regelliste vollständig, die alte Regel verschwindet damit
  (nur `smoke/`, nur CI-Daten).
- **`moto` zieht `boto3` in die Dev-Umgebung.** Dort ändert sich rasterio für
  Pfade mit `amazonaws.com` (`adr/0015` §3.1); `readers` öffnet nur
  `/vsicurl/`-Pfade, die Testsuite bleibt ohne Netz (`conftest.no_network`).

---

## 8. Fragen an Otto

**F1 — Client und Lock des Smoke (R4)**
1. `smoke.py` auf `botocore` wie das Modul; Lock-Datei aus `lock-backend.sh`
   mit dem Laufzeit-Lock als Constraint, also dieselben Versionen wie das Image
   **(Empfehlung)**
2. `boto3` bleibt im Smoke; eigene Lock-Datei ohne Constraint, Pins wie heute
3. Wie 1, aber eigenes Skript statt `lock-backend.sh`

**F2 — Wie der Smoke an die Dienstschlüssel kommt** (Änderung an `.github/`
über die Lock-Zeilen hinaus)
1. `show` druckt die zwei Dienstschlüssel zusätzlich; der vorhandene
   Schritt „Object store credentials …“ in `ci.yml` liest und maskiert sie und
   reicht sie an den Smoke weiter, rund zehn Zeilen **(Empfehlung)**
2. `smoke.py` ruft `docker compose run … show` selbst auf; `ci.yml` ändert sich
   nur in den Lock-Zeilen, die Werte sind aber nicht von GitHub maskiert
   (nur geschwärzt)
3. Leseschlüssel-Prüfungen nur mit `moto` in `pytest`, nicht am echten Image
   (erfüllt `adr/0015` §12 Punkt 4 nicht)

**F3 — Ablage der Dienstschlüssel**
1. Zwei neue Volumes `objectstore-key-api` und `objectstore-key-worker`, je mit
   `access_key` und `secret_key`; `objectstore-secrets` schreibt beide,
   `objectstore-init` liest beide read-only; `api` und `worker` sehen nur ihr
   eigenes **(Empfehlung)**
2. Unterordner im vorhandenen Volume, eingehängt mit `volume.subpath`
   (braucht eine neuere Docker-Compose- und Engine-Version; an Ottos Docker
   Desktop nicht geprüft, Versionsgrenze unbelegt)
3. Ein Volume für beide Dienste mit beiden Schlüsseln (jeder Dienst sähe den
   Schlüssel des anderen)

**F4 — Was die Startprüfung als „passende Regel“ annimmt**
1. Genau: aktiviert, Präfix `results/`, `Expiration.Days = 7`,
   `AbortIncompleteMultipartUpload = 1`; ID egal (Produktion setzt eigene
   IDs). Eine kürzere Frist würde Ergebnisse vor `expires_at` löschen, eine
   längere die 7 Tage für Bytes überziehen **(Empfehlung)**
2. Mindestens so streng: `Days ≤ 7`, Abbruch ≤ 1
3. Nur „eine aktivierte Regel mit Präfix `results/` existiert“

**F5 — `api` in M4-06**
1. Nur compose: Variablen und Volume für `api`, kein Code; `api` nutzt das
   Modul erst mit den Routen in M4-08b. `api` startet weiter ohne
   S3-Variablen, die vorhandenen API-Tests bleiben unverändert
   **(Empfehlung)**
2. `api` baut `Store.from_environ()` schon beim Start und startet ohne
   Konfiguration nicht

**F6 — Grenzwerte im Client**
1. Multipart ab 8 MiB, Teile 8 MiB, nacheinander (kein Thread-Pool) — die
   Vorgaben von `s3transfer` 0.19.2 (`manager.py` Z. 57–58) **[P]**; S3 verlangt
   Teile ≥ 5 MiB außer dem letzten und höchstens 10 000 Teile **[S]**, 8 MiB
   reichen damit bis rund 78 GiB. `connect_timeout` 5 s, `read_timeout` 60 s
   (Vorgabe von botocore 1.43.108 ist 60/60 **[P]**, `botocore/endpoint.py` Z. 39,
   `botocore/config.py` Z. 308–309; kürzer beim
   Verbindungsaufbau, weil der Speicher im selben Netz liegt **[A]**),
   `retries` standard mit 3 Versuchen (`adr/0015` §5) **(Empfehlung)**
2. Teile 64 MiB (weniger Anfragen bei großen Mosaiken, mehr Speicher je Teil)
3. Wie 1, aber parallele Teile in einem Thread-Pool

**F7 — Größe des PR**
1. Ein PR mit acht thematischen Commits (§6), rund 1 500 Zeilen ohne
   Lock-Dateien, gut die Hälfte Tests. Die Sitzung ist an einen Branch
   gebunden; ein Schnitt hieße eine zweite Sitzung **(Empfehlung)**
2. Teilen in M4-06a (Modul, Verträge, Abhängigkeiten, Logs; nur `pytest`) und
   M4-06b (compose, `bootstrap.py`, Smoke, `jobs`-Start, R4) als zwei Sitzungen

**Antworten (Otto, 06.10.2026):** F1–F7 je **(1)**; Kleinentscheidungen
angenommen. Auflagen:

- **F2:** Erlaubt ist unter `.github/` genau die Änderung am Schritt in
  `ci.yml`, der die Schlüssel liest, mit `::add-mask::` maskiert und
  weiterreicht, dazu die Lock-Zeile aus R4. Kein Schlüssel und keine
  Schlüssel-ID erscheint im CI-Log, auch nicht bei einem Fehler (Test oder
  Beleg im PR).
- **F4:** Die Regel wird am Inhalt erkannt (Präfix `results/`, aktiviert,
  Ablauf 7 Tage, Abbruch Multipart 1 Tag), nicht am Namen; weitere Regeln am
  Bucket stören nicht.

**Kleinentscheidungen** (angenommen):

- `signed_download` wirft `ResultExpiring` bei weniger als 60 s Restlaufzeit;
  die `410` daraus baut M4-08b.
- Ein schon vorhandener Schlüssel `earthx-api` verliert `write` und `owner`
  bei jedem `init` (`DenyBucketKey`).
- `init` setzt die Regelliste vollständig (nur `results-7d`); weitere Präfixe
  kommen mit eigenen Regeln, wenn sie entstehen (`adr/0015` §7.3).
- `result_id` folgt der Form von `secrets.token_urlsafe(16)`; `RESULT_NAMES`
  wächst mit M4-11/M4-12, wenn ein Job weitere Dateien schreibt.

---

## 9. Prüfanleitung für Otto (nach dem Merge, PowerShell)

```powershell
docker compose up -d --build
docker compose ps            # api, tiler, worker, harvester: healthy
docker compose logs objectstore-init
# erwartet u. a.: "objectstore-init: lifecycle rule results-7d set (prefix results/,
# expire after 7 days, abort multipart after 1 day)" — ohne Schlüssel oder Secret
```

`.env` bleibt, wie sie ist; die zwei Dienstschlüssel und zwei neue Volumes
entstehen beim ersten Start von selbst.

---

## 10. Umsetzung (06.10.2026)

Umgesetzt wie freigegeben, in thematischen Commits (§6) in PR #119. `main`
nach #121 (ADR 0016) per Merge geholt; die Lock-Dateien waren dort nicht
geändert.

**Abweichungen und Befunde beim Bauen:**

1. **Drei Versuche heißen `total_max_attempts: 3`.** botocore zählt
   `max_attempts` ohne den ersten Versuch (gemessen: `max_attempts: 3` ergibt
   `total_max_attempts: 4`). F6 meint drei Versuche insgesamt.
2. **Die Übersetzung der `botocore`-Fehler liegt in `client.py`, nicht in
   `results.py`.** Nur `client.py` darf `botocore` importieren, also auch
   dessen Ausnahmeklassen nicht anderswo nennen. `client.py` hat dafür eine
   schmale Klasse `S3` mit den neun Aufrufen, die das Modul braucht, alle
   gegen den einen Bucket aus der Konfiguration.
3. **`init` nannte bei „different secret“ die Schlüssel-ID** des
   Besitzerschlüssels im Fehlertext (seit M3-23). Das ginge in
   `docker compose logs` und das CI-Log; jetzt steht dort der Name
   `earthx-platform`. Ein Test je Schlüssel belegt es (Auflage F2).
4. **Smoke las `Content-Disposition` aus einem `dict`**; Garage sendet die
   Köpfe klein geschrieben. Gefunden am offiziellen Image (unten), behoben.
5. **Die Gegenprobe ist ein Test** (`test_import_linter_catches_violations.py`):
   `lint-imports` mit der echten `.importlinter` über eine Kopie des Pakets —
   grün mit „1 ignored import“, gebrochen bei einem zweiten `botocore`-Import
   in `objectstore` und in `processing`, bei `access -> objectstore`,
   `processing -> objectstore`, der Kette `processing -> catalog ->
   objectstore` und `objectstore -> catalog`.
6. **Weitere Tests als geplant:** `test_compose_objectstore_wiring.py` (jeder
   Prozess sieht nur seinen Schlüssel, `tiler`/`harvester` keinen, kein
   `AWS_*`, das Admin-Volume nur bei den Einmal-Schritten) und
   `test_objectstore_smoke_output.py` (der Smoke gibt bei keinem Fehler einen
   der sechs Schlüsselwerte aus). Der Smoke ist jetzt importierbar, weil er
   nur noch Pakete aus dem Dev-Lock braucht.
7. **Garages Zugriffs-Log nennt die Schlüssel-ID jeder Anfrage**
   (`(key GK…)`, `GET /v2/GetKeyInfo?id=GK…`), gesehen im CI-Log des ersten
   grünen Laufs, dort maskiert. Der Schritt „Wait for all services to report
   healthy“ gibt bei einem Fehlschlag aber `docker compose logs` aus, bevor die
   Schlüssel maskiert sind — gegen die Auflage zu F2. `.github/` bleibt dafür
   unverändert; stattdessen bekommt `objectstore` in `docker-compose.yml`
   `RUST_LOG: netapp=info,garage=info,garage_api_common=error` (Garages
   Vorgabe ohne Anfrage-Log). Gemessen am offiziellen Image: ohne Filter
   56, 24 und 22 Zeilen mit den drei IDs, mit Filter keine **[M]**.
8. `botocore` liest das S3-Dienstmodell je Session neu (rund 0,1 s je
   Client); ein gemeinsamer Daten-Loader spart das, die Sessions bleiben
   getrennt.
9. `results.py` hat zusätzlich `new_result_id()` (`secrets.token_urlsafe(16)`)
   für M4-08a.

**Lokaler Lauf am offiziellen Image [M].** `cloud-umgebung.md` §4 (Nachtrag
vom 05.10.2026): `docker pull` geht in der Sitzung. Garage
`dxflrs/garage:v2.4.1` mit dem Digest aus `docker-compose.yml` lief mit
`--network host` (Kopie von `garage.toml` mit `0.0.0.0` statt `[::]`, die
Sitzung hat kein IPv6). Dagegen, ohne Proxy-Variablen:

| Prüfung | Ergebnis |
|---|---|
| `bootstrap.py secrets`, `init`, zweites `init` | ✅ Schlüssel importiert, Rechte gesetzt, Regel gesetzt und zurückgelesen; zweiter Lauf idempotent; keine Kennung in der Ausgabe |
| Worker-Startprüfung mit Regel | ✅ startet |
| Regel mit Besitzerschlüssel gelöscht | ✅ `LifecycleMissing`, startet nicht |
| `S3_LIFECYCLE_CHECK=off` | ✅ eine Warnung ohne Werte, startet |
| erneutes `init` | ✅ Regel wieder da, Worker startet |
| `upload_result` 16 MiB (3 Teile), signierte URL, `delete_result` | ✅ `200`, Dateiname im Kopf, danach nichts unter dem Präfix |
| Modul mit dem `api`-Schlüssel | ✅ liest die Regel; Upload → `StoreDenied`, Text ohne Schlüssel-ID |
| Modul mit unbekanntem Schlüssel | ✅ `StoreDenied` ohne Schlüssel-ID (Garage nennt sie in `AccessDenied`) |
| `smoke.py --write-marker`, dann `--persisted` | ✅ 23 Prüfungen, davon 9 neue zu Regel, Rechten und Endpunkten |
| `smoke.py` mit falschem `api`-Schlüssel | ✅ bricht ab, Ausgabe `No such key: <redacted>`; keiner der Werte im Text |

Ein ganzes `docker compose up` ging in der Sitzung nicht (`apt-get` im
`Dockerfile` scheitert, `cloud-umgebung.md` §4); das belegt die CI
(`compose-topology`).

**Ergebnisse:** siehe PR-Beschreibung (pytest, ruff, `lint-imports`,
compose-topology).
