// @vitest-environment jsdom
//
// The legend of each layer under its row in the layer manager (M5-62, Otto 24.11.2026): shown by default, hidden and shown again with
// its button; where the list would scroll, the legends fold from the bottom up until it does not. jsdom has no layout: the height of the
// list is made up from the legends open in it. Synthetic layers only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MapLayer } from '../layers';
import { useLegendStore } from '../legendStore';
import { NO_CHOICE } from '../mapLegend';
import { useAppStore } from '../store';
import LayerManager, { HIDE_LEGEND_TIP, SHOW_LEGEND_TIP } from './LayerManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const CLASSES = [
  { value: 10, name: 'Tree cover', colour: '#006400' },
  { value: 20, name: 'Shrubland', colour: '#ffbb22' },
];

function resultLayer(id: string, query: string, legend?: typeof CLASSES): MapLayer {
  return {
    id,
    name: `Layer ${id}`,
    visible: true,
    opacity: 1,
    derived: 'result',
    overlays: [{ kind: 'raster', tileUrl: `/results/J${id}/tiles/{z}/{x}/{y}?tilesize=256${query}`, bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }],
    result: { jobID: `J${id}`, expires: '2099-01-01T00:00:00Z', gsd: 10, resampled: false, expired: false, dataType: 'uint8', stats: null, ...(legend ? { classes: true, legend } : {}) },
    restore: { datasetId: null, itemIds: [] } as never,
  };
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  useAppStore.setState({ layers: [], resultsAt: 0 });
  useLegendStore.setState({ choice: NO_CHOICE, folded: false, hidden: {} });
});

function mount(layers: MapLayer[]) {
  useAppStore.setState({ layers, resultsAt: layers.length, datasets: [], dock: 'layers' });
  act(() => root.render(<LayerManager />));
}

const rows = () => [...container.querySelectorAll('.layer-row')];
const legendOf = (row: Element) => row.querySelector('[data-col="legend"]');
const toggleOf = (row: Element) => row.querySelector<HTMLButtonElement>('button[data-col="legend-toggle"]');

describe('the legends in the layer manager', () => {
  it('stand under the row of each layer that has one, shown, with a button to hide them', () => {
    mount([resultLayer('a', '&colormap=x', CLASSES), resultLayer('b', '&colormap_name=viridis&rescale=0,1'), resultLayer('c', '')]);
    const [a, b, c] = rows();
    expect(legendOf(a)!.querySelectorAll('li')).toHaveLength(2);
    expect(legendOf(a)!.querySelector('.two-columns')).toBeNull();
    expect(legendOf(b)!.querySelector('.legend-bar')).not.toBeNull();
    expect(legendOf(c)).toBeNull();
    expect(toggleOf(c)).toBeNull();
    expect(c.querySelector('[data-col="legend-toggle"]')!.className).toBe('lm-slot');
    expect([toggleOf(a)!.getAttribute('aria-expanded'), toggleOf(a)!.getAttribute('data-tip')]).toEqual(['true', HIDE_LEGEND_TIP]);
  });

  it('hide and show with their button, each layer on its own', () => {
    mount([resultLayer('a', '&colormap=x', CLASSES), resultLayer('b', '&colormap=x', CLASSES)]);
    act(() => toggleOf(rows()[0])!.click());
    expect(legendOf(rows()[0])).toBeNull();
    expect([toggleOf(rows()[0])!.getAttribute('aria-expanded'), toggleOf(rows()[0])!.getAttribute('data-tip')]).toEqual(['false', SHOW_LEGEND_TIP]);
    expect(legendOf(rows()[1])).not.toBeNull();
    act(() => toggleOf(rows()[0])!.click());
    expect(legendOf(rows()[0])).not.toBeNull();
  });

  it('fold from the bottom up where the list would scroll, and the one opened by its button folds last', () => {
    // 100 px of rows and 200 px for each legend open, in a list 450 px high: one legend fits.
    vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('layer-list') ? 100 + 200 * this.querySelectorAll('[data-col="legend"]').length : 0;
    });
    vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockImplementation(function (this: HTMLElement) {
      return this.classList.contains('layer-list') ? 450 : 0;
    });
    mount([resultLayer('a', '&colormap=x', CLASSES), resultLayer('b', '&colormap=x', CLASSES), resultLayer('c', '&colormap=x', CLASSES)]);
    expect(rows().map((row) => legendOf(row) !== null)).toEqual([true, false, false]);
    act(() => toggleOf(rows()[2])!.click());
    expect(rows().map((row) => legendOf(row) !== null)).toEqual([false, false, true]);
  });
});
