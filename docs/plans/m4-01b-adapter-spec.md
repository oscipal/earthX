# M4-01b — `AdapterSpec`, Signaturen, Fehlerklassen, `harvest_run` entfernen: Plan

**Aufgabe:** M4-01b aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 06.10.2026 freigegeben** mit F1–F6 je Option 1,
mit einer Auflage zum Registry-Test (§7, Antworten), und **umgesetzt** (§8).
**Ort im Repo:** `docs/plans/m4-01b-adapter-spec.md`
**Grundlagen:** `adr/0011` §3.2 (B4, B6–B10), §5.1–§5.3, §6.5 Punkt 3, §11
(F1, F3, F5, F6, F7); `plans/m4-processing-kern.md` §1.1 (Q1), §1.2, M4-01b;
`plans/m4-01a-zugriffsaufloesung.md` §8 (Abweichung 3: Registry für
`/coverage`); `architekturplan.md` 3.1, 6.1; `KLAERUNGEN.md` B6, B10;
`ENTSCHEIDUNGSLOG.md` „`adr/0011` angenommen“ (30.09.2026) und „M4-01a
freigegeben“ (02.10.2026); Code in `backend/earthx/adapters/`,
`api/federating_client.py`, `api/item_source.py`, `api/coverage_route.py`,
`api/main.py`, `api/tiler.py`, `discovery/materialize.py`,
`catalog/registry.py`, `catalog/collection.py`, `catalog/datasets.py`.

---

## 1. Ergebnis in drei Sätzen

Jede Quelle meldet ihre Fähigkeiten an genau einer Stelle, einem
unveränderlichen `AdapterSpec` in `adapters/spec.py`. Was dort `None` ist, weisen
die Dispatcher mit einer festen Fehlerklasse ab, bevor eine Anfrage hinausgeht;
ob Registry und Tabelle zusammenpassen, prüft der App-Bau. Adapter und
Dispatcher nehmen die `DatasetConfig` statt `dataset_id` mit
`registry=REGISTRY`, die Fehlerklassen liegen in `adapters/errors.py`,
`SourceInfo.harvest_run` ist weg, und `/coverage` liest dieselbe Registry wie
der Rest der App.

---

## 2. Stand vor dieser Aufgabe (gelesen, 06.10.2026, `main` nach PR #121)

- **Ausgangslage grün:** `pytest` aus der Repo-Wurzel 1918 bestanden (mit
  Postgres der Session, also samt T-C), `ruff check backend` sauber,
  `lint-imports` 12 Verträge gehalten.
- **Dispatch** (`adapters/__init__.py`): drei private Tabellen mit Modulen bzw.
  Funktionen: `_ADAPTERS` (Suche, Einzelabruf), `_MATERIALIZERS`, `_COVERAGE`
  mit dem Schlüssel `(AdapterKind, CoverageProvider)`. `_adapter_for` sucht den
  Eintrag (Regel I → `UnknownCollection`), weist materialisierte Datensätze ab
  und wählt das Modul. Filter-Fähigkeiten sind die Modulkonstanten
  `SUPPORTS_INTERSECTS`/`SUPPORTS_IDS`, gelesen per `getattr` mit Vorgabe
  `False` (adr/0011 B7).
- **Signaturen mit Vorgabe-Registry** (adr/0011 B8): `search_items` und
  `get_item` im Dispatcher, in `earth_search.py` und `eopf_stac.py`;
  `coverage` im Dispatcher; `aggregate_coverage` und `sample_coverage` mit
  `config: DatasetConfig | None = None` und `registry=REGISTRY`. Jedes der zwei
  STAC-Module hat ein eigenes `resolve_dataset` (Regel I plus Prüfung der
  eigenen `AdapterKind`). `materialize_items` nimmt schon heute die
  `DatasetConfig`.
- **DEM-Zeitkonstanten:** `cop_dem_bucket.py:44` importiert
  `DEM_ACQUISITION_START/END` aus `catalog.datasets`; derselbe Wert steht im
  Eintrag als `temporal_extent` (`datasets.py:459`).
- **Fehlerklassen** (adr/0011 B9): `InvalidQuery`, `UnknownCollection`,
  `UnsupportedSource`, `UnsupportedFilter`, `UpstreamShapeError` in
  `federated_search.py`; `NotMaterialized(UnsupportedSource)` in
  `cop_dem_bucket.py`. `cop_dem_bucket` holt die Klassen aus
  `federated_search`, obwohl es nicht föderiert. `nominatim.py` hat eigene
  `InvalidQuery`/`UpstreamShapeError` mit denselben Namen.
- **Aufrufer:** `api/federating_client.py` (Suche; ruft `adapter_search_items`
  **ohne** `registry=`, also mit `REGISTRY`, obwohl die App seit M4-01a eine
  eigene Registry trägt), `api/item_source.py` (Einzelabruf, mit `registry=`),
  `api/coverage_route.py` (Coverage), `discovery/materialize.py`
  (Materialisierung), `api/tiler.py` und `api/mixed_search.py` (nur
  Fehlerklassen).
- **`/coverage`:** `coverage_route.router` ist auf Modulebene mit
  `build_router(REGISTRY)` gebaut; `api/main.py` hängt ihn ein. Eine App mit
  eigener Registry beantwortet `/coverage` also aus `REGISTRY` (M4-01a §8,
  Abweichung 3).
- **`harvest_run`:** Feld `SourceInfo.harvest_run` (`registry.py:268`), bei
  allen drei Einträgen `None`; Prüfung in `_check_item_holding`
  (`registry.py:781`); im Collection-Dokument als
  `earthx:source.harvest_run` (`collection.py:188`); dazu 7 T-C-Dateien und 4
  Katalog-Testdateien, die das Feld setzen oder prüfen. Das Frontend liest es
  nicht. `architekturplan.md` 5.1 nennt es nicht; §11 (Z. 611) nennt eine
  geplante **Tabelle** `harvest_run` des Harvesters, das ist etwas anderes und
  bleibt.

---

## 3. Umsetzung

### 3.1 `adapters/errors.py`

- Neu, mit den Klassen unverändert (Name, Basisklasse, Docstring):
  `InvalidQuery(ValueError)`, `UnknownCollection(LookupError)`,
  `UnsupportedSource(LookupError)`, `UnsupportedFilter(LookupError)`,
  `UpstreamShapeError(RuntimeError)`, `NotMaterialized(UnsupportedSource)`.
- `federated_search.py` und `cop_dem_bucket.py` definieren sie nicht mehr.
  Keine Re-Exporte am alten Ort (B6, wie M4-01a F1); Aufrufer importieren aus
  `earthx.adapters` oder `earthx.adapters.errors`. `earthx.adapters`
  exportiert die Klassen weiter wie heute.
- `nominatim.py` behält seine eigenen Klassen (F3).

### 3.2 Signaturen mit `DatasetConfig`

```python
# adapters/__init__.py
def dataset_config(registry: DatasetRegistry, dataset_id: str) -> DatasetConfig: ...   # Regel I, einzige Stelle

async def search_items(config, params=None, *, adapters, gateway, cache=None) -> ItemPage: ...
async def get_item(config, item_id, *, adapters, gateway, cache=None) -> dict[str, Any]: ...
async def materialize_items(config, *, adapters, gateway, known_version) -> MaterializeOutcome: ...
async def coverage(query, config, *, adapters, gateway, cache=None) -> CoverageResult: ...
```

- **Regel I an einer Stelle:** `dataset_config` schlägt den Eintrag nach und
  wirft `UnknownCollection`. Der Aufrufer in `api` ruft sie einmal je Anfrage
  und reicht den Eintrag weiter; `item_source.item_holding_of` nutzt sie
  ebenfalls. Die zwei `resolve_dataset` in `earth_search.py` und
  `eopf_stac.py` entfallen (F2).
- **Adapter-Module:** `search_items(config, params, *, gateway, cache)` und
  `get_item(config, item_id, *, gateway, cache)` in `earth_search.py` und
  `eopf_stac.py`; `aggregate_coverage(query, config, *, gateway, cache)` und
  `sample_coverage(query, config, *, gateway, cache)` mit Pflicht-`config`.
  Keine Vorgabe `REGISTRY` mehr; danach importiert kein Modul in `adapters`
  `catalog.datasets` (Test, §3.6). Jedes STAC-Modul prüft weiter, dass der
  Eintrag seine `AdapterKind` trägt (`UnsupportedSource`), damit ein direkter
  Aufruf mit falschem Eintrag nicht still eine fremde Quelle anfragt; die
  Prüfung ist eine gemeinsame Hilfsfunktion in `federated_search.py`.
- **Coverage-Funktionen** prüfen weiter `config.dataset_id == query.dataset_id`
  und den Provider (`CoverageProviderMismatch`); sie passen danach ohne
  `functools.partial` für `registry` auf `catalog.coverage.CoverageSource`.
- **DEM:** `cop_dem_bucket._item` nimmt `start_datetime`/`end_datetime` aus
  `config.temporal_extent`. Fehlt dort das Ende, weist `materialize_items` den
  Eintrag vor der ersten Anfrage mit `UnsupportedSource` ab (ein DEM-Item
  braucht beide Zeitpunkte). `DEM_ACQUISITION_START/END` bleiben in
  `catalog/datasets.py`, weil der Eintrag sie nutzt.
- **Aufrufer:** `federating_client` holt den Eintrag aus der Registry der App
  (`_registry_of(request)`), auch für die Suche. Das ändert im Betrieb nichts
  (dort ist es `REGISTRY`), schließt aber die zweite Registry je App.
  `item_source.build_item_source`, `coverage_route` und
  `discovery/materialize.py` reichen ihren Eintrag weiter.

### 3.3 `adapters/spec.py`

```python
class SearchItems(Protocol):
    async def __call__(self, config: DatasetConfig, params: SearchParams | None, *,
                       gateway: Gateway, cache: SearchCache | None) -> ItemPage: ...
class FetchItem(Protocol):
    async def __call__(self, config: DatasetConfig, item_id: str, *,
                       gateway: Gateway, cache: SearchCache | None) -> dict[str, Any]: ...
class MaterializeItems(Protocol):
    async def __call__(self, config: DatasetConfig, *, gateway: Gateway,
                       known_version: str | None) -> MaterializeOutcome: ...
class AnswerCoverage(Protocol):
    async def __call__(self, query: CoverageQuery, config: DatasetConfig, *,
                       gateway: Gateway, cache: SearchCache | None) -> CoverageResult: ...

@dataclass(frozen=True, slots=True)
class FilterSupport:
    intersects: bool
    ids: bool
    cql2: bool

@dataclass(frozen=True, slots=True)
class AdapterSpec:
    kind: AdapterKind
    search: SearchItems | None
    fetch: FetchItem | None
    materialize: MaterializeItems | None
    coverage: Mapping[CoverageProvider, AnswerCoverage]
    filters: FilterSupport | None

AdapterSpecs = Mapping[AdapterKind, AdapterSpec]
ADAPTER_SPECS: AdapterSpecs   # die drei echten Einträge, unveränderlich (MappingProxyType)
```

- **Kein Feld mit Vorgabewert** (B10). `__post_init__` prüft: `search` und
  `fetch` nur gemeinsam; `filters` genau dann gesetzt, wenn `search` gesetzt
  ist; `coverage` enthält nie `local-sql` (das beantwortet `catalog`, adr/0011
  B4); `coverage` wird als `MappingProxyType` eingefroren.
- **Die drei Einträge**, aus dem heutigen Code und den Messungen in adr/0011
  §3.1:

  | `kind` | `search`/`fetch` | `materialize` | `coverage` | `filters` (intersects, ids, cql2) |
  |---|---|---|---|---|
  | `earth-search-v1` | `earth_search` | — | `upstream-aggregation` → `aggregate_coverage` | ja, ja, nein |
  | `eopf-stac-v1` | `eopf_stac` | — | `sample` → `sample_coverage` | ja, ja, ja |
  | `cop-dem-bucket` | — | `cop_dem_bucket` | — | — |

  `cql2` liest in diesem PR niemand (F4). `SUPPORTS_INTERSECTS`/`SUPPORTS_IDS`
  in den Modulen entfallen.
- **Tabelle:** `ADAPTER_SPECS` baut ein Mapping mit Schlüssel `spec.kind`; ein
  doppeltes `kind` ist ein Fehler beim Import. `nominatim` steht nicht darin
  (keine Datensätze, adr/0011 §5.2).
- **Dispatcher** (`adapters/__init__.py`) nehmen die Tabelle als
  Schlüsselwort `adapters` **ohne Vorgabe** (adr/0011 §5.2). Ablauf je
  Fähigkeit: Eintrag der `AdapterKind` suchen (fehlt → `UnsupportedSource`),
  Haltung prüfen (Suche/Einzelabruf nur `federated`, Materialisierung nur
  `materialized` → sonst `UnsupportedSource` bzw. `NotMaterialized` wie heute),
  Fähigkeit `None` → `UnsupportedSource` mit dem Namen der Fähigkeit,
  Filter gegen `spec.filters` (`UnsupportedFilter` wie heute), dann Aufruf.
  Für Coverage: Provider nicht in `spec.coverage` →
  `CoverageProviderMismatch` wie heute. In jedem Abweisungsfall geht keine
  Anfrage hinaus.
- **Abgleich mit der Registry**, `check_adapter_specs(registry, adapters)`:
  wirft `AdapterSpecMismatch` (neu, in `errors.py`, `RuntimeError`) mit den
  betroffenen Dataset-IDs, wenn ein Eintrag etwas braucht, das die App beim
  Adapter abfragt, und die Tabelle es nicht hat: seine `AdapterKind` fehlt in
  der Tabelle; `federated` ohne `search`; sein `coverage.provider` fehlt in
  `spec.coverage`, außer bei `local-sql` und bei `single_coverage_product`
  (dort fragt die Route keinen Adapter: `coverage_route._area_path` bzw. der
  Ausdehnungsweg). Aufgerufen in `build_app` von `api` und `tiler` (synchron,
  ohne Datenbank: der App-Bau scheitert) (F1).
- **„`materialized` braucht `materialize`“ prüft nicht der App-Bau**, sondern
  der Abnahme-Test über `REGISTRY` (§3.6) und, wie heute, der Dispatcher im
  Lauf von `discovery` (`UnsupportedSource`, bevor eine Anfrage hinausgeht).
  Grund: Fünf T-C-Dateien bauen Apps mit einem materialisierten Eintrag, der
  `earth-search-v1` trägt (`replace(SENTINEL_2_L2A, …)`); die App fragt für
  ihn keinen Adapter, und eine föderierte Quelle, die doch materialisiert
  wird, ist in adr/0011 §5.1 (S3, Pro) ausdrücklich vorgesehen.
- **Herkunft der Tabelle in `api`:** `build_app(registry=REGISTRY, *,
  adapters=ADAPTER_SPECS)` in `api/main.py` und `api/tiler.py` legt sie neben
  die Registry auf `app.state.earthx_adapters`; `federating_client`,
  `build_item_source` und `coverage_route.build_router` bekommen sie von dort
  bzw. als Parameter (F1).

### 3.4 `/coverage` mit der Registry der App

- `coverage_route.build_router(registry, adapters)` ohne Vorgaben; das
  Modul-Objekt `router` entfällt. `api/main.build_app` baut den Router mit
  seiner eigenen Registry und Tabelle.
- Test: Eine App aus `build_app(eigene Registry)` beantwortet `/coverage` für
  einen Eintrag, der nur in dieser Registry steht, und antwortet `404` für
  einen Eintrag, der nur in `REGISTRY` steht. Das belegt „eine Registry je
  App“ für Routing, Suche, Einzelabruf und Coverage.

### 3.5 `harvest_run` entfernen

- `SourceInfo.harvest_run` und die Prüfung in `_check_item_holding` entfallen;
  der Docstring dort nennt nur noch den Provider.
- `catalog/collection.py`: `earthx:source` ohne `harvest_run`. Nach dem
  nächsten `catalog.load` fehlt der Schlüssel im gespeicherten Dokument und
  damit in `/stac/collections`; heute steht dort immer `null`. Das Frontend
  liest ihn nicht.
- `catalog/datasets.py` und alle Tests, die das Feld setzen oder prüfen: Zeile
  entfernt; die zwei Registry-Tests zu `harvest_run` entfallen, weil ihr
  Gegenstand entfällt. Ein Test belegt, dass `SourceInfo` kein solches Feld
  mehr annimmt und das Collection-Dokument keinen Schlüssel `harvest_run`
  trägt.
- Abnahme „`harvest_run` kommt im Code nicht mehr vor“: `grep -rn harvest_run
  backend frontend/src` leer, außer in dem einen Test, der die Abwesenheit
  prüft.
- `architekturplan.md`: 5.1 nennt das Feld nicht, nichts zu ändern; die
  Tabelle `harvest_run` in §11 bleibt (Harvester, M5).

### 3.6 Tests

- **Neu, `tests/earthx/adapters/test_spec.py`:**
  - `AdapterSpec` weist ab: `search` ohne `fetch` und umgekehrt, `filters`
    ohne `search`, `search` ohne `filters`, `local-sql` in `coverage`;
    doppeltes `kind` in einer Tabelle.
  - **Abnahme-Test über jeden Registry-Eintrag:** Für jeden Eintrag von
    `REGISTRY` und jede Fähigkeit (Suche, Einzelabruf, Materialisierung,
    Coverage, Filter `intersects`/`ids`) gilt entweder „der Spec deckt sie“
    oder „der Dispatcher weist sie mit der definierten Klasse ab, ohne eine
    Anfrage“. Geprüft mit einem Gateway, das jede Anfrage aufzeichnet und
    sonst scheitern lässt.
  - Über `REGISTRY` zusätzlich: jeder materialisierte Eintrag hat in seinem
    Spec `materialize`.
  - `check_adapter_specs` mit der echten Registry und Tabelle grün; mit
    synthetischen Tabellen für jeden der drei Abweichungsfälle
    `AdapterSpecMismatch`, die Meldung nennt die Dataset-ID; ein
    materialisierter Eintrag mit `earth-search-v1` und `local-sql` besteht.
  - `build_app` von `api` und `tiler` scheitert mit einer Tabelle, der eine
    `AdapterKind` der Registry fehlt.
  - AST-Test: kein Modul in `earthx/adapters/` importiert
    `earthx.catalog.datasets`.
- **Umgebaut:** `test_dispatch.py` ersetzt `monkeypatch.setitem(_ADAPTERS, …)`
  durch eigene Tabellen mit synthetischen Einträgen, die hereingereicht werden
  (adr/0011 B7); `test_every_known_adapter_supports_both_filters` liest
  `ADAPTER_SPECS[…].filters`. Die Adapter-Tests rufen mit `config` statt
  `dataset_id`/`registry`; ihre Assertions bleiben. Die Tests zu
  `resolve_dataset` werden zu Tests von `dataset_config` bzw. der
  `AdapterKind`-Prüfung im Modul.
- **DEM:** `start_datetime`/`end_datetime` kommen aus dem übergebenen Eintrag
  (Test mit abweichendem `temporal_extent`); ein Eintrag ohne Ende wird ohne
  Anfrage abgewiesen.
- **Bestehend:** alle Routen-Tests (`/stac`, Kachel, Download, `/coverage`,
  Ortssuche) inhaltlich unverändert grün; geändert werden nur Importzeilen,
  Aufrufe der umgebauten Signaturen und `build_router(...)`-Aufrufe.
- Onboarding-Checkliste grün; `lint-imports` grün mit unverändertem
  `.importlinter`.

### 3.7 Doku und Log

- Modul-Docstrings in `adapters/__init__.py`, `federated_search.py`,
  `earth_search.py`, `eopf_stac.py`, `cop_dem_bucket.py` und der Kommentar an
  `AdapterKind.COP_DEM_BUCKET` in `registry.py` (nennt `_ADAPTERS`) nachziehen.
- `architekturplan.md` 6.1, Absatz „Form“: „Der Umbau ist M4-01b“ wird zu
  „umgesetzt mit M4-01b“; die Tabelle bleibt.
- `ENTSCHEIDUNGSLOG.md`: je eine Zeile für die Freigabe dieses Plans mit den
  Antworten und für die Umsetzung, ans Ende.
- `m4-processing-kern.md` §3: Stand M4-01b.

---

## 4. Nicht in dieser Aufgabe

- Gemeinsames Modul für STAC-APIs (adr/0011 F6, M5).
- Discovery als Fähigkeit im `AdapterSpec` (M5, adr/0011 §8.2).
- Der Vertragstest des Item-Vertrags (adr/0011 §5.3, STAC 1.0 und
  `https`-hrefs je Eintrag der Tabelle): steht nicht im Umfang von M4-01b;
  Vorschlag als eigene Stufe-A-Aufgabe (F5).
- `access/resolve.py` (M4-01a), `.importlinter`, Registry-Felder außer
  `harvest_run`, das Verhalten der Routen.
- Fehlerklassen von `nominatim` (F3).

---

## 5. Umfang und Commits

Geschätzt rund 250 Zeilen Produktivcode geändert (davon etwa 80 nur
verschoben: Fehlerklassen, Dispatch), rund 150 Zeilen neue Tests und rund 200
Zeilen geänderte Testaufrufe (Signaturen, `harvest_run=None` in 11 Dateien).
Damit liegt der PR über dem Richtwert von 400 Zeilen (F6). Geplante Commits,
je eine Sache:

1. `adapters/errors.py`: Fehlerklassen umziehen, Importe nachziehen.
2. Signaturen mit `DatasetConfig`, `dataset_config` als einzige Stelle für
   Regel I, DEM-Zeit aus `temporal_extent`; Aufrufer und Tests.
3. `adapters/spec.py` mit `AdapterSpec`, `ADAPTER_SPECS`, Dispatch über die
   Tabelle, `check_adapter_specs`; `build_app` in `api` und `tiler`; Tests.
4. `/coverage` mit Registry und Tabelle der App; Test.
5. `harvest_run` entfernen.
6. Doku, Log, Stand im M4-Plan.

---

## 6. Risiken

| Risiko | Umgang |
|---|---|
| Der App-Bau scheitert in Tests, deren Registry eine `AdapterKind` oder einen Provider ohne Spec-Zeile trägt | geprüft: alle Test-Registries mit `build_app` nutzen die drei echten Kinds; ihre materialisierten Einträge mit `earth-search-v1` tragen `local-sql` und brauchen deshalb keine Spec-Zeile für den App-Bau (§3.3). Die Einträge mit unpassendem Provider (`test_coverage_route.py`, Z. 240) bauen nur den Router, nicht die App. Fällt doch einer, reicht der Test eine passende Tabelle herein, statt die Prüfung zu umgehen |
| Die Suche in `api` nutzt nach dem Umbau die Registry der App statt `REGISTRY` und ändert so das Verhalten eines T-C-Tests | die T-C-Tests bauen die App mit `(*REGISTRY, …)`; föderierte Einträge sind dieselben. Gegenprobe im PR |
| Ein Aufrufer fängt eine Fehlerklasse über den alten Modulpfad | ohne Re-Exporte scheitert der Import sofort beim Laden, nicht still; `ruff` und `pytest` decken alle Importstellen |
| Das gespeicherte Collection-Dokument verliert `earthx:source.harvest_run` | nur `null` fällt weg; kein Leser im Frontend und im Backend (grep §2) |
| PR über dem Richtwert | Commits nach §5 einzeln lesbar; F6 |

---

## 7. Fragen an Otto

**F1: Woher die Dispatcher ihre Tabelle bekommen, und wo der Abgleich läuft**
1. Dispatcher nehmen `adapters=` ohne Vorgabe (adr/0011 §5.2).
   `build_app(registry, *, adapters=ADAPTER_SPECS)` in `api` und `tiler` legt
   die Tabelle neben die Registry auf `app.state`; `check_adapter_specs` läuft
   in beiden `build_app` und prüft, was die App beim Adapter abfragt (§3.3);
   ein Fehler bricht den Bau ab. `discovery` reicht `ADAPTER_SPECS` herein
   **(Empfehlung)**
2. wie 1, aber die Aufrufer in `api` reichen immer `ADAPTER_SPECS` herein
   (kein Parameter an `build_app`); Abgleich nur im Test über die echte
   Registry
3. Dispatcher lesen `ADAPTER_SPECS` als Vorgabe; nur Tests reichen eine eigene
   Tabelle herein

**F2: Regel I nach dem Umbau** (M4-Plan: „prüft der Dispatcher einmal“;
adr/0011 §5.2: „prüft der Aufrufer, der den Eintrag sucht“)
1. Eine Funktion `adapters.dataset_config(registry, dataset_id)` ist die
   einzige Stelle für Regel I; der Aufrufer in `api` ruft sie einmal je
   Anfrage, die Dispatcher nehmen danach den Eintrag. Die zwei
   `resolve_dataset` entfallen; die STAC-Module prüfen nur noch ihre
   `AdapterKind` **(Empfehlung)**
2. Dispatcher nehmen weiter `dataset_id` und `registry` (ohne Vorgabe) und
   suchen den Eintrag selbst; nur die Adapter-Module nehmen `config`

**F3: Fehlerklassen von `nominatim`** (gleiche Namen `InvalidQuery`,
`UpstreamShapeError`, adr/0011 B9)
1. bleiben eigene Klassen in `nominatim.py`; Ortssuche ist keine
   Datensatz-Quelle und steht nicht in der Tabelle **(Empfehlung)**
2. werden Unterklassen der gemeinsamen Klassen aus `errors.py`

**F4: `FilterSupport.cql2`**
1. aufnehmen wie in adr/0011 §5.2 skizziert, mit den gemessenen Werten
   (Earth Search nein, EOPF ja, adr/0011 §3.1); in diesem PR liest es niemand
   **(Empfehlung)**
2. weglassen, bis ein Leser kommt (`filter`-Extension, M5)

**F5: Vertragstest des Item-Vertrags** (adr/0011 §5.3)
1. nicht in M4-01b; als eigene Stufe-A-Aufgabe nach M4-01b vormerken
   **(Empfehlung)**
2. in diesem PR mitnehmen (rund 80 Zeilen Test mehr)

**F6: PR-Größe** (rund 600 Zeilen mit Tests und Testaufrufen)
1. ein PR wie im M4-Plan, mit getrennten Commits nach §5 **(Empfehlung)**
2. zwei PRs: erst §3.1, §3.2 und §3.5 (Fehlerklassen, Signaturen,
   `harvest_run`), dann §3.3 und §3.4 (`AdapterSpec`, `/coverage`)

**Antworten (Otto, 06.10.2026):** F1–F6 je Option 1.

- **Einschränkung beim App-Bau angenommen, mit Auflage:** Der Test über die
  echte `REGISTRY` prüft jeden Eintrag vollständig gegen `adr/0011` §5: jede
  Fähigkeit aus dem Eintrag ist durch den `AdapterSpec` gedeckt oder wird
  ausdrücklich abgewiesen; materialisiert braucht Materialisierung; föderiert
  braucht Suche und Einzelabruf. Gegenprobe im PR: ein manipulierter Eintrag
  lässt den Test fallen.
- **Nebenwirkung STAC-Suche** (Registry der App statt fester `REGISTRY`):
  angenommen, das ist das Ziel; mit Test.
- **F5:** Der Vertragstest für Items kommt als offene Zeile ins Log
  („Vertragstest Items je Adapter, Stufe A, nach M4-01b“); Otto nimmt ihn beim
  nächsten Plan-Update als Aufgabe auf.
- Vor dem Fertigmelden `main` holen; Konflikte mit M4-07a (#120, Flag
  `reprojection`) in `catalog/registry.py` und `datasets.py` so lösen, dass
  beide Änderungen erhalten bleiben.

---

## 8. Umsetzung (06.10.2026)

Vor der Umsetzung ist `main` mit M4-06 (#118) und M4-07a (#120) in den Branch
geholt; der Merge lief ohne Konflikte, das Flag `reprojection` aus M4-07a steht
in `registry.py` und `datasets.py` unverändert. Danach sechs Commits nach §5:
(1) `adapters/errors.py`, (2) Signaturen mit `DatasetConfig`, (3)
`adapters/spec.py` mit Dispatch und Abgleich beim App-Bau, (4) `/coverage` mit
Registry und Tabelle der App, (5) `harvest_run` entfernen, (6) Doku und Log.

**Wie geplant:** §3.1 bis §3.7. `.importlinter` ist unverändert; kein Modul in
`adapters` importiert noch `catalog.datasets` (AST-Test).

**Abweichungen und Präzisierungen:**

- **Prüfung beim Bau eines Specs:** Ein `AdapterSpec` in einer von §5.2
  ausgeschlossenen Form wirft beim Bau `ValueError`, ein doppeltes `kind` in
  `spec_table` ebenso. Das sind Programmierfehler beim Import, keine
  `ConfigError` der Registry.
- **Texte der Abweisungen:** Eine Art ohne Spec heißt weiter „… which no
  adapter dispatch knows“; ein Spec ohne Suche „… which offers no search“; ein
  Spec ohne Materialisierung behält den alten Text „… which no materializer
  dispatch knows“, damit der bestehende Test unverändert bleibt.
- **Regel-I-Tests:** Die Tests „unbekannte Collection erreicht die Quelle
  nicht“ in `test_earth_search.py`, `test_eopf_stac.py`,
  `test_earth_search_coverage.py` und `test_eopf_sample_coverage.py` entfallen,
  weil dort keine Suche nach dem Eintrag mehr stattfindet. Regel I prüfen jetzt
  drei Tests von `dataset_config` in `test_dispatch.py`.
- **Adapter-Tests rufen das Modul:** `test_earth_search.py`,
  `test_cache_use.py` und `integration/test_search_cache.py` riefen den
  Dispatcher, obwohl sie das Earth-Search-Modul prüfen. Sie importieren jetzt
  `earthx.adapters.earth_search`, damit sie keine Tabelle brauchen. Ihre
  Assertions sind unverändert.
- **Testeintrag mit DEM-Zeitraum:** `integration/test_materialize_command.py`
  baut einen Eintrag auf Basis von Sentinel-2 mit `cop-dem-bucket`. Er hatte
  ein offenes Zeitende und bekommt jetzt `COP_DEM_GLO_30.temporal_extent`, weil
  der Adapter den Zeitraum aus dem Eintrag nimmt (§3.2).
- **Umfang:** rund 760 Zeilen Produktivcode geändert (453 hinzu, 309 weg) und
  rund 1070 Zeilen Tests (761 hinzu, 312 weg). Das ist mehr als die Schätzung in
  §5. Der größte Teil sind Testaufrufe mit der neuen Signatur und die neue
  Datei `test_spec.py` (rund 300 Zeilen).

**Tests (neu):** `tests/earthx/adapters/test_spec.py` (Form des Specs, der
Registry-Test nach Ottos Auflage, Gegenproben, `check_adapter_specs`,
App-Bau, AST-Test), `tests/earthx/api/test_one_registry_per_app.py`
(`/coverage`), `tests/integration/test_api_one_registry.py` (STAC-Suche und
Items-Route, T-C) sowie in `test_cop_dem_bucket.py` zwei Tests zum Zeitraum aus
dem Eintrag.

**Registry-Test nach Ottos Auflage:** Für jeden Eintrag von `REGISTRY` prüft
`test_what_its_holding_needs_is_offered`, dass der Spec alles anbietet, was die
Haltung verlangt: föderiert Suche, Einzelabruf, `intersects` und `ids`;
materialisiert Materialisierung; dazu Coverage, außer bei `local-sql` und
`single_coverage_product`. `test_what_it_does_not_need_is_refused_without_a_request`
ruft jede übrige Fähigkeit über den Dispatcher auf und verlangt eine Abweisung
mit `UnsupportedSource`, `UnsupportedFilter` oder `CoverageProviderMismatch`,
ohne Anfrage am Transport. Ein dritter Test belegt, dass beide zusammen jede
Fähigkeit abdecken.

**Gegenproben** (je einmal von Hand ausgeführt, danach zurückgesetzt):

- Im DEM-Spec `materialize=None`: 2 Tests in `test_spec.py` fallen
  (`test_what_its_holding_needs_is_offered[cop-dem-glo-30]`,
  `test_every_capability_of_every_entry_is_accounted_for`).
- Der echte Eintrag `sentinel-2-c1-l2a` mit Provider `sample` statt
  `upstream-aggregation`: 5 Tests fallen, darunter der Registry-Test für diesen
  Eintrag, der Abgleich und der Bau beider Apps.
- Suche bzw. `/coverage` wieder mit der festen `REGISTRY`: alle 4 Tests in
  `test_one_registry_per_app.py` und `test_api_one_registry.py` fallen.

Dauerhaft im Test stehen dieselben Gegenproben an manipulierten Kopien
(`TestTheCheckFailsForAManipulatedEntry`): ein materialisierter Eintrag ohne
Materialisierung, ein föderierter ohne Suche, ein Provider ohne Antwort, eine
Quelle ohne `ids` und eine Tabelle ohne die Art des Eintrags.

**Prüfungen:** `ruff check backend` sauber; `lint-imports` 14 Verträge
gehalten (12 vor M4-06 und M4-07a, 14 auf `main`); `pytest` aus der Repo-Wurzel
mit dem Postgres der Session 2578 bestanden; vor der Umsetzung, auf dem Branch
nach dem Merge von `main`, waren es 2542.
