import { describe, expect, it } from 'vitest';

import cop from './fixtures/processes/cop-dem-glo-30.json';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/synthetic-zarr.json';
import { bboxToPolygon, bufferPointToPolygon } from './geoUtils';
import { placeAoi } from './placeSearch';
import type { ProcessDescription } from './processing';
import { assetsCarrying, bandNamesOf, ownersOf } from './processingBands';
import {
  aoiProvenanceFor,
  aoiProvenanceOf,
  auxiliaryAssetsOf,
  bandSources,
  buildExportOrder,
  buildMosaicOrder,
  buildOrder,
  candidateItems,
  dataBandsOf,
  EMPTY_OUTPUT,
  formatBytes,
  formatDuration,
  lonelyBand,
  maskAssetOf,
  maskLayerOf,
  maskStepValues,
  namesInExpression,
  passesOf,
  processBlockReason,
  processInfo,
  registryUnit,
  selectableAssets,
  shownUnit,
  stepOfRefusal,
  type BandSource,
  type DraftStep,
} from './processingOrder';
import type { Collection, StacItem, TimeStepGroup } from './types';

const S2 = processInfo(s2 as unknown as ProcessDescription);
const ZARR = processInfo(zarr as unknown as ProcessDescription);
const DEM = processInfo(cop as unknown as ProcessDescription);

function item(id: string, assets: StacItem['assets'], bbox: [number, number, number, number] = [10, 50, 11, 51]): StacItem {
  return { id, bbox, geometry: bboxToPolygon(bbox), properties: {}, assets };
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

describe('processInfo from the fixtures (K3)', () => {
  it('lists the operators with tiers and kind, and the limits of the order', () => {
    expect(S2.operators.map((o) => [o.op, o.opVersion, o.tiers, o.kind])).toEqual([
      ['band_math', 2, ['T1', 'T2'], 'pixel'],
      ['mask', 2, ['T1', 'T2'], 'pixel'],
      ['normalize', 2, ['T1', 'T2'], 'pixel'],
      ['reproject', 4, ['T2'], 'grid'],
    ]);
    expect(S2).toMatchObject({ maxSteps: 16, variableSeparator: null });
    expect(S2.dtypes).toContain('float32');
  });

  it('knows no limit of bands: the order takes as many as the data has (adr/0020 §7)', () => {
    expect(S2).not.toHaveProperty('maxAssets');
  });

  it('reads the parameters band_math and normalize take in version 2: the name, and the bands as a list of names', () => {
    const form = (info: typeof S2, op: string) => {
      const operator = info.operators.find((o) => o.op === op)!;
      return operator.form.supported ? operator.form.fields : [];
    };
    expect(form(S2, 'band_math').map((f) => [f.name, f.kind, f.required])).toEqual([
      ['expression', 'string', true],
      ['name', 'string', true],
    ]);
    expect(form(S2, 'normalize').find((f) => f.name === 'bands')).toMatchObject({ kind: 'names', required: true, minItems: 1 });
    expect(form(S2, 'mask').map((f) => f.name).sort()).toEqual(['classes', 'source']);
  });

  it('reads the Zarr variable separator only where the dataset has one (F9)', () => {
    expect(ZARR.variableSeparator).toBe(':');
    expect(DEM.variableSeparator).toBeNull();
  });

  it.each([
    ['sentinel-2-c1-l2a', S2],
    ['synthetic-zarr', ZARR],
    ['cop-dem-glo-30', DEM],
  ])('%s: every operator has a form the panel supports', (_, info) => {
    expect(info.operators.length).toBeGreaterThan(0);
    for (const operator of info.operators) {
      expect(operator.form, operator.op).toMatchObject({ supported: true });
    }
  });

  it('leaves out a step variant it cannot read instead of guessing', () => {
    const broken = structuredClone(s2) as unknown as ProcessDescription;
    const schema = broken.inputs.recipe.schema as { $defs: Record<string, { properties: Record<string, unknown> }> };
    delete schema.$defs.step_reproject_v4.properties.op;
    expect(processInfo(broken).operators.map((o) => o.op)).toEqual(['band_math', 'mask', 'normalize']);
  });
});

describe('bandSources (K7)', () => {
  it('names a one-band COG asset like the asset', () => {
    const it1 = item('a', {
      red: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      thumbnail: { href: 'y', type: 'image/jpeg', roles: ['thumbnail'] },
    });
    expect(bandSources(it1, 'cog', null)).toEqual([
      { asset: 'red', names: ['red'], units: [null], unit: null, dataType: 'uint16', scaled: false, nodata: null },
    ]);
  });

  it('names the bands of a multi-band COG asset <asset>_1 … from raster:bands or bands', () => {
    const it1 = item('a', {
      visual: { href: 'x', type: COG, bands: [{}, {}, {}] },
    });
    expect(bandSources(it1, 'cog', null)[0].names).toEqual(['visual_1', 'visual_2', 'visual_3']);
  });

  it('reads bands where raster:bands is there but empty, as the backend does', () => {
    const it1 = item('a', { visual: { href: 'x', type: COG, 'raster:bands': [], bands: [{ data_type: 'uint8' }, {}] } });
    expect(bandSources(it1, 'cog', null)[0]).toMatchObject({ asset: 'visual', names: ['visual_1', 'visual_2'], dataType: 'uint8' });
  });

  it('reads what the item says about scaling and nodata', () => {
    const it1 = item('a', {
      // as the real Sentinel-2 item has it: scaled, with a nodata value
      red: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint16', nodata: 0, scale: 0.0001, offset: -0.1 }] },
      // no scaling, a nodata value
      scl: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] },
      // a multiband asset with one nodata value in one band only
      multi: { href: 'x', type: COG, bands: [{ data_type: 'uint8', nodata: 255 }, {}] },
      // two bands that disagree on nodata
      odd: { href: 'x', type: COG, bands: [{ nodata: 0 }, { nodata: 1 }] },
      // nodata NaN is no value an integer type can hold
      flt: { href: 'x', type: COG, bands: [{ data_type: 'float32', nodata: 'nan' }] },
    });
    const by = Object.fromEntries(bandSources(it1, 'cog', null).map((b) => [b.asset, b]));
    expect(by.red).toMatchObject({ scaled: true, nodata: 0 });
    expect(by.scl).toMatchObject({ scaled: false, nodata: 0 });
    expect(by.multi.nodata).toBeNull();
    expect(by.odd.nodata).toBeNull();
    expect(by.flt.nodata).toBeNull();
  });

  it('offers a COG asset without band descriptions with no name to insert', () => {
    const dem = item('d', { data: { href: 'x', type: 'image/tiff; application=geotiff' } });
    expect(bandSources(dem, 'cog', null)).toEqual([
      { asset: 'data', names: [], units: [], unit: null, dataType: null, scaled: false, nodata: null },
    ]);
  });

  it('names Zarr variables from the core field bands, one order asset per variable', () => {
    const z = item('z', {
      SR_10m: { href: 'x', type: 'application/vnd+zarr', bands: [{ name: 'b04' }, { name: 'b08' }] },
      product: { href: 'y', type: 'application/vnd+zarr' },
    });
    expect(bandSources(z, 'zarr', ':')).toEqual([
      { asset: 'SR_10m:b04', names: ['b04'], units: [null], unit: null, dataType: null, scaled: false, nodata: null },
      { asset: 'SR_10m:b08', names: ['b08'], units: [null], unit: null, dataType: null, scaled: false, nodata: null },
    ]);
  });

  it('offers nothing for Zarr without a separator', () => {
    const z = item('z', { SR_10m: { href: 'x', bands: [{ name: 'b04' }] } });
    expect(bandSources(z, 'zarr', null)).toEqual([]);
  });

  it('offers nothing for a Zarr asset that lists no band names, also if an extension field names them', () => {
    const z = item('z', {
      SR_10m: { href: 'x', 'eo:bands': [{ name: 'b04' }] } as never,
      SR_20m: { href: 'y', bands: [{}, { name: '' }] },
    });
    expect(bandSources(z, 'zarr', ':')).toEqual([]);
  });
});

describe('the unit of a band (M4-19b)', () => {
  const collection = (units: unknown): Collection => ({ id: 'c', 'earthx:band_units': units }) as unknown as Collection;
  const REGISTRY = collection({ red: '1', scl: null, data: 'm', 'SR_*': '1' });

  it('takes the unit of a COG asset from the registry where the item states none', () => {
    const it1 = item('a', {
      red: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      scl: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint8' }] },
      aot: { href: 'x', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
    });
    const by = Object.fromEntries(bandSources(it1, 'cog', null, REGISTRY).map((b) => [b.asset, b.units]));
    expect(by).toEqual({ red: ['1'], scl: [null], aot: [null] });
  });

  it('lets the unit of the item go before the registry', () => {
    const it1 = item('a', { red: { href: 'x', type: COG, 'raster:bands': [{ unit: 'percent' }] } });
    expect(bandSources(it1, 'cog', null, REGISTRY)[0].units).toEqual(['percent']);
  });

  it('gives each band of a multi-band asset its own unit, the registry standing in for the rest', () => {
    const it1 = item('a', { red: { href: 'x', type: COG, bands: [{ unit: 'K' }, {}] } });
    expect(bandSources(it1, 'cog', null, REGISTRY)[0].units).toEqual(['K', '1']);
  });

  it('gives an asset with no band description the unit of the registry for the asset', () => {
    const dem = item('d', { data: { href: 'x', type: COG } });
    expect(bandSources(dem, 'cog', null, REGISTRY)[0]).toMatchObject({ names: [], units: [], unit: 'm' });
  });

  it('finds the unit of a Zarr variable by its key, with a group pattern', () => {
    const z = item('z', { SR_10m: { href: 'x', bands: [{ name: 'b04' }, { name: 'b08', unit: 'percent' }] } });
    expect(bandSources(z, 'zarr', ':', REGISTRY).map((b) => b.unit)).toEqual(['1', 'percent']);
  });

  it.each([
    ['not a unit', 5],
    ['blank', ''],
    ['a list', ['m']],
    ['an object', { symbol: 'm' }],
  ])('does not take %s from an item for a unit', (_, unit) => {
    const it1 = item('a', { red: { href: 'x', type: COG, 'raster:bands': [{ unit }] as never } });
    expect(bandSources(it1, 'cog', null)[0].units).toEqual([null]);
  });

  it('knows no unit without the field, or where the field is not a table of texts', () => {
    const it1 = item('a', { red: { href: 'x', type: COG, 'raster:bands': [{}] } });
    for (const field of [undefined, null, [], 'm', { red: 5 }, { red: '' }]) {
      expect(bandSources(it1, 'cog', null, collection(field))[0].units).toEqual([null]);
    }
    expect(bandSources(it1, 'cog', null)[0].units).toEqual([null]);
  });
});

describe('shownUnit (Otto, 24.10.2026)', () => {
  it('writes a unit as it is', () => {
    expect(shownUnit('m')).toBe('m');
    expect(shownUnit('percent')).toBe('percent');
  });

  it('writes nothing for "1", for no unit and for what is no unit', () => {
    for (const unit of ['1', '', null, undefined, 1, ['m']]) expect(shownUnit(unit as never)).toBeNull();
  });

  it('writes "10" and " 1" as they are: only the exact "1" is dimensionless', () => {
    expect(shownUnit('10')).toBe('10');
    expect(shownUnit(' 1')).toBe(' 1');
  });

  it('leaves the data alone: the sources keep "1"', () => {
    const it1 = item('a', { red: { href: 'x', type: COG, 'raster:bands': [{ unit: '1' }] } });
    expect(bandSources(it1, 'cog', null)[0].units).toEqual(['1']);
  });
});

describe('registryUnit', () => {
  const units = { 'SR_*': '1', 'SR_20m:b05': 'x', 'a.b*': 'dot', 'p(1)*': 'paren', data: 'm', none: null };
  const collection = { id: 'c', 'earthx:band_units': units } as unknown as Collection;

  it('takes the exact key before a pattern', () => {
    expect(registryUnit(collection, 'SR_20m:b05')).toBe('x');
    expect(registryUnit(collection, 'SR_20m:b06')).toBe('1');
  });

  it('matches a pattern over the whole key only, and its other characters literally', () => {
    expect(registryUnit(collection, 'xSR_10m:b04')).toBeNull();
    expect(registryUnit(collection, 'a.bc')).toBe('dot');
    expect(registryUnit(collection, 'aXbc')).toBeNull();
    expect(registryUnit(collection, 'p(1)x')).toBe('paren');
    expect(registryUnit(collection, 'p1x')).toBeNull();
  });

  it('says null for an unknown key, an explicit unknown and a key of Object.prototype', () => {
    expect(registryUnit(collection, 'other')).toBeNull();
    expect(registryUnit(collection, 'none')).toBeNull();
    expect(registryUnit(collection, 'constructor')).toBeNull();
    expect(registryUnit(undefined, 'data')).toBeNull();
  });
});

describe('the assets of the order', () => {
  const plain = { units: [null], unit: null, dataType: null, scaled: false, nodata: null };
  const sources: BandSource[] = [
    { asset: 'red', names: ['red'], ...plain },
    { asset: 'nir', names: ['nir'], ...plain },
    { asset: 'scl', names: ['scl'], ...plain },
    { asset: 'A:b04', names: ['b04'], ...plain },
    { asset: 'B:b04', names: ['b04'], ...plain },
  ];

  it('finds the names of an expression, not its functions', () => {
    expect([...namesInExpression('where(nir > 0.1, (nir - red) / (nir + red), 1e5)')].sort()).toEqual(['nir', 'red']);
    expect(namesInExpression('sqrt (red)').has('sqrt')).toBe(false);
  });

  it('reads the assets that carry the names an expression and the output use, in the item order', () => {
    const names = [...namesInExpression('(nir - red)'), 'scl'];
    expect(assetsCarrying(sources, names)).toEqual(['red', 'nir', 'scl']);
  });

  it('leaves a name two assets carry to the user', () => {
    expect(ownersOf(sources).has('b04')).toBe(false);
    expect(assetsCarrying(sources, ['b04'])).toEqual([]);
  });

  it('takes an asset once, however many of its names are asked for', () => {
    const visual: BandSource = { asset: 'visual', names: ['visual_1', 'visual_2', 'visual_3'], ...plain, units: [null, null, null] };
    expect(assetsCarrying([...sources, visual], ['visual_3', 'visual_1', 'red', 'red'])).toEqual(['red', 'visual']);
  });

  it('does not invent an asset the scene lacks: a result, a typo, a band of another dataset', () => {
    expect(assetsCarrying(sources, ['red', 'NDVI', 'SCL_20m:scl', 'blue'])).toEqual(['red']);
  });

  it('names an asset the item does not describe like its key', () => {
    expect(bandNamesOf({ asset: 'data', names: [], ...plain, units: [] })).toEqual(['data']);
    expect(assetsCarrying([{ asset: 'data', names: [], ...plain, units: [] }], ['data'])).toEqual(['data']);
  });
});

describe('the bands of the data (adr/0020 §14)', () => {
  const plain = { dataType: null, scaled: false, nodata: null };
  const one = (asset: string, unit: string | null = null): BandSource => ({ asset, names: [asset], units: [unit], unit, ...plain });
  const sources: BandSource[] = [
    one('red', '1'),
    one('nir'),
    one('scl'),
    one('visual'),
    { asset: 'multi', names: ['multi_1', 'multi_2'], units: ['K', 'percent'], unit: null, ...plain },
    { asset: 'dem', names: [], units: [], unit: 'm', ...plain },
  ];

  it('lists every band in the order of the item, with its asset and the unit to show', () => {
    expect(dataBandsOf(sources, [], null)).toEqual([
      { name: 'red', asset: 'red', unit: null, auxiliary: false, layer: false },
      { name: 'nir', asset: 'nir', unit: null, auxiliary: false, layer: false },
      { name: 'scl', asset: 'scl', unit: null, auxiliary: false, layer: false },
      { name: 'visual', asset: 'visual', unit: null, auxiliary: false, layer: false },
      { name: 'multi_1', asset: 'multi', unit: 'K', auxiliary: false, layer: false },
      { name: 'multi_2', asset: 'multi', unit: 'percent', auxiliary: false, layer: false },
      { name: 'dem', asset: 'dem', unit: 'm', auxiliary: false, layer: false },
    ]);
  });

  it('marks what the registry says is no band, and the layer of the mask', () => {
    const bands = dataBandsOf(sources, ['visual'], 'scl');
    expect(bands.filter((b) => b.auxiliary).map((b) => b.name)).toEqual(['visual']);
    expect(bands.filter((b) => b.layer).map((b) => b.name)).toEqual(['scl']);
    expect(bands).toHaveLength(7);
  });

  it('leaves out a name two assets carry: an order cannot name it', () => {
    const twins = [one('red'), { asset: 'A:b04', names: ['b04'], units: [null], unit: null, ...plain }, { asset: 'B:b04', names: ['b04'], units: [null], unit: null, ...plain }];
    expect(dataBandsOf(twins, [], null).map((b) => b.name)).toEqual(['red']);
  });

  it('is empty for an item with no bands', () => {
    expect(dataBandsOf([], [], null)).toEqual([]);
  });

  it('selects the assets that are bands: not the auxiliary ones, not the layer of the mask', () => {
    expect(selectableAssets(sources, ['visual'], 'scl')).toEqual(['red', 'nir', 'multi', 'dem']);
    expect(selectableAssets(sources, [], null)).toHaveLength(6);
    expect(selectableAssets([], [], null)).toEqual([]);
  });

  it('knows the auxiliary assets only from the registry, and only texts', () => {
    const collection = (field: unknown) => ({ id: 'c', 'earthx:auxiliary_assets': field }) as unknown as Collection;
    expect(auxiliaryAssetsOf(collection(['visual', 'preview']))).toEqual(['visual', 'preview']);
    expect(auxiliaryAssetsOf(collection(['visual', 3, null]))).toEqual(['visual']);
    for (const field of [undefined, null, 'visual', { visual: true }]) expect(auxiliaryAssetsOf(collection(field))).toEqual([]);
    expect(auxiliaryAssetsOf(undefined)).toEqual([]);
  });

  it('finds the one band of a dataset that has one, by its name', () => {
    expect(lonelyBand(['dem'], [one('dem')])).toBe('dem');
    expect(lonelyBand(['dem'], [{ asset: 'dem', names: [], units: [], unit: 'm', ...plain }])).toBe('dem');
    expect(lonelyBand(['z:b04'], [{ asset: 'z:b04', names: ['b04'], units: [null], unit: null, ...plain }])).toBe('b04');
  });

  it('finds none where there are several bands, one asset with several, or nothing', () => {
    expect(lonelyBand(['red', 'nir'], sources)).toBeNull();
    expect(lonelyBand(['multi'], sources)).toBeNull();
    expect(lonelyBand([], sources)).toBeNull();
    expect(lonelyBand(['gone'], sources)).toBeNull();
  });
});

describe('the layer a mask reads (M4-18c)', () => {
  const layer = {
    asset: 'SCL_20m:scl',
    band: 'scl',
    classes: [
      { value: 3, label: 'CLOUD_SHADOWS' },
      { value: 8, label: 'CLOUD_MEDIUM_PROBABILITY' },
      { value: 10, label: 'THIN_CIRRUS' },
    ],
    suggested: [10, 3],
    reference: 'https://sentiwiki.copernicus.eu/web/s2-processing',
    note: 'Older baselines name some classes differently.',
  };
  const collection = (mask: unknown) => ({ id: 'x', 'earthx:mask': mask }) as unknown as Collection;

  it('is read from the collection as the registry writes it', () => {
    expect(maskLayerOf(collection(layer))).toEqual(layer);
  });

  it.each([
    ['no field', undefined],
    ['null, as a dataset without a layer serves it', null],
    ['a text', 'scl'],
    ['no asset', { ...layer, asset: '' }],
    ['no band', { ...layer, band: undefined }],
    ['no classes', { ...layer, classes: [] }],
    ['a class without a label', { ...layer, classes: [{ value: 3 }] }],
    ['a class value with a fraction', { ...layer, classes: [{ value: 3.5, label: 'x' }] }],
  ])('has none for %s', (_, mask) => {
    expect(maskLayerOf(collection(mask))).toBeNull();
    expect(maskLayerOf(undefined)).toBeNull();
  });

  it('keeps no suggestion the table does not hold, and no link that is not https', () => {
    const read = maskLayerOf(collection({ ...layer, suggested: [3, 99, 'x'], reference: 'javascript:alert(1)' }))!;
    expect(read.suggested).toEqual([3]);
    expect(read.reference).toBe('');
    expect(maskLayerOf(collection({ ...layer, reference: 'http://example.org/' }))!.reference).toBe('');
  });

  it('starts a mask step with the layer band and the suggested classes ascending', () => {
    expect(maskStepValues(layer)).toEqual({ source: 'scl', classes: '3, 10' });
    expect(maskStepValues({ ...layer, suggested: [] })).toEqual({ source: 'scl', classes: '' });
  });

  it('is found among the variables of a Zarr item, as <asset>:<variable>', () => {
    const zarrItem = {
      id: 'z',
      properties: {},
      assets: {
        SCL_20m: { href: 'https://example.org/scl20', type: 'application/vnd+zarr', bands: [{ name: 'scl' }] },
        reflectance: { href: 'https://example.org/r', type: 'application/vnd+zarr', bands: [{ name: 'b04' }] },
      },
    } as unknown as StacItem;
    const sources = bandSources(zarrItem, 'zarr', ':');
    expect(sources.map((s) => s.asset)).toEqual(['SCL_20m:scl', 'reflectance:b04']);
    expect(assetsCarrying(sources, ['b04', layer.band])).toEqual(['SCL_20m:scl', 'reflectance:b04']);
  });

  it('needs its asset only while a mask step is in the order', () => {
    expect(maskAssetOf([{ op: 'band_math' }, { op: 'mask' }], layer)).toBe('SCL_20m:scl');
    expect(maskAssetOf([{ op: 'band_math' }], layer)).toBeNull();
    expect(maskAssetOf([{ op: 'mask' }], null)).toBeNull();
  });
});

describe('candidateItems (F8)', () => {
  const aoi = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);

  it('keeps the scenes whose footprint meets the AOI', () => {
    const a = item('a', {}, [10, 50, 11, 51]);
    const b = item('b', {}, [10.5, 50.5, 11.5, 51.5]);
    const far = item('far', {}, [20, 50, 21, 51]);
    expect(candidateItems([a, b, far], aoi).map((i) => i.id)).toEqual(['a', 'b']);
  });

  it('drops a scene whose bbox meets the AOI but whose footprint does not', () => {
    const diagonal: StacItem = {
      id: 'diag',
      bbox: [10, 50, 11, 51],
      geometry: { type: 'Polygon', coordinates: [[[10, 50], [10.3, 50], [10, 50.3], [10, 50]]] },
      properties: {},
      assets: {},
    };
    expect(candidateItems([diagonal], aoi)).toEqual([]);
  });

  it('keeps a scene without a footprint: the server says what it skips', () => {
    expect(candidateItems([{ id: 'n', properties: {}, assets: {} }], aoi)).toHaveLength(1);
  });

  it('takes the buffered square of a point as the AOI, as the crop does (K11)', () => {
    const square = bufferPointToPolygon(10.5, 50.5, 0.05);
    expect(candidateItems([item('a', {})], square)).toHaveLength(1);
  });
});

describe('passesOf (M4-12b)', () => {
  const group = (label: string, items: StacItem[]): TimeStepGroup => ({ key: [label], label, items });
  const a = item('a', {});
  const b = item('b', {});
  const c = item('c', {});

  it('splits the scenes by the group of the results list, in the order of the list', () => {
    const groups = [group('2026-07-02', [c]), group('2026-07-01', [a, b])];
    const passes = passesOf([b, c, a], groups);
    expect(passes.map((p) => [p.label, p.items.map((i) => i.id)])).toEqual([
      ['2026-07-02', ['c']],
      ['2026-07-01', ['b', 'a']],
    ]);
  });

  it('gives each pass its own key', () => {
    const groups = [group('x', [a]), group('y', [b])];
    const keys = passesOf([a, b], groups).map((p) => p.key);
    expect(new Set(keys).size).toBe(2);
  });

  it('puts a scene the list does not know into a pass of its own, last', () => {
    const passes = passesOf([c, a], [group('2026-07-01', [a])]);
    expect(passes.map((p) => [p.label, p.items.map((i) => i.id)])).toEqual([
      ['2026-07-01', ['a']],
      ['Other scenes', ['c']],
    ]);
  });

  it('is empty without scenes', () => {
    expect(passesOf([], [group('x', [a])])).toEqual([]);
  });
});

describe('buildOrder', () => {
  const step = (op: string, opVersion: number, values: DraftStep['values'], key = 1): DraftStep => ({ key, op, opVersion, values });
  const ndvi = (name = 'NDVI', key = 1, expression = '(nir - red) / (nir + red)') => step('band_math', 2, { expression, name }, key);
  const aoi = bboxToPolygon([10.4, 50.4, 10.6, 50.6]);
  const DATA = ['blue', 'green', 'red', 'nir', 'scl'];
  const base = {
    datasetId: 'sentinel-2-c1-l2a',
    itemIds: ['S2B_X'],
    area: 'aoi' as const,
    aoi,
    steps: [ndvi()],
    bands: ['NDVI'],
    data: DATA,
    dtype: 'float32',
    info: S2,
  };
  const errorsOf = (built: ReturnType<typeof buildOrder>) => built.stepProblems.map((p) => p.errors);

  it('builds the envelope of version 2: one input named "input" with one item and no assets, the AOI, the bands of the output', () => {
    expect(buildOrder(base).order).toEqual({
      recipe_version: 2,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_X']] }],
      aoi,
      steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'NDVI' } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI'] },
    });
  });

  it('writes the bands of the output in the order given, results and bands of the data, each as it was named', () => {
    const order = buildOrder({ ...base, bands: ['NDVI', 'blue', 'red'] }).order;
    expect(order?.output).toEqual({ kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI', 'blue', 'red'] });
  });

  it('does not hold on to the list of bands it was given', () => {
    const bands = ['NDVI'];
    const order = buildOrder({ ...base, bands }).order!;
    bands.push('red');
    expect(order.output).toMatchObject({ bands: ['NDVI'] });
  });

  it('takes more than 16 bands: an order has no limit of bands (adr/0020 §7)', () => {
    const many = Array.from({ length: 40 }, (_, i) => `b${i}`);
    const built = buildOrder({ ...base, bands: many, data: [...DATA, ...many] });
    expect(built.problems).toEqual([]);
    expect(built.order?.output).toMatchObject({ bands: many });
  });

  it('sends no AOI for "Whole scene", and needs none (M4-13c §3.2)', () => {
    const order = buildOrder({ ...base, area: 'scene', aoi: null }).order;
    expect(order).not.toBeNull();
    expect(order).not.toHaveProperty('aoi');
    expect(buildOrder({ ...base, area: 'scene' }).order).toEqual(order);
  });

  it('needs an area for "AOI only"', () => {
    const built = buildOrder({ ...base, aoi: null });
    expect(built.order).toBeNull();
    expect(built.problems).toContain('Draw an area as AOI.');
  });

  it('puts all scenes of the pass into one group, sorted, so the same scenes are the same order', () => {
    const forward = buildOrder({ ...base, itemIds: ['S2B_B', 'S2B_A', 'S2B_C'] }).order;
    const backward = buildOrder({ ...base, itemIds: ['S2B_C', 'S2B_A', 'S2B_B'] }).order;
    expect(forward?.inputs[0].groups).toEqual([['S2B_A', 'S2B_B', 'S2B_C']]);
    expect(backward).toEqual(forward);
  });

  it('turns reprojection numbers into numbers and keeps the boolean', () => {
    const order = buildOrder({
      ...base,
      steps: [step('reproject', 4, { crs: 'EPSG:3035', resolution: '30', resampling: 'bilinear', align: false })],
      bands: ['red'],
    }).order;
    expect(order?.steps[0].params).toEqual({ crs: 'EPSG:3035', resolution: 30, resampling: 'bilinear', align: false });
  });

  it('writes the bands of a normalize step as a list of names, each once, in the order typed', () => {
    const normalize = step('normalize', 2, { bands: 'red, nir;red', in_min: '0', in_max: '1', out_min: '0', out_max: '255', clip: false });
    const order = buildOrder({ ...base, steps: [normalize], bands: ['red', 'nir'] }).order;
    expect(order?.steps[0].params).toMatchObject({ bands: ['red', 'nir'], in_min: 0, out_max: 255, clip: false });
  });

  it('writes a mask step with its layer band and its classes ascending', () => {
    const mask = step('mask', 2, { source: 'scl', classes: '10, 3' });
    const order = buildOrder({ ...base, steps: [mask, ndvi('NDVI', 2)] }).order;
    expect(order?.steps[0]).toEqual({ op: 'mask', op_version: 2, params: { source: 'scl', classes: [3, 10] } });
    expect(order?.output).toMatchObject({ bands: ['NDVI'] });
  });

  it.each([
    ['no scene', { itemIds: [] }, 'Pick a pass.'],
    ['a line as AOI', { aoi: { type: 'LineString', coordinates: [[0, 0], [1, 1]] } }, 'Draw an area as AOI.'],
    ['no step', { steps: [] }, 'Add a step.'],
    ['17 steps', { steps: Array.from({ length: 17 }, () => base.steps[0]) }, 'At most 16 steps.'],
    ['no band in the output', { bands: [] }, EMPTY_OUTPUT],
    ['no data type', { dtype: '' }, 'Pick an output data type.'],
  ])('blocks %s', (_, change, problem) => {
    const built = buildOrder({ ...base, ...change } as Parameters<typeof buildOrder>[0]);
    expect(built.order).toBeNull();
    expect(built.problems).toContain(problem);
  });

  it('says why the output is empty, in the words of the Start button', () => {
    expect(EMPTY_OUTPUT).toBe('Pick at least one band for the output.');
  });

  it('blocks a step whose form does not fit and says where', () => {
    const built = buildOrder({ ...base, steps: [ndvi('NDVI', 1, '')] });
    expect(built.order).toBeNull();
    expect(built.stepProblems[0].errors).toEqual({ expression: 'Required.' });
  });

  it('blocks an operator the dataset does not offer', () => {
    const built = buildOrder({ ...base, steps: [step('decomp', 1, {})] });
    expect(built.order).toBeNull();
    expect(built.stepProblems[0].unsupported).toMatch(/not available/);
  });

  it('blocks an operator version the dataset no longer lists', () => {
    const built = buildOrder({ ...base, steps: [step('band_math', 1, { expression: 'nir' })] });
    expect(built.order).toBeNull();
    expect(built.stepProblems[0].unsupported).toMatch(/not available/);
  });

  describe('the name of the band a band_math step adds (adr/0020 §6)', () => {
    it.each([
      ['no name', '', 'Enter a name'],
      ['a digit first', '1NDVI', /^Use letters, digits and _, a letter first/u],
      ['a space', 'my ndvi', /^Use letters, digits and _, a letter first/u],
      ['a dash', 'ndvi-1', /^Use letters, digits and _, a letter first/u],
      ['33 characters', 'N'.repeat(33), /at most 32 characters/u],
      ['a Python keyword', 'in', "'in' cannot be used in an expression"],
      ['the name of a function', 'sqrt', "'sqrt' is the name of a function"],
      ['the name of a band of the data', 'red', "'red' is already a band name"],
      ['the name of a band of the data in other case', 'RED', "'RED' is already a band name"],
    ])('refuses %s', (_, name, problem) => {
      const built = buildOrder({ ...base, steps: [ndvi(name)], bands: ['NDVI'] });
      expect(built.order).toBeNull();
      expect(built.stepProblems[0].errors.name).toMatch(problem);
    });

    it('takes 32 characters and a name that holds a band of the data as a part', () => {
      expect(buildOrder({ ...base, steps: [ndvi('N'.repeat(32))], bands: ['NDVI'] }).stepProblems[0].errors).toEqual({});
      expect(buildOrder({ ...base, steps: [ndvi('red_edge')], bands: ['red_edge'] }).stepProblems[0].errors).toEqual({});
    });

    it('refuses a name two steps share, in both of them, also in other case', () => {
      const built = buildOrder({ ...base, steps: [ndvi('NDVI', 1), ndvi('ndvi', 2, 'nir - red')] });
      expect(built.order).toBeNull();
      expect(errorsOf(built)).toEqual([
        { name: "'NDVI' is already used by another step" },
        { name: "'ndvi' is already used by another step" },
      ]);
    });

    it('does not count a step against itself, and not a step of another operator', () => {
      const built = buildOrder({ ...base, steps: [step('mask', 2, { source: 'scl', classes: '3' }, 1), ndvi('NDVI', 2)] });
      expect(errorsOf(built)).toEqual([{}, {}]);
    });
  });

  describe('the results a step reads (adr/0020 §4)', () => {
    it('lets a later step read the result of an earlier one', () => {
      const built = buildOrder({ ...base, steps: [ndvi('NDVI', 1), ndvi('Ratio', 2, 'NDVI * 2')], bands: ['NDVI', 'Ratio'] });
      expect(built.problems).toEqual([]);
      expect(errorsOf(built)).toEqual([{}, {}]);
      expect(built.order?.steps.map((s) => s.params.name)).toEqual(['NDVI', 'Ratio']);
    });

    it('refuses an expression that reads the result of a later step, naming it', () => {
      const built = buildOrder({ ...base, steps: [ndvi('First', 1, 'Second * 2'), ndvi('Second', 2)], bands: ['First', 'Second'] });
      expect(built.order).toBeNull();
      expect(errorsOf(built)).toEqual([{ expression: "'Second' is added by a later step" }, {}]);
    });

    it('refuses an expression that reads the band its own step adds', () => {
      const built = buildOrder({ ...base, steps: [ndvi('NDVI', 1, 'NDVI + 1')] });
      expect(errorsOf(built)).toEqual([{ expression: "'NDVI' is the band this step adds" }]);
    });

    it('does not take a function call or a longer name for a read of the result', () => {
      const longer = buildOrder({
        ...base,
        data: [...DATA, 'NDVI_22'],
        steps: [ndvi('First', 1, 'where(nir > 0, NDVI_22, red)'), ndvi('NDVI_2', 2)],
        bands: ['First', 'NDVI_2'],
      });
      expect(longer.stepProblems[0].errors).toEqual({});
      const call = buildOrder({ ...base, steps: [ndvi('First', 1, 'Ratio(red)'), ndvi('Ratio', 2)] });
      expect(call.stepProblems[0].errors).toEqual({});
    });

    it('refuses the bands of a normalize step that name a result added later', () => {
      const normalize = step('normalize', 2, { bands: 'Later', in_min: '0', in_max: '1', out_min: '0', out_max: '1', clip: false }, 1);
      const built = buildOrder({ ...base, steps: [normalize, ndvi('Later', 2)], bands: ['Later'] });
      expect(built.order).toBeNull();
      expect(errorsOf(built)[0]).toEqual({ bands: "'Later' is added by a later step" });
    });

    it('refuses an expression that names something that is no band, with the name (review of #250)', () => {
      const built = buildOrder({ ...base, steps: [ndvi('NDVI', 1, 'nir - re')] });
      expect(built.order).toBeNull();
      expect(errorsOf(built)).toEqual([{ expression: "'re' is not a band name" }]);
    });

    it('takes the bands of the data and the results of the steps before, and numbers and functions, as bands', () => {
      const steps = [ndvi('NDVI', 1), ndvi('Ratio', 2, 'where(NDVI > 0.5e1, sqrt(nir), minimum(red, 2)) + NDVI')];
      expect(errorsOf(buildOrder({ ...base, steps, bands: ['NDVI', 'Ratio'] }))).toEqual([{}, {}]);
    });

    it('says a result of a later step is added later, not that it is no band', () => {
      const built = buildOrder({ ...base, steps: [ndvi('First', 1, 'Second + re'), ndvi('Second', 2)] });
      expect(errorsOf(built)[0]).toEqual({ expression: "'Second' is added by a later step" });
    });

    it('has nothing to compare with where the data list no bands', () => {
      expect(errorsOf(buildOrder({ ...base, data: [], steps: [ndvi('NDVI', 1, 'whatever + 1')] }))).toEqual([{}]);
    });

    it('lets a normalize step name the result of an earlier step, and asks for at least one band', () => {
      const values = { in_min: '0', in_max: '1', out_min: '0', out_max: '1', clip: false };
      const ok = buildOrder({ ...base, steps: [ndvi('NDVI', 1), step('normalize', 2, { ...values, bands: 'NDVI' }, 2)] });
      expect(ok.problems).toEqual([]);
      expect(errorsOf(ok)).toEqual([{}, {}]);
      const none = buildOrder({ ...base, steps: [ndvi('NDVI', 1), step('normalize', 2, { ...values, bands: '' }, 2)] });
      expect(errorsOf(none)[1]).toEqual({ bands: 'Pick at least one band.' });
    });
  });
});

describe('buildMosaicOrder (M4-12 §3.1)', () => {
  it('names the whole scenes of one pass: one group, no AOI, no steps, no assets, the bands of the output', () => {
    expect(
      buildMosaicOrder({ datasetId: 'sentinel-2-c1-l2a', itemIds: ['B', 'A'], bands: ['visual_1', 'visual_2', 'visual_3'], dtype: 'uint8' }),
    ).toEqual({
      recipe_version: 2,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['A', 'B']] }],
      steps: [],
      output: { kind: 'raster', format: 'cog', dtype: 'uint8', bands: ['visual_1', 'visual_2', 'visual_3'] },
    });
  });

  it('carries no aoi member at all', () => {
    const order = buildMosaicOrder({ datasetId: 'd', itemIds: ['A'], bands: ['visual'], dtype: 'uint8' });
    expect('aoi' in order).toBe(false);
  });
});

const PLACE = {
  name: 'Somewhere',
  display_name: 'Somewhere',
  kind: 'city',
  bbox: [10, 50, 11, 51] as [number, number, number, number],
  outline: null,
  outline_simplified: false,
};

describe('buildExportOrder (M4-11 §3.1)', () => {
  const aoi = bboxToPolygon([10, 50, 11, 51]);

  it('is the crop as a job: the groups, assets and AOI of the request, no steps, factor 1', () => {
    expect(buildExportOrder({ datasetId: 'sentinel-2-c1-l2a', groups: [['B', 'A'], ['C']], assets: ['visual'], aoi })).toEqual({
      recipe_version: 2,
      inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['B', 'A'], ['C']], assets: ['visual'] }],
      aoi,
      steps: [],
      output: { kind: 'crop', format: 'cog', resolution_factor: 1, extent: 'bbox(aoi ∩ footprints)', mask: 'file' },
    });
  });

  it('sends only type and coordinates of a place-search AOI, never its properties', () => {
    const place = placeAoi(PLACE) as GeoJSON.Polygon;
    const order = buildExportOrder({ datasetId: 'd', groups: [['A']], assets: ['visual'], aoi: place });
    expect(order.aoi).toEqual({ type: 'Polygon', coordinates: aoi.coordinates });
  });
});

describe('aoiProvenanceFor (M4-30)', () => {
  const place = placeAoi(PLACE);
  const withArea = buildExportOrder({ datasetId: 'd', groups: [['A']], assets: ['visual'], aoi: bboxToPolygon([10, 50, 11, 51]) });
  const mosaic = buildMosaicOrder({ datasetId: 'd', itemIds: ['A', 'B'], bands: ['visual'], dtype: 'uint8' });

  it('is that of the AOI for an order that carries an area', () => {
    expect(aoiProvenanceFor(withArea, place)).toEqual(aoiProvenanceOf(place));
  });

  it('is nothing for an order without an area, however the AOI came about', () => {
    expect(aoiProvenanceFor(mosaic, place)).toBeUndefined();
  });

  it('is nothing for a drawn AOI or none', () => {
    expect(aoiProvenanceFor(withArea, bboxToPolygon([10, 50, 11, 51]))).toBeUndefined();
    expect(aoiProvenanceFor(withArea, null)).toBeUndefined();
  });
});

describe('aoiProvenanceOf (M4-11 F4)', () => {
  it('is the three fields of a place-search AOI as they are', () => {
    expect(aoiProvenanceOf(placeAoi(PLACE))).toEqual({
      source: 'OpenStreetMap / Nominatim',
      attribution: '© OpenStreetMap contributors',
      license: 'ODbL-1.0',
    });
  });

  it('is undefined for a drawn AOI, no AOI, or properties with nothing to send', () => {
    expect(aoiProvenanceOf(bboxToPolygon([10, 50, 11, 51]))).toBeUndefined();
    expect(aoiProvenanceOf(null)).toBeUndefined();
    const odd = { ...bboxToPolygon([10, 50, 11, 51]), properties: { source: 7, name: 'x' } } as GeoJSON.Geometry;
    expect(aoiProvenanceOf(odd)).toBeUndefined();
  });

  it('keeps the string fields and drops the rest', () => {
    const some = { ...bboxToPolygon([10, 50, 11, 51]), properties: { license: 'ODbL-1.0', source: null } } as GeoJSON.Geometry;
    expect(aoiProvenanceOf(some)).toEqual({ license: 'ODbL-1.0' });
  });
});

describe('small rules', () => {
  it('finds the step a refusal names', () => {
    expect(stepOfRefusal('the order is not valid: parameters of step 1 (reproject): crs')).toBe(1);
    expect(stepOfRefusal("step 0: 'band_math' cannot run here")).toBe(0);
    expect(stepOfRefusal('step 1: expression names unknown band(s): red; the input has: band_math')).toBe(1);
    expect(stepOfRefusal('invalid order: steps.2.params.expression: string_too_long')).toBe(2);
    expect(stepOfRefusal('the AOI does not touch any of the given items')).toBeNull();
    const bm = [{ op: 'reproject' }, { op: 'band_math' }];
    expect(stepOfRefusal('expression names unknown band(s): nir_2; the input has: red, nir', bm)).toBe(1);
    expect(stepOfRefusal('expression names unknown band(s): x', [...bm, { op: 'band_math' }])).toBeNull();
  });

  it('formats the estimate', () => {
    expect(formatBytes(4_200_000)).toBe('4.2 MB');
    expect(formatDuration('PT12.3S')).toBe('about 12 s');
    expect(formatDuration('PT0.4S')).toBe('under 1 s');
    expect(formatDuration('PT600.0S')).toBe('about 10 min');
    expect(formatDuration('P1D')).toBe('P1D');
  });

  it('says why Process cannot open; no AOI needed (M4-13c K1)', () => {
    const collection = (tier: string) => ({ id: 'x', 'earthx:license_flags': { tier } }) as unknown as Collection;
    expect(processBlockReason({ viewable: true, collection: collection('processing') }, 1)).toBeNull();
    expect(processBlockReason({ viewable: true, collection: collection('display') }, 1)).toMatch(/tier: display/);
    expect(processBlockReason({ viewable: true, collection: collection('processing') }, 0)).toMatch(/scene/);
    expect(processBlockReason(undefined, 1)).toMatch(/dataset/);
  });
});
