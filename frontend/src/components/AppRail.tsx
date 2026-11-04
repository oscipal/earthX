// The narrow rail at the left edge (UI-01 §6.9, UI-01g): one symbol each for the control menu, the layer
// manager, the processing manager and the search results. A symbol opens its panel beside the rail; a second
// click closes it. The arrow keys move between the symbols (one tab stop), and a number says how many layers
// there are, how many jobs run and how many scenes the search found.

import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

import { dockPanelId, railButtonId } from '../dock';
import { useProcessingStore } from '../processingStore';
import { hasResultsPanel, totalItems } from '../sections';
import { useAppStore, type DockPanel } from '../store';
import { ICON_SIZES } from './iconSizes';
import { JobsIcon, LayersIcon, ResultsListIcon, SearchIcon } from './icons';

interface Item {
  panel: DockPanel;
  label: string;
  icon: ReactNode;
}

const ITEMS: Item[] = [
  { panel: 'controls', label: 'Search and area', icon: <SearchIcon size={ICON_SIZES.rail} /> },
  { panel: 'layers', label: 'Layers', icon: <LayersIcon size={ICON_SIZES.rail} /> },
  { panel: 'jobs', label: 'Jobs', icon: <JobsIcon size={ICON_SIZES.rail} /> },
  { panel: 'results', label: 'Search results', icon: <ResultsListIcon size={ICON_SIZES.rail} /> },
];

const NO_RESULTS = 'No results yet: run a search first';

export default function AppRail() {
  const dock = useAppStore((s) => s.dock);
  const toggleDock = useAppStore((s) => s.toggleDock);
  const flipping = useAppStore((s) => s.flipThrough);
  const setFlipThrough = useAppStore((s) => s.setFlipThrough);
  const layerCount = useAppStore((s) => s.layers.length);
  // A job whose state is not known yet (an archived one, one of another tab) is not counted as running.
  const running = useProcessingStore((s) => s.jobs.filter((j) => j.phase === 'active' && j.status !== null).length);
  const found = useAppStore((s) => totalItems(s.sections));
  const hasResults = useAppStore((s) => hasResultsPanel(s.sections));
  const counts: Record<DockPanel, number> = { controls: 0, layers: layerCount, jobs: running, results: found };
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  // The symbol that takes the Tab key: the open panel's, else the one last used.
  const [stop, setStop] = useState(0);
  const current = dock ? ITEMS.findIndex((item) => item.panel === dock) : stop;

  const go = (index: number) => {
    const next = (index + ITEMS.length) % ITEMS.length;
    setStop(next);
    buttons.current[next]?.focus();
  };

  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    const at = buttons.current.findIndex((b) => b === document.activeElement);
    if (event.key === 'ArrowDown' || event.key === 'ArrowRight') go(at + 1);
    else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') go(at - 1);
    else if (event.key === 'Home') go(0);
    else if (event.key === 'End') go(ITEMS.length - 1);
    // Esc ends "Flip through layers" (NM4-65 part 9) and closes nothing: the panel closes with its symbol (Otto, 2.11.2026).
    else if (event.key === 'Escape' && dock && flipping) setFlipThrough(false);
    else return;
    event.preventDefault();
  };

  return (
    <nav className="app-rail" aria-label="Main" onKeyDown={onKeyDown}>
      {ITEMS.map((item, index) => {
        const count = counts[item.panel];
        const open = dock === item.panel;
        // Without results the symbol stays in its place, for the roving focus, and says why it does nothing.
        const locked = item.panel === 'results' && !hasResults;
        return (
          <button
            key={item.panel}
            type="button"
            id={railButtonId(item.panel)}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            className={`rail-btn has-tip${open ? ' on' : ''}`}
            data-tip={locked ? NO_RESULTS : item.label}
            data-tip-side="right"
            aria-label={locked ? `${item.label}, ${NO_RESULTS}` : count > 0 ? `${item.label}, ${count}` : item.label}
            aria-disabled={locked || undefined}
            aria-expanded={open}
            aria-controls={open ? dockPanelId(item.panel) : undefined}
            tabIndex={index === current ? 0 : -1}
            onFocus={() => setStop(index)}
            onClick={() => (locked ? undefined : toggleDock(item.panel))}
          >
            {item.icon}
            {count > 0 && <span className="rail-badge" aria-hidden="true">{count > 99 ? '99+' : count}</span>}
          </button>
        );
      })}
    </nav>
  );
}
