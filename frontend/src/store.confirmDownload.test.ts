// @vitest-environment jsdom
//
// `confirmDownload` needs real DOM APIs (`document.createElement('a')`,
// `URL.createObjectURL`) to trigger the browser's save dialog — split into
// its own file with the jsdom pragma rather than switching `store.test.ts`'s
// whole suite over, so the (larger) rest of that file keeps running under
// the faster, dependency-free default environment.
//
// Review finding on M3-17: a group dropped for not touching the AOI at all
// has to be visible to the user, not only inside the ZIP's ATTRIBUTION.txt —
// `api/tiler.py::download_crop`'s `X-Total-Groups`/`X-Skipped-Groups`
// headers (api.ts::downloadCrop) are how the dialog finds out.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { useAppStore } from './store';
import type { Collection, StacItem } from './types';

const AOI: GeoJSON.Polygon = {
  type: 'Polygon',
  coordinates: [
    [
      [0, 40],
      [20, 40],
      [20, 55],
      [0, 55],
      [0, 40],
    ],
  ],
};

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

const COG_DATASET: Collection = {
  id: 'sentinel-2-c1-l2a',
  title: 'Sentinel-2 L2A',
  'earthx:capabilities': CAPABILITIES,
  'earthx:viewer': {
    group_by: ['datetime'],
    min_zoom: 0,
    max_zoom: 19,
    browse: 'quicklook',
    quicklook_nodata_max: 16,
    results_group_by: ['datetime'],
  },
  'earthx:format': 'cog',
  'earthx:license_flags': {
    spdx_id: null,
    name: 'Sentinel Data Legal Notice',
    url: 'https://example.org/legal-notice',
    commercial_use: true,
    distribution: true,
    derivatives: true,
    share_alike: false,
    attribution_required: true,
    tier: 'processing',
    attribution_modified: 'Contains modified Copernicus Sentinel data {year}',
    attribution_unmodified: 'Copernicus Sentinel data {year}',
    terms_url: null,
    terms_notice: null,
  },
  'earthx:default_render': {
    title: 'True colour',
    assets: ['visual'],
    rescale: null,
    colormap_name: null,
    expression: null,
    resampling: 'nearest',
  },
};

function cogScene(id: string): StacItem {
  return { id, properties: { datetime: '2026-07-24T10:00:00Z' }, assets: { visual: { href: `https://data.test/${id}.tif` } } };
}

function textResponse(status: number): Response {
  return { ok: status >= 200 && status < 300, status, statusText: 'x', json: async () => ({}) } as Response;
}

function zipResponse(headers: Record<string, string>): Response {
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    headers: new Headers(headers),
    blob: async () => new Blob(['zip-bytes']),
  } as unknown as Response;
}

describe('confirmDownload — the skipped-groups notice (review finding on M3-17)', () => {
  beforeEach(() => {
    const items = [cogScene('S1'), cogScene('S2')];
    useAppStore.setState({
      datasets: datasetsFrom([COG_DATASET]),
      datasetId: COG_DATASET.id,
      items,
      groups: [
        { key: ['a'], label: 'Overpass A', items: [items[0]] },
        { key: ['b'], label: 'Overpass B', items: [items[1]] },
      ],
      activeGroupIndex: 0,
      selectedIds: ['S1', 'S2'],
      aoi: AOI,
      downloadDialogLayerId: null,
      downloadSelection: false,
      downloadOutcome: null,
      downloadOriginalLinks: null,
      downloadSkippedGroupsNotice: null,
      downloading: false,
      error: null,
      notice: null,
    });
    useAppStore.getState().openDownloadForSelection();
    vi.stubGlobal('fetch', vi.fn());
    vi.stubGlobal('URL', Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('no group dropped: closes the dialog with the ordinary "Downloaded" notice', async () => {
    vi.mocked(fetch).mockResolvedValue(zipResponse({ 'X-Total-Groups': '2', 'X-Skipped-Groups': '0' }));

    await useAppStore.getState().confirmDownload();

    const s = useAppStore.getState();
    expect(s.downloadDialogLayerId).toBeNull();
    expect(s.downloadSelection).toBe(false);
    expect(s.downloadOutcome).toBeNull();
    expect(s.downloadSkippedGroupsNotice).toBeNull();
    expect(s.notice).toMatch(/^Downloaded /);
  });

  it('one group dropped: the dialog stays open with an English hint, singular wording', async () => {
    vi.mocked(fetch).mockResolvedValue(zipResponse({ 'X-Total-Groups': '3', 'X-Skipped-Groups': '1' }));

    await useAppStore.getState().confirmDownload();

    const s = useAppStore.getState();
    expect(s.downloadSelection).toBe(true); // still open
    expect(s.downloadSkippedGroupsNotice).toBe('1 of 3 groups did not overlap the AOI and was skipped.');
    expect(s.notice).toBeNull(); // not also raised as the ordinary notice
  });

  it('more than one group dropped: plural wording', async () => {
    vi.mocked(fetch).mockResolvedValue(zipResponse({ 'X-Total-Groups': '4', 'X-Skipped-Groups': '2' }));

    await useAppStore.getState().confirmDownload();

    expect(useAppStore.getState().downloadSkippedGroupsNotice).toBe(
      '2 of 4 groups did not overlap the AOI and were skipped.',
    );
  });

  it('closing the dialog after the hint clears it', async () => {
    vi.mocked(fetch).mockResolvedValue(zipResponse({ 'X-Total-Groups': '2', 'X-Skipped-Groups': '1' }));
    await useAppStore.getState().confirmDownload();
    expect(useAppStore.getState().downloadSkippedGroupsNotice).not.toBeNull();

    useAppStore.getState().closeDownloadDialog();

    const s = useAppStore.getState();
    expect(s.downloadSkippedGroupsNotice).toBeNull();
    expect(s.downloadDialogLayerId).toBeNull();
    expect(s.downloadSelection).toBe(false);
  });

  it('a download failure still reports the usual error, not the skip notice', async () => {
    vi.mocked(fetch).mockResolvedValue(textResponse(502));

    await useAppStore.getState().confirmDownload();

    const s = useAppStore.getState();
    expect(s.error).toMatch(/Download failed/);
    expect(s.downloadSkippedGroupsNotice).toBeNull();
    expect(s.downloadSelection).toBe(true); // dialog stays open to show the error
  });
});
