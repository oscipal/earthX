import { useEffect, useRef } from 'react';
import { addProtocol, Map as MapLibreMap, NavigationControl } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  TerraDraw,
  TerraDrawPointMode,
  TerraDrawPolygonMode,
  TerraDrawRectangleMode,
} from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';

import { AOI_CLIP_PROTOCOL, aoiClipProtocol } from '../aoiClip';
import { showFootprints } from '../coverage';
import { bufferPointToPolygon, pointInFootprint, polygonBbox } from '../geoUtils';
import { itemsForMap } from '../grouping';
import type { CoverageDisplay } from '../mapLayers';
import {
  ensureBaseLayers,
  setAoiData,
  setCoverageDisplay,
  syncBrowseMosaic,
  syncFocusRaster,
  syncLayers,
  syncMosaic,
  syncSelectionHighlight,
} from '../mapLayers';
import { baseMapStyle } from '../mapStyles';
import { useAppStore } from '../store';
import type { ToolMode } from '../types';

// Only one of density/footprints is ever drawn (mapLayers.ts): footprints
// once the backend advises it *and* the zoom brake agrees (coverage.ts), a
// density fill otherwise. Turned off in focus mode so a full-resolution
// raster is never obscured by a leftover coverage layer underneath it.
function coverageDisplayFor(st: ReturnType<typeof useAppStore.getState>, zoom: number): CoverageDisplay {
  if (!st.showCoverage || st.focusMode || !st.coverage) {
    return { mode: 'off', cells: [], maxCount: 0, footprints: null };
  }
  // Falls back to the density it already has rather than an empty layer
  // while the footprints request is still in flight or failed
  // (store.ts::refreshCoverage leaves `coverageFootprints` at `null` then).
  if (showFootprints(st.coverage, zoom) && st.coverageFootprints) {
    return { mode: 'footprints', cells: [], maxCount: 0, footprints: st.coverageFootprints };
  }
  return { mode: 'density', cells: st.coverage.cells, maxCount: st.coverage.max_count, footprints: null };
}

function applyToolMode(draw: TerraDraw, mode: ToolMode): void {
  draw.setMode(mode === 'none' ? 'static' : mode);
}

// M3-19: the current map extent and its on-screen size, both of which
// `store.ts::refreshCoverage` needs (only for the no-AOI request) to derive
// the geotile level and the request bbox — read here, at the one place that
// has a live `Map` instance, rather than threaded through as separate state.
function reportViewport(map: MapLibreMap): void {
  const b = map.getBounds();
  const el = map.getContainer();
  useAppStore
    .getState()
    .setMapViewport(map.getZoom(), [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()], {
      width: el.clientWidth,
      height: el.clientHeight,
    });
}

// Which group's items the map should treat as "current" (V-11): the
// results list's own `expandedGroupIndex` in browse mode, since that is
// what quicklooks/preview tiles and the click-to-select hit test follow —
// collapsing every group there must hide them, same as never having
// expanded one. In focus mode the list isn't even shown any more (`App.tsx`
// swaps it for `ViewerControls`), so `activeGroupIndex` — the scene actually
// viewed at full resolution — is what matters instead.
function visibleGroupIndex(st: { focusMode: boolean; activeGroupIndex: number; expandedGroupIndex: number | null }): number | null {
  return st.focusMode ? st.activeGroupIndex : st.expandedGroupIndex;
}

// Registered once for the whole page, not per map instance — `addProtocol`
// is a maplibre-gl-wide registration (M3-09), so re-mounting `MapView` gains
// nothing from repeating it (and `addProtocol` is idempotent either way).
addProtocol(AOI_CLIP_PROTOCOL, aoiClipProtocol);

export default function MapView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const readyRef = useRef(false);

  // Reactive slices used to drive the imperative map updates.
  const toolMode = useAppStore((s) => s.toolMode);
  const aoi = useAppStore((s) => s.aoi);
  const groups = useAppStore((s) => s.groups);
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const activeGroupIndex = useAppStore((s) => s.activeGroupIndex);
  const expandedGroupIndex = useAppStore((s) => s.expandedGroupIndex);
  const selectedIds = useAppStore((s) => s.selectedIds);
  const downloaded = useAppStore((s) => s.downloaded);
  const flyToBbox = useAppStore((s) => s.flyToBbox);
  const appliedRender = useAppStore((s) => s.appliedRender);
  const focusMode = useAppStore((s) => s.focusMode);
  const cropToAoi = useAppStore((s) => s.cropToAoi);
  const showDownloaded = useAppStore((s) => s.showDownloaded);
  const showCoverage = useAppStore((s) => s.showCoverage);
  const coverage = useAppStore((s) => s.coverage);
  const coverageFootprints = useAppStore((s) => s.coverageFootprints);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const layers = useAppStore((s) => s.layers);
  const projection = useAppStore((s) => s.projection);

  // --- create the map once ---
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: baseMapStyle(),
      center: [10, 20],
      zoom: 1.6,
      attributionControl: { compact: true },
      // No rotate, no tilt (V-1, D27): mouse and touch only pan and zoom.
      // `maxPitch: 0` blocks tilt regardless of input method; the drag/touch/
      // keyboard handlers below additionally drop rotation itself so a
      // pinch-rotate or ctrl-drag gesture doesn't just silently do nothing.
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      maxPitch: 0,
    });
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();

    // `compact: true` only makes the attribution collapsible — MapLibre still
    // starts it expanded (`maplibregl-compact-show`/`open`) and collapses it
    // only once the user drags the map (its own `_updateCompactMinimize`,
    // bound to the `drag` event). Collapsed to the small "i" button from the
    // start instead of waiting for that first pan (V-7).
    containerRef.current
      .querySelector('.maplibregl-ctrl-attrib')
      ?.classList.remove('maplibregl-compact-show');
    containerRef.current.querySelector('.maplibregl-ctrl-attrib')?.removeAttribute('open');
    map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right');

    const initDraw = () => {
      if (drawRef.current) {
        try {
          drawRef.current.stop();
        } catch {
          /* already stopped */
        }
        drawRef.current = null;
      }
      const draw = new TerraDraw({
        adapter: new TerraDrawMapLibreGLAdapter({ map }),
        modes: [
          new TerraDrawPointMode(),
          new TerraDrawRectangleMode(),
          new TerraDrawPolygonMode(),
        ],
      });
      draw.start();
      draw.setMode('static');
      draw.on('finish', (id, context) => {
        if (context.action !== 'draw') return;
        const feat = draw.getSnapshotFeature(id);
        if (!feat) return;
        const store = useAppStore.getState();
        let geom = feat.geometry as GeoJSON.Geometry;
        // M3-08 F5a: the point itself is kept for `runSearch` to search by
        // (`store.setAoi`'s second argument) — `geom` still becomes the buffer
        // square that stays the display AOI and the download crop.
        let point: GeoJSON.Point | null = null;
        if (geom.type === 'Point') {
          point = geom as GeoJSON.Point;
          const [lon, lat] = point.coordinates;
          const buffer = store.config?.point_buffer_deg ?? 0.05;
          geom = bufferPointToPolygon(lon, lat, buffer);
        }
        store.setAoi(geom, point);
        // Zoom the map into the freshly drawn area.
        const bb = polygonBbox(geom);
        if (bb) store.flyTo(bb);
        draw.clear();
        draw.setMode('static');
        store.setToolMode('none');
        // Re-open the control panel so search/tools are reachable again.
        store.setPanelCollapsed(false);
      });
      drawRef.current = draw;
      applyToolMode(draw, useAppStore.getState().toolMode);
    };

    // Re-add every custom layer whenever a style (re)loads — including after a
    // theme switch, which wipes all custom sources/layers.
    const onStyleLoad = () => {
      ensureBaseLayers(map);
      const st = useAppStore.getState();
      map.setProjection({ type: st.projection });
      setAoiData(map, st.aoi);
      setCoverageDisplay(map, coverageDisplayFor(st, map.getZoom()));
      syncLayers(map, st.layers);
      syncMosaic(map, {
        items: itemsForMap(st.groups, visibleGroupIndex(st), st.selectedIds),
        dataset: st.datasets.find((d) => d.id === st.datasetId) ?? null,
        downloaded: st.downloaded,
        selectedIds: st.selectedIds,
        render: st.appliedRender,
        focusMode: st.focusMode,
        showDownloaded: st.showDownloaded,
        aoi: st.aoi,
        cropToAoi: st.cropToAoi,
      });
      initDraw();
      readyRef.current = true;
      // The store needs an initial viewport before the first `moveend`
      // (which only fires once the user pans/zooms) so a coverage fetch can
      // pick a sensible geotile level and bbox from the very first render.
      reportViewport(map);
    };
    map.on('style.load', onStyleLoad);

    // Coverage (M2-07c/M3-19) reacts to the map's zoom and, without an AOI,
    // its visible extent (`refreshCoverage` in store.ts). Registered once on
    // the map itself (unlike the custom layers, listeners survive a style
    // reload).
    map.on('moveend', () => {
      reportViewport(map);
    });

    // Clicking the displayed imagery toggles that scene's download selection
    // (only when no drawing tool is active, so it never eats draw clicks).
    map.on('click', (e) => {
      const st = useAppStore.getState();
      if (st.toolMode !== 'none') return;
      const idx = visibleGroupIndex(st);
      const group = idx === null ? undefined : st.groups[idx];
      if (!group) return;
      const { lng, lat } = e.lngLat;
      // Toggle the frame under the cursor.
      const hit = group.items.find((it) => pointInFootprint(lng, lat, it.geometry, it.bbox));
      if (hit) st.toggleSelected(hit.id);
    });

    return () => {
      readyRef.current = false;
      if (drawRef.current) {
        try {
          drawRef.current.stop();
        } catch {
          /* noop */
        }
        drawRef.current = null;
      }
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // --- tool mode ---
  useEffect(() => {
    if (drawRef.current && readyRef.current) applyToolMode(drawRef.current, toolMode);
  }, [toolMode]);

  // --- globe / flat map (V-1) — a display-only switch (D27); backend and
  // tile URLs are unaffected, `setProjection` just re-renders the same layers.
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) map.setProjection({ type: projection });
  }, [projection]);

  // --- AOI geometry ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) setAoiData(map, aoi);
  }, [aoi]);

  // --- coverage heatmap / footprints (M2-07c) ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) {
      setCoverageDisplay(map, coverageDisplayFor(useAppStore.getState(), mapZoom));
    }
  }, [showCoverage, coverage, coverageFootprints, mapZoom, focusMode]);

  // --- pinned layers (layer manager) ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) syncLayers(map, layers);
  }, [layers]);

  // --- full-resolution raster tiles (focus mode) — deliberately not keyed on
  // `selectedIds`: a selection toggle must never tear these down and reload
  // them, only change the highlight (the effect below handles that). Keyed on
  // `aoi` too (M3-09): redrawing the AOI while "Crop to AOI" is active must
  // re-clip the tiles already on screen. ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current && focusMode) {
      syncFocusRaster(map, { downloaded, render: appliedRender, showDownloaded, aoi, cropToAoi });
    }
  }, [focusMode, downloaded, appliedRender, showDownloaded, aoi, cropToAoi]);

  // --- browse-mode preview overlays (quicklooks / preview tiles) — these do
  // react to `selectedIds`, since a cross-group selection can pin a scene
  // from a time step that isn't the expanded one onto the map (V-3, finding 2). ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current && !focusMode) {
      syncBrowseMosaic(map, {
        items: itemsForMap(groups, expandedGroupIndex, selectedIds),
        dataset: datasets.find((d) => d.id === datasetId) ?? null,
      });
    }
  }, [focusMode, groups, expandedGroupIndex, selectedIds, datasets, datasetId]);

  // --- selection highlight — cheap, runs in both modes independently of the
  // (potentially expensive) overlay rebuilds above. ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) {
      const idx = focusMode ? activeGroupIndex : expandedGroupIndex;
      syncSelectionHighlight(map, itemsForMap(groups, idx, selectedIds), selectedIds);
    }
  }, [groups, focusMode, activeGroupIndex, expandedGroupIndex, selectedIds]);

  // --- fly to a geocoded place ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyToBbox) return;
    const [minx, miny, maxx, maxy] = flyToBbox;
    map.fitBounds(
      [
        [minx, miny],
        [maxx, maxy],
      ],
      { padding: 80, duration: 900, maxZoom: 14 },
    );
    useAppStore.getState().clearFly();
  }, [flyToBbox]);

  return <div ref={containerRef} className="map" />;
}
