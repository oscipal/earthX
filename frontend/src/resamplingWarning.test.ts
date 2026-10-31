// NM4-65 part 7: the facts of the estimate, and the text the warning makes of them.

import { describe, expect, it } from 'vitest';

import { parseEstimate, parseResampling, type EstimateDocument, type Resampling } from './processing';
import { describeResampling, metres, resamplingParts } from './resamplingWarning';

const FACTS: Resampling = {
  grid: { resolution: 10, crs: 'EPSG:32632' },
  method: 'nearest',
  bands: [{ band: 'rededge1', resolution: 20, crs: 'EPSG:32632' }, { band: 'swir', resolution: 60, crs: 'EPSG:32633' }],
  scenes: { count: 1, of: 3, crs: 'EPSG:32632' },
};
const ESTIMATE = { size: 1, duration: 'PT1.0S', outputPixels: 1, inputPixels: 1, inputBytes: 1, assets: 1, units: 1 };
const doc = (resampling?: unknown) => parseEstimate({ estimate: ESTIMATE, skippedItems: [], ...(resampling === undefined ? {} : { resampling }) })!;

describe('the facts of the estimate', () => {
  it('are read as the server writes them', () => {
    expect(doc(FACTS).resampling).toEqual(FACTS);
  });

  it('are none where the server says none, and for an older server that does not say', () => {
    expect(doc(null).resampling).toBeNull();
    expect(doc().resampling).toBeNull();
  });

  it('are none where they do not read whole: no grid, no method, a grid of no size, text that is none, nothing to say', () => {
    for (const bad of [
      'resampled',
      42,
      {},
      { ...FACTS, grid: null },
      { ...FACTS, grid: { resolution: 0, crs: 'EPSG:32632' } },
      { ...FACTS, grid: { resolution: 'ten', crs: 'EPSG:32632' } },
      { ...FACTS, method: '' },
      { ...FACTS, method: 7 },
      { ...FACTS, bands: [], scenes: null },
      { ...FACTS, bands: [{ band: '', resolution: 20 }], scenes: null },
      { ...FACTS, bands: 'rededge', scenes: { count: 0, of: 3 } },
    ]) {
      expect(parseResampling(bad), JSON.stringify(bad)).toBeNull();
    }
  });

  it('keep what reads and leave out the rest of a band or a scene entry, a CRS that is missing as none', () => {
    const read = parseResampling({ ...FACTS, bands: [{ band: 'a', resolution: 20 }, { band: 5, resolution: 20 }, null, { band: 'c', resolution: -1 }], scenes: { count: 1.5, of: 3 } });
    expect(read).toEqual({ grid: FACTS.grid, method: 'nearest', bands: [{ band: 'a', resolution: 20, crs: null }], scenes: null });
    expect(parseResampling({ ...FACTS, grid: { resolution: 10 }, bands: [{ band: 'a', resolution: 20 }], scenes: null })?.grid.crs).toBeNull();
  });

  it('never carry text of more than a line (an address, a long text) into the warning', () => {
    expect(parseResampling({ ...FACTS, method: 'x'.repeat(100) })).toBeNull();
    expect(parseResampling({ ...FACTS, bands: [{ band: 'y'.repeat(100), resolution: 20 }], scenes: null })).toBeNull();
  });
});

describe('resamplingParts', () => {
  const withFacts = doc(FACTS);
  const without = doc(null);
  it('is the facts of a lone job, or nothing', () => {
    expect(resamplingParts(withFacts, null)).toEqual([{ label: null, resampling: FACTS }]);
    expect(resamplingParts(without, null)).toEqual([]);
    expect(resamplingParts(null, null)).toEqual([]);
  });

  it('is the facts of every part of a batch that has some, each with its label; a part the server refused has none', () => {
    const batch = [
      { unit: { label: '2026-07-01' }, doc: withFacts },
      { unit: { label: '2026-07-06' }, doc: without },
      { unit: { label: '2026-07-11' }, doc: null as EstimateDocument | null },
    ];
    expect(resamplingParts(null, batch)).toEqual([{ label: '2026-07-01', resampling: FACTS }]);
  });
});

describe('describeResampling', () => {
  it('says which grid, by which method, which bands and which scenes, and what it means', () => {
    const text = describeResampling({ label: null, resampling: FACTS });
    expect(text.grid).toBe('The values are brought to one grid of 10 m in EPSG:32632, by nearest neighbour.');
    // A band in the zone of the grid names no CRS; one in another does.
    expect(text.bands).toBe('Resampled: rededge1 (20 m), swir (60 m, EPSG:32633).');
    expect(text.scenes).toBe('1 of 3 scenes lie in another UTM zone and are warped to EPSG:32632.');
    expect(text.meaning).toContain('no new values appear');
    expect(text.meaning).toContain('at the pixel edges the values change');
  });

  it('leaves out what is not there, and says what another method does', () => {
    const only = describeResampling({ label: 'pass', resampling: { grid: { resolution: 0.5, crs: null }, method: 'bilinear', bands: [{ band: 'a', resolution: 1, crs: null }], scenes: null } });
    expect(only.label).toBe('pass');
    expect(only.grid).toBe('The values are brought to one grid of 0.5 m, by bilinear interpolation.');
    expect(only.scenes).toBeNull();
    expect(only.meaning).toContain('new and smoothed');
    const scenes = describeResampling({ label: null, resampling: { ...FACTS, bands: [], scenes: { count: 2, of: 5, crs: null } } });
    expect(scenes.bands).toBeNull();
    expect(scenes.scenes).toBe('2 of 5 scenes lie in another UTM zone and are warped to the zone of most scenes.');
  });

  it('names a method it does not know as the server does, with a meaning that holds for every method', () => {
    const odd = describeResampling({ label: null, resampling: { ...FACTS, method: 'cubic' } });
    expect(odd.grid).toContain('by cubic.');
    expect(odd.meaning).toBe('The values at the pixel edges change, and the pixel counts differ from the source.');
  });

  it('writes a pixel size without the noise of a float', () => {
    expect(metres(10)).toBe('10 m');
    expect(metres(0.30000000000000004)).toBe('0.3 m');
    expect(metres(20.5)).toBe('20.5 m');
  });
});
