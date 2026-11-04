// @vitest-environment jsdom
//
// NM4-35: the terrain shading. Where its tiles come from, what it credits and what it looks like.

import { validateStyleMin } from '@maplibre/maplibre-gl-style-spec';
import type { StyleSpecification } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';

import { RELIEF_OVERLAY_ID, reliefLayer, reliefSource, TERRAIN_ATTRIBUTION, TERRAIN_ATTRIBUTION_URL, TERRAIN_MAXZOOM, TERRAIN_TILES } from './relief';

const style: StyleSpecification = {
  version: 8,
  sources: { dem: reliefSource() },
  layers: [reliefLayer('shade', 'dem')],
};

describe('the elevation tiles', () => {
  it('come from AWS Terrain Tiles as Terrarium PNG, over HTTPS and without a key', () => {
    expect(TERRAIN_TILES).toBe('https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png');
    expect(TERRAIN_TILES).not.toMatch(/key=|token|apikey|access_token/iu);
    expect(reliefSource()).toMatchObject({ type: 'raster-dem', encoding: 'terrarium', tiles: [TERRAIN_TILES], tileSize: 256 });
  });

  it('are asked for up to zoom 12 and no further (Otto, 28.10.2026)', () => {
    expect(TERRAIN_MAXZOOM).toBe(12);
    expect(reliefSource()).toMatchObject({ maxzoom: 12 });
  });

  it('credit the terrain in short, with a link to the full list of the publishers of the tiles (§6.11)', () => {
    expect(reliefSource()).toMatchObject({ attribution: TERRAIN_ATTRIBUTION });
    const div = document.createElement('div');
    div.innerHTML = TERRAIN_ATTRIBUTION;
    expect(div.textContent).toBe('Terrain: USGS, NOAA, EU-DEM (Copernicus) and others');
    const links = [...div.querySelectorAll('a')];
    expect(links.map((a) => a.getAttribute('href'))).toEqual([TERRAIN_ATTRIBUTION_URL]);
    expect(TERRAIN_ATTRIBUTION_URL).toBe('https://github.com/tilezen/joerd/blob/master/docs/attribution.md');
    expect(links[0].getAttribute('rel')).toBe('noopener noreferrer');
    expect(links[0].getAttribute('target')).toBe('_blank');
  });

  it('give every call a source of its own, so that one cannot change another', () => {
    expect(reliefSource()).not.toBe(reliefSource());
  });
});

describe('the shading', () => {
  it('is a style MapLibre accepts', () => {
    expect(validateStyleMin(style)).toEqual([]);
  });

  it('has light from the north-west at 45° that is fixed to the map', () => {
    expect(reliefLayer('shade', 'dem')).toMatchObject({
      type: 'hillshade',
      id: 'shade',
      source: 'dem',
      paint: { 'hillshade-illumination-direction': 315, 'hillshade-illumination-altitude': 45, 'hillshade-illumination-anchor': 'map' },
    });
  });

  it('is light-handed, so that the imagery under it stays readable', () => {
    const paint = reliefLayer('shade', 'dem').paint as Record<string, unknown>;
    expect(paint['hillshade-exaggeration']).toBe(0.5);
    expect(paint['hillshade-shadow-color']).toBe('rgba(0, 0, 0, 0.45)');
  });

  it('is the same in both themes: it asks for no colour of the theme', () => {
    expect(JSON.stringify(reliefLayer('shade', 'dem'))).not.toMatch(/--map-bg|var\(/u);
  });

  it('names its overlay with the prefix of the overlays', () => {
    expect(RELIEF_OVERLAY_ID).toBe('ov-relief');
  });
});
