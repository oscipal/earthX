// The picture a dataset shows below its first level where another dataset stands in (registry `viewer.overview:
// substitute`, plan M5-30b §4.8): swissALTI3D shows Copernicus DEM GLO-30 below z13. The tiler serves it on one route per
// dataset (`api.ts::buildOverviewTileTemplate`), in the look of the dataset that is drawn. It is a picture and nothing
// else: no text, no tooltip, no mark. Only the attribution line of the map names the substitute while it is drawn,
// which MapLibre does by itself for the `attribution` of a source whose layer is not hidden at the zoom.

import { buildOverviewTileTemplate } from './api';
import type { DatasetOption } from './datasets';
import { attributionText } from './download';
import type { PlannedRaster } from './mosaic';
import { firstZoomOf } from './tileSize';
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

// The raster below `dataset`'s first level, or `null` for a dataset without a substitute. The substitute has to be in the
// list (its attribution comes from its collection), and where its licence requires an attribution that cannot be written
// the picture is not drawn at all: the licence asks for the text, not for the picture.
export function substituteRasterOf(dataset: DatasetOption | null | undefined, datasets: readonly DatasetOption[] | undefined): PlannedRaster | null {
  if (!dataset?.viewable) return null;
  const viewer = dataset.collection['earthx:viewer'];
  if (viewer?.overview !== 'substitute' || !viewer.overview_substitute) return null;
  const firstLevel = dataset.zoom.min;
  const substitute = datasets?.find((d) => d.id === viewer.overview_substitute);
  const bounds = extentOf(dataset.collection);
  if (firstLevel < 1 || !substitute || !bounds) return null;
  const flags = substitute.collection['earthx:license_flags'];
  const attribution = attributionText(flags, null);
  if (flags?.attribution_required && !attribution) return null;
  const tileUrl = buildOverviewTileTemplate(dataset.id);
  return {
    tileUrl,
    bounds,
    minZoom: 0,
    // The substitute's own levels end where the dataset's begin; the layer steps aside for the mosaic (512 px, level L from
    // map zoom L - 0.5) as the scenes below a mosaic do (`mosaic.ts::viewOfPass`).
    maxZoom: firstLevel - 1,
    hideFrom: firstZoomOf(firstLevel, tileUrl),
    ...(attribution ? { attribution } : {}),
  };
}
