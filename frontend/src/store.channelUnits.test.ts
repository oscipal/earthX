// @vitest-environment jsdom
//
// A colour picture has a unit for each channel (UI-03e, Otto, 3.11.2026): red, green and blue are each typed in values or in percentiles.
// "Apply" measures only the channels in percentiles, "Save" and a pinned layer keep the unit of each, and a look made with one pair for
// the three (before) still reads as three channels in percentiles.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { lookChanged, lookOfPendingFields, pendingFieldsOf, colourChannelsOf } from './render';
import { useAppStore } from './store';
import type { Collection, DownloadedInfo, StacItem } from './types';

const collection = {
  id: 's2',
  title: 's2',
  'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'pyramid' as const, overview_resampling: 'average' as const },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:true_color': ['red', 'green', 'blue'],
} as unknown as Collection;
const item: StacItem = { id: 'a1', collection: 's2', bbox: [10, 47, 11, 48], properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} };
const info: DownloadedInfo = { datasetId: 's2', tileUrl: '/collections/s2/items/a1/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual', bounds: [10, 47, 11, 48], asset: 'visual', minZoom: 8, maxZoom: 14 };

const state = () => useAppStore.getState();
const json = (body: unknown) => new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });
const USUAL = { low: '2', high: '98' };

// The scene's three bands, each with its own percentiles.
const band = (offset: number) => ({ min: offset, max: 200 + offset, count: 9, ...Object.fromEntries([...Array.from({ length: 99 }, (_, i) => i + 1)].map((n) => [`percentile_${n}`, offset + n])) });
const STATS = { '1': band(0), '2': band(100), '3': band(1000) };
let fetchMock: ReturnType<typeof vi.fn>;

function openView() {
  useAppStore.setState({
    datasets: datasetsFrom([collection]), datasetId: 's2', sections: [], openSectionId: null, items: [item],
    groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }], selectedIds: ['a1'], downloaded: { a1: info },
    focusMode: true, cropToAoi: false, viewAoi: null, shownImage: null, viewLooks: {}, savedLooks: {}, appliedRender: { rescale: '0,255' },
    pendingBand: '', pendingIndex: '', pendingUnit: 'value', pendingPercentLow: '2', pendingPercentHigh: '98', pendingVmin: '0', pendingVmax: '255',
    pendingChannels: [], layers: [], mosaics: {}, mapZoom: 12, error: null, notice: null, enhance: null,
  });
}

beforeEach(() => {
  fetchMock = vi.fn(async () => json(STATS));
  vi.stubGlobal('fetch', fetchMock);
  openView();
});
afterEach(() => vi.unstubAllGlobals());

const asked = () => fetchMock.mock.calls.flatMap(([url]) => new URL(String(url), 'http://x').searchParams.getAll('p'));

describe('the unit of one channel', () => {
  it('is switched on its own: the others stay as they are', () => {
    state().setPendingChannelUnit(1, 'percent');
    expect(state().pendingChannels).toEqual([{ vmin: '0', vmax: '255' }, { vmin: '0', vmax: '255', percent: USUAL }, { vmin: '0', vmax: '255' }]);
    expect(lookOfPendingFields(state())).toMatchObject({ rescale: '0,255', percentChannels: [null, USUAL, null], percent: undefined });
  });

  it('is switched back to values: the channel has no pair any more, and the look none at all if no other has', () => {
    state().setPendingChannelUnit(1, 'percent');
    state().setPendingChannelUnit(1, 'value');
    expect(state().pendingChannels[1]).toEqual({ vmin: '0', vmax: '255' });
    expect(lookOfPendingFields(state()).percentChannels).toBeUndefined();
  });

  it('takes the pair typed in one channel and in no other', () => {
    state().setPendingChannelUnit(0, 'percent');
    state().setPendingChannelPercent(0, 'low', '5');
    expect(state().pendingChannels.map((channel) => channel.percent)).toEqual([{ low: '5', high: '98' }, undefined, undefined]);
  });

  it('counts as another look, so that "Apply" is there to press', () => {
    const applied = { rescale: '0,255' };
    expect(lookChanged(applied, state())).toBe(false);
    state().setPendingChannelUnit(2, 'percent');
    expect(lookChanged(applied, state())).toBe(true);
    // A pair that is none counts too: it is to be corrected, not silently drawn as values.
    expect(lookChanged({ rescale: '0,255', percentChannels: [null, null, USUAL] }, { ...state(), pendingChannels: [{ vmin: '0', vmax: '255' }, { vmin: '0', vmax: '255' }, { vmin: '0', vmax: '255', percent: { low: '', high: '98' } }] })).toBe(true);
  });
});

describe('"Apply" with channels in percentiles', () => {
  it('measures the channels in percentiles at their own pair and own values, and leaves a channel in values alone', async () => {
    state().setPendingChannel(0, 'vmin', '10');
    state().setPendingChannel(0, 'vmax', '120');
    state().setPendingChannelUnit(1, 'percent');
    state().setPendingChannelUnit(2, 'percent');
    state().setPendingChannelPercent(2, 'low', '5');
    state().setPendingChannelPercent(2, 'high', '95');
    await state().applyRender();
    // Green at 2/98 of its own band (100 + n), blue at 5/95 of its own (1000 + n); red as typed.
    expect(state().appliedRender.rescale).toBe('10,120;102,198;1005,1095');
    expect(state().appliedRender.percentChannels).toEqual([null, USUAL, { low: '5', high: '95' }]);
    expect(state().appliedRender.percent).toBeUndefined();
    expect(new Set(asked())).toEqual(new Set(['2', '98', '5', '95']));
    expect(state().pendingChannels.map((channel) => channel.percent)).toEqual([undefined, USUAL, { low: '5', high: '95' }]);
  });

  it('asks nothing of the source where every channel is in values', async () => {
    state().setPendingChannel(0, 'vmax', '120');
    await state().applyRender();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(state().appliedRender.rescale).toBe('0,120;0,255;0,255');
    expect(state().appliedRender.percentChannels).toBeUndefined();
  });

  it('names the channel whose pair is none, and draws nothing', async () => {
    state().setPendingChannelUnit(1, 'percent');
    state().setPendingChannelPercent(1, 'high', '120');
    await state().applyRender();
    expect(state().notice).toMatch(/^green: /u);
    expect(state().appliedRender).toEqual({ rescale: '0,255' });
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('says so, and draws nothing, where a channel has no range at its percentiles', async () => {
    fetchMock.mockImplementation(async () => json({ ...STATS, '2': { ...band(100), percentile_2: 150, percentile_98: 150 } }));
    state().setPendingChannelUnit(1, 'percent');
    await state().applyRender();
    expect(state().notice).toMatch(/no range/u);
    expect(state().appliedRender).toEqual({ rescale: '0,255' });
  });
});

describe('"auto-scale" and "Enhance contrast" with channels in percentiles', () => {
  it('"auto-scale" puts the usual pair on the channels in percentiles and measures the others', async () => {
    fetchMock.mockImplementation(async () => json({ '1': { min: 0, max: 255, percentile_2: 7, percentile_98: 211, count: 9 } }));
    state().setPendingChannelUnit(0, 'percent');
    state().setPendingChannelPercent(0, 'low', '10');
    await state().autoStretch();
    expect(state().pendingChannels).toEqual([{ vmin: '0', vmax: '255', percent: USUAL }, { vmin: '7', vmax: '211' }, { vmin: '7', vmax: '211' }]);
  });

  it('"Enhance contrast" puts every channel in percentiles at the usual pair and draws nothing; "Apply" draws; a second click puts the fields back', async () => {
    state().setPendingChannelUnit(1, 'percent');
    state().setPendingChannelPercent(1, 'low', '10');
    await state().applyRender();
    const drawn = { ...state().appliedRender };
    await state().enhanceContrast();
    expect(state().pendingChannels.map((channel) => channel.percent)).toEqual([USUAL, USUAL, USUAL]);
    expect(state().appliedRender).toEqual(drawn);
    expect(state().enhance).not.toBeNull();
    await state().applyRender();
    expect(state().appliedRender.percentChannels).toEqual([USUAL, USUAL, USUAL]);
    await state().enhanceContrast();
    expect(state().pendingChannels.map((channel) => channel.percent)).toEqual([undefined, { low: '10', high: '98' }, undefined]);
    expect(state().enhance).toBeNull();
  });
});

describe('a look with a unit for each channel', () => {
  const look = { rescale: '10,120;102,198;1005,1095', percentChannels: [null, USUAL, { low: '5', high: '95' }] };

  it('gives the fields back: each channel in its own unit', () => {
    const fields = pendingFieldsOf(look);
    expect(fields.pendingChannels).toEqual([{ vmin: '10', vmax: '120' }, { vmin: '102', vmax: '198', percent: USUAL }, { vmin: '1005', vmax: '1095', percent: { low: '5', high: '95' } }]);
    expect(lookOfPendingFields({ ...fields, pendingChannels: fields.pendingChannels })).toMatchObject(look);
  });

  it('"Save" keeps it for the dataset, and the view of the next image opens with it', async () => {
    state().setPendingChannelUnit(1, 'percent');
    state().setPendingChannelUnit(2, 'percent');
    state().setPendingChannelPercent(2, 'low', '5');
    state().setPendingChannelPercent(2, 'high', '95');
    // Not applied yet: "Save" measures first, so that what is kept is what is drawn.
    await state().saveViewLook();
    expect(state().savedLooks.s2).toMatchObject({ rescale: '0,255;102,198;1005,1095', percentChannels: [null, USUAL, { low: '5', high: '95' }] });
  });

  it('is kept by a pinned layer, and its settings open with each channel in its unit', async () => {
    state().setPendingChannelUnit(1, 'percent');
    await state().applyRender();
    state().addCurrentToLayers();
    const layer = state().layers[0];
    expect(layer.restore.appliedRender).toMatchObject({ percentChannels: [null, USUAL, null] });
    expect(pendingFieldsOf(layer.restore.appliedRender!).pendingChannels.map((channel) => channel.percent)).toEqual([undefined, USUAL, undefined]);
  });
});

describe('a look made with one pair for the three channels (before)', () => {
  const old = { rescale: '10,120;102,198;1005,1095', percent: USUAL };

  it('reads as three channels in percentiles, and stays that look while nothing is changed', () => {
    const fields = pendingFieldsOf(old);
    expect(fields.pendingUnit).toBe('percent');
    expect(colourChannelsOf(fields).map((channel) => channel.percent)).toEqual([USUAL, USUAL, USUAL]);
    expect(lookChanged(old, fields)).toBe(false);
  });

  it('keeps the other two in percentiles when one is switched to values', () => {
    useAppStore.setState({ ...pendingFieldsOf(old) });
    state().setPendingChannelUnit(0, 'value');
    expect(state().pendingChannels.map((channel) => channel.percent)).toEqual([undefined, USUAL, USUAL]);
    expect(state().pendingUnit).toBe('value');
    expect(lookOfPendingFields(state())).toMatchObject({ percentChannels: [null, USUAL, USUAL], percent: undefined });
  });
});
