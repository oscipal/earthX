# biomass-viewer

Interactive web app to **search, preview and download ESA BIOMASS satellite
imagery** (P-band SAR, Above-Ground-Biomass products) on a map — a bit like
Google Earth, but for the ESA BIOMASS mission.

- **Search** the [ESA MAAP STAC catalog](https://catalog.maap.eo.esa.int/catalogue/)
  for an area of interest (point / rectangle / polygon / place search, or upload
  a KML/GeoJSON). A global **coverage heatmap** shows where BIOMASS has acquired.
- **Pick a product** — `GN`, `DGM`, `FH`, `FD` (Level-2A/1B) or `SCS` (Level-1A
  complex) — and **preview** matching scenes as quicklook overlays, grouped by
  acquisition pass; scrub dates with a **timeline**.
- **Download** full-resolution data on demand — only the AOI window is fetched
  from the (multi-GB) Cloud-Optimized-GeoTIFFs via HTTP range requests, cropped,
  cached, and served as **pyramidal map tiles**. Selecting several **adjacent
  frames stitches them into a single mosaic**.
- **Explore polarizations** — for polarimetric products, view a single
  polarization (HH/HV/VH/VV) + colormap, an intensity RGB, or a pseudo-Pauli
  composite; for **SCS**, run full polarimetric **decompositions** (Pauli,
  Freeman–Durden) computed from the complex data and geocoded onto the map.
- **Pin results into a layer manager** — stack any view (quicklook, full-res
  crop, stitch or decomposition) with per-layer visibility, opacity and ordering.

The map uses a **satellite / aerial basemap** (Esri World Imagery) with a dark
translucent HUD overlay for the controls.

```
biomass-viewer/
  environment.yml     # conda env (Python 3.11 + geospatial stack)
  backend/            # FastAPI: STAC proxy, token auth, AOI-crop cache, COG tile server
  frontend/           # React + TypeScript + Vite + MapLibre GL JS
  README.md
```

---

## 1. Prerequisites

- [conda / miniconda](https://docs.conda.io/) (for the backend geospatial stack)
- [Node.js](https://nodejs.org/) ≥ 20 and npm (for the frontend)
- An **ESA MAAP account + offline token** to preview/download pixel data
  (searching works without one). See step 3.

---

## 2. Backend

### Create the conda environment

```bash
conda env create -f environment.yml
conda activate biomass-viewer
```

This installs GDAL, rasterio, rio-tiler, rio-cogeo, pystac-client, FastAPI, etc.
— all from conda-forge so they share one GDAL build.

### Configure your token

```bash
cd backend
cp .env.example .env      # then edit .env
```

Open `backend/.env` and set `MAAP_TOKEN`. See **step 3** for how to get one.
All other settings have sensible defaults (catalog URL, collections, cache dir,
cache size limit, geocoder, CORS origins…). The **token never leaves the
backend** — the frontend only talks to this server.

### Run the backend

```bash
# from the backend/ directory, with the conda env active:
uvicorn app.main:app --reload --port 8000
```

- API docs: <http://localhost:8000/docs>
- Health:  <http://localhost:8000/api/health>
- Config:  <http://localhost:8000/api/config> (shows whether a token is loaded)

---

## 3. Getting a MAAP token

Discovery (STAC search) is open, but reading quicklooks and COG assets is
token-secured.

1. Create an ESA MAAP account: <https://portal.maap.eo.esa.int>
2. Generate an **offline token**:
   <https://portal.maap.eo.esa.int/ini/services/auth/token/index.php>
3. Paste it into `backend/.env` as `MAAP_TOKEN=...`

The token you get is normally an **offline token** (a Keycloak refresh token).
The backend automatically exchanges it for a short-lived *access* token at the
MAAP OIDC endpoint and refreshes it as needed (see `backend/app/auth.py`) — you
don't have to do anything. If the token is missing or expired, the frontend
shows a clear message; just refresh it in `.env`.

> The OIDC client id/secret used for the exchange are the **public** values
> documented by MAAP and are baked in as defaults (`OIDC_CLIENT_ID`,
> `OIDC_CLIENT_SECRET`); override them in `.env` if MAAP changes them.

---

## 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>. The Vite dev server **proxies `/api`** to the
backend on port 8000, so make sure the backend is running.

Production build:

```bash
npm run build     # outputs to frontend/dist
npm run preview
```

If your backend runs elsewhere, set `VITE_API_PROXY` (dev) or `VITE_API_BASE`
(build) accordingly.

---

## 5. How to use

1. **Pick a product** in the left panel: `GN`, `DGM`, `FH`, `FD` or `SCS`
   (see the product table in section 7). Toggle **▦ Show BIOMASS coverage** to
   see the global acquisition-density heatmap for that product.
2. **Define an AOI** with the toolbar: **Point** (auto-buffered), **Rectangle**
   (click-drag), **Polygon** (click vertices, double-click to finish), or type a
   **place name** to geocode + fly there. You can also **upload a KML/GeoJSON**
   or reuse the **last AOI**. Drawing an AOI zooms the map into it.
3. Optionally set an **acquisition date** range, then **Search scenes**. The
   control panel slides away to the left — click the **‹ / ›** tab to toggle it.
   The floating panels (Mosaics, timeline, action bar) are **draggable**, and
   **⤢ Zoom to selection** (top-right) frames the current selection / mosaic / AOI.
4. Matching scenes appear as **quicklook overlays** covering the AOI. Adjacent
   frames from the *same acquisition pass* are grouped together — split by
   product, date **and orbit direction**, so an ascending (morning) pass and a
   descending (evening) pass over the same region stay in separate groups. Black
   nodata is keyed to transparent. Scrub dates with the bottom **timeline**.
5. **Select** scenes (checkbox in the list, or click the overlay) and produce
   full-resolution data:
   - **GN / DGM / FH / FD** → **Confirm download**. The backend crops the COGs to
     your AOI and switches to a **full-resolution view**, where you choose a
     **polarization view** and hit **Apply**:
       - *Single-pol* (HH/HV/VH/VV) + colormap
       - *Intensity RGB* — R=HH, G=cross-pol, B=VV
       - *Pseudo-Pauli* — R=|HH−VV|, G=cross-pol, B=|HH+VV|
     (FH/FD are single-band → colormap only.) Blank `vmin/vmax` = auto 2–98%.
   - **SCS** → choose a **decomposition** (*Pauli* / *Freeman–Durden*) and
     **Compute**. The complex quad-pol data is geocoded (via GCPs), decomposed,
     and cached as an RGB composite — ~1–2 min per scene, then instant to re-view.
6. In the full-resolution view: **Hide/Show** the overlay, **‹ Choose a different
   image** to return to browsing, or **Clear all** to reset the workspace.

---

## 6. Architecture / API

Backend endpoints (all under `/api`):

| Endpoint | Purpose |
| --- | --- |
| `POST /search` | STAC search over an AOI (GeoJSON) + optional date range. |
| `GET /tiles/{item_id}/{z}/{x}/{y}.png` | On-the-fly tiles (rio-tiler). Cached AOI crop when `?aoi=<hash>`, else the remote COG. Optional `?asset=`, `?indexes=1,2,4`, `?expression=` (band math), `?rescale=min,max`, `?colormap=`. One band → run through the colormap; multiple bands/expression → rendered as RGB. |
| `POST /download` | Partial COG read → crop to AOI → write cached COG. Returns a tile-URL template. |
| `POST /decompose` | **SCS only**: GCP-geocode the complex quad-pol data, run a polarimetric decomposition (`pauli` / `freeman`), and cache a 3-band RGB COG served via `/tiles?asset=decomp_<method>`. |
| `GET /asset` | Token-injecting proxy for quicklooks/thumbnails (never exposes the token; host-allowlisted). |
| `GET /geocode` | Place search proxy (Nominatim by default, swappable). |
| `GET /config`, `GET /health` | Non-secret status. |

Key backend modules: `stac.py` (search), `auth.py` (offline→access token
exchange), `cog.py` (multi-band/expression tiles + AOI crop), `decomp.py` (SCS
GCP-geocoding + Pauli / Freeman–Durden decompositions), `store.py` (item
registry + LRU crop cache), `routes/` (FastAPI routers).

Frontend: `store.ts` (Zustand — the single source of truth: tool mode, AOI,
results, active timestep, selection, downloads, product/polarization/render
state, UI layout), `products.ts` (product + polarization + decomposition model
and tile-param derivation), `MapView.tsx` (MapLibre + terra-draw + overlay sync),
`mapStyles.ts` (hand-authored satellite basemap style), `mapLayers.ts` (overlay
placement + transparent-nodata quicklook processing), `grouping.ts` (grouping by
product / date / orbit pass), `ViewerControls.tsx` (polarization & decomposition
controls).

---

## 7. Notes & caveats

- **Data availability:** BIOMASS Level-1 products are openly available since
  Dec 2025; Level-2 is rolling out. Each product searches its own collection
  (`GN/FH/FD`→`BiomassLevel2a`, `DGM`→`BiomassLevel1b`, `SCS`→`BiomassLevel1a`).
- **Asset names vary by product** (`enclosure_i_fd_tiff`, `enclosure_tiff`,
  `quicklook_jpg`, …). The backend picks a sensible quicklook + primary COG per
  item; override the defaults in `.env`.
- **Cache:** cropped COGs live in `backend/cache/` (gitignored) with LRU
  eviction once total size exceeds `CACHE_MAX_BYTES` (default 5 GiB).
- **Basemap** uses Esri **World Imagery** XYZ tiles (no API key required). See
  attribution below.
- **Products** (selectable in the left panel):

  | Product | Level | Bands | Notes |
  | --- | --- | --- | --- |
  | `GN`  | L2A | HH, VH, VV | ground-notched polarimetric backscatter |
  | `DGM` | L1B | HH, HV, VH, VV | detected ground multi-look, geocoded quad-pol |
  | `FH`  | L2A | 1 | forest height (m) |
  | `FD`  | L2A | 1 | forest disturbance (class) |
  | `SCS` | L1A | HH, HV, VH, VV (complex) | single-look complex; decompositions only |

  Polarization is a **band dimension** inside each TIFF. Colormap / `vmin` /
  `vmax` apply to the **downloaded COG tiles**, not to the static quicklook JPEGs.
  Each quicklook is placed on its bounding box with black nodata keyed to
  transparent. Forest-Disturbance (`FD`) quicklooks are published near-black, so
  `FD` groups sort last. SCS scenes lacking the complex (abs+phase) TIFFs are
  filtered out (they can't be decomposed).
- **Decompositions (SCS):** SCS is slant-range, geolocated only by GCPs, so the
  backend warps `i_abs` + `i_phase` to a geographic grid (nearest-neighbour, so
  each amplitude/phase pair stays co-located), reconstructs the complex
  scattering vector, and runs **Pauli** (`R=|HH−VV|, G=|HV|, B=|HH+VV|`) or
  **Freeman–Durden** (model-based `R=double-bounce, G=volume, B=surface`, with a
  5×5 boxcar multi-look) → a cached RGB COG. Cost is ~1–2 min per scene (the
  warp dominates); cached results re-view instantly. *Yamaguchi is not yet
  implemented.*

---

## 8. Attribution & references

This tool is a client for third-party data and services. When you use, publish,
or redistribute anything obtained through it, you must honour the providers'
terms and attribution requirements:

- **ESA BIOMASS mission data** — © ESA / European Space Agency, distributed via
  the [MAAP](https://portal.maap.eo.esa.int) STAC catalog
  (<https://catalog.maap.eo.esa.int/catalogue/>). BIOMASS products are subject to
  ESA's data policy and terms of use; cite the mission and processing level when
  publishing results. Mission reference: ESA BIOMASS Earth Explorer (P-band SAR),
  <https://www.esa.int/Applications/Observing_the_Earth/FutureEO/Biomass>.
- **Basemap imagery** — Esri **World Imagery**: *Esri, Maxar, Earthstar
  Geographics, and the GIS User Community*
  (<https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9>).
  Subject to the Esri terms of use.
- **Geocoding** — [Nominatim](https://nominatim.org/) over
  [OpenStreetMap](https://www.openstreetmap.org/copyright) data,
  © OpenStreetMap contributors (ODbL). Respect the Nominatim usage policy.
- **Core libraries** — [MapLibre GL JS](https://maplibre.org/),
  [terra-draw](https://github.com/JamesLMilner/terra-draw),
  [rio-tiler](https://github.com/cogeotiff/rio-tiler),
  [rio-cogeo](https://github.com/cogeotiff/rio-cogeo),
  [rasterio](https://rasterio.readthedocs.io/) / GDAL,
  [pystac-client](https://github.com/stac-utils/pystac-client),
  [FastAPI](https://fastapi.tiangolo.com/), [React](https://react.dev/),
  [Vite](https://vite.dev/).

Suggested data citation (adapt to the products you use):

> BIOMASS Level-<n> products, European Space Agency (ESA), accessed <date> via
> the ESA MAAP catalogue (https://catalog.maap.eo.esa.int/catalogue/).

---

## 9. License

Application source code: **AGPL-3.0-or-later** — see [`LICENSE`](./LICENSE).
Releases published before 2026-09-18 remain available under the MIT license they
were published under.

The AGPL covers this app's code only, **not** the satellite data, basemap imagery,
or geocoding results, which remain under their providers' terms (see section 8).

Note on AGPL section 13: if you run a modified version of this software and let
users interact with it over a network, you must offer those users access to the
corresponding source code.
