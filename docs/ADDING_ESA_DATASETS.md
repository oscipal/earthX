# ADDING_ESA_DATASETS — Hard Constraints und Anleitung für neue Datensätze

> **Herkunft:** Diese Datei entstand am 13.08.2026 in einem Planungs-Chat, nachdem das Repo `oscipal/biomass-viewer` geklont und inspiziert wurde. Sie wurde damals nur als Download geliefert und nie ins Repo gelegt. Diese Fassung ist am 18.09.2026 aus dem Chatverlauf rekonstruiert.
>
> **Wortgetreu übernommen:** Regeln 1 bis 6, Abschnitt 1, Abschnitt 2 (Grundfassung), Backend-Schritte 1 bis 6 und 8 bis 10, Frontend-Schritte, Definition of Done.
> **Sinngemäß rekonstruiert** (spätere Überarbeitungsrunden, Wortlaut nicht vollständig verfügbar): Regel 7, das Feld `format` und der Abschnitt zu Zarr.
>
> **Überholt durch die neueren Pläne:** Der damalige Geltungsbereich "nur ESA-Datensätze" ist eine offene Entscheidung (Projektplan Abschnitt 10). Regel 5 erlaubte token-pflichtigen Pixelzugriff nach BIOMASS-Muster; nach aktuellem Prinzip werden vorerst **nur token-freie Quellen** angebunden. Die sieben Hard Constraints selbst gelten unverändert.
>
> **Abschnitt 1 beschreibt den Code-Stand vom 13.08.2026.** Vor der Arbeit am Repo gegen den aktuellen Stand prüfen.

---

## 0. Hard constraints — read before writing any code

1. **Never change the request/response contract of an existing endpoint**
   in a way that breaks the current frontend: `/api/search`, `/api/download`,
   `/api/tiles/{item_id}/{z}/{x}/{y}.png`, `/api/decompose`, `/api/stitch`,
   `/api/coverage`, `/api/config`, `/api/asset`, `/api/geocode`. Extend with
   new **optional** fields/params only. If a breaking change seems
   necessary, stop and ask the user first — do not silently ship it.
2. **Never generalize `decomp.py` / the `DecompMethod`/`DECOMPS` frontend
   logic into a cross-dataset feature.** It implements BIOMASS SCS-specific
   polarimetric decomposition (complex quad-pol single-look data). If a new
   dataset has an analogous but different processing need, create a
   **new, separately named module** for it — do not repurpose or rename the
   existing one, even if the math looks similar.
3. **Never remove or repoint the current hardcoded BIOMASS defaults**
   (`stac_catalog_url`, `stac_collections`, `default_quicklook_asset`,
   `default_cog_asset`, `asset_host_allowlist`, the MAAP OIDC settings).
   After adding multi-dataset support, calling the API exactly as today
   (no `dataset` param) must behave **identically** to today — BIOMASS is
   the implicit default dataset.
4. **Never rename or change the signature of existing public functions**
   in a backward-incompatible way (`stac.search`, `stac.get_catalog`,
   `store.register_item`, `store.asset_href`, `cog.crop_to_aoi`,
   `cog.stitch_to_aoi`, `auth.get_access_token`). Add new **optional**
   parameters with defaults that preserve current behavior.
5. **Do not assume a new source is token-free.** Verify per source.
   Some ESA/Copernicus catalogs allow open STAC *search* but require
   credentials for *asset/pixel* access. *(Stand heute: Solche Quellen
   werden vorerst nicht angebunden. Wenn eine Quelle für Suche oder Zugriff
   ein Konto verlangt, vor der Umsetzung beim Nutzer nachfragen.)*
6. **One feature, one dataset, unless proven otherwise.** Don't add a
   checkbox/toggle/UI element that silently applies to all datasets. Every
   dataset-specific capability (decomposition, a special product view, a
   custom band index, a custom auth flow) must be explicitly gated by
   dataset id.
7. **Coverage map is mandatory for every dataset.** *(rekonstruiert)* Every
   dataset must expose a footprint layer through `/api/coverage`. A dataset
   without a working, correctly labeled coverage map is not done. The
   existing BIOMASS coverage behavior must stay identical.

---

## 1. Architecture as inspected on 2026-08-13

- `backend/app/config.py` — single `Settings` object: one STAC catalog URL,
  one token, one collections list, one asset host allowlist, one set of
  default asset keys.
- `backend/app/stac.py` — STAC search against **one** hardcoded catalog
  (`pystac_client.Client.open(settings.stac_catalog_url)`).
- `backend/app/auth.py` — MAAP-specific OIDC offline-token exchange logic.
- `backend/app/store.py` — in-process/on-disk item registry, keyed by
  `item_id` only (no dataset dimension yet).
- `backend/app/cog.py` — COG tile/crop reading over HTTP range requests,
  injects the (single) Bearer token via GDAL env.
- `backend/app/decomp.py` — BIOMASS SCS-only polarimetric decomposition.
- `backend/app/routes/*.py` — thin FastAPI routers calling the above
  (`search`, `decompose`, `download`, `tiles`, `coverage`, `meta`, `assets`,
  `stitch`, `geocode`).
- `frontend/src/products.ts` — BIOMASS product definitions
  (`GN`, `DGM`, `FH`, `FD`, `SCS`), decomposition methods, band mapping,
  all BIOMASS-specific.
- `frontend/src/api.ts`, `types.ts` — typed API client tied to the current
  single-dataset response shape.

Nothing here is dataset-parameterized today. That's fine — it's a working
single-dataset app. The goal is to add a **dataset dimension**, not to
rewrite what already works.

---

## 2. Target pattern: a dataset registry

Introduce one new module, `backend/app/datasets.py`, holding a small
registry of dataset configs. Each entry replaces the current global
`Settings` fields that were BIOMASS-only:

```python
# backend/app/datasets.py (new file)
from dataclasses import dataclass, field

@dataclass(frozen=True)
class DatasetConfig:
    id: str                          # e.g. "biomass"
    label: str                       # human-readable, for /api/config and UI
    stac_catalog_url: str
    collections: list[str]
    requires_token: bool
    asset_host_allowlist: list[str]
    default_quicklook_asset: str
    default_cog_asset: str
    format: str = "cog"              # "cog" | "zarr" — drives reader dispatch (später ergänzt)
    features: set[str] = field(default_factory=set)  # e.g. {"decompose", "stitch", "coverage"}

DATASETS: dict[str, DatasetConfig] = {
    "biomass": DatasetConfig(
        id="biomass",
        label="ESA BIOMASS",
        stac_catalog_url="https://catalog.maap.eo.esa.int/catalogue/",
        collections=["BiomassLevel2a", "BiomassLevel2b", "BiomassLevel1a", "BiomassLevel1b"],
        requires_token=True,
        asset_host_allowlist=["maap.eo.esa.int"],
        default_quicklook_asset="quicklook_png",
        default_cog_asset="enclosure_i_abs_tiff",
        features={"decompose", "stitch", "coverage"},
    ),
    # New datasets get added here, one entry each.
}

DEFAULT_DATASET = "biomass"
```

Key rule: **the `"biomass"` entry's values must be copied verbatim from the
current `config.py` defaults**, so behavior doesn't change. Die Werte oben
stammen aus der Inspektion vom 13.08.2026 und sind vor Verwendung gegen
`config.py` zu prüfen.

`config.py` keeps its current fields (for backward compatibility and
because settings that are genuinely global, like cache size, CORS origins,
geocoder URL, stay in `Settings`), but the STAC-specific fields become
sourced from `datasets.DATASETS[dataset_id]` instead.

### Formats *(sinngemäß rekonstruiert)*

Format preference: **Zarr > COG > legacy formats.** Zarr sources get a new
module `zarr_reader.py`, separate from `cog.py`; `cog.py`'s core paths are
not extended to handle Zarr. `DatasetConfig.format` selects the reader.
Top candidate at the time: EOPF Sentinel Zarr Samples Service (ESA-operated,
Zarr, STAC catalog, Zarr assets readable without credentials).

---

## 3. Backend checklist

1. **Add the registry** as in §2, with the `"biomass"` entry matching
   current `config.py` exactly.
2. **Verify the new source's access model** before writing an entry:
   is STAC search really open? Does asset access need a token? Document this
   in a code comment on the `DatasetConfig` entry, same style as the
   docstring in `auth.py`.
3. **Auth**: if a dataset ever needs its own credential flow, do **not**
   hardcode it into `auth.py`'s MAAP-specific exchange function. Either
   parameterize `auth.py`'s functions by dataset, or add a new, separate
   function (e.g. `auth.get_access_token_for(dataset_id)`) rather than
   branching inside the existing MAAP-specific function.
4. **`stac.py`**: add a `dataset: str = datasets.DEFAULT_DATASET` parameter
   to `search()`, `get_catalog()`, `coverage_features()`. Resolve
   `stac_catalog_url`/`collections` from `datasets.DATASETS[dataset]`
   instead of `get_settings()`. Existing callers (no `dataset` arg) must
   keep working unchanged.
5. **`store.py`**: extend `register_item`/the registry schema to also store
   `dataset` per item, so `/tiles`, `/download`, `/asset`, `/decompose`,
   `/stitch` can look up the *correct* dataset's `asset_host_allowlist` and
   token — not the global BIOMASS one — when resolving assets for an item
   from a different dataset.
6. **Routes**: add an optional `dataset` field to `SearchRequest` (and to
   `DownloadRequest`/`DecomposeRequest`/`StitchRequest` where relevant),
   defaulting to `datasets.DEFAULT_DATASET`. Existing request bodies
   without this field must behave exactly as today.
7. **Coverage map — mandatory for every dataset** (§0 rule 7).
   `stac.py` is format-agnostic — it only reads STAC item geometries, not
   pixel data — so the same coverage logic works for `format="zarr"` and
   `format="cog"` datasets without a new reader module. Two things must
   change to make it work per-dataset instead of BIOMASS-only:
   - `coverage_features()` and the `/api/coverage` route need the same
     `dataset` parameter as `search()` (step 4 above), resolving the
     catalog from `datasets.DATASETS[dataset]` instead of the global
     settings.
   - The on-disk cache filename in `routes/coverage.py`
     (currently `{collection}.geojson`) must include the dataset id too
     (e.g. `{dataset}__{collection}.geojson`), so two datasets that happen
     to reuse a collection name don't collide.
8. **Dataset-specific processing** (a new decomposition, a new band-math
   step, anything analogous to `decomp.py`) goes into its **own new
   module**, named after what it does (not reusing `decomp.py`), and is
   only reachable for datasets whose `DatasetConfig.features` includes it.
   Do not add `if dataset == "..."` branches inside `decomp.py` itself.
9. **`/api/config`**: extend the response with a `datasets` list
   (id/label/collections/features) in addition to the current fields.
   Keep the current top-level fields (`catalog`, `collections`, `token`,
   etc.) describing the default/BIOMASS dataset so the existing frontend
   doesn't break.
10. **Regression check before calling it done**: run `/api/search`,
    `/api/download`, `/api/decompose`, `/api/stitch`, `/api/coverage`
    against BIOMASS exactly as before your change and confirm identical
    responses (same fields, same values, same status codes).

---

## 4. Frontend checklist

1. Add the new dataset's product definitions in a **new file**
   (e.g. `products_<dataset-id>.ts`), or if kept in `products.ts`, as
   clearly separate, dataset-namespaced entries — never edit or remove the
   existing `PRODUCTS` array entries for BIOMASS.
2. `DecompMethod`, `DECOMPS`, and `computeRender`'s `decomp` branch are
   BIOMASS/SCS-specific. Any decomposition UI for a new dataset must be
   gated behind that dataset's own `complex`/feature flag — never assume
   another dataset's complex product behaves like SCS.
3. Extend `types.ts` and `api.ts` additively: new optional fields on
   existing interfaces, new functions for new endpoints — don't rename or
   remove existing exports the current UI depends on.
4. **Coverage map — mandatory for every dataset** (§0 rule 7 / §3 step 7).
   Today this is BIOMASS-only and hardcoded in a few places that need to
   become dataset-aware:
   - `api.ts`'s `fetchCoverage(collection)` needs a `dataset` argument,
     matching the new backend `/api/coverage?dataset=...&collection=...`.
   - `store.ts`'s `coverageProduct`/`loadCoverage` cache key must include
     the dataset id too (not just the product/collection), so switching
     datasets doesn't serve a stale coverage layer.
   - `ControlPanel.tsx`'s `CoverageToggle` button currently hardcodes the
     label `"Show BIOMASS coverage"`. Derive the label from the active
     dataset's `DatasetConfig.label` (from `/api/config`'s new `datasets`
     list) instead of hardcoding the string.
5. If a dataset switcher UI is needed, it should default to BIOMASS on
   load, matching current behavior, so a user who doesn't interact with it
   sees exactly today's app.

---

## 5. Definition of done

- [ ] Existing BIOMASS search/download/tiles/decompose/stitch/coverage
      endpoints produce **identical** output to before the change, called
      the same way (no `dataset` param).
- [ ] New dataset's access requirements (token or not) are documented in
      the `DatasetConfig` entry; if it needs a login, this was explicitly
      flagged to the user beforehand.
- [ ] **Coverage map works for the new dataset** — `/api/coverage` returns
      footprints for it, cached under a dataset-scoped filename, and the
      frontend toggle shows it with a correctly labeled button (not
      hardcoded "BIOMASS").
- [ ] Any new processing feature lives in its own module/file, gated by
      dataset id — nothing was merged into `decomp.py`, `cog.py`'s core
      paths, or `products.ts`'s existing `PRODUCTS`/`DECOMPS` in a way that
      makes them apply to datasets they weren't designed for.
- [ ] `/api/config` lists the new dataset alongside BIOMASS.
- [ ] Frontend still defaults to the BIOMASS dataset/product list.
- [ ] Zusätzlich die Onboarding-Checkliste aus `docs/projektuebersicht.md`
      Abschnitt 5 (Beschreibung, DOI bzw. Zitierangabe, Lizenz mit Flags,
      anonymer Zugriffs-Check).
