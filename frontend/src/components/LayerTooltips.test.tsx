// @vitest-environment jsdom
//
// The tooltips of the layer manager against the guide (`docs/ui/leitfaden.md` §4, §8a; Otto's check in the browser, 11.11.2026): a row of
// a dataset, of a result and "Search results" are treated alike. A locked control shows its reason in either step, also where the tip sits
// on the label around the field; a deleted job locks every control of its row with one reason; "Process" has one name for every layer.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import { jobEntry, jobId, NOW } from '../fixtures/jobEntries';
import { LOCKED_LAYER_TIP, type MapLayer } from '../layers';
import type { Order } from '../processing';
import { EXPIRED_PROCESS_TEXT, PROCESS_LAYER_TEXT, resetJobs, useProcessingStore } from '../processingStore';
import { useAppStore } from '../store';
import type { Collection } from '../types';
import { tipShown, type TipLevel } from '../tipLevel';
import LayerActions from './LayerActions';
import LayerManager from './LayerManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const DAY = 86_400_000;
const DATASET = 'optical';
const datasets = datasetsFrom([
  {
    id: DATASET,
    title: 'Optical',
    'earthx:license_flags': { tier: 'processing' },
    'earthx:capabilities': { time_range: true },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  } as unknown as Collection,
]);
const restore = (itemIds: string[]) => ({ datasetId: DATASET, itemIds, groupItemIds: [], aoi: null, cropToAoi: false }) as unknown as MapLayer['restore'];
const BANDS = [
  { name: 'red', stats: null },
  { name: 'nir', stats: null },
];

const datasetLayer: MapLayer = { id: 'view', name: 'Optical · 24 Jul', visible: true, opacity: 1, overlays: [], restore: restore(['a']) };
const resultLayer = (id: string, n: number, over: object = {}): MapLayer => ({
  id,
  name: `Result · ${id}`,
  visible: true,
  opacity: 1,
  overlays: [],
  derived: 'result',
  restore: restore([]),
  result: { jobID: jobId(n), expires: new Date(NOW + 7 * DAY).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, bands: BANDS, band: 0, ...over },
});
const order = { recipe_version: 2, inputs: [{ name: 'input', dataset: DATASET, groups: [['a']] }], steps: [], output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['red', 'nir'] } } as unknown as Order;

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'], now: NOW });
  resetJobs();
  useProcessingStore.setState({
    jobs: [
      jobEntry(1, { phase: 'successful', order }),
      jobEntry(2, { phase: 'dismissed', order, deletedUntil: new Date(NOW + DAY).toISOString(), serverDeleted: true }),
      jobEntry(3, { phase: 'successful', order }),
    ],
  });
  const section = { datasetId: DATASET, items: [{ id: 'a' }], groups: [], notes: [], groupingError: null, origin: 'search', incomplete: false };
  useAppStore.setState({
    datasets,
    sections: [section] as never,
    resultsAt: 0,
    layers: [datasetLayer, resultLayer('live', 1), resultLayer('deleted', 2, { deleted: true }), resultLayer('expired', 3, { expired: true })],
    dock: 'layers',
  });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  act(() => root.render(<LayerManager />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  resetJobs();
  vi.useRealTimers();
});

const row = (name: string) =>
  [...container.querySelectorAll<HTMLElement>('.layer-row')].find((r) => r.querySelector('[data-col="name"]')?.textContent === name)!;
const at = (name: string, col: string) => row(name).querySelector<HTMLElement>(`[data-col="${col}"]`)!;
// The tip the pointer on `element` gets in the step `level`, as `TipLayer` finds it: the nearest element with a tip up the tree that the step shows.
function shownTip(element: Element, level: TipLevel): string | null {
  for (let el = element.closest('[data-tip]'); el; el = el.parentElement?.closest('[data-tip]') ?? null) if (tipShown(el, level)) return el.getAttribute('data-tip');
  return null;
}
const locked = (r: HTMLElement) => [...r.querySelectorAll<HTMLElement>('button, input, select')].filter((c) => c.matches(':disabled, [aria-disabled="true"]'));

describe('a locked control of the layer manager', () => {
  it.each(['Result · deleted', 'Result · expired'])('shows its reason in the step "Simple" in the row %s, the band too', (name) => {
    const controls = locked(row(name));
    expect(controls.length).toBeGreaterThan(0);
    expect(controls.filter((control) => !shownTip(control, 'simple')).map((control) => control.getAttribute('aria-label') ?? control.tagName)).toEqual([]);
    expect(shownTip(row(name).querySelector('.lm-band select')!, 'simple')).not.toBeNull();
  });

  it('has one reason for everything a deleted job locks: the eye, the name, the opacity, the band, "+" and the download', () => {
    const r = row('Result · deleted');
    const reasons = ['eye', 'rename', 'opacity', 'download'].map((col) => at('Result · deleted', col).getAttribute('data-tip'));
    reasons.push(r.querySelector('.lm-band')!.getAttribute('data-tip'), r.querySelector('.lm-add-band')!.getAttribute('data-tip'));
    expect(new Set(reasons)).toEqual(new Set([LOCKED_LAYER_TIP]));
    expect((at('Result · deleted', 'download') as HTMLButtonElement).disabled).toBe(true);
    expect((r.querySelector('.lm-add-band') as HTMLButtonElement).disabled).toBe(true);
  });

  it('of an expired result keeps what is gone for good out of the row (Otto, 26.10.2026): no download, no "+"', () => {
    expect(at('Result · expired', 'download').tagName).toBe('SPAN');
    expect(row('Result · expired').querySelector('.lm-add-band')).toBeNull();
  });
});

describe('"Process" in the layer manager', () => {
  it('has one name for a layer of a dataset and of a result, its aria-label, in the step "Simple"', () => {
    for (const name of ['Optical · 24 Jul', 'Result · live']) {
      const gear = at(name, 'process');
      expect([gear.getAttribute('data-tip'), gear.getAttribute('aria-label'), shownTip(gear, 'simple')]).toEqual([PROCESS_LAYER_TEXT, PROCESS_LAYER_TEXT, PROCESS_LAYER_TEXT]);
    }
  });

  it('of an expired result names itself and says what runs, as a phrase without a full stop', () => {
    const gear = at('Result · expired', 'process');
    expect(gear.getAttribute('data-tip')).toBe(EXPIRED_PROCESS_TEXT);
    expect(EXPIRED_PROCESS_TEXT.startsWith(`${PROCESS_LAYER_TEXT}:`)).toBe(true);
    expect(EXPIRED_PROCESS_TEXT.endsWith('.')).toBe(false);
  });
});

describe('the rows of a dataset, of a result and "Search results"', () => {
  it('give the controls they share the same step of the tooltip', () => {
    const results = container.querySelector<HTMLElement>('.results-row')!;
    for (const col of ['grip', 'eye', 'up', 'down']) {
      const steps = [row('Optical · 24 Jul'), row('Result · live'), results].map((r) => r.querySelector(`[data-col="${col}"]`)?.getAttribute('data-tip-level'));
      expect(steps, col).toEqual(['advanced', 'advanced', 'advanced']);
    }
  });

  it('have no tooltip at the name, unless it says why nothing is shown, a note or what "Search results" is', () => {
    for (const name of ['Optical · 24 Jul', 'Result · live', 'Result · deleted', 'Result · expired']) expect(at(name, 'name').hasAttribute('data-tip'), name).toBe(false);
  });
});

describe('the actions of a layer of a deleted job in the settings bar', () => {
  it('lock "Add current view to layers" with the reason of the row (Otto, 11.11.2026)', () => {
    const layer = useAppStore.getState().layers.find((l) => l.id === 'deleted')!;
    act(() => root.render(<LayerActions layer={layer} />));
    const copy = container.querySelector<HTMLButtonElement>('.vc-copy')!;
    expect([copy.disabled, copy.getAttribute('data-tip'), shownTip(copy, 'simple')]).toEqual([true, LOCKED_LAYER_TIP, LOCKED_LAYER_TIP]);
    // The ZIP is locked with the same reason.
    const download = [...container.querySelectorAll<HTMLButtonElement>('button')].find((b) => b.textContent?.includes('Download'))!;
    expect([download.disabled, download.getAttribute('data-tip')]).toEqual([true, LOCKED_LAYER_TIP]);
  });
});
