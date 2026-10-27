// The "Basemap" button at the top right and its menu (UI-02a, Otto 27.10.2026): which map lies under the app's own
// layers, and how the earth is shown (flat or globe). It replaces the "Mercator/Globe" button; "Light/Dark" stays a
// button of its own. The tooltip of each basemap says where its tiles come from (UI-02 §6.7).

import { useRef, useState } from 'react';

import { BASEMAP_IDS, BASEMAPS } from '../basemaps';
import type { Projection } from '../preferences';
import { useAppStore } from '../store';
import Popover from './Popover';

const PROJECTIONS: { id: Projection; name: string; tip: string }[] = [
  { id: 'mercator', name: 'Mercator', tip: 'The flat map' },
  { id: 'globe', name: 'Globe', tip: 'The earth as a globe; it turns flat from zoom 12' },
];

function Choice({ name, tip, checked, onChoose }: { name: string; tip: string; checked: boolean; onChoose: () => void }) {
  return (
    <button type="button" role="menuitemradio" aria-checked={checked} title={tip} onClick={onChoose}>
      <span className="pm-menu-label">{name}</span>
    </button>
  );
}

export default function BasemapMenu() {
  const basemap = useAppStore((s) => s.basemap);
  const projection = useAppStore((s) => s.projection);
  const setBasemap = useAppStore((s) => s.setBasemap);
  const setProjection = useAppStore((s) => s.setProjection);
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);

  return (
    <>
      <button
        ref={button}
        type="button"
        className="panel zoom-btn basemap-btn"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Basemap and projection"
        onClick={() => setOpen((was) => !was)}
      >
        Basemap
      </button>
      <Popover
        anchorRef={button}
        open={open}
        onClose={() => setOpen(false)}
        className="pm-menu-list basemap-menu"
        role="menu"
        ariaLabel="Basemap and projection"
        focusOnOpen
      >
        <div role="group" aria-label="Basemap" className="menu-group">
          <span className="menu-group-label" aria-hidden="true">Basemap</span>
          {BASEMAP_IDS.map((id) => (
            <Choice key={id} name={BASEMAPS[id].name} tip={BASEMAPS[id].tip} checked={basemap === id} onChoose={() => setBasemap(id)} />
          ))}
        </div>
        <div role="group" aria-label="Projection" className="menu-group">
          <span className="menu-group-label" aria-hidden="true">Projection</span>
          {PROJECTIONS.map((p) => (
            <Choice key={p.id} name={p.name} tip={p.tip} checked={projection === p.id} onChoose={() => setProjection(p.id)} />
          ))}
        </div>
      </Popover>
    </>
  );
}
