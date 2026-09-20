// What the viewer needs from `/stac/collections`: the pick list, each entry's
// grouping key (`earthx:viewer.group_by`), and which quicklook asset to show.
//
// No default grouping key (KLAERUNGEN B10, Otto 20.09.2026): a collection
// without `earthx:viewer.group_by` is a gap in the dataset's onboarding, not
// a case for a guessed key that could merge scenes that do not belong
// together. Such a dataset stays listed, marked as not viewable, so the
// viewer says what is missing instead of silently leaving it out.

import type { Collection, EarthxDefaultRender, StacAsset, StacItem } from './types';

export type DatasetOption =
  | { id: string; title: string; collection: Collection; viewable: true; groupBy: string[] }
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

export function datasetsFrom(collections: Collection[]): DatasetOption[] {
  return collections.map((collection) => {
    const title = collection.title ?? collection.id;
    const groupBy = groupByOf(collection);
    if (groupBy) {
      return { id: collection.id, title, collection, viewable: true, groupBy };
    }
    return {
      id: collection.id,
      title,
      collection,
      viewable: false,
      reason: 'earthx:viewer.group_by is not set for this dataset',
    };
  });
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
