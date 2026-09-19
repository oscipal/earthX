# M1-08 — compose-Topologie und CI-Job: Plan

**Bezug:** `docs/plans/m1-fundament.md` M1-08. Stufe B — dieser Plan liegt im
Draft-PR, Umsetzung folgt erst nach Ottos OK.
**Abhängigkeit:** M1-02 (Paketgerüst `earthx`, scharfe Importregeln) — bereits
gemergt (PR #18).
**Grundlage:** `architekturplan.md` 3.2, 6.5 (nur als Randbedingung: Gateway
selbst ist nicht Teil dieser Aufgabe), 7.3, 12.1; `adr/0002` (Testaufteilung);
`docs/cloud-umgebung.md` (was in der Cloud-Sitzung tatsächlich funktioniert).

---

## 1. Ziel

`docker compose up` startet vier Prozesse aus **einem** Image mit vier
Startbefehlen (`api`, `tiler`, `worker`, `harvester`) plus Postgres mit PostGIS
und pgstac-Schema plus MinIO. `tiler`, `worker`, `harvester` sind reine Hüllen:
sie starten, melden sich über `/health` gesund und tun sonst nichts. `api`
bekommt in M1-08 ebenfalls nur `/health` — die eigentliche STAC-API kommt erst
mit M1-07, das denselben Prozess weiter ausbaut.

Wichtige Randbedingung aus `adr/0002` §1 und `cloud-umgebung.md` §4: **Docker
läuft in dieser Cloud-Sitzung nicht** (jeder `docker pull`/Build scheitert an
403 auf die Blob-CDNs). Diese Sitzung kann `docker compose up` deshalb nicht
selbst ausführen — nur Dateien schreiben und sie über den neuen CI-Job prüfen
lassen. Das ist keine Einschränkung dieser Aufgabe, sondern der Normalfall
laut ADR.

## 2. Geplante Struktur

### 2.1 Ein Image: `backend/Dockerfile`

- Basis `python:3.11-slim` (passt zu `environment.yml`s `python=3.11` und zu
  dem, was in der Cloud-Sitzung und in CI bereits per pip funktioniert —
  `cloud-umgebung.md` §3: die Wheels bringen ihr eigenes GDAL mit, kein
  System-GDAL nötig).
- Installiert `backend/requirements.txt` (Produktionsabhängigkeiten, nicht
  `-dev`).
- Kopiert nur `backend/earthx/` und `backend/app/` (der Prototyp bleibt im
  Image vorhanden, aber kein Compose-Service startet ihn) plus die
  installierten Abhängigkeiten. `backend/tests/` und `.venv` bleiben draußen.
- Kein `CMD`/`ENTRYPOINT` im Dockerfile selbst — jeder Compose-Service setzt
  seinen eigenen `command:`. Das ist wörtlich "ein Image, vier Startbefehle".
- Neue `.dockerignore` (`.venv`, `__pycache__`, `frontend/`, `backend/tests/`,
  `.git`, `cache/`, `data/`) hält den Build-Kontext klein.

### 2.2 Vier Prozess-Einstiegspunkte, je im Modul, das den Prozess später trägt

Damit später kein Umzug nötig ist, liegt jeder Health-Stub schon in dem Modul
aus `architekturplan.md` 3.1, das die jeweilige Prozesslogik übernehmen wird:

| Prozess | Datei | Modul-Begründung (3.1) |
|---|---|---|
| `api` | `backend/earthx/api/main.py` | „HTTP-Routen, setzt alles zusammen" |
| `tiler` | `backend/earthx/access/main.py` | „Tiles, Quicklooks, Statistik, Download-Vermittlung" |
| `worker` | `backend/earthx/jobs/main.py` | „Queue, Worker, Fortschritt, Ergebnisse" |
| `harvester` | `backend/earthx/discovery/main.py` | „Harvester, Normalisierung, Verifikation, Review" |

Jede Datei ist eine eigenständige, absichtlich kleine FastAPI-App (keine
gemeinsame Hilfsfunktion in einem neuen Modul — das würfe sonst selbst eine
Importgrenzen-Frage auf, für vier Zeilen Code):

```python
from fastapi import FastAPI

app = FastAPI(title="earthx-<prozess>")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "<prozess>"}
```

Start jeweils über `uvicorn earthx.<modul>.main:app --host 0.0.0.0 --port 8000`
(intern immer Port 8000, extern über die Compose-Portzuordnung unterschieden).
`fastapi`/`uvicorn` sind bereits Abhängigkeiten (aus dem Prototyp), keine neue
Bibliothek nötig.

### 2.3 `docker-compose.yml` (Repo-Wurzel)

| Service | Image/Build | Zweck | Healthcheck |
|---|---|---|---|
| `postgres` | `postgis/postgis:16-3.4` | Postgres 16 + PostGIS 3.4, wie in `cloud-umgebung.md` §5 gemessen | `pg_isready` |
| `pgstac-migrate` | `build: backend/Dockerfile`, `command: pypgstac migrate`, Version exakt gepinnt in `backend/requirements.txt` (einzige Pin-Stelle, `docker-compose.yml` nennt keine eigene Version) | einmalig, `depends_on: postgres (healthy)`, `restart: "no"` | keiner (Job endet) |
| `minio` | `quay.io/minio/minio:RELEASE.2025-04-08T15-41-24Z` (gepinnt statt `latest`; Docker Hub führt `minio/minio` nicht mehr, siehe Umsetzungsnotiz unten) | S3-kompatibler Objektspeicher | `curl -f http://localhost:9000/minio/health/live` |
| `api` | `build: backend/Dockerfile`, `command: uvicorn earthx.api.main:app --host 0.0.0.0 --port 8000` | Hülle mit `/health` | `curl -f http://localhost:8000/health` |
| `tiler` | dieselbe Basis, `command: uvicorn earthx.access.main:app ...` | Hülle | dito |
| `worker` | dieselbe Basis, `command: uvicorn earthx.jobs.main:app ...` | Hülle | dito |
| `harvester` | dieselbe Basis, `command: uvicorn earthx.discovery.main:app ...` | Hülle | dito |

- Konfiguration ausschließlich über `${VAR}`-Referenzen aus `.env`
  (`POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `MINIO_ROOT_USER`,
  `MINIO_ROOT_PASSWORD`); keine Literale in `docker-compose.yml`.
- Host-Portzuordnung (nur lokal relevant): `api` 8000, `tiler` 8001, `worker`
  8002, `harvester` 8003, `postgres` 5432, `minio` 9000/9001.
- `api`/`tiler`/`worker`/`harvester` erhalten `depends_on: postgres, minio
  (healthy)`, obwohl sie in M1 noch nichts damit tun — das entspricht der
  Zieltopologie aus `architekturplan.md` 12.1 und erspart eine spätere
  Compose-Änderung, wenn M1-04 ff. echte Anbindung bringen.

**Offener Punkt für Otto (siehe Abschnitt 4a):** pgstac-Migration jetzt schon
in Compose, oder Postgres in M1-08 nur mit PostGIS starten und die
pgstac-Migration M1-04 überlassen?

### 2.4 `.env.example` (Repo-Wurzel)

Nur Platzhalter, keine echten Werte (Aufgabentext „Keine Secrets" +
`ENTSCHEIDUNGEN` §4):

```
POSTGRES_USER=earthx
POSTGRES_PASSWORD=changeme
POSTGRES_DB=earthx
MINIO_ROOT_USER=earthx
MINIO_ROOT_PASSWORD=changeme12
```

`.env` selbst ist bereits über `.gitignore` ausgeschlossen. CI setzt eigene
Wegwerfwerte im Workflow (kein Bezug auf `.env.example`-Inhalte nötig).

### 2.5 CI-Job `compose-topology` in `.github/workflows/ci.yml`

Neuer Job, läuft auf jedem PR (ausdrücklich erlaubt laut Aufgabentext):

1. Checkout.
2. `docker compose build`.
3. `docker compose up -d` mit Wegwerf-Env-Werten aus dem Workflow.
4. Warteschleife (kurzes Retry, kein `sleep`-Rennen), die `docker compose ps`
   und die vier `/health`-Endpunkte sowie Postgres/MinIO-Health abfragt, bis
   alle gesund sind oder ein Timeout greift.
5. Neustart-Test für die Abnahme „Neustart eines einzelnen Dienstes lässt die
   anderen gesund": `docker compose restart worker`, dann erneut alle
   Healthchecks prüfen.
6. `docker compose logs` bei Fehlschlag ausgeben (Diagnose), danach
   `docker compose down -v`.

Das ist die einzige Stelle, an der diese Aufgabe überhaupt lauffähig geprüft
wird — die Cloud-Sitzung kann Schritt 2–3 nicht selbst nachvollziehen
(Abschnitt 1).

## 3. Nicht Teil dieser Aufgabe

- Echte Logik in `tiler`/`worker`/`harvester` (bleibt bis M2/M4/M5 aus).
- STAC-API-Inhalt in `api` (M1-07).
- pgstac-Collection-Daten (Sentinel-2 L2A, M1-04).
- Fetch-Gateway (M1-03).
- Erweiterung der Cloud-Sitzungs-Allowlist um Docker-Registry-Hosts — laut
  `cloud-umgebung.md` §7 Empfehlung „vorerst nein", hier nicht neu aufgeworfen.
- `backend/app/` bleibt unverändert; kein Compose-Service startet den
  Prototyp.

## 4. Offene Punkte, um die diese Aufgabe ausdrücklich Otto bittet (Stufe B)

**a) pgstac-Migration schon in M1-08 oder erst in M1-04?**
Der Aufgabentext sagt „Postgres mit pgstac"; das spräche für den
`pgstac-migrate`-Service oben. Das zieht aber `pypgstac[psycopg]` als neue
Abhängigkeit in `backend/requirements.txt`, obwohl M1-08 sonst reine Plumbing-
Arbeit ist und die eigentliche Nutzung von pgstac erst mit M1-04 kommt.
*Empfehlung:* jetzt schon migrieren (einmaliger Service, gepinnt auf **pgstac
0.9.12** wie in `cloud-umgebung.md` §5 gemessen) — sonst behauptet die
Abnahme „Postgres mit pgstac", ohne dass es zutrifft, und M1-04 müsste die
Compose-Datei ohnehin wieder anfassen.

**b) MinIO-Version.**
Vorschlag oben ist ein Platzhalter-Tag; ich habe keine bereits im Projekt
festgelegte MinIO-Version gefunden. Otto kann ein bestimmtes Release
vorgeben, sonst wird beim Umsetzen die zu diesem Zeitpunkt aktuelle stabile
Version gepinnt (nie `latest`, gleiche Begründung wie bei den Runner-Images
in `architekturplan.md` 7.7).

**c) FastAPI für alle vier Hüllen statt eines schlankeren Health-Servers?**
`fastapi`/`uvicorn` sind ohnehin Abhängigkeiten; das hält die vier Prozesse
einheitlich und macht `tiler`/`worker`/`harvester` einfach erweiterbar, wenn
ihre Module Fachcode bekommen. Alternative wäre ein Ein-Zeiler ohne Framework
— spart nichts Nennenswertes, verhält sich aber uneinheitlich zu `api`.

**d) Ports 8000–8003 für den lokalen Zugriff** — nur eine Namensfrage, überall
anpassbar, falls ein anderes Schema gewünscht ist.

## 5. Abnahme (unverändert aus dem Aufgabentext)

- CI-Job `compose-topology` grün.
- Neustart eines einzelnen Dienstes lässt die anderen gesund.

## 6. Nächster Schritt

Nach Ottos OK zu Abschnitt 4 (oder Bestätigung der Empfehlungen): Umsetzung in
diesem PR nachreichen, dann Testlauf über den neuen CI-Job — nicht lokal, aus
den in Abschnitt 1 genannten Gründen.

## 7. Umsetzung: Abweichung vom Plan

Der erste CI-Lauf ist am Image-Pull gescheitert: `minio/minio` gibt es auf
Docker Hub nicht mehr (`pull access denied ... repository does not exist`).
MinIO veröffentlicht seine Images inzwischen nur noch unter
`quay.io/minio/minio`, mit denselben Release-Tags. `docker-compose.yml` ist
entsprechend korrigiert.

Zweite Korrektur, von Otto angestoßen: `backend/requirements.txt` hatte
`pypgstac[psycopg]>=0.9,<0.10` — eine Spannbreite, kein exakter Pin, obwohl
Abschnitt 2.3 hier „gepinnt auf pgstac 0.9.12" behauptete. `docker-compose.yml`
selbst nennt keine eigene pgstac-Version (`pgstac-migrate` läuft schlicht mit
dem, was im Image installiert ist); `requirements.txt` ist also tatsächlich
die einzige Stelle — sie musste nur exakt werden. Jetzt `pypgstac[psycopg]==0.9.12`.
