# ADR 0011 — Adapter-Interface: aus drei Quellen abgeleitet

- **Status:** **Entwurf**, wartet auf Otto. Neun Fragen stehen in §11. Die
  Freigabe gehört zur M3-Abnahme (M3-14).
- **Datum:** 2026-09-30
- **Aufgabe:** M3-14 laut `docs/plans/m3-dritte-quelle-und-interface.md` §4 (P15).
- **Autonomiestufe:** C. Die Grundlage ist gelesen und berichtet. Code,
  Registry, Importregeln und `architekturplan.md` bleiben unverändert. Was sich
  nach einer Freigabe dort ändert, steht als Vorschlag in §4.3 und §6.5.
- **Grundlage:** `ENTSCHEIDUNGEN_2026-09-18.md` §3, §5; `KLAERUNGEN.md` B8, B9,
  B10, B13; `architekturplan.md` 1.2, 3.1, 5.1, 5.2, 6.1, 6.2, 7.1, 7.3, 7.7,
  15.2, 16; `adr/0004` §5; `adr/0005` Regeln I–VI; `adr/0009` §7, §10, §11;
  `plans/m3-02-konformitaetsbericht.md` K-04 bis K-11 und §8 Antwort 3;
  `plans/m3-11a-…`, `m3-11b-…`, `m3-11c-…`, `m3-13-…` samt Umsetzungsabschnitten;
  Entscheidungslog bis 26.09.2026.
- **Betroffen:** `backend/earthx/adapters/` (alle Module), `api/tiler.py`
  (Zugriffsauflösung, Item-Quelle), `api/federating_client.py` (Routing),
  `api/coverage_route.py`, `catalog/registry.py` (`SourceInfo.harvest_run`),
  `readers` (eigene Fehlerklasse, §6.4); `architekturplan.md` 3.1 (Spalte
  „Zuständig für“ bei `adapters` und `access`, nicht die Importspalte) und 6.1;
  M4 (erster Schritt), M5 (Harvester).

---

## Methode und Belegstufen

Gelesen in einer Cloud-Sitzung am 30.09.2026, auf dem Stand von `main` nach
PR #105. Die Belegstufen folgen `adr/0009`:

- **M:** in einer Sitzung gemessen. Hier nur übernommen, mit Verweis auf den Plan,
  der gemessen hat.
- **P:** am Primärdokument gelesen, meist am Quelltext im Repo mit Datei und Zeile.
- **S:** Zusammenfassung einer Quelle, deren Wortlaut nicht geprüft ist.
- **A:** eigene Ableitung, ein Argument und kein Beleg.

**Anfragen:** keine an eine Datenquelle. Zu EODAG (§9) gab es rund 40 Abrufe von
Dokumentation über `raw.githubusercontent.com` und `github.com`. Die Doku-Hosts
`eodag.readthedocs.io`, `pystac-client.readthedocs.io`, `api.openeo.org` und
`stac-utils.github.io` sind aus der Sitzung gesperrt. Was nur über eine
Zusammenfassung kam, trägt **[S]**. Zwei Dateien habe ich selbst gelesen und
belege sie mit **[P]**: `pyproject.toml` und `eodag/plugins/search/qssearch.py`.

---

## 0. Kurzfassung

Die Empfehlungen, jede mit einer Frage in §11:

1. **Fähigkeiten statt einer Adapterklasse (F1).** Jede Quelle meldet, was sie
   kann, als Eintrag `AdapterSpec`. Möglich sind Suche, Einzelabruf,
   Materialisierung, Coverage-Wege und Filter. Was fehlt, ist `None` und wird
   ausdrücklich abgewiesen. Der DEM-Bucket bekommt so keine Suche aufgezwungen
   (K1). Das folgt der Trennung der Plugin-Typen bei EODAG (§9).
2. **Zugriffsauflösung nach `access` (F2).** Die generische Auflösung zieht aus
   `api/tiler.py` nach `access`. Aus Item, Registry-Eintrag und Asset-Schlüssel
   wird dort eine serialisierbare Beschreibung, und daraus das Objekt, das der
   Reader öffnet. Den quellenspezifischen Teil liefert der Adapter schon im
   Item mit: Items mit lesbaren `href`s. Das Item besorgt weiter `api`.
   `processing` kann `access` importieren, ohne eine Importregel zu lockern.
   Der Worker-Kern bekommt aufgelöste Adressen (B9, 7.3). Das ist der erste
   Schritt von M4. **Es verschiebt eine Zuständigkeit aus 3.1:** Dort steht die
   Zugriffsauflösung heute bei `adapters`. Die Importspalte bleibt, die Spalte
   „Zuständig für“ ändert sich (F2, F8).
3. **Signaturen nehmen den Registry-Eintrag (F3).** Adapter bekommen die
   `DatasetConfig`, nicht `dataset_id` mit `registry=REGISTRY` als Vorgabe
   (K-09). Regel I prüft dann der Dispatcher einmal, statt dass jeder Adapter
   sein eigenes `resolve_dataset` hat.
4. **Eine Item-Quelle für alle Wege (F4).** Tiler, Download und später die
   Job-Annahme holen Items über dieselbe Funktion in `api`. Das Routing liest
   die Python-Registry. `api` prüft beim Start, dass pgstac dasselbe sagt (K-11).
5. **`SourceInfo.harvest_run` entfällt (F5).** Die Läufe protokolliert seit
   M3-11b eine eigene Tabelle. Ein Registry-Eintrag im Code kann keinen Lauf
   festhalten.
6. **STAC-API-Dialekt erst mit der nächsten STAC-API-Quelle (F6).** Die beiden
   STAC-Adapter unterscheiden sich im Code in drei Stellen (§3.2 B2). Das
   Zusammenlegen lohnt erst in M5 und wird nicht auf Vorrat gebaut.
7. **Architekturplan 3.1 und 6.1 anpassen (F8).** In 6.1 sind sechs
   Fähigkeiten nötig statt vier. „Genutzt von“ muss `api` bzw. `discovery`
   heißen statt `catalog` (K-07). In 3.1 wandert „Zugriffsauflösung“ von
   `adapters` zu `access`. Entwurf in §4.3.
8. **EODAG nicht als Bibliothek (F9).** EODAG holt selbst über `requests` und
   `boto3` [P]. Damit wäre `gateway` umgangen (B8) und die Importregel
   `http-only-in-gateway` verletzt.

---

## 1. Kontext und Frage

`architekturplan.md` 1.2 hat das Interface bewusst nicht vorab entworfen: „Die
konkreten Signaturen entstehen … aus den ersten zwei bis drei realen Quellen.
Damit das Interface nicht STAC-förmig wird, muss darunter eine Nicht-STAC-Quelle
sein“ (6.1). Die drei Quellen sind jetzt da:

| Quelle | Datensatz | Protokoll | Items | seit |
|---|---|---|---|---|
| Earth Search v1 | `sentinel-2-c1-l2a` (COG) | STAC API | föderiert | M1-06 |
| EOPF Sentinel Zarr Samples | `sentinel-2-l2a-zarr3` (Zarr) | STAC API (STAC 1.1) | föderiert | M2-09b |
| Copernicus DEM, AWS-Bucket | `cop-dem-glo-30` (COG) | Bucket: `tileList.txt`, `blacklist.txt`, S3-Listing | materialisiert in pgstac | M3-11b |

Die Frage: Welche Form bekommt die Nahtstelle zwischen Plattform und Quelle? Wo
lebt die Zugriffsauflösung? Das hat Otto am 23.09.2026 ausdrücklich an dieses
ADR gegeben (M3-02 §8, Antwort 3). Und was folgt daraus für M4 und M5?

---

## 2. Kriterien

| # | Kriterium | Quelle |
|---|---|---|
| K1 | Eine Nicht-STAC-Quelle wird nicht in STAC-Form gepresst: Sie muss keine Fähigkeit anbieten, die sie nicht hat. STAC bleibt das Modell der *Ergebnisse* (0.1), nicht die Form der *Aufrufe* | Plan M3-14; architekturplan 6.1, 16 |
| K2 | Jede Fähigkeit lässt sich mit synthetischen Fixtures testen, ohne private Tabellen zu überschreiben | Plan M3-14; CLAUDE.md; `adr/0002` |
| K3 | Der Harvester (M5) passt hinein, ohne dass sich die Form ändert | Plan M3-14; architekturplan 4, 15.1 |
| K4 | Processing (M4) bekommt die Zugriffsauflösung, ohne eine Importregel zu lockern und ohne Plattformdienste im Worker-Kern | Plan M3-14; 3.1; B9; 7.3 |
| K5 | Die Modulgrenzen aus 3.1 bleiben, wie sie sind: Keine Importregel wird gelockert. Eine Verschiebung in der Spalte „Zuständig für“ ist erlaubt, braucht aber Ottos Freigabe und wird als solche benannt | CLAUDE.md „Unverrückbar“ |
| K6 | Eine neue Quelle ändert eine Stelle, nicht jeden Aufrufer | architekturplan 1.1, Ziel 1 |
| K7 | Was nicht geht, wird ausdrücklich abgewiesen, nie still ersetzt | `adr/0005` Regel I; B10 |
| K8 | Der Umbau bleibt für ein kleines Team überschaubar | architekturplan 1.1, Ziel 6 |

---

## 3. Was die drei Adapter tatsächlich tun — [P]

### 3.1 Übersicht

| Fähigkeit | Earth Search | EOPF | DEM-Bucket | wo im Code |
|---|---|---|---|---|
| Collection-Discovery | — | — | — | Einträge von Hand in `catalog/datasets.py` |
| Suche | `search_items` | `search_items` | — (pgstac antwortet) | `adapters/__init__.py:71` `_ADAPTERS`; materialisiert: `api/federating_client.py` → `super()` |
| Einzelabruf | `get_item` | `get_item` | — (pgstac) | `api/tiler.py:760` `build_item_source` |
| Materialisierung | — | — | `materialize_items` | `adapters/__init__.py:79` `_MATERIALIZERS`; `discovery/materialize.py` |
| Normalisierung | keine | STAC 1.1 → 1.0, `zipped_product` entfernt | baut Items selbst | `eopf_stac.py:225`, `:222`; `cop_dem_bucket.py` `_item` |
| Coverage | Aggregation der Quelle | ausgewiesene Stichprobe | Fläche aus eigenen Items, SQL | `adapters/__init__.py:89` `_COVERAGE`; `catalog/local_coverage.py` |
| Filter `intersects`/`ids` | ja | ja | pgstac: ja | Modulkonstanten `SUPPORTS_*`, gelesen per `getattr` (`adapters/__init__.py:133`, `:135`) |
| CQL2 an der Quelle | nein [M] | ja [M] | pgstac: kann es, ist aus | `plans/m3-13-…` §2.3 |
| Seitenmarke | Keyset `body.next` | Keyset `body.token` | Keyset `coll:item-id` | `plans/m3-13-…` §2.3 [M] |
| Zugriffsauflösung | — | — | — | generisch in `api/tiler.py:356` `_resolve_asset_path` |

Außerhalb der Tabelle liegt `adapters/nominatim.py` (M3-07a). Es spricht das
Protokoll einer Quelle, liefert aber keine Datensätze, sondern Orte. Es hat
eigene Fehlerklassen mit denselben Namen wie `federated_search`
(`InvalidQuery`, `UpstreamShapeError`, `nominatim.py:89`, `:106`).

### 3.2 Befunde

- **B1: Discovery ist bei keiner Quelle Code.** Alle drei Collections stehen
  von Hand in `catalog/datasets.py`. Für die Fähigkeit „Discovery“ aus 6.1 gibt
  es also noch keine reale Quelle. Ihre Signatur kann dieses ADR nicht aus
  Erfahrung ableiten (§8.2).
- **B2: Die beiden STAC-Adapter sind fast gleich.** Die Funktionen
  `search_items`, `get_item`, `resolve_dataset`, `_search_body`, `_storable`
  und `_next_marker` unterscheiden sich im Code, ohne Kommentare und
  Docstrings, an drei Stellen. Das sind das Feld der Marke (`next` oder
  `token`), der Aufruf von `normalize_item` und der erwartete `AdapterKind`.
  Alles andere liegt schon gemeinsam in `federated_search.py`.
- **B3: Materialisierung ist eine eigene Fähigkeit mit eigenem Lebenslauf.**
  Das bestätigt `adr/0009` §11. Sie läuft offline im Prozess `discovery`, nicht
  bei einer Anfrage. Sie ist bedingt (`If-None-Match`, `known_version`) und
  liefert einen Bericht mit Zahlen: gelistet, im Bucket, fehlend,
  zurückgehalten, unbekannt. Sind mehr als 1 % der Liste fehlend oder
  zurückgehalten, bricht sie ab (`cop_dem_bucket.py:292`, `MaterializeOutcome`). Mit Suche hat die Signatur
  nichts gemein.
- **B4: Coverage hängt an der Item-Haltung, nicht nur am Adapter.** Die zwei
  föderierten Wege wählt die Tabelle `(AdapterKind, CoverageProvider)`. Den
  materialisierten Weg (`local-sql`) wählt `api/coverage_route.py:72`
  `_area_path` vorher. Er läuft in `catalog`, weil `adapters` keine
  Datenbankverbindung hat. Aggregation ist also nicht rein eine
  Adapter-Fähigkeit.
- **B5: Kein Adapter löst Zugriff auf.** Die Auflösung in `api/tiler.py` ist
  generisch: Sie wählt den Reader nach `format`, teilt Zarr-Variablen, holt das
  CRS aus dem Item, wählt die Zarr-Stufe und prüft die Adresse gegen die Policy.
  Der quellenspezifische Teil passiert früher, beim Bau oder bei der
  Normalisierung des Items. EOPF entfernt `zipped_product` (`eopf_stac.py:222`),
  der DEM baut `https`-Adressen aus dem Endpunkt. Die in `adr/0009` §11
  befürchtete Übersetzung von `s3://` nach `https` kam nicht vor, weil der DEM
  direkt aus dem Bucket kommt und nicht über Earth Search.
- **B6: Drei Stellen entscheiden „föderiert oder eigen“.**
  - Die Suche liest `earthx:source.item_holding` aus dem pgstac-Dokument
    (`federating_client.py:591`).
  - Der Einzelabruf für Kacheln und Download liest die Python-Registry
    (`tiler.py:760`).
  - Die Coverage liest die Python-Registry (`coverage_route.py:105`). Sie
    fragt nicht `item_holding`, sondern Provider `local-sql` und
    `single_coverage_product` (`_area_path`). Gleichwertig ist das nur, weil
    `DatasetConfig._check_item_holding` Haltung und Provider koppelt
    (`catalog/registry.py:744`).
  - Dazu kommt die Sicherung in `adapters._adapter_for` (`__init__.py:95`).

  Das sind zwei Wahrheiten (K-11). Sie stimmen, solange `catalog.load` nach
  jeder Registry-Änderung läuft (bei jedem `docker compose up`).
- **B7: Fähigkeiten eines Adapters sind implizit.**
  - `SUPPORTS_INTERSECTS`/`SUPPORTS_IDS` sind Modulkonstanten. Fehlen sie,
    liefert `getattr` stumm `False`.
  - Die Dispatch-Tabellen enthalten Module (`ModuleType`), keinen geprüften Typ.
  - Tests ersetzen eine private Tabelle per `monkeypatch.setitem(_ADAPTERS, …)`
    (`tests/earthx/adapters/test_dispatch.py:165`).
- **B8: Adapter lesen Registry-Inhalt (K-09, gewachsen).**
  - Fünf Module setzen `registry=REGISTRY` als Vorgabe.
  - `cop_dem_bucket.py:44` importiert zusätzlich `DEM_ACQUISITION_START/END`
    aus `catalog.datasets`. Dieselben Werte stehen im Eintrag als
    `temporal_extent` (`datasets.py:456`).
- **B9: Das Fehlervokabular liegt am falschen Ort.** `UnsupportedSource` und
  `UpstreamShapeError` stehen in `federated_search.py`. `cop_dem_bucket` ist
  nicht föderiert und importiert sie trotzdem von dort (`:43`).
- **B10: `SourceInfo.harvest_run` ist bei allen drei Einträgen `None`.** Den
  Lauf mit ETag protokolliert `public.earthx_materialize_runs` (M3-11b §3.5).
  M3-11a F3 und M3-11b §3.5 haben die Frage an dieses ADR gegeben.
- **B11: Die Paging-Form ist bei allen drei Quellen gleich.** Es sind
  Keyset-Marken, die auf das letzte Item zeigen, unabhängig von `limit`
  (M3-13 §2.3 [M]). Unsere eigene Marke umhüllt die der Quelle, versioniert
  (`TOKEN_VERSION` 2). Das Interface muss daran nichts ändern.
- **B12: Zeitachse und Wolkenfilter sind Eigenschaften des Datensatzes, nicht
  des Adapters.** `time_range=False` und `max_cloud_cover` behandelt `api`
  (`ignored_filters`) vor jedem Adapter. Das ist richtig so. Capability-Flags
  des Datensatzes (B10) und Filter-Fähigkeiten der Quelle sind zwei Dinge.

---

## 4. Die Fähigkeiten aus 6.1 gegen den Code

### 4.1 Abgleich

| 6.1 heute | Was der Code zeigt | Folge |
|---|---|---|
| Discovery, genutzt von `discovery` | noch keine reale Quelle (B1) | bleibt, Signatur mit M5 (§8.2) |
| Suche, genutzt von `catalog` | nur föderierte Quellen; materialisiert antwortet pgstac; aufgerufen von `api` (K-07) | Suche ist eine Fähigkeit der *föderierten* Haltung; Aufrufer `api` |
| Zugriffsauflösung, Adapter; genutzt von `access`, `processing` | kein Adapter tut es (B5); generisch in `api` | Anbieter wird `access`; der Adapter trägt „lesbare hrefs“ bei (§5.3) |
| Aggregation (optional), genutzt von `catalog` | drei Wege, einer davon in `catalog` (B4); Aufrufer `api` | Coverage-Weg je Provider; Aufrufer `api` |
| — | Einzelabruf ist eigenständig (Kacheln, Download) | neue Zeile |
| — | Materialisierung (B3) | neue Zeile |

### 4.2 Wer ruft auf (K-07)

`catalog` darf keinen Adapter importieren (3.1). Im Code setzt `api` die Teile
zusammen: `federating_client.py`, `coverage_route.py`, `tiler.py`. Die
Materialisierung ruft `discovery` auf. Das ist kein Mangel des Codes, sondern
ein Fehler im Text von 6.1.

### 4.3 Vorschlag für 6.1 (erst nach Freigabe übernehmen)

| Fähigkeit | Frage | Wer bietet sie | Wer ruft sie auf |
|---|---|---|---|
| Discovery (ab M5) | Welche Datensätze gibt es bei dieser Quelle, mit welchen Metadaten? | Adapter mit Collection-Protokoll | `discovery` |
| Suche | Welche Items gibt es für AOI, Zeitraum, `ids`? | Adapter einer föderierten Quelle; bei materialisierter Haltung pgstac | `api` |
| Einzelabruf | Welches Item hat diese Kennung? | wie Suche | `api` (Item-Quelle für Kachel, Download, Job-Annahme) |
| Materialisierung | Welche Items bietet die Quelle an, einmal gebaut und geprüft? | Adapter einer materialisierten Quelle | `discovery` |
| Aggregation (optional) | Wie viele Aufnahmen je Zelle und Zeitschritt unter Filter F? | Adapter (Aggregation der Quelle oder Stichprobe) oder `catalog` (SQL über eigene Items) | `api` |
| Zugriffsauflösung | Welcher Reader und welche geprüfte Adresse gehören zu diesem Asset? | `access`, generisch; Adapter liefern dafür Items mit lesbaren hrefs (§5.3) | `api`, `processing` |

Den Satz „Auth ist bewusst eine spätere Fähigkeit“ würde ich stehen lassen.

In **3.1** ändert sich mit F2 (1) nur die Spalte „Zuständig für“, nicht die
Importspalte:

| Modul | heute | nach F2 (1) |
|---|---|---|
| `adapters` | Protokolle der Quellen: Discovery, Suche, Zugriffsauflösung | Protokolle der Quellen: Discovery, Suche, Einzelabruf, Materialisierung, Aggregation; Items mit lesbaren hrefs (§5.3) |
| `access` | Tiles, Quicklooks, Statistik, Download-Vermittlung | Zugriffsauflösung, Tiles, Quicklooks, Statistik, Download-Vermittlung |

---

## 5. Optionen für die Form des Interfaces

### 5.1 Die Optionen

**S1: Status quo mit Typen.** Module behalten gleichnamige Funktionen. Neu sind
`typing.Protocol` je Funktion und ein Typ statt `ModuleType` in den drei
Tabellen. Filter-Fähigkeiten bleiben Modulkonstanten.

- Pro: kleinster Umbau.
- Contra: Eine neue Quelle berührt bis zu drei Tabellen und muss an ihre
  Konstanten denken. Fehlt eine, gilt still `False` (B7). Tests ersetzen
  weiter private Tabellen.

**S2: Eine Klasse `DataSourceAdapter`.** Eine abstrakte Basisklasse mit allen
Methoden (`discover`, `search`, `get_item`, `materialize`, `coverage`, `resolve`).
Was eine Quelle nicht kann, wirft `NotImplementedError`.

- Pro: eine Stelle je Quelle; einfach zu fälschen im Test.
- Contra: Die Form ist die einer STAC-Suche mit Anbau. Der DEM müsste eine
  Suche „haben“, die zur Laufzeit wirft (gegen K1). Welche Fähigkeit es gibt,
  zeigt erst der Aufruf. EODAG hat genau diese Bündelung nur als Sonderfall
  (Plugin-Typ „Api“, §9).

**S3: Getrennte Fähigkeiten, je Quelle ein deklarierter Eintrag.** Pro
Fähigkeit ein `Protocol`. Pro `AdapterKind` ein unveränderlicher Eintrag
`AdapterSpec`. Er nennt die Funktion je Fähigkeit oder `None`, dazu die
Filter-Fähigkeiten als Daten. Die Module bleiben, wie sie sind, und stellen nur
ihren Eintrag bereit.

- Pro: Der DEM meldet nur `materialize`. Eine STAC-API könnte später beides
  melden, etwa wenn eine föderierte Quelle doch materialisiert wird
  (architekturplan 16, „für kritische Quellen Items doch materialisieren“).
  Welche Haltung gilt, entscheidet dann weiter `item_holding` (P24). Tests
  bauen eine eigene Tabelle aus synthetischen Einträgen und reichen sie herein.
- Contra: Der Umbau ist etwas größer als bei S1. Es gibt eine Stelle mehr, an
  der Fähigkeit und Registry übereinstimmen müssen (Prüfung beim Start, §5.2).

**S4: Konfiguration statt Code.** Nach dem Vorbild von EODAG `providers.yml`
mit `metadata_mapping`: generische Adapter, je Quelle eine YAML-Beschreibung.

- Pro: Eine neue STAC-API-Quelle wäre eine Datei.
- Contra: Der DEM brauchte Prüfungen, die als Konfiguration nicht ausdrückbar
  sind: Liste gegen Listing, Blacklist, 1-%-Schwelle, strenger Namens-Parser.
  EODAG braucht für Sonderfälle ebenfalls eigene Such-Plugins (CSW, S3,
  Cop Marine, ECMWF) [S]. JSONPath in YAML ist schwer zu testen [A].

**Matrix** (✓ erfüllt, ~ teilweise, ✗ verfehlt):

| | K1 | K2 | K3 | K4 | K5 | K6 | K7 | K8 |
|---|---|---|---|---|---|---|---|---|
| S1 Status quo mit Typen | ✓ | ~ | ~ | ✓ | ✓ | ~ | ~ | ✓ |
| S2 eine Klasse | ✗ | ✓ | ~ | ✓ | ✓ | ✓ | ~ | ~ |
| **S3 Fähigkeiten, deklariert** | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ~ |
| S4 Konfiguration | ~ | ✓ | ~ | ✓ | ✓ | ~ | ~ | ✗ |

K4 ist bei allen gleich, weil die Zugriffsauflösung in keiner Option beim Adapter
liegt (§6). K3 (Harvester) ist bei S3 am besten, weil eine neue Fähigkeit ein
neues Feld im Eintrag ist, keine vierte Tabelle.

**Empfehlung: S3.** S4 nur im Kleinen, als „Dialekt“ für die Familie der
STAC-APIs, sobald eine dritte STAC-API-Quelle kommt (F6, §8.2).

### 5.2 Skizze der Empfehlung (Vorschlag, nicht gebaut)

```python
# adapters/spec.py
class SearchItems(Protocol):
    async def __call__(self, config: DatasetConfig, params: SearchParams, *,
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
```

Regeln, geprüft beim Bau der Tabelle und in einem Test über die echte Registry:

- `search` und `fetch` kommen nur gemeinsam vor. `filters` ist genau dann
  gesetzt, wenn `search` gesetzt ist. Kein Feld hat einen Vorgabewert (B10).
- Für jeden Registry-Eintrag gilt:
  - Bei `federated` hat der Eintrag seines Adapters `search`.
  - Bei `materialized` hat er `materialize`.
  - Der `coverage.provider` steht in `coverage`, außer bei `local-sql`, das
    `catalog` beantwortet (B4).

  Ob Haltung und Provider zusammenpassen, prüft der Eintrag schon heute beim
  Bau (`ConfigError`). Fehlt dagegen eine Zeile in einer Dispatch-Tabelle,
  fällt das heute erst beim ersten Aufruf auf.
- Die Dispatcher heißen weiter `search_items`, `get_item`, `materialize_items`
  und `coverage`. Sie nehmen `config` und eine Tabelle
  `Mapping[AdapterKind, AdapterSpec]`, ohne Vorgabe. Regel I (unbekannte
  Collection → 404) prüft der Aufrufer, der den Eintrag sucht, genau einmal.
- Die Fehlerklassen ziehen nach `adapters/errors.py` (B9). `federated_search`
  behält Paging, Marke und `SearchParams`. `nominatim` steht nicht in der
  Tabelle, weil es keine Datensätze liefert.

### 5.3 Der Item-Vertrag

Den quellenspezifischen Teil der Zugriffsauflösung (B5) trägt der Adapter bei,
und zwar in den Items selbst. Jedes Item, das `search`, `fetch` oder
`materialize` liefert, erfüllt:

1. Es ist STAC 1.0, so wie die eigene API es ausgibt. Normalisierung ist Sache
   des Adapters, wie `eopf_stac.normalize_item` heute.
2. Jeder `href` eines Assets ist eine `https`-Adresse. Eine Übersetzung wie
   `s3://` → `https` gehört hierher, nicht in den Reader. Ob der Host erlaubt
   ist, prüft weiter die Auflösung beim Öffnen und weist mit `502` ab
   (`api/tiler.py:413`). Dieses Verhalten bleibt, wie es ist. Der Vertrag
   entfernt keine Assets auf fremden Hosts.
3. Assets, von denen der Adapter weiß, dass sie nicht angeboten werden dürfen,
   fehlen, statt später gefiltert zu werden (Vorbild `zipped_product`, D23).
   Das tut EOPF schon heute.
4. Bei materialisierten Quellen: Keiner Quell-Liste wird geglaubt, ohne sie
   gegen das Listing zu prüfen. Der Bericht nennt, was fehlt (`adr/0009` §11,
   M3-11b §3.2).

Ein **Vertragstest** läuft über jeden Eintrag der Tabelle mit synthetischen
Fixtures. Er prüft Punkt 1 und 2 (Form und Schema, nicht den Host). Die
vorhandenen Fixtures zeigen bewusst auf `example.invalid`, eine enthält
absichtlich ein Asset auf einem fremden Host (`item_asset_hosts.json`). Eine
Host-Prüfung gegen die Registry würde also dort scheitern, und das ist
gewollt. So wird K2 zu einer Regel für jede künftige Quelle, nicht zu einer
Absicht.

---

## 6. Zielort der Zugriffsauflösung (K-04)

### 6.1 Was Zugriffsauflösung heute ist — [P]

Drei Schritte, heute alle im Prozess `tiler`:

| Schritt | Heute | Braucht |
|---|---|---|
| a) Item besorgen | `tiler.py:760` `build_item_source`: föderiert über `adapters.get_item`, materialisiert über `catalog.pgstac.fetch_item` | `adapters`, `gateway`, Datenbank |
| b) Quellenspezifisches am href | in den Adaptern, beim Bau des Items (B5) | Adapter |
| c) Asset → Reader-Eingabe | `tiler.py:356` `_resolve_asset_path` samt `_resolve_asset_href` (`:136`), `_proj_code` (`:183`), `_target_gsd` (`:207`): Reader nach `format`, Zarr-Trenner, CRS, Stufe, `check_url` über `readers.asset_path`/`zarr_asset` | Registry-Eintrag (`catalog`), `readers`, eine `Policy` |

Schritt c wird von Kachel und Download genutzt (`tiler.py:619`). In M4 braucht
ihn `processing`, und das darf `api` nicht importieren. Das ist der Kern von K-04.

Der heutige Ort ist begründet: Nach Ottos Antwort 5 vom 20.09.2026 zu
`adr/0006` behält `access` Fabrik und Rendering, die Zusammensetzung liegt in
`api`, weil `access` `gateway` nicht importieren darf (`api/tiler.py` Z. 1–7).
Die Empfehlung hier revidiert diese Antwort teilweise. Sie hält die
Begründung ein, denn `access` importiert auch nach Z3 nichts aus `gateway`.

### 6.2 Randbedingungen

- **3.1:**
  - `processing` darf `access`, `readers`, `catalog` importieren, nicht
    `adapters`, `gateway`, `api`.
  - `adapters` darf `readers` nicht importieren.
  - `readers` darf `catalog` nicht importieren.
  - Keine Regel wird gelockert (CLAUDE.md).
- **Kettenzählung:** Der Vertrag `no-database-in-worker-core` zählt Ketten
  (`processing → … → psycopg`). Nach dem Log vom 20.09.2026 darf `processing`
  ab M4 nur DB-freie Teile von `catalog` erreichen. Daraus folgt: Die neue
  Auflösung in `access` darf aus `catalog` nur `catalog.registry` importieren.
  Das ist heute frei von `psycopg` (geprüft durch Import in der Sitzung).
  `catalog.datasets`, `catalog.pgstac` und die Caches darf sie nicht importieren.
- **Kein `gateway` in `access` und `processing`, auch nicht als Typ:**
  `.importlinter` setzt kein `exclude_type_checking_imports`. Auch eine
  Annotation `policy: Policy` unter `TYPE_CHECKING` zählt als Import.
- **B9, 7.3:** Der Worker-Kern bekommt „Rezept und aufgelöste
  Asset-Adressen“. Er hat keine Datenbank und keine interne API. Schritt a
  kann deshalb nicht im Worker-Kern laufen: Er braucht die Datenbank
  (materialisiert) oder `adapters` (föderiert).
- **7.7:** Der lokale Runner holt „Rezept und Asset-Auflösung“ über die
  öffentliche API oder liest sie offline aus der Rezeptdatei. Das Ergebnis
  von Schritt c muss also **serialisierbar** sein. Heute ist es das nicht:
  `ZarrAsset` trägt `Policy` und `Resolver`.

### 6.3 Optionen für Schritt c

| | Ort | processing kann es nutzen | Importregeln | Bewertung |
|---|---|---|---|---|
| Z1 | bleibt in `api/tiler.py` | nein, zweite Kopie in `processing` | unverändert | gegen K4, K6 |
| Z2 | `adapters` (Wortlaut 3.1 und 6.1) | nein: `processing → adapters` verboten; `adapters → readers` verboten, also nur eine Beschreibung, kein Reader-Objekt | bräuchte zwei Lockerungen | entspricht der Zuständigkeit in 3.1, verletzt aber die Importregeln (gegen K4, K5); materialisierte Quellen haben zur Laufzeit gar keinen Adapter |
| **Z3** | **`access`** | ja: `processing → access` erlaubt | unverändert: `access` importiert `readers` und `catalog.registry`; Fehlerklasse aus `readers` (§6.4) | erfüllt K4; K5 teilweise: Importregeln bleiben, die Zuständigkeit in 3.1 verschiebt sich (F8) |
| Z4 | neues Modul, etwa `resolve` | ja, wenn 3.1 es so einträgt | neue Zeile in 3.1 und `.importlinter` | ein bewegliches Teil mehr (K8); fachlich dasselbe wie Z3 |
| Z5 | `readers` | ja | bräuchte `readers → catalog` (Lockerung) | gegen K5 |

### 6.4 Empfehlung: Z3, in zwei Hälften

In `access`, etwa `access/resolve.py`:

```python
@dataclass(frozen=True, slots=True)
class ResolvedAsset:               # serialisierbar, geht ins Rezept (7.1, 7.7)
    dataset_id: str
    item_id: str
    asset: str
    reader: Literal["cog", "zarr"]
    href: str                      # Host mit asset_hosts verglichen, DNS-Prüfung erst beim Öffnen des Eintrags
    variable: str | None           # nur Zarr
    crs: str | None                # proj:code bzw. proj:epsg des Items

def resolve_asset(item: Mapping[str, Any], config: DatasetConfig, asset: str) -> ResolvedAsset: ...

def open_asset_ref(ref: ResolvedAsset, policy, resolve, *,
                   target_gsd: float | None = None) -> AssetPath | ZarrAsset: ...
```

- `resolve_asset` ist rein: kein Netz, keine Policy. Hier liegt, was heute
  `_resolve_asset_path` ohne `check_url` tut, samt Abweisung eines Formats ohne
  Reader. Die heutige Unterscheidung „400 wegen des Schlüssels, 502 wegen des
  Items“ hängt an `UrlRejected`, das `readers.split_asset_key` wirft
  (`zarr_reader.py:420`). `access` kann das nicht fangen, ohne `gateway` zu
  importieren.
- **Fehler übersetzt `readers`.** `readers` darf `gateway` importieren. Es
  bekommt eine eigene Fehlerklasse, etwa `AssetRejected(UrlRejected)`.
  `split_asset_key`, `asset_path` und `zarr_asset` werfen nur noch sie. Weil
  sie von `UrlRejected` erbt, bleibt das Fangen in `api` gleich. `access` und
  `processing` fangen die Klasse aus `readers`. **Nur unter dieser Bedingung
  geht Z3 ohne Lockerung einer Importregel.**
- `open_asset_ref` reicht `policy` und `resolve` an `readers.asset_path` bzw.
  `readers.zarr_asset` durch, die `check_url` aufrufen. Das ist erlaubt, weil
  die Verträge direkte Importe zählen (`allow_indirect_imports = True`). Als
  Typ nimmt `access` den Neu-Export aus `readers` oder `object`, nie einen
  Import aus `gateway`. Die übrigen Fehler aus `gateway` übersetzt weiter `api`
  in HTTP-Codes.
- `_target_gsd` zieht mit nach `access`. Es rechnet aus einer Kachelgeometrie,
  was `access` ohnehin rendert.
- **Schritt a bleibt in `api`**, als eine gemeinsame Item-Quelle (F4, §7).
- **Schritt b bleibt beim Adapter** (Item-Vertrag, §5.3).

**Weg in M4:** Die Job-Annahme in `api` holt die Items (a), löst die Assets auf
(c, erste Hälfte) und schreibt `ResolvedAsset` ins Rezept. Der Worker-Kern ruft
nur `open_asset_ref` auf. Der lokale Runner bekommt dieselben `ResolvedAsset`
aus der API oder der Rezeptdatei.

### 6.5 Erster Schritt von M4 (Vorschlag für den Schnitt, F7)

1. `access/resolve.py` mit `ResolvedAsset`, `resolve_asset`, `open_asset_ref`.
   `api/tiler.py` ruft nur noch diese Funktionen auf. Tests: die bestehenden
   Tiler-Tests unverändert grün, dazu reine Tests von `resolve_asset` mit
   synthetischen Items und ein Serialisierungstest (Hin- und Rückweg JSON).
2. Die Item-Quelle aus `api/tiler.py` in ein eigenes Modul in `api`, genutzt von
   Tiler, Download und später Job-Annahme (§7).
3. `AdapterSpec`, Signaturen mit `config`, `adapters/errors.py`, `harvest_run`
   entfernen (F1, F3, F5). Das wäre ein eigener PR.

Offen für den M4-Plan, nicht hier zu entscheiden: Wer baut im Worker die
`Policy` aus den Hosts der `ResolvedAsset` (B9: „Allowlist ergibt sich aus den
aufgelösten Asset-Adressen“)? Und wer setzt dort die GDAL-Konfiguration
`gateway.gdal.gdal_options(policy)`, die der Tiler für jeden COG-Lesezugriff
setzt (`api/tiler.py:91`, `:825`)? `processing` und `jobs` dürfen `gateway`
nicht importieren. Eine kleine Fabrik in `readers`, die beides liefert, wäre
der naheliegende Ort [A].

---

## 7. Eine Item-Quelle und das Routing (K-11)

Drei Stellen entscheiden heute „föderiert oder eigen“, aus zwei Quellen der
Wahrheit (B6).

| | Vorgehen | Pro | Contra |
|---|---|---|---|
| D1 | so lassen | kein Umbau | zwei Wahrheiten; M4 bräuchte eine vierte Stelle für die Job-Annahme |
| **D2** | eine Item-Quelle in `api` für Einzelabruf (Tiler, Download, Job-Annahme, `federating_client.get_item`); das Routing aller Wege liest die Python-Registry; `api` prüft beim Start, dass jede Collection in pgstac dieselbe `item_holding` trägt, sonst Start mit Fehler (`api` läuft ohnehin nie ohne pgstac); der `tiler` prüft dasselbe nur, wenn er einen Pool hat, und startet ohne Datenbank wie heute (E5) | eine Wahrheit fürs Routing; ein Fehler fällt beim Start auf statt bei einer Anfrage | kleiner Umbau in `federating_client` |
| D3 | alles liest das pgstac-Dokument | eine Wahrheit | der Tiler bräuchte für jede Kachel eine Datenbankabfrage; ohne Datenbank bliebe er auch für föderierte Quellen stehen (gegen E5) |

Regel I bleibt bei D2 unverändert: Eine unbekannte Collection ist weiter die
404 von pgstac. Nur die Frage „welcher Weg“ liest die Registry.

**Empfehlung: D2**, im ersten Schritt von M4 zusammen mit §6.5 Punkt 2.

---

## 8. Folgen für M4 und M5

### 8.1 M4: Processing

- **Zugriffsauflösung:** siehe §6.4. Der Worker-Kern sieht weder Adapter noch
  pgstac, nur `ResolvedAsset`.
- **Rezept, Eingaben (7.1):** `dataset_version` und `etag` brauchen eine Quelle.
  Für materialisierte Datensätze gibt es sie schon: `source_version` im
  Lauf-Protokoll. Für föderierte fehlt sie. Der Weg (Asset-HEAD oder `updated`
  am Item) ist Sache des M4-Plans. Das Interface muss dafür nichts vorhalten.
- **Mosaik ganzer Szenen je Überflug (M4, P11):** Es braucht eine Suche als
  Eingabe. Sie läuft über die vorhandenen Dispatcher bzw. die gemischte Suche
  in `api`, nie im Worker.
- **Operatoren:** Sie hängen an den Capability-Flags des *Datensatzes* (B10),
  nicht an `FilterSupport` des Adapters (B12). Die beiden bleiben getrennt.

### 8.2 M5: Harvester

- **Discovery:** Die Signatur entsteht erst mit der ersten realen Quelle.
  Mögliche Kandidaten sind eine STAC-API mit Collection-Suche und Zenodo nur
  für Metadaten (`adr/0009` F6). Nach B13 und architekturplan 4.4 liefert sie
  *Vorschläge* für Einträge, die per Git geprüft werden, keine fertige
  `DatasetConfig`. Lizenzstufe und Flags entscheidet immer Otto (B11). In S3
  ist das ein weiteres Feld `discover` im `AdapterSpec`, ohne andere Stellen
  zu ändern.
- **Materialisierung als Harvester-Aufgabe:** `materialize_items` hat schon die
  Form, die ein Harvester braucht. Sie ist bedingt über `known_version`, hat
  einen Bericht, eine Abbruchschwelle und ein Lauf-Protokoll. Der Harvester
  plant den Einmal-Befehl nur noch ein.
- **Fassungen:** Hansen und Zenodo veröffentlichen neu statt nachzuliefern
  (`adr/0009` §11). Eine Collection braucht dann eine Aussage, welche Fassung
  sie meint. Das Lauf-Protokoll trägt `source_version`. Ob die Collection
  selbst ein Fassungsfeld bekommt, gehört zum M5-Plan.
- **STAC-API-Dialekt:** Kommt eine dritte STAC-API, würde ein Modul
  `stac_api.py` mit einem Dialekt je Quelle aus zwei Modulen eines machen.
  Der Dialekt enthält das Markenfeld, die Normalisierung und `FilterSupport`
  (B2, F6).
- **Ratengrenzen:** Sie sind je Quelle verschieden, bei Zenodo hart (133/min).
  Sie gehören nach `gateway` (Token-Bucket je Host, K-10), nicht ins
  Interface. `nominatim` zeigt mit `RateSlot` (Postgres, über Prozesse hinweg),
  wie das aussehen kann.

---

## 9. Lehren aus EODAG und Nachbarn

| Befund | Beleg | Folge hier |
|---|---|---|
| EODAG trennt Plugin-Typen: Search, Download, Authentication, Crunch; „Api“ bündelt alles nur für Sonderfälle. Ein Provider ist eine Kombination, meist per YAML | [S] [plugins.rst](https://raw.githubusercontent.com/CS-SI/eodag/develop/docs/plugins.rst), [add_provider.rst](https://raw.githubusercontent.com/CS-SI/eodag/develop/docs/add_provider.rst) | stützt S3 gegen S2 |
| Nicht-STAC-Quellen über `metadata_mapping` (Format-Templates und JSONPath); trotzdem eigene Such-Plugins für CSW, S3, Cop Marine, ECMWF | [S] [params_mapping.rst](https://raw.githubusercontent.com/CS-SI/eodag/develop/docs/params_mapping.rst), [search.rst](https://raw.githubusercontent.com/CS-SI/eodag/develop/docs/plugins_reference/search.rst) | Konfiguration nur für wiederkehrende Muster (Dialekt), sonst Code (gegen S4 im Großen) |
| EODAG 4.0.0 (16.03.2026) stellt die Eigenschaften auf STAC-Vokabular um, rund 40 Umbenennungen | [S] [BREAKING_CHANGES.rst](https://raw.githubusercontent.com/CS-SI/eodag/develop/BREAKING_CHANGES.rst) | bestätigt STAC als internes Modell von Anfang an (architekturplan 0.1) |
| Zählen ist optional seit 3.0.0; Anlass: eine Suche mit Zählung dauerte 54 s statt 0,8 s | [S] [Issue #1644](https://github.com/CS-SI/eodag/issues/1644) | `ItemPage.matched: int \| None` bleibt richtig; die Marke ist Keyset (B11) |
| Lesen (xarray, fsspec) liegt im eigenen Paket `eodag-cube`, getrennt von der Suche | [S] [ecosystem.rst](https://raw.githubusercontent.com/CS-SI/eodag/develop/docs/ecosystem.rst) | stützt: Zugriffsauflösung und Lesen nicht im Adapter (§6) |
| EODAG hängt von `requests`, `boto3`, `urllib3` ab; die Suche importiert `requests` direkt | [P] [pyproject.toml](https://raw.githubusercontent.com/CS-SI/eodag/develop/pyproject.toml), [qssearch.py](https://raw.githubusercontent.com/CS-SI/eodag/develop/eodag/plugins/search/qssearch.py) Z. 52–58 | als Bibliothek in `adapters` verletzt es B8 und den Importvertrag `http-only-in-gateway`: **kein EODAG als Bibliothek** (F9) |
| stac-fastapi-eodag: aktiv, vor 1.0 (0.6.1 vom 25.09.2026) | [S] [CHANGELOG.md](https://raw.githubusercontent.com/CS-SI/stac-fastapi-eodag/main/CHANGELOG.md) | kein Kandidat für den Kern (wie architekturplan 2) |
| pystac-client: `matched()` kann `None` sein, die Iteration läuft weiter | [S] [item_search.py](https://raw.githubusercontent.com/stac-utils/pystac-client/main/pystac_client/item_search.py) | wie bei uns |
| openEO `load_collection`: Sammlung und Filter rein, Datenwürfel raus; Filter gehören in den Aufruf | [S] [load_collection.json](https://raw.githubusercontent.com/Open-EO/openeo-processes/draft/load_collection.json) | Vorbild für die Rezept-Eingabe in M4, nicht für den Adapter |

Damit ist die Spike-Frage aus architekturplan 15.2 („Spart EODAG als Bibliothek
Adapter-Arbeit?“) für die drei realen Quellen beantwortet. Der
quellenspezifische Code je STAC-Quelle ist klein (B2). Der Rest sind
Plattformregeln (Regeln I–VI, `gateway`, Marke, Cache), die EODAG nicht kennt.
Und EODAG würde `gateway` umgehen.

---

## 10. Was dieses ADR nicht entscheidet

- Auth, also Token pro Connector: bleibt fern (ENTSCHEIDUNGEN §3).
- Zeit in Pixeln oder als Würfel-Dimension (Hansen `lossyear`, ARCO-ERA5,
  `adr/0009` §11): Das ist eine Frage an Reader und Rezept, sobald eine solche
  Quelle kommt. Das Interface bleibt davon unberührt, weil Items mit
  `datetime: null` und Zeitspanne schon gehen (DEM).
- Virtuelle Zarr-Stores (6.2 Rang 3): ein Reader-Thema.
- Form der Discovery-Signatur (§8.2).
- Wie die `Policy` im Worker entsteht (§6.5).

---

## 11. Fragen an Otto

**F1: Form des Interfaces**
1. S3: getrennte Fähigkeiten, je Quelle ein `AdapterSpec` **(Empfehlung)**
2. S1: Status quo mit Typen
3. S2: eine Klasse `DataSourceAdapter`
4. S4: Konfiguration statt Code

**F2: Zielort der Zugriffsauflösung (K-04)**
1. `access`, rein (`resolve_asset`) plus Öffnen (`open_asset_ref`); das Item
   besorgt `api`; Fehlerklasse in `readers`; in 3.1 wandert die Zuständigkeit
   von `adapters` zu `access` **(Empfehlung)**
2. bleibt in `api/tiler.py`; `processing` baut eine zweite Kopie
3. neues Modul in 3.1
4. `adapters`, mit Lockerung zweier Importregeln

**F3: Signaturen mit `DatasetConfig` (K-09)**
1. ja; `registry=REGISTRY` als Vorgabe entfällt, die DEM-Zeitkonstanten kommen
   aus `config.temporal_extent` **(Empfehlung)**
2. nur die Vorgabe `REGISTRY` streichen, `dataset_id` bleibt
3. so lassen

**F4: Weg zum Item und Routing (K-11)**
1. D2: eine Item-Quelle in `api`, Routing aus der Registry, Abgleich mit pgstac
   beim Start **(Empfehlung)**
2. D1: so lassen
3. D3: alles aus dem pgstac-Dokument

**F5: `SourceInfo.harvest_run`**
1. entfernen; die Läufe stehen in `earthx_materialize_runs` **(Empfehlung)**
2. bis M5 stehen lassen
3. umdeuten auf die Kennung des letzten Laufs

**F6: STAC-API-Dialekt (ein Modul für beide STAC-Quellen)**
1. erst mit der nächsten STAC-API-Quelle, also in M5 **(Empfehlung)**
2. jetzt, im ersten Schritt von M4
3. nie

**F7: Zeitpunkt und Schnitt des Umbaus**
1. erster Schritt von M4, zwei PRs: (a) Zugriffsauflösung und Item-Quelle
   (§6.5 Punkte 1–2), (b) `AdapterSpec`, Signaturen, Fehlerklassen,
   `harvest_run` (Punkt 3) **(Empfehlung)**
2. nur (a) in M4, (b) mit M5
3. beides noch in M3, als Stufe B

**F8: `architekturplan.md` 3.1 und 6.1**
1. nach Freigabe in diesem PR nach §4.3 anpassen: 6.1 neu, in 3.1 nur die
   Spalte „Zuständig für“ bei `adapters` und `access` **(Empfehlung)**
2. in M3-15

**F9: EODAG (Spike aus architekturplan 15.2)**
1. als beantwortet markieren: nicht als Bibliothek, Begründung §9 **(Empfehlung)**
2. für M5 offen lassen, für Protokolle wie OData oder CSW

---

## 12. Quellen

**Im Repo [P]**
- `backend/earthx/adapters/`: `__init__.py`, `earth_search.py`,
  `eopf_stac.py`, `cop_dem_bucket.py`, `federated_search.py`,
  `earth_search_coverage.py`, `eopf_sample_coverage.py`, `nominatim.py`
- `backend/earthx/api/`: `tiler.py`, `federating_client.py`, `coverage_route.py`
- `backend/earthx/catalog/`: `registry.py`, `datasets.py`, `coverage.py`,
  `local_coverage.py`, `pgstac.py`
- `backend/earthx/discovery/materialize.py`
- `backend/earthx/readers/cog.py`, `backend/earthx/readers/zarr_reader.py`
- `.importlinter`
- `backend/tests/earthx/adapters/test_dispatch.py`

**Außen**
- EODAG: https://github.com/CS-SI/eodag. Die Dateien sind in §9 verlinkt,
  abgerufen am 30.09.2026.
- stac-fastapi-eodag: https://github.com/CS-SI/stac-fastapi-eodag
- pystac-client: https://github.com/stac-utils/pystac-client
- openEO-Prozesse: https://github.com/Open-EO/openeo-processes
