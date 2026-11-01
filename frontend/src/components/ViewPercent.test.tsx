// @vitest-environment jsdom
//
// NM4-65 part 4 (Otto, 31.10.2026), the view of scenes: next to vmin and vmax a switch "value / %". With "%" the fields hold
// percentiles (2 and 98, say); "Apply" asks the tiler for exactly those on the first scene of the image shown, the values go
// into the fields and the look, what is drawn is always the values, and the look keeps what was typed. "Save" (Apply to all)
// takes the values of percentiles that are not applied yet first.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { NO_RANGE_AT_PERCENT, PERCENT_PROBLEMS, UNIT_TIP } from '../percentRange';
import { pendingFieldsOf } from '../render';
import { useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem } from '../types';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = {
  id: 'optical',
  title: 'Optical',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'Colour', assets: ['band'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
} as unknown as Collection;
const info = (id: string): DownloadedInfo => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=band`, bounds: [0, 0, 1, 1], asset: 'band', minZoom: 8, maxZoom: 14 });
const item = (id: string, day: string): StacItem => ({ id, collection: 'optical', bbox: [0, 0, 1, 1], properties: { datetime: `${day}T10:00:00Z` }, assets: {} });

let container: HTMLDivElement;
let root: Root;
let answer: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;

const stats = (band: Record<string, number>) => ({ '1': { count: 100, ...band } });
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function mount() {
  const items = [item('s0', '2026-07-01'), item('s1', '2026-07-06')];
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]),
      datasetId: 'optical',
      items,
      groups: [{ key: ['a'], label: 'a', items: [items[0]] }, { key: ['b'], label: 'b', items: [items[1]] }],
      selectedIds: [],
      downloaded: { s0: info('s0'), s1: info('s1') },
      focusMode: true,
      cropToAoi: true,
      showDownloaded: true,
      shownImage: null,
      viewLooks: {},
      savedLooks: {},
      appliedRender: { rescale: '0,3000' },
      pendingColormapName: '',
      pendingVmin: '0',
      pendingVmax: '3000',
      pendingIndex: '',
      pendingUnit: 'value',
      pendingPercentLow: '2',
      pendingPercentHigh: '98',
      mosaics: {},
      layers: [],
      focusLoading: false,
      pinLoading: false,
      notice: null,
      dock: null,
    });
    root.render(<ViewerControls />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  answer = () => json(stats({ min: 1, max: 9000, percentile_3: 30, percentile_97: 2800, percentile_2: 20, percentile_98: 2900 }));
  fetchMock = vi.fn(async () => answer());
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  mount();
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const state = () => useAppStore.getState();
const chip = () => container.querySelector<HTMLSelectElement>('.vc-unit')!;
const toggleUnit = () => {
  const select = chip();
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(select, select.value === 'value' ? 'percent' : 'value');
    select.dispatchEvent(new Event('change', { bubbles: true }));
  });
};
const unitText = () => chip().selectedOptions[0].textContent;
const inputs = () => [...container.querySelectorAll<HTMLInputElement>('.vc-num input')];
const button = (label: string) => [...container.querySelectorAll<HTMLButtonElement>('.vc-buttons button')].find((b) => b.textContent?.trim() === label)!;
const click = (el: Element) => act(() => el.dispatchEvent(new MouseEvent('click', { bubbles: true })));
const type = (input: HTMLInputElement, value: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
const settle = async () => act(async () => {
  for (let i = 0; i < 6; i++) await Promise.resolve();
});
const asked = () => fetchMock.mock.calls.map(([url]) => String(url));

describe('the switch "value / %"', () => {
  it('is a small dropdown in the label line of the field vmax with words, "absolute value" to begin with, and names the field', () => {
    expect(unitText()).toBe('absolute');
    expect([...chip().options].map((o) => o.textContent)).toEqual(['absolute', 'percentile']);
    expect(chip().title).toBe(UNIT_TIP);
    expect(chip().getAttribute('aria-label')).toBe('Range unit');
    expect(chip().closest('label')!.querySelector('span')!.textContent).toBe('vmax');
    // After the field in the markup, so that the label names the field; the style puts it in the line of the label.
    const vmax = container.querySelectorAll('.vc-num input')[1];
    expect(chip().previousElementSibling).toBe(vmax);
    expect(vmax.getAttribute('aria-labelledby')).toBe(chip().closest('label')!.querySelector('span')!.id);
    expect(container.querySelectorAll('.vc-unit')).toHaveLength(1);
    // The field vmin has nothing but its word and its box.
    expect(container.querySelector('.vc-num')!.children).toHaveLength(2);
  });

  it('turns the fields into percentiles, 2 and 98 to begin with, whole numbers from 0 to 100', () => {
    toggleUnit();
    expect(unitText()).toBe('percentile');
    expect(inputs().map((i) => i.value)).toEqual(['2', '98']);
    for (const input of inputs()) expect([input.min, input.max, input.step]).toEqual(['0', '100', '1']);
  });

  it('gives the values back when it is switched back', () => {
    toggleUnit();
    type(inputs()[0], '5');
    toggleUnit();
    expect(inputs().map((i) => i.value)).toEqual(['0', '3000']);
    expect(inputs()[0].min).toBe('');
    toggleUnit();
    expect(inputs().map((i) => i.value)).toEqual(['5', '98']);
  });

  it('puts "auto-scale" back to 2 and 98 in percentiles, with nothing measured', () => {
    toggleUnit();
    type(inputs()[0], '10');
    type(inputs()[1], '90');
    click(button('auto-scale'));
    expect(inputs().map((i) => i.value)).toEqual(['2', '98']);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('"Apply" with percentiles', () => {
  const typed = (low: string, high: string) => {
    toggleUnit();
    type(inputs()[0], low);
    type(inputs()[1], high);
  };

  it('asks the tiler for exactly those percentiles, and draws the values it gives', async () => {
    typed('3', '97');
    expect(button('Apply').getAttribute('aria-disabled')).toBeNull();
    click(button('Apply'));
    await settle();
    expect(asked()).toHaveLength(1);
    expect(asked()[0]).toContain('/collections/optical/items/s0/statistics?asset=band');
    expect(asked()[0]).toContain('p=3&p=97');
    expect(state().appliedRender).toMatchObject({ rescale: '30,2800', percent: { low: '3', high: '97' } });
    expect(state().pendingVmin).toBe('30');
    expect(state().pendingVmax).toBe('2800');
    expect(button('Apply').getAttribute('aria-disabled')).toBe('true');
    expect(state().notice).toBeNull();
  });

  it('takes the minimum and the maximum for 0 and 100, and asks for no percentile of them', async () => {
    typed('0', '100');
    click(button('Apply'));
    await settle();
    expect(asked()[0]).not.toContain('p=');
    expect(state().appliedRender).toMatchObject({ rescale: '1,9000', percent: { low: '0', high: '100' } });
  });

  it('shows "%" again for a look that was typed in percentiles, and "value" for any other', () => {
    expect(pendingFieldsOf({ rescale: '30,2800', percent: { low: '3', high: '97' } })).toMatchObject({ pendingUnit: 'percent', pendingPercentLow: '3', pendingPercentHigh: '97', pendingVmin: '30' });
    expect(pendingFieldsOf({ rescale: '30,2800' })).toMatchObject({ pendingUnit: 'value', pendingPercentLow: '2', pendingPercentHigh: '98' });
  });

  it('is open again with the same percentiles typed in values, and not for the same ones again', async () => {
    typed('3', '97');
    click(button('Apply'));
    await settle();
    expect(button('Apply').getAttribute('aria-disabled')).toBe('true');
    type(inputs()[1], '96');
    expect(button('Apply').getAttribute('aria-disabled')).toBeNull();
    type(inputs()[1], '97');
    expect(button('Apply').getAttribute('aria-disabled')).toBe('true');
    // Back to values: the same numbers, but no percentiles any more: that is something to apply.
    toggleUnit();
    expect(button('Apply').getAttribute('aria-disabled')).toBeNull();
    click(button('Apply'));
    expect(state().appliedRender.percent).toBeUndefined();
    expect(state().appliedRender.rescale).toBe('30,2800');
  });

  it('is open for a change of the colormap alone, once the percentiles are applied (Otto, 01.11.2026)', async () => {
    typed('3', '97');
    click(button('Apply'));
    await settle();
    expect(button('Apply').getAttribute('aria-disabled')).toBe('true');
    act(() => state().setPendingColormapName('magma'));
    expect(button('Apply').getAttribute('aria-disabled')).toBeNull();
    click(button('Apply'));
    await settle();
    expect(state().appliedRender).toMatchObject({ colormapName: 'magma', percent: { low: '3', high: '97' } });
    expect(button('Apply').getAttribute('aria-disabled')).toBe('true');
  });

  it('refuses what is no whole percent or in the wrong order, says why, and asks nothing', async () => {
    for (const [low, high, problem] of [['abc', '98', PERCENT_PROBLEMS.number], ['2.5', '98', PERCENT_PROBLEMS.number], ['2', '101', PERCENT_PROBLEMS.number], ['98', '2', PERCENT_PROBLEMS.order], ['50', '50', PERCENT_PROBLEMS.order]]) {
      mount();
      typed(low, high);
      click(button('Apply'));
      await settle();
      expect(state().notice, `${low}/${high}`).toBe(problem);
    }
    expect(fetchMock).not.toHaveBeenCalled();
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
  });

  it('says so where the tiler gives no range for them (a constant band, no valid pixel), and changes nothing', async () => {
    typed('3', '97');
    answer = () => json(stats({ min: 5, max: 5, percentile_3: 5, percentile_97: 5 }));
    click(button('Apply'));
    await settle();
    expect(state().notice).toBe(NO_RANGE_AT_PERCENT);
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
    answer = () => json({ '1': { count: 0 } });
    click(button('Apply'));
    await settle();
    expect(state().notice).toBe(NO_RANGE_AT_PERCENT);
  });

  it('says so where the measure fails, changes nothing, and lets go of the busy state', async () => {
    typed('3', '97');
    answer = () => json({ detail: 'nope' }, 502);
    click(button('Apply'));
    await settle();
    expect(state().notice).toMatch(/^Could not measure the percentiles/u);
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
    expect(state().focusLoading).toBe(false);
  });

  it('says so where the answer holds no such percentile, and does not invent one', async () => {
    typed('3', '97');
    answer = () => json(stats({ min: 1, max: 9 }));
    click(button('Apply'));
    await settle();
    expect(state().notice).toBe(NO_RANGE_AT_PERCENT);
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
  });
});

describe('"Apply to all" with percentiles that are not applied yet', () => {
  it('takes their values first, and then keeps what is drawn for every image', async () => {
    toggleUnit();
    type(inputs()[0], '3');
    type(inputs()[1], '97');
    const save = button('Apply to all');
    expect(save.getAttribute('aria-disabled')).toBeNull();
    click(save);
    await settle();
    expect(asked()).toHaveLength(1);
    expect(state().appliedRender).toMatchObject({ rescale: '30,2800', percent: { low: '3', high: '97' } });
    // The other image takes the look, percentiles and all.
    const other = Object.values(state().savedLooks).flatMap((look) => (look && typeof look === 'object' ? [look] : []));
    expect(JSON.stringify(other)).toContain('30,2800');
  });

  it('keeps nothing where the percentiles cannot be turned into values', async () => {
    toggleUnit();
    type(inputs()[0], '3');
    type(inputs()[1], '97');
    answer = () => json({ detail: 'nope' }, 502);
    click(button('Apply to all'));
    await settle();
    expect(state().savedLooks).toEqual({});
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
  });
});
