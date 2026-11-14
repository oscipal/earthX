// @vitest-environment jsdom
//
// Plan M5-30b part 9, Otto 11.11.2026 (`adr/0032` §14 F12): the overview of a dataset with a pyramid has no mark at all, only a
// tooltip at its layer. The "Overview" badge of a job's result (`PreviewBadge`) is another thing and stays as it is.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from '../datasets';
import type { MapLayer } from '../layers';
import { overviewNoteOf } from '../overviewSubstitute';
import { useAppStore } from '../store';
import type { Collection } from '../types';
import LayerManager, { RESULTS_ENTRY_TIP } from './LayerManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const COLLECTION = (overview: 'pyramid' | 'scenes', minZoom: number): Collection =>
  ({
    id: 'relief',
    title: 'Relief',
    'earthx:capabilities': { roi: true, time_range: false },
    'earthx:viewer': {
      group_by: ['datetime'], min_zoom: minZoom, max_zoom: 15, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['datetime'],
      overview, overview_resampling: overview === 'pyramid' ? 'average' : null, overview_substitute: null,
    },
  }) as unknown as Collection;

const layerOf = (note?: string): MapLayer => ({
  id: 'a',
  name: 'Layer a',
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: 'https://t/a/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 15 }],
  restore: { datasetId: 'relief', itemIds: [] } as never,
  ...(note ? { note } : {}),
});

const nameOf = () => container.querySelector<HTMLElement>('.layer-row .lm-name')!;
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

describe('the layer manager with a layer of a dataset with a pyramid', () => {
  const NOTE = overviewNoteOf(datasetsFrom([COLLECTION('pyramid', 7)])[0])!;

  beforeEach(() => {
    useAppStore.setState({ datasets: datasetsFrom([COLLECTION('pyramid', 7)]), datasetId: 'relief', sections: [], layers: [layerOf(NOTE)], mapZoom: 3, dock: 'layers', resultsOnMap: false });
    act(() => root.render(<LayerManager />));
  });

  it('says what the overview is in the tooltip of the name of the layer', () => {
    expect(nameOf().getAttribute('data-tip')).toBe(NOTE);
    expect(NOTE).toContain('overview');
  });

  it('shows no mark: no badge, no pill, and no word of it in the row, whatever the tooltip says', () => {
    const row = container.querySelector('.layer-row')!;
    expect(row.querySelector('.badge, [class*="badge"]')).toBeNull();
    expect(row.textContent).not.toMatch(/overview/iu);
    expect(container.querySelector('.badge, [class*="badge"]')).toBeNull();
    expect(container.textContent).not.toMatch(/overview/iu);
  });
});

describe('the entry "Search results" of a dataset with a pyramid', () => {
  const results = (collection: Collection, resultsOnMap: boolean) => {
    const item = { id: 'S', collection: 'relief', bbox: [0, 0, 1, 1], properties: { datetime: '2026-10-18T00:00:00Z' }, assets: {} };
    const groups = [{ key: ['2026-10-18'], label: '18 Oct', items: [item] }];
    act(() =>
      useAppStore.setState({
        datasets: datasetsFrom([collection]), datasetId: 'relief', sections: [{ datasetId: 'relief', items: [item], groups }] as never,
        layers: [], mapZoom: 3, resultsOnMap, focusMode: false, dock: 'layers',
      }),
    );
    act(() => root.render(<LayerManager />));
  };

  it('says the same in its tooltip, before what the entry is, while the results are on the map', () => {
    results(COLLECTION('pyramid', 7), true);
    expect(resultsName().getAttribute('data-tip')).toBe(`${overviewNoteOf(datasetsFrom([COLLECTION('pyramid', 7)])[0])} ${RESULTS_ENTRY_TIP}`);
    expect(container.textContent).not.toMatch(/overview/iu);
  });

  it('says only what the entry is for a dataset without a pyramid, or with the results off the map', () => {
    results(COLLECTION('scenes', 0), true);
    expect(resultsName().getAttribute('data-tip')).toBe(RESULTS_ENTRY_TIP);
    results(COLLECTION('pyramid', 7), false);
    expect(resultsName().getAttribute('data-tip')).toBe(RESULTS_ENTRY_TIP);
  });
});
