// Imperative helpers that keep the map's custom sources/layers in sync with app
// state. All are idempotent so they can be safely re-run after map.setStyle()
// (which wipes every custom source/layer).

import type { GeoJSONSource, Map as MapLibreMap } from 'maplibre-gl';

import type { CoverageCell } from './api';
import { cellsToFeatureCollection, coverageFillColorExpression } from './coverage';
import { quicklookAsset } from './datasets';
import { asFeatureCollection, bboxToPolygon, quicklookCoords } from './geoUtils';
import type { Coords4 } from './geoUtils';
import type { MapLayer } from './layers';
import type { AppliedRender, DownloadedInfo, StacItem } from './types';

const AOI_SRC = 'aoi-src';
const SEL_SRC = 'mosaicsel-src'; // highlighted (selected-for-download) footprints
const COVERAGE_SRC = 'coverage-src'; // the density grid (M2-07c)
const COVERAGE_FOOTPRINTS_SRC = 'coverage-footprints-src'; // real footprints once footprints_advised

const EMPTY_FC: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };
const MAX_MOSAIC_LAYERS = 40;

// Dynamic per-frame overlay ids created by syncMosaic (variable count).
let dynLayerIds: string[] = [];
let dynSourceIds: string[] = [];

// Bumped on each syncMosaic so slow async quicklook processing can tell whether
// it has been superseded before it touches the map.
let syncGen = 0;
// Bumped on each syncLayers (the layer manager) for the same reason.
let layerGen = 0;
const MAX_LAYER_OVERLAYS = 200;
// Cache of processed (black-nodata → transparent) quicklook data URLs, keyed by
// the (same-origin) image URL so the mosaic and the layer renderer share it.
const qlDataUrlCache = new Map<string, string>();

// Near-black luminance threshold below which a pixel is treated as nodata and
// made fully transparent.
const NODATA_THRESHOLD = 16;

// Redraw a quicklook JPEG into a canvas, turning its near-black nodata padding
// transparent so only the acquisition swath shows over the basemap. Runs on the
// same-origin proxied image, so the canvas is not tainted.
function keyBlackToTransparent(img: HTMLImageElement): string {
  const w = img.naturalWidth;
  const h = img.naturalHeight;
  const canvas = document.createElement('canvas');
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return img.src;
  ctx.drawImage(img, 0, 0);
  const data = ctx.getImageData(0, 0, w, h);
  const px = data.data;
  for (let p = 0; p < px.length; p += 4) {
    if (px[p] <= NODATA_THRESHOLD && px[p + 1] <= NODATA_THRESHOLD && px[p + 2] <= NODATA_THRESHOLD) {
      px[p + 3] = 0;
    }
  }
  ctx.putImageData(data, 0, 0);
  return canvas.toDataURL('image/png');
}

// Load a quicklook, key its black nodata transparent, and hand back the data
// URL (cached).
function loadTransparent(url: string, cb: (dataUrl: string) => void): void {
  const cached = qlDataUrlCache.get(url);
  if (cached) {
    cb(cached);
    return;
  }
  const img = new Image();
  // Load-bearing: the quicklook comes straight from the asset host now (D14),
  // not a same-origin proxy. Without this the browser taints the canvas the
  // moment the image isn't same-origin, and getImageData below throws — the
  // nodata keying would fail silently. The host sends
  // `Access-Control-Allow-Origin: *` (adr/0006 §3.6, gemessen); no test can
  // show that a CORS header actually arrived, so it is checked in the demo
  // instead (plan §9).
  img.crossOrigin = 'anonymous';
  img.onload = () => {
    const dataUrl = keyBlackToTransparent(img);
    qlDataUrlCache.set(url, dataUrl);
    cb(dataUrl);
  };
  img.onerror = () => {
    /* unreadable quicklook — skip */
  };
  img.src = url;
}

function placeImage(
  map: MapLibreMap,
  srcId: string,
  lyrId: string,
  dataUrl: string,
  coords: Coords4,
  opacity: number,
): void {
  if (map.getSource(srcId)) return;
  map.addSource(srcId, { type: 'image', url: dataUrl, coordinates: coords });
  map.addLayer(
    { id: lyrId, type: 'raster', source: srcId, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 } },
    beforeAoi(map),
  );
}

// No registry field names a dataset's ground sample distance yet (only the
// Zarr candidate's D23 gives zoom bounds, and only for that one dataset), so
// this is a generic ceiling rather than something derived per source. z19 is
// several times past Sentinel-2's ~10 m/px (≈z14 near the equator, coarser
// towards the poles) — enough headroom to zoom into real detail without
// MapLibre requesting tiles the source cannot add anything to. Without a cap
// here, nothing stops ordinary scroll-zoom from reaching MapLibre's own
// default ceiling of z22 (256x as many requests over a session as z14, for
// pixels no sharper than the source already has).
const MAX_RASTER_ZOOM = 19;

function placeRaster(
  map: MapLibreMap,
  srcId: string,
  lyrId: string,
  tileUrl: string,
  bounds: [number, number, number, number],
  opacity: number,
): void {
  if (map.getSource(srcId)) return;
  map.addSource(srcId, { type: 'raster', tiles: [tileUrl], tileSize: 256, bounds, maxzoom: MAX_RASTER_ZOOM });
  map.addLayer(
    { id: lyrId, type: 'raster', source: srcId, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0 } },
    beforeAoi(map),
  );
}

// Full tile URL for a full-res overlay: `info.tileUrl` already carries the
// mandatory `asset` (api.ts `buildTileTemplate`, adr/0001 Z4); this adds the
// stretch/colormap/band params committed via "Apply". Also used by the store
// to snapshot a layer.
export function buildTileUrl(info: DownloadedInfo, render: AppliedRender): string {
  const params = new URLSearchParams();
  if (render.bidx) params.set('bidx', render.bidx);
  if (render.expression) params.set('expression', render.expression);
  if (render.colormapName) params.set('colormap_name', render.colormapName);
  if (render.rescale) params.set('rescale', render.rescale);
  const q = params.toString();
  return q ? `${info.tileUrl}&${q}` : info.tileUrl;
}

export function ensureBaseLayers(map: MapLibreMap): void {
  if (!map.getSource(AOI_SRC)) {
    map.addSource(AOI_SRC, { type: 'geojson', data: EMPTY_FC });
    map.addLayer({
      id: 'aoi-fill',
      type: 'fill',
      source: AOI_SRC,
      paint: { 'fill-color': '#19e0ff', 'fill-opacity': 0.06 },
    });
    map.addLayer({
      id: 'aoi-line',
      type: 'line',
      source: AOI_SRC,
      paint: { 'line-color': '#19e0ff', 'line-width': 1.6, 'line-dasharray': [3, 2] },
    });
  }
  if (!map.getSource(COVERAGE_SRC)) {
    map.addSource(COVERAGE_SRC, { type: 'geojson', data: EMPTY_FC });
    // Acquisition-density heatmap: a `fill` choropleth over the geotile grid,
    // not MapLibre's own `heatmap` type (adr/0004 §5 — that type is
    // point-based and mixes intensity with radius and zoom, so a cell's exact
    // count would not be readable from it, and the legend has nothing to
    // anchor to). The color stops are set per response in `setCoverageDisplay`
    // (log-scaled, anchored on that response's own maximum).
    map.addLayer({
      id: 'coverage-heat',
      type: 'fill',
      source: COVERAGE_SRC,
      layout: { visibility: 'none' },
      paint: {
        // maplibre-gl doesn't export the expression-spec type this needs, so
        // `coverage.ts` returns a plain array and the cast happens once,
        // here — `setPaintProperty` below takes `value: any` and needs none.
        'fill-color': coverageFillColorExpression(1) as never,
        'fill-opacity': 0.5,
        'fill-outline-color': 'rgba(0,0,0,0)',
      },
    });
  }
  if (!map.getSource(COVERAGE_FOOTPRINTS_SRC)) {
    map.addSource(COVERAGE_FOOTPRINTS_SRC, { type: 'geojson', data: EMPTY_FC });
    // Below the switch point (`footprints_advised`), real scene footprints
    // replace the density cells — outlines only, so the imagery underneath
    // stays visible.
    map.addLayer({
      id: 'coverage-footprints-line',
      type: 'line',
      source: COVERAGE_FOOTPRINTS_SRC,
      layout: { visibility: 'none' },
      paint: { 'line-color': '#a6d96a', 'line-width': 1.4, 'line-opacity': 0.85 },
    });
  }
  if (!map.getSource(SEL_SRC)) {
    map.addSource(SEL_SRC, { type: 'geojson', data: EMPTY_FC });
    map.addLayer({
      id: 'mosaicsel-line',
      type: 'line',
      source: SEL_SRC,
      paint: { 'line-color': '#ffd166', 'line-width': 3, 'line-blur': 1, 'line-opacity': 0.95 },
    });
  }
}

export type CoverageDisplayMode = 'off' | 'density' | 'footprints';

export interface CoverageDisplay {
  mode: CoverageDisplayMode;
  cells: CoverageCell[];
  maxCount: number;
  footprints: GeoJSON.FeatureCollection | null;
}

// Reconciles both coverage layers with the current mode — only one of the
// two ever carries data, so a stray re-render can't show density and
// footprints at once (`store.ts` picks the mode via `coverage.ts::showFootprints`).
export function setCoverageDisplay(map: MapLibreMap, display: CoverageDisplay): void {
  const density = display.mode === 'density';
  const footprints = display.mode === 'footprints';
  setData(map, COVERAGE_SRC, density ? cellsToFeatureCollection(display.cells) : EMPTY_FC);
  if (density && map.getLayer('coverage-heat')) {
    map.setPaintProperty('coverage-heat', 'fill-color', coverageFillColorExpression(display.maxCount));
  }
  setVisibility(map, 'coverage-heat', density);
  setData(map, COVERAGE_FOOTPRINTS_SRC, footprints ? (display.footprints ?? EMPTY_FC) : EMPTY_FC);
  setVisibility(map, 'coverage-footprints-line', footprints);
}

function setVisibility(map: MapLibreMap, layerId: string, visible: boolean): void {
  if (!map.getLayer(layerId)) return;
  map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none');
}

function setData(map: MapLibreMap, srcId: string, data: GeoJSON.GeoJSON): void {
  const src = map.getSource(srcId) as GeoJSONSource | undefined;
  if (src) src.setData(data);
}

export function setAoiData(map: MapLibreMap, geom: GeoJSON.Geometry | null): void {
  setData(map, AOI_SRC, asFeatureCollection(geom));
}

function clearDynamicMosaic(map: MapLibreMap): void {
  // Remove by deterministic id across the whole index range — not just the
  // tracked ids — so an overlay placed by a slow async quicklook load that
  // finished around a re-sync can't survive as an orphan.
  for (let i = 0; i < MAX_MOSAIC_LAYERS; i++) {
    for (const lyr of [`m-img-lyr-${i}`, `m-tiles-lyr-${i}`]) {
      if (map.getLayer(lyr)) map.removeLayer(lyr);
    }
    for (const src of [`m-img-src-${i}`, `m-tiles-src-${i}`]) {
      if (map.getSource(src)) map.removeSource(src);
    }
  }
  dynLayerIds = [];
  dynSourceIds = [];
}

const beforeAoi = (map: MapLibreMap): string | undefined =>
  map.getLayer('aoi-fill') ? 'aoi-fill' : undefined;

function footprintOf(item: StacItem): GeoJSON.Geometry | null {
  if (item.geometry) return item.geometry;
  return item.bbox ? bboxToPolygon(item.bbox) : null;
}

// Exported for M2-07c: the same footprint-or-bbox fallback the mosaic
// selection highlight uses, reused to draw real scene footprints once the
// coverage answer's `footprints_advised` switches the map away from density.
export function footprintsFC(items: StacItem[]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const it of items) {
    const g = footprintOf(it);
    if (g) features.push({ type: 'Feature', properties: { id: it.id }, geometry: g });
  }
  return { type: 'FeatureCollection', features };
}

function addQuicklook(map: MapLibreMap, item: StacItem, i: number, gen: number): void {
  const coords = quicklookCoords(item);
  const asset = quicklookAsset(item);
  if (!coords || !asset) return;
  const srcId = `m-img-src-${i}`;
  const lyrId = `m-img-lyr-${i}`;
  loadTransparent(asset.href, (dataUrl) => {
    if (gen !== syncGen) return; // a newer sync superseded this group
    try {
      placeImage(map, srcId, lyrId, dataUrl, coords, 1);
      dynSourceIds.push(srcId);
      dynLayerIds.push(lyrId);
    } catch {
      /* map/style went away while loading */
    }
  });
}

function addTiles(map: MapLibreMap, info: DownloadedInfo, i: number, render: AppliedRender): void {
  const srcId = `m-tiles-src-${i}`;
  const lyrId = `m-tiles-lyr-${i}`;
  placeRaster(map, srcId, lyrId, buildTileUrl(info, render), info.bounds, 1);
  dynSourceIds.push(srcId);
  dynLayerIds.push(lyrId);
}

// --- layer manager rendering (pinned overlays, independent of the active view) ---
function clearLayerOverlays(map: MapLibreMap): void {
  for (let i = 0; i < MAX_LAYER_OVERLAYS; i++) {
    if (map.getLayer(`layer-lyr-${i}`)) map.removeLayer(`layer-lyr-${i}`);
    if (map.getSource(`layer-src-${i}`)) map.removeSource(`layer-src-${i}`);
  }
}

export function syncLayers(map: MapLibreMap, layers: MapLayer[]): void {
  const gen = ++layerGen;
  clearLayerOverlays(map);
  // Render bottom-to-top: layers[0] is the top of the list, so draw it last.
  let idx = 0;
  for (const layer of [...layers].reverse()) {
    if (!layer.visible) continue;
    for (const ov of layer.overlays) {
      if (idx >= MAX_LAYER_OVERLAYS) break;
      const srcId = `layer-src-${idx}`;
      const lyrId = `layer-lyr-${idx}`;
      idx += 1;
      if (ov.kind === 'raster') {
        placeRaster(map, srcId, lyrId, ov.tileUrl, ov.bounds, layer.opacity);
      } else {
        loadTransparent(ov.url, (dataUrl) => {
          if (gen !== layerGen) return;
          try {
            placeImage(map, srcId, lyrId, dataUrl, ov.coords, layer.opacity);
          } catch {
            /* superseded / map gone */
          }
        });
      }
    }
  }
}

export interface MosaicState {
  items: StacItem[]; // items of the active time step
  downloaded: Record<string, DownloadedInfo>;
  selectedIds: string[];
  render: AppliedRender;
  focusMode: boolean; // full-res tiles are only drawn while focused on a download
  showDownloaded: boolean; // when false, downloaded full-res overlays are hidden
}

/** Reconcile the whole active group: simultaneously show one overlay per
 *  adjacent frame covering the AOI (quicklook, or pyramidal tiles once
 *  downloaded), plus a highlight around frames selected for download. */
export function syncMosaic(map: MapLibreMap, s: MosaicState): void {
  const gen = ++syncGen;
  clearDynamicMosaic(map);
  if (s.focusMode) {
    // Full-res view: render each downloaded overlay (a normal crop, a stitched
    // mosaic, or a decomposition). Hidden via the visibility toggle.
    if (s.showDownloaded) {
      Object.values(s.downloaded)
        .slice(0, MAX_MOSAIC_LAYERS)
        .forEach((info, i) => addTiles(map, info, i, s.render));
    }
    setData(map, SEL_SRC, EMPTY_FC);
    return;
  }
  // Browsing: quicklooks for the active time step; highlight selected footprints.
  const items = s.items.slice(0, MAX_MOSAIC_LAYERS);
  items.forEach((it, i) => addQuicklook(map, it, i, gen));
  setData(map, SEL_SRC, footprintsFC(items.filter((it) => s.selectedIds.includes(it.id))));
}
