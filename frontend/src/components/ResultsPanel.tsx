import { useEffect, useState, type MouseEvent } from 'react';

import { quicklookAsset } from '../datasets';
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

export default function ResultsPanel() {
  const groups = useAppStore((s) => s.groups);
  const activeGroupIndex = useAppStore((s) => s.activeGroupIndex);
  const setActiveGroupIndex = useAppStore((s) => s.setActiveGroupIndex);
  const clearAll = useAppStore((s) => s.clearAll);
  // Which section is open in the list — separate from `activeGroupIndex`
  // (the time step the map/time slider show), so the currently open one can
  // be collapsed without forcing a different one open (V-6). Stays in sync
  // whenever `activeGroupIndex` changes some other way (a new search, the
  // time slider, "play"); a manual collapse only changes this local state,
  // so it doesn't get overwritten by that sync — `activeGroupIndex` itself
  // hasn't changed.
  const [expandedIndex, setExpandedIndex] = useState<number | null>(activeGroupIndex);
  useEffect(() => {
    setExpandedIndex(activeGroupIndex);
  }, [activeGroupIndex]);

  const toggleGroup = (index: number) => {
    if (index === expandedIndex) {
      setExpandedIndex(null);
    } else {
      setExpandedIndex(index);
      setActiveGroupIndex(index);
    }
  };

  if (groups.length === 0) return null;

  return (
    <div className="panel results-panel">
      <div className="results-head">
        <h2>Time steps</h2>
        <div className="results-head-right">
          <span>{groups.length}</span>
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
      <div className="results-list">
        {groups.map((g, i) => (
          <GroupBlock
            key={g.key.join('\u0000')}
            group={g}
            index={i}
            expanded={i === expandedIndex}
            onToggle={toggleGroup}
          />
        ))}
      </div>
    </div>
  );
}
