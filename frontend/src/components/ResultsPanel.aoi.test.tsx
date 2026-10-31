// @vitest-environment jsdom
//
// DS-03b: what the results list says of a search that checked the clouds inside the AOI: how far it got ("12 found /
// 180 checked") with "Stop" while it goes on, the share in each scene and time step, the order of the time steps by it,
// and the hints (limit, scenes that could not be read). Nothing of it shows for a dataset that was searched without.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import CSS from '../index.css?raw';
import { AOI_CLOUD_PROPERTY, type AoiCounts } from '../aoiFilter';
import { datasetsFrom } from '../datasets';
import { ELEVATION, OPTICAL } from '../fixtures/searchFilters';
import { buildSections } from '../sections';
import { useAppStore } from '../store';
import type { StacItem } from '../types';
import ResultsPanel from './ResultsPanel';
import StatusBar from './StatusBar';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const scene = (id: string, day: string, cloud?: { percent: number; cloudPixels: number; dataPixels: number; dataPercent?: number }): StacItem => ({
  id,
  collection: 'optical',
  bbox: [0, 0, 1, 1],
  properties: {
    datetime: `${day}T10:00:00Z`,
    ...(cloud
      ? {
          [AOI_CLOUD_PROPERTY]: cloud.percent,
          'earthx:aoi_measure': {
            data_percent: cloud.dataPercent ?? 100,
            cloud_pixels: cloud.cloudPixels,
            data_pixels: cloud.dataPixels,
            resolution: 80,
          },
        }
      : {}),
  },
  assets: {},
});

const counts = (change: Partial<AoiCounts> = {}): AoiCounts => ({ checked: 180, found: 12, unreadable: 0, limitReached: false, ...change });

interface Setup {
  features: StacItem[];
  counts?: AoiCounts;
  walking?: boolean;
  // Whether the search asked for the clouds inside the AOI.
  measured?: boolean;
  nextToken?: string | null;
  // The search was stopped before it found a scene.
  keepList?: boolean;
}

function load({ features, counts: aoiCounts, walking = false, measured = true, nextToken = null, keepList = false }: Setup) {
  const datasets = datasetsFrom([OPTICAL, ELEVATION]);
  const chosen = datasets.filter((d): d is Extract<typeof d, { viewable: true }> => d.viewable && d.id === 'optical');
  const answer = {
    ignoredFilters: [] as string[],
    ignoredFiltersByCollection: {},
    incompleteCollections: [],
    ...(aoiCounts ? { aoiFilter: { optical: aoiCounts } } : {}),
  };
  const built = buildSections(features, chosen, answer).sections;
  const sections = keepList ? built.map((section) => ({ ...section, keepList: true })) : built;
  useAppStore.setState({
    datasets,
    sections,
    openSectionId: 'optical',
    datasetId: 'optical',
    items: sections[0].items,
    groups: sections[0].groups,
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: [],
    aoiWalking: walking,
    resultSort: 'date',
    searching: false,
    searchContext: {
      datasetIds: ['optical'],
      query: { collections: ['optical'], ...(measured ? { queryByCollection: { optical: { [AOI_CLOUD_PROPERTY]: { lte: 20 } } } } : {}) },
      dateFrom: '2026-07-01',
      dateTo: '2026-07-31',
      aoi: { type: 'Polygon', coordinates: [] },
      truncatedNotice: null,
      features,
      answer,
      numberMatched: null,
      nextToken,
      openCollections: nextToken ? ['optical'] : [],
    },
  });
  act(() => root.render(<ResultsPanel />));
}

const text = (el: Element | null) => el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
const progress = () => container.querySelector('.aoi-progress');
const stopButton = () => [...container.querySelectorAll<HTMLButtonElement>('button')].find((b) => text(b) === 'Stop');
const groupLabels = () => [...container.querySelectorAll('.rg-label')].map(text);
const groupClouds = () => [...container.querySelectorAll('.result-group-head .cloud-value')].map(text);
const sortButtons = () => [...container.querySelectorAll<HTMLButtonElement>('.aoi-sort button')];

// Three overpasses, newest first by date: July 3 with 40 %, July 2 with 2 % and July 1 with none measured.
const THREE = [
  scene('a', '2026-07-03', { percent: 40, cloudPixels: 40, dataPixels: 100 }),
  scene('b', '2026-07-02', { percent: 2, cloudPixels: 2, dataPixels: 100, dataPercent: 64 }),
  scene('c', '2026-07-01'),
];

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  container.className = 'app';
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('how far the search got', () => {
  it('says how many scenes are within the limit of those checked, without "Stop" once it is done', () => {
    load({ features: THREE, counts: counts({ found: 3, checked: 500 }) });
    expect(text(progress())).toBe('3 found / 500 checked');
    expect(stopButton()).toBeUndefined();
  });

  it('has "Stop" beside it while the search goes on, and "Stop" ends the walk', () => {
    let stopped = 0;
    const original = useAppStore.getState().stopSearch;
    useAppStore.setState({ stopSearch: () => (stopped += 1) });
    load({ features: THREE, counts: counts(), walking: true });
    expect(text(progress()!.querySelector('span'))).toBe('12 found / 180 checked');
    act(() => stopButton()!.click());
    useAppStore.setState({ stopSearch: original });
    expect(stopped).toBe(1);
  });

  it('counts from zero before the first answer', () => {
    load({ features: THREE, walking: true });
    expect(text(progress()!.querySelector('span'))).toBe('0 found / 0 checked');
    expect(stopButton()).toBeDefined();
  });

  it('explains itself in a tooltip', () => {
    load({ features: THREE, counts: counts() });
    expect(progress()!.querySelector('span')!.title).toBe('Scenes within the limit, of the scenes checked so far');
  });

  it('is not there for a search without the limit', () => {
    load({ features: THREE.map((s) => scene(s.id, String(s.properties.datetime).slice(0, 10))), measured: false });
    expect(progress()).toBeNull();
    expect(container.querySelector('.aoi-sort')).toBeNull();
    expect(container.querySelector('.cloud-value')).toBeNull();
  });

  it('keeps "Load more" away while the search goes on by itself, and offers it once stopped', () => {
    load({ features: THREE, counts: counts(), walking: true, nextToken: 't2' });
    expect(container.querySelector('.load-more')).toBeNull();
    load({ features: THREE, counts: counts(), walking: false, nextToken: 't2' });
    expect(text(container.querySelector('.load-more'))).toContain('Load more');
  });
});

describe('a search stopped before it found a scene (Otto, 31.10.2026)', () => {
  it('shows the list with "0 found / m checked" and "Load more", and no "Stop"', () => {
    load({ features: [], counts: counts({ found: 0, checked: 100 }), nextToken: 't2', keepList: true });
    expect(container.querySelector('.results-panel')).not.toBeNull();
    expect(text(progress()!.querySelector('span'))).toBe('0 found / 100 checked');
    expect(stopButton()).toBeUndefined();
    expect(text(container.querySelector('.load-more'))).toContain('Load more');
  });

  it('is no list without that, for a search that found nothing and is done', () => {
    load({ features: [], counts: counts({ found: 0, checked: 100 }) });
    expect(container.querySelector('.results-panel')).toBeNull();
  });
});

describe('the hints in the head of the dataset', () => {
  it('says how many scenes it checked when the limit is reached, and that "Load more" is gone', () => {
    load({ features: THREE, counts: counts({ checked: 500, limitReached: true }) });
    act(() => (container.querySelector('.dataset-select-box') as HTMLButtonElement).click());
    expect(text(container)).toContain('Checked 500 scenes. Narrow the date range to search further.');
    expect(container.querySelector('.load-more button')).toBeNull();
  });

  it('says how many scenes could not be read', () => {
    load({ features: THREE, counts: counts({ unreadable: 2 }) });
    expect(text(container.querySelector('.dataset-select-box'))).toContain('2 scenes could not be checked');
  });

  it('says that nothing is within the limit, in place of "no scenes for this area", once the search is done', () => {
    load({ features: [], counts: counts({ found: 0 }) });
    const notes = [...container.querySelectorAll('.dataset-select-note')].map(text);
    expect(notes).toEqual([]);
    expect(text(container)).not.toContain('No scenes for this area.');
  });
});

describe('the share of clouds in a scene and in a time step', () => {
  it('stands beside the time of a scene, in whole percent', () => {
    load({ features: THREE, counts: counts() });
    act(() => (container.querySelector('.result-group-head') as HTMLButtonElement).click());
    act(() => (container.querySelector('.result-group-head') as HTMLButtonElement).click());
    const values = [...container.querySelectorAll('.result-row .cloud-value')].map(text);
    expect(values.length).toBeGreaterThan(0);
    expect(values[0]).toMatch(/^☁︎? ?(40|2|<1) %$/u);
  });

  it('stands in the head of a time step, from the pixels of its scenes', () => {
    load({
      features: [
        scene('a', '2026-07-03', { percent: 100, cloudPixels: 10, dataPixels: 10 }),
        scene('a2', '2026-07-03', { percent: 0, cloudPixels: 0, dataPixels: 990 }),
      ],
      counts: counts(),
    });
    // 10 of 1 000 valid pixels over both scenes of the step: 1 %, not the 50 % of the two shares.
    expect(groupClouds()).toEqual(['☁︎ 1 %']);
  });

  it('is "<1 %" under one percent and has no value for a step without a measure', () => {
    load({
      features: [scene('a', '2026-07-03', { percent: 0.4, cloudPixels: 4, dataPixels: 1000 }), scene('c', '2026-07-01')],
      counts: counts(),
    });
    expect(groupClouds()).toEqual(['☁︎ <1 %']);
  });

  it('explains itself in the words of the registry, and how much of the AOI was measured', () => {
    load({ features: THREE, counts: counts() });
    const head = container.querySelectorAll<HTMLElement>('.result-group-head .cloud-value')[1];
    expect(head.title).toContain("Clouds in AOI: 2 % of the AOI's valid pixels (classes 5, 6; cloud shadows do not count).");
    // The scene says how much of the AOI it was measured on, the step does not.
    act(() => (container.querySelectorAll('.result-group-head')[1] as HTMLButtonElement).click());
    const row = container.querySelector<HTMLElement>('.result-row .cloud-value')!;
    expect(row.title).toContain('Measured on 64 % of the AOI.');
    expect(head.title).not.toContain('Measured on');
  });
});

describe('"Sort: Date | Clouds in AOI"', () => {
  it('is there with the limit, by date at first', () => {
    load({ features: THREE, counts: counts() });
    expect(sortButtons().map(text)).toEqual(['Date', 'Clouds in AOI']);
    expect(sortButtons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['true', 'false']);
    expect(groupLabels()).toEqual(['2026-07-03', '2026-07-02', '2026-07-01']);
  });

  it('puts the time steps in the order of their share, least first and one without a value last, and back by date', () => {
    load({ features: THREE, counts: counts() });
    act(() => sortButtons()[1].click());
    expect(groupLabels()).toEqual(['2026-07-02', '2026-07-03', '2026-07-01']);
    expect(sortButtons().map((b) => b.getAttribute('aria-pressed'))).toEqual(['false', 'true']);
    act(() => sortButtons()[0].click());
    expect(groupLabels()).toEqual(['2026-07-03', '2026-07-02', '2026-07-01']);
  });

  it('opens the same time step whatever the order: the open one is the one of the state, not the first on screen', () => {
    load({ features: THREE, counts: counts() });
    act(() => sortButtons()[1].click());
    const open = container.querySelector('.result-group.active .rg-label');
    expect(text(open)).toBe('2026-07-03');
    expect(useAppStore.getState().expandedGroupIndex).toBe(0);
  });

  it('is not there without the limit, and the order stays by date even if "clouds" was chosen before', () => {
    load({ features: THREE, measured: false });
    useAppStore.setState({ resultSort: 'clouds' });
    act(() => root.render(<ResultsPanel />));
    expect(container.querySelector('.aoi-sort')).toBeNull();
    expect(groupLabels()[0]).toBe('2026-07-03');
  });
});

describe('the progress without a list', () => {
  const status = () => container.querySelector('.toast.busy');

  beforeEach(() => {
    act(() => root.render(<StatusBar />));
  });

  it('stands in the message of the search while there is nothing within the limit to list, with "Stop"', () => {
    useAppStore.setState({
      searching: true,
      aoiWalking: true,
      sections: [],
      searchContext: {
        datasetIds: ['optical'],
        query: { collections: ['optical'] },
        dateFrom: '',
        dateTo: '',
        aoi: { type: 'Polygon', coordinates: [] },
        truncatedNotice: null,
        features: [],
        answer: { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [], aoiFilter: { optical: counts({ found: 0, checked: 200 }) } },
        numberMatched: null,
        nextToken: 't2',
        openCollections: ['optical'],
      },
    });
    act(() => root.render(<StatusBar />));
    expect(text(status())).toContain('Checking scenes · 0 found / 200 checked');
    expect(status()!.querySelector('.aoi-stop')).not.toBeNull();
  });

  it('is the plain message before the first answer, with "Stop" already', () => {
    useAppStore.setState({ searching: true, aoiWalking: true, sections: [], searchContext: null });
    act(() => root.render(<StatusBar />));
    expect(text(status())).toContain('Searching STAC catalog…');
    expect(status()!.querySelector('.aoi-stop')).not.toBeNull();
  });

  it('is the plain message, without "Stop", for any other search', () => {
    useAppStore.setState({ searching: true, aoiWalking: false, sections: [], searchContext: null });
    act(() => root.render(<StatusBar />));
    expect(text(status())).toBe('Searching STAC catalog…');
    expect(status()!.querySelector('.aoi-stop')).toBeNull();
  });
});

describe('the style', () => {
  it('has a place for each part, in the colours of the theme and not in fixed ones', () => {
    for (const selector of ['.aoi-progress', '.aoi-sort', '.cloud-value', '.within-aoi']) {
      expect(CSS).toContain(selector);
    }
    const block = CSS.slice(CSS.indexOf('/* --- "Within AOI" in the results (DS-03b) --- */'));
    expect(block).not.toMatch(/#[0-9a-f]{3,8}\b/iu);
  });
});
