# ADR 0013 — Job-Queue und Hülle `jobs`

- **Status:** **Entwurf**, wartet auf Otto. Die Fragen F1–F11 stehen in §10.
- **Datum:** 2026-10-02
- **Aufgabe:** M4-02 laut `docs/plans/m4-processing-kern.md` §4.
- **Autonomiestufe:** C. Kein Produktivcode, keine Änderung an `.importlinter`,
  an `docker-compose.yml` oder an der CI. Gemessen wurde mit Skripten im
  Kratzverzeichnis der Sitzung, gegen eigene Kratz-Datenbanken im Postgres der
  Sitzung und mit einer eigenen Kratz-venv. Der Messanhang (§12) nennt die
  Abfragen und Befehle.
- **Vorab fest:**
  - Q4: `processing` bleibt ohne psycopg; `jobs` ist die Hülle mit Queue und
    Datenbank und darf psycopg. Die Vertragsform schlägt dieses ADR vor.
  - Q9: Job-IDs sind nicht zu erraten; ein globaler Deckel für gleichzeitige
    Jobs, Startwert hier.
  - Q10: 7 Tage Frist für Job-Ergebnisse und gespeicherte Rezepte.
  - Aus `adr/0014` (angenommen): `jobID` und `recipe_id` sind
    `secrets.token_urlsafe(16)` (F15); der Cache-Schlüssel ist der interne Hash
    mit Verfahrenskennung `c1:` (§4.4, §4.5); Job-API in der Form von OGC API
    Processes, nur asynchron, mit `dismiss`, ohne Job-Liste (§9); der Kern ist
    `processing.run(recipe, *, workdir, progress)` mit einem Rückruf je Block
    (§7.2, §13); `jobs` ruft beim Prozessstart
    `processing.worker_environment()` auf (§7.3, §8).
- **Grundlage:**
  - `architekturplan.md` 0, 3.1, 3.2, 7.3, 7.4, 7.5, 7.6, 10, 12.3, 12.4,
    15.2 (Spike „Job-Queue“).
  - `KLAERUNGEN.md` B8, B9 (mit Nachtrag vom 02.10.2026).
  - `adr/0001` §9.2; `adr/0002` §2 (Tests gegen echtes Postgres in CI und
    Sitzung); `adr/0005` §6 (Verbindungen je Host); `adr/0012` F3, F5;
    `adr/0014` §3.5, §3.6, §4.4–§4.7, §7.2, §7.3, §8, §9, §12, §13.
  - `plans/m3-07a-ortssuche-backend.md` §9 (`RateSlot`).
  - Entscheidungslog bis 02.10.2026, besonders „M4 Q4“, „M4 Q8“–„M4 Q11“ und
    die offene Zeile „Worker-Einstieg in `jobs` darf `datasets` nicht
    importieren“.
- **Betroffen:**
  - M4-08 (Queue, Hülle `jobs`, Job-API, Fortschritt, Ergebnis-Cache, Deckel,
    Ablauf), M4-11 und M4-12 (erste Jobs), M4-13 (Job-Status im Panel), M4-16
    (Runner: dieselbe Kern-Schnittstelle ohne Queue).
  - `.importlinter` (Vertrag `no-database-in-worker-core`),
    `backend/tests/test_module_boundaries.py` Z. 130,
    `architekturplan.md` 3.1 (Zeile `jobs`), `docker-compose.yml` (Dienst
    `worker`), `catalog/migrations/`.

---

## Methode und Belegstufen

Gelesen und gemessen in einer Cloud-Sitzung am 02.10.2026 auf dem Stand von
`main` nach PR #114. Die Belegstufen folgen `adr/0009`:

- **M:** in dieser Sitzung gemessen; Abfrage oder Befehl im Messanhang §12.
- **P:** am Primärdokument gelesen, mit Datei und Zeile (Quelltext im Repo, im
  Wheel von PyPI oder in einem Klon des Herausgeber-Repos).
- **S:** Zusammenfassung einer Quelle, deren Wortlaut nicht geprüft ist.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Werkzeuge.** PostgreSQL 16.14 der Sitzung (4 CPU, 16 GB RAM,
`max_connections 100`, `shared_buffers 128MB`, alles Vorgaben). Gemessen mit
Python 3.12.3 und psycopg 3.3.6 (dieselbe Version wie in
`backend/requirements.lock`). Procrastinate 3.10.0 und der Python-Client
`pgmq` 1.1.4 lagen nur in einer eigenen venv im Kratzverzeichnis, nie im
Projekt-venv. pgmq 1.13.1 wurde als reines SQL in eine eigene Kratz-Datenbank
geladen. Gemessen wurde in drei eigenen Datenbanken (`m402_spike`,
`m402_procr`, `m402_pgmq`), nicht in `earthx`.

**Quellen.** Klone (Tiefe 1) von `procrastinate-org/procrastinate`
(`58c4b34`, 28.09.2026), `pgmq/pgmq` (`8cc0959`, 26.09.2026),
`hatchet-dev/hatchet` (`caa973a`, 01.10.2026), `temporalio/sdk-python`
(`d67e609`, 01.10.2026) und `celery/celery` (`6bc4220`, 01.10.2026); das Wheel
`procrastinate-3.10.0-py3-none-any.whl`; die PyPI-JSON-API (abgerufen
02.10.2026); die PostgreSQL-16-Dokumentation als SGML aus
`postgres/postgres`, Zweig `REL_16_STABLE`, über
`raw.githubusercontent.com`. Ein Hilfsagent hat die Primärtexte gelesen; sein
Bericht mit wörtlichen Zitaten liegt nur im Kratzverzeichnis. Was er am
Primärtext gelesen hat, trägt hier **[P]** mit Datei und Zeile und lässt sich
aus dem Klon bzw. dem Wheel nachprüfen.

**Gesperrte Hosts.** `*.readthedocs.io`, `docs.celeryq.dev`,
`docs.temporal.io`, `docs.hatchet.run`, `www.postgresql.org`, `github.com`
(HTML) und `api.github.com`. Dokumentation kam deshalb aus den `docs/`-Ordnern
der Klone und aus den SGML-Quellen der Postgres-Doku.

**Anfragen an Datenquellen: 0.** Für eine Queue braucht es keine echte Quelle
(M4-Plan M4-02). Keine AOI kommt vor; alle Jobs in den Messungen sind leer oder
schlafen.

---

## 0. Kurzfassung

Jede Empfehlung hat eine Frage in §10.

1. **Eine eigene schlanke Queue auf Postgres in `jobs` (F1),** hinter der
   Nahtstelle `JobRunner` aus 7.5. Keine neue Abhängigkeit, kein neuer Dienst.
   - Die Anforderungen, die M4 über 7.5 hinaus stellt (globaler Deckel nach Q9,
     Grenze je Quelle über Prozesse, Fortschritt, Ablauf nach Q10, kein Hash
     im Payload nach Q8), deckt keine der geprüften Bibliotheken ab [P].
   - Jede davon ist mit wenigen SQL-Anweisungen gemessen [M]: Abholen mit
     `SKIP LOCKED`, Deckel, Grenze je Host, Erkennung toter Worker,
     Abschirmung gegen einen wieder erwachten Worker, Fortschritt per
     `NOTIFY`, gleiche Aufträge, Aufräumen.
   - Procrastinate 3.10 ist der stärkste Kandidat einer Bibliothek (F1
     Option 2). Es bringt Wiederholung, Abbruch und Heartbeat, aber keinen
     Deckel über Prozesse, keinen Fortschritt und keinen automatischen
     Neustart festhängender Jobs [P][M]. Es nennt sich selbst noch nicht
     „really ready for production“ und sucht Maintainer [P].
2. **Vertrag (F2):** `no-database-in-worker-core` gilt nur noch für
   `processing` und verbietet dort zusätzlich `psycopg_pool` und `asyncpg`.
   Der Vertrag `jobs` bleibt. Die Zeile `jobs` in 3.1 nennt psycopg.
3. **Worker-Hülle (F3):** Ein Aufseher je Container holt Jobs und startet je
   Job einen frischen Kindprozess, der nur `processing.run` ausführt.
   - Nur so lässt sich ein laufender Job hart beenden. Ein Thread lässt sich
     nicht abbrechen; Procrastinate kann es bei synchronen Jobs auch nicht
     [P].
   - Kosten: rund 1,0–1,5 s Start und 143 MB je Kind [M].
4. **Startwerte (F4):** global **4** gleichzeitige Jobs, je Quell-Host **2**,
   je Worker-Container 2 Slots. Der Deckel steht in der Datenbank, nicht in
   der Zahl der Container.
   - Gemessen hält der Deckel über 8 Prozesse genau, aber **nur**, wenn die
     Sperre in einer eigenen Anweisung vor dem Zählen genommen wird. In einer
     Anweisung lief er unter `READ COMMITTED` auf 4 bis 6 statt 3 [M].
5. **Tote Worker (F5):** Lease 60 s, Heartbeat alle 15 s durch den Aufseher.
   - Stirbt nur das Kind, merkt es der Aufseher sofort.
   - Ein wieder erwachter Worker kann ein fremdes Ergebnis nicht
     überschreiben: Abschluss nur mit seiner Versuchsnummer [M].
   - Session-Advisory-Locks erkennen einen beendeten Prozess in 13 ms, einen
     hängenden aber nie [M]. Deshalb sind sie nur eine Option.
6. **Gleiche Aufträge (F6):** Der öffentliche Job ist vom internen Lauf
   getrennt. Gleichzeitige gleiche Aufträge hängen an einem Lauf
   (8 gleichzeitige Einreichungen → 1 Lauf, [M]). Ein `DELETE` bricht den
   Lauf nur ab, wenn kein anderer Job daran hängt. So kann niemand fremde Jobs
   abbrechen, nur weil er dasselbe Rezept kennt.
7. **Fortschritt (F7):** Die Zeile in Postgres ist die Wahrheit, `NOTIFY` nur
   der Weckruf. Jeder `api`-Prozess hält eine `LISTEN`-Verbindung und
   verteilt an SSE-Clients.
   - Gemessen: Median 0,8 ms, p99 2,1 ms bei 100 Ereignissen/s.
   - Kein Ereignis bei Rollback; Payload über 8000 Bytes wird abgewiesen.
   - Wer nicht zuhört, verpasst Ereignisse; die Zeile hat den Stand [M][P].
8. **Wiederholung (F8):** automatisch höchstens 3 Versuche, nur bei
   vorübergehenden Fehlern, mit Backoff und Jitter.
9. **Ablauf (F9):** Job-, Lauf- und Rezeptzeilen laufen 7 Tage nach Abschluss
   ab und werden stündlich in Stapeln gelöscht. Ein Cache-Treffer gilt nur,
   wenn das Ergebnis noch mindestens 24 h gilt.
   - Ohne Index auf dem Fremdschlüssel dauerte das Löschen von 50 000
     abgelaufenen Rezepten 232 s, mit Index 0,38 s [M].
10. **Einstieg und Migrationen (F10, F11):** Der Worker startet aus einer
    Kompositionswurzel in `api`; die Schleife liegt in `jobs`. Das löst die
    offene Logzeile zu `datasets` ohne Lockerung. Die Tabellen kommen als
    nächste Nummer in `catalog/migrations/`.
11. **Grenze je Quelle über Prozesse:** `RateSlot` taugt nicht als Vorbild für
    die Lesezugriffe des Kerns. Der Kern liest über GDAL und darf die
    Datenbank nicht erreichen (B9). Die Grenze gilt deshalb je Job beim
    Abholen [M]. Mit einem Lesethread je Job (`adr/0014` §7.2) ist das
    zugleich eine Grenze für die Verbindungen [A].

---

## 1. Kontext und Frage

`architekturplan.md` 7.5 empfiehlt eine Postgres-gestützte Queue hinter einer
Nahtstelle `JobRunner` und nennt Procrastinate oder eine schlanke
`SKIP LOCKED`-Implementierung. Ein Spike soll das entscheiden (15.2: „Erfüllt
eine Postgres-Queue die Anforderungen aus 7.5, inklusive Fairness und
Fortschritts-Events?“). Der M4-Plan ergänzt die Kettenregel nach Q4, den
globalen Deckel nach Q9, die Rücksicht auf die Quellen über Prozessgrenzen
und das Aufräumen nach Q10. `adr/0014` hat Rezept, Kern und Job-API
festgelegt und dieses ADR für Queue, Deckel, SSE und den Ort des
Worker-Einstiegs offen gelassen (`adr/0014` §14).

Heute ist `jobs` eine Hülle ohne Inhalt: `jobs/main.py` startet eine
FastAPI-App mit `/health` (`backend/earthx/jobs/main.py` Z. 1–25 [P]); compose
startet sie mit `uvicorn earthx.jobs.main:app` (`docker-compose.yml` Z. 236
[P]). `processing` ist leer.

## 2. Kriterien

| # | Kriterium | Herkunft |
|---|---|---|
| K1 | Dauerhaft: übersteht Neustarts von Worker, `api` und Datenbank | 7.5 |
| K2 | Transaktionales Einreihen zusammen mit Job- und Rezeptzeile | 7.5 |
| K3 | Fairness je Nutzer; Prioritäten (Free/Pro) | 7.5; bis M6 ohne Konten (Q9) |
| K4 | Abbruch: wartend sofort, laufend kooperativ, notfalls hart | 7.5; `adr/0014` §9 (`dismiss`) |
| K5 | Wiederholung mit Idempotenz über den Rezept-Hash | 7.5; M4-Plan M4-02 |
| K6 | Fortschritt bis in `api` (SSE) | 7.4; `adr/0014` §9 |
| K7 | Worker-Pools nach Region und Ressourcentyp | 7.5; 12.2 |
| K8 | Globaler Deckel für gleichzeitige Jobs, über Prozesse | Q9 |
| K9 | Grenze je Quell-Host über Prozesse | 7.5; Q9; M4-Plan M4-02 |
| K10 | Aufräumen der Zeilen nach der Frist | Q10 |
| K11 | Kettenregel: `processing` ohne Datenbank und Queue, `jobs` mit | Q4; B9 |
| K12 | Kein neuer Dienst; die Bibliothek öffnet selbst keine Verbindung nach außen | 0 Punkt 9; B8 |
| K13 | Lizenz vereinbar mit AGPL-3.0-or-later | ENTSCHEIDUNGEN §4 |
| K14 | Pflege, Reife, neue Abhängigkeiten | M4-Plan §1.2 |
| K15 | Datenschutz: weder Hash noch AOI in Payload, Kanal, Log | Q8; `adr/0014` §4.7 |

---

## 3. Befunde

### 3.1 Kandidaten — [P], Lizenz [A]

**Procrastinate 3.10.0** (23.09.2026):

- **Pflege und Lizenz:**
  - Neun Releases in den letzten 12 Monaten (3.6.0 vom 08.12.2025 bis
    3.10.0) [P, PyPI].
  - MIT (`METADATA` Z. 16), `Requires-Python >=3.10` (Z. 17) [P].
  - Das README sucht „additional maintainers“ (`METADATA` Z. 50) [P]. Die
    eigene Doku sagt: „we'd like to develop real monitoring tools before we
    call this really ready for production“ (`docs/discussions.md`
    Z. 307–308) [P].
- **Abhängigkeiten:**
  - Pflicht sind `asgiref`, `attrs`, `croniter`, `packaging`,
    `psycopg[pool]`, `python-dateutil` und `typing-extensions` (`METADATA`
    Z. 18–35) [P].
  - Im Projekt-venv fehlen davon nur `asgiref` und `croniter` [P, Liste der
    installierten Pakete].
  - Kein Import eines HTTP-, Socket- oder Telemetriemoduls im Wheel; die
    Bibliothek verbindet sich nur zur Datenbank [P].
- **Schema:**
  - Vier Tabellen `procrastinate_{jobs,workers,events,periodic_defers}` im
    Schema `public`. Ein anderes Schema geht nur über `search_path`
    (`docs/howto/production/schema.md` Z. 8–23) [P].
  - Abholen mit `FOR UPDATE OF jobs SKIP LOCKED` (`sql/schema.sql`
    Z. 251–252) [P].
  - `procrastinate_jobs` hat keine Spalte für Ergebnis oder Fortschritt
    (`schema.sql` Z. 65–78) [P].
- **Migrationen:** SQL-Dateien im Paket, ohne Buchführung: „It's your
  responsibility to keep track of which migrations have been applied“
  (`docs/howto/production/migrations.md` Z. 40–41) [P].
- **Transaktional:** `task.configure(connection=conn).defer_async()` schreibt
  in die eigene Transaktion (`docs/howto/production/external_connection.md`
  Z. 10–13) [P]. Das gibt es ab 3.8; 3.7.3 hat es nicht [P, Wheels
  verglichen].
- **Abbruch:**
  - `cancel` wirkt auf wartende Jobs.
  - `abort` bricht asynchrone Jobs per asyncio ab. Synchrone Jobs laufen in
    einem Thread und müssen `context.should_abort()` selbst prüfen
    (`worker.py` Z. 541–544; `utils.py` Z. 106–111) [P].
  - „Procrastinate does not provide a built-in method to forcefully terminate
    a worker“ (`docs/howto/advanced/shutdown.md` Z. 23) [P].
- **Festhängende Jobs:**
  - Worker-Heartbeat alle 10 s; als tot gilt ein Worker nach 30 s
    (`worker.py` Z. 48–49) [P].
  - `get_stalled_jobs()` findet die Jobs, wiedereingereiht wird aber nicht:
    „these *stalled* jobs will remain in the queue forever“; dafür braucht es
    eine eigene periodische Task (`docs/howto/production/retry_stalled_jobs.md`
    Z. 7–8, 24–34) [P].
- **Grenzen:**
  - Nebenläufigkeit nur je Worker (`concurrency`) [P].
  - Kein globaler Deckel, keine Fairness [A, Suche in `docs/`].
  - Priorität ohne Schutz vor Verhungern (`docs/howto/advanced/priorities.md`
    Z. 37–43) [P].
- **`lock`:** Ein Unique-Index auf laufende Jobs je Lock-Text (`schema.sql`
  Z. 102) [P]. Nach einem Absturz blockiert ein Job mit `lock` alle folgenden
  mit demselben Lock, bis er von Hand gesetzt wird (`docs/discussions.md`
  Z. 128–130) [P].

**pgmq 1.13** (Extension; Python-Client `pgmq` 1.1.4 vom 20.09.2026):

- **Lizenz und Pflege:**
  - PostgreSQL License (`LICENSE` Z. 1–3) [P].
  - Neun Release-Tags in 12 Monaten [P].
- **Installation:** Seit 1.3.0 reines SQL/PGXS. Die unversionierte Datei
  `pgmq-extension/sql/pgmq.sql` lässt sich ohne Extension laden („only works
  for a fresh installation“, `INSTALLATION.md` Z. 79–95) [P]. Das ging in der
  Sitzung [M].
- **Lesen:** `read(queue, vt, qty)` holt mit `FOR UPDATE SKIP LOCKED` und
  setzt ein Sichtbarkeitsfenster (`pgmq.sql` Z. 340–378) [P]. Gemessen: Eine
  gelesene, nicht gelöschte Nachricht ist nach Ablauf von `vt` wieder lesbar,
  `read_ct` steigt auf 2 [M].
- **Fehlt:** Priorität, Eindeutigkeit, Abbruch, Fortschritt, Dead-Letter und
  Wiederholungsstrategie [P, Suche in `pgmq.sql`]. Dazu kommt ein festes
  Schema `pgmq` (`pgmq.control` Z. 2–6) [P].
- **Python-Client:** bringt `orjson` neu mit (PyPI) [P].

**Nur als Vergleich:**

| | zusätzlicher Dienst | einreihbar in derselben Postgres-Transaktion | Lizenz | Auffälligkeit |
|---|---|---|---|---|
| **Celery + Redis** | ja: Redis | nein, nur über eine Outbox [A] | Celery BSD-3 [P]; Redis-Server ab 7.4 RSALv2/SSPLv1/AGPLv3 zur Wahl, ≤ 7.2 und Valkey BSD-3 [P] | laufende Tasks nur per `revoke(terminate=True)`, „you must never call this programmatically“ (`docs/userguide/workers.rst` Z. 589–600) [P]; Redis-Sichtbarkeit 1 h, lange Tasks laufen sonst mehrfach (`redis.rst` Z. 79–89) [P] |
| **Hatchet** | ja: Engine, API, Migration; RabbitMQ als Vorgabe (`pkg/config/server/server.go` Z. 568) [P] | nein, Einreihen über gRPC/REST [A] | MIT [P] | Server ruft per Vorgabe `https://security.hatchet.run` auf (`server.go` Z. 395–398; `pkg/security/security.go` Z. 140–159) [P]; SDK bringt `aiohttp`, `urllib3`, `grpcio` [P, PyPI] |
| **Temporal** | ja: Server mit eigener Persistenz [P] | nein [A] | MIT [P] | SDK mit Rust-Kern (`.gitmodules`) [P] |

Alle drei brauchen einen Dienst neben Postgres. Damit verletzen sie die
Entscheidung „eine Datenbank: Postgres“ (0 Punkt 9) und 7.5 („kein
zusätzlicher Dienst“). Die Lizenzen von Procrastinate (MIT), pgmq
(PostgreSQL), dem pgmq-Client (Apache-2.0) und den neuen Abhängigkeiten
(BSD-3, MIT) sind mit AGPL-3.0-or-later vereinbar [A]. Eine Lizenzfrage wäre
nur der Redis-Server; die stellt sich bei der Empfehlung nicht.

### 3.2 Postgres-Semantik — [P]

Quelle: PostgreSQL 16, SGML aus `REL_16_STABLE`.

- **`SKIP LOCKED`:** Es „provides an inconsistent view of the data, so this is
  not suitable for general purpose work, but can be used to avoid lock
  contention with multiple consumers accessing a queue-like table“
  (`ref/select.sgml` Z. 1603–1607).
- **`NOTIFY`:**
  - Zustellung erst beim Commit: „not delivered until and unless the
    transaction is committed“ (`ref/notify.sgml` Z. 78–80).
  - Gleiche Payloads in einer Transaktion werden zu einer Nachricht
    zusammengefasst (Z. 97–99).
  - Die Payload muss kürzer als 8000 Bytes sein (Z. 144).
  - Die Queue fasst 8 GB; ist sie voll, scheitert der Commit (Z. 158–160).
- **`LISTEN`:** Nur Sitzungen, die gerade zuhören, werden benachrichtigt
  (`ref/listen.sgml` Z. 40–45). Wer erst zuhört und dann den Zustand liest,
  verliert nichts (Z. 99–107).
- **Session-Advisory-Locks** gelten, bis sie freigegeben werden oder die
  Sitzung endet, und ignorieren Rollback (`mvcc.sgml` Z. 1531–1552).
- **Tote Clients:** „Without connection checks, the server will detect the
  loss of the connection only at the next interaction with the socket“
  (`config.sgml` Z. 1052–1055). `client_connection_check_interval`,
  `idle_in_transaction_session_timeout` und `idle_session_timeout` sind in
  der Vorgabe aus.
  - Mit den Keepalive-Vorgaben von Linux (2 h, dann 9 × 75 s; `ip-sysctl.rst`
    Z. 593–605 im Linux-Repo) bemerkt der Server einen still verschwundenen
    Client erst nach rund 2 h 11 min [A]. So lange hielten Sperren einer
    solchen Sitzung.

### 3.3 Messungen — [M]

Alle gegen Postgres 16.14 der Sitzung; das Schema der eigenen Queue steht in
§12.1.

**M1 Einreihen und Abholen (eigene Queue).**

| Messung | Ergebnis |
|---|---|
| Einreihen: Rezeptzeile und Jobzeile in einer Transaktion, 1 Verbindung | 1471 Jobs/s |
| Abholen und Abschließen mit `SKIP LOCKED`, 4 Prozesse | 2356 Jobs/s |
| Genau einmal | 5000/5000; jeder Job mit Versuch 1, keine Doppelzeile |

**M2 Globaler Deckel über Prozesse:** 8 Prozesse, Deckel 3, je Job 0,2 s,
120 Jobs. Ein Beobachter zählte laufende Zeilen (rund 90 000 Stichproben je
Lauf).

| Variante | Höchstzahl gleichzeitig (4 Läufe) |
|---|---|
| Sperre `pg_advisory_xact_lock` und Zählen **in einer Anweisung** | 6, 4 (statt 3) |
| Sperre in **eigener Anweisung**, dann Zählen und Holen | 3, 3 |

- Die Ursache ist der Schnappschuss [A]: Unter `READ COMMITTED` nimmt die
  Anweisung ihn zu Beginn, also vor dem Warten auf die Sperre. Sie zählt
  deshalb den Stand von vorher.
- Die Wandzeit lag in beiden Varianten bei 8,4–8,6 s gegenüber 8,0 s ideal.
  Die Sperre kostet also kaum Durchsatz.

**M3 Abgestürzter und hängender Worker.** Ein Worker holt einen Job mit Lease
6 s und Heartbeat alle 2 s. Zusätzlich hält er eine Session-Advisory-Lock auf
den Job. Gemessen wurde aus einer zweiten Sitzung alle 10 ms.

| Ereignis | Advisory-Lock frei nach | Lease abgelaufen nach |
|---|---|---|
| `SIGKILL` (3 Läufe) | 0,012–0,013 s | 5,50 s |
| `SIGSTOP` (Prozess hängt) | nicht in 15 s | 5,49 s |

Nach `SIGSTOP` reihte ein Aufräumer den Job nach dem Lease neu ein. Ein
zweiter Worker rechnete Versuch 2 und schloss ab. Danach lief der erste Worker
weiter (`SIGCONT`) und wollte Versuch 1 abschließen: **0 Zeilen geändert**. Der
Job blieb `successful` mit Versuch 2. Die Versuchsnummer schirmt also ab.

**M4 Fortschritt per `NOTIFY`.** Je Ereignis `UPDATE progress` und
`pg_notify` in einer Transaktion; ein zweiter Prozess hört zu.

| Messung | Ergebnis |
|---|---|
| 1000 Ereignisse bei ~100/s | alle zugestellt; Latenz Median 0,81 ms, p99 2,12 ms, max 7,75 ms |
| `NOTIFY` in einer zurückgerollten Transaktion | 0 zugestellt |
| Payload 7900 B / 8100 B | angenommen / `payload string too long` |
| 5 Ereignisse, bevor der Zuhörer startet | 0 empfangen; die Zeile hat den letzten Stand |

**M5 Gleiche Aufträge und Aufräumen.**

- **Gleiche Aufträge:** 8 Prozesse reichen gleichzeitig denselben
  Cache-Schlüssel ein, über `INSERT … ON CONFLICT (cache_key) WHERE status IN
  (…) DO NOTHING` auf einem partiellen Unique-Index. In 3 von 3 Runden
  entstand genau 1 Lauf, und 7 Einreichungen hängten sich an.
- **Aufräumen:** 100 000 Jobs, die Hälfte abgelaufen, gelöscht in Stapeln von
  5000 über die Rezeptzeile mit `ON DELETE CASCADE`.

| Aufräumen | Zeit |
|---|---|
| ohne Index auf `job.recipe_id` | **231,9 s** |
| mit Index | **0,38 s** |

**M6 Grenze je Quell-Host über Prozesse.** 8 Prozesse, global 4, je Host 2,
3 Hosts, jeder vierte Job auf zwei Hosts, 150 Jobs, je 0,15 s. In 2 von 2
Läufen gleichzeitig höchstens 4, je Host höchstens 2; alle 150 fertig.

**M7 Procrastinate 3.10.0.**

| Messung | Ergebnis |
|---|---|
| `defer_async`, 1 Verbindung | 802 Jobs/s |
| Worker, `concurrency=4`, leere async-Jobs | 570 Jobs/s |
| eigene Zeile und `configure(connection=…)` in einer Transaktion, dann Rollback | kein Job, keine Zeile |
| `SIGKILL` des Workers mitten im Job | Status bleibt `doing`; `get_stalled_jobs()` nennt ihn nach 29,2 s; **kein** automatisches Neueinreihen; erst `retry_job()` setzt `todo` |
| `abort` eines laufenden async-Jobs | `aborted` nach 0,01 s |
| `abort` eines laufenden sync-Jobs, der `should_abort()` alle 50 ms prüft | `aborted` nach 0,04 s |

Nebenbefund: Ein Worker, der aus einem Prozess mit schon geöffnetem
Procrastinate-Pool per `fork` startet, bekam keine Verbindung
(`PoolTimeout`). Mit `spawn` lief er. Für die eigene Queue gilt dasselbe: Der
Kindprozess öffnet keine Verbindung, und gestartet wird mit `spawn` (§5.3).

**M8 Kosten eines Kindprozesses je Job.** Start von Python und Import von
`numpy`, `rasterio`, `rio_tiler.io`, `xarray`, `zarr`, `numexpr`,
`earthx.access.resolve` und `earthx.readers` im Projekt-venv:

- 1,01–1,54 s in 4 Läufen;
- 142–143 MB höchster Speicher des Kindes.

---

## 4. Kriterienmatrix

Bewertung **[A]** aus den Belegen in §3: ✅ erfüllt, ⚠ mit Einschränkung oder
eigenem Code, ❌ nicht erfüllt.

| # | Kriterium | **E** eigene Queue in `jobs` | **P** Procrastinate 3.10 | **G** pgmq + eigene Logik | Celery + Redis | Hatchet | Temporal |
|---|---|---|---|---|---|---|---|
| K1 | dauerhaft | ✅ Postgres | ✅ Postgres | ✅ Postgres | ⚠ Redis-Persistenz | ✅ | ✅ |
| K2 | transaktional mit Jobzeile | ✅ [M1] | ✅ ab 3.8 [P][M7] | ✅ `pgmq.send` ist ein `INSERT` [A] | ❌ | ❌ | ❌ |
| K3 | Fairness, Prioritäten | ⚠ Spalte `priority`; Fairness erst mit Konten (M6) | ⚠ Priorität, kein Schutz vor Verhungern [P] | ❌ keine Priorität [P] | ⚠ | ✅ [S] | ✅ [S] |
| K4 | Abbruch, notfalls hart | ✅ Kindprozess [M8][A] | ⚠ async ja, sync nur kooperativ, kein hartes Ende [P][M7] | ❌ selbst bauen | ⚠ Prozess beenden, „never programmatically“ [P] | ✅ [S] | ✅ [S] |
| K5 | Wiederholung, Idempotenz | ✅ Versuchsnummer schirmt ab [M3]; gleiche Aufträge [M5] | ⚠ Strategien ja [P]; tote Jobs nur mit eigener Task [P][M7] | ⚠ nur Sichtbarkeitsfenster [M] | ⚠ [P] | ✅ [S] | ✅ [S] |
| K6 | Fortschritt bis `api` | ✅ Zeile + `NOTIFY` [M4] | ❌ keine Spalte [P], selbst bauen | ❌ selbst bauen | ⚠ Result-Backend | ✅ [S] | ✅ [S] |
| K7 | Pools nach Region/Ressource | ✅ Spalte `pool` im Holen [A] | ✅ Queues [P] | ✅ Queues [P] | ✅ | ✅ | ✅ |
| K8 | globaler Deckel über Prozesse | ✅ [M2] | ❌ nur Worker × `concurrency` [P][A] | ❌ selbst bauen | ⚠ | ⚠ [S] | ⚠ [S] |
| K9 | Grenze je Host über Prozesse | ✅ [M6] | ❌ | ❌ | ❌ | ⚠ [S] | ❌ |
| K10 | Aufräumen nach Frist | ✅ mit Index [M5] | ⚠ `remove_old_jobs`, eigene Zeilen dazu [P] | ⚠ Archivtabelle [P] | ⚠ | ⚠ | ⚠ |
| K11 | Kettenregel Q4 | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| K12 | kein neuer Dienst, keine Verbindung nach außen | ✅ | ✅ [P] | ✅ | ❌ Redis | ❌ Engine; Rückruf nach außen [P] | ❌ Server |
| K13 | Lizenz | ✅ eigener Code | ✅ MIT | ✅ PostgreSQL, Apache-2.0 | ⚠ Redis-Server | ✅ | ✅ |
| K14 | Pflege, Abhängigkeiten | ⚠ eigener Code und eigene Tests | ⚠ 9 Releases/Jahr; „looking for maintainers“; +2 Pakete [P] | ⚠ +`orjson`; viel eigener Code | ⚠ | ⚠ viele Pakete | ⚠ Rust-Kern |
| K15 | kein Hash, keine AOI im Payload | ✅ Payload nur `jobID` und Zahlen [A] | ✅ Argumente frei wählbar | ✅ | ✅ | ✅ | ✅ |

---

## 5. Empfehlung: eigene schlanke Queue in `jobs` (E)

**Begründung [A]:**

- Was Procrastinate über E hinaus mitbringt (Wiederholungsstrategien,
  periodische Tasks, Ereignistabelle), braucht M4 nur in kleinem Umfang.
- Was M4 zusätzlich braucht (K6, K8, K9, ein harter Abbruch, Ablauf), bringt
  keine Bibliothek mit. Das müsste um Procrastinate herum gebaut werden, gegen
  dessen eigenes Abholen und dessen Worker-Modell.
- Die nötigen SQL-Anweisungen sind wenige und hier gemessen.
- Das Risiko von E sind subtile Nebenläufigkeitsfehler. M2 zeigt einen davon.
  Deshalb kommen in M4-08 Tests gegen echtes Postgres dazu, mit mehreren
  Prozessen; die CI hat Postgres schon (`adr/0002` §2;
  `.github/workflows/ci.yml` Z. 34–45 [P]).
- Die Nahtstelle `JobRunner` (7.5) hält den Wechsel offen: `api` reiht über
  `jobs` ein und liest über `jobs`. Ob dahinter E, Procrastinate oder später
  Kubernetes-Jobs für T3 stehen, ist dort gekapselt.

Die folgenden Abschnitte sind ein **Vorschlag für M4-08**, nicht gebaut.

### 5.1 Tabellen (Skizze)

Drei Tabellen im Schema `public` mit Präfix `earthx_`, wie die bestehenden
Migrationen (`catalog/migrations/005_geocode.sql` [P]). Sie sind getrennt nach
öffentlichem Job und internem Lauf (F6):

```sql
-- Rezept: angenommen von api, personenbezogen (Q8), 7 Tage (Q10)
CREATE TABLE public.earthx_recipe (
    recipe_id   text PRIMARY KEY,          -- token_urlsafe(16), nach außen (adr/0014 F15)
    body        jsonb NOT NULL,            -- Rezept mit ResolvedAsset (adr/0014 §4.1)
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);

-- Lauf: intern, je Cache-Schlüssel höchstens einer aktiv
CREATE TABLE public.earthx_run (
    run_id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    cache_key        text NOT NULL,        -- "c1:<hex>", nie nach außen (Q8)
    cacheable        boolean NOT NULL,     -- alle Eingaben mit Fassung (Q11)
    recipe_id        text NOT NULL REFERENCES public.earthx_recipe ON DELETE CASCADE,
    status           text NOT NULL CHECK (status IN ('accepted','running','successful','failed','dismissed')),
    pool             text NOT NULL DEFAULT 'default',
    priority         smallint NOT NULL DEFAULT 0,
    hosts            text[] NOT NULL,      -- Hosts der ResolvedAsset (K9)
    attempt          int NOT NULL DEFAULT 0,
    max_attempts     int NOT NULL DEFAULT 3,
    not_before       timestamptz NOT NULL DEFAULT now(),   -- Backoff
    progress         smallint NOT NULL DEFAULT 0,
    cancel_requested boolean NOT NULL DEFAULT false,
    worker           text,
    lease_until      timestamptz,
    error_kind       text,                 -- Fehlerklasse, kein Text mit URL
    result_ref       jsonb,                -- Verweis in den Speicher (adr/0015)
    created_at       timestamptz NOT NULL DEFAULT now(),
    started_at       timestamptz,
    finished_at      timestamptz,
    expires_at       timestamptz
);
CREATE INDEX ON public.earthx_run (pool, priority DESC, created_at) WHERE status = 'accepted';
CREATE INDEX ON public.earthx_run (lease_until) WHERE status = 'running';
CREATE INDEX ON public.earthx_run (recipe_id);                         -- M5: 232 s → 0,38 s
CREATE UNIQUE INDEX ON public.earthx_run (cache_key) WHERE status IN ('accepted','running');
CREATE INDEX ON public.earthx_run (cache_key, finished_at) WHERE status = 'successful' AND cacheable;

-- Job: öffentlich, ein Auftrag; OGC-Statusdokument liest den Lauf
CREATE TABLE public.earthx_job (
    job_id      text PRIMARY KEY,          -- token_urlsafe(16) (Q9, adr/0014 F15)
    run_id      bigint NOT NULL REFERENCES public.earthx_run ON DELETE CASCADE,
    recipe_id   text NOT NULL REFERENCES public.earthx_recipe ON DELETE CASCADE,
    dismissed   boolean NOT NULL DEFAULT false,
    created_at  timestamptz NOT NULL DEFAULT now(),
    expires_at  timestamptz NOT NULL
);
CREATE INDEX ON public.earthx_job (run_id);
CREATE INDEX ON public.earthx_job (recipe_id);
CREATE INDEX ON public.earthx_job (expires_at);
```

- **Annahme** in `api`, in **einer** Transaktion (K2):
  1. Rezeptzeile schreiben.
  2. Bei einem Treffer im Cache: Jobzeile auf den fertigen Lauf, fertig (F9).
  3. Sonst `INSERT … ON CONFLICT (cache_key) WHERE status IN
     ('accepted','running') DO NOTHING` für den Lauf. Wurde nichts eingefügt,
     den aktiven Lauf lesen (M5).
  4. Jobzeile auf den Lauf.
- **Lauf ohne Fassung:** Trägt eine Eingabe keine Fassung, ist
  `cacheable = false` (Q11). Der Lauf wird nie Treffer für Spätere. Gleich
  gleichzeitige Aufträge dürfen sich trotzdem anhängen, weil sie dieselbe
  Fassung „bei Annahme“ lesen [A].

### 5.2 Abholen mit Deckel und Grenze je Host

Zwei Anweisungen in einer Transaktion (M2, M6):

```sql
SELECT pg_advisory_xact_lock(<fester Schlüssel für jobs>);   -- Anweisung 1

WITH running AS (SELECT hosts FROM public.earthx_run WHERE status = 'running'),
next AS (                                                    -- Anweisung 2
    SELECT r.run_id FROM public.earthx_run r
    WHERE r.status = 'accepted' AND r.pool = ANY(%(pools)s) AND r.not_before <= now()
      AND (SELECT count(*) FROM running) < %(global_cap)s
      AND NOT EXISTS (SELECT 1 FROM unnest(r.hosts) h
                      WHERE (SELECT count(*) FROM running x WHERE h = ANY (x.hosts)) >= %(host_cap)s)
    ORDER BY r.priority DESC, r.created_at
    FOR UPDATE SKIP LOCKED
    LIMIT 1
)
UPDATE public.earthx_run r
SET status = 'running', attempt = r.attempt + 1, worker = %(worker)s,
    started_at = now(), lease_until = now() + make_interval(secs => %(lease)s)
FROM next WHERE r.run_id = next.run_id
RETURNING r.run_id, r.attempt, r.recipe_id;
```

- Die Sperre serialisiert nur die Entscheidung „wer darf als Nächstes“.
  Sie gilt bis zum Ende der kurzen Transaktion. Gemessen kostet sie kaum
  Durchsatz (M2).
- Wartet kein Job oder ist der Deckel voll, schläft der Aufseher, bis ein
  `NOTIFY` auf dem Kanal `earthx_jobs_wake` kommt. Den Weckruf senden
  Einreichen, Abschluss und Abbruch. Spätestens nach 5 s holt der Aufseher
  trotzdem (wie Procrastinate, `worker.py` Z. 29 [P]).
- Der Deckel steht in der Datenbank. Mehr Container erhöhen ihn also nicht
  still [A].

### 5.3 Worker-Hülle: Aufseher und Kindprozess je Job (F3)

```
worker-Container
└── Aufseher (jobs, psycopg; ein Prozess)
    ├── Slot 1: Kindprozess (spawn) → processing.worker_environment(); processing.run(recipe, workdir, progress)
    └── Slot 2: …
```

- **Der Aufseher:**
  - holt nach §5.2;
  - schreibt das Rezept in den Arbeitsordner;
  - startet das Kind mit `multiprocessing` im Modus `spawn`, ohne geöffnete
    Verbindung (M7, Nebenbefund);
  - erneuert alle 15 s die Lease;
  - schreibt den Fortschritt (§5.4);
  - lädt nach dem Ende hoch (Modul aus `adr/0015`);
  - schließt mit der Versuchsnummer ab (§5.6).
- **Das Kind** kennt weder Datenbank noch Queue noch Speicher (B9). Es
  bekommt Rezept, Arbeitsordner und eine Pipe für Fortschritt und
  Abbruchsignal. Das ist genau die Schnittstelle aus `adr/0014` §8: „`jobs`
  und der Runner … geben je Job nur Rezept, Arbeitsordner und
  Fortschrittsrückruf herein“. Der Runner (M4-16) ruft dieselbe Funktion ohne
  Aufseher.
- **Warum ein Prozess je Job [A]:**
  - Ein hängender oder zu langer Job lässt sich hart beenden. Ein Thread lässt
    sich das nicht (Procrastinate synchron: nur kooperativ [P]).
  - Speicher und GDAL-Cache eines Jobs gehen mit dem Prozess.
  - `processing.worker_environment()` gilt im Hauptthread des Kindes für den
    ganzen Prozess (`adr/0014` §3.6, §7.3). Der Aufseher braucht kein GDAL.
  - Ein Absturz des Kindes, etwa durch den OOM-Killer, ist für den Aufseher
    sofort sichtbar (Exit-Code) und wird nach §5.6 behandelt.
- **Kosten:** 1,0–1,5 s Start und 143 MB je Kind (M8). Ein Band-Math-Job über
  eine 8192²-Szene braucht lokal rund 10 s (`adr/0014` §3.5). Für Jobs im
  Bereich Sekunden bis Minuten ist das vertretbar [A]. Ein langlebiges Kind
  je Slot wäre schneller, verlöre aber die Abgrenzung zwischen Jobs.
- **Health:** Der Aufseher behält `/health` (heute `jobs/main.py`). „Gesund“
  heißt: Er hat in den letzten 30 s die Datenbank erreicht [A].

### 5.4 Fortschritt bis `api` (SSE, F7)

- **Wahrheit ist die Zeile:**
  - Der Aufseher schreibt `progress` (0–100) und sendet in **derselben**
    Transaktion `pg_notify('earthx_job_progress', '{"run":…,"p":…,"s":…}')`.
  - Gedrosselt auf höchstens eine Meldung je Sekunde und Lauf, außer bei
    Statuswechseln [A]. Bei Blöcken von 1024 px kommen sonst bis zu rund 7
    Meldungen je Sekunde (§3.5 in `adr/0014`: 9,8 s für 64 Blöcke).
  - Die Payload trägt die interne `run_id`, keine `jobID`, keinen Hash und
    keine AOI. Ein Kanal ist innerhalb der Datenbank für jede Sitzung
    lesbar; nach außen geht davon nichts.
- **`api`:**
  - Je Prozess eine eigene `LISTEN`-Verbindung außerhalb des Pools, wie
    Procrastinate es macht (`psycopg_connector.py` Z. 306 [P]).
  - Verteilt wird im Speicher an die SSE-Verbindungen des Prozesses, über
    `run_id` → `jobID`.
- **Route:** `GET /jobs/{jobID}/events` mit `text/event-stream`, gebaut auf
  `StreamingResponse` ohne neue Abhängigkeit [A].
  - Beim Verbinden erst `LISTEN`, dann die Zeile lesen und als erstes Ereignis
    senden (`listen.sgml` Z. 99–107 [P]). Wer zwischendurch weg war, verliert
    so nichts (M4).
  - Alle 15 s ein Kommentar als Lebenszeichen. Nach einem Endstatus schließt
    der Server.
- **Statusdokument:** Dazu trägt `GET /jobs/{jobID}` den Fortschritt im
  OGC-Statusdokument (`adr/0014` §9). Ein Client ohne SSE fragt dort.
- **Logs:** Kennung, Status und Zahlen, nie Rezept oder Hash
  (`adr/0014` §4.7).

### 5.5 Abbruch (K4)

`DELETE /jobs/{jobID}` (OGC `dismiss`) setzt `earthx_job.dismissed`. Hängt
kein anderer, nicht verworfener Job am Lauf, dann gilt:

- **wartend:** `UPDATE … SET status = 'dismissed' WHERE status = 'accepted'`,
  sofort.
- **laufend:**
  - `cancel_requested = true` und ein Weckruf.
  - Der Aufseher liest das Flag bei jeder Fortschrittsmeldung zurück
    (`UPDATE … RETURNING cancel_requested`, kein zusätzlicher Umlauf) und gibt
    es über die Pipe ans Kind.
  - Der Kern bricht im nächsten Block-Rückruf ab (`adr/0014` §7.2).
  - Endet das Kind nicht binnen 30 s, beendet der Aufseher es mit `SIGKILL`.
    Der Lauf endet als `dismissed`, ohne Wiederholung.
- Hängen weitere Jobs am Lauf, sieht nur der verwerfende Auftraggeber
  `dismissed`. Der Lauf rechnet für die anderen weiter (F6).

### 5.6 Wiederholung und Idempotenz (K5, F5, F8)

- **Abschluss:**
  - Er schirmt sich über die Versuchsnummer ab:
    `UPDATE … SET status = 'successful', result_ref = … WHERE run_id = … AND
    attempt = :mein_versuch AND status = 'running'`.
  - 0 Zeilen heißen: Der Lauf gehört inzwischen einem anderen Versuch. Das
    eigene Ergebnis wird verworfen (M3).
- **Hochladen:** unter einem Schlüssel aus interner `run_id` und Versuch, der
  nach außen nichts verrät.
  - Erst der Abschluss macht das Objekt zum Ergebnis.
  - Verwaiste Objekte verwerfen die Ablaufregeln des Speichers (`adr/0015`)
    [A].
- **Tote Worker:**
  - Lease 60 s, Heartbeat alle 15 s durch den Aufseher.
  - Ein Aufräumer in jedem Aufseher prüft alle 15 s
    `status = 'running' AND lease_until < now()`. Fällt ein Lauf darunter und
    bleiben Versuche übrig, wird er neu eingereiht, sonst `failed`.
  - Eine Session-Advisory-Lock würde einen beendeten Prozess in 13 ms
    erkennen (M3). Sie erkennt aber weder einen hängenden Prozess (M3) noch
    einen still verschwundenen Rechner vor rund 2 h (§3.2). Hinter einem
    Pooler im Transaktionsmodus gilt sie nicht [A]. Deshalb nur als Option
    in F5.
- **Wiederholung nur bei vorübergehenden Fehlern:**
  - Dazu zählen ein Abbruch des Workers (Lease, Kind-Absturz), eine
    Zeitüberschreitung der Quelle und eine `5xx`.
  - Backoff über `not_before`: 30 s × 2^(Versuch−1), mit ±20 % Jitter. Höchstens
    3 Versuche.
  - Nie wiederholt werden: eine Abweisung durch `gateway`, Fehler der
    Validierung, eine abweichende Skalierung (`adr/0014` F7a: der Job
    scheitert) und eine Überschreitung der Laufzeit. Die Fehlerklasse steht in
    `error_kind`, ohne URL (wie `gateway/errors.py`).
- **Laufzeitdeckel:** Ein Lauf, der länger als das Doppelte der Schätzung
  (`adr/0014` §5.5) und mindestens 10 min läuft, wird hart beendet [A]. Den
  festen Wert kalibriert M4-08 an echten Läufen.

### 5.7 Globaler Deckel und Rücksicht auf die Quellen (K8, K9, F4)

**Startwerte:**

| Wert | Start | Begründung [A] |
|---|---|---|
| gleichzeitige Läufe, global | **4** | Ein Lauf braucht 110–150 MB für das Lesen (`adr/0014` §3.5) und ein Kind mit 143 MB Grundlast (M8). 4 Läufe passen damit in rund 1,2 GB. Ein Lesethread je Lauf (`adr/0014` §7.2) heißt bis zu 4 Kerne; die Sitzung und GitHub-Runner haben 4. |
| gleichzeitige Läufe je Quell-Host | **2** | `gateway` erlaubt je Prozess 6 Verbindungen je Host (`gateway/policy.py` Z. 72, `adr/0005` §6 [P]). Mit 2 Läufen zu je einem Lesethread bleibt der Worker-Anteil je Host bei rund 2 gleichzeitigen Abrufen, neben `tiler` und `api`. Das schont kleine Anbieter wie `data.eodc.eu`. |
| Slots je Worker-Container | **2** | Lokal reicht ein Container. Mit 2 Containern ist der globale Deckel erreicht. |
| Lease / Heartbeat | 60 s / 15 s | Vier Heartbeats je Lease; ein verpasster schadet nicht |
| Abholen ohne Weckruf | alle 5 s | wie Procrastinate [P] |

- Alle Werte kommen aus Umgebungsvariablen. Nur der globale Deckel und die
  Grenze je Host stehen in der Abfrage (§5.2).
- **`RateSlot` als Vorbild (Auftrag des Plans):**
  - `PostgresRateSlot` ist ein gemeinsamer Zeiger je Quelle, der Abstände
    zwischen einzelnen Anfragen vergibt (`catalog/geocode_cache.py` Z. 81–102
    [P]).
  - Für die Lesezugriffe des Kerns passt das nicht. Sie stellt GDAL, und der
    Kern darf die Datenbank nicht erreichen (B9) [A].
  - Die Grenze greift deshalb je Lauf beim Abholen (M6).
  - Bleibt `RateSlot` das Muster für Anfragen, die `api` selbst stellt, etwa
    das `HEAD` für ein ETag bei der Annahme (`adr/0014` §4.6), wenn eine
    Quelle dort eine Rate verlangt [A].
- **Grenze der Grenze:**
  - Gezählt werden Läufe, nicht Verbindungen.
  - Hält GDAL je Lauf mehr als eine Verbindung offen, liegt die Zahl höher. Das
    belegt M4-08 mit einem Zähler im Test-Gateway [A].
  - Die eigentliche Durchsetzung bleibt der Egress-Proxy aus M6 (B8).

### 5.8 Aufräumen nach der Frist (K10, F9)

- **Ablaufzeiten:**
  - `earthx_run.expires_at = finished_at + 7 Tage`.
  - Job und Rezept laufen 7 Tage nach ihrem eigenen Abschluss ab (Q10).
  - Läufe, die nie fertig wurden, laufen 7 Tage nach `created_at` ab.
- **Aufräumen:**
  - Stündlich räumt ein Aufseher auf, geschützt durch `pg_try_advisory_lock`,
    sodass es nur einer tut.
  - Gelöscht wird in Stapeln von 5000: erst Jobs, dann Läufe ohne Job, dann
    Rezepte ohne Job.
  - Indizes auf allen Fremdschlüsseln sind Pflicht (M5: 232 s gegen 0,38 s).
- **Cache-Treffer:**
  - Ein Treffer gilt nur, wenn der fertige Lauf `cacheable` ist und
    `expires_at` noch mindestens 24 h entfernt liegt. Sonst wird neu
    gerechnet [A].
  - Grund: Der neue Job verweist auf das alte Objekt. Er darf nicht länger
    leben als das Objekt im Speicher, und eine signierte URL soll nicht kurz
    vor dem Löschen ausgegeben werden.
  - Die Regel am Bucket und ihr Beleg sind Sache von `adr/0015` (Q10,
    `adr/0012` §9 Punkt 5).

### 5.9 Fairness, Prioritäten, Pools (K3, K7) — vorbereitet, nicht gebaut

- **Fairness je Nutzer:** braucht Konten, also M6 (D6, Q9). Bis dahin gilt die
  Reihenfolge nach Priorität und Eingang.
  - Eine spätere Fairness passt in dieselbe Abfrage: höchstens n laufende je
    Konto, wie die Grenze je Host [A].
- **Priorität:** Die Spalte gibt es, in M4 ist sie immer 0. Free/Pro kommt mit
  M6.
- **Pools:** Die Spalte `pool` gibt es, in M4 heißt der einzige Pool
  `default`. Pools nach Region (12.2) und T3-Läufe über Kubernetes-Jobs (7.5)
  hängen später an derselben Nahtstelle.

---

## 6. Kettenregel, Einstieg, Migrationen

### 6.1 Vertrag in `.importlinter` (F2)

Vorschlag für M4-08, **nicht** in diesem PR umgesetzt:

```ini
[importlinter:contract:no-database-in-worker-core]
name = the worker core reaches no database (KLAERUNGEN B9, M4 Q4)
type = forbidden
source_modules =
    earthx.processing
forbidden_modules =
    psycopg
    psycopg_pool
    asyncpg
```

- **`earthx.jobs` fällt aus `source_modules` heraus** (Q4). Die Kette bleibt
  geprüft: Der Vertrag zählt weiter auch indirekte Importe. Damit fällt jede
  Kette `processing → … → psycopg` auf.
- **Neu verboten:**
  - `psycopg_pool` ist ein eigenes Paket neben `psycopg`.
  - `asyncpg` liegt im venv (über `stac-fastapi.pgstac`) [P].
  - Beide könnten `processing` sonst unbemerkt zur Datenbank bringen.
  - Eine Queue-Bibliothek kommt mit Empfehlung E nicht dazu. Mit F1 Option 2
    gehörte `procrastinate` in dieselbe Liste.
- **Vertrag `jobs`:** bleibt in M4-08 („jobs import only processing“). Das
  Modul für Plattformdienste aus `adr/0015` kommt dort mit M4-06 dazu, nicht
  hier.
- **Test:** `backend/tests/test_module_boundaries.py` Z. 130 prüft heute
  `{"jobs", "processing"}`. Die Zeile ändert sich mit, und der Test prüft
  zusätzlich `psycopg_pool` und `asyncpg`.

**Zeile `jobs` in 3.1 (Vorschlag):**

| Modul | Zuständig für | Darf importieren |
|---|---|---|
| `jobs` | Queue, Aufseher und Kindprozesse der Worker, Fortschritt, Abbruch, Ablauf, Ergebnisse | `processing`; psycopg (Q4); das Modul für Plattformdienste (`adr/0015`) |

### 6.2 Ort des Worker-Einstiegs (F10)

- **Heute:** `jobs/main.py`. Der Vertrag `jobs` verbietet `datasets`. Ein
  späterer Quad-Pol-Operator ließe sich dort nicht registrieren (`adr/0014`
  §12; offene Logzeile vom 02.10.2026).
- **Vorschlag:** ein Einstieg `earthx/api/worker_main.py` als
  Kompositionswurzel, wie `api/tiler.py` für den `tiler`.
  - Er baut die Operator-Registry; später gehört der Quad-Pol-Operator aus
    `datasets` dazu.
  - Er übergibt sie an `jobs.worker.run(operators=…, settings=…)`.
  - Das Kind startet über eine Funktion in derselben Datei. Sie ist für
    `spawn` importierbar und gibt die Registry an `processing.run` weiter.
  - `jobs` selbst importiert weiter nur `processing`. Keine Regel wird
    gelockert.
  - compose startet `worker` dann mit `python -m earthx.api.worker_main`.
    `/health` liefert der Aufseher aus `jobs`.

### 6.3 Migrationen (F11)

- **Ein Läufer:** `catalog/schema.py` hat eine Buchführung je Version und eine
  Folge von Dateien (`schema.py` Z. 29, 103 [P]). `catalog.load` wendet sie an
  (`catalog/load.py` Z. 22, 30 [P]).
- **`jobs` darf `catalog` nicht importieren.** Ein eigener Läufer in `jobs`
  wäre eine zweite Buchführung.
  - Ein eigenes Verzeichnis `jobs/migrations/` mit demselben Läufer stieße auf
    dessen Schlüssel: Er bucht nach `version` allein [P, Z. 40]. Zwei
    Verzeichnisse hätten also zwei `006`.
- **Vorschlag:** die Tabellen aus §5.1 als nächste Nummer in
  `catalog/migrations/` (`006_jobs.sql`), mit einem Kommentar, dass sie `jobs`
  gehören. `jobs` greift nur mit SQL darauf zu.
  - Eine eigene DB-Rolle je Komponente (architekturplan 10) bleibt Sache von
    M6.

---

## 7. Was dieses ADR nicht entscheidet

- Name, Client und Vertrag des Moduls für Plattformdienste, signierte URLs, die
  Ablaufregel am Bucket und ob ein Ergebnis ohne Fassung für den
  Auftraggeber gespeichert wird: `adr/0015`.
- Rezept, Hash, Kern, Kostenschätzung, Job-API: `adr/0014` (angenommen).
- Fairness je Konto, Quotas, Ratenbegrenzung je Nutzer oder IP: M6.
- Kubernetes-Jobs oder Argo für T3: M7.
- Aufbau des lokalen Runners: `adr/0016`.

## 8. Was M4-08 belegen muss

Tests gegen echtes Postgres, in CI und Sitzung (`adr/0002` §2):

1. **Deckel:** mehrere Prozesse, Deckel n → nie mehr als n laufend (Muster M2,
   mit Beobachter). Ein Gegentest zeigt, dass die Variante in einer
   Anweisung scheitert. So fällt ein Rückbau auf.
2. **Grenze je Host:** wie M6.
3. **Abschirmung:** Versuch 1 kann nach Neueinreihen nicht abschließen (M3).
4. **Toter Worker:** Kind mit `SIGKILL` → sofortige Behandlung; Aufseher weg →
   Neueinreihen nach Ablauf der Lease (mit kurzer Lease im Test).
5. **Gleiche Aufträge:** gleichzeitig eingereicht → ein Lauf; `DELETE` eines
   Jobs bricht den Lauf nicht ab, solange ein anderer daran hängt.
6. **Fortschritt:** SSE liefert den Stand der Zeile beim Verbinden und danach
   Ereignisse; ein Rollback erzeugt keines.
7. **Abbruch:** wartend sofort; laufend im nächsten Block; ein hängendes Kind
   wird nach der Frist beendet.
8. **Ablauf:** abgelaufene Zeilen verschwinden, nicht abgelaufene bleiben; ein
   Treffer mit weniger als 24 h Rest gilt nicht.
9. **Zweckfremde Nutzung:** fremde, falsch geformte oder abgelaufene `jobID` →
   `404`; keine Antwort und kein Log nennt Hash, AOI oder `href`.
10. **Kettenregel:** `lint-imports` mit dem Vertrag aus §6.1;
    `test_module_boundaries.py` angepasst.

---

## 9. Abweichung von `adr/0014`

`adr/0014` §9 sagt zu F15: „ein Job ist dagegen ein Lauf“. Mit F6 Option 1
ist ein Job ein Auftrag. Mehrere Aufträge können sich einen internen Lauf
teilen. Nach außen ändert sich nichts: Jeder Auftrag bekommt eine eigene
zufällige `jobID` mit eigenem Status und eigenem `dismiss`. Wählt Otto F6
Option 2, bleibt der Wortlaut von `adr/0014` unberührt.

---

## 10. Fragen an Otto

**F1 — Welche Queue?**
1. Eigene schlanke Queue auf Postgres in `jobs`, hinter `JobRunner` (§5) —
   **Empfehlung**
2. Procrastinate 3.10 (MIT, +`asgiref`, +`croniter`). Dazu kommen eigene
   Tabellen für Fortschritt und Ablauf, eine periodische Task für
   festhängende Jobs und ein Deckel nur über Worker × `concurrency`
3. pgmq als reines SQL, dazu eigene Logik für alles außer Abholen

**F2 — Vertrag für den Worker-Kern (§6.1)?**
1. `no-database-in-worker-core` nur noch für `processing`, verboten dort
   `psycopg`, `psycopg_pool`, `asyncpg`; Vertrag `jobs` bleibt; Zeile `jobs`
   in 3.1 wie in §6.1 — **Empfehlung**
2. Nur `earthx.jobs` aus `source_modules` streichen, sonst nichts
3. Wie 1, dazu ein neuer Vertrag: Datenbanktreiber nur in `catalog`, `jobs`,
   `api`, `discovery`

**F3 — Wie führt der Worker einen Job aus (§5.3)?**
1. Aufseher je Container, je Job ein frischer Kindprozess (`spawn`); hartes
   Beenden möglich; 1–1,5 s und 143 MB je Kind — **Empfehlung**
2. Ein langlebiges Kind je Slot (schneller, aber Zustand zwischen Jobs)
3. Threads im Worker-Prozess (kein hartes Beenden)

**F4 — Startwerte (§5.7)?**
1. Global 4 Läufe, je Quell-Host 2, 2 Slots je Container — **Empfehlung**
2. Vorsichtiger: global 2, je Host 1, 1 Slot
3. Großzügiger: global 8, je Host 4, 4 Slots

**F5 — Wie werden tote Worker erkannt (§5.6)?**
1. Lease 60 s mit Heartbeat 15 s durch den Aufseher, Abschluss mit
   Versuchsnummer — **Empfehlung**
2. Wie 1, zusätzlich eine Session-Advisory-Lock je Lauf als schneller Weg
   (13 ms nach Prozessende, M3); bricht hinter einem Pooler im
   Transaktionsmodus
3. Nur Advisory-Lock (erkennt hängende Worker nicht, M3)

**F6 — Gleiche Aufträge zur selben Zeit (§5.1, §5.5, §9)?**
1. Öffentlicher Job getrennt vom internen Lauf. Gleiche Aufträge hängen an
   einem Lauf; `DELETE` bricht den Lauf nur ab, wenn kein anderer Job daran
   hängt — **Empfehlung**
2. Jeder Auftrag rechnet selbst; der Cache greift erst nach einem Erfolg
3. Die vorhandene `jobID` zurückgeben. **Nicht empfohlen:** Wer das Rezept
   kennt, könnte fremde Jobs abbrechen

**F7 — Fortschritt (§5.4)?**
1. SSE `GET /jobs/{jobID}/events` aus `api`, je Prozess eine
   `LISTEN`-Verbindung, Zeile als Wahrheit, höchstens 1 Meldung je Sekunde und
   Lauf; zusätzlich `progress` im Statusdokument — **Empfehlung**
2. Kein SSE in M4, nur Abfragen von `GET /jobs/{jobID}`
3. SSE, aber `api` fragt die Zeile jede Sekunde ab statt `LISTEN`

**F8 — Wiederholung (§5.6)?**
1. Automatisch, höchstens 3 Versuche, nur bei vorübergehenden Fehlern, Backoff
   30 s × 2^(n−1) mit Jitter — **Empfehlung**
2. Keine automatische Wiederholung; der Nutzer startet neu

**F9 — Ablauf und Cache-Treffer (§5.8)?**
1. Zeilen laufen 7 Tage nach Abschluss ab; stündlich in Stapeln löschen; ein
   Treffer nur mit mindestens 24 h Restlaufzeit — **Empfehlung**
2. Ein Treffer verlängert die Frist des Ergebnisses (braucht ein Kopieren
   oder Neusetzen im Speicher, `adr/0015`)
3. Jeder Treffer gilt bis zum Ablauf; die signierte URL endet dann früher

**F10 — Ort des Worker-Einstiegs (§6.2)?**
1. Kompositionswurzel `api/worker_main.py`, Schleife in `jobs`; löst die
   offene Logzeile zu `datasets` ohne Lockerung — **Empfehlung**
2. Einstieg bleibt in `jobs/main.py`; der Quad-Pol-Operator wird später
   anders gelöst

**F11 — Wohin die Migration der Job-Tabellen (§6.3)?**
1. Nächste Nummer in `catalog/migrations/` (`006_jobs.sql`), ein Läufer, eine
   Folge — **Empfehlung**
2. Eigenes Verzeichnis `jobs/migrations/`; der Läufer bucht dann nach
   Verzeichnis und Version (Änderung an `catalog/schema.py`)

---

## 11. Quellen

**Im Repo:**
- `architekturplan.md` 0, 3.1, 3.2, 7.3–7.6, 10, 12.2–12.4, 15.2;
  `KLAERUNGEN.md` B8, B9.
- `adr/0002` §2; `adr/0005` §6; `adr/0012` F3, F5; `adr/0014` §3.5, §3.6,
  §4.4–§4.7, §5.5, §7.2, §7.3, §8, §9, §12–§14.
- `backend/earthx/jobs/main.py`; `docker-compose.yml` Z. 232–244;
  `.importlinter`; `backend/tests/test_module_boundaries.py` Z. 103–131.
- `backend/earthx/gateway/policy.py` Z. 72; `backend/earthx/gateway/client.py`
  Z. 103–107, 305–307 (Semaphore je Host und Prozess).
- `backend/earthx/catalog/geocode_cache.py` Z. 81–102;
  `backend/earthx/adapters/nominatim.py` Z. 129–145.
- `backend/earthx/catalog/schema.py` Z. 29, 40, 103; `backend/earthx/catalog/load.py`
  Z. 22, 30; `backend/earthx/catalog/migrations/005_geocode.sql`.
- `.github/workflows/ci.yml` Z. 25–55.

**Procrastinate** (Wheel 3.10.0 und Klon `58c4b34`):
- `METADATA` Z. 12–50.
- `procrastinate/sql/schema.sql` Z. 60–109, 210–262, 294–324, 404–430, 553–599.
- `procrastinate/worker.py` Z. 28–30, 43–65, 97, 335–357, 445–448, 481–490,
  541–544, 568–602.
- `procrastinate/manager.py` Z. 223–270.
- `procrastinate/psycopg_connector.py` Z. 55–63, 306.
- `procrastinate/utils.py` Z. 106–111.
- `procrastinate/retry.py` Z. 164, 188–208.
- `docs/discussions.md` Z. 128–130, 180–181, 199–231, 253–260, 307–308.
- `docs/howto/production/`: `schema.md`, `migrations.md`,
  `external_connection.md`, `retry_stalled_jobs.md`, `concurrency.md`,
  `delete_finished_jobs.md`.
- `docs/howto/advanced/`: `priorities.md`, `locks.md`, `queueing_locks.md`,
  `retry.md`, `cancellation.md`, `shutdown.md`, `cron.md`, `events.md`.

**pgmq** (Klon `8cc0959`):
- `LICENSE` Z. 1–3; `INSTALLATION.md` Z. 5–120; `UPDATING.md` Z. 11–48.
- `pgmq-extension/pgmq.control` Z. 2–6.
- `pgmq-extension/sql/pgmq.sql` Z. 7–14, 340–378, 580–710, 983–1070,
  1211–1219, 1702–1745.

**Celery** (Klon `6bc4220`):
- `LICENSE`.
- `docs/userguide/workers.rst` Z. 589–600.
- `docs/getting-started/backends-and-brokers/redis.rst` Z. 79–89, 307–322.
- `celery/app/defaults.py` Z. 269.

**Redis:** `redis/redis` `LICENSE.txt` Z. 3–5; `valkey-io/valkey` `COPYING`
Z. 1 (raw.githubusercontent.com).

**Hatchet** (Klon `caa973a`):
- `LICENSE`; `README.md` Z. 85–90; `docker-compose.release.yml` Z. 3–65.
- `pkg/config/server/server.go` Z. 395–428, 568, 896.
- `pkg/security/security.go` Z. 140–159.
- `sdks/python/hatchet_sdk/config.py` Z. 239, 320–330;
  `sdks/python/hatchet_sdk/embedded.py` Z. 24, 194–253.

**Temporal:** `temporalio/sdk-python` (Klon `d67e609`) `LICENSE`,
`.gitmodules`, `temporalio/runtime.py` Z. 499; `temporalio/temporal`
`LICENSE` und `schema/` (raw.githubusercontent.com).

**PyPI** (JSON-API, 02.10.2026): `procrastinate`, `asgiref`, `croniter`,
`pgmq`, `tembo-pgmq-python`, `celery`, `kombu`, `redis`, `hatchet-sdk`,
`temporalio`.

**PostgreSQL 16** (`postgres/postgres`, `REL_16_STABLE`,
`doc/src/sgml/`):
- `ref/select.sgml` Z. 1603–1611.
- `ref/notify.sgml` Z. 78–175.
- `ref/listen.sgml` Z. 40–107.
- `mvcc.sgml` Z. 1531–1552.
- `func.sgml` Z. 28590–28592, 28736–28752.
- `config.sgml` Z. 954–1062, 9346–9391.

**Linux:** `torvalds/linux` `Documentation/networking/ip-sysctl.rst`
Z. 593–605.

---

## 12. Messanhang

Die Skripte liegen nur im Kratzverzeichnis der Sitzung. Die tragenden
Abfragen stehen hier. Verbindung: Postgres der Sitzung, Benutzer und Passwort
wie in `scripts/setup-cloud-session.sh` (lokale Wegwerfwerte), eigene
Datenbanken:

```sh
psql -c "CREATE DATABASE m402_spike"; psql -c "CREATE DATABASE m402_procr"; psql -c "CREATE DATABASE m402_pgmq"
uv venv venv-spike -p 3.12
VIRTUAL_ENV=venv-spike uv pip install "psycopg[binary,pool]==3.3.6" procrastinate pgmq   # procrastinate 3.10.0, pgmq 1.1.4
```

### 12.1 Schema der eigenen Queue (Messung)

Wie §5.1, vereinfacht: eine Tabelle `spike.recipe` und eine Tabelle
`spike.job`, die Lauf und Job zusammenfasst. Spalten `job_id`, `recipe_id`
(FK mit `ON DELETE CASCADE`), `cache_key`, `status`, `priority`, `attempt`,
`max_attempts`, `progress`, `cancel_requested`, `hosts text[]`,
`lock_key bigint GENERATED ALWAYS AS IDENTITY`, `worker`, `lease_until` und
die Zeitstempel. Indizes: Holen (partiell `accepted`), Lease (partiell
`running`), `recipe_id`, `recipe.expires_at` und Unique `cache_key` (partiell
`accepted`/`running`). Dazu `spike.run_log(job_id, attempt, worker, t_start,
t_end)` mit Primärschlüssel `(job_id, attempt)` für den Nachweis „genau
einmal“ und die Überlappung.

### 12.2 M1

```sql
-- Holen
WITH next AS (SELECT job_id FROM spike.job WHERE status = 'accepted'
              ORDER BY priority DESC, created_at FOR UPDATE SKIP LOCKED LIMIT 1)
UPDATE spike.job j SET status = 'running', attempt = j.attempt + 1, worker = $1,
       started_at = clock_timestamp(), lease_until = clock_timestamp() + make_interval(secs => $2)
FROM next WHERE j.job_id = next.job_id RETURNING j.job_id, j.attempt, j.lock_key;
-- Abschluss mit Versuchsnummer
UPDATE spike.job SET status = $1, finished_at = clock_timestamp(), progress = 100, lease_until = NULL
WHERE job_id = $2 AND attempt = $3 AND status = 'running';
```

`m1_throughput.py 5000 4`: 5000 Einreichungen (Rezept + Job je Transaktion),
dann 4 Prozesse holen und schließen ab, bis nichts mehr wartet.

### 12.3 M2

- Variante „eine Anweisung“: CTE
  `gate AS (SELECT pg_advisory_xact_lock(4202))`, Zählen
  `FROM spike.job, gate` und Holen im selben `UPDATE`.
- Variante „zwei Anweisungen“: erst `SELECT pg_advisory_xact_lock(4202)`, dann
  das Holen mit `AND (SELECT count(*) FROM spike.job WHERE status='running') <
  $cap` in der Bedingung.
- `m2_cap.py one|two`: 8 Prozesse, Deckel 3, 120 Jobs zu 0,2 s.
- Gezählt wurde zweifach:
  - Höchste Überlappung der Intervalle in `run_log` (Selbstverbund über
    `b.t_start <= a.t_start AND b.t_end > a.t_start`).
  - Ein Beobachterprozess zählte in einer Schleife
    `count(*) WHERE status='running'`.

### 12.4 M3

- `m3_crash.py`:
  - Worker: Holen mit Lease 6 s, dann `SELECT pg_advisory_lock(lock_key)`;
    Heartbeat alle 2 s:
    `UPDATE … SET lease_until = clock_timestamp() + 6 s WHERE job_id = … AND
    attempt = … AND status = 'running'`.
  - Beobachter alle 10 ms: `pg_try_advisory_lock(lock_key)` (bei Erfolg
    sofort `pg_advisory_unlock`) und `lease_until < clock_timestamp()`.
  - Drei Läufe mit `SIGKILL`, einer mit `SIGSTOP`.
- Nach `SIGSTOP`:
  - Neueinreihen über
    `UPDATE … SET status='accepted' WHERE status='running' AND lease_until <
    clock_timestamp()`.
  - Ein zweiter Worker holt und schließt ab, dann `SIGCONT`.
  - Der erste Worker versucht den Abschluss mit Versuch 1 (`rowcount` 0).

### 12.5 M4

`m4_progress.py`:
- Je Ereignis eine Transaktion aus
  `UPDATE spike.job SET progress = … WHERE job_id = …` und
  `SELECT pg_notify('job_progress', '{"job":…,"p":…,"t":<Sendezeit>}')`.
- Der Zuhörer hört mit `LISTEN job_progress` in einem eigenen Prozess (psycopg
  `notifies()`) und rechnet die Latenz gegen die Sendezeit; beide auf
  demselben Rechner.
- Rollback: `pg_notify` in einer Transaktion, die mit einer Ausnahme endet.
- Payload: Füllfeld mit 7900 bzw. 8100 Zeichen.
- Lücke: 5 Ereignisse, dann ein neuer Zuhörer mit 1 s Wartezeit.

### 12.6 M5

`m5_dedupe_cleanup.py`:

- **Gleiche Aufträge:**

  ```sql
  INSERT INTO spike.job (job_id, recipe_id, cache_key, status, expires_at)
  VALUES ($1, $2, 'same-key', 'accepted', now() + interval '7 days')
  ON CONFLICT (cache_key) WHERE status IN ('accepted','running') DO NOTHING
  RETURNING job_id;
  ```

  Gestartet von 8 Prozessen auf einen gemeinsamen Zeitpunkt; ohne Rückgabe
  liest der Prozess den aktiven Job.
- **Aufräumen:**
  - 100 000 Rezepte und Jobs über `generate_series`, jedes zweite
    abgelaufen, dann `ANALYZE`.
  - Gelöscht wird in einer Schleife mit
    `DELETE FROM spike.recipe WHERE recipe_id IN (SELECT recipe_id FROM
    spike.recipe WHERE expires_at < now() LIMIT 5000)`, die Jobs folgen über
    `ON DELETE CASCADE`.
  - Erster Lauf ohne Index auf `spike.job(recipe_id)`, zweiter mit.

### 12.7 M6

`m6_host_cap.py`: Abfrage wie §5.2 (ohne `pool`, `not_before`) auf
`spike.job`; 8 Prozesse, global 4, je Host 2, 150 Jobs zu 0,15 s, Hosts
`a.example`, `b.example`, `c.example` (Zufall mit festem Startwert 1, jeder
vierte Job zwei Hosts); ein Beobachter zählte laufende Jobs je Host.

### 12.8 M7 (Procrastinate)

- App mit `PsycopgConnector` auf `m402_procr`, Schema per
  `schema_manager.apply_schema_async()`.
- `p1_throughput.py 5000 4`:
  - 5000 × `defer_async()` auf einen leeren async-Task, dann
    `run_worker_async(concurrency=4, wait=False)`.
  - Danach eine eigene Zeile und
    `tasks["noop"].configure(connection=conn).defer_async()` in einer
    Transaktion, die zurückgerollt wird.
- `p2_crash_abort.py`:
  - Ein Worker als eigener Prozess (`spawn`) startet einen Job mit
    `asyncio.sleep(600)`.
  - `SIGKILL`, dann alle 0,5 s `job_manager.get_stalled_jobs()` (Vorgabe 30 s
    seit Heartbeat), danach `retry_job()`.
  - Abbruch:
    `cancel_job_by_id_async(id, abort=True)` je für einen async-Task und einen
    sync-Task mit `should_abort()` alle 50 ms.

### 12.9 pgmq

```sh
psql -d m402_pgmq -v ON_ERROR_STOP=1 -f pgmq-extension/sql/pgmq.sql   # Klon 8cc0959, Version 1.13.1
```

```sql
SELECT pgmq.create('jobs');
SELECT pgmq.send('jobs', '{"job":"x"}');
SELECT msg_id, read_ct FROM pgmq.read('jobs', 3, 1);   -- 1, 1
SELECT count(*) FROM pgmq.read('jobs', 3, 1);          -- 0 (unsichtbar)
SELECT pg_sleep(3.2);
SELECT msg_id, read_ct FROM pgmq.read('jobs', 3, 1);   -- 1, 2
```

### 12.10 M8

Im Projekt-venv, viermal:

```python
subprocess.run([sys.executable, "-c", "import numpy, rasterio, rio_tiler.io, xarray, zarr, numexpr, "
                "earthx.access.resolve, earthx.readers"], check=True)
```

Gemessen wurden Wandzeit und `ru_maxrss` des Kindes (rasterio 1.5.2, GDAL
3.12.2).
