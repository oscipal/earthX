// @vitest-environment jsdom
//
// "Copy original scene name" in the view and in the settings of a pinned layer (Otto, 3.11.2026, zu #282): the small line under the title copies
// the item ids of the scenes of the image shown, one to a line; "n scenes" is its tooltip for several.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import CSS from '../index.css?raw';
import { useAppStore, type AppState } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import ViewerControls from './ViewerControls';
import { tipOf } from '../fixtures/tips';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = {
  id: 'optical',
  title: 'Optical',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid' as const, overview_resampling: 'average' as const, overview_substitute: null },
} as unknown as Collection;

const item = (id: string, day: string): StacItem => ({ id, collection: 'optical', bbox: [10, 47, 11, 48], properties: { datetime: `${day}T10:00:00Z` }, assets: {} });
const info = (id: string): DownloadedInfo => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/{z}/{x}/{y}?asset=visual`, bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 8, maxZoom: 14 });

let container: HTMLDivElement;
let root: Root;
let write: ReturnType<typeof vi.fn>;

function mount(ids: string[], over: Partial<AppState> = {}) {
  const items = [...ids.map((id) => item(id, '2026-07-24')), item('other', '2026-07-25')];
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', sections: [], openSectionId: null, items,
      groups: [{ key: ['2026-07-24'], label: '2026-07-24', items: items.slice(0, ids.length) }, { key: ['2026-07-25'], label: '2026-07-25', items: items.slice(ids.length) }],
      focusMode: true, cropToAoi: false, viewAoi: null, downloaded: Object.fromEntries(ids.map((id) => [id, info(id)])), showDownloaded: true, shownImage: null,
      selectedIds: [], pendingBand: '', pendingIndex: '', pendingColormapName: '', pendingVmin: '0', pendingVmax: '255', layers: [], dock: null, resultsOnMap: true, ...over,
    });
    root.render(<ViewerControls />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  write = vi.fn(async () => undefined);
  vi.stubGlobal('navigator', { clipboard: { writeText: write } });
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const line = () => container.querySelector<HTMLButtonElement>('.vc-head .vc-scene-names');
const press = async () => {
  await act(async () => {
    line()!.click();
  });
};

describe('the view', () => {
  it('has the line in the row of the date, and copies the name of its one scene', async () => {
    mount(['S2A_1']);
    expect(line()!.textContent).toBe('Copy original scene name');
    expect(tipOf(line()!)).toBe('Copy the name of the original scene');
    // In the row of the date, left of it: the date keeps the right end (Otto, 3.11.2026). The order is the style's.
    const row = line()!.parentElement!;
    expect(row.classList.contains('insp-row2')).toBe(true);
    expect(row.querySelector('.vc-stepper')).not.toBeNull();
    const rule = (selector: string) => CSS.slice(CSS.indexOf(`\n${selector} {`), CSS.indexOf('}', CSS.indexOf(`\n${selector} {`)));
    expect(rule('.inspector .vc-scene-names')).toContain('order: -1');
    expect(rule('.inspector .vc-scene-names')).not.toMatch(/margin:[^;]*auto/u);
    expect(rule('.inspector .vc-stepper')).toContain('margin-left: auto');
    // And the dataset, where there is one, stays first of the three.
    expect(rule('.inspector .insp-row2 .vc-dataset')).toContain('order: -2');
    await press();
    expect(write).toHaveBeenCalledWith('S2A_1');
    expect(line()!.textContent).toBe('Copied');
  });

  it('copies every scene of a merged image, one to a line, with "n scenes" as the tooltip', async () => {
    mount(['S2A_1', 'S2A_2', 'S2A_3']);
    expect(tipOf(line()!)).toBe('3 scenes');
    await press();
    expect(write).toHaveBeenCalledWith('S2A_1\nS2A_2\nS2A_3');
  });

  it('copies the scenes of the image that is shown, not of the others', async () => {
    mount(['S2A_1', 'S2B_1'], { groups: [
      { key: ['d1'], label: 'd1', items: [item('S2A_1', '2026-07-24')] },
      { key: ['d2'], label: 'd2', items: [item('S2B_1', '2026-07-25')] },
    ] as never, items: [item('S2A_1', '2026-07-24'), item('S2B_1', '2026-07-25')] });
    await press();
    expect(write).toHaveBeenCalledTimes(1);
    expect(String(write.mock.calls[0][0]).split('\n')).toHaveLength(1);
  });

  it('is not there with no scene in the view', () => {
    mount([]);
    expect(line()).toBeNull();
  });
});
