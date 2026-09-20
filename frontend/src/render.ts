// Turns a `/statistics` answer into one stretch range for the tile URL
// (adr/0006 §3.4, F18): the 2nd/98th percentile across every band the asset
// carries, so a multi-band asset (e.g. a true-colour composite) gets one
// shared range rather than one per band — TiTiler's `rescale` broadcasts a
// single pair to every output band when only one is given.

import type { BandStatistics } from './api';

export function autoRescale(stats: Record<string, BandStatistics>): [number, number] | null {
  const bands = Object.values(stats);
  const los = bands.map((b) => b.percentile_2).filter((v) => typeof v === 'number' && Number.isFinite(v));
  const his = bands.map((b) => b.percentile_98).filter((v) => typeof v === 'number' && Number.isFinite(v));
  if (los.length === 0 || his.length === 0) return null;
  return [Math.min(...los), Math.max(...his)];
}
