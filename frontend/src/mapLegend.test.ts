// The legends over the map (M5-62, Otto 24.11.2026): what each visible layer shows, from the tile URL the map draws it with, and in
// which order. Synthetic layers and collections only.

import { describe, expect, it } from 'vitest';

import type { BandClass } from './bandClasses';
import { datasetsFrom } from './datasets';
import type { MapLayer, ResultLayerInfo } from './layers';
import { chooseLegend, layersSignature, legendEntries, legendOfTile, legendPlace, NO_CHOICE, VIEW_LEGEND, type LegendEntry } from './mapLegend';
import type { Collection, DownloadedInfo } from './types';

const CLASSES: BandClass[] = [
  { value: 10, name: 'Tree cover', colour: '#006400' },
  { value: 20, name: 'Shrubland', colour: '#ffbb22' },
];
const T = 'https://tiles.example/{z}/{x}/{y}.png?assets=b';

describe('legendOfTile', () => {
  it('lists the classes of a class table or of the colours of classes, where the data names them', () => {
    expect(legendOfTile(`${T}&colormap_name=esa-worldcover`, CLASSES, null)).toEqual({ kind: 'classes', classes: CLASSES });
    expect(legendOfTile(`${T}&colormap=${encodeURIComponent('{"10":[0,100,0,255]}')}`, CLASSES, null)).toEqual({ kind: 'classes', classes: CLASSES });
    expect(legendOfTile(`${T}&colormap_name=esa-worldcover`, null, null)).toBeNull();
  });

  it('draws a bar from the range and colormap of the tiles, with the unit', () => {
    expect(legendOfTile(`${T}&colormap_name=viridis&rescale=0%2C2900`, null, 'm')).toEqual({ kind: 'bar', colormap: 'viridis', min: 0, max: 2900, unit: 'm' });
    expect(legendOfTile(`${T}&colormap_name=rdylgn_r&rescale=-1,1`, null, null)).toMatchObject({ colormap: 'rdylgn_r', min: -1, max: 1 });
    // A band stretched without a colormap is drawn in grey.
    expect(legendOfTile(`${T}&rescale=1,5`, null, null)).toMatchObject({ kind: 'bar', colormap: '' });
    // The range wins over the classes: a band of classes stretched like any other is a scale.
    expect(legendOfTile(`${T}&colormap_name=viridis&rescale=0,100`, CLASSES, null)).toMatchObject({ kind: 'bar' });
  });

  it('tells the ends in physical values (M5-60): the stored range turned with the scaling of the band, a step or an index as it is', () => {
    const reflectance = { scale: 0.0001, offset: -0.1 };
    expect(legendOfTile(`${T}&colormap_name=viridis&rescale=1000,4000`, null, null, reflectance)).toMatchObject({ min: expect.closeTo(0, 9), max: expect.closeTo(0.3, 9) });
    expect(legendOfTile(`${T}&expression=(b-a)&colormap_name=rdylgn&rescale=-1,1`, null, null, reflectance)).toMatchObject({ min: -1, max: 1 });
    expect(legendOfTile(`${T}&op=terrain&colormap_name=gray&rescale=0,255`, null, null, reflectance)).toMatchObject({ min: 0, max: 255 });
    expect(legendOfTile(`${T}&colormap_name=viridis&rescale=0,100`, null, '%')).toMatchObject({ min: 0, max: 100, unit: '%' });
  });

  it('has none for a colour picture, a picture drawn as it is, or a range that does not read', () => {
    expect(legendOfTile(`${T}&rescale=0,3000&rescale=0,3000&rescale=0,3000`, null, null)).toBeNull();
    expect(legendOfTile(`${T}&bidx=3&bidx=2&bidx=1&rescale=0,1`, null, null)).toBeNull();
    expect(legendOfTile(T, null, null)).toBeNull();
    expect(legendOfTile('https://tiles.example/{z}/{x}/{y}.png', CLASSES, null)).toBeNull();
    expect(legendOfTile(`${T}&rescale=a,b`, null, null)).toBeNull();
  });
});

const LAND = {
  id: 'land',
  title: 'Land cover',
  'earthx:band_units': { map: null, height: 'm', counts: 'DN' },
  'earthx:bands': [{ name: 'map', description: 'Land cover class', 'classification:classes': [
    { value: 10, name: 'tree_cover', title: 'Tree cover', color_hint: '006400' },
    { value: 20, name: 'shrubland', title: 'Shrubland', color_hint: 'FFBB22' },
  ] }],
} as unknown as Collection;
const DATASETS = datasetsFrom([LAND]);

const scene = (asset: string): DownloadedInfo => ({ datasetId: 'land', tileUrl: `https://tiles.example/{z}/{x}/{y}.png?assets=${asset}`, bounds: [0, 0, 1, 1], asset, minZoom: 0, maxZoom: 14 });

function layer(id: string, tileUrl: string, over: Partial<MapLayer> = {}, asset = 'map'): MapLayer {
  return {
    id,
    name: `Layer ${id}`,
    visible: true,
    opacity: 1,
    overlays: [{ kind: 'raster', tileUrl, bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 14 }],
    restore: { downloaded: { s: scene(asset) } } as unknown as MapLayer['restore'],
    ...over,
  };
}

const result = (info: Partial<ResultLayerInfo>): Partial<MapLayer> => ({
  derived: 'result',
  result: { jobID: 'J', expires: '2099-01-01T00:00:00Z', gsd: 10, resampled: false, expired: false, dataType: 'uint8', stats: null, ...info },
});

describe('legendEntries', () => {
  const classes = layer('a', 'https://tiles.example/{z}/{x}/{y}.png?assets=map&colormap_name=esa-worldcover');
  const heights = layer('b', 'https://tiles.example/{z}/{x}/{y}.png?assets=height&colormap_name=terrain&rescale=0,4000', {}, 'height');
  const counts = layer('c', 'https://tiles.example/{z}/{x}/{y}.png?assets=counts&rescale=1,500', {}, 'counts');
  const rgb = layer('d', 'https://tiles.example/{z}/{x}/{y}.png?assets=visual');

  it('has one legend per visible layer that has one, the topmost first, titled by the layer', () => {
    const entries = legendEntries({ layers: [classes, rgb, heights], resultsAt: 3, datasets: DATASETS, view: null });
    expect(entries.map((e) => [e.id, e.title, e.content.kind])).toEqual([
      ['a', 'Layer a', 'classes'],
      ['b', 'Layer b', 'bar'],
    ]);
  });

  it('has none for a hidden layer', () => {
    expect(legendEntries({ layers: [{ ...classes, visible: false }, heights], resultsAt: 0, datasets: DATASETS, view: null }).map((e) => e.id)).toEqual(['b']);
  });

  it('names only a physical unit: metres yes, digital numbers not, an index none', () => {
    const index = layer('i', 'https://tiles.example/{z}/{x}/{y}.png?assets=height&expression=(a-b)&colormap_name=rdylgn&rescale=-1,1', {}, 'height');
    const [h, c, i] = legendEntries({ layers: [heights, counts, index], resultsAt: 3, datasets: DATASETS, view: null });
    expect([h.content, c.content, i.content].map((content) => (content.kind === 'bar' ? content.unit : 'x'))).toEqual(['m', null, null]);
  });

  it('turns the range of a scaled band into physical values with the scaling of the scene, in a layer and in the view', () => {
    const stored = (asset: string): DownloadedInfo => ({ ...scene(asset), scalings: { height: { scale: 0.5, offset: 100 } } });
    const scaled = layer('h', 'https://tiles.example/{z}/{x}/{y}.png?assets=height&colormap_name=terrain&rescale=0,4000', { restore: { downloaded: { s: stored('height') } } as unknown as MapLayer['restore'] });
    const view = { downloaded: { s: stored('height') }, render: { colormapName: 'terrain', rescale: '0,4000' } };
    const [layerEntry, viewEntry] = legendEntries({ layers: [scaled], resultsAt: 1, datasets: DATASETS, view });
    expect(layerEntry.content).toMatchObject({ min: 100, max: 2100, unit: 'm' });
    expect(viewEntry.content).toMatchObject({ min: 100, max: 2100, unit: 'm' });
    // Another asset of the same scene is not scaled.
    expect(legendEntries({ layers: [counts], resultsAt: 1, datasets: DATASETS, view: null })[0].content).toMatchObject({ min: 1, max: 500 });
  });

  it('puts the view of the search where the entry "Search results" stands, titled by its dataset', () => {
    const view = { downloaded: { s: scene('map') }, render: { colormapName: 'esa-worldcover' } };
    const entries = legendEntries({ layers: [classes, heights], resultsAt: 1, datasets: DATASETS, view });
    expect(entries.map((e) => [e.id, e.title])).toEqual([
      ['a', 'Layer a'],
      [VIEW_LEGEND, 'Land cover'],
      ['b', 'Layer b'],
    ]);
  });

  it('has none, and fails on nothing, for a layer or a view without tiles', () => {
    const bare = { ...classes, overlays: [{ kind: 'raster' } as unknown as MapLayer['overlays'][number]] };
    const view = { downloaded: { s: { datasetId: 'land', asset: 'map' } as unknown as DownloadedInfo }, render: {} };
    expect(legendEntries({ layers: [bare], resultsAt: 1, datasets: DATASETS, view })).toEqual([]);
    expect(legendEntries({ layers: [], resultsAt: 0, datasets: DATASETS, view: { downloaded: {}, render: {} } })).toEqual([]);
  });

  it('takes the classes and the unit a result names, and none of an expired or deleted result', () => {
    const classed = layer('r', 'https://r.example/{z}/{x}/{y}?tilesize=256&colormap=x', result({ classes: true, legend: CLASSES }));
    const scaled = layer('s', 'https://r.example/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0,10', result({ dataType: 'float32', unit: 'm' }));
    const expired = layer('e', scaled.overlays[0].kind === 'raster' ? scaled.overlays[0].tileUrl : '', result({ expired: true }));
    const deleted = layer('x', classed.overlays[0].kind === 'raster' ? classed.overlays[0].tileUrl : '', result({ deleted: true, legend: CLASSES }));
    const entries = legendEntries({ layers: [classed, scaled, expired, deleted], resultsAt: 4, datasets: DATASETS, view: null });
    expect(entries.map((e) => e.content)).toEqual([
      { kind: 'classes', classes: CLASSES },
      { kind: 'bar', colormap: 'viridis', min: 0, max: 10, unit: 'm' },
    ]);
  });
});

describe('chooseLegend (Otto, 24.11.2026)', () => {
  const entry = (id: string): LegendEntry => ({ id, title: id, content: { kind: 'classes', classes: CLASSES } });
  const A = entry('a');
  const B = entry('b');

  it('shows the topmost, and a choice while the layers stay as they are', () => {
    const first = chooseLegend(NO_CHOICE, [A, B], 's1');
    expect(first).toEqual({ chosen: 'a', signature: 's1' });
    expect(chooseLegend({ ...first, chosen: 'b' }, [A, B], 's1').chosen).toBe('b');
  });

  it('goes back to the topmost when the layers change, and when the chosen one has no legend any more', () => {
    expect(chooseLegend({ chosen: 'b', signature: 's1' }, [A, B], 's2').chosen).toBe('a');
    expect(chooseLegend({ chosen: 'b', signature: 's1' }, [A], 's1').chosen).toBe('a');
    expect(chooseLegend({ chosen: 'b', signature: 's1' }, [], 's2').chosen).toBeNull();
  });
});

describe('layersSignature', () => {
  const one = layer('a', 'u');
  const two = layer('b', 'u');
  const entries = [{ id: 'a', title: 'a', content: { kind: 'classes' as const, classes: CLASSES } }];

  it('changes when a layer is added, removed, hidden, shown or moved, or the entries change, not with the look', () => {
    const base = layersSignature([one, two], 2, entries);
    expect(layersSignature([one, two, layer('c', 'u')], 3, entries)).not.toBe(base);
    expect(layersSignature([one], 1, entries)).not.toBe(base);
    expect(layersSignature([one, { ...two, visible: false }], 2, entries)).not.toBe(base);
    expect(layersSignature([two, one], 2, entries)).not.toBe(base);
    expect(layersSignature([one, two], 1, entries)).not.toBe(base);
    expect(layersSignature([one, two], 2, [])).not.toBe(base);
    expect(layersSignature([{ ...one, overlays: [] }, two], 2, entries)).toBe(base);
  });
});

// UI-12, Otto 25.11.2026: the legend never goes away; it folds where the map is too low, and its title goes into the status line where a
// panel would cover it or not even the title fits.
describe('the place of the legend', () => {
  it('is open at the bottom left where the map holds it', () => {
    expect(legendPlace({ covered: false, room: 300, head: 30, full: 120 })).toBe('open');
  });

  it('is its title there where the map holds the title but not the box', () => {
    expect(legendPlace({ covered: false, room: 80, head: 30, full: 120 })).toBe('folded');
  });

  it('is its title in the status line where a panel would cover it or not even the title fits', () => {
    expect(legendPlace({ covered: true, room: 300, head: 30, full: 120 })).toBe('docked');
    expect(legendPlace({ covered: false, room: 20, head: 30, full: 120 })).toBe('docked');
  });
});
