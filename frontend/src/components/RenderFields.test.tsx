// @vitest-environment jsdom
//
// NM4-65 part 6 (Otto, 31.10.2026): the fields that say how a picture is drawn come in one order and under one set of
// names wherever they are — Band · Index · vmin · vmax · colormap — from one component, not a variant per place. The
// processing preview ("Band", not "Show"; "vmin"/"vmax", not "min"/"max") is pinned by `ProcessingShow.test.tsx`, the
// view of scenes by `ViewerControls.test.tsx` and `ViewIndex.test.tsx`; here the component itself and the settings of a
// result layer.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MapLayer } from '../layers';
import { RGB } from '../processingBands';
import { useAppStore } from '../store';
import RenderFields from './RenderFields';
import ResultControls from './ResultControls';

vi.mock('./MapView', () => ({ default: () => null }));

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
  useAppStore.setState({ layers: [], resultViewLayerId: null });
});

const names = () => [...container.querySelectorAll('.vc-field > span')].map((span) => span.textContent);
const noop = () => undefined;

describe('RenderFields', () => {
  it('puts every field in the order Band · Index · vmin · vmax · Colormap', () => {
    act(() =>
      root.render(
        <RenderFields
          band={{ value: 'red', options: [{ value: 'red', label: 'red' }], onChange: noop }}
          index={{ value: '', options: [{ name: 'NDVI', tip: 'Vegetation' }], tip: 'Index', onChange: noop }}
          vmin={{ value: '0', onChange: noop }}
          vmax={{ value: '1', onChange: noop }}
          colormap={{ value: 'viridis', onChange: noop }}
        />,
      ),
    );
    expect(names()).toEqual(['Band', 'Index', 'vmin', 'vmax', 'Colormap']);
  });

  it('leaves out a field a place does not offer and keeps the order of the rest', () => {
    act(() => root.render(<RenderFields vmin={{ value: '', onChange: noop }} vmax={{ value: '', onChange: noop }} colormap={null} />));
    expect(names()).toEqual(['vmin', 'vmax']);
    act(() =>
      root.render(
        <RenderFields
          index={{ value: 'NDVI', options: [{ name: 'NDVI', tip: '' }], tip: '', onChange: noop }}
          vmin={{ value: '', onChange: noop }}
          vmax={{ value: '', onChange: noop }}
          colormap={{ fixed: 'RGB', title: 'True colour' }}
        />,
      ),
    );
    expect(names()).toEqual(['Index', 'vmin', 'vmax', 'Colormap']);
    expect(container.querySelector('select[title="True colour"] option')?.textContent).toBe('RGB');
  });

  it('never calls the ends "min" and "max"', () => {
    act(() => root.render(<RenderFields vmin={{ value: '', onChange: noop }} vmax={{ value: '', onChange: noop }} colormap={null} />));
    expect(names()).not.toContain('min');
    expect(names()).not.toContain('max');
  });

  it('keeps a note beside vmax (the unit of the range in the preview) in the same place', () => {
    act(() =>
      root.render(<RenderFields vmin={{ value: '', onChange: noop }} vmax={{ value: '', onChange: noop, after: <span className="pp-unit">m</span> }} colormap={null} />),
    );
    const bound = container.querySelector('.pp-bound')!;
    expect(bound.querySelector('.vc-field > span')?.textContent).toBe('vmax');
    expect(bound.querySelector('.pp-unit')?.textContent).toBe('m');
  });

  it('reports what is typed and chosen', () => {
    const calls: string[] = [];
    act(() =>
      root.render(
        <RenderFields
          vmin={{ value: '', onChange: (v) => calls.push(`vmin=${v}`) }}
          vmax={{ value: '', onChange: (v) => calls.push(`vmax=${v}`) }}
          colormap={{ value: '', onChange: (v) => calls.push(`colormap=${v}`) }}
          index={{ value: '', options: [{ name: 'NDVI', tip: '' }], tip: '', onChange: (v) => calls.push(`index=${v}`) }}
        />,
      ),
    );
    const type = (el: HTMLInputElement | HTMLSelectElement, value: string) =>
      act(() => {
        const proto = el instanceof HTMLSelectElement ? HTMLSelectElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value')!.set!.call(el, value);
        el.dispatchEvent(new Event(el instanceof HTMLSelectElement ? 'change' : 'input', { bubbles: true }));
      });
    const [index, colormap] = [...container.querySelectorAll('select')];
    const [vmin, vmax] = [...container.querySelectorAll('input')];
    type(vmin, '2');
    type(vmax, '9');
    type(colormap, 'turbo');
    type(index, 'NDVI');
    type(index, '');
    expect(calls).toEqual(['vmin=2', 'vmax=9', 'colormap=turbo', 'index=NDVI', 'index=null']);
  });
});

const layer = (band: number | typeof RGB, colour = true): MapLayer => ({
  id: 'R1',
  name: 'Result · bands',
  visible: true,
  opacity: 1,
  derived: 'result',
  overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
  result: {
    jobID: 'AbCdEfGhIjKlMnOpQrSt_-',
    expires: new Date(Date.now() + 86_400_000).toISOString(),
    gsd: 10,
    resampled: null,
    expired: false,
    dataType: 'float32',
    stats: null,
    bands: [
      { name: 'red', stats: null },
      { name: 'green', stats: null },
      { name: 'blue', stats: null },
    ],
    band,
    colour: colour ? [0, 1, 2] : undefined,
  },
  restore: { datasetId: null, itemIds: [] } as never,
});

describe('the settings of a result layer', () => {
  it('read Band · vmin · vmax · Colormap, like the preview and the view', () => {
    useAppStore.setState({ layers: [layer(1)], resultViewLayerId: 'R1' });
    act(() => root.render(<ResultControls />));
    expect(names()).toEqual(['Band', 'vmin', 'vmax', 'Colormap', 'Opacity']);
    expect(container.querySelector<HTMLSelectElement>('.band-select select')!.value).toBe('1');
  });

  it('keep the colormap in its place for "RGB", locked, and the band dropdown offers it first (NM4-54 part 5)', () => {
    useAppStore.setState({ layers: [layer(RGB)], resultViewLayerId: 'R1' });
    act(() => root.render(<ResultControls />));
    expect(names()).toEqual(['Band', 'vmin', 'vmax', 'Colormap', 'Opacity']);
    const colormap = [...container.querySelectorAll<HTMLLabelElement>('label.vc-field')].find((l) => l.querySelector('span')?.textContent === 'Colormap')!;
    expect(colormap.querySelector('select')!.disabled).toBe(true);
    expect(colormap.querySelector('select')!.selectedOptions[0].textContent).toBe('— none —');
    expect(colormap.title).toBe('True colour: three bands, no colormap');
    expect([...container.querySelectorAll<HTMLOptionElement>('.band-select option')].map((o) => o.textContent)).toEqual(['RGB', 'red', 'green', 'blue']);
  });

  it('have no band dropdown for a result of one band', () => {
    const one = layer(0, false);
    one.result!.bands = [{ name: 'data', stats: null }];
    useAppStore.setState({ layers: [one], resultViewLayerId: 'R1' });
    act(() => root.render(<ResultControls />));
    expect(names()).toEqual(['vmin', 'vmax', 'Colormap', 'Opacity']);
  });
});
