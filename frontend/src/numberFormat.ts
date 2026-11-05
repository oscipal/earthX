// NM4-21 (UI-04 part 6): the one way a number is shown. Only the display changes: what goes to the API, into a recipe, a permalink or a file
// keeps its full value, and a field keeps exactly what the user typed.
//
// - At most three decimals, without trailing zeros: 12.3456 → "12.346", 2 → "2".
// - A very small or a very large amount is scientific, with up to three significant digits and no "+": 0.000000052 → "5.2e-8",
//   1234567 → "1.23e6". "Very" is below 0.001 (zero excepted) and from 1e6.
// - A number and its unit are separated by a space ("4.2 MB", "12 s"); a percent and a degree stand close to it ("50%", "52.5°").
// - `NaN` is "—", the infinities are "∞" and "-∞". The minus is the plain hyphen, so that a shown value can be typed back into a field.
//
// Nothing else in the front end calls `toFixed`, `toPrecision`, `toExponential` or `toLocaleString` for a number (`uiRules.test.ts`).

const SMALL = 0.001;
const LARGE = 1e6;
const DECIMALS = 3;

function scientific(abs: number): string {
  const [mantissa, exponent] = abs.toExponential(DECIMALS - 1).split('e');
  const digits = mantissa.includes('.') ? mantissa.replace(/0+$/u, '').replace(/\.$/u, '') : mantissa;
  return `${digits}e${Number(exponent)}`;
}

// A number for the eye.
export function formatNumber(value: number): string {
  if (Number.isNaN(value)) return '—';
  if (!Number.isFinite(value)) return value > 0 ? '∞' : '-∞';
  if (value === 0) return '0';
  const sign = value < 0 ? '-' : '';
  const abs = Math.abs(value);
  if (abs < SMALL || abs >= LARGE) return sign + scientific(abs);
  const fixed = abs.toFixed(DECIMALS);
  // 999999.9996 rounds up to a million: it is a large number then.
  if (Number(fixed) >= LARGE) return sign + scientific(abs);
  return sign + String(Number(fixed));
}

// A value rounded to `digits` decimals, still a number: where a track of a slider is coarser than the three decimals of the display.
export const roundTo = (value: number, digits: number): number => Number(value.toFixed(digits));

// 0–100 and the like: "50%", "42.5%", no space (English).
export const formatPercent = (value: number): string => (Number.isFinite(value) ? `${formatNumber(value)}%` : formatNumber(value));

// A number the user may type back: the shown text of `value`, or `''` for none. The fields of a range take their start values from the
// statistics through this; what is typed afterwards is never touched.
export const fieldNumber = (value: number): string => (Number.isFinite(value) ? formatNumber(value) : '');

// --- sizes, which have their own steps -------------------------------------------------------------------------------

// A file size: bytes, kB (whole), MB and GB (one decimal).
export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return formatNumber(bytes);
  if (bytes >= 1e9) return `${formatOneDecimal(bytes / 1e9)} GB`;
  if (bytes >= 1e6) return `${formatOneDecimal(bytes / 1e6)} MB`;
  if (bytes >= 1e3) return `${Math.round(bytes / 1e3)} kB`;
  return `${bytes} B`;
}

// An image size in megapixels: whole from ten, one decimal below.
export function formatMegapixels(pixels: number): string {
  if (!Number.isFinite(pixels) || pixels < 0) return formatNumber(pixels);
  const mp = pixels / 1e6;
  return mp >= 10 ? `${Math.round(mp)} MP` : `${formatOneDecimal(mp)} MP`;
}

// One decimal at most, none trailing: "4.2", "4".
function formatOneDecimal(value: number): string {
  return String(Number(value.toFixed(1)));
}

// "1 unit", "2.5 units": the cost unit of the estimate of a job.
export const formatUnits = (units: number): string => `${formatNumber(units)} ${units === 1 ? 'unit' : 'units'}`;

// The latitude in the cell-size line: one decimal and a hemisphere, "52.5° N".
export const formatLatitude = (phi: number): string => `${Math.abs(phi).toFixed(1)}° ${phi < 0 ? 'S' : 'N'}`;

// What a user typed, given back as digits without an exponent and without the noise of a float: the line of the cell size repeats the
// resolution of the field, and 0.0000001 stays 0.0000001 (Otto, M4-13c-3). The only place a number may be longer than three decimals.
export function formatPlain(value: number): string {
  if (!Number.isFinite(value)) return formatNumber(value);
  const text = value.toFixed(12).replace(/0+$/u, '').replace(/\.$/u, '');
  return text === '-0' ? '0' : text;
}

// --- dates ---------------------------------------------------------------------------------------------------------------

const MONTH_DAY = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short' });
const HOUR_MINUTE = new Intl.DateTimeFormat('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false });
const YEAR = new Intl.DateTimeFormat('en-GB', { year: 'numeric' });

// A moment of the browser's time: "31 Oct, 14:02"; the year only when it is not this one ("5 Jan 2027, 14:02"). The text as it came where it
// is no date.
export function formatMoment(iso: string, now: number = Date.now()): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const year = YEAR.format(date) === YEAR.format(now) ? '' : ` ${YEAR.format(date)}`;
  return `${MONTH_DAY.format(date)}${year}, ${HOUR_MINUTE.format(date)}`;
}

// A day of the browser's time, the same in every browser and language: "2026-12-03". The text as it came where it is no date.
export function formatDay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  const two = (n: number): string => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`;
}
