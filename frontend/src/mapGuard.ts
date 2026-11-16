// A listener of a map event that throws must not take the page with it (UI-10). MapLibre calls the listeners of an event straight from
// `fire`, so an error in one of them rises into whatever made the map fire: a change of a layer inside a React effect, the render loop.
// Every listener the app lays on the map is wrapped once here: an error is logged and the other listeners and the map carry on.

type Listener = (...args: unknown[]) => unknown;

interface Evented {
  on: (...args: never[]) => unknown;
  once: (...args: never[]) => unknown;
  off: (...args: never[]) => unknown;
}

export function guardMapEvents(map: Evented, log: (message: string, error: unknown) => void = console.error): void {
  // The same wrapper for the same listener, so that `off` finds what `on` laid.
  const guarded = new WeakMap<Listener, Listener>();
  const guard = (listener: Listener): Listener => {
    let wrapper = guarded.get(listener);
    if (!wrapper) {
      wrapper = function (this: unknown, ...args: unknown[]) {
        try {
          return listener.apply(this, args);
        } catch (error) {
          const type = (args[0] as { type?: unknown } | undefined)?.type;
          log(`Map event${typeof type === 'string' ? ` "${type}"` : ''} failed`, error);
          return undefined;
        }
      };
      guarded.set(listener, wrapper);
    }
    return wrapper;
  };
  for (const name of ['on', 'once', 'off'] as const) {
    const original = (map[name] as (...args: unknown[]) => unknown).bind(map);
    (map as unknown as Record<string, unknown>)[name] = (...args: unknown[]) =>
      original(...args.map((arg) => (typeof arg === 'function' ? guard(arg as Listener) : arg)));
  }
}
