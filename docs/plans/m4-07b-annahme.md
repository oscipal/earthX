# M4-07b — Annahme in `api`: Auftrag → Rezept, Fassung, Host-Prüfung: Plan

**Aufgabe:** M4-07b aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — **von Otto am 07.10.2026 freigegeben** mit F1–F8 je Option 1 und
Auflagen zu `gateway.head()`, F5 und F6 (§8). Wo §3 und §8 sich widersprechen,
gilt §8.
**Ort im Repo:** `docs/plans/m4-07b-annahme.md`
**Grundlagen:** `adr/0014` §4.1, §4.2, §4.3, §4.6, §4.7, §5.3, §5.4 (F7a),
§8 (Allowlist), §10.1, §15a, §15b; `adr/0013` §9 Punkt 2;
`plans/m4-processing-kern.md` §1.1 (Q8, Q11), §1.2, „Gemeinsam für M4-06 bis
M4-15“, M4-07b; `plans/m4-07a-processing-kern.md` §3.1, §4, §8;
`plans/m4-01a-zugriffsaufloesung.md`; `architekturplan.md` 3.1, 7.1;
`KLAERUNGEN.md` B8, B10, B11. Code in `processing/recipe.py`,
`processing/operators/registry.py`, `access/resolve.py`, `access/download.py`,
`api/item_source.py`, `api/tiler.py`, `gateway/client.py`, `gateway/policy.py`,
`catalog/registry.py`, `adapters/eopf_stac.py`, `adapters/cop_dem_bucket.py`.

---

## 1. Ergebnis in drei Sätzen

Ein neues Modul `api/intake.py` macht aus einem Auftrag (JSON-Text) ein
vollständiges `processing.recipe.Recipe`: Es validiert den Auftrag, holt die
Items über die Item-Quelle aus M4-01a, löst jedes Asset mit
`access.resolve_asset` auf, prüft jeden Host gegen `asset_hosts` seines
Datensatzes, übernimmt Bandangaben, Skalierungsquelle und `gsd`, bestimmt die
Fassung je Eingabe nach F4 (Prüfsumme, sonst ETag per `HEAD` über `gateway`,
sonst `updated`), prüft `applicable` für jeden Schritt und vergibt eine
zufällige `recipe_id`. Daneben baut es `recipe.json` für den synchronen
Zuschnitt (`steps: []`, §10.1) als Bytes, ohne dass `access.download`
`processing` importiert. Routen gibt es keine; M4-08b, M4-14 und M4-15 rufen
diese Funktionen auf.

---

## 2. Stand vor dieser Aufgabe (gelesen, 07.10.2026, `main` nach PR #122)

- **Rezeptmodelle (M4-07a, PR #120):** `parse_request(raw, operators)` prüft
  I-JSON und validiert den Auftrag strikt; `recipe_from_data(data, operators)`
  baut ein `Recipe` über denselben JSON-Weg. `ResolvedInput` verlangt `asset`,
  `version`, `bands`, `scaling` und `gsd`; das Modell prüft selbst, dass
  `scaling` zur Bandliste passt (`item` nur mit Skalierung in `bands`,
  `store-cf` nur für Zarr, `none` nur für COG). `Input` prüft, dass `resolved`
  genau ein Eintrag je Item und Asset hat. `recipe_id` ist optional, 22
  Zeichen, nicht im Hash. `input_version(item, asset, *, etag=None)` ist die
  reine Hilfe nach F4; „den `HEAD` stellt M4-07b über `gateway`“.
  `cache_key` gibt `None`, sobald eine Eingabe kein `version` trägt (Q11).
- **Operator-Registry:** `REGISTRY` ist leer bis M4-09/M4-10;
  `applicable(operator, config, params)` liefert die Gründe, warum ein
  Operator nicht passt (Flags, Datenklasse, Lizenzstufe). Tests nutzen die
  Test-Operatoren aus `tests/earthx/processing/testops.py`.
- **Item-Quelle (M4-01a):** `api.item_source.build_item_source` liefert
  `ItemSource(dataset_id, item_id)`; sie hängt heute nur am `tiler`
  (`app.state.earthx_item_source`). Die Fehlerabbildung auf HTTP steht in
  `api/tiler.py::_fetch_item` (404, 501, 502, 503, 504), samt Prüfung, dass
  das Item die erfragte `id` trägt.
- **Auflösung:** `access.resolve_asset` ist rein und prüft keinen Host
  (`access/resolve.py`, „without fetching or checking anything“). Der
  `tiler` verlässt sich auf die Prozess-Policy, die Vereinigung aller
  `asset_hosts` und Endpunkte (`api/dependencies.py::policy_from_registry`).
  Eine Prüfung **je Datensatz** gibt es noch nirgends.
- **`gateway`** kennt nur `get` und `post_json`. Ein `HEAD` ginge heute durch
  `_read`, und das weist eine Antwort ab, deren `Content-Length` über
  `max_response_bytes` (8 MB) liegt — bei einer DEM-Kachel in der Regel.
  `_log` schreibt je Anfrage Host und Pfad, nie die Query.
- **Zuschnitt:** `api/tiler.py::download_crop` filtert je Gruppe mit
  `filter_items_intersecting_aoi` (bbox) und `compute_crop_region`
  (Footprints); Gruppen ohne Berührung fallen weg, erst ohne Gruppe gibt es
  `400`. Deckel: `MAX_DOWNLOAD_ITEMS` 25. `_asset_gsd` in `access/download.py`
  liest `gsd` aus Asset, `raster:bands` oder Item (privat).
- **Bandangaben der drei Datensätze** [P, Code und Fixtures]:
  - `sentinel-2-c1-l2a`: STAC 1.0, `raster:bands` je Asset mit `nodata`,
    `data_type`, `scale`, `offset`; `file:checksum` am Asset (`adr/0014`
    §17.1).
  - `sentinel-2-l2a-zarr3`: STAC 1.1; der Adapter normalisiert `nodata` und
    `data_type` am Asset zu **einem** Eintrag `raster:bands` ohne Namen und
    `bands` zu `eo:bands` (`adapters/eopf_stac.py::_normalize_asset`). Keine
    Skalierung, keine Prüfsumme, `properties.updated` am Item.
  - `cop-dem-glo-30`: eigene Items (`cop_dem_bucket._item`), kein
    `raster:bands`, keine Prüfsumme, kein `updated`, `properties.gsd` 30.
- **Importregeln:** `api` hat keinen eigenen Vertrag und darf `processing`,
  `access`, `gateway`, `adapters` und `catalog` importieren. Keine Regel
  ändert sich.

---

## 3. Umsetzung

### 3.1 `gateway`: `Gateway.head(url)`

- Neue Methode `head(url, *, retry=True) -> GatewayResponse` mit leerem
  `content`. Dieselben Prüfungen wie `get`: `check_url` je Sprung, Redirects
  hier verfolgt, Grenze je Host, `UpstreamError` ab Status 400.
- In `_once` wird bei `HEAD` kein Rumpf gelesen und die Größenprüfung von
  `_read` entfällt; es gibt keinen Rumpf, den sie begrenzen könnte.
- Das Log bleibt wie bei jeder Anfrage (Host, Pfad, Status, ohne Query); F7.
- Keine Lockerung: Allowlist, Schema, Port, private Adressen und Redirects
  laufen unverändert durch `check_url`.

### 3.2 `access/download.py`: `asset_gsd` öffentlich

`_asset_gsd` wird zu `asset_gsd` (Umbenennung, Aufrufer angepasst, kein
Re-Export). Die Annahme braucht genau diese Regel, damit Schätzung im Job und
Deckel im Zuschnitt dieselbe Bodenauflösung sehen.

### 3.3 `api/intake.py` — die Annahme

**Öffentliche Namen:**

```python
class OrderRefused(Exception):
    status_code: int        # 400, 403, 413, 422, 501, 502, 503, 504
    detail: str             # Englisch, kurz, ohne AOI, href oder Hash

@dataclass(frozen=True, slots=True)
class AcceptedOrder:
    recipe: Recipe                  # mit recipe_id
    cacheable: bool                 # cache_key(recipe) is not None (Q11)
    skipped_items: tuple[str, ...]  # wie im Zuschnitt ausgelassen (F4)

async def accept_order(
    raw: bytes | str, *, registry: DatasetRegistry, operators: OperatorRegistry,
    item_source: ItemSource, gateway: Gateway,
) -> AcceptedOrder

def check_recipe_hosts(recipe: Recipe, registry: DatasetRegistry) -> None

def crop_recipe_json(
    config: DatasetConfig, *, groups: Sequence[Sequence[Mapping[str, Any]]],
    assets: Sequence[str], aoi: Mapping[str, Any], resolution_factor: int,
    accepted_at: datetime,
) -> bytes
```

**Ablauf von `accept_order`** (jede Stufe weist mit `OrderRefused` ab, bevor
die nächste etwas kostet):

1. **Auftrag parsen:** `parse_request(raw, operators)`. `RecipeInvalid` und
   `UnknownOperator` → `422` mit dem geschwärzten Text aus `processing`
   (Felder und Gründe, nie Werte). Ein Dokument mit `resolved` oder
   `recipe_id` ist kein Auftrag (F1).
2. **Deckel ohne Netz** (F5): eine Eingabe; höchstens 25 Items
   (`MAX_DOWNLOAD_ITEMS`), 16 Assets je Eingabe, 16 Schritte. Darüber `413`
   bzw. `422`.
3. **Datensatz und Operatoren ohne Netz:** `adapters.dataset_config` (Regel I;
   unbekannt → `422`, weil der Datensatz im Rumpf steht, nicht im Pfad);
   Lizenzstufe *Processing* (B11, wie der Zuschnitt) → sonst `403`; für jeden
   Schritt `applicable(operator, config, params)`, die Gründe im Text → `422`.
   Ein Datensatz, dem ein Operator nicht passt, kostet so keine Anfrage an die
   Quelle.
4. **Items holen:** je Item-ID einmal über `item_source`, nebenläufig. Die
   Fehlerabbildung ist die aus `api/tiler.py::_fetch_item`, mit `422` statt
   `404` für ein unbekanntes Item (es steht im Rumpf); ein Item mit fremder
   `id` → `502`. Die Abbildung wandert dafür in eine gemeinsame Funktion in
   `api/intake.py`, die `_fetch_item` nur noch in `HTTPException` übersetzt —
   eine Stelle statt zwei.
5. **AOI gegen Items** (F4): je Gruppe `filter_items_intersecting_aoi` und
   `compute_crop_region` wie im Zuschnitt. Gruppen ohne Berührung fallen weg
   und stehen in `skipped_items`; bleibt keine Gruppe, `422` „the AOI does not
   touch any of the given items“. Das Rezept enthält nur, was gerechnet wird.
6. **Auflösen je Item und Asset:** `resolve_asset(item, config, asset)`
   (`NoReader` → `501`, `InvalidAssetKey` und `AssetNotOnItem` → `422`,
   `MalformedItem` → `502`).
7. **Host-Prüfung** (§8): `gateway.inspect_url(href,
   Policy(allowed_hosts=config.source.asset_hosts))` je `ResolvedAsset` —
   prüft Schema `https`, keine Zugangsdaten, Port 443, Host in der Liste
   **dieses** Datensatzes, Länge. Ohne Netz. Abweichung → `502` mit dem Text
   des `tiler` („the item points at a host this dataset does not declare
   (asset_hosts)“): Die Adresse kommt aus dem Item der Quelle, nicht vom
   Auftraggeber.
8. **Bandangaben, Skalierungsquelle, `gsd`** (F3, §3.4).
9. **Fassung** (F2): `file:checksum` am Asset ohne Anfrage; sonst für
   `reader="cog"` ein `HEAD` über `gateway` (nebenläufig, die Grenze je Host
   in `gateway` gilt); sonst `updated`. Aufgerufen wird
   `processing.recipe.input_version` mit dem ETag. Ein schwaches ETag
   (`W/…`) oder eines über 256 Zeichen zählt nicht. Fehlerfälle nach F6.
10. **Rezept bauen:** `recipe_from_data` mit `recipe_id =
    secrets.token_urlsafe(16)` (128 Bit, `adr/0013` §9 Punkt 2), danach
    `check_recipe_hosts` als Gegenprobe. `cacheable = cache_key(recipe) is not
    None`.
11. **Log:** eine Zeile `order accepted` mit `recipe_id`, Datensatz, Zahl der
    Items und Assets, Operatoren und `cacheable`; bei Abweisung `order
    refused` mit Status und Stufe. Nie AOI, `href`, Item-Geometrie oder Hash.

**`check_recipe_hosts`** prüft ein fertiges `Recipe`: Datensatz bekannt, jeder
Host nach Schritt 7. Abweichung → `400` („the recipe names an address its
dataset does not declare“). Die Annahme ruft sie als Gegenprobe; M4-08b ruft
sie vor dem Einreihen, M4-19 vor dem erneuten Start eines gespeicherten
Rezepts. So wird ein Rezept mit fremden Adressen nie durchgereicht, gleich
woher es kommt (§8).

### 3.4 Bandangaben und Skalierungsquelle (F3)

Generisch, ohne Code je Datensatz (Auflage F7):

- **Liste am Item-Asset:** `raster:bands` (raster v1: `scale`, `offset`,
  `nodata`, `data_type`), sonst `bands` (STAC 1.1: `raster:scale`,
  `raster:offset`, `nodata`, `data_type`).
- **Zarr-Schlüssel mit Variablen** (`SR_10m:b04,b08`): ein Eintrag je
  Variable. Tragen die Einträge Namen, wird nach Name zugeordnet; ein
  einzelner Eintrag ohne Namen beschreibt das ganze Asset und gilt für jede
  Variable (so liefert ihn der EOPF-Adapter); sonst je Variable ein leerer
  Eintrag (alle Felder `null`).
- **Ohne Liste** (DEM): `bands: []`.
- **Ungültige Werte** (Skalierung als Text, nicht endlich, unbekannter
  `data_type`) → `502`, Item nicht intakt. Still verwerfen hieße still anders
  rechnen (K7).
- **`scaling`:** `item`, sobald ein Eintrag `scale` oder `offset` trägt;
  sonst `store-cf` für Zarr, `none` für COG. Das ist genau die Regel, die
  `ResolvedInput` selbst prüft.
- **`gsd`:** `access.download.asset_gsd(item, item_asset)`.

Erwartet je Datensatz (Tests in §3.6):

| Datensatz | `bands` | `scaling` | `version` | Anfragen |
|---|---|---|---|---|
| `sentinel-2-c1-l2a` | aus `raster:bands`, mit `scale`/`offset` | `item` | `file:checksum` | keine |
| `sentinel-2-l2a-zarr3` | ein Eintrag je Variable (`nodata`, `data_type`) | `store-cf` | `updated` | keine |
| `cop-dem-glo-30` | `[]` | `none` | `etag` | 1 `HEAD` je Kachel |

### 3.5 `crop_recipe_json` (§10.1)

- Baut aus den **schon gefilterten** Gruppen des Zuschnitts dasselbe Schema:
  eine Eingabe `input`, `steps: []`, `output: {"kind": "crop", "format":
  "cog", "resolution_factor": n, "extent": "bbox(aoi ∩ footprints)", "mask":
  "file"}`.
- Auflösung, Host-Prüfung und Bandangaben wie §3.3 Schritte 6–8; Fassung nur
  ohne Anfrage (`file:checksum`, `updated`), für das DEM `null` (§10.1: ein
  `HEAD` je Kachel lohnt für eine Begleitdatei nicht). Deshalb synchron.
- Ohne `recipe_id` und ohne Hash (§10.1). Dazu ein Block `provenance`:
  `execution: "cloud"`, `kind: "sync-download"`, `self_attested: false`,
  `engine_versions()`, `started = accepted_at`, Attribution mit demselben
  Text, den `build_notice_text` wählt. `scaling: []`, weil der Zuschnitt
  nichts skaliert.
- Ausgabe: UTF-8, zwei Leerzeichen Einzug, Schlüssel sortiert. Die Datei ist
  die des Nutzers, kein Hash-Eingang.
- Die AOI kommt ohne `properties` hinein; deren Herkunft steht weiter in
  `aoi.geojson` und `ATTRIBUTION.txt`.
- Eingebaut in den Zuschnitt wird es erst in M4-14.

### 3.6 Tests

Alle synthetisch, ohne Netz; die Item-Quelle ist eine Funktion im Test, das
`HEAD` ein `httpx.MockTransport` hinter einem echten `Gateway` mit festem
Resolver. Operatoren aus `tests/earthx/processing/testops.py`.

- `tests/earthx/gateway/test_client_head.py`: ETag kommt an; große
  `Content-Length` ohne `ResponseTooLarge`; Redirect auf fremden Host
  abgewiesen; `404` → `UpstreamError`; `503` wird wiederholt.
- `tests/earthx/api/test_intake.py`:
  - **je Datensatz** ein synthetisches Item nach der Form der echten Quelle
    (Tabelle §3.4): Fassung, Bandangaben, Skalierungsquelle, `gsd`; Zahl der
    `HEAD`-Anfragen 0, 0 bzw. 1 je Kachel.
  - **Fassung:** ohne ETag oder bei schwachem ETag → `updated` bzw. `null`;
    `cacheable` falsch, sobald eine Eingabe `null` trägt; Fehlerfälle nach F6.
  - **Host-Prüfung:** Asset auf einem Host eines anderen Datensatzes, auf
    einem Subdomain-Trick (`evil-host.example` gegen `host.example`), mit
    `http`, Port oder Zugangsdaten → `502`; `check_recipe_hosts` auf einem
    Rezept mit fremdem `href` → `400`; ein Dokument mit `resolved` → F1.
  - **zweckfremd:** unbekannter Datensatz, unbekanntes Item, Item mit fremder
    `id`, Operator unbekannt oder nicht anwendbar (Flag aus, Lizenzstufe
    *Display*), Parameter ungültig, AOI ohne Überschneidung, Deckel
    überschritten, unbekannter Asset-Schlüssel, Zarr-Schlüssel ohne Trenner,
    ungültige Skalierung am Item, Datensatz ohne Reader (`LEGACY`).
  - **Auslassen wie im Zuschnitt:** eine Gruppe ohne Berührung steht in
    `skipped_items`, nicht im Rezept.
  - **`recipe_id`:** 22 Zeichen, je Auftrag neu, nicht im Hash (zwei Annahmen
    desselben Auftrags: gleicher `recipe_hash`, verschiedene `recipe_id`).
  - **Logs:** `caplog` über die ganze Annahme (auch `earthx.gateway`): kein
    Eintrag enthält eine AOI-Koordinate, einen vollständigen `href` oder
    `c1:`.
  - **`crop_recipe_json`:** gültig nach `parse_recipe`, `steps == []`, kein
    `recipe_id`, kein Hash, DEM-Fassung `null` ohne Anfrage, `provenance`
    vollständig, mehrere Gruppen.
- `test_tiler.py` / `test_item_id_mismatch.py`: unverändert grün nach dem
  Umzug der Fehlerabbildung (§3.3 Schritt 4).

### 3.7 Doku und Log

- Docstring von `api/intake.py` verweist auf `adr/0014` §4.1, §4.6, §8, §10.1.
- `architekturplan.md` 3.1, Zeile `api`: Nachtrag mit Datum „Annahme von
  Aufträgen (`api/intake.py`)“.
- `ENTSCHEIDUNGSLOG.md` nach der Freigabe: „M4-07b freigegeben“ mit den
  Antworten; je eine Zeile für Antworten, die über `adr/0014` hinausgehen.
- `m4-processing-kern.md` §3: Stand von M4-07b auf den PR.

---

## 4. Nicht in dieser Aufgabe

- Routen, Rumpfgröße, `Prefer`, `jobID`, SSE: M4-08b. Welcher Prozess die
  Annahme ausführt (die Item-Quelle hängt heute nur am `tiler`), entscheidet
  M4-08b.
- Prüfung, ob `processing.run` das Rezept schon rechnen kann (mehrere Items,
  `crop`): bleibt in `processing` (`UnsupportedRecipe`); M4-08b entscheidet,
  ob es das vor dem Einreihen fragt.
- Einbau von `recipe.json` und `citation.bib` in den Zuschnitt, `sci:doi`:
  M4-14.
- Erneuter Start über eine gespeicherte `recipe_id`: M4-19.
- Lizenzkombination mehrerer Datensätze (architekturplan 7.1): F5.
- `processing`, `jobs`, `datasets/`, `.importlinter` und das Frontend bleiben
  unberührt.

---

## 5. Umfang und Commits

Geschätzt rund 350 Zeilen Code (`api/intake.py` etwa 280, `gateway` 30,
Umzug der Fehlerabbildung und Umbenennung 40) und 550 Zeilen Tests, also
über dem Richtwert von 400 Zeilen. Ein Teilen lohnt nicht: Ohne `HEAD` gibt
es keine Fassung für das DEM, ohne Annahme keinen Aufrufer für `HEAD`.
Commits, je ein Thema:

1. `gateway`: `head()` ohne Rumpf und Größenprüfung, mit Tests
2. `access`: `asset_gsd` öffentlich
3. `api`: Fehlerabbildung der Item-Quelle an einer Stelle
4. `api`: `accept_order` und `check_recipe_hosts`
5. `api`: `crop_recipe_json`
6. Tests der Annahme je Datensatz und für zweckfremde Aufträge
7. Doku und Log

Vor dem Fertigmelden: `main` holen, `pytest`, `ruff check backend`,
`PYTHONPATH=backend lint-imports --config .importlinter`; Ergebnisse im PR.

---

## 6. Risiken

- **Fassung bei Annahme, nicht beim Lesen** (`adr/0014` §4.6 Restrisiko):
  Ändert sich das DEM zwischen `HEAD` und Lauf, trägt das Ergebnis die ältere
  Fassung. Steht in der Provenienz als „Fassung bei Annahme“; bei Archivdaten
  selten.
- **Ein `HEAD` je Kachel:** Ein DEM-Auftrag über 25 Kacheln kostet 25
  Anfragen in der Annahme; die Grenze je Host in `gateway` (6) bremst sie.
  Messung an der echten Quelle nicht in der Session (gesperrt, §1.2); belegt
  wird der Ablauf mit dem Mock.
- **Bandangaben bei Zarr:** Die Zuordnung „ein Eintrag ohne Namen gilt für
  jede Variable“ stimmt für den EOPF-Adapter, wie er heute normalisiert.
  Liefert eine Quelle später je Variable eigene Einträge ohne Namen in anderer
  Zahl, gibt es leere Einträge statt falscher; Skalierung kommt dann aus dem
  Store (`store-cf`).
- **`skipped_items` statt Abweisung** (F4) heißt: Das Rezept kann weniger
  Items enthalten als der Auftrag. Die Antwort von M4-08b muss das zeigen.

---

## 7. Fragen an Otto

**F1 — Eingereichtes Rezept statt Auftrag (§3.3 Schritt 1, `adr/0014` §8)**
1. Die Annahme nimmt nur Aufträge. Ein Dokument mit `resolved` oder
   `recipe_id` wird mit `400` abgewiesen, der Text sagt, dass der Auftrag ohne
   Adressen zu schicken ist. `check_recipe_hosts` sichert jedes Rezept vor dem
   Einreihen zusätzlich ab **(Empfehlung)**
2. Ein eingereichtes Rezept wird auf seinen Auftrag zurückgeführt und neu
   aufgelöst; seine Adressen und Fassungen werden verworfen

**F2 — Wann ein `HEAD` gestellt wird (§3.3 Schritt 9, F4 in `adr/0014`)**
1. Nur für `reader="cog"` ohne `file:checksum`. Ein Zarr-`href` ist eine
   Gruppe aus vielen Objekten; ein ETag darauf beschreibt nicht die Daten,
   also gilt dort `updated`. Regel nach Leserart, nicht je Datensatz
   **(Empfehlung)**
2. Für jedes Asset ohne `file:checksum`; bei EOPF kostet das je Asset eine
   Anfrage ohne ETag (gemessen, `adr/0014` §3.1)
3. Neues Registry-Feld je Datensatz, ob ein ETag zählt (ohne Vorgabe, B10)

**F3 — Bandangaben eines Zarr-Schlüssels mit Variablen (§3.4)**
1. Ein Eintrag je Variable: Zuordnung nach Name, ein einzelner Eintrag ohne
   Namen gilt für jede Variable, sonst leere Einträge; ungültige Werte → `502`
   **(Empfehlung)**
2. Für Zarr immer leere Einträge; die Skalierung kommt stets aus dem Store

**F4 — AOI berührt nicht jedes Item (§3.3 Schritt 5)**
1. Wie der Zuschnitt (M3-17): Gruppen ohne Berührung fallen weg und werden in
   `skipped_items` genannt; erst ohne Gruppe `422`. Ein `recipe.json` des
   Zuschnitts und das Rezept eines Jobs über dieselbe Auswahl beschreiben dann
   dasselbe **(Empfehlung)**
2. Streng: Jedes Item muss die AOI berühren, sonst `422` mit den Item-IDs

**F5 — Deckel und mehrere Eingaben (§3.3 Schritt 2)**
1. Eine Eingabe je Auftrag, bis die Lizenzkombination (architekturplan 7.1)
   entschieden ist; höchstens 25 Items (wie der Zuschnitt), 16 Assets und 16
   Schritte. M4-11 und M4-12 heben die Item-Grenze mit eigener Begründung
   **(Empfehlung)**
2. Mehrere Eingaben zulassen, jede einzeln gegen ihre Lizenzstufe geprüft; die
   Kombinationsregel kommt später

**F6 — `HEAD` scheitert (§3.3 Schritt 9)**
1. Eine Antwort ab `400` (das Objekt fehlt oder ist gesperrt) → `502`, der Job
   scheiterte sonst später. Zeitüberschreitung, `5xx` oder nicht erreichbar →
   Fassung `null`, also kein Cache-Treffer, mit Warnung im Log (Datensatz,
   Item, Asset, Fehlerklasse) **(Empfehlung)**
2. Jeder Fehler → Fassung `null`
3. Jeder Fehler → `502`

**F7 — Log der `HEAD`-Anfrage (§3.1)**
1. Wie jede Anfrage in `gateway`: Host und Pfad, ohne Query. Die Abnahme
   „kein Log enthält AOI oder `href`“ prüft AOI-Koordinaten und den
   vollständigen `href`; Item-IDs mit Kachelnamen stehen schon heute im Log
   der Item-Abrufe **(Empfehlung)**
2. `HEAD` loggt ohne Pfad, weil ein DEM-Kachelname die Lage auf ein Grad
   genau verrät

**F8 — Form der Abweisung (§3.3)**
1. Eine Klasse `OrderRefused` mit Status und geschwärztem Text, die Tabelle
   der Status steht in `api/intake.py`; M4-08b übersetzt sie in einer Zeile in
   `HTTPException` **(Empfehlung)**
2. Fachliche Fehlerklassen je Fall; die Abbildung auf Status macht M4-08b

---

## 8. Freigabe (Otto, 07.10.2026) und Umsetzung

F1–F8 je Option 1, mit diesen Auflagen. Sie gehen §3 vor.

- **`gateway.head()`:** Ein Test belegt, dass `head()` dieselben Prüfungen
  durchläuft wie `get`: `check_url`, Grenze je Host, Weiterleitungen mit
  Prüfung jedes Ziels, keine private Adresse; Gegenprobe mit abgewiesenen
  Adressen. → `tests/earthx/gateway/test_client_head.py` (30 Fälle: Schema,
  Port, Zugangsdaten, Namenstricks, IP-Literale, zu lange URL, privater Name,
  Weiterleitung auf fremden Host und auf private Adresse, Schleife, Grenze
  von sechs je Host, Wiederholung, Zeitüberschreitung, kein Query im Log). Eine
  Gegenprobe mit herausgenommener Körper-Ausnahme lässt zwei der Tests scheitern.
- **F6 enger:** 404 und 410 weisen den Auftrag mit `502` ab. Jede andere
  Antwort ab 400, jede `5xx` und eine Zeitüberschreitung lassen die Fassung
  leer (kein Cache-Treffer); eine Warnung steht im Log ohne Query und ohne
  Adresse. Tests für 404, 410, 403, 405, 503 und Zeitüberschreitung; dazu
  Weiterleitung auf fremden Host. Ein gescheitertes `HEAD` fällt **nicht** auf
  `updated` zurück: leer heißt leer.
- **F5:** `MAX_ORDER_ITEMS = 25`, `MAX_ORDER_ASSETS = 16`, `MAX_ORDER_STEPS = 16`
  als Konstanten an einer Stelle (`api/intake.py`). M4-12 darf die Grenze für
  Items mit Begründung anheben; sie hängt bewusst nicht an
  `MAX_DOWNLOAD_ITEMS`.

**Wie umgesetzt, wo es von §3 abweicht oder es genauer sagt:**

- Die Fehlerabbildung der Item-Quelle steht in `api/intake.py::fetch_item` und
  wirft `OrderRefused`; `api/tiler.py::_fetch_item` übersetzt sie in einer
  Zeile. Der Parameter `not_found` trennt `404` (Pfad) von `422` (Rumpf).
- `skipped_items` nennt jedes Item, das die AOI nicht berührt, auch innerhalb
  einer Gruppe, die bleibt. Der Zuschnitt lässt solche Items ebenfalls weg,
  nennt aber nur ganze Gruppen; das Rezept ist hier genauer.
- `check_recipe_hosts(recipe, registry)` ruft `check_recipe_hosts_of(recipe,
  config)`; `crop_recipe_json` nutzt die zweite für seine bekannte
  Konfiguration.
- Der Auftrag für einen Job verlangt eine Ausgabe `raster`; `crop` ist nur für
  `crop_recipe_json` da (`422`).
- Ein Operator, der nicht in `T2` läuft, ist als Job abgewiesen (`422`).
- `access.download.attribution_text` ist neu und gemeinsam für
  `build_notice_text` und `recipe.json`; `asset_gsd` ist öffentlich
  (Umbenennung).
- Der Test der Logs setzt `httpx` wie die Produktion auf `WARNING`
  (`earthx/logging.py`): Der Logger von `httpx` schreibt sonst die URL, bei
  `HEAD` ohne Query.
