# M5-43 — Postgres-Image mit pgvector für Compose, CI und Cloud-Umgebung

**Status (27.11.2026):** Plan, **Stufe B**. Auftrag Otto vom 27.11.2026 (`plans/m5/m5-discovery-und-suche.md` §6.2), Erlaubnis für `.github/` im Auftrag; das Setup der Cloud-Umgebung trägt Otto selbst ein (Text in §6). Fragen F1–F4 in §9, von Otto am 27.11.2026 beantwortet (§9a).

Belegstufen wie in `plans/m5/m5-41-pgvector.md`: **M** in dieser Sitzung gemessen, **P** Primärquelle selbst gelesen, **P\*** Primärseite über das Abrufwerkzeug eines Hilfsagenten gelesen, **S** Suchtreffer, Seite nicht gelesen, **A** eigene Ableitung.

---

## 1. Auftrag und Voraussetzung

- **Ziel:** ein eigenes Dockerfile auf `postgis/postgis:16-3.7` plus pgvector ≥ 0.8.4. Es ersetzt `postgis/postgis:16-3.4` in `docker-compose.yml` und `.github/workflows/ci.yml`. Die Cloud-Umgebung bekommt pgvector 0.8.7 im Setup. Die CI baut das Dockerfile im Job mit Layer-Cache, die Bauzeit wird gemessen.
- **Entscheidungen, auf denen der Auftrag steht:** `adr/0026` §14 Punkt 4 und 5 (M5-41, G4 = 1, G5 = 1 mit Auflage; Otto, 15.11.2026).
- **Voraussetzung M5-41 gemergt:** ja, [#354](https://github.com/oscipal/earthX/pull/354) am 15.11.2026 [M, GitHub].
- **Nicht in diesem PR:** Spalte `halfvec`, HNSW-Index, `CREATE EXTENSION vector` in einer Migration, `shm_size` und `maintenance_work_mem` (alles M5-23).

## 2. Stand der Technik (abgefragt am 27.11.2026)

| Was | Stand | Beleg |
|---|---|---|
| pgvector, neueste Fassung | **0.8.7**, Tag `v0.8.7` = Commit `f37c13f68b57` | `git ls-remote --tags https://github.com/pgvector/pgvector` [M]; Tags 0.8.4 bis 0.8.7 vorhanden |
| pgvector, Lizenz | **PostgreSQL License** (SPDX `PostgreSQL`), frei, ohne Copyleft | `LICENSE` am Tag `v0.8.7`, https://raw.githubusercontent.com/pgvector/pgvector/v0.8.7/LICENSE [P\*]; schon in M5-41 §3.1 [P] |
| `postgis/postgis:16-3.7` | zuletzt gebaut **24.11.2026**; Basis `postgres:16-trixie`, PostgreSQL **16.16**, PostGIS **3.7.0**, Debian 13 trixie, glibc **2.41**, PGDG-Quelle `trixie-pgdg main 16` eingetragen | Docker Hub API `tags/16-3.7` (`tag_last_pushed`) [M]; `docker inspect` und `docker run` im Image [M]; Dockerfile https://github.com/postgis/docker-postgis/blob/master/16-3.7/Dockerfile [P] |
| `postgis/postgis:16-3.4` (heute) | zuletzt gebaut **14.10.2024**; PostgreSQL **16.4**, PostGIS **3.4.3**, Debian 11 bullseye, glibc **2.31** | Docker Hub API `tags/16-3.4` [M]; `docker inspect`/`docker run` [M] |
| `pgvector/pgvector:0.8.7-pg16-trixie` | gebaut 12.11.2026, ohne PostGIS | Docker Hub API [M] |
| pgvector in PGDG für trixie | **0.8.7-2.pgdg13+1** (Kandidat), daneben 0.8.7-1.pgdg13+2 und 0.8.7-1.pgdg13+1; 0.8.6 nicht mehr im Index | `apt-cache policy postgresql-16-pgvector` im Bau der CI am 27.11.2026 [M]. Aus der Sitzung nicht lesbar: `apt.postgresql.org`, `ftp.postgresql.org`, `www.postgresql.org` gesperrt (403) [M]; ein Suchtreffer nannte noch 0.8.6-1.pgdg13+2 [S], mit dem der erste Bau scheiterte |
| pgvector in Ubuntu 24.04 (Cloud-Sitzung) | nur **0.6.0** | `apt-cache policy postgresql-16-pgvector` [M] |

Beide Images legen die Daten unter `PGDATA=/var/lib/postgresql/data` ab und setzen `LANG=en_US.utf8` [M]. Die Hauptversion bleibt 16, das Datenverzeichnis ist also lesbar. Es ändern sich die Unterversion (16.4 → 16.16), PostGIS (3.4.3 → 3.7.0) und glibc (2.31 → 2.41).

## 3. Dockerfile (`compose/postgres/Dockerfile`)

Neben `compose/objectstore/`, wo die übrigen Dateien der Compose-Dienste liegen.

Mehrstufig (F1 = 3, §9a); die erste Fassung dieses PR installierte pgvector aus PGDG.

1. **Stufe `build`** auf `postgis/postgis:16-3.7`: `build-essential`, `git` und `postgresql-server-dev-16` (aus PGDG, das im Basis-Image eingetragen ist); `git clone --branch v0.8.7` von GitHub, Prüfung, dass der Tag auf den Commit `f37c13f68b57…` zeigt; `make OPTFLAGS=""` (ohne `-march=native`, läuft auf jedem x86-64-Rechner) und `make install DESTDIR=/out`, ohne die Header von pgvector.
2. **Endstufe** auf `postgis/postgis:16-3.7`: nur `COPY --from=build /out/usr/ /usr/`. Compiler, Header und `git` bleiben in der Bau-Stufe.
3. Prüfung im Bau: `default_version` in `vector.control` ≥ 0.8.4, sonst bricht der Bau ab.
4. **Anheben** ist eine bewusste Änderung: `PGVECTOR_TAG` und `PGVECTOR_COMMIT` zusammen, eigener PR.
5. Nichts weiter: kein eigenes Init-Skript, keine Einstellungen. Die Erweiterung legt später die Migration von M5-23 an.

## 4. Compose

`services.postgres`: `build: ./compose/postgres` statt `image: postgis/postgis:16-3.4`. Volume, Umgebung und Healthcheck bleiben. `docker compose build` baut das Image mit.

## 5. CI (`.github/workflows/ci.yml`)

- **`backend-tests` (vier Teile):** Ein Service-Container lässt sich nicht aus einem Dockerfile bauen (M5-41 §7 Punkt 2). Der Service `postgres` fällt weg; jeder Teil baut das Dockerfile mit `docker/setup-buildx-action` und `docker/build-push-action` (`load: true`, `cache-from`/`cache-to` vom Typ `gha`, eigener `scope`), startet den Container mit `docker run` auf `127.0.0.1:5432` und wartet auf `healthy`. Umgebung und Werte wie bisher. Den Cache schreibt nur Teil 1, alle lesen ihn.
- **`compose-topology`:** baut das Image über `docker compose build` mit, wie die übrigen.
- **Bauzeit:** gemessen an den Schritten „Build the Postgres image“ (kalt und mit Cache) und „Build images“, Ergebnis in §8 und im PR.

## 6. Cloud-Umgebung (Text für Otto)

Die Ubuntu-Pakete haben nur 0.6.0, PGDG ist gesperrt. Das Setup baut deshalb pgvector 0.8.7 aus dem GitHub-Tag, wie in M5-41 und `adr/0026` §14 Punkt 5. Gilt erst für neue Sessions. Der vollständige Text steht in `docs/cloud-umgebung.md` §5 (Nachtrag M5-43) und im PR. In dieser Sitzung getestet [M]: `apt-get install postgresql-server-dev-16 build-essential` 9 s, `git clone --branch v0.8.7` 0,6 s, `make` und `make install` 16 s.

Der Hook `scripts/setup-cloud-session.sh` ändert sich nicht: Er legt die Erweiterung nicht an (das tut die Migration von M5-23).

## 7. Test

T-C-Test `backend/tests/integration/test_postgres_extensions.py`: Die Datenbank bietet `vector` in einer Fassung ≥ 0.8.4 an (`pg_available_extension_versions`), dazu `postgis` und die Erweiterungen, die die Migrationen anlegen (`pg_trgm`, `unaccent`). Er läuft in CI und Cloud-Sitzung und überspringt sich nicht (`integration/conftest.py`). Ohne den Setup-Text aus §6 wird er in einer neuen Session rot (F2).

## 8. Messung der Bauzeit [M]

Schrittdauern aus der CI (27.11.2026), verglichen mit dem letzten Lauf auf `main` (46018938382, Service-Container `16-3.4`). Gemessen ist die mehrstufige Fassung (F1 = 3): Lauf 46031421724 ohne Cache, Lauf MIT_CACHE_RUN mit Cache.

| Schritt je Testteil | `main` (Service) | ohne Cache | mit Cache |
|---|---|---|---|
| „Initialize containers“ (Pull und Start von `16-3.4`) | 14–19 s | — | — |
| `setup-buildx` | — | 5–9 s | MIT_CACHE_BUILDX |
| Bau (`build-push-action`, mit `load`) | — | 45–50 s; Teil 1 114 s, weil er den Cache schreibt | MIT_CACHE_BUILD |
| Start bis `healthy` | — | 3–5 s | MIT_CACHE_START |
| **zusammen** | **14–19 s** | **55–64 s** (Teil 1 125 s) | **MIT_CACHE_SUM** |

Im Bau ohne Cache (Logs der Läufe 46031239436 und 46031421724): Basis-Image 5–6 s, `apt` mit `build-essential`, `git` und `postgresql-server-dev-16` 17–28 s, Klonen und Übersetzen 9–10 s, Export ins lokale Docker 10–11 s; die Endstufe kopiert nur die Dateien von pgvector. Die Prüfung meldet `pgvector 0.8.7`.

- **Compose-Job:** „Build images“ 81 s ohne Cache gegenüber 73 s auf `main`; die Bau-Stufe von Postgres läuft parallel zum Backend-Image.
- **Ohne Cache** (erster Lauf, neues Basis-Image, verdrängter Cache) kostet das je Teil rund 40–45 s mehr als der Service-Container, Teil 1 rund 110 s. Die Testteile laufen parallel und brauchen danach 4–6 min.
- Die erste Fassung (pgvector aus PGDG, ohne Bau-Stufe) brauchte mit Cache 18–27 s und ohne Cache 26–74 s.

## 9. Fragen an Otto

**F1 — Feste pgvector-Fassung aus PGDG.** Gemessen (§2): PGDG behält im Index mehrere Builds derselben Fassung, eine ältere Fassung (0.8.6) aber nicht. Die feste Paketfassung hält also bis zur nächsten Fassung von pgvector; danach bricht der Bau, sobald der Layer-Cache nicht mehr greift (neues Basis-Image, Ottos erster Bau).
1. So lassen (G4 = 1): feste Fassung `0.8.7-2.pgdg13+1`. Bricht der Bau, wird die Fassung bewusst angehoben (eine Zeile, eigener PR) **(Empfehlung)**
2. PGDG ohne feste Fassung, Bau bricht nur unter 0.8.4 ab; die Fassung steht im Bau-Log
3. Bau aus dem Quelltext am Tag `v0.8.7`, wie die Cloud-Umgebung: unabhängig von PGDG, Bau ohne Cache etwa 30 s länger

**F2 — Reihenfolge Setup und Merge.** Der neue T-C-Test verlangt pgvector auch in der Cloud-Sitzung.
1. Otto trägt den Setup-Text (§6) vor dem Merge ein; der Test gilt überall **(Empfehlung)**
2. Test nur in der CI; die Cloud-Sitzung prüft pgvector erst mit M5-23

**F3 — Basis-Image festnageln?** `postgis/postgis:16-3.7` wird laufend neu gebaut (zuletzt 24.11.2026).
1. Tag ohne Digest, wie entschieden: Unterversionen und Sicherheitskorrekturen kommen mit dem nächsten Bau **(Empfehlung)**
2. Tag mit Digest, Anheben von Hand

**F4 — Tiger-Geocoder in Ottos Bestand.** PostGIS 3.7 liefert `postgis_tiger_geocoder` nicht mehr mit; das neue Image legt ihn nicht an [M]. In Ottos Datenbank hat ihn das alte Init-Skript angelegt (Fassung 3.4.3, nur mitgelieferte Nachschlagetabellen, von EarthX nicht benutzt). Er bleibt nach dem Wechsel auf 3.4.3 liegen, und eine Rücksicherung aus `pg_dump` meldet für ihn Fehler (sonst vollständig, §10) [M].
1. Nach der Prüfung entfernen (`DROP EXTENSION postgis_tiger_geocoder`, Befehl in §11 Schritt 5); `fuzzystrmatch` bleibt **(Empfehlung)**
2. Liegen lassen


### 9a. Antworten Otto (27.11.2026)

| Frage | Antwort | Folge |
|---|---|---|
| F1 | 3 | pgvector aus dem GitHub-Tag `v0.8.7`, wie im Cloud-Setup, mehrstufig (Compiler und Header nicht im Image); Mindestfassung 0.8.4 bleibt als Prüfung; Anheben bleibt bewusste Änderung; Bauzeit ohne und mit Cache neu gemessen (§8) |
| F2 | 1 | Otto trägt den Setup-Text (§6) vor dem Merge ein; der T-C-Test gilt überall |
| F3 | 1 | Basis-Image per Tag `16-3.7`, ohne Digest |
| F4 | 1 | `DROP EXTENSION postgis_tiger_geocoder` als Teil von Schritt 5 der Anleitung (§11) |

Dazu: Die Anleitung in §11 nennt in Schritt 3 die Form nach dem Merge (`git pull origin main`); Otto wechselt erst nach dem Merge.

## 10. Ottos lokaler Bestand: Vorgehen und Simulation

Wechsel im **selben Volume**, ohne `docker compose down -v`: Die Hauptversion bleibt 16, das neue Image liest das Datenverzeichnis. Zwei Dinge sind danach nötig:

- **Erweiterungen:** PostGIS 3.4.3 → 3.7.0 über `postgis_extensions_upgrade()` (zieht `postgis_topology` mit), die übrigen mit `ALTER EXTENSION … UPDATE`.
- **Collation:** glibc 2.31 → 2.41. Postgres meldet „collation version mismatch“ bei jeder Verbindung; Text-Indizes können falsch sortieren. Abhilfe: `REINDEX DATABASE` und `ALTER DATABASE … REFRESH COLLATION VERSION` in jeder Datenbank.

Beides steht in `scripts/m5-43-postgres-switch/` und läuft im Container. Die Sicherung davor ist doppelt: logisch (`pg_dumpall --globals-only` und `pg_dump -Fc`) und physisch (Archiv des Datenverzeichnisses bei gestopptem Postgres, für den schnellen Rückweg auf das alte Image).

**Simulation in der Sitzung [M]:** Mini-Compose-Projekt mit demselben Dienst `postgres`. Altes Image `16-3.4` mit pgstac 0.9.12, allen 37 Migrationen, `catalog-load` und einer Texttabelle mit 10⁵ Zeilen und B-Baum. Dann Sicherung, Wechsel auf `16-3.7` mit pgvector (in der Sitzung aus dem Quelltext statt aus PGDG, das gesperrt ist), `upgrade-all.sh`, Prüfung. Ergebnis: Zeilenzahlen aller Tabellen gleich; PostGIS und Topologie 3.7.0; Collation 2.41 in allen Datenbanken; nach Neustart keine Warnung mehr; `pypgstac migrate` und `catalog-load` laufen danach durch; `vector` 0.8.7 angeboten. Die Rücksicherung des Dumps in ein frisches neues Image ging vollständig bis auf den Tiger-Geocoder (F4, wird in Schritt 5 entfernt) und die Meldung, dass die Rolle schon existiert. Den physischen Rückweg habe ich nicht simuliert; er braucht Löschen im Volume und gehört Otto.

## 11. PowerShell-Befehle für Otto (Windows, PowerShell 5.1)

Im Wurzelverzeichnis des Repos, **nach dem Merge** von #431. Ausgaben nach `..\earthx-ausgaben\m5-43`, nie ins Repo. Schritte 0 bis 2 **vor** `git pull` (Schritt 3): Bis dahin ist der Dienst `postgres` noch das alte Image.

**0. Ablage und Skripte holen (ohne den Arbeitsstand zu ändern)**

```powershell
$out = '..\earthx-ausgaben\m5-43'
New-Item -ItemType Directory -Force -Path $out | Out-Null
git fetch origin main
git archive -o "$out\switch.zip" FETCH_HEAD scripts/m5-43-postgres-switch
Expand-Archive -Force "$out\switch.zip" -DestinationPath $out
$s = "$out\scripts\m5-43-postgres-switch"
Get-ChildItem $s
```

**1. Stand vorher erfassen**

```powershell
docker compose up -d --wait postgres
docker compose cp "$s\versions.sql" postgres:/tmp/versions.sql
docker compose cp "$s\counts.sql" postgres:/tmp/counts.sql
docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At -f /tmp/versions.sql' | Out-File -Encoding utf8 "$out\versionen-vorher.txt"
docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At -f /tmp/counts.sql' | Out-File -Encoding utf8 "$out\zeilen-vorher.txt"
Get-Content "$out\versionen-vorher.txt"
```

Die Zeile `size` zeigt die Größe der Datenbank; Dump und Archiv brauchen zusammen etwa so viel Platz.

**2. Sicherung (logisch und physisch)**

```powershell
docker compose exec -T postgres sh -c 'pg_dumpall -U $POSTGRES_USER --globals-only -f /tmp/globals.sql && pg_dump -U $POSTGRES_USER -d $POSTGRES_DB -Fc -f /tmp/earthx.dump'
docker compose cp postgres:/tmp/globals.sql "$out\globals.sql"
docker compose cp postgres:/tmp/earthx.dump "$out\earthx.dump"
docker compose stop
docker compose run --rm --no-deps -v "$((Resolve-Path $out).Path):/backup" --entrypoint tar postgres -czf /backup/postgres-data.tgz -C /var/lib/postgresql/data .
Get-ChildItem $out
```

`docker compose cp` statt `>`: PowerShell 5.1 schreibt Umleitungen als UTF-16 und würde den binären Dump zerstören.

**3. Wechsel**

```powershell
git pull origin main
docker compose build postgres
docker compose up -d --wait postgres
```

Der Bau übersetzt pgvector einmal (rund 1 min, §8). Der neue Container hat ein leeres `/tmp`; deshalb kopiert Schritt 4 die Skripte noch einmal.

**4. Erweiterungen, Indizes und Collation**

```powershell
docker compose cp "$s\upgrade.sql" postgres:/tmp/upgrade.sql
docker compose cp "$s\upgrade-all.sh" postgres:/tmp/upgrade-all.sh
docker compose cp "$s\versions.sql" postgres:/tmp/versions.sql
docker compose cp "$s\counts.sql" postgres:/tmp/counts.sql
docker compose exec -T postgres sh -c 'sh /tmp/upgrade-all.sh 2>&1' | Tee-Object -FilePath "$out\upgrade.txt"
```

Erwartet: je Datenbank `== <Name>`, bei `earthx` und `template_postgis` „Upgrade to version 3.7.0 completed“, überall „changing version from 2.31 to 2.41“, kein `ERROR`. Die Warnungen „collation version mismatch“ davor sind der Grund für diesen Schritt.

**5. Prüfung**

```powershell
docker compose restart postgres
docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At -f /tmp/versions.sql' | Out-File -Encoding utf8 "$out\versionen-nachher.txt"
docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At -f /tmp/counts.sql' | Out-File -Encoding utf8 "$out\zeilen-nachher.txt"
Get-Content "$out\versionen-nachher.txt"
Compare-Object (Get-Content "$out\zeilen-vorher.txt") (Get-Content "$out\zeilen-nachher.txt")
docker compose logs --since 2m postgres | Select-String 'collation version mismatch'
```

Erwartet: `server|PostgreSQL 16.16 …`, jede Datenbank `|2.41`, `postgis|3.7.0`, `postgis_topology|3.7.0`, `vector offered|0.8.7`; `Compare-Object` und `Select-String` geben **nichts** aus (gleiche Zeilenzahlen, keine Warnung). `postgis_tiger_geocoder|3.4.3` steht noch da; ihn entfernt der nächste Befehl (F4 = 1), in deiner Datenbank und in `template_postgis`:

```powershell
docker compose exec -T postgres sh -c 'for db in $POSTGRES_DB template_postgis; do psql -U $POSTGRES_USER -d $db -c ''DROP EXTENSION IF EXISTS postgis_tiger_geocoder''; done'
docker compose exec -T postgres sh -c 'psql -U $POSTGRES_USER -d $POSTGRES_DB -At -f /tmp/versions.sql' | Select-String 'tiger'
```

Erwartet: zweimal `DROP EXTENSION`, danach gibt `Select-String` nichts aus. Die leeren Schemas `tiger` und `tiger_data` bleiben stehen; `fuzzystrmatch` bleibt.

**6. Alles starten**

```powershell
docker compose up -d
docker compose ps -a
```

`pgstac-migrate` und `catalog-load` müssen mit Exit 0 enden, die übrigen Dienste `healthy` sein. Danach im Browser: Data catalogue mit gelisteten Einträgen, eine Suche, eine Ebene mit Pyramide.

**Wenn etwas schiefgeht:** nichts löschen, Postgres mit `docker compose stop postgres` anhalten und mir die Dateien aus `..\earthx-ausgaben\m5-43` (ohne Dump und Archiv) schicken. Der Rückweg auf das alte Image aus `postgres-data.tgz` braucht Löschen im Volume; die Befehle dafür gebe ich dir dann einzeln.
