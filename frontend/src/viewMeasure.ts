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

// Said where the area could not be measured and the first whole scene stood in.
export const SCENE_MEASURE_NOTICE = 'The area could not be measured: the range is measured over the first whole scene.';

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
  // Says whether two measures ask the same question; it holds the order, and so the AOI, and is kept in memory only.
  key: string;
}

const INPUT_NAME = 'input';

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

// The area question for what the view draws, or `null` where none can be asked: no area, scenes the page does not know, an asset of
// no known bands, a source that is no COG, or scenes of the image whose bands are scaled differently (one range in raw values would then
// be right for none of them).
//  - an index: one `band_math` step as the job of a download runs it (`indexOrdersOfScenes`), that band as the output;
//  - a band or the colour picture: no step, the bands of the asset as the output (`float32`, so that nothing is cut off).
export function areaQuestionOf(args: {
  datasetId: string;
  collection: Collection | undefined;
  items: readonly StacItem[];
  aoi: GeoJSON.Geometry | null;
  index: IndexPreset | null;
  asset: string;
}): AreaQuestion | null {
  const { datasetId, collection, items, aoi, index, asset } = args;
  if (!isArea(aoi) || items.length === 0 || collection?.['earthx:format'] !== 'cog') return null;
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
    const own = source && source.names.length > 0 ? scalingsOf(item, asset, source.names.length) : null;
    if (!source || !own || (scalings && !sameScalings(scalings, own)) || (names.length > 0 && names.join() !== source.names.join())) return null;
    names = source.names;
    scalings = own;
  }
  if (!scalings) return null;
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
}

// The statistics of what the view draws, by band, in the values the tiles draw. `fellBack`: the area was asked for and the tiler did not
// take it (`413`, `422`); the first whole scene was measured instead. Any other failure passes to the caller, as it always did.
//  - `percentiles`: whole percents the scene route is asked to add (the area route has every whole percent);
//  - `histogram`: with the histogram of each band.
export async function measureView(
  measure: ViewMeasure,
  { percentiles = [], histogram = false }: { percentiles?: readonly number[]; histogram?: boolean } = {},
): Promise<{ statistics: Record<string, BandStatistics>; fellBack: boolean }> {
  const scene = async () => {
    const asked = withPercentiles(measure.sceneUrl, percentiles);
    return fetchStatisticsAt(histogram ? withHistogram(asked) : asked);
  };
  if (!measure.area) return { statistics: await scene(), fellBack: false };
  try {
    return { statistics: statisticsOfArea(await answerTo(measure.area), measure.area.scalings), fellBack: false };
  } catch (error) {
    // The status alone is told: an order the page built wrongly must not pass unnoticed, but nothing of it or its answer is kept.
    if (!(error instanceof HttpError && (error.status === 413 || error.status === 422))) throw error;
    console.warn(`area statistics: status ${error.status}; measuring the first whole scene`);
    return { statistics: await scene(), fellBack: true };
  }
}
