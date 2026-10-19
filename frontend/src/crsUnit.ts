// What the resolution of `reproject` means (M4-13c-3, plan §3.7): the unit of the
// target CRS from `GET /processing/crs/{code}`, and for degrees the size of a cell
// on the ground at the latitude of the area. The wording is the panel's; the
// numbers come from the server's answer and the WGS84 series below.

import type { CrsInfo } from './processing';
import type { Bbox } from './types';

// What the `crs` parameter takes (`ReprojectParams.crs`); only such a value is asked for.
export const CRS_PATTERN = /^EPSG:[0-9]{4,6}$/u;

// How long the field rests before the unit is asked for.
export const CRS_DELAY_MS = 300;

// What the store knows about a code. A lookup in flight is no entry: the field
// derives it. Only a refusal (`422`) blocks the review; an answer that could not
// be fetched is a hint, and the next change of the code asks again.
export type CrsEntry =
  | { state: 'ready'; info: CrsInfo }
  | { state: 'refused'; message: string }
  | { state: 'error'; message: string };

// Metres per degree of latitude (north–south) and of longitude (east–west) at
// the latitude `phi`, in degrees, on WGS84 (the series of the plan; the error
// stays under 0.1 %).
export function metresPerDegree(phi: number): { northSouth: number; eastWest: number } {
  const r = (phi * Math.PI) / 180;
  return {
    northSouth: 111132.954 - 559.822 * Math.cos(2 * r) + 1.175 * Math.cos(4 * r),
    eastWest: 111412.84 * Math.cos(r) - 93.5 * Math.cos(3 * r) + 0.118 * Math.cos(5 * r),
  };
}

// The middle latitude of the boxes: halfway between the southernmost and the
// northernmost edge. `null` for none.
export function midLatitude(boxes: readonly Bbox[]): number | null {
  if (boxes.length === 0) return null;
  const south = Math.min(...boxes.map((b) => b[1]));
  const north = Math.max(...boxes.map((b) => b[3]));
  return Number.isFinite(south) && Number.isFinite(north) ? (south + north) / 2 : null;
}

// A number as plain digits, without an exponent.
function plain(value: number): string {
  return value.toLocaleString('en-US', { maximumFractionDigits: 12, useGrouping: false });
}

// A length on the ground: to the centimetre below 10 m, to the metre above.
function metres(value: number): string {
  return plain(value < 10 ? Math.round(value * 100) / 100 : Math.round(value));
}

function latitudeText(phi: number): string {
  return `${Math.abs(phi).toFixed(1)}° ${phi < 0 ? 'S' : 'N'}`;
}

// "Cell size: …" for a resolution in the units of `info`'s CRS, or `null` while
// there is no usable number. `latitude` is the middle latitude of the area; without
// it, degrees stay degrees.
export function cellSizeText(info: CrsInfo, resolution: number, latitude: number | null): string | null {
  if (!Number.isFinite(resolution) || resolution <= 0) return null;
  const { name, kind, toBase } = info.unit;
  const size = plain(resolution);
  if (!Number.isFinite(toBase) || toBase <= 0) return `Cell size: ${size} ${name} × ${size} ${name}`;
  if (kind === 'angular') {
    const label = name === 'degree' ? '°' : ` ${name}`;
    const own = `Cell size: ${size}${label} × ${size}${label}`;
    if (latitude === null || !Number.isFinite(latitude) || Math.abs(latitude) > 90) return own;
    const degrees = resolution * toBase;
    const ground = metresPerDegree(latitude);
    return (
      `${own} ≈ ${metres(degrees * ground.northSouth)} m (N–S) × ${metres(degrees * ground.eastWest)} m (E–W)` +
      ` at ${latitudeText(latitude)}`
    );
  }
  if (name === 'metre') return `Cell size: ${size} m × ${size} m`;
  return `Cell size: ${size} ${name} × ${size} ${name} (≈ ${metres(resolution * toBase)} m)`;
}

// Why the review waits: a step whose target CRS the server turned away.
export function crsBlockReason(
  steps: readonly { op: string; values: Record<string, unknown> }[],
  crs: Readonly<Record<string, CrsEntry>>,
): string | null {
  for (const step of steps) {
    if (step.op !== 'reproject') continue;
    const code = step.values.crs;
    const entry = typeof code === 'string' ? crs[code] : undefined;
    if (entry?.state === 'refused') return entry.message;
  }
  return null;
}
