// @vitest-environment jsdom
//
// Plan M5-30 §8.7, Otto 13.11.2026: a map layer that takes longer than a moment to load shows a mark (a symbol, no text) in its row of the
// layer manager, and the mark goes with the loading.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DOWNLOADED, GROUPS, ITEMS, LIST } from '../fixtures/swissalti';
import { pinned } from '../fixtures/liveMap';
import { setMapLoading } from '../layerLoading';
import { RESULTS_OWNER } from '../mapLayers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';
import { LOADING_MARK_TIP } from './useLayerLoading';
import { LOADING_AFTER_MS } from './usePreviewLoading';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.useFakeTimers();
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({
    layers: [
      pinned('A', '/a/{z}/{x}/{y}', { name: 'First', restore: { datasetId: 'optical', itemIds: [] } as never }),
      pinned('B', '/b/{z}/{x}/{y}', { name: 'Second', restore: { datasetId: 'optical', itemIds: [] } as never }),
    ],
    mapLoading: [],
    focusMode: false,
    downloaded: {},
    mosaics: {},
    sections: [{ datasetId: 'terrain', items: ITEMS, groups: GROUPS, notes: [], groupingError: null, origin: 'search' as const, incomplete: false }],
    dock: 'layers',
    resultsAt: 1,
  });
  act(() => root.render(<LayerManager />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

const marks = () => [...container.querySelectorAll<HTMLElement>('[role="status"]')];
const rowOf = (name: string) => [...container.querySelectorAll('.layer-row')].find((row) => row.textContent?.includes(name))!;
const wait = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

describe('the loading mark of a layer', () => {
  it('shows nothing while no tile is on its way', () => {
    expect(marks()).toEqual([]);
  });

  it('appears once the loading has lasted a moment, in the row of that layer and no other, as a symbol without text', () => {
    act(() => setMapLoading(['A']));
    wait(LOADING_AFTER_MS - 1);
    expect(marks()).toEqual([]);
    wait(1);
    expect(marks()).toHaveLength(1);
    const [mark] = marks();
    expect(rowOf('First').contains(mark)).toBe(true);
    expect(rowOf('Second').contains(mark)).toBe(false);
    expect(mark.textContent).toBe('');
    expect(mark.getAttribute('aria-label')).toBe(LOADING_MARK_TIP);
    expect(mark.getAttribute('data-tip')).toBe(LOADING_MARK_TIP);
    expect(mark.className).toContain('spinner');
  });

  it('does not appear for a tile that is there before the moment is over', () => {
    act(() => setMapLoading(['A']));
    wait(LOADING_AFTER_MS - 100);
    act(() => setMapLoading([]));
    wait(LOADING_AFTER_MS * 3);
    expect(marks()).toEqual([]);
  });

  it('goes when the tiles are loaded, and the count starts anew for the next load', () => {
    act(() => setMapLoading(['A']));
    wait(LOADING_AFTER_MS);
    expect(marks()).toHaveLength(1);
    act(() => setMapLoading([]));
    expect(marks()).toEqual([]);
    act(() => setMapLoading(['A']));
    wait(LOADING_AFTER_MS - 1);
    expect(marks()).toEqual([]);
  });

  it('is in the row of each layer that loads', () => {
    act(() => setMapLoading(['A', 'B']));
    wait(LOADING_AFTER_MS);
    expect(marks()).toHaveLength(2);
  });

  it('is not shown for a layer that is switched off: it loads nothing', () => {
    useAppStore.setState({ layers: useAppStore.getState().layers.map((l) => (l.id === 'A' ? { ...l, visible: false } : l)) });
    act(() => setMapLoading(['A']));
    wait(LOADING_AFTER_MS);
    expect(marks()).toEqual([]);
  });

  it('is shown for "Search results", the view and the preview, which are one entry, by what the map loads for them', () => {
    act(() => setMapLoading([RESULTS_OWNER]));
    wait(LOADING_AFTER_MS);
    expect(marks()).toHaveLength(1);
    expect(rowOf('Search results').contains(marks()[0])).toBe(true);
  });

  it('is shown for the view while the selection of its mosaic is being made, though no tile has been asked for', () => {
    act(() =>
      useAppStore.setState({
        focusMode: true,
        showDownloaded: true,
        downloaded: DOWNLOADED,
        datasets: LIST,
        datasetId: 'terrain',
        items: ITEMS,
        groups: GROUPS,
        sections: [{ datasetId: 'terrain', items: ITEMS, groups: GROUPS, notes: [], groupingError: null, origin: 'search' as const, incomplete: false }],
        openSectionId: 'terrain',
        shownImage: null,
        mosaics: {},
      }),
    );
    wait(LOADING_AFTER_MS);
    expect(marks()).toHaveLength(1);
    expect(rowOf('Search results').contains(marks()[0])).toBe(true);
    act(() => useAppStore.setState({ mosaics: { x: null } }));
    act(() => useAppStore.setState({ focusMode: false }));
    expect(marks()).toEqual([]);
  });
});
