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

export interface Collection {
  id: string;
  title?: string | null;
  description?: string | null;
  license?: string | null;
  'earthx:access'?: CollectionAccess;
  'earthx:viewer'?: EarthxViewer | null;
}

// A time step: the items that share one grouping key (registry.ViewerInfo).
export interface TimeStepGroup {
  key: string[];
  label: string;
  items: StacItem[];
}

// Tile-render params for a downloaded/rendered raster (rebuilt properly with
// 07b; mapLayers.ts's full-res path needs the shape today even though nothing
// in 07a ever fills it in).
export interface AppliedRender {
  indexes?: string;
  expression?: string;
  colormap?: string;
  rescale?: string;
}

// Info stored per item once its AOI-crop has been rendered (07b).
export interface DownloadedInfo {
  tileUrl: string; // MapLibre tile template ({z}/{x}/{y})
  aoiHash: string;
  bounds: Bbox;
  asset: string;
}
