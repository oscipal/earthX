// @vitest-environment jsdom
//
// UI-06 (Otto, 11.11.2026): the buttons at the bottom right of the map, on a stand-in of the map. Top to bottom the compass, zoom in,
// zoom out and "3D"; the compass is always there and turns with the map, a click turns north and lays the map flat; in 3D a drag
// on it and ←/→ turn the map, in 2D neither does; "3D" is a switch that is filled when on.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { stepWithArrowKeys } from '../stepKeys';
import { useAppStore } from '../store';
import { COMPASS_TIP, MapControls, MAX_ZOOM_REASON, MIN_ZOOM_REASON, TERRAIN_OFF_TIP, TERRAIN_ON_TIP, TURN_STEP, type ControlledMap } from './MapControls';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

function fakeMap(start: { bearing?: number; zoom?: number } = {}) {
  const listeners: Record<string, Set<() => void>> = {};
  const state = { bearing: start.bearing ?? 0, zoom: start.zoom ?? 5 };
  const fire = (event: string) => listeners[event]?.forEach((done) => done());
  return {
    state,
    on: vi.fn((event: string, done: () => void) => {
      (listeners[event] ??= new Set()).add(done);
    }),
    off: vi.fn((event: string, done: () => void) => {
      listeners[event]?.delete(done);
    }),
    turn: (bearing: number) => {
      state.bearing = bearing;
      fire('rotate');
    },
    zoomTo: (zoom: number) => {
      state.zoom = zoom;
      fire('zoom');
    },
    getBearing: () => state.bearing,
    setBearing: vi.fn((bearing: number) => {
      state.bearing = bearing;
      fire('rotate');
    }),
    easeTo: vi.fn(),
    resetNorthPitch: vi.fn(),
    getZoom: () => state.zoom,
    getMinZoom: () => 0,
    getMaxZoom: () => 22,
    zoomIn: vi.fn(),
    zoomOut: vi.fn(),
  };
}

let container: HTMLDivElement;
let root: Root;
let map: ReturnType<typeof fakeMap>;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.appendChild(container);
  root = createRoot(container);
  map = fakeMap();
  useAppStore.setState({ terrain: false });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

const mount = () => act(() => root.render(<MapControls map={map as unknown as ControlledMap} />));
const buttons = () => [...container.querySelectorAll<HTMLButtonElement>('.map-controls > button')];
const compass = () => container.querySelector<HTMLButtonElement>('.map-compass')!;
const three = () => container.querySelector<HTMLButtonElement>('.map-3d')!;
const needleTurn = () => container.querySelector<SVGElement>('.compass-needle')!.style.transform;

// A pointer on the compass of a size of 40 px at (0, 0): its centre is (20, 20).
function pointer(type: string, x: number, y: number) {
  const event = new MouseEvent(type, { bubbles: true, clientX: x, clientY: y, button: 0 });
  Object.assign(event, { pointerId: 1 });
  compass().dispatchEvent(event);
}

function placeCompass() {
  vi.spyOn(compass(), 'getBoundingClientRect').mockReturnValue({ left: 0, top: 0, width: 40, height: 40, right: 40, bottom: 40, x: 0, y: 0, toJSON: () => ({}) });
}

describe('MapControls: order and names', () => {
  it('stands as compass, zoom in, zoom out and 3D, in one group', () => {
    mount();
    expect(container.querySelector('.map-controls')?.getAttribute('role')).toBe('group');
    expect(buttons().map((b) => b.getAttribute('aria-label') ?? b.textContent)).toEqual([COMPASS_TIP, 'Zoom in', 'Zoom out', '3D']);
  });

  it('gives every button a tooltip of the step "advanced", no title and no locked look while nothing is locked', () => {
    mount();
    for (const button of buttons()) {
      expect(button.getAttribute('data-tip')).toBeTruthy();
      expect(button.getAttribute('data-tip-level')).toBe('advanced');
      expect(button.hasAttribute('title')).toBe(false);
      expect(button.disabled).toBe(false);
      expect(button.getAttribute('aria-disabled')).toBeNull();
    }
  });
});

describe('MapControls: the compass (F2, F3, F15, F16)', () => {
  it('is there in 2D, not locked, and points up while the map faces north', () => {
    mount();
    expect(compass()).not.toBeNull();
    expect(compass().getAttribute('aria-disabled')).toBeNull();
    expect(needleTurn()).toBe('rotate(0deg)');
  });

  it('turns its needle against the map: a map turned by 30° has north 30° to the left', () => {
    mount();
    act(() => map.turn(30));
    expect(needleTurn()).toBe('rotate(-30deg)');
  });

  it('turns north and lays the map flat on a click, in 2D and in 3D', () => {
    mount();
    act(() => compass().click());
    act(() => useAppStore.setState({ terrain: true }));
    act(() => compass().click());
    expect(map.resetNorthPitch).toHaveBeenCalledTimes(2);
  });

  it('turns the map with a drag around it in 3D, and the click at the end of the drag does not undo the turn', () => {
    useAppStore.setState({ terrain: true });
    mount();
    placeCompass();
    act(() => {
      // From the right of the centre to below it: the pointer goes a quarter turn clockwise, so does north.
      pointer('pointerdown', 40, 20);
      pointer('pointermove', 20, 40);
      pointer('pointerup', 20, 40);
      compass().click();
    });
    expect(map.state.bearing).toBeCloseTo(-90, 6);
    expect(needleTurn()).toBe('rotate(90deg)');
    expect(map.resetNorthPitch).not.toHaveBeenCalled();
    // The next click without a drag resets again.
    act(() => compass().click());
    expect(map.resetNorthPitch).toHaveBeenCalledTimes(1);
  });

  it('takes a move of less than 4 px for a click', () => {
    useAppStore.setState({ terrain: true });
    mount();
    placeCompass();
    act(() => {
      pointer('pointerdown', 40, 20);
      pointer('pointermove', 41, 22);
      pointer('pointerup', 41, 22);
      compass().click();
    });
    expect(map.setBearing).not.toHaveBeenCalled();
    expect(map.resetNorthPitch).toHaveBeenCalledTimes(1);
  });

  it('does not turn the map with a drag in 2D (D27)', () => {
    mount();
    placeCompass();
    act(() => {
      pointer('pointerdown', 40, 20);
      pointer('pointermove', 20, 40);
      pointer('pointerup', 20, 40);
    });
    expect(map.setBearing).not.toHaveBeenCalled();
  });

  it('turns by 15° with ←/→ in 3D, not in 2D and not with a modifier', () => {
    mount();
    const key = (k: string, extra: KeyboardEventInit = {}) =>
      act(() => {
        compass().dispatchEvent(new KeyboardEvent('keydown', { key: k, bubbles: true, ...extra }));
      });
    key('ArrowLeft');
    expect(map.easeTo).not.toHaveBeenCalled();
    act(() => useAppStore.setState({ terrain: true }));
    map.state.bearing = 10;
    key('ArrowLeft');
    expect(map.easeTo).toHaveBeenLastCalledWith({ bearing: 10 - TURN_STEP });
    key('ArrowRight');
    expect(map.easeTo).toHaveBeenLastCalledWith({ bearing: 10 + TURN_STEP });
    key('ArrowRight', { shiftKey: true });
    key('ArrowUp');
    expect(map.easeTo).toHaveBeenCalledTimes(2);
  });

  it('keeps its arrows from the time slider, which browses the passes with them elsewhere', () => {
    mount();
    const event = new KeyboardEvent('keydown', { key: 'ArrowLeft', bubbles: true });
    Object.defineProperty(event, 'target', { value: compass() });
    useAppStore.setState({ groups: [{}, {}] as never, activeGroupIndex: 0 });
    expect(stepWithArrowKeys(event)).toBe(false);
  });

  it('leaves the map alone once it is gone', () => {
    mount();
    act(() => root.unmount());
    expect(map.off).toHaveBeenCalledWith('rotate', expect.any(Function));
    expect(map.off).toHaveBeenCalledWith('zoom', expect.any(Function));
    root = createRoot(container);
  });
});

describe('MapControls: zoom', () => {
  it('zooms in and out', () => {
    mount();
    act(() => buttons()[1].click());
    act(() => buttons()[2].click());
    expect(map.zoomIn).toHaveBeenCalledTimes(1);
    expect(map.zoomOut).toHaveBeenCalledTimes(1);
  });

  it('locks zoom in at the closest zoom and zoom out at the farthest, with the reason in the tooltip', () => {
    mount();
    act(() => map.zoomTo(22));
    expect(buttons()[1].getAttribute('aria-disabled')).toBe('true');
    expect(buttons()[1].getAttribute('data-tip')).toBe(MAX_ZOOM_REASON);
    act(() => buttons()[1].click());
    expect(map.zoomIn).not.toHaveBeenCalled();
    act(() => map.zoomTo(0));
    expect(buttons()[1].getAttribute('aria-disabled')).toBeNull();
    expect(buttons()[2].getAttribute('aria-disabled')).toBe('true');
    expect(buttons()[2].getAttribute('data-tip')).toBe(MIN_ZOOM_REASON);
    act(() => buttons()[2].click());
    expect(map.zoomOut).not.toHaveBeenCalled();
  });
});

describe('MapControls: 3D (F4, F5)', () => {
  it('is a switch with the text "3D", pressed while on, and says what a click does', () => {
    mount();
    expect(three().textContent).toBe('3D');
    expect(three().classList.contains('seg')).toBe(true);
    expect(three().getAttribute('aria-pressed')).toBe('false');
    expect(three().getAttribute('data-tip')).toBe(TERRAIN_ON_TIP);
    act(() => three().click());
    expect(useAppStore.getState().terrain).toBe(true);
    expect(three().getAttribute('aria-pressed')).toBe('true');
    expect(three().getAttribute('data-tip')).toBe(TERRAIN_OFF_TIP);
    act(() => three().click());
    expect(useAppStore.getState().terrain).toBe(false);
  });

  it('names the host the elevation tiles load from', () => {
    expect(TERRAIN_ON_TIP).toContain('amazonaws.com');
  });
});
