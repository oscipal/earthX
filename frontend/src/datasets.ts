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
import type { AppliedRender, Collection, EarthxDefaultRender, StacAsset, StacItem } from './types';

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
    }
  | { id: string; title: string; collection: Collection; viewable: false; reason: string };

export function groupByOf(collection: Collection): string[] | null {
  const groupBy = collection['earthx:viewer']?.group_by;
  return groupBy && groupBy.length > 0 ? groupBy : null;
}

// The registry's standard visualisation (M2-04/D20) — what full-resolution
// viewing (M2-07b) defaults to before the user touches the stretch/colormap
// controls. `null` when the dataset has not set one yet.
export function defaultRenderOf(collection: Collection): EarthxDefaultRender | null {
  return collection['earthx:default_render'] ?? null;
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

export function datasetsFrom(collections: Collection[]): DatasetOption[] {
  return collections.map((collection) => {
    const title = collection.title ?? collection.id;
    const groupBy = groupByOf(collection);
    const zoom = zoomRangeOf(collection);
    if (groupBy && zoom) {
      return { id: collection.id, title, collection, viewable: true, groupBy, zoom };
    }
    return {
      id: collection.id,
      title,
      collection,
      viewable: false,
      reason: groupBy
        ? 'earthx:viewer names no usable zoom range (min_zoom/max_zoom) for this dataset'
        : 'earthx:viewer.group_by is not set for this dataset',
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

// The quicklook asset, chosen generically: role `thumbnail`, then `overview`,
// then the first `image/*` asset. `null` when the item carries none.
export function quicklookAsset(item: StacItem): StacAsset | null {
  const assets = Object.values(item.assets ?? {});
  const byRole = (role: string): StacAsset | undefined =>
    assets.find((a) => a.roles?.includes(role));
  return (
    byRole('thumbnail') ?? byRole('overview') ?? assets.find((a) => a.type?.startsWith('image/')) ?? null
  );
}

// What the browse view can show for one scene before anyone asks for full
// resolution (M2-10, Otto F3 a).
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
// That equation holds while `min_zoom` is in the order of a scene, which is why
// `sentinel-2-l2a-zarr3` sets z8 ("one tile is about one scene", adr/0007 §12.10).
// For a dataset released from z0 the preview would be a world tile clipped to one
// item — nearly nothing. No dataset reaches that case today (the COG one publishes
// quicklooks, so it never takes this branch), and the day one does, the preview
// level is the thing to name in the registry, not a rule to bend here.
//
// The decision hangs on the item and the registry entry, never on a dataset id:
// a source that starts publishing thumbnails tomorrow gets them without a change
// here, and one that stops falls back to the tiles the same way.
export type QuicklookPlan =
  | { kind: 'image'; href: string }
  // `render` is the registry's standard visualisation, carried because a preview
  // tile needs the same stretch the full-resolution view uses — without it the
  // two views of one scene do not look like the same data (M2-10 review).
  | { kind: 'tiles'; asset: string; zoom: number; render: AppliedRender };

export function quicklookPlan(item: StacItem, dataset: DatasetOption): QuicklookPlan | null {
  const asset = quicklookAsset(item);
  if (asset?.href) return { kind: 'image', href: asset.href };
  if (!dataset.viewable) return null;
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
