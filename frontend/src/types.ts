// Shared types for the EarthX viewer.

// Mutually-exclusive AOI selection tools.
export type ToolMode = 'none' | 'point' | 'rectangle' | 'polygon';

export type Bbox = [number, number, number, number]; // [minx, miny, maxx, maxy]

export interface StacAsset {
  href: string;
  type?: string | null;
  title?: string | null;
  roles?: string[];
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

export interface Collection {
  id: string;
  title?: string | null;
  description?: string | null;
  license?: string | null;
  'earthx:access'?: CollectionAccess;
  'earthx:viewer'?: EarthxViewer | null;
  'earthx:default_render'?: EarthxDefaultRender | null;
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
