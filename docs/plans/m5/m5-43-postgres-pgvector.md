# M5-43 — Postgres-Image mit pgvector für Compose, CI und Cloud-Umgebung

**Status (27.11.2026):** Plan, **Stufe B**. Auftrag Otto vom 27.11.2026 (`plans/m5/m5-discovery-und-suche.md` §6.2), Erlaubnis für `.github/` im Auftrag; das Setup der Cloud-Umgebung trägt Otto selbst ein (Text in §6). Fragen F1–F3 in §9.

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
| pgvector in PGDG für trixie | **in der Sitzung nicht lesbar**: `apt.postgresql.org`, `ftp.postgresql.org` und `www.postgresql.org` sind aus der Sitzung gesperrt (403) [M]. Suchtreffer nennt `0.8.6-1.pgdg13+2` [S]. Die CI liest die Fassung beim Bau aus (`apt-cache policy` im Log) | §7 |
| pgvector in Ubuntu 24.04 (Cloud-Sitzung) | nur **0.6.0** | `apt-cache policy postgresql-16-pgvector` [M] |

Beide Images legen die Daten unter `PGDATA=/var/lib/postgresql/data` ab und setzen `LANG=en_US.utf8` [M]. Die Hauptversion bleibt 16, das Datenverzeichnis ist also lesbar. Es ändern sich die Unterversion (16.4 → 16.16), PostGIS (3.4.3 → 3.7.0) und glibc (2.31 → 2.41).

## 3. Dockerfile (`compose/postgres/Dockerfile`)

Neben `compose/objectstore/`, wo die übrigen Dateien der Compose-Dienste liegen.

1. `FROM postgis/postgis:16-3.7`.
2. pgvector aus PGDG mit fester Paketfassung (`postgresql-16-pgvector=<Fassung>`, als `ARG`), wie das Dockerfile von `postgis/postgis` PostGIS festschreibt (G4 = 1). Vorher `apt-cache policy` ins Bau-Log, damit eine abgelöste Fassung sofort sichtbar ist.
3. Prüfung im Bau: `default_version` in `vector.control` ≥ 0.8.4, sonst bricht der Bau ab.
4. Nichts weiter: kein eigenes Init-Skript, keine Einstellungen. Die Erweiterung legt später die Migration von M5-23 an.

## 4. Compose

`services.postgres`: `build: ./compose/postgres` statt `image: postgis/postgis:16-3.4`, dazu `image: earthx-postgres:16-3.7` als fester Name des gebauten Images. Volume, Umgebung und Healthcheck bleiben. `docker compose build` baut das Image mit.

## 5. CI (`.github/workflows/ci.yml`)

- **`backend-tests` (vier Teile):** Ein Service-Container lässt sich nicht aus einem Dockerfile bauen (M5-41 §7 Punkt 2). Der Service `postgres` fällt weg; jeder Teil baut das Dockerfile mit `docker/setup-buildx-action` und `docker/build-push-action` (`load: true`, `cache-from`/`cache-to` vom Typ `gha`, eigener `scope`), startet den Container mit `docker run` auf `127.0.0.1:5432` und wartet auf `healthy`. Umgebung und Werte wie bisher. Den Cache schreibt nur Teil 1, alle lesen ihn.
- **`compose-topology`:** baut das Image über `docker compose build` mit, wie die übrigen.
- **Bauzeit:** gemessen an den Schritten „Build the Postgres image“ (kalt und mit Cache) und „Build images“, Ergebnis in §8 und im PR.

## 6. Cloud-Umgebung (Text für Otto)

Die Ubuntu-Pakete haben nur 0.6.0, PGDG ist gesperrt. Das Setup baut deshalb pgvector 0.8.7 aus dem GitHub-Tag, wie in M5-41 und `adr/0026` §14 Punkt 5. Gilt erst für neue Sessions. Der vollständige Text steht in `docs/cloud-umgebung.md` §5 (Nachtrag M5-43) und im PR. In dieser Sitzung getestet [M]: `apt-get install postgresql-server-dev-16 build-essential` 9 s, `git clone --branch v0.8.7` 0,6 s, `make` und `make install` 16 s.

Der Hook `scripts/setup-cloud-session.sh` ändert sich nicht: Er legt die Erweiterung nicht an (das tut die Migration von M5-23).

## 7. Test

T-C-Test `backend/tests/integration/test_postgres_extensions.py`: Die Datenbank bietet `vector` in einer Fassung ≥ 0.8.4 an (`pg_available_extension_versions`), dazu `postgis` und die Erweiterungen, die die Migrationen anlegen (`pg_trgm`, `unaccent`). Er läuft in CI und Cloud-Sitzung und überspringt sich nicht (`integration/conftest.py`). Ohne den Setup-Text aus §6 wird er in einer neuen Session rot (F2).

## 8. Messung der Bauzeit

Wird nach dem ersten CI-Lauf eingetragen.

## 9. Fragen an Otto

**F1 — Feste pgvector-Fassung aus PGDG.** PGDG führt im Paketindex nur die jeweils neueste Fassung. Ein festgeschriebenes Paket lässt sich nach einem neuen Upload nicht mehr installieren; der Bau bricht ab, sobald der Layer-Cache nicht mehr greift (z. B. nach einem neuen Basis-Image).
1. So lassen (G4 = 1): feste Fassung aus PGDG. Bricht der Bau, wird die Fassung im Dockerfile bewusst angehoben **(Empfehlung, bis der erste CI-Lauf die PGDG-Fassung zeigt; dann aktualisiert in §8)**
2. PGDG ohne feste Fassung, aber Bau bricht unter 0.8.4 ab; die Fassung steht im Bau-Log
3. Bau aus dem Quelltext am Tag `v0.8.7`, wie die Cloud-Umgebung: überall dieselbe Fassung, unabhängig von PGDG; Bau etwa 30 s länger ohne Cache

**F2 — Reihenfolge Setup und Merge.** Der neue T-C-Test verlangt pgvector auch in der Cloud-Sitzung.
1. Otto trägt den Setup-Text (§6) vor dem Merge ein; der Test gilt überall **(Empfehlung)**
2. Test nur in der CI; die Cloud-Sitzung prüft pgvector erst mit M5-23

**F3 — Basis-Image festnageln?** `postgis/postgis:16-3.7` wird laufend neu gebaut (zuletzt 24.11.2026).
1. Tag ohne Digest, wie entschieden: Unterversionen und Sicherheitskorrekturen kommen mit dem nächsten Bau **(Empfehlung)**
2. Tag mit Digest, Anheben von Hand

## 10. Ottos lokaler Bestand

PowerShell-Befehle für Sicherung, Wechsel, `ALTER EXTENSION … UPDATE` und Prüfung stehen im PR und in §11. Vorgehen: Sicherung (logisch mit `pg_dump`, physisch als Archiv des Datenverzeichnisses), Wechsel im selben Volume ohne `down -v`, danach `ALTER EXTENSION … UPDATE` für alle Erweiterungen, `REINDEX DATABASE` und `ALTER DATABASE … REFRESH COLLATION VERSION` wegen der neuen glibc, Prüfung der Fassungen und Zeilenzahlen gegen den Stand vorher.

## 11. Ablauf lokal (wird mit der Umsetzung ergänzt)

Siehe PR-Beschreibung; nach der Simulation in der Sitzung hier nachgetragen.
