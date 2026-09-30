// The results list's per-dataset sections (M3-10): one search over several
// datasets comes back as a single flat page of items, and this turns it into
// one section per dataset — each with its own time-step groups (the dataset's
// own `results_group_by`) and the notes that belong in its head. Pure functions
// only; the store decides what to do with the result.

import type { IncompleteCollection } from './api';
import type { DatasetOption } from './datasets';
import { acquisitionNote } from './datasets';
import { buildGroups, MissingProperty } from './grouping';
import type { StacItem, TimeStepGroup } from './types';

type ViewableDataset = Extract<DatasetOption, { viewable: true }>;

export interface ResultSection {
  datasetId: string;
  items: StacItem[];
  groups: TimeStepGroup[];
  // What the section head says besides the count, in order: dropped filters,
  // an unreachable source, a grouping failure, or that nothing was found.
  notes: string[];
  // Set when the scenes could not be grouped (a grouping property missing on an
  // item, `grouping.ts::MissingProperty`): the section then holds no scenes.
  groupingError: string | null;
  // Where the scenes come from: the search itself, the ±90-day fallback run for
  // this dataset (M3-10b), or a lookup by scene name.
  origin: 'search' | 'fallback' | 'name';
  // The source did not answer in full (`incomplete_collections`): an empty
  // section then says nothing about the date range.
  incomplete: boolean;
}

export const NO_SCENES_NOTE = 'No scenes for this area.';

// Why a source did not answer, in the words of the head (the reasons are
// `api/mixed_search.py`'s four; anything else still gets named).
export function incompleteNote(reason: string): string {
  switch (reason) {
    case 'timeout':
      return 'Results incomplete: the source timed out.';
    case 'unreachable':
      return 'Results incomplete: the source was not reachable.';
    case 'upstream_error':
      return 'Results incomplete: the source reported an error.';
    case 'unrecognised_answer':
      return 'Results incomplete: the source sent an unreadable answer.';
    default:
      return `Results incomplete (${reason}).`;
  }
}

// A dropped `datetime` is the case the interface has fixed wording for (M3-11b
// F11: "No time axis – acquired Dec 2010 to Jan 2015"); any other dropped
// filter is named as it came.
function ignoredFilterNote(dataset: ViewableDataset, filter: string): string {
  if (filter === 'datetime') {
    return acquisitionNote(dataset.collection) ?? 'No time axis – the date range does not apply.';
  }
  return `Filter not applied: ${filter}`;
}

export interface SectionSearchAnswer {
  ignoredFilters: readonly string[];
  ignoredFiltersByCollection: Readonly<Record<string, readonly string[]>>;
  incompleteCollections: readonly IncompleteCollection[];
}

// One section per searched dataset, in the order given, from the flat list a
// (mixed) search returned. `stray` counts items whose `collection` names none of
// the searched datasets (or none at all): they are left out of every section
// rather than guessed into one, and the caller says so. With exactly one dataset
// searched there is nothing to tell apart, so every item is that dataset's.
export function buildSections(
  features: readonly StacItem[],
  datasets: readonly ViewableDataset[],
  answer: SectionSearchAnswer,
): { sections: ResultSection[]; stray: number } {
  const byDataset = new Map<string, StacItem[]>(datasets.map((d) => [d.id, []]));
  let stray = 0;
  for (const item of features) {
    const owner = datasets.length === 1 ? datasets[0].id : item.collection;
    const bucket = typeof owner === 'string' ? byDataset.get(owner) : undefined;
    if (bucket) bucket.push(item);
    else stray += 1;
  }
  const sections = datasets.map((dataset): ResultSection => {
    const items = byDataset.get(dataset.id) ?? [];
    const notes: string[] = [];
    // A search over one source may name no per-collection breakdown; its flat
    // list can then only mean that source.
    const ignored = Object.hasOwn(answer.ignoredFiltersByCollection, dataset.id)
      ? answer.ignoredFiltersByCollection[dataset.id]
      : datasets.length === 1
        ? answer.ignoredFilters
        : [];
    for (const filter of ignored) notes.push(ignoredFilterNote(dataset, filter));
    const incomplete = answer.incompleteCollections.find((entry) => entry.collection === dataset.id);
    if (incomplete) notes.push(incompleteNote(incomplete.reason));
    let groups: TimeStepGroup[] = [];
    let kept = items;
    let groupingError: string | null = null;
    try {
      groups = buildGroups(items, dataset.resultsGroupBy);
    } catch (e) {
      if (!(e instanceof MissingProperty)) throw e;
      // Only this dataset's section loses its scenes; the others stay.
      kept = [];
      groupingError = e.message;
      notes.push(`Grouping failed: ${e.message}`);
    }
    if (kept.length === 0 && notes.length === 0) notes.push(NO_SCENES_NOTE);
    return { datasetId: dataset.id, items: kept, groups, notes, groupingError, origin: 'search', incomplete: !!incomplete };
  });
  return { sections, stray };
}

// Two answers of one search as one (a first walk and its "Load more"): as within
// a walk (`api.searchAllPages`), the first answer that names a collection's
// dropped filters speaks for the whole search, and every source that failed on
// any page stays named, once.
export function combineAnswers(first: SectionSearchAnswer, next: SectionSearchAnswer): SectionSearchAnswer {
  const incomplete = [...first.incompleteCollections];
  for (const entry of next.incompleteCollections) {
    if (!incomplete.some((known) => known.collection === entry.collection)) incomplete.push(entry);
  }
  return {
    ignoredFilters: first.ignoredFilters.length > 0 ? first.ignoredFilters : next.ignoredFilters,
    ignoredFiltersByCollection: { ...next.ignoredFiltersByCollection, ...first.ignoredFiltersByCollection },
    incompleteCollections: incomplete,
  };
}

// Whether the ±90-day fallback (`dateFallback.ts`) is due for a section chosen in
// the dropdown (M3-10 F7, Otto 30.09.2026): the search found nothing for it in a
// date range, its source answered in full, and a date range means something to
// it. It runs once per section — a section it has run for has another origin.
export function needsFallback(
  section: ResultSection,
  dataset: ViewableDataset,
  dateFrom: string,
  dateTo: string,
): boolean {
  return (
    section.origin === 'search' &&
    section.items.length === 0 &&
    section.groupingError === null &&
    !section.incomplete &&
    dataset.hasTimeAxis &&
    (dateFrom !== '' || dateTo !== '')
  );
}

// The section that is open right after a search (M3-10 F2): the first, in the
// datasets' list order, that has scenes.
export function firstSectionWithItems(sections: readonly ResultSection[]): ResultSection | null {
  return sections.find((section) => section.items.length > 0) ?? null;
}

export function totalItems(sections: readonly ResultSection[]): number {
  return sections.reduce((sum, section) => sum + section.items.length, 0);
}

// Whether the results panel has anything to show: scenes, or several datasets
// whose sections can say why they have none. A single dataset with nothing found
// is the search notice's business alone. The panel never disappears because of
// what is chosen in it (M3-10).
export function hasResultsPanel(sections: readonly ResultSection[]): boolean {
  return totalItems(sections) > 0 || sections.length > 1;
}
