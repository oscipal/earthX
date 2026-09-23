import { describe, expect, it } from 'vitest';

import {
  attributionText,
  canDownloadLayer,
  canExportLicense,
  downloadRequestFor,
  termsNoticeText,
} from './download';
import type { LayerRestore, MapLayer } from './layers';
import type { LicenseFlags } from './types';

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
    aoi: AOI,
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

describe('downloadRequestFor', () => {
  it('builds items/assets/aoi from a full-resolution layer', () => {
    const req = downloadRequestFor(layer());
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
        downloaded: {
          S2A_1: { tileUrl: 't1', bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 0, maxZoom: 19 },
          S2A_2: { tileUrl: 't2', bounds: [11, 47, 12, 48], asset: 'visual', minZoom: 0, maxZoom: 19 },
        },
      }),
    );
    expect(req?.items).toEqual(['S2A_1', 'S2A_2']);
    expect(req?.assets).toEqual(['visual']);
  });

  it('returns null for a quicklook-only layer (not focus mode)', () => {
    expect(downloadRequestFor(layer({ focusMode: false }))).toBeNull();
  });

  it('returns null without a drawn AOI', () => {
    expect(downloadRequestFor(layer({ aoi: null }))).toBeNull();
  });

  it('returns null without a pinned dataset id', () => {
    expect(downloadRequestFor(layer({ datasetId: null }))).toBeNull();
  });

  it('returns null with nothing downloaded', () => {
    expect(downloadRequestFor(layer({ downloaded: {} }))).toBeNull();
  });
});

describe('canDownloadLayer', () => {
  it('mirrors downloadRequestFor', () => {
    expect(canDownloadLayer(layer())).toBe(true);
    expect(canDownloadLayer(layer({ focusMode: false }))).toBe(false);
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
