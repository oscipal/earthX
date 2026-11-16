// UI-10: a listener of a map event that throws is logged; the event, the other listeners and the page go on.

import { Evented } from 'maplibre-gl';
import { describe, expect, it } from 'vitest';

import { guardMapEvents } from './mapGuard';

function guardedMap() {
  const map = new Evented();
  const logged: [string, unknown][] = [];
  guardMapEvents(map, (message, error) => logged.push([message, error]));
  return { map, logged };
}

const boom = () => {
  throw new TypeError('tiles?.some is not a function');
};

describe('guardMapEvents', () => {
  it('without it, an error of a listener rises out of the code that made the map fire', () => {
    const map = new Evented();
    map.on('styledata', boom);
    expect(() => map.fire('styledata')).toThrow(TypeError);
  });

  it('logs an error of a listener with the event, and the listeners after it still run', () => {
    const { map, logged } = guardedMap();
    const heard: string[] = [];
    map.on('styledata', boom);
    map.on('styledata', () => heard.push('after'));
    expect(() => map.fire('styledata')).not.toThrow();
    expect(heard).toEqual(['after']);
    expect(logged).toHaveLength(1);
    expect(logged[0][0]).toBe('Map event "styledata" failed');
    expect(logged[0][1]).toBeInstanceOf(TypeError);
  });

  it('guards a listener laid once, and `off` still removes a guarded listener', () => {
    const { map, logged } = guardedMap();
    let calls = 0;
    const count = () => calls++;
    map.once('idle', boom);
    map.on('idle', count);
    map.fire('idle');
    map.off('idle', count);
    map.fire('idle');
    expect(calls).toBe(1);
    expect(logged).toHaveLength(1);
  });

  it('keeps what a listener returns and its `this`', () => {
    const { map } = guardedMap();
    let self: unknown = null;
    map.on('zoomend', function (this: unknown) {
      self = this;
    });
    map.fire('zoomend');
    expect(self).toBe(map);
  });

  it('logs a throw that is no Error', () => {
    const { map, logged } = guardedMap();
    map.on('moveend', () => {
      throw 'not an error';
    });
    map.fire('moveend');
    expect(logged).toEqual([['Map event "moveend" failed', 'not an error']]);
  });
});
