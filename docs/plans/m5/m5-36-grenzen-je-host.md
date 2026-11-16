# M5-36 — Grenzen je Host in der Registry, Teilbudget je Instanz: Plan-Schritt

**Status (16.11.2026):** Plan angenommen (Otto, 16.11.2026: G1–G6 je 1, §8a), **Stufe B**. PR 1 nach §7 umgesetzt und gemessen (§9), PR 2 folgt.
**Aufgabe:** M5-36 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2, Auftrag von Otto vom 16.11.2026.
**Grundlagen:** `plans/m5/m5-35-skalierbarkeit.md` B1 (§2), B3 (§4.2), F1 = 1 (§8a); `adr/0032` §8.2 und Nachtrag 14.11.2026 (`TileGate`); `adr/0023` §3.1 (Fair Use der FSDI); `adr/0005` §6 (6 Verbindungen je Host); `architekturplan.md` 3.1, 6.5; KLAERUNGEN B8, B9.

Belegstufen wie in `adr/0025`: **P** am Quelltext gelesen (Stand `main` 5099e32), **S** Sekundärquelle, **A** eigene Ableitung. Gemessen wird erst in der Umsetzung, nur gegen die synthetische Quelle (§6); keine echte Quelle aus der Sitzung.

---

## 1. Ziel

Die Last auf eine Quelle soll nicht mehr mit der Zahl der Instanzen wachsen. Nach F1 = 1 heißt das bis zum Egress-Proxy in M6:

1. Die Grenzen je Host stehen **in der Registry**, nicht im Code.
2. **Zarr-Stores teilen ein `Gateway` je Prozess**, statt je Store eines zu bauen.
3. **Der `tiler` begrenzt GDAL-Lesen je Host** wie `api` heute (`ReadSlots`), dazu das Lesen der Zarr-Stores.
4. **Festes Teilbudget je Instanz:** Jede Instanz bekommt die Grenze der Quelle geteilt durch die konfigurierte Zahl der Instanzen; zusammen halten N Instanzen die Grenze.

Randbedingungen aus dem Auftrag: Kacheln werden nicht spürbar langsamer (vorher/nachher gemessen, §6); nie verschwindet ein Bild; Importregeln bleiben, wie sie sind.

**Nicht Teil von M5-36:** der Zeiger je Host in Postgres für Harvester, `materialize` und Pyramidenbau (M5-37); `host_cap`/`global_cap` der Job-Queue (M6, F6); GDAL im Kind des Workers (bleibt über `host_cap` = 2 Läufe je Host begrenzt, M5-37/M6); Unterbrecher je Host über Instanzen (M5-37, W6).

---

## 2. Ausgangslage im Code [P]

| Grenze | Wo | gilt heute für |
|---|---|---|
| 6 gleichzeitige Anfragen je Host | `Policy.max_connections_per_host` (`gateway/policy.py:124`), `asyncio.Semaphore` je Host im `Gateway` (`gateway/client.py:115`, `:413–416`) | je `Gateway`-Objekt |
| Mindestabstand je Host | `Policy.min_interval_s`, `host_intervals` (`gateway/policy.py:130–133`); `_space` (`gateway/client.py:284`) | je Objekt; gesetzt nur von `materialize`, fest im Code: FSDI 1 s (`discovery/materialize.py:87`, `:187–197`) |
| 0,25 s je Host für GDAL im Pyramidenbau | `HostPacer` (`gateway/pacer.py`), `EARTHX_OVERVIEW_HOST_INTERVAL_S`; nimmt einen Eintrag aus `host_intervals` vor der Vorgabe | je Bau; cluster-weit, weil höchstens ein Bau je Host läuft |
| 6 GDAL-Leser je Host | `ReadSlots` (`gateway/slots.py`), eine Instanz je Prozess `api` (`api/main.py:231`) | nur Wolken- und Überflugfilter der Suche (`api/aoi_cloud_filter.py:543`, `api/pass_filter.py:257–260`) |

**Der `tiler`** (`api/tiler.py:2366–2420`) baut seine `Policy` aus der Registry (`policy_from_registry`, `api/dependencies.py:145–157`: nur Allowlist, alle Grenzen auf Vorgabe) und ein `Gateway` für Item-Abrufe (`api/tiler.py:2311`). `ReadSlots` kommt im `tiler` nicht vor. Seine Lesestellen auf Quellen:

| Lesestelle | Faden | Host bekannt |
|---|---|---|
| Einzelkachel, TileJSON, Statistik, Vorschau über die Factory von titiler (`reader=_open_reader`, `api/tiler.py:797–801`, `access/tiles.py:75–88`, `:371–373`, `:458–485`) | Thread-Pool von Starlette (synchrone Routen, 40 Fäden) | im `AssetPath` aus der Pfad-Abhängigkeit, vor dem Thread |
| Mosaik-Kachel und Dateien des Ersatzes (`access/mosaic_tiles.py:394–455`; `read()` je Szene `:428`) | eigene Fäden von rio-tiler, 4 je Kachel, höchstens 2 Kacheln je Prozess hinter `TileGate` | je Szene im `AssetPath` |
| Zuschnitt zum Download (`api/tiler.py:2132–2169`, `access/download.py`) | `run_in_threadpool`, große Ausgabe einzeln | je Asset |
| Flächen-Statistik (`api/area_statistics.py:146–152`, `:247`), Operatoren (`_open_reader` mit `OperatorInput`, `processing/tile.py`) | Thread-Pool | je Eingabe; Weg in der Umsetzung zu verfolgen |
| Zarr (`readers/zarr_reader.py:156–278`) | Event-Loop von zarr in eigenem Faden; **jeder Store baut ein eigenes `Gateway`** (`:264–278`, `:544`) | je Anfrage |

Keine Lesestelle: Pyramiden und Ergebnisse aus dem eigenen Objektspeicher (`access/overview_tiles.py`, `api/result_tiles.py`).

**Importregel** (`.importlinter:110–126`): `access` darf `gateway` **nicht** importieren, auch nicht indirekt; `readers` darf es. Ein Platz je Host erreicht `access` deshalb nur als hereingereichtes Objekt, wie der `Pacer` im Kern (`processing/overview.py:77`).

**Registry:** Sechs volle Einträge mit sechs Hosts, davon vier S3-Buckets (`backend/catalog/datasets/*.yaml`, `source.endpoint` und `source.asset_hosts`). Hosts werden geteilt: WorldCover 2020 und 2021 auf demselben Bucket, Sentinel-1 und -2 auf demselben Endpunkt. Heute hat kein Eintrag Zarr (`zarr: null`); der Zarr-Pfad wird trotzdem umgebaut, weil er der Weg für EOPF-Zarr bleibt.

---

## 3. Grenzen je Host in der Registry (nach G1, G2)

### 3.1 Form (Vorschlag G1 = 1)

Eine neue Datei **`backend/catalog/hosts.yaml`**, ein Eintrag je Host. Grund für eine eigene Datei statt eines Felds im Datensatz: Hosts gehören mehreren Datensätzen (§2); eine Grenze ist eine Regel der Quelle, nicht des Datensatzes, und zwei Datensätze könnten sich sonst widersprechen.

```yaml
# Die Grenzen gelten für die ganze Plattform, alle Instanzen zusammen (M5-36).
hosts:
  data.geo.admin.ch:
    connections: 6        # gleichzeitige Anfragen bzw. GDAL-Leser
    interval_s: 1.0       # Mindestabstand zwischen zwei Anfragen; fehlt = keine Regel der Quelle
    reason: FSDI, Fair Use (adr/0023 §3.1)
  esa-worldcover.s3.eu-central-1.amazonaws.com:
    connections: 32
    reason: AWS Open Data, Bucket
```

- **Prüfung beim Laden** (streng wie die Datensätze, `catalog.datasets.registry()`): Host in der Schreibweise von `normalize_host`; `connections` ganzzahlig 1–256; `interval_s` 0–300 s (`gateway.policy.MAX_INTERVAL_S`) oder fehlt; `reason` Pflicht. Ein Host, den kein voller Eintrag nennt, ist ein Ladefehler (keine toten Einträge). Jeder Host eines vollen Eintrags (`endpoint`, `asset_hosts`) braucht einen Eintrag; fehlt einer, ist das ein Ladefehler (die sichere Seite, wie `asset_hosts` ohne Vorgabe).
- **Lader:** `catalog/hosts.py` (neu), gibt ein unveränderliches `HostLimits` zurück; `DatasetRegistry` hält es neben den Einträgen. `gateway` liest die Datei nicht (es kennt keine Datensätze); die Hülle (`api`, `discovery`) übersetzt in die `Policy`.
- **Prototyp-Instanz:** Die Hosts der Prototyp-Einträge (`backend/catalog/prototype/`) stehen in einer eigenen `hosts.yaml` daneben, die nie ins Image kommt (wie `adr/0024` R4, R5).
- **Onboarding:** `adr/0031` bekommt einen Satz: Ein neuer Host braucht eine Zeile in `hosts.yaml`; die Grenze ist eine Angabe zur Quelle und wird mit dem Eintrag geprüft (keine Lizenzfrage).

### 3.2 `Policy`

- **Neu `Policy.host_connections: Mapping[str, int]`**, wie `host_intervals`: Eintrag des Hosts oder des nächsten Elternteils, sonst `max_connections_per_host`. Methode `connections_for(host)`. Werte ≥ 1.
- Alle 10 Stellen im Produktivcode, die heute `Policy(...)` bauen, bleiben unverändert und behalten 6 je Host. Nur die Policy aus der Registry (`policy_from_registry`) und `materialize` setzen die neuen Felder.

### 3.3 Wer welche Angabe nutzt

| Angabe | `api`, `tiler` | `materialize` | Pyramidenbau, Harvester |
|---|---|---|---|
| `connections` | Teilbudget je Instanz (§5) | volle Grenze (ein Lauf; cluster-weit erst mit M5-37) | unverändert bis M5-37 |
| `interval_s` | **nicht angewandt** (G3) | ja, ersetzt die feste Tabelle `ENDPOINT_INTERVALS_S` (FSDI 1 s; Verhalten gleich) | unverändert bis M5-37 (`HostPacer` 0,25 s) |

Ein Host ohne `interval_s` bekommt in `materialize` keinen Abstand, wie heute bei den Buckets. Der Pyramidenbau bleibt bei seiner Vorgabe 0,25 s, weil seine Policy nicht aus der Registry kommt (`readers/access.py:105–125`).

---

## 4. Ein Zähler je Host und Prozess; Zarr teilt das Gateway

### 4.1 `HostSlots` statt zweier Zähler

Im selben Prozess fragen heute zwei getrennte Zähler: das Semaphor des `Gateway` (asynchron, je Objekt) und `ReadSlots` (Fäden). Zusammen könnten sie die doppelte Grenze stellen. Vorschlag: **ein Zähler je Host und Prozess** in `gateway/slots.py`:

- `HostSlots(policy)`: je Host höchstens `policy.connections_for(host)` Inhaber. `with slots.slot(host):` für Fäden (GDAL), `async with slots.aslot(host):` für den Event-Loop (`httpx`, Zarr). Gemeinsame Warteschlange in Reihenfolge der Anfrage; ein wartender Event-Loop wird über `call_soon_threadsafe` geweckt, blockiert also keinen Faden. Ein Platz wird auch bei Fehler und Abbruch (`CancelledError`) zurückgegeben.
- `ReadSlots` wird zu `HostSlots` (der Name bleibt als Alias für die zwei Aufrufer in `api`, oder sie werden umbenannt; entscheidet die Umsetzung nach Umfang).
- `Gateway(policy, slots=...)`: Ohne Angabe baut es sich eigene `HostSlots`, wie heute je Objekt; Tests, Runner, Worker und `materialize` ändern sich damit nicht. `api` und `tiler` geben ihre eine Instanz herein.
- **Keine Verschachtelung:** Ein Zarr-Leser hält keinen Platz für den Leser, nur jede Anfrage über das `Gateway` (sonst könnten alle Plätze bei Lesern liegen, die auf einen Platz für ihre Anfragen warten). Ein GDAL-Leser hält einen Platz von Öffnen bis Schließen; GDAL fragt nicht über das `Gateway`. Ein Operator mit Eingaben auf mehreren Hosts nimmt die Plätze in der Reihenfolge der Hostnamen (keine Verklemmung).

### 4.2 Zarr: ein `Gateway` je Prozess und Event-Loop

zarr führt jede Store-Anfrage auf **einem** eigenen Event-Loop in eigenem Faden aus (`zarr.core.sync`). Vorschlag: `readers/zarr_reader.py` hält ein `Gateway` je (Event-Loop, Policy) für den ganzen Prozess, gebaut beim ersten Lesen; ein Store schließt es nicht mehr, der Prozess schließt es beim Herunterfahren (Lifespan des `tiler`, `atexit` sonst). `ZarrAsset` trägt die `HostSlots` des Prozesses neben `policy` und `resolve`; fehlen sie (Worker, Runner), teilen sich die Stores dort ein `Gateway` mit eigenen Plätzen. Damit gelten die Grenzen auch für vier Zarr-Szenen einer Mosaik-Kachel zusammen (heute 4 × 6 = 24, M5-35 §2.1).

---

## 5. `tiler`: Plätze je Host und Teilbudget je Instanz

### 5.1 Zahl der Instanzen (Vorschlag G4 = 1)

- **`EARTHX_SOURCE_INSTANCES`**: die höchste Zahl der Prozesse `api` und `tiler` zusammen, die gleichzeitig laufen dürfen. Vorgabe 1 (heutiges Verhalten). Eine ganze Zahl ≥ 1; ein anderer Wert hält den Prozess beim Start an, die Meldung nennt die Variable, nicht den Wert (wie `EARTHX_USER_AGENT`). In `docker-compose.yml`, `.env.example` und README; `docs/cloud-umgebung.md` bekommt den Satz, dass die Zahl beim Skalieren mitgeht.
- **Teilbudget:** je Host `max(1, connections // EARTHX_SOURCE_INSTANCES)`. Ist `connections` kleiner als die Zahl der Instanzen, startet der Prozess trotzdem mit 1 je Host und schreibt beim Start eine Warnung mit dem Host (ein öffentlicher Name aus der Registry). Grund: ein `tiler`, der nicht startet, zeigt kein Bild; die Warnung macht sichtbar, dass die Summe dann über der Grenze liegt.
- `api` und `tiler` bauen ihre `Policy` aus der Registry mit diesen Teilbudgets und eine `HostSlots` je Prozess; das `Gateway` des Prozesses, die Zarr-Stores und alle GDAL-Leser teilen sie.

### 5.2 Wo gewartet wird (B3)

Warten auf einen Platz darf den Thread-Pool von Starlette nicht füllen (M5-35 §4.2). Deshalb:

- **Einzelkachel, TileJSON, Statistik, Vorschau:** Der Platz wird **vor dem Thread-Pool** genommen, asynchron in einer Abhängigkeit mit `yield` an der Pfad-Abhängigkeit (`dataset_asset_path`), die den Host schon kennt, und nach der Antwort zurückgegeben. Der Faden der Route wartet also nie.
- **Mosaik-Kachel und Ersatz:** Die Kachel wartet wie heute am `TileGate` im Event-Loop; danach nimmt jede Szene in ihrem Faden von rio-tiler den Platz ihres Hosts (`access/mosaic_tiles.py:428`). Diese Fäden gehören nicht zum gemeinsamen Pool.
- **Zuschnitt, Flächen-Statistik, Operatoren:** Platz je geöffnetem Leser im Faden; diese Routen laufen selten und sind schon begrenzt (große Ausgabe einzeln, `api/tiler.py:2125`).
- **Importregel:** `access` bekommt den Platz als Protokoll `HostSlot` (ein Kontextmanager je Host), hereingereicht von `api` wie `gdal_config`; `access` importiert nichts aus `gateway`.

### 5.3 Was sich für den Nutzer ändert

- **Kein Bild verschwindet:** Ein Platz wird gewartet, nie verweigert. Das Warten auf einen Platz zählt bei der Mosaik-Kachel zum Budget von 4 s (es liegt nach `TileGate`); reicht die Zeit nicht, gibt es die Teilkachel wie heute bei langsamer Quelle (`adr/0032` §6.2), nie eine leere Antwort ohne Kopf. Die Einzelkachel hat kein Zeitbudget; sie wartet.
- **Langsamer werden kann es nur bei Hosts mit kleiner Grenze** und viel gleichzeitiger Last. Dafür ist die Messung (§6).

---

## 6. Messung vorher/nachher (synthetisch)

Mit dem vorhandenen Messstand `scripts/tile-bench/` (NM4-26, NM4-62): `slow_source.py` (synthetische COGs aus `make_cogs.py`, RTT 170 ms, Verbindungsaufbau 350 ms), der echte `tiler` über `run_tiler.py`, `compare.sh <main> <branch>` mit 5 Wiederholungen im Wechsel. Keine echte Quelle, keine AOI im Log.

| Fall | Werkzeug | Grenze des synthetischen Hosts |
|---|---|---|
| Ansicht 13 Szenen × 25 Kacheln (Ottos NDVI-Ansicht vom 25.10.2026) | `view.py` | 32 und 6 |
| Mosaik-Kachel kalt und warm, 4 Szenen | `cold_warm.py` | 32 und 6 |
| Viele Einzelkacheln auf einem Host: 40 gleichzeitig | `view.py --conns 40` | 6 |
| Wie oben mit `EARTHX_SOURCE_INSTANCES=2` (nur nachher) | `view.py` | 6 → 3 je Instanz |

`run_tiler.py` bekommt dafür eine Registry-Datei `hosts.yaml` für den synthetischen Host. Ergebnis als Tabelle (Median, p95, Wandzeit) im Plan §9 und im PR. **Schwelle „nicht spürbar langsamer“: G5.**

---

## 7. Schnitt (Vorschlag G6 = 1)

| PR | Inhalt | Umfang (ohne Tests, geschätzt) |
|---|---|---|
| **PR 1** (dieser Draft-PR) | Plan; `hosts.yaml` mit Lader und Prüfung; `Policy.host_connections`; `materialize` aus der Registry; `HostSlots` mit `aslot`; `Gateway(slots=…)`; Zarr teilt ein `Gateway` je Prozess; Nachträge `architekturplan.md` 6.5, `adr/0005` §6, `adr/0031`, KLAERUNGEN B13 (Nachtrag) | ~350 Zeilen |
| **PR 2** | `EARTHX_SOURCE_INSTANCES` und Teilbudget in `api` und `tiler`; Plätze an allen Lesestellen des `tiler` (§5.2); Messung §6 vorher/nachher; Compose, `.env.example`, README, `cloud-umgebung.md` | ~300 Zeilen |

PR 2 baut auf PR 1 auf. Tests je PR, mit Fehlerfällen: fehlender und überzähliger Host in `hosts.yaml`, falsche Werte (0, negativ, `NaN`, über der Grenze, falscher Typ, Host als IP), Teilbudget bei N > Grenze, ungültige Variable; `HostSlots` mit Fäden und Event-Loop gemischt, Abbruch beim Warten, Fehler im Block, Reihenfolge; Zarr: zwei Stores, ein `Gateway`, gemeinsame Grenze; `tiler`: jede Lesestelle hält einen Platz (aufzeichnende Plätze), Einzelkachel wartet nicht im Thread-Pool, Mosaik-Kachel mit Grenze 1 liefert vollständig oder als Teilkachel. Ein Test prüft, dass die Hosts der Registry und `hosts.yaml` zusammenpassen.

---

## 8. Fragen an Otto

**G1 — Wo stehen die Grenzen je Host?**
1. Eigene Datei `backend/catalog/hosts.yaml`, ein Eintrag je Host, Pflicht für jeden Host eines vollen Eintrags **(Empfehlung, §3.1)**
2. Im Datensatz unter `source`; zwei Datensätze mit verschiedenen Werten für einen Host sind ein Ladefehler
3. Wie 1, aber ohne Pflicht: Hosts ohne Eintrag bekommen 6 Verbindungen und keinen Abstand

**G2 — Welche Werte (für alle Instanzen zusammen)?**
1. `data.geo.admin.ch` 6 Verbindungen und 1 s Abstand (Wert von `materialize`); `earth-search.aws.element84.com` 6; die vier S3-Buckets je 32 **(Empfehlung: S3 trägt Tausende Anfragen je Sekunde und Präfix, M5-35 §2.2 [S]; mit 6 würden S3-Kacheln ab 2 Instanzen langsamer)**
2. Alle Hosts 6 wie heute (dann teilen sich 2 Instanzen 3 je Host, auch bei S3)
3. Andere Werte: bitte je Host nennen

**G3 — Gilt der Abstand je Host auch für Kacheln und Suche?**
1. Nein: Kacheln und Suche halten nur die Verbindungen; der Abstand gilt für `materialize`, später Harvester und Bau (M5-37) **(Empfehlung: eine swissALTI3D-Kachel liest bis 32 Dateien mit je 1–2 Anfragen; bei 1 s Abstand wären es 30–60 s)**
2. Ja, auch für Kacheln

**G4 — Wer teilt sich die Grenze eines Hosts?**
1. Alle Prozesse `api` und `tiler` zusammen, über eine Zahl `EARTHX_SOURCE_INSTANCES` **(Empfehlung: nur so hält die Summe sicher)**
2. Nur der `tiler` teilt (`EARTHX_TILER_INSTANCES`); `api` behält die volle Grenze je Prozess
3. Feste Anteile je Prozesstyp (z. B. `tiler` zwei Drittel, `api` ein Drittel), je eine Zahl der Instanzen

**G5 — Was heißt „nicht spürbar langsamer“ in der Messung (§6) bei einer Instanz?**
1. Median und p95 je Fall höchstens 5 % über `main`, bei Grenze 32 und bei Grenze 6 **(Empfehlung)**
2. Höchstens 10 %
3. Nur bei Grenze 32 (S3); bei Grenze 6 wird berichtet, nicht gefordert

**G6 — Schnitt?**
1. Zwei PRs wie §7 **(Empfehlung)**
2. Ein PR mit allem (über 600 Zeilen)

### 8a. Antworten Otto (16.11.2026)

| Frage | Antwort | Folge |
|---|---|---|
| G1 | 1 | `backend/catalog/hosts.yaml`, Pflicht für jeden Host eines vollen Eintrags (§3.1) |
| G2 | 1 | FSDI 6 und 1 s; Earth Search 6; vier S3-Buckets je 32 |
| G3 | 1 | kein Abstand für Kacheln und Suche |
| G4 | 1 | `EARTHX_SOURCE_INSTANCES` für `api` und `tiler` zusammen (PR 2) |
| G5 | 1 | Median und p95 je Fall höchstens +5 % über `main`, bei Grenze 32 und 6 |
| G6 | 1 | zwei PRs nach §7 |

---

## 9. Umsetzung und Messung

### 9.1 PR 1 ([#360](https://github.com/oscipal/earthX/pull/360)), Stand 16.11.2026

- **`backend/catalog/hosts.yaml`** mit den Werten aus G2; Lader `catalog/hosts.py`; `DatasetRegistry(…, hosts=…)` prüft beide Richtungen (`source_hosts`). Eine Registry ohne Datei (Tests) hat keine Grenzen, die `Policy` dann die Vorgabe 6. Das Image kopiert die Datei. Prototyp-Hosts in einer eigenen `hosts.yaml` im Prototyp-Verzeichnis (README dort nachgeführt); **Otto braucht sie lokal**, sobald ein Prototyp-Eintrag einen Host liest, der nicht in der freigegebenen Datei steht.
- **`Policy.host_connections`** und `connections_for(host)`; Werte 1–256, auch `max_connections_per_host`.
- **Abweichung vom Plan:** Der Zähler heißt weiter **`ReadSlots`** (kein `HostSlots`), weil 46 Stellen ihn so nennen; er hat jetzt `slot()` für Fäden und `aslot()` für Event-Loops. Wer aufhört zu warten (Abbruch, Unterbrechung), verlässt die Warteschlange oder gibt einen schon übergebenen Platz weiter. `Gateway(policy, slots=…)` nutzt ihn statt eines Semaphors je Objekt. Noch übergibt kein Prozess seinen Zähler; das verdrahtet PR 2 zusammen mit dem Teilbudget.
- **`policy_from_registry`** setzt `host_connections`, keinen Abstand (G3). **`materialize`** nimmt Verbindungen und Abstand seiner Hosts aus der Registry; die feste Tabelle `ENDPOINT_INTERVALS_S` entfällt, die FSDI bleibt bei 1 s.
- **Zarr:** ein `Gateway` je (Event-Loop, Policy, Naht `open_gateway`) für den Prozess; der Resolver gehört nicht zum Schlüssel, weil `read_access_for` je Lauf einen neuen baut (sonst bliebe je Flächen-Statistik ein Client liegen, Befund der Prüfung). `close()` eines Stores lässt es offen; der `tiler` schließt es am Ende seines Lifespans in einem Faden, sonst `atexit`.
- **Importregeln:** `catalog.hosts` steht im Vertrag `runner` unter den verbotenen Modulen (Verschärfung, wie jedes andere Modul von `catalog`); sonst unverändert, `lint-imports` 16 von 16.
- **Messstand:** `scripts/tile-bench/run_tiler.py` beantwortet jetzt die gebündelte Item-Suche (`POST /search` mit `ids`), die Mosaik-Auswahlen seit M5-30b stellen; vorher endeten die Mosaik-Messungen auch auf `main` mit `500`. `job_bench.py` ist ebenfalls veraltet (importiert `REGISTRY`, seit M5-13 entfallen); Jobs gehören nicht zum Kachelpfad und wurden nicht gemessen.

### 9.2 Messung vorher/nachher (G5)

Synthetische Quelle (`slow_source.py`, RTT 170 ms, Verbindungsaufbau 350 ms, COGs aus `make_cogs.py`), echter `tiler`, `main` 5099e32 gegen den Branch eddee1d, 5 Wiederholungen je Stand im Wechsel, jeder Lauf mit frischen Prozessen und leeren Caches. Keine echte Quelle.

| Fall | n | main Median | Branch Median | Δ Median | main p95 | Branch p95 | Δ p95 |
|---|---|---|---|---|---|---|---|
| Mosaik-Kachel kalt, 4 Szenen, NDVI, z10 (s) | 5/5 | 3,71 | 3,71 | +0,1 % | 3,75 | 3,76 | +0,4 % |
| Mosaik-Kachel warm (s) | 5/5 | 0,35 | 0,33 | −6,2 % | 0,37 | 0,35 | −5,1 % |
| Zuschnitt 0,05° (s) | 5/5 | 2,51 | 2,49 | −0,8 % | 2,53 | 2,56 | +1,2 % |
| Ansicht 13 Szenen × 25 Kacheln, Wandzeit (s) | 5/5 | 26,2 | 26,0 | −0,8 % | 27,8 | 26,3 | −5,4 % |
| Ansicht, je Kachel beim Client (s) | 1625/1625 | 15,66 | 15,53 | −0,9 % | 24,80 | 24,57 | −0,9 % |

Alle 1625 Kacheln je Stand mit `200`; die Prüfsummen der Raster des Zuschnitts sind in allen Läufen beider Stände gleich. **Ergebnis:** kein Fall über +5 % (G5). Die Rückgänge liegen im Rauschen. Grenze 6 wirkt in PR 1 nur auf die Item-Abrufe (Earth Search, jetzt über den gemeinsamen Zähler); GDAL-Lesen ist in PR 1 noch nicht begrenzt. Die Fälle mit Grenze 6 und 32 für GDAL und mit `EARTHX_SOURCE_INSTANCES=2` (§6) misst PR 2.
