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
| Python | 3.11.15, systemweit; **kein** conda/mamba — `environment.yml` ist hier nicht nutzbar |
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
| Python | 3.11.15 (`/usr/local/bin/python3`) | pip 24.0; venv funktioniert |
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

## 4. Docker: startbar, aber nutzlos

- Der Daemon läuft beim Sitzungsstart nicht; `/var/run/docker.sock` fehlt.
- `sudo` ist ohne Passwort möglich, und `sudo dockerd` startet sauber
  (Storage-Driver `overlayfs`, buildkit initialisiert).
- **Aber:** Jeder `docker pull` bricht ab. Die Registry-Indizes
  (`registry-1.docker.io`, `ghcr.io`) antworten, die Blob-CDNs
  (`production.cloudfront.docker.com`, `pkg-containers.githubusercontent.com`)
  antworten mit **403**. Schon `hello-world` lässt sich nicht laden.

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
| `pypi.org`, `files.pythonhosted.org` | `earth-search.aws.element84.com` |
| `registry.npmjs.org` | `planetarycomputer.microsoft.com` |
| `api.github.com`, `github.com` | `catalogue.dataspace.copernicus.eu` |
| Ubuntu-Archiv (`apt`) | `stac.eopf.copernicus.eu` |
| `mcr.microsoft.com` | `nominatim.openstreetmap.org`, `tile.openstreetmap.org` |
| `sentinel-cogs.s3.us-west-2.amazonaws.com` (antwortet; nicht als Datenquelle geprüft) | `data.maap-project.org`, `quay.io`, Container-Blob-CDNs |

**Keine EO-Datenquelle und kein Geocoder ist erreichbar** — genau die Annahme,
auf der `projektplan.md` 2.4 und `docs/adr/0002-testaufteilung.md` aufbauen. Das
ist kein Mangel, sondern die Rechtfertigung dafür, ohne Live-Quellen zu testen.
Für den Kandidaten EOPF Sentinel Zarr Samples (M0 Schritt 6) heißt es: Eine
Quelle lässt sich in einer Cloud-Sitzung nicht ausprobieren, sondern nur über
aufgezeichnete Antworten oder lokal bei Otto.

`sentinel-cogs...amazonaws.com` antwortet als einziger EO-naher Host. Darauf ist
nichts gebaut: Der Host war nicht angefragt, wurde nicht als Datenquelle
verifiziert, und eine Policy kann ihn jederzeit schließen.

## 7. Was daraus folgt

1. **Setup-Skript:** `scripts/setup-cloud-session.sh` (Vorschlag, Otto trägt es
   selbst ein). Es legt das venv an, installiert Frontend-Pakete, startet
   Postgres und richtet PostGIS ein. Ohne Secrets, idempotent.
2. **Testaufteilung:** `docs/adr/0002-testaufteilung.md`.
3. **Offen für Otto:**
   - Sollen `production.cloudfront.docker.com` und
     `pkg-containers.githubusercontent.com` in die Allowlist der Umgebung, damit
     Docker in Sitzungen nutzbar wird? Empfehlung: **vorerst nein** — die
     Testaufteilung kommt ohne aus, und in CI gibt es Service-Container.
   - Objektspeicher in Tests: `moto` im Prozess oder nur in CI? Empfehlung:
     **`moto`**, sobald der erste Test ihn braucht (nicht jetzt).
