// The images of the full-resolution view (NM4-53). An image is one time step of one dataset: a group of the results
// with those of its scenes the view holds, merged. The view draws one image at a time and steps through the others.
// Pure functions; the state (`shownImage`, the looks) lives in `store.ts`.

import type { DatasetOption } from './datasets';
import type { ResultSection } from './sections';
import { searchFiltersOf } from './searchFilters';
import type { DownloadedInfo, StacItem } from './types';
import { viewDates } from './viewKind';

export interface ViewImage {
  // Dataset and group, as one text; stable while the view is open.
  key: string;
  datasetId: string;
  // The name of the group in the results list ("2025-07-29 · 32UQD"); empty for scenes no group holds any more.
  groupLabel: string;
  // The scenes of the group that the view holds.
  ids: string[];
  // The acquisition day (UTC) or the span of days; null for a product without an instant (the elevation model).
  date: string | null;
  // The satellites the scenes name (`properties.platform`), each once, in the registry's words where it has them.
  platforms: string[];
}

// What a view needs of a section of the results: the dataset, its scenes and their time steps.
export type ViewSection = Pick<ResultSection, 'datasetId' | 'items' | 'groups'>;

// The sections the view looks scenes up in: those of the last search, with the open one as the list shows it
// (`items` and `groups` mirror it). Where no section stands for the open dataset (a result put together by hand), the
// list's own scenes are a section of their own.
export function sectionsForView(s: {
  sections: readonly ViewSection[];
  openSectionId: string | null;
  datasetId: string | null;
  items: StacItem[];
  groups: ViewSection['groups'];
}): ViewSection[] {
  const open = s.openSectionId ?? s.datasetId;
  if (open === null) return [...s.sections];
  const here: ViewSection = { datasetId: open, items: s.items, groups: s.groups };
  return s.sections.some((x) => x.datasetId === open) ? s.sections.map((x) => (x.datasetId === open ? here : x)) : [here, ...s.sections];
}

const KEY_SEPARATOR = '\u0000';

// The scenes of a view that no group holds (a layer of an earlier search) make one image of their dataset.
const UNGROUPED = 'ungrouped';

// "Sentinel-2A" → "S2A"; every other label stays as it is. One rule for the naming of the Copernicus missions.
export function satelliteShort(label: string): string {
  const m = /^Sentinel-(\d+)([A-Za-z]?)$/u.exec(label.trim());
  return m ? `S${m[1]}${m[2].toUpperCase()}` : label;
}

// The label the registry gives a `platform` value (the choices of its filter), else the value itself.
export function platformLabel(dataset: DatasetOption | undefined, value: string): string {
  const filter = dataset ? searchFiltersOf(dataset.collection).find((f) => f.property === 'platform') : undefined;
  return filter?.values.find((v) => v.value === value)?.label ?? value;
}

const firstDay = (item: StacItem | undefined): string | null => {
  const value = item?.properties?.datetime;
  const date = typeof value === 'string' ? new Date(value) : null;
  return date && !Number.isNaN(date.getTime()) ? date.toISOString() : null;
};

// The images of `downloaded`: by dataset in the order of the sections, within a dataset by day, the earliest first
// (a product without a day keeps the order of its groups).
export function imagesOf(downloaded: Record<string, DownloadedInfo>, sections: readonly ViewSection[], datasets: readonly DatasetOption[]): ViewImage[] {
  const order = new Map(sections.map((section, i) => [section.datasetId, i]));
  const built = new Map<string, ViewImage & { rank: number; first: string | null; at: number }>();
  for (const [id, info] of Object.entries(downloaded)) {
    const section = sections.find((x) => x.datasetId === info.datasetId);
    const groupIndex = section ? section.groups.findIndex((g) => g.items.some((it) => it.id === id)) : -1;
    const group = section && groupIndex >= 0 ? section.groups[groupIndex] : undefined;
    const key = [info.datasetId, group ? group.key.join('\u0001') : UNGROUPED].join(KEY_SEPARATOR);
    let image = built.get(key);
    if (!image) {
      image = {
        key,
        datasetId: info.datasetId,
        groupLabel: group?.label ?? '',
        ids: [],
        date: null,
        platforms: [],
        rank: order.get(info.datasetId) ?? order.size,
        first: null,
        at: groupIndex >= 0 ? groupIndex : Number.MAX_SAFE_INTEGER,
      };
      built.set(key, image);
    }
    image.ids.push(id);
  }
  const dataset = (id: string) => datasets.find((d) => d.id === id);
  for (const image of built.values()) {
    const section = sections.find((x) => x.datasetId === image.datasetId);
    const items = image.ids.map((id) => section?.items.find((it) => it.id === id)).filter((it): it is StacItem => it !== undefined);
    image.date = viewDates(items);
    image.first = items.map(firstDay).filter((d): d is string => d !== null).sort()[0] ?? null;
    const values = new Set(items.map((it) => it.properties?.platform).filter((v): v is string => typeof v === 'string' && v !== ''));
    image.platforms = [...values].map((v) => platformLabel(dataset(image.datasetId), v));
  }
  return [...built.values()]
    .sort((a, b) => a.rank - b.rank || (a.first && b.first ? a.first.localeCompare(b.first) : 0) || a.at - b.at)
    .map(({ rank: _rank, first: _first, at: _at, ...image }) => image);
}

// The satellites of an image for the row: "S2A", or "S2A/S2B" where both took a scene of the step; "" for none.
export const satellitesOf = (image: ViewImage): string => image.platforms.map(satelliteShort).join('/');

// The distinct datasets of the images, in the order of the images.
export function datasetIdsOf(images: readonly ViewImage[]): string[] {
  return [...new Set(images.map((image) => image.datasetId))];
}

// The images of one dataset, in order.
export const imagesOfDataset = (images: readonly ViewImage[], datasetId: string): ViewImage[] => images.filter((image) => image.datasetId === datasetId);
