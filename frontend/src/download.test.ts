import { describe, expect, it } from 'vitest';

import type { DatasetOption } from './datasets';
import {
  assetHostsOf,
  attributionText,
  canDownloadLayer,
  canExportLicense,
  decideDownloadOutcome,
  decideDownloadOutcomeForLayer,
  downloadRequestFor,
  downloadRequestForSelection,
  isCogFormat,
  isDirectDownloadHref,
  originalFileLinks,
  resolutionOptionLabel,
  termsNoticeText,
} from './download';
import type { LayerRestore, MapLayer } from './layers';
import type { Collection, LicenseFlags, StacItem } from './types';

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
    groupItemIds: [['S2A_1']],
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
      groups: [['S2A_1']],
      assets: ['visual'],
      aoi: AOI,
    });
  });

  it('deduplicates the asset across several pinned items', () => {
    const req = downloadRequestFor(
      layer({
        itemIds: ['S2A_1', 'S2A_2'],
        groupItemIds: [['S2A_1', 'S2A_2']],
        downloaded: {
          S2A_1: { tileUrl: 't1', bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 0, maxZoom: 19 },
          S2A_2: { tileUrl: 't2', bounds: [11, 47, 12, 48], asset: 'visual', minZoom: 0, maxZoom: 19 },
        },
      }),
      DATASETS,
    );
    expect(req?.groups).toEqual([['S2A_1', 'S2A_2']]);
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
      groups: [['S2A_1']],
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
  it('mirrors downloadRequestFor for the crop outcome', () => {
    expect(canDownloadLayer(layer(), DATASETS)).toBe(true);
  });

  it('is true for a quicklook-only layer with a default render asset', () => {
    expect(canDownloadLayer(layer({ focusMode: false, downloaded: {} }), DATASETS)).toBe(true);
  });

  it('is true (originals) for a "View full selection" COG layer without an AOI', () => {
    const cog = [dataset({ collection: collection({ 'earthx:format': 'cog' }) })];
    expect(canDownloadLayer(layer({ cropToAoi: false, aoi: null }), cog)).toBe(true);
  });

  it('is false (disabled) for a "View full selection" Zarr layer without an AOI', () => {
    const zarr = [dataset({ collection: collection({ 'earthx:format': 'zarr' }) })];
    expect(canDownloadLayer(layer({ cropToAoi: false, aoi: null }), zarr)).toBe(false);
  });

  it('is false for a layer with nothing pinned at all', () => {
    expect(canDownloadLayer(layer({ itemIds: [] }), DATASETS)).toBe(false);
  });
});

describe('decideDownloadOutcome (M3-17 plan §4)', () => {
  it('a cropped view ("Crop & merge to AOI") always crops, whatever the format', () => {
    expect(decideDownloadOutcome({ cropToAoi: true, hasAoi: true, isCog: true })).toBe('crop');
    expect(decideDownloadOutcome({ cropToAoi: true, hasAoi: true, isCog: false })).toBe('crop');
  });

  it('"View full selection" of a COG is always the originals, AOI or not', () => {
    expect(decideDownloadOutcome({ cropToAoi: false, hasAoi: true, isCog: true })).toBe('originals');
    expect(decideDownloadOutcome({ cropToAoi: false, hasAoi: false, isCog: true })).toBe('originals');
  });

  it('"View full selection" of a non-COG source needs the AOI, else disabled', () => {
    expect(decideDownloadOutcome({ cropToAoi: false, hasAoi: true, isCog: false })).toBe('crop');
    expect(decideDownloadOutcome({ cropToAoi: false, hasAoi: false, isCog: false })).toBe('disabled');
  });

  it('browsing (no full-resolution view, cropToAoi null) follows the AOI, else the format', () => {
    expect(decideDownloadOutcome({ cropToAoi: null, hasAoi: true, isCog: true })).toBe('crop');
    expect(decideDownloadOutcome({ cropToAoi: null, hasAoi: true, isCog: false })).toBe('crop');
    expect(decideDownloadOutcome({ cropToAoi: null, hasAoi: false, isCog: true })).toBe('originals');
    expect(decideDownloadOutcome({ cropToAoi: null, hasAoi: false, isCog: false })).toBe('disabled');
  });
});

describe('decideDownloadOutcomeForLayer', () => {
  it('reads cropToAoi only in focus mode, format from the dataset', () => {
    const cog = [dataset({ collection: collection({ 'earthx:format': 'cog' }) })];
    expect(decideDownloadOutcomeForLayer(layer({ focusMode: true, cropToAoi: false, aoi: null }), cog)).toBe(
      'originals',
    );
    // A quicklook-only layer ignores its own `cropToAoi` (meaningless outside
    // focus mode) — it reads like browsing, not "View full selection".
    expect(
      decideDownloadOutcomeForLayer(layer({ focusMode: false, cropToAoi: false, aoi: null }), cog),
    ).toBe('originals');
  });

  it('an unknown dataset is never assumed to be a COG', () => {
    expect(decideDownloadOutcomeForLayer(layer({ cropToAoi: false, aoi: null }), [])).toBe('disabled');
  });
});

describe('isCogFormat', () => {
  it('is true only for the exact value "cog"', () => {
    expect(isCogFormat(dataset({ collection: collection({ 'earthx:format': 'cog' }) }))).toBe(true);
    expect(isCogFormat(dataset({ collection: collection({ 'earthx:format': 'zarr' }) }))).toBe(false);
    expect(isCogFormat(dataset({ collection: collection({ 'earthx:format': 'legacy' }) }))).toBe(false);
  });

  it('a missing/unrecognised value is never assumed to be a COG', () => {
    expect(isCogFormat(dataset({ collection: collection({ 'earthx:format': null }) }))).toBe(false);
    expect(isCogFormat(dataset({ collection: collection({ 'earthx:format': 'geotiff' }) }))).toBe(false);
    expect(isCogFormat(undefined)).toBe(false);
  });
});

describe('assetHostsOf', () => {
  it('reads earthx:source.asset_hosts', () => {
    const withHosts = dataset({ collection: collection({ 'earthx:source': { asset_hosts: ['a.example'] } }) });
    expect(assetHostsOf(withHosts)).toEqual(['a.example']);
  });

  it('is empty without a source entry or a dataset at all', () => {
    expect(assetHostsOf(dataset())).toEqual([]);
    expect(assetHostsOf(undefined)).toEqual([]);
  });
});

describe('isDirectDownloadHref', () => {
  const HOSTS = ['e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com'];

  it('accepts an https href on a registered host', () => {
    expect(isDirectDownloadHref('https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/x.tif', HOSTS)).toBe(
      true,
    );
  });

  it('refuses a host not on the list', () => {
    expect(isDirectDownloadHref('https://elsewhere.example.invalid/x.tif', HOSTS)).toBe(false);
  });

  it('refuses anything not https (plain http, javascript:, s3:, data:)', () => {
    expect(isDirectDownloadHref('http://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/x.tif', HOSTS)).toBe(
      false,
    );
    expect(isDirectDownloadHref('javascript:alert(1)', HOSTS)).toBe(false);
    expect(isDirectDownloadHref('s3://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/x.tif', HOSTS)).toBe(
      false,
    );
    expect(isDirectDownloadHref('data:text/plain,x', HOSTS)).toBe(false);
  });

  it('refuses an unparseable href rather than throwing', () => {
    expect(isDirectDownloadHref('not a url at all', HOSTS)).toBe(false);
  });

  it('refuses every host when the list is empty', () => {
    expect(isDirectDownloadHref('https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/x.tif', [])).toBe(
      false,
    );
  });
});

describe('originalFileLinks', () => {
  const HOSTS = ['good.example'];

  it('one link per item and asset, only on a registered https host', () => {
    const good = item({ id: 'A', assets: { visual: { href: 'https://good.example/a.tif' } } });
    const bad = item({ id: 'B', assets: { visual: { href: 'https://bad.example/b.tif' } } });
    const links = originalFileLinks([{ label: 'Group 1', items: [good, bad] }], ['visual'], HOSTS);
    expect(links).toEqual([{ itemId: 'A', groupLabel: 'Group 1', asset: 'visual', href: 'https://good.example/a.tif' }]);
  });

  it('an item with no asset of that name contributes nothing', () => {
    const noAsset = item({ id: 'A', assets: {} });
    expect(originalFileLinks([{ label: 'Group 1', items: [noAsset] }], ['visual'], HOSTS)).toEqual([]);
  });

  it('keeps groups and their labels apart', () => {
    const a = item({ id: 'A', assets: { visual: { href: 'https://good.example/a.tif' } } });
    const b = item({ id: 'B', assets: { visual: { href: 'https://good.example/b.tif' } } });
    const links = originalFileLinks(
      [
        { label: 'Group 1', items: [a] },
        { label: 'Group 2', items: [b] },
      ],
      ['visual'],
      HOSTS,
    );
    expect(links.map((l) => l.groupLabel)).toEqual(['Group 1', 'Group 2']);
  });
});

describe('downloadRequestForSelection (M3-17: groups, not a flat item list)', () => {
  it('builds one group per given list of ids', () => {
    const req = downloadRequestForSelection(dataset(), [['A', 'B'], ['C']], AOI);
    expect(req).toEqual({ datasetId: 'sentinel-2-l2a', groups: [['A', 'B'], ['C']], assets: ['visual'], aoi: AOI });
  });

  it('drops an empty group rather than sending it to the backend', () => {
    const req = downloadRequestForSelection(dataset(), [['A'], []], AOI);
    expect(req?.groups).toEqual([['A']]);
  });

  it('is null once every group is empty, without an AOI, or without a viewable dataset', () => {
    expect(downloadRequestForSelection(dataset(), [[]], AOI)).toBeNull();
    expect(downloadRequestForSelection(dataset(), [['A']], null)).toBeNull();
    expect(downloadRequestForSelection(undefined, [['A']], AOI)).toBeNull();
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

  it('picks the unmodified text first when asked to (M3-17: the originals are unmodified)', () => {
    expect(attributionText(flags(), 2026, false)).toBe('Copernicus Sentinel data 2026');
  });

  it('falls back to the modified text when unmodified is not set, even when asked for it', () => {
    expect(attributionText(flags({ attribution_unmodified: null }), 2026, false)).toBe(
      'Contains modified Copernicus Sentinel data 2026',
    );
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

function item(overrides: Partial<StacItem> = {}): StacItem {
  return {
    id: 'ITEM1',
    properties: {},
    assets: { visual: { href: 'https://example.invalid/visual.tif', gsd: 10 } },
    ...overrides,
  };
}

describe('resolutionOptionLabel', () => {
  it('names the factor alone, native without a suffix', () => {
    expect(resolutionOptionLabel([], 'visual', 1)).toBe('Native');
    expect(resolutionOptionLabel([], 'visual', 4)).toBe('4×');
  });

  it('adds the metre figure once a gsd is known', () => {
    expect(resolutionOptionLabel([item()], 'visual', 1)).toBe('Native (10 m)');
    expect(resolutionOptionLabel([item()], 'visual', 2)).toBe('2× (20 m)');
  });

  it('reads the gsd off proj:transform when the asset has none of its own', () => {
    const withTransform = item({ assets: { visual: { href: 'h', 'proj:transform': [20, 0, 0, 0, -20, 0] } } });
    expect(resolutionOptionLabel([withTransform], 'visual', 1)).toBe('Native (20 m)');
  });

  it('uses the finest gsd among several items, matching the backend worst case', () => {
    const fine = item({ id: 'A', assets: { visual: { href: 'h', gsd: 10 } } });
    const coarse = item({ id: 'B', assets: { visual: { href: 'h', gsd: 60 } } });
    expect(resolutionOptionLabel([coarse, fine], 'visual', 1)).toBe('Native (10 m)');
  });

  it('falls back to the factor alone when no item names this asset', () => {
    expect(resolutionOptionLabel([item()], 'thumbnail', 1)).toBe('Native');
  });
});
