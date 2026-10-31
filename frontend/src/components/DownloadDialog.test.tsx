// @vitest-environment jsdom
//
// Review finding on M3-17: the original files download straight from the
// source at the "Katalogeintrag" licence tier (KLAERUNGEN B11: "Link bzw.
// Weiterleitung zum Download bei der Quelle" is already what that tier
// permits, no "Processing" tier needed) — but the attribution the licence
// still requires has to actually reach the dialog, next to the links, not
// only exist as text somewhere in `download.ts`. This mounts the real
// component (not just its pure helpers, already covered in
// `download.test.ts`) to prove it renders. The dialog of the originals starts
// the download by itself when it opens (NM4-33); the browser part of that is
// replaced by `page` below, and the logic is tested in `originalsRun.test.ts`.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAppStore } from '../store';
import type { StacItem } from '../types';
import DownloadDialog from './DownloadDialog';

// What the page would do; recorded instead. The source lets the page read nothing here (no `cors` in the collection),
// so every file is a download of the browser.
const page = vi.hoisted(() => ({ navigated: [] as string[], saved: [] as string[], disposed: 0 }));
vi.mock('../originalsClient', () => ({
  canStream: () => false,
  browserDeps: () => ({
    deps: {
      fetch: async () => new Response(null),
      zip: null,
      saveBlob: (name: string) => page.saved.push(name),
      navigate: (href: string) => page.navigated.push(href),
      now: () => new Date('2026-10-20T12:00:00Z'),
    },
    dispose: () => {
      page.disposed += 1;
    },
  }),
}));

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  page.navigated.length = 0;
  page.saved.length = 0;
  page.disposed = 0;
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  // "The year of today" below is 2026.
  vi.useFakeTimers({ toFake: ['Date'], now: Date.parse('2026-10-20T12:00:00Z') });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
  vi.useRealTimers();
});

function scene(id: string, properties: Record<string, unknown>): StacItem {
  return { id, properties, assets: { visual: { href: `https://data.test/${id}.tif`, roles: ['visual'] } } };
}

function show(): HTMLElement {
  act(() => {
    root.render(<DownloadDialog />);
  });
  return container;
}

describe('the originals dialog shows attribution and terms next to the links', () => {
  beforeEach(() => {
    useAppStore.setState({
      datasets: [
        {
          id: 'sentinel-2-c1-l2a',
          title: 'Sentinel-2 L2A',
          viewable: true,
          groupBy: ['datetime'],
          zoom: { min: 0, max: 19 },
          browse: 'quicklook',
          quicklookNodataMax: 16,
          resultsGroupBy: ['datetime'],
          hasTimeAxis: true,
          collection: {
            id: 'sentinel-2-c1-l2a',
            title: 'Sentinel-2 L2A',
            'earthx:format': 'cog',
            'earthx:source': { asset_hosts: ['data.test'] },
            'earthx:band_units': { visual: null },
            'earthx:auxiliary_assets': ['visual'],
            'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
            'earthx:license_flags': {
              spdx_id: null,
              name: 'Sentinel Data Legal Notice',
              url: 'https://example.org/legal-notice',
              commercial_use: true,
              distribution: true,
              derivatives: true,
              share_alike: false,
              attribution_required: true,
              tier: 'catalog',
              attribution_modified: 'Contains modified Copernicus Sentinel data {year}',
              attribution_unmodified: 'Copernicus Sentinel data {year}',
              terms_url: 'https://example.org/legal-notice',
              terms_notice: { en: 'Subject to {terms_url}.' },
            },
          },
        },
      ],
      datasetId: 'sentinel-2-c1-l2a',
      downloadDialogLayerId: null,
      downloadSelection: true,
      downloadOutcome: 'originals',
      downloadSkippedGroupsNotice: null,
      downloadOriginalLinks: [
        { itemId: 'S1', groupLabel: 'Overpass A', asset: 'visual', href: 'https://data.test/S1.tif' },
      ],
      downloadPasses: [{ label: 'Overpass A', items: [scene('S1', { datetime: '2025-07-29T10:15:00Z' })] }],
      downloading: false,
      error: null,
      notice: null,
    });
  });

  it('shows the unmodified attribution text (not the modified one), never a licence-tier gate', () => {
    const el = show();
    const text = el.textContent ?? '';
    expect(text).toContain('Copernicus Sentinel data 2025');
    expect(text).not.toContain('Contains modified Copernicus Sentinel data');
    // Katalogeintrag: B11 already permits a link at this tier — no
    // "licence does not permit a data export" message, no disabled Download
    // button gate as the crop view has.
    expect(text).not.toContain('does not permit a data export');
  });

  it('names the year of the scenes, not the year of today (NM4-01)', () => {
    useAppStore.setState({
      downloadPasses: [
        { label: 'A', items: [scene('S1', { datetime: '2024-12-30T10:00:00Z' })] },
        { label: 'B', items: [scene('S2', { datetime: '2025-01-02T10:00:00Z' })] },
      ],
    });
    expect(show().textContent).toContain('Copernicus Sentinel data 2024\u20132025');
    expect(show().textContent).not.toContain(String(new Date().getFullYear()));
  });

  it('shows no attribution rather than a guessed year for a scene without a date', () => {
    useAppStore.setState({ downloadPasses: [{ label: 'A', items: [scene('S1', {})] }] });
    const text = show().textContent ?? '';
    expect(text).not.toContain('Copernicus Sentinel data');
    expect(text).toContain('Subject to');
  });

  it('shows the terms notice and the terms URL', () => {
    const el = show();
    expect(el.textContent).toContain('Subject to https://example.org/legal-notice.');
  });

  it('renders each original file as its own clickable, direct link', () => {
    const el = show();
    const link = el.querySelector<HTMLAnchorElement>('a[href="https://data.test/S1.tif"]');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('download')).not.toBeNull();
    expect(link?.getAttribute('rel')).toContain('noopener');
    expect(link?.textContent).toContain('S1');
    expect(link?.textContent).toContain('visual');
  });

  it('loading (fetch for a pinned layer still in flight) says so instead of an empty list', () => {
    useAppStore.setState({ downloadOriginalLinks: null });
    const el = show();
    expect(el.textContent).toContain('Loading the original files');
  });

  it('no reachable link at all says so, plainly, rather than showing nothing', () => {
    useAppStore.setState({
      downloadOriginalLinks: [],
      downloadPasses: [{ label: 'Overpass A', items: [{ id: 'S1', properties: { datetime: '2025-07-29T10:15:00Z' }, assets: {} }] }],
    });
    const el = show();
    expect(el.textContent).toContain('No original file');
    expect(page.navigated).toEqual([]);
  });
});

describe('the crop dialog (NM4-01)', () => {
  it('shows no attribution line and no year: the file in the ZIP carries the text', () => {
    useAppStore.setState({
      downloadOutcome: 'crop',
      downloadOriginalLinks: null,
      downloadPasses: null,
      selectedIds: ['S1'],
      items: [scene('S1', { datetime: '2025-07-29T10:15:00Z' })],
    });
    const text = show().textContent ?? '';
    expect(text).toContain('Download crop');
    expect(text).not.toContain('Copernicus Sentinel data');
    expect(text).toContain('Subject to');
  });
});

// Last: the store is global, and the crop dialog above reads what the first describe left in it.
describe('the originals dialog starts by itself (NM4-33)', () => {
  beforeEach(() => {
    useAppStore.setState({
      datasets: [
        {
          id: 'sentinel-2-c1-l2a',
          title: 'Sentinel-2 L2A',
          viewable: true,
          groupBy: ['datetime'],
          zoom: { min: 0, max: 19 },
          browse: 'quicklook',
          quicklookNodataMax: 16,
          resultsGroupBy: ['datetime'],
          hasTimeAxis: true,
          collection: {
            id: 'sentinel-2-c1-l2a',
            'earthx:format': 'cog',
            'earthx:source': { asset_hosts: ['data.test'] },
            'earthx:band_units': { visual: null },
            'earthx:auxiliary_assets': ['visual'],
            'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
            'earthx:license_flags': {
              spdx_id: null,
              name: 'Sentinel Data Legal Notice',
              url: 'https://example.org/legal-notice',
              commercial_use: true,
              distribution: true,
              derivatives: true,
              share_alike: false,
              attribution_required: true,
              tier: 'catalog',
              attribution_modified: null,
              attribution_unmodified: 'Copernicus Sentinel data {year}',
              terms_url: null,
              terms_notice: null,
            },
          },
        },
      ],
      datasetId: 'sentinel-2-c1-l2a',
      downloadDialogLayerId: null,
      downloadSelection: true,
      downloadOutcome: 'originals',
      downloadSkippedGroupsNotice: null,
      downloadOriginalLinks: [],
      downloadPasses: [{ label: 'A', items: [scene('S1', { datetime: '2025-07-29T10:15:00Z' })] }],
      downloading: false,
      error: null,
      notice: null,
    });
  });

  it('opens without a question and hands every file to the download, with ATTRIBUTION.txt first', async () => {
    const el = show();
    await act(async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    expect(el.textContent).not.toContain('How do you want');
    expect(page.saved).toEqual(['sentinel-2-c1-l2a_ATTRIBUTION.txt']);
    expect(page.navigated).toEqual(['https://data.test/S1.tif']);
    expect(el.querySelector('.dialog-original-row')?.textContent).toContain('Started in your browser');
  });

  it('is titled for one scene or for several', () => {
    expect(show().querySelector('h2')?.textContent).toBe('Download full scene');
    useAppStore.setState({
      downloadPasses: [{ label: 'A', items: [scene('S1', { datetime: '2025-07-29T10:15:00Z' }), scene('S2', { datetime: '2025-07-29T10:15:00Z' })] }],
    });
    expect(show().querySelector('h2')?.textContent).toBe('Download full scenes');
  });

  it('says in a tooltip that closing stops a download that is running', () => {
    expect(show().querySelector('.results-head button')?.getAttribute('title')).toContain('stops a download');
  });

  it('closing the dialog frees what the page put into itself for the downloads', () => {
    show();
    act(() => useAppStore.getState().closeDownloadDialog());
    expect(page.disposed).toBeGreaterThanOrEqual(1);
  });

  it('a scene without a date: nothing is downloaded, and the row says why (NM4-01)', async () => {
    useAppStore.setState({ downloadPasses: [{ label: 'A', items: [scene('S1', {})] }] });
    const el = show();
    await act(async () => {
      for (let i = 0; i < 10; i++) await Promise.resolve();
    });
    expect(page.saved).toEqual([]);
    expect(page.navigated).toEqual([]);
    expect(el.querySelector('.dialog-original-row')?.textContent).toContain('no acquisition date');
  });
});
