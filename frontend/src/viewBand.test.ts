import { describe, expect, it } from 'vitest';

import type { Collection, StacItem } from './types';
import { bandAssetsOf, bandLookOf, fixedRangeOf, scalingOfBand } from './viewBand';

const meteo = (overrides: Partial<Collection> = {}): Collection =>
  ({
    id: 'meteoswiss-daily-1km',
    title: 'MeteoSwiss daily climate grids 1 km',
    'earthx:format': 'netcdf-refs',
    'earthx:band_units': { TabsD: '°C', TminD: '°C', TmaxD: '°C', SrelD: '%' },
    'earthx:auxiliary_assets': [],
    'earthx:default_render': { title: 'Daily mean temperature', assets: ['TabsD'], rescale: [[-20, 30]], colormap_name: 'rdbu_r', expression: null, resampling: 'nearest' },
    ...overrides,
  }) as Collection;

const day = (quantities: string[]): StacItem => ({
  id: 'meteoswiss-daily-1km-20240701',
  collection: 'meteoswiss-daily-1km',
  properties: { datetime: '2024-07-01T00:00:00Z' },
  assets: Object.fromEntries(
    quantities.map((q) => [
      q,
      { href: `https://data.example/${q}_2024.nc`, type: 'application/x-netcdf', roles: ['data'], 'earthx:refs': { etag: '"a"' }, 'raster:bands': [{ data_type: 'float32' }] },
    ]),
  ),
});

describe('bandAssetsOf (the dropdown "Band" of the view)', () => {
  it('offers every quantity of a day read through chunk references (M5-11)', () => {
    expect(bandAssetsOf(day(['TabsD', 'TminD', 'TmaxD', 'SrelD']), meteo())).toEqual(['TabsD', 'TminD', 'TmaxD', 'SrelD']);
  });

  it('offers only the quantities a day has (before 1971 only TabsD)', () => {
    expect(bandAssetsOf(day(['TabsD']), meteo())).toEqual(['TabsD']);
  });

  it('leaves out an asset without references', () => {
    const item = day(['TabsD', 'TminD']);
    delete item.assets.TminD['earthx:refs'];
    expect(bandAssetsOf(item, meteo())).toEqual(['TabsD']);
  });

  it('offers nothing for a Zarr store or without an item', () => {
    expect(bandAssetsOf(day(['TabsD', 'TminD']), meteo({ 'earthx:format': 'zarr' }))).toEqual([]);
    expect(bandAssetsOf(undefined, meteo())).toEqual([]);
  });
});

describe('bandLookOf (M5-60: the look the collection publishes for a band)', () => {
  const bands = [
    { name: 'TabsD', description: 'Mean', 'earthx:look': { colormap: 'rdbu_r', scale: 'fixed', low: -20, high: 30 } },
    { name: 'SrelD', description: 'Sunshine', 'earthx:look': { colormap: 'viridis', scale: 'fixed', low: 0, high: 100 } },
    { name: 'B04', description: 'Red', 'earthx:look': { colormap: 'viridis', scale: 'measured' } },
    { name: 'map', description: 'Classes', 'classification:classes': [] },
    { name: 'odd', description: 'Half a look', 'earthx:look': { colormap: 'viridis', scale: 'fixed', low: 5 } },
    { name: 'flat', description: 'An empty range', 'earthx:look': { colormap: 'viridis', scale: 'fixed', low: 5, high: 5 } },
    { name: 'wide', description: 'Percentiles out of range', 'earthx:look': { colormap: 'viridis', scale: 'percentiles', low: -1, high: 100 } },
    { name: 'blank', description: 'No colormap', 'earthx:look': { colormap: '', scale: 'measured' } },
  ];
  const withBands = meteo({ 'earthx:bands': bands });

  it('reads a fixed and a measured look as published', () => {
    expect(bandLookOf(withBands, 'TabsD')).toEqual({ colormap: 'rdbu_r', scale: 'fixed', low: -20, high: 30 });
    expect(bandLookOf(withBands, 'SrelD')).toEqual({ colormap: 'viridis', scale: 'fixed', low: 0, high: 100 });
    expect(bandLookOf(withBands, 'B04')).toEqual({ colormap: 'viridis', scale: 'measured' });
  });

  it('gives none for a band of classes, an unknown band, a collection without bands and no collection', () => {
    expect(bandLookOf(withBands, 'map')).toBeNull();
    expect(bandLookOf(withBands, 'nope')).toBeNull();
    expect(bandLookOf(meteo(), 'TabsD')).toBeNull();
    expect(bandLookOf(meteo({ 'earthx:bands': null }), 'TabsD')).toBeNull();
    expect(bandLookOf(undefined, 'TabsD')).toBeNull();
  });

  it('leaves out a look that is not complete: one end, an empty range, percentiles beyond 0–100, no colormap', () => {
    for (const band of ['odd', 'flat', 'wide', 'blank']) expect(bandLookOf(withBands, band), band).toBeNull();
  });
});

describe('fixedRangeOf (a fixed look in physical values, M5-68)', () => {
  it('takes the values of the look as they are, a reflectance as well as a percentage of clouds or a temperature', () => {
    const fixed = { colormap: 'viridis', scale: 'fixed' as const, low: 0, high: 0.3 };
    expect(fixedRangeOf(fixed)).toEqual({ vmin: '0', vmax: '0.3' });
    expect(fixedRangeOf({ ...fixed, low: 0, high: 100 })).toEqual({ vmin: '0', vmax: '100' });
    expect(fixedRangeOf({ ...fixed, low: -20, high: 30 })).toEqual({ vmin: '-20', vmax: '30' });
  });

  it('gives none for a range that comes from a measure', () => {
    expect(fixedRangeOf({ colormap: 'viridis', scale: 'measured' })).toBeNull();
    expect(fixedRangeOf({ colormap: 'viridis', scale: 'percentiles', low: 0, high: 100 })).toBeNull();
  });
});

describe('scalingOfBand (the scaling the registry states, M5-68)', () => {
  const collection = {
    'earthx:bands': [
      { name: 'red', description: '', 'earthx:scaling': { scale: 0.0001, offset: -0.1 } },
      { name: 'cloud', description: '' },
      { name: 'odd', description: '', 'earthx:scaling': { scale: 0, offset: 0 } },
      { name: 'text', description: '', 'earthx:scaling': { scale: '0.0001', offset: 0 } },
    ],
  } as unknown as Collection;

  it('reads it for a scaled band and none for an unscaled one, an unknown one or no band', () => {
    expect(scalingOfBand(collection, 'red')).toEqual({ scale: 0.0001, offset: -0.1 });
    expect(scalingOfBand(collection, 'cloud')).toBeNull();
    expect(scalingOfBand(collection, 'nothing')).toBeNull();
    expect(scalingOfBand(collection, undefined)).toBeNull();
    expect(scalingOfBand(undefined, 'red')).toBeNull();
  });

  it('reads none that cannot be turned back or is no number', () => {
    expect(scalingOfBand(collection, 'odd')).toBeNull();
    expect(scalingOfBand(collection, 'text')).toBeNull();
  });
});
