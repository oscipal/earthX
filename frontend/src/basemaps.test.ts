// UI-02a: the catalogue of the basemaps. What is chosen from and where each one's tiles come from.

import { describe, expect, it } from 'vitest';

import { BASEMAP_IDS, BASEMAP_PREFIX, BASEMAPS, DEFAULT_BASEMAP } from './basemaps';

describe('the basemap catalogue', () => {
  it('offers satellite, streets, grey and outlines, in that order, and starts on satellite', () => {
    expect(BASEMAP_IDS).toEqual(['satellite', 'streets', 'grey', 'outlines']);
    expect(DEFAULT_BASEMAP).toBe('satellite');
    expect(Object.keys(BASEMAPS)).toEqual([...BASEMAP_IDS]);
  });

  it.each(BASEMAP_IDS)('%s has a name, an id of its own and a tooltip that says where its tiles come from', (id) => {
    const basemap = BASEMAPS[id];
    expect(basemap.id).toBe(id);
    expect(basemap.name).toMatch(/^[A-Z][a-z]+$/u);
    expect(basemap.tip).toMatch(/Tiles load from [a-z.]+\.(com|org)\.$/u);
  });

  it('names the host the tiles come from, and no other', () => {
    expect(BASEMAPS.satellite.tip).toContain('arcgisonline.com');
    for (const id of ['streets', 'grey', 'outlines'] as const) expect(BASEMAPS[id].tip).toContain('openfreemap.org');
  });

  it('keeps a key or token out of every address (no secret in the repository)', () => {
    const everything = JSON.stringify(Object.values(BASEMAPS).map((basemap) => basemap.style));
    expect(everything).not.toMatch(/key=|token|apikey|access_token/iu);
    for (const url of everything.match(/https?:\/\/[^"\s]+/gu) ?? []) expect(url.startsWith('https://')).toBe(true);
  });

  it('points the published styles at HTTPS addresses of the style server', () => {
    expect(BASEMAPS.streets.style).toBe('https://tiles.openfreemap.org/styles/liberty');
    expect(BASEMAPS.grey.style).toBe('https://tiles.openfreemap.org/styles/positron');
  });

  it.each(['satellite', 'outlines'] as const)('draws %s from layers whose sources all exist, and gives none an id with the basemap prefix', (id) => {
    const style = BASEMAPS[id].style;
    if (typeof style === 'string') throw new Error('a local style is an object');
    for (const layer of style.layers) {
      if ('source' in layer && layer.source !== undefined) expect(Object.keys(style.sources)).toContain(layer.source);
      expect(layer.id.startsWith(BASEMAP_PREFIX)).toBe(false);
    }
    for (const key of Object.keys(style.sources)) expect(key.startsWith(BASEMAP_PREFIX)).toBe(false);
  });

  it('draws the outlines from the sea and the borders only, no roads, places or labels', () => {
    const style = BASEMAPS.outlines.style;
    if (typeof style === 'string') throw new Error('a local style is an object');
    const drawn = style.layers.map((layer) => ('source-layer' in layer ? layer['source-layer'] : undefined));
    expect(new Set(drawn)).toEqual(new Set(['water', 'boundary']));
    expect(style.layers.some((layer) => layer.type === 'symbol')).toBe(false);
    expect(style.glyphs).toBeUndefined();
  });

  it('keeps the maritime borders and nothing of a lower rank than a region out of the border lines', () => {
    const style = BASEMAPS.outlines.style;
    if (typeof style === 'string') throw new Error('a local style is an object');
    for (const layer of style.layers.filter((l) => l.type === 'line')) {
      const filter = JSON.stringify('filter' in layer ? layer.filter : null);
      expect(filter).toContain('maritime');
      expect(filter).toContain('admin_level');
    }
  });

  it('serves the satellite imagery as 256 px raster tiles to zoom 19', () => {
    const style = BASEMAPS.satellite.style;
    if (typeof style === 'string') throw new Error('a local style is an object');
    expect(style.sources.satellite).toMatchObject({ type: 'raster', tileSize: 256, maxzoom: 19 });
  });
});
