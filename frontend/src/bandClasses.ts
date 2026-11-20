// The classes of a band whose values are classes (M5-62): value, name and colour, as the registry gives them. The Data catalogue
// (table Value | Class | Colour), the legend "Classes" of a layer and `BANDS.txt` show what the platform names and derive nothing.

import type { Collection } from './types';

export interface BandClass {
  value: number;
  name: string;
  // `#rrggbb`, lower case, as the registry and `BANDS.txt` write it.
  colour: string;
}

// The classes of one band, each read on its own: a class without a whole value, a name or a colour of six hex digits is left
// out. `null` where there is no list or nothing in it reads.
function readClasses(rows: unknown, read: (row: Record<string, unknown>) => { value: unknown; name: unknown; colour: unknown }): BandClass[] | null {
  if (!Array.isArray(rows)) return null;
  const classes = rows.flatMap((row: unknown) => {
    if (!row || typeof row !== 'object') return [];
    const { value, name, colour } = read(row as Record<string, unknown>);
    if (!Number.isInteger(value) || typeof name !== 'string' || name === '' || typeof colour !== 'string') return [];
    const hex = /^#?([0-9a-fA-F]{6})$/u.exec(colour)?.[1];
    return hex ? [{ value: value as number, name, colour: `#${hex.toLowerCase()}` }] : [];
  });
  return classes.length > 0 ? classes : null;
}

// The classes of `band` as the collection publishes them in `earthx:bands`: the classification extension, the name people read in
// `title`, the colour as `color_hint` (hex without `#`).
export function classesOfBand(collection: Collection, band: string | undefined): BandClass[] | null {
  const listed = Array.isArray(collection['earthx:bands']) ? collection['earthx:bands'] : [];
  const entry = listed.find((one) => one?.name === band);
  return readClasses(entry?.['classification:classes'], (row) => ({ value: row.value, name: row.title, colour: row.color_hint }));
}

// The classes of a band in the answer of `POST /collections/{dataset}/bands`: `value`, `name`, `colour`.
export function parseClasses(rows: unknown): BandClass[] | null {
  return readClasses(rows, (row) => ({ value: row.value, name: row.name, colour: row.colour }));
}

// Every band of the collection that has classes, in the order of `earthx:bands`.
export function classBandsOf(collection: Collection): { band: string; classes: BandClass[] }[] {
  const listed = Array.isArray(collection['earthx:bands']) ? collection['earthx:bands'] : [];
  return listed.flatMap((entry) => {
    const classes = typeof entry?.name === 'string' ? classesOfBand(collection, entry.name) : null;
    return classes ? [{ band: entry.name, classes }] : [];
  });
}
