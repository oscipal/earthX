// How the registry of an operator says a band is drawn (M5-10, Otto, 16.11.2026): read from the process description, applied to the
// measure of a preview and of a result. The terrain products are the case: slope, hillshade and aspect.

import { describe, expect, it } from 'vitest';

import { DEFAULT_PERCENT } from './percentRange';
import { lookOfStep, looksOfOperator, lookRange, percentOfLook, type DisplayLook } from './displayLook';
import dem from './fixtures/processes/cop-dem-glo-30.json';
import swiss from './fixtures/processes/swissalti3d.json';
import type { ProcessDescription } from './processing';
import { processInfo } from './processingOrder';
import { measuredRange, type PreviewMeasure } from './processingPreview';
import type { ResultStats } from './render';

const SLOPE: DisplayLook = { colormap: 'rdylgn_r', scale: 'measured' };
const HILLSHADE: DisplayLook = { colormap: 'greys_r', scale: 'percentiles', low: 0, high: 100 };
const ASPECT: DisplayLook = { colormap: 'hsv', scale: 'fixed', low: 0, high: 360 };
const RAW = { by: { slope: SLOPE, hillshade: HILLSHADE, aspect: ASPECT } };
// What a job measured: 3 to 96 degrees of slope in the middle 96 %, 0 to 100 at the ends.
const STATS: ResultStats = { expression: false, bands: [{ minimum: 0, maximum: 100, percentile2: 3, percentile98: 96 }] };

describe('the looks of a terrain step in the process description', () => {
  it.each([['cop-dem-glo-30', dem], ['swissalti3d', swiss]])('are the ones of the registry for %s, as it says them', (_, description) => {
    const terrain = processInfo(description as unknown as ProcessDescription).operators.find((o) => o.op === 'terrain')!;
    expect(terrain.looks).toEqual({ param: 'product', ...RAW });
  });

  it('are none for an operator that says none', () => {
    const others = processInfo(dem as unknown as ProcessDescription).operators.filter((o) => o.op !== 'terrain');
    expect(others.length).toBeGreaterThan(0);
    expect(others.map((o) => o.looks)).toEqual(others.map(() => null));
  });
});

describe('looksOfOperator', () => {
  it('reads what the description says', () => {
    expect(looksOfOperator({ param: 'product', by: { slope: { colormap: 'rdylgn_r', scale: 'measured' } } })).toEqual({ param: 'product', by: { slope: SLOPE } });
  });

  it.each([
    ['nothing', undefined],
    ['text', 'terrain'],
    ['a list', []],
    ['no parameter', { by: { a: SLOPE } }],
    ['no table', { param: 'product' }],
    ['an empty table', { param: 'product', by: {} }],
  ])('is none for %s', (_, value) => {
    expect(looksOfOperator(value)).toBeNull();
  });

  it.each([
    ['no colormap', { scale: 'measured' }],
    ['an empty colormap', { colormap: '', scale: 'measured' }],
    ['an unknown scale', { colormap: 'hsv', scale: 'log' }],
    ['a fixed scale without ends', { colormap: 'hsv', scale: 'fixed' }],
    ['ends that are text', { colormap: 'hsv', scale: 'fixed', low: '0', high: '360' }],
    ['ends the wrong way round', { colormap: 'hsv', scale: 'fixed', low: 360, high: 0 }],
    ['equal ends', { colormap: 'hsv', scale: 'fixed', low: 5, high: 5 }],
    ['percentiles over 100', { colormap: 'greys_r', scale: 'percentiles', low: 0, high: 101 }],
    ['percentiles below 0', { colormap: 'greys_r', scale: 'percentiles', low: -1, high: 100 }],
  ])('leaves out a look with %s, and keeps the others', (_, look) => {
    expect(looksOfOperator({ param: 'product', by: { bad: look, slope: SLOPE } })).toEqual({ param: 'product', by: { slope: SLOPE } });
  });

  it('is none where the only look is incomplete', () => {
    expect(looksOfOperator({ param: 'product', by: { bad: { colormap: 'hsv', scale: 'fixed' } } })).toBeNull();
  });
});

describe('lookOfStep', () => {
  const looks = { param: 'product', ...RAW };

  it('takes the look of the value of the parameter of the step', () => {
    expect(lookOfStep(looks, { product: 'aspect', name: 'a' })).toEqual(ASPECT);
    expect(lookOfStep(looks, { product: 'hillshade' })).toEqual(HILLSHADE);
  });

  it('is none for a value the registry does not know, a missing or a wrong parameter, and an operator without looks', () => {
    expect(lookOfStep(looks, { product: 'curvature' })).toBeNull();
    expect(lookOfStep(looks, {})).toBeNull();
    expect(lookOfStep(looks, { product: 3 })).toBeNull();
    expect(lookOfStep(looks, { product: 'toString' })).toBeNull();
    expect(lookOfStep(null, { product: 'slope' })).toBeNull();
    expect(lookOfStep(undefined, { product: 'slope' })).toBeNull();
  });
});

describe('lookRange', () => {
  it('draws a slope on the usual scale of the measure, in the colormap of the registry', () => {
    expect(lookRange(SLOPE, STATS)).toEqual({ vmin: '3', vmax: '96', colormap: 'rdylgn_r' });
  });

  it('draws a hillshade from the minimum to the maximum (0 to 100 %)', () => {
    expect(lookRange(HILLSHADE, STATS)).toEqual({ vmin: '0', vmax: '100', colormap: 'greys_r' });
  });

  it('draws an aspect on 0 to 360 whatever was measured, and with nothing measured', () => {
    const fixed = { vmin: '0', vmax: '360', colormap: 'hsv' };
    expect(lookRange(ASPECT, STATS)).toEqual(fixed);
    expect(lookRange(ASPECT, { expression: false, bands: [{ minimum: 10, maximum: 20, percentile2: 11, percentile98: 19 }] })).toEqual(fixed);
    expect(lookRange(ASPECT, null)).toEqual(fixed);
  });

  it('has nothing to draw a measured scale with where nothing was measured', () => {
    expect(lookRange(SLOPE, null)).toBeNull();
    expect(lookRange(HILLSHADE, null)).toBeNull();
    expect(lookRange(HILLSHADE, { expression: false, bands: [] })).toBeNull();
  });

  it('does not judge the values as an index, however flat the slope is (−1 to 1)', () => {
    const flat: ResultStats = { expression: true, bands: [{ minimum: 0, maximum: 0.9, percentile2: 0.1, percentile98: 0.8 }] };
    expect(lookRange(SLOPE, flat)).toEqual({ vmin: '0.1', vmax: '0.8', colormap: 'rdylgn_r' });
  });

  it('takes the 2nd to 98th percentile where the percentiles asked are those', () => {
    const wide: DisplayLook = { colormap: 'greys_r', scale: 'percentiles', low: 2, high: 98 };
    expect(lookRange(wide, STATS)).toEqual({ vmin: '3', vmax: '96', colormap: 'greys_r' });
  });

  it('falls back to the usual scale for percentiles the measure does not carry', () => {
    const odd: DisplayLook = { colormap: 'greys_r', scale: 'percentiles', low: 5, high: 95 };
    expect(lookRange(odd, STATS)).toEqual({ vmin: '3', vmax: '96', colormap: 'greys_r' });
  });

  it('takes the minimum and the maximum of all the bands of the measure', () => {
    const two: ResultStats = { expression: false, bands: [{ minimum: 5, maximum: 50, percentile2: 6, percentile98: 49 }, { minimum: 1, maximum: 70, percentile2: 2, percentile98: 60 }] };
    expect(lookRange(HILLSHADE, two)).toEqual({ vmin: '1', vmax: '70', colormap: 'greys_r' });
  });
});

describe('measuredRange with a look', () => {
  const measure = (stats: ResultStats | null): PreviewMeasure => ({ key: 'k', stats, unit: null, source: 'scene', exact: true });

  it('is the range of the look, the fields as numbers', () => {
    expect(measuredRange(measure(STATS), HILLSHADE)).toEqual({ vmin: '0', vmax: '100', colormap: 'greys_r' });
    expect(measuredRange(measure(STATS), SLOPE)).toEqual({ vmin: '3', vmax: '96', colormap: 'rdylgn_r' });
    expect(measuredRange(null, ASPECT)).toEqual({ vmin: '0', vmax: '360', colormap: 'hsv' });
  });

  it('is the usual rule of the measure without a look', () => {
    expect(measuredRange(measure(STATS))).toEqual({ vmin: '3', vmax: '96', colormap: 'viridis' });
  });

  it('is nothing where a look needs a measure that is not there', () => {
    expect(measuredRange(null, SLOPE)).toBeNull();
  });
});

describe('percentOfLook ("Auto-scale" of a range typed in percentiles)', () => {
  it('is 0 and 100 for a hillshade, and the usual 2 and 98 for the others', () => {
    expect(percentOfLook(HILLSHADE)).toEqual({ low: '0', high: '100' });
    expect(percentOfLook(SLOPE)).toEqual(DEFAULT_PERCENT);
    expect(percentOfLook(null)).toEqual(DEFAULT_PERCENT);
  });
});
