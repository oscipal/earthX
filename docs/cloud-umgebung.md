# EarthX — Was die Cloud-Umgebung bereitstellt

- **Stand:** 2026-09-18, gemessen in einer Claude-Code-Cloud-Sitzung.
- **Aufgabe:** M0 Schritt 2 laut `ENTSCHEIDUNGEN_2026-09-18.md` §6; beantwortet die
  Frage aus `projektplan.md` 2.3 ("ob in der Cloud-VM Docker bzw. ein lokales
  Postgres verfügbar ist").
- **Methode:** ausgeführt und beobachtet, nicht aus Dokumentation abgeleitet. Jede
  Zeile unten wurde in dieser Sitzung geprüft. Kein MAAP, kein BIOMASS, kein Token.
- **Gültigkeit:** eine Momentaufnahme **einer** Sitzung. Das Image und die
  Netz-Policy können sich ändern; bei Überraschungen neu messen.

---

## 1. Kurzfassung

| Frage | Antwort |
|---|---|
| Python | seit M3-03 **3.12** (Ubuntu-Paket im Image) im venv des Hooks; `python3` zeigt weiter auf 3.11.15; **kein** conda/mamba |
| Node | 22.22.2 mit npm 10.9.7; `npx`, `yarn`, `pnpm` vorhanden |
| Backend-Abhängigkeiten | installieren sich **vollständig per pip**, ohne System-GDAL |
| Docker | Daemon startbar, **Images aber nicht ladbar** — praktisch unbrauchbar |
| Postgres | 16.13 vorinstalliert, gestoppt; startet; PostGIS 3.4 nachinstallierbar |
| pgstac | 0.9.12 migriert erfolgreich in die lokale Datenbank |
| EO-Datenquellen | **keine erreichbar** |

Die wichtigste Abweichung von der Annahme in `projektplan.md` 2.3: Ein lokales
Postgres mit PostGIS **und** pgstac läuft in der Cloud-Sitzung. Die dort
genannte Rückfallebene (Integrationstests nur in GitHub Actions mit
Service-Containern) bleibt für CI richtig, ist für die Sitzung aber nicht nötig.
Umgekehrt ist Docker die Erwartung, die sich **nicht** erfüllt.

## 2. Laufzeiten und Werkzeuge

| Werkzeug | Version | Anmerkung |
|---|---|---|
| Betriebssystem | Ubuntu 24.04.4 LTS | 4 CPU, 15 GiB RAM, ~30 GiB freier Schreibplatz |
| Python | 3.12.3 (`/usr/bin/python3.12`, Ubuntu-Paket, mit `venv`) | Stand 2026-09-23 (M3-03). Das venv des Projekts wird damit angelegt, siehe §7 |
| Python, systemweit | 3.11.15 (`/usr/local/bin/python3 → /usr/bin/python3.11`) | `python3` und `python` zeigen darauf; im Image liegen außerdem 3.10 und 3.13. Nicht für das Projekt benutzen |
| conda / mamba / micromamba | — | nicht vorhanden und nicht installierbar ohne Netzausnahme |
| Node | 22.22.2, npm 10.9.7 | `npm ci` im Frontend: 56 Pakete, wenige Sekunden |
| Docker CLI | 29.3.1, Compose v5.1.1 | siehe Abschnitt 4 |
| Postgres | 16.13 (Ubuntu-Paket) | beim Sitzungsstart **gestoppt** |
| `apt-get` | funktioniert | Ubuntu-Archiv erreichbar; die PPAs `deadsnakes` und `ondrej` sind gesperrt (nur Warnungen) |

## 3. Backend-Abhängigkeiten: ja, per pip

`pip install -r backend/requirements.txt` läuft in einem frischen venv ohne
Fehler durch. Kein System-GDAL nötig — die Wheels bringen ihr eigenes mit:

| Paket | Version | Anmerkung |
|---|---|---|
| rasterio | 1.4.4 | GDAL 3.10.3 im Wheel |
| rio-tiler | 9.4.6 | deutlich neuer als die Untergrenze `>=6.4` |
| shapely | 2.1.2 | |
| pystac-client | 0.9.0 | |
| fastapi | 0.141.1 | |
| numpy | 2.4.6 | |

Geprüft wurde nicht nur der Import: eine Koordinatentransformation
EPSG:4326 → EPSG:3857 liefert das richtige Ergebnis, PROJ-Daten sind also
vollständig. Das venv belegt rund 310 MB.

**Folge für `environment.yml`:** Die conda-Datei beschreibt weiter Ottos lokale
Umgebung, ist in der Cloud aber wirkungslos. Der pip-Weg ist dort der einzige,
und CI geht denselben Weg — damit prüft CI, was die Sitzung benutzt.
*(Stand 2026-09-18. `environment.yml` ist mit dem Prototyp entfallen,
`adr/0008`; der pip-Weg ist seither überall der einzige. Die Tabelle oben ist
eine Messung unter 3.11; unter 3.12 lösen mehrere Pakete neuer auf,
`plans/m3-03-python-312.md` §2.3.)*

## 4. Docker: startbar, aber nutzlos

- Der Daemon läuft beim Sitzungsstart nicht; `/var/run/docker.sock` fehlt.
- `sudo` ist ohne Passwort möglich, und `sudo dockerd` startet sauber
  (Storage-Driver `overlayfs`, buildkit initialisiert).
- **Aber:** Jeder `docker pull` bricht ab. Die Registry-Indizes
  (`registry-1.docker.io`, `ghcr.io`) antworten, die Blob-CDNs
  (`production.cloudfront.docker.com`, `pkg-containers.githubusercontent.com`)
  antworten mit **403**. Schon `hello-world` lässt sich nicht laden.

> **Regel zur Allowlist (bestätigt am 18.09.2026):** Eine Egress-Freigabe wirkt
> erst in einer **neu gestarteten** Sitzung. Wird ein Host mitten in einer
> Sitzung eingetragen, antwortet er dort weiter mit 403 — das sagt dann nichts
> über die Freigabe aus. Prüfungen, die einen neu freigegebenen Host brauchen,
> gehören deshalb in die nächste Sitzung. Belegt an
> `sentinel.esa.int`, `sentinels.copernicus.eu` und `spacedata.copernicus.eu`
> (`adr/0003` §10.2, §11.3).

Damit sind Testcontainer, `docker compose` und der lokale Runner als Container
in der Cloud-Sitzung nicht verfügbar. Selbst gebaute Images aus einem
`Dockerfile` scheitern am Basis-Image aus derselben Quelle. Das ist eine
Netz-Policy-Frage, keine Rechtefrage: Otto könnte die beiden Blob-Hosts der
Allowlist der Umgebung hinzufügen; ohne das bleibt Docker außen vor.

## 5. Postgres, PostGIS, pgstac: ja

Vollständig geprüft, in dieser Reihenfolge:

1. `pg_ctlcluster 16 main start` → Cluster nimmt Verbindungen an.
2. `apt-get install postgresql-16-postgis-3` → PostGIS **3.4**
   (`USE_GEOS=1 USE_PROJ=1 USE_STATS=1`).
3. `pip install pypgstac[psycopg]`, dann `pypgstac migrate` gegen eine frische
   Datenbank → **pgstac 0.9.12**, fehlerfrei.

Beides kostet beim Sitzungsstart Zeit (Paketinstallation, Migration) und gehört
deshalb ins Setup-Skript, dessen Ergebnis zwischengespeichert wird.

Nicht geprüft: ein S3-kompatibler Objektspeicher. MinIO wird üblicherweise als
Container ausgeliefert und ist damit aus dem Grund aus Abschnitt 4 nicht
verfügbar. Für Tests, die einen Objektspeicher brauchen, bleibt es bei der
Rückfallebene GitHub Actions — oder es wird ein reines Python-Double benutzt
(`moto`); das ist noch nicht entschieden und steht im Entscheidungslog.

## 6. Erreichbare Domains

Ausgehendes HTTPS geht über den Agent-Proxy der Umgebung. Gemessen:

| Erreichbar | Gesperrt (403 auf CONNECT) |
|---|---|
| `pypi.org`, `files.pythonhosted.org` | `planetarycomputer.microsoft.com` |
| `registry.npmjs.org` | `catalogue.dataspace.copernicus.eu` |
| `earth-search.aws.element84.com` (seit dem 18.09.2026 freigegeben, in Sitzungen vom 19.09.2026 erreichbar und gemessen) | `stac.eopf.copernicus.eu` |
| `api.github.com`, `github.com` | `tile.openstreetmap.org` |
| Ubuntu-Archiv (`apt`) | `data.maap-project.org`, `quay.io`, Container-Blob-CDNs |
| `mcr.microsoft.com` | `operations.osmfoundation.org`, `nominatim.org`, `osmfoundation.org`, `www.openstreetmap.org` (Doku-Seiten, Beleg `plans/m3-07a-ortssuche-backend.md` §2) |
| `nominatim.openstreetmap.org` (seit dem 26.09.2026 freigegeben, für M3-07a gemessen, Beleg `plans/m3-07a-ortssuche-backend.md` §3) | |
| `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com` (tatsächlicher Asset-Host von `sentinel-2-c1-l2a`, Beleg `adr/0006`) | |
| `objects.eodc.eu`, **`data.eodc.eu`**, `stac.core.eopf.eodc.eu` (Beleg `adr/0007` §3.1, §12.1) | `download.user.eopf.eodc.eu`, `stac.browser.user.eopf.eodc.eu` (Beleg `adr/0007` §12.1) |

**Stand 19.09.2026: Earth Search v1 ist erreichbar.** Die Tabelle oben führte
`earth-search.aws.element84.com` bis dahin als gesperrt; das war der Stand der
Messung vom 18.09.2026, **vor** der Egress-Freigabe aus `adr/0003` §11. Seit dem
19.09.2026 ist der Host in mehreren Sitzungen gemessen — `adr/0004` §3 und
`adr/0005` §3 beruhen auf über 100 Metadaten-Anfragen dorthin. Zusammen mit dem
tatsächlichen Asset-Host ist damit der Weg des ersten Datensatzes in der
Cloud-Sitzung vollständig offen: Metadaten und Assets.

**Widerspruch beim Asset-Host von `sentinel-2-c1-l2a` — aufgelöst (2026-09-20,
`adr/0006`, PR #34):** Frühere Fassungen dieser Tabelle führten
`sentinel-cogs.s3.us-west-2.amazonaws.com` als den Asset-Host des ersten
Datensatzes. Gemessen und am Code geklärt: Die Assets von `sentinel-2-c1-l2a`
liegen auf `e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com`.
`sentinel-cogs...amazonaws.com` gehört zur **älteren** Earth-Search-Collection
`sentinel-2-l2a`, die Collection 1 ablöst (adr/0003 §3, Option B) — nicht zum
Datensatz, den `earthx` führt. Die Tabelle oben ist entsprechend korrigiert.

**EOPF-Hosts — Stand nach der Freigabe (2026-09-20, M2-03b, `adr/0007` §12.1):**
`data.eodc.eu` ist **freigegeben und gemessen erreichbar**; darauf liegen die
Zarr-v3-Produkte der Collection `sentinel-2-l2a-zarr3`, die in `adr/0007` §12
durchgemessen sind. `objects.eodc.eu` (ältere Tutorial-Produkte, S1-SLC) und
`stac.core.eopf.eodc.eu` (die STAC-API) sind unverändert erreichbar; die Tabelle
oben führte die STAC-API bisher gar nicht.

**Gesperrt bleiben** `download.user.eopf.eodc.eu` und
`stac.browser.user.eopf.eodc.eu`, beides so gewollt: ganze gezippte Produkte
braucht die Plattform nie, und die Browser-Oberfläche ist keine Schnittstelle.
`stac.eopf.copernicus.eu` bleibt gesperrt — es ist nach `adr/0007` §3.1 nur die
zweite Adresse derselben STAC-API, die über EODC offen ist. **Achtung:** Die
Sperre von `download.user.eopf.eodc.eu` hält gezippte Produkte nicht mehr fern —
bei den aktuellen Items liegt das Asset `zipped_product` mit 1,2 GB auf dem jetzt
offenen `data.eodc.eu` (`adr/0007` §12.1). Fernhalten muss es der
Registry-Eintrag.

**Die Fassung von PR #35 ist damit überholt.** Sie führte `data.eodc.eu` als
gesperrt; das war der Stand **vor** der Freigabe aus `adr/0007` F1.

Das ändert nichts an der Testaufteilung. Seit dem 26.09.2026 ist
`nominatim.openstreetmap.org` erreichbar, nur für gedrosselte Messungen per
`curl` (M3-07a); Tests laufen weiter gegen synthetische Fixtures. Für CDSE gilt die Sperre
unverändert. Die Annahme, auf der `projektplan.md` 2.4
und `docs/adr/0002-testaufteilung.md` aufbauen — Tests laufen ohne Live-Quellen —,
bleibt bestehen: Erreichbarkeit ist die Grundlage für Spikes und Messungen, nicht
für Tests in CI oder PR-Läufen. Live-Zugriffe bleiben auf zeitgesteuerte
T-D-Smoke-Tests beschränkt (`adr/0002`), Fixtures bleiben synthetisch.

**Überholt ist dagegen der frühere Satz, die EOPF-Quelle lasse sich in einer
Cloud-Sitzung nicht ausprobieren, sondern nur lokal bei Otto.** Seit der
Freigabe geht es: `adr/0007` §12 hat Kachel, Statistik und AOI-Zuschnitt in
einer Cloud-Sitzung gegen die echte Quelle gemessen.

Eine Freigabe wirkt erst in **neu gestarteten** Sitzungen; eine mitten in der
Sitzung eingetragene Freigabe wirkt dort nicht (`adr/0003` §11.3).

## 7. Was daraus folgt

1. **Setup als SessionStart-Hook (Stand 2026-09-19):** Der ursprüngliche
   Vorschlag, `scripts/setup-cloud-session.sh` ins Umgebungsfeld der
   Cloud-Umgebung einzutragen, ist dort gescheitert: Pfadauflösung über
   `BASH_SOURCE` griff nicht, `sudo` lief als root ins Leere, und der
   Postgres-Start ging über den Cache-Snapshot der Sitzung verloren. Das
   Umgebungsfeld installiert seither nur noch PostGIS per `apt`; den Rest
   erledigt `scripts/setup-cloud-session.sh` jetzt als SessionStart-Hook
   (`.claude/settings.json`, Matcher `startup|resume`), wie in
   [Claude Code on the web](https://code.claude.com/docs/en/cloud-environments)
   beschrieben ("Install dependencies with a SessionStart hook"). Das Skript
   legt das venv an, installiert Frontend-Pakete (jeweils nur, wenn noch
   nicht vorhanden), startet Postgres per `service postgresql start` und
   richtet Rolle, Datenbank und PostGIS-Extension idempotent ein. Es läuft
   nur bei `CLAUDE_CODE_REMOTE=true`, verwendet `sudo` nicht, wenn die
   Sitzung schon als root läuft, und endet immer mit Exit 0 — ein
   fehlgeschlagener Schritt wird gemeldet, blockiert aber nie den
   Sitzungsstart. Am 2026-09-19 zweimal hintereinander in derselben Sitzung
   getestet: erster Lauf legt venv, Frontend-Abhängigkeiten, Postgres-Rolle
   und -Datenbank an; zweiter Lauf überspringt venv und Frontend-Pakete
   (bereits vorhanden) und meldet Rolle/Datenbank als bereits vorhanden.
   Die PostGIS-Extension schlug in dieser Sitzung fehl, weil das Paket hier
   noch nicht installiert war — erwartungsgemäß, da die apt-Installation
   erst mit der nächsten neu gestarteten Sitzung wirkt (siehe die
   Allowlist-Regel oben).
   **Nachtrag 2026-09-23 (M3-03, `plans/m3-03-python-312.md`):** Der Hook
   legt das venv mit `/usr/bin/python3.12` an, über den absoluten Pfad: `python3`
   zeigt im Image auf 3.11, und ein `python3.12` im `PATH` kann ein anderer Build
   sein (`uv python install` legt einen nach `~/.local/bin`, vor `/usr/bin`). Ein
   venv mit anderer Version oder ein kaputtes venv wird ersetzt; fehlt der
   Interpreter, meldet der Hook `venv FEHLT` und weicht nicht auf 3.11 aus.
   Außerdem trägt er `.venv/bin` über `CLAUDE_ENV_FILE` in den `PATH` der
   Sitzung ein. Vorher war ein nacktes `pytest` in der Sitzung
   `/root/.local/bin/pytest`, ein Werkzeug des Images ohne die Backend-Pakete,
   das beim Sammeln abbrach; nur `.venv/bin/pytest` lief.
   **Nachtrag 2026-09-23, zweite Messung — in einer frisch gestarteten
   Sitzung bestanden:** `.venv/bin` steht vorn im `PATH`, ein nacktes `pytest`
   ist das des venv, 1087 Tests grün auf 3.12.3. In einer laufenden
   (fortgesetzten) Sitzung dagegen ist `$CLAUDE_ENV_FILE` leer — die Variable
   ist nur im Prozess des Hooks selbst gesetzt, nicht in der Shell, die
   Werkzeuge danach benutzen. Das ist kein Fehler des Hooks, sondern zeigt nur
   den Unterschied zwischen „neu gestartet“ und „fortgesetzt“, wie schon in
   §4 und §6 für Allowlist-Freigaben festgehalten. In der öffentlichen
   Dokumentation von Claude Code (claude-code-on-the-web, Abschnitt zu
   Umgebungsvariablen) ist `CLAUDE_ENV_FILE` nicht beschrieben; es steht nur
   in der eingebauten Skill-Datei `session-start-hook`. **Folge:** Findet eine
   Sitzung `pytest` außerhalb von `.venv` (z. B. `/root/.local/bin/pytest`
   ohne die Backend-Pakete), ist das kein neuer Fehler, sondern dieser bereits
   bekannte Fall — mit `.venv/bin/pytest` arbeiten oder eine neue Sitzung
   starten.
2. **Testaufteilung:** `docs/adr/0002-testaufteilung.md`.
3. **Offen für Otto:**
   - Sollen `production.cloudfront.docker.com` und
     `pkg-containers.githubusercontent.com` in die Allowlist der Umgebung, damit
     Docker in Sitzungen nutzbar wird? Empfehlung: **vorerst nein** — die
     Testaufteilung kommt ohne aus, und in CI gibt es Service-Container.
   - Objektspeicher in Tests: `moto` im Prozess oder nur in CI? Empfehlung:
     **`moto`**, sobald der erste Test ihn braucht (nicht jetzt).
