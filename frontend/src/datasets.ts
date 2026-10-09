// What the viewer needs from `/stac/collections`: the pick list, each entry's
// grouping key and released zoom levels (`earthx:viewer`), how settled the
// source is (`earthx:maturity`), and what to show for one scene before anyone
// asks for full resolution.
//
// Nothing here has a default (KLAERUNGEN B10, Otto 20.09.2026 and 22.09.2026):
// a collection without `earthx:viewer.group_by` is a gap in the dataset's
// onboarding, not a case for a guessed key that could merge scenes that do not
// belong together, and one without a zoom range is a gap the tile route would
// answer with a 400 anyway. Such a dataset stays listed, marked as not
// viewable, so the viewer says what is missing instead of silently leaving it
// out — and every difference between two datasets comes from here, never from
// a branch on a dataset id somewhere in a component (M2-10).

import { appliedRenderFrom } from './render';
import type { AppliedRender, BrowseMode, Collection, EarthxDefaultRender, StacAsset, StacItem } from './types';

// The tile levels a dataset is released for (registry `ViewerInfo`, M2-10).
export interface ZoomRange {
  min: number;
  max: number;
}

// The same ceiling the registry enforces (`catalog.registry.MAX_TILE_ZOOM`), so a
// range the backend would never accept is not treated as viewable here either. It
// is also below MapLibre's own style limit of 24 — a source built with a larger
// `maxzoom` throws inside `addSource`, in the middle of a map sync, which is not
// where anyone would look for a registry mistake.
const MAX_TILE_ZOOM = 22;

export type DatasetOption =
  | {
      id: string;
      title: string;
      collection: Collection;
      viewable: true;
      groupBy: string[];
      zoom: ZoomRange;
      // M3-12: what the browse view shows, its quicklook freistellung threshold
      // if any, the results-list/download grouping key, and whether a chosen
      // time window means anything for this dataset — all read off the
      // registry, none of it a source-specific branch here (P10).
      browse: BrowseMode;
      quicklookNodataMax: number | null;
      resultsGroupBy: string[];
      hasTimeAxis: boolean;
    }
  | { id: string; title: string; collection: Collection; viewable: false; reason: string };

export function groupByOf(collection: Collection): string[] | null {
  const groupBy = collection['earthx:viewer']?.group_by;
  return groupBy && groupBy.length > 0 ? groupBy : null;
}

// M3-12: the key the results list and the download route (P19) group by —
// distinct from `group_by` above, which a dataset may deliberately not use for
// its own display (M3-02 F-01, e.g. Sentinel-2's day+MGRS-tile `group_by` vs.
// its day+overpass `results_group_by`).
export function resultsGroupByOf(collection: Collection): string[] | null {
  const resultsGroupBy = collection['earthx:viewer']?.results_group_by;
  return resultsGroupBy && resultsGroupBy.length > 0 ? resultsGroupBy : null;
}

const BROWSE_MODES: readonly BrowseMode[] = ['quicklook', 'preview_tiles', 'full_resolution'];

// What the browse view shows right after a search (M3-12), or `null` where the
// registry names none or names something this viewer does not recognise — the
// same "no guess" rule every other viewer field here follows.
export function browseOf(collection: Collection): BrowseMode | null {
  const browse = collection['earthx:viewer']?.browse;
  return browse && (BROWSE_MODES as string[]).includes(browse) ? browse : null;
}

// The freistellung threshold for a `browse: 'quicklook'` dataset (`mapLayers.ts`
// `NODATA_THRESHOLD`, M3-12 F-02) — `null` where the registry sets none, which
// is also the only legal value outside `browse: 'quicklook'`.
export function quicklookNodataMaxOf(collection: Collection): number | null {
  const value = collection['earthx:viewer']?.quicklook_nodata_max;
  return typeof value === 'number' ? value : null;
}

// Whether a chosen time window means anything for this dataset
// (`earthx:capabilities.time_range`, M3-12 F-06) — `null` where the registry
// has not set the capability at all (a gap, not "no axis").
export function timeAxisOf(collection: Collection): boolean | null {
  const value = collection['earthx:capabilities']?.time_range;
  return typeof value === 'boolean' ? value : null;
}

// English month abbreviations for `acquisitionNote` below — the interface is
// English-only (D25, D28), so this never reads the viewer's own locale.
const SHORT_MONTHS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
] as const;

function shortMonth(isoInstant: string): string | null {
  const parsed = new Date(isoInstant);
  if (Number.isNaN(parsed.getTime())) return null;
  return `${SHORT_MONTHS[parsed.getUTCMonth()]} ${parsed.getUTCFullYear()}`;
}

// The fixed text for a dataset without a time axis (Otto, 26.09.2026: "No time
// axis – acquired Dec 2010 to Jan 2015"), read from the collection's own STAC
// `extent.temporal.interval` — the same interval `earthx:capabilities.
// time_range=False` already says a chosen search window cannot narrow. `null`
// where the dataset has a time axis, or where the extent carries nothing this
// can format (an open interval says nothing a "No time axis" note could use).
export function acquisitionNote(collection: Collection): string | null {
  if (timeAxisOf(collection) !== false) return null;
  const interval = collection.extent?.temporal?.interval?.[0];
  const [start, end] = interval ?? [null, null];
  if (!start || !end) return null;
  const from = shortMonth(start);
  const to = shortMonth(end);
  if (!from || !to) return null;
  return `No time axis – acquired ${from} to ${to}`;
}

// The registry's standard visualisation (M2-04/D20) — what full-resolution
// viewing (M2-07b) defaults to before the user touches the stretch/colormap
// controls. `null` when the dataset has not set one yet.
export function defaultRenderOf(collection: Collection): EarthxDefaultRender | null {
  return collection['earthx:default_render'] ?? null;
}

// The asset georeferencing (`quicklookCoords`/`quicklookAoiPixelRings`,
// M3-12 review F-04) should read off of, rather than the `visual` literal those
// functions used to assume: the registry's own standard-visualisation asset,
// the same one full-resolution viewing renders by default. `undefined` where
// the dataset names none, which leaves those functions' `visual`/generic
// fallback in charge, unchanged.
export function preferredGeoreferencedAsset(dataset: DatasetOption): string | undefined {
  if (!dataset.viewable) return undefined;
  return defaultRenderOf(dataset.collection)?.assets?.[0];
}

// The released tile levels, or `null` where the dataset names none or names
// something that cannot be a range. No guessed range, for the same reason there
// is no guessed grouping key: below the lower bound a tile shows several scenes
// and above the upper one the source has nothing finer, and both answers differ
// per dataset. The tile route refuses a level outside the range with a 400, so a
// guess here would only turn a registry gap into a wall of failed tiles.
export function zoomRangeOf(collection: Collection): ZoomRange | null {
  const viewer = collection['earthx:viewer'];
  if (!viewer) return null;
  const { min_zoom: min, max_zoom: max } = viewer;
  if (!Number.isInteger(min) || !Number.isInteger(max)) return null;
  if (min < 0 || max > MAX_TILE_ZOOM || min > max) return null;
  return { min, max };
}

// The first reason a dataset is not viewable, checked in this order so a
// broken entry always points at the field to fix first. Called only once at
// least one of the four is missing (`datasetsFrom` below) — when every other
// one is present, the caller's own gate already knows `hasTimeAxis` is the
// null one, so there is nothing left for this function to take or check.
function viewabilityGap(
  groupBy: string[] | null,
  zoom: ZoomRange | null,
  browse: BrowseMode | null,
  resultsGroupBy: string[] | null,
): string {
  if (!groupBy) return 'earthx:viewer.group_by is not set for this dataset';
  if (!zoom) return 'earthx:viewer names no usable zoom range (min_zoom/max_zoom) for this dataset';
  if (!browse) return 'earthx:viewer.browse is not set for this dataset';
  if (!resultsGroupBy) return 'earthx:viewer.results_group_by is not set for this dataset';
  return 'earthx:capabilities.time_range is not set for this dataset';
}

export function datasetsFrom(collections: Collection[]): DatasetOption[] {
  return collections.map((collection) => {
    const title = collection.title ?? collection.id;
    const groupBy = groupByOf(collection);
    const zoom = zoomRangeOf(collection);
    const browse = browseOf(collection);
    const resultsGroupBy = resultsGroupByOf(collection);
    const hasTimeAxis = timeAxisOf(collection);
    if (groupBy && zoom && browse && resultsGroupBy && hasTimeAxis !== null) {
      return {
        id: collection.id,
        title,
        collection,
        viewable: true,
        groupBy,
        zoom,
        browse,
        quicklookNodataMax: quicklookNodataMaxOf(collection),
        resultsGroupBy,
        hasTimeAxis,
      };
    }
    return {
      id: collection.id,
      title,
      collection,
      viewable: false,
      reason: viewabilityGap(groupBy, zoom, browse, resultsGroupBy),
    };
  });
}

// How settled the source is (`earthx:maturity`), as the one line the interface
// shows for it — `null` for a settled source, which needs no warning. An unknown
// value is passed through rather than swallowed: a provider label nobody has
// taught the viewer about still belongs in front of the user.
export function maturityLabel(collection: Collection): string | null {
  const maturity = collection['earthx:maturity'];
  if (typeof maturity !== 'string' || maturity === '' || maturity === 'stable') return null;
  return maturity;
}

export function maturityNote(collection: Collection): string | null {
  const maturity = maturityLabel(collection);
  if (maturity === null) return null;
  if (maturity === 'staging') {
    return 'staging: the provider may withdraw this collection without notice';
  }
  if (maturity === 'experimental') {
    return 'experimental: the provider offers no stability for this collection';
  }
  return maturity;
}

// Why the map shows no imagery for this dataset at this zoom, or `null` when
// that is not the reason (M2-10).
//
// Below `min_zoom` MapLibre requests no tiles at all — a raster source has no
// underzoom — so the scenes simply are not drawn, and the map looks empty rather
// than out of range. Above the floor this says nothing: an empty map then has
// some other cause, and a hint that is always on is a hint nobody reads.
//
// Two limits worth knowing. It speaks for the *tile* paths, which is what a
// released range bounds: a published quicklook is placed as an image and has no
// floor, so for a dataset with `min_zoom > 0` whose items carry thumbnails this
// would be wrong — no entry is in that position today (the COG one releases from
// z0). And it follows the map's `moveend`, so during a long zoom gesture the map
// is already empty while this still says nothing.
//
// M3-12 (Otto, 26.09.2026): only for `browse: 'preview_tiles'` — a dataset with
// no coarse-tile preview at all (`full_resolution`, the DEM) shows no "zoom in"
// hint when zoomed out; its tiles are per-item (M3-09), so there is nothing a
// released range would be hiding several scenes behind (M3-12 plan step §3).
//
// It belongs wherever the app talks to the user and not in a panel that can be
// slid away: the first version of this sat in the control panel, which
// `runSearch` collapses, so it was never once visible in the situation it is
// for (found locally by Otto, 22.09.2026).
export function zoomFloorHint(dataset: DatasetOption | undefined, mapZoom: number): string | null {
  // A zoom that is not a number compares false against everything, which would
  // otherwise turn a broken reading into a standing hint.
  if (!Number.isFinite(mapZoom)) return null;
  if (!dataset?.viewable || dataset.browse !== 'preview_tiles' || mapZoom >= dataset.zoom.min) return null;
  return (
    `Zoom in to level ${dataset.zoom.min} to see imagery for ${dataset.title} — ` +
    'below it one tile covers several scenes, which is what the coverage layer is for.'
  );
}

// The quicklook asset, chosen generically: role `thumbnail`, then `overview`,
// then the first `image/*` asset. `null` when the item carries none.
// Media types a browser can actually decode behind an `<img>` tag — found
// while answering Otto's question on F-04 (26.09.2026): `image/tiff` also
// starts with `image/`, so the generic fallback below used to treat the
// DEM's own COG (`type: "image/tiff; …"`, no `thumbnail`/`overview` role) as
// a browsable quicklook. Placement (`quicklookCoords`) already fails safe for
// the DEM today, because its asset carries no `proj:transform` either — but
// that is a second, unrelated reason nothing gets drawn, not something this
// function should keep depending on. A COG is data, never a quicklook.
const BROWSABLE_IMAGE_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];

export function quicklookAsset(item: StacItem): StacAsset | null {
  const assets = Object.values(item.assets ?? {});
  const byRole = (role: string): StacAsset | undefined =>
    assets.find((a) => a.roles?.includes(role));
  const byBrowsableType = (): StacAsset | undefined =>
    assets.find((a) => a.type && BROWSABLE_IMAGE_TYPES.some((t) => a.type!.startsWith(t)));
  return byRole('thumbnail') ?? byRole('overview') ?? byBrowsableType() ?? null;
}

// What the browse view can show for one scene before anyone asks for full
// resolution (M2-10, Otto F3 a; M3-12 F-05).
//
// `image` is a ready-made quicklook the source publishes; the browser loads it
// straight from the asset host (D14). `tiles` is the substitute for a source that
// publishes none at all — `sentinel-2-l2a-zarr3` has no asset with a `thumbnail`,
// `overview`, `preview` or `visual` role anywhere (adr/0007 §12.7). The substitute
// is a tile URL on the coarsest level the dataset releases, which for that dataset
// is z8 and reads `r720m`: 38 kB and 0.6 s, measured (adr/0007 §12.4). No extra
// registry field defines "the preview level" — the coarsest released level *is*
// the preview, and everything above it is overzoomed, which is what a quicklook is.
//
// That equation only holds while `min_zoom` is in the order of a scene, which is
// why `sentinel-2-l2a-zarr3` sets z8 ("one tile is about one scene", adr/0007
// §12.10) — for a dataset released globally from z0 the tile fallback would be a
// world tile clipped to one item, nearly nothing (M3-02 F-05). `earthx:viewer.
// browse` (M3-12) is the registry saying which of the two applies, rather than
// this function guessing from the released range: `preview_tiles` for a source
// like the Zarr one, `full_resolution` for a source with neither a quicklook nor
// a meaningful coarse tile (the DEM) — that one returns `null` here and the
// viewer shows the AOI crop in full resolution directly instead (`store.ts`).
//
// An item's own quicklook still wins first regardless of `browse`: a source that
// starts publishing thumbnails tomorrow gets them without a change here, and one
// that stops falls back to whatever `browse` says next.
export type QuicklookPlan =
  | { kind: 'image'; href: string }
  // `render` is the registry's standard visualisation, carried because a preview
  // tile needs the same stretch the full-resolution view uses — without it the
  // two views of one scene do not look like the same data (M2-10 review).
  | { kind: 'tiles'; asset: string; zoom: number; render: AppliedRender };

export function quicklookPlan(item: StacItem, dataset: DatasetOption): QuicklookPlan | null {
  const asset = quicklookAsset(item);
  if (asset?.href) return { kind: 'image', href: asset.href };
  if (!dataset.viewable || dataset.browse !== 'preview_tiles') return null;
  const render = defaultRenderOf(dataset.collection);
  const rendered = render?.assets?.[0];
  if (!render || !rendered) return null;
  return {
    kind: 'tiles',
    asset: rendered,
    zoom: dataset.zoom.min,
    render: appliedRenderFrom(render),
  };
}
