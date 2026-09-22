import { useEffect, useRef } from 'react';
import { Map as MapLibreMap, NavigationControl } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import {
  TerraDraw,
  TerraDrawPointMode,
  TerraDrawPolygonMode,
  TerraDrawRectangleMode,
} from 'terra-draw';
import { TerraDrawMapLibreGLAdapter } from 'terra-draw-maplibre-gl-adapter';

import { showFootprints } from '../coverage';
import { bufferPointToPolygon, pointInFootprint, polygonBbox } from '../geoUtils';
import type { CoverageDisplay } from '../mapLayers';
import { ensureBaseLayers, setAoiData, setCoverageDisplay, syncLayers, syncMosaic } from '../mapLayers';
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
  const selectedIds = useAppStore((s) => s.selectedIds);
  const downloaded = useAppStore((s) => s.downloaded);
  const flyToBbox = useAppStore((s) => s.flyToBbox);
  const appliedRender = useAppStore((s) => s.appliedRender);
  const focusMode = useAppStore((s) => s.focusMode);
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
        if (geom.type === 'Point') {
          const [lon, lat] = (geom as GeoJSON.Point).coordinates;
          const buffer = store.config?.point_buffer_deg ?? 0.05;
          geom = bufferPointToPolygon(lon, lat, buffer);
        }
        store.setAoi(geom);
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
        items: st.groups[st.activeGroupIndex]?.items ?? [],
        dataset: st.datasets.find((d) => d.id === st.datasetId) ?? null,
        downloaded: st.downloaded,
        selectedIds: st.selectedIds,
        render: st.appliedRender,
        focusMode: st.focusMode,
        showDownloaded: st.showDownloaded,
      });
      initDraw();
      readyRef.current = true;
      // The store needs an initial zoom before the first `moveend` (which
      // only fires once the user pans/zooms) so a coverage fetch can pick a
      // sensible geotile level from the very first render.
      useAppStore.getState().setMapZoom(map.getZoom());
    };
    map.on('style.load', onStyleLoad);

    // Coverage (M2-07c) reacts to the map's zoom — its geotile *level*, per
    // adr/0004 §6.3 — never to the pan viewport as a spatial filter (see the
    // long comment on `refreshCoverage` in store.ts). Registered once on the
    // map itself (unlike the custom layers, listeners survive a style reload).
    map.on('moveend', () => {
      useAppStore.getState().setMapZoom(map.getZoom());
    });

    // Clicking the displayed imagery toggles that scene's download selection
    // (only when no drawing tool is active, so it never eats draw clicks).
    map.on('click', (e) => {
      const st = useAppStore.getState();
      if (st.toolMode !== 'none') return;
      const group = st.groups[st.activeGroupIndex];
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

  // --- active overlay / selection highlight ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) {
      syncMosaic(map, {
        items: groups[activeGroupIndex]?.items ?? [],
        dataset: datasets.find((d) => d.id === datasetId) ?? null,
        downloaded,
        selectedIds,
        render: appliedRender,
        focusMode,
        showDownloaded,
      });
    }
  }, [
    groups,
    activeGroupIndex,
    selectedIds,
    downloaded,
    appliedRender,
    focusMode,
    showDownloaded,
    datasets,
    datasetId,
  ]);

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
