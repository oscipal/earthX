// @vitest-environment jsdom
//
// UI-02b: the overlays "Labels" and "Graticule" on the map. Where they lie among the app's layers (over every picture,
// under the area of interest and the drawing, on every basemap), what they cost the map when they are switched (a few
// commands on their own ids, no rebuild), where the names of a basemap without names come from, and who is credited.

import { diff } from '@maplibre/maplibre-gl-style-spec';
import type { StyleSpecification, TransformStyleFunction } from 'maplibre-gl';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { BASEMAP_IDS, BASEMAPS, ESRI_ATTRIBUTION, OPENFREEMAP_ATTRIBUTION, type BasemapId } from './basemaps';
import { appLayers, publishedStyle } from './fixtures/publishedStyle';
import { applyBasemap, baseMapStyle, composeStyle, createBasemapSwitcher, forgetPublishedStyles } from './mapStyles';
import { NO_OVERLAYS, OVERLAY_PREFIX, type Overlays } from './overlays';

const LABELS: Overlays = { labels: true, graticule: false };
const GRATICULE: Overlays = { labels: false, graticule: true };
const BOTH: Overlays = { labels: true, graticule: true };

const idsOf = (style: StyleSpecification): string[] => style.layers.map((layer) => layer.id);
const overlayIds = (style: StyleSpecification): string[] => idsOf(style).filter((id) => id.startsWith(OVERLAY_PREFIX));
const layer = (style: StyleSpecification, id: string) => style.layers.find((l) => l.id === id);

// The style of Grey as a style server publishes it (made up): a label layer on the vector tiles that Outlines draws as well.
function greyStyle(): StyleSpecification {
  const style = publishedStyle();
  // The credit is in the TileJSON, not in the style.
  const tiles = (BASEMAPS.outlines.style as StyleSpecification).sources.openmaptiles;
  style.sources.openmaptiles = { type: 'vector', url: tiles.type === 'vector' ? tiles.url : undefined };
  return style;
}

// A made-up published style, with the layers of the basemap `id`.
function styleOf(id: BasemapId): StyleSpecification {
  const source = BASEMAPS[id].style;
  return typeof source === 'string' ? publishedStyle() : source;
}

// The map as it runs with `id` and `overlays`: the first style, the app's layers laid, the globe set.
function running(id: BasemapId, overlays: Overlays = NO_OVERLAYS): StyleSpecification {
  const base = baseMapStyle('#04070a', 'satellite');
  const own = appLayers();
  const first: StyleSpecification = { ...base, sources: { ...base.sources, ...own.sources }, layers: [...base.layers, ...own.layers], projection: own.projection };
  return composeStyle(first, styleOf(id), id, overlays, greyStyle());
}

describe('where the overlays lie', () => {
  it.each(BASEMAP_IDS)('%s: over every picture of the app, under the area of interest and the drawing, over the basemap', (id) => {
    const style = running(id, BOTH);
    const ids = idsOf(style);
    const at = (name: string) => ids.indexOf(name);
    const overlays = overlayIds(style);
    expect(overlays.length).toBeGreaterThan(4);
    for (const name of overlays) {
      expect(at(name)).toBeGreaterThan(at('m-img-lyr-0'));
      expect(at(name)).toBeGreaterThan(at('overlays-base'));
      expect(at(name)).toBeLessThan(at('aoi-fill'));
      expect(at(name)).toBeLessThan(at('aoi-line'));
      expect(at(name)).toBeLessThan(at('td-polygon'));
      expect(at(name)).toBeGreaterThan(Math.max(...ids.filter((other) => other.startsWith('bm-')).map((other) => at(other))));
    }
  });

  it('puts the graticule under the names', () => {
    const ids = idsOf(running('streets', BOTH));
    expect(ids.indexOf('ov-graticule-1')).toBeLessThan(ids.indexOf('ov-place-label'));
  });

  it('keeps the app\'s own layers in their order and takes nothing from them', () => {
    const own = (style: StyleSpecification) => idsOf(style).filter((id) => id !== 'background' && !id.startsWith('bm-') && !id.startsWith(OVERLAY_PREFIX));
    expect(own(running('streets', BOTH))).toEqual(own(running('satellite')));
  });

  it('goes at the end where there is no area of interest to lie under (a map without the app\'s layers)', () => {
    const previous: StyleSpecification = { version: 8, sources: {}, layers: [{ id: 'background', type: 'background' }, { id: 'm-img-lyr-0', type: 'raster', source: 'x' }] };
    const ids = idsOf(composeStyle(previous, publishedStyle(), 'streets', BOTH));
    expect(ids.slice(-6)).toEqual(['m-img-lyr-0', 'ov-graticule-30', 'ov-graticule-10', 'ov-graticule-5', 'ov-graticule-1', 'ov-place-label']);
  });

  it('is laid once, however often it is composed on the result', () => {
    const once = running('streets', BOTH);
    const twice = composeStyle(once, styleOf('streets'), 'streets', BOTH, greyStyle());
    expect(idsOf(twice)).toEqual(idsOf(once));
    expect(Object.keys(twice.sources).sort()).toEqual(Object.keys(once.sources).sort());
  });
});

describe('Labels', () => {
  it('are the symbol layers of a basemap that has some, over the app\'s pictures and shown when Labels is on', () => {
    const style = running('streets', LABELS);
    expect(layer(style, 'ov-place-label')?.layout?.visibility).toBeUndefined();
    expect(layer(style, 'bm-place-label')).toBeUndefined();
    expect(layer(style, 'ov-place-label')).toMatchObject({ type: 'symbol', source: 'bm-openmaptiles' });
  });

  it('are hidden, not dropped, when Labels is off', () => {
    const style = running('streets');
    expect(layer(style, 'ov-place-label')?.layout?.visibility).toBe('none');
  });

  it('keep the visibility a published layer has of its own when Labels is on', () => {
    const published = publishedStyle();
    published.layers.push({ id: 'poi', type: 'symbol', source: 'openmaptiles', 'source-layer': 'poi', layout: { visibility: 'none' } });
    expect(layer(composeStyle(running('satellite'), published, 'streets', LABELS), 'ov-poi')?.layout?.visibility).toBe('none');
  });

  it('are not forced on a basemap that has names: Streets and Grey take no names from elsewhere', () => {
    for (const id of ['streets', 'grey'] as const) {
      const style = running(id, LABELS);
      expect(idsOf(style).filter((name) => name.includes('labels-'))).toEqual([]);
      expect(Object.keys(style.sources).filter((key) => key.includes('labels-'))).toEqual([]);
    }
  });

  it.each(['satellite', 'outlines'] as const)('%s has none of its own: it takes the names of Grey when Labels is on, with their glyphs and sprite', (id) => {
    const style = running(id, LABELS);
    // Over Outlines the names use its own tiles; over the satellite imagery they bring a source of their own.
    expect(layer(style, 'ov-labels-place-label')).toMatchObject({ type: 'symbol', source: id === 'outlines' ? 'bm-openmaptiles' : 'bm-labels-openmaptiles' });
    expect(style.glyphs).toBe('https://styles.example/fonts/{fontstack}/{range}.pbf');
    expect(style.sprite).toBe('https://styles.example/sprite');
    expect(layer(style, 'ov-labels-place-label')?.layout?.visibility).toBeUndefined();
  });

  it.each(['satellite', 'outlines'] as const)('%s asks nobody for names and loads no vector tiles while Labels is off', (id) => {
    const style = running(id);
    expect(overlayIds(style)).toEqual([]);
    expect(Object.keys(style.sources).filter((key) => key.includes('labels'))).toEqual([]);
    expect(style.glyphs).toBeUndefined();
    if (id === 'satellite') expect(Object.values(style.sources).some((source) => source.type === 'vector')).toBe(false);
  });

  it('use the tiles Outlines already has, not a second copy of them', () => {
    const outlines = BASEMAPS.outlines.style as StyleSpecification;
    const style = composeStyle(running('outlines'), outlines, 'outlines', LABELS, greyStyle());
    expect(layer(style, 'ov-labels-place-label')).toMatchObject({ source: 'bm-openmaptiles' });
    expect(Object.keys(style.sources).filter((key) => key.startsWith('bm-'))).toEqual(['bm-openmaptiles']);
  });

  it('are left out where the style of Grey has no names, or has not been fetched', () => {
    const none = greyStyle();
    none.layers = none.layers.filter((l) => l.type !== 'symbol');
    expect(overlayIds(composeStyle(running('satellite'), styleOf('satellite'), 'satellite', LABELS, none))).toEqual([]);
    expect(overlayIds(composeStyle(running('satellite'), styleOf('satellite'), 'satellite', LABELS))).toEqual([]);
    const bare = { version: 8, layers: [] } as unknown as StyleSpecification;
    expect(() => composeStyle(running('satellite'), styleOf('satellite'), 'satellite', LABELS, bare)).not.toThrow();
  });
});

describe('Graticule', () => {
  it('is one GeoJSON source and four line layers, on every basemap', () => {
    for (const id of BASEMAP_IDS) {
      const style = running(id, GRATICULE);
      expect(style.sources['ov-graticule']).toMatchObject({ type: 'geojson' });
      expect(overlayIds(style).filter((name) => name.startsWith('ov-graticule-'))).toHaveLength(4);
    }
  });

  it('draws no label (that would need the glyphs of a third party)', () => {
    const style = running('satellite', GRATICULE);
    expect(style.layers.filter((l) => l.type === 'symbol')).toEqual([]);
    expect(style.glyphs).toBeUndefined();
  });

  it('is gone with the switch, source and layers', () => {
    const style = composeStyle(running('satellite', GRATICULE), styleOf('satellite'), 'satellite', NO_OVERLAYS);
    expect(overlayIds(style)).toEqual([]);
    expect(style.sources['ov-graticule']).toBeUndefined();
  });
});

describe('the attribution with the overlays', () => {
  const attributions = (style: StyleSpecification) =>
    Object.entries(style.sources)
      .filter(([key]) => key.startsWith('bm-'))
      .map(([, source]) => ('attribution' in source ? source.attribution : undefined))
      .filter(Boolean);

  it('credits OpenMapTiles, OpenFreeMap and OpenStreetMap over the satellite imagery once Labels is on, and Esri still', () => {
    expect(attributions(running('satellite', LABELS))).toEqual([ESRI_ATTRIBUTION, OPENFREEMAP_ATTRIBUTION]);
  });

  it('credits nobody but Esri over the satellite imagery without Labels, and with the graticule', () => {
    expect(attributions(running('satellite'))).toEqual([ESRI_ATTRIBUTION]);
    expect(attributions(running('satellite', GRATICULE))).toEqual([ESRI_ATTRIBUTION]);
  });

  it.each(['streets', 'grey', 'outlines'] as const)('%s credits OpenFreeMap once, with or without the overlays', (id) => {
    // A published style keeps the credit of the raster source of its own beside it.
    const expected = id === 'outlines' ? [OPENFREEMAP_ATTRIBUTION] : [OPENFREEMAP_ATTRIBUTION, 'a raster source of its own'];
    for (const overlays of [NO_OVERLAYS, LABELS, BOTH]) expect(attributions(running(id, overlays))).toEqual(expected);
  });

  it('drops the credit with the names, so that nobody is credited who is not shown', () => {
    const style = composeStyle(running('satellite', LABELS), styleOf('satellite'), 'satellite', NO_OVERLAYS, greyStyle());
    expect(attributions(style)).toEqual([ESRI_ATTRIBUTION]);
  });
});

// --- what a switch costs the map ---------------------------------------------------------------------------------

const ALLOWED = new Set(['addSource', 'removeSource', 'addLayer', 'removeLayer', 'setGlyphs', 'setSprite', 'setPaintProperty', 'setLayoutProperty', 'setFilter', 'setLayerZoomRange']);
const ON_AN_ID = /^(add|remove)(Source|Layer)$|^set(PaintProperty|LayoutProperty|Filter|LayerZoomRange)$/u;
const idOf = (command: { args: unknown[] }): string => {
  const [first] = command.args;
  return typeof first === 'string' ? first : (first as { id: string }).id;
};

const switches: [string, Overlays, Overlays][] = [
  ['Labels on', NO_OVERLAYS, LABELS],
  ['Labels off', LABELS, NO_OVERLAYS],
  ['Graticule on', NO_OVERLAYS, GRATICULE],
  ['Graticule off', GRATICULE, NO_OVERLAYS],
  ['both on', NO_OVERLAYS, BOTH],
  ['Graticule on beside Labels', LABELS, BOTH],
];

describe('the style diff of a switch', () => {
  it.each(BASEMAP_IDS.flatMap((id) => switches.map(([name, from, to]) => [id, name, from, to] as const)))(
    '%s, %s: only commands on the ids of the basemap and the overlays, none that rebuild the map',
    (id, _name, from, to) => {
      const previous = running(id, from);
      const next = composeStyle(previous, styleOf(id), id, to, greyStyle());
      const commands = diff(previous, next);
      expect(commands.length).toBeGreaterThan(0);
      expect(commands.map((c) => c.command).filter((name) => !ALLOWED.has(name))).toEqual([]);
      for (const command of commands.filter((c) => ON_AN_ID.test(c.command))) {
        const name = idOf(command);
        expect(name.startsWith('bm-') || name.startsWith(OVERLAY_PREFIX)).toBe(true);
      }
      expect(next.projection).toEqual(previous.projection);
      expect(next.sky).toEqual(previous.sky);
    },
  );

  it.each(['streets', 'grey'] as const)('%s: Labels is a change of the visibility of its names, nothing is added or removed', (id) => {
    for (const [from, to] of [[NO_OVERLAYS, LABELS], [LABELS, NO_OVERLAYS]]) {
      const commands = diff(running(id, from), composeStyle(running(id, from), styleOf(id), id, to, greyStyle()));
      expect(commands.length).toBeGreaterThan(0);
      expect(new Set(commands.map((c) => c.command))).toEqual(new Set(['setLayoutProperty']));
    }
  });

  it.each(BASEMAP_IDS)('%s: the same overlays again change nothing', (id) => {
    const previous = running(id, BOTH);
    expect(diff(previous, composeStyle(previous, styleOf(id), id, BOTH, greyStyle()))).toEqual([]);
  });

  it('a change of the basemap with the overlays on takes the overlays along', () => {
    const previous = running('streets', BOTH);
    const next = composeStyle(previous, styleOf('satellite'), 'satellite', BOTH, greyStyle());
    expect(overlayIds(next)).toContain('ov-graticule-1');
    expect(overlayIds(next)).toContain('ov-labels-place-label');
    expect(overlayIds(next)).not.toContain('ov-place-label');
    expect(diff(previous, next).map((c) => c.command).filter((name) => !ALLOWED.has(name))).toEqual([]);
  });
});

// --- fetching and switching --------------------------------------------------------------------------------------

function recordingMap() {
  const calls: { style: StyleSpecification; transform: TransformStyleFunction }[] = [];
  return {
    calls,
    map: { setStyle: vi.fn((style: StyleSpecification, options: { transformStyle: TransformStyleFunction }) => void calls.push({ style, transform: options.transformStyle })) },
  };
}
const jsonAnswer = (status: number, body: unknown): Response => ({ ok: status >= 200 && status < 300, status, json: async () => body }) as Response;
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe('applyBasemap with the overlays', () => {
  beforeEach(forgetPublishedStyles);
  afterEach(() => vi.unstubAllGlobals());

  it('fetches the style of Grey for the names over the satellite imagery, and for nothing else', async () => {
    const fetchSpy = vi.fn(async () => jsonAnswer(200, greyStyle()));
    vi.stubGlobal('fetch', fetchSpy);
    const { map, calls } = recordingMap();
    expect(await applyBasemap(map, 'satellite', vi.fn(), LABELS)).toBe(true);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchSpy).toHaveBeenCalledWith(BASEMAPS.grey.style);
    expect(overlayIds(calls[0].transform(running('satellite'), calls[0].style))).toEqual(['ov-labels-place-label']);
    await applyBasemap(map, 'satellite', vi.fn(), GRATICULE);
    await applyBasemap(map, 'outlines', vi.fn());
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('does not fetch the names for a basemap that has them (Streets asks for its own style only)', async () => {
    const fetchSpy = vi.fn(async () => jsonAnswer(200, greyStyle()));
    vi.stubGlobal('fetch', fetchSpy);
    expect(await applyBasemap(recordingMap().map, 'streets', vi.fn(), LABELS)).toBe(true);
    expect(fetchSpy.mock.calls).toEqual([[BASEMAPS.streets.style]]);
  });

  it('asks the style server once for a published style, however often the overlays change', async () => {
    const fetchSpy = vi.fn(async () => jsonAnswer(200, greyStyle()));
    vi.stubGlobal('fetch', fetchSpy);
    const { map } = recordingMap();
    for (const overlays of [NO_OVERLAYS, LABELS, BOTH, GRATICULE]) await applyBasemap(map, 'streets', vi.fn(), overlays);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('does not keep a failed answer: the next try asks again', async () => {
    const fetchSpy = vi.fn().mockResolvedValueOnce(jsonAnswer(503, {})).mockResolvedValueOnce(jsonAnswer(200, greyStyle()));
    vi.stubGlobal('fetch', fetchSpy);
    const { map } = recordingMap();
    expect(await applyBasemap(map, 'streets', vi.fn())).toBe(false);
    expect(await applyBasemap(map, 'streets', vi.fn())).toBe(true);
  });

  it('says it was the labels that could not be loaded, and leaves the map as it is', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonAnswer(503, {})));
    const { map } = recordingMap();
    const onError = vi.fn();
    expect(await applyBasemap(map, 'satellite', onError, LABELS)).toBe(false);
    expect(onError).toHaveBeenCalledWith('The labels could not be loaded: the style server answered 503.');
    expect(map.setStyle).not.toHaveBeenCalled();
  });

  it('puts the satellite imagery under the overlays that need nothing from a third party at once', async () => {
    const fetchSpy = vi.fn();
    vi.stubGlobal('fetch', fetchSpy);
    const { map, calls } = recordingMap();
    expect(await applyBasemap(map, 'satellite', vi.fn(), GRATICULE)).toBe(true);
    expect(fetchSpy).not.toHaveBeenCalled();
    expect(overlayIds(calls[0].transform(running('satellite'), calls[0].style)).length).toBe(4);
  });
});

describe('createBasemapSwitcher with the overlays', () => {
  beforeEach(forgetPublishedStyles);
  afterEach(() => vi.unstubAllGlobals());

  it('applies a change of an overlay once, however often it is asked for, and leaves the same look alone', async () => {
    const { map } = recordingMap();
    const switcher = createBasemapSwitcher(map, 'satellite', vi.fn());
    switcher.show('satellite', NO_OVERLAYS);
    switcher.show('satellite', GRATICULE);
    switcher.show('satellite', { ...GRATICULE });
    await settle();
    expect(map.setStyle).toHaveBeenCalledTimes(1);
    // A choice that is overtaken before it reaches the map never does.
    switcher.show('satellite', NO_OVERLAYS);
    switcher.show('satellite', BOTH);
    await settle();
    expect(map.setStyle).toHaveBeenCalledTimes(2);
  });

  it('takes a failed Labels back to the overlays the map shows, and tells why', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonAnswer(503, {})));
    const { map } = recordingMap();
    const onFailure = vi.fn();
    const switcher = createBasemapSwitcher(map, 'satellite', onFailure);
    switcher.show('satellite', GRATICULE);
    await settle();
    switcher.show('satellite', BOTH);
    await settle();
    expect(onFailure).toHaveBeenCalledTimes(1);
    expect(onFailure).toHaveBeenCalledWith(expect.stringMatching(/^The labels could not be loaded/u), 'satellite', GRATICULE);
  });

  it('says there are no overlays to keep when the first published style fails', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => Promise.reject(new TypeError('Failed to fetch'))));
    const { map } = recordingMap();
    const onFailure = vi.fn();
    createBasemapSwitcher(map, null, onFailure).show('streets', BOTH);
    await settle();
    expect(onFailure).toHaveBeenCalledWith(expect.stringContaining('Failed to fetch'), null, NO_OVERLAYS);
  });

  it('applies a basemap with the overlays that were asked for with it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => jsonAnswer(200, greyStyle())));
    const { map, calls } = recordingMap();
    createBasemapSwitcher(map, null, vi.fn()).show('streets', BOTH);
    await settle();
    expect(overlayIds(calls[0].transform(running('satellite'), calls[0].style))).toContain('ov-graticule-30');
  });
});
