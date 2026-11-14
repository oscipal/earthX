// @vitest-environment jsdom
//
// The free area of the map (Otto, 14.11.2026): the status box lies centred between an open panel at the left and an open panel at the
// right, and narrower where they leave less room, so that no panel covers it. This is the rule of the classes of `.app` and of the sheet that
// reads them; `e2e/status-box.cjs` measures the box in a real browser. The Data catalogue may cover the box and takes nothing from the area.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from './App';
import index from './index.css?raw';
import { mapEdgeClasses } from './mapEdges';
import { resetJobs, useProcessingStore } from './processingStore';
import { useAppStore } from './store';
import tokens from './tokens.css?raw';
import type { MapLayer } from './layers';

vi.mock('./components/MapView', () => ({ default: () => null }));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const NONE = { dock: false, inspector: false, processing: false };

describe('the classes of the open panels', () => {
  it('has none with no panel open: the box stays in the middle of the map right of the rail', () => {
    expect(mapEdgeClasses(NONE)).toBe('');
  });

  it('marks a panel of the rail at the left only', () => {
    expect(mapEdgeClasses({ ...NONE, dock: true })).toBe(' has-dock');
  });

  it('marks the settings bar at the right only', () => {
    expect(mapEdgeClasses({ ...NONE, inspector: true })).toBe(' has-inspector');
  });

  it('marks the wide sheet at the right only, and not the settings bar the sheet has pushed out of the column', () => {
    expect(mapEdgeClasses({ ...NONE, processing: true })).toBe(' has-sheet');
    expect(mapEdgeClasses({ dock: false, inspector: true, processing: true })).toBe(' has-sheet');
  });

  it('marks both sides when a panel is open at each', () => {
    expect(mapEdgeClasses({ dock: true, inspector: true, processing: false })).toBe(' has-dock has-inspector');
    expect(mapEdgeClasses({ dock: true, inspector: false, processing: true })).toBe(' has-dock has-sheet');
  });
});

const css = index.replace(/\/\*[\s\S]*?\*\//gu, '');
const wide = '@media (min-width: 900px)';

// The declarations of the first rule with exactly this selector, inside the media query when one is given, else outside any.
function ruleOf(sheet: string, selector: string, inMedia?: string): string {
  const scope = inMedia ? (sheet.slice(sheet.indexOf(inMedia)).split(/\n\}\n/u)[0] ?? '') : sheet;
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');
  return new RegExp(`(?:^|\\n)\\s*${escaped}\\s*\\{([^}]*)\\}`, 'u').exec(scope)?.[1] ?? '';
}

describe('the sheet', () => {
  it('takes the edges of the free area from the widths of the panels, not from numbers of its own', () => {
    expect(ruleOf(css, '.app', wide)).toContain('--map-left: var(--rail-width)');
    expect(ruleOf(css, '.app', wide)).toContain('--map-right: 0px');
    expect(ruleOf(css, '.app.has-dock', wide)).toContain('--map-left: calc(var(--rail-width) + var(--dock-width))');
    expect(ruleOf(css, '.app.has-inspector', wide)).toContain('--map-right: var(--inspector-width)');
    expect(ruleOf(css, '.app.has-sheet', wide)).toContain('--map-right: var(--sheet-wide-width)');
  });

  it('centres the box between the two edges, whichever are there, with one rule', () => {
    const rule = ruleOf(css, '.overlay.status', wide);
    expect(rule).toContain('left: calc((100% + var(--map-left) - var(--map-right)) / 2)');
    expect(rule).toContain('calc(100% - var(--map-left) - var(--map-right) - 2 * var(--space-4))');
    // No second rule per panel: one mechanism.
    expect(css.match(/\.overlay\.status \{/gu)).toHaveLength(2);
    expect(css).not.toMatch(/\.app\.has-(?:inspector|sheet) \.overlay\.status/u);
  });

  it('is no wider than 560 px and not narrower than its minimum, however little room the panels leave', () => {
    expect(ruleOf(css, '.overlay.status', wide)).toContain('width: max(var(--status-min-width), min(560px, ');
    expect(tokens).toMatch(/--status-min-width:\s*240px/u);
  });

  it('leaves the narrow window to its own rule: no panel is taken from the map there', () => {
    expect(css.slice(css.indexOf('.status {')).split('@media')[0]).toContain('width: min(560px, calc(100vw - var(--rail-width) - 16px))');
    expect(ruleOf(css, '.overlay.status', '@media (max-width: 899px)')).toContain('z-index: 13');
    expect(ruleOf(css, '.app.has-dock', '@media (max-width: 899px)')).toBe('');
  });

  it('does not read the Data catalogue: it covers the box and the box does not move for it', () => {
    expect(css).not.toMatch(/catalogue[^{]*\{[^}]*--map-(?:left|right)/u);
    expect(css).not.toMatch(/\.catalogue[^{]*\.overlay\.status|\.overlay\.status[^{]*\.catalogue/u);
    expect(ruleOf(css, '.catalogue')).toContain('z-index: 12');
    expect(ruleOf(css, '.status')).not.toContain('z-index');
  });
});

let container: HTMLDivElement;
let root: Root;
const app = () => container.querySelector('.app')!;
const result = (): MapLayer => ({
  id: 'R1',
  name: 'Result',
  visible: true,
  opacity: 1,
  derived: 'result',
  overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/{z}/{x}/{y}?colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
  result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null },
  restore: { datasetId: null, itemIds: [] } as never,
});

describe('the app', () => {
  beforeEach(() => {
    globalThis.IS_REACT_ACT_ENVIRONMENT = true;
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
    resetJobs();
    useProcessingStore.setState({ open: false, jobs: [] });
    useAppStore.setState({ dock: null, catalogueOpen: false, focusMode: false, layers: [], resultViewLayerId: null, error: null, notice: null });
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    act(() => root.render(<App />));
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    resetJobs();
    vi.unstubAllGlobals();
    useAppStore.setState({ dock: null, catalogueOpen: false, layers: [], resultViewLayerId: null });
  });

  it('marks the left edge while a panel of the rail is open, and gives the centre back when it closes', () => {
    expect(app().classList.contains('has-dock')).toBe(false);
    for (const dock of ['controls', 'layers', 'results', 'jobs', 'settings'] as const) {
      act(() => useAppStore.setState({ dock }));
      expect(app().classList.contains('has-dock'), dock).toBe(true);
    }
    act(() => useAppStore.getState().closeDock());
    expect(app().classList.contains('has-dock')).toBe(false);
  });

  it('marks both edges with a panel at each side, and drops each one on its own when it closes', () => {
    act(() => useAppStore.setState({ dock: 'layers', layers: [result()], resultViewLayerId: 'R1' }));
    expect(app().classList.contains('has-dock')).toBe(true);
    expect(app().classList.contains('has-inspector')).toBe(true);
    act(() => useAppStore.setState({ resultViewLayerId: null }));
    expect(app().classList.contains('has-inspector')).toBe(false);
    expect(app().classList.contains('has-dock')).toBe(true);
    act(() => useProcessingStore.setState({ open: true }));
    expect(app().classList.contains('has-sheet')).toBe(true);
    act(() => useProcessingStore.setState({ open: false }));
    expect(app().classList.contains('has-sheet')).toBe(false);
    act(() => useAppStore.setState({ dock: null }));
    expect(app().className).toBe('app');
  });

  it('does not move the box for the Data catalogue', () => {
    act(() => useAppStore.setState({ dock: 'controls' }));
    const before = app().className;
    act(() => useAppStore.setState({ catalogueOpen: true }));
    expect(container.querySelector('.catalogue')).not.toBeNull();
    expect(app().className).toBe(before);
    act(() => useAppStore.setState({ dock: null }));
    expect(app().className).toBe('app');
  });
});
