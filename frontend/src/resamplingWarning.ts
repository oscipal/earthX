// The warning that comes before a job whose bands are brought to a common grid (NM4-65 part 7, Otto, 31.10.2026), in place of the
// exclamation mark "Resampled to a common grid": what is resampled to which grid, by which method, and what that means for the
// values. The facts are the server's (`resampling` of the estimate); this makes the short English text of them.

import type { EstimateDocument, Resampling } from './processing';

export interface ResamplingPart {
  // Which job of a batch (the pass or the scene); `null` for a lone job.
  label: string | null;
  resampling: Resampling;
}

// The facts of an estimate, or of every part of a batch that has some; empty where nothing is resampled.
export function resamplingParts(estimate: EstimateDocument | null, batch: readonly { unit: { label: string }; doc: EstimateDocument | null }[] | null): ResamplingPart[] {
  if (batch) return batch.flatMap((part) => (part.doc?.resampling ? [{ label: part.unit.label, resampling: part.doc.resampling }] : []));
  return estimate?.resampling ? [{ label: null, resampling: estimate.resampling }] : [];
}

const METHODS: Record<string, { name: string; meaning: string }> = {
  nearest: {
    name: 'nearest neighbour',
    meaning: 'Pixels are repeated, so no new values appear; but at the pixel edges the values change, and the pixel counts differ from the source.',
  },
  bilinear: {
    name: 'bilinear interpolation',
    meaning: 'Each new pixel is a weighted mean of its neighbours, so the values are new and smoothed, and the extremes of the source flatten.',
  },
};

const FALLBACK_MEANING = 'The values at the pixel edges change, and the pixel counts differ from the source.';

export const metres = (resolution: number): string => `${Number(resolution.toPrecision(6))} m`;

export interface ResamplingText {
  label: string | null;
  // The grid and the method, in one sentence.
  grid: string;
  // The bands that are resampled, with their own pixel size; `null` where only scenes are.
  bands: string | null;
  // The scenes of another UTM zone; `null` where there are none.
  scenes: string | null;
  // What it means for the values.
  meaning: string;
}

export function describeResampling(part: ResamplingPart): ResamplingText {
  const { grid, method, bands, scenes } = part.resampling;
  const known = METHODS[method];
  const gridCrs = grid.crs ? ` in ${grid.crs}` : '';
  return {
    label: part.label,
    grid: `The values are brought to one grid of ${metres(grid.resolution)}${gridCrs}, by ${known?.name ?? method}.`,
    bands:
      bands.length > 0
        ? `Resampled: ${bands.map((b) => `${b.band} (${metres(b.resolution)}${b.crs && b.crs !== grid.crs ? `, ${b.crs}` : ''})`).join(', ')}.`
        : null,
    scenes: scenes ? `${scenes.count} of ${scenes.of} scenes lie in another UTM zone and are warped${scenes.crs ? ` to ${scenes.crs}` : ' to the zone of most scenes'}.` : null,
    meaning: known?.meaning ?? FALLBACK_MEANING,
  };
}
