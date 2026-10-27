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
import type { Collection, DownloadedInfo } from '../types';
import { viewKind } from '../viewKind';
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

const info = (): DownloadedInfo => ({ tileUrl: '/t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 0, maxZoom: 14 });
const scenes = (n: number) => Object.fromEntries(Array.from({ length: n }, (_, i) => [`s${i}`, info()]));

let container: HTMLDivElement;
let root: Root;

function mount(over: Partial<AppState> = {}, title = 'Sentinel-2 L2A') {
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection(title)]), datasetId: 'optical', focusMode: true, cropToAoi: true, downloaded: scenes(1), showDownloaded: true,
      pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', focusLoading: false, pinLoading: false, ...over,
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
  it('has five controls in the first row and four buttons in the second', () => {
    mount();
    const first = [...row('vc-render').children];
    expect(first).toHaveLength(5);
    expect(first.map((el) => el.tagName)).toEqual(['LABEL', 'LABEL', 'LABEL', 'BUTTON', 'BUTTON']);
    expect([first[0], first[1], first[2]].map((el) => el.querySelector('span')?.textContent)).toEqual(['Colormap', 'vmin', 'vmax']);
    expect([first[3], first[4]].map((el) => el.textContent)).toEqual(['auto', 'Apply']);
    expect([...row('vc-actions').children].map((el) => el.textContent)).toEqual(['＋ Add to layers', '⚙ Process', '‹ Change image', '✕ Clear']);
  });

  it('has the tooltips: "Choose a different image" and "Remove this view and deselect"', () => {
    mount();
    const buttons = [...row('vc-actions').children] as HTMLButtonElement[];
    expect(buttons[2].title).toBe('Choose a different image');
    expect(buttons[3].title).toBe('Remove this view and deselect');
  });

  it('leaves the view with "Change image", keeping the choice of scenes, and takes everything with "Clear"', () => {
    mount({ selectedIds: ['s0'] });
    const [, , change, clear] = [...row('vc-actions').children] as HTMLButtonElement[];
    act(() => change.click());
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().selectedIds).toEqual(['s0']);
    mount({ focusMode: true, selectedIds: ['s0'], downloaded: scenes(1) });
    act(() => ([...row('vc-actions').children][3] as HTMLButtonElement).click());
    expect(useAppStore.getState().focusMode).toBe(false);
    expect(useAppStore.getState().selectedIds).toEqual([]);
    expect(clear).toBeDefined();
  });
});

// The grid cannot be laid out in jsdom: what the CSS promises is read off the file.
describe('the layout contract in index.css', () => {
  const rule = (selector: string): string => {
    const start = CSS.indexOf(`${selector} {`);
    expect(start, `no rule for ${selector}`).toBeGreaterThanOrEqual(0);
    return CSS.slice(start, CSS.indexOf('}', start));
  };

  it('puts the head and both rows in one grid of eight columns, which decides the width of the view', () => {
    expect(rule('.scene-view')).toContain('grid-template-columns: repeat(8, minmax(0, 1fr))');
    expect(rule('.scene-view')).toMatch(/width: min\(/u);
    expect(rule('.scene-view .vc-render,\n.scene-view .vc-actions')).toContain('grid-template-columns: subgrid');
    expect(rule('.scene-view .vc-head')).toContain('grid-column: 1 / -1');
  });

  it('cuts a long title with "…" and lets it shrink, so the head is never wider than the rows', () => {
    const title = rule('.scene-view .vc-title');
    expect(title).toContain('text-overflow: ellipsis');
    expect(title).toContain('overflow: hidden');
    expect(title).toContain('white-space: nowrap');
    expect(title).toContain('min-width: 0');
  });

  it('gives the four buttons of the second row two columns each and wraps them below 600 px', () => {
    expect(rule('.scene-view .vc-actions > *')).toContain('grid-column: span 2');
    expect(CSS).toMatch(/@media \(max-width: 599px\) \{\s*\.scene-view \{\s*grid-template-columns: repeat\(4, minmax\(0, 1fr\)\);/u);
  });

  it('breaks a word that is too long for its button instead of running over the edge', () => {
    expect(rule('.scene-view .vc-actions > *')).toContain('overflow-wrap: anywhere');
  });
});
