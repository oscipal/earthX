// NM4-24: where the view falls back to the scenes one by one (a mosaic the tiler refused, a time step over 64 scenes, a dataset
// released below z8 only), the scene that lies on top in an overlap is the one the mosaic has on top, the crop and the export
// read first - whichever of the scenes was ticked first.

import { describe, expect, it } from 'vitest';

import { liveMap } from './fixtures/liveMap';
import { previewDataset, previewScene, sceneInfo } from './fixtures/viewScenes';
import { ensureBaseLayers, syncFocusRaster } from './mapLayers';
import { mosaicTemplateOf, orderKeyOf } from './mosaic';
import type { Mosaics, SceneEntry } from './mosaic';
import type { DownloadedInfo, TimeStepGroup } from './types';

const dataset = previewDataset();
const [A, B] = [previewScene('A'), previewScene('B')];
const group = { key: ['d'], label: 'd', items: [A, B] } as unknown as TimeStepGroup;
const info = (id: string, minZoom = 0): DownloadedInfo => sceneInfo(id === 'A' ? A : B, minZoom, 14, dataset.id);

// The scenes in the order they were ticked.
const ticked = (...ids: string[]): Record<string, DownloadedInfo> => Object.fromEntries(ids.map((id) => [id, info(id)]));
const entriesOf = (downloaded: Record<string, DownloadedInfo>): SceneEntry[] => Object.entries(downloaded);

// The scene on top of the scenes drawn one by one: the last raster of a single scene names it in its tile address (the
// mosaic, where there is one, lies over all of them from z8).
function topScene(downloaded: Record<string, DownloadedInfo>, mosaics: Mosaics): string {
  const live = liveMap();
  ensureBaseLayers(live.map as never);
  syncFocusRaster(live.map as never, { downloaded, render: {}, showDownloaded: true, items: [A, B], dataset, groups: [group], mosaics });
  const rasters = live.stack
    .filter((id) => /^[mn]-tiles-lyr-/.test(id))
    .map((id) => String((live.sources.get(live.layers.get(id)!.source!)!.tiles as string[])[0]))
    .filter((url) => url.includes('/items/'));
  return /items\/([A-Z])\//.exec(rasters.at(-1)!)![1];
}

// What the tiler gives for the two scenes, A first (the order of the mosaic job: the target CRS, then by id).
const mosaicOf = (downloaded: Record<string, DownloadedInfo>): Mosaics => ({
  [mosaicTemplateOf(dataset.id, entriesOf(downloaded))!]: {
    tileUrl: mosaicTemplateOf(dataset.id, entriesOf(downloaded))!,
    bounds: [10, 47, 11, 48],
    minZoom: 8,
    maxZoom: 14,
    order: ['A', 'B'],
  },
});
const refusedWithOrder = (downloaded: Record<string, DownloadedInfo>): Mosaics => ({
  [mosaicTemplateOf(dataset.id, entriesOf(downloaded))!]: null,
  [orderKeyOf(dataset.id, entriesOf(downloaded))!]: { order: ['A', 'B'] },
});
const refused = (downloaded: Record<string, DownloadedInfo>): Mosaics => ({
  [mosaicTemplateOf(dataset.id, entriesOf(downloaded))!]: null,
});

describe.each([
  ['A, then B', ['A', 'B']],
  ['B, then A', ['B', 'A']],
])('the overlap of two scenes ticked %s', (_name, order) => {
  const downloaded = ticked(...order);

  it('has the first scene of the mosaic order on top below the mosaic, as the mosaic reads it', () => {
    expect(topScene(downloaded, mosaicOf(downloaded))).toBe('A');
  });

  it('has the same scene on top where the tiler refused the mosaic and gave the order', () => {
    expect(topScene(downloaded, refusedWithOrder(downloaded))).toBe('A');
  });

  it('keeps the order of the selection where the tiler gave no order', () => {
    expect(topScene(downloaded, refused(downloaded))).toBe(order[0]);
  });
});
