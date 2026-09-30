// @vitest-environment jsdom
//
// M3-10 (Otto, 30.09.2026): the results list has a box with a dropdown at the top
// to choose the dataset whose scenes are shown — the choice is the active
// dataset. Title, scene count and the dataset's notes are in the box and in the
// dropdown; the time-step groups below stay grouped per overpass. The panel does
// not disappear by choosing.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { buildSections } from '../sections';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ResultsPanel from './ResultsPanel';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

function collection(id: string, title: string, extra: Partial<Collection> = {}): Collection {
  return {
    id,
    title,
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': {
      group_by: ['datetime'],
      min_zoom: 0,
      max_zoom: 14,
      browse: 'quicklook',
      quicklook_nodata_max: null,
      results_group_by: ['datetime'],
    },
    ...extra,
  };
}

const COLLECTIONS = [
  collection('optical', 'Optical imagery', { 'earthx:maturity': 'staging' }),
  collection('zarr', 'Optical (Zarr)'),
  collection('dem', 'Elevation model', {
    extent: { temporal: { interval: [['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']] } },
    'earthx:capabilities': { ...CAPABILITIES, time_range: false },
    'earthx:viewer': {
      group_by: ['start_datetime'],
      min_zoom: 0,
      max_zoom: 14,
      browse: 'full_resolution',
      quicklook_nodata_max: null,
      results_group_by: ['start_datetime'],
    },
  }),
];

function scene(id: string, collectionId: string, properties: Record<string, unknown>): StacItem {
  return { id, collection: collectionId, bbox: [0, 0, 1, 1], properties, assets: {} };
}

let container: HTMLDivElement;
let root: Root;

function load(features: StacItem[], answer = { ignoredFilters: [] as string[], ignoredFiltersByCollection: {}, incompleteCollections: [] as { collection: string; reason: string }[] }) {
  const datasets = datasetsFrom(COLLECTIONS);
  const chosen = datasets.filter((d): d is Extract<typeof d, { viewable: true }> => d.viewable);
  const { sections } = buildSections(features, chosen, answer);
  const open = sections.find((s) => s.items.length > 0) ?? null;
  useAppStore.setState({
    datasets,
    sections,
    openSectionId: open?.datasetId ?? null,
    datasetId: open?.datasetId ?? 'optical',
    items: open?.items ?? [],
    groups: open?.groups ?? [],
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: [],
  });
  act(() => root.render(<ResultsPanel />));
}

function box(): HTMLButtonElement {
  return container.querySelector('.dataset-select-box') as HTMLButtonElement;
}
function options(): HTMLButtonElement[] {
  return [...container.querySelectorAll('.dataset-select-option')] as HTMLButtonElement[];
}
function openList(): void {
  act(() => box().click());
}
function text(el: Element | null): string {
  return el?.textContent ?? '';
}

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

const MIXED = [
  scene('o1', 'optical', { datetime: '2026-07-24T10:00:00Z' }),
  scene('o2', 'optical', { datetime: '2026-07-25T10:00:00Z' }),
  scene('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' }),
];

describe('ResultsPanel dataset dropdown', () => {
  it('sets the dropdown apart as a selector card of its own, labelled, above the scenes', () => {
    load(MIXED);
    const card = container.querySelector('.dataset-select')!;
    expect(card.querySelector('.eyebrow')?.textContent).toBe('Showing dataset');
    expect(box().getAttribute('aria-labelledby')).toBe('dataset-select-label');
    const eyebrows = [...container.querySelectorAll('.eyebrow')].map((e) => e.textContent);
    expect(eyebrows).toEqual(['Showing dataset', 'Scenes by time step']);
    // the card comes before the list of scenes in the panel
    const panel = container.querySelector('.results-panel')!;
    expect(card.compareDocumentPosition(panel.querySelector('.results-list')!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('shows the dataset chosen in the box with its title, chip and scene count, and the total', () => {
    load(MIXED);
    expect(text(box())).toContain('Optical imagery');
    expect(text(box())).toContain('staging');
    expect(text(box().querySelector('.rg-count'))).toBe('2');
    expect(text(container.querySelector('.results-head'))).toContain('3');
    expect(container.querySelector('h2')?.textContent).toBe('Results');
  });

  it('starts on the first dataset with scenes and shows its time steps', () => {
    load(MIXED);
    expect(container.querySelectorAll('.result-group')).toHaveLength(2);
    expect(useAppStore.getState().openSectionId).toBe('optical');
  });

  it('keeps the list closed until the box is clicked, then lists every searched dataset with its count', () => {
    load(MIXED);
    expect(options()).toHaveLength(0);
    openList();
    expect(options().map((o) => text(o.querySelector('.dataset-select-title')))).toEqual([
      'Optical imagery',
      'Optical (Zarr)',
      'Elevation model',
    ]);
    expect(options().map((o) => text(o.querySelector('.rg-count')))).toEqual(['2', '0', '1']);
    expect(options().map((o) => o.getAttribute('aria-selected'))).toEqual(['true', 'false', 'false']);
  });

  it('choosing a dataset shows its scenes, makes it the active dataset and closes the list', () => {
    load(MIXED);
    openList();
    act(() => options()[2].click());
    expect(useAppStore.getState().datasetId).toBe('dem');
    expect(useAppStore.getState().openSectionId).toBe('dem');
    expect(text(box())).toContain('Elevation model');
    expect(container.querySelectorAll('.result-group')).toHaveLength(1);
    expect(options()).toHaveLength(0);
  });

  it('the panel stays whatever is chosen — also a dataset without scenes', () => {
    load(MIXED);
    openList();
    act(() => options()[1].click());
    expect(container.querySelector('.results-panel')).not.toBeNull();
    expect(container.querySelectorAll('.result-group')).toHaveLength(0);
    expect(text(box())).toContain('Optical (Zarr)');
    expect(text(box())).toContain('No scenes for this area.');
    // and back again
    openList();
    act(() => options()[0].click());
    expect(container.querySelectorAll('.result-group')).toHaveLength(2);
  });

  it('clicking the box again closes the list without changing the choice', () => {
    load(MIXED);
    openList();
    act(() => box().click());
    expect(options()).toHaveLength(0);
    expect(useAppStore.getState().openSectionId).toBe('optical');
  });

  it('Escape and a click outside close the list', () => {
    load(MIXED);
    openList();
    act(() => {
      document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
    });
    expect(options()).toHaveLength(0);
    openList();
    act(() => {
      document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    });
    expect(options()).toHaveLength(0);
  });

  it("shows a dataset's notes in the box and in its option of the dropdown", () => {
    load(MIXED, {
      ignoredFilters: ['datetime'],
      ignoredFiltersByCollection: { dem: ['datetime'] },
      incompleteCollections: [{ collection: 'zarr', reason: 'unreachable' }],
    });
    // the box shows the chosen dataset's notes (none for the optical one) …
    expect(box().querySelectorAll('.dataset-select-note')).toHaveLength(0);
    openList();
    const notes = options().map((o) => [...o.querySelectorAll('.dataset-select-note')].map((n) => n.textContent));
    expect(notes).toEqual([
      [],
      ['Results incomplete: the source was not reachable.'],
      ['No time axis – acquired Dec 2010 to Jan 2015'],
    ]);
    // … and choosing the DEM brings its note into the box
    act(() => options()[2].click());
    expect(text(box())).toContain('No time axis – acquired Dec 2010 to Jan 2015');
  });

  it('keeps time-step grouping inside the list', () => {
    load(MIXED);
    const labels = [...container.querySelectorAll('.result-group .rg-label')].map((l) => l.textContent);
    expect(labels).toEqual(['2026-07-25', '2026-07-24']);
  });

  it('shows the panel with several datasets even when none has scenes, so the box can say why', () => {
    load([]);
    expect(container.querySelector('.results-panel')).not.toBeNull();
    expect(text(box())).toContain('No scenes for this area.');
  });

  it('for a single dataset shows the box, without a dropdown to open', () => {
    const datasets = datasetsFrom(COLLECTIONS);
    const single = datasets.filter((d) => d.id === 'optical') as Extract<(typeof datasets)[number], { viewable: true }>[];
    const { sections } = buildSections(MIXED.slice(0, 2), single, { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    useAppStore.setState({
      datasets,
      sections,
      openSectionId: 'optical',
      datasetId: 'optical',
      items: sections[0].items,
      groups: sections[0].groups,
    });
    act(() => root.render(<ResultsPanel />));
    expect(box().disabled).toBe(true);
    expect(box().querySelector('.rg-caret')).toBeNull();
  });

  it('shows nothing for a single dataset with nothing found (the search notice speaks)', () => {
    const datasets = datasetsFrom(COLLECTIONS);
    const single = datasets.filter((d) => d.id === 'optical') as Extract<(typeof datasets)[number], { viewable: true }>[];
    const { sections } = buildSections([], single, { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    useAppStore.setState({ datasets, sections, openSectionId: 'optical', items: [], groups: [] });
    act(() => root.render(<ResultsPanel />));
    expect(container.querySelector('.results-panel')).toBeNull();
  });

  it('renders nothing before any search', () => {
    useAppStore.setState({ sections: [], openSectionId: null, items: [], groups: [] });
    act(() => root.render(<ResultsPanel />));
    expect(container.querySelector('.results-panel')).toBeNull();
  });

  it('offers to pin the crop of a dataset drawn as one, only while that dataset is chosen', () => {
    load(MIXED);
    expect(container.querySelector('.crop-row')).toBeNull();
    const crop = { id: 'c', name: 'Elevation model · x', visible: true, opacity: 1, overlays: [], restore: { datasetId: 'dem' } } as never;
    useAppStore.setState({ searchCrops: [crop] });
    act(() => root.render(<ResultsPanel />));
    expect(container.querySelector('.crop-row')).toBeNull(); // optical is chosen
    openList();
    act(() => options()[2].click());
    expect(container.querySelector('.crop-row')?.textContent).toContain('Full-resolution crop is on the map.');
    act(() => (container.querySelector('.crop-row .link-btn') as HTMLButtonElement).click());
    expect(useAppStore.getState().layers).toHaveLength(1);
    useAppStore.setState({ searchCrops: [], layers: [] });
  });

  it('"Clear all" empties the list', () => {
    load(MIXED);
    act(() => (container.querySelector('.link-btn') as HTMLButtonElement).click());
    expect(useAppStore.getState().sections).toEqual([]);
  });
});

describe('ResultsPanel "Load more" and the fallback (M3-10b)', () => {
  type Context = NonNullable<ReturnType<typeof useAppStore.getState>['searchContext']>;
  const withToken = (nextToken: string | null) => ({ searchContext: { nextToken } as Context });
  const loadMoreRow = () => container.querySelector('.load-more');
  const loadMoreButton = () => loadMoreRow()?.querySelector('button') as HTMLButtonElement | null;
  const original = useAppStore.getState().loadMore;

  beforeEach(() => useAppStore.setState({ searchContext: null, loadingMore: false, loadMoreError: null, fallbackDatasetId: null }));
  afterEach(() => useAppStore.setState({ loadMore: original }));

  it('offers "Load more" below the scenes while the search has a token left, naming no dataset', () => {
    const loadMore = vi.fn(async () => {});
    useAppStore.setState({ ...withToken('p4'), loadMore });
    load(MIXED);
    expect(text(loadMoreRow())).toContain('More scenes may be available.');
    expect(text(loadMoreRow())).not.toContain('Optical');
    const list = container.querySelector('.results-list')!;
    expect(list.compareDocumentPosition(loadMoreRow()!) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    act(() => loadMoreButton()!.click());
    expect(loadMore).toHaveBeenCalledTimes(1);
  });

  it('stays below whichever dataset is chosen', () => {
    useAppStore.setState(withToken('p4'));
    load(MIXED);
    openList();
    act(() => options()[2].click());
    expect(useAppStore.getState().openSectionId).toBe('dem');
    expect(loadMoreButton()).not.toBeNull();
  });

  it('is locked while loading', () => {
    useAppStore.setState({ ...withToken('p4'), loadingMore: true });
    load(MIXED);
    expect(loadMoreButton()!.disabled).toBe(true);
    expect(text(loadMoreButton())).toBe('Loading…');
  });

  it('is not there without a token; after a failure it says to search again instead', () => {
    load(MIXED);
    expect(loadMoreRow()).toBeNull();
    act(() => useAppStore.setState({ loadMoreError: 'Could not load more results — search again.' }));
    expect(text(loadMoreRow())).toBe('Could not load more results — search again.');
    expect(loadMoreButton()).toBeNull();
  });

  it('says in the box that the nearest date is being looked for, in place of the notes', () => {
    load([scene('d1', 'dem', { start_datetime: '2011-01-01T00:00:00Z' })]);
    openList();
    act(() => options()[0].click());
    act(() => useAppStore.setState({ fallbackDatasetId: 'optical' }));
    expect(text(box())).toContain('Looking for the nearest date with scenes…');
    expect(text(box())).not.toContain('No scenes for this area.');
  });
});
