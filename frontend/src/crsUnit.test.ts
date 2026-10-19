import { describe, expect, it } from 'vitest';

import { CRS_PATTERN, cellSizeText, crsBlockReason, metresPerDegree, midLatitude, type CrsEntry } from './crsUnit';
import type { CrsInfo } from './processing';

const metre: CrsInfo = {
  code: 'EPSG:3035',
  name: 'ETRS89-extended / LAEA Europe',
  kind: 'projected',
  unit: { name: 'metre', kind: 'linear', toBase: 1 },
};
const foot: CrsInfo = {
  code: 'EPSG:2227',
  name: 'NAD83 / California zone 3 (ftUS)',
  kind: 'projected',
  unit: { name: 'US survey foot', kind: 'linear', toBase: 1200 / 3937 },
};
const degree: CrsInfo = {
  code: 'EPSG:4326',
  name: 'WGS 84',
  kind: 'geographic',
  unit: { name: 'degree', kind: 'angular', toBase: 1 },
};

describe('the pattern of a target CRS', () => {
  it.each(['EPSG:3035', 'EPSG:4326', 'EPSG:2056', 'EPSG:102100'])('takes %s', (code) => {
    expect(CRS_PATTERN.test(code)).toBe(true);
  });

  it.each(['epsg:3035', 'EPSG:303', 'EPSG:3035000', 'EPSG:3035\n', ' EPSG:3035', 'EPSG:30 35', '3035', 'EPSG:', 'EPSG:３０３５'])(
    'turns away %j',
    (code) => {
      expect(CRS_PATTERN.test(code)).toBe(false);
    },
  );
});

describe('metres per degree (WGS84 series)', () => {
  it('at the equator a degree of latitude is 110574 m and of longitude 111319 m', () => {
    const { northSouth, eastWest } = metresPerDegree(0);
    expect(northSouth).toBeCloseTo(110574.3, 1);
    expect(eastWest).toBeCloseTo(111319.5, 1);
  });

  it('at 47.3° N a degree of longitude is 75629 m', () => {
    const { northSouth, eastWest } = metresPerDegree(47.3);
    expect(northSouth).toBeCloseTo(111176.7, 1);
    expect(eastWest).toBeCloseTo(75629.2, 1);
  });

  it('is symmetric about the equator', () => {
    expect(metresPerDegree(-47.3)).toEqual(metresPerDegree(47.3));
  });

  it('at the pole a degree of latitude is 111694 m and of longitude (almost) nothing', () => {
    const { northSouth, eastWest } = metresPerDegree(90);
    expect(northSouth).toBeCloseTo(111694, 0);
    expect(Math.abs(eastWest)).toBeLessThan(1e-6);
  });
});

describe('the middle latitude of an area', () => {
  it('is halfway between the southern and the northern edge of all boxes', () => {
    expect(midLatitude([[10, 46, 11, 47]])).toBe(46.5);
    expect(midLatitude([[10, 46, 11, 47], [5, 50, 6, 52]])).toBe(49);
  });

  it('is signed in the south', () => {
    expect(midLatitude([[10, -40, 11, -30]])).toBe(-35);
  });

  it('is none without a box', () => {
    expect(midLatitude([])).toBeNull();
  });
});

describe('the cell size in words', () => {
  it('metres: the size twice', () => {
    expect(cellSizeText(metre, 10, 47.3)).toBe('Cell size: 10 m × 10 m');
    expect(cellSizeText(metre, 0.5, null)).toBe('Cell size: 0.5 m × 0.5 m');
  });

  it('another linear unit: its name and the metres it comes to', () => {
    expect(cellSizeText(foot, 10, null)).toBe('Cell size: 10 US survey foot × 10 US survey foot (≈ 3.05 m)');
    expect(cellSizeText(foot, 1000, null)).toBe('Cell size: 1000 US survey foot × 1000 US survey foot (≈ 305 m)');
  });

  it('degrees: the size on the ground at the latitude, north–south and east–west', () => {
    expect(cellSizeText(degree, 0.0003, 47.3)).toBe(
      'Cell size: 0.0003° × 0.0003° ≈ 33 m (N–S) × 23 m (E–W) at 47.3° N',
    );
  });

  it('degrees on the equator are as wide as they are high', () => {
    expect(cellSizeText(degree, 0.0003, 0)).toBe('Cell size: 0.0003° × 0.0003° ≈ 33 m (N–S) × 33 m (E–W) at 0.0° N');
  });

  it('degrees in the south say S', () => {
    expect(cellSizeText(degree, 0.0003, -33.9)).toBe(
      'Cell size: 0.0003° × 0.0003° ≈ 33 m (N–S) × 28 m (E–W) at 33.9° S',
    );
  });

  it('coarse degrees are given in whole metres, fine ones to the centimetre', () => {
    expect(cellSizeText(degree, 0.1, 47.3)).toContain('≈ 11118 m (N–S) × 7563 m (E–W)');
    expect(cellSizeText(degree, 0.0003, 89)).toContain('× 0.58 m (E–W)');
  });

  it('degrees without a latitude stay degrees', () => {
    expect(cellSizeText(degree, 0.0003, null)).toBe('Cell size: 0.0003° × 0.0003°');
    expect(cellSizeText(degree, 0.0003, Number.NaN)).toBe('Cell size: 0.0003° × 0.0003°');
    expect(cellSizeText(degree, 0.0003, 91)).toBe('Cell size: 0.0003° × 0.0003°');
  });

  it('an angle in another unit is turned into degrees for the ground', () => {
    const grad: CrsInfo = { ...degree, unit: { name: 'grad', kind: 'angular', toBase: 0.9 } };
    expect(cellSizeText(grad, 0.001, 0)).toBe('Cell size: 0.001 grad × 0.001 grad ≈ 100 m (N–S) × 100 m (E–W) at 0.0° N');
  });

  it('a unit the answer gives no usable factor for is named, nothing more', () => {
    const odd: CrsInfo = { ...metre, unit: { name: 'furlong', kind: 'linear', toBase: 0 } };
    expect(cellSizeText(odd, 10, 47)).toBe('Cell size: 10 furlong × 10 furlong');
    expect(cellSizeText({ ...odd, unit: { ...odd.unit, toBase: Number.NaN } }, 10, 47)).toBe(
      'Cell size: 10 furlong × 10 furlong',
    );
  });

  it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY])('says nothing for the resolution %s', (resolution) => {
    expect(cellSizeText(metre, resolution, 47)).toBeNull();
  });

  it('writes a very small cell without an exponent', () => {
    expect(cellSizeText(degree, 0.0000001, null)).toBe('Cell size: 0.0000001° × 0.0000001°');
  });
});

describe('what holds the review back', () => {
  const refused: CrsEntry = { state: 'refused', message: 'EPSG:99999 is not a CRS this platform knows' };
  const ready: CrsEntry = { state: 'ready', info: metre };
  const step = (op: string, crs: unknown) => ({ op, values: { crs } });

  it('is the reason of a refused target CRS of a reproject step', () => {
    expect(crsBlockReason([step('reproject', 'EPSG:99999')], { 'EPSG:99999': refused })).toBe(refused.message);
  });

  it('is nothing for a known CRS, one not asked for yet, or one that could not be looked up', () => {
    expect(crsBlockReason([step('reproject', 'EPSG:3035')], { 'EPSG:3035': ready })).toBeNull();
    expect(crsBlockReason([step('reproject', 'EPSG:3035')], {})).toBeNull();
    expect(
      crsBlockReason([step('reproject', 'EPSG:3035')], { 'EPSG:3035': { state: 'error', message: 'no answer' } }),
    ).toBeNull();
  });

  it('looks at reproject steps only, and at the code as it stands in the step', () => {
    expect(crsBlockReason([step('band_math', 'EPSG:99999')], { 'EPSG:99999': refused })).toBeNull();
    expect(crsBlockReason([step('reproject', 'EPSG:3035')], { 'EPSG:99999': refused })).toBeNull();
    expect(crsBlockReason([step('reproject', undefined)], { 'EPSG:99999': refused })).toBeNull();
  });

  it('is the reason of the first refused step, whatever comes after', () => {
    const second: CrsEntry = { state: 'refused', message: 'second' };
    const codes = { 'EPSG:3035': ready, 'EPSG:12345': second, 'EPSG:99999': refused };
    expect(crsBlockReason([step('reproject', 'EPSG:3035'), step('reproject', 'EPSG:12345')], codes)).toBe('second');
    expect(crsBlockReason([step('reproject', 'EPSG:99999'), step('reproject', 'EPSG:12345')], codes)).toBe(
      refused.message,
    );
  });
});
