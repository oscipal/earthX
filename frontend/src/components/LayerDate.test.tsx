// @vitest-environment jsdom
//
// NM4-65 part 3 (Otto, 31.10.2026: "bei den layern immer das datum der aufnahme dabei stehen haben"; 1.11.2026: in the name, not a
// subtitle, with the buttons under the title): every row of the layer
// manager shows the acquisition date of its layer — scene, preview, result and band layers alike — and none for data without
// a time axis. The jobs keep the day of their scenes for the layer of the result.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import CSS from '../index.css?raw';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  useAppStore.setState({ layers: [], sections: [] });
});

const layer = (id: string, date?: string, over: Partial<MapLayer> = {}): MapLayer => ({
  id,
  name: `Layer ${id}`,
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
  restore: { datasetId: null, itemIds: [] } as never,
  ...(date ? { date } : {}),
  ...over,
});

const names = () => [...container.querySelectorAll('.layer-row .lm-name')].map((n) => n.textContent);

describe('the date in the name of a layer (Otto, 1.11.2026: "das datum gehört in den layer namen, nicht als untertitel")', () => {
  it('stands after the name: one day, a span of days, and nothing for a layer without a time axis', () => {
    useAppStore.setState({ layers: [layer('a', '2026-07-01'), layer('b', '2026-07-01 – 2026-07-06'), layer('c')], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(names()).toEqual(['Layer a · 2026-07-01', 'Layer b · 2026-07-01 – 2026-07-06', 'Layer c']);
  });

  it('is no line of its own: the row has no element for it', () => {
    useAppStore.setState({ layers: [layer('a', '2026-07-01')], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(container.querySelector('.lm-date')).toBeNull();
    expect(container.querySelector('.layer-row')!.children).toHaveLength(10);
  });

  it('is in the name of results and previews too, and the name is its tooltip in full', () => {
    useAppStore.setState({ layers: [layer('p', '2026-07-01', { derived: 'preview' }), layer('r', '2026-07-02', { derived: 'result' })], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(names()).toEqual(['Layer p · 2026-07-01', 'Layer r · 2026-07-02']);
    expect(container.querySelector('.layer-row .lm-name')!.getAttribute('title')).toContain('Layer p · 2026-07-01');
  });

  it('is not added to a name that has it already (a layer named after its group)', () => {
    useAppStore.setState({ layers: [layer('a', '2026-07-01', { name: 'Sentinel-2 L2A · 2026-07-01 · S2A' })], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(names()).toEqual(['Sentinel-2 L2A · 2026-07-01 · S2A']);
  });

  it('is not kept in the layer: the layer keeps the name it was given', () => {
    useAppStore.setState({ layers: [layer('a', '2026-07-01')], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(useAppStore.getState().layers[0].name).toBe('Layer a');
  });

  it('does not show on the entry "Results", which is no layer of scenes', () => {
    useAppStore.setState({
      layers: [layer('a', '2026-07-01')],
      dock: 'layers',
      sections: [{ datasetId: 's2', items: [{ id: 'x', collection: 's2', properties: { datetime: '2026-07-01T00:00:00Z' }, assets: {} }], groups: [] } as never],
    });
    act(() => root.render(<LayerManager />));
    expect(container.querySelector('.results-row .lm-name')!.textContent).toBe('Search results');
  });
});

describe('the buttons of a row stand under its title (Otto, 1.11.2026)', () => {
  const rule = (selector: string) => {
    const start = CSS.indexOf(`\n${selector} {`);
    expect(start, selector).toBeGreaterThanOrEqual(0);
    return CSS.slice(start, CSS.indexOf('}', start));
  };

  it('puts the title on the first line over every column but the grip, and the other places on the second', () => {
    expect(rule(".layer-row > [data-col='name']")).toContain('grid-column: 2 / -1');
    expect(rule(".layer-row > [data-col='name']")).toContain('grid-row: 1');
    for (const col of ['eye', 'opacity', 'up', 'down', 'process', 'download', 'note', 'remove']) expect(rule(`.layer-row > [data-col='${col}']`), col).toContain('grid-row: 2');
    expect(rule(".layer-row > [data-col='grip']")).toContain('grid-row: 1 / span 2');
  });

  it('gives the slider the wide place of the second line, in the order eye, opacity, ▲, ▼, ⚙, ⇩, note, remove', () => {
    const columns = ['eye', 'opacity', 'up', 'down', 'process', 'download', 'note', 'remove'].map((col) => Number(/grid-column: (\d+)/u.exec(rule(`.layer-row > [data-col='${col}']`))![1]));
    expect(columns).toEqual([2, 3, 4, 5, 6, 7, 8, 9]);
    expect(rule('.layer-row')).toContain('grid-template-columns: 14px var(--lm-button) minmax(0, 1fr)');
  });
});
