// @vitest-environment jsdom
//
// DS-02c (Otto, 30.10.2026): "Advanced search" is a button above "Search", with the number of filters set, and a
// pop-up with the filters of one dataset at a time under the headings of the registry. The button is there only while
// a ticked dataset has filters; the pop-up keeps the values of each dataset apart, closes on "Done", Escape and a click
// beside it without losing a value, marks fields that are wrong and leaves "Search" held back while one is.

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
  // The pop-ups open in `.app` (`Popover`), outside the panel.
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
const button = () => container.querySelector<HTMLButtonElement>('.advanced-btn');
const popup = () => container.querySelector<HTMLElement>('.advanced-popup');
const box = () => container.querySelector<HTMLButtonElement>('.advanced-popup .dataset-select-box')!;
const options = () => [...container.querySelectorAll<HTMLElement>('.dataset-select-list [role="option"]')];
const text = (el: Element | null) => el?.textContent ?? '';
const field = (label: string) => container.querySelector<HTMLInputElement>(`input[aria-label="${label}"]`)!;
const titles = () => [...container.querySelectorAll('.filter-title')].map((el) => text(el));
const headings = () => [...container.querySelectorAll('.filter-group-title')].map((el) => text(el));
const searchButton = () => container.querySelector<HTMLButtonElement>('.control-footer .primary-btn')!;
const open = () => act(() => button()!.click());
const key = (target: Element | Document, name: string) =>
  act(() => {
    target.dispatchEvent(new KeyboardEvent('keydown', { key: name, bubbles: true }));
  });
const switchTo = (index: number) => {
  act(() => box().click());
  act(() => options()[index].click());
};

function type(input: HTMLInputElement, value: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
    input.dispatchEvent(new Event('input', { bubbles: true }));
  });
}
const tick = (label: string) =>
  act(() => [...container.querySelectorAll<HTMLInputElement>('.filter-check input')].find((i) => text(i.parentElement) === label)!.click());

describe('when the button is there', () => {
  it('is not there while no dataset is ticked', () => {
    expect(button()).toBeNull();
  });

  it('is there for a dataset with filters, with no pop-up and no count', () => {
    pick('optical');
    expect(text(button())).toBe('Advanced search');
    expect(button()!.getAttribute('aria-expanded')).toBe('false');
    expect(button()!.hasAttribute('aria-controls')).toBe(false);
    expect(popup()).toBeNull();
  });

  it.each([
    ['a dataset without filters', ['elevation']],
    ['a dataset of an older backend', ['legacy']],
  ])('is not there for %s — hidden, not greyed out', (_name, ids) => {
    pick(...ids);
    expect(button()).toBeNull();
  });

  it('goes with the last dataset that has filters, and comes back with it', () => {
    pick('optical', 'elevation');
    expect(button()).not.toBeNull();
    pick('elevation');
    expect(button()).toBeNull();
    pick('optical');
    expect(button()).not.toBeNull();
  });

  it('closes the pop-up when the last dataset with filters goes, and does not open it again with the next', () => {
    pick('optical');
    open();
    expect(popup()).not.toBeNull();
    pick('elevation');
    expect(button()).toBeNull();
    expect(popup()).toBeNull();
    pick('optical');
    expect(popup()).toBeNull();
  });

  it('is the button right above "Search", in the footer that stays in view, and as wide', () => {
    pick('optical');
    const footer = container.querySelector('.control-footer')!;
    expect(button()!.nextElementSibling).toBe(searchButton());
    expect(button()!.parentElement).toBe(footer);
    expect(container.querySelector('.control-scroll')!.contains(button())).toBe(false);
  });
});

describe('the pop-up', () => {
  it('opens by the button, as a dialog the button names', () => {
    pick('optical');
    open();
    expect(popup()!.getAttribute('role')).toBe('dialog');
    expect(popup()!.getAttribute('aria-label')).toBe('Advanced search');
    expect(button()!.getAttribute('aria-expanded')).toBe('true');
    expect(button()!.getAttribute('aria-controls')).toBe(popup()!.querySelector('.advanced-popup-body')!.id);
  });

  it('closes by the button again', () => {
    pick('optical');
    open();
    open();
    expect(popup()).toBeNull();
  });

  it('stands the filters under the headings of the registry, in its order', () => {
    pick('optical');
    open();
    expect(headings()).toEqual(['Clouds', 'Scene', 'Acquisition']);
    expect(titles()).toEqual(['Cloud cover', 'No data', 'Satellite']);
    const sections = [...container.querySelectorAll('.filter-group')];
    expect(sections.map((s) => s.getAttribute('aria-label'))).toEqual(['Clouds', 'Scene', 'Acquisition']);
    expect(sections.map((s) => [...s.querySelectorAll('.filter-title')].map((t) => text(t)))).toEqual([['Cloud cover'], ['No data'], ['Satellite']]);
  });

  it('has no heading where the dataset has only one group', () => {
    pick('radar');
    open();
    expect(headings()).toEqual([]);
    expect(titles()).toEqual(['Relative orbit']);
  });

  it('shows a filter of the registry that no code here knows, in the group it names', () => {
    const extra = {
      property: 'made:up',
      kind: 'range',
      title: 'Brand new',
      group: 'Elsewhere',
      description: 'A filter added to the registry only.',
      unit: 'km',
      type: 'number',
      minimum: 0,
      maximum: 5,
    };
    const added = { ...OPTICAL, 'earthx:search_filters': [...OPTICAL['earthx:search_filters']!, extra] };
    act(() => useAppStore.setState({ datasets: datasetsFrom([added]) }));
    pick('optical');
    open();
    expect(headings()).toEqual(['Clouds', 'Scene', 'Acquisition', 'Elsewhere']);
    expect(text(container.querySelectorAll('.filter-range')[2])).toBe('fromtokm');
    type(field('Brand new, to'), '3');
    expect(useAppStore.getState().searchFilters.optical['made:up']).toEqual({ kind: 'range', from: '', to: '3' });
  });

  it('shows a range as two fields with the bounds as placeholders and the unit, a tooltip on the title', () => {
    pick('optical');
    open();
    const from = field('Cloud cover, from');
    const to = field('Cloud cover, to');
    expect([from.type, from.placeholder, to.placeholder, from.value, to.value]).toEqual(['text', '0', '100', '', '']);
    expect(from.inputMode).toBe('decimal');
    expect(text(container.querySelector('.filter-range'))).toBe('fromto%');
    expect(container.querySelector('.filter-title')!.getAttribute('title')).toBe('Share of the scene covered by clouds.');
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

  it('puts the focus on the first thing to work with when it opens', () => {
    pick('optical');
    open();
    expect(document.activeElement).toBe(field('Cloud cover, from'));
    open();
    pick('optical', 'radar');
    open();
    expect(document.activeElement).toBe(box());
  });
});

describe('closing keeps the values', () => {
  const filled = () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '20');
    tick('Satellite A');
  };
  const kept = {
    optical: { 'test:cloud': { kind: 'range', from: '', to: '20' }, platform: { kind: 'values', values: ['sat-a'] } },
  };

  it('"Done" closes it and gives the focus back to the button', () => {
    filled();
    act(() => [...container.querySelectorAll<HTMLButtonElement>('.advanced-actions button')].find((b) => text(b) === 'Done')!.click());
    expect(popup()).toBeNull();
    expect(document.activeElement).toBe(button());
    expect(useAppStore.getState().searchFilters).toEqual(kept);
  });

  // NM4-65 part 8: the red "x" of every closing, here beside the dataset box; it closes like "Done".
  it('the red "x" closes it, gives the focus back to the button and keeps the values', () => {
    filled();
    const cross = popup()!.querySelector<HTMLButtonElement>('.advanced-top .close-x')!;
    expect(cross.title).toBe('Close');
    act(() => cross.click());
    expect(popup()).toBeNull();
    expect(document.activeElement).toBe(button());
    expect(useAppStore.getState().searchFilters).toEqual(kept);
  });

  it('Escape closes it and gives the focus back to the button', () => {
    filled();
    key(field('Cloud cover, to'), 'Escape');
    expect(popup()).toBeNull();
    expect(document.activeElement).toBe(button());
    expect(useAppStore.getState().searchFilters).toEqual(kept);
  });

  it('a click beside it closes it', () => {
    filled();
    act(() => {
      document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    });
    expect(popup()).toBeNull();
    expect(useAppStore.getState().searchFilters).toEqual(kept);
  });

  it('a click inside it, and in the list of datasets that lies over it, does not', () => {
    pick('optical', 'radar');
    open();
    act(() => {
      field('Cloud cover, from').dispatchEvent(new Event('pointerdown', { bubbles: true }));
    });
    expect(popup()).not.toBeNull();
    act(() => box().click());
    act(() => {
      options()[1].dispatchEvent(new Event('pointerdown', { bubbles: true }));
    });
    expect(popup()).not.toBeNull();
    act(() => options()[1].click());
    expect(popup()).not.toBeNull();
    expect(titles()).toEqual(['Relative orbit']);
  });

  it('Escape in the list of datasets closes the list only; the next Escape the pop-up', () => {
    pick('optical', 'radar');
    open();
    act(() => box().click());
    expect(options()).toHaveLength(2);
    key(document, 'Escape');
    expect(options()).toHaveLength(0);
    expect(popup()).not.toBeNull();
    key(box(), 'Escape');
    expect(popup()).toBeNull();
  });

  it('Tab moves between the fields instead of closing it', () => {
    pick('optical');
    open();
    key(field('Cloud cover, from'), 'Tab');
    key(field('Cloud cover, from'), 'ArrowDown');
    expect(popup()).not.toBeNull();
  });

  it('opens again with what was in it', () => {
    filled();
    key(field('Cloud cover, to'), 'Escape');
    open();
    expect(field('Cloud cover, to').value).toBe('20');
    expect(container.querySelector<HTMLInputElement>('.filter-check input')!.checked).toBe(true);
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
    const label = container.querySelector('.advanced-popup .eyebrow')!;
    expect(box().getAttribute('aria-labelledby')).toBe(label.id);
    expect(text(label)).toBe('Dataset');
    expect(options()).toHaveLength(0);

    key(box(), 'ArrowDown');
    expect(options().map((o) => text(o))).toEqual(['Optical imagery', 'Radar imagery']);
    expect(options().map((o) => o.getAttribute('aria-selected'))).toEqual(['true', 'false']);
    expect(document.querySelector('[role="listbox"]')!.getAttribute('aria-label')).toBe('Datasets with filters');
  });

  it('switching shows the filters of the other dataset and gives the focus back to the box', () => {
    pick('optical', 'radar');
    open();
    switchTo(1);
    expect(text(box())).toBe('Radar imagery▾');
    expect(titles()).toEqual(['Relative orbit']);
    expect(headings()).toEqual([]);
    expect(options()).toHaveLength(0);
    expect(document.activeElement).toBe(box());
  });

  it('keeps the values of each dataset apart, and as they were when it comes back', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    switchTo(1);
    expect(field('Relative orbit, from').value).toBe('');
    type(field('Relative orbit, from'), '22');
    switchTo(0);
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
    switchTo(1);
    pick('optical');
    expect(text(box())).toBe('Optical imagery');
    expect(titles()).toEqual(['Cloud cover', 'No data', 'Satellite']);
  });
});

describe('the number on the button', () => {
  it('says nothing while no filter is set', () => {
    pick('optical', 'radar');
    expect(text(button())).toBe('Advanced search');
    expect(button()!.title).toMatch(/^Narrow the search/);
  });

  it('counts the filters that are set, over the datasets, with the tooltip naming them', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    expect(text(button())).toBe('Advanced search · 1');
    tick('Satellite A');
    expect(text(button())).toBe('Advanced search · 2');
    expect(button()!.title).toBe('Optical imagery: Cloud cover, Satellite');
    switchTo(1);
    type(field('Relative orbit, from'), '22');
    expect(text(button())).toBe('Advanced search · 3');
    expect(button()!.title).toBe('Optical imagery: Cloud cover, Satellite\nRadar imagery: Relative orbit');
  });

  it('stays when the pop-up is closed', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '20');
    open();
    expect(text(button())).toBe('Advanced search · 1');
  });

  it('does not count a dataset that is unticked, and counts it again when it is back', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    pick('radar');
    expect(text(button())).toBe('Advanced search');
    pick('optical', 'radar');
    expect(text(button())).toBe('Advanced search · 1');
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
    expect(button()!.classList.contains('wrong')).toBe(true);

    type(field('Cloud cover, to'), '12');
    expect(states()).toEqual({ search: false, invalid: [], messages: [] });
    expect(button()!.classList.contains('wrong')).toBe(false);
    expect(text(container.querySelector('.control-footer'))).not.toContain('Correct the filters');
  });

  it('marks both fields when the start is above the end', () => {
    pick('optical');
    open();
    type(field('Cloud cover, from'), '50');
    type(field('Cloud cover, to'), '20');
    expect(states()).toEqual({ search: true, invalid: ['Cloud cover, from', 'Cloud cover, to'], messages: ['From is above to'] });
  });

  it.each(['20-', '-', '1e', '--5', '1,5', 'abc'])('marks half-typed or wrong text "%s" instead of dropping the filter', (value) => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), value);
    expect(field('Cloud cover, to').value).toBe(value);
    expect(states()).toEqual({ search: true, invalid: ['Cloud cover, to'], messages: ['Enter a number'] });
  });

  it('says so for a fraction where only whole numbers are asked for', () => {
    pick('radar');
    open();
    type(field('Relative orbit, from'), '2.5');
    expect(states().messages).toEqual(['Whole numbers only']);
    expect(states().search).toBe(true);
  });

  it('"Done" closes the pop-up all the same, the field stays red and "Search" stays held back', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '-5');
    act(() => [...container.querySelectorAll<HTMLButtonElement>('.advanced-actions button')].find((b) => text(b) === 'Done')!.click());
    expect(popup()).toBeNull();
    expect(searchButton().disabled).toBe(true);
    expect(button()!.classList.contains('wrong')).toBe(true);
    open();
    expect(field('Cloud cover, to').value).toBe('-5');
    expect(field('Cloud cover, to').getAttribute('aria-invalid')).toBe('true');
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
  const reset = () => [...container.querySelectorAll<HTMLButtonElement>('.advanced-actions button')].find((b) => text(b) === 'Reset filters');

  it('is there once a filter of the dataset shown is set, and not before', () => {
    pick('optical', 'radar');
    open();
    expect(reset()).toBeUndefined();
    type(field('Cloud cover, to'), '20');
    expect(reset()).toBeDefined();
    switchTo(1);
    expect(reset()).toBeUndefined();
  });

  it('keeps the focus in the pop-up when the button goes with the filters', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '20');
    act(() => reset()!.focus());
    act(() => reset()!.click());
    expect(reset()).toBeUndefined();
    expect(popup()!.contains(document.activeElement)).toBe(true);
  });

  it('takes back the filters of the dataset shown only, and "Done" is still there', () => {
    pick('optical', 'radar');
    open();
    type(field('Cloud cover, to'), '20');
    tick('Satellite A');
    switchTo(1);
    type(field('Relative orbit, from'), '22');
    switchTo(0);

    act(() => reset()!.click());

    expect(useAppStore.getState().searchFilters).toEqual({
      radar: { 'test:track': { kind: 'range', from: '22', to: '' } },
    });
    expect(field('Cloud cover, to').value).toBe('');
    expect(reset()).toBeUndefined();
    expect(text(button())).toBe('Advanced search · 1');
    expect([...container.querySelectorAll('.advanced-actions button')].map((b) => text(b))).toEqual(['Done']);
  });
});

describe('the search settings', () => {
  it('stay when the results are cleared', () => {
    pick('optical');
    open();
    type(field('Cloud cover, to'), '20');
    act(() => useAppStore.getState().clearSearchResults());
    expect(field('Cloud cover, to').value).toBe('20');
    expect(text(button())).toBe('Advanced search · 1');
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
    switchTo(1);
    type(field('Relative orbit, from'), '22');
    type(field('Relative orbit, to'), '22');
    act(() => [...container.querySelectorAll<HTMLButtonElement>('.advanced-actions button')].find((b) => text(b) === 'Done')!.click());

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
