// @vitest-environment jsdom
//
// Plan M5-30 §8.7, Otto 13.11.2026: one mark on the map (a symbol, no text) whenever any visible layer has loaded for longer than a moment, at
// the first load and after a zoom or a pan, whether the layer manager is open or not.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DOWNLOADED, GROUPS, ITEMS, LIST } from '../fixtures/swissalti';
import { setMapLoading } from '../layerLoading';
import { RESULTS_OWNER } from '../mapLayers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';
import MapLoadingMark from './MapLoadingMark';
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
  useAppStore.setState({ layers: [], mapLoading: [], focusMode: false, downloaded: {}, mosaics: {}, sections: [], dock: null });
  act(() => root.render(<MapLoadingMark />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
});

const marks = () => [...container.querySelectorAll<HTMLElement>('.map-loading')];
const wait = (ms: number) => act(() => void vi.advanceTimersByTime(ms));

describe('the loading mark on the map', () => {
  it('shows nothing while no tile is on its way', () => {
    expect(marks()).toEqual([]);
  });

  it('appears after the moment, with the layer manager closed, as a spinner without text', () => {
    expect(useAppStore.getState().dock).toBeNull();
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS - 1);
    expect(marks()).toEqual([]);
    wait(1);
    expect(marks()).toHaveLength(1);
    const [mark] = marks();
    expect(mark.textContent).toBe('');
    expect(mark.getAttribute('role')).toBe('status');
    expect(mark.getAttribute('aria-label')).toBe(LOADING_MARK_TIP);
    expect(mark.querySelector('.spinner')).not.toBeNull();
  });

  it('is one mark whatever the number of layers that load', () => {
    act(() => setMapLoading(['L1', 'L2', RESULTS_OWNER]));
    wait(LOADING_AFTER_MS);
    expect(marks()).toHaveLength(1);
  });

  it('does not appear for tiles that are there before the moment is over', () => {
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS - 100);
    act(() => setMapLoading([]));
    wait(LOADING_AFTER_MS * 3);
    expect(marks()).toEqual([]);
  });

  it('goes when the tiles are in or failed, and comes again for the tiles of a zoom and then of a pan', () => {
    for (const _move of ['first load', 'zoom in', 'pan']) {
      act(() => setMapLoading(['L1']));
      wait(LOADING_AFTER_MS - 1);
      expect(marks()).toEqual([]);
      wait(1);
      expect(marks()).toHaveLength(1);
      act(() => setMapLoading([]));
      expect(marks()).toEqual([]);
    }
  });

  it('stays through a pan that asks for tiles of another layer before the first ones are in', () => {
    act(() => setMapLoading(['L1']));
    wait(LOADING_AFTER_MS);
    act(() => setMapLoading(['L1', 'L2']));
    expect(marks()).toHaveLength(1);
    act(() => setMapLoading(['L2']));
    expect(marks()).toHaveLength(1);
  });

  it('is shown for the view while the selection of its mosaic is made, though no tile was asked for, and with no row in the manager', () => {
    act(() =>
      useAppStore.setState({
        focusMode: true, showDownloaded: true, downloaded: DOWNLOADED, datasets: LIST, datasetId: 'terrain', items: ITEMS, groups: GROUPS,
        sections: [], openSectionId: null, shownImage: null, mosaics: {},
      }),
    );
    wait(LOADING_AFTER_MS);
    expect(marks()).toHaveLength(1);
    act(() => useAppStore.setState({ focusMode: false }));
    expect(marks()).toEqual([]);
  });

  it('is shown with the layer manager open as well, besides the mark in its row, and the manager does not need to be there', () => {
    const manager = document.createElement('div');
    document.body.append(manager);
    const open = createRoot(manager);
    useAppStore.setState({ dock: 'layers', sections: [{ datasetId: 'terrain', items: ITEMS, groups: GROUPS, notes: [], groupingError: null, origin: 'search' as const, incomplete: false }] });
    act(() => open.render(<LayerManager />));
    act(() => setMapLoading([RESULTS_OWNER]));
    wait(LOADING_AFTER_MS);
    expect(marks()).toHaveLength(1);
    expect(manager.querySelectorAll('.layer-row [role="status"]')).toHaveLength(1);
    act(() => open.unmount());
    manager.remove();
    expect(marks()).toHaveLength(1);
  });
});
