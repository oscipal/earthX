// @vitest-environment jsdom
//
// M3-10: the results list is one collapsible section per dataset — title and
// scene count in the head, the section's notes under it even while folded, the
// time-step groups inside while open.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

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

function heads(): HTMLButtonElement[] {
  return [...container.querySelectorAll('.result-section-head')] as HTMLButtonElement[];
}
function headText(head: HTMLElement): string {
  return head.textContent ?? '';
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

describe('ResultsPanel sections', () => {
  it('shows one head per dataset with its title and scene count, and the total', () => {
    load(MIXED);
    expect(heads().map((h) => headText(h))).toEqual([
      '▾Optical imagerystaging2',
      '▸Optical (Zarr)0',
      '▸Elevation model1',
    ]);
    expect(container.querySelector('.results-head')?.textContent).toContain('3');
    expect(container.querySelector('h2')?.textContent).toBe('Results');
  });

  it('has the first section with scenes open, and shows its time steps only', () => {
    load(MIXED);
    expect(heads()[0].getAttribute('aria-expanded')).toBe('true');
    expect(heads()[2].getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelectorAll('.result-group')).toHaveLength(2);
  });

  it('opening another section closes the first: one open at a time', () => {
    load(MIXED);
    act(() => heads()[2].click());
    expect(heads()[0].getAttribute('aria-expanded')).toBe('false');
    expect(heads()[2].getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelectorAll('.result-group')).toHaveLength(1);
    expect(useAppStore.getState().datasetId).toBe('dem');
  });

  it('clicking the open head closes it, and the panel stays', () => {
    load(MIXED);
    act(() => heads()[0].click());
    expect(container.querySelectorAll('.result-group')).toHaveLength(0);
    expect(heads()).toHaveLength(3);
    expect(useAppStore.getState().openSectionId).toBeNull();
  });

  it('shows a section\'s notes under its head even while the section is folded', () => {
    load(MIXED, {
      ignoredFilters: ['datetime'],
      ignoredFiltersByCollection: { dem: ['datetime'] },
      incompleteCollections: [{ collection: 'zarr', reason: 'unreachable' }],
    });
    const notes = [...container.querySelectorAll('.result-section')].map((s) =>
      [...s.querySelectorAll('.result-section-note')].map((n) => n.textContent),
    );
    expect(notes).toEqual([
      [],
      ['Results incomplete: the source was not reachable.'],
      ['No time axis – acquired Dec 2010 to Jan 2015'],
    ]);
    expect(heads()[2].getAttribute('aria-expanded')).toBe('false');
  });

  it('keeps time-step grouping inside a section', () => {
    load(MIXED);
    const labels = [...container.querySelectorAll('.result-section.open .rg-label')].map((l) => l.textContent);
    expect(labels).toEqual(['2026-07-25', '2026-07-24']);
  });

  it('shows the panel with several datasets even when none has scenes, so the sections can say why', () => {
    load([]);
    expect(heads()).toHaveLength(3);
    expect(container.querySelectorAll('.result-section-note')).toHaveLength(3);
  });

  it('shows nothing for a single dataset with nothing found (the search notice speaks)', () => {
    const datasets = datasetsFrom(COLLECTIONS);
    const single = datasets.filter((d) => d.id === 'optical') as Extract<(typeof datasets)[number], { viewable: true }>[];
    const { sections } = buildSections([], single, { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    useAppStore.setState({ datasets, sections, openSectionId: null, items: [], groups: [] });
    act(() => root.render(<ResultsPanel />));
    expect(container.querySelector('.results-panel')).toBeNull();
  });

  it('renders nothing before any search', () => {
    useAppStore.setState({ sections: [], openSectionId: null, items: [], groups: [] });
    act(() => root.render(<ResultsPanel />));
    expect(container.querySelector('.results-panel')).toBeNull();
  });

  it('"Clear all" empties the list', () => {
    load(MIXED);
    act(() => (container.querySelector('.link-btn') as HTMLButtonElement).click());
    expect(useAppStore.getState().sections).toEqual([]);
  });
});
