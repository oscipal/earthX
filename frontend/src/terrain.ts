// The map in 3D (UI-06, `docs/plans/vp3/ui-06-3d-und-nordpfeil.md` §5): the button "3D" lays the map over the elevation
// tiles of the relief (AWS Terrain Tiles, `relief.ts`), tilts it to 50° and lets it turn and tilt; off, it turns back
// to the north, lies flat and only pans and zooms again (D27 holds in 2D). The tiles load in the browser, not through
// the platform, like those of the relief and the basemaps.

import type { Map as MapLibreMap, RasterDEMSourceSpecification } from 'maplibre-gl';

import { TERRAIN_ATTRIBUTION, TERRAIN_MAXZOOM, TERRAIN_TILES } from './relief';
import type { Bbox } from './types';

// The map's own source, without the prefix of a basemap or an overlay: `composeStyle` keeps it, and the terrain with
// it, across a change of the basemap (`MAP_OWN`). The overlay "Relief" has a source of its own (`ov-relief`).
export const TERRAIN_SOURCE = 'terrain';
export const TERRAIN_EXAGGERATION = 1.5;
// Over 60° MapLibre calls the drawing experimental, and the tiles grow by half for little more picture (§4).
export const MAX_PITCH = 60;
// Where switching on tilts the map to (Otto, F5).
export const PITCH_3D = 50;

export function terrainSource(): RasterDEMSourceSpecification {
  return { type: 'raster-dem', tiles: [TERRAIN_TILES], encoding: 'terrarium', tileSize: 256, maxzoom: TERRAIN_MAXZOOM, attribution: TERRAIN_ATTRIBUTION };
}

// The part of the map the 3D switch works on.
export type TerrainMap = Pick<
  MapLibreMap,
  'getSource' | 'addSource' | 'getTerrain' | 'setTerrain' | 'setMaxPitch' | 'getPitch' | 'getBearing' | 'easeTo' | 'jumpTo' | 'once' | 'dragRotate' | 'touchZoomRotate' | 'touchPitch' | 'keyboard'
>;

const reducedMotion = (): boolean => {
  try {
    return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  } catch {
    return false;
  }
};

function allowTurning(map: TerrainMap, on: boolean): void {
  if (on) {
    map.dragRotate.enable();
    map.touchZoomRotate.enableRotation();
    map.touchPitch.enable();
    map.keyboard.enableRotation();
  } else {
    map.dragRotate.disable();
    map.touchZoomRotate.disableRotation();
    map.touchPitch.disable();
    map.keyboard.disableRotation();
  }
}

// The terrain is on, `animate` false for the first picture of a visit (no flight while the page loads).
function switchOn(map: TerrainMap, animate: boolean): void {
  map.setMaxPitch(MAX_PITCH);
  if (!map.getSource(TERRAIN_SOURCE)) map.addSource(TERRAIN_SOURCE, terrainSource());
  if (!map.getTerrain()) map.setTerrain({ source: TERRAIN_SOURCE, exaggeration: TERRAIN_EXAGGERATION });
  allowTurning(map, true);
  if (animate && !reducedMotion()) map.easeTo({ pitch: PITCH_3D });
  else map.jumpTo({ pitch: PITCH_3D });
}

// Back to north and flat first, then without terrain: taking it away while the map is tilted would make it jump.
function switchOff(map: TerrainMap, animate: boolean, stillOff: () => boolean): void {
  allowTurning(map, false);
  const settle = () => {
    if (!stillOff()) return;
    if (map.getTerrain()) map.setTerrain(null);
    map.setMaxPitch(0);
  };
  if (map.getPitch() === 0 && map.getBearing() === 0) {
    settle();
    return;
  }
  if (animate && !reducedMotion()) {
    // Also when a pan stops the flight halfway: the map then lies flat at once.
    map.once('moveend', settle);
    map.easeTo({ pitch: 0, bearing: 0 });
  } else {
    map.jumpTo({ pitch: 0, bearing: 0 });
    settle();
  }
}

// `stillOff` asks at the end of the flight back whether the user has not switched 3D on again in the meantime.
export function applyTerrain(map: TerrainMap, on: boolean, options: { animate: boolean; stillOff: () => boolean }): void {
  if (on) switchOn(map, options.animate);
  else switchOff(map, options.animate, options.stillOff);
}

// The world in pixels at `zoom`, as MapLibre counts it (tiles of 512 px).
const worldSize = (zoom: number): number => 512 * 2 ** zoom;
const MAX_LAT = 85.051129;
const toX = (lon: number, size: number): number => ((lon + 180) / 360) * size;
const toY = (lat: number, size: number): number => {
  const sin = Math.sin((Math.max(-MAX_LAT, Math.min(MAX_LAT, lat)) * Math.PI) / 180);
  return (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * size;
};
const toLon = (x: number, size: number): number => (x / size) * 360 - 180;
const toLat = (y: number, size: number): number => (Math.atan(Math.sinh(Math.PI * (1 - (2 * y) / size))) * 180) / Math.PI;

// What the map would show flat, at the same centre, zoom and turn: the box the coverage asks for when the map is
// tilted (F10). The bounds of a tilted map reach the horizon, far more than the level of the cells counts on (#286).
// A box wider than the world is the world.
export function flatViewBounds(center: [number, number], zoom: number, width: number, height: number, bearing: number): Bbox {
  const size = worldSize(zoom);
  const cx = toX(center[0], size);
  const cy = toY(center[1], size);
  const turn = (bearing * Math.PI) / 180;
  const halfX = (Math.abs(Math.cos(turn)) * width + Math.abs(Math.sin(turn)) * height) / 2;
  const halfY = (Math.abs(Math.sin(turn)) * width + Math.abs(Math.cos(turn)) * height) / 2;
  const wide = 2 * halfX >= size;
  const west = wide ? -180 : toLon(cx - halfX, size);
  const east = wide ? 180 : toLon(cx + halfX, size);
  const north = toLat(Math.max(0, cy - halfY), size);
  const south = toLat(Math.min(size, cy + halfY), size);
  return [west, south, east, north];
}
