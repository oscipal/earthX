// @vitest-environment jsdom
//
// The histograms of a picture while the values of its parameters change (M5-14, Otto, 17.11.2026): the last ones stay until the new ones come,
// and the new ones are asked for once the values rest, so the panel does not jump while a dial turns. Another picture starts empty, as before.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { Histogram } from '../histogram';
import { forgetHistograms, HISTOGRAM_REST_MS, useHistograms } from './useHistograms';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const histogram = (n: number): Histogram => ({ counts: [n], edges: [0, 1] }) as unknown as Histogram;

let container: HTMLDivElement;
let root: Root;
let shown: Histogram[] | null;
let load: ReturnType<typeof vi.fn<(key: string) => Promise<Histogram[] | null>>>;

function Probe({ id, family }: { id: string; family: string | null }) {
  shown = useHistograms(id, () => load(id), family);
  return null;
}
const render = (id: string, family: string | null) => act(() => root.render(<Probe id={id} family={family} />));
const settle = () =>
  act(async () => {
    for (let i = 0; i < 10; i++) await Promise.resolve();
  });

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  forgetHistograms();
  vi.useFakeTimers();
  load = vi.fn(async (key: string) => [histogram(Number(key.split(':')[1]))]);
  container = document.createElement('div');
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  vi.useRealTimers();
});

describe('the histograms of one picture with other values', () => {
  it('stay as they were while the values change, and are asked for once, after the pause', async () => {
    render('hillshade:315', 'view|hillshade');
    await settle();
    expect(shown).toEqual([histogram(315)]);
    for (const azimuth of [316, 317, 318, 330]) render(`hillshade:${azimuth}`, 'view|hillshade');
    await settle();
    expect(shown).toEqual([histogram(315)]);
    expect(load).toHaveBeenCalledTimes(1);
    await act(async () => {
      vi.advanceTimersByTime(HISTOGRAM_REST_MS);
    });
    await settle();
    expect(load.mock.calls.map(([key]) => key)).toEqual(['hillshade:315', 'hillshade:330']);
    expect(shown).toEqual([histogram(330)]);
  });

  it('are asked for at once, and none shown meanwhile, for another picture', async () => {
    render('hillshade:315', 'view|hillshade');
    await settle();
    render('slope:1', 'view|slope');
    expect(shown).toBeNull();
    await settle();
    expect(shown).toEqual([histogram(1)]);
  });

  it('are asked for at once without a family, as for any picture', async () => {
    render('ndvi:1', null);
    await settle();
    render('ndvi:2', null);
    expect(shown).toBeNull();
    await settle();
    expect(load).toHaveBeenCalledTimes(2);
  });
});
