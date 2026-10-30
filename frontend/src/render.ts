// Turns a `/statistics` answer into one stretch range for the tile URL
// (adr/0006 §3.4, F18): the 2nd/98th percentile across every band the asset
// carries, so a multi-band asset (e.g. a true-colour composite) gets one
// shared range rather than one per band — TiTiler's `rescale` broadcasts a
// single pair to every output band when only one is given.

import type { BandStatistics } from './api';
import type { AppliedRender, EarthxDefaultRender } from './types';

// Named colormaps rio-tiler/matplotlib ship — generic, not tied to any dataset.
export const COLORMAPS = [
  'viridis',
  'plasma',
  'inferno',
  'magma',
  'cividis',
  'turbo',
  'greens',
  'ylgn',
  'rdylgn',
  'spectral',
  'terrain',
  'gist_earth',
  'greys',
];

export function autoRescale(stats: Record<string, BandStatistics>): [number, number] | null {
  const bands = Object.values(stats);
  const los = bands.map((b) => b.percentile_2).filter((v) => typeof v === 'number' && Number.isFinite(v));
  const his = bands.map((b) => b.percentile_98).filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (los.length === 0 || his.length === 0) return null;
  return [Math.min(...los), Math.max(...his)];
}

// The registry's standard visualisation as tile-URL parameters (`DefaultRender`
// → `AppliedRender`, M2-04/D20). The same translation on both paths that show
// pixels, because the two must agree: full resolution reads it when entering
// focus (`store.enterFocus`), and the browse preview reads it for its own tile
// URL (M2-10).
//
// Without it a preview of float data renders wrong rather than not at all —
// rio-tiler falls back to the *type's* min/max bounds and returns a washed-out
// image (measured: 127..255 instead of 0..255 for reflectance in 0..0.30), so
// the preview and the full-resolution view of one scene would not look like the
// same data. `rescale` takes the first band pair, which TiTiler broadcasts to
// every output band, exactly as `autoRescale` above relies on.
export function appliedRenderFrom(render: EarthxDefaultRender): AppliedRender {
  const rescale = render.rescale?.[0];
  return {
    expression: render.expression ?? undefined,
    colormapName: render.colormap_name ?? undefined,
    rescale: rescale ? `${rescale[0]},${rescale[1]}` : undefined,
  };
}

// The fields of the view's controls for a look, the other way round: what "Apply" would send back to make the same
// picture. Where a view starts from a layer, the controls show what the layer was made with (NM4-50).
export function pendingFieldsOf(render: AppliedRender): { pendingColormapName: string; pendingVmin: string; pendingVmax: string } {
  const [vmin = '', vmax = ''] = (render.rescale ?? '').split(',');
  return { pendingColormapName: render.colormapName ?? '', pendingVmin: vmin, pendingVmax: vmax };
}

// What the disabled "Apply" and "Save" say in their tooltips (the view of scenes and of a result).
export const NOTHING_TO_APPLY = 'Nothing to apply: the map shows these values';
export const NOTHING_TO_SAVE = 'Nothing to save: the layer is saved as it is drawn';

type PendingFields = { pendingColormapName: string; pendingVmin: string; pendingVmax: string };

// What the fields of the controls ask for: the colormap, and a range once both ends are typed.
export function lookOfPendingFields(p: PendingFields): AppliedRender {
  const vmin = p.pendingVmin.trim();
  const vmax = p.pendingVmax.trim();
  return {
    colormapName: p.pendingColormapName || undefined,
    rescale: vmin !== '' && vmax !== '' ? `${vmin},${vmax}` : undefined,
  };
}

// Whether "Apply" would draw anything else than the map shows now.
export function lookChanged(applied: AppliedRender, p: PendingFields): boolean {
  const asked = lookOfPendingFields(p);
  return (applied.colormapName || undefined) !== asked.colormapName || (applied.rescale || undefined) !== asked.rescale;
}

// --- one colour scale for a preview and a result (M4-32b, M4-19c) --------------------

// What a measure says of one band, for the colour scale: the fields that are numbers. A result gets it from
// its results document, a preview from `/statistics` with the steps.
export interface BandStats {
  minimum: number | null;
  maximum: number | null;
  percentile2: number | null;
  percentile98: number | null;
}

export interface ResultStats {
  bands: BandStats[];
  // The values come from a Band math step: what an index looks like is judged by the values.
  expression: boolean;
}

// An index has no unit and lies in −1…1, and is drawn so, in the same colours, wherever it is drawn.
export const INDEX_RANGE: readonly [number, number] = [-1, 1];
export const INDEX_COLORMAP = 'rdylgn';

// The colormap of values whose quantity is not known; `rdylgn` is for indices.
export const MEASURED_COLORMAP = 'viridis';

export interface Scale {
  low: number;
  high: number;
  colormap: string;
}

const smallest = (values: Array<number | null>) => Math.min(...values.filter((v): v is number => v !== null));
const largest = (values: Array<number | null>) => Math.max(...values.filter((v): v is number => v !== null));

const finite = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);

// The statistics of the bands of a results document (`properties.bands`) or of the area statistics of the tiler
// (`bands`, NM4-19): both carry the object of the results document per band. `null` where no band names a value.
export function statsFrom(bands: unknown, expression: boolean): ResultStats | null {
  if (!Array.isArray(bands) || bands.length === 0) return null;
  const read = bands.map((band): BandStats => {
    const stats = (band as { statistics?: Record<string, unknown> } | null)?.statistics;
    // `count` 0: the band has no valid pixel, and its statistics name no value.
    const usable = stats !== null && typeof stats === 'object' && (finite(stats.count) ?? 0) > 0;
    return {
      minimum: usable ? finite(stats.minimum) : null,
      maximum: usable ? finite(stats.maximum) : null,
      percentile2: usable ? finite(stats.percentile_2) : null,
      percentile98: usable ? finite(stats.percentile_98) : null,
    };
  });
  if (read.every((band) => band.minimum === null && band.maximum === null)) return null;
  return { bands: read, expression };
}

// The scale the measured values call for, or `null` where they name none. In order:
//  1. an index (a Band math result whose 2–98 % lie in −1…1 for every band; the minimum…maximum where a band has
//     no percentiles) is drawn at −1…1 in `rdylgn`, so that indices can be compared with one another. Single
//     pixels beyond −1…1 do not make it another quantity (NM4-19, Otto, 28.10.2026), and a coarser read, which
//     smooths them away, picks the same scale as the exact one;
//  2. otherwise the 2–98 % of the measure, in `viridis`; the minimum…maximum where there are no percentiles.
export function scaleOf(stats: ResultStats | null): Scale | null {
  const present = stats?.bands.filter((band) => band.minimum !== null && band.maximum !== null) ?? [];
  if (!stats || present.length === 0) return null;
  const isIndex = present.every(
    (band) => (band.percentile2 ?? band.minimum!) >= INDEX_RANGE[0] && (band.percentile98 ?? band.maximum!) <= INDEX_RANGE[1],
  );
  if (stats.expression && isIndex) {
    return { low: INDEX_RANGE[0], high: INDEX_RANGE[1], colormap: INDEX_COLORMAP };
  }
  let low = smallest(present.map((band) => band.percentile2));
  let high = largest(present.map((band) => band.percentile98));
  if (!(low < high)) {
    low = smallest(present.map((band) => band.minimum));
    high = largest(present.map((band) => band.maximum));
  }
  return low < high ? { low, high, colormap: MEASURED_COLORMAP } : null;
}
