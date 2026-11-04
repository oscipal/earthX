// The "Settings" symbol at the bottom of the rail and its menu (UI-04 part 4, Otto, 4.11.2026): which map lies under the app's own layers
// (Basemap), the overlays over it (names, graticule, relief), how the earth is shown (Projection), how the page looks (Appearance: Light,
// Dark, System) and how many tooltips there are (Tooltips: Simple, Advanced). It takes the place of the buttons "Basemap" and "Light/Dark"
// at the top right. Every choice is kept per browser (`preferences.ts`) and works with a storage that is locked. The tooltip of each
// basemap says where its tiles come from (UI-02 §6.7).

import { useRef, useState, type ReactNode, type Ref } from 'react';

import { BASEMAP_IDS, BASEMAPS } from '../basemaps';
import { OVERLAY_IDS, OVERLAYS } from '../overlays';
import { APPEARANCES, type Appearance, type Projection } from '../preferences';
import { useAppStore } from '../store';
import { TIP_LEVELS, type TipLevel } from '../tipLevel';
import { MonitorIcon, MoonIcon, SettingsIcon, SunIcon } from './icons';
import { ICON_SIZES } from './iconSizes';
import MenuTick from './MenuTick';
import Popover from './Popover';

export const SETTINGS_LABEL = 'Settings';
// As wide as the longest entry needs; the popover is cut to the window on a phone.
const SETTINGS_MENU_WIDTH = 188;

const PROJECTIONS: { id: Projection; name: string; tip: string }[] = [
  { id: 'mercator', name: 'Mercator', tip: 'The flat map' },
  { id: 'globe', name: 'Globe', tip: 'The earth as a globe; it turns flat from zoom 12' },
];

const APPEARANCE_ENTRIES: Record<Appearance, { name: string; icon: ReactNode; tip: string }> = {
  light: { name: 'Light', icon: <SunIcon lead />, tip: 'The light theme' },
  dark: { name: 'Dark', icon: <MoonIcon lead />, tip: 'The dark theme' },
  system: { name: 'System', icon: <MonitorIcon lead />, tip: 'Light or dark as the system asks for' },
};

const TIP_LEVEL_ENTRIES: Record<TipLevel, { name: string; tip: string }> = {
  simple: { name: 'Simple', tip: 'Tooltips only where they are needed: the reason a control is locked, the name of an unclear icon, a cut-off text' },
  advanced: { name: 'Advanced', tip: 'A tooltip on every control' },
};

function Choice({
  name,
  tip,
  checked,
  onChoose,
  role = 'menuitemradio',
  icon,
}: {
  name: string;
  tip: string;
  checked: boolean;
  onChoose: () => void;
  role?: string;
  icon?: ReactNode;
}) {
  return (
    <button type="button" role={role} aria-checked={checked} data-tip-level="advanced" data-tip={tip} onClick={onChoose}>
      <MenuTick checked={checked} />
      {icon}
      <span className="pm-menu-label">{name}</span>
    </button>
  );
}

function Group({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div role="group" aria-label={label} className="menu-group">
      <span className="menu-group-label" aria-hidden="true">
        {label}
      </span>
      {children}
    </div>
  );
}

// `buttonRef`, `tabIndex` and `onFocus` are the rail's: the symbol is one of its stops (`AppRail.tsx`).
export default function SettingsMenu({
  buttonRef,
  tabIndex,
  onFocus,
}: {
  buttonRef: Ref<HTMLButtonElement>;
  tabIndex: number;
  onFocus: () => void;
}) {
  const basemap = useAppStore((s) => s.basemap);
  const overlays = useAppStore((s) => s.overlays);
  const projection = useAppStore((s) => s.projection);
  const appearance = useAppStore((s) => s.appearance);
  const tipLevel = useAppStore((s) => s.tipLevel);
  const setBasemap = useAppStore((s) => s.setBasemap);
  const setOverlay = useAppStore((s) => s.setOverlay);
  const setProjection = useAppStore((s) => s.setProjection);
  const setAppearance = useAppStore((s) => s.setAppearance);
  const setTipLevel = useAppStore((s) => s.setTipLevel);
  const [open, setOpen] = useState(false);
  // The popover needs the element; the rail needs it too (arrow keys): one callback ref feeds both.
  const anchorRef = useRef<HTMLButtonElement | null>(null);

  return (
    <>
      <button
        ref={(element) => {
          anchorRef.current = element;
          if (typeof buttonRef === 'function') buttonRef(element);
          else if (buttonRef) buttonRef.current = element;
        }}
        type="button"
        className={`icon-btn rail-btn rail-settings has-tip${open ? ' on' : ''}`}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={SETTINGS_LABEL}
        data-tip={SETTINGS_LABEL}
        data-tip-side="right"
        tabIndex={tabIndex}
        onFocus={onFocus}
        onClick={() => setOpen((was) => !was)}
      >
        <SettingsIcon size={ICON_SIZES.rail} />
      </button>
      <Popover
        anchorRef={anchorRef}
        open={open}
        onClose={() => setOpen(false)}
        className="pm-menu-list settings-menu"
        role="menu"
        ariaLabel={SETTINGS_LABEL}
        focusOnOpen
        beside={SETTINGS_MENU_WIDTH}
      >
        <Group label="Basemap">
          {BASEMAP_IDS.map((id) => (
            <Choice key={id} name={BASEMAPS[id].name} tip={BASEMAPS[id].tip} checked={basemap === id} onChoose={() => setBasemap(id)} />
          ))}
        </Group>
        <Group label="Overlays">
          {OVERLAY_IDS.map((id) => (
            <Choice
              key={id}
              role="menuitemcheckbox"
              name={OVERLAYS[id].name}
              tip={OVERLAYS[id].tip}
              checked={overlays[id]}
              onChoose={() => setOverlay(id, !overlays[id])}
            />
          ))}
        </Group>
        <Group label="Projection">
          {PROJECTIONS.map((p) => (
            <Choice key={p.id} name={p.name} tip={p.tip} checked={projection === p.id} onChoose={() => setProjection(p.id)} />
          ))}
        </Group>
        <Group label="Appearance">
          {APPEARANCES.map((id) => (
            <Choice
              key={id}
              name={APPEARANCE_ENTRIES[id].name}
              tip={APPEARANCE_ENTRIES[id].tip}
              icon={APPEARANCE_ENTRIES[id].icon}
              checked={appearance === id}
              onChoose={() => setAppearance(id)}
            />
          ))}
        </Group>
        <Group label="Tooltips">
          {TIP_LEVELS.map((id) => (
            <Choice key={id} name={TIP_LEVEL_ENTRIES[id].name} tip={TIP_LEVEL_ENTRIES[id].tip} checked={tipLevel === id} onChoose={() => setTipLevel(id)} />
          ))}
        </Group>
      </Popover>
    </>
  );
}
