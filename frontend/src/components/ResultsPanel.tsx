import { useState, type MouseEvent } from 'react';

import { quicklookAsset } from '../datasets';
import { useAppStore } from '../store';
import type { StacItem, TimeStepGroup } from '../types';

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
            {copied ? '✓' : '⧉'}
          </button>
        </span>
      </div>
    </li>
  );
}

function GroupBlock({ group, index }: { group: TimeStepGroup; index: number }) {
  const activeGroupIndex = useAppStore((s) => s.activeGroupIndex);
  const setActiveGroupIndex = useAppStore((s) => s.setActiveGroupIndex);
  const active = index === activeGroupIndex;

  return (
    <div className={`result-group${active ? ' active' : ''}`}>
      <button
        type="button"
        className="result-group-head"
        onClick={() => setActiveGroupIndex(index)}
      >
        <span className="rg-caret">{active ? '▾' : '▸'}</span>
        <span className="rg-label">{group.label}</span>
        <span className="rg-count">{group.items.length}</span>
      </button>
      {active && (
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
  const clearAll = useAppStore((s) => s.clearAll);
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
          <GroupBlock key={g.key.join('\u0000')} group={g} index={i} />
        ))}
      </div>
    </div>
  );
}
