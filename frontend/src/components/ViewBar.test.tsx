// @vitest-environment jsdom
//
// The bar of the selection. The two download buttons (M4-11b-2, Zusatz 1a), always both, each disabled with
// its reason; UI-01g: the buttons name what they do for one scene or for several, none says "Full resolution"
// or "Clear", and they are one size.

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
    expect(button('⇩ Download merged crop')).toBeDefined();
    expect(button('⇩ Download full scenes')).toBeDefined();
    expect([...container.querySelectorAll('button')].map((b) => b.textContent)).not.toContain('⇩ Download');
  });

  it('crop: disabled without an AOI, with the reason', () => {
    select('cog', null);
    show();
    expect(button('⇩ Download merged crop').disabled).toBe(true);
    expect(button('⇩ Download merged crop').title).toBe(DRAW_AOI_TO_CROP);
  });

  it('crop: open with an AOI, for a Zarr dataset too', () => {
    select('zarr', AOI);
    show();
    expect(button('⇩ Download merged crop').disabled).toBe(false);
  });

  it('originals: open for a COG dataset with and without an AOI', () => {
    for (const aoi of [null, AOI]) {
      select('cog', aoi);
      show();
      expect(button('⇩ Download full scenes').disabled).toBe(false);
    }
  });

  it('originals: disabled for Zarr, with the reason', () => {
    select('zarr', AOI);
    show();
    expect(button('⇩ Download full scenes').disabled).toBe(true);
    expect(button('⇩ Download full scenes').title).toContain('no single original file per scene');
  });

  it('each opens its own dialog: the crop, or the originals with an AOI drawn', () => {
    select('cog', AOI);
    show();
    act(() => button('⇩ Download merged crop').dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useAppStore.getState().downloadOutcome).toBe('crop');
    act(() => useAppStore.getState().closeDownloadDialog());
    act(() => button('⇩ Download full scenes').dispatchEvent(new MouseEvent('click', { bubbles: true })));
    expect(useAppStore.getState().downloadOutcome).toBe('originals');
    expect(useAppStore.getState().downloadOriginalLinks).toHaveLength(2);
  });
});

describe('the labels of the bar (UI-01g)', () => {
  const labels = () => [...container.querySelectorAll('button')].map((b) => b.textContent?.trim());

  it('name the action for one scene', () => {
    select('cog', AOI);
    act(() => useAppStore.setState({ selectedIds: ['A'] }));
    show();
    expect(labels()).toEqual(['Crop to AOI', 'View whole scene', '＋ Add to layers', '⇩ Download crop', '⇩ Download full scene', '⚙ Process']);
  });

  it('say "merged" for several scenes', () => {
    select('cog', AOI);
    show();
    expect(labels()).toEqual([
      'Crop & merge to AOI',
      'View merged scenes',
      '＋ Add to layers',
      '⇩ Download merged crop',
      '⇩ Download full scenes',
      '⚙ Process',
    ]);
  });

  it('have no "Full resolution" label and no "Clear", for one scene or for several', () => {
    for (const selectedIds of [['A'], ['A', 'B']]) {
      select('cog', AOI);
      act(() => useAppStore.setState({ selectedIds }));
      show();
      expect(container.textContent).not.toContain('Full resolution');
      expect(labels()).not.toContain('Clear');
    }
  });

  it('say in their tooltips that the view and the downloads are at full resolution', () => {
    select('cog', AOI);
    show();
    expect(button('Crop & merge to AOI').title).toContain('full resolution');
    expect(button('View merged scenes').title).toContain('full resolution');
    expect(button('⇩ Download merged crop').title).toContain('full resolution');
  });

  it('put the number above its label, so the count has one box whether it says "scene" or "scenes"', () => {
    select('cog', AOI);
    act(() => useAppStore.setState({ selectedIds: ['A'] }));
    show();
    const count = () => [container.querySelector('.download-count strong')?.textContent, container.querySelector('.download-count span')?.textContent];
    expect(count()).toEqual(['1', 'scene selected']);
    act(() => useAppStore.setState({ selectedIds: ['A', 'B'] }));
    expect(count()).toEqual(['2', 'scenes selected']);
    expect(container.querySelectorAll('.download-count')).toHaveLength(1);
  });

  it('are one size: no button sets a width or height of its own', () => {
    select('cog', AOI);
    show();
    for (const b of container.querySelectorAll('button')) {
      expect(b.getAttribute('style')).toBeNull();
      expect(['primary-btn', 'ghost-btn']).toContain(b.className);
    }
  });
});
