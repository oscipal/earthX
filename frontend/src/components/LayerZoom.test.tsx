// @vitest-environment jsdom
//
// UI-09 (Otto, 16.11.2026): "Zoom to layer" in every row of the layer manager, left of the download, fits the map to the extent of the layer. The
// row has no loading mark any more: the map says "Loading data" in the status bar.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { jobEntry, jobId, NOW } from '../fixtures/jobEntries';
import { GROUPS, ITEMS } from '../fixtures/swissalti';
import { setMapLoading } from '../layerLoading';
import { LOCKED_LAYER_TIP, type LayerOverlay, type MapLayer } from '../layers';
import { RESULTS_OWNER } from '../mapLayers';
import { resetJobs, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import LayerManager, { ZOOM_LAYER_TIP } from './LayerManager';
import { LOADING_AFTER_MS } from './usePreviewLoading';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const raster = (bounds: [number, number, number, number]): LayerOverlay => ({ kind: 'raster', tileUrl: 't/{z}/{x}/{y}', bounds, minZoom: 0, maxZoom: 14 });
const restore = { datasetId: 'ds', itemIds: ['s'], groupItemIds: [['s']], aoi: null, cropToAoi: false } as unknown as MapLayer['restore'];
const layer = (id: string, over: Partial<MapLayer> = {}): MapLayer => ({ id, name: id, visible: true, opacity: 1, overlays: [raster([10, 47, 11, 48])], restore, ...over });
const result = (over: object) => ({ jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, ...over });

const rows = () => [...container.querySelectorAll<HTMLElement>('.layer-row')];
const zoom = (row: number) => rows()[row].querySelector<HTMLElement>('[data-col="zoom"]')!;
const show = (layers: MapLayer[]) => {
  useAppStore.setState({ datasets: [], layers, dock: 'layers', flyToBbox: null, mapLoading: [], sections: [] });
  act(() => root.render(<LayerManager />));
};

beforeEach(() => {
  vi.useFakeTimers();
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

describe('Zoom to layer', () => {
  it('sits directly left of the download, as an icon with the name in the tooltip and nowhere else', () => {
    show([layer('a')]);
    const button = zoom(0);
    expect(button.tagName).toBe('BUTTON');
    expect(button.getAttribute('aria-label')).toBe('Zoom to layer');
    expect(button.getAttribute('data-tip')).toBe(ZOOM_LAYER_TIP);
    expect(button.textContent).toBe('');
    expect(button.querySelector('svg')).not.toBeNull();
    const cols = [...rows()[0].children].map((c) => c.getAttribute('data-col'));
    expect(cols.indexOf('zoom') + 1).toBe(cols.indexOf('download'));
  });

  it('fits the map to the extent of the layer when it is clicked, also for a layer that is switched off', () => {
    show([layer('a', { overlays: [raster([10, 47, 11, 48]), raster([12, 46, 13, 47.5])] }), layer('b', { visible: false, overlays: [raster([-5, 40, -4, 41])] })]);
    act(() => zoom(0).click());
    expect(useAppStore.getState().flyToBbox).toEqual([10, 46, 13, 48]);
    act(() => zoom(1).click());
    expect(useAppStore.getState().flyToBbox).toEqual([-5, 40, -4, 41]);
  });

  it('fits a job result as well', () => {
    show([layer('r', { derived: 'result', result: result({}) as MapLayer['result'], overlays: [raster([6, 46, 7, 47])] })]);
    act(() => zoom(0).click());
    expect(useAppStore.getState().flyToBbox).toEqual([6, 46, 7, 47]);
  });

  it('leaves its place empty, hidden from the screen reader, where the layer has no extent', () => {
    show([layer('none', { overlays: [] })]);
    expect([zoom(0).tagName, zoom(0).getAttribute('aria-hidden'), zoom(0).className]).toEqual(['SPAN', 'true', 'lm-slot']);
  });

  it('leaves its place empty for an expired result, whose data is gone', () => {
    show([layer('old', { derived: 'result', result: result({ expired: true }) as MapLayer['result'] })]);
    expect(zoom(0).className).toBe('lm-slot');
  });

  it('is locked with the one reason of the row while the job is deleted, and does not move the map', () => {
    vi.setSystemTime(NOW);
    resetJobs();
    show([layer('del', { derived: 'result', result: result({ jobID: jobId(1) }) as MapLayer['result'] })]);
    act(() => useProcessingStore.setState({ jobs: [jobEntry(1, { phase: 'dismissed', deletedUntil: new Date(NOW + 86_400_000).toISOString(), serverDeleted: true })] }));
    expect(zoom(0).tagName).toBe('BUTTON');
    expect(zoom(0).hasAttribute('disabled')).toBe(true);
    expect(zoom(0).getAttribute('data-tip')).toBe(LOCKED_LAYER_TIP);
    act(() => zoom(0).click());
    expect(useAppStore.getState().flyToBbox).toBeNull();
  });

  it('is not asked for a layer that is gone', () => {
    show([layer('a')]);
    act(() => useAppStore.getState().zoomToLayer('missing'));
    expect(useAppStore.getState().flyToBbox).toBeNull();
  });

  it('has the row of the search results leave the place empty', () => {
    useAppStore.setState({ datasets: [], layers: [], dock: 'layers', flyToBbox: null, sections: [{ datasetId: 'terrain', items: ITEMS, groups: GROUPS, notes: [], groupingError: null, origin: 'search' as const, incomplete: false }] });
    act(() => root.render(<LayerManager />));
    const entry = container.querySelector('.results-row')!;
    expect(entry.querySelector('[data-col="zoom"]')?.className).toBe('lm-slot');
  });
});

describe('the row while its tiles load', () => {
  it('shows no loading circle, long after the moment, for a layer or the search results', () => {
    show([layer('a')]);
    act(() => setMapLoading(['a', RESULTS_OWNER]));
    act(() => void vi.advanceTimersByTime(LOADING_AFTER_MS * 3));
    expect(container.querySelectorAll('.spinner, [role="status"]')).toHaveLength(0);
    expect(rows()[0].querySelector('[data-col="note"]')?.className).toBe('lm-slot');
  });
});
