// The buttons at the bottom right of the map (UI-06, Otto 11.11.2026), top to bottom: the compass, zoom in, zoom out and "3D"
// (`docs/ui/leitfaden.md` §9). They replace MapLibre's `NavigationControl`, so that all four have one form and the tokens of
// both themes.
//
// The compass is always there; in 2D it points up. A click turns the map to the north and lays it flat. In 3D a drag around
// it turns the map, and with the focus on it ←/→ turn it by 15° (F15); in 2D it is not locked (F16): the click finds the map
// already facing north and flat.

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import type { Map as MapLibreMap } from 'maplibre-gl';

import { useAppStore } from '../store';
import { CompassNeedle } from './CompassNeedle';
import { MinusIcon, PlusIcon } from './icons';

export const COMPASS_TIP = 'Reset north and tilt';
export const TERRAIN_ON_TIP = 'Lay the map over the terrain and tilt it. Elevation tiles load from amazonaws.com.';
export const TERRAIN_OFF_TIP = 'Show the map flat and facing north';
export const MAX_ZOOM_REASON = 'Already zoomed in all the way';
export const MIN_ZOOM_REASON = 'Already zoomed out all the way';
// A turn of the compass by the keys, as MapLibre turns the map with Shift and the arrows.
export const TURN_STEP = 15;
// A drag starts after this many pixels; a shorter move is a click.
const DRAG_START = 4;

export type ControlledMap = Pick<
  MapLibreMap,
  'on' | 'off' | 'getBearing' | 'setBearing' | 'easeTo' | 'resetNorthPitch' | 'getZoom' | 'getMinZoom' | 'getMaxZoom' | 'zoomIn' | 'zoomOut'
>;

interface Drag {
  pointer: number;
  x: number;
  y: number;
  centerX: number;
  centerY: number;
  angle: number;
  bearing: number;
  moved: boolean;
}

const degrees = (radians: number): number => (radians * 180) / Math.PI;

export function MapControls({ map }: { map: ControlledMap }) {
  const terrain = useAppStore((s) => s.terrain);
  const setTerrain = useAppStore((s) => s.setTerrain);
  const [bearing, setBearing] = useState(() => map.getBearing());
  const [zoom, setZoom] = useState(() => map.getZoom());
  const drag = useRef<Drag | null>(null);
  // The click that ends a drag does not reset the turn the drag made.
  const dragged = useRef(false);

  useEffect(() => {
    const turned = () => setBearing(map.getBearing());
    const zoomed = () => setZoom(map.getZoom());
    map.on('rotate', turned);
    map.on('zoom', zoomed);
    return () => {
      map.off('rotate', turned);
      map.off('zoom', zoomed);
    };
  }, [map]);

  const startDrag = (event: PointerEvent<HTMLButtonElement>) => {
    if (!terrain || event.button !== 0) return;
    const box = event.currentTarget.getBoundingClientRect();
    const centerX = box.left + box.width / 2;
    const centerY = box.top + box.height / 2;
    drag.current = {
      pointer: event.pointerId,
      x: event.clientX,
      y: event.clientY,
      centerX,
      centerY,
      angle: degrees(Math.atan2(event.clientY - centerY, event.clientX - centerX)),
      bearing: map.getBearing(),
      moved: false,
    };
    event.currentTarget.setPointerCapture?.(event.pointerId);
  };

  const moveDrag = (event: PointerEvent<HTMLButtonElement>) => {
    const now = drag.current;
    if (!now || now.pointer !== event.pointerId) return;
    if (!now.moved && Math.hypot(event.clientX - now.x, event.clientY - now.y) < DRAG_START) return;
    now.moved = true;
    // The needle follows the pointer around the button; the map turns the other way, as the needle is turned against it.
    const angle = degrees(Math.atan2(event.clientY - now.centerY, event.clientX - now.centerX));
    map.setBearing(now.bearing - (angle - now.angle));
  };

  const endDrag = (event: PointerEvent<HTMLButtonElement>) => {
    const now = drag.current;
    if (!now || now.pointer !== event.pointerId) return;
    dragged.current = now.moved;
    drag.current = null;
  };

  const resetNorth = () => {
    if (dragged.current) {
      dragged.current = false;
      return;
    }
    map.resetNorthPitch();
  };

  const turnByKey = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (!terrain || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
    event.preventDefault();
    map.easeTo({ bearing: map.getBearing() + (event.key === 'ArrowLeft' ? -TURN_STEP : TURN_STEP) });
  };

  const atMax = zoom >= map.getMaxZoom();
  const atMin = zoom <= map.getMinZoom();

  return (
    <div className="map-controls" role="group" aria-label="Map controls">
      <button
        type="button"
        className="icon-btn map-compass"
        aria-label={COMPASS_TIP}
        data-tip={COMPASS_TIP}
        data-tip-level="advanced"
        onClick={resetNorth}
        onKeyDown={turnByKey}
        onPointerDown={startDrag}
        onPointerMove={moveDrag}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        <CompassNeedle bearing={bearing} />
      </button>
      <button
        type="button"
        className="icon-btn map-zoom-in"
        aria-label="Zoom in"
        aria-disabled={atMax || undefined}
        data-tip={atMax ? MAX_ZOOM_REASON : 'Zoom in'}
        data-tip-level="advanced"
        onClick={() => {
          if (!atMax) map.zoomIn();
        }}
      >
        <PlusIcon />
      </button>
      <button
        type="button"
        className="icon-btn map-zoom-out"
        aria-label="Zoom out"
        aria-disabled={atMin || undefined}
        data-tip={atMin ? MIN_ZOOM_REASON : 'Zoom out'}
        data-tip-level="advanced"
        onClick={() => {
          if (!atMin) map.zoomOut();
        }}
      >
        <MinusIcon />
      </button>
      <button
        type="button"
        className="btn seg map-3d"
        aria-pressed={terrain}
        data-tip={terrain ? TERRAIN_OFF_TIP : TERRAIN_ON_TIP}
        data-tip-level="advanced"
        onClick={() => setTerrain(!terrain)}
      >
        3D
      </button>
    </div>
  );
}
