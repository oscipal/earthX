// @vitest-environment jsdom
//
// Plan M5-30 §8.7, Otto 14.11.2026: tiles that load for long show as the busy toast of the status bar, the display of a search, with the text
// "Loading data". Whatever runs at the same time, there is one busy toast.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DOWNLOADED, GROUPS, ITEMS, LIST } from '../fixtures/swissalti';
import { setMapLoading } from '../layerLoading';
import { RESULTS_OWNER } from '../mapLayers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';
import StatusBar from './StatusBar';
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
    layers: [], mapLoading: [], focusMode: false, downloaded: {}, mosaics: {}, sections: [], dock: null, searching: false, downloading: false,
    error: null, notice: null, aoiWalking: false,
  });
  act(() => root.render(<StatusBar />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

const toasts = () => [...container.querySelectorAll<HTMLElement>('.status-stack .toast.busy')];
const texts = () => toasts().map((toast) => toast.textContent);
const wait = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

describe('the busy toast for tiles that load', () => {
  it('shows nothing while no tile is on its way', () => {
    expect(toasts()).toEqual([]);
  });

  it('says "Loading data" after the moment, with the layer manager closed and no results panel, and goes when the tiles are in', () => {
    expect(useAppStore.getState().dock).toBeNull();
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS - 1);
    expect(toasts()).toEqual([]);
    wait(1);
    expect(texts()).toEqual(['Loading data']);
    expect(toasts()[0].querySelector('.spinner')).not.toBeNull();
    expect(container.querySelector('.map-loading')).toBeNull();
    act(() => setMapLoading([]));
    expect(toasts()).toEqual([]);
  });

  it('is one toast whatever the number of layers that load', () => {
    act(() => setMapLoading(['L1', 'L2', RESULTS_OWNER]));
    wait(LOADING_AFTER_MS);
    expect(texts()).toEqual(['Loading data']);
  });

  it('does not appear for tiles that are there before the moment is over', () => {
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS - 100);
    act(() => setMapLoading([]));
    wait(LOADING_AFTER_MS * 3);
    expect(toasts()).toEqual([]);
  });

  it('does not appear for a flag that flips fast, though the flips add up to more than the moment', () => {
    for (let i = 0; i < 10; i += 1) {
      act(() => setMapLoading(['L1']));
      wait(LOADING_AFTER_MS / 2);
      act(() => setMapLoading([]));
      expect(toasts()).toEqual([]);
    }
  });

  it('comes again for the tiles of a zoom and then of a pan', () => {
    for (const _move of ['first load', 'zoom in', 'pan']) {
      act(() => setMapLoading(['L1']));
      wait(LOADING_AFTER_MS);
      expect(texts()).toEqual(['Loading data']);
      act(() => setMapLoading([]));
      expect(toasts()).toEqual([]);
    }
  });

  it('is shown for the view while the selection of its mosaic is made, though no tile was asked for', () => {
    act(() =>
      useAppStore.setState({
        focusMode: true, showDownloaded: true, downloaded: DOWNLOADED, datasets: LIST, datasetId: 'terrain', items: ITEMS, groups: GROUPS,
        sections: [], openSectionId: null, shownImage: null, mosaics: {},
      }),
    );
    wait(LOADING_AFTER_MS);
    expect(texts()).toEqual(['Loading data']);
    act(() => useAppStore.setState({ focusMode: false }));
    expect(toasts()).toEqual([]);
  });

  it('is one toast with the search text while a search runs, and the tiles text comes back after it', () => {
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS);
    act(() => useAppStore.setState({ searching: true }));
    expect(texts()).toEqual(['Searching STAC catalog…']);
    act(() => useAppStore.setState({ searching: false }));
    expect(texts()).toEqual(['Loading data']);
  });

  it('is one toast with the search text when the search starts first', () => {
    act(() => useAppStore.setState({ searching: true }));
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS);
    expect(texts()).toEqual(['Searching STAC catalog…']);
  });

  it('is one toast with the download text while a download runs', () => {
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS);
    act(() => useAppStore.setState({ downloading: true }));
    expect(texts()).toEqual(['Processing on the server (crop / decomposition)…']);
    act(() => useAppStore.setState({ downloading: false }));
    expect(texts()).toEqual(['Loading data']);
  });

  it('is shown with the layer manager open as well, and the row of the layer has no mark of its own', () => {
    const manager = document.createElement('div');
    document.body.append(manager);
    const open = createRoot(manager);
    useAppStore.setState({ dock: 'layers', sections: [{ datasetId: 'terrain', items: ITEMS, groups: GROUPS, notes: [], groupingError: null, origin: 'search' as const, incomplete: false }] });
    act(() => open.render(<LayerManager />));
    act(() => setMapLoading([RESULTS_OWNER]));
    wait(LOADING_AFTER_MS);
    expect(texts()).toEqual(['Loading data']);
    expect(manager.querySelectorAll('.layer-row [role="status"], .layer-row .spinner')).toHaveLength(0);
    act(() => open.unmount());
    manager.remove();
  });
});
