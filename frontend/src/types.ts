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

export interface EarthxViewer {
  group_by: string[];
  // The tile levels this dataset is released for (M2-10, registry `ViewerInfo`).
  // Below `min_zoom` one tile shows several scenes, which is the coverage map's
  // job; above `max_zoom` the source has nothing finer, so the last level is
  // overzoomed. The tile route enforces both — asking outside the range is a 400,
  // not a slow tile.
  min_zoom: number;
  max_zoom: number;
}

// How settled the *source* is, not a measurement (`earthx:maturity`,
// architekturplan.md 5.1). The union is what the registry can emit today; the
// field is read as a plain string so a fourth value shows up in the interface
// instead of being silently dropped.
export type Maturity = 'stable' | 'staging' | 'experimental';

// Result of the last check of the source (`earthx:health`). Checklist point 10
// asks for `last_checked_ok` to be set *and visible*, which is why the viewer
// reads it at all.
export interface CollectionHealth {
  status: string;
  last_checked_ok: string | null;
}

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

export interface Collection {
  id: string;
  title?: string | null;
  description?: string | null;
  license?: string | null;
  'earthx:access'?: CollectionAccess;
  'earthx:viewer'?: EarthxViewer | null;
  'earthx:maturity'?: Maturity | string | null;
  'earthx:health'?: CollectionHealth | null;
  'earthx:default_render'?: EarthxDefaultRender | null;
  'earthx:license_flags'?: LicenseFlags | null;
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
}
