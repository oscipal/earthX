# M4-01a — Zugriffsauflösung nach `access`, eine Item-Quelle in `api`: Plan

**Aufgabe:** M4-01a aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — Plan zur Freigabe; die Session hält nach diesem Plan an.
**Ort im Repo:** `docs/plans/m4-01a-zugriffsaufloesung.md`
**Grundlagen:** `adr/0011` §6.1–§6.5, §7 (D2), §11 (F2, F4, F7);
`plans/m4-processing-kern.md` §1.1 (Q1), §1.2, M4-01a; `architekturplan.md`
3.1; `KLAERUNGEN.md` B8, B9; `ENTSCHEIDUNGSLOG.md` E5 und „Kettenzählung“ vom
20.09.2026; Code in `backend/earthx/api/tiler.py`,
`api/federating_client.py`, `api/main.py`, `readers/cog.py`,
`readers/zarr_reader.py`, `catalog/pgstac.py`.

---

## 1. Ergebnis in drei Sätzen

Die Auflösung „Item + Registry-Eintrag + Asset-Schlüssel → Reader-Eingabe“
zieht aus `api/tiler.py` nach `access/resolve.py`, geteilt in einen reinen
Schritt (`resolve_asset` → serialisierbares `ResolvedAsset`) und das Öffnen
(`open_asset_ref`), ohne dass `access` etwas aus `gateway` importiert.
Möglich wird das durch eine eigene Fehlerklasse `AssetRejected` in `readers`.
Die Item-Quelle zieht aus `api/tiler.py` in `api/item_source.py`; das Routing
„föderiert oder materialisiert“ liest danach überall die Python-Registry, und
`api` gleicht beim Start die `item_holding` mit pgstac ab.

---

## 2. Stand vor dieser Aufgabe (gelesen, 02.10.2026, `main` nach PR #110)

- **Ausgangslage grün:** `pytest` aus der Repo-Wurzel 1769 bestanden (mit
  Postgres der Session, also samt T-C), `ruff check backend` sauber,
  `lint-imports` 12 Verträge gehalten.
- **Auflösung heute** (`api/tiler.py`): `_resolve_asset_path` (Z. 356) mit
  `_resolve_asset_href` (Z. 136), `_proj_code` (Z. 183), `_target_gsd`
  (Z. 207) und `_READABLE_FORMATS`. Sie wirft direkt `HTTPException`:
  501 (Format ohne Reader), 400 (`split_asset_key` wirft `UrlRejected`), 404
  (Asset fehlt am Item), 502 (jeder `GatewayError` beim Öffnen). Genutzt von
  `dataset_asset_path` (Kachel, Statistik, Info, Punkt, TileJSON) und
  `download_crop._crops_for`.
- **Item-Quelle heute** (`api/tiler.py`): `build_item_source` (Z. 760) mit
  `MaterializedItemNotFound` und `MaterializedCatalogUnavailable`, Routing aus
  der Python-Registry. `_fetch_item` übersetzt die Fehler in HTTP.
- **Routing in `api`** (`federating_client.py`): `_source_info_of` (Z. 613)
  liest `item_holding` und `time_range` aus dem pgstac-Dokument; ein fehlendes
  oder unbekanntes `item_holding` ist eine `500`. `get_item` (Z. 515) holt
  föderierte Items über `adapters.get_item` mit Vorgabe `REGISTRY`,
  materialisierte über `super().get_item` (stac-fastapi, mit Links).
- **`readers`**: `split_asset_key`, `split_asset_href` und `zarr_asset` werfen
  `UrlRejected`; `asset_path` und `zarr_asset` lassen jeden Fehler aus
  `check_url` durch (`UrlRejected`, `AddressRejected`, `UrlTooLong`, …).
- **`api/main.py`** baut die App ohne Registry-Parameter (`REGISTRY` fest).
  Die T-C-Tests `test_api_materialized.py`, `test_api_search_time_axis.py`
  und `test_api_mixed_search.py` laden eigene Collections nach pgstac, die
  nicht in `REGISTRY` stehen, und starten dann diese App — ihr Routing hängt
  heute am pgstac-Dokument.

---

## 3. Umsetzung

### 3.1 `readers`: eigene Fehlerklasse

- Neu `readers/errors.py`: `class AssetRejected(UrlRejected)`. Weil sie von
  `UrlRejected` (und damit `GatewayError`) erbt, fangen `api` und die
  bestehenden Tests sie unverändert.
- `split_asset_key`, `split_asset_href` und die eigenen Abweisungen in
  `zarr_asset` werfen `AssetRejected`. `asset_path` und `zarr_asset` fangen
  jeden `GatewayError` aus `check_url` und werfen ihn als `AssetRejected`
  weiter (`raise … from error`, Text unverändert, nennt keine Adresse). Damit
  gilt „werfen nur noch sie“ wörtlich, und `access` muss nur eine Klasse
  kennen. Die HTTP-Antwort bleibt `502`, weil `api` dort heute schon jeden
  `GatewayError` gleich behandelt.
- `readers/__init__.py` exportiert `AssetRejected` sowie `Policy` und
  `Resolver` als Typen, damit `access` Signaturen schreiben kann, ohne
  `gateway` zu importieren (`adr/0011` §6.4: „Neu-Export aus `readers`“).

### 3.2 `access/resolve.py`

```python
@dataclass(frozen=True, slots=True)
class ResolvedAsset:
    dataset_id: str
    item_id: str
    asset: str                       # der Schlüssel der Anfrage, z. B. "SR_10m:b04"
    reader: Literal["cog", "zarr"]
    href: str
    variable: str | None             # nur Zarr mit variable_separator
    crs: str | None                  # proj:code bzw. proj:epsg des Items

    def to_json(self) -> dict[str, Any]: ...
    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> ResolvedAsset: ...

def resolve_asset(item: Mapping[str, Any], config: DatasetConfig, asset: str) -> ResolvedAsset: ...
def open_asset_ref(ref: ResolvedAsset, policy: Policy, resolve: Resolver, *,
                   target_gsd: float | None = None) -> AssetPath | ZarrAsset: ...
def target_gsd(request: Request, stac_item: Mapping[str, Any]) -> float | None: ...
```

- **`resolve_asset`** ist rein (kein Netz, keine Policy) und übernimmt die
  Logik von `_resolve_asset_path` ohne `check_url`: Reader nach
  `config.format`, Zarr-Trenner über `split_asset_key`, `href` des
  Item-Assets, CRS aus `proj:code`/`proj:epsg`. Eigene Fehlerklassen in
  `access`, die `api` auf die heutigen Codes abbildet:

  | Klasse | heute | Fall |
  |---|---|---|
  | `NoReader` | 501 | Format ohne Reader (`LEGACY`) |
  | `InvalidAssetKey` | 400 | `split_asset_key` weist ab (fängt `AssetRejected` aus `readers`) |
  | `AssetNotOnItem` | 404 | Item trägt das Asset nicht |

- **`ResolvedAsset.from_json`** prüft streng: unbekannte oder fehlende
  Felder, falsche Typen, `reader` außerhalb von `cog`/`zarr`, `variable` bei
  `cog` → `ValueError`. Kein Vorgabewert für ein Feld (B10). Der Host wird
  hier **nicht** geprüft; das bleibt allein `check_url` beim Öffnen (eine
  zweite, schwächere Prüfung ohne DNS wäre eine zweite Wahrheit).
- **`open_asset_ref`** reicht an `readers.asset_path` bzw.
  `readers.zarr_asset` durch; Fehler kommen als `AssetRejected`.
- **`target_gsd`** (bisher `_target_gsd`) und `_COARSEST_LEVEL` ziehen mit;
  Verhalten und Signatur bleiben.
- **Importe:** aus `catalog` nur `catalog.registry`; aus `readers` die
  Funktionen, Typen und `AssetRejected`; aus `gateway` nichts, auch nicht als
  Typ. Ein Test belegt in einem frischen Interpreter, dass der Import von
  `earthx.access.resolve` weder `psycopg` noch `earthx.catalog.datasets`
  oder `earthx.catalog.pgstac` lädt (Kettenregel für `processing`), und ein
  AST-Test, dass `access/resolve.py` keinen Import aus `earthx.gateway` und
  aus `catalog` nur `catalog.registry` hat.

### 3.3 `api/tiler.py`

- `_resolve_asset_path` bleibt als dünne Hülle mit gleicher Signatur: ruft
  `resolve_asset` und `open_asset_ref` und übersetzt `NoReader`/
  `InvalidAssetKey`/`AssetNotOnItem`/`AssetRejected` in 501/400/404/502 mit
  den heutigen Texten. Kachel und Download rufen sie wie bisher.
- `_resolve_asset_href`, `_proj_code`, `_target_gsd`, `_READABLE_FORMATS` und
  die Item-Quelle verschwinden aus `tiler.py`.

### 3.4 `api/item_source.py`

- Zieht aus `tiler.py`: `build_item_source`, `MaterializedItemNotFound`,
  `MaterializedCatalogUnavailable`.
- Neu `item_holding_of(registry, dataset_id) -> ItemHolding` (wirft
  `UnknownCollection`), die eine Stelle für „föderiert oder materialisiert“.
- Neu `check_item_holdings(registry, conn)`: liest `id` und
  `earthx:source.item_holding` aller Collections aus pgstac (neue Abfrage
  `catalog.pgstac.read_item_holdings`, async, auf derselben Verbindung wie
  `fetch_item`) und wirft `ItemHoldingMismatch` mit den abweichenden
  Collection-IDs (keine AOI, keine Adresse). Umfang siehe F2.
- `api/main.py`: bekommt `build_app(registry=REGISTRY)` wie der `tiler`
  (für Tests mit eigener Registry), legt `earthx_registry` und
  `earthx_item_source` auf `app.state` und ruft im Lifespan
  `check_item_holdings`; ein Fehler bricht den Start ab.
- `api/tiler.py`: ruft den Abgleich im Lifespan nur, wenn ein Pool da ist;
  ohne Datenbank startet er wie heute (E5).

### 3.5 `api/federating_client.py`

- `_source_info_of` holt das Collection-Dokument weiter über
  `get_collection` (Regel I: unbekannt → pgstac-404 wie bisher) und liest
  `time_range` weiter daraus; nur `item_holding` kommt aus
  `item_holding_of(request.app.state.earthx_registry, …)`. Eine Collection in
  pgstac, die die Registry nicht kennt, bleibt eine `500` mit Hinweis auf
  `item_holding` (wie heute ein Dokument ohne gültiges Feld).
- `get_item`: Routing über `item_holding_of`; föderiert über
  `app.state.earthx_item_source` (dieselbe Funktion wie Kachel und Download),
  Fehlerabbildung über `_adapter_error_to_http` unverändert. Materialisiert
  siehe F3.

### 3.6 Tests

- **Neu, rein:** `resolve_asset` mit synthetischen Items für COG, Zarr ohne
  und mit `variable_separator`, ein materialisiertes Item (DEM-Form);
  Fehlerfälle: Format ohne Reader, Asset fehlt, `assets` kein Objekt, `href`
  kein String, Schlüssel ohne Variable, kein CRS am Item.
- **Neu, Serialisierung:** Hin- und Rückweg über `json.dumps`/`json.loads`
  für COG und Zarr; `from_json` weist zusätzliche, fehlende und falsch
  getypte Felder, unbekannten `reader` und `variable` bei `cog` ab.
- **Neu, Öffnen:** `open_asset_ref` liefert `AssetPath` bzw. `ZarrAsset`
  wie bisher `_resolve_asset_path`; ein fremder Host wirft `AssetRejected`
  und bleibt als `UrlRejected` fangbar.
- **Neu, Startabgleich:** reine Tests von `check_item_holdings` mit falscher
  Verbindung (gleich, abweichend, Collection ohne Feld); ein T-C-Test gegen
  das Postgres der Session, dass `api` mit abweichender `item_holding` nicht
  startet.
- **Bestehend:** alle Tests zu Kachel und Download inhaltlich unverändert
  grün, auch 400 gegen 502 (`test_tiler_zarr_group_addressing.py`). Was sich
  an ihnen ändern muss, steht in F1.
- `lint-imports` grün, `.importlinter` unverändert.

### 3.7 Doku und Log

- Docstring am Kopf von `api/tiler.py` nachziehen (Zusammensetzung jetzt aus
  `access.resolve` und `api.item_source`).
- `ENTSCHEIDUNGSLOG.md`: je eine Zeile für die Freigabe dieses Plans mit den
  Antworten und für die Umsetzung, ans Ende.
- `m4-processing-kern.md` §3: Stand M4-01a.

---

## 4. Nicht in dieser Aufgabe

- Wer im Worker `Policy` und GDAL-Konfiguration baut (`adr/0014`).
- Adapter-Signaturen, `AdapterSpec`, `adapters/errors.py`, `harvest_run`
  (M4-01b). Deshalb ruft die Item-Quelle `adapters.get_item` weiter mit
  `dataset_id` und `registry=`.
- `time_range` aus der Registry statt aus pgstac: nicht Teil des Routings;
  bleibt wie heute.
- `.importlinter`, Registry-Felder, Verhalten der Routen.

---

## 5. Umfang und Commits

Geschätzt rund 350 Zeilen Produktivcode geändert, davon etwa 200 nur
verschoben (`tiler.py` → `access/resolve.py`, `api/item_source.py`), dazu
rund 350 Zeilen neue Tests. Damit liegt der PR über dem Richtwert von 400
Zeilen (F4). Geplante Commits, je eine Sache:

1. `readers`: `AssetRejected` und Umstellung der Würfe.
2. `access/resolve.py` mit Tests; `tiler.py` nutzt es.
3. `api/item_source.py` aus `tiler.py`; Tests umziehen.
4. Routing in `federating_client` aus der Registry; `build_app(registry)` in
   `api/main.py`; T-C-Tests auf eigene Registry.
5. Startabgleich mit Tests.
6. Doku, Log, Stand im M4-Plan.

---

## 6. Risiken

| Risiko | Umgang |
|---|---|
| Ein Fehler aus `check_url` ändert durch das Umhüllen seinen Typ, und eine Stelle fängt den Untertyp | geprüft: außerhalb `gateway` fängt nur `adapters/earth_search_coverage.py` `UrlTooLong`, und zwar aus dem eigenen `Gateway`-Aufruf, nicht aus `readers`; `__cause__` bleibt erhalten |
| T-C-Tests mit eigenen Collections routen nach dem Umbau nicht mehr | sie bauen die App mit eigener Registry (§3.4); Assertions bleiben |
| Startabgleich hält `api` an, weil in pgstac eine alte Collection liegt | Umfang nach F2; Fehlermeldung nennt die IDs und `python -m earthx.catalog.load` |
| `processing` erreicht über `access.resolve` doch `psycopg` | Test im frischen Interpreter (§3.2) |

---

## 7. Fragen an Otto

**F1: Bestehende Tests, die private Namen aus `api.tiler` importieren**
(`_target_gsd` in `test_tiler_zarr_group_addressing.py`; `build_item_source`,
die zwei Fehlerklassen und die `monkeypatch`-Ziele `earthx.api.tiler.fetch_item`
/ `…get_item` in `test_tiler.py`)
1. Nur Importzeilen und `monkeypatch`-Ziele anpassen, Assertions bleiben;
   die Item-Quellen-Tests ziehen nach `test_item_source.py`. Keine Re-Exporte
   am alten Ort (B6) **(Empfehlung)**
2. Re-Exporte in `api/tiler.py` behalten, damit die Testdateien byte-gleich
   bleiben

**F2: Umfang des Startabgleichs in `api`**
1. Start scheitert, wenn eine Collection in Registry **und** pgstac eine
   andere `item_holding` trägt. Eine Collection nur in pgstac: Warnung im Log
   beim Start, `500` je Anfrage (heute nur, wenn ihr das Feld fehlt; mit
   gültigem Feld wird sie heute geroutet). Ein Eintrag nur in der Registry:
   nichts (Regel I, pgstac-404) **(Empfehlung)**
2. Streng: auch eine Collection nur in pgstac lässt den Start scheitern.
   Folge: ein aus der Registry entfernter Datensatz blockiert `api`, bis seine
   Collection gelöscht ist; die T-C-Tests mit kaputten Collections
   (`TestUnrecognisedItemHolding`) werden zu Starttests
3. Wie 2, zusätzlich scheitert ein Registry-Eintrag ohne Collection in pgstac

**F3: Einzelabruf eines materialisierten Items über die STAC-API**
1. bleibt bei `super().get_item` (stac-fastapi, mit dessen Links und
   404-Text); nur die Routing-Entscheidung und der föderierte Abruf laufen
   über `api/item_source.py`. Die Antwort der Route bleibt byte-gleich
   **(Empfehlung)**
2. auch materialisiert über die Item-Quelle (`catalog.pgstac.fetch_item`) und
   Links selbst setzen; ändert Links und 404-Text der Route

**F4: PR-Größe** (rund 700 Zeilen mit Tests und Verschiebungen)
1. ein PR wie im M4-Plan, mit getrennten Commits nach §5 **(Empfehlung)**
2. zwei PRs: erst §3.1–§3.3 (Zugriffsauflösung), dann §3.4–§3.5 (Item-Quelle)
