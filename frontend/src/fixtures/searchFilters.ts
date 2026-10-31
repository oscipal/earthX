// Synthetic datasets with search filters (DS-02c), in the form the collection publishes them as
// `earthx:search_filters` (`backend/earthx/catalog/collection.py::_earthx_search_filters`). Made up for the tests: two
// datasets with filters of their own and one without, so that nothing here depends on a real dataset (and no source-specific property name stands in this file, `test_frontend_no_dataset_literals`).

import type { Collection, EarthxMask } from '../types';

export const CLOUD_FILTER = {
  property: 'test:cloud',
  kind: 'range',
  title: 'Cloud cover',
  group: 'Clouds',
  description: 'Share of the scene covered by clouds.',
  unit: '%',
  within_aoi: true,
  type: 'number',
  minimum: 0,
  maximum: 100,
};

export const NODATA_FILTER = {
  property: 'test:nodata',
  kind: 'range',
  title: 'No data',
  group: 'Scene',
  description: 'Share of the scene without image data.',
  unit: '%',
  within_aoi: false,
  type: 'number',
  minimum: 0,
  maximum: 100,
};

export const SATELLITE_FILTER = {
  property: 'platform',
  kind: 'values',
  title: 'Satellite',
  group: 'Acquisition',
  description: 'The satellite that took the scene.',
  unit: null,
  within_aoi: false,
  type: 'string',
  oneOf: [
    { const: 'sat-a', title: 'Satellite A' },
    { const: 'sat-b', title: 'Satellite B' },
  ],
};

export const ORBIT_FILTER = {
  property: 'test:track',
  kind: 'range',
  title: 'Relative orbit',
  group: 'Acquisition',
  description: 'The orbit track the scene lies on.',
  unit: null,
  within_aoi: false,
  type: 'integer',
  minimum: 1,
  maximum: 175,
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

// The classification layer of the optical dataset (`earthx:mask`, DS-03): which classes count as clouds when the cloud
// share is measured in the AOI, and the registry's note to the limits of the classification. Made up like the rest.
export const CLASSIFICATION: EarthxMask = {
  asset: 'cls',
  band: 'cls',
  classes: [
    { value: 0, label: 'No data' },
    { value: 4, label: 'Vegetation' },
    { value: 5, label: 'Cloud' },
    { value: 6, label: 'Thick cloud' },
    { value: 7, label: 'Cloud shadow' },
  ],
  suggested: [5, 6, 7],
  reference: 'https://example.invalid/classes',
  note: '',
  cloud_classes: [5, 6],
  cloud_note: 'The classification can miss thin haze and can take snow for clouds.',
};

function viewable(id: string, title: string, filters: unknown[] | undefined, mask?: EarthxMask): Collection {
  return {
    id,
    title,
    'earthx:capabilities': CAPABILITIES,
    'earthx:viewer': {
      group_by: ['datetime'],
      min_zoom: 8,
      max_zoom: 14,
      browse: 'quicklook',
      quicklook_nodata_max: null,
      results_group_by: ['datetime'],
    },
    ...(filters ? { 'earthx:search_filters': filters } : {}),
    ...(mask ? { 'earthx:mask': mask } : {}),
  };
}

// Three groups, so that the pop-up has headings; the radar has one, so that it has none.
export const OPTICAL = viewable('optical', 'Optical imagery', [CLOUD_FILTER, NODATA_FILTER, SATELLITE_FILTER], CLASSIFICATION);
export const RADAR = viewable('radar', 'Radar imagery', [ORBIT_FILTER]);
// A dataset without filters publishes an empty list (the DEM), one from an older backend none at all.
export const ELEVATION = viewable('elevation', 'Elevation model', []);
export const LEGACY = viewable('legacy', 'Legacy imagery', undefined);
