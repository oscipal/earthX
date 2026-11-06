// @vitest-environment jsdom
//
// DS-03c (Otto, 04./05.11.2026): "Evaluate: per pass / per scene" at the top of "Advanced search" and the filter "AOI coverage".
// Two segment buttons, per pass first and pressed until the user chooses; what they mean, with an example, behind a (i). The
// coverage as a slider and a field that say the same, locked with the reason when there is no area, with its own (i), and
// working with or without "Filter within AOI only".

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { ELEVATION, OPTICAL, RADAR, TILES } from '../fixtures/searchFilters';
import { tipOf } from '../fixtures/tips';
import { useAppStore } from '../store';
import ControlPanel from './ControlPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] };
const COVERAGE = 'earthx:aoi_coverage';

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  container.className = 'app';
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({
    datasets: datasetsFrom([OPTICAL, RADAR, ELEVATION, TILES]),
    selectedDatasetIds: [],
    datasetId: null,
    aoi: AOI,
    aoiPoint: null,
    dateFrom: '',
    dateTo: '',
    searchFilters: {},
    searchWithin: {},
    searchEvaluate: 'pass',
    searching: false,
    error: null,
  });
  act(() => root.render(<ControlPanel />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const pick = (...ids: string[]) => act(() => useAppStore.setState({ selectedDatasetIds: ids, datasetId: ids[0] ?? null }));
const button = () => container.querySelector<HTMLButtonElement>('.advanced-btn');
const open = () => act(() => button()!.click());
const text = (el: Element | null) => el?.textContent ?? '';
const choice = () => container.querySelector<HTMLElement>('.evaluate-choice');
const segment = (name: string) => [...choice()!.querySelectorAll<HTMLButtonElement>('.btn.seg')].find((b) => text(b) === name)!;
const coverage = () => container.querySelector<HTMLElement>('.filter-coverage');
const slider = () => coverage()!.querySelector<HTMLInputElement>('input[type="range"]')!;
const number = () => coverage()!.querySelector<HTMLInputElement>('input[type="text"]')!;
const stored = () => useAppStore.getState().searchFilters;

function set(input: HTMLInputElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event(input.type === 'range' ? 'change' : 'input', { bubbles: true }));
  });
}

describe('"Evaluate: per pass / per scene"', () => {
  it('is two segment buttons, per pass first and pressed, per scene beside it', () => {
    pick('optical');
    open();
    const group = choice()!;
    expect(group.getAttribute('role')).toBe('group');
    expect(text(group.querySelector('.evaluate-label'))).toBe('Evaluate');
    const buttons = [...group.querySelectorAll<HTMLButtonElement>('.btn.seg')];
    expect(buttons.map((b) => text(b))).toEqual(['per pass', 'per scene']);
    expect(buttons.map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false']);
  });

  it('is the store\'s choice, per pass at first, and a click on the other one changes it, and back', () => {
    expect(useAppStore.getState().searchEvaluate).toBe('pass');
    pick('optical');
    open();
    act(() => segment('per scene').click());
    expect(useAppStore.getState().searchEvaluate).toBe('scene');
    expect(segment('per scene').getAttribute('aria-pressed')).toBe('true');
    expect(segment('per pass').getAttribute('aria-pressed')).toBe('false');
    act(() => segment('per pass').click());
    expect(useAppStore.getState().searchEvaluate).toBe('pass');
  });

  it('is at the top: above the switch "Filter within AOI only" and the fields', () => {
    pick('optical');
    open();
    const body = container.querySelector('.advanced-popup-body')!;
    const order = [...body.children].map((c) => c.className.split(' ')[0]);
    expect(order.indexOf('evaluate-choice')).toBeGreaterThan(order.indexOf('advanced-top'));
    expect(order.indexOf('evaluate-choice')).toBeLessThan(order.indexOf('within-aoi-row'));
    expect(order.indexOf('evaluate-choice')).toBeLessThan(order.indexOf('advanced-fields'));
  });

  it('is there for a dataset that offers it and not for one that does not', () => {
    pick('optical', 'radar');
    open();
    expect(choice()).not.toBeNull();
    act(() => container.querySelector<HTMLElement>('.advanced-popup .dataset-select-box')!.click());
    const options = [...container.querySelectorAll<HTMLElement>('.dataset-select-list [role="option"]')];
    act(() => options.find((o) => text(o).includes('Radar'))!.click());
    expect(choice()).toBeNull();
  });

  it('says what it means behind a (i), with a short example, in a tooltip and not as a paragraph', () => {
    pick('optical');
    open();
    const tip = choice()!.querySelector<HTMLElement>('.tip')!;
    const said = tipOf(tip);
    expect(said).toContain('Per pass');
    expect(said).toContain('Per scene');
    expect(said).toMatch(/Example/);
    expect(said).toMatch(/merged/);
    expect(container.querySelector('.advanced-popup-body')!.textContent).not.toContain('Example');
  });

  it('holds every filter: it is the same choice whichever filters are set, and Reset leaves it alone', () => {
    pick('optical');
    open();
    act(() => segment('per scene').click());
    act(() => useAppStore.getState().setSearchFilter('optical', 'platform', { kind: 'values', values: ['sat-a'] }));
    act(() => useAppStore.getState().resetSearchFilters('optical'));
    expect(useAppStore.getState().searchEvaluate).toBe('scene');
  });
});

describe('"AOI coverage"', () => {
  it('is a slider and a field under "Area", with a (i) that says what it measures', () => {
    pick('optical');
    open();
    expect(coverage()).not.toBeNull();
    expect([...container.querySelectorAll('.filter-group-title')].map((el) => text(el))).toContain('Area');
    const title = [...container.querySelectorAll('.filter-title')].find((el) => text(el) === 'AOI coverage')!;
    const said = tipOf(title.querySelector<HTMLElement>('.tip')!);
    expect(said).toMatch(/outlines/);
    expect(said).toMatch(/not the valid pixels/);
    expect(said).toMatch(/No data/);
    expect(said).toMatch(/Per pass/);
    expect(said).toMatch(/Per scene/);
  });

  it('is the only thing a dataset without filters of its own shows', () => {
    pick('tiles');
    expect(button()).not.toBeNull();
    open();
    expect([...container.querySelectorAll('.filter-title')].map((el) => text(el))).toEqual(['AOI coverage']);
    expect(choice()).toBeNull();
  });

  it('is not there for a dataset that does not offer it', () => {
    pick('radar');
    open();
    expect(coverage()).toBeNull();
    pick('elevation');
    expect(button()!.getAttribute('aria-disabled')).toBe('true');
    expect(coverage()).toBeNull();
  });

  it('is set by the slider, and the field shows the same', () => {
    pick('optical');
    open();
    set(slider(), '60');
    expect(stored().optical[COVERAGE]).toEqual({ kind: 'range', from: '60', to: '' });
    expect(number().value).toBe('60');
    expect(text(button())).toBe('Advanced search · 1');
  });

  it('is set by the field, and the slider shows the same', () => {
    pick('optical');
    open();
    set(number(), '45');
    expect(stored().optical[COVERAGE]).toEqual({ kind: 'range', from: '45', to: '' });
    expect(slider().value).toBe('45');
  });

  it('is no filter at 0 on the slider and with an empty field', () => {
    pick('optical');
    open();
    set(slider(), '60');
    set(slider(), '0');
    expect(number().value).toBe('');
    expect(text(button())).toBe('Advanced search');
    set(number(), '30');
    set(number(), '');
    expect(slider().value).toBe('0');
  });

  it('marks a number outside 0 to 100 and one that is none, and the search waits for it', () => {
    pick('optical');
    open();
    set(number(), '150');
    expect(number().getAttribute('aria-invalid')).toBe('true');
    expect(container.querySelector('.filter-field .error')).not.toBeNull();
    expect(container.querySelector<HTMLButtonElement>('.control-footer .btn.primary')!.disabled).toBe(true);
    set(number(), 'abc');
    expect(number().getAttribute('aria-invalid')).toBe('true');
    set(number(), '99');
    expect(number().getAttribute('aria-invalid')).toBe('false');
  });

  it('needs no date range', () => {
    useAppStore.setState({ dateFrom: '', dateTo: '' });
    pick('optical');
    open();
    expect(slider().disabled).toBe(false);
    expect(number().disabled).toBe(false);
  });

  it('is locked without an AOI, with the reason in its tooltip, and the fields are off', () => {
    useAppStore.setState({ aoi: null });
    pick('optical');
    open();
    expect(slider().disabled).toBe(true);
    expect(number().disabled).toBe(true);
    expect(coverage()!.getAttribute('data-tip')).toBe('Draw an AOI to use this filter');
  });

  it('is not locked for a point: the square around it is the AOI (Otto, 06.11.2026)', () => {
    useAppStore.setState({ aoiPoint: { type: 'Point', coordinates: [10.5, 47.5] } });
    pick('optical');
    open();
    expect(number().disabled).toBe(false);
    expect(slider().disabled).toBe(false);
    expect(coverage()!.getAttribute('data-tip')).toBeNull();
  });

  it('is free again with the AOI, empty', () => {
    useAppStore.setState({ aoi: null });
    pick('optical');
    open();
    act(() => useAppStore.setState({ aoi: AOI }));
    expect(number().disabled).toBe(false);
    expect(number().value).toBe('');
    expect(coverage()!.hasAttribute('data-tip')).toBe(false);
  });

  it('goes with the AOI: what stood in it is gone, in every dataset, and does not come back with the next', () => {
    pick('optical', 'tiles');
    open();
    set(number(), '70');
    act(() => useAppStore.getState().setSearchFilter('tiles', COVERAGE, { kind: 'range', from: '40', to: '' }));
    act(() => useAppStore.setState({ aoi: null }));
    expect(stored().optical?.[COVERAGE]).toBeUndefined();
    expect(stored().tiles?.[COVERAGE]).toBeUndefined();
    act(() => useAppStore.setState({ aoi: AOI }));
    expect(number().value).toBe('');
  });

  it('works with and without "Filter within AOI only": the switch does not change it', () => {
    useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' });
    pick('optical');
    open();
    set(number(), '80');
    act(() => useAppStore.getState().setSearchWithin('optical', true));
    expect(number().value).toBe('80');
    expect(stored().optical[COVERAGE]).toEqual({ kind: 'range', from: '80', to: '' });
    expect(number().disabled).toBe(false);
  });

  it('is cleared by "Reset filters"', () => {
    pick('optical');
    open();
    set(number(), '55');
    const reset = [...container.querySelectorAll<HTMLButtonElement>('.advanced-actions .btn')].find((b) => text(b) === 'Reset filters')!;
    act(() => reset.click());
    expect(stored().optical).toBeUndefined();
    expect(number().value).toBe('');
  });
});

describe('the (i) beside "Filter within AOI only"', () => {
  it('names the filters it measures, with the class of each share the registry gives', () => {
    const water = {
      property: 'test:water',
      kind: 'range',
      title: 'Water',
      group: 'Scene',
      description: 'Share of the scene classified as water.',
      unit: '%',
      within_aoi: 'earthx:aoi_water',
      area_based: true,
      type: 'number',
      minimum: 0,
      maximum: 100,
    };
    const added = {
      ...OPTICAL,
      'earthx:search_filters': [...OPTICAL['earthx:search_filters']!, water],
      'earthx:mask': { ...OPTICAL['earthx:mask']!, share_classes: { 'earthx:aoi_water': [6] } },
    };
    act(() => useAppStore.setState({ datasets: datasetsFrom([added]) }));
    pick('optical');
    open();
    const said = tipOf(container.querySelector<HTMLElement>('.within-aoi-row .tip')!);
    expect(said).toContain('Cloud cover (classes 5, 6; cloud shadows do not count), No data, Water (class 6).');
    expect(said).toContain('Others are unchanged.');
    expect(said).not.toContain('Satellite');
  });

  it('is a (i) and the switch itself carries a tooltip only for the reason it is locked', () => {
    useAppStore.setState({ dateFrom: '2026-07-01', dateTo: '2026-07-31' });
    pick('optical');
    open();
    expect(container.querySelector('.within-aoi-row .tip')).not.toBeNull();
    expect(container.querySelector('.within-aoi')!.hasAttribute('data-tip')).toBe(false);
    act(() => useAppStore.setState({ aoi: null }));
    expect(tipOf(container.querySelector<HTMLElement>('.within-aoi')!)).toBe('Draw an AOI and set a date range first');
  });
});
