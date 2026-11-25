// The colours of the bars of a histogram (M5-60 §12, Otto 21.11.2026): each bar in the colour its value has on the map, the colours of
// the ends below and above the range. Synthetic colormaps only.

import { describe, expect, it } from 'vitest';

import type { ColormapGroup } from './colormaps';
import { barColours, classColours, colourAt } from './histogramColours';

const GROUPS: ColormapGroup[] = [
  {
    name: 'Sequential',
    colormaps: [
      { name: 'ramp', reversed: 'ramp_r', colors: ['#000000', '#ff0000', '#ffffff'] },
      { name: 'gray', reversed: 'gray_r', colors: ['#000000', '#ffffff'] },
    ],
  },
];

// Four bars over 0…40, their middles at 5, 15, 25 and 35.
const HISTOGRAM = { counts: [1, 2, 3, 4], edges: [0, 10, 20, 30, 40] };

describe('colourAt', () => {
  it('runs straight between the colours of the preview', () => {
    expect(colourAt(['#000000', '#ff0000', '#ffffff'], 0)).toBe('#000000');
    expect(colourAt(['#000000', '#ff0000', '#ffffff'], 0.25)).toBe('#800000');
    expect(colourAt(['#000000', '#ff0000', '#ffffff'], 0.5)).toBe('#ff0000');
    expect(colourAt(['#000000', '#ff0000', '#ffffff'], 1)).toBe('#ffffff');
  });

  it('keeps to the ends beyond 0 and 1, and has the one colour of a list of one', () => {
    expect(colourAt(['#000000', '#ffffff'], -3)).toBe('#000000');
    expect(colourAt(['#000000', '#ffffff'], 7)).toBe('#ffffff');
    expect(colourAt(['#123456'], 0.4)).toBe('#123456');
  });
});

describe('barColours', () => {
  it('gives each bar the colour of its middle in the range', () => {
    expect(barColours(HISTOGRAM, GROUPS, 'gray', 0, 40)).toEqual(['#202020', '#606060', '#9f9f9f', '#dfdfdf']);
  });

  it('gives bars below and above the range the colours of its ends', () => {
    expect(barColours(HISTOGRAM, GROUPS, 'gray', 12, 28)).toEqual(['#000000', '#303030', '#cfcfcf', '#ffffff']);
  });

  it('reverses a colormap named with "_r"', () => {
    expect(barColours(HISTOGRAM, GROUPS, 'gray_r', 0, 40)).toEqual(['#dfdfdf', '#9f9f9f', '#606060', '#202020']);
  });

  it('draws a band without a colormap in the grey of the tiler', () => {
    expect(barColours(HISTOGRAM, GROUPS, '', 0, 40)).toEqual(barColours(HISTOGRAM, GROUPS, 'gray', 0, 40));
  });

  it('follows another colormap and another range at once, from what it is given', () => {
    expect(barColours(HISTOGRAM, GROUPS, 'ramp', 0, 40)?.[1]).toBe('#bf0000');
    expect(barColours(HISTOGRAM, GROUPS, 'ramp', 0, 20)?.[1]).toBe('#ff8080');
  });

  it('splits an empty range at its value: below it the lower end, from it on the upper', () => {
    expect(barColours(HISTOGRAM, GROUPS, 'gray', 20, 20)).toEqual(['#000000', '#000000', '#ffffff', '#ffffff']);
  });

  it('gives none where the colormap is not known or the list is not there yet', () => {
    expect(barColours(HISTOGRAM, GROUPS, 'nope', 0, 40)).toBeNull();
    expect(barColours(HISTOGRAM, null, 'gray', 0, 40)).toBeNull();
    expect(barColours(HISTOGRAM, [{ name: 'x', colormaps: [{ name: 'void', reversed: null, colors: [] }] }], 'void', 0, 40)).toBeNull();
  });
});

describe('classColours (Otto F9 = 1)', () => {
  const classes = [
    { value: 10, name: 'Tree cover', colour: '#006400' },
    { value: 20, name: 'Shrubland', colour: '#ffbb22' },
    { value: 21, name: 'Close by', colour: '#123456' },
    { value: 40, name: 'Cropland', colour: '#f096ff' },
  ];

  it('gives a bar the colour of the class whose value lies in it, the one nearest its middle where it holds several', () => {
    // Bars 0–10, 10–20, 20–30, 30–40: 10 lies in the second, 20 and 21 in the third (21 nearer 25), 40 on the last edge.
    expect(classColours(HISTOGRAM, classes)).toEqual([null, '#006400', '#123456', '#f096ff']);
  });

  it('has no colour for a bar without a class, and none at all without classes', () => {
    expect(classColours({ counts: [1, 1], edges: [50, 60, 70] }, classes)).toEqual([null, null]);
    expect(classColours(HISTOGRAM, [])).toEqual([null, null, null, null]);
  });
});
