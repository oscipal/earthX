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
}

// What the browse view shows right after a search, before any tile is requested
// (M3-12, registry `BrowseMode`): a published quicklook the browser crops on its
// own canvas, a coarse tile over one item standing in for one, or the AOI crop in
// full resolution straight away, for a dataset with neither.
export type BrowseMode = 'quicklook' | 'preview_tiles' | 'full_resolution';

export interface EarthxViewer {
  group_by: string[];
  // The tile levels this dataset is released for (M2-10, registry `ViewerInfo`).
  // Below `min_zoom` one tile shows several scenes, which is the coverage map's
  // job; above `max_zoom` the source has nothing finer, so the last level is
  // overzoomed. The tile route enforces both — asking outside the range is a 400,
  // not a slow tile. (For a dataset released from tiles already clipped to their
  // own item's extent — every tile URL is per-item since M3-09 — `min_zoom` is a
  // cost floor on how many tiles a viewport can ask for at once instead: the DEM
  // sets it to 0, M3-12 plan step §3.)
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

export interface Collection {
  id: string;
  title?: string | null;
  description?: string | null;
  license?: string | null;
  extent?: { temporal?: StacTemporalExtent };
  'earthx:access'?: CollectionAccess;
  'earthx:viewer'?: EarthxViewer | null;
  'earthx:capabilities'?: EarthxCapabilities;
  'earthx:maturity'?: Maturity | string | null;
  'earthx:default_render'?: EarthxDefaultRender | null;
  'earthx:license_flags'?: LicenseFlags | null;
  'earthx:format'?: DatasetFormat | string | null;
  'earthx:source'?: EarthxSource | null;
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
  bidx?: string;
  expression?: string;
  colormapName?: string;
  rescale?: string; // "min,max" (adr/0006 §3.4 Z4)
}

// Full-resolution tile info for one item, keyed by item id in the store's
// `downloaded` map (M2-07b). The tiler renders straight from the source asset —
// there is no crop or download step here, that is M2-06/M2-07d.
export interface DownloadedInfo {
  tileUrl: string; // MapLibre tile template ({z}/{x}/{y}), asset already baked in
  bounds: Bbox;
  asset: string;
  // The levels this dataset is released for (`earthx:viewer`, M2-10). Below the
  // lower one MapLibre requests nothing, above the upper one it overzooms the
  // last level — which is also what the tile route allows, so the map never asks
  // for a tile the backend answers with a 400.
  minZoom: number;
  maxZoom: number;
}
