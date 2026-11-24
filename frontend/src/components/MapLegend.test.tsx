// @vitest-environment jsdom
//
// The legend over the map (M5-62, Otto 24.11.2026): one box titled "Legend", always there; a dropdown in its head lists the visible
// layers with a legend in the order of the layer manager and shows the topmost; a choice holds until the layers change. The title
// folds it. No other text. Synthetic layers only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { forgetColormaps } from '../colormaps';
import type { MapLayer } from '../layers';
import { useLegendStore } from '../legendStore';
import { NO_CHOICE } from '../mapLegend';
import { useAppStore } from '../store';
import MapLegend, { LEGEND, ONE_LEGEND_TIP } from './MapLegend';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const CLASSES = Array.from({ length: 11 }, (_, i) => ({ value: (i + 1) * 10, name: `Class ${i + 1}`, colour: `#0000${(i * 20).toString(16).padStart(2, '0')}` }));
const COLORMAPS = { groups: [{ name: 'sequential', colormaps: [{ name: 'viridis', reversed: 'viridis_r', colors: ['#440154', '#21918c', '#fde725'] }] }] };

function resultLayer(id: string, name: string, query: string, legend?: typeof CLASSES, unit?: string): MapLayer {
  return {
    id,
    name,
    visible: true,
    opacity: 1,
    derived: 'result',
    overlays: [{ kind: 'raster', tileUrl: `/results/J${id}/tiles/{z}/{x}/{y}?tilesize=256${query}`, bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }],
    result: { jobID: `J${id}`, expires: '2099-01-01T00:00:00Z', gsd: 10, resampled: false, expired: false, dataType: 'uint8', stats: null, ...(legend ? { classes: true, legend } : {}), ...(unit ? { unit } : {}) },
    restore: { datasetId: null, itemIds: [] } as never,
  };
}

const LAND = resultLayer('1', 'Land cover', '&colormap=x', CLASSES);
const HEIGHTS = resultLayer('2', 'Heights', '&colormap_name=viridis_r&rescale=0,2900', undefined, 'm');
const COLOUR = resultLayer('3', 'Colour', '&bidx=3&bidx=2&bidx=1&rescale=0,1&rescale=0,1&rescale=0,1');

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  forgetColormaps();
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(COLORMAPS), { status: 200 })));
  container = document.createElement('div');
  container.className = 'app';
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  useAppStore.setState({ layers: [], resultsAt: 0 });
  useLegendStore.setState({ choice: NO_CHOICE, folded: false, hidden: {} });
});

async function mount(layers: MapLayer[]) {
  useAppStore.setState({ layers, resultsAt: layers.length, focusMode: false });
  await act(async () => root.render(<MapLegend />));
}

const box = () => container.querySelector<HTMLElement>('.map-legend .legend')!;
const choice = () => container.querySelector<HTMLSelectElement>('.legend-choice');
const options = () => [...(choice()?.options ?? [])].map((option) => option.textContent);
const set = (layers: MapLayer[]) => act(() => useAppStore.setState({ layers }));
const pick = (value: string) =>
  act(() => {
    choice()!.value = value;
    choice()!.dispatchEvent(new Event('change', { bubbles: true }));
  });

describe('the legend over the map', () => {
  it('is one box titled "Legend" that offers the visible layers with a legend, the topmost first, and shows the topmost', async () => {
    await mount([LAND, HEIGHTS, COLOUR]);
    expect(container.querySelectorAll('.map-legend .legend')).toHaveLength(1);
    expect(box().getAttribute('aria-label')).toBe(LEGEND);
    expect(container.querySelector('.legend-title')!.textContent).toBe(LEGEND);
    expect(options()).toEqual(['Land cover', 'Heights']);
    expect(choice()!.value).toBe('1');
    expect(box().querySelector('.legend-classes')).not.toBeNull();
  });

  it('shows the layer chosen in the dropdown: a bar with the colours of its colormap, its ends and unit', async () => {
    await mount([LAND, HEIGHTS]);
    pick('2');
    await act(async () => {});
    const bar = box().querySelector<HTMLElement>('.legend-bar')!;
    // Reversed: the last colour of the colormap first.
    expect(bar.style.background.indexOf('253, 231, 37')).toBeLessThan(bar.style.background.indexOf('68, 1, 84'));
    expect([...box().querySelectorAll('.legend-ends span')].map((end) => end.textContent)).toEqual(['0 m', '2900 m']);
  });

  it('keeps a choice while the look of a layer changes, and goes back to the topmost when the layers change', async () => {
    await mount([LAND, HEIGHTS]);
    pick('2');
    set([LAND, resultLayer('2', 'Heights', '&colormap_name=viridis&rescale=100,200', undefined, 'm')]);
    expect(choice()!.value).toBe('2');
    expect([...box().querySelectorAll('.legend-ends span')].map((end) => end.textContent)).toEqual(['100 m', '200 m']);
    // Moved: Heights is the topmost now, and shown as such.
    set([HEIGHTS, LAND]);
    expect(choice()!.value).toBe('2');
    pick('1');
    // Hidden: the topmost visible one.
    set([{ ...HEIGHTS, visible: false }, LAND]);
    expect(options()).toEqual(['Land cover']);
    expect(choice()!.value).toBe('1');
    // Shown again: the topmost again, though Land cover was chosen.
    set([HEIGHTS, LAND]);
    expect(choice()!.value).toBe('2');
    // A new layer on top: it.
    set([resultLayer('4', 'New result', '&colormap=x', CLASSES.slice(0, 3)), HEIGHTS, LAND]);
    expect(choice()!.value).toBe('4');
  });

  it('locks the dropdown with its reason where only one layer has a legend', async () => {
    await mount([HEIGHTS]);
    expect(choice()!.getAttribute('aria-disabled')).toBe('true');
    expect(choice()!.getAttribute('data-tip')).toBe(ONE_LEGEND_TIP);
  });

  it('lists many classes in two columns: colour, value, name, and nothing else', async () => {
    await mount([LAND]);
    const list = box().querySelector('.legend-classes')!;
    expect(list.classList.contains('two-columns')).toBe(true);
    expect([...list.querySelector('li')!.children].map((cell) => cell.className)).toEqual(['class-swatch', 'legend-value', 'legend-name']);
    expect(list.textContent).toBe(CLASSES.map((c) => `${c.value}${c.name}`).join(''));
  });

  it('folds by its title', async () => {
    await mount([LAND]);
    const title = container.querySelector<HTMLButtonElement>('.legend-title')!;
    act(() => title.click());
    expect(title.getAttribute('aria-expanded')).toBe('false');
    expect(box().querySelector('.legend-classes')).toBeNull();
    act(() => title.click());
    expect(box().querySelector('.legend-classes')).not.toBeNull();
  });

  it('stays without a layer with a legend, with its title and nothing else', async () => {
    await mount([{ ...LAND, visible: false }, COLOUR]);
    expect(box().textContent).toBe(LEGEND);
    expect(choice()).toBeNull();
  });
});
