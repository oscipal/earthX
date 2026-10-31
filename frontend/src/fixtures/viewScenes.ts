import { datasetsFrom } from '../datasets';
import type { DownloadedInfo, StacAsset, StacItem } from '../types';

const CAPABILITIES = {
  roi: true,
  time_range: true,
  band_math: true,
  interpolation: true,
  ml_processing: true,
  quad_pol: false,
  single_coverage_product: false,
};

const viewer = (browse: 'preview_tiles' | 'quicklook', minZoom: number, maxZoom: number, nodata: number | null) => ({
  group_by: ['datetime'],
  min_zoom: minZoom,
  max_zoom: maxZoom,
  browse,
  quicklook_nodata_max: nodata,
  results_group_by: ['datetime'],
});

// A source that publishes no quicklook: its browse preview is a tile of the coarsest released level (released from z8).
export const previewDataset = () =>
  datasetsFrom([
    {
      id: 'preview-source',
      title: 'Preview source',
      'earthx:capabilities': CAPABILITIES,
      'earthx:viewer': viewer('preview_tiles', 8, 14, null),
      'earthx:default_render': {
        title: 'True colour',
        assets: ['SR_10m:b04,b03,b02'],
        rescale: [[0, 0.3]] as [number, number][],
        colormap_name: null,
        expression: null,
        resampling: 'nearest',
      },
    },
  ])[0];

// A source with a quicklook whose tiles are released from `minZoom`.
export const quicklookDataset = (minZoom = 8) =>
  datasetsFrom([
    {
      id: 'quicklook-source',
      title: 'Quicklook source',
      'earthx:capabilities': CAPABILITIES,
      'earthx:viewer': viewer('quicklook', minZoom, 19, 16),
    },
  ])[0];

export const previewScene = (id: string): StacItem => ({
  id,
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-24T10:00:00Z' },
  assets: { SR_10m: { href: 'https://data.test/x.zarr/r10m', roles: ['data'] } },
});

const VISUAL: StacAsset = {
  href: 'https://example.invalid/visual.tif',
  'proj:transform': [10, 0, 499980, 0, -10, 5300040],
  'proj:shape': [10980, 10980],
};

export const quicklookScene = (id = 'S2A_1'): StacItem => ({
  id,
  bbox: [8.999746, 46.866609, 9.668828, 47.853693],
  properties: { datetime: '2026-07-24T10:00:00Z', 'proj:epsg': 32632 },
  assets: { thumbnail: { href: `https://example.invalid/${id}.jpg`, roles: ['thumbnail'] }, visual: VISUAL },
});

export const sceneInfo = (item: StacItem, minZoom: number, maxZoom: number): DownloadedInfo => ({
  datasetId: 'sentinel-2-c1-l2a', tileUrl: `/collections/c/items/${item.id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
  bounds: item.bbox ?? [10, 47, 11, 48],
  asset: 'visual',
  minZoom,
  maxZoom,
});

// `Image`, as a browser loads a quicklook: it arrives when the test says so (or at once, `instant`).
export class FakeImage {
  static all: FakeImage[] = [];
  static instant = false;
  crossOrigin = '';
  naturalWidth = 4;
  naturalHeight = 4;
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private target = '';
  constructor() {
    FakeImage.all.push(this);
  }
  set src(value: string) {
    this.target = value;
    if (FakeImage.instant) this.onload?.();
  }
  get src() {
    return this.target;
  }
  static arrive(url?: string) {
    for (const image of FakeImage.all) if (url === undefined || image.src === url) image.onload?.();
  }
}
