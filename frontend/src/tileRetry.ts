// A tile that failed while a service was away is asked again (UI-08, Otto 16.11.2026). MapLibre marks a tile whose request failed as
// errored and never asks for it again while it stays in view: after `docker compose up` or a restart of the tiler a layer kept the gaps of
// the restart until the page was reloaded. Two ways bring such a tile back:
//   - its own clock: a tile of a layer's source that failed for a passing reason (no answer at all, `408`, `429`, `502`, `503`, `504` of the
//     proxy or the tiler while it starts) is asked again after 1 s, then after twice as long, up to 30 s, eight times, about two minutes;
//   - the service is back: once a tile of the same source loads, every failed tile of that source in view is asked again at once and its
//     count starts afresh, at most once in 10 s per source. So a longer restart ends with the first tile that loads (a move of the map
//     asks for new ones), and a tile the tiler refuses for good (`502` of a source that cannot be read) is not asked over and over.
// A refusal (`400`, `404`, `410`, `422`) and a `500` (a fault of the tiler, not a restart) are answers and are not asked again.
//
// The tile is loaded again as MapLibre does it for a failed tile when its source changes (`TileManager.reload`): in the state "loading",
// which draws nothing until the picture is there. `map.refreshTiles` is no way: it puts a failed tile into "expired", which counts as
// having data, and the next frame draws a tile without a picture (`texture.bind` of undefined, seen in the browser with MapLibre 6.16).
// `tileRetry.test.ts` and `tsc` (MapView hands the map itself) hold the parts of MapLibre this needs.

import type { Map as MapLibreMap } from 'maplibre-gl';
import { ownerOfSource } from './mapLayers';

export const RETRY_DELAYS_MS: readonly number[] = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000, 30_000];
// The least time between two "the service is back" reloads of one source.
export const RECOVERY_GAP_MS = 10_000;

// Whether a failed tile request may succeed when it is sent again: `0` is MapLibre's status for a request that got no answer.
export function isPassingFailure(status: number | undefined): boolean {
  return status === 0 || status === 408 || status === 429 || status === 502 || status === 503 || status === 504;
}

interface TileId {
  x: number;
  y: number;
  z: number;
}

interface TileEvent {
  sourceId?: string;
  tile?: { tileID?: { canonical?: TileId }; state?: string };
  error?: { status?: number };
}

// What of MapLibre's tile manager of a source is used: the tiles in view by id, and loading one of them again.
export interface TileManagerLike {
  getIds: () => string[];
  getTileByID: (id: string) => { state: string; tileID: { canonical: TileId } } | undefined;
  _reloadTile: (id: string, state: 'loading') => Promise<void> | void;
}

export type RetryMap = Pick<MapLibreMap, 'getSource'> & {
  on: (type: 'error' | 'sourcedata', listener: (event: TileEvent) => void) => unknown;
  style?: { tileManagers?: Record<string, TileManagerLike | undefined> };
};

// Loads the failed tiles of `sourceId` again: those at `at`, or all of them; nothing where the source is gone. Says how many.
export function reloadFailedTiles(map: RetryMap, sourceId: string, at: TileId | null): number {
  if (!map.getSource(sourceId)) return 0;
  const manager = map.style?.tileManagers?.[sourceId];
  if (!manager) return 0;
  let count = 0;
  for (const id of manager.getIds()) {
    const tile = manager.getTileByID(id);
    if (tile?.state !== 'errored') continue;
    const { x, y, z } = tile.tileID.canonical;
    if (at && (x !== at.x || y !== at.y || z !== at.z)) continue;
    void manager._reloadTile(id, 'loading');
    count += 1;
  }
  return count;
}

export function watchTileRetry(map: RetryMap, delays: readonly number[] = RETRY_DELAYS_MS, now: () => number = Date.now): void {
  const tries = new Map<string, number>();
  const waiting = new Set<string>();
  const recovered = new Map<string, number>();
  const keyOf = (sourceId: string, { x, y, z }: TileId) => `${sourceId}/${z}/${x}/${y}`;
  const forgetSource = (sourceId: string) => {
    for (const key of tries.keys()) if (key.startsWith(`${sourceId}/`)) tries.delete(key);
  };
  map.on('error', ({ sourceId, tile, error }) => {
    const canonical = tile?.tileID?.canonical;
    if (!sourceId || !canonical || ownerOfSource(sourceId) === null || !isPassingFailure(error?.status)) return;
    const key = keyOf(sourceId, canonical);
    const done = tries.get(key) ?? 0;
    if (waiting.has(key) || done >= delays.length) return;
    tries.set(key, done + 1);
    waiting.add(key);
    const { x, y, z } = canonical;
    setTimeout(() => {
      waiting.delete(key);
      if (!map.getSource(sourceId)) forgetSource(sourceId);
      else reloadFailedTiles(map, sourceId, { x, y, z });
    }, delays[done]);
  });
  map.on('sourcedata', ({ sourceId, tile }) => {
    const canonical = tile?.tileID?.canonical;
    if (!sourceId || !canonical || tile?.state !== 'loaded' || ownerOfSource(sourceId) === null) return;
    tries.delete(keyOf(sourceId, canonical));
    const last = recovered.get(sourceId);
    if (last !== undefined && now() - last < RECOVERY_GAP_MS) return;
    if (reloadFailedTiles(map, sourceId, null) > 0) {
      recovered.set(sourceId, now());
      forgetSource(sourceId);
    }
  });
}
