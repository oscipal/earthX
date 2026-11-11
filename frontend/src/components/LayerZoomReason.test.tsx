// @vitest-environment jsdom
//
// A layer below the zoom its tiles start at shows nothing; the tooltip of its row says why (Otto, 10.11.2026), in either step
// of the tooltips, and nothing over the map says it. The same for the row "Search results" of a dataset drawn from a zoom
// above the map's (`browse: preview_tiles`). Generic: any layer, any dataset. Synthetic layers and collections only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from '../datasets';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import type { Collection } from '../types';
import LayerManager, { RESULTS_ENTRY_TIP } from './LayerManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const layer = (id: string, minZoom: number, extra: Partial<MapLayer> = {}): MapLayer => ({
  id,
  name: `Layer ${id}`,
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: `https://t/${id}/{z}/{x}/{y}`, bounds: [0, 0, 1, 1], minZoom, maxZoom: 14 }],
  restore: { datasetId: null, itemIds: [] } as never,
  ...extra,
});

const PREVIEW_TILES = {
  id: 'radar',
  title: 'Radar',
  'earthx:capabilities': { roi: true, time_range: true },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 7, max_zoom: 14, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid' as const, overview_resampling: 'average' as const },
} as unknown as Collection;

const nameOf = (id: string) =>
  [...container.querySelectorAll<HTMLElement>('.layer-row')].find((row) => row.textContent?.includes(`Layer ${id}`))!.querySelector<HTMLElement>('.lm-name')!;
const resultsName = () => container.querySelector<HTMLElement>('.results-name')!;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('the row of a layer below the zoom it starts at', () => {
  beforeEach(() => {
    useAppStore.setState({ datasets: [], sections: [], layers: [layer('high', 10), layer('low', 0), layer('off', 10, { visible: false })], mapZoom: 3, dock: 'layers' });
    act(() => root.render(<LayerManager />));
  });

  it('says from which zoom the layer is drawn, in either step of the tooltips', () => {
    expect(nameOf('high').getAttribute('data-tip')).toBe('Nothing shown at this zoom: this layer is drawn from zoom 9.');
    expect(nameOf('high').hasAttribute('data-tip-level')).toBe(false);
  });

  it('says nothing for a layer drawn at this zoom, or switched off', () => {
    expect(nameOf('low').hasAttribute('data-tip')).toBe(false);
    expect(nameOf('off').hasAttribute('data-tip')).toBe(false);
  });

  it('keeps the note of the layer after the reason, and drops the reason once the map is zoomed in', () => {
    act(() => useAppStore.setState({ layers: [layer('high', 10, { note: 'A note.' })] }));
    expect(nameOf('high').getAttribute('data-tip')).toBe('Nothing shown at this zoom: this layer is drawn from zoom 9. A note.');
    act(() => useAppStore.setState({ mapZoom: 9 }));
    expect(nameOf('high').getAttribute('data-tip')).toBe('A note.');
    expect(nameOf('high').getAttribute('data-tip-level')).toBe('advanced');
  });
});

describe('the row "Search results" of a dataset drawn from a zoom above the map', () => {
  const results = (zoom: number, extra: Record<string, unknown> = {}) => {
    const item = { id: 'S', collection: 'radar', bbox: [0, 0, 1, 1], properties: { datetime: '2026-10-18T00:00:00Z' }, assets: {} };
    const groups = [{ key: ['2026-10-18'], label: '18 Oct', items: [item] }];
    act(() =>
      useAppStore.setState({
        datasets: datasetsFrom([PREVIEW_TILES]), datasetId: 'radar', sections: [{ datasetId: 'radar', items: [item], groups }] as never,
        layers: [], mapZoom: zoom, resultsOnMap: true, focusMode: false, dock: 'layers', ...extra,
      }),
    );
    act(() => root.render(<LayerManager />));
  };

  it('says why the results show nothing, before what the row is', () => {
    results(5);
    expect(resultsName().getAttribute('data-tip')).toBe(
      `Nothing shown at this zoom: Radar is drawn from zoom 7. Below it one tile covers several scenes; the coverage shows where they are. ${RESULTS_ENTRY_TIP}`,
    );
    expect(resultsName().hasAttribute('data-tip-level')).toBe(false);
  });

  it.each([
    ['at the zoom it starts at', 7, {}],
    ['while the results are hidden', 5, { resultsOnMap: false }],
    ['in a view', 5, { focusMode: true }],
  ])('says only what the row is %s', (_case, zoom, extra) => {
    results(zoom, extra);
    expect(resultsName().getAttribute('data-tip')).toBe(RESULTS_ENTRY_TIP);
  });

  it('has no row to say it on without results', () => {
    results(5, { sections: [] });
    expect(container.querySelector('.results-name')?.getAttribute('data-tip') ?? RESULTS_ENTRY_TIP).toBe(RESULTS_ENTRY_TIP);
  });
});
