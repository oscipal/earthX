// The size of the tiles a raster source asks for (NM4-29b, `docs/plans/querschnitt/nm4-29-kacheln-512.md` §15, §17).
//
// A mosaic tile is 512 px: the browser opens only 6 connections to a host over HTTP/1.1, and a mosaic has the most
// expensive tiles, so it gains most from a quarter of the requests. A scene, the preview of a scene and a result stay at
// 256 px. The size is part of the tile template (`tilesize` in its query, which the tiler takes as 256 or 512 and
// answers with `400` otherwise) and of the source (`tileSize` in MapLibre); the source reads it from the template, so
// the two cannot differ.

export const TILE_SIZE = 256;
export const MOSAIC_TILE_SIZE = 512;

const TILESIZE = /[?&]tilesize=(\d+)(?:&|$)/u;

// The size a tile template asks for; the tiler's own 256 where it names none.
export function tileSizeOf(tileUrl: string): number {
  const size = Number(TILESIZE.exec(tileUrl)?.[1]);
  return size === MOSAIC_TILE_SIZE ? MOSAIC_TILE_SIZE : TILE_SIZE;
}

// The tile level the map asks a source with tiles of `tileSize` px for at a map zoom: `round(zoom + log2(512 / tileSize))`
// (maplibre-gl 5 `covering_tiles.ts`), before the source's own `minzoom` and `maxzoom` hold it.
export function levelAskedAt(mapZoom: number, tileSize: number): number {
  return Math.round(mapZoom + Math.log2(512 / tileSize));
}

// By how many zoom levels the map asks for level L before the map zoom reaches L: level L is first asked at map zoom
// L - 1.5 for 256-px tiles and at L - 0.5 for 512-px ones.
export function tileLevelAhead(tileSize: number): number {
  return 0.5 + Math.log2(512 / tileSize);
}

// The first map zoom from which a source with tile levels from `minZoom` is asked for a tile.
export function firstZoomOf(minZoom: number, tileUrl: string): number {
  return minZoom - tileLevelAhead(tileSizeOf(tileUrl));
}

// Metres per pixel of a Web Mercator tile of `tileSize` px at `latitude` and level `zoom`.
export function tileMetres(latitude: number, zoom: number, tileSize: number): number {
  return (156543.03392 * Math.cos((latitude * Math.PI) / 180) * (TILE_SIZE / tileSize)) / 2 ** zoom;
}
