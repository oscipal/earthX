// All colormaps (UI-03d, Otto, 2.11.2026): a bar of its own at the right edge, in the place of the settings, over them or the
// processing panel, which stay as they were. Each colormap with its preview and its name, by group; a search and "Reverse". A click
// chooses and goes back; the arrow goes back without a choice. Esc closes nothing. Under 900 px a sheet from the bottom, as the settings are.

import { useMemo, useState } from 'react';

import { baseOf, gradientOf, isReversed, withReverse } from '../colormaps';
import { useColormapPicker } from '../colormapPicker';
import { REVERSE_TIP } from './ColormapField';
import { ArrowLeftIcon, ArrowLeftRightIcon, ChevronDownIcon, ChevronUpIcon } from './icons';
import { useColormapGroups } from './useColormapGroups';

export const BACK_TIP = 'Back';
const GROUP_TITLES: Record<string, string> = {
  sequential: 'Sequential',
  diverging: 'Diverging',
  cyclic: 'Cyclic',
  qualitative: 'Qualitative',
  other: 'Other',
};

function Picker({ value, onPick }: { value: string; onPick: (name: string) => void }) {
  const close = useColormapPicker((s) => s.close);
  const groups = useColormapGroups();
  const [query, setQuery] = useState('');
  const [reversed, setReversed] = useState(isReversed(value));
  // Under 900 px a sheet with the grip of the settings, which folds it to its head.
  const [folded, setFolded] = useState(false);
  const chosen = baseOf(value);
  const shown = useMemo(() => {
    const text = query.trim().toLowerCase();
    return (groups === null || groups === 'failed' ? [] : groups).map((group) => ({ ...group, colormaps: group.colormaps.filter((c) => c.name.includes(text)) })).filter((group) => group.colormaps.length > 0);
  }, [groups, query]);
  return (
    <aside className={`inspector panel colormap-picker${folded ? ' folded' : ''}`} aria-label="Colormaps">
      <button
        type="button"
        className="pp-grip"
        aria-expanded={!folded}
        aria-label={folded ? 'Show the colormaps' : 'Fold the colormaps down'}
        data-tip-level="advanced" data-tip={folded ? 'Show the colormaps' : 'Fold the colormaps down'}
        onClick={() => setFolded(!folded)}
      >
        {folded ? <ChevronUpIcon /> : <ChevronDownIcon />}
      </button>
      <div className="vc-head">
        <div className="insp-row">
          <button type="button" className="icon-btn" data-tip-level="advanced" data-tip={BACK_TIP} aria-label={BACK_TIP} onClick={close}>
            <ArrowLeftIcon />
          </button>
          <span className="vc-title">Colormap</span>
        </div>
        <div className="insp-row insp-row2">
          <input autoComplete="off" className="cm-search" type="search" placeholder="Search" aria-label="Search colormaps" value={query} onChange={(e) => setQuery(e.target.value)} />
          <button type="button" className={`btn vc-reverse${reversed ? ' on' : ''}`} aria-pressed={reversed} data-tip={REVERSE_TIP} onClick={() => setReversed(!reversed)}>
            <ArrowLeftRightIcon />
            Reverse
          </button>
        </div>
      </div>
      <div className="insp-body">
        {groups === null ? (
          <p className="hint">Loading the colormaps…</p>
        ) : groups === 'failed' ? (
          <p className="hint warn" role="alert">
            The colormaps could not be loaded. Choose from the few of the field, or try again later.
          </p>
        ) : shown.length === 0 ? (
          <p className="hint">No colormap of this name</p>
        ) : (
          shown.map((group) => (
            <section key={group.name} className="insp-section">
              <h3 className="insp-heading">{GROUP_TITLES[group.name] ?? group.name}</h3>
              <ul className="cm-list">
                {group.colormaps.map((entry) => (
                  <li key={entry.name}>
                    <button
                      type="button"
                      className={`cm-item${entry.name === chosen ? ' on' : ''}`}
                      aria-pressed={entry.name === chosen}
                      onClick={() => {
                        onPick(withReverse(entry.name, reversed && entry.reversed !== null));
                        close();
                      }}
                    >
                      <span className="cm-strip" style={{ background: gradientOf(entry.colors, reversed) }} aria-hidden="true" />
                      <span className="cm-name">{entry.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </div>
    </aside>
  );
}

export default function ColormapPicker() {
  const request = useColormapPicker((s) => s.request);
  // A new opening starts over: the search empty, "Reverse" as the colormap of the field is.
  return request ? <Picker key={request.opening} value={request.value} onPick={request.onPick} /> : null;
}
