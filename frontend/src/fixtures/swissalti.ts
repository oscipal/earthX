import { datasetsFrom } from '../datasets';
import { mosaicKeyOf, type Mosaics, type SceneEntry } from '../mosaic';
import type { Collection, DownloadedInfo, StacItem, TimeStepGroup } from '../types';
import { sceneInfo } from './viewScenes';

// A dataset that is released from level 13 and shows the picture of another below it (registry `viewer.overview: substitute`),
// as swissALTI3D does with Copernicus DEM GLO-30, and the view of two of its scenes that is cropped to an AOI: the data of the
// browser checks and tests of "no dataset loses its picture when zoomed out" (plan M5-30b §8.8).

const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const FLAGS = {
  spdx_id: null,
  name: 'Made-up licence',
  url: 'https://licence.example/',
  commercial_use: true,
  distribution: true,
  derivatives: true,
  share_alike: false,
  attribution_required: true,
  tier: 'processing' as const,
  attribution_modified: '© Provider made up for the test',
  attribution_unmodified: 'unmodified text',
  terms_url: null,
  terms_notice: null,
};
const viewer = (min: number, max: number, over: Record<string, unknown>) => ({
  group_by: ['earthx:state'],
  min_zoom: min,
  max_zoom: max,
  browse: 'full_resolution' as const,
  quicklook_nodata_max: null,
  results_group_by: ['earthx:state'],
  overview: 'pyramid' as const,
  overview_resampling: 'average' as const,
  overview_substitute: null,
  ...over,
});
const render = (asset: string) => ({ title: 'Elevation', assets: [asset], rescale: [[0, 5000]] as [number, number][], colormap_name: 'terrain', expression: null, resampling: 'nearest' });

export const TERRAIN_EXTENT: [number, number, number, number] = [5.9, 45.7, 10.5, 47.8];
export const COLLECTIONS: Collection[] = [
  {
    id: 'terrain',
    title: 'Terrain',
    extent: { spatial: { bbox: [TERRAIN_EXTENT] } },
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': viewer(13, 20, { overview: 'substitute', overview_resampling: null, overview_substitute: 'surface' }),
    'earthx:default_render': render('dtm'),
  },
  {
    id: 'surface',
    title: 'Surface',
    extent: { spatial: { bbox: [[-180, -90, 180, 84]] } },
    'earthx:capabilities': CAPABILITIES,
    'earthx:license_flags': FLAGS,
    'earthx:viewer': viewer(0, 15, {}),
    'earthx:default_render': render('data'),
  },
];
export const LIST = datasetsFrom(COLLECTIONS);
export const TERRAIN = LIST[0];

// The area a person crops to, a part of the dataset around a city.
export const AOI: GeoJSON.Geometry = { type: 'Polygon', coordinates: [[[8.3, 47.2], [8.8, 47.2], [8.8, 47.6], [8.3, 47.6], [8.3, 47.2]]] };
export const ITEMS: StacItem[] = ['A', 'B'].map((id, n) => ({ id, collection: 'terrain', bbox: [8 + n / 2, 47, 8.5 + n / 2, 47.8], properties: { datetime: '2026-01-01T00:00:00Z' }, assets: {} }));
export const GROUPS: TimeStepGroup[] = [{ key: ['A'], label: 'A', items: ITEMS }];
export const DOWNLOADED: Record<string, DownloadedInfo> = Object.fromEntries(
  ITEMS.map((item) => [
    item.id,
    { ...sceneInfo(item, 13, 20, 'terrain'), tileUrl: `/collections/terrain/items/${item.id}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512` },
  ]),
);
export const ENTRIES = Object.entries(DOWNLOADED) as SceneEntry[];
// The selection of the pass is created: its tiles are the dataset's own mosaic, from level 13.
export const MOSAIC_URL = '/collections/terrain/mosaic/0123456789abcdef0123456789abcdef/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512';
export const MOSAICS: Mosaics = {
  [mosaicKeyOf('terrain', ENTRIES) as string]: { tileUrl: MOSAIC_URL, bounds: TERRAIN_EXTENT, minZoom: 13, maxZoom: 20, order: ['A', 'B'] },
};
