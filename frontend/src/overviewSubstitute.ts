// The picture a dataset shows below its first level where it has no original files to draw (registry `viewer.overview:
// substitute` or `pyramid`, plan M5-30b §4.8 and part 9): swissALTI3D shows Copernicus DEM GLO-30 below z13, GLO-30 and
// WorldCover show their own overview pyramid below z7 and z5. The tiler serves it on one route per dataset
// (`api.ts::buildOverviewTileTemplate`), in the look of the dataset that is drawn. It is a picture: no mark, no text over the map.
// Only the attribution line of the map names its source while it is drawn, which MapLibre does by itself for the `attribution` of a
// source whose layer is not hidden at the zoom; and the tooltip of a pyramid dataset's layer says what the picture is (`overviewNoteOf`).

import { buildOverviewTileTemplate, type ShownBands, type TileStep } from './api';
import type { DatasetOption } from './datasets';
import { attributionText } from './download';
import type { PlannedRaster } from './mosaic';
import { firstZoomOf } from './tileSize';
import { scalingOfBand } from './viewBand';
import type { Bbox, Collection } from './types';

// The latitudes a Web Mercator map reaches; a source with a bound beyond them would not load.
const MAX_LATITUDE = 85.0511;

// The surface of the dataset that is drawn, from its collection: the picture lies where the dataset does, so that a map
// fitted to the layer is not fitted to the world. `null` where the collection names no usable box.
function extentOf(collection: Collection): Bbox | null {
  const box = collection.extent?.spatial?.bbox?.[0];
  if (!box || box.length < 4 || !box.slice(0, 4).every(Number.isFinite)) return null;
  const [west, south, east, north] = box;
  return [west, Math.max(south, -MAX_LATITUDE), east, Math.min(north, MAX_LATITUDE)];
}

// The raster below `dataset`'s first level, or `null` for a dataset that draws nothing there but its own files. Two ways, one
// route (`api.ts::buildOverviewTileTemplate`): a dataset with `overview: substitute` draws another dataset of the list (it has
// to be in the list: its attribution comes from its collection); one with `overview: pyramid` draws its own pyramid, which the
// platform builds from the original files (plan M5-30b part 9), under its own attribution for modified data. Where the licence
// requires an attribution that cannot be written the picture is not drawn at all: the licence asks for the text, not for the
// picture.
//
// With `chain` the picture is computed: the tiler runs the steps of a preview or an index on the picture of the overview (M5-10
// part B, G1), so that nothing computed disappears below the first level either; `computedNoteOf` says what it is.
export interface OverviewChain {
  steps: readonly TileStep[];
  band: ShownBands;
}

export function overviewRasterOf(
  dataset: DatasetOption | null | undefined,
  datasets: readonly DatasetOption[] | undefined,
  chain: OverviewChain | null = null,
): PlannedRaster | null {
  if (!dataset?.viewable) return null;
  const viewer = dataset.collection['earthx:viewer'];
  if (viewer?.overview !== 'substitute' && viewer?.overview !== 'pyramid') return null;
  const firstLevel = dataset.zoom.min;
  const drawn = viewer.overview === 'pyramid' ? dataset : datasets?.find((d) => d.id === viewer.overview_substitute);
  const bounds = extentOf(dataset.collection);
  if (firstLevel < 1 || !drawn || !bounds) return null;
  const flags = drawn.collection['earthx:license_flags'];
  const attribution = attributionText(flags, null);
  if (flags?.attribution_required && !attribution) return null;
  const tileUrl = chain ? buildOverviewTileTemplate(dataset.id, chain.steps, chain.band) : buildOverviewTileTemplate(dataset.id);
  // Without steps the overview draws the stored numbers of the band of the standard picture; no item is at hand, so the registry's
  // scaling turns the physical range of the view into them (M5-68). With steps the values are physical already.
  const scaling = chain ? null : scalingOfBand(drawn.collection, drawn.collection['earthx:default_render']?.assets[0]);
  return {
    tileUrl,
    bounds,
    minZoom: 0,
    // The picture's own levels end where the dataset's begin; the layer steps aside for the mosaic (512 px, level L from
    // map zoom L - 0.5) as the scenes below a mosaic do (`mosaic.ts::viewOfPass`).
    maxZoom: firstLevel - 1,
    hideFrom: firstZoomOf(firstLevel, tileUrl),
    ...(attribution ? { attribution } : {}),
    ...(scaling ? { scaling } : {}),
  };
}

// The sentence the tooltip of a layer of this dataset adds for its pyramid, or `null` for any other dataset: below the first level
// the map shows an overview that the platform resampled from the original files. Nothing but a tooltip: no mark on the map or in the
// row (Otto, 11.11.2026, `adr/0032` §14 F12). A substitute says nothing at all (plan M5-30b §4.8).
export function overviewNoteOf(dataset: DatasetOption | null | undefined): string | null {
  if (!dataset?.viewable || dataset.collection['earthx:viewer']?.overview !== 'pyramid' || dataset.zoom.min < 1) return null;
  const from = Math.ceil(firstZoomOf(dataset.zoom.min, buildOverviewTileTemplate(dataset.id)));
  return `Below zoom ${from} the map shows an overview of ${dataset.title}, resampled from the original files; zoom in to ${from} for the originals.`;
}

// `overviewNoteOf` as the field of a layer the tooltip of its name reads (`MapLayer.note`), for the places that make a layer; for a
// computed picture (an index, a preview) `computedNoteOf`.
export function noteOfOverview(
  dataset: DatasetOption | null | undefined,
  computed: { datasets: readonly DatasetOption[] } | null = null,
): { note?: string } {
  const note = computed ? computedNoteOf(dataset, computed.datasets) : overviewNoteOf(dataset);
  return note ? { note } : {};
}

// The sentence of the tooltip of a computed picture below the first level (a preview, an index; M5-10 part B, G2): it is computed
// from an overview, the pyramid of the dataset or the picture that stands in for it, and only the originals give its values. For a
// substitute as well: the values are those of another dataset. `null` where nothing is drawn below the first level.
export function computedNoteOf(dataset: DatasetOption | null | undefined, datasets: readonly DatasetOption[] | undefined): string | null {
  if (!dataset?.viewable || !overviewRasterOf(dataset, datasets)) return null;
  const viewer = dataset.collection['earthx:viewer'];
  const drawn = viewer?.overview === 'pyramid' ? dataset : datasets?.find((d) => d.id === viewer?.overview_substitute);
  const from = Math.ceil(firstZoomOf(dataset.zoom.min, buildOverviewTileTemplate(dataset.id)));
  return `Below zoom ${from} this is computed from an overview of ${drawn?.title ?? dataset.title}, resampled from the original files; zoom in to ${from} for values from the originals.`;
}
