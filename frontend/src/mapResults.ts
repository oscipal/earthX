// What of the search results is on the map (Otto, 27.10.2026, zu #211): one function of the state, used by every
// place that draws or answers for them: the quicklooks of browsing, the ones over a full-resolution view, the crops a
// search draws by itself, the outline of the ticked scenes, and the click on a scene. Nothing else may decide it, a
// rebuild of the map included.
//
// The rules:
//  1. "Hide results" holds: no outline, quicklook or crop of a search result is on the map, whatever came before
//     (a view opened or left, a crop, a layer removed, a change of basemap or projection, "Load more", a new search).
//  2. The one exception is a ticked scene: it is on the map with its usual controls, hidden or not, and goes when
//     the tick goes.
//  3. Only the switch changes show/hide (`store.ts::toggleResultsOnMap`), no other button.

import { itemsForMap, itemsOverView } from './grouping';
import type { StacItem, TimeStepGroup } from './types';

export interface ResultsState {
  resultsOnMap: boolean;
  focusMode: boolean;
  groups: TimeStepGroup[];
  // The time step open in the list (null: all closed) and the one the view shows.
  expandedGroupIndex: number | null;
  selectedIds: readonly string[];
  // The scenes a full-resolution view draws itself, by id.
  downloaded: Record<string, unknown>;
}

export interface ResultsOnMap {
  // Browsing: the scenes whose quicklook is drawn.
  quicklooks: StacItem[];
  // Under a full-resolution view: the scenes whose quicklook lies below it (the results on, or the ticked ones).
  overlay: StacItem[];
  // The crops a search draws by itself: all of the chosen dataset, or only those of these ticked scenes.
  cropsOf: readonly string[] | null;
  // The scenes outlined as ticked.
  highlight: StacItem[];
  // The scenes a click on the map can pick or drop: those that are drawn.
  clickable: StacItem[];
}

const ticked = (groups: TimeStepGroup[], selectedIds: readonly string[]): StacItem[] =>
  groups.flatMap((group) => group.items).filter((item) => selectedIds.includes(item.id));

export function resultsOnMapOf(s: ResultsState): ResultsOnMap {
  const viewed = Object.keys(s.downloaded);
  const quicklooks = s.focusMode ? [] : itemsForMap(s.groups, s.resultsOnMap ? s.expandedGroupIndex : null, s.selectedIds);
  const overlay = s.focusMode ? itemsOverView(s.groups, s.expandedGroupIndex, s.selectedIds, s.resultsOnMap) : [];
  // The view's own scenes are drawn as well in a view, and can be picked or dropped like the others.
  const ofView = s.focusMode ? s.groups.flatMap((group) => group.items).filter((item) => viewed.includes(item.id)) : [];
  const clickable = [...new Map([...quicklooks, ...overlay, ...ofView].map((item) => [item.id, item])).values()];
  return {
    quicklooks,
    overlay,
    cropsOf: s.resultsOnMap ? null : s.selectedIds,
    highlight: ticked(s.groups, s.selectedIds),
    clickable,
  };
}
