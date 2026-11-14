import type { Percent } from './percentRange';
// Shared types for the EarthX viewer.

// Mutually-exclusive AOI selection tools.
export type ToolMode = 'none' | 'point' | 'rectangle' | 'polygon';

export type Bbox = [number, number, number, number]; // [minx, miny, maxx, maxy]

export interface StacAsset {
  href: string;
  type?: string | null;
  title?: string | null;
  roles?: string[];
  // STAC projection extension (v1.1): the asset's own pixel grid, read for
  // quicklook placement (geoUtils.quicklookCoords) when the item sets no
  // `proj:bbox` of its own.
  'proj:transform'?: number[];
  'proj:shape'?: number[];
  // Ground sample distance in metres/pixel (STAC `gsd`, adr/0003 §3): read for
  // the download dialog's resolution choice (F10c, M3-18 §10) — how many
  // metres each `RESOLUTION_FACTORS` step actually means for this asset.
  gsd?: number | null;
  // STAC file extension: the byte length of the file the `href` names. Read by the download of a whole scene
  // (NM4-33), which needs every size beforehand to tell the browser the length of the ZIP.
  'file:size'?: number | null;
  // The band descriptions (M4-13 K7, Otto 10.10.2026), read only to name the
  // bands an expression can use and to start the output data type:
  // `raster:bands` (or the STAC 1.1 core field `bands`) says how many bands a
  // COG asset has, and `bands[].name` names the variables of a Zarr group. The
  // frontend reads no extension prefix of one source (M3-12).
  'raster:bands'?: StacBand[] | null;
  bands?: StacBand[] | null;
}

export interface StacBand {
  name?: string | null;
  data_type?: string | null;
  nodata?: number | string | null;
  spatial_resolution?: number | null;
  scale?: number | null;
  offset?: number | null;
  unit?: string | null;
}

// A STAC Item as `/stac` returns it. `properties` is where a real STAC item
// carries `datetime`, `grid:code` and everything else the registry's
// `earthx:viewer.group_by` can name.
export interface StacItem {
  id: string;
  collection?: string | null;
  bbox?: Bbox | null;
  geometry?: GeoJSON.Geometry | null;
  properties: Record<string, unknown>;
  assets: Record<string, StacAsset>;
}

// The `earthx:` fields of a STAC Collection that the viewer reads
// (architekturplan.md 5.1). Only what 07a uses; the rest of the shape comes
// with the tasks that need it.
export interface CollectionAccess {
  token_free_checked_at?: string | null;
  method?: string | null;
  cors: boolean | null;
  // What reading the assets needs (`adr/0027` §6.1): `none` is anonymous; any other value makes the dataset a catalogue
  // entry with a link (W0). Every collection carries it since M5-13; a collection without it reads as `none`.
  account?: string | null;
}

// The reader dispatch format (`DataFormat`, architekturplan.md 6.2), read only
// to tell a whole scene the viewer may link straight to the source (a COG, one
// file) from one it may not (a Zarr store has no single file, M3-17) —
// without a dataset-specific branch anywhere. A value this union does not
// name is treated like `'zarr'` (download.ts): unknown is never assumed to be
// a linkable single file.
export type DatasetFormat = 'cog' | 'zarr' | 'legacy';

// `earthx:source` (architekturplan.md 5.1). `asset_hosts` is what M3-17's
// original-file download checks a `href` against before ever showing it as a
// link — the same hosts the tile path already trusts (D12), read here for the
// first time by the frontend.
export interface EarthxSource {
  asset_hosts: string[];
  // Where the catalogue of the source answers, and the collection there (shown as "Source" in the Data catalogue, UI-05).
  endpoint?: string | null;
  source_collection_id?: string | null;
  // Where the storage of the assets lies, `<operator>:<place>` or `unknown` (M5-07).
  data_region?: string | null;
}

// A STAC provider (UI-05 F2): who produces, licenses, processes or hosts the data.
export interface StacProvider {
  name: string;
  roles?: string[] | null;
  url?: string | null;
}

// What the browse view shows right after a search, before any tile is requested
// (M3-12, registry `BrowseMode`): a published quicklook the browser crops on its
// own canvas, a coarse tile over one item standing in for one, or the AOI crop in
// full resolution straight away, for a dataset with neither.
export type BrowseMode = 'quicklook' | 'preview_tiles' | 'full_resolution';

// What the tile route shows below `min_zoom` (registry `OverviewMode`, adr/0032 §9): one file's own overviews, a
// pyramid in the platform's object store, the chosen scenes through their own overviews, or another dataset
// (`substitute`, plan M5-30b §4.8).
export type OverviewMode = 'own' | 'pyramid' | 'scenes' | 'substitute';
export type OverviewResampling = 'average' | 'mode' | 'nearest';

export interface EarthxViewer {
  group_by: string[];
  // The tile levels this dataset is released for (M2-10, registry `ViewerInfo`).
  // From `min_zoom` on a tile is read from the original files; below it, the way `overview` names serves it
  // (adr/0032 §9). Above `max_zoom` the source has nothing finer, so the last level is overzoomed.
  min_zoom: number;
  max_zoom: number;
  browse: BrowseMode;
  // For `browse: 'quicklook'` only: a quicklook pixel at or below this value in
  // every band is keyed transparent (`mapLayers.ts`), so dark padding around an
  // irregular scene does not paint over the basemap. `null` where the quicklook
  // needs no such freistellung, and always `null` for the other two `browse`
  // values.
  quicklook_nodata_max: number | null;
  // The key the results list heads its groups by (V-4/D30) and the download
  // route reuses as its per-group merge (P19, M3-17) — separate from `group_by`
  // because a dataset may head its display by a property `group_by` deliberately
  // does not use (M3-02 F-01).
  results_group_by: string[];
  // What happens below `min_zoom` (adr/0032 §9). The resampling is set for `pyramid` only, the substitute (a dataset
  // id) for `substitute` only.
  overview: OverviewMode;
  overview_resampling: OverviewResampling | null;
  overview_substitute: string | null;
}

// `earthx:capabilities` (architekturplan.md 5.1). Only `time_range` is read by
// the viewer today (M3-12, F-06): whether a search with a chosen time window
// answers differently from one without. The others travel with the collection
// but have no reader here yet.
export interface EarthxCapabilities {
  roi: boolean;
  time_range: boolean;
  band_math: boolean;
  interpolation: boolean;
  ml_processing: boolean;
  quad_pol: boolean;
  single_coverage_product: boolean;
}

// How settled the *source* is, not a measurement (`earthx:maturity`,
// architekturplan.md 5.1). The union is what the registry can emit today; the
// field is read as a plain string so a fourth value shows up in the interface
// instead of being silently dropped.
export type Maturity = 'stable' | 'staging' | 'experimental';

// The registry's standard visualisation (`DefaultRender`, M2-04/D20), field names
// mirroring the STAC `render` extension so they map onto tile-URL query params
// 1:1 (`assets[0]` → `asset`, `colormap_name` → `colormap_name`, …).
export interface EarthxDefaultRender {
  title: string;
  assets: string[];
  rescale: [number, number][] | null;
  colormap_name: string | null;
  expression: string | null;
  resampling: string;
  // Which of `assets` an item is drawn with (DS-04 F2): `all` of them, or the `first_present` one the item carries,
  // with the `rescale` pair at its place. Absent on a backend before DS-04b, which means `all`.
  asset_selection?: 'all' | 'first_present';
}

// The registry's licence flags (`earthx.catalog.collection._earthx_license_flags`),
// mirrored field for field. `terms_notice` carries one text per language code
// (always `de`, M2-07d also reads `en`); `null` where the licence names no terms.
export interface LicenseFlags {
  spdx_id: string | null;
  name: string;
  url: string;
  commercial_use: boolean;
  distribution: boolean;
  derivatives: boolean;
  share_alike: boolean;
  attribution_required: boolean;
  tier: 'catalog' | 'display' | 'processing';
  attribution_modified: string | null;
  attribution_unmodified: string | null;
  terms_url: string | null;
  terms_notice: Record<string, string> | null;
}

// The one part of the STAC `extent` block the viewer reads (M3-12, F-06): the
// acquisition period of a dataset with no time axis, shown in place of a date
// filter that would answer the same regardless of the range chosen.
export interface StacTemporalExtent {
  interval: (string | null)[][];
}

// One class of the layer `mask` reads, and the layer itself (`earthx:mask`, M4-18): where the
// panel takes the class names, the pre-ticked classes and the band the recipe names.
export interface EarthxMaskClass {
  value: number;
  label: string;
}

export interface EarthxMask {
  // The order's asset key of the layer, and the band name the operator sees.
  asset: string;
  band: string;
  classes: EarthxMaskClass[];
  // What the panel ticks first; the recipe always names its classes itself.
  suggested: number[];
  // Where the class table comes from (https URL).
  reference: string;
  note: string;
  // DS-03: the classes that count as clouds when the cloud share is measured in the AOI (ascending; empty or absent
  // where the dataset has no such measure), and the registry's sentence to the limits of the classification.
  cloud_classes?: number[] | null;
  cloud_note?: string | null;
  // DS-03c: the classes of the other shares measured in the AOI, by the property the search sends the range under.
  share_classes?: Record<string, number[]> | null;
}

// What a dataset's search can do besides its filters (DS-03c): judge them per overpass, and the filter "AOI coverage".
export interface EarthxSearchCapabilities {
  evaluate?: boolean;
  aoi_coverage?: boolean;
}

export interface Collection {
  id: string;
  title?: string | null;
  description?: string | null;
  // STAC core `keywords` (M3-10): kept for the dataset browser that comes after M3
  // (looking through all datasets with their descriptions); the viewer does not read
  // them yet. Optional — a collection served by an older backend carries none.
  keywords?: string[] | null;
  license?: string | null;
  // STAC scientific extension (`catalog/collection.py::_scientific`): the DOI name and the citation, where the
  // dataset has them. Written into `ATTRIBUTION.txt` of a download of original files (NM4-33).
  'sci:doi'?: string | null;
  'sci:citation'?: string | null;
  extent?: { spatial?: { bbox?: number[][] }; temporal?: StacTemporalExtent };
  // STAC core (UI-05 F2): the providers, and the resolution in metres under `summaries.gsd`.
  providers?: StacProvider[] | null;
  summaries?: { gsd?: number[] | null } | null;
  // The group of the Data catalogue (UI-05 F1).
  'earthx:category'?: string | null;
  // `adr/0024` R3: `unclear` marks a prototype source, with `legal_note` saying what is unclear (`null` when cleared).
  // Every collection carries them since M5-13; a collection without them reads as cleared.
  'earthx:legal_status'?: string | null;
  'earthx:legal_note'?: string | null;
  'earthx:access'?: CollectionAccess;
  'earthx:viewer'?: EarthxViewer | null;
  'earthx:capabilities'?: EarthxCapabilities;
  'earthx:maturity'?: Maturity | string | null;
  'earthx:default_render'?: EarthxDefaultRender | null;
  'earthx:license_flags'?: LicenseFlags | null;
  'earthx:format'?: DatasetFormat | string | null;
  // How the files are placed on the map (registry `georeferencing`): `gcp_tps` places them through their ground
  // control points (adr/0018 F1), so a picture of the source in the files' own geometry has no place on the map.
  'earthx:georeferencing'?: 'geotransform' | 'gcp_tps' | string | null;
  'earthx:source'?: EarthxSource | null;
  'earthx:mask'?: EarthxMask | null;
  // The unit of the values of an asset, by the asset key an order names (`red`, `SR_10m:b04`); a key may end in
  // `*` for a group (`SR_*`). `null` says the registry does not know it (M4-19b).
  'earthx:band_units'?: Record<string, string | null> | null;
  // The assets that are no band of the data (a picture, a preview), by the asset key an order names (NM4-07).
  'earthx:auxiliary_assets'?: string[] | null;
  // The three bands of the colour picture, red, green, blue (NM4-64); empty for a dataset that has none.
  'earthx:true_color'?: string[] | null;
  // What the data cannot do, as whole sentences for the row "Limitations" of the Data catalogue (adr/0018 F2, Nachtrag
  // DS-04c); empty where there is none. Absent on a backend before it.
  'earthx:limitations'?: unknown[] | null;
  // The filters the search offers for this dataset (DS-02), in the words of STAC queryables; read, and checked
  // entry by entry, by `searchFilters.ts`. Absent on a backend before DS-02a.
  'earthx:search_filters'?: unknown[] | null;
  // What the search can do besides filtering (DS-03c); absent on a backend before it, which means neither.
  'earthx:search_capabilities'?: EarthxSearchCapabilities | null;
  // The indices the panel offers as one click each (NM4-14), in the words of the registry; read, and checked entry by
  // entry, by `indexPresets.ts`. Absent on a backend before NM4-14a.
  'earthx:index_presets'?: unknown[] | null;
}

// A time step: the items that share one grouping key (registry.ViewerInfo).
export interface TimeStepGroup {
  key: string[];
  label: string;
  items: StacItem[];
}

// Tile-render params committed via "Apply" (F18) — everything a tile URL needs
// beyond the asset itself, which `DownloadedInfo.tileUrl` already carries. Field
// names follow TiTiler's own query parameters (`bidx`, `colormap_name`, …) so
// `buildTileUrl` (mapLayers.ts) can pass them straight through.
export interface AppliedRender {
  // The name of the index preset of the dataset the view draws instead of a band (NM4-14b, `viewIndex.ts`); the range and
  // colormap below are the ones the index is drawn with.
  index?: string;
  // The single band of the data the view draws instead of its standard picture (NM4-45, `viewBand.ts`): the key of its asset.
  // None is the standard picture ("RGB" where the dataset has a true-colour one).
  band?: string;
  // The band of a result by its place from 1; several, comma-separated, for a colour picture (`3,2,1`).
  bidx?: string;
  expression?: string;
  colormapName?: string;
  rescale?: string; // "min,max" (adr/0006 §3.4 Z4)
  // What the range was typed as where it was typed in percentiles (NM4-65 part 4): `rescale` holds the values they gave when
  // they were applied, so the picture is always drawn from values; this is only for the fields to show "%" again.
  percent?: Percent;
  // The same for a colour picture whose channels are each typed in their own unit (UI-03e, Otto, 3.11.2026): a pair for a channel typed
  // in percentiles, `null` for one typed in values, in the order red, green, blue. `rescale` holds the values they gave. Where it is
  // set, `percent` is not.
  percentChannels?: (Percent | null)[];
}

// Full-resolution tile info for one item, keyed by item id in the store's
// `downloaded` map (M2-07b). The tiler renders straight from the source asset —
// there is no crop or download step here, that is M2-06/M2-07d.
export interface DownloadedInfo {
  // The dataset the scene belongs to: a view can hold scenes of several (NM4-53), so it is not the open section's.
  datasetId: string;
  tileUrl: string; // MapLibre tile template ({z}/{x}/{y}), asset already baked in
  bounds: Bbox;
  asset: string;
  // The asset the scene was opened with, when the view draws another one for the look of its image (NM4-45): the one the
  // standard picture of the dataset comes from.
  baseAsset?: string;
  // The levels this dataset is released for (`earthx:viewer`, M2-10). Below the
  // lower one MapLibre requests nothing, above the upper one it overzooms the
  // last level — which is also what the tile route allows, so the map never asks
  // for a tile the backend answers with a 400.
  minZoom: number;
  maxZoom: number;
}
