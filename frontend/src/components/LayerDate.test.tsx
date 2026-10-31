// @vitest-environment jsdom
//
// NM4-65 part 3 (Otto, 31.10.2026: "bei den layern immer das datum der aufnahme dabei stehen haben"): every row of the layer
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

const dates = () => [...container.querySelectorAll('.layer-row')].map((row) => row.querySelector('.lm-date')?.textContent ?? null);

describe('the date in the rows of the layer manager', () => {
  it('shows one day, a span of days, and nothing for a layer without a time axis', () => {
    useAppStore.setState({ layers: [layer('a', '2026-07-01'), layer('b', '2026-07-01 – 2026-07-06'), layer('c')], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(dates()).toEqual(['2026-07-01', '2026-07-01 – 2026-07-06', null]);
  });

  it('shows it for results and previews too, and names it in the tooltip', () => {
    useAppStore.setState({ layers: [layer('p', '2026-07-01', { derived: 'preview' }), layer('r', '2026-07-02', { derived: 'result' })], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(dates()).toEqual(['2026-07-01', '2026-07-02']);
    expect(container.querySelector('.lm-date')?.getAttribute('title')).toBe('Acquisition date (UTC)');
  });

  it('does not show it on the entry "Results", which is no layer of scenes', () => {
    useAppStore.setState({
      layers: [layer('a', '2026-07-01')],
      dock: 'layers',
      sections: [{ datasetId: 's2', items: [{ id: 'x', collection: 's2', properties: { datetime: '2026-07-01T00:00:00Z' }, assets: {} }], groups: [] } as never],
    });
    act(() => root.render(<LayerManager />));
    const results = container.querySelector('.results-row');
    expect(results).not.toBeNull();
    expect(results!.querySelector('.lm-date')).toBeNull();
  });

  it('is a small muted line under the name, from the name to the end of the row, and never wider than the row', () => {
    const start = CSS.indexOf('\n.lm-date {');
    const rule = CSS.slice(start, CSS.indexOf('}', start));
    expect(start).toBeGreaterThanOrEqual(0);
    expect(rule).toContain('grid-column: 3 / -1');
    expect(rule).toContain('color: var(--muted)');
    expect(rule).toContain('text-overflow: ellipsis');
  });
});
