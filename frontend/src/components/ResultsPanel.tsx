import { useEffect, useRef, useState, type MouseEvent } from 'react';

import { maturityLabel, quicklookAsset } from '../datasets';
import type { ResultSection } from '../sections';
import { hasResultsPanel, totalItems } from '../sections';
import { useAppStore } from '../store';
import type { StacItem, TimeStepGroup } from '../types';

// Two overlapping rounded rectangles — the same copy glyph Claude's own
// interface uses, in place of the earlier "⧉" character glyph, which
// rendered inconsistently and didn't read as "copy" at a glance (V-6).
// `currentColor` so `.copy-btn`'s own color (and its `:hover` accent) still
// drive it.
function CopyIcon({ copied }: { copied: boolean }) {
  if (copied) {
    return (
      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M20 6 9 17l-5-5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

function timeOf(properties: Record<string, unknown>): string {
  const dt = properties['datetime'];
  if (typeof dt !== 'string') return '';
  const d = new Date(dt);
  return Number.isNaN(d.getTime()) ? '' : d.toISOString().slice(11, 19) + 'Z';
}

function Row({ item }: { item: StacItem }) {
  const selectedIds = useAppStore((s) => s.selectedIds);
  const toggleSelected = useAppStore((s) => s.toggleSelected);
  const [copied, setCopied] = useState(false);

  const selected = selectedIds.includes(item.id);
  const asset = quicklookAsset(item);

  const copyName = (e: MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard
      .writeText(item.id)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => {
        // Clipboard unavailable (no permission, insecure context) — the name
        // stays visible in the row to select and copy by hand.
      });
  };

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
        // No preview image on this item (for sentinel-2-l2a-zarr3 that is every
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
          <button
            type="button"
            className="copy-btn"
            title="Copy scene name"
            aria-label={`Copy scene name ${item.id}`}
            onClick={copyName}
          >
            <CopyIcon copied={copied} />
          </button>
        </span>
      </div>
    </li>
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
      <button type="button" className="result-group-head" onClick={() => onToggle(index)}>
        <span className="rg-caret">{expanded ? '▾' : '▸'}</span>
        <span className="rg-label" title={group.label}>
          {group.label}
        </span>
        <span className="rg-count">{group.items.length}</span>
      </button>
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
// dataset to switch. The list is part of the panel's own flow, not a popup, so
// the panel's edge does not clip it. Choosing never closes the panel.
function DatasetDropdown({ sections, openId }: { sections: ResultSection[]; openId: string | null }) {
  const setOpenSection = useAppStore((s) => s.setOpenSection);
  const [listOpen, setListOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const shown = sections.find((section) => section.datasetId === openId) ?? sections[0];

  useEffect(() => {
    if (!listOpen) return;
    const away = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setListOpen(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setListOpen(false);
    };
    document.addEventListener('pointerdown', away);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', away);
      document.removeEventListener('keydown', escape);
    };
  }, [listOpen]);

  if (!shown) return null;
  const several = sections.length > 1;
  return (
    <div className="dataset-select" ref={rootRef}>
      <span className="eyebrow" id="dataset-select-label">
        Showing dataset
      </span>
      <button
        type="button"
        className="dataset-select-box"
        aria-haspopup={several ? 'listbox' : undefined}
        aria-expanded={several ? listOpen : undefined}
        aria-labelledby="dataset-select-label"
        disabled={!several}
        onClick={() => setListOpen((v) => !v)}
      >
        <SectionSummary section={shown} />
        {several && <span className="rg-caret">{listOpen ? '▴' : '▾'}</span>}
      </button>
      {several && listOpen && (
        <div className="dataset-select-list" role="listbox" aria-label="Searched datasets">
          {sections.map((section) => (
            <button
              key={section.datasetId}
              type="button"
              role="option"
              aria-selected={section.datasetId === shown.datasetId}
              className={`dataset-select-option${section.datasetId === shown.datasetId ? ' selected' : ''}`}
              onClick={() => {
                setOpenSection(section.datasetId);
                setListOpen(false);
              }}
            >
              <SectionSummary section={section} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// A dataset with no browsable preview (the DEM) is drawn on the map as its AOI crop
// as soon as it is the chosen dataset (`store.ts::searchCrops`). It is part of the
// results, so it leaves the map with them; pinning is the user's own step.
function CropRow({ openId }: { openId: string | null }) {
  const hasCrop = useAppStore((s) => s.searchCrops.some((c) => c.restore.datasetId === openId));
  const pin = useAppStore((s) => s.pinSearchCrops);
  if (!hasCrop) return null;
  return (
    <div className="crop-row">
      <span className="hint-text">Full-resolution crop is on the map.</span>
      <button type="button" className="link-btn" title="Keep it on the map when another dataset is chosen" onClick={() => pin()}>
        ＋ Pin to layers
      </button>
    </div>
  );
}

// "Load more" (M3-10 F1) continues the whole search, whichever dataset the
// dropdown shows: the page token spans every dataset asked and cannot be split
// per dataset, so the sentence names none of them as the one with more.
function LoadMore() {
  const canLoad = useAppStore((s) => s.searchContext?.nextToken != null);
  const loading = useAppStore((s) => s.loadingMore);
  const failed = useAppStore((s) => s.loadMoreError);
  const loadMore = useAppStore((s) => s.loadMore);
  if (failed) return <p className="hint-text load-more">{failed}</p>;
  if (!canLoad) return null;
  return (
    <div className="load-more">
      <span className="hint-text">More scenes may be available.</span>
      <button type="button" className="ghost-btn" disabled={loading} onClick={() => void loadMore()}>
        {loading ? 'Loading…' : 'Load more'}
      </button>
    </div>
  );
}

export default function ResultsPanel() {
  const sections = useAppStore((s) => s.sections);
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
  const clearAll = useAppStore((s) => s.clearAll);

  if (!hasResultsPanel(sections)) return null;

  return (
    <div className="panel results-panel">
      <div className="results-head">
        <h2>Results</h2>
        <div className="results-head-right">
          <span>{totalItems(sections)}</span>
          <button
            type="button"
            className="link-btn"
            title="Clear the search and selection"
            onClick={() => clearAll()}
          >
            Clear all
          </button>
        </div>
      </div>
      <DatasetDropdown sections={sections} openId={openSectionId} />
      <CropRow openId={openSectionId} />
      <div className="eyebrow results-list-eyebrow">Scenes by time step</div>
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
      <LoadMore />
    </div>
  );
}
