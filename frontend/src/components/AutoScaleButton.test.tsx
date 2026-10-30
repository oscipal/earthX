// @vitest-environment jsdom
//
// Otto, 30.10.2026 (zu #234): "auto-scale" is one button: the same name, size and look in the view of scenes and in the
// settings of a result, from one component.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from '../datasets';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import AutoScaleButton from './AutoScaleButton';
import ResultControls from './ResultControls';
import ViewerControls from './ViewerControls';
import resultSource from './ResultControls.tsx?raw';
import viewSource from './ViewerControls.tsx?raw';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

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

const resultLayer = (): MapLayer => ({
  id: 'R1',
  name: 'Result · Band math',
  visible: true,
  opacity: 1,
  derived: 'result',
  overlays: [{ kind: 'raster', tileUrl: '/results/x/tiles/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=1%2C9', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }],
  result: { jobID: 'J', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null },
  restore: { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null },
});

const collection = {
  id: 'optical',
  title: 'Optical',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
};

const autoScale = () => [...container.querySelectorAll('button')].filter((b) => b.textContent?.trim() === 'auto-scale');

describe('"auto-scale"', () => {
  it('is one button in the view of scenes and in the settings of a result: the same name, the same classes', () => {
    act(() => {
      useAppStore.setState({
        datasets: datasetsFrom([collection] as never), datasetId: 'optical', focusMode: true, cropToAoi: false, showDownloaded: true, groups: [], selectedIds: [],
        downloaded: { s0: { tileUrl: '/t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], asset: 'visual', minZoom: 0, maxZoom: 14 } },
        pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', focusLoading: false, resultViewLayerId: null, layers: [],
      });
      root.render(<ViewerControls />);
    });
    const inView = autoScale();
    expect(inView).toHaveLength(1);
    act(() => root.unmount());
    root = createRoot(container);
    act(() => {
      useAppStore.setState({ layers: [resultLayer()], resultViewLayerId: 'R1', focusMode: false });
      root.render(<ResultControls />);
    });
    const inResult = autoScale();
    expect(inResult).toHaveLength(1);
    expect(inResult[0].className).toBe(inView[0].className);
    expect(inResult[0].textContent).toBe(inView[0].textContent);
    expect(inResult[0].closest('.vc-buttons')).not.toBeNull();
    expect(inView[0].closest('.vc-buttons')).not.toBeNull();
  });

  it('is made by the component in both places, and neither has a button of its own with that name', () => {
    for (const [file, source] of [['ViewerControls.tsx', viewSource], ['ResultControls.tsx', resultSource]]) {
      expect(source, file).toContain("import AutoScaleButton from './AutoScaleButton'");
      expect(source, file).toContain('<AutoScaleButton');
      expect(source, file).not.toMatch(/>\s*auto(-scale)?\s*</u);
      expect(source, file).not.toContain('vc-auto');
    }
  });

  it('is locked while it is busy, and asks what it was asked to', () => {
    const asked: string[] = [];
    act(() => root.render(<AutoScaleButton title="Measure" busy onClick={() => asked.push('x')} />));
    const button = container.querySelector('button')!;
    expect(button.disabled).toBe(true);
    act(() => root.render(<AutoScaleButton title="Measure" onClick={() => asked.push('x')} />));
    act(() => container.querySelector('button')!.click());
    expect(asked).toEqual(['x']);
  });
});
