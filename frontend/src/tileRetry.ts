// A tile that failed while a service was away is asked again (UI-08, Otto 16.11.2026). MapLibre marks a tile whose request failed as
// errored and never asks for it again while it stays in view: after `docker compose up` or a restart of the tiler a layer kept the gaps of
// the restart until the page was reloaded. Here a tile of a layer's source that failed for a passing reason (no answer at all, `408`,
// `429`, a `5xx` of the proxy or the tiler while it starts) is asked again after 1 s, then after twice as long, up to 30 s between two tries
// and about four minutes in all. A refusal (`400`, `404`, `410`, `422`) is an answer and is not asked again. A tile that loads starts its
// count afresh; a tile that left the view is not asked (`refreshTiles` reloads only the tiles in view).

import type { Map as MapLibreMap } from 'maplibre-gl';
import { ownerOfSource } from './mapLayers';

export const RETRY_DELAYS_MS: readonly number[] = [1_000, 2_000, 4_000, 8_000, 16_000, 30_000, 30_000, 30_000, 30_000, 30_000, 30_000, 30_000];

// Whether a failed tile request may succeed when it is sent again: `0` is MapLibre's status for a request that got no answer.
export function isPassingFailure(status: number | undefined): boolean {
  return status === 0 || status === 408 || status === 429 || (status !== undefined && status >= 500 && status < 600);
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

type RetryMap = Pick<MapLibreMap, 'getSource' | 'refreshTiles'> & { on: (type: 'error' | 'sourcedata', listener: (event: TileEvent) => void) => unknown };

export function watchTileRetry(map: RetryMap, delays: readonly number[] = RETRY_DELAYS_MS): void {
  const tries = new Map<string, number>();
  const waiting = new Set<string>();
  const keyOf = (sourceId: string, { x, y, z }: TileId) => `${sourceId}/${z}/${x}/${y}`;
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
      if (map.getSource(sourceId)) map.refreshTiles(sourceId, [{ x, y, z }]);
    }, delays[done]);
  });
  map.on('sourcedata', ({ sourceId, tile }) => {
    const canonical = tile?.tileID?.canonical;
    if (sourceId && canonical && tile?.state === 'loaded') tries.delete(keyOf(sourceId, canonical));
  });
}
