// The narrow rail at the left edge (UI-01 §6.9): one symbol each for the control menu, the layer manager
// and the processing manager. A symbol opens its panel beside the rail; a second click closes it. The
// arrow keys move between the symbols (one tab stop), and a number says how many layers there are and how
// many jobs run.

import { useRef, useState, type KeyboardEvent, type ReactNode } from 'react';

import { dockPanelId, railButtonId } from '../dock';
import { useProcessingStore } from '../processingStore';
import { useAppStore, type DockPanel } from '../store';

interface Item {
  panel: DockPanel;
  label: string;
  icon: ReactNode;
}

const svg = (children: ReactNode) => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
    {children}
  </svg>
);

const ITEMS: Item[] = [
  {
    panel: 'controls',
    label: 'Search and area',
    icon: svg(
      <>
        <circle cx="10.5" cy="10.5" r="6" />
        <path d="m15 15 6 6" />
      </>,
    ),
  },
  {
    panel: 'layers',
    label: 'Layers',
    icon: svg(
      <>
        <path d="m12 3 9 5-9 5-9-5z" />
        <path d="m3 12 9 5 9-5" />
        <path d="m3 16 9 5 9-5" />
      </>,
    ),
  },
  {
    panel: 'jobs',
    label: 'Processing jobs',
    icon: svg(
      <>
        <rect x="4" y="3" width="16" height="18" rx="2" />
        <path d="M8 8h8M8 12h8M8 16h5" />
      </>,
    ),
  },
];

export default function AppRail() {
  const dock = useAppStore((s) => s.dock);
  const toggleDock = useAppStore((s) => s.toggleDock);
  const closeDock = useAppStore((s) => s.closeDock);
  const layerCount = useAppStore((s) => s.layers.length);
  const running = useProcessingStore((s) => s.jobs.filter((j) => j.phase === 'active').length);
  const counts: Record<DockPanel, number> = { controls: 0, layers: layerCount, jobs: running };
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
    else if (event.key === 'Escape' && dock) closeDock();
    else return;
    event.preventDefault();
  };

  return (
    <nav className="app-rail" aria-label="Main" onKeyDown={onKeyDown}>
      {ITEMS.map((item, index) => {
        const count = counts[item.panel];
        const open = dock === item.panel;
        return (
          <button
            key={item.panel}
            type="button"
            id={railButtonId(item.panel)}
            ref={(element) => {
              buttons.current[index] = element;
            }}
            className={`rail-btn has-tip${open ? ' on' : ''}`}
            data-tip={item.label}
            aria-label={count > 0 ? `${item.label}, ${count}` : item.label}
            aria-expanded={open}
            aria-controls={open ? dockPanelId(item.panel) : undefined}
            tabIndex={index === current ? 0 : -1}
            onFocus={() => setStop(index)}
            onClick={() => toggleDock(item.panel)}
          >
            {item.icon}
            {count > 0 && <span className="rail-badge" aria-hidden="true">{count > 99 ? '99+' : count}</span>}
          </button>
        );
      })}
    </nav>
  );
}
