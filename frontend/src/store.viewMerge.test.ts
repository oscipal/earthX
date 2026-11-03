// @vitest-environment jsdom
//
// "Crop to AOI" with a view open (Otto, 3.11.2026, zu #282): no second view. The scenes picked join the open one, as if its scenes and the
// new ones were ticked together and the button pressed (NM4-53): the same pass is merged into the same image, another day is a new step,
// another dataset an entry of the dataset dropdown. The look of the view stays; a layer that held the view no longer does ("Temporary").

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { datasetsFrom } from './datasets';
import { bboxToPolygon } from './geoUtils';
import { useAppStore, viewImagesOf } from './store';
import type { Collection, StacItem, TimeStepGroup } from './types';
import { datasetIdsOf } from './viewImages';
import { isTemporaryImage } from './viewLayer';

const collection = (id: string): Collection =>
  ({
    id,
    title: id,
    'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
    'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  }) as unknown as Collection;

const AOI = bboxToPolygon([10.1, 47.1, 10.4, 47.4]);
const scene = (id: string, day: string, dataset = 'optical'): StacItem => ({ id, collection: dataset, bbox: [10, 47, 11, 48], properties: { datetime: `${day}T10:00:00Z` }, assets: {} });
const group = (day: string, items: StacItem[]): TimeStepGroup => ({ key: [day], label: day, items }) as unknown as TimeStepGroup;

const OPTICAL = [scene('A1', '2026-07-24'), scene('A2', '2026-07-24'), scene('B1', '2026-07-25')];
const DEM = [scene('D1', '2026-07-24', 'dem')];
const GROUPS = [group('2026-07-24', OPTICAL.slice(0, 2)), group('2026-07-25', OPTICAL.slice(2))];

const state = () => useAppStore.getState();
const imagesNow = () => viewImagesOf(state());

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 404 })));
  useAppStore.setState({
    datasets: datasetsFrom([collection('optical'), collection('dem')]), selectedDatasetIds: ['optical', 'dem'], datasetId: 'optical', openSectionId: 'optical',
    items: OPTICAL, groups: GROUPS, sections: [
      { datasetId: 'optical', items: OPTICAL, groups: GROUPS },
      { datasetId: 'dem', items: DEM, groups: [group('2026-07-24', DEM)] },
    ] as never,
    activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: ['A1'], focusMode: false, cropToAoi: false, viewAoi: null, downloaded: {}, appliedRender: {},
    savedLooks: {}, viewLooks: {}, shownImage: null, mosaics: {}, layers: [], viewLayerId: null, resultViewLayerId: null, aoi: AOI, error: null, notice: null,
    pinLoading: false, resultsOnMap: true,
  });
});
afterEach(() => vi.unstubAllGlobals());

describe('"Crop to AOI" with a view open', () => {
  it('merges a scene of the same pass into the same image: still one view, one image, no new view', async () => {
    await state().enterFocus(true);
    expect(Object.keys(state().downloaded)).toEqual(['A1']);
    useAppStore.setState({ selectedIds: ['A2'] });
    await state().enterFocus(true);
    expect(Object.keys(state().downloaded).sort()).toEqual(['A1', 'A2']);
    expect(imagesNow().map((image) => image.ids.sort())).toEqual([['A1', 'A2']]);
    expect(state().focusMode).toBe(true);
    // A crop drops the tick of the scenes it was made of, as it always did.
    expect(state().selectedIds).toEqual([]);
  });

  it('makes another day a new step of the view', async () => {
    await state().enterFocus(true);
    useAppStore.setState({ selectedIds: ['B1'] });
    await state().enterFocus(true);
    expect(imagesNow().map((image) => image.ids)).toEqual([['A1'], ['B1']]);
    // The step that was made is the one shown.
    expect(imagesNow().find((image) => image.key === state().shownImage)?.ids).toEqual(['B1']);
  });

  it('makes another dataset an entry of the dataset dropdown', async () => {
    await state().enterFocus(true);
    useAppStore.setState({ selectedIds: ['D1'] });
    await state().enterFocus(true);
    expect(datasetIdsOf(imagesNow())).toEqual(['optical', 'dem']);
    expect(Object.keys(state().downloaded).sort()).toEqual(['A1', 'D1']);
  });

  it('keeps the look of the view: the range and colormap the person set stay on the image they were set on', async () => {
    await state().enterFocus(true);
    useAppStore.setState({ appliedRender: { rescale: '100,900', colormapName: 'viridis' }, pendingVmin: '100', pendingVmax: '900', selectedIds: ['A2'] });
    await state().enterFocus(true);
    expect(state().appliedRender).toEqual({ rescale: '100,900', colormapName: 'viridis' });
    expect(state().pendingVmin).toBe('100');
    // Another day starts from the look of its dataset; the image that was left keeps what it had.
    useAppStore.setState({ selectedIds: ['B1'] });
    await state().enterFocus(true);
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
    const left = imagesNow().find((image) => image.ids.includes('A1'))!;
    expect(state().viewLooks[left.key]).toEqual({ rescale: '100,900', colormapName: 'viridis' });
  });

  it('keeps the opacity, and the look saved for the dataset', async () => {
    await state().enterFocus(true);
    useAppStore.setState({ viewOpacity: 0.4, savedLooks: { optical: { rescale: '5,50' } }, selectedIds: ['B1'] });
    await state().enterFocus(true);
    expect(state().viewOpacity).toBe(0.4);
    expect(state().savedLooks.optical).toEqual({ rescale: '5,50' });
  });

  it('is "Temporary" where a layer held the view: the layer holds the scenes it was made of, not the ones with the new', async () => {
    await state().enterFocus(true);
    state().addCurrentToLayers();
    expect(state().layers).toHaveLength(1);
    const heldBefore = !isTemporaryImage(state().layers, imagesNow()[0], state().appliedRender, { cropToAoi: true, aoi: state().viewAoi });
    expect(heldBefore).toBe(true);
    useAppStore.setState({ selectedIds: ['A2'] });
    await state().enterFocus(true);
    expect(isTemporaryImage(state().layers, imagesNow()[0], state().appliedRender, { cropToAoi: true, aoi: state().viewAoi })).toBe(true);
    // The layer itself is as it was: it keeps its one scene.
    expect(state().layers).toHaveLength(1);
    expect(Object.keys(state().layers[0].restore.downloaded)).toEqual(['A1']);
  });

  it('crops all of them to the area when it is pressed, and views all of them whole with "View whole scene"', async () => {
    await state().enterFocus(false);
    expect(state().cropToAoi).toBe(false);
    useAppStore.setState({ selectedIds: ['A2'] });
    await state().enterFocus(true);
    expect(state().cropToAoi).toBe(true);
    expect(state().viewAoi).toEqual(AOI);
    useAppStore.setState({ selectedIds: ['B1'] });
    await state().enterFocus(false);
    expect(state().cropToAoi).toBe(false);
    expect(state().viewAoi).toBeNull();
    expect(Object.keys(state().downloaded).sort()).toEqual(['A1', 'A2', 'B1']);
  });

  it('adds a scene the view has once, not twice', async () => {
    await state().enterFocus(false);
    // The tick of a whole scene stays; pressing again changes nothing of the scenes.
    await state().enterFocus(false);
    expect(Object.keys(state().downloaded)).toEqual(['A1']);
    expect(imagesNow()).toHaveLength(1);
  });

  it('needs an area for a crop, and then the view stays as it was', async () => {
    await state().enterFocus(false);
    useAppStore.setState({ aoi: null, selectedIds: ['B1'] });
    await state().enterFocus(true);
    expect(state().error).toMatch(/area of interest/u);
    expect(Object.keys(state().downloaded)).toEqual(['A1']);
    expect(state().focusMode).toBe(true);
  });

  // The counter-check: the callers that mean a new view (a dataset opened in full resolution, a scene looked up by name) say so.
  it('opens a new view instead, where it is told not to merge', async () => {
    await state().enterFocus(true);
    useAppStore.setState({ selectedIds: ['B1'] });
    await state().enterFocus(true, false);
    expect(Object.keys(state().downloaded)).toEqual(['B1']);
  });

  it('opens a view as always where none is open', async () => {
    await state().enterFocus(true);
    expect(Object.keys(state().downloaded)).toEqual(['A1']);
    expect(state().appliedRender).toEqual({ rescale: '0,3000' });
  });
});
