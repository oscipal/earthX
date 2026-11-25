// @vitest-environment jsdom
//
// The histograms of "Scale" in the colours of the picture (M5-60 §12, Otto 21.11.2026): one band in the colours of its colormap over the
// range of the fields, a colour picture in red, green and blue. A change of the range or the colormap colours them again at once, with no
// request but the one list of colormaps.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { forgetColormaps } from '../colormaps';
import type { Histogram } from '../histogram';
import ScaleHistograms from './ScaleHistograms';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const COLORMAPS = {
  groups: [{ name: 'Sequential', colormaps: [
    { name: 'gray', reversed: 'gray_r', colors: ['#000000', '#ffffff'] },
    { name: 'ramp', reversed: 'ramp_r', colors: ['#000000', '#ff0000'] },
  ] }],
};
const HISTOGRAM: Histogram = { counts: [1, 2, 3, 4], edges: [0, 10, 20, 30, 40] };

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  forgetColormaps();
  fetchMock = vi.fn(async () => new Response(JSON.stringify(COLORMAPS), { status: 200, headers: { 'Content-Type': 'application/json' } }));
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

const noop = () => {};

async function draw(props: Partial<Parameters<typeof ScaleHistograms>[0]>) {
  await act(async () => {
    root.render(<ScaleHistograms histograms={[HISTOGRAM]} unit="value" vmin="0" vmax="40" onVmin={noop} onVmax={noop} {...props} />);
    await new Promise((r) => setTimeout(r, 0));
  });
}

const fills = () => [...container.querySelectorAll<SVGRectElement>('.range-hist-bars rect')].map((rect) => rect.style.fill || rect.getAttribute('class'));

describe('the colours of the histogram of one band', () => {
  it('draws each bar in the colour of its value on the colormap', async () => {
    await draw({ colormap: 'gray' });
    expect(fills()).toEqual(['rgb(32, 32, 32)', 'rgb(96, 96, 96)', 'rgb(159, 159, 159)', 'rgb(223, 223, 223)']);
  });

  it('gives the bars outside the range the colours of its ends, and follows the fields as they change', async () => {
    await draw({ colormap: 'gray', vmin: '12', vmax: '28' });
    expect(fills()).toEqual(['rgb(0, 0, 0)', 'rgb(48, 48, 48)', 'rgb(207, 207, 207)', 'rgb(255, 255, 255)']);
    await draw({ colormap: 'gray_r', vmin: '12', vmax: '28' });
    expect(fills()[0]).toBe('rgb(255, 255, 255)');
    await draw({ colormap: 'ramp', vmin: '0', vmax: '40' });
    expect(fills()[3]).toBe('rgb(223, 0, 0)');
    // The list of colormaps was asked for once; nothing is measured again.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('places the range of fields in percentiles on the histogram', async () => {
    await draw({ colormap: 'gray', unit: 'percent', vmin: '0', vmax: '100' });
    expect(fills()).toEqual(['rgb(32, 32, 32)', 'rgb(96, 96, 96)', 'rgb(159, 159, 159)', 'rgb(223, 223, 223)']);
  });

  it('draws a band without a colormap in grey', async () => {
    await draw({ colormap: '' });
    expect(fills()[0]).toBe('rgb(32, 32, 32)');
  });

  it('keeps the colour of the page where the colormap is unknown or the list cannot be read', async () => {
    await draw({ colormap: 'nope' });
    expect(fills()).toEqual(['in', 'in', 'in', 'in']);
    forgetColormaps();
    fetchMock.mockImplementation(async () => new Response('', { status: 500 }));
    await act(async () => root.unmount());
    root = createRoot(container);
    await draw({ colormap: 'gray', vmin: '12', vmax: '28' });
    expect(fills()).toEqual(['out', 'in', 'in', 'out']);
  });
});

describe('the histograms of a colour picture', () => {
  it('draws each channel in its colour, without the colours of a colormap', async () => {
    await draw({ histograms: [HISTOGRAM, HISTOGRAM, HISTOGRAM], colormap: 'gray' });
    expect([...container.querySelectorAll('.range-hist')].map((el) => el.className)).toEqual(['range-hist range-hist-red', 'range-hist range-hist-green', 'range-hist range-hist-blue']);
    expect(fills().every((fill) => fill === 'in')).toBe(true);
  });
});

describe('the sliders on the bars (Otto, 24.11.2026)', () => {
  // Bars of ten over 0…120.
  const TENS: Histogram = { counts: Array(12).fill(5), edges: Array.from({ length: 13 }, (_, i) => i * 10) };
  const sliders = () => [...container.querySelectorAll<HTMLInputElement>('.range-hist input[type=range]')].map((input) => Number(input.value));

  it('stand outside the bars in the range where min and max lie inside bars; the bars between are the ones in the colours inside', async () => {
    await draw({ histograms: [TENS], colormap: 'gray', vmin: '23', vmax: '87' });
    expect(sliders()).toEqual([20, 90]);
    const bars = fills();
    expect(bars.slice(0, 2)).toEqual(['rgb(0, 0, 0)', 'rgb(0, 0, 0)']);
    expect(bars.slice(9)).toEqual(['rgb(255, 255, 255)', 'rgb(255, 255, 255)', 'rgb(255, 255, 255)']);
    expect(new Set(bars.slice(2, 9)).size).toBe(7);
  });

  it('stand the same way for each channel of a colour picture, the bars outside faint', async () => {
    await draw({ histograms: [TENS, TENS, TENS], vmin: '23', vmax: '87' });
    expect(sliders()).toEqual([20, 90, 20, 90, 20, 90]);
    expect(fills().slice(0, 12)).toEqual(['out', 'out', ...Array(7).fill('in'), 'out', 'out', 'out']);
  });

  it('move the value with the keys, not the place they are drawn at', async () => {
    const onVmin = vi.fn();
    await draw({ histograms: [TENS], colormap: 'gray', vmin: '23', vmax: '87', onVmin });
    const low = container.querySelector<HTMLInputElement>('.range-hist-low')!;
    await act(async () => {
      low.dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
    });
    // From 23, not from the edge at 20 where the slider stands; a thousandth of the track, rounded as a slider writes.
    expect(onVmin).toHaveBeenCalledWith('23.1');
  });
});

describe('a slider dragged (Otto, 24.11.2026)', () => {
  const TENS: Histogram = { counts: Array(12).fill(5), edges: Array.from({ length: 13 }, (_, i) => i * 10) };
  // The histogram 112 px wide: the thumb's line travels from 6 px to 106 px, over 0…120.
  const placed = (input: HTMLInputElement) => {
    input.getBoundingClientRect = () => ({ left: 100, width: 112, top: 0, height: 20, right: 212, bottom: 20, x: 100, y: 0, toJSON: () => ({}) });
    input.style.setProperty('--hist-thumb', '12px');
    return input;
  };
  const pointer = (input: HTMLInputElement, type: string, clientX: number) =>
    act(async () => {
      input.dispatchEvent(new MouseEvent(type, { bubbles: true, clientX }));
    });

  it('follows the pointer over the whole travel, past the ends to the ends of the histogram', async () => {
    const onVmin = vi.fn();
    const onVmax = vi.fn();
    await draw({ histograms: [TENS], colormap: 'gray', vmin: '23', vmax: '87', onVmin, onVmax });
    const low = placed(container.querySelector<HTMLInputElement>('.range-hist-low')!);
    await pointer(low, 'pointerdown', 126);
    await pointer(low, 'pointermove', 156);
    expect(onVmin).toHaveBeenLastCalledWith('60');
    await pointer(low, 'pointermove', 40);
    expect(onVmin).toHaveBeenLastCalledWith('0');
    await pointer(low, 'pointerup', 40);
    const high = placed(container.querySelector<HTMLInputElement>('.range-hist-high')!);
    await pointer(high, 'pointerdown', 196);
    await pointer(high, 'pointermove', 400);
    expect(onVmax).toHaveBeenLastCalledWith('120');
    await pointer(high, 'pointerup', 400);
    // Once let go, a move of the pointer moves nothing.
    onVmax.mockClear();
    await pointer(high, 'pointermove', 150);
    expect(onVmax).not.toHaveBeenCalled();
  });

  it('never takes the lower past the upper', async () => {
    const onVmin = vi.fn();
    await draw({ histograms: [TENS], colormap: 'gray', vmin: '23', vmax: '87', onVmin });
    const low = placed(container.querySelector<HTMLInputElement>('.range-hist-low')!);
    await pointer(low, 'pointerdown', 126);
    await pointer(low, 'pointermove', 500);
    expect(onVmin).toHaveBeenLastCalledWith('87');
  });
});

describe('the histogram of a band of classes (Otto F9 = 1)', () => {
  it('draws each bar in the colour of its class, without sliders', async () => {
    const { default: ClassHistogram } = await import('./ClassHistogram');
    await act(async () => {
      root.render(<ClassHistogram histogram={HISTOGRAM} classes={[{ value: 15, name: 'A', colour: '#ff0000' }, { value: 35, name: 'B', colour: '#0000ff' }]} />);
    });
    expect(fills()).toEqual(['in', 'rgb(255, 0, 0)', 'in', 'rgb(0, 0, 255)']);
    expect(container.querySelectorAll('input').length).toBe(0);
  });
});
