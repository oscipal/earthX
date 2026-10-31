// The other half of the order contract (M4-13b; plans/m4/m4-13-processing-panel.md
// §12): what the panel really sends, written to `src/fixtures/orders/*.json`,
// and checked against the backend's own schema by
// `backend/tests/earthx/api/test_frontend_orders.py`.
//
// An order is built the way the panel builds it (`buildOrder` from a process
// description fixture and the draft's values) and sent through the real client
// with `fetch` replaced by a recorder. The recorded body is compared with the
// file: a change of what the panel sends fails here until the files are
// written anew (`npx vitest run -u src/processingContract.test.ts`), and the
// backend test then holds the new files against the schema. Neither half
// alone would have noticed an AOI that carries `properties`.

import { afterEach, describe, expect, it, vi } from 'vitest';

import cop from './fixtures/processes/cop-dem-glo-30.json';
import s2 from './fixtures/processes/sentinel-2-c1-l2a.json';
import zarr from './fixtures/processes/synthetic-zarr.json';
import { placeAoi } from './placeSearch';
import { estimateOrder, placeJob, type ProcessDescription } from './processing';
import { buildMosaicOrder, buildOrder, processInfo, type Area, type DraftStep } from './processingOrder';
import { initialValues, type FieldValue } from './schemaForm';


const SQUARE: GeoJSON.Polygon = {
  type: 'Polygon',
  coordinates: [[[9.0, 47.0], [9.05, 47.0], [9.05, 47.05], [9.0, 47.05], [9.0, 47.0]]],
};

function draft(description: unknown, op: string, values: Record<string, FieldValue>): DraftStep {
  const info = processInfo(description as ProcessDescription);
  const operator = info.operators.find((o) => o.op === op)!;
  if (!operator.form.supported) throw new Error(operator.form.reason);
  return { key: 1, op, opVersion: operator.opVersion, values: { ...initialValues(operator.form.fields), ...values } };
}

// `band_math` adds the band `name`; the output names it (adr/0020 §5).
const NDVI = { expression: '(nir - red) / (nir + red)', name: 'NDVI' };
// The bands of the data the panel offers, as the item names them: a result may not take one of these names.
const S2_DATA = ['blue', 'green', 'red', 'rededge1', 'rededge2', 'rededge3', 'nir', 'nir08', 'nir09', 'swir16', 'swir22', 'scl'];
const DEM_DATA = ['data'];
const ZARR_DATA = ['b04', 'b08'];
const REPROJECT = { crs: 'EPSG:3035', resolution: '30', resampling: 'bilinear' };

interface Case {
  name: string;
  // The scenes of the order; one by default.
  itemIds?: string[];
  datasetId: string;
  description: unknown;
  // The bands of the output in the order of the file, and every band of the data.
  bands: string[];
  data: string[];
  // `null`: "Whole scene" (M4-13c §3.2), the order names no AOI.
  aoi: GeoJSON.Geometry | null;
  steps: DraftStep[];
  dtype: string;
}

const CASES: Case[] = [
  {
    name: 'ndvi-with-place-search-aoi',
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    bands: ['NDVI'],
    data: S2_DATA,
    // The outline a place search hands out, with its provenance in `properties`.
    aoi: placeAoi({
      name: 'x',
      display_name: 'x',
      kind: 'x',
      bbox: [9.0, 47.0, 9.05, 47.05],
      outline: SQUARE,
      outline_simplified: false,
    }),
    steps: [draft(s2, 'band_math', NDVI)],
    dtype: 'float32',
  },
  {
    name: 'reproject-dem-with-drawn-aoi',
    datasetId: 'cop-dem-glo-30',
    description: cop,
    bands: ['data'],
    data: DEM_DATA,
    aoi: SQUARE,
    steps: [draft(cop, 'reproject', REPROJECT)],
    dtype: 'float32',
  },
  {
    name: 'band-math-then-reproject-with-multipolygon',
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    bands: ['NDVI'],
    data: S2_DATA,
    // Altitudes in the positions and a `bbox` member, as an uploaded file can have them.
    aoi: {
      type: 'MultiPolygon',
      bbox: [9.0, 47.0, 9.2, 47.05],
      coordinates: [
        [[[9.0, 47.0, 100], [9.05, 47.0, 100], [9.05, 47.05, 100], [9.0, 47.05, 100], [9.0, 47.0, 100]]],
        [[[9.15, 47.0, 100], [9.2, 47.0, 100], [9.2, 47.05, 100], [9.15, 47.05, 100], [9.15, 47.0, 100]]],
      ],
    } as GeoJSON.MultiPolygon,
    steps: [draft(s2, 'band_math', NDVI), { ...draft(s2, 'reproject', { ...REPROJECT, align: true }), key: 2 }],
    dtype: 'float32',
  },
  {
    name: 'band-math-on-zarr-variables',
    datasetId: 'synthetic-zarr',
    description: zarr,
    bands: ['NDVI'],
    data: ZARR_DATA,
    aoi: SQUARE,
    steps: [draft(zarr, 'band_math', { expression: '(b08 - b04) / (b08 + b04)', name: 'NDVI' })],
    dtype: 'float32',
  },
  {
    // A mask in front of the index: the layer the mask reads stays in the stock but not in the output (M4-18c, adr/0020 §4).
    name: 'masked-ndvi-with-drawn-aoi',
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    bands: ['NDVI'],
    data: S2_DATA,
    aoi: SQUARE,
    steps: [draft(s2, 'mask', { source: 'scl', classes: '3, 8, 9, 10' }), { ...draft(s2, 'band_math', NDVI), key: 2 }],
    dtype: 'float32',
  },
  {
    // A mask by value on the result of an earlier step; the band that decides is in the output too (DS-06b).
    name: 'mask-ndvi-below-a-value-with-drawn-aoi',
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    bands: ['NDVI', 'red'],
    data: S2_DATA,
    aoi: SQUARE,
    steps: [
      draft(s2, 'band_math', NDVI),
      { ...draft(s2, 'mask_values', { band: 'NDVI', condition: 'between', values: '0.2; 0.8' }), key: 2 },
    ],
    dtype: 'float32',
  },
  {
    // The DEM has no classification layer; the mask by value works on its one band (DS-06b).
    name: 'mask-dem-equal-to-values-with-drawn-aoi',
    datasetId: 'cop-dem-glo-30',
    description: cop,
    bands: ['data'],
    data: DEM_DATA,
    aoi: SQUARE,
    steps: [draft(cop, 'mask_values', { band: 'data', condition: 'eq', values: '0, 2000, 1000' })],
    dtype: 'float32',
  },
  {
    // A DEM with a step that keeps the grid, so that the area can be measured (no `reproject`).
    name: 'normalize-dem-with-drawn-aoi',
    datasetId: 'cop-dem-glo-30',
    description: cop,
    bands: ['data'],
    data: DEM_DATA,
    aoi: SQUARE,
    steps: [draft(cop, 'normalize', { bands: 'data', in_min: '0', in_max: '3000', out_min: '0', out_max: '1', clip: true })],
    dtype: 'float32',
  },
  {
    // The scenes of one pass (M4-12b): one group, the AOI of the selection.
    name: 'ndvi-on-a-mosaic-of-three-scenes',
    itemIds: ['ITEM_C', 'ITEM_A', 'ITEM_B'],
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    // A band of the data next to the result: the results come first, then the bands of the data.
    bands: ['NDVI', 'red'],
    data: S2_DATA,
    aoi: SQUARE,
    steps: [draft(s2, 'band_math', NDVI)],
    dtype: 'float32',
  },
  {
    // "Whole scene" with steps (M4-13c §3.2): the scenes of a pass, no AOI.
    name: 'ndvi-on-whole-scenes-without-aoi',
    itemIds: ['ITEM_B', 'ITEM_A'],
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    bands: ['NDVI'],
    data: S2_DATA,
    aoi: null,
    steps: [draft(s2, 'band_math', NDVI)],
    dtype: 'float32',
  },
  {
    // One job of a batch "per scene" (M4-13c-4): the steps of the draft on one
    // scene of the selection, no AOI.
    name: 'ndvi-on-one-scene-of-a-batch',
    itemIds: ['ITEM_B'],
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    bands: ['NDVI'],
    data: S2_DATA,
    aoi: null,
    steps: [draft(s2, 'band_math', NDVI)],
    dtype: 'float32',
  },
];

const area = (c: Case): Area => (c.aoi ? 'aoi' : 'scene');

afterEach(() => {
  vi.unstubAllGlobals();
});

function recorder() {
  const bodies: { url: string; body: unknown }[] = [];
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      bodies.push({ url, body: JSON.parse(init?.body as string) });
      return new Response('{}', { status: 500 }); // the answer is not the point here
    }),
  );
  return bodies;
}

// The order of the download dialog's mosaic job: whole scenes, no AOI, no steps.
const MOSAIC_FILE = 'whole-scenes-of-a-pass-without-aoi';

describe('the order the panel sends', () => {
  it.each(CASES)('$name: the same body to the estimate and to the execution, as in the file', async (c) => {
    const built = buildOrder({
      datasetId: c.datasetId,
      itemIds: c.itemIds ?? ['ITEM_A'],
      area: area(c),
      aoi: c.aoi,
      steps: c.steps,
      bands: c.bands,
      data: c.data,
      dtype: c.dtype,
      info: processInfo(c.description as ProcessDescription),
    });
    expect(built.problems).toEqual([]);
    expect(built.order).not.toBeNull();
    const bodies = recorder();
    await estimateOrder(built.order!).catch(() => undefined);
    await placeJob(built.order!).catch(() => undefined);
    expect(bodies.map((b) => b.url)).toEqual([
      '/processing/processes/recipe/estimate',
      '/processing/processes/recipe/execution',
    ]);
    expect(bodies[1].body).toEqual(bodies[0].body);
    await expect(`${JSON.stringify(bodies[0].body, null, 2)}\n`).toMatchFileSnapshot(`./fixtures/orders/${c.name}.json`);
  });

  it.each(CASES)('$name: is version 2, names no assets and holds the bands of the output', (c) => {
    const built = buildOrder({
      datasetId: c.datasetId,
      itemIds: c.itemIds ?? ['ITEM_A'],
      area: area(c),
      aoi: c.aoi,
      steps: c.steps,
      bands: c.bands,
      data: c.data,
      dtype: c.dtype,
      info: processInfo(c.description as ProcessDescription),
    });
    const order = built.order!;
    expect(order.recipe_version).toBe(2);
    expect(order.inputs.every((input) => !('assets' in input))).toBe(true);
    expect(order.output).toEqual({ kind: 'raster', format: 'cog', dtype: c.dtype, bands: c.bands });
  });

  it.each(CASES.filter((c) => c.aoi))('$name: the AOI is a bare 2D geometry', (c) => {
    const built = buildOrder({
      datasetId: c.datasetId,
      itemIds: c.itemIds ?? ['ITEM_A'],
      area: area(c),
      aoi: c.aoi,
      steps: c.steps,
      bands: c.bands,
      data: c.data,
      dtype: c.dtype,
      info: processInfo(c.description as ProcessDescription),
    });
    const aoi = built.order!.aoi!;
    expect(Object.keys(aoi).sort()).toEqual(['coordinates', 'type']);
    const positions = JSON.stringify(aoi.coordinates).match(/\[[^[\]]*\]/g)!;
    expect(positions.every((p) => p.split(',').length === 2)).toBe(true);
  });

  it('leaves the AOI of the store as it was: the download still needs the provenance', () => {
    const aoi = CASES[0].aoi as GeoJSON.Polygon & { properties?: unknown };
    const before = JSON.stringify(aoi);
    buildOrder({
      datasetId: CASES[0].datasetId,
      itemIds: ['ITEM_A'],
      area: 'aoi',
      aoi,
      steps: CASES[0].steps,
      bands: CASES[0].bands,
      data: CASES[0].data,
      dtype: 'float32',
      info: processInfo(s2 as unknown as ProcessDescription),
    });
    expect(JSON.stringify(aoi)).toBe(before);
    expect(aoi.properties).toBeDefined();
  });
});

describe('the order the download dialog sends for the whole scenes of a pass', () => {
  const order = () =>
    buildMosaicOrder({
      datasetId: 'sentinel-2-c1-l2a',
      itemIds: ['ITEM_B', 'ITEM_A'],
      // The three bands of the asset `visual`, as the dialog names them (`bandNamesOf`).
      bands: ['visual_1', 'visual_2', 'visual_3'],
      dtype: 'uint8',
    });

  it('goes as the same body to the execution, as in the file', async () => {
    const bodies = recorder();
    await placeJob(order()).catch(() => undefined);
    expect(bodies.map((b) => b.url)).toEqual(['/processing/processes/recipe/execution']);
    await expect(`${JSON.stringify(bodies[0].body, null, 2)}\n`).toMatchFileSnapshot(`./fixtures/orders/${MOSAIC_FILE}.json`);
  });

  it('has no aoi member and no steps', () => {
    expect(Object.keys(order()).sort()).toEqual(['inputs', 'output', 'recipe_version', 'steps']);
    expect(order().steps).toEqual([]);
  });

  it('is version 2: no assets in the input, the bands in the output', () => {
    expect(order().recipe_version).toBe(2);
    expect('assets' in order().inputs[0]).toBe(false);
    expect(order().output).toEqual({ kind: 'raster', format: 'cog', dtype: 'uint8', bands: ['visual_1', 'visual_2', 'visual_3'] });
  });
});

