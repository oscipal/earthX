import { maturityLabel, quicklookAsset } from '../datasets';
import type { ResultSection } from '../sections';
import { hasResultsPanel, totalItems } from '../sections';
import { useAppStore } from '../store';
import type { StacItem, TimeStepGroup } from '../types';
import CopyButton from './CopyButton';
import DatasetSelect from './DatasetSelect';

function timeOf(properties: Record<string, unknown>): string {
  const dt = properties['datetime'];
  if (typeof dt !== 'string') return '';
  const d = new Date(dt);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(11, 19) + 'Z';
}

function Row({ item }: { item: StacItem }) {
  const selectedIds = useAppStore((s) => s.selectedIds);
  const toggleSelected = useAppStore((s) => s.toggleSelected);
  const selected = selectedIds.includes(item.id);
  const asset = quicklookAsset(item);

  return (
    <li className={`result-row${selected ? ' selected' : ''}`} onClick={() => toggleSelected(item.id)}>
      <input
        type="checkbox"
        checked={selected}
        title="Select this scene"
        onClick={(e) => e.stopPropagation()}
        onChange={() => toggleSelected(item.id)}
        aria-label={`Select ${item.id}`}
      />
      {asset ? (
        <img
          className="result-thumb"
          src={asset.href}
          alt=""
          loading="lazy"
          onError={(e) => (e.currentTarget.style.visibility = 'hidden')}
        />
      ) : (
        // No preview image on this item (for a Zarr dataset that is every
        // item, adr/0007 §12.7), and the substitute is a map tile rather than a
        // picture per row (M2-10, F4 a) — so the row says why it is empty instead
        // of looking broken. It says only that, and not what the map does: whether
        // the scene shows there depends on the dataset's standard visualisation and
        // on the zoom, neither of which this row knows.
        <span
          className="result-thumb placeholder"
          title="No preview image for this scene"
        />
      )}
      <div className="result-meta">
        <span className="result-date">{timeOf(item.properties)}</span>
        <span className="result-id-row">
          <span className="result-id" title={item.id}>
            {item.id}
          </span>
          <CopyButton text={item.id} title="Copy scene name" label={`Copy scene name ${item.id}`} />
        </span>
      </div>
    </li>
  );
}

// A check box tri-state for a set of scenes: ticked when all are selected, empty
// when none is; ticking selects them all, unticking deselects them all.
function SelectBox({
  checked,
  partial,
  label,
  onChange,
}: {
  checked: boolean;
  partial: boolean;
  label: string;
  onChange: () => void;
}) {
  return (
    <label className="select-all-box">
      <input
        type="checkbox"
        checked={checked}
        ref={(el) => {
          if (el) el.indeterminate = partial;
        }}
        onChange={onChange}
      />
      {label}
    </label>
  );
}

function GroupSelectBox({ group, index }: { group: TimeStepGroup; index: number }) {
  const count = useAppStore((s) => group.items.filter((it) => s.selectedIds.includes(it.id)).length);
  const toggleGroupSelected = useAppStore((s) => s.toggleGroupSelected);
  const all = count === group.items.length;
  return (
    <input
      type="checkbox"
      className="rg-select"
      checked={all}
      ref={(el) => {
        if (el) el.indeterminate = count > 0 && !all;
      }}
      title={`Select all scenes of ${group.label}`}
      aria-label={`Select all scenes of ${group.label}`}
      onChange={() => toggleGroupSelected(index)}
    />
  );
}

function GroupBlock({
  group,
  index,
  expanded,
  onToggle,
}: {
  group: TimeStepGroup;
  index: number;
  expanded: boolean;
  onToggle: (index: number) => void;
}) {
  return (
    <div className={`result-group${expanded ? ' active' : ''}`}>
      <div className="result-group-row">
        <GroupSelectBox group={group} index={index} />
        <button type="button" className="result-group-head" onClick={() => onToggle(index)}>
          <span className="rg-caret">{expanded ? '▾' : '▸'}</span>
          <span className="rg-label" title={group.label}>
            {group.label}
          </span>
          <span className="rg-count">{group.items.length}</span>
        </button>
      </div>
      {expanded && (
        <ul className="rg-items">
          {group.items.map((it) => (
            <Row key={it.id} item={it} />
          ))}
        </ul>
      )}
    </div>
  );
}

// One dataset's entry in the box and in the dropdown (M3-10): title, maturity
// chip, scene count, and under them the notes that belong to it — dropped
// filters, an unreachable source, a grouping failure, the ±90-day fallback.
function SectionSummary({ section }: { section: ResultSection }) {
  const lookingForDate = useAppStore((s) => s.fallbackDatasetIds.includes(section.datasetId));
  const title = useAppStore((s) => s.datasets.find((d) => d.id === section.datasetId)?.title ?? section.datasetId);
  const label = useAppStore((s) => {
    const dataset = s.datasets.find((d) => d.id === section.datasetId);
    return dataset?.viewable ? maturityLabel(dataset.collection) : null;
  });
  return (
    <>
      <span className="dataset-select-line">
        <span className="dataset-select-title" title={title}>
          {title}
        </span>
        {label && <span className="maturity-chip">{label}</span>}
        <span className="rg-count">{section.items.length}</span>
      </span>
      {lookingForDate ? (
        <span className="dataset-select-note">Looking for the nearest date with scenes…</span>
      ) : (
        section.notes.map((note, i) => (
          <span key={`${i}-${note}`} className="dataset-select-note">
            {note}
          </span>
        ))
      )}
    </>
  );
}

// The box at the top of the results (M3-10, Otto 30.09.2026): it names the
// dataset whose scenes the list shows — the active dataset, which heatmap,
// quicklooks and full resolution follow — and opens a list of every searched
// dataset to switch (`DatasetSelect`). Choosing never closes the panel.
function DatasetDropdown({ sections, openId }: { sections: ResultSection[]; openId: string | null }) {
  const setOpenSection = useAppStore((s) => s.setOpenSection);
  const shown = sections.find((section) => section.datasetId === openId) ?? sections[0];
  if (!shown) return null;
  return (
    <DatasetSelect
      label="Showing dataset"
      labelId="dataset-select-label"
      listLabel="Searched datasets"
      choices={sections.map((section) => ({ id: section.datasetId, content: <SectionSummary section={section} /> }))}
      shownId={shown.datasetId}
      onChoose={setOpenSection}
    />
  );
}

// "Load more" (M3-10 F1) continues the whole search with one page token, but
// the row belongs to the dataset the dropdown shows: only a dataset whose source
// still has pages offers the button (`openCollections`); another one says there
// is nothing more once "Load more" has been used, and otherwise stays silent.
function LoadMore({ openId }: { openId: string | null }) {
  const canLoad = useAppStore((s) => {
    const ctx = s.searchContext;
    return ctx?.nextToken != null && (openId === null || (ctx.openCollections?.includes(openId) ?? true));
  });
  const used = useAppStore((s) => s.loadMoreUsed);
  const loading = useAppStore((s) => s.loadingMore);
  const failed = useAppStore((s) => s.loadMoreError);
  const loadMore = useAppStore((s) => s.loadMore);
  if (failed) return <p className="hint-text load-more">{failed}</p>;
  if (!canLoad) return used ? <p className="hint-text load-more">No more results available.</p> : null;
  return (
    <div className="load-more">
      <span className="hint-text">More scenes may be available.</span>
      <button type="button" className="ghost-btn" disabled={loading} onClick={() => void loadMore()}>
        {loading ? 'Loading…' : 'Load more'}
      </button>
    </div>
  );
}

// "Select all" (M4-29), on the line of the list's heading so
// the list loses no height. The box takes the scenes loaded so far and says so when
// the source reports more; it never loads pages.
function SelectionRow() {
  const loaded = useAppStore((s) => s.items.length);
  const selectedCount = useAppStore((s) => s.items.filter((it) => s.selectedIds.includes(it.id)).length);
  const matched = useAppStore((s) => s.searchContext?.numberMatched ?? null);
  const loadedAll = useAppStore((s) => totalItems(s.sections));
  const several = useAppStore((s) => s.sections.length > 1);
  const selectAllLoaded = useAppStore((s) => s.selectAllLoaded);
  const clearSelection = useAppStore((s) => s.clearSelection);
  const more = matched !== null && matched > loadedAll;
  const label = !more
    ? `Select all ${loaded}`
    : several
      ? `Select all ${loaded} loaded (more matched in total)`
      : `Select all ${loaded} loaded (of ${matched})`;
  const all = loaded > 0 && selectedCount === loaded;
  return (
    <div className="selection-row">
      <SelectBox
        checked={all}
        partial={selectedCount > 0 && !all}
        label={label}
        onChange={() => (all ? clearSelection() : selectAllLoaded())}
      />
    </div>
  );
}

export default function ResultsPanel() {
  const sections = useAppStore((s) => s.sections);
  const resultsOnMap = useAppStore((s) => s.resultsOnMap);
  // Of the scenes found, the ones ticked (a tick on a scene that is not in the results counts for nothing).
  const selected = useAppStore((s) => {
    const ids = new Set(s.selectedIds);
    return s.sections.reduce((n, section) => n + section.items.filter((it) => ids.has(it.id)).length, 0);
  });
  const toggleResultsOnMap = useAppStore((s) => s.toggleResultsOnMap);

  if (!hasResultsPanel(sections)) return null;

  return (
    <div className="panel dock-panel results-panel" role="region" aria-label="Results">
      <div className="results-head">
        <h2 title="Selected scenes / scenes found">Results ({selected}/{totalItems(sections)})</h2>
        <button
          type="button"
          className="results-map-toggle"
          title={
            resultsOnMap
              ? 'Take the search results off the map; the list stays, and ticked scenes still show'
              : 'Show the search results on the map again, over the layers'
          }
          onClick={() => toggleResultsOnMap()}
        >
          {resultsOnMap ? 'Hide results' : 'Show results'}
        </button>
      </div>
      <ResultsList sections={sections} />
    </div>
  );
}

// Under "Load more": takes the list of results away, and its pictures on the map. The area, dates, choice of
// datasets and filters stay, and so do the pinned layers and the jobs; the control menu opens (Otto, 26.10.2026).
function ClearResults() {
  const clearSearchResults = useAppStore((s) => s.clearSearchResults);
  return (
    <button
      type="button"
      className="clear-results"
      title="Remove the results from the list and the map. Area, dates, datasets and filters, layers and jobs stay."
      onClick={() => clearSearchResults()}
    >
      <span className="clear-results-x" aria-hidden="true">
        ✕
      </span>
      Clear search results
    </button>
  );
}

function ResultsList({ sections }: { sections: ResultSection[] }) {
  // The dataset shown is the one whose scenes `groups`/`items` hold
  // (`store.ts::setOpenSection`). Within it, the open time step stays separate
  // from `activeGroupIndex` (the one the map and time slider show), so the open
  // group can be collapsed without forcing a different one open, and collapsing
  // every group also hides its quicklooks on the map (V-6, V-11 —
  // `store.ts::toggleResultsGroup` has the full reasoning).
  const openSectionId = useAppStore((s) => s.openSectionId);
  const groups = useAppStore((s) => s.groups);
  const expandedGroupIndex = useAppStore((s) => s.expandedGroupIndex);
  const toggleGroup = useAppStore((s) => s.toggleResultsGroup);
  return (
    <>
      <DatasetDropdown sections={sections} openId={openSectionId} />
      <div className="results-list-head">
        <div className="eyebrow results-list-eyebrow">Scenes by time step</div>
        <SelectionRow />
      </div>
      <div className="results-list">
        {groups.map((g, i) => (
          <GroupBlock
            key={g.key.join('\u0000')}
            group={g}
            index={i}
            expanded={i === expandedGroupIndex}
            onToggle={toggleGroup}
          />
        ))}
      </div>
      <LoadMore openId={openSectionId} />
      <ClearResults />
    </>
  );
}
