// Turns a `/statistics` answer into one stretch range for the tile URL
// (adr/0006 §3.4, F18): the 2nd/98th percentile across every band the asset
// carries, so a multi-band asset (e.g. a true-colour composite) gets one
// shared range rather than one per band — TiTiler's `rescale` broadcasts a
// single pair to every output band when only one is given.

import type { BandStatistics } from './api';
import type { AppliedRender, EarthxDefaultRender } from './types';

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
