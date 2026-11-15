# M5-41 — Vektorsuche bei 10⁶ Einträgen: pgvector oder Vergleich im Prozess (Nachtrag zu `adr/0026` F3)

**Status (15.11.2026):** Bericht, **Stufe C** (nur lesen, messen und berichten, kein Produktivcode). Fragen G1–G6 von Otto am 15.11.2026 beantwortet (§10a); Entscheidung in `adr/0026` §14 (angenommen).
**Aufgabe:** M5-41 aus `plans/m5/m5-35-skalierbarkeit.md` §10. Otto hat am 14.11.2026 entschieden: Zielgröße **10⁶ gelistete Einträge** (M5-35 F3 = 1), und `adr/0026` F3 („ohne pgvector, Vergleich im Prozess `api`“) wird **vor M5-23** neu geöffnet, mit Recherche aus Primärquellen (M5-35 F5 = 1).
**Grundlage:** `plans/m5/m5-35-skalierbarkeit.md` Befund B4 (§5), F3, F5; `adr/0026` §3.2, §4.3, §4.4, §9, F3; `architekturplan.md` 0 Punkt 9, 3.1, 3.2, 5.3, 10, 12.
**Geändert in diesem PR:** dieser Bericht, ein Nachtrag-Entwurf in `adr/0026` §14, eine Zeile im Entscheidungslog und das Messskript `scripts/m5-41-vector-bench/bench.py`. Unverändert: `backend/`, `frontend/`, `docker-compose.yml`, `.github/`, `.claude/`, `CLAUDE.md`, Cloud-Umgebung.

Belegstufen wie in `adr/0026`: **M** in dieser Sitzung gemessen, **P** Primärquelle selbst gelesen (Quelltext, README, Changelog, Dockerfile im Repository des Projekts), **P\*** Primärseite über das Abrufwerkzeug eines Hilfsagenten gelesen (sinngemäß), **S** Suchtreffer, Seite nicht gelesen, **A** eigene Ableitung.

---

## 1. Kurzfassung

**Empfehlung: `adr/0026` F3 neu als V4 — pgvector ≥ 0.8.4 mit HNSW auf `halfvec`, aber gefilterte Anfragen exakt über den Index der Filterspalte, gewählt im Code.** Dafür ein eigenes Postgres-Image auf `postgis/postgis:16-3.7` für Compose und CI (§6, §7).

Was die Messung in der Sitzung zeigt (pgvector 0.8.7, synthetische Vektoren wie e5, 4 vCPU; §4):

1. **Ohne Filter trägt HNSW bis 10⁶:** 2–3 ms je Anfrage, Recall@10 0,98 (D = 384) bzw. 0,975 (768) mit `ef_search` 200; Bau 2–3 Minuten, Index 1,1 bzw. 2,0 GB mit `halfvec`. Exakt dauert dasselbe 220–700 ms in Postgres, 130–240 ms mit numpy auf einem Kern.
2. **Mit Filter ist HNSW unzuverlässig, gerade bei AOI-artigen Filtern:** Der Filter wirkt nach dem Index-Scan. Ohne iterativen Scan fehlen bei einem 1 %-Filter neun von zehn Treffern; mit iterativem Scan (`relaxed_order`) ist die Liste voll, aber bei einem Filter, der mit dem Inhalt zusammenhängt, stimmen nur 51–66 % (1 %) bzw. 78–89 % (10 %). Der Planer wählt bei 10⁶ trotz B-Baum auf der Filterspalte immer den HNSW-Index.
3. **Exakt hinter dem Filterindex** ist bei 10⁴ passenden Zeilen 22–29 ms schnell und hat Recall 1,0. Daraus die Regel: bis zu einer Schwelle (Vorschlag 5·10⁴ Zeilen) exakt, darüber HNSW mit iterativem Scan.
4. **`halfvec` statt `vector`:** halbe Größe, Recall gleich; bei 768 Dimensionen liegt `vector` außerhalb der Zeile (TOAST), exakt dann 4- bis 5-mal langsamer.
5. **Binäre Quantisierung** lohnt bei 384/768 Dimensionen nicht (Recall 0,90–0,97 erst bei Neusortierung von 200).
6. **Der heutige Weg (V1)** ist schon bei 10⁴ Zeilen ohne Filter langsam (0,9 s, wenn `real[]` über psycopg in Listen kommt). **Vektoren je Prozess `api` (V2)** tragen bis 10⁵, kosten bei 10⁶ aber 1,5–2,9 GB RAM je Instanz und 130–240 ms CPU je ungefilterter Anfrage.

Aus Primärquellen (§3): pgvector 0.8.7 ist aktuell; iterative Scans seit 0.8.0, wichtige Korrekturen beim Vacuum erst in 0.8.3/0.8.4, deshalb **Mindestfassung 0.8.4**. Kein fertiges Image hat PostGIS und pgvector zusammen; das heute genutzte `postgis/postgis:16-3.4` wird seit Oktober 2024 nicht mehr gebaut. Die Cloud-Sitzung hat aus Ubuntu nur pgvector 0.6.0; der Bau aus dem Quelltext geht. Verwaltete Anbieter führen 0.8.x (nur Suchtreffer), die Fassung ist auf einer Testinstanz zu prüfen.

Modulgrenzen ändern sich nicht: der Vektorarm wird eine SQL-Teilabfrage in `catalog`, das Modell bleibt in `api` (§8). Mit mehreren Instanzen `api` ist V4 besser als V2: eine Wahrheit in Postgres, kein Katalog im RAM jeder Instanz.

Offen bleibt der Recall auf echten e5-Embeddings; gemessen wird er in M5-23 (§9). Otto hat G1–G6 am 15.11.2026 beantwortet (§10a): V4 ist entschieden.

---

## 2. Was sich seit F3 geändert hat

- F3 = 2 stand unter der Annahme „einige Tausend Datensätze“ (`adr/0026` §1, K7: „von zehn auf einige Tausend“). Bis dahin ist der exakte Vergleich unbestritten richtig: exakt, keine Filterfallen, kein Image-Wechsel.
- Das Ziel ist jetzt 10⁶ gelistete Einträge (M5-35 F3 = 1). Gebaut ist der Vektorarm noch nicht (M5-23 offen); die Tabelle `earthx_dataset_search` (Migration `016_dataset_search.sql`) hat noch keine Spalte für das Embedding, M5-23 legt sie an [P]. Eine Entscheidung jetzt kostet also keinen Umbau.
- Der Vektorarm ist einer von drei Armen der RRF (Volltext, Trigramm, Vektor; `adr/0026` §4.4). Harte Filter (Raum, Zeit, Zugang) gelten **vor** der Fusion. Das ist der heikle Punkt für jeden ANN-Index (§3.1, §4.5).

---

## 3. Stand der Technik aus Primärquellen

### 3.1 pgvector 0.8.7 [P]

Gelesen am Tag `v0.8.7` (Commit `f37c13f`): `README.md`, `CHANGELOG.md`, `Dockerfile` im Repository https://github.com/pgvector/pgvector; aus demselben Stand in der Sitzung gebaut (§4).

- **Fassungen:** 0.8.7 vom 01.10.2026 ist die neueste. Iterative Index-Scans seit **0.8.0** (30.10.2024), zusammen mit besserer Kostenschätzung bei Filtern. `halfvec`, `bit`-Indizes und `binary_quantize` seit 0.7.0. Unterstützt Postgres 13 und neuer.
- **Korrekturen nach 0.8.0, die uns betreffen:** 0.8.2 „Fixed buffer overflow with parallel HNSW index build“; 0.8.3 „Fixed possible index corruption with HNSW vacuuming“; 0.8.4 „Fixed `hnsw graph not repaired` error with HNSW vacuuming“ und „possible error with inserts during HNSW vacuuming“. Für einen Katalog, in den der Harvester laufend schreibt und aus dem er löscht, ist damit **0.8.4** die sinnvolle Mindestfassung, nicht 0.8.0 [A aus P].
- **Ohne Index** sucht pgvector exakt („perfect recall“). Ein Index (HNSW oder IVFFlat) macht die Suche näherungsweise: „you will see different results for queries after adding an approximate index“.
- **HNSW:** Vorgaben `m` 16, `ef_construction` 64, `hnsw.ef_search` 40. „A higher value provides better recall at the cost of speed.“ Ergebnisse sind auf `ef_search` begrenzt: Ein `LIMIT 50` liefert bei `ef_search` 40 höchstens 40 Zeilen („Why are there less results …“), außer mit iterativem Scan. Typen: `vector` bis 2 000, `halfvec` bis 4 000 Dimensionen.
- **Bauzeit:** „Indexes build significantly faster when the graph fits into `maintenance_work_mem`“; sonst eine `NOTICE`. Parallel mit `max_parallel_maintenance_workers` (Vorgabe 2). Im Container muss `--shm-size` mindestens so groß sein wie `maintenance_work_mem`, „to avoid an error with parallel HNSW index builds“. Index nach dem Laden bauen; im Betrieb `CREATE INDEX CONCURRENTLY`.
- **Filter:** „With approximate indexes, filtering is applied *after* the index is scanned. If a condition matches 10% of rows, with HNSW and the default `hnsw.ef_search` of 40, only 4 rows will match on average.“ Empfohlen: zuerst ein gewöhnlicher Index auf der Filterspalte („Exact indexes work well for conditions that match a low percentage of rows“), sonst iterative Scans, partielle Indizes bei wenigen Werten, Partitionierung bei vielen.
- **Iterative Scans:** `hnsw.iterative_scan` = `off` (Vorgabe), `strict_order` oder `relaxed_order`; „relaxed … provides better recall“. Ende bei `hnsw.max_scan_tuples` (Vorgabe 20 000, „approximate and does not affect the initial scan“) oder Speicher (`hnsw.scan_mem_multiplier` × `work_mem`). Mit `relaxed_order` stellt eine `MATERIALIZED`-CTE die Reihenfolge wieder her (`ORDER BY distance + 0` ab Postgres 17). **Ein Filter auf die Distanz** (unsere Mindestähnlichkeit, `adr/0026` §4.3) gehört außerhalb der CTE, alle anderen Filter hinein.
- **Speicher:** „Use the `halfvec` type instead of `vector` for a smaller working set“; Indizes müssen nicht in den Speicher passen, laufen aber besser, wenn sie es tun. Binäre Quantisierung (`binary_quantize(...)::bit(n)` mit `bit_hamming_ops`, dann Neusortierung nach dem vollen Vektor) „for smaller indexes and faster build times at scale“.
- **Skalierung:** vertikal; horizontal über Lese-Replikate („Scale horizontally with replicas“) oder Sharding (Citus, PgDog). pgvector schreibt ins WAL, Replikation und PITR gehen.
- **Hybrid-Suche:** Das README verweist für die Fusion mit Volltext auf RRF — dasselbe Muster wie `adr/0026` §4.4.
- **Lizenz:** PostgreSQL License (`LICENSE`) [P].

### 3.2 Images [P]

| Image | Basis | pgvector | Beleg |
|---|---|---|---|
| `postgis/postgis:16-3.4` (heute in `docker-compose.yml` und `.github/workflows/ci.yml`) | `postgres:16-bullseye`, PostGIS 3.4.3 | nein | Dockerfile im Repository `postgis/docker-postgis` vor dem Commit `27528c8` (15.10.2024) [P]; **letzter Push des Tags am 14.10.2024** (Docker Hub API, `tag_last_pushed`) [M] |
| `postgis/postgis:16-3.7`, `17-3.7` | `postgres:16-trixie` bzw. `17-trixie`, PostGIS 3.7.0, Paket aus PGDG | nein | `16-3.7/Dockerfile` auf `master` [P]; gepusht am 14.11.2026 [M] |
| `pgvector/pgvector:0.8.7-pg16-trixie`, `-bookworm` | offizielles `postgres`, pgvector aus dem Quelltext `v0.8.7` | ja, ohne PostGIS | `Dockerfile` im Repository pgvector [P]; gepusht am 12.11.2026 [M] |
| pgstac (`docker/pgstac/Dockerfile`, `main` und `v0.10.1`) | `postgres:17-trixie` mit PostGIS 3, `pgtap`, `plpgsql-check`, `partman` | nein | [P\*] |
| offizielles `postgres:16-bookworm` | Debian bookworm, Quelle `apt.postgresql.org … bookworm-pgdg main 16` ist eingetragen | — | `docker-library/postgres` `16/bookworm/Dockerfile` [P] |

Folgen [A]:
- **Kein fertiges Image hat PostGIS und pgvector zusammen.** Der Weg ist ein eigenes, kleines Dockerfile: `FROM postgis/postgis:<pg>-<postgis>` plus pgvector. Weil die offiziellen `postgres`-Images die PGDG-Quelle schon eingetragen haben, reicht `apt-get install postgresql-<pg>-pgvector`; ob PGDG dort 0.8.x führt, ist nur über Suchtreffer belegt (`postgresql-16-pgvector 0.8.2-1.pgdg12+1` für bookworm) [S], `apt.postgresql.org` war aus der Sitzung nicht erreichbar. Unabhängig davon geht der Bau aus dem Quelltext mit festem Tag, wie im Dockerfile von pgvector selbst (`build-essential`, `postgresql-server-dev-<pg>`, `make`, `make install`, Pakete wieder entfernen) [P].
- **Nebenbefund:** Das heute verwendete `postgis/postgis:16-3.4` wird seit Oktober 2024 nicht mehr gebaut (Debian bullseye, Postgres 16 aus diesem Stand). Ein Wechsel des Images ist also ohnehin fällig; er lässt sich mit pgvector verbinden. Die Wahl zwischen `16-3.7` (gleiche Hauptversion, kein Dump nötig) und `17-3.7` ist eine eigene Frage (G4).
- Die Cloud-Sitzung hat Ubuntu-Pakete: `postgresql-16-pgvector` nur in **0.6.0** [M] (ohne iterative Scans, ohne die Korrekturen aus §3.1). Der Bau aus dem Quelltext von GitHub geht in der Sitzung (`postgresql-server-dev-16` aus Ubuntu, Tag `v0.8.7`, `make install`; so in dieser Sitzung gemacht) [M].

### 3.3 Verwaltetes Postgres (für M6) [S]

Die Seiten der Anbieter waren aus der Sitzung nicht erreichbar (AWS, Azure, Google-Doku, Scaleway, OVH, DigitalOcean, Neon, Supabase); alle Angaben sind Suchtreffer:

| Anbieter | pgvector laut Treffer | Quelle |
|---|---|---|
| AWS RDS for PostgreSQL | 0.8.0 ab 17.1, 16.5, 15.9 (Nov. 2024) | https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-rds-for-postgresql-pgvector-080 |
| Aurora PostgreSQL | 0.8.0 ab 16.8 (Apr. 2025) | https://aws.amazon.com/about-aws/whats-new/2025/04/pgvector-0-8-0-aurora-postgresql |
| Google Cloud SQL | bis 0.8.5 (Aug. 2026); nach Wartung `ALTER EXTENSION vector UPDATE` selbst | https://docs.cloud.google.com/sql/docs/postgres/release-notes |
| Scaleway (EU) | 0.8.0 auf PG 16, 0.8.1 auf PG 17 (Stand Sept. 2025) | https://www.scaleway.com/en/docs/managed-databases-for-postgresql-and-mysql/reference-content/pg-version-updates.md |
| OVHcloud (EU) | gelistet, Fassung unbekannt | https://docs.ovhcloud.com/en/guides/public-cloud/databases/postgresql-extensions |
| Azure Flexible Server | gelistet, Fassung nicht belegt | https://learn.microsoft.com/azure/postgresql/flexible-server/release-notes |

Folge [A]: pgvector schließt keinen der großen Anbieter aus, aber **die Fassung ist beim Anbieter oft älter als 0.8.4** (§3.1). Die Anforderung an M6 heißt deshalb „pgvector ≥ 0.8.4 mit `halfvec` und `hnsw.iterative_scan`“, geprüft mit `SELECT * FROM pg_available_extension_versions WHERE name = 'vector'` auf einer Testinstanz, nicht aus der Doku.

### 3.4 Embedding-Modelle [P\*]

multilingual-e5-small hat 384, -base 768 Dimensionen (`microsoft/unilm`, `e5/README.md`). Dass e5-Ähnlichkeiten eng beieinander liegen (meist 0,7–1,0) und dass die Modellkarte Normierung und Kosinus empfiehlt, ist nur über Suchtreffer belegt [S]; `huggingface.co` ist aus der Sitzung gesperrt. Für die Messung heißt das: Die synthetischen Vektoren in §4 sind so gebaut, dass zufällige Paare im Mittel bei Kosinus 0,75 liegen.

---

## 4. Messung in der Sitzung

### 4.1 Aufbau [M]

- **Rechner:** Cloud-Sitzung, 4 vCPU, 15 GB RAM, ohne Swap. Postgres 16.15 (Ubuntu), pgvector **0.8.7** aus dem Quelltext gebaut, in einer eigenen leeren Datenbank (danach gelöscht). Für die Messung `shared_buffers` 4 GB, `effective_cache_size` 10 GB, beim Indexbau `maintenance_work_mem` 5 GB und 3 parallele Worker plus Leiter; sonst Vorgaben. Client (psycopg) und Datenbank teilen sich die 4 Kerne.
- **Skript:** `scripts/m5-41-vector-bench/bench.py`, Aufruf im Kopf des Skripts. Eine JSON-Zeile je Schritt; die Rohdaten liegen nicht im Repo.
- **Daten:** synthetisch, D = 384 (e5-small) und 768 (e5-base), N = 10⁴, 10⁵, 10⁶. Einheitsvektoren mit gemeinsamer Richtung, gehäuft auf einem 64-dimensionalen Unterraum; Kosinus zufälliger Paare im Mittel 0,75, des nächsten Nachbarn einer Anfrage 0,94 (so eng wie e5 laut §3.4). 200 Anfragen aus demselben Erzeuger, nicht aus dem Korpus. Vergleich mit Kosinus.
- **Filter:** `u` gleichverteilt und unabhängig vom Vektor (wie ein Zugangsfilter), `grp` = nächster von 256 Ankerpunkten (wie eine AOI: hält ganze Gegenden des Vektorraums). Je bei 1 % und 10 % der Zeilen.
- **Recall@k:** Anteil der exakten float32-Top-k unter den Zeilen, die den Filter bestehen. k = 10 (erste Seite) und k = 50 (Tiefe einer Liste für die RRF).
- **Latenz:** p50/p95 aus Sicht des Clients über 200 Anfragen (exakte Suche bei 10⁶ über 20), warmer Cache, ein Client. numpy auf **einem** Faden (`OPENBLAS_NUM_THREADS=1`), weil in `api` mehrere Anfragen gleichzeitig laufen.
- **Grenzen:** Recall auf synthetischen Vektoren ist nicht der Recall auf e5 (§9, Messung in M5-23). Die Tabelle hat nur Kennung, zwei Filterspalten und den Vektor; die echte Tabelle trägt Texte und `tsvector`, ein exakter Scan wird dort langsamer [A]. Keine gleichzeitigen Schreibzugriffe, kein `VACUUM` unter Last.

### 4.2 Speicher und Bau [M]

MB; Bauzeit in s mit 4 Prozessen. V2 laden = alle Vektoren als `halfvec` per binärem `COPY` nach `api` holen (Start einer Instanz).

| N | D | numpy float32 | Tabelle `vector` | Tabelle `halfvec` | HNSW `vector` | HNSW `halfvec` | Index binär (BQ) | V2 laden |
|---|---|---|---|---|---|---|---|---|
| 10⁴ | 384 | 15 | 16 | 9 | 20 (1,4 s) | 11 (1,6 s) | 3 (1,3 s) | 0,02 s |
| 10⁴ | 768 | 29 | 41 | 16 | 39 (2,9 s) | 20 (1,9 s) | 4 (1,9 s) | 0,04 s |
| 10⁵ | 384 | 147 | 159 | 89 | 195 (11 s) | 112 (11 s) | 33 (7 s) | 0,2 s |
| 10⁵ | 768 | 293 | 403 | 159 | 391 (52 s) | 195 (13 s) | 38 (23 s) | 0,4 s |
| 10⁶ | 384 | 1 465 | 1 584 | 890 | 1 953 (140 s) | 1 116 (137 s) | 333 (90 s) | 2,3 s |
| 10⁶ | 768 | 2 930 | 4 029 | 1 584 | 3 906 (208 s) | 1 953 (177 s) | 380 (111 s) | 4,5 s |

- **`vector(768)` liegt außerhalb der Zeile (TOAST):** 3 080 Byte je Wert gegen 1 544 bei `halfvec(768)`. Die Tabelle ist 2,5-mal so groß, ein exakter Scan bei 10⁵ dauert 340 statt 70 ms, der Indexbau 52 statt 13 s. Bei 384 Dimensionen liegen beide in der Zeile. Das README nennt den Effekt bei parallelen Scans („out-of-line storage“) [P]; die Größe ist gemessen [M].
- **Bau bei 10⁶:** 2–3 Minuten mit 4 Prozessen, der Graph passte in 5 GB `maintenance_work_mem` (keine `NOTICE`). Ein Neubau nach Modellwechsel kostet also Minuten; das Einbetten von 10⁶ Texten kostet Stunden (M5-35 §5.2).
- **RAM der Datenbank** bei 10⁶ mit `halfvec`: Tabelle 0,9–1,6 GB plus Index 1,1–2,0 GB. Das README rät, dass der Index in den Speicher passt; laut Issue #700 bricht der Durchsatz ein, sobald er `shared_buffers` übersteigt [P\*].

### 4.3 Ohne Filter [M]

k = 10, p50/p95 in ms, R = Recall@10. Exakt mit `halfvec`, ein Prozess bzw. mit 2 parallelen Workern.

| N | D | V2 numpy | V3 exakt (1 / 3 Prozesse) | V4 HNSW `ef_search` 40 | 100 | 200 |
|---|---|---|---|---|---|---|
| 10⁴ | 384 | 0,9 / 1,2 | 3,1 / 3,4 | R 0,996 · 0,6 | 0,996 · 0,8 | 0,996 · 1,4 |
| 10⁴ | 768 | 1,3 / 2,4 | 7,8 / 7,9 | 0,999 · 0,8 | 0,999 · 0,9 | 0,999 · 1,5 |
| 10⁵ | 384 | 12 / 13 | 45 / 28 | 0,964 · 1,2 | 0,990 · 1,4 | 0,996 · 1,7 |
| 10⁵ | 768 | 25 / 52 | 70 / 36 | 0,948 · 1,4 | 0,992 · 1,6 | 0,997 · 1,7 |
| 10⁶ | 384 | 129 / 212 | 471 / 221 | 0,847 · 2,0 | 0,946 · 1,9 | **0,981 · 2,2** |
| 10⁶ | 768 | 242 / 382 | 698 / 297 | 0,795 · 3,6 | 0,938 · 2,3 | **0,975 · 3,1** |

- HNSW bleibt bei 2–3 ms bis 10⁶; der Recall sinkt mit N, `ef_search` 200 hält ihn bei 0,98. Mit `vector` statt `halfvec` sind Recall und Zeit fast gleich (10⁶, 384: 0,985 bei 2,7 ms).
- **Tiefe der Liste:** Mit `LIMIT 50` und `ef_search` 40 kommen höchstens 40 Zeilen (gemessen: im Mittel 40,0), wie das README sagt; mit iterativem Scan 50. Für die RRF muss `ef_search` ≥ Tiefe sein.

### 4.4 V1 und V2: Vektoren nach `api` holen [M]

- **V1 wie in `adr/0026` §4.3** (Spalte `real[]`, je Anfrage die gefilterten Zeilen über psycopg holen, in numpy wandeln): 10⁴ Zeilen 0,9 s (384) bzw. 2,2 s (768), 10⁵ Zeilen 11 bzw. 21 s. Der Aufwand liegt im Umwandeln der Arrays in Python-Listen. Über binäres `COPY` von `halfvec` sind es 0,02 s für 10⁴ und 2,3–4,5 s für 10⁶ — als Start einer Instanz tragbar, je Anfrage nicht.
- **V2:** schnell bis 10⁵ (12–25 ms auf einem Kern), bei 10⁶ 129–242 ms ohne Filter und 1,5–2,9 GB je Instanz `api`. Mit 1 %-Filter 3–8 ms.

### 4.5 Mit Filtern [M]

10⁶ Zeilen, `halfvec`, D = 768 (384 in Klammern, wo abweichend), k = 10 bzw. 50, Recall · p50 in ms:

| Weg | `u` 1 % | `grp` 1 % | `u` 10 % | `grp` 10 % |
|---|---|---|---|---|
| HNSW, `ef_search` 100, ohne iterativen Scan, k = 10 | 0,10 (1,0 Zeilen) | 0,07 (0,7 Zeilen) | 0,83 (8,9 Zeilen) | 0,46 (5,0 Zeilen) |
| HNSW, `relaxed_order`, `ef_search` 200, k = 10 | 0,80 · 17 | **0,66 · 41** | 0,97 · 2,8 | 0,88 · 4,3 |
| dasselbe, k = 50 | 0,65 · 53 | **0,53 · 60** | 0,95 · 7,4 | 0,78 · 13 |
| HNSW, `relaxed_order`, `max_scan_tuples` 200 000, `scan_mem_multiplier` 8, k = 10 | — | 0,72 · 40 (p95 131) | — | 0,86 · 3,9 |
| **Planer** mit B-Baum auf `u`/`grp`, `relaxed_order`, k = 10 | 0,80 (HNSW) | 0,65 (HNSW) | 0,94 (HNSW) | 0,86 (HNSW) |
| **exakt hinter dem Filterindex** (`enable_indexscan = off`, Bitmap-Scan, 1 Prozess) | **1,0 · 22** (22) | **1,0 · 24** (29) | 1,0 · 214 (180) | 1,0 · 231 (228) |
| V2 numpy mit Maske | 1,0 · 7,5 (2,9) | 1,0 · 8,4 (4,0) | 1,0 · 126 (68) | 1,0 · 128 (71) |

- **Ohne iterativen Scan** fehlen fast alle Treffer, genau wie das README es vorrechnet (1 % · 100 ≈ 1 Zeile).
- **Iterative Scans** füllen die Liste, aber mit falschen Zeilen, wenn der Filter mit dem Inhalt zusammenhängt (`grp`): Recall 0,53–0,66 bei 1 %, 0,78–0,88 bei 10 %. Mehr `max_scan_tuples` hebt das nur auf 0,72, bei dreifacher p95. Bei unabhängigem Filter (`u`) reicht der iterative Scan ab 10 %.
- **Der Planer** wählt bei 10⁶ in allen Fällen den HNSW-Index, auch bei 1 %. Bei 10⁴ wählte er für 1 % noch den Bitmap-Scan (Recall 1,0), bei 10⁵ je nach Fall das eine oder das andere (z. B. `grp` 1 %, k = 10: HNSW mit 0,77). Auf die Wahl des Planers ist also kein Verlass.
- **Exakt hinter dem Filterindex** ist bei 1 % (10⁴ Zeilen) mit 22–29 ms schnell genug und exakt; bei 10 % (10⁵ Zeilen) 180–231 ms auf einem Kern. Bei 10⁵ Zeilen insgesamt kostet derselbe Weg 1,4–2,2 ms (1 %) bzw. 13–23 ms (10 %).
- `strict_order` lag in allen gefilterten Fällen unter `relaxed_order` (z. B. 10⁴, `u` 1 %: 0,89 gegen 0,97).

### 4.6 Durchsatz [M]

HNSW `halfvec`, `ef_search` 100, k = 10, ohne Filter, Anfragen je Sekunde mit 1 bzw. 4 Clients auf demselben Rechner (4 vCPU für Datenbank und Clients):

| N | D = 384 | D = 768 |
|---|---|---|
| 10⁴ | 876 / 1 902 | 736 / 1 279 |
| 10⁵ | 544 / 1 653 | 451 / 1 236 |
| 10⁶ | 350 / 1 202 | 246 / 873 |

### 4.7 Binäre Quantisierung [M]

HNSW auf `binary_quantize(emb)::bit(D)` mit Hamming-Abstand, dann Neusortierung nach dem vollen Vektor (README). 10⁶, D = 384: Tiefe 40 Recall@10 0,48, Tiefe 200 0,905 bei 3 ms; D = 768: 0,59 bzw. 0,967 bei 11 ms. Der Index ist klein (0,33 GB statt 1,1 GB), aber bei 384/768 Dimensionen verliert ein Bit je Dimension zu viel. Das README empfiehlt die binäre Quantisierung für Skalierung, nennt aber keine Dimension [P]; für unsere Modelle lohnt sie nicht [A aus M].

---

## 5. Optionen

Namen wie in M5-35 §5.3. Zahlen aus §4 (D = 384, 4 vCPU), Bewertung [A].

| Option | Wie | 10⁶: Antwort | 10⁶: Recall@10 | Speicher bei 10⁶ | trägt bis | Preis |
|---|---|---|---|---|---|---|
| **V1** F3 = 2 wie entschieden | Vektoren als Spalte, je Anfrage die gefilterten Zeilen nach `api` holen, numpy | Sekunden bis Minuten (schon 10⁴ ohne Filter: 0,9 s mit `real[]` über psycopg; binär 0,02 s) | 1,0 | DB 0,9 GB | ~10⁴ | keiner jetzt, Umbau danach |
| **V2** Vektoren je Prozess `api` | beim Start alle laden, im Speicher vergleichen | 128 ms (p95 212 ms) ohne Filter, 1 Kern; mit 1 %-Filter 3–4 ms | 1,0 | **1,5 GB je Instanz `api`** (float32) | ~10⁵ | RAM × Instanzen, Nachladen, verschiedene Stände (§8.2) |
| **V3** pgvector exakt, ohne Index | `ORDER BY emb <=> q` als Seq Scan | 220–470 ms ohne Filter | 1,0 | DB 0,9 GB (`halfvec`) | ~10⁵ | Image; O(N) je Anfrage in der Datenbank |
| **V4** pgvector, HNSW auf `halfvec`, gefilterte Anfragen exakt über den Filterindex | zwei Wege, im Code gewählt (§6) | **2 ms** ohne Filter (`ef_search` 200); gefiltert-exakt 22–29 ms bei 10⁴ passenden Zeilen, ~200 ms bei 10⁵ | 0,98 ohne Filter; **1,0** gefiltert-exakt | DB 0,9 GB Tabelle + 1,1 GB Index | 10⁶–10⁷ | Image, Indexbau 2–3 min, Recall < 1 ohne Filter |
| V4′ wie V4, aber Filter nur über iterative Scans bzw. den Planer | eine Abfrage, Planer entscheidet | 2–50 ms | **0,51–0,89** bei inhaltsnahen Filtern | wie V4 | — | stille Lücken bei AOI-Filtern (§4.5) |
| V4b binäre Quantisierung + Neusortierung | HNSW auf `bit(384)` | 3 ms | 0,91 (Tiefe 200) | Index 0,33 GB | 10⁷ | Recall bei 384 Dim. zu niedrig |
| **V5** eigener Vektordienst | — | — | — | — | > 10⁷ | ausgeschlossen (`architekturplan.md` 0 Punkt 9) |

- **V1** trägt die Zielgröße nicht; selbst bei 10⁴ hängt es an der Art der Übertragung (§4.4).
- **V2** ist schnell genug bis 10⁵, aber bei 10⁶ kostet jede Instanz `api` 1,5 GB (D = 384) bzw. 2,9 GB (D = 768) und 128–250 ms Rechnung auf einem Kern je Anfrage ohne Filter. Mit mehreren Instanzen und laufendem Harvest wird das zur eigenen Infrastruktur (Nachladen, Stände).
- **V3** ist eine gute Brücke: exakt, ohne Index, dieselbe Spalte wie V4. Ohne Filter bei 10⁶ zu langsam für eine Suche beim Tippen.
- **V4** ist schnell und hält die Filter exakt, weil gefilterte Anfragen nicht durch den ANN-Index gehen. Der Preis ist Recall < 1 ohne Filter; bei der RRF zählt nur der Rang, und der lexikalische Arm fängt Namen und Kürzel exakt (`adr/0026` §4.2).
- **V4′** ist die naheliegende, aber falsche Form: Der Planer wählt bei 10⁶ auch für einen 1 %-Filter den HNSW-Index (§4.5), und ein AOI-Filter hängt mit dem Inhalt zusammen (regionale Datensätze liegen im Vektorraum nahe beieinander) — genau der Fall `grp`, in dem iterative Scans die Lücke nicht schließen.

---

## 6. Empfehlung

**V4: pgvector ≥ 0.8.4 mit HNSW auf `halfvec`, gefilterte Anfragen exakt über den Index der Filterspalte.** Damit gilt der Kern von `adr/0026` §4.3 weiter („Exakt heißt auch: Filter und Vektor vertragen sich ohne die Fallen gefilterter ANN-Suche“) — für gefilterte Anfragen bleibt die Suche exakt; nur die ungefilterte nutzt den Index.

Im Einzelnen (Vorschlag für M5-23, Stufe B):

1. **Spalte** `embedding halfvec(D)` in `earthx_dataset_search` (D aus dem gewählten Modell; neue Migration in M5-23). Ob gelistete Einträge als pgstac-Collections oder in einer eigenen Tabelle liegen, entscheidet M5-40 (`adr/0033` §2.3, §13); für den Vektorarm zählt, dass volle und gelistete Einträge in **einer** Suchtabelle mit einer Spalte und einem Index stehen, sonst wären es zwei ANN-Suchen mit eigener Zusammenführung [A]. `halfvec` statt `vector`: halbe Tabelle, bei D = 768 bleibt die Zeile unter der TOAST-Grenze (exakt 70 statt 340 ms bei 10⁵), Recall gegen float32 0,998–1,0 [M].
2. **Index** `USING hnsw (embedding halfvec_cosine_ops)` mit den Vorgaben `m` 16, `ef_construction` 64; `SET LOCAL hnsw.ef_search = 200` je Anfrage (Recall@10 0,975–0,98 bei 10⁶ für 0,4–0,8 ms mehr als mit 100) [M]. `ef_search` nie kleiner als die Tiefe der Liste des Vektorarms für die RRF.
3. **Zwei Wege, im Code gewählt, nicht vom Planer:**
   - **ohne harten Filter:** HNSW-Index-Scan, `LIMIT` = Tiefe des Arms;
   - **mit hartem Filter (Raum, Zeit, Zugang):** zuerst zählen, wie viele Zeilen den Filter bestehen (über die Indizes der Filterspalten; dafür braucht es die räumliche Spalte mit GiST aus M5-42/B7). Bis zu einer Schwelle T **exakt** über diese Zeilen (`SET LOCAL enable_indexscan = off`, sodass der Planer über den Filterindex liest und sortiert), darüber HNSW mit `hnsw.iterative_scan = relaxed_order` in einer `MATERIALIZED`-CTE, außen nach Distanz sortiert. Vorschlag T = 5·10⁴ Zeilen: Exakt kostet gemessen rund 2,2 ms je 10³ Zeilen auf einem Kern (§4.5: 22–29 ms für 10⁴, 180–231 ms für 10⁵), bei T also gut 100 ms. Darüber lag der Recall des iterativen Scans in der Messung bei 0,94–0,97 (unabhängiger Filter, 10 %) bzw. 0,78–0,89 (inhaltsnah, 10 %); das ist die verbleibende Lücke von V4, kleiner, je mehr Zeilen den Filter bestehen [A]. Die Schwelle ist eine Zahl in der Konfiguration und wird mit echten Daten nachgestellt (§9).
   - **Mindestähnlichkeit** (`adr/0026` §4.3) als Filter außerhalb der CTE (README „Iterative Index Scans“).
4. **Fassung:** pgvector ≥ 0.8.4 (Korrekturen beim Vacuum, §3.1), im Image fest 0.8.7.
5. **Image:** eigenes Dockerfile auf `postgis/postgis:16-3.7` (§7), für Compose, CI und als Vorlage für die Cloud-Sitzung.
6. **Bewertungs-Set:** unverändert; der Test in der CI läuft mit den Vektoren aus der Fixture gegen dieselbe Spalte (`adr/0026` §8.4). Bei zehn bis Tausend Zeilen ist das Ergebnis mit und ohne Index praktisch gleich (Recall@10 0,996–1,0 bei 10⁴ ohne Filter, §4.3).
7. **Nicht nötig:** binäre Quantisierung (Recall bei 384/768 Dim. zu niedrig), Partitionierung, eigener Dienst.

Was gleich bleibt: Modell und Einbetten der Anfrage im Prozess `api` (`adr/0026` F2), RRF mit k = 60, harte Filter vor der Fusion, Schnittstelle (F9).

**Reihenfolge (G6, §10a):** erst der Wechsel des Postgres-Images als eigene Aufgabe (Stufe B), dann M5-23 mit V4 und der Messung mit echten Embeddings (§9).

---

## 7. Weg ins Image

Drei Orte brauchen dasselbe Postgres: Compose, CI und die Cloud-Sitzung; in M6 der Anbieter. Vorschlag [A], Umsetzung erst nach Freigabe (G4, G5), weil `.github/` und die Cloud-Umgebung nur mit Otto geändert werden:

1. **Ein Dockerfile** im Repo (z. B. `docker/postgres/Dockerfile`): `FROM postgis/postgis:16-3.7` (gepflegt, trixie; §3.2) und `apt-get install postgresql-16-pgvector` mit fester Fassung aus PGDG; geht das nicht, Bau aus dem Quelltext am Tag `v0.8.7` wie im Dockerfile von pgvector [P]. Compose baut daraus (`build:` statt `image:`) und setzt `shm_size` (§8.3).
2. **CI** (`.github/workflows/ci.yml`, heute `services.postgres.image: postgis/postgis:16-3.4`): Ein Service-Container lässt sich in GitHub Actions nicht aus einem Dockerfile bauen [A]. Wege:
   - (a) dasselbe Dockerfile im Job bauen (mit Cache) und Postgres als Schritt starten statt als Service — **eine Wahrheit mit Compose**;
   - (b) Service `postgis/postgis:16-3.7` lassen und vor den Tests `docker exec … apt-get install postgresql-16-pgvector` — kein eigenes Image, aber Netz zu PGDG in jedem der vier Shards;
   - (c) eigenes Image in eine Registry (GHCR) und als Service nutzen — ein Workflow und eine Registry mehr.
   Das pgvector-Projekt selbst empfiehlt für Service-Container sein Image `pgvector/pgvector` (setup-pgvector, README „Service“) [P]; das hat kein PostGIS und passt deshalb nicht.
3. **Cloud-Sitzung:** Die Ubuntu-Pakete haben nur 0.6.0 [M], `apt.postgresql.org` ist gesperrt [M]. Was geht: im Setup der Umgebung `postgresql-server-dev-16` aus Ubuntu und `make install` aus dem GitHub-Tag (so in dieser Sitzung, wenige Sekunden) [M]. Das Setup-Skript der Umgebung gehört Otto.
4. **Wechsel des Images in Compose:** Bleibt die Hauptversion 16, bleibt das Datenverzeichnis lesbar. Von bullseye nach trixie ändert sich aber die glibc und damit die Sortierfolge von Text; Postgres warnt dann vor abweichenden Collation-Versionen, Text-Indizes sind neu zu bauen [A, nicht gemessen]. Für Entwicklungsdaten reicht `REINDEX DATABASE` oder ein frisches Volume plus `catalog-load`.
5. **M6:** Anforderung an den Anbieter „pgvector ≥ 0.8.4, `halfvec`, `hnsw.iterative_scan`“, geprüft auf einer Testinstanz (§3.3, §9).

---

## 8. Modulgrenzen und Skalierung über mehrere Instanzen

### 8.1 Modulgrenzen (`architekturplan.md` 3.1) [A, aus P]

- **Ort der Suche:** Der Vektorarm wird eine weitere Teilabfrage in `catalog` (wie Volltext und Trigramm in `catalog/search.py`). `api` bettet die Anfrage ein und gibt den Vektor als Parameter weiter; die Fusion kann in `api` bleiben (`adr/0026` §4.4) oder in dieselbe SQL-Abfrage wandern. Beides hält die Importregeln: `catalog` importiert weiter nur `gateway`, `api` darf `catalog` nutzen.
- **Keine neue Bibliothek nötig:** Der Vektor geht als Text (`'[0.1,…]'::halfvec(384)`) an psycopg; das Python-Paket `pgvector` ist bequem, aber nicht nötig. Keine neue Importregel in `.importlinter`.
- **`gateway`, Worker-Kern (B9), Runner-Image:** unberührt. Die Suche ruft nichts nach außen; der Worker sieht keine Vektoren.
- **Modell:** bleibt nur im Image von `api` und `catalog-load` (`adr/0026` F2 a). Mit V4 braucht `api` keine Vektoren des Katalogs im Speicher, nur das Modell.

### 8.2 Mehrere Instanzen `api` (`architekturplan.md` 1.1 Ziel 2, 3.2)

| | V2 (Vektoren je Prozess `api`) | V4 (pgvector, HNSW) |
|---|---|---|
| Speicher je Instanz `api` | N·D·4 Byte zusätzlich: bei 10⁶ und D = 384 rund 1,5 GB, D = 768 rund 2,9 GB; als float16 halb so viel (Rechenzeit damit nicht gemessen) [M, §4.2] | nur das Modell |
| Start einer Instanz | alle Vektoren laden (§4.2: 2,3 s bei D = 384, 4,5 s bei 768, je 10⁶) | nichts |
| Gleichstand der Instanzen | jede Instanz lädt nach einer neuen Fassung des Index nach; bis dahin antworten Instanzen verschieden; bei laufendem Harvest ständig | eine Wahrheit in Postgres, Änderungen sofort für alle sichtbar |
| CPU je Anfrage | im Prozess `api`, der „I/O-lastig, async“ ist (`architekturplan.md` 3.2): muss aus dem Event-Loop in einen Thread; skaliert mit der Zahl der Instanzen | in Postgres; `api` bleibt I/O-gebunden |
| Engpass bei Last | RAM je Instanz × Zahl der Instanzen | CPU und RAM **einer** Datenbank; Ausweg Lese-Replikate (README „Scaling“) |
| Zustandslos im Sinn von Prinzip 16 | ja (abgeleitet), aber teuer | ja |

Die Last der Katalogsuche ist klein gegen Kacheln: eine Anfrage je Tippen nach einer Pause (`adr/0026` §7). Gemessen: 870–1 200 Anfragen je Sekunde auf 4 Kernen bei 10⁶ ohne Filter (§4.6); gefilterte Anfragen auf dem exakten Weg kosten einen Kern für 20–100 ms. Das trägt eine Plattform dieser Größe weit; Lese-Replikate sind der Weg, wenn nicht [A].

### 8.3 Index im Betrieb [P, A]

- **Schreiben:** HNSW nimmt `INSERT`/`UPDATE` ohne Neubau auf (kein Trainingsschritt, README §HNSW). Der Harvester bzw. `catalog-load` schreibt gelistete Einträge einzeln oder in Stapeln; das kostet je Zeile einen Einfügeschritt in den Graphen [A, nicht gemessen].
- **Löschen und `VACUUM`:** „Vacuuming can take a while for HNSW indexes. Speed it up by reindexing first“ (`REINDEX INDEX CONCURRENTLY`). Die Korrekturen 0.8.3/0.8.4 betreffen genau diesen Weg (§3.1).
- **Modellwechsel:** neues Modell heißt alle Embeddings neu (`adr/0026` §4.6). Mit pgvector: neue Spalte bzw. Zeilen mit neuer Modellkennung, Index darauf mit `CREATE INDEX CONCURRENTLY` (README „In production environments, create indexes concurrently“), dann umschalten; partieller Index je Modell nach README-FAQ („`WHERE (model_id = 123)`“). Ein Neubau dauert bei 10⁶ zwei bis drei Minuten (§4.2), das Einbetten selbst Stunden (M5-35 §5.2) — das Einbetten ist der teure Teil, nicht der Index.
- **Container:** `shm_size` im Compose-Dienst `postgres` mindestens so groß wie `maintenance_work_mem` beim Bau (README §Docker); Vorgabe von Docker sind 64 MB [A].

---

## 9. Messung mit echten Embeddings (in M5-23)

Die Sitzung kann kein Embedding-Modell laden (`huggingface.co` gesperrt, `adr/0026` [M]). Was die synthetischen Vektoren nicht zeigen, ist der Recall auf echten e5-Embeddings. Ursprünglich als Messauftrag an Otto vorgeschlagen; nach G6 (§10a) gehört die Messung in **M5-23**, wo Embeddings und Modellwahl am Set entstehen. Kein lokaler Auftrag an Otto. Ablauf:

1. **Korpus:** Titel und Beschreibungen aus Metadaten mit offener Lizenz, möglichst mehrsprachig, mindestens 10⁵ Texte (z. B. ein CKAN-Export eines DACH-Portals, dessen Metadaten unter CC0 oder CC-BY stehen; die Lizenz stuft Otto ein), mindestens aber die Suchtexte des Katalogs. 200 Anfragen aus dem Bewertungs-Set und frei formulierte in Deutsch und Englisch.
2. **Einbetten** mit multilingual-e5-small und -base (Präfixe `passage: ` und `query: `), als `float32`-Arrays `corpus.npy` und `queries.npy`.
3. **Messen** in einer leeren Datenbank mit pgvector ≥ 0.8.4:
   `PGDATABASE=<leere Datenbank> python scripts/m5-41-vector-bench/bench.py --corpus corpus.npy --queries queries.npy`
4. **Im PR von M5-23** stehen nur die JSON-Zeilen bzw. eine Tabelle daraus (keine Texte, keine Vektoren). Maßgeblich: Recall von `hnsw_halfvec` bei `ef_search` 200 ohne Filter, mit `grp1`/`grp10` und `relaxed_order`, und `hnsw_halfvec_filtered_exact`.
5. **Schwelle T (§6 Punkt 3)**, kann auch eine Sitzung übernehmen: nach M5-40, sobald gelistete Einträge in Postgres stehen: für einige typische AOIs (Land, Region, Stadt) zählen, wie viele Einträge den Raumfilter bestehen. Das legt T fest und zeigt, wie oft der HNSW-Weg mit Filter überhaupt vorkommt.

Für M6 zusätzlich je Kandidat des Anbieters: `SELECT * FROM pg_available_extension_versions WHERE name = 'vector';` auf einer Testinstanz (§3.3).

---

## 10. Fragen an Otto

Am Handy beantwortbar: je Frage eine Nummer.

**G1 — `adr/0026` F3 neu?**
1. V4: pgvector ≥ 0.8.4, HNSW auf `halfvec`, gefilterte Anfragen exakt hinter dem Filterindex (§6) **(Empfehlung)**
2. V3: pgvector ohne Index (exakt), HNSW erst, wenn die Menge da ist
3. V2: ohne pgvector, Vektoren im Speicher jeder Instanz `api` (trägt bis ~10⁵)
4. F3 = 2 bleibt

**G2 — Gefilterte Anfragen (Raum, Zeit, Zugang)?**
1. Im Code gewählt: bis T = 5·10⁴ passende Zeilen exakt, darüber HNSW mit iterativem Scan; T in der Konfiguration, nach M5-40 nachgestellt (§9 Punkt 5) **(Empfehlung)**
2. Immer exakt, sobald ein harter Filter gesetzt ist (bei 10⁶ und unscharfem Filter bis ~1 s)
3. Immer HNSW mit iterativem Scan, der Planer entscheidet (gemessen: Recall 0,51–0,89 bei inhaltsnahen Filtern)

**G3 — Typ der Spalte?**
1. `halfvec(D)` als Spalte, HNSW darauf **(Empfehlung)**
2. `vector(D)` als Spalte, HNSW auf `halfvec` als Ausdrucksindex (volle Genauigkeit beim exakten Weg, doppelte Tabelle, TOAST bei 768)
3. `vector(D)` ohne `halfvec`

**G4 — Postgres-Image?**
1. Eigenes Dockerfile auf `postgis/postgis:16-3.7` mit `postgresql-16-pgvector` aus PGDG, Fassung fest; gleiche Hauptversion, Entwicklungsdaten mit `REINDEX` bzw. neuem Volume (§7) **(Empfehlung)**
2. Dasselbe auf `postgis/postgis:17-3.7` (Postgres 17; Dump und Restore der Entwicklungsdaten)
3. pgvector aus dem Quelltext statt aus PGDG

**G5 — CI und Cloud-Sitzung (beides nur mit dir)?**
1. CI baut das Dockerfile aus G4 im Job und startet Postgres als Schritt; die Cloud-Umgebung baut pgvector 0.8.7 im Setup aus dem GitHub-Tag; Erlaubnis für `.github/workflows/ci.yml` und das Setup mit dem Auftrag **(Empfehlung)**
2. CI: Service `postgis/postgis:16-3.7` plus `apt-get install` im Container vor den Tests
3. CI: eigenes Image in GHCR

**G6 — Wie geht es weiter?**
1. Nachtrag `adr/0026` §14 so annehmen; der Wechsel des Images als eigene kleine Aufgabe (Stufe B) vor M5-23; M5-23 baut V4 und nennt den Recall am Bewertungs-Set; Messauftrag §9 parallel **(Empfehlung)**
2. Erst die Messung §9 mit echten e5-Embeddings, dann entscheiden
3. Image-Wechsel in M5-23 mit erledigen

### 10a. Antworten Otto (15.11.2026)

| Frage | Antwort | Folge |
|---|---|---|
| G1 | 1 | V4: pgvector ≥ 0.8.4 mit HNSW auf `halfvec`; F3 neu in `adr/0026` §14 |
| G2 | 1 | gefilterte Anfragen bis T = 5·10⁴ passende Zeilen exakt, darüber HNSW mit iterativem Scan; T in der Konfiguration, nach M5-40 nachgestellt |
| G3 | 1 | Spalte `halfvec(D)`, HNSW darauf |
| G4 | 1 | eigenes Dockerfile auf `postgis/postgis:16-3.7` mit pgvector aus PGDG, Fassung fest |
| G5 | 1 **mit Auflage:** Der CI-Job nutzt Layer-Cache (z. B. `cache-from`/`cache-to` vom Typ `gha`), damit die Backend-CI nicht spürbar langsamer wird; der Folge-PR misst die Bauzeit. Die Erlaubnis für `.github/workflows/ci.yml` und das Setup der Cloud-Umgebung gibt Otto in der Folgeaufgabe. | Folgeaufgabe Image-Wechsel |
| G6 | 1 **mit Änderung:** Die Messung mit echten Embeddings geht in M5-23 (dort entstehen Embeddings und Modellwahl am Set), kein lokaler Auftrag an Otto; das Messskript bleibt im Repo. | Image-Wechsel als eigene Aufgabe (Stufe B) vor M5-23; M5-23 baut V4 und misst nach §9 |

---

## 11. Quellen

Abgerufen am 14.11.2026.

**Gelesen (P):**
- pgvector, Tag `v0.8.7` (Commit `f37c13f`): `README.md` (Abschnitte Indexing, HNSW, Filtering, Iterative Index Scans, Half-Precision, Binary Quantization, Performance, Scaling, FAQ, Troubleshooting, Docker, APT), `CHANGELOG.md`, `Dockerfile`, `LICENSE` — https://github.com/pgvector/pgvector
- setup-pgvector, `README.md` (Step, Service) — https://github.com/pgvector/setup-pgvector
- PostGIS-Images: `16-3.7/Dockerfile` auf `master` und `16-3.4/Dockerfile` vor Commit `27528c8` — https://github.com/postgis/docker-postgis
- Offizielles Postgres-Image: `16/bookworm/Dockerfile` — https://github.com/docker-library/postgres
- pgstac: `docker/pgstac/Dockerfile` (`main`) — https://github.com/stac-utils/pgstac
- Repo: `docker-compose.yml`, `.github/workflows/ci.yml`, `backend/earthx/catalog/migrations/016_dataset_search.sql`, `.importlinter`, `docs/adr/0026-hybrid-suche.md`, `docs/plans/m5/m5-35-skalierbarkeit.md`, `docs/architekturplan.md` 0, 3, 3.1, 5.3, 10.

**Gemessen (M):** §4; Docker Hub API `https://hub.docker.com/v2/repositories/<repo>/tags/<tag>` (`tag_last_pushed` für `postgis/postgis:16-3.4`, `16-3.7`, `17-3.7`, `pgvector/pgvector:0.8.7-pg16-trixie`, `-bookworm`); `apt-cache policy postgresql-16-pgvector`; Erreichbarkeit von `apt.postgresql.org`, `huggingface.co`, Anbieter-Seiten.

**Über das Abrufwerkzeug eines Hilfsagenten (P\*):** pgstac `docker/pgstac/Dockerfile` am Tag `v0.10.1` und Releases; e5-Dimensionen in https://raw.githubusercontent.com/microsoft/unilm/master/e5/README.md; Messungen in den Issues https://github.com/pgvector/pgvector/issues/409 (Parallelbau, SIFT-1M: 415 s mit einem, 107 s mit vier Prozessen), /500 (1M, Bauzeit hängt an `maintenance_work_mem`), /700 (Durchsatz bricht ein, sobald der Index größer als `shared_buffers` ist).

**Suchtreffer (S):** die Anbieter-Seiten in §3.3; PGDG-Paket `postgresql-16-pgvector 0.8.2-1.pgdg12+1` (https://aptpeek.dev/postgresql/bookworm/main/amd64/postgresql-16-pgvector-dbgsym/0.8.2-1.pgdg12+1); e5-Modellkarte (FAQ zu Kosinuswerten) https://huggingface.co/intfloat/multilingual-e5-large.
