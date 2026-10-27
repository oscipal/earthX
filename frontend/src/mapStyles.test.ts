// @vitest-environment jsdom
//
// M3-10 (Otto, 30.09.2026): the backdrop behind the globe is a theme token —
// dark in the tech theme, white in the light one — not a fixed colour.

import type { StyleSpecification, TransformStyleFunction } from 'maplibre-gl';
import { afterEach, describe, expect, it, vi } from 'vitest';

import CSS from './index.css?raw';
import { BASEMAP_IDS, BASEMAPS, ESRI_ATTRIBUTION, OPENFREEMAP_ATTRIBUTION, type BasemapId } from './basemaps';
import { publishedStyle } from './fixtures/publishedStyle';
import {
  applyBasemap,
  applyMapBackground,
  applyProjection,
  ATTRIBUTION_CONTROL,
  baseMapStyle,
  composeStyle,
  createBasemapSwitcher,
  isInFirstStyle,
  mapBackgroundOf,
} from './mapStyles';

// The declarations of one theme's token block, e.g. `.app[data-theme='normal']`.
function tokenBlock(theme: string): string {
  const start = CSS.indexOf(`.app[data-theme='${theme}'] {`);
  expect(start).toBeGreaterThanOrEqual(0);
  return CSS.slice(start, CSS.indexOf('}', start));
}
function mapBg(block: string): string | null {
  return /--map-bg:\s*([^;]+);/.exec(block)?.[1].trim() ?? null;
}

describe('the map backdrop is a theme token', () => {
  it('is defined in both themes, dark in the tech one and white in the light one', () => {
    expect(mapBg(tokenBlock('tech'))).toMatch(/^#0[0-9a-f]{5}$/i);
    expect(mapBg(tokenBlock('normal'))?.toLowerCase()).toBe('#ffffff');
  });

  it('is what the app paints behind the map, and nothing paints a fixed dark colour there', () => {
    const app = CSS.slice(CSS.indexOf('.app {'), CSS.indexOf('}', CSS.indexOf('.app {')));
    expect(app).toContain('background: var(--map-bg)');
    const body = CSS.slice(CSS.indexOf('body {'), CSS.indexOf('}', CSS.indexOf('body {')));
    expect(body).not.toMatch(/background:\s*#/);
  });

  it('is read off the element that carries the theme', () => {
    const app = document.createElement('div');
    app.style.setProperty('--map-bg', ' #ffffff ');
    document.body.append(app);
    expect(mapBackgroundOf(app)).toBe('#ffffff');
    app.remove();
  });

  it('is undefined without an element or without the token', () => {
    expect(mapBackgroundOf(null)).toBeUndefined();
    expect(mapBackgroundOf(document.createElement('div'))).toBeUndefined();
  });
});

describe('baseMapStyle', () => {
  it('puts the colour into the background layer and the globe sky', () => {
    const style = baseMapStyle('#ffffff');
    const background = style.layers.find((l) => l.id === 'background');
    expect(background?.type === 'background' && background.paint?.['background-color']).toBe('#ffffff');
    expect(style.sky).toMatchObject({ 'sky-color': '#ffffff', 'horizon-color': '#ffffff', 'fog-color': '#ffffff', 'atmosphere-blend': 0 });
  });

  it('carries no colour of its own without a token colour', () => {
    const style = baseMapStyle();
    expect(style.sky).toBeUndefined();
    expect(JSON.stringify(style)).not.toMatch(/#04070a/i);
  });

  it('returns a fresh copy every time', () => {
    expect(baseMapStyle('#fff')).not.toBe(baseMapStyle('#fff'));
  });
});

describe('applyMapBackground', () => {
  it('re-tints the background layer and the sky of a running map', () => {
    const map = { getLayer: vi.fn(() => ({})), setPaintProperty: vi.fn(), setSky: vi.fn() };
    applyMapBackground(map, '#04070a');
    expect(map.setPaintProperty).toHaveBeenCalledWith('background', 'background-color', '#04070a');
    expect(map.setSky).toHaveBeenCalledWith(expect.objectContaining({ 'sky-color': '#04070a' }));
  });

  it('still sets the sky when the style has no background layer', () => {
    const map = { getLayer: vi.fn(() => undefined), setPaintProperty: vi.fn(), setSky: vi.fn() };
    applyMapBackground(map, '#ffffff');
    expect(map.setPaintProperty).not.toHaveBeenCalled();
    expect(map.setSky).toHaveBeenCalled();
  });
});

// --- the basemaps (UI-02a) -------------------------------------------------------------------------------------

const attributionsOf = (style: StyleSpecification): (string | undefined)[] =>
  Object.values(style.sources).map((source) => ('attribution' in source ? source.attribution : undefined));

// A map as the app has it running: the backdrop, a basemap, the app's own layers, and a globe with a sky.
function runningStyle(basemap: BasemapId = 'satellite'): StyleSpecification {
  const own: StyleSpecification = {
    version: 8,
    sources: {
      'aoi-src': { type: 'geojson', data: { type: 'FeatureCollection', features: [] } },
      'm-img-src-0': { type: 'image', url: 'data:image/png;base64,AAAA', coordinates: [[0, 1], [1, 1], [1, 0], [0, 0]] },
    },
    layers: [
      { id: 'layers-top', type: 'background', layout: { visibility: 'none' } },
      { id: 'm-img-lyr-0', type: 'raster', source: 'm-img-src-0' },
      { id: 'aoi-line', type: 'line', source: 'aoi-src' },
    ],
    sky: { 'sky-color': '#04070a' },
    projection: { type: 'globe' },
  };
  const base = baseMapStyle('#04070a', basemap);
  return { ...base, sources: { ...base.sources, ...own.sources }, layers: [...base.layers, ...own.layers], projection: own.projection };
}

const idsOf = (style: StyleSpecification): string[] => style.layers.map((layer) => layer.id);

describe('baseMapStyle with a basemap', () => {
  it('holds the satellite imagery by default, under the backdrop colour', () => {
    const style = baseMapStyle('#ffffff');
    expect(idsOf(style)).toEqual(['background', 'bm-satellite']);
    expect(Object.keys(style.sources)).toEqual(['bm-satellite']);
    expect(style.sky).toBeDefined();
  });

  it('holds the outlines in the first style, and no published style (it is fetched when applied)', () => {
    expect(idsOf(baseMapStyle('#fff', 'outlines'))).toEqual(['background', 'bm-water', 'bm-boundary-region', 'bm-boundary-country']);
    for (const id of ['streets', 'grey'] as const) {
      expect(isInFirstStyle(id)).toBe(false);
      expect(idsOf(baseMapStyle('#fff', id))).toEqual(['background']);
    }
    expect(isInFirstStyle('satellite') && isInFirstStyle('outlines')).toBe(true);
  });
});

describe('composeStyle', () => {
  it('puts the backdrop first, then the basemap, then everything of the app, in the app\'s order', () => {
    const style = composeStyle(runningStyle(), publishedStyle(), 'streets');
    expect(idsOf(style)).toEqual([
      'background',
      'bm-background',
      'bm-aoi-fill',
      'bm-place-label',
      'bm-photos',
      'layers-top',
      'm-img-lyr-0',
      'aoi-line',
    ]);
  });

  it('prefixes the sources of the basemap and the source each of its layers points at, so no id of the app is taken', () => {
    const style = composeStyle(runningStyle(), publishedStyle(), 'streets');
    expect(Object.keys(style.sources).sort()).toEqual(['aoi-src', 'bm-openmaptiles', 'bm-photos', 'm-img-src-0']);
    const layer = style.layers.find((l) => l.id === 'bm-aoi-fill');
    expect(layer && 'source' in layer && layer.source).toBe('bm-openmaptiles');
    // The layer "aoi-fill" of the published style does not collide with a layer of the app of that name.
    expect(idsOf(style).filter((id) => id.endsWith('aoi-fill'))).toEqual(['bm-aoi-fill']);
  });

  it('carries the app\'s sources over unchanged', () => {
    const before = runningStyle();
    const style = composeStyle(before, publishedStyle(), 'streets');
    expect(style.sources['aoi-src']).toEqual(before.sources['aoi-src']);
    expect(style.sources['m-img-src-0']).toEqual(before.sources['m-img-src-0']);
  });

  it('takes the projection and the sky from the running map, not from the published style', () => {
    const style = composeStyle(runningStyle(), publishedStyle(), 'grey');
    expect(style.projection).toEqual({ type: 'globe' });
    expect(style.sky).toEqual({ 'sky-color': '#04070a', 'horizon-color': '#04070a', 'fog-color': '#04070a', 'atmosphere-blend': 0 });
  });

  it('does not invent a projection, a sky, a light or a terrain the running map does not have', () => {
    const previous: StyleSpecification = { version: 8, sources: {}, layers: [{ id: 'background', type: 'background' }] };
    const style = composeStyle(previous, publishedStyle(), 'streets');
    expect('projection' in style || 'sky' in style || 'light' in style || 'terrain' in style).toBe(false);
  });

  it('replaces the former basemap completely when the basemap changes', () => {
    const streets = composeStyle(runningStyle(), publishedStyle(), 'streets');
    const satellite = composeStyle(streets, BASEMAPS.satellite.style as StyleSpecification, 'satellite');
    expect(idsOf(satellite)).toEqual(['background', 'bm-satellite', 'layers-top', 'm-img-lyr-0', 'aoi-line']);
    expect(Object.keys(satellite.sources).sort()).toEqual(['aoi-src', 'bm-satellite', 'm-img-src-0']);
  });

  it('gives a published style the glyphs and sprite of its own, and a style without them none', () => {
    const streets = composeStyle(runningStyle(), publishedStyle(), 'streets');
    expect(streets.glyphs).toContain('{fontstack}');
    expect(streets.sprite).toBe('https://styles.example/sprite');
    const satellite = composeStyle(streets, BASEMAPS.satellite.style as StyleSpecification, 'satellite');
    expect(satellite.glyphs).toBeUndefined();
    expect(satellite.sprite).toBeUndefined();
  });

  it('works for a first style without a running one, and for a published style that names no sources', () => {
    expect(idsOf(composeStyle(undefined, publishedStyle(), 'streets'))).toEqual(['bm-background', 'bm-aoi-fill', 'bm-place-label', 'bm-photos']);
    const bare = { version: 8, layers: [] } as unknown as StyleSpecification;
    expect(() => composeStyle(runningStyle(), bare, 'streets')).not.toThrow();
  });
});

describe('the attribution of each basemap', () => {
  const published = (): StyleSpecification => publishedStyle();
  const styleOf = (id: BasemapId): StyleSpecification => {
    const source = BASEMAPS[id].style;
    return typeof source === 'string' ? published() : source;
  };

  it.each(BASEMAP_IDS)('%s shows the attribution its provider asks for, and only that', (id) => {
    const style = composeStyle(runningStyle(), styleOf(id), id);
    const basemapSources = Object.entries(style.sources).filter(([key]) => key.startsWith('bm-'));
    const attributions = attributionsOf({ ...style, sources: Object.fromEntries(basemapSources) }).filter(Boolean);
    if (id === 'satellite') expect(attributions).toEqual([ESRI_ATTRIBUTION]);
    else if (id === 'outlines') expect(attributions).toEqual([OPENFREEMAP_ATTRIBUTION]);
    // A published style: the wording OpenFreeMap asks for on its vector source; the raster source of its own stays.
    else expect(attributions).toEqual([OPENFREEMAP_ATTRIBUTION, 'a raster source of its own']);
  });

  it('names OpenFreeMap, OpenMapTiles and OpenStreetMap, each with its link', () => {
    for (const name of ['OpenFreeMap', 'OpenMapTiles', 'OpenStreetMap']) expect(OPENFREEMAP_ATTRIBUTION).toContain(name);
    expect(OPENFREEMAP_ATTRIBUTION).toContain('https://www.openstreetmap.org/copyright');
  });

  it('is not left on a basemap that was replaced', () => {
    const streets = composeStyle(runningStyle(), published(), 'streets');
    const satellite = composeStyle(streets, BASEMAPS.satellite.style as StyleSpecification, 'satellite');
    expect(attributionsOf(satellite).filter(Boolean)).toEqual([ESRI_ATTRIBUTION]);
  });

  it('stays open: the control is not made compact (OSMF, Otto 27.10.2026)', () => {
    expect(ATTRIBUTION_CONTROL).toEqual({ compact: false });
  });
});

// A map that records what `applyBasemap` hands it.
function recordingMap() {
  const calls: { style: StyleSpecification; diff: boolean; transform: TransformStyleFunction }[] = [];
  return {
    calls,
    map: {
      setStyle: vi.fn((style: StyleSpecification, options: { diff: boolean; transformStyle: TransformStyleFunction }) => {
        calls.push({ style, diff: options.diff, transform: options.transformStyle });
      }),
    },
  };
}

const jsonAnswer = (status: number, body: unknown): Response =>
  ({ ok: status >= 200 && status < 300, status, json: async () => body }) as Response;

describe('applyBasemap', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it.each(['satellite', 'outlines'] as const)('hands the map the %s style at once, as a diff that keeps the app\'s layers', async (id) => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const { map, calls } = recordingMap();
    expect(await applyBasemap(map, id)).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(calls).toHaveLength(1);
    expect(calls[0].diff).toBe(true);
    const composed = calls[0].transform(runningStyle(), calls[0].style);
    expect(idsOf(composed)).toContain('aoi-line');
    expect(idsOf(composed).some((layer) => layer.startsWith('bm-'))).toBe(true);
    expect(composed.projection).toEqual({ type: 'globe' });
  });

  it.each(['streets', 'grey'] as const)('fetches the published style of %s and hands it over', async (id) => {
    const fetchSpy = vi.fn(async () => jsonAnswer(200, publishedStyle()));
    vi.stubGlobal('fetch', fetchSpy);
    const { map, calls } = recordingMap();
    expect(await applyBasemap(map, id)).toBe(true);
    expect(fetchSpy).toHaveBeenCalledWith(BASEMAPS[id].style);
    expect(calls).toHaveLength(1);
    const composed = calls[0].transform(runningStyle(), calls[0].style);
    expect(attributionsOf(composed)).toContain(OPENFREEMAP_ATTRIBUTION);
    expect(idsOf(composed)).toContain('m-img-lyr-0');
  });

  it.each([
    ['the server answers with an error', () => jsonAnswer(503, {}), /answered 503/u],
    ['the answer is not a style', () => jsonAnswer(200, { hello: 'world' }), /not a map style/u],
    ['the answer is a list', () => jsonAnswer(200, []), /not a map style/u],
    ['the style is of another version', () => jsonAnswer(200, { version: 7, layers: [] }), /not a map style/u],
    ['the style has no layers', () => jsonAnswer(200, { version: 8 }), /not a map style/u],
    ['the answer is not JSON', () => ({ ok: true, status: 200, json: async () => Promise.reject(new SyntaxError('Unexpected token <')) }) as unknown as Response, /Unexpected token/u],
  ])('keeps the map as it is and says so when %s', async (_name, answer, reason) => {
    vi.stubGlobal('fetch', vi.fn(async () => answer()));
    const { map } = recordingMap();
    const onError = vi.fn();
    expect(await applyBasemap(map, 'streets', onError)).toBe(false);
    expect(map.setStyle).not.toHaveBeenCalled();
    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toMatch(/^The Streets basemap could not be loaded: /u);
    expect(onError.mock.calls[0][0]).toMatch(reason);
  });

  it('keeps the map as it is and says so when the network is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    const { map } = recordingMap();
    const onError = vi.fn();
    expect(await applyBasemap(map, 'grey', onError)).toBe(false);
    expect(onError).toHaveBeenCalledWith('The Grey basemap could not be loaded: Failed to fetch.');
  });

  it('drops an answer that arrives after a newer choice, without an error', async () => {
    let answerStreets: (response: Response) => void = () => {};
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) =>
        url === BASEMAPS.streets.style ? new Promise<Response>((resolve) => (answerStreets = resolve)) : jsonAnswer(200, publishedStyle()),
      ),
    );
    const { map, calls } = recordingMap();
    const onError = vi.fn();
    const streets = applyBasemap(map, 'streets', onError);
    const grey = applyBasemap(map, 'grey', onError);
    expect(await grey).toBe(true);
    answerStreets(jsonAnswer(200, publishedStyle()));
    expect(await streets).toBe(false);
    expect(calls).toHaveLength(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it('drops a published style that is still on its way when a local basemap is chosen', async () => {
    let answer: (response: Response) => void = () => {};
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => (answer = resolve))));
    const { map, calls } = recordingMap();
    const streets = applyBasemap(map, 'streets');
    expect(await applyBasemap(map, 'satellite')).toBe(true);
    answer(jsonAnswer(200, publishedStyle()));
    expect(await streets).toBe(false);
    expect(calls).toHaveLength(1);
    expect(calls[0].style.name).toBe('satellite');
  });
});

describe('applyProjection', () => {
  it.each(['mercator', 'globe'] as const)('sets %s on the map', (projection) => {
    const map = { setProjection: vi.fn() };
    applyProjection(map, projection);
    expect(map.setProjection).toHaveBeenCalledWith({ type: projection });
  });
});

describe('createBasemapSwitcher', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('applies a basemap once, however often it is asked for', async () => {
    const { map } = recordingMap();
    const switcher = createBasemapSwitcher(map, 'satellite', vi.fn());
    switcher.show('satellite');
    switcher.show('outlines');
    switcher.show('outlines');
    await settle();
    expect(map.setStyle).toHaveBeenCalledTimes(1);
  });

  it('applies a published style when the first style holds none', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonAnswer(200, publishedStyle())));
    const { map } = recordingMap();
    createBasemapSwitcher(map, null, vi.fn()).show('streets');
    await settle();
    expect(map.setStyle).toHaveBeenCalledTimes(1);
  });

  it('takes a failed choice back to what the map shows, and tells why', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonAnswer(503, {})));
    const { map } = recordingMap();
    const onFailure = vi.fn();
    const switcher = createBasemapSwitcher(map, 'satellite', onFailure);
    switcher.show('grey');
    await settle();
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure.mock.calls[0][0]).toMatch(/^The Grey basemap could not be loaded/u);
    expect(onFailure.mock.calls[0][1]).toBe('satellite');
    expect(map.setStyle).not.toHaveBeenCalled();
    // Asked for again (a second try), it is tried again.
    switcher.show('grey');
    await settle();
    expect(onFailure).toHaveBeenCalledTimes(2);
  });

  it('says there is nothing to keep when the first published style fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    const { map } = recordingMap();
    const onFailure = vi.fn();
    createBasemapSwitcher(map, null, onFailure).show('streets');
    await settle();
    expect(onFailure).toHaveBeenCalledWith(expect.stringContaining('Failed to fetch'), null);
  });

  it('goes back to the basemap that was handed over, not to one that was only asked for', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => (url === BASEMAPS.grey.style ? jsonAnswer(500, {}) : jsonAnswer(200, publishedStyle()))));
    const { map } = recordingMap();
    const onFailure = vi.fn();
    const switcher = createBasemapSwitcher(map, 'satellite', onFailure);
    switcher.show('streets');
    switcher.show('grey');
    await settle();
    // `streets` was overtaken and never reached the map, so what the map shows is still the satellite imagery.
    expect(onFailure).toHaveBeenCalledWith(expect.any(String), 'satellite');
    expect(map.setStyle).not.toHaveBeenCalled();
  });
});
