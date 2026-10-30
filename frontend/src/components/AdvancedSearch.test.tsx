// @vitest-environment jsdom
//
// DS-02c: "Advanced search" in the control menu. It is there only while a ticked dataset has filters, shows the
// filters of one dataset at a time (the box is the one of the results), keeps the values of each dataset apart,
// says in its head for how many datasets filters are set, and marks fields that are wrong while "Search" waits.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { ELEVATION, LEGACY, OPTICAL, RADAR } from '../fixtures/searchFilters';
import { useAppStore } from '../store';
import ControlPanel from './ControlPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const AOI: GeoJSON.Polygon = { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] };

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  // Dropdowns open in `.app` (`Popover`), outside the panel.
  container.className = 'app';
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({
    datasets: datasetsFrom([OPTICAL, RADAR, ELEVATION, LEGACY]),
    selectedDatasetIds: [],
    datasetId: null,
    aoi: AOI,
    aoiPoint: null,
    searchFilters: {},
    sceneNameQuery: '',
    showCoverage: false,
    coverageDatasetId: null,
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
const head = () => container.querySelector<HTMLButtonElement>('.advanced-head');
const section = () => container.querySelector('.advanced-search');
const body = () => container.querySelector('.advanced-body');
const box = () => container.querySelector<HTMLButtonElement>('.advanced-body .dataset-select-box')!;
const options = () => [...document.querySelectorAll<HTMLElement>('.dataset-select-list [role="option"]')];
const text = (el: Element | null) => el?.textContent ?? '';
const field = (label: string) => container.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!;
const titles = () => [...container.querySelectorAll('.filter-title')].map((el) => text(el));
const searchButton = () => container.querySelector<HTMLButtonElement>('.primary-btn')!;
const open = () => act(() => head()!.click());

function type(input: HTMLInputElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
const tick = (label: string) =>
  act(() => [...container.querySelectorAll<HTMLInputElement>('.filter-check input')].find((i) => text(i.parentElement) === label)!.click());

describe('when "Advanced search" is there', () => {
  it('is not there while no dataset is ticked', () => {
    expect(section()).toBeNull();
  });

  it('is there for a dataset with filters, closed, with no filter shown', () => {
    pick('optical');
    expect(head()).not.toBeNull();
    expect(text(head())).toBe('▸Advanced search');
    expect(head()!.getAttribute('aria-expanded')).toBe('false');
    expect(body()).toBeNull();
  });

  it.each([
    ['a dataset without filters', ['elevation']],
    ['a dataset of an older backend', ['legacy']],
  ])('is not there for %s — hidden, not greyed out', (_name, ids) => {
    pick(...ids);
    expect(section()).toBeNull();
  });

  it('goes with the last dataset that has filters, and comes back with it', () => {
    pick('optical', 'elevation');
    expect(head()).not.toBeNull();
    pick('elevation');
    expect(section()).toBeNull();
    pick('optical');
    expect(head()).not.toBeNull();
  });

  it('opens and closes by its head, and shows a caret for it', () => {
    pick('optical');
    expect(head()!.hasAttribute('aria-controls')).toBe(false);
    open();
    expect(head()!.getAttribute('aria-controls')).toBe(body()!.id);
    expect(head()!.getAttribute('aria-expanded')).toBe('true');
    expect(text(head())).toBe('▾Advanced search');
    expect(body()).not.toBeNull();
    open();
    expect(body()).toBeNull();
  });

  it('sits below the acquisition date, in the scrolling part of the menu', () => {
    pick('optical');
    const dates = container.querySelector('.date-row')!;
    expect(dates.compareDocumentPosition(section()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(container.querySelector('.control-scroll')!.contains(section())).toBe(true);
  });
});

describe('the filters of the dataset shown', () => {
  it('lists the filters of the registry in its order, with a tooltip each', () => {
    pick('optical');
    open();
    expect(titles()).toEqual(['Cloud cover', 'Satellite']);
    expect(container.querySelector('.filter-title')!.getAttribute('title')).toBe('Share of the scene covered by clouds.');
  });

  it('shows a range as two fields with the bounds as placeholders and the unit', () => {
    pick('optical');
    open();
    const from = field('Cloud cover, from');
    const to = field('Cloud cover, to');
    expect([from.type, from.placeholder, to.placeholder, from.value, to.value]).toEqual(['text', '0', '100', '', '']);
    expect(text(container.querySelector('.filter-range'))).toBe('fromto%');
    expect(from.inputMode).toBe('decimal');
  });

  it('asks for whole numbers where the registry says so', () => {
    pick('radar');
    open();
    expect(field('Relative orbit, from').inputMode).toBe('numeric');
    expect(container.querySelector('.filter-unit')).toBeNull();
  });

  it('shows a choice as one box per value, none ticked at first', () => {
    pick('optical');
    open();
    const checks = [...container.querySelectorAll<HTMLInputElement>('.filter-check input')];
    expect(checks.map((c) => text(c.parentElement))).toEqual(['Satellite A', 'Satellite B']);
    expect(checks.map((c) => c.checked)).toEqual([false, false]);
  });

  it('puts what is typed and ticked into the store, as the fields say it', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '20');
    tick('Satellite B');
    expect(useAppStore.getState().searchFilters).toEqual({
      optical: {
        'test:cloud': { kind: 'range', from: '', to: '20' },
        platform: { kind: 'values', values: ['sat-b'] },
      },
    });
    expect(field('Cloud cover, to').value).toBe('20');
    tick('Satellite B');
    type(field('Cloud cover, to'), '');
    expect(useAppStore.getState().searchFilters).toEqual({});
  });

  it('keeps both bounds when one is typed', () => {
    pick('optical');
    open();
    type(field('Cloud cover, from'), '5');
    type(field('Cloud cover, to'), '20');
    expect(useAppStore.getState().searchFilters.optical['test:cloud']).toEqual({ kind: 'range', from: '5', to: '20' });
  });
});

describe('one dataset at a time, each with its own values', () => {
  it('shows the first dataset with filters, and a box that is no button with only one', () => {
    pick('optical', 'elevation');
    open();
    expect(text(box())).toBe('Optical imagery');
    expect(box().disabled).toBe(true);
    expect(box().getAttribute('aria-haspopup')).toBeNull();
  });

  it('lists only the ticked datasets that have filters, in the keyboard way of the results box', () => {
    pick('optical', 'elevation', 'radar');
    open();
    expect(box().disabled).toBe(false);
    expect(box().getAttribute('aria-haspopup')).toBe('listbox');
    expect(box().getAttribute('aria-labelledby')).toBe(container.querySelector('.advanced-body .eyebrow')!.id);
    expect(text(container.querySelector('.advanced-body .eyebrow'))).toBe('Dataset');
    expect(options()).toHaveLength(0);

    act(() => {
      box().dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true }));
    });
    expect(options().map((o) => text(o))).toEqual(['Optical imagery', 'Radar imagery']);
    expect(options().map((o) => o.getAttribute('aria-selected'))).toEqual(['true', 'false']);
    expect(document.querySelector('[role="listbox"]')!.getAttribute('aria-label')).toBe('Datasets with filters');

    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(options()).toHaveLength(0);
  });

  it('switching shows the filters of the other dataset and gives the focus back to the box', () => {
    pick('optical', 'radar');
    open();
    act(() => box().click());
    act(() => options()[1].click());
    expect(text(box())).toBe('Radar imagery▾');
    expect(titles()).toEqual(['Relative orbit']);
    expect(options()).toHaveLength(0);
    expect(document.activeElement).toBe(box());
  });

  it('keeps the values of each dataset apart, and as they were when it comes back', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    act(() => box().click());
    act(() => options()[1].click());
    expect(field('Relative orbit, from').value).toBe('');
    type(field('Relative orbit, from'), '22');
    act(() => box().click());
    act(() => options()[0].click());
    expect(field('Cloud cover, to').value).toBe('20');
    expect(useAppStore.getState().searchFilters).toEqual({
      optical: { 'test:cloud': { kind: 'range', from: '', to: '20' } },
      radar: { 'test:track': { kind: 'range', from: '22', to: '' } },
    });
  });

  it('marks in the list the datasets that have filters set', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    expect(box().querySelector('.filter-dot')).not.toBeNull();
    act(() => box().click());
    expect(options().map((o) => o.querySelector('.filter-dot') !== null)).toEqual([true, false]);
    expect(options()[0].querySelector('.filter-dot')!.getAttribute('aria-label')).toBe('Filters set');
  });

  it('falls back to another dataset when the one shown is unticked', () => {
    pick('optical', 'radar');
    open();
    act(() => box().click());
    act(() => options()[1].click());
    pick('optical');
    expect(text(box())).toBe('Optical imagery');
    expect(titles()).toEqual(['Cloud cover', 'Satellite']);
  });
});

describe('the head says for how many datasets filters are set', () => {
  it('says nothing while none is set, even closed', () => {
    pick('optical', 'radar');
    expect(container.querySelector('.advanced-count')).toBeNull();
    expect(head()!.title).toMatch(/^Narrow the search/);
  });

  it('counts the datasets, not the filters, with the tooltip naming them', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    tick('Satellite A');
    expect(text(head())).toBe('▾Advanced search· 1 dataset');
    expect(head()!.title).toBe('Optical imagery: Cloud cover, Satellite');

    act(() => box().click());
    act(() => options()[1].click());
    type(field('Relative orbit, from'), '22');
    expect(text(head())).toBe('▾Advanced search· 2 datasets');
    expect(head()!.title).toBe('Optical imagery: Cloud cover, Satellite\nRadar imagery: Relative orbit');
    open();
    expect(text(head())).toBe('▸Advanced search· 2 datasets');
  });

  it('does not count a dataset that is unticked, and counts it again when it is back', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    pick('radar');
    expect(container.querySelector('.advanced-count')).toBeNull();
    pick('optical', 'radar');
    expect(text(container.querySelector('.advanced-count'))).toBe('· 1 dataset');
  });
});

describe('fields that are wrong', () => {
  const states = () => ({
    search: searchButton().disabled,
    invalid: [...container.querySelectorAll('input[aria-invalid="true"]')].map((i) => i.getAttribute('aria-label')),
    messages: [...container.querySelectorAll('.filter-field .hint-text.error')].map((p) => text(p)),
  });

  it('marks the field, says why under it and holds "Search" back until it is right', () => {
    pick('optical');
    open();
    expect(states().search).toBe(false);

    type(field('Cloud cover, to'), '120');
    expect(states()).toEqual({ search: true, invalid: ['Cloud cover, to'], messages: ['Between 0 and 100'] });
    expect(field('Cloud cover, to').getAttribute('aria-describedby')).toBe(container.querySelector('.filter-field .hint-text.error')!.id);
    expect(text(container.querySelector('.control-footer'))).toContain('Correct the filters in Advanced search.');
    expect(text(head())).toContain('· check input');

    type(field('Cloud cover, to'), '12');
    expect(states()).toEqual({ search: false, invalid: [], messages: [] });
    expect(text(head())).not.toContain('check input');
    expect(text(container.querySelector('.control-footer'))).not.toContain('Correct the filters');
  });

  it('marks both fields when the start is above the end', () => {
    pick('optical');
    open();
    type(field('Cloud cover, from'), '50');
    type(field('Cloud cover, to'), '20');
    expect(states()).toEqual({
      search: true,
      invalid: ['Cloud cover, from', 'Cloud cover, to'],
      messages: ['From is above to'],
    });
  });

  it.each(['20-', '-', '1e', '--5', '1,5', 'abc'])('marks half-typed or wrong text "%s" instead of dropping the filter', (text) => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), text);
    expect(field('Cloud cover, to').value).toBe(text);
    expect(states()).toEqual({ search: true, invalid: ['Cloud cover, to'], messages: ['Enter a number'] });
  });

  it('says so for a fraction where only whole numbers are asked for', () => {
    pick('radar');
    open();
    type(field('Relative orbit, from'), '2.5');
    expect(states().messages).toEqual(['Whole numbers only']);
    expect(states().search).toBe(true);
  });

  it('still holds "Search" back when the section is closed, and says so in the head', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '-5');
    open();
    expect(body()).toBeNull();
    expect(searchButton().disabled).toBe(true);
    expect(text(head())).toContain('· check input');
  });

  it('holds back for a ticked dataset only, and the wrong values come back with it', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '500');
    pick('radar');
    expect(searchButton().disabled).toBe(false);
    pick('optical', 'radar');
    expect(searchButton().disabled).toBe(true);
  });

  it('does not hold back the lookup of a scene by its name, which reads no filter', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '500');
    useAppStore.setState({ aoi: null });
    act(() => useAppStore.getState().setSceneNameQuery('S2C_T32TNT_20260920T103025_L2A'));
    expect(searchButton().disabled).toBe(false);
    expect(text(container.querySelector('.control-footer'))).not.toContain('Correct the filters');
  });
});

describe('"Reset filters"', () => {
  it('is there once a filter of the dataset shown is set, and not before', () => {
    pick('optical', 'radar');
    open();
    expect(container.querySelector('.reset-filters')).toBeNull();
    type(field('Cloud cover, to'), '20');
    expect(text(container.querySelector('.reset-filters'))).toBe('Reset filters');
  });

  it('keeps the focus in the section when the button goes with the filters', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '20');
    act(() => container.querySelector<HTMLButtonElement>('.reset-filters')!.focus());
    act(() => container.querySelector<HTMLButtonElement>('.reset-filters')!.click());
    expect(container.querySelector('.reset-filters')).toBeNull();
    expect(container.querySelector('.advanced-body')!.contains(document.activeElement)).toBe(true);
  });

  it('takes back the filters of the dataset shown only', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    tick('Satellite A');
    act(() => box().click());
    act(() => options()[1].click());
    type(field('Relative orbit, from'), '22');
    act(() => box().click());
    act(() => options()[0].click());

    act(() => container.querySelector<HTMLButtonElement>('.reset-filters')!.click());

    expect(useAppStore.getState().searchFilters).toEqual({
      radar: { 'test:track': { kind: 'range', from: '22', to: '' } },
    });
    expect(field('Cloud cover, to').value).toBe('');
    expect(container.querySelector('.reset-filters')).toBeNull();
    expect(text(container.querySelector('.advanced-count'))).toBe('· 1 dataset');
  });
});

describe('the search settings', () => {
  it('stay when the results are cleared', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '20');
    act(() => useAppStore.getState().clearSearchResults());
    expect(field('Cloud cover, to').value).toBe('20');
  });
});

describe('"Search" sends what the fields say', () => {
  it('asks each ticked dataset with its own filters, and nothing for the one without', async () => {
    const fetchMock = vi.fn(async () => ({
      ok: true,
      status: 200,
      statusText: '',
      json: async () => ({ features: [], numberReturned: 0, links: [] }),
    }));
    vi.stubGlobal('fetch', fetchMock);
    pick('optical', 'radar', 'elevation');
    open();
    type(field('Cloud cover, to'), '20');
    tick('Satellite B');
    act(() => box().click());
    act(() => options()[1].click());
    type(field('Relative orbit, from'), '22');
    type(field('Relative orbit, to'), '22');

    await act(async () => {
      searchButton().click();
    });

    const calls = fetchMock.mock.calls as unknown as [string, RequestInit][];
    const searches = calls.filter(([url]) => url === '/stac/search').map(([, init]) => JSON.parse(init.body as string));
    expect(searches[0].collections).toEqual(['optical', 'radar', 'elevation']);
    expect(searches[0].query_by_collection).toEqual({
      optical: { 'test:cloud': { lte: 20 }, platform: { in: ['sat-b'] } },
      radar: { 'test:track': { gte: 22, lte: 22 } },
    });
  });
});
