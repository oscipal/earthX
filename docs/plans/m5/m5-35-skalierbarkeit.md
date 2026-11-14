# M5-35 — Skalierbarkeit der Bausteine aus M4 und M5: Bericht

**Status (14.11.2026):** Bericht, **Stufe C** (nur lesen und berichten, kein Produktivcode). Fragen F1–F7 von Otto am 14.11.2026 beantwortet (§8a); Folgeaufgaben M5-36 bis M5-42 und M6 (§10).
**Aufgabe:** M5-35, Auftrag von Otto vom 14.11.2026 (steht noch nicht in `docs/plans/m5/m5-discovery-und-suche.md` §6.2).
**Maßstab:** `projektuebersicht.md` Prinzip 16 und Abschnitt „Skalierbarkeit & Cloud-Portabilität“; `architekturplan.md` 1.1 Qualitätsziel 2 („zustandslos, horizontale Skalierung pro Prozesstyp“), 3.2 (Prozesstypen), 6.5 (Fetch-Gateway), 12.3 (Caching-Ebenen).
**Neue Vorgabe Otto (14.11.2026):** Alles, was entschieden wird, muss skalierbar sein. Neues Ziel für den Katalog: **alle Geodaten der Anbieter gelistet**, auch Tabellen und Daten ohne direkten Download.

Belegstufen wie in `adr/0025`: **P** am Quelltext gelesen (Stand `main` 324ef3c), **S** Sekundärquelle mit Link (§9), **A** eigene Ableitung oder Rechnung. Gemessen wurde nichts; es lief kein Code gegen eine Quelle.

---

## 1. Kurzfassung

Die Plattform hält schon heute an den Stellen, an denen sie Zustand braucht, das Muster „Wahrheit in Postgres, Sperre in Postgres“ ein: die Job-Queue mit Obergrenzen je Cluster und je Host, der Pyramidenbau mit „ein Bau je Host“, die Aufräumrunde, das Ratenfenster der Ortssuche und die Mosaik-Auswahlen. Diese Teile halten mit vielen Instanzen.

Nicht cluster-weit gelten dagegen alle **Grenzen zum Schutz der Quellen im Lesepfad**: Die 6 Verbindungen je Host gelten je `Gateway`-Objekt, nicht je Prozess und nicht für alle Instanzen; die 0,25 s Abstand gelten nur im Pyramidenbau; Lesezugriffe über GDAL im `tiler` haben gar keine Grenze je Host. Die Last auf eine Quelle wächst damit linear mit der Zahl der Instanzen und Anfragen. Das ist der wichtigste Befund, weil `architekturplan.md` 12.4 die Quellen als „erwartbar erstes Limit“ nennt.

Für das neue Ziel „alle Geodaten gelistet“ tragen drei Entscheidungen nicht: die Registry als YAML im Image, das jeder Prozess beim Start ganz liest (`adr/0025` §7.1, B13 Stufe 2); die Liste aller Collections in einer Antwort ans Frontend; und der Vektorvergleich ohne pgvector im Prozess `api` (`adr/0026` F3 = 2), der ab etwa 10⁵ Einträgen pro Anfrage zu viel liest.

| # | Befund | Risiko | ab wann | Empfehlung (kurz) |
|---|---|---|---|---|
| B1 | Grenzen je Host im `gateway` gelten je Objekt, nicht cluster-weit; GDAL-Lesen im `tiler` ohne Grenze | **hoch** | ab 2 Instanzen `tiler` oder vielen gleichzeitigen Kacheln | Budget je Host in Postgres (wie Ortssuche) für seltene Zugriffe, festes Teilbudget je Instanz für Kacheln; M6: Egress-Proxy |
| B2 | Pyramidenbau: Sperre in der Datenbank hält; Verlängerung und Aufräumen laufen auf jedem Worker | niedrig | ab 2 Workern | Verlängerung unter `pg_try_advisory_xact_lock` wie `cleanup` |
| B3 | Prozesszustand: Semaphoren und Pools je Prozess (2 Mosaik-Kacheln, Thread-Pool von Starlette) | mittel | ab Last nahe der Grenze | Autoskalierung über gleichzeitige Anfragen; Wartezeit statt Blockade |
| B4 | Vektorsuche ohne pgvector bei 10⁵–10⁶ Einträgen | **hoch** (für das neue Ziel) | ab ~10⁵ Einträgen | pgvector mit HNSW, vor M5-23 neu entscheiden |
| B5 | Registry im Image, ganz geladen in jedem Prozess; volle Collection-Liste ans Frontend | **hoch** (für das neue Ziel) | ab ~10⁴ Einträgen | gelistete Einträge nur in Postgres; Seiten statt Gesamtliste |
| B6 | `earthx_job_limits`: `global_cap` 4, `host_cap` 2 für den ganzen Cluster | mittel | ab 3 Workern | Werte je Pool und Host statt einer Zeile |
| B7 | Volltext- und Trigramm-Arm: Trigramm ohne Index, Fläche ohne räumlichen Index | mittel | ab ~10⁵ Einträgen | Operator `<%` statt Funktion; Spalte `geometry` mit GiST |

Weitere kleinere Punkte: §7.

---

## 2. B1 — `gateway`: Verbindungen und Abstand je Host

### 2.1 Was der Code tut [P]

| Grenze | Wo | Geltungsbereich |
|---|---|---|
| 6 gleichzeitige Anfragen je Host (`max_connections_per_host`) | `gateway/policy.py:124`, Semaphor je Host in `gateway/client.py:115`, `:219`, `:413–416` | **je `Gateway`-Objekt** (`asyncio.Semaphore` im Objekt) |
| Mindestabstand je Host (`min_interval_s`, `host_intervals`) | `gateway/policy.py:130–133`, `_space` in `gateway/client.py:284–299` | je `Gateway`-Objekt; Vorgabe 0, gesetzt nur von `materialize` (FSDI 1 s, `discovery/materialize.py:87`, `:186–191`) |
| 0,25 s Abstand für GDAL-Lesen (`HostPacer`) | `gateway/pacer.py:78–79`, `:97–161`; erzeugt in `readers/access.py:70–72` | je Objekt, genutzt **nur im Pyramidenbau** |
| 6 GDAL-Leser je Host (`ReadSlots`) | `gateway/slots.py:18–54`; eine Instanz je Prozess `api` (`api/main.py:231`) | je Prozess `api`, nur Wolkenfilter und Überflugfilter der Suche (`api/aoi_cloud_filter.py:543`, `api/pass_filter.py:259`) |
| Ratenfenster der Ortssuche (1 Anfrage/s) | `catalog/geocode_cache.py:47–61`, `:81–106` (Tabelle `earthx_rate_slots`) | **cluster-weit**, in Postgres |
| Läufe je Host (`host_cap` 2) und gesamt (`global_cap` 4) | `jobs/queue.py:71–91`, Migration `006_jobs.sql:37` | **cluster-weit**, gezählt unter `pg_advisory_xact_lock` |
| ein Pyramidenbau je Host | `jobs/overviews.py:166–211` | **cluster-weit** (§3) |

Wie viele `Gateway`-Objekte es gibt, entscheidet also, was „je Host“ heißt:

- **`api`:** ein Objekt je Prozess (`api/main.py:124`, `api/dependencies.py:159–161`), dazu eines für die Ortssuche (`api/main.py:156`).
- **`tiler`:** ein Objekt je Prozess für Items (`api/tiler.py:1883`). **Jeder geöffnete Zarr-Store baut aber sein eigenes** (`readers/zarr_reader.py:145–153`, `:264–278`, `:544`): Eine Mosaik-Kachel mit vier Zarr-Szenen auf einem Host darf damit 4 × 6 = 24 Anfragen gleichzeitig stellen, zwei solche Kacheln 48 [A].
- **COG über GDAL im `tiler`:** keine Grenze je Host. `tile_gdal_options` setzt Zeitlimits und Wiederholungen, aber nichts zur Gleichzeitigkeit (`gateway/gdal.py:71–93`). Gebremst wird nur indirekt: höchstens 2 Mosaik-Kacheln × 4 Fäden je Prozess (`access/mosaic_tiles.py:67`, `:74–75`) und für Einzelkacheln der Thread-Pool von Starlette, in dem die synchronen Kachel-Routen von titiler laufen (titiler.core 2.3.0, `factory.py:866`; Vorgabe von AnyIO: 40 Fäden [S]).
- **`worker`:** GDAL im Kind ohne Grenze je Host; begrenzt nur über `host_cap` = 2 Läufe je Host im ganzen Cluster.
- **`materialize` und künftig `harvester`:** ein Objekt je Lauf (`discovery/materialize.py:196`); der Abstand von 1 s zur FSDI gilt je Lauf.

### 2.2 Was das bei N Instanzen heißt [A]

Die Last auf einen Host ist eine Summe über Objekte, nicht ein fester Wert:

- **Abfragen über `httpx`** (Item-Suche, Item-Abruf, Zarr): höchstens 6 je Objekt. Bei N Prozessen `api` und M Prozessen `tiler` also 6·(N + M) gleichzeitig, dazu 6 je offenem Zarr-Store.
- **GDAL-Lesen im `tiler`:** bis zu 40 Einzelkacheln je Prozess gleichzeitig, jede mit eigenen Range-Anfragen; bei M Prozessen bis zu 40·M. Ein Beispiel mit Gewicht: swissALTI3D liegt auf `data.geo.admin.ch` (`backend/catalog/datasets/swissalti3d.yaml:126`), dessen Fair-Use-Regel der Grund für die 0,25 s im Pyramidenbau war (`adr/0032` §8.2, F4). Für die Kacheln derselben Dateien gilt kein Abstand; eine Ansicht mit 124 Szenen (`access/mosaic_tiles.py:71–73`) liest bei zwei `tiler`-Instanzen doppelt so schnell von diesem Host wie bei einer.
- **Abstand je Host:** wirkt nur, wo ein Objekt ihn kennt. Zwei Läufe von `materialize` gegen die FSDI fragen zusammen jede halbe Sekunde, nicht jede Sekunde. Bei mehreren `harvester`-Instanzen (`architekturplan.md` 3.2: „wenige Instanzen“) gilt dasselbe für `robots.txt`-Crawl-Delay, weil auch dieser im Objekt liegt (`gateway/client.py:119–122`, `:290`).
- **Wiederholungen:** `MAX_ATTEMPTS` 3 je Anfrage (`gateway/client.py:53`) und bei GDAL `GDAL_HTTP_MAX_RETRY` 2 (`gateway/gdal.py:61`) sind je Anfrage richtig, aber ohne gemeinsamen Unterbrecher: Antwortet ein Host mit `503`, wiederholen alle Instanzen unabhängig. Den in `architekturplan.md` 6.5 genannten Circuit Breaker, Token-Bucket und die Bündelung gleicher Anfragen gibt es im `gateway` nicht; Bündelung gibt es nur für Items innerhalb eines Prozesses (`ItemFetches`, `api/mosaic_tiles.py:225–270`).

**Folge:** „Rücksicht auf die Quellen“ (`projektuebersicht.md`, Abschnitt Skalierbarkeit) ist heute eine Eigenschaft der einzelnen Instanz. Für große Objektspeicher (AWS Open Data, CDSE) ist das unkritisch; dort liegt das Limit pro Präfix bei Tausenden Anfragen je Sekunde [S]. Für Behördenserver (FSDI, BEV, GeoSphere mit 240 Anfragen je Stunde, `adr/0025` §6.2) wird es mit der zweiten Instanz zum Risiko einer Sperre — und eine Sperre trifft alle Nutzer zugleich.

### 2.3 Optionen

| Option | Wie | Hält mit N Instanzen | Kosten |
|---|---|---|---|
| **G1** Budget je Instanz | Grenze je Host durch die Zahl der Instanzen teilen (Variable, beim Start gesetzt) | ungefähr, wenn N bekannt und fest ist; bei Autoskalierung nicht | klein; passt nicht zu elastischem `tiler` |
| **G2** Postgres-Zeiger je Host | das Muster der Ortssuche (`earthx_rate_slots`, ein `UPDATE … RETURNING` je Anfrage, kein Halten einer Verbindung) für Abstand; für Gleichzeitigkeit eine Leasing-Zeile je Host | ja, exakt | ein Datenbank-Umlauf je Anfrage; heiße Zeile bei vielen Anfragen je Sekunde; nicht im Worker-Kern (B9) |
| **G3** Redis mit GCRA oder Token-Bucket | gemeinsamer Zähler je Host | ja | neuer Dienst (in `architekturplan.md` 12.1 schon als „optional Redis“ vorgesehen); Umlauf unter 1 ms |
| **G4** Egress-Proxy mit Grenzen je Ziel | der Proxy aus KLAERUNGEN B8 Stufe 2 (M6) bekommt Verbindungs- und Ratengrenzen je Upstream; deckt GDAL ab, das an `gateway` vorbeiliest | ja, auch für GDAL | in M6 ohnehin geplant; ein globaler Ratendienst nötig, sobald der Proxy selbst mehrfach läuft |
| **G5** Host-Partitionierung | wie Crawler: ein Host gehört einer Instanz (Hash des Hosts) | ja für Harvester und Worker | passt nicht zum Kachelpfad (jede Instanz muss jeden Host lesen) |

### 2.4 Empfehlung

1. **Sofort, ohne Infrastruktur:** Die Grenzen je Host bekommen einen Ort in der Registry je Quelle (`host_intervals`, `max_connections_per_host`), statt fest im Code zu stehen. Zarr-Stores teilen sich das `Gateway`-Objekt des Prozesses, statt je Store ein eigenes zu bauen. Der `tiler` bekommt für GDAL-Lesen dieselben `ReadSlots` wie `api`. Damit gilt „6 je Host“ wenigstens je Prozess.
2. **Für seltene Zugriffe (Harvester, `materialize`, Verify, Health-Checks, Pyramidenbau): G2.** Das Muster ist im Repo erprobt und braucht keinen neuen Dienst. Die Hülle (`jobs`, `discovery`) reserviert, der Kern bleibt ohne Datenbank (B9).
3. **Für den Kachelpfad: G1 jetzt, G4 in M6.** Kacheln sind zu häufig für einen Datenbank-Umlauf je Range-Anfrage, und GDAL liest an `gateway` vorbei. Bis M6 eine feste Teilmenge je Instanz (Budget je Host geteilt durch die höchste Instanzzahl, die die Plattform zulässt) und ein CDN vor dem `tiler`, damit wiederholte Kacheln die Quelle nicht erreichen. In M6 der Egress-Proxy mit Grenzen je Ziel.
4. **Unterbrecher je Host cluster-weit** über dieselbe Zeile wie G2: Nach `429` oder Serien von `5xx` schiebt eine Instanz den Zeiger des Hosts vor (wie `push_back` der Ortssuche, `catalog/geocode_cache.py:102–106`); alle anderen warten mit.

G3 (Redis) erst, wenn G2 messbar zum Engpass wird (Sperrwartezeit auf der Zeile des Hosts). Begründung: Prinzip „skalierbar entwerfen, aber nicht vorzeitig skalieren“ (`projektuebersicht.md` Prinzip 16); ein Dienst weniger.

---

## 3. B2 — Pyramiden (M5-30b Teil 8)

### 3.1 „Höchstens ein Bau je Host“ [P]

Hält mit mehreren Workern. `claim` nimmt `pg_advisory_xact_lock(OVERVIEW_LOCK_KEY)` in einer eigenen Anweisung, beendet abgelaufene Bauten (`lease_lost`), liest die belegten Hosts aus allen Zeilen mit `status = 'building'` und legt erst dann eine Zeile an (`jobs/overviews.py:166–211`, Regeln im Kopf `:10–21`). Die Hosts stehen in der Zeile (`hosts`), nicht im Prozess; auch zwei Worker mit unterschiedlichem Stand der Registry (rollendes Deployment) sehen dieselbe Belegung. Das ist dasselbe Muster wie die Queue (`jobs/queue.py:66–91`), dort mit dem Befund aus M2, dass eine Zählung in der wartenden Anweisung nicht reicht.

Die Abstandsregel von 0,25 s im Bau liegt im Prozess (`HostPacer`), gilt aber trotzdem für den ganzen Cluster, weil höchstens ein Bau je Host läuft [A]. Sie zählt nur die Anfragen des Baus, nicht die Kacheln derselben Dateien aus dem `tiler` (B1).

### 3.2 Übernahme von Bauwünschen [P]

Hält. Ein Bau gehört einem Versuch mit Frist (`lease_until`); der Faden erneuert sie zwischen Seiten und Kacheln (`jobs/overview_builder.py:270–290`). Läuft sie ab, setzt das nächste `claim` irgendeines Workers die Zeile auf `failed`/`lease_lost` und nimmt sie sofort wieder auf (`jobs/overviews.py:89–112`). Jede spätere Änderung prüft den Versuch (`_own`, `:214–224`); ein spät erwachter Worker überschreibt nichts. Wünsche liegen in `earthx_overview_request`; `request_missing` ist mit `ON CONFLICT` wiederholbar (`:125–141`).

### 3.3 Was nicht abgestimmt ist [P]

- **Verlängerung** (`overview_upkeep.extend`, `jobs/overview_upkeep.py:81–118`): läuft stündlich im Faden `overview` **jedes** Workers (`jobs/overview_builder.py:162–186`), ohne Sperre. `to_extend` wird vor jeder Pyramide neu gefragt, doch zwei Worker, die zur selben Zeit beginnen, kopieren dieselben Tausende Objekte doppelt; `mark_extended` ist bedingt, das Ergebnis also richtig, nur die Arbeit N-fach.
- **Ablauf und Waisen** (`overview_upkeep.sweep`, `:62–78`): im Wartungsfaden jedes Workers stündlich (`jobs/worker.py:256–270`). Der Ablauf ist über die bedingte Aktualisierung sicher; das Auflisten aller Schlüssel unter `overviews/` läuft aber N-mal je Stunde. Die Aufräumrunde der Jobs daneben nimmt dagegen `pg_try_advisory_xact_lock` und läuft nur einmal (`jobs/cleanup.py:81–90`).

**Risiko:** niedrig, aber linear in N: Objektspeicher-Anfragen (Kopien, Listen) kosten bei Cloud-Anbietern je Anfrage.
**Empfehlung:** `extend` und `sweep` unter je einen eigenen `pg_try_advisory_xact_lock`-Schlüssel wie `cleanup`, oder als Zeile „nächster Lauf“ mit `SKIP LOCKED`; wer die Sperre nicht bekommt, überspringt die Runde. Kein neuer Dienst.

---

## 4. B3 — Zustand im Prozess

### 4.1 Was nichts an eine Instanz bindet [P]

Kein Token, keine ID und kein Cursor, den ein Client bekommt, hängt am Speicher einer Instanz. Seiten-Token der föderierten und gemischten Suche und Cursor des Wolkenfilters sind in sich geschlossenes JSON mit ungeschlüsseltem SHA-256 (`adapters/federated_search.py:426–456`, `api/mixed_search.py:128–170`, `api/aoi_cloud_filter.py:305–343`); die Mosaik-Auswahl-ID ist der Hash ihres Inhalts mit Zeile in Postgres (`catalog/mosaic_selection.py:61–63`); Ergebnis-, Job-, Rezept- und Permalink-IDs liegen in Postgres oder im Objektspeicher (`objectstore/results.py:85`, `jobs/submit.py:151`, `jobs/permalinks.py:52–53`). Der einzige Schlüssel je Prozess ist der HMAC-Schlüssel für den Abfrage-Hash im Log (`gateway/client.py:87`); er prüft nichts, macht nur Logzeilen verschiedener Instanzen unvergleichbar. Fortschritt per SSE liest jede Instanz selbst aus der Zeile; ein Client kann zu jeder Instanz neu verbinden (`api/job_events.py:1–19`).

Die Caches im Prozess sind begrenzt und halten unveränderliche Inhalte oder Inhalte mit kurzer Frist: Auswahlen 120 s, 256 Einträge (`api/mosaic_selection.py:29–33`, `:113–167`), Kopfdaten und signierte URLs von Ergebnissen 60 s bzw. 10 min, 128 Einträge (`api/result_tiles.py:75–81`), DNS 5 s (`gateway/resolver.py:31`, `:35`). Das ist das Muster aus `architekturplan.md` 12.3 und für N Instanzen in Ordnung. Folge: Eine gelöschte Auswahl oder ein gelöschtes Ergebnis kann auf einer anderen Instanz noch bis zu 120 s bzw. 60 s erscheinen; bei Ergebnissen endet das als Lesefehler von GDAL statt `404`/`410` [A].

### 4.2 Grenzen je Prozess [P]

| Grenze | Wo | richtige Einheit? |
|---|---|---|
| 2 Mosaik-Kacheln gleichzeitig | `access/mosaic_tiles.py:70–75`, `:234` | ja: CPU je Prozess |
| 4 Fäden je Mosaik-Kachel | `access/mosaic_tiles.py:64–67` | ja: CPU; die Begründung „bleibt unter 6 Verbindungen je Host“ gilt nur für eine Kachel in einem Prozess |
| 1 große Datei-Ausgabe (≥ 100 MB) je Prozess, sonst `503` | `api/tiler.py:185–192`, `:1695–1701` | ja: Speicher je Prozess |
| 4 ZIP-Ausgaben je Prozess | `api/processing_route.py:163`, `:232–245` | ja |
| 500 SSE-Clients je Prozess | `api/job_events.py:46` | ja |
| 4 Item-Abrufe je Prozess, gleiche Items zusammengelegt | `api/mosaic_tiles.py:125`, `:225–270` | Grenze ja; die Bündelung wirkt nur innerhalb einer Instanz |
| GDAL-Caches (`/vsicurl/` 256 MiB, `VSI_CACHE` 64 MiB je Datei) | `gateway/gdal.py:30`, `:36` | je Prozess üblich [S: titiler Performance Tuning]; die Trefferquote sinkt mit N, wenn die Kacheln einer Ansicht auf N Instanzen verteilt werden |

Zwei Punkte verdienen Arbeit:

- **Warten im Thread-Pool:** Eine Mosaik-Kachel wartet auf ihren Platz (`with _TILE_SLOTS`) innerhalb der synchronen Route, also in einem der 40 Fäden des Standard-Pools von AnyIO (titiler.core 2.3.0 `factory.py:866`; AnyIO 4.15.1, `current_default_thread_limiter().total_tokens` = 40, in der Sitzung abgefragt). Unter Last können wartende Mosaik-Kacheln alle 40 Fäden belegen, dann stehen auch Einzelkacheln, Ausschnitte und Statistik desselben Prozesses. Die Instanz wirkt überlastet, obwohl sie nur zwei Kacheln rechnet [A]. Abhilfe: den Platz vor dem Thread-Pool nehmen (asynchroner Semaphor in der Route) oder einen eigenen `CapacityLimiter` für Mosaik-Routen, wie ihn `api/federating_client.py:662–674` schon für Lesezugriffe hat.
- **Lastverteilung:** Ohne Klebrigkeit landen die sechs Kacheln einer Ansicht auf verschiedenen Instanzen; der gemessene Gewinn des Block-Caches (`gateway/gdal.py:77–82`: 284 MB statt 1,72 GB von der Quelle für eine Ansicht) und die Bündelung der Item-Abrufe gehen dann teilweise verloren. Ein CDN vor dem `tiler` fängt Wiederholungen ab, nicht den ersten Abruf. Konsistentes Hashing auf Auswahl-ID bzw. Datensatz und Item im Lastverteiler (nginx `hash … consistent` [S]) hält den Gewinn und ist zustandslos im Sinn des Prinzips: Fällt eine Instanz aus, rechnet eine andere, nur kälter.

**Risiko:** mittel. **Empfehlung:** (1) Mosaik-Platz vor dem Thread-Pool; (2) Autoskalierung des `tiler` nach gleichzeitigen Anfragen oder Wartezeit, nicht nach CPU allein, weil wartende Kacheln keine CPU brauchen [A]; (3) konsistentes Hashing erst, wenn die Messung in M6 eine niedrige Trefferquote zeigt (Primärquelle zur Trefferquote bei N Instanzen fand die Recherche nicht).

---

## 5. B4 — Vektorsuche ohne pgvector bei sehr vielen Einträgen

### 5.1 Was entschieden ist [P]

`adr/0026` F3 = 2: Vektoren als Spalte (`real[]`) in Postgres, harte Filter in SQL, exakter Kosinus-Vergleich in `api` mit numpy; „bei bis zu einigen Tausend Zeilen … schnell genug“; „je Anfrage liest `api` die Vektoren der gefilterten Datensätze“ (`adr/0026` §4.3, §9). Gebaut ist der Vektorarm noch nicht (M5-23 offen). Die Entscheidung stand unter der Annahme „tausende Collections“ (`architekturplan.md` 5.2, `adr/0026` §2).

### 5.2 Was das neue Ziel ändert [A]

„Alle Geodaten der Anbieter gelistet“ heißt eine andere Größenordnung. Allein die drei CKAN-Portale der DACH-Länder, die INSPIRE-Dienste und CMR/STAC-Kataloge der Raumfahrtagenturen führen zusammen eher 10⁵ als 10³ Datensätze; eine belastbare Zahl gibt es im Repo nicht (Frage F3). Rechnung je Anfrage (D = 384 bei e5-small, 768 bei e5-base; Speicher N·D·4 Byte; ein Kern liest grob 10–15 GB/s):

| Einträge | Vektoren float32 (D = 384 / 768) | je Anfrage aus Postgres lesen (heutiger Plan) | Vergleich im Speicher, ein Kern |
|---|---|---|---|
| 10⁴ | 15 / 31 MB | 15–31 MB | ~1–3 ms |
| 10⁵ | 154 / 307 MB | 154–307 MB: **zu viel** | ~20–30 ms |
| 10⁶ | 1,5 / 3,1 GB | nicht machbar | ~200–300 ms, je Prozess `api` 1,5–3 GB RAM |
| 10⁷ | 15 / 31 GB | nicht machbar | Sekunden |

Rechnung und Größenordnung wie in der Recherche (§9, Thema 3); gemessen ist nichts. Dazu kommt: Der Vergleich ist CPU-Arbeit im Prozess `api`, der laut `architekturplan.md` 3.2 „I/O-lastig, async“ ist, und muss dort aus dem Event-Loop heraus. Und das Einbetten aller Texte in `catalog-load` (§4.6) wächst linear: bei 10⁶ Einträgen auf CPU Stunden für einen vollen Neubau nach Modellwechsel [A, nicht gemessen].

### 5.3 Optionen

| Option | Hält bis | Kosten |
|---|---|---|
| **V1** wie entschieden (Spalte, Lesen je Anfrage) | ~10⁴ | keine; danach Umbau |
| **V2** Vektoren je Prozess `api` im Speicher, neu geladen bei neuer Index-Fassung | ~10⁵ | RAM je Instanz, Ladezeit beim Start; jede Instanz hält eine Kopie (widerspricht nicht der Zustandslosigkeit, weil abgeleitet) |
| **V3** pgvector, exakt ohne Index | ~10⁵ | Image der Datenbank ändert sich (`adr/0026` F3 Option 1); kein Transfer, aber O(N) in Postgres |
| **V4** pgvector mit HNSW (`halfvec`), ab 0.8.0 mit iterativem Scan für Filter | 10⁶–10⁷ | Index im RAM der Datenbank (Größenordnung einige GB je 10⁶ bei 768 Dim, aus AWS-Angaben hochgerechnet [S]); Recall statt exakt; Filter-Fallen ohne iterativen Scan [S: pgvector README] |
| **V5** eigener Vektordienst | > 10⁷ | `architekturplan.md` 0 Punkt 9 schließt ihn aus, „solange die Mengen ihn nicht erzwingen“ |

pgvector gibt es bei AWS RDS und Aurora (0.8.0), Google Cloud SQL (0.8.1), Azure Flexible Server und Scaleway; die Fassungen weichen ab, der iterative Scan kommt erst mit 0.8.0 [S, §9]. Für die Wahl des Anbieters in M6 ist pgvector damit kein Ausschluss, aber die Mindestfassung 0.8.0 gehört in die Anforderungen.

### 5.4 Empfehlung

**V4 als Ziel, F3 vor M5-23 neu entscheiden.** Die Spalte lässt sich ohne neues Einbetten in `vector`/`halfvec` umwandeln (`adr/0026` §4.3), der Umweg über V1 kostet also wenig — aber M5-23 sollte nicht erst den Vergleich in `api` bauen, wenn absehbar ist, dass er bei der Zielmenge nicht trägt. Bis zur Entscheidung: V2 ist die kleinste Änderung, wenn M5-23 vorher starten soll. Gleich bleibt: Modell und Einbetten der Anfrage im Prozess `api` (skaliert mit der Zahl der `api`-Instanzen), RRF in `api`.

---

## 6. B5 bis B7 — Katalog bei sehr vielen Einträgen

### 6.1 B5: Registry im Image und Gesamtliste [P]

- **Registry:** Jeder Prozess liest beim ersten Zugriff alle YAML-Dateien unter `backend/catalog/datasets/` und hält sie für seine Lebenszeit (`catalog/datasets.py:104–131`, `@cache`). Gelistete Einträge sollen nach `adr/0025` §7.1 ebenfalls im Image unter `backend/catalog/listed/` liegen und „immer“ geladen werden. Bei 10⁵ Einträgen hieße das: 10⁵ Dateien im Image und in Git, Startzeit und Speicher in **jedem** Prozess (`api`, `tiler`, `worker`, `harvester`), ein neues Image für jede neue Zeile im Katalog.
- **Allowlist:** `policy_from_registry` sammelt die Hosts aller Einträge (`api/dependencies.py:143–156`); `Policy.allows_host` prüft sie linear (`gateway/policy.py:158–160`), bei jeder Anfrage und jedem Hop. Gelistete Einträge brauchen keinen Host in der Allowlist (sie haben keinen Lese- und Kachelweg, `adr/0025` §6.1a); das muss beim Bau so bleiben.
- **Gesamtliste:** `GET /stac/collections` ohne Parameter liefert bis zu 10 000 Collections in einer Antwort (`api/federating_client.py:705–706`, `api/collection_search.py:45`); das Frontend holt sie beim Start ganz (`frontend/src/api.ts:126`) für Control Panel und Data catalogue. Bei mehr als 10 000 Einträgen fehlen die übrigen ohne Hinweis, darunter wird die Antwort Megabytes groß.
- **Rollendes Deployment:** Weil die Registry im Image liegt, sehen Instanzen mit altem und neuem Image für Minuten verschiedene Datensätze und Allowlists. Bei wenigen, von Hand gepflegten Einträgen harmlos; bei täglichen Sammel-PRs (`adr/0031`) Alltag.

**Risiko:** hoch für das neue Ziel, heute (6 Einträge) keins.
**Optionen:** (R1) alles bleibt YAML im Image; (R2) volle Einträge bleiben YAML im Image (sie bringen Code-Eigenheiten mit, B13), **gelistete Einträge nur in Postgres** (pgstac und Suchindex), geschrieben vom Harvester nach Freigabe, Review weiter über Git als Kandidatendatei oder Regel; (R3) auch volle Einträge in Postgres, YAML nur als Quelle von `catalog-load`.
**Empfehlung: R2.** Es hält B13 Stufe 3 („nie zwei gepflegte Wahrheiten“), wenn die Kandidatendatei die Wahrheit bleibt und Postgres daraus befüllt wird. Prozesse laden nur volle Einträge. Das Frontend fragt Seiten und Suche statt der Gesamtliste; das Control Panel braucht ohnehin nur volle Einträge (Anzeige), der Data catalogue blättert. Eine Änderung an `adr/0025` §7.1 und `adr/0031` (Sammel-PR) — Frage F4.

### 6.2 B6: Grenzen der Job-Queue [P]

`earthx_job_limits` hat genau eine Zeile: `global_cap` 4, `host_cap` 2 (`catalog/migrations/006_jobs.sql:33–37`), cluster-weit und richtig gezählt (`jobs/queue.py:66–91`). Folge: Mehr als zwei Worker mit je zwei Slots bringen nichts, und alle Sentinel-2-Läufe teilen sich zwei Plätze, weil sie vom selben Host lesen. Das ist Rücksicht auf die Quelle, aber eine **feste** Obergrenze für die Plattform.
**Empfehlung:** `host_cap` je Host aus der Registry (große Objektspeicher hoch, Behördenserver niedrig), `global_cap` je Pool (`adr/0013`), als Konfiguration statt Migration. Klein, kein neuer Dienst.

### 6.3 B7: Lexikalische Suche in SQL [P]

Die Suche läuft vollständig in Postgres (gut für N Instanzen), aber nicht über die Indizes:

- **Volltext:** `filtered f CROSS JOIN units u` mit `count(*) FILTER (WHERE f.document @@ u.query)` und `ts_rank_cd` für jede Zeile; ein `@@` in der `WHERE`-Klausel gibt es nicht (`catalog/search.py:211–240`). Der GIN-Index `earthx_dataset_search_document_idx` (`catalog/migrations/016_dataset_search.sql:40`) kann so nicht greifen [A, Plan nicht gemessen].
- **Trigramm:** `word_similarity(…) >= threshold` als Funktion (`catalog/search.py:248–254`); nur die Operatoren `<%`/`%>` nutzen den Trigramm-Index (`:41`) [S: pg_trgm-Doku].
- **Fläche:** `ST_MakeEnvelope(s.west, s.south, s.east, s.north)` je Zeile, ohne räumlichen Index (`catalog/search.py:94–112`).

Bei Hunderten Einträgen egal, bei 10⁵–10⁶ ein voller Tabellenscan mit Rangberechnung je Anfrage und Arm [A].
**Empfehlung:** vor großen Mengen ein `@@`-Vorfilter (ODER über die Einheiten) vor der Rangberechnung; `<%` mit `pg_trgm.word_similarity_threshold`; eine Spalte `geometry` mit GiST statt der vier Zahlen. Am Bewertungs-Set prüfen, dass sich keine Rangfolge ändert. Gehört zu M5-23 oder einer eigenen Aufgabe.

---

## 7. Weitere Stellen

| # | Befund | Beleg [P] | Risiko | Empfehlung |
|---|---|---|---|---|
| W1 | **Verbindungen zu Postgres:** je `api` grob 20 (pgstac bis 10, Suchcache 5, Jobs 4, ein `LISTEN`), je `tiler` 5, je Worker Slots + 3 (+1 Pyramide); `max_connections` 100 | `stac_fastapi.pgstac.config` (`db_max_conn_size` 10), `api/dependencies.py:37–38`, `api/main.py:96–98`, `api/job_events.py:1–7`, `jobs/worker.py:3–6` | mittel: ab etwa 4 `api` + 4 `tiler` + 4 Worker voll | Pooler (PgBouncer) in M6; die Sperren im Code sind alle transaktionsgebunden (`pg_advisory_xact_lock`, `pg_try_advisory_xact_lock`) und vertragen Transaktions-Pooling, `LISTEN` nicht (`api/job_events.py:18–19`, `jobs/worker.py:224–239`): `LISTEN` direkt oder über Session-Pooling |
| W2 | **Arbeitsordner des Workers:** beim Start löscht jeder Worker alle Lauf- und Pyramiden-Ordner unter `WORKER_WORKDIR` | `jobs/worker.py:204–209` | niedrig, solange der Ordner lokal ist; hoch, falls ihn je mehrere Worker teilen | festhalten: `WORKER_WORKDIR` nie geteilt (Doku in `cloud-umgebung.md`/M6) |
| W3 | **Platzmangel ohne Wiederholung:** `disk_space` wird nicht wiederholt, auch wenn ein anderer Worker Platz hätte | `jobs/worker.py:312–320` | niedrig | Bedarf beim `claim` gegen den freien Platz prüfen (Worker meldet ihn), statt danach zu scheitern |
| W4 | **Wolkenfilter läuft nach der Antwort weiter**, bis 10 s beim Herunterfahren | `api/aoi_cloud_filter.py:790`, `api/main.py:100` | niedrig: nur Cache-Fehlschläge | so lassen |
| W5 | **Stündliche Runden je Worker:** `request_missing` und `sweep` N-mal | `jobs/worker.py:256–270` | niedrig | wie B2 unter Sperre |
| W6 | **Kein Unterbrecher und keine Bündelung über Instanzen** (`architekturplan.md` 6.5 verspricht beides) | `gateway/client.py` (fehlt) | mittel | mit B1 (G2) |
| W7 | **Der `harvester` ist noch leer** | `discovery/main.py:19–25` | — | M5-24 von Anfang an mit Sperre je Quelle in Postgres (Lauf-Zeile mit Frist wie `earthx_overview`), damit „wenige Instanzen“ nicht dieselbe Quelle doppelt ernten |

---

## 8. Fragen an Otto (beantwortet, §8a)

**F1 — Rücksicht auf die Quellen über alle Instanzen (B1)?**
1. Jetzt: Grenzen je Host in die Registry, Zarr teilt das Gateway, `ReadSlots` auch im `tiler`; Harvester, `materialize` und Pyramide über einen Zeiger je Host in Postgres; Kacheln mit festem Teilbudget je Instanz bis zum Egress-Proxy in M6 **(Empfehlung)**
2. Redis als gemeinsamer Zähler für alles, schon vor M6
3. Erst in M6 mit dem Egress-Proxy, bis dahin nichts

**F2 — Verlängerung und Aufräumen der Pyramiden unter Sperre (B2, W5)?**
1. Ja, als kleine Aufgabe der Stufe A nach M5-30b **(Empfehlung)**
2. Nein, doppelte Arbeit hinnehmen

**F3 — Zielgröße des Katalogs für „alle Geodaten gelistet“?**
1. Planen für 10⁶ gelistete Einträge, 10³ volle **(Empfehlung, Annahme dieses Berichts)**
2. 10⁵ gelistete Einträge
3. Erst messen: der Harvester zählt in M5-19/M5-21 die Funde je Quelle, dann entscheiden

**F4 — Wo liegen gelistete Einträge (B5)?**
1. Nur in Postgres (pgstac und Suchindex), aus Kandidatendateien bzw. Regeln befüllt; volle Einträge bleiben YAML im Image; Frontend blättert statt Gesamtliste **(Empfehlung)**; ändert `adr/0025` §7.1 und `adr/0031`
2. Alles bleibt YAML im Image wie entschieden
3. Auch volle Einträge nach Postgres

**F5 — pgvector (B4, `adr/0026` F3)?**
1. F3 vor M5-23 neu öffnen: pgvector ≥ 0.8.0 mit HNSW (`halfvec`), eigenes Postgres-Image für Compose und CI, Erlaubnis für `.github/workflows/ci.yml` mit dem Auftrag **(Empfehlung)**
2. F3 = 2 bleibt; M5-23 hält die Vektoren je `api`-Prozess im Speicher (trägt bis ~10⁵)
3. F3 = 2 bleibt unverändert, Umbau erst bei Bedarf

**F6 — Grenzen der Job-Queue (B6)?**
1. `host_cap` je Host aus der Registry, `global_cap` je Pool aus der Konfiguration, mit M6 **(Empfehlung)**
2. So lassen, Werte bei Bedarf per SQL ändern

**F7 — Wie geht es weiter?**
1. Folgeaufgaben aus §10 in den M5-Plan (§6.2) bzw. das Backlog für M6 übernehmen, Reihenfolge durch den Planungs-Chat **(Empfehlung)**
2. Erst ein ADR „Skalierung und Rücksicht über Instanzen“ (Stufe C), dann Aufgaben

### 8a. Antworten Otto (14.11.2026)

| Frage | Antwort | Folge |
|---|---|---|
| F1 | 1 | M5-36, M5-37; Egress-Proxy in M6 |
| F2 | 1 | M5-38 |
| F3 | 1: mit 10⁶ gelisteten Einträgen planen | Maßstab für M5-40, M5-41, M5-42 |
| F4 | 1 **mit Bedingung:** Die Freigabe durch Otto bleibt (`adr/0025` P1, Lizenz immer durch Otto). Für Einträge in Postgres geschieht sie über freigegebene Lizenzregeln und Stichproben statt über einen PR je Eintrag; wie genau, klärt eine eigene Vorlage vor dem Umbau. | M5-39 (Vorlage), dann M5-40 |
| F5 | 1, als **Neuentscheidung mit Recherche aus Primärquellen vor M5-23** (die Quellen in §9 sind zum Teil nur Suchtreffer) | M5-41 |
| F6 | 1 | M6 |
| F7 | 1: Folgeaufgaben in den M5-Plan | §10 |

---

## 9. Stand der Technik

Recherche in der Sitzung. Nur GitHub ließ sich öffnen; Stripe, Envoy, PostgreSQL, Development Seed, AWS und andere waren aus der Sitzung nicht erreichbar. Was nicht auf GitHub liegt, stammt aus Texten der Suchtreffer und ist mit **[S, Suche]** markiert: Die Aussage stimmt mit dem Treffertext überein, die Seite selbst ist nicht gelesen.

**Thema 1 — Ratengrenzen über viele Instanzen (B1).**
- GCRA als gemeinsamer Zähler: `redis-cell`, ein Befehl je Prüfung, rund 0,1 ms aus Sicht des Clients; Wartung nur noch „best effort“ — https://github.com/brandur/redis-cell
- Envoy unterscheidet lokale Grenzen (Token-Bucket im Proxy, ohne Abstimmung) und globale (eigener Dienst, meist mit Redis), empfiehlt beide zusammen — https://gateway.envoyproxy.io/v1.7/concepts/rate-limiting/ [S, Suche]
- Stripe: Token-Bucket, Grenzen für Rate und für Gleichzeitigkeit, dazu Lastabwurf — https://stripe.com/blog/rate-limiters [S, Suche]
- Crawler halten Rücksicht über Warteschlangen je Host; ein Fetcher besitzt einen Host (StormCrawler, Crawl-Delay höchstens 30 s) — https://stormcrawler.apache.org/docs/, https://stormcrawler.apache.org/faq [S, Suche]; Nutch begrenzt Seiten je Host (`generate.max.per.host`) — https://cwiki.apache.org/confluence/spaces/NUTCH/pages/115512217/OptimizingCrawls [S, Suche]
- Für einen Token-Bucket in Postgres fand die Recherche weder Quelle noch Messung. Im Repo läuft das Muster für die Ortssuche mit 1 Anfrage je Sekunde (`catalog/geocode_cache.py`); für viele Anfragen je Sekunde je Host ist eine heiße Zeile zu erwarten [A].
- Große Objektspeicher: S3 verträgt je Präfix Tausende Anfragen je Sekunde (AWS-Dokumentation „Best practices design patterns: optimizing Amazon S3 performance“) [S, aus dem Gedächtnis, nicht in der Sitzung geprüft].

**Thema 2 — Sperren in Postgres (B2).**
- Sitzungsgebundene Advisory-Locks gehen mit PgBouncer im Transaktionsmodus nicht, transaktionsgebundene schon — https://pgbouncer.org/features [S, Suche]
- Warteschlangen über `SKIP LOCKED` (seit PostgreSQL 9.5) mit Grenzen beim Durchsatz durch tote Zeilen und Autovacuum — https://www.2ndquadrant.com/en/?p=9279 [S, Suche]
- Eindeutigkeit über einen partiellen Unique-Index statt Advisory-Lock (River) — https://brandur.org/river [S, Suche]; `singleton`/`exclusive`-Regeln in pg-boss — https://github.com/timgit/pg-boss; `job_key` in Graphile Worker — https://worker.graphile.org/docs/job-key [S, Suche]
- Der Code folgt dem: Frist mit Herzschlag, Versuch je Zeile, Sperre nur in der Transaktion.

**Thema 3 — Vektorsuche (B4).**
- pgvector: HNSW-Vorgaben (`m` 16, `ef_construction` 64, `ef_search` 40); Filter greifen nach dem Index-Scan (bei 10 % passenden Zeilen bleiben im Mittel rund 4 von 40 Treffern); iterativer Scan seit 0.8.0 (`hnsw.iterative_scan`, Vorgabe aus); `halfvec` seit 0.7.0; aktuelle Fassung 0.8.7 — https://github.com/pgvector/pgvector, https://github.com/pgvector/pgvector/blob/master/CHANGELOG.md
- Bau von HNSW für 10⁶ Vektoren (1536 Dim): einfädig 1 h 27 min, parallel 9,5 min (pgvector 0.6.0) — https://aws.amazon.com/blogs/database/load-vector-embeddings-up-to-67x-faster-with-pgvector-and-amazon-aurora [S, Suche]
- Indexgröße rund 367 GB für 10⁸ Vektoren mit 768 Dim, linear also rund 3,7 GB je 10⁶ [A, hochgerechnet] — https://aws.amazon.com/blogs/database/scale-pgvector-with-binary-quantization-on-amazon-aurora-postgresql/ [S, Suche]
- Mit 0.8.0 bei selektiven Filtern volle Trefferzahl statt teils 1–10 % — https://aws.amazon.com/blogs/database/supercharging-vector-search-performance-and-relevance-with-pgvector-0-8-0-on-amazon-aurora-postgresql [S, Suche]
- Verfügbarkeit: AWS RDS 0.8.0 (https://aws.amazon.com/about-aws/whats-new/2024/11/amazon-rds-for-postgresql-pgvector-080), Aurora 0.8.0 (https://aws.amazon.com/about-aws/whats-new/2025/04/pgvector-0-8-0-aurora-postgresql), Google Cloud SQL 0.8.1 (https://docs.cloud.google.com/sql/docs/postgres/release-notes), Azure Flexible Server (https://learn.microsoft.com/azure/postgresql/flexible-server/release-notes), Scaleway 0.8.0/0.8.1 (https://www.scaleway.com/en/docs/managed-databases-for-postgresql-and-mysql/reference-content/pg-version-updates.md), alle [S, Suche]; Sammlung der Anbieter im Issue https://github.com/pgvector/pgvector/issues/54
- Alternativen nur selbst betrieben: pgvectorscale (PostgreSQL-Lizenz, StreamingDiskANN) — https://github.com/timescale/pgvectorscale; VectorChord (AGPLv3 oder Elastic License v2) — https://github.com/tensorchord/VectorChord
- Die Tabelle in §5.2 ist eigene Rechnung (Speicherbandbreite), nicht gemessen.

**Thema 4 — Tiler horizontal (B3).**
- Development Seed empfiehlt GDAL-Caches je Prozess (`GDAL_CACHEMAX` 200 MB, `CPL_VSIL_CURL_CACHE_SIZE` 200 MB, `VSI_CACHE_SIZE` je Datei) — https://github.com/developmentseed/titiler/blob/main/docs/src/advanced/performance_tuning.md
- Konsistentes Hashing im Lastverteiler (`hash $key consistent`, ketama): beim Hinzufügen einer Instanz wandern nur wenige Schlüssel — https://nginx.com/resources/wiki/modules/ketama_chash/ [S, Suche]
- Eine Primärquelle zur Trefferquote von Caches je Prozess bei N Instanzen fand die Recherche nicht.

**Thema 5 — Bündeln gleicher Anfragen (W6).**
- CDNs bündeln gleichzeitige Fehlschläge je Rechenzentrum (Fastly — https://www.fastly.com/documentation/guides/concepts/cache/request-collapsing/; Cloudflare — https://developers.cloudflare.com/cache/concepts/default-cache-behavior; Varnish — https://www.varnish.org/docs/users-guide/vcl-grace/), über Rechenzentren nur mit Shield bzw. Tiered Cache, alle [S, Suche]. Bündelung im Prozess wie `ItemFetches` entspricht Go `singleflight` (https://pkg.go.dev/golang.org/x/sync/singleflight [S, Suche]).

Weitere: AnyIO-Standard von 40 Fäden in der Sitzung abgefragt (AnyIO 4.15.1); pg_trgm-Operatoren und Index: https://www.postgresql.org/docs/16/pgtrgm.html [S, aus dem Gedächtnis].

---

## 10. Folgeaufgaben (von Otto am 14.11.2026 in den M5-Plan übernommen)

| Aufgabe | Inhalt | Stufe | Befund | Reihenfolge |
|---|---|---|---|---|
| **M5-36** | Grenzen je Host in der Registry; Zarr teilt das Gateway; `ReadSlots` im `tiler`; Teilbudget je Instanz für Kacheln | B | B1 | nach M5-30b Teil 9 |
| — | Mosaik-Platz vor dem Thread-Pool (§4.2) | — | B3 | kommt schon mit M5-30b Teil 9 |
| **M5-37** | Zeiger und Unterbrecher je Host in Postgres für Harvester, `materialize`, Pyramide (W6, W7) | B | B1 | vor M5-19 und M5-24 |
| **M5-38** | `extend` und `sweep` der Pyramiden unter Sperre (W5) | A | B2 | — |
| **M5-39** | Vorlage zur Freigabe gelisteter Einträge in Postgres (Bedingung zu F4: Lizenzregeln und Stichproben statt PR je Eintrag); Nachträge `adr/0025` §7.1, `adr/0031` | C | B5 | vor M5-40 |
| **M5-40** | Gelistete Einträge in Postgres, Frontend blättert statt Gesamtliste | B | B5 | nach M5-39, vor M5-17 |
| **M5-41** | Nachtrag `adr/0026` F3: pgvector ≥ 0.8.0 mit HNSW, Recherche aus Primärquellen | C | B4 | vor M5-23 |
| **M5-42** | Lexikalische Suche indexfähig | B | B7 | — |
| **M6** | `host_cap` je Host und `global_cap` je Pool (B6); Egress-Proxy mit Grenzen je Ziel (B1); Pooler (W1); CDN (B3); Lasttest mit N Instanzen je Prozesstyp (`architekturplan.md` 12.4) | — | B1, B3, B6, W1 | M6 |
