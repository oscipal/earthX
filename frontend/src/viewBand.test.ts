import { describe, expect, it } from 'vitest';

import type { Collection, StacItem } from './types';
import { bandAssetsOf, standardLookOfBand } from './viewBand';

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

describe('standardLookOfBand (Otto, H1 = 1)', () => {
  const item = day(['TabsD', 'TminD', 'TmaxD', 'SrelD']);

  it('gives a band in the unit of the standard band its colormap and starting range', () => {
    expect(standardLookOfBand(meteo(), item, 'TminD')).toEqual({ colormapName: 'rdbu_r', vmin: '-20', vmax: '30' });
    expect(standardLookOfBand(meteo(), item, 'TmaxD')).toEqual({ colormapName: 'rdbu_r', vmin: '-20', vmax: '30' });
  });

  it('leaves a band in another unit, the standard band itself and a band without unit to the measure', () => {
    expect(standardLookOfBand(meteo(), item, 'SrelD')).toBeNull();
    expect(standardLookOfBand(meteo(), item, 'TabsD')).toBeNull();
    expect(standardLookOfBand(meteo({ 'earthx:band_units': { TabsD: '°C' } }), item, 'TminD')).toBeNull();
  });

  it('gives nothing where the standard picture has no colormap or no range', () => {
    const render = meteo()['earthx:default_render']!;
    expect(standardLookOfBand(meteo({ 'earthx:default_render': { ...render, colormap_name: null } }), item, 'TminD')).toBeNull();
    expect(standardLookOfBand(meteo({ 'earthx:default_render': { ...render, rescale: null } }), item, 'TminD')).toBeNull();
  });
});
