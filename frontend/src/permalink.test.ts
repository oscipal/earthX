// @vitest-environment jsdom
//
// Permalinks (M4-19e): the address, the view, the keys of this browser and the calls, with
// `fetch` stubbed. Opening a link in the panel is in `components/ProcessingShare.test.tsx`.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { HttpError } from './api';
import {
  createPermalink,
  deletePermalink,
  fetchPermalink,
  forgetKey,
  GONE_TEXT,
  KEYS_STORAGE,
  loadKeys,
  parseView,
  permalinkAddress,
  permalinkIdIn,
  rememberKey,
  removePermalink,
  viewOf,
} from './permalink';
import type { Order } from './processing';

const ID = 'AbCdEfGhIjKlMnOpQrSt_-';
const OTHER = 'ZyXwVuTsRqPoNmLkJiHg_-';
const ORDER: Order = {
  recipe_version: 1,
  inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2_A']], assets: ['red', 'nir'] }],
  aoi: { type: 'Polygon', coordinates: [[[9.01, 47.01], [9.02, 47.01], [9.02, 47.02], [9.01, 47.02], [9.01, 47.01]]] },
  steps: [{ op: 'band_math', op_version: 1, params: { expression: '(nir - red) / (nir + red)' } }],
  output: { kind: 'raster', format: 'cog', dtype: 'float32' },
};
const VIEW = { center: [9.5, 47.25] as [number, number], zoom: 9.5, range: null, title: null };
const FUTURE = new Date(Date.now() + 86_400_000).toISOString();

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

let fetchMock: ReturnType<typeof vi.fn>;
beforeEach(() => {
  localStorage.clear();
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

describe('the address', () => {
  it('holds the identifier and nothing of the order', () => {
    const address = permalinkAddress(ID, { origin: 'https://earthx.example', pathname: '/app/' });
    expect(address).toBe(`https://earthx.example/app/?permalink=${ID}`);
    expect(address).not.toMatch(/47\.0|9\.0|sentinel|aoi/u);
  });

  it('is read only where it is an identifier', () => {
    expect(permalinkIdIn(`?permalink=${ID}`)).toBe(ID);
    expect(permalinkIdIn(`?x=1&permalink=${ID}`)).toBe(ID);
    for (const search of ['', '?permalink=', '?permalink=short', `?permalink=${ID}x`, '?permalink=../../x', '?permalink=%3Cb%3E']) {
      expect(permalinkIdIn(search)).toBeNull();
    }
  });
});

describe('viewOf', () => {
  it('takes the centre of the viewport, also across the antimeridian', () => {
    expect(viewOf([8, 46, 11, 48], 9.5, null, '').center).toEqual([9.5, 47]);
    expect(viewOf([170, -10, -160, 10], 3, null, '').center).toEqual([-175, 0]);
    expect(viewOf([175, -10, -175, 10], 3, null, '').center[0]).toBe(180);
  });

  it('keeps a range only where the user set one, as numbers, and drops one that is none', () => {
    expect(viewOf([8, 46, 11, 48], 5, null, '').range).toBeNull();
    expect(viewOf([8, 46, 11, 48], 5, { vmin: '0', vmax: '0.5', colormap: 'viridis' }, '').range).toEqual({
      vmin: 0,
      vmax: 0.5,
      colormap: 'viridis',
    });
    expect(viewOf([8, 46, 11, 48], 5, { vmin: '', vmax: '1', colormap: 'viridis' }, '').range).toBeNull();
    expect(viewOf([8, 46, 11, 48], 5, { vmin: 'x', vmax: '1', colormap: '' }, '').range).toBeNull();
  });

  it('clamps the zoom and trims and cuts the title', () => {
    expect(viewOf([8, 46, 11, 48], 99, null, '').zoom).toBe(24);
    expect(viewOf([8, 46, 11, 48], -1, null, '').zoom).toBe(0);
    expect(viewOf([8, 46, 11, 48], 5, null, '   ').title).toBeNull();
    expect(viewOf([8, 46, 11, 48], 5, null, `  ${'x'.repeat(150)} `).title).toHaveLength(100);
  });
});

describe('parseView', () => {
  it('reads what viewOf writes', () => {
    const view = viewOf([8, 46, 11, 48], 5, { vmin: '0', vmax: '1', colormap: 'plasma' }, 'Lake');
    expect(parseView(JSON.parse(JSON.stringify(view)))).toEqual(view);
  });

  it.each([null, 'x', [], {}, { center: [1], zoom: 1 }, { center: [1, 2], zoom: '1' }, { center: [1, 'x'], zoom: 1 }, { center: [1, 2], zoom: 1, range: 5 }, { center: [1, 2], zoom: 1, range: { vmin: 0 } }])(
    'refuses %j',
    (value) => expect(parseView(value)).toBeNull(),
  );
});

describe('the calls', () => {
  it('creates a link with the order and the view and nothing else', async () => {
    fetchMock.mockResolvedValue(json({ id: ID, expires_at: FUTURE, delete_key: 'k'.repeat(22) }, 201));
    expect(await createPermalink(ORDER, VIEW)).toEqual({ id: ID, expiresAt: FUTURE, deleteKey: 'k'.repeat(22) });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/processing/permalinks');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ order: ORDER, view: VIEW });
  });

  it('refuses an answer it cannot read, and passes a refusal on', async () => {
    fetchMock.mockResolvedValueOnce(json({ id: 'short', expires_at: FUTURE, delete_key: 'k' }, 201));
    await expect(createPermalink(ORDER, VIEW)).rejects.toThrow(/cannot read/u);
    fetchMock.mockResolvedValueOnce(json({ detail: 'invalid view: zoom: less_than_equal' }, 422));
    await expect(createPermalink(ORDER, VIEW)).rejects.toMatchObject({ status: 422 });
  });

  it('reads a link back as an order and a view', async () => {
    fetchMock.mockResolvedValue(json({ order: ORDER, view: VIEW, expires_at: FUTURE }));
    const document = await fetchPermalink(ID);
    expect(fetchMock.mock.calls[0][0]).toBe(`/processing/permalinks/${ID}`);
    expect(document.order).toEqual(ORDER);
    expect(document.view).toEqual(VIEW);
  });

  it('does not ask for what cannot be an identifier, and takes no order that is none', async () => {
    await expect(fetchPermalink('../x')).rejects.toMatchObject({ status: 404, message: GONE_TEXT });
    expect(fetchMock).not.toHaveBeenCalled();
    fetchMock.mockResolvedValue(json({ order: { recipe_version: 2 }, view: VIEW, expires_at: FUTURE }));
    await expect(fetchPermalink(ID)).rejects.toThrow(/cannot read/u);
    fetchMock.mockResolvedValue(json({ order: ORDER, view: 'x', expires_at: FUTURE }));
    await expect(fetchPermalink(ID)).rejects.toThrow(/cannot read/u);
  });

  it('passes a 404 on as an HttpError', async () => {
    fetchMock.mockResolvedValue(json({ detail: 'there is no such permalink' }, 404));
    await expect(fetchPermalink(ID)).rejects.toBeInstanceOf(HttpError);
  });

  it('deletes with the key in a header and takes a 404 as done', async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await deletePermalink(ID, 'secret-key');
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'DELETE', headers: { 'X-Delete-Key': 'secret-key' } });
    fetchMock.mockResolvedValueOnce(json({ detail: 'no' }, 404));
    await expect(deletePermalink(ID, 'k')).resolves.toBeUndefined();
    fetchMock.mockResolvedValueOnce(json({ detail: 'down' }, 503));
    await expect(deletePermalink(ID, 'k')).rejects.toMatchObject({ status: 503 });
  });
});

describe('the keys of this browser', () => {
  it('are kept per link until the link expires', () => {
    rememberKey({ id: ID, expiresAt: FUTURE, deleteKey: 'a' });
    rememberKey({ id: OTHER, expiresAt: new Date(Date.now() - 1000).toISOString(), deleteKey: 'b' });
    expect(loadKeys()).toEqual({ [ID]: { key: 'a', expiresAt: FUTURE } });
    forgetKey(ID);
    expect(loadKeys()).toEqual({});
  });

  it.each(['not json', '[]', '{"x":{"key":"a","expiresAt":"2999-01-01"}}', `{"${ID}":{"key":1}}`, `{"${ID}":"a"}`])(
    'are none where the stored value is %s',
    (value) => {
      localStorage.setItem(KEYS_STORAGE, value);
      expect(loadKeys()).toEqual({});
    },
  );

  it('are none where the storage throws, and the link still comes out', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(loadKeys()).toEqual({});
    expect(() => rememberKey({ id: ID, expiresAt: FUTURE, deleteKey: 'a' })).not.toThrow();
    vi.restoreAllMocks();
  });

  it('delete a link with the stored key, and forget it only once the server has answered', async () => {
    rememberKey({ id: ID, expiresAt: FUTURE, deleteKey: 'a' });
    fetchMock.mockResolvedValueOnce(json({ detail: 'down' }, 503));
    await expect(removePermalink(ID)).rejects.toMatchObject({ status: 503 });
    expect(loadKeys()[ID]).toBeDefined();
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    expect(await removePermalink(ID)).toBe(true);
    expect(loadKeys()).toEqual({});
    expect(await removePermalink(ID)).toBe(false);
  });
});
