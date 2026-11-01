// @vitest-environment jsdom
//
// Otto, 27.10.2026 (zu #211): the view of scenes has a head of one line, an eye for "Hide image", two rows of buttons
// of one width, and "✕ Clear". The CSS contract is read off `index.css`, as `mapStyles.test.ts` does for the theme.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CSS from '../index.css?raw';
import { datasetsFrom } from '../datasets';
import { useAppStore, type AppState } from '../store';
import type { Collection, DownloadedInfo, StacItem, TimeStepGroup } from '../types';
import { viewDates, viewKind } from '../viewKind';
import { NOTHING_TO_APPLY, NOTHING_TO_APPLY_TO_ALL_LAYER, NOTHING_TO_SAVE_ONE_IMAGE } from '../render';
import ViewerControls from './ViewerControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const collection = (title: string) =>
  ({
    id: 'optical',
    title,
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  }) as unknown as Collection;

const info = (): DownloadedInfo => ({ datasetId: 'optical', tileUrl: '/t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 0, maxZoom: 14 });
const scenes = (n: number) => Object.fromEntries(Array.from({ length: n }, (_, i) => [`s${i}`, info()]));

// Scenes s0, s1, … of the search, one per entry of `days` (a datetime, or undefined for a product without an instant).
const withDays = (days: (string | undefined)[]): TimeStepGroup[] => [
  {
    label: 'all',
    key: ['all'],
    items: days.map((day, i) => ({ id: `s${i}`, collection: 'optical', bbox: [0, 0, 1, 1], properties: day ? { datetime: day } : {}, assets: {} }) as StacItem),
  } as unknown as TimeStepGroup,
];

let container: HTMLDivElement;
let root: Root;

function mount(over: Partial<AppState> = {}, title = 'Sentinel-2 L2A') {
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection(title)]), datasetId: 'optical', focusMode: true, cropToAoi: true, downloaded: scenes(1), showDownloaded: true,
      pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', focusLoading: false, pinLoading: false, groups: [], selectedIds: [], dock: null, resultsOnMap: true, ...over,
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
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const head = () => container.querySelector('.vc-head')!;
const title = () => container.querySelector('.vc-title') as HTMLElement;
const eye = () => container.querySelector('.vc-eye') as HTMLButtonElement;
const row = (name: 'vc-render' | 'vc-actions') => container.querySelector(`.${name}`)!;

describe('the head', () => {
  it.each([
    [true, 1, 'Sentinel-2 L2A · AOI crop'],
    [false, 1, 'Sentinel-2 L2A · whole scene'],
    [true, 3, 'Sentinel-2 L2A · AOI crop · 3 scenes merged'],
    [false, 3, 'Sentinel-2 L2A · 3 scenes merged'],
  ])('is one short line: crop %s, %s scene(s) -> "%s"', (cropToAoi, count, text) => {
    mount({ cropToAoi, downloaded: scenes(count) });
    expect(title().textContent).toBe(text);
  });

  // Otto, 31.10.2026 (zu #257): the date is chosen with the arrows (`ViewerControls.steps.test.tsx`), so the head does not say it.
  it.each([
    [['2025-07-29T23:30:00Z'], 1],
    [['2025-07-29T08:00:00Z', '2025-07-29T20:15:00Z'], 2],
    [['2025-08-03T10:00:00Z', '2025-07-29T10:00:00Z'], 2],
    [[undefined], 1],
  ])('has no date, neither in the line nor in the tooltip: scenes of %j', (days, count) => {
    mount({ downloaded: scenes(count), groups: withDays(days) });
    expect(title().textContent).not.toMatch(/\d{4}-\d{2}-\d{2}/u);
    expect(title().title).not.toMatch(/\d{4}-\d{2}-\d{2}/u);
  });

  it('has no empty separator for a product without an instant, and the scenes merged in the tooltip', () => {
    mount({ groups: withDays([undefined]) });
    expect(title().textContent).toBe('Sentinel-2 L2A · AOI crop');
    mount({ downloaded: scenes(2), groups: withDays(['2025-07-29T10:00:00Z', '2025-08-03T10:00:00Z']) });
    expect(title().title).toBe('Sentinel-2 L2A · cropped to the AOI · 2 scenes merged');
  });

  it('has no "Full-resolution view" and no count of one image', () => {
    mount();
    expect(container.textContent).not.toMatch(/full-resolution view|FULL-RESOLUTION|1 image|image\b.*images?\b/iu);
    expect(head().textContent).not.toMatch(/\bimages?\b/u);
  });

  it('gives the whole text as the tooltip, for the cut-off one', () => {
    mount({ cropToAoi: true, downloaded: scenes(3) }, 'Copernicus DEM GLO-30, global 30 m digital surface model');
    expect(title().title).toBe('Copernicus DEM GLO-30, global 30 m digital surface model · cropped to the AOI · 3 scenes merged');
    expect(title().textContent).toContain('Copernicus DEM GLO-30, global 30 m digital surface model');
  });

  it('gives the dates of the helper in UTC, as a day or a span, and none for bad or missing ones', () => {
    const at = (datetime?: unknown) => ({ properties: datetime === undefined ? {} : { datetime } });
    expect(viewDates([at('2025-07-29T23:59:59Z')])).toBe('2025-07-29');
    expect(viewDates([at('2025-07-30T01:00:00+02:00')])).toBe('2025-07-29');
    expect(viewDates([at('2025-08-03T00:00:00Z'), at('2025-07-29T12:00:00Z'), at('2025-07-31T12:00:00Z')])).toBe('2025-07-29 – 2025-08-03');
    expect(viewDates([at('not a date'), at(42), at()])).toBeNull();
    expect(viewDates([])).toBeNull();
    expect(viewDates([at('2025-07-29T12:00:00Z'), at()])).toBe('2025-07-29');
  });

  it('says only what the kind is, for the helper', () => {
    expect(viewKind(true, 1)).toBe('AOI crop');
    expect(viewKind(false, 0)).toBe('whole scene');
    expect(viewKind(true, 2)).toBe('AOI crop · 2 scenes merged');
  });
});

describe('the eye', () => {
  it('is in the head, on the right, with the tooltip of what a click does', () => {
    mount({ showDownloaded: true });
    expect(head().lastElementChild).toBe(eye());
    expect(eye().title).toBe('Hide image');
    expect(eye().getAttribute('aria-label')).toBe('Hide image');
    expect(eye().textContent).toBe('');
  });

  it('hides and shows the image, and the tooltip follows', () => {
    mount({ showDownloaded: true });
    act(() => eye().click());
    expect(useAppStore.getState().showDownloaded).toBe(false);
    expect(eye().title).toBe('Show image');
    expect(eye().classList.contains('off')).toBe(true);
    act(() => eye().click());
    expect(useAppStore.getState().showDownloaded).toBe(true);
    expect(eye().title).toBe('Hide image');
  });

  it('is not the results switch: it leaves "Hide results" alone', () => {
    mount({ resultsOnMap: false });
    act(() => eye().click());
    expect(useAppStore.getState().resultsOnMap).toBe(false);
  });
});

describe('the rows of buttons', () => {
  it('has three fields and the buttons "auto-scale" and "Apply" in the first row, and four buttons in the second', () => {
    mount();
    const first = [...row('vc-render').children];
    expect(first).toHaveLength(4);
    expect(first.map((el) => el.tagName)).toEqual(['LABEL', 'LABEL', 'LABEL', 'DIV']);
    expect([first[0], first[1], first[2]].map((el) => el.querySelector('span')?.textContent)).toEqual(['vmin', 'vmax', 'Colormap']);
    expect([...first[3].children].map((el) => el.textContent)).toEqual(['auto-scale', 'Apply', 'Apply to all']);
    expect([...row('vc-actions').children].map((el) => el.textContent)).toEqual(['＋ Add to layers', '⚙ Process', '‹ Change image', '✕ Clear']);
  });

  it('has the tooltips of what "Change image" and "Clear" do', () => {
    mount();
    const buttons = [...row('vc-actions').children] as HTMLButtonElement[];
    expect(buttons[2].title).toBe('Remove this view and choose another scene from the results');
    expect(buttons[3].title).toBe('Remove this view from the map');
  });

  it('"Clear" takes the view off the map and nothing else: the tick, the results panel and the switch stay', () => {
    mount({ selectedIds: ['s0'], dock: 'controls', resultsOnMap: false });
    act(() => ([...row('vc-actions').children][3] as HTMLButtonElement).click());
    const s = useAppStore.getState();
    expect(s.focusMode).toBe(false);
    expect(s.downloaded).toEqual({});
    expect(s.selectedIds).toEqual(['s0']);
    expect(s.dock).toBe('controls');
    expect(s.resultsOnMap).toBe(false);
  });

  it('"Change image" takes the view off the map and opens the results, and leaves the tick and the switch', () => {
    const sections = [{ datasetId: 'optical', items: withDays([undefined])[0].items, groups: [], notes: [] }] as never;
    mount({ selectedIds: ['s0'], dock: 'controls', resultsOnMap: false, sections });
    act(() => ([...row('vc-actions').children][2] as HTMLButtonElement).click());
    const s = useAppStore.getState();
    expect(s.focusMode).toBe(false);
    expect(s.dock).toBe('results');
    expect(s.selectedIds).toEqual(['s0']);
    expect(s.resultsOnMap).toBe(false);
  });

  it('puts "Apply" under "auto-scale", in one cluster with "Apply to all" beside them (NM4-53)', () => {
    mount();
    const cluster = row('vc-render').children[3];
    expect(cluster.classList.contains('vc-buttons')).toBe(true);
    expect([...cluster.children].map((el) => el.textContent)).toEqual(['auto-scale', 'Apply', 'Apply to all']);
    expect(container.textContent).not.toContain('Save');
  });
});

// Otto, 29.10.2026 (zu #234): "Apply" is locked while nothing is changed, and says why.
describe('"Apply" of the view', () => {
  const apply = () => container.querySelector('.vc-apply') as HTMLButtonElement;
  const type = (input: HTMLInputElement, value: string) =>
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  const field = (label: string) =>
    [...container.querySelectorAll<HTMLElement>('.vc-field')].find((l) => l.textContent?.startsWith(label))!.querySelector('input')!;

  it('is locked while the fields hold what the map shows, with the reason as its tooltip', () => {
    mount({ appliedRender: { rescale: '0,3000' } });
    expect(apply().getAttribute('aria-disabled')).toBe('true');
    expect(apply().title).toBe(NOTHING_TO_APPLY);
  });

  it('is open once a field is changed, draws the view and is locked again', () => {
    mount({ appliedRender: { rescale: '0,3000' } });
    type(field('vmin'), '5');
    expect(apply().hasAttribute('aria-disabled')).toBe(false);
    expect(apply().title).not.toBe(NOTHING_TO_APPLY);
    act(() => apply().click());
    expect(useAppStore.getState().appliedRender.rescale).toBe('5,3000');
    expect(apply().getAttribute('aria-disabled')).toBe('true');
  });

  it('does nothing when it is locked and clicked', () => {
    mount({ appliedRender: { rescale: '0,3000' } });
    const before = useAppStore.getState().appliedRender;
    act(() => apply().click());
    expect(useAppStore.getState().appliedRender).toBe(before);
  });

  it('counts an empty colormap and a missing one as the same, and a range of one end as none', () => {
    mount({ appliedRender: {}, pendingColormapName: '', pendingVmin: '4', pendingVmax: '' });
    expect(apply().getAttribute('aria-disabled')).toBe('true');
  });
});

// Otto, 30.10.2026 (zu #234): the view of a pinned layer is its settings, with a "Save" beside "Apply".
describe('"Save" of the view of a pinned layer', () => {
  const save = () => container.querySelector('.vc-save') as HTMLButtonElement | null;
  const type = (input: HTMLInputElement, value: string) =>
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input, value);
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
  const vmax = () => [...container.querySelectorAll<HTMLElement>('.vc-field')].find((l) => l.textContent?.startsWith('vmax'))!.querySelector('input')!;
  const layer = {
    id: 'L1', name: 'Optical · day', visible: true, opacity: 1,
    overlays: [{ kind: 'raster', tileUrl: '/t/{z}/{x}/{y}?asset=visual&rescale=0%2C3000', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }],
    restore: { focusMode: true, downloaded: scenes(1), appliedRender: { rescale: '0,3000' }, activeGroupIndex: 0, selectedIds: [], itemIds: ['s0'], groupItemIds: [['s0']], aoi: null, cropToAoi: false, datasetId: 'optical' },
  };

  // Otto, 31.10.2026 (zu #257): "Save" is "Apply to all" and always there; where there is nothing to apply it is locked.
  it('is there for a view that is no layer\'s too, locked for a dataset of one image, with the reason', () => {
    mount({ appliedRender: { rescale: '0,3000' } });
    expect(save()).not.toBeNull();
    expect(save()!.textContent).toBe('Apply to all');
    expect(save()!.getAttribute('aria-disabled')).toBe('true');
    expect(save()!.title).toBe(NOTHING_TO_SAVE_ONE_IMAGE);
  });

  it('stands beside "Apply", under "auto-scale", and is locked while the layer is saved as it is, with the reason', () => {
    mount({ appliedRender: { rescale: '0,3000' }, layers: [layer as never], viewLayerId: 'L1', cropToAoi: false });
    expect([...container.querySelector('.vc-buttons')!.children].map((el) => el.textContent)).toEqual(['auto-scale', 'Apply', 'Apply to all']);
    expect(save()!.getAttribute('aria-disabled')).toBe('true');
    expect(save()!.title).toBe(NOTHING_TO_APPLY_TO_ALL_LAYER);
  });

  it('is the one blue button: "Apply" has the format of "auto-scale"', () => {
    mount({ appliedRender: { rescale: '0,3000' }, layers: [layer as never], viewLayerId: 'L1', cropToAoi: false });
    const [auto, apply, saveButton] = [...container.querySelector('.vc-buttons')!.children] as HTMLButtonElement[];
    const format = (el: HTMLElement) => [...el.classList].filter((c) => !c.startsWith('vc-')).sort();
    expect(format(apply)).toEqual(format(auto));
    expect(format(apply)).toEqual(['ghost-btn']);
    expect(format(saveButton)).toEqual(['primary-btn']);
    expect(container.querySelectorAll('.vc-buttons .primary-btn')).toHaveLength(1);
  });

  it('opens with a change, keeps the look for the layer and is locked again', () => {
    mount({ appliedRender: { rescale: '0,3000' }, layers: [layer as never], viewLayerId: 'L1', cropToAoi: false });
    type(vmax(), '2000');
    expect(save()!.hasAttribute('aria-disabled')).toBe(false);
    act(() => save()!.click());
    expect(useAppStore.getState().layers[0].restore.appliedRender.rescale).toBe('0,2000');
    expect(save()!.getAttribute('aria-disabled')).toBe('true');
  });

  it('does nothing when it is locked and clicked', () => {
    mount({ appliedRender: { rescale: '0,3000' }, layers: [layer as never], viewLayerId: 'L1', cropToAoi: false });
    const before = useAppStore.getState().layers;
    act(() => save()!.click());
    expect(useAppStore.getState().layers).toBe(before);
  });
});

// The grid cannot be laid out in jsdom: what the CSS promises is read off the file.
describe('the layout contract in index.css', () => {
  const rule = (selector: string): string => {
    const start = CSS.indexOf(`${selector} {`);
    expect(start, `no rule for ${selector}`).toBeGreaterThanOrEqual(0);
    return CSS.slice(start, CSS.indexOf('}', start));
  };

  it('puts the head and both rows in one grid of twelve columns, which decides the width of the view', () => {
    expect(rule('.scene-view')).toContain('grid-template-columns: repeat(12, minmax(0, 1fr))');
    expect(rule('.scene-view')).toMatch(/width: min\(/u);
    expect(rule('.scene-view .vc-render')).toContain('grid-template-columns: subgrid');
    expect(rule('.scene-view .vc-head')).toContain('grid-column: 1 / -1');
  });

  it('cuts a long title with "…" and lets it shrink, so the head is never wider than the rows', () => {
    const title = rule('.scene-view .vc-title');
    expect(title).toContain('text-overflow: ellipsis');
    expect(title).toContain('overflow: hidden');
    expect(title).toContain('white-space: nowrap');
    expect(title).toContain('min-width: 0');
  });

  it('lets the dataset and the date in the head shrink and the head wrap below the title, never wider than the rows (NM4-53)', () => {
    expect(rule('.scene-view .vc-head')).toContain('min-width: 0');
    expect(CSS).toMatch(/\.scene-view \.vc-head \{\s*flex-wrap: wrap;/u);
    expect(rule('.scene-view .vc-dataset')).toContain('min-width: 0');
    expect(rule('.vc-stepper')).toContain('min-width: 0');
    expect(rule('.vc-step-text')).toContain('text-overflow: ellipsis');
    expect(rule('.scene-view .vc-title')).toContain('flex: 1 1 120px');
  });

  it('makes "auto-scale" and "Apply" together as high as the fields, and "Apply to all" as high as the two together', () => {
    const cluster = rule('.vc-buttons');
    const height = Number(/--row-height: (\d+)px/u.exec(cluster)?.[1]);
    // The fields of the view and of the settings of a result are as high as the cluster.
    expect(Number(/--row-height: (\d+)px/u.exec(rule('.scene-view'))?.[1])).toBe(height);
    // The settings of a result are the view's box (`.scene-view`), with no rules of their own for size or places (NM4-54 part 5).
    expect(CSS).not.toMatch(/^\.result-controls\b/mu);
    expect(cluster).toContain('height: var(--row-height)');
    expect(cluster).toContain('grid-template-rows: 1fr 1fr');
    // "Save" takes both rows of the second column.
    expect(rule('.vc-buttons > .vc-save')).toContain('grid-area: 1 / 2 / 3 / 3');
    expect(rule('.vc-buttons > .vc-auto')).toContain('grid-area: 1 / 1');
    expect(rule('.vc-buttons > .vc-apply')).toContain('grid-area: 2 / 1');
    const buttons = rule('.vc-buttons > button');
    expect(buttons).not.toMatch(/\n  height:/u);
    // `.vc-apply` aligns itself to the end of a row: in the cluster every button fills its cell, or "Apply" is lower than "auto-scale".
    expect(buttons).toContain('align-self: stretch');
    expect(buttons).toContain('align-items: center');
    expect(buttons).toContain('justify-content: center');
    expect(rule('.vc-buttons')).toContain('grid-template-columns: 1fr 1fr');
    expect(rule('.scene-view .vc-render > :nth-child(3)')).toContain('grid-column: span 3');
    expect(rule('.scene-view .vc-render > :nth-child(4)')).toContain('grid-column: span 5');
    expect(rule('.scene-view .vc-field select,\n.scene-view .vc-field input')).toContain('height: var(--row-height)');
    expect(rule('.scene-view .vc-render')).toContain('align-items: end');
    expect(rule('.scene-view .vc-actions')).toContain('align-items: end');
  });

  // Otto, 1.11.2026: the view is two rows high under its head and wider rather than taller; its buttons are in one row.
  it('puts the buttons of the second row in one row, four or five of one width, and wraps them below 600 px', () => {
    expect(rule('.scene-view .vc-actions')).toContain('grid-template-columns: repeat(var(--buttons), minmax(0, 1fr))');
    expect(rule('.scene-view .vc-actions')).toContain('--buttons: 4');
    expect(rule('.scene-view .vc-actions.has-all')).toContain('--buttons: 5');
    expect(CSS).toMatch(/@media \(max-width: 599px\) \{\s*\.scene-view \{\s*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/u);
    expect(CSS).toMatch(/\.scene-view \.vc-actions\.has-all \{\s*--buttons: 2;/u);
  });

  it('is wide enough for five buttons in one row, and wider than it is high', () => {
    const cell = Number(/--cell: (\d+)px/u.exec(rule('.scene-view'))?.[1]);
    const inner = 12 * cell + 11 * 8;
    expect((inner - 4 * 8) / 5).toBeGreaterThanOrEqual(110);
  });

  it('breaks a word that is too long for its button instead of running over the edge', () => {
    expect(rule('.scene-view .vc-actions > *')).toContain('overflow-wrap: anywhere');
  });
});
