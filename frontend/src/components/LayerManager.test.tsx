// @vitest-environment jsdom
//
// M3-10 (Otto, 30.09.2026): the coverage map is switched in the control panel;
// the layer manager lists pinned layers only.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from '../datasets';
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
});
