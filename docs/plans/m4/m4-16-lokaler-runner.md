# M4-16 — Lokaler Runner offline, Vergleichstest in der CI

**Stand:** 20.10.2026, Plan zur Freigabe durch Otto.
**Stufe B:** Bis zur Freigabe ist kein Produktivcode geändert. Nach der Freigabe
setzt dieselbe Session um (oder die Sessions aus Frage 5).
**Modell:** Opus für den Plan, Sonnet (Effort hoch) für die Umsetzung.
**Startsatz:** „Führe Aufgabe M4-16 aus `docs/plans/m4/m4-processing-kern.md` aus.“
**Grundlage:**
- `plans/m4/m4-processing-kern.md` M4-16, Q11, Q12, §1.2, §1.3 („Vor M4-16“).
- `adr/0016` (angenommen 06.10.2026, F1–F11 je Option 1, Auflagen §12a).
- `adr/0014` §4.1–§4.3, §6.3, §6.4, §10.1, §15c, §15d, §15f, §15g.
- `KLAERUNGEN.md` B8, B9; `architekturplan.md` 3.1, 7.7.

Belegstufen wie in `adr/0009`: [M] gemessen, [P] am Primärdokument oder im
Code gelesen, [A] eigene Ableitung.

**Kurzfassung.**

- Der Runner wird ein neues Modul `earthx.runner` mit den Unterbefehlen `run`,
  `check` und `versions`, eine Build-Stufe `runner` im bestehenden
  `backend/Dockerfile` und ein Vergleichstest Job-Kind gegen Runner in
  `pytest`. So hat es `adr/0016` entschieden; hier steht nur, wie.
- Vier Stellen in `adr/0016` passen nicht zum Code, wie er seit M4-08b,
  M4-11a und M4-14 ist (§2). Daraus folgen die Fragen 2, 3, 4 und 6.
- Docker läuft in der Session, `docker pull` geht, der `apt`-Schritt des
  `Dockerfile` scheitert weiter an den Debian-Spiegeln [M] (Frage 1).
- Der Umfang liegt bei rund 1000 geänderten Zeilen, davon etwa 450 Tests
  (Frage 5).

---

## 1. Was schon entschieden ist

| `adr/0016` | Inhalt | wird hier so umgesetzt |
|---|---|---|
| F1 | eigene Stufe `runner` im selben `Dockerfile`, `USER 10001`, `ENTRYPOINT`; compose baut `target: app` | §3.5 |
| F2 + Auflage | Modul `earthx.runner`, darf nur `processing` und `catalog.datasets`; Kettenvertrag ohne `psycopg`, `psycopg_pool`, `asyncpg`, `earthx.objectstore`, `botocore`; Test auf `sys.modules` | §3.6, §3.7 |
| F3 | nur vorhandene `recipe.json`, dieselben strikten Modelle, R5; kein neuer Endpunkt | §3.2 |
| F4 | Hosts des Rezepts, zusätzlich gegen `asset_hosts` der Registry im Image; vor dem Lesen genannt | §3.3 |
| F5 | neuer Ordner je Lauf mit zufälligem Namen, nie überschreiben, `provenance.json` | §3.4 |
| F6 | kein Cache-Volume | nichts zu bauen |
| F7 | `pytest` mit zwei Einstiegen in `spawn`-Prozessen, ohne gespeicherten Hash; Prüfung der Stufe im Compose-Job | §3.7, §3.8 |
| F8 + Auflage | bitgleich auf derselben Maschine; R5 eingeengt (seit M4-09 umgesetzt) | Testrezepte nur aus der R5-Liste |
| F9 | x86_64; ARM nativ außerhalb der Bitgleich-Zusage | Anleitung, `platform` in `provenance.json` |
| F10 + Auflage | Tag `earthx-runner:<version>`, `runner_version` = `<version>+g<commit>`; `__version__` gibt es seit M4-07a (heute `0.4.1`) | §3.4, §3.5 |
| F11 | `python:3.12-slim` per Digest, für alle vier Dienste | §3.5 |
| Kleinentscheidungen | Exit-Codes 0/2/3/4/5, UID 10001, Befehle in einer Zeile, Hinweise zu WSL2 und Docker Desktop | §3.1, §3.9 |

---

## 2. Befunde aus dem Code

### 2.1 Jede `recipe.json` trägt einen Block `provenance` [P]

- Job: `processing.recipe.job_recipe_document` schreibt
  `{…Rezept…, "provenance": {execution: "cloud", kind: "job", engine, scaling,
  started, finished, attribution}}`. `api` liefert genau das unter
  `/results/recipe.json` und im `result.zip`
  (`api/processing_route.py::_recipe_bytes`).
- Export-Job und synchroner Zuschnitt: derselbe Block, `kind` `job` bzw.
  `sync-download` (`adr/0014` §10.1, §15f).
- `adr/0016` §7.2 verlangt „Provenienzfelder in der Eingabe → Exit-Code 2“.
  Wörtlich genommen nähme der Runner keine einzige echte `recipe.json` an.
  → **Frage 3.**

### 2.2 Was ein Raster-Job in der Cloud liefert [P]

- Der Kern schreibt nur `result.tif` und `mask.tif`
  (`jobs/worker.py::RESULT_FILES`). `recipe.json` baut `api` beim Abruf,
  `citation.bib` steht nur im `result.zip`, das `api` aus der Registry
  zusammensetzt (`api/citation.py`). Eine Datei `attribution.txt` gibt es bei
  Raster-Jobs nicht; die Attribution steht in `provenance.attribution`.
- `adr/0016` F5 sagt „dieselben Dateien wie in der Cloud“ und nennt
  `citation.bib` und `attribution.txt`. Der Runner darf weder `api` noch
  `access` importieren (F2) und kann `citation.bib` deshalb nicht selbst bauen.
  → **Frage 4.**

### 2.3 Die Ausgabe `crop` braucht Beilagen aus `api` [P]

- `processing.run` rechnet `crop` nur mit `Attachments`: `ATTRIBUTION.txt`,
  `citation.bib`, `aoi.geojson` und die Attribution, fertig gebaut von `api`
  (`processing/export.py`, M4-11a K3).
- Im Runner gäbe es sie nur aus den Dateien neben der `recipe.json`, also aus
  dem entpackten ZIP. Geprüft wären sie dann nicht.
- Raster-Rezepte, auch das Mosaik eines Überflugs (M4-12a), brauchen keine
  Beilagen. → **Frage 2.**

### 2.4 Ohne Netz meldet der Kern „rejected“, nicht „Quelle nicht erreichbar“ [P]

- Im Compose-Job soll `run` unter `--network none` mit Exit-Code 4 enden
  (`adr/0016` §7.2).
- Tatsächlich scheitert zuerst die Namensauflösung in `gateway`:
  `resolve_host` wirft `AddressRejected("host does not resolve")`, ein
  `GatewayError`. `readers.source_failure_kind` nennt das `rejected`
  (`gateway/resolver.py`, `readers/failures.py`).
- Der Runner sieht nur diesen Namen (`processing.failure_kind`), weil er
  `gateway` nicht importieren darf. → **Frage 6.**

### 2.5 Hostprüfung ohne `gateway` [P]

- `api` prüft die Hosts mit `gateway.inspect_url` gegen `asset_hosts`
  (`api/intake.py::check_recipe_hosts`). Der Runner darf `gateway` nicht
  importieren.
- Auch `readers` und `urllib` sind ihm verboten (Vertrag `runner`,
  `http-only-in-gateway`). `processing` bietet heute nur `recipe_hosts` für
  das ganze Rezept an, nicht je Eingabe.
- Vorschlag: eine kleine Funktion `input_hosts(entry)` in
  `processing/recipe.py` neben `recipe_hosts`, beide über `readers.hosts_for`.
  Der Runner vergleicht damit je Eingabe mit `asset_hosts` des Datensatzes.
  Schema, öffentliche Adresse und Port prüft danach `check_url` beim Lesen,
  wie in jedem Job (B9).

### 2.6 Import des Runners [M]

- In einem frischen Prozess laden `earthx.processing`,
  `earthx.processing.recipe` und `earthx.catalog.datasets` zusammen keines der
  fünf Module (`psycopg`, `psycopg_pool`, `asyncpg`, `botocore`,
  `earthx.objectstore`), wenn `boto3` fehlt wie im Image.
- Im Dev-venv ist `boto3` installiert. rasterio lädt es dann und mit ihm
  `botocore`. Der Test versteckt `boto3` deshalb wie
  `tests/earthx/jobs/child_targets.py::probe_modules`.

### 2.7 Docker in der Session [M]

- `sudo dockerd` startet. `docker pull python:3.12-slim` geht: Index-Digest
  `sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`,
  darin Python 3.12.15 und glibc 2.41, wie in `adr/0016` §3.1 gemessen.
- `deb.debian.org` und `security.debian.org` lehnt der Proxy ab
  (`connect_rejected`). Der `apt`-Schritt des `Dockerfile` scheitert also wie
  am 05.10.2026. → **Frage 1.**

---

## 3. Entwurf

### 3.1 Modul `earthx.runner`

```
backend/earthx/runner/
  __init__.py      Docstring, importiert nichts
  __main__.py      python -m earthx.runner → cli.main()
  cli.py           argparse: run, check, versions; Exit-Codes
  recipe_file.py   recipe.json lesen und prüfen, Hosts gegen die Registry
  output.py        Laufordner, Dateien, provenance.json
```

- `main(argv, *, registry=REGISTRY) -> int`. Die Registry ist ein Parameter,
  damit der Vergleichstest einen synthetischen Eintrag übergibt, ohne zu
  patchen.
- **`check <recipe.json>`:** lesen, prüfen, Hosts nennen (einer je Zeile auf
  stdout), nichts lesen, Exit 0.
- **`run <recipe.json> [--out /out]`:** wie `check`, dann im Hauptthread
  `with processing.worker_environment(): processing.run(...)`. Fortschritt als
  eine Zeile je 10 % auf stderr; am Ende der Name des Laufordners auf stdout.
- **`versions`:** JSON auf stdout: `engine_versions()`, `runner_version`,
  `platform`.
- **Exit-Codes** (Zuordnung über `processing.failure_kind`, eine Tabelle in
  `cli.py`):

| Code | wann |
|---|---|
| 0 | fertig |
| 2 | Rezept ungültig: kein I-JSON, Modellfehler, `recipe_version` oder `op_version` unbekannt, Ausdruck außerhalb R5, Ausgabe, die der Runner nicht rechnet (Frage 2) |
| 3 | Prüfung vor dem Lesen: Datensatz nicht in der Registry dieses Images, Host nicht in seinen `asset_hosts`, Adresse ohne Host |
| 4 | beim Lesen: Quelle nicht erreichbar, Zeitüberschreitung, HTTP-Fehler, Ablehnung durch `gateway` (Frage 6) |
| 5 | alles andere: `scaling_mismatch`, `grid_mismatch`, `aoi_outside_inputs`, `out_of_memory`, `unknown`; Ausgabeordner vorhanden oder nicht beschreibbar |

- Jede Meldung ist eine englische Zeile mit dem Namen aus `failure_kind` und
  der Version des Runners, wo sie hilft („this runner (0.4.1) runs
  recipe_version 1“). Nie eine Adresse, nie eine Koordinate, nie ein Hash.
- Logging: die Warnungen des Kerns als Text auf stderr. Der Kern loggt weder
  AOI noch Adresse (`adr/0014` §4.7).

### 3.2 `recipe.json` lesen (F3)

1. Bytes lesen, höchstens 4 MiB (Body eines Auftrags 1 MiB plus Footprints und
   `resolved`). Mehr → Exit 2.
2. `loads_i_json` (doppelte Schlüssel, `NaN`, Zahlen außerhalb float64).
3. Den Block `provenance` abtrennen und behandeln wie in Frage 3.
4. Den Rest mit `recipe_from_data(…, REGISTRY)` prüfen: `strict`,
   `extra="forbid"`, `op_version`, R5 im Parametermodell, bevor numexpr ihn
   sieht. Ohne `resolved` scheitert schon das Modell `Input`.
5. `processing.check_scope` (Ausgabe und Umfang), dann die Ausgabe nach
   Frage 2.
6. **Fassung des Kerns:** Weicht `provenance.engine` der Datei von
   `engine_versions()` des Runners ab, nennt der Runner beide Versionen auf
   stderr und rechnet trotzdem. Bitgleichheit ist dann nicht zugesagt.
   `provenance.json` hält beide Blöcke fest (Kleinentscheidung K1).

### 3.3 Hosts (F4)

- Je Eingabe: `registry.get(dataset)`; unbekannt → Exit 3.
- Hosts der Eingabe (`input_hosts`, §2.5) ⊆ `asset_hosts` des Datensatzes, sonst
  Exit 3. Die Meldung nennt den Datensatz, nicht den Host.
- `check` und der Anfang von `run` geben die Hosts aus, sortiert, nur
  Hostnamen. Die Hosts kommen aus der Registry des Images, also sind sie
  öffentlich bekannt.
- Danach liest der Kern wie im Job: `read_access_for(recipe.hrefs())`,
  `check_url` je Adresse (B9).

### 3.4 Ausgabe und `provenance.json` (F5)

```
<out>/<run_id>/          run_id = secrets.token_urlsafe(16), mkdir ohne exist_ok
  result.tif             aus processing.run
  mask.tif               aus processing.run
  recipe.json            die Bytes der Eingabe, unverändert
  provenance.json        zuletzt geschrieben
  .work/                 Arbeitsordner von processing.run, am Ende gelöscht
```

- Ein abgebrochener Lauf hinterlässt einen Ordner ohne `provenance.json`; der
  Kern hat seine Dateien in `.work` selbst entfernt.
- `provenance.json`:

```json
{
  "execution": "local",
  "kind": "job",
  "self_attested": true,
  "runner_version": "0.4.1+g1a2b3c4",
  "engine": {"earthx": "0.4.1", "gdal": "3.12.2", "rasterio": "1.5.2", "numexpr": "2.14.2", "numpy": "2.5.3"},
  "scaling": [],
  "started": "…", "finished": "…",
  "attribution": ["…"],
  "platform": {"machine": "x86_64", "numpy_dispatch": "X86_V4"},
  "properties": {"proj:code": "EPSG:…", "bands": […], "processing:software": {…}, "processing:lineage": "…"},
  "source_engine": {"earthx": "0.4.1", …}
}
```

- Die ersten neun Felder sind `processing.recipe.Provenance` und werden mit dem
  Modell gebaut. Das Modell erzwingt `self_attested == (execution == "local")`.
- `kind` bleibt `job`: Das Rezept stammt aus einem Job. Das Modell kennt nur
  `job` und `sync-download`; ein neuer Wert hieße, das Modell zu ändern
  (Kleinentscheidung K2).
- `attribution` übernimmt der Runner aus `provenance.attribution` der Eingabe;
  bauen kann er sie nicht (§2.2).
- `properties` sind die STAC-Properties des Ergebnisses
  (`RunResult.properties`), wie sie der Job meldet. Darüber vergleicht der
  Test die Metadaten.
- `platform.numpy_dispatch` ist die höchste Stufe unter
  `X86_V4`/`X86_V3`/`X86_V2` bzw. `ASIMD` aus
  `numpy._core._multiarray_umath.__cpu_features__`, sonst `"unknown"`. Das ist
  ein privates Attribut von numpy; ein Test sichert, dass es in der gepinnten
  Version da ist (Kleinentscheidung K3).
- `runner_version`: `earthx.__version__` + `+g` + `EARTHX_COMMIT`, wenn dieses
  7 bis 40 Hexzeichen sind, sonst `+unknown` (Kleinentscheidung K4).
- Kein Hash, keine `recipe_id` in `provenance.json`, keine Kennung der
  Maschine. Nichts geht zurück zur Plattform (Q11, Q12).

### 3.5 Image, compose (F1, F10, F11)

```dockerfile
FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS app
# … unverändert …

FROM app AS runner
ARG EARTHX_COMMIT=unknown
ENV EARTHX_COMMIT=${EARTHX_COMMIT}
USER 10001:10001
ENTRYPOINT ["python", "-m", "earthx.runner"]
```

- Der Digest ist der des Multi-Arch-Index, damit ein ARM-Rechner nativ baut
  (F9). Erneuert wird er als eigener PR, wie die Lock-Datei.
- `docker-compose.yml`: `target: app` an allen neun `build:` mit
  `context: ./backend`. Sonst liefen die Dienste ohne eigenes `entrypoint:`
  mit dem `ENTRYPOINT` des Runners.
- Der Kommentar am Kopf des `Dockerfile` („sets no CMD/ENTRYPOINT“) gilt dann
  nur noch für die Stufe `app`; er wird angepasst.

### 3.6 Importregeln (F2, Auflage)

- `.importlinter`, neuer Vertrag `runner` (direkte Importe): verboten sind
  `gateway`, `adapters`, `readers`, `access`, `jobs`, `discovery`,
  `identity`, `api`, `datasets`, `objectstore` und jedes Untermodul von
  `catalog` außer `datasets` und `registry`. import-linter kennt kein „nur
  diese Untermodule“; die Liste nennt sie deshalb einzeln, und ein Test prüft,
  dass sie jedes Untermodul unter `catalog/` außer den beiden nennt.
- Neuer Vertrag `no-platform-services-in-runner`, zählt Ketten: Quelle
  `earthx.runner`, verboten `psycopg`, `psycopg_pool`, `asyncpg`,
  `earthx.objectstore`, `botocore`. Ein eigener Vertrag statt einer weiteren
  Quelle in `no-database-in-worker-core` und `no-object-store-in-worker-core`:
  Die beiden heißen nach dem Kern, und R2 hält Belange in getrennten
  Verträgen (Kleinentscheidung K5).
- `earthx.runner` als Quelle in `http-only-in-gateway` und
  `datasets-isolated`.
- `test_module_boundaries.py`: Zeile `runner` in der Tabelle, beide neuen
  Verträge, die Liste der `catalog`-Untermodule.
- `architekturplan.md` 3.1: neue Zeile `runner` (Wortlaut aus `adr/0016` §5)
  und ein Nachtrag. Keine bestehende Regel wird gelockert.

### 3.7 Tests (`pytest`, Backend-Job)

**Vergleich T2 ↔ T2L (F7, `adr/0014` §6.4, §15c).** Neu:
`tests/earthx/runner/test_compare.py` mit einem Startziel
`tests/earthx/runner/targets.py`.

- Zwei Kindprozesse mit `get_context("spawn")` im selben Test:
  - Job: `earthx.jobs.child.run_child` über dieselben Nähte wie
    `child_targets.end_to_end` (letzter Schritt der Reader auf die lokale
    COG; Zarr über `MockTransport`).
  - Runner: `earthx.runner.cli.main(["run", …, "--out", …],
    registry=<synthetischer Eintrag>)` mit denselben Nähten.
- Rezepte, beide aus der R5-Liste:
  - Band-Math mit `where` und `sqrt` auf der COG mit `scale`/`offset`;
  - `reproject` `bilinear` auf dem Zarr mit CF-Attributen.
- Verglichen werden:
  - `result.tif` und `mask.tif`: Pixel mit `numpy.array_equal`, dazu Profil,
    Tags und Übersichten gleich; zusätzlich SHA-256 der Dateien gleich (GDAL
    schreibt keinen Zeitstempel, `adr/0016` §3.2);
  - `properties` und `scaling` des Jobs gegen `provenance.json`;
  - `engine` gleich.
- **Gegenprobe:** Dasselbe Paar mit einem veränderten Rezept auf der Seite
  des Runners (Konstante im Ausdruck; `nearest` statt `bilinear`) muss
  ungleich sein.
- Kein gespeicherter Referenz-Hash.

**Zweckfremde Nutzung und Fehler**, je ein Test über `main(...)` im
Testprozess:

- fremder Host, unbekannter Datensatz → 3, kein Lesen (die Naht zählt null
  Öffnungen);
- unbekannte `recipe_version`, unbekannte `op_version` → 2, Meldung nennt die
  Version des Runners;
- Ausdruck außerhalb R5 (`log(red)`, `red & 1`) → 2, numexpr nie aufgerufen;
- `recipe.json` ohne `resolved`, doppelter Schlüssel, `NaN`, über 4 MiB, kein
  JSON → 2;
- `provenance` nach Frage 3 (ungültig, `execution: "local"`, Felder der
  Provenienz auf oberster Ebene) → 2;
- Ausgabe `crop` → 2 (bei Frage 2, Option 1);
- Laufordner vorhanden (erzwungener Name) → 5, nichts überschrieben;
- Abbruch mitten im Lauf → Ordner ohne `provenance.json`, `.work` leer;
- stdout, stderr und `provenance.json` enthalten weder Adresse noch
  Koordinate der AOI noch `recipe_id`;
- `versions` gibt JSON mit den Feldern aus §3.4 aus; `EARTHX_COMMIT` leer
  oder ungültig → `+unknown`;
- Unterbefehl fehlt oder unbekannt → 2 (argparse).

**Import (Auflage F2):** Ein `spawn`-Kind versteckt `boto3` wie im Image,
importiert `earthx.runner.cli` und meldet `sys.modules`: keines der fünf
Module, dazu weder `earthx.jobs` noch `earthx.api`.

### 3.8 Compose-Job der CI (F7 Teil 2)

Neue Schritte in `compose-topology` nach „Build images“ (die Änderung an
`.github/workflows/ci.yml` erlaubt M4-16 ausdrücklich):

1. `docker build --target runner --build-arg EARTHX_COMMIT=${GITHUB_SHA::7} -t earthx-runner:ci backend`
   (Schichten aus dem Cache des Compose-Builds).
2. `versions` unter `--read-only --tmpfs /tmp --cap-drop ALL --security-opt
   no-new-privileges --network none`: Der Block `engine` ist gleich dem aus
   `docker compose run --rm --no-deps worker python -c …`.
3. `docker run --rm --entrypoint id earthx-runner:ci -u` gibt `10001`.
4. `check` auf `backend/tests/fixtures/runner/recipe-ci.json` mit denselben
   Optionen: Exit 0, die Ausgabe nennt genau den Host des Rezepts.
5. `run` auf derselben Datei mit `--network none` und einem beschreibbaren
   `/out`: Exit 4 (Frage 6), kein Ergebnis im Ordner.

`recipe-ci.json` ist synthetisch: echter Datensatz `sentinel-2-c1-l2a` mit
einem Host aus seinen `asset_hosts`, erfundene Item-ID und Pfad, ein
Quadrat ohne Bezug zu einem Ort, Band-Math. Es wird nie gelesen, weil kein
Netz da ist.

### 3.9 Anleitung (README) und Prüfanleitung

**README**, neuer Abschnitt „Lokaler Runner (seit M4-16)“: Image bauen,
`recipe.json` aus dem Download, Lauf, Ausgabeordner, Exit-Codes;
Linux mit `--user "$(id -u):$(id -g)"`; Podman; WSL2 und Pfade im
Windows-Dateisystem; Docker Desktop und seine Lizenzschwellen ohne
Einstufung; ARM außerhalb der Bitgleich-Zusage; kein `latest`, kein Push.

**Prüfanleitung für Otto** (Windows PowerShell 5.1, im PR, Entwurf):

```powershell
docker compose up -d --build
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\try-job.ps1
docker build --target runner --build-arg EARTHX_COMMIT=$(git rev-parse --short HEAD) -t earthx-runner:0.4.1 backend
New-Item -ItemType Directory -Force -Path .\runner-out | Out-Null
docker run --rm --read-only --tmpfs /tmp --cap-drop ALL --security-opt no-new-privileges -v "${PWD}\try-job-output:/in:ro" -v "${PWD}\runner-out:/out" earthx-runner:0.4.1 run /in/recipe.json
$run = Get-ChildItem .\runner-out -Directory | Sort-Object LastWriteTime | Select-Object -Last 1
(Get-FileHash .\try-job-output\result.tif).Hash -eq (Get-FileHash (Join-Path $run.FullName 'result.tif')).Hash
Get-Content (Join-Path $run.FullName 'provenance.json')
```

Erwartet: `True` beim Vergleich der Hashes (gleiche Maschine, gleiches Image),
`"self_attested": true` und `"execution": "local"`. Der Runner liest dabei
selbst bei der Quelle, also von Ottos IP (B9, 7.7).

---

## 4. Fragen an Otto

**Frage 1 — Bauen und messen, wenn `docker build` in der Session scheitert (§1.3, §2.7)**
1. **Die Session baut für die eigene Prüfung eine Kopie des `Dockerfile` im
   Kratzverzeichnis, in der `libexpat.so.1` und `curl` aus dem Host den
   `apt`-Schritt ersetzen (wie `adr/0016` §14.1). Damit prüft sie Stufe,
   Härtung, `versions`, `check` und `run` ohne Netz. Maßgeblich ist der Bau
   im Compose-Job der CI (Empfehlung).**
2. Du nimmst `deb.debian.org` und `security.debian.org` in die Allowlist auf;
   die Umsetzung startet in einer neuen Session.
3. Kein Bau in der Session, nur in der CI.

**Frage 2 — Welche Ausgabe rechnet der Runner in M4 (§2.3)?**
1. **Nur `raster`, auch das Mosaik eines Überflugs. `crop` (Export-Job und
   synchroner Zuschnitt) endet mit Exit 2 und dem Satz, dass ein Zuschnitt
   von der Plattform kommt. Die Abnahme 1 braucht nur `raster` (Empfehlung).**
2. Dazu `crop`: Der Runner nimmt `ATTRIBUTION.txt`, `citation.bib` und
   `aoi.geojson` aus dem Ordner der `recipe.json` (entpacktes ZIP), prüft sie
   mit `Attachments` und schreibt `export.zip`. Etwa 150 Zeilen mehr. Die
   Beilagen sind dann vom Nutzer geliefert, nicht von `api` gebaut.

**Frage 3 — Der Block `provenance` in der Eingabe (§2.1)**
1. **Der Runner trennt genau einen Block `provenance` auf oberster Ebene ab
   und prüft ihn mit dem Modell `Provenance`; er muss
   `execution: "cloud"` tragen. Sonst Exit 2, ebenso für Felder der
   Provenienz (`execution`, `runner_version`, `self_attested`) auf oberster
   Ebene. Er dient nur der Attribution und dem Vergleich der Versionen
   (§3.2 Schritt 6). Dazu ein Nachtrag in `adr/0016` (Empfehlung).**
2. Wie 1, aber ohne Prüfung des Blocks; er wird nur entfernt.
3. Wörtlich nach `adr/0016` §7.2: Eine Datei mit `provenance` wird
   abgewiesen; der Nutzer muss den Block selbst löschen.

**Frage 4 — `citation.bib` im Laufordner (§2.2)**
1. **Keine. Der Laufordner enthält `result.tif`, `mask.tif`, `recipe.json`
   und `provenance.json`; die Attribution steht in `provenance.json`. Die
   Anleitung sagt, dass `citation.bib` aus dem Download stammt. Nachtrag in
   `adr/0016` zu F5 (Empfehlung).**
2. Liegt neben der `recipe.json` eine `citation.bib`, kopiert der Runner sie
   ungeprüft mit.
3. `citation_bib` wandert aus `api` nach `catalog` (es braucht nur die
   `DatasetConfig`), und der Runner baut sie selbst. Ändert `api` und damit
   „Nicht anfassen“ der Aufgabe.

**Frage 5 — Schnitt des PRs (Richtwert 400 Zeilen)**
Schätzung: Modul etwa 300, Tests etwa 450, `.importlinter` und
`test_module_boundaries.py` etwa 70, `Dockerfile`, compose und CI etwa 80,
README und Doku etwa 120, zusammen etwa 1000.
1. **Zwei PRs. M4-16a in dieser Session: Modul, Importregeln, alle
   `pytest`-Tests mit dem Vergleich (etwa 800). M4-16b in einer neuen Session
   nach dem Merge von a: Stufe `runner`, Digest, `target: app`, Compose-Job,
   README, Prüfanleitung (etwa 200) (Empfehlung).**
2. Ein PR mit etwa 1000 Zeilen, in Commits getrennt nach §5.
3. Drei PRs: Modul mit Tests ohne Vergleich, Vergleichstest, Image mit CI.

**Frage 6 — Exit-Code ohne Netz (§2.4)**
1. **3 nur für die Prüfung vor dem Lesen (F4), alles beim Lesen ist 4, auch
   die Ablehnung durch `gateway`. Der Compose-Job erwartet 4; Nachtrag in
   `adr/0016` zu den Exit-Codes (Empfehlung).**
2. Ablehnungen von `gateway` beim Lesen sind 3; der Compose-Job erwartet 3
   unter `--network none`.

**Kleinentscheidungen** (gelten, sofern du nicht widersprichst):
- **K1:** Weicht die Version des Kerns in der Datei ab, warnt der Runner und
  rechnet; `provenance.json` trägt `source_engine`.
- **K2:** `kind` bleibt `job`; das Modell `Provenance` ändert sich nicht.
- **K3:** `numpy_dispatch` aus dem privaten `__cpu_features__`, mit Test und
  Rückfall `"unknown"`.
- **K4:** `runner_version` `<version>+g<commit>`, ohne gültigen Commit
  `<version>+unknown`.
- **K5:** eigener Kettenvertrag `no-platform-services-in-runner`.
- **K6:** `recipe.json` höchstens 4 MiB.

---

## 5. Umsetzung nach Freigabe

Annahme: die Empfehlungen. Bei anderen Antworten passe ich den Plan vor dem
Code an. Commits in dieser Reihenfolge; bei Frage 5, Option 1 sind 1–5 M4-16a
und 6–8 M4-16b.

| Commit | Was | Dateien | Zeilen (ca.) |
|---|---|---|---|
| 1 | Modul `runner`: Lesen und Prüfen, Hosts, Ausgabe, CLI, Exit-Codes; `input_hosts` | `backend/earthx/runner/*`, `processing/recipe.py` | 300 |
| 2 | Importregeln und Abgleich mit 3.1 | `.importlinter`, `tests/test_module_boundaries.py`, `docs/architekturplan.md` 3.1 | 90 |
| 3 | Tests der CLI: Fehler, zweckfremde Nutzung, `versions`, Import | `tests/earthx/runner/test_cli.py`, `test_import.py`, Fixtures | 250 |
| 4 | Vergleich Job ↔ Runner mit Gegenprobe | `tests/earthx/runner/test_compare.py`, `targets.py` | 200 |
| 5 | Doku zu a: Nachtrag `adr/0016` §12b (Fragen 2, 3, 4, 6), Log, §3 im Plan | `docs/` | 50 |
| 6 | Image: Digest, Stufe `runner`, `target: app` | `backend/Dockerfile`, `docker-compose.yml` | 30 |
| 7 | Compose-Job: Stufe bauen, `versions`, UID, `check`, `run` ohne Netz | `.github/workflows/ci.yml`, `backend/tests/fixtures/runner/recipe-ci.json` | 60 |
| 8 | Anleitung und Doku zu b | `README.md`, Log, §3 im Plan | 80 |

**Bleibt, wie es ist:** `jobs`, `api` und die Verträge anderer Module.
`processing` bekommt nur `input_hosts` (§2.5, in Commit 1, mit Test); sonst
nutzt der Runner, was es heute anbietet: `run`, `worker_environment`,
`check_scope`, `failure_kind`, `recipe.Provenance`, `recipe_from_data`,
`loads_i_json`, `engine_versions`, `operators.REGISTRY`. Keine neue
Abhängigkeit, keine neue Lock-Datei.

Vor dem Fertigmelden: `main` holen; `pytest`, `ruff check backend`,
`PYTHONPATH=backend lint-imports --config .importlinter`; Ergebnisse im PR.

## 6. Abnahme gegen M4-16

| Punkt | wo |
|---|---|
| Vergleichstest grün in der CI | §3.7 (Backend-Job), §3.8 (Compose-Job) |
| Gegenprobe im PR: ein verändertes Rezept bricht die Bitgleichheit | §3.7, Test und Ausgabe im PR |
| Abweisung eines Rezepts mit fremdem Host (Test) | §3.7 |
| `provenance.json` mit `self_attested: true` | §3.4, Test |
| Prüfanleitung mit dem Ergebnis aus `scripts/try-job.ps1` | §3.9 |

---

## 7. Freigabe (Otto, 20.10.2026)

| Frage | Antwort |
|---|---|
| 1 Bau in der Session | **Option 2:** Allowlist für den Debian-Spiegel; gilt ab der neuen Session für M4-16b. Der Bau braucht nur `deb.debian.org` (§8) |
| 2 Ausgabe | Option 1: nur `raster`, `crop` → Exit-Code 2 |
| 3 `provenance` in der Eingabe | Option 1: abtrennen und als `Provenance` mit `execution: "cloud"` prüfen |
| 4 `citation.bib` | Option 1: keine im Laufordner |
| 5 Schnitt | Option 1: M4-16a jetzt, M4-16b in einer neuen Session nach dem Merge von a |
| 6 Exit-Code ohne Netz | Option 1: 3 nur vor dem Lesen, beim Lesen immer 4 |
| K1–K6 | angenommen |

**Auflage:** Nachtrag in `adr/0016` zu den vier Abweichungen
(`provenance`, `citation.bib`, `crop`, Exit-Code ohne Netz); das Original
bleibt stehen. Erledigt als `adr/0016` §12b.

## 8. M4-16b — Image, Compose-Job, Anleitung

**Startsatz:** „Führe Aufgabe M4-16b aus `docs/plans/m4/m4-16-lokaler-runner.md` aus.“
**Stufe B, Plan freigegeben** (§4 bis §7); die Session setzt direkt um.
**Voraussetzungen:** M4-16a ist gemergt. Die Session ist neu gestartet, nachdem
Otto `deb.debian.org` in die Allowlist der Cloud-Umgebung aufgenommen hat.

**Hosts für den Bau [M]:** Das gepinnte Basis-Image holt `apt`-Pakete nur von
`deb.debian.org`, über HTTP (Port 80), unter `/debian` (Suiten `trixie`,
`trixie-updates`) und `/debian-security` (Suite `trixie-security`). So steht es
in `/etc/apt/sources.list.d/debian.sources` im Image.
`security.debian.org` kommt dort nicht vor. Das Basis-Image selbst und die
Python-Pakete (`pip` aus der Lock-Datei) lädt die Session schon heute.

**Umfang:** Commits 6 bis 8 aus §5, also §3.5, §3.8 und §3.9:
- `backend/Dockerfile` mit dem Digest aus §2.7 und der Stufe `runner`;
- `target: app` an allen neun `build:` in `docker-compose.yml`;
- die Schritte im Compose-Job und `backend/tests/fixtures/runner/recipe-ci.json`;
- der README-Abschnitt und die Prüfanleitung im PR.

Die Exit-Codes und Dateien gelten nach `adr/0016` §12b: `run` ohne Netz endet
mit 4, und der Laufordner enthält keine `citation.bib`.

**Zuerst prüfen:** `docker build --target runner backend` gelingt in der
Session. Scheitert `apt` trotz Allowlist, nennt die Session Host und Antwort
und hält an (`CLAUDE.md`, „Fehlt der Zugang …“).

## 9. M4-16a umgesetzt (20.10.2026)

- **Modul** `backend/earthx/runner/` mit `__init__.py`, `__main__.py`,
  `cli.py`, `recipe_file.py` und `output.py`, wie in §3.1 bis §3.4 und nach §7.
  `processing.recipe.input_hosts` ist neu (§2.5).
- **Importregeln:** Verträge `runner` und `no-platform-services-in-runner`.
  `earthx.runner` steht in den Verbotslisten aller anderen Modulverträge und
  als Quelle in `http-only-in-gateway` und `datasets-isolated`.
  `test_module_boundaries.py` gleicht die `catalog`-Untermodule mit der Platte
  ab. Dazu die Zeile in `architekturplan.md` 3.1.
- **Tests** in `backend/tests/earthx/runner/`:
  - `test_compare.py`: Job-Kind ↔ Runner, bitgleich, mit zwei Gegenproben;
  - `test_cli.py`: Fehler, zweckfremde Nutzung, `versions`, Import im frischen
    Prozess.
  Abweichung von §5: Es gibt keine eigene `test_import.py`; der Import-Test
  steht in `test_cli.py`.
- **Doku:** `adr/0016` §12b, Log-Zeilen, §3 von `plans/m4/m4-processing-kern.md`.
- **Nach dem Review (Subagent `reviewer`):**
  - Die Hostprüfung ist jetzt dieselbe wie bei der Annahme in `api`:
    `inspect_url` gegen `asset_hosts` prüft Schema, Zugangsdaten, Port und Host.
    Dafür bekommt `readers` die Funktion `check_hrefs`; `processing.recipe.input_hosts`
    ruft sie. Abweichung von §2.5 und §5: Zuvor verglich der Runner nur Hostnamen,
    und eine `http`-Adresse auf einem erlaubten Host wäre erst beim Lesen mit 4
    statt vor dem Lesen mit 3 abgewiesen worden.
  - `check_scope` läuft vor dem Lesen und vor dem Laufordner (§3.2 Schritt 5).
  - Ein Fehler beim Abschließen des Ordners endet mit 5, nicht mit einem
    Traceback.
  - Die Warnung zu anderen Versionen (K1) und die Meldung zu einem unbekannten
    Datensatz geben keine Werte aus der Datei wieder.
  - Die Gegenproben prüfen die Vergleichsfunktion selbst.

## 10. M4-16b umgesetzt (20.10.2026)

- **Image** (`backend/Dockerfile`): Basis `python:3.12-slim` per Digest des
  Multi-Arch-Index (§2.7), die bisherige Stufe heißt `app`, dazu die Stufe
  `runner` (`EARTHX_COMMIT`, `USER 10001:10001`, `ENTRYPOINT`). Alle neun
  `build:` in `docker-compose.yml` nennen `target: app`. Ein Test
  (`tests/test_runner_image_definition.py`) hält Digest, Stufen und `target`
  fest, weil der Bau in der Session nicht durchläuft.
- **Compose-Job** (`.github/workflows/ci.yml`, ausdrücklich Teil der Aufgabe):
  Stufe bauen, UID `10001`, `versions` unter `--network none` gleich dem Block
  `engine` des Dienstes `worker`, `check` auf
  `tests/fixtures/runner/recipe-ci.json` nennt genau einen Host, `run` ohne
  Netz endet mit 4 und lässt keine Datei zurück. Die Datei ist synthetisch
  (echter Datensatz, erfundene Item-ID, Quadrat bei 0°/0°); die Fassung des
  Kerns entspricht dem Stand der Lock-Datei und muss bei einer Änderung der
  Versionen neu geschrieben werden, sonst warnt `run` nur (K1).
- **README:** Abschnitt „Lokaler Runner (seit M4-16)“.
- **Prüfung in der Session [M]:** `apt` ist mit der Allowlist durchgelaufen
  (Schicht `apt-get install curl libexpat1` gebaut). `pip install` im Bau
  scheitert dort an der TLS-Kette des Session-Proxys (`self-signed certificate
  in certificate chain`); das Image enthält dessen CA nicht. Das ist eine Frage
  des Zugangs der Session, nicht des `Dockerfile`. Deshalb **nicht in der
  Session geprüft:** Bau der Stufe, `versions`, UID, `check`, `run` unter
  `--network none`. Maßgeblich ist der Compose-Job der CI.
  Ohne Image geprüft: `check` auf `recipe-ci.json` gibt genau den einen Host
  aus (Exit 0), `ruff`, die Tests des Runners und der Bau-Definition laufen.
- **Prüfanleitung für Otto** (Windows PowerShell 5.1): im PR. Zum Vergleich Cloud ↔ Runner siehe §10.1.

### 10.1 Antwort von Otto und der Vergleichstest (20.10.2026)

- **Bau:** Der Image-Bau bleibt in der CI (und lokal bei Otto). Keine CA des
  Session-Proxys im Image.
- **Wo steht der Vergleich Cloud ↔ Runner (M4-Abnahme, Kriterium 1)?** In
  `backend/tests/earthx/runner/test_compare.py`, Backend-Job der CI: Job-Kind
  (`earthx.jobs.child.run_child`) und Runner (`earthx.runner.cli.main`) in je einem
  `spawn`-Prozess, gleiches Rezept, `result.tif` und `mask.tif` pixelgleich und
  als Datei mit gleichem SHA-256, dazu zwei Gegenproben. Das ist der Kern gegen
  den Runner, nicht das Image.
- **Warum nicht zusätzlich im Image mit lokaler Eingabe:** `gateway` lässt nur
  `https`-Adressen zu, die öffentlich auflösen und auf einem erklärten Host
  liegen (`check_url`, `asset_hosts`). Eine lokale Eingabe ginge nur über eine
  Naht, die das ersetzt. Solche Nähte (`vsicurl_path`, `resolve_host`) gibt es
  nur in `pytest` (`tests/earthx/processing/sources.py::serve`). Sie ins Image
  zu legen hieße, eine Ausnahme in Produktivcode einzubauen oder die Prüfung
  zu umgehen; beides ist ausgeschlossen (B8, B9). Das Image enthält außerdem
  weder `pytest` noch `rio-cogeo` zum Bauen der Eingaben.
- **Was stattdessen trägt:**
  1. der `pytest`-Vergleich am Kern (oben);
  2. im Compose-Job: dieselben Engine-Versionen wie `worker`, und **dieselben
     Schichten** wie das Image von `worker` (die Stufe `runner` fügt nur `ENV`,
     `USER` und `ENTRYPOINT` hinzu). Was der Vergleich für den Code zeigt, gilt
     also für die Dateien im Image;
  3. `check` und `run` im Container unter Härtung und ohne Netz (Grenze,
     Exit-Codes, kein Ergebnis);
  4. der Hashvergleich gegen einen echten Cloud-Job in Ottos Prüfanleitung (§3.9,
     PR): Er braucht eine echte Quelle und gehört nicht in die CI (`adr/0002`).
- **Offen:** Ein Hash im Image gegen den Kern aus derselben CI ist damit nicht
  nachgewiesen, nur geschlossen über Schichten und Versionen.
