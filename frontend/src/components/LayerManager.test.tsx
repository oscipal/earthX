// @vitest-environment jsdom
//
// M3-10 (Otto, 30.09.2026): the coverage map is switched in the control panel;
// the layer manager lists pinned layers only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import { jobEntry, jobId, NOW } from '../fixtures/jobEntries';
import { resetJobs, useProcessingStore } from '../processingStore';
import LayerManager, { DELETED_LAYER_TIP, EXPIRED_LAYER_TEXT, HIDE_LAYER_TIP, RESAMPLED_LAYER_TEXT, SHOW_LAYER_TIP } from './LayerManager';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

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

describe('LayerManager', () => {
  it('has no coverage row, with or without an active dataset', () => {
    const datasets = datasetsFrom([
      {
        id: 'optical',
        title: 'Optical',
        'earthx:capabilities': {
          roi: true,
          time_range: true,
          band_math: true,
          interpolation: true,
          ml_processing: true,
          quad_pol: false,
          single_coverage_product: false,
        },
        'earthx:viewer': {
          group_by: ['datetime'],
          min_zoom: 0,
          max_zoom: 14,
          browse: 'quicklook',
          quicklook_nodata_max: null,
          results_group_by: ['datetime'],
        },
      },
    ]);
    useAppStore.setState({ datasets, datasetId: 'optical', selectedDatasetIds: ['optical'], layers: [], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(container.textContent).not.toContain('Coverage');
    expect(container.querySelector('.coverage-row')).toBeNull();
    expect(container.textContent).toContain('No layers yet');
  });

  // Otto, 24.10.2026: no kind of layer shows a unit; they stay on the band chips and in the data.
  it('shows no unit on a layer of a dataset that names units', () => {
    const datasets = datasetsFrom([{ id: 'dem', title: 'Elevation', 'earthx:band_units': { data: 'm' } }]);
    const layer: MapLayer = {
      id: 'dem-layer',
      name: 'Elevation · tile',
      visible: true,
      opacity: 1,
      overlays: [{ kind: 'raster', tileUrl: 'https://t/dem/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
      restore: { datasetId: 'dem', itemIds: [] } as never,
    };
    useAppStore.setState({ datasets, datasetId: 'dem', selectedDatasetIds: ['dem'], layers: [layer], dock: 'layers' });
    act(() => root.render(<LayerManager />));
    expect(container.querySelector('.layer-row')).not.toBeNull();
    expect(container.textContent).not.toMatch(/\bm\b/u);
  });

  // M4-28: a click arrives at the row it was made on — also when every row has the
  // same name and shows the same picture, and after the list was reordered.
  describe('a click on a row', () => {
    const layer = (id: string): MapLayer => ({
      id,
      name: 'Optical · same name',
      visible: true,
      opacity: 1,
      overlays: [{ kind: 'raster', tileUrl: 'https://t/same/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
      restore: { datasetId: null, itemIds: [] } as never,
    });
    const rows = () => [...container.querySelectorAll('.layer-row')];
    const click = (el: Element | null | undefined) => act(() => el?.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    const flags = () => useAppStore.getState().layers.map((l) => `${l.id}:${l.visible ? 1 : 0}`);

    beforeEach(() => {
      useAppStore.setState({ datasets: [], layers: ['one', 'two', 'three', 'four', 'five'].map(layer), dock: 'layers' });
      act(() => root.render(<LayerManager />));
    });

    it('switches the layer of that row and no other', () => {
      click(rows()[2].querySelector('.lm-eye'));
      expect(flags()).toEqual(['one:1', 'two:1', 'three:0', 'four:1', 'five:1']);
      click(rows()[2].querySelector('.lm-eye'));
      expect(flags()).toEqual(['one:1', 'two:1', 'three:1', 'four:1', 'five:1']);
    });

    it('still reaches its own layer after the rows were moved', () => {
      click(rows()[3].querySelector('button[title="Move up"]'));
      click(rows()[2].querySelector('button[title="Move up"]'));
      expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['one', 'four', 'two', 'three', 'five']);
      click(rows()[1].querySelector('.lm-eye')); // "four", now second
      expect(flags()).toEqual(['one:1', 'four:0', 'two:1', 'three:1', 'five:1']);
      click(rows()[4].querySelector('button[title="Remove layer"]')); // "five"
      click(rows()[3].querySelector('.lm-eye')); // "three"
      expect(flags()).toEqual(['one:1', 'four:0', 'two:1', 'three:0']);
    });

    it('lands on the layers clicked in quick succession, each once', () => {
      for (const i of [0, 4, 2, 0, 3, 4]) click(rows()[i].querySelector('.lm-eye'));
      expect(flags()).toEqual(['one:1', 'two:1', 'three:0', 'four:0', 'five:1']);
    });

    it('on the name chooses the layer for the view and leaves the order of the list alone', () => {
      const restore = {
        focusMode: true,
        downloaded: {},
        appliedRender: {},
        activeGroupIndex: 0,
        selectedIds: [],
        itemIds: [],
        groupItemIds: [],
        aoi: null,
        cropToAoi: false,
        datasetId: null,
      };
      useAppStore.setState({ layers: useAppStore.getState().layers.map((l) => ({ ...l, restore })) });
      click(rows()[3].querySelector('.lm-name'));
      expect(useAppStore.getState().viewLayerId).toBe('four');
      expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['one', 'two', 'three', 'four', 'five']);
      click(rows()[1].querySelector('.lm-name'));
      expect(useAppStore.getState().viewLayerId).toBe('two');
      expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['one', 'two', 'three', 'four', 'five']);
    });

    it('sets the opacity of that row only', () => {
      const slider = rows()[1].querySelector('input.lm-opacity') as HTMLInputElement;
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      act(() => {
        set.call(slider, '0.25');
        slider.dispatchEvent(new Event('input', { bubbles: true }));
      });
      expect(useAppStore.getState().layers.map((l) => l.opacity)).toEqual([1, 0.25, 1, 1, 1]);
    });
  });

  // Otto, 20.10.2026: every row has the same places, and a button that is missing leaves its place empty.
  describe('the rows', () => {
    const base = { visible: true, opacity: 1, overlays: [] };
    const restore = { datasetId: 'ds', itemIds: ['scene'], groupItemIds: [['scene']], aoi: null, cropToAoi: false } as unknown as MapLayer['restore'];
    const result = (over: object) => ({
      jobID: 'AbCdEfGhIjKlMnOpQrSt_-',
      expires: new Date(Date.now() + 86_400_000).toISOString(),
      gsd: 10,
      resampled: null,
      expired: false,
      dataType: 'float32',
      stats: null,
      ...over,
    });
    const kinds: MapLayer[] = [
      { ...base, id: 'scene', name: 'Optical · a scene with a download', restore },
      { ...base, id: 'bare', name: 'Optical · a layer without scenes', restore: { ...restore, itemIds: [] } },
      { ...base, id: 'preview', name: 'Preview · NDVI', derived: 'preview', restore },
      { ...base, id: 'result', name: 'Result · Band math', derived: 'result', result: result({}), restore },
      { ...base, id: 'old', name: 'Result · expired and resampled', derived: 'result', result: result({ expired: true, resampled: true }), restore },
      { ...base, id: 'long', name: 'Optical · '.padEnd(200, 'long name '), restore },
    ];
    const rows = () => [...container.querySelectorAll('.layer-row')];
    const places = (row: Element) => [...row.children].map((c) => c.getAttribute('data-col'));

    beforeEach(() => {
      useAppStore.setState({ datasets: [], layers: kinds, dock: 'layers' });
      act(() => root.render(<LayerManager />));
    });

    it('have the nine places in the same order, whatever the kind of layer', () => {
      expect(rows()).toHaveLength(kinds.length);
      for (const row of rows()) {
        expect(places(row)).toEqual(['eye', 'name', 'opacity', 'up', 'down', 'process', 'download', 'note', 'remove']);
      }
    });

    it('keep every button at its place when the download or the note is missing', () => {
      const at = (id: string, col: string) => rows()[kinds.findIndex((k) => k.id === id)].querySelector(`[data-col="${col}"]`)!;
      // A layer without scenes, a preview: no download; the place is there and empty.
      for (const id of ['bare', 'preview']) {
        const empty = at(id, 'download');
        expect(empty.getAttribute('aria-hidden')).toBe('true');
        expect(empty.tagName).toBe('SPAN');
        expect(empty.textContent).toBe('');
        expect(empty.className).toBe('lm-slot');
      }
      expect(at('scene', 'download').tagName).toBe('BUTTON');
      expect(at('result', 'download').tagName).toBe('A');
      // The other buttons are the ones of every row, in the same class.
      for (const col of ['eye', 'up', 'down', 'remove']) {
        for (const row of rows()) expect(row.querySelector(`[data-col="${col}"]`)?.tagName).toBe('BUTTON');
      }
      // ⚙ is a button on every row; a result's is one where the browser keeps the order of its job (NM4-05b), and its place is empty
      // where it does not (these results have no job in the list).
      for (const k of kinds) {
        const gear = at(k.id, 'process');
        expect(gear.tagName).toBe(k.result ? 'SPAN' : 'BUTTON');
        expect(gear.getAttribute('aria-hidden') === 'true').toBe(Boolean(k.result));
      }
      expect(at('scene', 'note').className).toBe('lm-slot');
    });

    it('say their notes in a symbol with a tooltip, in the place of the note', () => {
      const note = rows()[kinds.findIndex((k) => k.id === 'old')].querySelector('[data-col="note"]')!;
      expect(note.className).toBe('lm-note');
      expect(note.querySelector('.tip')?.getAttribute('data-tip')).toBe(`${EXPIRED_LAYER_TEXT} ${RESAMPLED_LAYER_TEXT}`);
      // No text of a note lies in the row, which keeps its height.
      expect(rows()[kinds.findIndex((k) => k.id === 'old')].textContent).not.toContain('Resampled');
    });

    it('show the whole name in the tooltip of a name that is cut', () => {
      const name = rows()[kinds.length - 1].querySelector<HTMLElement>('[data-col="name"]')!;
      expect(name.getAttribute('title')).toContain(kinds[kinds.length - 1].name);
    });
  });
});

// NM4-27 (Otto, 27.10.2026): while a job is deleted its result stays in the list, locked and not drawn; "Restore" shows it
// again, and when the day is over the entry goes.
// NM4-50 (Otto, 28.10.2026): the switch of a layer is an eye, open while the layer is shown and struck through while it is
// hidden; the tooltip says what a click does.
describe('the eye of a layer', () => {
  const scene = (id: string, visible: boolean): MapLayer => ({
    id,
    name: id,
    visible,
    opacity: 1,
    overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
    restore: { datasetId: 'dem', itemIds: [] } as never,
  });
  const eye = (id: string) => container.querySelectorAll('.layer-row')[id === 'shown' ? 0 : 1].querySelector('[data-col="eye"]') as HTMLButtonElement;

  beforeEach(() => {
    useAppStore.setState({ layers: [scene('shown', true), scene('hidden', false)], dock: 'layers' });
    act(() => root.render(<LayerManager />));
  });

  it('is open for a shown layer and struck through for a hidden one, with a drawing and no text glyph', () => {
    expect(eye('shown').querySelector('svg')).not.toBeNull();
    expect(eye('shown').querySelectorAll('svg path')).toHaveLength(1);
    expect(eye('shown').classList.contains('off')).toBe(false);
    expect(eye('hidden').querySelectorAll('svg path')).toHaveLength(2);
    expect(eye('hidden').classList.contains('off')).toBe(true);
    expect(eye('shown').textContent).toBe('');
  });

  it('says "Hide layer" while shown and "Show layer" while hidden', () => {
    expect(eye('shown').getAttribute('title')).toBe(HIDE_LAYER_TIP);
    expect(eye('shown').getAttribute('aria-label')).toBe(HIDE_LAYER_TIP);
    expect(eye('hidden').getAttribute('title')).toBe(SHOW_LAYER_TIP);
    expect(eye('shown').getAttribute('aria-pressed')).toBe('true');
    expect(eye('hidden').getAttribute('aria-pressed')).toBe('false');
  });

  it('switches the layer with a click, and the eye follows', () => {
    act(() => eye('shown').click());
    expect(useAppStore.getState().layers.map((l) => l.visible)).toEqual([false, false]);
    expect(eye('shown').getAttribute('title')).toBe(SHOW_LAYER_TIP);
    expect(eye('shown').querySelectorAll('svg path')).toHaveLength(2);
    act(() => eye('hidden').click());
    expect(useAppStore.getState().layers.map((l) => l.visible)).toEqual([false, true]);
    expect(eye('hidden').getAttribute('title')).toBe(HIDE_LAYER_TIP);
  });
});

describe('the result layer of a deleted job', () => {
  const DAY = 86_400_000;
  const restore = { datasetId: 'ds', itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false } as unknown as MapLayer['restore'];
  const resultLayer = (id: string, job: string, over: object = {}): MapLayer => ({
    id,
    name: `Result · ${id}`,
    visible: true,
    opacity: 1,
    overlays: [],
    derived: 'result',
    restore,
    result: { jobID: job, expires: new Date(NOW + 7 * DAY).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, ...over },
  });
  const rows = () => [...container.querySelectorAll<HTMLElement>('.layer-row')];
  const deleteJobAt = (n: number, until: number) =>
    act(() => useProcessingStore.setState({ jobs: [jobEntry(n, { phase: 'dismissed', deletedUntil: new Date(until).toISOString(), serverDeleted: true })] }));

  beforeEach(() => {
    vi.useFakeTimers({ toFake: ['Date', 'setTimeout', 'clearTimeout'], now: NOW });
    resetJobs();
    useAppStore.setState({ datasets: [], layers: [resultLayer('a', jobId(1)), resultLayer('b', jobId(2))], dock: 'layers' });
    act(() => root.render(<LayerManager />));
  });

  afterEach(() => {
    resetJobs();
    vi.useRealTimers();
  });

  it('is locked once the job is deleted: the reason is the tooltip, the row says nothing', () => {
    deleteJobAt(1, NOW + DAY);
    const [locked, free] = rows();
    expect(locked.classList.contains('locked')).toBe(true);
    expect(free.classList.contains('locked')).toBe(false);
    const eye = locked.querySelector<HTMLElement>('[data-col="eye"]')!;
    expect(eye.getAttribute('title')).toBe(DELETED_LAYER_TIP);
    expect(eye.getAttribute('aria-disabled')).toBe('true');
    expect(DELETED_LAYER_TIP).toBe('Job deleted – restore to show');
    expect(locked.querySelector('[data-col="opacity"]')?.hasAttribute('disabled')).toBe(true);
    expect(locked.querySelector('[data-col="download"]')?.tagName).toBe('SPAN');
    expect(locked.querySelector('[data-col="note"]')?.className).toBe('lm-slot');
    expect(locked.textContent).not.toMatch(/delet|restore|job/iu);
    expect(useAppStore.getState().layers[0].result?.deleted).toBe(true);
    expect(useAppStore.getState().layers[1].result?.deleted).toBeFalsy();
  });

  it('keeps its nine places', () => {
    deleteJobAt(1, NOW + DAY);
    expect([...rows()[0].children].map((c) => c.getAttribute('data-col'))).toEqual(['eye', 'name', 'opacity', 'up', 'down', 'process', 'download', 'note', 'remove']);
  });

  it('cannot be switched on with the eye while it is locked, and can still be removed', () => {
    deleteJobAt(1, NOW + DAY);
    act(() => rows()[0].querySelector<HTMLElement>('[data-col="eye"]')!.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useAppStore.getState().layers[0].visible).toBe(true);
    act(() => rows()[0].querySelector<HTMLElement>('[data-col="remove"]')!.dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['b']);
  });

  it('is shown again, as it was, once the job is restored', () => {
    act(() => useAppStore.getState().toggleLayerVisible('a'));
    act(() => useAppStore.getState().toggleLayerVisible('a'));
    deleteJobAt(1, NOW + DAY);
    act(() => useProcessingStore.setState({ jobs: [jobEntry(1)] }));
    const layer = useAppStore.getState().layers[0];
    expect(layer.result?.deleted).toBe(false);
    expect(layer.visible).toBe(true);
    expect(rows()[0].classList.contains('locked')).toBe(false);
    expect(rows()[0].querySelector('[data-col="eye"]')?.getAttribute('title')).toBe('Hide layer');
  });

  it('goes from the list when the day is over, on the minute and not before', () => {
    deleteJobAt(1, NOW + 5000);
    expect(rows()).toHaveLength(2);
    act(() => {
      vi.advanceTimersByTime(4900);
    });
    expect(rows()).toHaveLength(2);
    act(() => {
      vi.advanceTimersByTime(400);
    });
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['b']);
    expect(rows()).toHaveLength(1);
  });

  it('is not there at all for a job whose day was over before the page was open', () => {
    deleteJobAt(1, NOW - 1000);
    expect(useAppStore.getState().layers.map((l) => l.id)).toEqual(['b']);
  });

  it('closes the view of the layer that goes', () => {
    act(() => useAppStore.setState({ resultViewLayerId: 'a' }));
    deleteJobAt(1, NOW - 1000);
    expect(useAppStore.getState().resultViewLayerId).toBeNull();
  });

  it('leaves the layers of other jobs, and a layer that is no result, alone', () => {
    const scene: MapLayer = { id: 'scene', name: 'Optical · scene', visible: true, opacity: 1, overlays: [], restore };
    act(() => useAppStore.setState({ layers: [resultLayer('a', jobId(1)), scene] }));
    deleteJobAt(2, NOW + DAY);
    expect(useAppStore.getState().layers.map((l) => [l.id, l.result?.deleted])).toEqual([['a', undefined], ['scene', undefined]]);
  });
});
