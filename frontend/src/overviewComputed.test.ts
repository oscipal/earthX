// A computed picture below the first level (M5-10 part B, G1, G2): the preview of the panel, a pinned preview, an index in the
// view and in a pinned layer are computed on the overview there, so that none of them disappears when the map zooms out. Each
// says so in the tooltip it already has, and nowhere else.

import { describe, expect, it } from 'vitest';

import { datasetsFrom } from './datasets';
import dem from './fixtures/processes/cop-dem-glo-30.json';
import { sceneInfo } from './fixtures/viewScenes';
import { zoomMap } from './fixtures/zoomMap';
import { syncFocusRaster } from './mapLayers';
import { computedNoteOf, noteOfOverview, overviewNoteOf, overviewRasterOf } from './overviewSubstitute';
import type { ProcessDescription } from './processing';
import { processInfo, type DraftStep } from './processingOrder';
import { DEFAULT_RANGE, planPreview, previewOverlays, previewSpec, previewTitle } from './processingPreview';
import { initialValues } from './schemaForm';
import { overviewOverlaysOf } from './searchLayers';
import type { Collection, LicenseFlags, StacItem } from './types';
import { indexBlockOf, indexChainOf, viewIndexOf } from './viewIndex';

const DEM = processInfo(dem as unknown as ProcessDescription);
const CAPABILITIES = { roi: true, time_range: false, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
const FLAGS: LicenseFlags = {
  spdx_id: null,
  name: 'Made-up licence',
  url: 'https://licence.example/',
  commercial_use: true,
  distribution: true,
  derivatives: true,
  share_alike: false,
  attribution_required: true,
  tier: 'processing',
  attribution_modified: '© Made up (modified)',
  attribution_unmodified: '© Made up',
  terms_url: null,
  terms_notice: null,
};
const PRESET = {
  name: 'double',
  title: 'Double',
  expression: 'data * 2',
  rescale: [[0, 6000]],
  colormap_name: 'viridis',
  formula: 'data × 2',
  reference: 'made up for the test',
};

const collection = (id: string, title: string, viewer: Partial<NonNullable<Collection['earthx:viewer']>>): Collection => ({
  id,
  title,
  extent: { spatial: { bbox: [[5, 45, 11, 48]] } },
  'earthx:capabilities': CAPABILITIES,
  'earthx:license_flags': FLAGS,
  'earthx:index_presets': [PRESET],
  'earthx:viewer': {
    group_by: ['start_datetime'],
    min_zoom: 7,
    max_zoom: 15,
    browse: 'full_resolution',
    quicklook_nodata_max: null,
    results_group_by: ['start_datetime'],
    overview: 'pyramid',
    overview_resampling: 'average',
    overview_substitute: null,
    ...viewer,
  },
  'earthx:default_render': { title: 'Elevation', assets: ['data'], rescale: [[0, 3000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
}) as unknown as Collection;

const LIST = datasetsFrom([
  collection('relief', 'Relief', {}),
  collection('terrain', 'Terrain', { min_zoom: 13, overview: 'substitute', overview_resampling: null, overview_substitute: 'relief' }),
]);
const [RELIEF, TERRAIN] = LIST;
const ITEM: StacItem = { id: 'r1', collection: 'relief', bbox: [7, 46, 8, 47], properties: { datetime: '2026-01-01T00:00:00Z' }, assets: {} };
const INDEX_LOOK = { index: 'double', rescale: '0,6000', colormapName: 'viridis' };
const query = (url: string) => new URL(url, 'http://localhost').searchParams;

const view = (over: Record<string, unknown> = {}) => ({
  downloaded: { r1: { ...sceneInfo(ITEM, 7, 15, 'relief'), tileUrl: '/collections/relief/mosaic/s/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512' } },
  render: INDEX_LOOK,
  showDownloaded: true,
  aoi: null,
  cropToAoi: false,
  items: [ITEM],
  dataset: RELIEF,
  datasets: LIST,
  ...over,
});

const overviewSourcesOf = (live: ReturnType<typeof zoomMap>) =>
  [...live.sources.entries()].filter(([id, s]) => id.includes('tiles-src') && (s.tiles as string[])[0].includes('/overview/'));

describe('an index below the first level', () => {
  it('is computed on the overview in the view and in "Crop and merge"', () => {
    for (const over of [{}, { cropToAoi: true, aoi: { type: 'Polygon', coordinates: [[[7, 46], [8, 46], [8, 47], [7, 47], [7, 46]]] } }]) {
      const live = zoomMap();
      syncFocusRaster(live.map as never, view(over) as never);
      const [[, source]] = overviewSourcesOf(live);
      const params = query((source.tiles as string[])[0]);
      expect(params.getAll('op')).toEqual(['band_math']);
      expect(params.get('band')).toBe('double');
      expect(params.get('rescale')).toBe('0,6000');
      expect(source.maxzoom).toBe(6);
    }
  });

  it('is computed on the overview in a pinned layer, on the substitute as on the pyramid', () => {
    for (const dataset of [RELIEF, TERRAIN]) {
      const [overlay] = overviewOverlaysOf([dataset.id], LIST, INDEX_LOOK, null);
      expect(overlay.kind).toBe('raster');
      if (overlay.kind !== 'raster') continue;
      expect(overlay.tileUrl).toContain(`/collections/${dataset.id}/overview/tiles/`);
      expect(query(overlay.tileUrl).getAll('op')).toEqual(['band_math']);
      expect(overlay.minZoom).toBe(0);
    }
  });

  it('asks nobody to zoom in where the overview draws it', () => {
    const preset = viewIndexOf(INDEX_LOOK, RELIEF.collection)!;
    const args = { datasetId: 'relief', entries: [['r1', view().downloaded.r1]] as never, groups: undefined, mosaics: undefined, preset, mapZoom: 3 };
    expect(indexBlockOf(args)).toBe('zoom');
    expect(indexBlockOf({ ...args, overview: true })).toBeNull();
  });

  it('carries the step of the index and the band it adds', () => {
    const chain = indexChainOf(viewIndexOf(INDEX_LOOK, RELIEF.collection)!);
    expect(chain.band).toBe('double');
    expect(JSON.parse(chain.steps[0].paramsJson)).toEqual({ expression: 'data * 2', name: 'double' });
  });
});

describe('what a computed picture says of itself', () => {
  it('names the overview it is computed from, also where another dataset stands in', () => {
    expect(computedNoteOf(RELIEF, LIST)).toBe(
      'Below zoom 7 this is computed from an overview of Relief, resampled from the original files; zoom in to 7 for values from the originals.',
    );
    expect(computedNoteOf(TERRAIN, LIST)).toContain('computed from an overview of Relief');
    expect(computedNoteOf(TERRAIN, LIST)).toContain('zoom in to 13');
  });

  it('is the note of a pinned layer of an index, not the sentence of the plain picture', () => {
    expect(noteOfOverview(RELIEF, { datasets: LIST }).note).toBe(computedNoteOf(RELIEF, LIST));
    expect(noteOfOverview(RELIEF).note).toBe(overviewNoteOf(RELIEF));
  });

  it('is nothing for a dataset that draws its own files at every level', () => {
    const own = datasetsFrom([collection('own', 'Own', { min_zoom: 0, overview: 'own' })]);
    expect(computedNoteOf(own[0], own)).toBeNull();
    expect(overviewRasterOf(own[0], own, indexChainOf(viewIndexOf(INDEX_LOOK, own[0].collection)!))).toBeNull();
  });
});

describe('the preview of the panel below the first level', () => {
  const form = DEM.operators.find((o) => o.op === 'terrain')!.form;
  if (!form.supported) throw new Error(form.reason);
  const slope: DraftStep = { key: 1, op: 'terrain', opVersion: 1, values: { ...initialValues(form.fields), bands: 'data', name: 'slope' } };
  const plan = planPreview([slope], DEM);
  if (plan.state !== 'ready') throw new Error('no plan');
  const item: StacItem = { ...ITEM, properties: { ...ITEM.properties, gsd: 30 } } as StacItem;
  const spec = previewSpec({ dataset: RELIEF, items: [item], assets: ['data'], info: DEM, plan, range: DEFAULT_RANGE, area: 'scene', datasets: LIST })!;

  it('draws the steps on the overview, under the scenes', () => {
    expect(spec.overview).not.toBeNull();
    const overlays = previewOverlays(spec, null);
    const last = overlays.at(-1)!;
    expect(last.kind === 'raster' && last.tileUrl).toContain('/collections/relief/overview/tiles/');
    if (last.kind !== 'raster') return;
    expect(query(last.tileUrl).getAll('op')).toEqual(['terrain']);
    expect(last.minZoom).toBe(0);
    expect(last.maxZoom).toBe(6);
    expect(last.preview).toBe(true);
  });

  it('says so in the tooltip of "Preview"', () => {
    expect(previewTitle(spec, null)).toContain('computed from an overview of Relief');
  });

  it('is part of the key, so that a new overview is a new picture', () => {
    expect(JSON.parse(spec.key).overview).toBe(spec.overview?.url);
  });
});
