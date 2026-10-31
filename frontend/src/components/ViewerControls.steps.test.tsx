// @vitest-environment jsdom
//
// NM4-53: the steps in the head of the view of scenes (Otto, 31.10.2026, zu #257), between the title and the eye — the
// dataset to choose, the arrows to step through its images with the date and the satellite of the image that is shown;
// what is not possible is not there.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { useAppStore } from '../store';
import type { Collection, DownloadedInfo, StacItem, TimeStepGroup } from '../types';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

// The ranges of the standard visualisation of Sentinel-2 here: one (a band) or three (RGB).
let s2Rescale: number[][] = [[0, 255]];

const base = (id: string, title: string): Collection =>
  ({
    id,
    title,
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: id === 's2', band_math: true, interpolation: true },
    'earthx:default_render': { title: 'Standard', assets: ['visual'], rescale: id === 's2' ? s2Rescale : [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:search_filters':
      id === 's2'
        ? [{ property: 'platform', kind: 'values', title: 'Satellite', group: 'Acquisition', description: 'The satellite.', oneOf: [{ const: 'sentinel-2a', title: 'Sentinel-2A' }, { const: 'sentinel-2b', title: 'Sentinel-2B' }] }]
        : [],
  }) as unknown as Collection;

const scene = (id: string, collection: string, datetime: string | null, platform?: string): StacItem => ({
  id,
  collection,
  bbox: [0, 0, 1, 1],
  properties: { ...(datetime ? { datetime } : {}), ...(platform ? { platform } : {}) },
  assets: {},
});
const info = (datasetId: string): DownloadedInfo => ({ datasetId, tileUrl: '/t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 0, maxZoom: 14 });
const group = (label: string, items: StacItem[]): TimeStepGroup => ({ key: [label], label, items });

const A = scene('A', 's2', '2025-07-29T10:00:00Z', 'sentinel-2a');
const B = scene('B', 's2', '2025-08-03T10:00:00Z', 'sentinel-2b');
const C = scene('C', 's2', '2025-08-08T10:00:00Z', 'sentinel-2a');
const D = scene('D', 'dem', null);
const section = (datasetId: string, items: StacItem[], groups: TimeStepGroup[]) => ({
  datasetId, items, groups, notes: [], groupingError: null, origin: 'search' as const, incomplete: false,
});
const S2_SECTION = section('s2', [A, B, C], [group('2025-08-08', [C]), group('2025-08-03', [B]), group('2025-07-29', [A])]);
const DEM_SECTION = section('dem', [D], [group('dem', [D])]);

let container: HTMLDivElement;
let root: Root;

function mount(downloaded: Record<string, DownloadedInfo>, sections = [S2_SECTION, DEM_SECTION], shownImage: string | null = null) {
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([base('s2', 'Sentinel-2 L2A'), base('dem', 'Copernicus DEM')]),
      sections,
      openSectionId: 's2',
      datasetId: 's2',
      items: sections[0].items,
      groups: sections[0].groups,
      focusMode: true,
      cropToAoi: true,
      downloaded,
      shownImage,
      layers: [],
      resultsAt: 0,
      viewLooks: {},
      savedLooks: {},
      appliedRender: { rescale: '0,255' },
      showDownloaded: true,
      pendingColormapName: '',
      pendingVmin: '0',
      pendingVmax: '255',
      focusLoading: false,
      pinLoading: false,
      selectedIds: [],
      dock: null,
      resultsOnMap: true,
    });
    root.render(<ViewerControls />);
  });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  s2Rescale = [[0, 255]];
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const steps = () => container.querySelector('.vc-head .vc-stepper');
const stepText = () => container.querySelector('.vc-step-text')?.textContent;
const prev = () => container.querySelector('button[aria-label="Previous image"]') as HTMLButtonElement | null;
const next = () => container.querySelector('button[aria-label="Next image"]') as HTMLButtonElement | null;
const dataset = () => container.querySelector('select[aria-label="Dataset"]') as HTMLSelectElement | null;
const title = () => container.querySelector('.vc-title')?.textContent;

const THREE = { A: info('s2'), B: info('s2'), C: info('s2') };

describe('what is not possible is not there', () => {
  it('has neither the dataset nor the arrows for a view of one image, and no row of its own', () => {
    mount({ A: info('s2') });
    expect(steps()).toBeNull();
    expect(dataset()).toBeNull();
    expect(container.querySelector('.vc-steps')).toBeNull();
  });

  it('has neither for several scenes of one time step', () => {
    mount({ A: info('s2'), B: info('s2') }, [section('s2', [A, B], [group('same', [A, B])]), DEM_SECTION]);
    expect(steps()).toBeNull();
    expect(dataset()).toBeNull();
  });

  it('puts them in the head, the dataset and then the date with the arrows, between the title and the eye', () => {
    mount({ ...THREE, D: info('dem') });
    const head = [...container.querySelector('.vc-head')!.children].map((el) => el.className);
    expect(head).toEqual(['vc-title', 'vc-dataset', 'vc-stepper', 'vc-eye']);
    expect(container.querySelectorAll('.vc-head .vc-dataset, .vc-head .vc-stepper')).toHaveLength(2);
  });

  it('has the arrows but no dataset to choose where the view holds one dataset', () => {
    mount(THREE);
    expect(steps()).not.toBeNull();
    expect(dataset()).toBeNull();
    expect(prev()).not.toBeNull();
    expect(next()).not.toBeNull();
  });

  it('has the dataset to choose but no date and no arrows where each dataset has one image', () => {
    mount({ A: info('s2'), D: info('dem') });
    expect(dataset()).not.toBeNull();
    expect(prev()).toBeNull();
    expect(next()).toBeNull();
    expect(stepText()).toBeUndefined();
  });

  it('has the arrows of a dataset with several images and none for one with a single image', () => {
    mount({ ...THREE, D: info('dem') });
    expect(next()).not.toBeNull();
    act(() => useAppStore.getState().chooseViewDataset('dem'));
    expect(prev()).toBeNull();
    expect(next()).toBeNull();
    expect(stepText()).toBeUndefined();
  });
});

describe('the arrows', () => {
  it('say the date and the satellite of the image shown, earliest first', () => {
    mount(THREE);
    expect(stepText()).toBe('2025-07-29 · S2A');
  });

  it('step to the next and the previous image', () => {
    mount(THREE);
    act(() => next()!.click());
    expect(stepText()).toBe('2025-08-03 · S2B');
    expect(title()).not.toContain('2025-08-03');
    act(() => next()!.click());
    expect(stepText()).toBe('2025-08-08 · S2A');
    act(() => prev()!.click());
    expect(stepText()).toBe('2025-08-03 · S2B');
  });

  it('are greyed out with the reason at the ends, and do nothing there', () => {
    mount(THREE);
    expect(prev()!.getAttribute('aria-disabled')).toBe('true');
    expect(prev()!.title).toBe('This is the first image');
    act(() => prev()!.click());
    expect(stepText()).toBe('2025-07-29 · S2A');
    act(() => useAppStore.getState().showImage(useAppStore.getState().shownImage ?? ''));
    act(() => next()!.click());
    act(() => next()!.click());
    expect(next()!.getAttribute('aria-disabled')).toBe('true');
    expect(next()!.title).toBe('This is the last image');
    act(() => next()!.click());
    expect(stepText()).toBe('2025-08-08 · S2A');
  });

  it('tell the step and the group in the tooltip of the date', () => {
    mount(THREE);
    expect(container.querySelector('.vc-step-text')?.getAttribute('title')).toBe('2025-07-29 · S2A · step 1 of 3 · 2025-07-29');
  });

  it('are reached with the keys when one of them has the focus, and not otherwise', () => {
    mount(THREE);
    act(() => {
      document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    });
    expect(stepText()).toBe('2025-07-29 · S2A');
    act(() => {
      next()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    });
    expect(stepText()).toBe('2025-08-03 · S2B');
    act(() => {
      next()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true }));
    });
    expect(stepText()).toBe('2025-07-29 · S2A');
    act(() => {
      next()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'a', bubbles: true }));
    });
    expect(stepText()).toBe('2025-07-29 · S2A');
  });

  it('leave "Hide image" as it is', () => {
    mount(THREE);
    act(() => useAppStore.setState({ showDownloaded: false }));
    act(() => next()!.click());
    expect(useAppStore.getState().showDownloaded).toBe(false);
    expect(container.querySelector('.vc-eye.off')).not.toBeNull();
  });
});

describe('the dataset', () => {
  it('lists the datasets of the view in the order of the results, with the one shown selected', () => {
    mount({ ...THREE, D: info('dem') });
    expect([...dataset()!.options].map((o) => o.textContent)).toEqual(['Sentinel-2 L2A', 'Copernicus DEM']);
    expect(dataset()!.value).toBe('s2');
  });

  it('shows the first image of the dataset that is chosen, and the head follows', () => {
    mount({ ...THREE, D: info('dem') });
    act(() => {
      dataset()!.value = 'dem';
      dataset()!.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(useAppStore.getState().shownImage).toContain('dem');
    expect(title()).toBe('Copernicus DEM · AOI crop');
  });
});

describe('a satellite the registry does not name', () => {
  it('is shown as the source gives it, and no satellite leaves no separator', () => {
    const X = scene('X', 's2', '2025-09-01T10:00:00Z', 'landsat-9');
    const Y = scene('Y', 's2', '2025-09-05T10:00:00Z');
    mount({ X: info('s2'), Y: info('s2') }, [section('s2', [X, Y], [group('2025-09-05', [Y]), group('2025-09-01', [X])]), DEM_SECTION]);
    expect(stepText()).toBe('2025-09-01 · landsat-9');
    act(() => next()!.click());
    expect(stepText()).toBe('2025-09-05');
  });
});

const button = (label: string) => [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const colormapField = () => [...container.querySelectorAll('.vc-field span')].find((el) => el.textContent === 'Colormap');
const type = (vmin: string, vmax: string) => act(() => useAppStore.setState({ pendingVmin: vmin, pendingVmax: vmax }));

describe('"Apply to all" for the images of a dataset', () => {
  it('is always there, also for a dataset of one image and for the elevation model, locked with the reason', () => {
    mount({ A: info('s2'), D: info('dem') });
    expect(button('Apply to all')!.getAttribute('aria-disabled')).toBe('true');
    expect(button('Apply to all')!.title).toBe('Nothing to apply to all: this dataset has only one image in the view');
    expect(button('Save')).toBeUndefined();
    act(() => useAppStore.getState().chooseViewDataset('dem'));
    expect(button('Apply to all')!.getAttribute('aria-disabled')).toBe('true');
    expect(button('Apply to all')!.title).toBe('Nothing to apply to all: this dataset has only one image in the view');
  });

  it('is there where it has several, locked with the reason while all look alike', () => {
    mount(THREE);
    type('0', '255');
    expect(button('Apply to all')!.getAttribute('aria-disabled')).toBe('true');
    expect(button('Apply to all')!.title).toBe('Nothing to apply to all: every image of this dataset is drawn like this');
    act(() => button('Apply to all')!.click());
    expect(useAppStore.getState().savedLooks).toEqual({});
  });

  it('opens when the fields differ from what another image shows, and saves for the dataset', () => {
    mount(THREE);
    type('10', '90');
    expect(button('Apply to all')!.getAttribute('aria-disabled')).toBeNull();
    expect(button('Apply to all')!.title).toBe('Draw every image of this dataset with these values');
    act(() => button('Apply to all')!.click());
    expect(useAppStore.getState().savedLooks.s2).toMatchObject({ rescale: '10,90' });
    expect(button('Apply to all')!.getAttribute('aria-disabled')).toBe('true');
  });

  it('applies to the image shown only: "Apply" opens with a change, and the next image does not take it', () => {
    mount(THREE);
    type('10', '90');
    expect(button('Apply')!.getAttribute('aria-disabled')).toBeNull();
    act(() => button('Apply')!.click());
    expect(button('Apply')!.getAttribute('aria-disabled')).toBe('true');
    act(() => next()!.click());
    expect(useAppStore.getState().appliedRender.rescale).toBe('0,255');
    expect(container.querySelectorAll('.vc-num input')[0]).toHaveProperty('value', '0');
  });
});

describe('an image of three bands', () => {
  it('has no colormap field, and the range fields and buttons are still there and not locked', () => {
    s2Rescale = [[0, 255], [0, 255], [0, 255]];
    mount(THREE);
    expect(colormapField()).toBeUndefined();
    expect(container.querySelector('.vc-render')!.className).toContain('no-colormap');
    expect(container.querySelectorAll('.vc-num input')).toHaveLength(2);
    expect(button('Apply')).toBeDefined();
  });

  it('has the colormap field for a single band, and for the dataset after the one of three bands', () => {
    mount(THREE);
    expect(colormapField()).toBeDefined();
    s2Rescale = [[0, 255], [0, 255], [0, 255]];
    mount({ ...THREE, D: info('dem') });
    expect(colormapField()).toBeUndefined();
    act(() => useAppStore.getState().chooseViewDataset('dem'));
    expect(colormapField()).toBeDefined();
  });
});

describe('"Add to layers" and "Add all to layers"', () => {
  it('has "Add all to layers" only where the view holds more than one image', () => {
    mount({ A: info('s2') });
    expect(button('＋ Add all to layers')).toBeUndefined();
    expect(container.querySelector('.vc-actions')!.className).not.toContain('has-all');
    mount(THREE);
    expect(button('＋ Add all to layers')).toBeDefined();
    expect(container.querySelector('.vc-actions')!.className).toContain('has-all');
  });

  it('pins the image shown with "Add to layers" and every image of every dataset with "Add all to layers"', () => {
    mount({ ...THREE, D: info('dem') });
    act(() => button('＋ Add to layers')!.click());
    expect(useAppStore.getState().layers.map((l) => l.restore.itemIds)).toEqual([['A']]);
    act(() => useAppStore.setState({ layers: [] }));
    act(() => button('＋ Add all to layers')!.click());
    const { layers } = useAppStore.getState();
    expect(layers.map((l) => l.restore.itemIds)).toEqual([['D'], ['C'], ['B'], ['A']]);
    expect(layers.map((l) => l.restore.datasetId)).toEqual(['dem', 's2', 's2', 's2']);
  });

  it('names the layers after dataset, time step and satellite', () => {
    mount(THREE);
    act(() => button('＋ Add all to layers')!.click());
    expect(useAppStore.getState().layers.map((l) => l.name)).toEqual([
      'Sentinel-2 L2A · 2025-08-08 · S2A',
      'Sentinel-2 L2A · 2025-08-03 · S2B',
      'Sentinel-2 L2A · 2025-07-29 · S2A',
    ]);
  });

  it('puts every new layer on top of the list', () => {
    mount(THREE);
    act(() => useAppStore.setState({ layers: [], resultsAt: 0 }));
    act(() => button('＋ Add all to layers')!.click());
    expect(useAppStore.getState().resultsAt).toBe(3);
  });
});
