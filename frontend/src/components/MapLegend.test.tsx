// @vitest-environment jsdom
//
// The legends over the map (M5-62, Otto 24.11.2026): stacked in the order of the layers, a title each that folds the legend away for
// that layer alone, a list of classes in two columns where it is long, a bar in the colours of the colormap the tiles are drawn with.
// No other text. Synthetic layers only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { forgetColormaps } from '../colormaps';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import MapLegend from './MapLegend';

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
});

async function mount(layers: MapLayer[]) {
  useAppStore.setState({ layers, resultsAt: layers.length, focusMode: false });
  await act(async () => root.render(<MapLegend />));
}

const legends = () => [...container.querySelectorAll<HTMLElement>('.legend')];
const titles = () => [...container.querySelectorAll('.legend-title')].map((title) => title.textContent);

describe('the legends over the map', () => {
  it('stand one per layer in the order of the layers, the topmost first, with its name as the title', async () => {
    await mount([
      resultLayer('1', 'Land cover', '&colormap=x', CLASSES),
      resultLayer('2', 'Heights', '&colormap_name=viridis&rescale=0,2900', undefined, 'm'),
      resultLayer('3', 'Colour', '&bidx=3&bidx=2&bidx=1&rescale=0,1&rescale=0,1&rescale=0,1'),
    ]);
    expect(titles()).toEqual(['Land cover', 'Heights']);
    expect(container.querySelector('.map-legend')?.getAttribute('aria-label')).toBe('Legend');
  });

  it('list many classes in two columns: colour, value, name, and nothing else', async () => {
    await mount([resultLayer('1', 'Land cover', '&colormap=x', CLASSES)]);
    const list = container.querySelector('.legend-classes')!;
    expect(list.classList.contains('two-columns')).toBe(true);
    const first = list.querySelector('li')!;
    expect([...first.children].map((cell) => cell.className)).toEqual(['class-swatch', 'legend-value', 'legend-name']);
    expect(first.textContent).toBe('10Class 1');
    expect(legends()[0].textContent).toBe(`Land cover${CLASSES.map((c) => `${c.value}${c.name}`).join('')}`);
  });

  it('keep a short list in one column', async () => {
    await mount([resultLayer('1', 'Few', '&colormap=x', CLASSES.slice(0, 3))]);
    expect(container.querySelector('.legend-classes')!.classList.contains('two-columns')).toBe(false);
  });

  it('draw a bar in the colours of the colormap of the tiles, with its ends and unit', async () => {
    await mount([resultLayer('2', 'Heights', '&colormap_name=viridis_r&rescale=0,2900', undefined, 'm')]);
    const bar = container.querySelector<HTMLElement>('.legend-bar')!;
    expect(bar.style.background).toContain('linear-gradient');
    // Reversed: the last colour of the colormap first.
    expect(bar.style.background.indexOf('253, 231, 37')).toBeLessThan(bar.style.background.indexOf('68, 1, 84'));
    expect([...container.querySelectorAll('.legend-ends span')].map((end) => end.textContent)).toEqual(['0 m', '2900 m']);
  });

  it('change with the tiles of the layer', async () => {
    await mount([resultLayer('2', 'Heights', '&colormap_name=viridis&rescale=0,2900')]);
    act(() => useAppStore.setState({ layers: [resultLayer('2', 'Heights', '&colormap_name=viridis&rescale=100,200')] }));
    expect([...container.querySelectorAll('.legend-ends span')].map((end) => end.textContent)).toEqual(['100', '200']);
  });

  it('fold away by the title, each layer on its own', async () => {
    await mount([resultLayer('1', 'Land cover', '&colormap=x', CLASSES), resultLayer('2', 'Heights', '&colormap_name=viridis&rescale=0,1')]);
    const [first, second] = [...container.querySelectorAll<HTMLButtonElement>('.legend-title')];
    act(() => first.click());
    expect(first.getAttribute('aria-expanded')).toBe('false');
    expect(legends()[0].querySelector('.legend-classes')).toBeNull();
    expect(second.getAttribute('aria-expanded')).toBe('true');
    expect(legends()[1].querySelector('.legend-bar')).not.toBeNull();
    act(() => first.click());
    expect(legends()[0].querySelector('.legend-classes')).not.toBeNull();
  });

  it('are not there for hidden layers, or where no layer has one', async () => {
    await mount([{ ...resultLayer('1', 'Land cover', '&colormap=x', CLASSES), visible: false }, resultLayer('3', 'As it is', '')]);
    expect(container.querySelector('.map-legend')).toBeNull();
  });
});
