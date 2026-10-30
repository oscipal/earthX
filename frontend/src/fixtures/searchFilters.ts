// Synthetic datasets with search filters (DS-02c), in the form the collection publishes them as
// `earthx:search_filters` (`backend/earthx/catalog/collection.py::_earthx_search_filters`). Made up for the tests: two
// datasets with filters of their own and one without, so that nothing here depends on a real dataset (and no source-specific property name stands in this file, `test_frontend_no_dataset_literals`).

import type { Collection } from '../types';

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

function viewable(id: string, title: string, filters: unknown[] | undefined): Collection {
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
  };
}

// Three groups, so that the pop-up has headings; the radar has one, so that it has none.
export const OPTICAL = viewable('optical', 'Optical imagery', [CLOUD_FILTER, NODATA_FILTER, SATELLITE_FILTER]);
export const RADAR = viewable('radar', 'Radar imagery', [ORBIT_FILTER]);
// A dataset without filters publishes an empty list (the DEM), one from an older backend none at all.
export const ELEVATION = viewable('elevation', 'Elevation model', []);
export const LEGACY = viewable('legacy', 'Legacy imagery', undefined);
