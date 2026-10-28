// UI-02a: what MapLibre's own style diff makes of a change of the basemap. `Map.setStyle(…, { diff: true })` only
// keeps the app's layers if the diff is made of a few commands that touch the basemap's ids; a diff that falls back
// to "set the whole style" (or touches the projection, the sky or an id of the app) would rebuild the map and blink
// every picture. Run against the diff of `@maplibre/maplibre-gl-style-spec`, which `maplibre-gl` itself uses.

import { diff } from '@maplibre/maplibre-gl-style-spec';
import type { StyleSpecification } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';

import { BASEMAP_IDS, BASEMAP_PREFIX, BASEMAPS, type BasemapId } from './basemaps';
import { OVERLAY_PREFIX } from './overlays';
import { appLayers, publishedStyle } from './fixtures/publishedStyle';
import { baseMapStyle, composeStyle } from './mapStyles';

// What a change of the basemap may be made of: whole sources and layers, the glyphs and sprite, and the properties of
// a layer that two styles share.
const ALLOWED = new Set(['addSource', 'removeSource', 'addLayer', 'removeLayer', 'setGlyphs', 'setSprite', 'setPaintProperty', 'setLayoutProperty', 'setFilter', 'setLayerZoomRange']);
const ON_AN_ID = /^(add|remove)(Source|Layer)$|^set(PaintProperty|LayoutProperty|Filter|LayerZoomRange)$/u;

// The two published styles differ in the colour of their land, as the real ones differ in much more.
function styleOf(id: BasemapId): StyleSpecification {
  const source = BASEMAPS[id].style;
  if (typeof source !== 'string') return source;
  const style = publishedStyle();
  if (id === 'grey') style.layers[0] = { id: 'background', type: 'background', paint: { 'background-color': '#eeeeee' } };
  return style;
}

// The map as it runs with `id` under the app's layers: the first style, the app's layers laid, the globe set.
function running(id: BasemapId): StyleSpecification {
  const base = baseMapStyle('#04070a', 'satellite');
  const own = appLayers();
  const first = { ...base, sources: { ...base.sources, ...own.sources }, layers: [...base.layers, ...own.layers], projection: own.projection, center: [10, 20] as [number, number], zoom: 1.6 };
  return id === 'satellite' ? first : composeStyle(first, styleOf(id), id);
}

const idOf = (command: { command: string; args: unknown[] }): string => {
  const [first] = command.args;
  return typeof first === 'string' ? first : (first as { id: string }).id;
};

const pairs = BASEMAP_IDS.flatMap((from) => BASEMAP_IDS.filter((to) => to !== from).map((to) => [from, to] as const));

describe('the style diff of a change of the basemap', () => {
  it.each(pairs)('%s to %s: only commands on the basemap, none that rebuild the map', (from, to) => {
    const previous = running(from);
    const next = composeStyle(previous, styleOf(to), to);
    const commands = diff(previous, next);
    expect(commands.length).toBeGreaterThan(0);
    expect(commands.map((c) => c.command).filter((name) => !ALLOWED.has(name))).toEqual([]);
    // Every command on a source or a layer is on one of the basemap's, never on one of the app's.
    for (const command of commands.filter((c) => ON_AN_ID.test(c.command))) {
      expect(idOf(command).startsWith(BASEMAP_PREFIX) || idOf(command).startsWith(OVERLAY_PREFIX)).toBe(true);
    }
  });

  it.each(pairs)('%s to %s: the app\'s layers and sources are neither removed nor added, and keep their order', (from, to) => {
    const previous = running(from);
    const next = composeStyle(previous, styleOf(to), to);
    const own = (layers: StyleSpecification['layers']) =>
      layers.map((l) => l.id).filter((id) => id !== 'background' && !id.startsWith(BASEMAP_PREFIX) && !id.startsWith(OVERLAY_PREFIX));
    expect(own(next.layers)).toEqual(own(previous.layers));
    expect(Object.keys(next.sources).filter((k) => !k.startsWith(BASEMAP_PREFIX)).sort()).toEqual(
      Object.keys(previous.sources).filter((k) => !k.startsWith(BASEMAP_PREFIX)).sort(),
    );
  });

  it.each(pairs)('%s to %s: the projection, the sky and the camera stay as they are', (from, to) => {
    const previous = running(from);
    const next = composeStyle(previous, styleOf(to), to);
    expect(next.projection).toEqual(previous.projection);
    expect(next.sky).toEqual(previous.sky);
    expect([next.center, next.zoom]).toEqual([previous.center, previous.zoom]);
    expect(diff(previous, next).some((c) => ['setProjection', 'setSky', 'setCenter', 'setZoom'].includes(c.command))).toBe(false);
  });

  it.each(BASEMAP_IDS)('%s again: nothing to change', (id) => {
    const previous = running(id);
    expect(diff(previous, composeStyle(previous, styleOf(id), id))).toEqual([]);
  });
});
