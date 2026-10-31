// Synthetic Sentinel-2 style collection and items for the tests of the download of whole scenes (NM4-33): the field
// names are the registry's, the values and addresses are made up.
import type { Collection, StacItem } from '../types';

export const HOST = 'data.test';
export const S2_BANDS = [
  'coastal', 'blue', 'green', 'red', 'rededge1', 'rededge2', 'rededge3', 'nir', 'nir08', 'nir09', 'swir16', 'swir22',
  'aot', 'wvp', 'cloud', 'snow', 'scl', 'visual', 'preview',
]; // fmt: skip

export function collection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: 'made-up-scenes',
    title: 'Sentinel-2 L2A',
    'sci:doi': '10.5270/S2_-742ikth',
    'earthx:access': { cors: true },
    'earthx:source': { asset_hosts: [HOST] },
    'earthx:band_units': Object.fromEntries(S2_BANDS.map((key) => [key, key === 'visual' || key === 'preview' ? null : 'x'])),
    'earthx:auxiliary_assets': ['visual', 'preview'],
    'earthx:default_render': {
      title: 'True colour',
      assets: ['visual'],
      rescale: null,
      colormap_name: null,
      expression: null,
      resampling: 'nearest',
    },
    'earthx:license_flags': {
      spdx_id: null,
      name: 'Sentinel Data Legal Notice',
      url: 'https://example.org/legal',
      commercial_use: true,
      distribution: true,
      derivatives: true,
      share_alike: false,
      attribution_required: true,
      tier: 'processing',
      attribution_modified: 'Contains modified Copernicus Sentinel data {year}',
      attribution_unmodified: 'Copernicus Sentinel data {year}',
      terms_url: 'https://example.org/legal',
      terms_notice: { en: 'Subject to {terms_url}.' },
    },
    ...overrides,
  };
}

export function item(id = 'S2C_T32UPU_20260702', extra: StacItem['assets'] = {}, only?: string[]): StacItem {
  const assets: StacItem['assets'] = {};
  for (const key of only ?? S2_BANDS) {
    assets[key] = { href: `https://${HOST}/${id}/${key}.tif`, roles: key === 'visual' ? ['visual'] : ['data'], 'file:size': 1000 };
  }
  assets.preview = { href: `https://${HOST}/${id}/preview.tif`, roles: ['overview'] };
  assets.thumbnail = { href: `https://${HOST}/${id}/thumb.jpg`, roles: ['thumbnail'] };
  assets.granule_metadata = { href: `https://${HOST}/${id}/granule.xml`, roles: ['metadata'], 'file:size': 500 };
  assets.product_metadata = { href: `https://${HOST}/${id}/product.xml`, roles: ['metadata'], 'file:size': 500 };
  assets.tileinfo_metadata = { href: `https://${HOST}/${id}/tileinfo.json`, roles: ['metadata'], 'file:size': 500 };
  return { id, properties: { datetime: '2026-07-02T10:15:00Z' }, assets: { ...assets, ...extra } };
}
