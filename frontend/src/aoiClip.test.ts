import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  aoiClipProtocol,
  bboxesOverlap,
  clipTileUrl,
  lonLatToMerc,
  parseClipUrl,
  ringsToTilePixels,
  tileLonLatBounds,
  tileMercBounds,
} from './aoiClip';

const TEMPLATE = '/collections/sentinel-2-c1-l2a/items/S2A_1/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual';

function poly(coords: number[][]): GeoJSON.Polygon {
  return { type: 'Polygon', coordinates: [coords] };
}

// A polygon with a distinctive, easy-to-spot coordinate — every test below
// that inspects a wrapped URL checks this string is *not* in it.
const AOI = poly([
  [12.3456789, 47.1234567],
  [13, 47],
  [13, 48],
  [12, 48],
  [12.3456789, 47.1234567],
]);

// MapLibre replaces every literal `{z}`/`{x}`/`{y}` occurrence in the whole
// URL with one global substitution (`TileID.url`, maplibre-gl-js source) —
// simulated the same way here rather than against a real map.
function substituteZXY(url: string, z: number, x: number, y: number): string {
  return url.replaceAll('{z}', String(z)).replaceAll('{x}', String(x)).replaceAll('{y}', String(y));
}

describe('clipTileUrl / parseClipUrl', () => {
  it('leaves the template unchanged without an AOI', () => {
    expect(clipTileUrl(TEMPLATE, null)).toBe(TEMPLATE);
  });

  it('leaves the template unchanged for a geometry with no readable bbox', () => {
    expect(clipTileUrl(TEMPLATE, { type: 'Polygon', coordinates: [] }, )).toBe(TEMPLATE);
  });

  it('never puts an AOI coordinate into the wrapped URL', () => {
    const wrapped = clipTileUrl(TEMPLATE, AOI);
    expect(wrapped).not.toContain('12.3456789');
    expect(wrapped).not.toContain('47.1234567');
  });

  it('round-trips z/x/y and the exact original tile URL through the protocol wrapper', () => {
    const wrapped = clipTileUrl(TEMPLATE, AOI);
    const substituted = substituteZXY(wrapped, 5, 10, 12);
    const parsed = parseClipUrl(substituted);
    expect(parsed).not.toBeNull();
    expect(parsed).toMatchObject({ z: 5, x: 10, y: 12 });
    expect(parsed?.inner).toBe(substituteZXY(TEMPLATE, 5, 10, 12));
  });

  it('gives the same key for the same AOI object, reused across several tiles/overlays', () => {
    const a = clipTileUrl(TEMPLATE, AOI);
    const b = clipTileUrl('/other/tiles/{z}/{x}/{y}', AOI);
    expect(parseClipUrl(substituteZXY(a, 1, 0, 0))?.key).toBe(
      parseClipUrl(substituteZXY(b, 1, 0, 0))?.key,
    );
  });

  it('gives a different key for a different AOI object, even with identical coordinates', () => {
    const same = poly(AOI.coordinates[0]);
    const a = parseClipUrl(substituteZXY(clipTileUrl(TEMPLATE, AOI), 1, 0, 0));
    const b = parseClipUrl(substituteZXY(clipTileUrl(TEMPLATE, same), 1, 0, 0));
    expect(a?.key).not.toBe(b?.key);
  });

  it.each([
    ['not the earthx-clip scheme', 'https://host/tiles/5/10/12'],
    ['too few segments', 'earthx-clip://c0/5/10/tiles'],
    ['a non-integer z', 'earthx-clip://c0/x/10/12/https://host/t'],
    ['no inner URL at all', 'earthx-clip://c0/5/10/12/'],
  ])('rejects a malformed URL: %s', (_label, url) => {
    expect(parseClipUrl(url)).toBeNull();
  });
});

describe('lonLatToMerc', () => {
  it('maps the origin to the origin', () => {
    const [x, y] = lonLatToMerc([0, 0]);
    expect(x).toBeCloseTo(0, 6);
    expect(y).toBeCloseTo(0, 6);
  });

  it('is monotonically increasing in both axes', () => {
    const [x1] = lonLatToMerc([10, 0]);
    const [x2] = lonLatToMerc([20, 0]);
    expect(x2).toBeGreaterThan(x1);
    const [, y1] = lonLatToMerc([0, 10]);
    const [, y2] = lonLatToMerc([0, 20]);
    expect(y2).toBeGreaterThan(y1);
  });

  it('clamps latitude to the Web Mercator limit instead of diverging at the pole', () => {
    const [, yAtLimit] = lonLatToMerc([0, 85.0511287798]);
    const [, yPastLimit] = lonLatToMerc([0, 89.9]);
    expect(yPastLimit).toBeCloseTo(yAtLimit, 0);
    expect(Number.isFinite(yPastLimit)).toBe(true);
  });
});

describe('tileLonLatBounds', () => {
  it('covers the whole world (within the Mercator latitude limit) at z0', () => {
    const [minx, miny, maxx, maxy] = tileLonLatBounds(0, 0, 0);
    expect(minx).toBeCloseTo(-180, 6);
    expect(maxx).toBeCloseTo(180, 6);
    expect(miny).toBeCloseTo(-85.0511287798, 3);
    expect(maxy).toBeCloseTo(85.0511287798, 3);
  });

  it('quarters the world at z1', () => {
    expect(tileLonLatBounds(1, 0, 0)[0]).toBeCloseTo(-180, 6);
    expect(tileLonLatBounds(1, 0, 0)[2]).toBeCloseTo(0, 6);
    expect(tileLonLatBounds(1, 1, 0)[0]).toBeCloseTo(0, 6);
    expect(tileLonLatBounds(1, 1, 0)[2]).toBeCloseTo(180, 6);
  });
});

describe('tileMercBounds', () => {
  it('is square, like every WebMercatorQuad tile', () => {
    const [minx, miny, maxx, maxy] = tileMercBounds(6, 20, 30);
    expect(maxx - minx).toBeCloseTo(maxy - miny, 3);
  });
});

describe('bboxesOverlap', () => {
  it('is true when two boxes intersect', () => {
    expect(bboxesOverlap([0, 0, 10, 10], [5, 5, 15, 15])).toBe(true);
  });

  it('is true for boxes that only touch at an edge', () => {
    expect(bboxesOverlap([0, 0, 10, 10], [10, 0, 20, 10])).toBe(true);
  });

  it('is false for disjoint boxes', () => {
    expect(bboxesOverlap([0, 0, 10, 10], [20, 20, 30, 30])).toBe(false);
  });
});

describe('ringsToTilePixels', () => {
  it('maps a polygon covering exactly the tile bounds onto the tile\'s own corners', () => {
    const [z, x, y] = [5, 10, 12];
    const [minx, miny, maxx, maxy] = tileLonLatBounds(z, x, y);
    const exact = poly([
      [minx, miny],
      [maxx, miny],
      [maxx, maxy],
      [minx, maxy],
      [minx, miny],
    ]);
    const [ring] = ringsToTilePixels(exact, z, x, y, 256);
    const xs = ring.map(([px]) => px);
    const ys = ring.map(([, py]) => py);
    expect(Math.min(...xs)).toBeCloseTo(0, 3);
    expect(Math.max(...xs)).toBeCloseTo(256, 3);
    expect(Math.min(...ys)).toBeCloseTo(0, 3);
    expect(Math.max(...ys)).toBeCloseTo(256, 3);
  });

  it('maps the same polygon onto the whole pixel space of a 512-px tile, not onto a quarter of it (NM4-29b)', () => {
    const [z, x, y] = [5, 10, 12];
    const [minx, miny, maxx, maxy] = tileLonLatBounds(z, x, y);
    const exact = poly([
      [minx, miny],
      [maxx, miny],
      [maxx, maxy],
      [minx, maxy],
      [minx, miny],
    ]);
    const [ring] = ringsToTilePixels(exact, z, x, y, 512);
    expect(Math.max(...ring.map(([px]) => px))).toBeCloseTo(512, 3);
    expect(Math.max(...ring.map(([, py]) => py))).toBeCloseTo(512, 3);
    // The middle of the tile in longitude lies at the middle of the picture, 256 px in.
    const [ring2] = ringsToTilePixels(poly([[(minx + maxx) / 2, miny], [maxx, miny], [maxx, maxy], [(minx + maxx) / 2, miny]]), z, x, y, 512);
    expect(ring2[0][0]).toBeCloseTo(256, 3);
  });

  it('projects a polygon east of the tile to pixels beyond its right edge', () => {
    const [z, x, y] = [5, 10, 12];
    const [, , maxx] = tileLonLatBounds(z, x, y);
    const east = poly([
      [maxx + 1, 10],
      [maxx + 2, 10],
      [maxx + 2, 11],
      [maxx + 1, 11],
      [maxx + 1, 10],
    ]);
    const [ring] = ringsToTilePixels(east, z, x, y, 256);
    expect(ring.every(([px]) => px > 256)).toBe(true);
  });

  it('returns one ring per polygon of a MultiPolygon, none merged', () => {
    const multi: GeoJSON.MultiPolygon = {
      type: 'MultiPolygon',
      coordinates: [
        [[[10, 47], [10.1, 47], [10.1, 47.1], [10, 47.1], [10, 47]]],
        [[[12, 47], [12.1, 47], [12.1, 47.1], [12, 47.1], [12, 47]]],
      ],
    };
    expect(ringsToTilePixels(multi, 5, 10, 12, 256)).toHaveLength(2);
  });

  it('returns exterior ring and hole separately for a polygon with a hole', () => {
    const withHole: GeoJSON.Polygon = {
      type: 'Polygon',
      coordinates: [
        [[10, 47], [13, 47], [13, 48], [10, 48], [10, 47]],
        [[11, 47.2], [12, 47.2], [12, 47.5], [11, 47.5], [11, 47.2]],
      ],
    };
    expect(ringsToTilePixels(withHole, 5, 10, 12, 256)).toHaveLength(2);
  });
});

// The protocol in a browser-less test: the picture a tile arrives as, the canvas it is masked on and the path of the AOI
// it is masked with are recorded, not drawn.
describe('aoiClipProtocol on a tile of 256 and of 512 px (NM4-29b)', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const WEST_HALF_AT = (z: number, x: number, y: number) => {
    const [minx, miny, maxx, maxy] = tileLonLatBounds(z, x, y);
    // Left half of the tile in longitude, which is the left half in Web Mercator too.
    return poly([[minx - 0.1, miny - 0.1], [(minx + maxx) / 2, miny - 0.1], [(minx + maxx) / 2, maxy + 0.1], [minx - 0.1, maxy + 0.1], [minx - 0.1, miny - 0.1]]);
  };

  async function maskedWith(tileSize: number, aoi: GeoJSON.Geometry) {
    const points: [number, number][] = [];
    let canvasSize: [number, number] | null = null;
    class FakePath {
      moveTo(x: number, y: number) {
        points.push([x, y]);
      }
      lineTo(x: number, y: number) {
        points.push([x, y]);
      }
      closePath() {}
    }
    class FakeCanvas {
      width: number;
      height: number;
      constructor(width: number, height: number) {
        [this.width, this.height] = [width, height];
        canvasSize = [width, height];
      }
      getContext() {
        return { save() {}, restore() {}, clip() {}, drawImage() {} };
      }
      transferToImageBitmap() {
        return { width: this.width, height: this.height };
      }
    }
    vi.stubGlobal('Path2D', FakePath);
    vi.stubGlobal('OffscreenCanvas', FakeCanvas);
    vi.stubGlobal('createImageBitmap', async () => ({ width: tileSize, height: tileSize }));
    vi.stubGlobal('fetch', async () => ({ ok: true, blob: async () => new Blob() }));
    const [z, x, y] = [5, 17, 11];
    const template = `${TEMPLATE}&tilesize=${tileSize}`;
    const url = substituteZXY(clipTileUrl(template, aoi), z, x, y);
    await aoiClipProtocol({ url } as never, new AbortController());
    return { points, canvasSize: canvasSize! };
  }

  it.each([256, 512])('cuts a %i-px tile at the AOI over the whole tile, not over a quarter of it', async (size) => {
    const { points, canvasSize } = await maskedWith(size, WEST_HALF_AT(5, 17, 11));
    expect(canvasSize).toEqual([size, size]);
    const xs = points.map(([px]) => px);
    const ys = points.map(([, py]) => py);
    // The AOI reaches from beyond the left edge to the middle of the tile, and from the top to the bottom.
    expect(Math.min(...xs)).toBeLessThan(0);
    expect(xs.filter((px) => px > 0).every((px) => Math.abs(px - size / 2) < 1)).toBe(true);
    expect(Math.min(...ys)).toBeLessThan(0);
    expect(Math.max(...ys)).toBeGreaterThan(size);
  });
});
