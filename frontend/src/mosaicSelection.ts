// The selections the map's mosaics are drawn from (M5-30b part 3, `adr/0032` §10.2).
//
// A mosaic's tile URL names a selection by an id the tiler derives from its content, so the list of scenes does not sit in the
// URL. What the page keeps are logical keys (dataset, assets, sorted scene ids): a selection is created once for a key, two
// callers that ask while it is being created share the one request, and the id that comes back is the same wherever and whenever
// the same list is created.
//
// A selection expires at the tiler (seven days) and the tile then answers `410`. The page creates the same selection again and
// draws it again: for a TileJSON that comes up as an `HttpError` `410` (`withSelection`), for the tiles of the map as an `error`
// event of the map (`watchGoneSelections`). MapLibre gives the status of a tile that failed (`AJAXError.status`), so the tile is
// told from any other failure of a source, and a tile of an unrelated failure never creates anything.

import type { Map as MapLibreMap, RasterTileSource } from 'maplibre-gl';
import { createMosaicSelection, HttpError, type MosaicSelection } from './api';

// What a selection is made from, by its id: what creating it again needs.
interface SelectionList {
  datasetId: string;
  ids: string[];
  assets: string[];
}

export const selectionKeyOf = (datasetId: string, assets: readonly string[], ids: readonly string[]): string =>
  JSON.stringify([datasetId, [...new Set(assets)].sort(), [...new Set(ids)].sort()]);

const made = new Map<string, MosaicSelection>();
const making = new Map<string, Promise<MosaicSelection>>();
const lists = new Map<string, SelectionList>();
const renewing = new Map<string, Promise<boolean>>();
const renewals = new Map<string, { count: number; at: number }>();

// Forgets every selection and every renewal: a test starts without what the one before made.
export function resetSelections(): void {
  made.clear();
  making.clear();
  lists.clear();
  renewing.clear();
  renewals.clear();
}

// What has been created, by key: the selections a pure function (`previewSpec`) reads.
export const knownSelections: ReadonlyMap<string, MosaicSelection> = made;

function remember(key: string, list: SelectionList, selection: MosaicSelection): MosaicSelection {
  made.set(key, selection);
  lists.set(selection.id, list);
  return selection;
}

// The selection of this content, created at the first ask and shared by the ones that come while it is being created. A failure
// (`HttpError` with the tiler's words) is not kept: the next ask creates again.
export function ensureSelection(datasetId: string, ids: readonly string[], assets: readonly string[]): Promise<MosaicSelection> {
  const key = selectionKeyOf(datasetId, assets, ids);
  const known = made.get(key);
  if (known) return Promise.resolve(known);
  let creation = making.get(key);
  if (!creation) {
    const list = { datasetId, ids: [...new Set(ids)].sort(), assets: [...new Set(assets)].sort() };
    creation = createMosaicSelection(datasetId, list.ids, list.assets)
      .then((selection) => remember(key, list, selection))
      .finally(() => making.delete(key));
    making.set(key, creation);
  }
  return creation;
}

// The creation again of the selection with this id, one request for the callers that ask together. `false` where the page never
// made it (an id it was not given) or where the tiler does not take the list any more.
export function renewSelection(id: string): Promise<boolean> {
  const list = lists.get(id);
  if (!list) return Promise.resolve(false);
  let renewal = renewing.get(id);
  if (!renewal) {
    renewal = createMosaicSelection(list.datasetId, list.ids, list.assets)
      .then((selection) => {
        remember(selectionKeyOf(list.datasetId, list.assets, list.ids), list, selection);
        return selection.id === id;
      })
      .catch(() => false)
      .finally(() => renewing.delete(id));
    renewing.set(id, renewal);
  }
  return renewal;
}

// Runs what asks the tiler about a selection; where it says `410` the selection is created again and the question is asked once more.
export async function withSelection<T>(selection: MosaicSelection, ask: (selection: MosaicSelection) => Promise<T>): Promise<T> {
  try {
    return await ask(selection);
  } catch (error) {
    if (!(error instanceof HttpError) || error.status !== 410 || !(await renewSelection(selection.id))) throw error;
    return ask(selection);
  }
}

// --- the tiles of the map ---------------------------------------------------

export const selectionIdOfUrl = (url: string): string | null => /\/mosaic\/([0-9a-f]{32})\//.exec(url)?.[1] ?? null;

// A selection is renewed at most this often in a page, and not again while the tiles of the last renewal may still be answering.
const RENEWALS_PER_ID = 3;
const QUIET_AFTER_RENEWAL_MS = 3000;

// Sources whose tiles name the selection are loaded again: the id, and with it the URL, is the same, so only a reload brings the tiles.
function reloadSourcesOf(map: MapLibreMap, id: string): void {
  for (const [sourceId, source] of Object.entries(map.getStyle()?.sources ?? {})) {
    const tiles = source.type === 'raster' ? source.tiles : undefined;
    if (tiles?.some((url) => selectionIdOfUrl(url) === id)) (map.getSource(sourceId) as RasterTileSource | undefined)?.setTiles([...tiles]);
  }
}

// Creates a selection again when a tile of it answers `410`, and draws it again: for the tiles of the view, of the pinned layers
// and of a preview alike. Other errors of a source are left to MapLibre.
export function watchGoneSelections(map: MapLibreMap, now: () => number = Date.now): void {
  map.on('error', (event) => {
    const failure = (event as { error?: { status?: unknown; url?: unknown } }).error;
    const id = failure?.status === 410 && typeof failure.url === 'string' ? selectionIdOfUrl(failure.url) : null;
    if (id === null) return;
    const before = renewals.get(id) ?? { count: 0, at: -Infinity };
    if (before.count >= RENEWALS_PER_ID || now() - before.at < QUIET_AFTER_RENEWAL_MS) return;
    renewals.set(id, { count: before.count + 1, at: now() });
    void renewSelection(id).then((renewed) => {
      renewals.set(id, { count: before.count + 1, at: now() });
      if (renewed) reloadSourcesOf(map, id);
    });
  });
}
