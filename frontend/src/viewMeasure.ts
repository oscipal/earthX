// The measure of the view over the AOI (UI-03e, Otto, 3.11.2026): "auto-scale", "Enhance contrast" and the histograms of "Scale" ask the
// same question, and where the view is cropped to the AOI it is asked of the area, with the route of the tiler that counts an order as the
// job does (`postAreaStatistics`, NM4-19), not of the first whole scene.
//
// That route measures in physical values (`scale`/`offset` of the item applied), while the tiles of a band and of the colour picture draw
// the raw numbers of the file: the answer of a band is turned back with the item's own scaling, so that a range measured here fits the
// tiles. An index is computed from physical values on both sides and stays as it is.
//
// The order is built here and never leaves the page but in the body of that one request; its text lives in memory (`areaAnswers`) and goes
// into no URL, storage, log or message. Where the tiler does not take it (`413` too many files, `422` an order or area it refuses) the
// first whole scene is measured as before, and the caller says so.

import { fetchStatisticsAt, HttpError, postAreaStatistics, withHistogram, withPercentiles, type AreaStatistics, type BandStatistics } from './api';
import type { IndexPreset } from './indexPresets';
import { canonicalJson, type Order } from './processing';
import { bandsOf, bandSources, isArea, orderAoi } from './processingOrder';
import type { Collection, StacItem } from './types';

// Said, always the same, wherever the first whole scene stands in for the area of the crop (Otto, 3.11.2026, zu #282): in the view next to
// the fields, the reason behind a ⓘ. No fall-back is silent.
export const MEASURED_ON_SCENE = 'Measured on the first scene';

const REFUSED_TOO_MANY = 'The tiler measures at most 16 files (scenes times bands) in one go; this image has more.';
const REFUSED_ORDER = 'The tiler does not take the area of this image.';

// What the raw number of the file becomes: `raw · scale + offset`.
export interface BandScaling {
  scale: number;
  offset: number;
}

// The question for the area of the view: the order the tiler counts, and how to read each band of its answer.
export interface AreaQuestion {
  datasetId: string;
  order: Order;
  scalings: BandScaling[];
}

// How the statistics of what the view draws are asked: of the area where the view is cropped and the tiler can take it, always of the first
// scene (`sceneUrl`, the statistics route of the tile server) as the fall-back.
export interface ViewMeasure {
  sceneUrl: string;
  area: AreaQuestion | null;
  // Why the view is cropped and the area was not asked for (nothing to turn back into raw values, scenes unknown); `null` otherwise.
  skipped: string | null;
  // Says whether two measures ask the same question; it holds the order, and so the AOI, and is kept in memory only.
  key: string;
}

const INPUT_NAME = 'input';

const NOT_INVERTIBLE = 'A band of this image has a scale that cannot be turned back into the stored values.';

// The scaling of each band of an asset as the item states it, or `null` where a band has one that cannot be turned back.
function scalingsOf(item: StacItem, asset: string, count: number): BandScaling[] | null {
  const described = bandsOf(item.assets[asset]);
  const scalings: BandScaling[] = [];
  for (let i = 0; i < count; i += 1) {
    const { scale, offset } = described?.[i] ?? {};
    const one = { scale: scale ?? 1, offset: offset ?? 0 };
    if (!(one.scale > 0) || !Number.isFinite(one.scale) || !Number.isFinite(one.offset)) return null;
    scalings.push(one);
  }
  return scalings;
}

const sameScalings = (a: BandScaling[], b: BandScaling[]) => a.length === b.length && a.every((one, i) => one.scale === b[i].scale && one.offset === b[i].offset);

// The area question for what the view draws: `null` where the view is not cropped (nothing to say), `{ reason }` where it is and none can be
// asked: scenes the page does not know, an asset of no known bands, a source that is no COG, a scale that cannot be turned back, or scenes
// of the image whose bands are scaled differently (one range in raw values would then be right for none of them).
//  - an index: one `band_math` step as the job of a download runs it (`indexOrdersOfScenes`), that band as the output;
//  - a band or the colour picture: no step, the bands of the asset as the output (`float32`, so that nothing is cut off).
export function areaQuestionOf(args: {
  datasetId: string;
  collection: Collection | undefined;
  items: readonly StacItem[];
  aoi: GeoJSON.Geometry | null;
  index: IndexPreset | null;
  asset: string;
}): AreaQuestion | { reason: string } | null {
  const { datasetId, collection, items, aoi, index, asset } = args;
  if (!isArea(aoi)) return null;
  if (items.length === 0) return { reason: 'The scenes of this image are not all known to the page.' };
  if (collection?.['earthx:format'] !== 'cog') return { reason: 'The area of this dataset cannot be measured: it is no cloud-optimized GeoTIFF.' };
  const input = { name: INPUT_NAME, dataset: datasetId, groups: [items.map((item) => item.id).sort()] };
  const output = (bands: string[]) => ({ kind: 'raster' as const, format: 'cog' as const, dtype: 'float32', bands });
  if (index) {
    const step = { op: 'band_math', op_version: 2, params: { expression: index.expression, name: index.name } };
    return { datasetId, order: { recipe_version: 2, inputs: [input], aoi: orderAoi(aoi), steps: [step], output: output([index.name]) }, scalings: [{ scale: 1, offset: 0 }] };
  }
  let names: string[] = [];
  let scalings: BandScaling[] | null = null;
  for (const item of items) {
    const source = bandSources(item, 'cog', null, collection).find((one) => one.asset === asset);
    if (!source || source.names.length === 0 || (names.length > 0 && names.join() !== source.names.join())) return { reason: 'The items do not describe the bands of this picture.' };
    const own = scalingsOf(item, asset, source.names.length);
    if (!own) return { reason: NOT_INVERTIBLE };
    if (scalings && !sameScalings(scalings, own)) return { reason: 'The scenes of this image are scaled differently, so one range would not fit them all.' };
    names = source.names;
    scalings = own;
  }
  if (!scalings) return { reason: 'The items do not describe the bands of this picture.' };
  return { datasetId, order: { recipe_version: 2, inputs: [input], aoi: orderAoi(aoi), steps: [], output: output(names) }, scalings };
}

const KEYS_OF_VALUES = /^(minimum|maximum|min|max|mean|median|percentile_\d+)$/u;

// One band of the answer, its numbers back in the raw values the tiles draw. A scaling is linear and rising, so every value, every
// percentile and every edge of the histogram goes through the same line; the spread only grows by the scale.
export function inRawValues(statistics: Record<string, unknown>, { scale, offset }: BandScaling): Record<string, unknown> {
  const raw = (value: number) => (value - offset) / scale;
  const out: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(statistics)) {
    if (KEYS_OF_VALUES.test(key) && typeof value === 'number') out[key] = raw(value);
    else if (key === 'stddev' && typeof value === 'number') out[key] = value / scale;
    else if (key === 'histogram' && Array.isArray(value) && Array.isArray(value[1])) out[key] = [value[0], value[1].map((edge) => (typeof edge === 'number' ? raw(edge) : edge))];
    else out[key] = value;
  }
  return out;
}

// The answer of the route as the statistics of the tile server have them (`Record<string, BandStatistics>`: by band, `min`/`max` and the
// percentiles at hand), so that what reads those reads these.
export function statisticsOfArea(answer: AreaStatistics, scalings: readonly BandScaling[]): Record<string, BandStatistics> {
  const out: Record<string, BandStatistics> = {};
  answer.bands.forEach((band, index) => {
    const values = scalings[index] ? inRawValues(band.statistics, scalings[index]) : band.statistics;
    out[band.name || String(index)] = { ...values, min: values.minimum, max: values.maximum, unit: band.unit } as BandStatistics;
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

// The statistics of what the view draws, by band, in the values the tiles draw. `fellBack` is the reason, where the first whole scene was
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
    return fetchStatisticsAt(histogram ? withHistogram(asked) : asked);
  };
  if (!measure.area) return { statistics: await scene(), fellBack: measure.skipped };
  try {
    const statistics = statisticsOfArea(await answerTo(measure.area), measure.area.scalings);
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
