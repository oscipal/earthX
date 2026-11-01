// @vitest-environment jsdom
//
// NM4-65 part 5 (Otto, 31.10.2026): in the settings of a layer that was clicked, the opacity slider could not be pushed
// all the way to the right, and showed less than the layer manager did at opacity 1. The value was right (1); the picture
// was not: `.vc-field input` gave the slider the padding and the frame of a text box, which shrank its track inside its
// own box. jsdom has no layout, so the test reads what the DOM holds and what the CSS promises off `index.css`.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import CSS from '../index.css?raw';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';
import ResultControls from './ResultControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const layer = (opacity: number): MapLayer => ({
  id: 'R1',
  name: 'Result · Band math',
  visible: true,
  opacity,
  derived: 'result',
  overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/{z}/{x}/{y}?colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
  result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null },
  restore: { datasetId: null, itemIds: [] } as never,
});

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

const rule = (selector: string): string => {
  const start = CSS.indexOf(`\n${selector} {`);
  expect(start, `no rule for ${selector}`).toBeGreaterThanOrEqual(0);
  return CSS.slice(start, CSS.indexOf('}', start));
};

describe('the opacity slider in the settings of a layer', () => {
  it('holds the same value as the slider of the row, and reaches the end of its scale at opacity 1', () => {
    useAppStore.setState({ layers: [layer(1)], resultViewLayerId: 'R1' });
    act(() => root.render(<><LayerManager /><ResultControls /></>));
    const inRow = container.querySelector<HTMLInputElement>('.layer-row input[type="range"]')!;
    const inSettings = container.querySelector<HTMLInputElement>('.result-controls input[type="range"]')!;
    expect(inSettings.value).toBe(inRow.value);
    expect(inSettings.value).toBe('1');
    expect(inSettings.max).toBe(inRow.max);
    expect(inSettings.title).toBe('Opacity 100%');
  });

  it('is moved to 1 by the keyboard and the store keeps exactly 1 (the way Otto reached it)', () => {
    useAppStore.setState({ layers: [layer(0.95)], resultViewLayerId: 'R1' });
    act(() => root.render(<ResultControls />));
    const slider = container.querySelector<HTMLInputElement>('.result-controls input[type="range"]')!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(slider, '1');
      slider.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(useAppStore.getState().layers[0].opacity).toBe(1);
    expect(container.querySelector<HTMLInputElement>('.result-controls input[type="range"]')!.value).toBe('1');
  });

  it('has no padding and no frame of its own, so the track fills its box (the cause was `.vc-field input`)', () => {
    // The generic rule that caused it is still there for text boxes…
    expect(rule('.vc-field select,\n.vc-field input,\n.vc-field textarea,\n.vc-dataset')).toContain('padding: 6px 8px');
    // …and the slider is taken out of it, by a rule that is later and more specific.
    const own = rule(".vc-field input[type='range']");
    expect(own).toContain('padding: 0');
    expect(own).toContain('border: 0');
    expect(own).toContain('background: none');
    expect(CSS.indexOf(".vc-field input[type='range'] {")).toBeGreaterThan(CSS.indexOf('.vc-field select,\n.vc-field input,'));
  });

  it('keeps a visible focus ring now that the frame is gone', () => {
    expect(rule(".vc-field input[type='range']:focus-visible")).toContain('outline: 2px solid var(--accent)');
  });
});

// Otto, 1.11.2026 (Browsertest zu #272): the opacity is kept with "Save" only; closing the settings without it puts the saved one back.
describe('the opacity of a result whose settings are open', () => {
  it('is seen at once and kept with "Save"', () => {
    useAppStore.setState({ layers: [layer(1)], resultViewLayerId: 'R1' });
    act(() => root.render(<ResultControls />));
    act(() => useAppStore.getState().setLayerOpacity('R1', 0.4));
    expect(useAppStore.getState().layers[0]).toMatchObject({ opacity: 0.4, saved: { opacity: 1 } });
    const save = container.querySelector('.vc-save') as HTMLButtonElement;
    expect(save.getAttribute('aria-disabled')).toBeNull();
    act(() => save.click());
    expect(useAppStore.getState().layers[0].saved).toBeUndefined();
    act(() => useAppStore.getState().closeResultView());
    expect(useAppStore.getState().layers[0].opacity).toBe(0.4);
  });

  it('goes back to the saved one when the settings close without it: the x, Esc, another layer', () => {
    useAppStore.setState({ layers: [layer(1), { ...layer(0.8), id: 'R2' }], resultViewLayerId: 'R1' });
    act(() => root.render(<ResultControls />));
    act(() => useAppStore.getState().setLayerOpacity('R1', 0.2));
    act(() => useAppStore.getState().closeResultView());
    expect(useAppStore.getState().layers[0].opacity).toBe(1);
    expect(useAppStore.getState().layers[0].saved).toBeUndefined();
    // Esc.
    useAppStore.setState({ resultViewLayerId: 'R1' });
    act(() => root.render(<ResultControls />));
    act(() => useAppStore.getState().setLayerOpacity('R1', 0.2));
    act(() => void document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(useAppStore.getState().resultViewLayerId).toBeNull();
    expect(useAppStore.getState().layers[0].opacity).toBe(1);
    // Another layer.
    useAppStore.setState({ resultViewLayerId: 'R1' });
    act(() => useAppStore.getState().setLayerOpacity('R1', 0.2));
    act(() => useAppStore.getState().selectLayer('R2'));
    expect(useAppStore.getState().layers.map((l) => l.opacity)).toEqual([1, 0.8]);
  });

  it('is not set aside for a layer whose settings are not open', () => {
    useAppStore.setState({ layers: [layer(1)], resultViewLayerId: null });
    act(() => useAppStore.getState().setLayerOpacity('R1', 0.5));
    expect(useAppStore.getState().layers[0].opacity).toBe(0.5);
    expect(useAppStore.getState().layers[0].saved).toBeUndefined();
  });
});
