// @vitest-environment jsdom
//
// NM4-35: the terrain shading on the map, as the overlay "Relief" over every basemap (it is no basemap since UI-04 part 4).
// Where it lies among the app's layers (over the basemap, under every picture, so under the names and the graticule),
// what switching it costs the map, and who is credited.

import { diff } from '@maplibre/maplibre-gl-style-spec';
import type { StyleSpecification } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';

import { BASEMAP_IDS, BASEMAPS, ESRI_ATTRIBUTION, OPENFREEMAP_ATTRIBUTION, type BasemapId } from './basemaps';
import { appLayers, publishedStyle } from './fixtures/publishedStyle';
import { baseMapStyle, composeStyle } from './mapStyles';
import { NO_OVERLAYS, type Overlays } from './overlays';
import { RELIEF_OVERLAY_ID, TERRAIN_ATTRIBUTION } from './relief';

const RELIEF: Overlays = { ...NO_OVERLAYS, relief: true };
const ALL: Overlays = { labels: true, graticule: true, relief: true };

const idsOf = (style: StyleSpecification): string[] => style.layers.map((layer) => layer.id);
const layer = (style: StyleSpecification, id: string) => style.layers.find((l) => l.id === id);

function greyStyle(): StyleSpecification {
  const style = publishedStyle();
  const tiles = (BASEMAPS.outlines.style as StyleSpecification).sources.openmaptiles;
  style.sources.openmaptiles = { type: 'vector', url: tiles.type === 'vector' ? tiles.url : undefined };
  return style;
}

const styleOf = (id: BasemapId): StyleSpecification => {
  const source = BASEMAPS[id].style;
  return typeof source === 'string' ? publishedStyle() : source;
};

// The map as it runs with `id` and `overlays`: the first style, the app's layers laid, the globe set.
function running(id: BasemapId, overlays: Overlays = NO_OVERLAYS): StyleSpecification {
  const base = baseMapStyle('#04070a', 'satellite');
  const own = appLayers();
  const first: StyleSpecification = { ...base, sources: { ...base.sources, ...own.sources }, layers: [...base.layers, ...own.layers], projection: own.projection };
  return composeStyle(first, styleOf(id), id, overlays, greyStyle());
}

const attributions = (style: StyleSpecification): string[] =>
  Object.entries(style.sources)
    .map(([, source]) => ('attribution' in source ? source.attribution : undefined))
    .filter((text): text is string => Boolean(text));

describe('the overlay "Relief"', () => {
  it.each(BASEMAP_IDS)('%s: lies over the basemap and under every picture and layer of the app', (id) => {
    const ids = idsOf(running(id, RELIEF));
    const at = (name: string) => ids.indexOf(name);
    expect(at(RELIEF_OVERLAY_ID)).toBeGreaterThan(Math.max(...ids.filter((other) => other.startsWith('bm-')).map(at)));
    for (const own of ids.filter((other) => !other.startsWith('bm-') && !other.startsWith('ov-') && other !== 'background')) {
      expect(at(RELIEF_OVERLAY_ID)).toBeLessThan(at(own));
    }
    expect(at(RELIEF_OVERLAY_ID)).toBeGreaterThan(at('background'));
  });

  it('lies under the names and the graticule, which lie over the pictures (Otto, 27.10.2026)', () => {
    const ids = idsOf(running('satellite', ALL));
    const at = (name: string) => ids.indexOf(name);
    for (const over of ids.filter((name) => name.startsWith('ov-') && name !== RELIEF_OVERLAY_ID)) {
      expect(at(RELIEF_OVERLAY_ID)).toBeLessThan(at('m-img-lyr-0'));
      expect(at(RELIEF_OVERLAY_ID)).toBeLessThan(at(over));
    }
    expect(ids.filter((name) => name === RELIEF_OVERLAY_ID)).toHaveLength(1);
  });

  it('is a hillshade of a raster-dem source of its own, with the overlay look', () => {
    const style = running('streets', RELIEF);
    expect(layer(style, RELIEF_OVERLAY_ID)).toMatchObject({ type: 'hillshade', source: RELIEF_OVERLAY_ID });
    expect(style.sources[RELIEF_OVERLAY_ID]).toMatchObject({ type: 'raster-dem', encoding: 'terrarium', maxzoom: 12 });
    expect(layer(style, RELIEF_OVERLAY_ID)).toMatchObject({ paint: { 'hillshade-exaggeration': 0.5 } });
  });

  it.each(BASEMAP_IDS)('%s: no overlay is in the style while it is off', (id) => {
    const style = running(id);
    expect(layer(style, RELIEF_OVERLAY_ID)).toBeUndefined();
    expect(style.sources[RELIEF_OVERLAY_ID]).toBeUndefined();
    expect(attributions(style).includes(TERRAIN_ATTRIBUTION)).toBe(false);
  });

  it('keeps the app\'s layers where they were, in their order', () => {
    const own = (style: StyleSpecification) => idsOf(style).filter((name) => !name.startsWith('bm-') && !name.startsWith('ov-'));
    expect(own(running('satellite', RELIEF))).toEqual(own(running('satellite')));
  });
});

describe('who is credited for the terrain', () => {
  it('the overlay adds the credit to that of the basemap, once, over every basemap', () => {
    expect(attributions(running('satellite', RELIEF))).toEqual([ESRI_ATTRIBUTION, TERRAIN_ATTRIBUTION]);
    expect(attributions(running('outlines', RELIEF))).toEqual([OPENFREEMAP_ATTRIBUTION, TERRAIN_ATTRIBUTION]);
  });

  it('is dropped with the overlay, so that nobody is credited who is not shown', () => {
    const on = running('satellite', RELIEF);
    const off = composeStyle(on, styleOf('satellite'), 'satellite', NO_OVERLAYS, greyStyle());
    expect(attributions(off)).toEqual([ESRI_ATTRIBUTION]);
  });
});

// --- what a switch costs the map ---------------------------------------------------------------------------------

const ALLOWED = new Set(['addSource', 'removeSource', 'addLayer', 'removeLayer', 'setGlyphs', 'setSprite', 'setPaintProperty', 'setLayoutProperty', 'setFilter', 'setLayerZoomRange']);
const ON_AN_ID = /^(add|remove)(Source|Layer)$|^set(PaintProperty|LayoutProperty|Filter|LayerZoomRange)$/u;
const idOf = (command: { args: unknown[] }): string => {
  const [first] = command.args;
  return typeof first === 'string' ? first : (first as { id: string }).id;
};

describe('switching the relief', () => {
  it.each(BASEMAP_IDS)('%s: the overlay on and off is a few commands on its own ids, none that rebuild the map', (id) => {
    const off = running(id);
    const on = running(id, RELIEF);
    for (const [from, to] of [[off, on], [on, off]]) {
      const commands = diff(from, to);
      expect(commands.length).toBeGreaterThan(0);
      expect(commands.map((c) => c.command).filter((name) => !ALLOWED.has(name))).toEqual([]);
      expect(new Set(commands.map(idOf))).toEqual(new Set([RELIEF_OVERLAY_ID]));
      expect(to.projection).toEqual(from.projection);
      expect(to.sky).toEqual(from.sky);
    }
  });

  it.each(BASEMAP_IDS)('%s: a change of the basemap with the overlay on keeps the overlay and touches only the basemaps\' own ids', (id) => {
    const previous = running(id, RELIEF);
    for (const next of BASEMAP_IDS.filter((other) => other !== id).map((other) => composeStyle(previous, styleOf(other), other, RELIEF, greyStyle()))) {
      expect(layer(next, RELIEF_OVERLAY_ID)).toBeDefined();
      const commands = diff(previous, next);
      expect(commands.map((c) => c.command).filter((name) => !ALLOWED.has(name))).toEqual([]);
      expect(commands.filter((c) => ON_AN_ID.test(c.command)).map(idOf).filter((name) => name === RELIEF_OVERLAY_ID)).toEqual([]);
    }
  });

  it('the same choice again changes nothing', () => {
    for (const id of BASEMAP_IDS) {
      const previous = running(id, ALL);
      expect(diff(previous, composeStyle(previous, styleOf(id), id, ALL, greyStyle()))).toEqual([]);
    }
  });
});
