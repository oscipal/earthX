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
        <span className="result-thumb placeholder" />
      )}
      <div className="result-meta">
        <span className="result-date">{timeOf(item.properties)}</span>
        <span className="result-id" title={item.id}>
          {item.id}
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
