// "Download crop" of a layer that shows an index (NM4-14b, Otto 1.11.2026): the file is the result a Processing job would give for
// the same scenes, area and index, and the person sees neither the Processing panel nor a job in the list of jobs.
//
// The order is built by the panel's own `buildOrder` from the same pieces (one `band_math` step of Version 2 with the expression
// and the name of the preset, that band as the output, the data type the panel proposes), so the recipe, its hash and the
// result are those of a job started by hand. The job is placed, waited for and downloaded here and never enters the store of the
// panel (`processingStore.jobs`, the shelf in the browser). Several groups are several jobs and one bundle.

import type { DatasetOption } from './datasets';
import type { IndexPreset } from './indexPresets';
import type { MapLayer } from './layers';
import { HttpError } from './api';
import {
  createBundle,
  dismissJob,
  estimateOrder,
  fetchJob,
  fetchProcess,
  placeJob,
  resultUrl,
  type AoiProvenance,
  type Order,
  type StatusInfo,
} from './processing';
import { chooseDtype } from './processingDefaults';
import { aoiProvenanceFor, buildOrder, formatBytes, formatDuration, isArea, processBlockReason, processInfo, type DraftStep } from './processingOrder';
import { RESULT_ZIP } from './resultLayer';
import { viewIndexOf } from './viewIndex';

export const POLL_MS = 2000;

// The index a pinned layer shows, if its dataset offers it.
export function indexOfLayer(layer: MapLayer, datasets: readonly DatasetOption[]): IndexPreset | null {
  const dataset = datasets.find((d) => d.id === layer.restore.datasetId);
  // A layer made before looks were kept has none.
  return layer.restore.appliedRender ? viewIndexOf(layer.restore.appliedRender, dataset?.collection) : null;
}

// Why the index of a layer cannot be downloaded, or `null`: only an AOI crop can (a whole scene is a job of its own to start in
// Processing), and only where the licence allows processing.
export function indexDownloadBlock(layer: MapLayer, datasets: readonly DatasetOption[]): string | null {
  const { restore } = layer;
  const dataset = datasets.find((d) => d.id === restore.datasetId);
  if (!restore.focusMode || !restore.cropToAoi || !isArea(restore.aoi)) {
    return 'The index of whole scenes is computed by a job: start one in Processing.';
  }
  return processBlockReason(dataset, restore.itemIds.length);
}

// One order for each group, as the panel builds it for one pass: a `band_math` step of Version 2 with the expression and the name of the
// preset, that band as the output. With an `aoi` it is the crop, without one the whole scenes. `{ problem }` where one cannot be built.
export function indexOrdersOfScenes(args: {
  datasetId: string;
  groups: readonly (readonly string[])[];
  aoi: GeoJSON.Polygon | GeoJSON.MultiPolygon | null;
  preset: IndexPreset;
  dataset: DatasetOption;
  info: ReturnType<typeof processInfo>;
}): { orders: Order[] } | { problem: string } {
  const { datasetId, groups, aoi, preset, dataset, info } = args;
  const step: DraftStep = { key: 0, op: 'band_math', opVersion: 2, values: { expression: preset.expression, name: preset.name } };
  const dtype = chooseDtype({ steps: [{ op: 'band_math' }], bands: [], allowed: info.dtypes }).value;
  const data = Object.keys(dataset.collection['earthx:band_units'] ?? {});
  const orders: Order[] = [];
  for (const itemIds of groups.filter((group) => group.length > 0)) {
    const built = buildOrder({ datasetId, itemIds, area: aoi ? 'aoi' : 'scene', aoi, steps: [step], bands: [preset.name], data, dtype, info });
    if (!built.order) return { problem: [...built.problems, ...built.stepProblems.flatMap((p) => [p.unsupported, ...Object.values(p.errors)])].filter(Boolean).join(' ') || 'The index cannot be computed for this layer.' };
    orders.push(built.order);
  }
  return orders.length > 0 ? { orders } : { problem: 'The layer has no scenes left.' };
}

// The same for a layer: the groups it was pinned with, and its AOI where it is a crop.
export function indexOrdersOf(args: {
  layer: MapLayer;
  preset: IndexPreset;
  dataset: DatasetOption;
  info: ReturnType<typeof processInfo>;
}): { orders: Order[] } | { problem: string } {
  const { layer, preset, dataset, info } = args;
  const { restore } = layer;
  const groups = restore.groupItemIds.length > 0 ? restore.groupItemIds : [restore.itemIds];
  const aoi = restore.cropToAoi && isArea(restore.aoi) ? restore.aoi : null;
  return indexOrdersOfScenes({ datasetId: dataset.id, groups, aoi, preset, dataset, info });
}

// What the dialog says of the download in one short line, the reason or the explanation as its tooltip (Otto, 1.11.2026: the job
// this runs counts against the caps and the estimate like any other, and a cap that applies is told in the dialog).
//  estimating  the estimate is on its way;
//  ready       the estimate, and nothing in the way;
//  blocked     a cap stops it before a job is placed (an estimate the server refuses): "Download" stays locked;
//  failed      the last try ended without a file (the server refused the job, the job failed); "Download" may try again.
export type IndexNote =
  | { state: 'estimating' }
  | { state: 'ready' | 'blocked' | 'failed'; text: string; tip: string };

export const TOO_LARGE_TIP = 'An export job may write at most 5 GB. Choose a smaller area or fewer scenes.';
const COUNTS_TIP = 'The job this download runs on the platform; it counts against the same limits as a job of Processing.';

// A refusal as one short line and its explanation: the text before the first colon, the whole message as the tooltip.
function explain(error: unknown): { text: string; tip: string } {
  if (error instanceof HttpError && error.status === 413) return { text: 'Too large for one job', tip: TOO_LARGE_TIP };
  // As the panel words a refusal of the server: its `detail`, else the status line (503: try again).
  const message =
    error instanceof HttpError
      ? `${error.detail ?? error.message}${error.status === 503 && !/try again/iu.test(error.detail ?? error.message) ? ' Try again in a moment.' : ''}`
      : error instanceof Error
        ? error.message
        : String(error);
  const [first] = message.split(': ');
  return { text: first.length > 70 ? `${first.slice(0, 67)}…` : first, tip: message };
}

// What the jobs of the download are expected to cost, asked of the server as "Review" asks it, or the cap that stops them.
export async function estimateIndexDownload(args: { layer: MapLayer; datasets: readonly DatasetOption[]; signal: AbortSignal }): Promise<IndexNote> {
  const { layer, datasets, signal } = args;
  const preset = indexOfLayer(layer, datasets);
  const dataset = datasets.find((d) => d.id === layer.restore.datasetId);
  if (!preset || !dataset) return { state: 'blocked', text: 'This layer shows no index', tip: 'This layer shows no index.' };
  const block = indexDownloadBlock(layer, datasets);
  if (block) return { state: 'blocked', text: block.split(': ')[0].split('. ')[0], tip: block };
  try {
    const info = processInfo(await fetchProcess(dataset.id, signal));
    const made = indexOrdersOf({ layer, preset, dataset, info });
    if ('problem' in made) return { state: 'blocked', text: made.problem, tip: made.problem };
    const docs = await Promise.all(made.orders.map((order) => estimateOrder(order, signal)));
    const size = docs.reduce((sum, doc) => sum + doc.estimate.size, 0);
    const time = docs.length === 1 ? ` · ${formatDuration(docs[0].estimate.duration)}` : ` · ${docs.length} jobs`;
    return { state: 'ready', text: `About ${formatBytes(size)}${time}`, tip: COUNTS_TIP };
  } catch (error) {
    return { state: 'blocked', ...explain(error) };
  }
}

const done = (status: StatusInfo) => status.status === 'successful' || status.status === 'failed' || status.status === 'dismissed';

const sleep = (ms: number, signal: AbortSignal) =>
  new Promise<void>((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener('abort', () => (clearTimeout(timer), resolve()), { once: true });
  });

// Starts the browser's own download of an address.
export function saveFrom(url: string): void {
  const a = document.createElement('a');
  a.href = url;
  a.download = '';
  a.rel = 'noopener noreferrer';
  a.click();
}

// Places the jobs, waits for them and starts the download of their file (one result ZIP, or one bundle of several). Resolves with
// `null` on success, else with what to tell (a `failed` note); `onStatus` says how far it is. An abort dismisses what still waits or runs: no job of
// this is left behind that nobody can see.
export async function downloadIndexCrop(args: {
  layer: MapLayer;
  datasets: readonly DatasetOption[];
  signal: AbortSignal;
  onStatus?: (text: string) => void;
  save?: (url: string) => void;
  pollMs?: number;
}): Promise<{ text: string; tip: string } | null> {
  const { layer, datasets, signal, onStatus = () => undefined, save = saveFrom, pollMs = POLL_MS } = args;
  const preset = indexOfLayer(layer, datasets);
  const dataset = datasets.find((d) => d.id === layer.restore.datasetId);
  const say = (reason: string) => ({ text: reason.split(': ')[0].split('. ')[0], tip: reason });
  if (!preset || !dataset) return say('This layer shows no index.');
  const block = indexDownloadBlock(layer, datasets);
  if (block) return say(block);
  const placed: string[] = [];
  const running = new Set<string>();
  try {
    onStatus(`Computing ${preset.name}…`);
    const info = processInfo(await fetchProcess(dataset.id, signal));
    const made = indexOrdersOf({ layer, preset, dataset, info });
    if ('problem' in made) return say(made.problem);
    for (const order of made.orders) {
      const provenance: AoiProvenance | undefined = aoiProvenanceFor(order, layer.restore.aoi);
      const status = await placeJob(order, { aoiProvenance: provenance });
      placed.push(status.jobID);
      running.add(status.jobID);
    }
    // Each job is asked for until it is over.
    while (running.size > 0) {
      if (signal.aborted) return say('Cancelled.');
      const statuses = await Promise.all([...running].map((id) => fetchJob(id, signal)));
      for (const status of statuses) {
        if (!done(status)) continue;
        running.delete(status.jobID);
        if (status.status !== 'successful') return say(status.message || `${preset.name} could not be computed.`);
      }
      const progress = statuses.reduce((sum, s) => sum + (done(s) ? 1 : s.progress / 100), 0) / Math.max(1, statuses.length);
      onStatus(`Computing ${preset.name}… ${Math.round(progress * 100)} %`);
      if (running.size > 0) await sleep(pollMs, signal);
    }
    if (signal.aborted) return say('Cancelled.');
    save(placed.length === 1 ? resultUrl(placed[0], RESULT_ZIP) : (await createBundle(placed)).href);
    return null;
  } catch (error) {
    if (signal.aborted) return say('Cancelled.');
    return explain(error);
  } finally {
    // Whatever still waits or runs when this ends (a cancel, a failure of another part) is dismissed.
    for (const id of running) void dismissJob(id).catch(() => undefined);
  }
}
