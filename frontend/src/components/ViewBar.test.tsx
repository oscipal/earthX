// @vitest-environment jsdom
//
// The two download buttons of the results view (M4-11b-2, Zusatz 1a): "Download
// crop" and "Download originals", always both, each disabled with its reason.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import type { DatasetOption } from '../datasets';
import { DRAW_AOI_TO_CROP } from '../download';
import { bboxToPolygon } from '../geoUtils';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import ViewBar from './ViewBar';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const AOI = bboxToPolygon([10.2, 50.2, 10.4, 50.4]);

function item(id: string): StacItem {
  return {
    id,
    collection: 'd',
    bbox: [10, 50, 11, 51],
    properties: { datetime: '2026-07-01T10:00:00Z' },
    assets: { visual: { href: `https://data.test/${id}.tif` } },
  };
}

function dataset(format: string): DatasetOption {
  return {
    id: 'd',
    title: 'Some dataset',
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 8, max: 14 },
    browse: 'quicklook',
    quicklookNodataMax: null,
    resultsGroupBy: ['datetime'],
    hasTimeAxis: true,
    collection: {
      id: 'd',
      'earthx:format': format,
      'earthx:default_render': { assets: ['visual'] },
      'earthx:source': { asset_hosts: ['data.test'] },
      'earthx:license_flags': { tier: 'processing' },
    } as unknown as Collection,
  };
}

function select(format: string, aoi: GeoJSON.Polygon | null) {
  const items = [item('A'), item('B')];
  useAppStore.setState({
    datasets: [dataset(format)],
    datasetId: 'd',
    items,
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items }],
    activeGroupIndex: 0,
    selectedIds: ['A', 'B'],
    aoi,
    downloadDialogLayerId: null,
    downloadSelection: false,
    downloadOutcome: null,
    error: null,
  });
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
  useAppStore.getState().closeDownloadDialog();
});

const button = (label: string) =>
  [...container.querySelectorAll('button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement;

function show() {
  act(() => root.render(<ViewBar />));
}

describe('the download buttons', () => {
  it.each([
    ['cog', AOI],
    ['cog', null],
    ['zarr', AOI],
    ['zarr', null],
  ])('are both there for a %s dataset with AOI %j', (format, aoi) => {
    select(format, aoi);
    show();
    expect(button('⇩ Download crop')).toBeDefined();
    expect(button('⇩ Download originals')).toBeDefined();
    expect(container.textContent).not.toMatch(/⇩ Download\s*$/u);
  });

  it('crop: disabled without an AOI, with the reason', () => {
    select('cog', null);
    show();
    expect(button('⇩ Download crop').disabled).toBe(true);
    expect(button('⇩ Download crop').title).toBe(DRAW_AOI_TO_CROP);
  });

  it('crop: open with an AOI, for a Zarr dataset too', () => {
    select('zarr', AOI);
    show();
    expect(button('⇩ Download crop').disabled).toBe(false);
  });

  it('originals: open for a COG dataset with and without an AOI', () => {
    for (const aoi of [null, AOI]) {
      select('cog', aoi);
      show();
      expect(button('⇩ Download originals').disabled).toBe(false);
    }
  });

  it('originals: disabled for Zarr, with the reason', () => {
    select('zarr', AOI);
    show();
    expect(button('⇩ Download originals').disabled).toBe(true);
    expect(button('⇩ Download originals').title).toContain('no single original file per scene');
  });

  it('each opens its own dialog: the crop, or the originals with an AOI drawn', () => {
    select('cog', AOI);
    show();
    act(() => button('⇩ Download crop').dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useAppStore.getState().downloadOutcome).toBe('crop');
    act(() => useAppStore.getState().closeDownloadDialog());
    act(() => button('⇩ Download originals').dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useAppStore.getState().downloadOutcome).toBe('originals');
    expect(useAppStore.getState().downloadOriginalLinks).toHaveLength(2);
  });
});
