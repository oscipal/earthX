import { describe, expect, it } from 'vitest';

import type { DatasetOption } from './datasets';
import {
  attributionText,
  canDownloadLayer,
  canExportLicense,
  downloadRequestFor,
  termsNoticeText,
} from './download';
import type { LayerRestore, MapLayer } from './layers';
import type { Collection, LicenseFlags } from './types';

const AOI: GeoJSON.Geometry = {
  type: 'Polygon',
  coordinates: [
    [
      [10, 47],
      [11, 47],
      [11, 48],
      [10, 48],
      [10, 47],
    ],
  ],
};

function restore(overrides: Partial<LayerRestore> = {}): LayerRestore {
  return {
    focusMode: true,
    downloaded: { S2A_1: { tileUrl: 't', bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 0, maxZoom: 19 } },
    appliedRender: {},
    activeGroupIndex: 0,
    selectedIds: ['S2A_1'],
    itemIds: ['S2A_1'],
    aoi: AOI,
    cropToAoi: true,
    datasetId: 'sentinel-2-l2a',
    ...overrides,
  };
}

function layer(overrides: Partial<LayerRestore> = {}): MapLayer {
  return {
    id: 'L1',
    name: 'test layer',
    visible: true,
    opacity: 1,
    overlays: [],
    restore: restore(overrides),
  };
}

function collection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: 'sentinel-2-l2a',
    title: 'Sentinel-2 L2A',
    'earthx:default_render': {
      title: 'True color',
      assets: ['visual'],
      rescale: null,
      colormap_name: null,
      expression: null,
      resampling: 'nearest',
    },
    ...overrides,
  };
}

function dataset(overrides: Partial<DatasetOption> = {}): DatasetOption {
  return {
    id: 'sentinel-2-l2a',
    title: 'Sentinel-2 L2A',
    collection: collection(),
    viewable: true,
    groupBy: ['datetime'],
    zoom: { min: 0, max: 19 },
    ...overrides,
  } as DatasetOption;
}

const DATASETS = [dataset()];

describe('downloadRequestFor', () => {
  it('builds items/assets/aoi from a full-resolution layer', () => {
    const req = downloadRequestFor(layer(), DATASETS);
    expect(req).toEqual({
      datasetId: 'sentinel-2-l2a',
      items: ['S2A_1'],
      assets: ['visual'],
      aoi: AOI,
    });
  });

  it('deduplicates the asset across several pinned items', () => {
    const req = downloadRequestFor(
      layer({
        itemIds: ['S2A_1', 'S2A_2'],
        downloaded: {
          S2A_1: { tileUrl: 't1', bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 0, maxZoom: 19 },
          S2A_2: { tileUrl: 't2', bounds: [11, 47, 12, 48], asset: 'visual', minZoom: 0, maxZoom: 19 },
        },
      }),
      DATASETS,
    );
    expect(req?.items).toEqual(['S2A_1', 'S2A_2']);
    expect(req?.assets).toEqual(['visual']);
  });

  // V-6: a quicklook-only layer (pinned straight from the results list,
  // never viewed at full resolution) can now be downloaded too, over the
  // dataset's default visualisation asset — same reasoning as
  // downloadRequestForSelection.
  it('falls back to the dataset default render asset for a quicklook-only layer', () => {
    const req = downloadRequestFor(layer({ focusMode: false, downloaded: {} }), DATASETS);
    expect(req).toEqual({
      datasetId: 'sentinel-2-l2a',
      items: ['S2A_1'],
      assets: ['visual'],
      aoi: AOI,
    });
  });

  it('returns null for a quicklook-only layer whose dataset has no default render', () => {
    const noRender = [dataset({ collection: collection({ 'earthx:default_render': null }) })];
    expect(downloadRequestFor(layer({ focusMode: false, downloaded: {} }), noRender)).toBeNull();
  });

  it('returns null for a quicklook-only layer whose dataset is not viewable', () => {
    const notViewable = [
      { id: 'sentinel-2-l2a', title: 'x', collection: collection(), viewable: false, reason: 'nope' } as DatasetOption,
    ];
    expect(downloadRequestFor(layer({ focusMode: false, downloaded: {} }), notViewable)).toBeNull();
  });

  it('returns null without a drawn AOI', () => {
    expect(downloadRequestFor(layer({ aoi: null }), DATASETS)).toBeNull();
  });

  it('returns null without a pinned dataset id', () => {
    expect(downloadRequestFor(layer({ datasetId: null }), DATASETS)).toBeNull();
  });

  it('returns null with nothing downloaded in focus mode', () => {
    expect(downloadRequestFor(layer({ downloaded: {} }), DATASETS)).toBeNull();
  });

  it('returns null without any pinned scenes', () => {
    expect(downloadRequestFor(layer({ itemIds: [] }), DATASETS)).toBeNull();
  });

  // M3-09 review (Otto, 24.09.2026): a "View full selection" layer's download
  // does *not* follow the view — it still needs the drawn AOI, exactly like a
  // "Crop to AOI" layer. Routing an uncropped download through this same
  // crop endpoint would downsize it to the tiler's output cap, which is not
  // what P19 asks for a whole scene (the original, unresized, straight from
  // the source); that real behaviour is M3-17's job.
  it('still needs the drawn AOI when the layer was pinned uncropped ("View full selection")', () => {
    expect(downloadRequestFor(layer({ cropToAoi: false, aoi: null }), DATASETS)).toBeNull();
  });

  it('a quicklook-only layer needs the AOI regardless of cropToAoi', () => {
    expect(
      downloadRequestFor(layer({ focusMode: false, downloaded: {}, cropToAoi: false, aoi: null }), DATASETS),
    ).toBeNull();
  });
});

describe('canDownloadLayer', () => {
  it('mirrors downloadRequestFor', () => {
    expect(canDownloadLayer(layer(), DATASETS)).toBe(true);
    expect(canDownloadLayer(layer({ aoi: null }), DATASETS)).toBe(false);
  });

  it('is true for a quicklook-only layer with a default render asset', () => {
    expect(canDownloadLayer(layer({ focusMode: false, downloaded: {} }), DATASETS)).toBe(true);
  });
});

function flags(overrides: Partial<LicenseFlags> = {}): LicenseFlags {
  return {
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
    terms_url: 'https://example.org/legal-notice',
    terms_notice: {
      de: 'Es gilt {terms_url}.',
      en: 'Subject to {terms_url}.',
    },
    ...overrides,
  };
}

describe('attributionText', () => {
  it('fills {year} into the modified-data text', () => {
    expect(attributionText(flags(), 2026)).toBe('Contains modified Copernicus Sentinel data 2026');
  });

  it('falls back to the unmodified text when no modified text is set', () => {
    expect(attributionText(flags({ attribution_modified: null }), 2026)).toBe(
      'Copernicus Sentinel data 2026',
    );
  });

  it('is null without any attribution text', () => {
    expect(
      attributionText(flags({ attribution_modified: null, attribution_unmodified: null }), 2026),
    ).toBeNull();
  });

  it('is null without licence flags at all', () => {
    expect(attributionText(null, 2026)).toBeNull();
  });
});

describe('termsNoticeText', () => {
  it('picks the requested language and fills {terms_url}', () => {
    expect(termsNoticeText(flags(), 'en')).toBe('Subject to https://example.org/legal-notice.');
  });

  it('falls back to English when the requested language is missing but English is set', () => {
    expect(termsNoticeText(flags(), 'fr')).toBe('Subject to https://example.org/legal-notice.');
  });

  it('falls back to whatever language is present when neither the requested one nor English is set', () => {
    const onlyDe = flags({ terms_notice: { de: 'Nur Deutsch: {terms_url}.' } });
    expect(termsNoticeText(onlyDe, 'fr')).toBe('Nur Deutsch: https://example.org/legal-notice.');
  });

  it('is null without terms at all', () => {
    expect(termsNoticeText(flags({ terms_notice: null }), 'en')).toBeNull();
  });
});

describe('canExportLicense', () => {
  it('allows the processing tier', () => {
    expect(canExportLicense(flags())).toBe(true);
  });

  it('refuses the display and catalog tiers', () => {
    expect(canExportLicense(flags({ tier: 'display' }))).toBe(false);
    expect(canExportLicense(flags({ tier: 'catalog' }))).toBe(false);
  });

  it('refuses without licence flags', () => {
    expect(canExportLicense(null)).toBe(false);
    expect(canExportLicense(undefined)).toBe(false);
  });
});
