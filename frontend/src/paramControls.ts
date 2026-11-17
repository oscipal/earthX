// What the parameters of a step preset are offered as under "Quick processing" (M5-14, Otto, 17.11.2026), and the arithmetic of the dial for
// an angle from north. Pure functions; the controls are `components/PresetParamControls.tsx` and `components/AngleDial.tsx`.

import type { Field } from './schemaForm';

// What a field can be offered as; `null` for a field the controls do not offer (no bounds to slide between).
export type ParamControl = 'choice' | 'dial' | 'slider';
export function controlOf(field: Field): ParamControl | null {
  if (field.kind === 'enum' && (field.options?.length ?? 0) > 1) return 'choice';
  if (field.kind !== 'number' || field.minimum === undefined) return null;
  if (field.unit === 'deg' && field.minimum === 0 && field.exclusiveMaximum === 360) return 'dial';
  return field.maximum !== undefined && field.maximum > field.minimum ? 'slider' : null;
}

// One degree per arrow key, fifteen with Shift (Otto, 17.11.2026).
const STEP = 1;
const BIG_STEP = 15;

// The angle in whole degrees, 0 to 359, of a point seen from the centre of the dial: north up, clockwise.
export function angleAt(dx: number, dy: number): number {
  if (dx === 0 && dy === 0) return 0;
  const degrees = (Math.atan2(dx, -dy) * 180) / Math.PI;
  return ((Math.round(degrees) % 360) + 360) % 360;
}

// The angle after a key, or `null` for a key the dial does not take.
export function angleAfterKey(angle: number, key: string, shift: boolean): number | null {
  const step = shift ? BIG_STEP : STEP;
  const by = key === 'ArrowRight' || key === 'ArrowUp' ? step : key === 'ArrowLeft' || key === 'ArrowDown' ? -step : null;
  return by === null ? null : (((Math.round(angle) + by) % 360) + 360) % 360;
}


// A number typed for a parameter, as the parameter takes it (Otto, 17.11.2026): whole degrees within its bounds, a value outside them at the
// nearer bound; an angle of a full circle (the dial) takes 360 as 0. `null` for a text that is no number.
export function paramNumberOf(field: Field, text: string): number | null {
  const typed = Number(text.trim().replace(',', '.'));
  if (text.trim() === '' || !Number.isFinite(typed)) return null;
  const low = field.minimum ?? field.exclusiveMinimum ?? -Infinity;
  const high = field.maximum ?? field.exclusiveMaximum ?? Infinity;
  const kept = Math.round(Math.min(high, Math.max(low, typed)));
  return controlOf(field) === 'dial' ? ((kept % 360) + 360) % 360 : kept;
}
