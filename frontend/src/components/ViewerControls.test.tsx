// @vitest-environment jsdom
//
// Otto, 27.10.2026 (zu #211): the view of scenes has a head with an eye for "Hide image", its fields and buttons, and "✕ Clear". Since
// UI-03a (2.11.2026) it stands in the settings bar: the head has two rows, then "Display" and "Actions". The CSS contract is read off
// `index.css`, as `mapStyles.test.ts` does for the theme.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CSS from '../index.css?raw';
import TOKENS from '../tokens.css?raw';
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
const labelOf = (el: Element) => el.querySelector('span')?.textContent;

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

  // Otto, 1.11.2026 (zu #272): the view of the search is a temporary picture, and a yellow box beside the title says so.
  it('has a badge "Temporary" right after the title, before the eye and the x, in the style of the "Preview" badge', () => {
    mount();
    const temporary = container.querySelector('.vc-temporary') as HTMLElement;
    expect(temporary.textContent).toBe('Temporary');
    expect(temporary.previousElementSibling).toBe(title());
    expect(temporary.nextElementSibling).toBe(eye());
    expect(temporary.classList.contains('pp-badge')).toBe(true);
    expect(CSS).toMatch(/\.preview-badge,\s*\.pp-badge \{[^}]*border: 1px solid var\(--accent-2\)/u);
  });

  it('has the dataset and the date with the arrows in a second row, under the title', () => {
    mount();
    const rows = head().children;
    expect(rows).toHaveLength(2);
    expect(rows[0].contains(title())).toBe(true);
    expect(rows[1].querySelector('.vc-stepper')).not.toBeNull();
    expect(rows[0].querySelector('.vc-stepper')).toBeNull();
  });

  it('has no box "Temporary" in the settings of a layer: a layer is not temporary', () => {
    mount({ viewOfLayer: true, layers: [{ id: 'L1', name: 'Optical', visible: true, opacity: 1, overlays: [], restore: { focusMode: true, downloaded: scenes(1), appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: true, datasetId: 'optical' } } as never], viewLayerId: 'L1' });
    expect(container.querySelector('.vc-temporary')).toBeNull();
    act(() => useAppStore.setState({ viewOfLayer: false, layers: [], viewLayerId: null }));
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
  it('is in the first row of the head, before the red x, with the tooltip of what a click does', () => {
    mount({ showDownloaded: true });
    expect(eye().nextElementSibling).toBe(container.querySelector('.vc-head .close-x'));
    expect(head().firstElementChild!.contains(eye())).toBe(true);
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

describe('the fields and the buttons', () => {
  const ACTIONS = ['＋ Add to layers', '＋ Add all to layers', '⚙ Process', '‹ Change image', '⇩ Download crop', '⇩ Download full scene', '✕ Clear'];
  const actions = () => [...row('vc-actions').children] as HTMLButtonElement[];
  const actionNamed = (text: string) => actions().find((b) => b.textContent === text)!;

  it('has the fields in the order of the place, then the opacity and the buttons "auto-scale", "Apply", "Apply to all"; the actions under them', () => {
    mount();
    const first = [...row('vc-render').children];
    expect(first.map((el) => el.tagName)).toEqual(['LABEL', 'LABEL', 'LABEL', 'LABEL', 'DIV', 'DIV']);
    expect(first.slice(0, 4).map(labelOf)).toEqual(['Band', 'vmin', 'vmax', 'Colormap']);
    expect(first[4].classList.contains('vc-opacity')).toBe(true);
    expect([...first[5].children].map((el) => el.textContent)).toEqual(['auto-scale', 'Apply', 'Apply to all']);
    expect(actions().map((el) => el.textContent)).toEqual(ACTIONS);
  });

  it('has the tooltips of what "Change image" and "Clear" do', () => {
    mount();
    expect(actions()[3].title).toBe('Remove this view and choose another scene from the results');
    expect(actions()[6].title).toBe('Remove this view from the map');
  });

  it('"Clear" takes the view off the map and nothing else: the tick, the results panel and the switch stay', () => {
    mount({ selectedIds: ['s0'], dock: 'controls', resultsOnMap: false });
    act(() => actions()[6].click());
    const s = useAppStore.getState();
    expect(s.focusMode).toBe(false);
    expect(s.downloaded).toEqual({});
    expect(s.selectedIds).toEqual(['s0']);
    expect(s.dock).toBe('controls');
    expect(s.resultsOnMap).toBe(false);
  });

  it('"Change image" takes the view off the map, opens the results and shows them, and leaves the tick (Otto, 2.11.2026)', () => {
    const sections = [{ datasetId: 'optical', items: withDays([undefined])[0].items, groups: [], notes: [] }] as never;
    mount({ selectedIds: ['s0'], dock: 'controls', resultsOnMap: false, sections });
    act(() => actionNamed('‹ Change image').click());
    const s = useAppStore.getState();
    expect(s.focusMode).toBe(false);
    expect(s.dock).toBe('results');
    expect(s.selectedIds).toEqual(['s0']);
    expect(s.resultsOnMap).toBe(true);
  });

  it('puts "auto-scale", "Apply" and "Apply to all" in one row (NM4-53)', () => {
    mount();
    const cluster = row('vc-render').children[5];
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

  // Otto, 1.11.2026 (zu #272): "Temporary" goes when the image is a layer, and comes back with a change.
  it('takes off "Temporary" while a layer holds the image as it is drawn, and puts it back with an applied change; the fields alone do not', () => {
    mount({ appliedRender: { rescale: '0,3000' }, pendingVmin: '0', pendingVmax: '3000', layers: [], cropToAoi: false });
    expect(container.querySelector('.vc-temporary')).not.toBeNull();
    mount({ appliedRender: { rescale: '0,3000' }, pendingVmin: '0', pendingVmax: '3000', layers: [layer as never], viewLayerId: 'L1', cropToAoi: false });
    expect(container.querySelector('.vc-temporary')).toBeNull();
    type(vmax(), '2000');
    expect(container.querySelector('.vc-temporary')).toBeNull(); // typed, not drawn
    act(() => void (container.querySelector('.vc-apply') as HTMLButtonElement).click());
    expect(container.querySelector('.vc-temporary')).not.toBeNull();
    type(vmax(), '3000');
    act(() => void (container.querySelector('.vc-apply') as HTMLButtonElement).click());
    expect(container.querySelector('.vc-temporary')).toBeNull();
  });

  it('stands beside "Apply", after "auto-scale", and is locked while the layer is saved as it is, with the reason', () => {
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

// The layout cannot be laid out in jsdom: what the CSS promises is read off the file.
describe('the layout contract in index.css', () => {
  const rule = (selector: string): string => {
    const start = CSS.indexOf(`${selector} {`);
    expect(start, `no rule for ${selector}`).toBeGreaterThanOrEqual(0);
    return CSS.slice(start, CSS.indexOf('}', start));
  };

  it('puts the bar at the right edge from 64 px to the foot, 320 px wide, with a line on the left and no corners', () => {
    const bar = rule('.inspector.panel');
    for (const declaration of ['top: 64px', 'right: 0', 'bottom: 0', 'width: var(--inspector-width)', 'border-radius: 0', 'border-width: 0 0 0 var(--line-width)']) expect(bar).toContain(declaration);
    expect(Number(/--inspector-width: (\d+)px/u.exec(TOKENS)?.[1])).toBe(320);
  });

  it('makes it a sheet from the bottom under 900 px, at most 55 % high, round at the top', () => {
    expect(CSS).toMatch(/@media \(max-width: 899px\) \{\s*\.inspector\.panel \{[^}]*top: auto;[^}]*left: var\(--rail-width\);[^}]*max-height: 55vh;[^}]*border-radius: var\(--radius-md\) var\(--radius-md\) 0 0;/u);
  });

  it('keeps the head standing and lets the middle scroll', () => {
    expect(rule('.inspector .vc-head')).toContain('flex: none');
    expect(rule('.inspector .insp-body')).toContain('overflow-y: auto');
    expect(rule('.inspector .insp-body')).toContain('min-height: 0');
  });

  it('cuts a long title with "…" and lets it shrink', () => {
    const title = rule('.inspector .vc-title');
    expect(title).toContain('text-overflow: ellipsis');
    expect(title).toContain('overflow: hidden');
    expect(title).toContain('white-space: nowrap');
    expect(title).toContain('min-width: 0');
  });

  it('makes both rows of the head as high as a control, so that "Display" begins at one height', () => {
    expect(rule('.inspector .insp-row')).toContain('min-height: var(--control-height)');
  });

  it('lays the fields out as a form: a label column of 72 px, the control filling the rest, a row as high as a control', () => {
    const field = rule('.inspector .vc-field');
    expect(field).toContain('grid-template-columns: 72px minmax(0, 1fr)');
    expect(field).toContain('min-height: var(--control-height)');
    expect(rule('.inspector .vc-field select,\n.inspector .vc-field input:not([type=\'range\'])')).toContain('height: var(--control-height)');
    expect(rule('.inspector .vc-render')).toContain('gap: var(--space-2)');
  });

  it('puts "auto-scale", "Apply" and "Save" in three columns of one width, the actions one per line without wrapping', () => {
    expect(rule('.inspector .vc-buttons')).toContain('grid-template-columns: repeat(3, minmax(0, 1fr))');
    expect(rule('.inspector .vc-actions')).toContain('flex-direction: column');
    expect(rule('.inspector .vc-actions > *')).toContain('white-space: nowrap');
    expect(rule('.inspector .vc-actions > *')).toContain('min-width: 0');
  });

  it('keeps the switch of the range below the one height of the fields, so that it stays in the line of the label', () => {
    expect(rule('.vc-field.vc-num .vc-unit')).toContain('min-height: 0');
  });
});
