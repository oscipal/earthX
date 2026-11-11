// A synthetic multispectral collection, item and answer of the platform for the tests of the choice of bands (NM4-75): the band names,
// wavelengths and addresses are made up.
import { parseBands } from '../api';
import type { DownloadBand } from '../bandChoice';
import type { Collection, StacAsset, StacItem } from '../types';

export const HOST = 'data.test';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

interface Spec {
  key: string;
  name: string;
  common?: string;
  wavelength?: number;
  gsd: number;
  dataType?: string;
  scale?: number;
  offset?: number;
  nodata?: number;
}

// Four spectral bands of two resolutions, a layer of classes, a layer that is no spectral band, and a picture made from the bands.
export const SPECS: Spec[] = [
  { key: 'a_blue', name: 'B02', common: 'blue', wavelength: 0.49, gsd: 10, dataType: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0 },
  { key: 'a_red', name: 'B04', common: 'red', wavelength: 0.665, gsd: 10, dataType: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0 },
  { key: 'a_edge', name: 'B05', common: 'rededge', wavelength: 0.704, gsd: 20, dataType: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0 },
  { key: 'a_coast', name: 'B01', common: 'coastal', wavelength: 0.443, gsd: 60, dataType: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0 },
  { key: 'scl', name: 'scl', gsd: 20, dataType: 'uint8', nodata: 0 },
  { key: 'aerosol', name: 'AOT', gsd: 20, dataType: 'uint16', nodata: 0 },
];

function asset(spec: Spec, id: string): StacAsset {
  return { href: `https://${HOST}/${id}/${spec.key}.tif`, type: COG, roles: ['data'], gsd: spec.gsd, 'file:size': 1000 };
}

// What the platform answers to `POST /collections/{dataset}/bands` for the item below (`fetchBands`): the same rows, in the same order,
// with the spectral bands and the layer of the mask preselected.
export function bandsResponse(): { bands: Record<string, unknown>[] } {
  return {
    bands: SPECS.map((spec) => ({
      asset: spec.key,
      name: spec.name,
      common_name: spec.common ?? null,
      wavelength_um: spec.wavelength ?? null,
      resolution_m: spec.gsd,
      data_type: spec.dataType ?? null,
      scale: spec.scale ?? null,
      offset: spec.offset ?? null,
      nodata: spec.nodata ?? null,
      unit: spec.key === 'scl' ? null : '1',
      categorical: spec.key === 'scl',
      preselected: spec.wavelength !== undefined || spec.key === 'scl',
    })),
  };
}

export const bandsTable = (): DownloadBand[] => parseBands(bandsResponse());

export function bandsCollection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: 'made-up-bands',
    title: 'Made-up multispectral',
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, browse: 'quicklook', quicklook_nodata_max: 16, results_group_by: ['datetime'], overview: 'own' as const, overview_resampling: null },
    'earthx:access': { cors: true },
    'earthx:source': { asset_hosts: [HOST] },
    'earthx:band_units': { ...Object.fromEntries(SPECS.map((spec) => [spec.key, spec.key === 'scl' ? null : '1'])), visual: null },
    'earthx:auxiliary_assets': ['visual'],
    'earthx:mask': {
      asset: 'scl',
      band: 'scl',
      classes: [
        { value: 0, label: 'No data' },
        { value: 4, label: 'Vegetation' },
      ],
      suggested: [4],
      reference: '',
      note: '',
    },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
    'earthx:license_flags': {
      spdx_id: null,
      name: 'Made-up notice',
      url: 'https://example.org/legal',
      commercial_use: true,
      distribution: true,
      derivatives: true,
      share_alike: false,
      attribution_required: true,
      tier: 'processing',
      attribution_modified: 'Contains modified made-up data {year}',
      attribution_unmodified: 'Made-up data {year}',
      terms_url: 'https://example.org/legal',
      terms_notice: { en: 'Subject to {terms_url}.' },
    },
    ...overrides,
  };
}

export function bandsItem(id = 'M_A', datetime = '2026-07-02T10:15:00Z'): StacItem {
  const assets: Record<string, StacAsset> = {};
  for (const spec of SPECS) assets[spec.key] = asset(spec, id);
  assets.visual = { href: `https://${HOST}/${id}/visual.tif`, type: COG, roles: ['visual'], gsd: 10, 'file:size': 1000 };
  assets.thumbnail = { href: `https://${HOST}/${id}/thumb.jpg`, type: 'image/jpeg', roles: ['thumbnail'] };
  assets.granule_metadata = { href: `https://${HOST}/${id}/granule.xml`, type: 'application/xml', roles: ['metadata'], 'file:size': 500 };
  return { id, collection: 'made-up-bands', bbox: [10, 50, 11, 51], properties: { datetime }, assets };
}
