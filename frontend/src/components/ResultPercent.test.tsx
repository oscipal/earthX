// @vitest-environment jsdom
//
// NM4-65 part 4 (Otto, 31.10.2026), the settings of a result layer: the switch "value / %" at vmin. In percentiles "Apply" reads
// the statistics of the result over its mask (`GET /results/{id}/statistics`, every whole percent), draws the values and the
// layer keeps what was typed; "Save" keeps that for the layer and the job (the saved look shows "%" again); closing without
// "Save" takes it back.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { NO_RANGE_AT_PERCENT, PERCENT_PROBLEMS } from '../percentRange';
import { useProcessingStore } from '../processingStore';
import { rangeOfTileUrl } from '../resultLayer';
import { useAppStore } from '../store';
import type { MapLayer } from '../layers';
import ResultControls from './ResultControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const RESULT = 'AbCdEfGhIjKlMnOpQrSt_-';
const JOB = 'ZyXwVuTsRqPoNmLkJiHg_-';
const stat = (min: number, max: number, p3: number, p97: number) => ({ minimum: min, maximum: max, count: 100, percentile_2: p3 - 1, percentile_3: p3, percentile_97: p97, percentile_98: p97 + 1 });
let body: () => Response;
let fetchMock: ReturnType<typeof vi.fn>;
const json = (b: unknown, status = 200) => new Response(JSON.stringify(b), { status, headers: { 'Content-Type': 'application/json' } });

const layer = (url = `/results/${RESULT}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0%2C100`, over: object = {}): MapLayer => ({
  id: 'R1',
  name: 'Result · Band math',
  visible: true,
  opacity: 1,
  derived: 'result',
  overlays: [{ kind: 'raster', tileUrl: url, bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
  result: { jobID: JOB, expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, ...over },
  restore: { datasetId: null, itemIds: [] } as never,
});

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  body = () => json({ bands: [{ name: 'a', statistics: stat(-5, 205, 3, 97) }] });
  fetchMock = vi.fn(async () => body());
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
  useAppStore.setState({ layers: [], resultViewLayerId: null });
  useProcessingStore.setState({ jobs: [] });
});

const state = () => useAppStore.getState();
const open = (l: MapLayer = layer()) => {
  act(() => useAppStore.setState({ layers: [l], resultViewLayerId: 'R1' }));
  act(() => root.render(<ResultControls />));
};
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
  for (let i = 0; i < 8; i++) await Promise.resolve();
});
const urlOf = () => (state().layers[0].overlays[0] as { tileUrl: string }).tileUrl;
const typedPercent = (low: string, high: string) => {
  toggleUnit();
  type(inputs()[0], low);
  type(inputs()[1], high);
};

describe('the switch in the settings of a result', () => {
  it('is at vmin, "value" to begin with, and turns the fields into 2 and 98', () => {
    open();
    expect(unitText()).toBe('absolute value');
    toggleUnit();
    expect(inputs().map((i) => i.value)).toEqual(['2', '98']);
    expect([...container.querySelectorAll('.vc-field > span')].map((s) => s.textContent)).toEqual(['vmin', 'vmax', 'Colormap', 'Opacity']);
  });

  it('is not there where nothing can be set: a result of whole numbers, one that is gone', () => {
    open(layer(undefined, { dataType: 'uint16' }));
    expect(container.querySelector('.vc-unit')).toBeNull();
    open(layer(undefined, { expired: true }));
    expect(container.querySelector('.vc-unit')).toBeNull();
  });

  it('opens in "%" for a layer whose look was typed that way', () => {
    open(layer(undefined, { percent: { low: '3', high: '97' } }));
    expect(unitText()).toBe('percentile');
    expect(inputs().map((i) => i.value)).toEqual(['3', '97']);
  });
});

describe('"Apply" with percentiles', () => {
  it('reads the statistics of the result, draws the values, and keeps what was typed on the layer', async () => {
    open();
    typedPercent('3', '97');
    click(button('Apply'));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(String(fetchMock.mock.calls[0][0])).toBe(`/results/${RESULT}/statistics`);
    expect(rangeOfTileUrl(urlOf())).toMatchObject({ vmin: '3', vmax: '97', colormap: 'viridis' });
    expect(state().layers[0].result).toMatchObject({ percent: { low: '3', high: '97' } });
    // What was saved before stays the saved look, with how it was typed.
    expect(state().layers[0].result!.savedTileUrl).toContain('rescale=0%2C100');
    expect(state().layers[0].result!.savedPercent).toBeNull();
    expect(button('Apply').getAttribute('aria-disabled')).toBe('true');
  });

  it('takes the minimum and the maximum for 0 and 100', async () => {
    open();
    typedPercent('0', '100');
    click(button('Apply'));
    await settle();
    expect(rangeOfTileUrl(urlOf())).toMatchObject({ vmin: '-5', vmax: '205' });
  });

  it('asks the statistics for the band the tile URL draws, and for all three of a colour picture, sharing one range', async () => {
    body = () => json({ bands: [{ statistics: stat(0, 10, 1, 9) }, { statistics: stat(0, 50, 5, 45) }, { statistics: stat(0, 20, 2, 18) }] });
    open(layer(`/results/${RESULT}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&bidx=2&rescale=0%2C100&colormap_name=viridis`));
    typedPercent('3', '97');
    click(button('Apply'));
    await settle();
    expect(rangeOfTileUrl(urlOf())).toMatchObject({ vmin: '5', vmax: '45' });
    // `percentile_3`/`percentile_97` are the 5 and 45 of the second band only.
    act(() => root.unmount());
    root = createRoot(container);
    body = () => json({ bands: [{ statistics: { ...stat(0, 10, 1, 9), percentile_3: 1, percentile_97: 9 } }, { statistics: { ...stat(0, 50, 5, 45), percentile_3: 5, percentile_97: 45 } }, { statistics: { ...stat(0, 20, 2, 18), percentile_3: 2, percentile_97: 18 } }] });
    open(layer(`/results/${RESULT}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&bidx=1&bidx=2&bidx=3&rescale=0%2C100`));
    typedPercent('3', '97');
    click(button('Apply'));
    await settle();
    expect(rangeOfTileUrl(urlOf())).toMatchObject({ vmin: '1', vmax: '45' });
  });

  it('refuses what is no whole percent or in the wrong order, says why, and reads nothing', async () => {
    open();
    typedPercent('abc', '98');
    click(button('Apply'));
    await settle();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe(PERCENT_PROBLEMS.number);
    type(inputs()[0], '98');
    type(inputs()[1], '2');
    click(button('Apply'));
    await settle();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe(PERCENT_PROBLEMS.order);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(urlOf()).toContain('rescale=0%2C100');
  });

  it('says so where the statistics give no range, fail, or are gone (410), and changes nothing', async () => {
    open();
    typedPercent('3', '97');
    body = () => json({ bands: [{ statistics: { count: 0, valid_percent: 0 } }] });
    click(button('Apply'));
    await settle();
    expect(container.querySelector('[role="alert"]')?.textContent).toBe(NO_RANGE_AT_PERCENT);
    body = () => json({ detail: 'gone' }, 410);
    click(button('Apply'));
    await settle();
    expect(container.querySelector('[role="alert"]')?.textContent).toMatch(/^Could not measure the percentiles/u);
    body = () => json({ nothing: true });
    click(button('Apply'));
    await settle();
    expect(container.querySelector('[role="alert"]')?.textContent).toMatch(/^Could not measure the percentiles/u);
    expect(urlOf()).toContain('rescale=0%2C100');
    expect(state().layers[0].result).not.toHaveProperty('percent');
  });

  it('keeps the colormap and does not read again where only the colormap changed', async () => {
    open();
    typedPercent('3', '97');
    click(button('Apply'));
    await settle();
    const select = container.querySelector<HTMLSelectElement>('.result-controls .vc-field select:not(.vc-unit)')!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(select, 'turbo');
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    click(button('Apply'));
    await settle();
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(urlOf()).toContain('colormap_name=turbo');
    expect(state().layers[0].result).toMatchObject({ percent: { low: '3', high: '97' } });
  });

  it('puts the usual stretch, 2 and 98, in the fields with "auto-scale", and reads nothing', () => {
    open();
    typedPercent('10', '90');
    click(button('auto-scale'));
    expect(inputs().map((i) => i.value)).toEqual(['2', '98']);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe('"Save" with percentiles', () => {
  const job = () => useProcessingStore.getState().jobs[0];
  beforeEach(() => {
    useProcessingStore.setState({ jobs: [{ jobID: JOB, range: null, bandRanges: {} } as never] });
  });

  it('reads the statistics first where they are not applied yet, then keeps the look for the layer and the job, typed as it was', async () => {
    open();
    typedPercent('3', '97');
    click(button('Save'));
    await settle();
    expect(rangeOfTileUrl(urlOf())).toMatchObject({ vmin: '3', vmax: '97' });
    expect(state().layers[0].result).not.toHaveProperty('savedTileUrl');
    expect(state().layers[0].result).not.toHaveProperty('savedPercent');
    expect(state().layers[0].result).toMatchObject({ percent: { low: '3', high: '97' } });
    expect(job().range).toMatchObject({ vmin: '3', vmax: '97', percent: { low: '3', high: '97' } });
    // Closing does not take it back.
    act(() => state().closeResultView());
    expect(rangeOfTileUrl(urlOf())).toMatchObject({ vmin: '3', vmax: '97' });
  });

  it('keeps nothing where the percentiles cannot be turned into values', async () => {
    open();
    typedPercent('3', '97');
    body = () => json({ detail: 'nope' }, 502);
    click(button('Save'));
    await settle();
    expect(job().range).toBeNull();
    expect(state().layers[0].result).toMatchObject({});
    expect(urlOf()).toContain('rescale=0%2C100');
  });

  it('keeps a layer made from one band for itself only, percentiles too', async () => {
    open(layer(undefined, { own: true }));
    typedPercent('3', '97');
    click(button('Save'));
    await settle();
    expect(state().layers[0].result).toMatchObject({ percent: { low: '3', high: '97' } });
    expect(job().range).toBeNull();
    expect(job().bandRanges).toEqual({});
  });
});

describe('the look that is applied and not saved', () => {
  it('goes with the settings: the saved look comes back, typed as it was', async () => {
    open(layer(undefined, { percent: { low: '5', high: '95' } }));
    // Saved as 5/95 (the settings open in "%"); now 3/97 is applied.
    type(inputs()[0], '3');
    type(inputs()[1], '97');
    click(button('Apply'));
    await settle();
    expect(state().layers[0].result).toMatchObject({ percent: { low: '3', high: '97' }, savedPercent: { low: '5', high: '95' } });
    act(() => state().revertResultLayer('R1'));
    expect(urlOf()).toContain('rescale=0%2C100');
    expect(state().layers[0].result).toMatchObject({ percent: { low: '5', high: '95' } });
    expect(state().layers[0].result).not.toHaveProperty('savedPercent');
  });

  it('goes back to "value" when the saved look was typed in values', async () => {
    open();
    typedPercent('3', '97');
    click(button('Apply'));
    await settle();
    act(() => state().revertResultLayer('R1'));
    expect(state().layers[0].result).not.toHaveProperty('percent');
  });
});
