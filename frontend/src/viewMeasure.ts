// The measure of the view over the AOI (UI-03e, Otto, 3.11.2026): "auto-scale", "Enhance contrast" and the histograms of "Scale" ask the
// same question, and where the view is cropped to the AOI it is asked of the area, with the route of the tiler that counts an order as the
// job does (`postAreaStatistics`, NM4-19), not of the first whole scene.
//
// Every range of the page is physical (M5-68): that route measures in physical values (`scale`/`offset` of the item applied) and its
// answer stays as it is; the statistics of a scene the tile server reads from the stored numbers of the file are turned into physical
// values here (`measureView`), and a range into stored ones only where a tile URL is built (`storedRescale`, `buildTileUrl`).
//
// The order is built here and never leaves the page but in the body of that one request; its text lives in memory (`areaAnswers`) and goes
// into no URL, storage, log or message. Where the tiler does not take it (`413` too many files, `422` an order or area it refuses) the
// first whole scene is measured as before, and the caller says so.

import { fetchStatisticsAt, HttpError, postAreaStatistics, withHistogram, withPercentiles, type AreaStatistics, type BandStatistics } from './api';
import { significant } from './numberFormat';
import type { QuickPreset } from './quickPresets';
import { canonicalJson, type Order } from './processing';
import { bandsOf, bandSources, isAoi, orderAoi } from './processingOrder';
import type { Collection, StacItem } from './types';

// Said, always the same, wherever the first whole scene stands in for the area of the crop (Otto, 3.11.2026, zu #282): in the view next to
// the fields, the reason behind an (i). No fall-back is silent.
export const MEASURED_ON_SCENE = 'Measured on the first scene';

const REFUSED_TOO_MANY = 'The tiler measures at most 16 files (scenes times bands) in one go; this image has more.';
const REFUSED_ORDER = 'The tiler does not take the area of this image.';

// What the raw number of the file becomes: `raw · scale + offset`.
export interface BandScaling {
  scale: number;
  offset: number;
}

// The question for the area of the view: the order the tiler counts.
export interface AreaQuestion {
  datasetId: string;
  order: Order;
}

// How the statistics of what the view draws are asked: of the area where the view is cropped and the tiler can take it, always of the first
// scene (`sceneUrl`, the statistics route of the tile server) as the fall-back.
export interface ViewMeasure {
  sceneUrl: string;
  // The scaling of the stored numbers the scene route answers in: the asset of one band it measures, where the item states one; `null`
  // for an index or a step (physical already) and for an unscaled asset.
  scaling: BandScaling | null;
  area: AreaQuestion | null;
  // Why the view is cropped and the area was not asked for (scenes or bands unknown, no COG); `null` otherwise.
  skipped: string | null;
  // Says whether two measures ask the same question; it holds the order, and so the AOI, and is kept in memory only.
  key: string;
}

const INPUT_NAME = 'input';

// Twelve significant digits, as the registry writes a physical value (`BandScaling.physical`): 1200 · 0.0001 − 0.1 is 0.02.
const tidy = (value: number): number => significant(value, 12);

// A stored value in physical terms, and back.
export const physicalOf = (raw: number, { scale, offset }: BandScaling): number => tidy(raw * scale + offset);
export const rawOf = (value: number, { scale, offset }: BandScaling): number => tidy((value - offset) / scale);

// The scaling of an asset of one band as the item states it; `null` where it cannot be turned back (a scale of 0 or below).
export function scalingOfAsset(item: StacItem, asset: string): BandScaling | null {
  const described = item.assets?.[asset];
  const { scale, offset } = (described ? bandsOf(described)?.[0] : undefined) ?? {};
  const one = { scale: scale ?? 1, offset: offset ?? 0 };
  return one.scale > 0 && Number.isFinite(one.scale) && Number.isFinite(one.offset) ? one : null;
}

// A physical range of a look (`AppliedRender.rescale`: one pair, or three joined by `;`) in the stored values of a tile of one band, or
// the other way round with `physicalOf`. An end that is no number stays as it is.
export function rescaleThrough(rescale: string, convert: (value: number) => number): string {
  return rescale
    .split(';')
    .map((pair) => pair.split(',').map((end) => (end.trim() !== '' && Number.isFinite(Number(end)) ? String(convert(Number(end))) : end)).join(','))
    .join(';');
}

// The range of `rescale` as a tile URL of stored values takes it (M5-68): the one place a physical range becomes a stored one. A range
// the registry gives in stored values (`stored`) and a picture without scaling keep theirs.
export function storedRescale(rescale: string, stored: boolean | undefined, scaling: BandScaling | null | undefined): string {
  return stored || !scaling ? rescale : rescaleThrough(rescale, (value) => rawOf(value, scaling));
}

// The scaling of every asset of one band of `item` that has one other than 1 and 0, for `DownloadedInfo.scalings`; `undefined` for none.
export function scaledAssetsOf(item: StacItem): Record<string, BandScaling> | undefined {
  const scaled = Object.keys(item.assets).flatMap((asset) => {
    const one = bandsOf(item.assets[asset])?.length === 1 ? scalingOfAsset(item, asset) : null;
    return one && (one.scale !== 1 || one.offset !== 0) ? [[asset, one] as const] : [];
  });
  return scaled.length > 0 ? Object.fromEntries(scaled) : undefined;
}

// The area question for what the view draws: `null` where the view is not cropped (nothing to say), `{ reason }` where it is and none can be
// asked: scenes the page does not know, an asset of no known bands, a source that is no COG. Scenes scaled differently are no reason: the
// answer is physical, and a physical range fits each of them (M5-68).
//  - a preset: its steps as a job runs them (an index: the one `band_math` step of `indexOrdersOfScenes`), its band or bands as the output;
//  - a band or the colour picture: no step, the bands of the asset as the output (`float32`, so that nothing is cut off).
export function areaQuestionOf(args: {
  datasetId: string;
  collection: Collection | undefined;
  items: readonly StacItem[];
  aoi: GeoJSON.Geometry | null;
  index: QuickPreset | null;
  asset: string;
}): AreaQuestion | { reason: string } | null {
  const { datasetId, collection, items, aoi, index, asset } = args;
  if (!isAoi(aoi)) return null;
  if (items.length === 0) return { reason: 'The scenes of this image are not all known to the page.' };
  if (collection?.['earthx:format'] !== 'cog') return { reason: 'The area of this dataset cannot be measured: it is no cloud-optimized GeoTIFF.' };
  const input = { name: INPUT_NAME, dataset: datasetId, groups: [items.map((item) => item.id).sort()] };
  const output = (bands: string[]) => ({ kind: 'raster' as const, format: 'cog' as const, dtype: 'float32', bands });
  if (index) {
    const steps = index.steps.map((step) => ({ op: step.op, op_version: step.opVersion, params: step.params }));
    return { datasetId, order: { recipe_version: 2, inputs: [input], aoi: orderAoi(aoi), steps, output: output(index.bands) } };
  }
  let names: string[] = [];
  for (const item of items) {
    const source = bandSources(item, 'cog', null, collection).find((one) => one.asset === asset);
    if (!source || source.names.length === 0 || (names.length > 0 && names.join() !== source.names.join())) return { reason: 'The items do not describe the bands of this image.' };
    names = source.names;
  }
  if (names.length === 0) return { reason: 'The items do not describe the bands of this image.' };
  return { datasetId, order: { recipe_version: 2, inputs: [input], aoi: orderAoi(aoi), steps: [], output: output(names) } };
}

const KEYS_OF_VALUES = /^(minimum|maximum|min|max|mean|median|percentile_\d+)$/u;

// The statistics of a scene in the stored numbers of its file, in physical values. A scaling is linear and rising, so every value, every
// percentile and every edge of the histogram goes through the same line; the spread only grows by the scale.
export function inPhysicalValues(statistics: Record<string, unknown>, scaling: BandScaling): Record<string, unknown> {
  const physical = (value: number) => physicalOf(value, scaling);
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(statistics)) {
    if (KEYS_OF_VALUES.test(key) && typeof value === 'number') out[key] = physical(value);
    else if (key === 'stddev' && typeof value === 'number') out[key] = value * scaling.scale;
    else if (key === 'histogram' && Array.isArray(value) && Array.isArray(value[1])) out[key] = [value[0], value[1].map((edge) => (typeof edge === 'number' ? physical(edge) : edge))];
    else out[key] = value;
  }
  return out;
}

// The answer of the route as the statistics of the tile server have them (`Record<string, BandStatistics>`: by band, `min`/`max` and the
// percentiles at hand), so that what reads those reads these.
export function statisticsOfArea(answer: AreaStatistics): Record<string, BandStatistics> {
  const out: Record<string, BandStatistics> = {};
  answer.bands.forEach((band, index) => {
    out[band.name || String(index)] = { ...band.statistics, min: band.statistics.minimum, max: band.statistics.maximum, unit: band.unit } as BandStatistics;
  });
  return out;
}

// The answers of the route once per order (the page asks for the range, the percentiles and the histograms of one picture). The text of an
// order carries its AOI, so the keys live here in memory and nowhere else.
const ANSWERS_KEPT = 8;
const answers = new Map<string, Promise<AreaStatistics>>();

function answerTo(question: AreaQuestion): Promise<AreaStatistics> {
  const key = canonicalJson(question.order);
  let answer = answers.get(key);
  if (!answer) {
    if (answers.size >= ANSWERS_KEPT) answers.delete(answers.keys().next().value!);
    answer = postAreaStatistics(question.datasetId, question.order);
    answers.set(key, answer);
    // A failed question is asked again next time.
    answer.catch(() => {
      if (answers.get(key) === answer) answers.delete(key);
    });
  }
  return answer;
}

// For the tests: forget every answer.
export function forgetAreaAnswers(): void {
  answers.clear();
  refused.clear();
}

// The reason the tiler gave for not measuring a question, by `ViewMeasure.key`, for as long as it is refused: the view shows it beside the
// fields once the first measure of that picture (its histograms) is in.
const refused = new Map<string, string>();

// Why the first scene stands in for the area of this measure, or `null` where the area is measured (or the view is not cropped).
export function fallbackReasonOf(measure: ViewMeasure): string | null {
  return measure.skipped ?? refused.get(measure.key) ?? null;
}

// The statistics of what the view draws, by band, in physical values. `fellBack` is the reason, where the first whole scene was
// measured although the view is cropped: the area was not asked for (`skipped`) or the tiler did not take it (`413`, `422`). Any other
// failure passes to the caller, as it always did.
//  - `percentiles`: whole percents the scene route is asked to add (the area route has every whole percent);
//  - `histogram`: with the histogram of each band.
export async function measureView(
  measure: ViewMeasure,
  { percentiles = [], histogram = false }: { percentiles?: readonly number[]; histogram?: boolean } = {},
): Promise<{ statistics: Record<string, BandStatistics>; fellBack: string | null }> {
  const scene = async () => {
    const asked = withPercentiles(measure.sceneUrl, percentiles);
    const statistics = await fetchStatisticsAt(histogram ? withHistogram(asked) : asked);
    const { scaling } = measure;
    if (!scaling) return statistics;
    return Object.fromEntries(Object.entries(statistics).map(([band, values]) => [band, inPhysicalValues(values as Record<string, unknown>, scaling) as BandStatistics]));
  };
  if (!measure.area) return { statistics: await scene(), fellBack: measure.skipped };
  try {
    const statistics = statisticsOfArea(await answerTo(measure.area));
    refused.delete(measure.key);
    return { statistics, fellBack: null };
  } catch (error) {
    // The status alone is told: an order the page built wrongly must not pass unnoticed, but nothing of it or its answer is kept.
    if (!(error instanceof HttpError && (error.status === 413 || error.status === 422))) throw error;
    console.warn(`area statistics: status ${error.status}; measuring the first whole scene`);
    const reason = error.status === 413 ? REFUSED_TOO_MANY : REFUSED_ORDER;
    refused.set(measure.key, reason);
    return { statistics: await scene(), fellBack: reason };
  }
}
