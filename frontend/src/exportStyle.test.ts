import { describe, expect, it } from 'vitest';

import { exportStyleOf, resultLayerStyle, resultStyleOf, styleQuery } from './exportStyle';
import { SENTINEL_2_PRESETS } from './fixtures/indexPresets';
import type { MapLayer } from './layers';
import type { Collection } from './types';

const FALSE_COLOUR = {
  name: 'false_colour_ir',
  title: 'False colour (IR)',
  expressions: ['nir', 'red', 'green'],
  rescale: [[0, 0.5], [0, 0.3], [0, 0.3]],
  reference: 'https://example.org/false-colour',
};
const collection = (fields: Record<string, unknown>) => ({ id: 'x', ...fields }) as unknown as Collection;
const S2 = collection({
  'earthx:true_color': ['red', 'green', 'blue'],
  'earthx:default_render': { assets: ['visual'], rescale: [[0, 255]], colormap_name: null },
  'earthx:index_presets': SENTINEL_2_PRESETS,
  'earthx:composite_presets': [FALSE_COLOUR],
  'earthx:step_presets': [],
});
const DEM = collection({ 'earthx:true_color': [], 'earthx:default_render': { assets: ['dtm'], rescale: [[0, 5000]], colormap_name: 'terrain' } });
const CLASSES = collection({ 'earthx:true_color': [], 'earthx:default_render': { assets: ['map'], rescale: null, colormap_name: 'worldcover' } });

describe('exportStyleOf (M5-64)', () => {
  it('a band with its colormap and range, or grey without one', () => {
    expect(exportStyleOf({ band: 'red', colormapName: 'viridis', rescale: '0.02,0.24' }, S2)).toEqual({
      band: 'red',
      colormap: 'viridis',
      range: [0.02, 0.24],
    });
    expect(exportStyleOf({ band: 'vh', rescale: '-25,0' }, S2)).toEqual({ band: 'vh', colormap: null, range: [-25, 0] });
  });

  it('a composite as a colour picture of its bands, one range each', () => {
    const style = exportStyleOf({ index: 'false_colour_ir', rescale: '0,0.5;0,0.3;0,0.2' }, S2);
    expect(style).toEqual({ rgb: ['nir', 'red', 'green'], ranges: [[0, 0.5], [0, 0.3], [0, 0.2]] });
    expect(exportStyleOf({ index: 'false_colour_ir', rescale: '0,0.4' }, S2)).toEqual({
      rgb: ['nir', 'red', 'green'],
      ranges: [[0, 0.4], [0, 0.4], [0, 0.4]],
    });
  });

  it('a composite that computes a channel shows nothing the files hold', () => {
    const computed = collection({ ...S2, 'earthx:composite_presets': [{ ...FALSE_COLOUR, expressions: ['nir * 2', 'red', 'green'] }] });
    expect(exportStyleOf({ index: 'false_colour_ir', rescale: '0,0.5;0,0.3;0,0.2' }, computed)).toBeNull();
  });

  it('the standard picture of one band takes its asset', () => {
    expect(exportStyleOf({ colormapName: 'terrain', rescale: '400,1200' }, DEM)).toEqual({ band: 'dtm', colormap: 'terrain', range: [400, 1200] });
  });

  it('nothing for an index, a true-colour picture of an auxiliary asset, classes, a stored or unfinished range', () => {
    expect(exportStyleOf({ index: 'ndvi', colormapName: 'rdylgn', rescale: '-1,1' }, S2)).toBeNull();
    expect(exportStyleOf({ rescale: '0,255' }, S2)).toBeNull();
    expect(exportStyleOf({ colormapName: 'worldcover' }, CLASSES)).toBeNull();
    expect(exportStyleOf({ colormapName: 'terrain', rescale: '0,5000', stored: true }, DEM)).toBeNull();
    expect(exportStyleOf({ band: 'red', rescale: '0.3,0.1' }, S2)).toBeNull();
    expect(exportStyleOf({ band: 'red', rescale: '0,' }, S2)).toBeNull();
    expect(exportStyleOf({ band: 'red', rescale: '0,1;0,1;0,1' }, S2)).toBeNull();
    expect(exportStyleOf({ band: 'red' }, S2)).toBeNull();
    expect(exportStyleOf({}, undefined)).toBeNull();
  });
});

describe('resultStyleOf', () => {
  it('names the band at bidx, or three for a colour picture', () => {
    expect(resultStyleOf({ bidx: '2', colormapName: 'magma', rescale: '0,1' }, ['a', 'b'])).toEqual({ band: 'b', colormap: 'magma', range: [0, 1] });
    expect(resultStyleOf({ bidx: '3,2,1', rescale: '0,1;0,2;0,3' }, ['b', 'g', 'r'])).toEqual({
      rgb: ['r', 'g', 'b'],
      ranges: [[0, 1], [0, 2], [0, 3]],
    });
  });

  it('a result of one band needs no name', () => {
    expect(resultStyleOf({ colormapName: 'rdylgn', rescale: '-0.2,0.9' }, [])).toEqual({ band: 'band', colormap: 'rdylgn', range: [-0.2, 0.9] });
  });

  it('nothing for classes, a band it cannot name, no range', () => {
    expect(resultStyleOf({ colormap: '{"10":[0,100,0,255]}' }, [])).toBeNull();
    expect(resultStyleOf({ bidx: '3', rescale: '0,1' }, ['a', 'b'])).toBeNull();
    expect(resultStyleOf({ bidx: '0', rescale: '0,1' }, ['a'])).toBeNull();
    expect(resultStyleOf({ bidx: '1' }, ['a'])).toBeNull();
  });
});

describe('resultLayerStyle and styleQuery', () => {
  const layer = (tileUrl: string, names?: string[]) =>
    ({
      overlays: [{ kind: 'raster', tileUrl, bounds: [0, 0, 1, 1] }],
      result: names ? { bands: names.map((name) => ({ name, stats: null })) } : {},
    }) as unknown as MapLayer;

  it('reads what the layer draws from its tile URL', () => {
    const url = '/results/abc/tiles/{z}/{x}/{y}?tilesize=256&bidx=2&colormap_name=viridis&rescale=0.1%2C0.5';
    expect(resultLayerStyle(layer(url, ['a', 'b']))).toEqual({ band: 'b', colormap: 'viridis', range: [0.1, 0.5] });
    const rgb = '/results/abc/tiles/{z}/{x}/{y}?tilesize=256&bidx=1&bidx=2&bidx=3&rescale=0,1&rescale=0,2&rescale=0,3';
    expect(resultLayerStyle(layer(rgb, ['r', 'g', 'b']))).toEqual({ rgb: ['r', 'g', 'b'], ranges: [[0, 1], [0, 2], [0, 3]] });
    expect(resultLayerStyle({ overlays: [] } as unknown as MapLayer)).toBeNull();
  });

  it('puts the style into the address of the ZIP, or nothing', () => {
    const query = styleQuery({ band: 'b', colormap: null, range: [0, 1] });
    expect(JSON.parse(decodeURIComponent(query.replace('?style=', '')))).toEqual({ band: 'b', colormap: null, range: [0, 1] });
    expect(styleQuery(null)).toBe('');
  });
});
