// M5-56 (Otto, 18.11.2026): "Crop and merge to AOI" draws its picture below the first level over its own scenes only, not over the
// whole area: on the overview route of a footprint selection of the scenes, which the tiler masks to their outlines. The same area is
// drawn below and above the first level, also where tiles of the search were not ticked.

import { describe, expect, it } from 'vitest';

import { AOI, DOWNLOADED, ENTRIES, FOOTPRINTS_ID, GROUPS, ITEMS, LIST, MOSAICS, outlined, TERRAIN } from './fixtures/swissalti';
import { zoomMap } from './fixtures/zoomMap';
import { syncFocusRaster } from './mapLayers';
import { footprintsKeyOf, MAX_FOOTPRINT_ITEMS, mosaicsOfView, overviewOverScenes, type Mosaics } from './mosaic';
import { overviewRasterOf } from './overviewSubstitute';
import { overviewOverlaysOf, overviewsWaiting } from './searchLayers';
import type { DownloadedInfo } from './types';

const BELOW = overviewRasterOf(TERRAIN, LIST)!;
const view = (over: Record<string, unknown> = {}) => ({
  downloaded: DOWNLOADED,
  render: { rescale: '0,3000' },
  showDownloaded: true,
  aoi: AOI,
  cropToAoi: true,
  items: ITEMS,
  dataset: TERRAIN,
  datasets: LIST,
  groups: GROUPS,
  mosaics: MOSAICS,
  ...over,
});
const urlsBelow = (live: ReturnType<typeof zoomMap>) =>
  live.picturesAt(5).map((id) => (live.sources.get(live.layers.get(id)!.source!)!.tiles as string[])[0]);
const withoutFootprints = (): Mosaics => Object.fromEntries(Object.entries(MOSAICS).filter(([key]) => !key.startsWith('footprints|')));

describe('overviewOverScenes', () => {
  it('draws the picture of the footprint selection, cut to the box of the scenes', () => {
    const raster = overviewOverScenes(BELOW, 'terrain', ENTRIES, MOSAICS, false)!;
    expect(raster.tileUrl).toBe(`/collections/terrain/overview/${FOOTPRINTS_ID}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=512`);
    const boxes = ENTRIES.map(([, info]) => info.bounds);
    expect(raster.bounds).toEqual([
      Math.min(...boxes.map((b) => b[0])),
      Math.min(...boxes.map((b) => b[1])),
      Math.max(...boxes.map((b) => b[2])),
      Math.max(...boxes.map((b) => b[3])),
    ]);
    expect({ ...raster, tileUrl: '', bounds: [] }).toEqual({ ...BELOW, tileUrl: '', bounds: [] });
  });

  it('draws nothing while the selection is being made', () => {
    expect(overviewOverScenes(BELOW, 'terrain', ENTRIES, withoutFootprints(), false)).toBeUndefined();
  });

  it('draws the picture of the whole area where the tiler did not take the selection, for an index, or where nobody asked', () => {
    const refused: Mosaics = { ...withoutFootprints(), [footprintsKeyOf('terrain', ENTRIES.map(([id]) => id))]: null };
    expect(overviewOverScenes(BELOW, 'terrain', ENTRIES, refused, false)).toBe(BELOW);
    expect(overviewOverScenes(BELOW, 'terrain', ENTRIES, MOSAICS, true)).toBe(BELOW);
    expect(overviewOverScenes(BELOW, 'terrain', ENTRIES, undefined, false)).toBe(BELOW);
  });

  it(`draws the picture of the whole area over more than ${MAX_FOOTPRINT_ITEMS} scenes, which no selection takes`, () => {
    const [, info] = ENTRIES[0];
    const many = Array.from({ length: MAX_FOOTPRINT_ITEMS + 1 }, (_, i) => [`T${i}`, info] as [string, DownloadedInfo]);
    expect(overviewOverScenes(BELOW, 'terrain', many, {}, false)).toBe(BELOW);
  });

  it('takes the scenes of its own dataset: those of another one are another selection', () => {
    const other: [string, DownloadedInfo] = ['X', { ...ENTRIES[0][1], datasetId: 'other' }];
    expect(overviewOverScenes(BELOW, 'terrain', [...ENTRIES, other], MOSAICS, false)?.tileUrl).toContain(FOOTPRINTS_ID);
  });

  it('is asked for by the view, so that the view is drawn again when the selection comes', () => {
    expect(Object.keys(mosaicsOfView(MOSAICS, 'terrain', ENTRIES, GROUPS))).toContain(footprintsKeyOf('terrain', ENTRIES.map(([id]) => id)));
  });
});

describe('the view of "Crop and merge to AOI" below the first level', () => {
  it('draws the overview of its scenes, through the AOI clip', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view());
    const [url] = urlsBelow(live);
    expect(url).toMatch(/^earthx-clip:\/\//);
    expect(url).toContain(`/collections/terrain/overview/${FOOTPRINTS_ID}/tiles/`);
  });

  it('draws nothing below the first level until the selection is there, and then its picture', () => {
    const live = zoomMap();
    syncFocusRaster(live.map as never, view({ mosaics: withoutFootprints() }));
    expect(urlsBelow(live)).toEqual([]);
    syncFocusRaster(live.map as never, view({ mosaics: { ...withoutFootprints(), ...outlined() } }));
    expect(urlsBelow(live)[0]).toContain(FOOTPRINTS_ID);
  });

  it('draws the whole area as before where the tiler refused the selection', () => {
    const live = zoomMap();
    const refused: Mosaics = { ...withoutFootprints(), [footprintsKeyOf('terrain', Object.keys(DOWNLOADED))]: null };
    syncFocusRaster(live.map as never, view({ mosaics: refused }));
    expect(urlsBelow(live)[0]).toContain('/collections/terrain/overview/tiles/');
  });

  it('draws the scenes left after some were not ticked over those only: another selection', () => {
    const [kept] = Object.keys(DOWNLOADED);
    const fewer = { [kept]: DOWNLOADED[kept] };
    const live = zoomMap();
    syncFocusRaster(live.map as never, view({ downloaded: fewer, mosaics: outlined(fewer), groups: [] }));
    expect(urlsBelow(live)[0]).toContain(FOOTPRINTS_ID);
    const elsewhere = zoomMap();
    syncFocusRaster(elsewhere.map as never, view({ downloaded: fewer, mosaics: MOSAICS, groups: [] }));
    expect(urlsBelow(elsewhere)).toEqual([]);
  });
});

describe('a layer pinned from the view', () => {
  const urlOf = (overlays: ReturnType<typeof overviewOverlaysOf>) => (overlays[0] as Extract<(typeof overlays)[0], { kind: 'raster' }>).tileUrl;

  it('draws its picture below the first level over its scenes, as the view did', () => {
    expect(urlOf(overviewOverlaysOf(['terrain'], LIST, { rescale: '0,3000' }, null, { entries: ENTRIES, mosaics: MOSAICS }))).toContain(FOOTPRINTS_ID);
  });

  it('waits while the selection is on its way, and not once it is there, refused, or for a dataset that draws nothing below', () => {
    const look = { rescale: '0,3000' };
    const refused: Mosaics = { ...withoutFootprints(), [footprintsKeyOf('terrain', ENTRIES.map(([id]) => id))]: null };
    expect(overviewsWaiting(['terrain'], LIST, look, { entries: ENTRIES, mosaics: withoutFootprints() })).toBe(true);
    expect(overviewsWaiting(['terrain'], LIST, look, { entries: ENTRIES, mosaics: MOSAICS })).toBe(false);
    expect(overviewsWaiting(['terrain'], LIST, look, { entries: ENTRIES, mosaics: refused })).toBe(false);
    expect(overviewsWaiting([], LIST, look, { entries: [], mosaics: {} })).toBe(false);
    expect(urlOf(overviewOverlaysOf(['terrain'], LIST, look, null))).toContain('/collections/terrain/overview/tiles/');
  });
});

