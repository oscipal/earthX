import { describe, expect, it } from 'vitest';

import { buildMosaicOperatorTileTemplate, buildMosaicTileTemplate } from './api';
import {
  isMosaicPass,
  MAX_MOSAIC_REQUEST_BYTES,
  MAX_MOSAIC_SCENES,
  mosaicRequestBytes,
  mosaicsOfView,
  mosaicTemplateOf,
  oversizeNote,
  passesOf,
  sameMosaics,
  viewOfPass,
} from './mosaic';
import type { MosaicInfo, Mosaics, SceneEntry } from './mosaic';
import type { DownloadedInfo, StacItem, TimeStepGroup } from './types';

const DATASET = 'sentinel-2-c1-l2a';

function entry(id: string, overrides: Partial<DownloadedInfo> = {}): SceneEntry {
  return [
    id,
    {
      tileUrl: `/collections/${DATASET}/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
      bounds: [10, 47, 11, 48],
      asset: 'visual',
      minZoom: 0,
      maxZoom: 19,
      ...overrides,
    },
  ];
}

const pass = (...ids: string[]) => ids.map((id) => entry(id));
const stac = (id: string): StacItem => ({ id, properties: {}, assets: {} });
const group = (...ids: string[]): TimeStepGroup => ({ key: [ids[0]], label: ids[0], items: ids.map(stac) });

function mosaicOf(entries: SceneEntry[], overrides: Partial<MosaicInfo> = {}): Mosaics {
  const tileUrl = mosaicTemplateOf(DATASET, entries) as string;
  return {
    [tileUrl]: { tileUrl, bounds: [9, 46, 12, 49], minZoom: 8, maxZoom: 19, order: entries.map(([id]) => id), ...overrides },
  };
}

describe('passesOf', () => {
  it('splits the scenes by the time step each belongs to, in the order they came', () => {
    const entries = pass('A1', 'B1', 'A2');
    const passes = passesOf(entries, [group('A1', 'A2'), group('B1')]);
    expect(passes.map((p) => p.map(([id]) => id))).toEqual([['A1', 'A2'], ['B1']]);
  });

  it('leaves a scene that no group holds on its own, because its time step is not known', () => {
    const passes = passesOf(pass('X1', 'X2'), [group('A1')]);
    expect(passes.map((p) => p.length)).toEqual([1, 1]);
  });

  it('copes with no groups at all', () => {
    expect(passesOf(pass('A1', 'A2'), undefined)).toHaveLength(2);
    expect(passesOf([], [])).toEqual([]);
  });
});

describe('what is a mosaic', () => {
  it('needs two to 64 scenes', () => {
    expect(isMosaicPass(pass('A'))).toBe(false);
    expect(isMosaicPass(pass('A', 'B'))).toBe(true);
    const ids = Array.from({ length: MAX_MOSAIC_SCENES }, (_, i) => `S${i}`);
    expect(isMosaicPass(pass(...ids))).toBe(true);
    expect(isMosaicPass(pass(...ids, 'one more'))).toBe(false);
    expect(isMosaicPass([])).toBe(false);
  });

  it('needs scenes of one asset', () => {
    expect(isMosaicPass([entry('A'), entry('B', { asset: 'thumbnail' })])).toBe(false);
  });

  it('needs a dataset that is released from z8 on somewhere (the tiler answers 400 below)', () => {
    expect(isMosaicPass([entry('A', { maxZoom: 7 }), entry('B', { maxZoom: 7 })])).toBe(false);
    expect(isMosaicPass([entry('A', { minZoom: 8, maxZoom: 14 }), entry('B', { minZoom: 8, maxZoom: 14 })])).toBe(true);
  });

  it('is named by the sorted scenes and the asset, so one selection is one URL', () => {
    const forward = mosaicTemplateOf(DATASET, pass('B', 'A', 'C'));
    expect(forward).toBe(mosaicTemplateOf(DATASET, pass('C', 'B', 'A')));
    expect(forward).toBe(buildMosaicTileTemplate(DATASET, ['A', 'B', 'C'], 'visual'));
    expect(mosaicTemplateOf(DATASET, pass('A'))).toBeNull();
  });
});

describe('viewOfPass', () => {
  const entries = pass('B', 'A', 'C');

  it('draws scene by scene without mosaics, without a dataset and for a single scene', () => {
    expect(viewOfPass(DATASET, entries, undefined)).toEqual({ kind: 'scenes' });
    expect(viewOfPass(null, entries, {})).toEqual({ kind: 'scenes' });
    expect(viewOfPass(DATASET, pass('A'), {})).toEqual({ kind: 'scenes' });
  });

  it('waits for a mosaic that has not answered yet, drawing nothing', () => {
    expect(viewOfPass(DATASET, entries, {})).toEqual({ kind: 'pending' });
  });

  it('draws scene by scene once the tiler has refused the mosaic', () => {
    const refused = { [mosaicTemplateOf(DATASET, entries) as string]: null };
    expect(viewOfPass(DATASET, entries, refused)).toEqual({ kind: 'scenes' });
  });

  it('puts the mosaic on top and, below its first level, the scenes in the order it reads them', () => {
    const view = viewOfPass(DATASET, entries, mosaicOf(entries, { order: ['C', 'A', 'B'] }));
    if (view.kind !== 'mosaic') throw new Error('expected a mosaic');
    const [c, a, b] = view.rasters.slice(0, 3).reverse(); // top to bottom
    expect([c, a, b].map((r) => r.tileUrl.split('/items/')[1].split('/')[0])).toEqual(['C', 'A', 'B']);
    const mosaic = view.rasters[view.rasters.length - 1];
    expect(mosaic.tileUrl).toBe(mosaicTemplateOf(DATASET, entries));
    expect(mosaic.bounds).toEqual([9, 46, 12, 49]);
    expect([mosaic.minZoom, mosaic.maxZoom, mosaic.hideFrom]).toEqual([8, 19, undefined]);
  });

  it('steps each scene aside where the mosaic is first asked for, so a source is not overzoomed above z7', () => {
    const view = viewOfPass(DATASET, entries, mosaicOf(entries));
    if (view.kind !== 'mosaic') throw new Error('expected a mosaic');
    for (const scene of view.rasters.slice(0, -1)) {
      expect([scene.minZoom, scene.maxZoom, scene.hideFrom]).toEqual([0, 7, 6.5]);
    }
  });

  it('draws no single scene for a dataset that is released from the mosaic level on', () => {
    const zarr = [entry('A', { minZoom: 8, maxZoom: 14 }), entry('B', { minZoom: 8, maxZoom: 14 })];
    const view = viewOfPass(DATASET, zarr, mosaicOf(zarr, { maxZoom: 14 }));
    if (view.kind !== 'mosaic') throw new Error('expected a mosaic');
    expect(view.rasters).toHaveLength(1);
  });

  it('puts a scene the tiler left out of its order below the others', () => {
    const view = viewOfPass(DATASET, entries, mosaicOf(entries, { order: ['A'] }));
    if (view.kind !== 'mosaic') throw new Error('expected a mosaic');
    expect(view.rasters[2].tileUrl).toContain('/items/A/'); // topmost of the scenes
  });
});

describe('oversizeNote', () => {
  const ids = (n: number) => Array.from({ length: n }, (_, i) => `S${i}`);

  it('says nothing while every pass fits one mosaic', () => {
    expect(oversizeNote([pass(...ids(64)), pass('X')], 0)).toBeNull();
    expect(oversizeNote([], 0)).toBeNull();
  });

  it('says how big the time step is and how many scenes are not drawn', () => {
    expect(oversizeNote([pass(...ids(70))], 30)).toBe(
      'A time step of 70 scenes is more than one mosaic takes (64); its scenes are drawn one by one, 30 of them not at all.',
    );
    expect(oversizeNote([pass(...ids(65))], 0)).not.toContain('not at all');
  });
});

describe('the mosaics a view asks for', () => {
  const view = pass('A', 'B');
  const other = pass('C', 'D');
  const known = { ...mosaicOf(view), ...mosaicOf(other) };

  it('are those of its own time steps, not those of another view', () => {
    const picked = mosaicsOfView(known, DATASET, view, [group('A', 'B')]);
    expect(Object.keys(picked)).toEqual([mosaicTemplateOf(DATASET, view)]);
  });

  it('leaves out one that has not answered, and picks nothing without a dataset', () => {
    expect(mosaicsOfView({}, DATASET, view, [group('A', 'B')])).toEqual({});
    expect(mosaicsOfView(known, null, view, [group('A', 'B')])).toEqual({});
  });

  it('are the same while only another view\'s answer is new', () => {
    const alone = mosaicOf(view);
    const before = mosaicsOfView(alone, DATASET, view, [group('A', 'B')]);
    const after = mosaicsOfView({ ...alone, ...mosaicOf(other) }, DATASET, view, [group('A', 'B')]);
    expect(sameMosaics(before, after)).toBe(true);
    expect(sameMosaics(before, {})).toBe(false);
    expect(sameMosaics(before, mosaicOf(view, { order: ['B', 'A'] }))).toBe(false); // another answer for it
  });
});

describe('the length of a mosaic request (NM4-04b)', () => {
  const step = { op: 'band_math', opVersion: 1, paramsJson: '{"expression":"red"}' };

  it('counts path and query as the tiler does: the largest tile of the level in the grid, no address of the API', () => {
    const template = buildMosaicOperatorTileTemplate(DATASET, ['B', 'A'], ['red', 'nir'], [step]);
    const request = template.slice(template.indexOf('/collections/'));
    expect(mosaicRequestBytes(`https://api.example.org${template}`, 10)).toBe(
      request.replace('{z}', '10').replace('{x}', '1023').replace('{y}', '1023').length,
    );
    expect(mosaicRequestBytes(template, 10)).toBe(mosaicRequestBytes(`https://api.example.org/v1${template}`, 10));
  });

  it('grows with the level, and with every scene', () => {
    const one = buildMosaicOperatorTileTemplate(DATASET, ['A'], ['red'], [step]);
    const two = buildMosaicOperatorTileTemplate(DATASET, ['A', 'B'], ['red'], [step]);
    expect(mosaicRequestBytes(one, 14)).toBeGreaterThan(mosaicRequestBytes(one, 8));
    expect(mosaicRequestBytes(two, 8)).toBeGreaterThan(mosaicRequestBytes(one, 8));
  });

  it('is under the limit of the tiler for a pass of 64 scenes of 60 characters and the usual chain', () => {
    const ids = Array.from({ length: MAX_MOSAIC_SCENES }, (_, i) => `${'S'.repeat(57)}${String(i).padStart(3, '0')}`);
    const template = buildMosaicOperatorTileTemplate(DATASET, ids, ['red', 'nir', 'scl'], [step, step]);
    expect(mosaicRequestBytes(template, 14)).toBeLessThan(MAX_MOSAIC_REQUEST_BYTES);
  });
});
