// Whole scenes as one file per resolution or one multi-band file (NM4-75), and the look before a crop that may resample: the job is
// the export order of the platform with a `layout` (no AOI for whole scenes, so the server takes the union of the footprints). Like the
// download of an index (`indexDownload.ts`) it is placed, waited for and downloaded here and never enters the list of jobs.

import type { ExportLayout } from './processing';
import { dismissJob, estimateOrder, type Order } from './processing';
import type { DownloadPass } from './download';
import { explain, placeAndFollow, POLL_MS, saveFrom } from './indexDownload';
import { buildExportOrder, formatBytes, formatDuration } from './processingOrder';
import { resamplingParts, type ResamplingPart } from './resamplingWarning';

// The order of whole scenes: the passes as groups, the chosen assets, the layout; `null` where no pass holds a scene.
export function sceneJobOrder(args: {
  datasetId: string;
  passes: readonly DownloadPass[];
  assets: readonly string[];
  layout: ExportLayout;
}): Order | null {
  const groups = args.passes.map((pass) => pass.items.map((item) => item.id)).filter((ids) => ids.length > 0);
  if (groups.length === 0 || args.assets.length === 0) return null;
  return buildExportOrder({ datasetId: args.datasetId, groups, assets: args.assets, layout: args.layout });
}

// What the dialog says of the job in one short line, the explanation as its tooltip. `parts` are the facts of a resampling the person
// confirms before the job starts (`ResamplingDialog`).
//  estimating  the estimate is on its way;
//  ready       the estimate, and nothing in the way;
//  blocked     the server refuses the order (too large, not allowed): "Download" stays locked;
//  failed      the last try ended without a file; "Download" may try again.
export type JobNote =
  | { state: 'estimating' }
  | { state: 'ready' | 'blocked' | 'failed'; text: string; tip: string; parts: ResamplingPart[] };

const COUNTS_TIP = 'The job this download runs on the platform; it counts against the same limits as a job of Processing.';

export async function estimateSceneJob(order: Order, signal: AbortSignal): Promise<JobNote> {
  try {
    const doc = await estimateOrder(order, signal);
    const { size, duration } = doc.estimate;
    return { state: 'ready', text: `About ${formatBytes(size)} · ${formatDuration(duration)}`, tip: COUNTS_TIP, parts: resamplingParts(doc, null) };
  } catch (error) {
    return { state: 'blocked', ...explain(error), parts: [] };
  }
}

// Whether the order resamples anything, as the server's estimate tells; none where the estimate cannot be had (the server has the
// last word when the download itself is asked for).
export async function resamplingOfOrder(order: Order, signal: AbortSignal): Promise<ResamplingPart[]> {
  try {
    return resamplingParts(await estimateOrder(order, signal), null);
  } catch {
    return [];
  }
}

// Places the job, waits for it and starts the download of its ZIP. Resolves with `null` on success, else with what to tell. An abort
// dismisses what still waits or runs.
export async function downloadSceneJob(args: {
  order: Order;
  signal: AbortSignal;
  onStatus?: (text: string) => void;
  save?: (url: string) => void;
  pollMs?: number;
}): Promise<{ text: string; tip: string } | null> {
  const { order, signal, onStatus = () => undefined, save = saveFrom, pollMs = POLL_MS } = args;
  const running = new Set<string>();
  try {
    onStatus('Preparing…');
    return await placeAndFollow({
      orders: [order],
      aoi: null,
      working: 'Preparing',
      failed: 'The files could not be prepared.',
      signal,
      running,
      onStatus,
      save,
      pollMs,
    });
  } catch (error) {
    if (signal.aborted) return { text: 'Cancelled.', tip: 'Cancelled.' };
    return explain(error);
  } finally {
    for (const id of running) void dismissJob(id).catch(() => undefined);
  }
}
