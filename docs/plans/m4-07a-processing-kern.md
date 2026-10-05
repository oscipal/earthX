# M4-07a — Kern: Rezept, Hash, Operator-Registry, Blockschleife, Lesen im Worker: Plan

**Aufgabe:** M4-07a aus `docs/plans/m4-processing-kern.md` §4.
**Stufe B** — Plan zur Freigabe; die Session hält nach diesem Dokument an.
**Ort im Repo:** `docs/plans/m4-07a-processing-kern.md`
**Grundlagen:** `adr/0014` §4–§8, §13, §15a, §15b; `adr/0013` §5.3, §5.5, §9
(Kind ruft `worker_environment()`, Abbruch im nächsten Block);
`plans/m4-processing-kern.md` §1.1b (R3), §1.2, „Gemeinsam für M4-06 bis
M4-15“, M4-07a; `architekturplan.md` 3.1, 7.1–7.3; `KLAERUNGEN.md` B8, B9,
B10; `plans/m3-18-download-deckel-maske.md` §10.3, §11, §13. Code in
`access/resolve.py`, `access/download.py`, `readers/cog.py`,
`readers/zarr_reader.py`, `gateway/gdal.py`, `gateway/policy.py`,
`catalog/registry.py`, `catalog/datasets.py`, `catalog/collection.py`.

---

## 1. Ergebnis in drei Sätzen

`earthx.processing` bekommt die Modelle für Auftrag, Rezept und Provenienz
samt Kanonisierung `c1` und Cache-Schlüssel, eine Operator-Registry aus
strikten pydantic-Modellen, einen Planer mit Kostenschätzung und
`run(recipe, *, workdir, progress)`, das ein Rezept blockweise (1024 px) über
die vorhandenen `readers` liest, die Skalierungsregel F7/F7a anwendet und eine
COG im Arbeitsordner schreibt. `readers` bekommt die Fabrik
`read_access_for(hrefs)` mit `process_gdal_options()` und eine generische
Option, Zarr ohne CF-Dekodierung zu öffnen. Die Registry bekommt das Flag
`reprojection` (R3); konkrete Operatoren gibt es erst mit M4-09 und M4-10,
hier nur einen Test-Operator im Testbaum.

---

## 2. Stand vor dieser Aufgabe (gelesen, 05.10.2026, `main` nach PR #118)

- **`processing`** ist ein leeres Paket (nur Docstring). Es darf `access`,
  `readers` und `catalog` importieren (`.importlinter`, Vertrag
  `processing`); `no-database-in-worker-core` zählt Ketten und verbietet
  `psycopg`. Ein Import von `access.resolve` und `access.download` lädt heute
  kein `psycopg`, `psycopg_pool`, `asyncpg` oder `botocore` (geprüft per
  `sys.modules`), wohl aber `httpx` über `readers → gateway` (erlaubt, B9).
- **Lesen:** `access.open_asset_ref` macht aus einem `ResolvedAsset` ein
  `AssetPath` (über `check_url`) bzw. ein `ZarrAsset`. `CogReader` und
  `ZarrReader` weisen alles andere ab. `_open_group` öffnet Zarr mit
  xarray-Standard, also mit CF-Dekodierung (`readers/zarr_reader.py` Z. 638).
- **GDAL-Optionen:** `gateway.gdal.gdal_options(policy)` hängt nur von den
  Zeitlimits der `Policy` ab, nicht von der Allowlist (Z. 31–54).
- **Schreiben in Blöcken** gibt es schon im Zuschnitt:
  `access.download._write_native_windowed_cog` (1024er Blöcke, je Band eigenes
  `nodata`, `cog_translate` mit Deflate). Der Zuschnitt reprojiziert nach
  EPSG:4326; der Kern liest dagegen im Raster der Eingabe, ohne Warp
  (`adr/0014` §7.2).
- **Kostenschätzung:** `access.download.estimate_output_dims` und
  `plan_outputs` rechnen aus AOI, `gsd` und Datentyp.
- **Registry:** `Capabilities` hat sieben Flags ohne Vorgabe, kein
  `reprojection` (`registry.py` Z. 156–169). `collection.py` gibt alle Flags
  als `earthx:capabilities` aus, das Frontend liest davon nur `time_range`.
- **Abhängigkeiten:** pydantic 2.13.5, numpy, numexpr 2.14.2 und rio-cogeo
  7.0.3 stehen schon in `backend/requirements.lock`. M4-07a braucht **keine
  neue Abhängigkeit** und ändert keine Lock-Datei.
- **Ausgangslage grün:** `pytest` aus der Repo-Wurzel 1918 bestanden (mit
  Postgres der Session), `ruff check backend` sauber, `lint-imports`
  12 Verträge gehalten.

---

## 3. Umsetzung

### 3.1 `processing/recipe.py` — Modelle, Kanonisierung, Hash (§4)

**Modelle** (pydantic, `strict=True`, `extra="forbid"`, `allow_inf_nan=False`,
`frozen=True`; Literal statt Enum, damit Strict-Modus und JSON-Schema
dasselbe sagen):

- `RecipeRequest` (Auftrag): `recipe_version`, `inputs` (Name, Datensatz,
  `groups`, `assets`), `aoi`, `steps` (`op`, `op_version`, `params`), `output`.
  Keine Adresse.
- `Recipe` (Rezept): wie der Auftrag, dazu je Eingabe `resolved`, eine Liste
  aus `ResolvedInput`:
  - `asset`: die Felder von `access.ResolvedAsset`, unverändert (§4.2). Ein
    Test hält die Feldmengen gleich; umgewandelt wird über den Dataclass, damit
    seine eigenen Prüfungen laufen.
  - `version`: `{"kind": "file:checksum" | "etag" | "updated", "value": str}`
    oder `null` (§4.6).
  - `bands`: je Band `data_type`, `nodata`, `scale`, `offset` aus dem Item.
  - `scaling`: `"item"`, `"store-cf"` oder `"none"` (F7a, „Quelle im Rezept“).
    Geprüft im Modell: `item` nur mit Skalierung in `bands`; `store-cf` nur
    für `reader="zarr"`; `none` nur für `reader="cog"` (für Zarr ohne
    Skalierung im Item gilt immer die CF-Dekodierung, die nichts tut, wenn der
    Store keine Attribute trägt).
  - `gsd`: Bodenauflösung aus dem Item oder `null` (neu gegenüber der Skizze
    §4.2, F6 unten; die Kostenschätzung braucht sie, und der Kern sieht das
    Item nicht).
  - `recipe_id`: optional, wird nicht gehashed (§9, F15; setzt M4-07b).
- `output`: Union über `kind` — `raster` (`format: "cog"`, `dtype`) für Jobs
  und `crop` (§10.1) für `recipe.json` des synchronen Zuschnitts. `run`
  rechnet nur `raster`; `crop` ist da, damit M4-07b und M4-14 `processing`
  nicht anfassen müssen.
- `aoi`: GeoJSON `Polygon` oder `MultiPolygon` in EPSG:4326, endliche
  Koordinaten im Wertebereich, gültig nach shapely.
- `Provenance`: `execution` (`cloud`/`local`), `runner_version`,
  `self_attested`, `engine` (Versionen), angewandte Skalierung je Eingabe,
  Start- und Endzeit, Attribution. Den Kern füllt `RunResult` (§3.4), den Rest
  die Hülle.
- `recipe_version` 1; eine unbekannte Version, ein unbekannter Operator oder
  eine nicht geführte `op_version` ist ein benannter Fehler (`422` macht daraus
  erst `api`).

**Parsen** (`parse_recipe(raw: bytes | str, operators)`), §4.4 Schritte 1–2:
erst `json.loads` mit Haken, die doppelte Schlüssel, `NaN`, `Infinity` und
nicht endliche Zahlen abweisen; dann `model_validate_json(strict=True)`. Danach
validiert jeder Schritt `params` mit dem Modell seines Operators und ersetzt sie
durch dessen `model_dump(mode="json")`. So gilt die Regel „float-Feld ist immer
float“ auch innerhalb der Parameter.

**Kanonisierung `c1`** genau nach §4.4 (Regeln 1–8): `model_dump(mode="json")`
ohne `recipe_id`, `-0.0` → `0.0` rekursiv, `json.dumps(sort_keys=True,
separators=(",", ":"), ensure_ascii=False, allow_nan=False)`, SHA-256 über
UTF-8, Präfix `c1:`.

- `recipe_hash(recipe) -> str` — der Kern aus §4.5.
- `cache_key(recipe, engine=engine_versions()) -> str | None` — Kern plus
  Block `engine`; `None`, sobald eine Eingabe kein `version` trägt (Q11).
- `engine_versions()`: `earthx.processing` als ganze Zahl `ENGINE_VERSION`
  (steigt, wenn der Kern Ergebnisse ändert, etwa Blockgröße), GDAL, rasterio,
  numexpr (über `importlib.metadata`, ohne Import), numpy (Auflage F3).
- `input_version(item, asset, *, etag=None)`: reine Hilfe nach F4 —
  `file:checksum` am Asset, sonst das übergebene ETag, sonst `updated` am
  Item, sonst `None`. Den `HEAD` stellt M4-07b über `gateway`.

### 3.2 `processing/operators/` — Registry (§5.1–§5.3, §5.6, §5.7)

- `base.py`: `Tier` (`T1`, `T2`), `Requirement` (Capability-Namen,
  Datenklassen, Lizenzstufe), `RasterMeta` (CRS, Transform, Größe, Bänder mit
  Name, Datentyp, `nodata`, Einheit, Skalierung; dazu `resampled: bool` für die
  Ehrlichkeit nach §5.6) und `Operator` wie in der Skizze §5.2, mit zwei
  Abweichungen:
  - statt `estimate` ein `cost_factor(params) -> float`; die Schätzung selbst
    rechnet `plan.py` einmal für alle (§3.3). Die Reprojektion braucht je
    Methode einen Faktor (§5.5), mehr nicht.
  - `run` ist je `kind` typisiert: `pixel` nimmt und gibt `ImageData` (rio-tiler,
    derselbe Typ wie in der Kachel), `grid` bekommt eine geöffnete lokale
    Quelle, das Zielraster und ein Fenster und gibt ein maskiertes Array (§3.4).
- `registry.py`: `OperatorRegistry` als unveränderliches Mapping
  `op → {op_version → Operator}`, `REGISTRY` zunächst leer. `params_schema()`
  gibt JSON Schema 2020-12 aus `model_json_schema()`, `applicable(op, config)`
  gibt die Gründe zurück (leer heißt anwendbar), geprüft gegen die übergebene
  `DatasetConfig`: Capability-Flags, Datenklasse, Lizenzstufe *Processing*
  (B11). Methodenabhängige Zusatzflags (`interpolation` außer bei `nearest`)
  meldet der Operator über eine eigene Funktion `extra_requirements(params)`;
  sie füllt M4-10.
- Der Test-Operator steht nur in `backend/tests/earthx/processing/`.

### 3.3 `processing/plan.py` — Planer, Ausgaberaster, Schätzung (§5.5, §6.1)

- `split_tiers(steps, operators)`: der längste Anfang aus `pixel`-Schritten mit
  `T1` wird Kachelparameter, der Rest Job (§6.1).
- `segments(steps, operators)`: zerlegt die Schritte in Abschnitte „Folge von
  `pixel`-Schritten“ und „ein `grid`-Schritt“; daraus liest `core.py` den Ablauf.
- `output_grid(...)`: Ausgaberaster eines Abschnitts. Für den ersten: Raster
  der Eingabe, beschnitten auf `bbox(AOI) ∩ Rastergrenzen`, an den Pixeln der
  Eingabe ausgerichtet (F9). Für `grid`-Schritte rechnet der Operator selbst
  (`transform`).
- `estimate(recipe, operators) -> CostEstimate`: Eingabepixel und -bytes aus
  AOI, `gsd` und `data_type` über `access.download.estimate_output_dims`;
  Ausgabe über die `transform`-Kette; Dauer = 0,034 s/MB Eingabe + 1 s je
  Asset; Einheiten = Megapixel der Ausgabe × Summe der Faktoren, ohne Schritte
  0,9 (Export, §5.5). Ohne `gsd` die konservative Obergrenze wie
  `plan_outputs`.

### 3.4 `processing/core.py` — `run` und `worker_environment` (§7, §5.4, §5.6)

**Signatur:** `run(recipe, *, workdir: Path, progress, operators=REGISTRY) ->
RunResult`. `operators` ist ein zusätzliches Schlüsselwort mit Vorgabe; die
Signatur aus `adr/0014` §13 bleibt, Tests und später die Komposition für den
Quad-Pol-Operator (§12) geben eine eigene Registry herein.

**Ablauf:**

1. Rezept prüfen (Version, Operatoren, Parameter, F2: Umfang).
2. `read_access_for(alle hrefs)` aus `readers` → `Policy`, GDAL-Optionen,
   ein `CachingResolver` je Lauf (§8).
3. Jede Eingabe einmal öffnen über `access.open_asset_ref` (für
   `scaling="item"` mit `decode_cf=False`), Skalierung prüfen (unten), Raster
   der Assets vergleichen: Für `pixel`-Schritte müssen alle Assets dasselbe
   Raster haben (CRS, Transform, Größe), sonst `GridMismatch`. Bänder über
   verschiedene Auflösungen bringt M4-09 oder ein vorangestellter `grid`-Schritt.
4. Abschnitt für Abschnitt (§3.3):
   - **`pixel`-Abschnitt:** je Block von 1024 px `part()` je Asset im Raster der
     Eingabe (genaues Fenster, kein Warp), zu einem `ImageData` mit Bandnamen
     = Asset-Schlüssel bzw. Variablen zusammengefügt, Skalierung angewandt,
     dann die Kerne der Reihe nach, Ergebnis in ein gekacheltes GeoTIFF im
     Arbeitsordner, `nodata` je Band wie im Zuschnitt (M3-18, Befund B).
   - **`grid`-Abschnitt:** liest nur ein lokales GeoTIFF (F3). Steht er vorn,
     schreibt der Kern zuerst die Eingabe im Ausschnitt nativ in den
     Arbeitsordner (Blockschleife ohne Kern). Dann je Zielblock der Kern des
     Operators; der Blockplan ist fest (1024 px), `tolerance` und
     `warp_mem_limit` legt M4-10 im Operator fest.
   - Nach jedem Block `progress(done, total)`; Abbruch nach F5.
5. Am Ende `cog_translate` mit dem Deflate-Profil des Zuschnitts nach
   `workdir/result.tif`; Zwischendateien werden gelöscht.
6. `RunResult`: Pfad der COG, `RasterMeta` des Ergebnisses, die
   STAC-Eigenschaften nach §5.6 (`proj:code`, `gsd`, `bands`,
   `processing:software`, `processing:lineage`; `processing:expression` setzt
   M4-09; Links mit eigenen URLs setzt M4-08b), angewandte Skalierung je
   Eingabe, Zahl der Blöcke und gültigen Pixel, `engine_versions()`.

**Skalierung (§5.4, F7, F7a, Auslegung fest am 05.10.2026):**

| `scaling` | Reader liest | Vergleich beim Öffnen | angewandt |
|---|---|---|---|
| `item`, COG | roh | Tags `scales`/`offsets` ungleich 1/0 → gleich den Werten im Item, sonst `ScalingMismatch` | Werte aus dem Item |
| `item`, Zarr | roh (`decode_cf=False`) | CF-Attribute `scale_factor`/`add_offset`, falls vorhanden → gleich, sonst `ScalingMismatch` | Werte aus dem Item |
| `store-cf`, Zarr | CF-dekodiert (heutiger Weg) | — | was der Store sagt; Werte stehen in `RunResult` |
| `none`, COG | roh | Tags ungleich 1/0 → `ScalingMismatch` | nichts |

- Verglichen wird auf `math.isclose(rel_tol=1e-9)`, damit Dezimaltext und
  double einander treffen, sonst nichts.
- Angewandt wird mit einer Funktion `apply_scaling(image, bands)`, die
  rio-tilers `unscale` nachrechnet (float32, erst multiplizieren, dann
  addieren, `reader.py` Z. 281–288). M4-09 hängt dieselbe Funktion in die
  Kachel, damit T1 und T2 bitgleich bleiben (§6.3).
- Eine Zahl der Bänder im Item, die nicht zur Datei passt, ist ebenso ein
  benannter Fehler.

**`worker_environment()`:** Kontextmanager um
`rasterio.Env(**process_gdal_options())`. Er wirft, wenn er nicht im
Hauptthread betreten wird, weil die Optionen dann nur threadlokal gälten
(§3.6). Zusätzlich betritt `run` dieselben Optionen auf dem lesenden Thread
(§7.3 Punkt 2). Gelesen wird auf dem aufrufenden Thread; einen zweiten
Lesethread oder einen Vorab-Leser gibt es nicht (§7.2: ein Lesethread je Job).
`GDAL_NUM_THREADS` bleibt ungesetzt.

**Fehler:** eine Basisklasse `ProcessingError` mit benannten Unterklassen
(`UnsupportedRecipe`, `UnknownOperator`, `ScalingMismatch`, `GridMismatch`,
`AoiOutsideInputs`, `RunCancelled`). Texte englisch, kurz, ohne `href`, AOI
oder Hash. `AssetRejected` aus `readers` geht unverändert durch.

**Logs:** Start und Ende je Lauf mit Datensatz, Operatoren, Blöcken, Pixeln und
Dauer — nie `href`, AOI, Hash.

### 3.5 Lokale Dateien: `processing/workfile.py`

Zwischen- und Ergebnisdateien im Arbeitsordner öffnet `processing` nur über
`open_workfile(workdir, name, mode, **profile)`. Es nimmt einen Dateinamen
ohne Pfadtrenner, legt ihn unter `workdir` an und öffnet ihn mit
`rasterio.open`. Das ist die einzige Stelle in `processing` mit
`rasterio.open` (F4, §3.7 AST-Test).

### 3.6 `readers` und `access`

- `readers/access.py` (§8):
  - `process_gdal_options()` = `gateway.gdal.gdal_options(Policy(frozenset()))`
    plus `GDAL_CACHEMAX` (F1).
  - `ReadAccess(policy, gdal_options, resolve)` und `read_access_for(hrefs)`:
    Allowlist = Hosts der Adressen über `gateway.host_of`, ein frischer
    `CachingResolver`. Eine Adresse ohne gültigen Host wird `AssetRejected`
    mit Text ohne Adresse.
- `readers/zarr_reader.py`: `ZarrAsset.decode_cf: bool = True`;
  `zarr_asset(..., decode_cf=True)`; `_open_group` gibt bei `False`
  `mask_and_scale=False` an xarray. Generisch, nicht je Datensatz (F7a).
  Prüfen, dass `nodata` dann aus `_FillValue` kommt.
- `access/resolve.py`: `open_asset_ref(..., decode_cf=True)` reicht die
  Option an `zarr_asset` durch; für COG ohne Wirkung.
- `readers/__init__.py`: Export von `ReadAccess`, `read_access_for`,
  `process_gdal_options`.

### 3.7 Registry: Flag `reprojection` (R3)

- `Capabilities.reprojection: bool`, ohne Vorgabe (B10).
- `catalog/datasets.py`: alle drei Einträge `reprojection=True` mit
  Kommentar auf R3.
- `catalog/collection.py`: in `earthx:capabilities` ausgeben (F7);
  `architekturplan.md` 5.1 Zeile `earthx:capabilities` um „Reprojektion“
  ergänzen.
- Tests: `test_registry.py` (Liste der Pflichtflags), `tests/catalog/conftest.py`,
  `test_collection.py`.

### 3.8 Tests

Neues Verzeichnis `backend/tests/earthx/processing/`, Fixtures synthetisch
nach dem Muster von `mini_cog.py`/`mini_zarr.py` (lokale Datei hinter
`serve_cog` bzw. dem Gateway-Transport der Zarr-Tests):

| Test | belegt | Grundlage |
|---|---|---|
| `test_recipe_hash.py`: feste erwartete Hashwerte für vier synthetische Rezepte; `1`/`1.0`, `-0.0`, `1e-7`, Nicht-ASCII im Wert, andere Schlüsselreihenfolge → gleicher Hash; `recipe_id` ändert den Hash nicht | Kanonisierung `c1` | §4.4, Auflage F2 |
| dazu: doppelte Schlüssel, `NaN`, `Infinity`, `1e400`, `"20"` für float, `1.0`/`true` für int, unbekanntes Feld, unbekannte `recipe_version`/`op`/`op_version`, ungültige AOI → benannte Fehler | zweckfremde Eingaben | §4.3, §4.4, K7 |
| `test_cache_key.py`: `None` ohne Fassung einer Eingabe; Schlüssel ändert sich mit jeder Engine-Version (GDAL, rasterio, numexpr, numpy, `ENGINE_VERSION`), nicht mit `recipe_id`; `input_version` in der Reihenfolge Prüfsumme → ETag → `updated` | §4.5, §4.6, Q11, Auflage F3 | |
| `test_operators.py`: Registry unveränderlich; Schema ist 2020-12 und strikt; `applicable` gegen Flags, Datenklasse und Lizenzstufe; doppelte Registrierung abgewiesen | §5.1–§5.3 | |
| `test_plan.py`: `split_tiers`, `segments`, Ausgaberaster an Pixel ausgerichtet, AOI außerhalb → `AoiOutsideInputs`, Schätzung mit und ohne `gsd` | §5.5, §6.1 | |
| `test_scaling.py`: synthetisches COG mit `scale`/`offset`-Tags und `nodata`, Item mit Offset und Nodata → physikalische Werte, `nodata` maskiert; dazu die vier Fälle aus F7a (Item, `store-cf` mit Mini-Zarr mit CF-Attributen, Item gegen Store abweichend → `ScalingMismatch`, weder Item noch Store aber COG-Tags ≠ 1/0 → `ScalingMismatch`) | §5.4, Auflage F7, F7a | |
| `test_core_run.py`: T2-Lauf des Test-Operators (`pixel`) auf COG und Zarr, Ergebnis-COG gültig (`rio_cogeo` validate), Werte gleich der Rechnung auf dem ganzen Array; Blockgröße ändert nichts; Fortschritt monoton bis `total`; Abbruch im Rückruf → `RunCancelled`, keine Reste im Arbeitsordner; `grid`-Test-Operator nach einem `pixel`-Schritt; verschiedene Raster → `GridMismatch`; fremder Host → `AssetRejected`; Logs ohne `href`, AOI und Hash | §7.2, §5.6, Q8 | |
| `test_no_direct_open.py` (AST, Muster `test_no_outbound_outside_gateway.py`): in `processing` kein Aufruf von `rasterio.open`, `xarray.open_*`, `rioxarray.open_rasterio`, `rio_tiler.io.Reader` (auch nicht über Alias), außer `rasterio.open` in `workfile.py` | §7.3 Punkt 1 | F4 |
| `test_gdal_env_threads.py`: `worker_environment()` im Hauptthread → Option in einem `ThreadPoolExecutor` sichtbar (`rasterio._env.get_gdal_config`); die Lesefunktion des Kerns sieht sie auch ohne `worker_environment()` aus einem Pool-Thread; Betreten außerhalb des Hauptthreads wirft | §7.3 Punkt 2, §3.6 | |
| `test_import_is_pure.py`: frischer Prozess, `import earthx.processing`, danach kein `psycopg`, `psycopg_pool`, `asyncpg`, `botocore`, `earthx.objectstore` in `sys.modules` | B9, Q4, R2 | M4-07a Umfang |
| `test_read_access.py`: Allowlist = Hosts der hrefs, GDAL-Optionen gleich `process_gdal_options()`, `GDAL_CACHEMAX` gesetzt, Adresse ohne Host → `AssetRejected` ohne Adresse im Text | §8 | F11 |
| `test_memory_8192.py`: T2-Lauf des Test-Operators auf synthetischem COG 8192², zwei Bänder `uint16`, im eigenen Prozess (`spawn`), `ru_maxrss` < 300 MB | §3.5, Abnahme | F10 |

Bestehende Tests: `test_zarr_reader.py` um `decode_cf=False` (roh, `nodata`
aus `_FillValue`), `test_registry.py`/`conftest.py`/`test_collection.py` um
das Flag.

### 3.9 Doku und Log

- `architekturplan.md` 5.1: Flag `reprojection` in der Zeile
  `earthx:capabilities`.
- Docstrings der neuen Module verweisen auf die Abschnitte von `adr/0014`.
- `ENTSCHEIDUNGSLOG.md`: nach der Freigabe eine Zeile „M4-07a freigegeben“ mit
  den Antworten auf F1–F10, dazu je eine Zeile für Antworten, die über
  `adr/0014` hinausgehen (F1, F4, F5).
- `m4-processing-kern.md` §3: Stand von M4-07a nach dem Merge (macht der Chat
  bzw. M4-20; hier nicht).

---

## 4. Nicht in dieser Aufgabe

- Annahme in `api` (Items holen, `resolve_asset`, `HEAD` für ETag,
  Host-Prüfung gegen `asset_hosts`, `recipe_id`): M4-07b.
- Band-Math, Prüfung der Ausdrücke (R5), Mehr-Asset-Pfad im `tiler`,
  `processing:expression`: M4-09. Reprojektion samt `tolerance`,
  `warp_mem_limit` und Faktoren je Methode: M4-10.
- Queue, Kindprozess, Upload, Cache-Treffer, SSE: M4-08a, M4-08b.
- Mosaik mehrerer Items und mehrere Gruppen (F2): M4-11, M4-12.
- AOI-Maskendatei neben dem Ergebnis: M4-11.
- `recipe.json`, `citation.bib`, `sci:doi`: M4-14.
- `.importlinter`, `gateway`, `api`, `jobs`, `datasets/` bleiben unberührt.
  Kein Frontend.

---

## 5. Umfang und Commits

Geschätzt rund 1200 Zeilen Code und 1000 Zeilen Tests, also weit über dem
Richtwert von 400 Zeilen (F8). Commits, je ein Thema:

1. `readers`: `read_access_for`, `process_gdal_options`, Zarr `decode_cf`
   (mit `access.open_asset_ref`)
2. `catalog`: Flag `reprojection` (R3), Collection, Architekturplan 5.1
3. `processing`: Rezeptmodelle, Parsen, Kanonisierung, Hash, Cache-Schlüssel
4. `processing`: Operator-Registry und `applicable`
5. `processing`: Planer und Kostenschätzung
6. `processing`: `workfile`, Blockschleife, Skalierung, `run`,
   `worker_environment`
7. Tests zu Reinheit, AST und GDAL-Threads
8. Speichermessung 8192² und Plan-Nachtrag mit Ergebnissen

Vor dem Fertigmelden: `main` holen, `pytest`, `ruff check backend`,
`PYTHONPATH=backend lint-imports --config .importlinter`; Ergebnisse im PR.

---

## 6. Risiken

- **Grenze 300 MB bei `GDAL_CACHEMAX` 256 MB.** §3.5 hat 1024er Blöcke nur mit
  64 MB (148 MB Spitze) und mit Standard (400 MB) gemessen, nicht mit 256 MB.
  Ein Lauf über 268 MB Rohdaten füllt einen 256-MB-Cache voraussichtlich ganz
  [A]; mit 70 MB für den Prozess läge die Spitze dann über 300 MB. Deshalb F1.
- **Fernlesen gegen die Messung.** Die Abnahmemessung liest eine lokale Datei.
  Über `/vsicurl/` kommt je geöffneter Datei bis zu `VSI_CACHE_SIZE` (64 MB)
  dazu. Das nennt der PR als Grenze der Messung.
- **`XarrayReader.part` im nativen Raster.** Dass `part()` mit dem Raster der
  Eingabe ohne Resampling liest, ist für COG über das Fenster klar, für Zarr
  am Code zu prüfen; der Test „gleich der Rechnung auf dem ganzen Array“ deckt
  beides.
- **`mask_and_scale=False`** ändert, woher `nodata` kommt. Ein eigener Test im
  Reader belegt es; scheitert er, kommt der Punkt als Frage zurück.
- **Größe des PR** (F8).

---

## 7. Fragen an Otto

**F1 — `GDAL_CACHEMAX` im Worker (§3.6, §6)**
1. 64 MB, wie in §3.5 gemessen (148 MB Spitze); der PR misst zusätzlich
   256 MB und nennt beide Zahlen **(Empfehlung)**
2. 256 MB wie in `adr/0014` §7.2 vorgeschlagen; die Abnahmegrenze 300 MB ist
   dann voraussichtlich nicht zu halten
3. 128 MB

**F2 — Umfang von `run` in M4-07a (§3.4)**
1. Eine Eingabe, eine Gruppe, ein Item mit beliebig vielen Assets; mehr wird
   mit `UnsupportedRecipe` abgewiesen, bis M4-11 und M4-12 es brauchen. Das
   Schema erlaubt es schon **(Empfehlung)**
2. Mehrere Gruppen schon jetzt, je Gruppe eine Ergebnisdatei

**F3 — Wovon ein `grid`-Schritt liest (§3.4)**
1. Nur von einem lokalen GeoTIFF im Arbeitsordner. Steht er vorn, schreibt der
   Kern die Eingabe vorher im Ausschnitt nativ dorthin. Fernlesen bleibt an
   einer Stelle, COG und Zarr gehen gleich **(Empfehlung)**
2. Direkt von der Quelle über den Reader (`WarpedVRT` auf dem COG-Dataset,
   eigener Weg für Zarr); spart eine lokale Kopie

**F4 — Lokale Dateien und AST-Test (§3.5, §7.3 Punkt 1)**
1. Die vier Öffner sind in `processing` ganz verboten; einzige Ausnahme ist
   `rasterio.open` in `workfile.py`, das nur einen Dateinamen unter `workdir`
   annimmt **(Empfehlung)**
2. Wörtlich nach §7.3: verboten ist nur ein Aufruf mit einer Zeichenkette als
   Literal

**F5 — Abbruch (§3.4, `adr/0013` §5.5)**
1. `progress(done, total)` je Block; die Hülle bricht ab, indem der Rückruf
   `processing.RunCancelled` wirft. Der Kern räumt den Arbeitsordner auf und
   wirft weiter **(Empfehlung)**
2. Der Rückruf gibt `False` zurück, der Kern wirft dann selbst

**F6 — Ergänzungen zur Skizze §4.2 (§3.1)**
1. Je aufgelöster Eingabe zusätzlich `scaling` (Quelle nach F7a) und `gsd`
   (für die Schätzung); `recipe_id` optional und ohne Einfluss auf den Hash;
   `output` als Union aus `raster` und `crop` **(Empfehlung)**
2. Ohne `gsd`; die Schätzung bekommt die Items als eigenes Argument (in
   `api`), der Kern schätzt nicht

**F7 — Flag `reprojection` nach außen (§3.7)**
1. In der Registry und in `earthx:capabilities` der Collection; den
   Frontend-Typ ergänzt M4-13 **(Empfehlung)**
2. Nur in der Registry

**F8 — Größe des PR (§5)**
1. Ein PR wie im Aufgabenschnitt, rund 2200 Zeilen mit Tests, in acht
   thematischen Commits, die einzeln lesbar sind **(Empfehlung)**
2. Zwei PRs: M4-07a-1 (Rezept, Hash, Registry, Flag, Planer) und M4-07a-2
   (`readers`, Blockschleife, Skalierung, `run`); ändert den Schnitt aus R1

**F9 — Ausdehnung des Ergebnisses (§3.3)**
1. `bbox(AOI) ∩ Rastergrenzen` im Raster der Eingabe; Pixel außerhalb des
   Polygons bleiben wie im Zuschnitt erhalten (M3-18 §11). Der Kern sieht keine
   Footprints, die Rastergrenze ersetzt sie; eine AOI-Maske ist Sache von
   M4-11 **(Empfehlung)**
2. Zusätzlich außerhalb des Polygons auf `nodata` setzen

**F10 — Speichermessung 8192² (§3.8)**
1. Als Test in der normalen Suite, im eigenen Prozess (geschätzt 20–40 s und
   rund 200 MB in `tmp_path`) **(Empfehlung)**
2. Nur als Messskript mit Ergebnis im PR; in der Suite ein kleiner Lauf (2048²)
   mit anteiliger Grenze
