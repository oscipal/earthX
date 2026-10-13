// The other half of the order contract (M4-13b; plans/m4-13-processing-panel.md
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
import zarr from './fixtures/processes/sentinel-2-l2a-zarr3.json';
import { placeAoi } from './placeSearch';
import { estimateOrder, placeJob, type ProcessDescription } from './processing';
import { buildMosaicOrder, buildOrder, processInfo, type DraftStep } from './processingOrder';
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

const NDVI = { expression: '(nir - red) / (nir + red)' };
const REPROJECT = { crs: 'EPSG:3035', resolution: '30', resampling: 'bilinear' };

interface Case {
  name: string;
  // The scenes of the order; one by default.
  itemIds?: string[];
  datasetId: string;
  description: unknown;
  assets: string[];
  aoi: GeoJSON.Geometry;
  steps: DraftStep[];
  dtype: string;
}

const CASES: Case[] = [
  {
    name: 'ndvi-with-place-search-aoi',
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    assets: ['red', 'nir'],
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
    assets: ['data'],
    aoi: SQUARE,
    steps: [draft(cop, 'reproject', REPROJECT)],
    dtype: 'float32',
  },
  {
    name: 'band-math-then-reproject-with-multipolygon',
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    assets: ['red', 'nir'],
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
    datasetId: 'sentinel-2-l2a-zarr3',
    description: zarr,
    assets: ['SR_10m:b04', 'SR_10m:b08'],
    aoi: SQUARE,
    steps: [draft(zarr, 'band_math', { expression: '(b08 - b04) / (b08 + b04)' })],
    dtype: 'float32',
  },
  {
    // The scenes of one pass (M4-12b): one group, the AOI of the selection.
    name: 'ndvi-on-a-mosaic-of-three-scenes',
    itemIds: ['ITEM_C', 'ITEM_A', 'ITEM_B'],
    datasetId: 'sentinel-2-c1-l2a',
    description: s2,
    assets: ['red', 'nir'],
    aoi: SQUARE,
    steps: [draft(s2, 'band_math', NDVI)],
    dtype: 'float32',
  },
];

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
      aoi: c.aoi,
      steps: c.steps,
      assets: c.assets,
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

  it.each(CASES)('$name: the AOI is a bare 2D geometry', (c) => {
    const built = buildOrder({
      datasetId: c.datasetId,
      itemIds: c.itemIds ?? ['ITEM_A'],
      aoi: c.aoi,
      steps: c.steps,
      assets: c.assets,
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
      aoi,
      steps: CASES[0].steps,
      assets: CASES[0].assets,
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
      assets: ['visual'],
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
});

