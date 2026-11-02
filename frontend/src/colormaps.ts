// The colormaps to choose from (UI-03d, Otto, 2.11.2026): the list and the colours of the previews come from the tiler
// (`GET /colormaps`, `access/colormaps.py`), not from the page. The dropdown "Colormap" offers a few of them and "More…", which opens
// the whole list. "Reverse" is the tiler's own reversed colormap, its name with `_r`: what the look keeps, the tile asks for and
// "Save", a result layer and the permalink carry.

import { BASE } from './api';

export interface ColormapEntry {
  name: string;
  // The name of the same colormap reversed, `null` where the tiler has none.
  reversed: string | null;
  // A few colours from the first to the last, for the preview.
  colors: string[];
}

export interface ColormapGroup {
  name: string;
  colormaps: ColormapEntry[];
}

export const REVERSED = '_r';

// The few the dropdown offers (a proposal to Otto): a grey scale, two perceptually even ones, the two of the indices and one for
// elevation.
export const SHORT_COLORMAPS = ['gray', 'viridis', 'magma', 'rdylgn', 'rdbu', 'terrain'] as const;

export const isReversed = (name: string): boolean => name.endsWith(REVERSED);
// The colormap a name stands for, reversed or not.
export const baseOf = (name: string): string => (isReversed(name) ? name.slice(0, -REVERSED.length) : name);
export const withReverse = (name: string, reversed: boolean): string => (name === '' ? '' : `${baseOf(name)}${reversed ? REVERSED : ''}`);

// The answer of the tiler, checked; `null` where it is none.
export function parseColormaps(body: unknown): ColormapGroup[] | null {
  const groups = (body as { groups?: unknown } | null)?.groups;
  if (!Array.isArray(groups)) return null;
  const read: ColormapGroup[] = [];
  for (const group of groups) {
    const { name, colormaps } = (group ?? {}) as Record<string, unknown>;
    if (typeof name !== 'string' || !Array.isArray(colormaps)) return null;
    const entries: ColormapEntry[] = [];
    for (const entry of colormaps) {
      const e = (entry ?? {}) as Record<string, unknown>;
      if (typeof e.name !== 'string' || !Array.isArray(e.colors) || !e.colors.every((c) => typeof c === 'string' && /^#[0-9a-f]{6}$/iu.test(c))) return null;
      entries.push({ name: e.name, reversed: typeof e.reversed === 'string' ? e.reversed : null, colors: e.colors as string[] });
    }
    read.push({ name, colormaps: entries });
  }
  return read;
}

let asked: Promise<ColormapGroup[] | null> | null = null;

// Asked once for the page; a failure is asked again next time.
export function loadColormaps(): Promise<ColormapGroup[] | null> {
  asked ??= fetch(`${BASE}/colormaps`)
    .then(async (res) => (res.ok ? parseColormaps(await res.json()) : null))
    .catch(() => null)
    .then((groups) => {
      if (groups === null) asked = null;
      return groups;
    });
  return asked;
}

// For the tests: forget the answer.
export function forgetColormaps(): void {
  asked = null;
}

// The entry of a colormap by its name, reversed or not.
export function entryOf(groups: readonly ColormapGroup[] | null, name: string): ColormapEntry | null {
  const base = baseOf(name);
  for (const group of groups ?? []) for (const entry of group.colormaps) if (entry.name === base) return entry;
  return null;
}

// What the dropdown offers: the few, as far as the tiler has them, and the one chosen, where it is another.
export function shortList(groups: readonly ColormapGroup[] | null, chosen: string): string[] {
  const known = groups === null ? null : new Set(groups.flatMap((g) => g.colormaps.map((c) => c.name)));
  const few = SHORT_COLORMAPS.filter((name) => known === null || known.has(name));
  const base = baseOf(chosen);
  return base === '' || few.includes(base as (typeof SHORT_COLORMAPS)[number]) ? [...few] : [...few, base];
}

// The colours of a preview as a CSS gradient from left to right, reversed where asked.
export function gradientOf(colors: readonly string[], reversed = false): string {
  const list = reversed ? [...colors].reverse() : colors;
  return `linear-gradient(to right, ${list.join(', ')})`;
}
