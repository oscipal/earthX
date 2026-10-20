// @vitest-environment jsdom
//
// M3-10 (Otto, 30.09.2026): the coverage map is switched in the control panel;
// the layer manager lists pinned layers only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from '../datasets';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';

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
    useAppStore.setState({ datasets, datasetId: 'optical', selectedDatasetIds: ['optical'], layers: [], layerManagerOpen: true });
    act(() => root.render(<LayerManager />));
    expect(container.textContent).not.toContain('Coverage');
    expect(container.querySelector('.coverage-row')).toBeNull();
    expect(container.textContent).toContain('No layers yet');
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
      useAppStore.setState({ datasets: [], layers: ['one', 'two', 'three', 'four', 'five'].map(layer), layerManagerOpen: true });
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
});
