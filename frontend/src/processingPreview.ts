// The preview of the steps on the map (M4-13c-2, plan §3.3): which steps can be
// shown as tiles, the tile URLs of the scenes of an order, when the map says
// "Preview", and the layer a preview becomes. Pure functions; the state lives in
// `processingStore.ts`.

import { clipTileUrl } from './aoiClip';
import { buildOperatorTileTemplate } from './api';
import type { DatasetOption } from './datasets';
import type { LayerOverlay } from './layers';
import { buildTileUrl } from './mapLayers';
import { canonicalJson } from './processing';
import { bandsOf, type Area, type DraftStep, type Operator, type ProcessInfo } from './processingOrder';
import { paramsFrom } from './schemaForm';
import type { Bbox, StacItem } from './types';

// As many scenes as the full-resolution view draws (`mapLayers.ts`).
export const MAX_PREVIEW_SCENES = 40;
// The tile route takes at most this many assets with an operator (`api/tiler.py`).
export const MAX_PREVIEW_ASSETS = 16;

export const PREVIEW_BADGE_TITLE =
  'This is a preview, not the result. A job uses the full resolution of the data.';

export const NO_PREVIEW = 'No preview: the first step runs only as a job.';

// --- range and colormap ------------------------------------------------------

// What the preview is drawn with (F3 (1)): a range and a colormap by hand, the
// start values for an index such as NDVI. "Auto stretch" is not offered: the
// statistics route takes no operator.
export interface PreviewRange {
  vmin: string;
  vmax: string;
  // `''`: no colormap.
  colormap: string;
}

export const DEFAULT_RANGE: PreviewRange = { vmin: '-1', vmax: '1', colormap: 'rdylgn' };

export const AUTO_STRETCH_REASON = 'Not for a preview: the statistics of a tile cannot be measured through an operator. Set the range by hand.';

export function rescaleOf(range: PreviewRange): { rescale: string } | { problem: string } {
  const number = (text: string) => (text.trim() === '' ? NaN : Number(text));
  const low = number(range.vmin);
  const high = number(range.vmax);
  if (!Number.isFinite(low) || !Number.isFinite(high)) return { problem: 'Enter a number for both ends of the range.' };
  if (low >= high) return { problem: 'The lower end of the range must be below the upper end.' };
  return { rescale: `${low},${high}` };
}

// --- the planner (adr/0014 §6.1) ---------------------------------------------

export type PreviewPlan =
  | { state: 'off'; reason: string | null }
  | {
      state: 'ready';
      step: DraftStep;
      operator: Operator;
      params: Record<string, unknown>;
      // Steps after the first: the tile route takes one operator, so the preview
      // shows the first and the job runs them all.
      further: boolean;
    };

// The preview is the first step if it runs as a tile (`T1`, a pixel operator)
// and its fields are complete; nothing else is shown. Without steps there is
// nothing to say.
export function planPreview(steps: readonly DraftStep[], info: ProcessInfo | null): PreviewPlan {
  const first = steps[0];
  if (!info || !first) return { state: 'off', reason: null };
  const operator = info.operators.find((o) => o.op === first.op && o.opVersion === first.opVersion);
  if (!operator || !operator.form.supported || !operator.tiers.includes('T1') || operator.kind !== 'pixel') {
    return { state: 'off', reason: NO_PREVIEW };
  }
  const { params, errors } = paramsFrom(operator.form.fields, first.values);
  if (Object.keys(errors).length > 0) return { state: 'off', reason: 'Complete the step to see the preview.' };
  return { state: 'ready', step: first, operator, params, further: steps.length > 1 };
}

// --- what the map draws -----------------------------------------------------

export interface PreviewScene {
  id: string;
  bbox: Bbox;
  // The tile template of the scene, without any AOI clip.
  url: string;
}

export interface PreviewSpec {
  // Changes whenever the picture does; the map and the debounce compare it.
  key: string;
  title: string;
  scenes: PreviewScene[];
  minZoom: number;
  // Capped so that no tile is as fine as the data (`previewMaxZoom`).
  maxZoom: number;
  // "AOI only": the tiles are cut to the AOI in the browser (`aoiClip.ts`).
  clipToAoi: boolean;
}

const positive = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) && value > 0 ? value : null;

// The order `access/download.py::asset_gsd` reads them in: the asset's own `gsd`,
// the first band's `spatial_resolution`, the item's `gsd`.
export function assetGsd(item: StacItem, key: string): number | null {
  const asset = item.assets?.[key];
  return positive(asset?.gsd) ?? positive((asset ? bandsOf(asset) : null)?.[0]?.spatial_resolution) ?? positive(item.properties?.gsd);
}

// The asset of the item an order asset reads: its own key, or — a variable of a
// Zarr group, `<asset><separator><variable>` — the key of the group.
function itemAssetKey(item: StacItem, orderAsset: string, separator: string | null): string {
  if (item.assets?.[orderAsset]) return orderAsset;
  if (separator) {
    const group = Object.keys(item.assets ?? {}).find((key) => orderAsset.startsWith(`${key}${separator}`));
    if (group) return group;
  }
  return orderAsset;
}

// The finest pixel size among the assets of the order; where only some state
// one, those count.
export function finestGsd(items: readonly StacItem[], assets: readonly string[], separator: string | null): number | null {
  const known = items.flatMap((item) =>
    assets.map((asset) => assetGsd(item, itemAssetKey(item, asset, separator))).filter((gsd): gsd is number => gsd !== null),
  );
  return known.length === 0 ? null : Math.min(...known);
}

export function previewSpec(args: {
  dataset: DatasetOption | undefined;
  items: readonly StacItem[];
  assets: readonly string[];
  info: ProcessInfo;
  plan: Extract<PreviewPlan, { state: 'ready' }>;
  range: PreviewRange;
  area: Area;
}): PreviewSpec | null {
  const { dataset, items, assets, info, plan, range, area } = args;
  if (!dataset?.viewable || assets.length === 0 || assets.length > MAX_PREVIEW_ASSETS) return null;
  const rescale = rescaleOf(range);
  if ('problem' in rescale) return null;
  const paramsJson = canonicalJson(plan.params);
  const scenes: PreviewScene[] = [];
  for (const item of items.slice(0, MAX_PREVIEW_SCENES)) {
    if (!item.bbox) continue;
    const template = buildOperatorTileTemplate(dataset.id, item.id, assets, plan.step.op, plan.step.opVersion, paramsJson);
    scenes.push({
      id: item.id,
      bbox: item.bbox,
      url: buildTileUrl(template, { rescale: rescale.rescale, colormapName: range.colormap || undefined }),
    });
  }
  if (scenes.length === 0) return null;
  // Without a pixel size there is no level to hold the preview under: it is drawn
  // as before, up to the last released level, and "Preview" says what it is (Otto,
  // 19.10.2026).
  const gsd = finestGsd(items, assets, info.variableSeparator);
  const maxZoom = gsd === null ? dataset.zoom.max : previewMaxZoom(scenes.map((s) => s.bbox), gsd, dataset.zoom);
  const clipToAoi = area === 'aoi';
  return {
    key: canonicalJson({ urls: scenes.map((s) => s.url), minZoom: dataset.zoom.min, maxZoom, clipToAoi }),
    title: plan.operator.title,
    scenes,
    minZoom: dataset.zoom.min,
    maxZoom,
    clipToAoi,
  };
}

// The overlays of a preview, as the map and a layer hold them.
export function previewOverlays(spec: PreviewSpec, aoi: GeoJSON.Geometry | null): LayerOverlay[] {
  const clip = spec.clipToAoi ? aoi : null;
  return spec.scenes.map((scene) => ({
    kind: 'raster' as const,
    tileUrl: clipTileUrl(scene.url, clip),
    bounds: scene.bbox,
    minZoom: spec.minZoom,
    maxZoom: spec.maxZoom,
    preview: true as const,
  }));
}

// --- never as fine as the data (Otto, 19.10.2026) ---------------------------

// Metres per pixel of a 256-pixel Web Mercator tile at `latitude`.
export function tileResolution(latitude: number, zoom: number): number {
  return (156543.03392 * Math.cos((latitude * Math.PI) / 180)) / 2 ** zoom;
}

// The last tile level the preview asks for. A tile is the finest where the scene
// lies farthest from the equator, so the level is chosen there: every tile is
// coarser than `gsd` (strictly), everywhere in the scenes. Above it the map
// stretches the last level, the picture gets blurry and no finer. Held within the
// released levels; a dataset whose lowest level is already finer than the data
// cannot be held under it, and keeps that level.
export function previewMaxZoom(bboxes: readonly Bbox[], gsd: number, zoom: { min: number; max: number }): number {
  const farthest = Math.max(0, ...bboxes.flatMap(([, south, , north]) => [Math.abs(south), Math.abs(north)]));
  const coarsest = (156543.03392 * Math.cos((Math.min(farthest, 89) * Math.PI) / 180)) / gsd;
  // The largest whole level below log2(coarsest): its tiles are still coarser than `gsd`.
  const level = Math.ceil(Math.log2(coarsest)) - 1;
  return Math.max(zoom.min, Math.min(zoom.max, level));
}
