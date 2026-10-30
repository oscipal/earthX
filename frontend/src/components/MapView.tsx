import { useEffect, useMemo, useRef } from 'react';
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
import { areaGeometry, isAreaAnswer, showFootprints } from '../coverage';
import { bufferPointToPolygon, pointInFootprint, polygonBbox } from '../geoUtils';
import { openIdsOf, resultsOnMapOf } from '../mapResults';
import { mosaicsOfView, sameMosaics } from '../mosaic';
import type { CoverageDisplay } from '../mapLayers';
import {
  ensureBaseLayers,
  hasOwnLayers,
  overlayBudgetNote,
  setAoiData,
  setCoverageDisplay,
  syncBrowseMosaic,
  syncFocusRaster,
  syncHighlight,
  syncLayers,
  syncMosaic,
  syncPreview,
  syncResultsOverlay,
  watchPreviewLoading,
} from '../mapLayers';
import { DEFAULT_BASEMAP } from '../basemaps';
import { applyMapBackground, applyProjection, ATTRIBUTION_CONTROL, baseMapStyle, createBasemapSwitcher, isInFirstStyle, mapBackgroundOf } from '../mapStyles';
import { previewOverlays } from '../processingPreview';
import { useProcessingStore } from '../processingStore';
import { layersForMap, viewLayerOf, viewShown } from '../viewLayer';
import { useAppStore } from '../store';
import type { StacItem, ToolMode } from '../types';

// Only one of density/footprints/area is ever drawn (mapLayers.ts): a one-off
// product's extent (`area`, M3-12 F-07, ENTSCHEIDUNGEN §2) whenever the
// answer names one, footprints once the backend advises them *and* the zoom
// brake agrees (coverage.ts) for a time series, a density fill otherwise.
// Turned off in focus mode so a full-resolution raster is never obscured by a
// leftover coverage layer underneath it.
function coverageDisplayFor(st: ReturnType<typeof useAppStore.getState>, zoom: number): CoverageDisplay {
  const off: CoverageDisplay = { mode: 'off', cells: [], maxCount: 0, footprints: null, area: null };
  if (!st.showCoverage || st.focusMode || !st.coverage) return off;
  if (isAreaAnswer(st.coverage)) {
    return { ...off, mode: 'area', area: areaGeometry(st.coverage) };
  }
  // Falls back to the density it already has rather than an empty layer
  // while the footprints request is still in flight or failed
  // (store.ts::refreshCoverage leaves `coverageFootprints` at `null` then).
  if (showFootprints(st.coverage, zoom) && st.coverageFootprints) {
    return { ...off, mode: 'footprints', footprints: st.coverageFootprints };
  }
  return { ...off, mode: 'density', cells: st.coverage.cells, maxCount: st.coverage.max_count };
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

// Registered once for the whole page, not per map instance — `addProtocol`
// is a maplibre-gl-wide registration (M3-09), so re-mounting `MapView` gains
// nothing from repeating it (and `addProtocol` is idempotent either way).
addProtocol(AOI_CLIP_PROTOCOL, aoiClipProtocol);

// The same list while its scenes are the same ones: an effect that draws them runs again only for another list.
function useSameScenes(items: StacItem[]): StacItem[] {
  const ref = useRef(items);
  if (ref.current !== items && !(ref.current.length === items.length && ref.current.every((it, i) => it === items[i]))) ref.current = items;
  return ref.current;
}

// The step of the timeline that is on the map, told to the playing (`playback.ts`) while it plays.
const reportShown = (index: number) => {
  if (useAppStore.getState().playing) useAppStore.setState({ shownGroupIndex: index });
};

export default function MapView() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const drawRef = useRef<TerraDraw | null>(null);
  const readyRef = useRef(false);
  // The time step the browse preview was last synced for, while the timeline plays.
  const heldIndexRef = useRef<number | null>(null);
  const basemapRef = useRef<ReturnType<typeof createBasemapSwitcher> | null>(null);

  // Reactive slices used to drive the imperative map updates.
  const toolMode = useAppStore((s) => s.toolMode);
  const aoi = useAppStore((s) => s.aoi);
  const groups = useAppStore((s) => s.groups);
  const items = useAppStore((s) => s.items);
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const expandedGroupIndex = useAppStore((s) => s.expandedGroupIndex);
  const selectedIds = useAppStore((s) => s.selectedIds);
  const downloaded = useAppStore((s) => s.downloaded);
  const allMosaics = useAppStore((s) => s.mosaics);
  const flyToBbox = useAppStore((s) => s.flyToBbox);
  const flyToView = useAppStore((s) => s.flyToView);
  const appliedRender = useAppStore((s) => s.appliedRender);
  const focusMode = useAppStore((s) => s.focusMode);
  const cropToAoi = useAppStore((s) => s.cropToAoi);
  // The area a cropped view was opened with: the view is cut to it whatever the area in the control menu becomes.
  const viewAoi = useAppStore((s) => s.viewAoi);
  const showDownloaded = useAppStore((s) => s.showDownloaded);
  const showCoverage = useAppStore((s) => s.showCoverage);
  const coverage = useAppStore((s) => s.coverage);
  const coverageFootprints = useAppStore((s) => s.coverageFootprints);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const layers = useAppStore((s) => s.layers);
  const viewLayerId = useAppStore((s) => s.viewLayerId);
  const resultsOnMap = useAppStore((s) => s.resultsOnMap);
  const playing = useAppStore((s) => s.playing);
  const activeGroupIndex = useAppStore((s) => s.activeGroupIndex);
  const revealNotBefore = useAppStore((s) => s.revealNotBefore);
  const sections = useAppStore((s) => s.sections);
  const openSectionId = useAppStore((s) => s.openSectionId);
  const projection = useAppStore((s) => s.projection);
  const basemap = useAppStore((s) => s.basemap);
  const overlays = useAppStore((s) => s.overlays);
  const theme = useAppStore((s) => s.theme);
  const preview = useProcessingStore((s) => s.preview);
  // Cut to the AOI only for "AOI only": a new AOI leaves the others alone.
  const clipAoi = preview?.clipToAoi ? aoi : null;
  const previewTiles = useMemo(() => (preview ? previewOverlays(preview, clipAoi) : []), [preview, clipAoi]);
  const previewTilesRef = useRef(previewTiles);
  previewTilesRef.current = previewTiles;

  // --- create the map once ---
  useEffect(() => {
    if (!containerRef.current) return;
    const map = new MapLibreMap({
      container: containerRef.current,
      style: baseMapStyle(mapBackgroundOf(containerRef.current), useAppStore.getState().basemap),
      center: [10, 20],
      zoom: 1.6,
      attributionControl: ATTRIBUTION_CONTROL,
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
    watchPreviewLoading(map, (loading) => {
      if (useProcessingStore.getState().previewTilesLoading !== loading) useProcessingStore.setState({ previewTilesLoading: loading });
    });
    const first = useAppStore.getState().basemap;
    basemapRef.current = createBasemapSwitcher(map, isInFirstStyle(first) ? first : null, (reason, keep, overlays) => {
      // The map keeps what it shows; the choice stays saved, so that the next visit tries it again.
      useAppStore.getState().setError(reason);
      useAppStore.setState({ basemap: keep ?? DEFAULT_BASEMAP, overlays });
    });
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
        store.reopenControls();
      });
      drawRef.current = draw;
      applyToolMode(draw, useAppStore.getState().toolMode);
    };

    // Lay every custom layer when the first style has loaded. A change of the basemap fires `style.load` too, with
    // the app's layers all still there: laying them again would blink the pictures and restart the drawing tool.
    const onStyleLoad = () => {
      const carried = hasOwnLayers(map);
      if (!carried) ensureBaseLayers(map);
      const st = useAppStore.getState();
      applyProjection(map, st.projection);
      // A basemap with a published style comes after the first style (it is fetched).
      basemapRef.current?.show(st.basemap, st.overlays);
      if (carried) return;
      setAoiData(map, st.aoi);
      setCoverageDisplay(map, coverageDisplayFor(st, map.getZoom()));
      const viewLayer = viewLayerOf(st.layers, st);
      const shown = resultsOnMapOf(st);
      syncLayers(map, layersForMap(st.layers, viewLayer, st.showDownloaded));
      syncMosaic(map, {
        // What browsing draws; a view draws its own scenes and needs the whole list for the quicklook under them.
        items: st.focusMode ? st.items : shown.quicklooks,
        highlight: shown.highlight,
        dataset: st.datasets.find((d) => d.id === st.datasetId) ?? null,
        downloaded: st.downloaded,
        selectedIds: st.selectedIds,
        render: st.appliedRender,
        focusMode: st.focusMode,
        showDownloaded: viewShown(viewLayer, st.showDownloaded),
        tilesInLayer: viewLayer !== null,
        aoi: st.viewAoi,
        cropToAoi: st.cropToAoi,
        groups: st.groups,
        datasets: st.datasets,
        openIds: openIdsOf(st.groups, st.expandedGroupIndex),
      });
      syncResultsOverlay(map, { items: shown.overlay, openIds: openIdsOf(st.groups, st.expandedGroupIndex), selectedIds: st.selectedIds, dataset: st.datasets.find((d) => d.id === st.datasetId) ?? null, datasets: st.datasets });
      syncPreview(map, previewTilesRef.current);
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
      const { lng, lat } = e.lngLat;
      // Toggle the frame under the cursor, among the scenes that are drawn.
      const hit = resultsOnMapOf(st).clickable.find((it) => pointInFootprint(lng, lat, it.geometry, it.bbox));
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

  // --- backdrop colour: the theme token, into the style's own background layer
  // and the globe's sky, on every theme switch ---
  useEffect(() => {
    const map = mapRef.current;
    const colour = mapBackgroundOf(containerRef.current);
    if (map && readyRef.current && colour) applyMapBackground(map, colour);
  }, [theme]);

  // --- globe / flat map (V-1) — a display-only switch (D27); backend and
  // tile URLs are unaffected, `setProjection` just re-renders the same layers.
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) applyProjection(map, projection);
  }, [projection]);

  // --- basemap (UI-02a) under the app's own layers, which stay where they are, and the overlays (UI-02b) over them ---
  useEffect(() => {
    if (readyRef.current) basemapRef.current?.show(basemap, overlays);
  }, [basemap, overlays]);

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
  // The mosaics this view asks for, the same object until one of them changes: another view's
  // TileJSON arriving must not tear this view's tiles down.
  const picked = useMemo(
    () => mosaicsOfView(allMosaics, datasetId, Object.entries(downloaded), groups),
    [allMosaics, datasetId, downloaded, groups],
  );
  const mosaicsRef = useRef(picked);
  if (!sameMosaics(mosaicsRef.current, picked)) mosaicsRef.current = picked;
  const mosaics = mosaicsRef.current;
  // The layer that is the full-resolution view (`viewLayer.ts`) draws it at its
  // place, with its eye.
  // Which of the search results are on the map: `mapResults.ts` alone says.
  const shown = useMemo(
    () => resultsOnMapOf({ resultsOnMap, focusMode, groups, expandedGroupIndex, selectedIds, downloaded, sections, openSectionId }),
    [resultsOnMap, focusMode, groups, expandedGroupIndex, selectedIds, downloaded, sections, openSectionId],
  );
  // The scenes of the group that is open lie on top of the other results; a change of group lays them out again.
  const openIds = useMemo(() => openIdsOf(groups, expandedGroupIndex), [groups, expandedGroupIndex]);
  const quicklooks = useSameScenes(shown.quicklooks);
  const overlay = useSameScenes(shown.overlay);
  const highlight = useSameScenes(shown.highlight);
  // The ticked scenes, whose quicklooks lie over the other results in the order they were ticked (`mapLayers.ts`).
  const ticked = useMemo(() => highlight.map((item) => item.id), [highlight]);
  const viewLayer = useMemo(
    () => viewLayerOf(layers, { viewLayerId, focusMode, downloaded, appliedRender, cropToAoi, aoi: viewAoi, showDownloaded }),
    [layers, viewLayerId, focusMode, downloaded, appliedRender, cropToAoi, viewAoi, showDownloaded],
  );
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) {
      const note = overlayBudgetNote(
        syncLayers(map, layersForMap(layers, viewLayer, showDownloaded)),
      );
      if (note && useAppStore.getState().notice !== note) useAppStore.setState({ notice: note });
    }
  }, [layers, viewLayer, showDownloaded]);

  // --- full-resolution raster tiles (focus mode) — deliberately not keyed on
  // `selectedIds`: a selection toggle must never tear these down and reload
  // them, only change the highlight (the effect below handles that). Cut to the
  // area the view was opened with (`viewAoi`, Otto 27.10.2026), not to the one in
  // the control menu: drawing, changing or clearing that leaves the view alone. ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current && focusMode) {
      const dataset = datasets.find((d) => d.id === datasetId) ?? null;
      syncFocusRaster(map, {
        downloaded,
        render: appliedRender,
        showDownloaded: viewShown(viewLayer, showDownloaded),
        tilesInLayer: viewLayer !== null,
        aoi: viewAoi,
        cropToAoi,
        items,
        dataset,
        groups,
        mosaics,
      });
    }
  }, [focusMode, downloaded, appliedRender, showDownloaded, viewLayer, viewAoi, cropToAoi, items, datasets, datasetId, groups, mosaics]);

  // --- the preview of the processing panel (M4-13c-2), a tier of "Results" over the results and the view
  // (`mapLayers.ts`); a new AOI cuts it again. ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) syncPreview(map, previewTiles);
  }, [previewTiles]);

  // --- browse-mode preview overlays (quicklooks / preview tiles) — these do
  // react to `selectedIds`, since a cross-group selection can pin a scene
  // from a time step that isn't the expanded one onto the map (V-3, finding 2). ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current && !focusMode) {
      // While the timeline plays, the step arrives out of sight and says when it is on the map (`playback.ts`).
      const now = useAppStore.getState();
      const shownIndex = now.expandedGroupIndex ?? now.activeGroupIndex;
      const hold = now.playing ? { notBefore: now.revealNotBefore, onShown: () => reportShown(shownIndex) } : undefined;
      heldIndexRef.current = shownIndex;
      syncBrowseMosaic(map, { items: quicklooks, openIds, selectedIds: ticked, dataset: datasets.find((d) => d.id === datasetId) ?? null, datasets, hold });
    }
  }, [focusMode, quicklooks, openIds, ticked, datasets, datasetId]);

  // --- a step of the timeline that the effect above did not draw (the results are off the map, or the step is the same
  // scenes as the one before): there is nothing to wait for, and the playing is told once the picture before it has had
  // its time ---
  useEffect(() => {
    if (!playing || focusMode) return;
    const index = expandedGroupIndex ?? activeGroupIndex;
    if (heldIndexRef.current === index) return;
    const id = window.setTimeout(() => {
      heldIndexRef.current = index;
      reportShown(index);
    }, Math.max(0, revealNotBefore - Date.now()));
    return () => window.clearTimeout(id);
  }, [playing, focusMode, expandedGroupIndex, activeGroupIndex, revealNotBefore]);

  // --- the results over a full-resolution view, while the eye of "Results" is on: over the view, in the tiers of
  // browsing (`mapLayers.ts`). ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) syncResultsOverlay(map, { items: overlay, openIds, selectedIds: ticked, dataset: datasets.find((d) => d.id === datasetId) ?? null, datasets });
  }, [focusMode, overlay, openIds, ticked, datasets, datasetId, downloaded, appliedRender, showDownloaded, viewLayer, viewAoi, cropToAoi, mosaics]);

  // --- selection highlight — cheap, runs in both modes independently of the
  // (potentially expensive) overlay rebuilds above. In a cropped focus view
  // ("Crop & merge to AOI", M3-09 §10) this draws one ring per group instead
  // of one per scene (`syncHighlight` picks between the two). ---
  useEffect(() => {
    const map = mapRef.current;
    if (map && readyRef.current) {
      syncHighlight(map, {
        items: highlight,
        selectedIds,
        focusMode,
        cropToAoi,
        aoi: viewAoi,
        downloaded,
        groups,
      });
    }
  }, [groups, focusMode, cropToAoi, viewAoi, downloaded, highlight, selectedIds]);

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

  // --- jump to the view of a permalink ---
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !flyToView) return;
    map.jumpTo({ center: flyToView.center, zoom: flyToView.zoom });
    useAppStore.getState().clearFlyView();
  }, [flyToView]);

  return <div ref={containerRef} className="map" />;
}
