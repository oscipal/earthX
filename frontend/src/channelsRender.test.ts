// UI-03d: a range for each channel travels through the look, the controls, the tile URL and the result view. Tested here: the round
// trips between the modules, because each one reads the `;`-joined text of `channels.ts` on its own. A pair that is lost, doubled or
// moved on one of the ways would draw another picture than the one asked for without any error.

import { describe, expect, it } from 'vitest';

import { channelsOf } from './channels';
import { buildTileUrl } from './mapLayers';
import { rescaleOf } from './processingPreview';
import { lookChanged, lookOfPendingFields, pendingFieldsOf } from './render';
import { rangeOfTileUrl, renderOfRange } from './resultLayer';

const TEMPLATE = '/collections/c/items/i/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual';
const THREE = '1,2;3,4;5,6';
const rescalesOf = (url: string) => new URLSearchParams(url.slice(url.indexOf('?') + 1)).getAll('rescale');
const range = (vmin: string, vmax: string) => ({ vmin, vmax });
const fields = (over: Partial<Parameters<typeof lookOfPendingFields>[0]> = {}) => ({ pendingColormapName: '', pendingVmin: '', pendingVmax: '', ...over });

describe('buildTileUrl with a range for each channel', () => {
  it('appends three `rescale` parameters, in the order red, green, blue', () => {
    const url = buildTileUrl(TEMPLATE, { rescale: 'a,b;c,d;e,f' });
    expect(rescalesOf(url)).toEqual(['a,b', 'c,d', 'e,f']);
    expect(url.startsWith(`${TEMPLATE}&`)).toBe(true);
    expect(rescalesOf(buildTileUrl(TEMPLATE, { rescale: '5,6;3,4;1,2' }))).toEqual(['5,6', '3,4', '1,2']);
  });

  it('keeps one pair as one parameter', () => {
    expect(rescalesOf(buildTileUrl(TEMPLATE, { rescale: '10,2900' }))).toEqual(['10,2900']);
    // Gegenprobe: the `;` never reaches the URL as text.
    expect(buildTileUrl(TEMPLATE, { rescale: THREE })).not.toContain('%3B');
    expect(buildTileUrl(TEMPLATE, { rescale: THREE })).not.toContain(';');
  });

  it('leaves the template as it is where there is no range', () => {
    expect(buildTileUrl(TEMPLATE, {})).toBe(TEMPLATE);
    expect(buildTileUrl(TEMPLATE, { rescale: '' })).toBe(TEMPLATE);
    expect(buildTileUrl(TEMPLATE, { rescale: undefined })).toBe(TEMPLATE);
  });

  it('carries the other parameters along with the three ranges', () => {
    const query = new URLSearchParams(buildTileUrl(TEMPLATE, { bidx: '3,2,1', rescale: THREE }).split('&').slice(1).join('&'));
    expect(query.getAll('bidx')).toEqual(['3', '2', '1']);
    expect(query.getAll('rescale')).toEqual(['1,2', '3,4', '5,6']);
  });
});

describe('pendingFieldsOf and lookOfPendingFields', () => {
  it('splits three pairs into three channels, and the first pair into the shared fields', () => {
    const p = pendingFieldsOf({ rescale: '1,2;3,4;5,6' });
    expect(p.pendingChannels).toEqual([range('1', '2'), range('3', '4'), range('5', '6')]);
    expect([p.pendingVmin, p.pendingVmax]).toEqual(['1', '2']);
  });

  it('leaves the channels empty for one pair, for no range, and for two or four pairs', () => {
    expect(pendingFieldsOf({ rescale: '1,2' }).pendingChannels).toEqual([]);
    expect(pendingFieldsOf({}).pendingChannels).toEqual([]);
    expect(pendingFieldsOf({ rescale: '1,2;3,4' }).pendingChannels).toEqual([]);
    expect(pendingFieldsOf({ rescale: '1,2;3,4;5,6;7,8' }).pendingChannels).toEqual([]);
  });

  it('puts the channels back to the same rescale', () => {
    for (const rescale of [THREE, '-1,1;0,0.5;10,2900']) expect(lookOfPendingFields(fields(pendingFieldsOf({ rescale }))).rescale).toBe(rescale);
    expect(lookOfPendingFields(fields({ pendingChannels: [range('1', '2'), range('3', '4'), range('5', '6')] })).rescale).toBe(THREE);
  });

  it('writes three equal channels as one pair', () => {
    expect(lookOfPendingFields(fields({ pendingChannels: channelsOf('0', '255') })).rescale).toBe('0,255');
    // Gegenprobe: one channel differing keeps all three.
    expect(lookOfPendingFields(fields({ pendingChannels: [range('0', '255'), range('0', '255'), range('0', '254')] })).rescale).toBe('0,255;0,255;0,254');
  });

  it('uses the shared fields as before where no channels are set', () => {
    expect(lookOfPendingFields(fields({ pendingVmin: ' 10 ', pendingVmax: '2900', pendingChannels: [] })).rescale).toBe('10,2900');
    expect(lookOfPendingFields(fields({ pendingVmin: '10', pendingVmax: '2900' })).rescale).toBe('10,2900');
    expect(lookOfPendingFields(fields({ pendingVmin: '10', pendingVmax: '' })).rescale).toBeUndefined();
  });

  it('lets the channels win over the shared fields', () => {
    expect(lookOfPendingFields(fields({ pendingVmin: '7', pendingVmax: '8', pendingChannels: [range('1', '2'), range('3', '4'), range('5', '6')] })).rescale).toBe(THREE);
  });

  it('asks for no range while a channel is half typed, whatever the shared fields say', () => {
    const half = [range('1', '2'), range('3', ''), range('5', '6')];
    expect(lookOfPendingFields(fields({ pendingVmin: '7', pendingVmax: '8', pendingChannels: half })).rescale).toBeUndefined();
  });

  it('asks for no range for a wrong number of channels', () => {
    expect(lookOfPendingFields(fields({ pendingChannels: [range('1', '2'), range('3', '4')] })).rescale).toBeUndefined();
  });
});

describe('lookChanged with channels', () => {
  const applied = { rescale: THREE };
  const same = fields(pendingFieldsOf(applied));

  it('sees no change in the channels the look was made with', () => {
    expect(lookChanged(applied, same)).toBe(false);
  });

  it('sees a change in any end of any channel', () => {
    const channels = pendingFieldsOf(applied).pendingChannels;
    for (const index of [0, 1, 2]) {
      for (const end of ['vmin', 'vmax'] as const) {
        const changed = channels.map((c, i) => (i === index ? { ...c, [end]: `${c[end]}9` } : c));
        expect(lookChanged(applied, fields({ pendingChannels: changed })), `${end} ${index}`).toBe(true);
      }
    }
  });

  it('sees one range for all set channel by channel, and the other way round', () => {
    expect(lookChanged({ rescale: '1,2' }, fields({ pendingVmin: '1', pendingVmax: '2', pendingChannels: [range('1', '2'), range('3', '4'), range('5', '6')] }))).toBe(true);
    expect(lookChanged(applied, fields({ pendingVmin: '1', pendingVmax: '2' }))).toBe(true);
  });

  it('sees no change where three equal channels are the one pair of the look', () => {
    expect(lookChanged({ rescale: '0,255' }, fields({ pendingChannels: channelsOf('0', '255') }))).toBe(false);
  });

  it('sees a channel half typed as a change from the look', () => {
    expect(lookChanged(applied, fields({ pendingChannels: [range('1', '2'), range('3', ''), range('5', '6')] }))).toBe(true);
  });
});

describe('rangeOfTileUrl and renderOfRange', () => {
  const resultUrl = `/collections/c/results/r/tiles/{z}/{x}/{y}?tilesize=256&bidx=1&bidx=2&bidx=3&rescale=1%2C2&rescale=3%2C4&rescale=5%2C6`;

  it('reads three `rescale` parameters as three channels, the first in the shared ends', () => {
    const range3 = rangeOfTileUrl(resultUrl);
    expect(range3.channels).toEqual([range('1', '2'), range('3', '4'), range('5', '6')]);
    expect([range3.vmin, range3.vmax]).toEqual(['1', '2']);
  });

  it('reads one `rescale` and the colormap as before, without channels', () => {
    const one = rangeOfTileUrl('/r/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=10%2C2900');
    expect(one).toEqual({ vmin: '10', vmax: '2900', colormap: 'viridis' });
    expect(one.channels).toBeUndefined();
  });

  it('reads a URL without a `rescale` as an empty range', () => {
    expect(rangeOfTileUrl('/r/{z}/{x}/{y}?tilesize=256')).toEqual({ vmin: '', vmax: '', colormap: '' });
  });

  it('gives the joined rescale back for the channels it read', () => {
    expect(renderOfRange(rangeOfTileUrl(resultUrl))).toEqual({ rescale: THREE });
    const url = buildTileUrl('/r/{z}/{x}/{y}?tilesize=256', { rescale: '-1,1;0,0.5;10,2900' });
    expect(renderOfRange(rangeOfTileUrl(url))).toEqual({ rescale: '-1,1;0,0.5;10,2900' });
  });

  it('returns the joined rescale for channels, and the colormap beside them where there is one', () => {
    const channels = [range('1', '2'), range('3', '4'), range('5', '6')];
    expect(renderOfRange({ vmin: '', vmax: '', colormap: '', channels })).toEqual({ rescale: THREE });
    expect(renderOfRange({ vmin: '1', vmax: '2', colormap: 'viridis', channels })).toEqual({ rescale: THREE, colormapName: 'viridis' });
  });

  it('returns null with a broken channel, and not the shared ends in its place', () => {
    expect(renderOfRange({ vmin: '1', vmax: '2', colormap: '', channels: [range('1', '2'), range('x', '4'), range('5', '6')] })).toBeNull();
    expect(renderOfRange({ vmin: '1', vmax: '2', colormap: '', channels: [range('1', '2'), range('3', '4'), range('6', '5')] })).toBeNull();
    expect(renderOfRange({ vmin: '1', vmax: '2', colormap: '', channels: [range('1', '2'), range('3', '4'), range('5', '')] })).toBeNull();
    // Gegenprobe: without channels the same shared ends are a range.
    expect(renderOfRange({ vmin: '1', vmax: '2', colormap: '' })).toEqual({ rescale: '1,2' });
  });

  it('returns null for a URL with two `rescale` parameters: two are no colour picture', () => {
    expect(renderOfRange(rangeOfTileUrl('/r/{z}/{x}/{y}?tilesize=256&rescale=1%2C2&rescale=3%2C4'))).toBeNull();
  });

  it('returns null for a URL with a `rescale` that is no number', () => {
    expect(renderOfRange(rangeOfTileUrl('/r/{z}/{x}/{y}?tilesize=256&rescale=a%2Cb&rescale=1%2C2&rescale=3%2C4'))).toBeNull();
    expect(renderOfRange(rangeOfTileUrl('/r/{z}/{x}/{y}?tilesize=256&rescale=1%2C2&rescale=3%2C4&rescale='))).toBeNull();
  });
});

describe('rescaleOf with channels', () => {
  it('gives the joined rescale of the channels', () => {
    expect(rescaleOf({ vmin: '', vmax: '', colormap: '', channels: [range('1', '2'), range('3', '4'), range('5', '6')] })).toEqual({ rescale: THREE });
  });

  it('writes three equal channels as one pair, and the numbers as numbers', () => {
    expect(rescaleOf({ vmin: '', vmax: '', colormap: '', channels: channelsOf('010', '20') })).toEqual({ rescale: '10,20' });
  });

  it('takes the channels, not the shared ends, where it has both', () => {
    expect(rescaleOf({ vmin: '7', vmax: '8', colormap: '', channels: [range('0', '1'), range('1', '2'), range('2', '3')] })).toEqual({ rescale: '0,1;1,2;2,3' });
    // Even where the shared ends are broken.
    expect(rescaleOf({ vmin: 'x', vmax: '', colormap: '', channels: [range('1', '2'), range('3', '4'), range('5', '6')] })).toEqual({ rescale: THREE });
  });

  it('names the channel where one is broken', () => {
    expect(rescaleOf({ vmin: '', vmax: '', colormap: '', channels: [range('1', '2'), range('3', 'x'), range('5', '6')] })).toEqual({ problem: 'Enter a number for both ends of green.' });
    expect(rescaleOf({ vmin: '', vmax: '', colormap: '', channels: [range('1', '2'), range('3', '4'), range('6', '5')] })).toEqual({ problem: 'The lower end of blue must be below the upper end.' });
  });

  it('asks for a range for each channel where there are not three', () => {
    expect(rescaleOf({ vmin: '', vmax: '', colormap: '', channels: [range('1', '2')] })).toEqual({ problem: 'Enter a range for each channel.' });
  });

  it('uses the shared ends as before where the channels are empty or missing', () => {
    expect(rescaleOf({ vmin: '1', vmax: '2', colormap: '', channels: [] })).toEqual({ rescale: '1,2' });
    expect(rescaleOf({ vmin: '1', vmax: '2', colormap: '' })).toEqual({ rescale: '1,2' });
    expect(rescaleOf({ vmin: '2', vmax: '1', colormap: '', channels: [] })).toEqual({ problem: 'The lower end of the range must be below the upper end.' });
    expect(rescaleOf({ vmin: '', vmax: '', colormap: '' })).toEqual({ problem: 'Enter a number for both ends of the range.' });
  });
});

describe('a reversed colormap of a result layer (UI-03d)', () => {
  it('is drawn and read back as the tiler names it', () => {
    const render = renderOfRange({ vmin: '0', vmax: '1', colormap: 'mako_r' });
    expect(render).toMatchObject({ colormapName: 'mako_r' });
    expect(rangeOfTileUrl(buildTileUrl('/results/x/tiles/{z}/{x}/{y}?tilesize=256', render!)).colormap).toBe('mako_r');
  });
});
