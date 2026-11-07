# M5-08 — Allgemeiner STAC-Adapter und swissALTI3D: Plan-Schritt

**Status (07.11.2026):** Plan angenommen (Otto, 07.11.2026; Antworten in §8a). Teil 1 (M5-08a: Vergleichstest und `stac_api.py`) umgesetzt im selben Draft-PR [#314](https://github.com/oscipal/earthX/pull/314) (§11); M5-08b und M5-08c folgen als eigene PRs.
**Aufgabe:** M5-08 aus `docs/plans/m5/m5-discovery-und-suche.md` §6.2. **Stufe B.** Hängt von M5-13 ab (gemergt mit #311). Danach warten M5-10, M5-09 und M5-11 auf den Merge. **DS-04** (#312) baut Sentinel-1 nach dem Merge auf dem neuen Adapter; Earth Search muss dabei bitgleich bleiben (§3.2).
**Modell:** Opus, Effort hoch.
**Grundlagen:** `adr/0011` F1, F6 und §8.2 (Dialekt je STAC-API); `adr/0005` Regeln I–V; `adr/0023` §4.1, §7.2, §7.3, §8.3, §9.1, F2, F5, F7, §11 Punkt 2; `adr/0025` §9 (Stände: Regel bei M5-08); `adr/0030` §5.4; `adr/0026` F7 (Schlagworte, Glossar); `adr/0024` (`legal_status`); `adr/0027` §6.1 (`access.account`); `KLAERUNGEN.md` B8, B10–B13; `architekturplan.md` 3.1, 5.1, 5.2, 6.1; `projektuebersicht.md` §5.

Belegstufen wie in `adr/0023`: **M** in dieser Sitzung gemessen (07.11.2026, nur Metadaten und ein Range-Read von 1024 Bytes, mit `curl` über den Proxy der Sitzung), **P** am Quelltext oder Primärtext gelesen (Code: Stand `main` 309f0ec), **A** eigene Ableitung. Item-IDs, `href`, Prüfsummen und Flächen stehen nicht in diesem Dokument.

---

## 1. Ziel

1. **Ein Modul für STAC-APIs.** Aus `adapters/earth_search.py` wird `adapters/stac_api.py` mit einem **Dialekt je Quelle** (`adr/0011` F6: „erst mit der nächsten STAC-API-Quelle“, das ist diese). Der Dialekt enthält, was sich je API unterscheidet: Feld der Seitenmarke, `FilterSupport`, Übersetzung der Bedingungen, Normalisierung der Items (`adr/0011` §8.2).
2. **Earth Search bitgleich.** Gleiche Anfragen Byte für Byte, gleiche Cache-Schlüssel, gleiche Seitenmarken, gleiche Items. Der Registry-Eintrag von Sentinel-2 ändert sich nicht (§3.2).
3. **Zweiter Dialekt FSDI** (STAC API von swisstopo, `data.geo.admin.ch`) und **Materialisierung über eine STAC-API**: Alle Items einer Collection werden seitenweise gelesen und in die eigene pgstac geladen, mit dem Einmal-Befehl aus M3-11b.
4. **swissALTI3D** als vierter materialisierter Datensatz (nach DEM und WorldCover 2020/2021), als YAML unter `backend/catalog/datasets/`, mit vollständiger Onboarding-Checkliste.
5. **Regel für mehrere Stände je Kachel** als allgemeine Registry-Angabe (`adr/0023` §8.3, `adr/0025` §9). BEV (M5-09) nutzt dieselbe Angabe.

**Nicht Teil von M5-08:** der Geländeoperator und die Capability `terrain` (M5-10, `adr/0023` F5); BEV (M5-09); SWISSIMAGE und MeteoSchweiz (andere Aufgaben, gleicher Dialekt); die Differenz zweier Stände (`adr/0030` §5.4, P3); die Abbildung `s3://` → `https://`, die Prüfsumme `crc64nvme` und die Hinweise je Datensatz (DS-04b).

---

## 2. Messungen an der Quelle (07.11.2026) [M]

FSDI-STAC unter `https://data.geo.admin.ch/api/stac/v1`, Collection `ch.swisstopo.swissalti3d`. Ergänzt `adr/0023` §4.1 und §9.1 (06.11.2026).

| Was | Ergebnis |
|---|---|
| Konformität | Core, Collections, OGC Features, Item Search, Sort (1.1.0), Sortables. **Keine** Query-Extension, **kein** CQL2 |
| Collection | `license: proprietary`; Ausdehnung CH und FL (rund 5,95–10,50° O, 45,72–47,82° N); Zeitraum 2019-01-01 bis 2026-01-01; ein Provider („Federal Office of Topography swisstopo“); `summaries`: `gsd` 0,5 und 2, `proj:epsg` 2056; kein `item_assets`; `ETag`, `cache-control: max-age=600`; bedingte Anfrage `304` |
| Suche `POST /search` | Antwort ohne `numberMatched` und ohne `context` |
| Seitenmarke | Link `next` mit `method: POST`, **`merge: true`** und `body: {"cursor": …}`. Earth Search dagegen: `merge: false`, ganzer Body mit `next` (Fixtures `tests/fixtures/earth_search/`) |
| `sortby` | `properties.datetime desc` und `id asc` wirken (Reihenfolge der Jahre kehrt sich um). Sortables: `id`, `datetime`, `title`, `created`, `updated` |
| Unbekanntes Feld im Body | **`400`** mit Namen des Feldes. Earth Search übergeht so etwas (`adr/0021`) |
| `query` | `400` für jedes Feld außer `created`, `updated`, `title`, `cf:standard_name`, `unit`. Für Filter nach `adr/0021` also nicht brauchbar |
| `filter` (CQL2) | `400` |
| `ids`, `intersects`, `bbox`, `datetime` | wirken |
| `limit` 101 | `200` mit 100 Items, **ohne Fehler**. Eine Seite mit 100 Items wiegt rund 280 kB |
| Unbekannte Collection | `200` mit leerer Liste (wie Earth Search; Regel I fängt das ab) |
| `bbox` mit Breite 95° | `400` (Earth Search: still angenommen) |
| Item per `GET …/items/{id}` | `200`; unbekanntes Item `404` |
| Item | `properties` nur `datetime` (1. Januar des Jahres), `created`, `updated`; kein `title`, kein `start_datetime`, keine Kachelangabe. ID-Form `swissalti3d_<Jahr>_<Kachel>` |
| Assets | vier je Item: COG 0,5 m, COG 2 m, ASCII-XYZ 0,5 m und 2 m (ZIP). **Schlüssel ist der Dateiname** (mit Jahr und Kachel), also je Item verschieden. Je Asset `type`, `gsd`, `proj:epsg`, `file:checksum` (Multihash SHA2-256), `created`, `updated` |
| Asset-Host | derselbe Host wie die API; S3 hinter CloudFront; Range `206`; `ETag`, `Last-Modified`; `Access-Control-Allow-Origin: *` |
| Lage | LV95 (EPSG:2056). PROJ wählt ohne Gitterdatei „CH1903+ to WGS 84 (1)“ mit 1 m Genauigkeit; es fehlt keine Transformation (pyproj der Sitzung) |

**Stände je Kachel** in fünf Stichproben (je rund 0,1° × 0,08°, ganze Seiten):

| Gebiet | Kacheln | Stände |
|---|---|---|
| Mittelland | 80 | alle 2019 und 2025 |
| Berner Alpen | 75 | alle 2019; dazu 2024 (66), 2025 (38); 29 Kacheln mit drei Ständen |
| Tessin | 64 | alle 2019 und 2022 |
| Jura | 54 | alle 2019; dazu 2021 (53), 2025 (7) |
| Graubünden | 75 | alle 2019 und 2023 |

- **Jede Kachel hat einen Stand 2019 und einen bis zwei neuere.** Mehrere Stände sind der Normalfall, keine Ausnahme.
- Bei einem Drittel der Kacheln (25 von 75 im Alpengebiet) unterscheidet sich die Geometrie der Stände. Die Kachel ist also nur über die ID erkennbar, nicht über den Umriss.
- Hochgerechnet [A]: rund 45 000 Kacheln (`adr/0023` §8.3) mal rund 2,2 Stände ≈ 100 000 Items, ≈ 1 000 Seiten, ≈ 280 MB Metadaten für einen vollen Lauf.

**Quellenangabe [P]** (Seite „How to indicate the source“ von swisstopo, heute erreichbar, am 06.11.2026 noch `500`): Bei dynamischen Karten steht die Quelle ideal neben den Daten, zulässig ist eine zentrale Seite mit Link. Bei abgeleiteten Daten darf „derived from …“ vor der Quellenangabe stehen.

---

## 3. Ausgangslage im Code [P]

- **`adapters/earth_search.py`**: `search_items`, `get_item`, `normalize_item`, `_search_body`, `query_extension`, `_storable`, `_next_marker`. Quellspezifisch sind nur drei Stellen (`adr/0011` §3.2 B2): das Feld der Marke (`body.next`), die Übersetzung der Bedingungen (`query`) und `normalize_item` (`with_core_bands`). Alles andere liegt schon in `federated_search.py` (Regeln III und V, Cache, Fingerabdruck, Seitenmarke).
- **`adapters/earth_search_coverage.py`** ruft `/aggregate` von Earth Search und nutzt `query_extension`. Die Aggregation ist Earth-Search-eigen und bleibt es.
- **`adapters/spec.py`**: `AdapterSpec` je `AdapterKind`; Earth Search mit `FilterSupport(intersects, ids, cql2=False, query=True)`.
- **`AdapterKind`**: `earth-search-v1`, `cop-dem-bucket`, `esa-worldcover-bucket`. Der Wert `earth-search-v1` steht im YAML von Sentinel-2 und im Plan von DS-04.
- **Materialisierung**: `MaterializeOutcome` (`status`, `source_version`, `listed`, `in_bucket`, `missing`, `withheld`, `unknown`, `items`); `discovery/materialize.py` schreibt in einer Transaktion und protokolliert in `earthx_materialize_runs` (Spalten `listed`, `missing`, `withheld`). Abbruch bei mehr als 1 % nicht ladbarer Einträge (`MAX_NOT_LOADABLE_FRACTION`).
- **Gruppierung**: `ViewerInfo.group_by` verlangt mindestens eine Eigenschaft. Der DEM gruppiert über `start_datetime`, das alle Items gleich tragen; ein Mosaik nimmt das erste gültige Pixel (`api/mosaic_tiles.py`).
- **Registry**: kein Feld für feste Asset-Schlüssel und keines für Stände. `default_render.assets`, `band_units` und `auxiliary_assets` nennen Asset-Schlüssel und setzen damit voraus, dass jedes Item dieselben Schlüssel hat.
- **Fassung einer Eingabe** (`processing/recipe.py`, `input_version`): zuerst `file:checksum`. Die FSDI liefert es an jedem Asset.

---

## 4. Umsetzung

### 4.1 `adapters/stac_api.py` mit Dialekten

- **`StacDialect`** (frozen, ohne Vorgaben, B10): `kind`, `marker_field` (`"next"` bzw. `"cursor"`), `filters: FilterSupport`, `write_conditions` (Funktion oder `None`), `normalize_item`.
- **Generisch** `search_items(dialect, config, params, …)` und `get_item(dialect, config, item_id, …)`: der heutige Code aus `earth_search.py`, mit dem Dialekt an den drei Stellen aus §3. `spec.py` bindet je `AdapterKind` die Funktionen an ihren Dialekt (`functools.partial`); die Protokolle `SearchItems`/`FetchItem` bleiben.
- **Seitenmarke**: Der Body ist immer unser eigener (wie heute), die Marke kommt unter `marker_field` hinzu. Das trifft beide Formen: Earth Search (`merge: false`, Body mit `next`) und FSDI (`merge: true`, nur `cursor`). Ein `next`-Link ohne Marke unter dem Feld des Dialekts bleibt `UpstreamShapeError` (heutige Regel).
- **Earth Search**: Dialekt `EARTH_SEARCH` mit `marker_field="next"`, `query_extension` und dem heutigen `normalize_item`. `earth_search.py` entfällt (B6: keine Re-Exporte nötig); `earth_search_coverage.py` importiert `query_extension` aus `stac_api`.
- **FSDI**: neuer `AdapterKind.FSDI_STAC_V1 = "fsdi-stac-v1"`, Dialekt mit `marker_field="cursor"`, `FilterSupport(intersects=True, ids=True, cql2=False, query=False)`, `write_conditions=None`. Da die FSDI jedes unbekannte Feld mit `400` beantwortet, darf der Body nie ein Feld tragen, das der Dialekt nicht kennt; `check_adapter_specs` weist Suchfilter schon heute ab, wenn `query` fehlt.
- **Normalisierung je Eintrag**: `normalize_item` wendet nach dem Dialekt die Angaben des Eintrags an (§4.3 `asset_keys`). Für alle bisherigen Einträge sind diese Angaben leer; DS-04b hängt `asset_href_rewrites` an dieselbe Stelle.

### 4.2 Materialisierung über eine STAC-API

- **`stac_api.materialize_items(dialect, config, gateway, known_version)`** im Protokoll `MaterializeItems`: liest alle Items der Collection über `POST /search` (`collections`, `limit` 100, `sortby` `id asc`, ohne Fläche und Zeit) bis zur letzten Seite.
- **Bedingt**: zuerst `GET` der Collection mit `If-None-Match` aus `known_version` (gemessen `304`). Fassung = `ETag` der Collection. Bei `304` `status="unchanged"` ohne weiteren Abruf. Risiko §7 R1.
- **Je Item**: Normalisierung (§4.1), dann Prüfung gegen die Registry: Collection-Feld, Geometrie, alle Assets aus `asset_keys` vorhanden, Asset-Host in `asset_hosts`, `datetime` vorhanden. Wer durchfällt, zählt als `unknown`; über 1 % bricht den Lauf ab (wie DEM und WorldCover).
- **Stände** nach §4.4, danach `items`.
- **Bericht**: `listed` (gelesene Items), `in_bucket` (= `listed`, die Quelle hat keinen Bucket-Begriff), `missing` 0, `withheld` = ersetzte Stände, `unknown`. Keine Migration (Auslegung A2).
- **Abstand je Host**: `data.geo.admin.ch` bekommt im Materialize-Befehl einen Mindestabstand (M5-18 `host_intervals`), Vorschlag 1 s: rund 17 min für 1 000 Seiten. swisstopo behält sich vor, bei übermäßiger Nutzung zu drosseln (`adr/0023` §4.1).
- Kein Asset wird geöffnet.

### 4.3 Feste Asset-Schlüssel (allgemein)

- **Registry-Feld** `source.asset_keys`: Liste von Regeln `{key, media_type, gsd}`, ohne Vorgabe; leer heißt „Schlüssel wie von der Quelle“ (alle bisherigen Einträge).
- **Bei einer nicht leeren Liste** bekommt jedes Asset den Schlüssel der Regel, auf die Medientyp und `gsd` genau passen. Ein Asset ohne Regel, zwei Assets auf derselben Regel oder eine fehlende Regel machen das Item ungültig (zählt als `unknown`). Ein Asset bleibt nie stillschweigend unter seinem Dateinamen.
- **Startprüfung**: Schlüssel eindeutig und nach den Regeln für Asset-Schlüssel; `default_render.assets`, `band_units` und `auxiliary_assets` nennen nur Schlüssel aus der Liste.
- swissALTI3D nach F2.

### 4.4 Mehrere Stände je Kachel (allgemein)

- **Registry-Feld** `source.item_states`, ohne Vorgabe: `null` (jedes Item ein eigener Stand, alle bisherigen Einträge) oder `{rule, tile_pattern}`.
  - `tile_pattern`: regulärer Ausdruck auf die Item-ID mit genau einer benannten Gruppe `tile`, beim Start kompiliert. Die ID ist das einzige verlässliche Merkmal der Kachel (§2: Geometrie der Stände weicht bei einem Drittel ab).
  - `rule` nach F1.
- **Gruppierung**: Die Materialisierung schreibt `earthx:tile` an jedes Item. Für die Ansicht schreibt sie `earthx:state` mit dem Wert der Regel (z. B. `latest`), gleich für alle Items. `viewer.group_by` und `results_group_by` nennen `earthx:state`, damit eine AOI über Kacheln verschiedener Befliegungsjahre **ein** Mosaik bleibt (Auslegung A3). `datetime` (Befliegungsjahr) bleibt am Item unverändert.
- **Fehler**: ID passt nicht auf `tile_pattern` → `unknown`; zwei Stände einer Kachel mit gleichem `datetime` → `unknown` für beide, weil „jünger“ nicht entscheidbar ist.
- **Veröffentlichung**: `earthx:source` bekommt `asset_keys` und `item_states` (`architekturplan.md` 5.1).

### 4.5 Registry-Eintrag `swissalti3d` (YAML)

| Feld | Wert | Herkunft |
|---|---|---|
| `dataset_id` | `swissalti3d` (im Bewertungs-Set von `adr/0026` vorläufig, hier fest) | A |
| `title` | „swissALTI3D“ | P |
| `description` | Geländemodell (DTM) der Schweiz und Liechtensteins, 0,5 m und 2 m, Kacheln 1 km, LV95, Höhen LN02; Stand je Kachel nach F1; Lage über eine Transformation mit 1 m Genauigkeit | M, P |
| `keywords` | deutsch und englisch (`adr/0026` F7): swissalti3d, swisstopo, Geländemodell, digital terrain model, DTM, Höhenmodell, elevation, lidar, Schweiz, Switzerland, Liechtenstein | A |
| `category` | `elevation` | P |
| `providers` | „Federal Office of Topography swisstopo“ (licensor, producer, host), wie die Collection; Rollen bestätigt Otto im PR | M |
| `gsd` | 0,5 und 2 (`summaries`) | M |
| `doi`, `citation` | keine DOI gefunden; Zitierangabe in der Umsetzung prüfen (Checkliste Punkt 3) | — |
| `data_class`, `format` | statisches Raster, COG | M |
| Ausdehnung | Bbox der Collection; Zeitraum 2019-01-01 bis Ende des jüngsten Stands | M |
| `capabilities` | `roi`, `band_math`, `interpolation`, `reprojection`, `normalization`, `ml_processing` an; `time_range` aus; `masking` aus; `value_masking` an (wie DEM, Auslegung A5); `quad_pol` aus; `single_coverage_product` nach F1 | `adr/0023` §8.3 |
| `license` | nach F4 | `adr/0023` §4.1, §7.2 |
| `legal_status`, `access.account` | `cleared` nach Ottos Einstufung, `none` | `adr/0024`, `adr/0027` |
| `access` | anonym HTTPS, `cors: true`, geprüft am Tag der Umsetzung | M |
| `source` | `fsdi-stac-v1`, Endpunkt `https://data.geo.admin.ch/api/stac/v1`, `ch.swisstopo.swissalti3d`; `asset_hosts` `data.geo.admin.ch`; `materialized`; `data_region` `aws:eu-central-1` (`adr/0023` §7.3, F7: Code-Vorgabe der FSDI); `asset_keys` nach F2; `item_states` nach F1 | M, P |
| `coverage` | `local-sql`; Breite einer Kachel 1 km; `max_geotile_level` 8 wie DEM, bis Otto anders entscheidet (Auslegung A6) | A |
| `default_render` | Asset nach F2; Colormap `terrain`, Bereich 0–5 000 m wie DEM (Auslegung A4) | A |
| `viewer` | `group_by` und `results_group_by` `[earthx:state]` (§4.4); `browse: full_resolution` wie DEM; `min_zoom` aus einer Messung der Kachelzeit in der Umsetzung (bei z12 läge eine Kachel über rund 100 Items) | A |
| `maturity` | `stable` (Standardprodukt, OGD seit 2021) | P |
| `mask` | keiner | — |
| `band_units` | COG-Assets `m` (LN02) | `adr/0023` §8.3 |
| `auxiliary_assets` | die beiden XYZ-ZIPs (nur Originale, nicht lesbar) | M |
| `search_filters`, `search_capabilities` | keine Filter (die Quelle kann `query` nicht, `adr/0023` §8.3); `evaluate: false`, `aoi_coverage: true` wie DEM | P |
| `index_presets`, `true_color` | leer; Gelände kommt mit M5-10 | `adr/0023` §8.3 |

### 4.6 Onboarding-Checkliste (`projektuebersicht.md` §5)

| Punkt | Wie |
|---|---|
| 1 Beschreibung | §4.5, deutsch und englisch in den Schlagworten |
| 2 Coverage | `LOCAL_SQL` aus den materialisierten Items; Test der Vollständigkeitsprobe mit synthetischen Kacheln |
| 3 DOI / Zitierung | in der Umsetzung prüfen; ohne DOI die Landing Page der Collection |
| 4 Lizenz | nach F4; Wortlaut bestätigt Otto im PR |
| 5 Format | COG (Medientyp und Kopf, `adr/0023` §9.1) |
| 6 Anonymer Zugriff | §2 [M] |
| 7 Klasse, Flags | §4.5 |
| 8 Darstellung | §4.5, `min_zoom` gemessen |
| 9 End-to-End | Operator-Lauf (Reprojektion von LV95) gegen ein synthetisches COG in EPSG:2056 |
| 10 Geprüft | Live-Smoke mit Marker `live_dataset("swissalti3d")` |

### 4.7 Tests

Alle ohne Netz, Fixtures synthetisch unter `backend/tests/fixtures/` (CLAUDE.md):

- **Bitgleichheit Earth Search (zuerst, eigener Commit vor dem Umbau):** Ein Golden-Test hält für eine Matrix aus Suchen (ohne Filter, Zeit offen und geschlossen, `bbox`, `intersects`, `ids`, Bedingungen, zweite Seite) und Item-Abrufen fest: Methode, URL und **Body als Bytes**, Cache-Schlüssel, gespeicherter Cache-Wert, Seitenmarke, zurückgegebene Items, Coverage-Anfrage. Erzeugt auf dem heutigen Code, als Fixture eingecheckt; nach dem Umbau unverändert grün. Alle bestehenden Tests unter `tests/earthx/adapters/` und `tests/integration/` bleiben unverändert grün.
- **FSDI-Dialekt:** Marke aus `cursor` mit `merge: true`; `next` ohne `cursor` → `UpstreamShapeError`; Antwort ohne Zähler → `matched` `None`; `ids`/`intersects` gehen hinaus; Bedingungen → `UnsupportedFilter` vor jeder Anfrage; der Body enthält nur bekannte Felder; `404` beim Item bleibt `404`.
- **Asset-Schlüssel:** Regel trifft → fester Schlüssel; Asset ohne Regel, doppelte Regel, fehlendes Asset → `unknown`; Startfehler bei doppeltem Schlüssel und bei `default_render`/`band_units`/`auxiliary_assets` mit fremdem Schlüssel.
- **Stände:** zwei und drei Stände je Kachel → Regel nach F1; ID ohne Treffer → `unknown`; gleiches Jahr zweimal → beide `unknown`; `tile_pattern` ohne Gruppe `tile` oder nicht kompilierbar → Startfehler; Geometrie der Stände verschieden → trotzdem eine Kachel.
- **Materialisierung:** mehrere Seiten; `304` → `unchanged` ohne Suche; über 1 % `unknown` → Abbruch ohne Schreiben; Asset auf fremdem Host → `unknown`; Bericht mit `withheld` = ersetzte Stände; der Befehl schreibt in einer Transaktion (bestehender Test erweitert).
- **Eintrag:** Laden aus YAML, Collection mit `earthx:source` (neue Felder), `check_adapter_specs` grün.
- **Live-Smoke** `tests_live/test_swissalti3d_smoke.py`: Collection `200` und `304`; eine Suchseite mit `cursor`; ein Item; Assets auf die Regeln aus `asset_keys`; Range-`GET` `206` auf ein COG über `gateway`. Läuft lokal bei Otto bzw. in der CI ohne Proxy, nicht aus der Cloud-Sitzung (M5-Plan §6.5).

### 4.8 Doku mit der Umsetzung

- `architekturplan.md` 5.1 (`earthx:source` mit `asset_keys`, `item_states`; `earthx:tile`, `earthx:state`) und 6.1 (ein Modul für STAC-APIs).
- `adr/0011`: Nachtrag zu F6 (umgesetzt mit M5-08).
- `adr/0023` §8.3 und §11 Punkt 2: Regel für Stände und Asset-Wahl entschieden, mit Verweis.
- `docs/cloud-umgebung.md`: `data.geo.admin.ch` in die Tabelle der Hosts, falls dort nicht schon geführt.
- Befehle für Ottos lokalen Lauf: `python -m earthx.discovery.materialize swissalti3d` und Live-Smoke, PowerShell 5.1.
- Log-Zeile(n).

---

## 5. Auslegungen

- **A1 — Zwei `AdapterKind` statt einer.** `earth-search-v1` bleibt, `fsdi-stac-v1` kommt dazu, beide aus `stac_api.py` (`adr/0011` §8.2: „ein Modul mit einem Dialekt je Quelle“). Der Dialekt ist Code, weil er gemessen wird wie `FilterSupport` (`adr/0011` F1). Ein Feld „Dialekt“ im YAML gibt es nicht; eine weitere FSDI-Collection (SWISSIMAGE, MeteoSchweiz) braucht nur einen YAML-Eintrag.
- **A2 — Keine Migration für den Bericht.** Ersetzte Stände stehen in `withheld` („vorhanden, aber nicht geladen“); die Bedeutung steht im Docstring und im Lauf-Bericht.
- **A3 — Ein Mosaik über alle Kacheln.** Die Gruppierung über `earthx:state` hält eine AOI über Kacheln verschiedener Jahre zusammen; das Befliegungsjahr je Kachel bleibt als `datetime` am Item sichtbar.
- **A4 — Darstellung wie der DEM** (`terrain`, 0–5 000 m), damit beide Höhenmodelle gleich aussehen. Den Bereich je Ansicht passt `/statistics` an.
- **A5 — `value_masking` an wie beim DEM.** Eine Maske nach Höhe („über 2 000 m“) ist sinnvoll, anders als `adr/0023` §8.3 vermutet; nach Ottos Wunsch abschaltbar.
- **A6 — Coverage z8 wie DEM und WorldCover**, bis Otto anders entscheidet (die Stufe ist seine Einstellung, `adr/0004` §5).
- **A7 — Genauigkeit der Lage 1 m** (§2) steht in der Beschreibung. Für 0,5-m-Daten ist das sichtbar; eine Gitterdatei (CHENyx06) bräuchte einen freigegebenen Download von PROJ und ist nicht Teil von M5-08.
  - **Zusatz Otto (07.11.2026):** Die Gitterdatei für LV95 kommt **nie** über das Netz von PROJ (`PROJ_NETWORK`, `cdn.proj.org`), weil das an `gateway` vorbeiginge (B8). Ob sie ins Image kommt, ist eine spätere, eigene Aufgabe.

---

## 6. Nicht Teil dieser Aufgabe

- Geländeoperator, Capability `terrain`, Schummerung im `tiler` (M5-10).
- Auswahl älterer Stände in der Oberfläche, falls F1 = 1 (später, mit eigenem Plan).
- Differenz zweier Stände (`adr/0030` §5.4, P3).
- Abbildung `s3://`, `crc64nvme`, `notices` (DS-04b), BEV und ATOM (M5-09).
- Neue Abhängigkeiten: keine.

---

## 7. Risiken

- **R1 — `ETag` der Collection als Fassung.** Ob er sich ändert, wenn nur Items dazukommen, ist nicht gemessen. Gegenmittel: Fassung aus `ETag` **und** `updated` der Collection; `--force` lädt immer neu. Prüfpunkt im Live-Smoke: `updated` der Collection gegen das jüngste `updated` einer Suchseite.
- **R2 — Laufzeit und Last.** Rund 1 000 Seiten und 280 MB für einen vollen Lauf; nur lokal bei Otto, mit Abstand je Host.
- **R3 — Viele Items je Kartenkachel.** Bei kleinem Maßstab lägen Hunderte COGs unter einer Kachel; `viewer.min_zoom` aus der Messung begrenzt das, darunter zeigt die Karte die Coverage.
- **R4 — Bitgleichheit.** Ein Umbau kann die Reihenfolge der Schlüssel im JSON-Body ändern, ohne dass ein Test auf Felder es merkt. Deshalb vergleicht der Golden-Test Bytes (§4.7).

---

## 8. Fragen an Otto — beantwortet am 07.11.2026 (§8a)

**F1 — Mehrere Stände je Kachel?** Jede Kachel hat einen Stand 2019 und einen bis zwei neuere (§2).
1. **Je Kachel nur der jüngste Stand wird geladen**; ältere Stände bleiben bei der Quelle. `time_range` aus, `single_coverage_product` an, ein Mosaik über alle Kacheln; das Befliegungsjahr steht am Item. Ältere Stände lassen sich später über dieselbe Regel nachrüsten **(Empfehlung)**
2. Alle Stände laden; Vorgabe ist der jüngste je Kachel, ältere über „Stand am …“ (je Kachel der jüngste Stand bis zu diesem Datum) wählbar. Braucht eine Suche mit Regel in pgstac und ein Feld im Panel; eigener PR, über 400 Zeilen
3. Jedes Befliegungsjahr ein Schritt der Zeitleiste (`time_range` an): 2019 flächendeckend, spätere Jahre als Flickenteppich

**F2 — Welche Assets (0,5 m / 2 m)?**
1. **Beide COGs mit festen Schlüsseln** (`dtm` 0,5 m, `dtm_2m`); Darstellung und Vorgabe im Processing 0,5 m, 2 m wählbar wie ein Band (für große AOIs, `adr/0030` §5.4); die XYZ-ZIPs nur als Originale **(Empfehlung)**
2. Nur 0,5 m
3. Nur 2 m (16-mal weniger Pixel); 0,5 m nur als Original

**F3 — Schnitt?** Richtwert 400 Zeilen.
1. **Drei PRs:** M5-08a (dieser Draft-PR) Plan, Golden-Test und `stac_api.py` mit Earth Search bitgleich; M5-08b FSDI-Dialekt, Materialisierung, `asset_keys`, `item_states`; M5-08c YAML-Eintrag, Live-Smoke, Doku. DS-04 kann nach M5-08a weiter **(Empfehlung)**
2. Zwei PRs: Adapter (08a und 08b zusammen, rund 600 Zeilen), dann Eintrag
3. Ein PR für alles

**F4 — Lizenz und Quellenangabe (B11, immer Otto)?** Vorschlag aus `adr/0023` §7.2: swisstopo-OGD, `spdx_id` leer, alle Flags an, Quellenangabe Pflicht, Stufe Processing; Bedingungen „Terms of use for free geodata and geoservices from swisstopo“.
1. **Unverändert „© swisstopo“, verändert „Derived from © swisstopo“** (Wortlaut der Seite zur Quellenangabe, §2) **(Empfehlung)**
2. Unverändert „© swisstopo“, verändert „© swisstopo (modified)“ (Form aus `adr/0023` §7.2)
3. Name des Amtes: „Federal Office of Topography swisstopo“ bzw. „Derived from data of the Federal Office of Topography swisstopo“

Den Text `terms.notice.en` (Haftung, Drosselung bei übermäßiger Nutzung) lege ich mit der Umsetzung aus dem Primärtext vor; den Wortlaut bestätigt Otto im PR vor dem Merge (`adr/0023` F2).

Die Auslegungen A1–A7 (§5) gelten, wenn Otto nicht widerspricht.

## 8a. Antworten Otto (07.11.2026)

F1–F3 jeweils Option 1, F4 = 2; Auslegungen A1–A7 angenommen, zu A7 mit Zusatz (§5).

- **F1:** Je Kachel nur der jüngste Stand; `time_range` aus, `single_coverage_product` an, ein Mosaik über alle Kacheln.
- **F2:** Beide COGs mit festen Schlüsseln (`dtm` 0,5 m, `dtm_2m`), Vorgabe 0,5 m; XYZ-ZIPs nur als Originale.
- **F3:** Drei PRs. M5-08a (dieser Draft-PR): Vergleichstest und `stac_api.py`, Earth Search bitgleich. M5-08b: FSDI-Dialekt, Materialisierung, `asset_keys`, `item_states`. M5-08c: YAML-Eintrag, Live-Smoke, Doku.
- **F4:** Unverändert „© swisstopo“, verändert „© swisstopo (modified)“, einheitlich mit `adr/0023` §7.2 und WorldCover. Vorher die Seite zur Quellenangabe lesen und den geforderten Wortlaut in die PR-Beschreibung schreiben; Otto bestätigt ihn vor dem Merge.
  - **Gelesen am 07.11.2026 [P]:** Die „Terms of use for free geodata and geoservices (OGD) from swisstopo“ (Version 1.3.2021) verlangen bei jeder Darstellung, Veröffentlichung und Weitergabe eine der Angaben „Bundesamt für Landestopografie swisstopo“ (bzw. französisch, italienisch, rätoromanisch, englisch „Federal Office of Topography swisstopo“) oder **„©swisstopo“ (ohne Leerzeichen)**. Für swissALTI Regio und swissEO gilt eine andere Angabe, swissALTI3D gehört nicht dazu.
  - Die Seite „How to indicate the source“ regelt den Ort: in dynamischen Karten ideal neben den Daten, zulässig eine zentrale Seite der Quellen mit Link; bei Daten ohne Darstellung in der begleitenden Dokumentation. Bei abgeleiteten Daten gelten dieselben Regeln, der Angabe darf „derived from …“ (deutsch „abgeleitet von …“) vorangestellt werden.
  - Folge für den Eintrag (M5-08c): Schreibweise „©swisstopo“ wie in den Bedingungen; „(modified)“ ist ein Zusatz hinter der geforderten Angabe, den die Seite nicht nennt, aber auch nicht ausschließt. Otto bestätigt Schreibweise und Zusatz im PR.

---

## 9. Begriffe für das Glossar (`adr/0026` F7)

Geländemodell ↔ digital terrain model (DTM); Höhenmodell ↔ elevation model; Befliegung ↔ aerial survey; Stand ↔ edition; Landesvermessung ↔ national survey; LV95 ↔ Swiss coordinate system LV95 (EPSG:2056).

---

## 10. Grenzen

- Modulgrenzen laut `architekturplan.md` 3.1 (Import-Linter); ausgehende Requests nur über `gateway`; Worker-Kern zustandslos; `decomp.py` unberührt (`quad_pol` aus).
- Kein Code je Datensatz: Asset-Schlüssel und Stände sind Registry-Angaben; der Dialekt ist eine Eigenschaft der Quelle.
- Keine AOI, Item-IDs, Hashes, `href` oder Prüfsummen in Logs, URLs, Issues oder PRs.
- Fixtures nur synthetisch.
- `CLAUDE.md`, `.github/`, `.claude/` und `CODEOWNERS` bleiben unverändert.
- Vor „fertig“: `main` geholt, Lint, Typprüfung, Tests und Importregeln grün.

---

## 11. Umsetzung Teil 1 (M5-08a, 07.11.2026)

- **Vergleichstest zuerst** (eigener Commit vor dem Umbau): `tests/earthx/adapters/test_earth_search_golden.py` mit `tests/fixtures/earth_search/golden_requests.json`. Elf Fälle: Suche mit Folgeseite und Cache-Treffer, `bbox` und geschlossenes Zeitfenster, offenes Ende, `intersects`, `ids` ohne Zähler, Bedingungen, alles zusammen, Item mit Cache-Treffer, Item mit Band-Assets, Coverage ohne und mit Fläche, Zeit und Bedingungen. Verglichen werden Methode, URL, Kopfzeilen, Body als Text, jeder Cache-Schreibvorgang (Schlüssel, Wert, Lebensdauer) und die Antwort (Items, Zähler, Seitenmarke, Cache-Herkunft). Der Test geht nur über die Dispatch-Funktionen aus `earthx.adapters`; Testdatei und Fixture sind nach dem Umbau unverändert.
- **Umbau:** `adapters/earth_search.py` heißt jetzt `adapters/stac_api.py` (`git mv`). `StacDialect` (`kind`, `marker_field`, `filters`, `write_conditions`, `normalize_item`) mit der Prüfung, dass Bedingungen genau dann geschrieben werden, wenn die Quelle `query` kann. `DIALECTS` mit dem einen Eintrag `EARTH_SEARCH`; `dialect_of` ersetzt `federated_search.require_adapter`, das sonst niemand nutzte.
- **`FilterSupport`** liegt jetzt in `federated_search`; `spec.py` liest die Filter von Earth Search aus dem Dialekt, ein Test hält das für jeden Dialekt fest.
- **`earth_search_coverage.py`** nimmt `query_extension` aus `stac_api` und die übrigen Bausteine direkt aus `federated_search`; sonst unverändert.
- **Abweichung vom Plan:** keine. `AdapterKind.FSDI_STAC_V1` und der FSDI-Dialekt kommen wie geplant erst mit M5-08b.
- **Für DS-04:** Der Adapter heißt `earth-search-v1` wie bisher, das YAML von Sentinel-2 ist unverändert. Eine Übersetzung je Eintrag (`asset_href_rewrites`) gehört in `stac_api` hinter `dialect.normalize_item`; dieselbe Stelle nutzt M5-08b für `asset_keys`.
- **Doku:** `architekturplan.md` 6.1 (Dialekt), `adr/0011` §11b.
- **Prüfung:** `ruff check backend` grün; `lint-imports` 16 Verträge eingehalten; `pytest` 9578 bestanden, 25 übersprungen (PowerShell fehlt in der Sitzung).
