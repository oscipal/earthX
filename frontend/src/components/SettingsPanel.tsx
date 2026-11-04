// The panel "Settings" of the rail (UI-04 part 4, Otto, 4.11.2026): which map lies under the app's own layers (Basemap), the overlays over it
// (Labels, Graticule, Relief), how the earth is shown (Projection), how the page looks (Appearance) and how many tooltips there are (Tooltips).
// It opens beside the rail like the other panels — the same width, a head with the title and the red x, a sheet over the map under 900 px —
// and takes the place of the buttons "Basemap" and Light/Dark at the top right. A choice of one is a row of segment buttons, an overlay is a
// button that is pressed while it is on, the tooltips are a switch. Every choice is kept per browser (`preferences.ts`) and works with a
// storage that is locked. The tooltip of each basemap says where its tiles come from (UI-02 §6.7).

import type { ReactNode } from 'react';

import { BASEMAP_IDS, BASEMAPS } from '../basemaps';
import { OVERLAY_IDS, OVERLAYS } from '../overlays';
import { APPEARANCES, type Appearance, type Projection } from '../preferences';
import { useAppStore } from '../store';
import CloseButton from './CloseButton';
import { MonitorIcon, MoonIcon, SunIcon } from './icons';
import Switch from './Switch';

export const SETTINGS_LABEL = 'Settings';

const PROJECTIONS: { id: Projection; name: string; tip: string }[] = [
  { id: 'mercator', name: 'Mercator', tip: 'The flat map' },
  { id: 'globe', name: 'Globe', tip: 'The earth as a globe; it turns flat from zoom 12' },
];

const APPEARANCE_ENTRIES: Record<Appearance, { name: string; icon: ReactNode; tip: string }> = {
  light: { name: 'Light', icon: <SunIcon lead />, tip: 'The light theme' },
  dark: { name: 'Dark', icon: <MoonIcon lead />, tip: 'The dark theme' },
  system: { name: 'System', icon: <MonitorIcon lead />, tip: 'Light or dark as the system asks for' },
};

const TIPS_TIP = 'Simple: tooltips only where they are needed (the reason a control is locked, the name of an unclear icon, a cut-off text). Advanced: a tooltip on every control.';

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <section className="settings-section" aria-label={label}>
      <h3 className="settings-heading">{label}</h3>
      {children}
    </section>
  );
}

// One choice of a row: the chosen one is pressed.
function Choice({ name, tip, pressed, onChoose, icon }: { name: string; tip: string; pressed: boolean; onChoose: () => void; icon?: ReactNode }) {
  return (
    <button type="button" className="btn seg" aria-pressed={pressed} data-tip-level="advanced" data-tip={tip} onClick={onChoose}>
      {icon}
      {name}
    </button>
  );
}

export default function SettingsPanel() {
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
  const closeDock = useAppStore((s) => s.closeDock);
  const advanced = tipLevel === 'advanced';

  return (
    <div className="panel dock-panel settings-panel" role="region" aria-label={SETTINGS_LABEL}>
      <div className="results-head">
        <h2>{SETTINGS_LABEL}</h2>
        <CloseButton onClick={closeDock} />
      </div>
      <div className="settings-body">
        <Section label="Basemap">
          <div className="settings-row" role="group" aria-label="Basemap">
            {BASEMAP_IDS.map((id) => (
              <Choice key={id} name={BASEMAPS[id].name} tip={BASEMAPS[id].tip} pressed={basemap === id} onChoose={() => setBasemap(id)} />
            ))}
          </div>
        </Section>
        <Section label="Overlays">
          <div className="settings-row" role="group" aria-label="Overlays">
            {OVERLAY_IDS.map((id) => (
              <Choice key={id} name={OVERLAYS[id].name} tip={OVERLAYS[id].tip} pressed={overlays[id]} onChoose={() => setOverlay(id, !overlays[id])} />
            ))}
          </div>
        </Section>
        <Section label="Projection">
          <div className="settings-row" role="group" aria-label="Projection">
            {PROJECTIONS.map((p) => (
              <Choice key={p.id} name={p.name} tip={p.tip} pressed={projection === p.id} onChoose={() => setProjection(p.id)} />
            ))}
          </div>
        </Section>
        <Section label="Appearance">
          <div className="settings-row" role="group" aria-label="Appearance">
            {APPEARANCES.map((id) => (
              <Choice
                key={id}
                name={APPEARANCE_ENTRIES[id].name}
                tip={APPEARANCE_ENTRIES[id].tip}
                icon={APPEARANCE_ENTRIES[id].icon}
                pressed={appearance === id}
                onChoose={() => setAppearance(id)}
              />
            ))}
          </div>
        </Section>
        <Section label="Tooltips">
          <div className="settings-switch-row">
            <span className={`settings-switch-side${advanced ? '' : ' on'}`}>
              Simple
            </span>
            <Switch on={advanced} onChange={(on) => setTipLevel(on ? 'advanced' : 'simple')} label="Advanced tooltips" tip={TIPS_TIP} />
            <span className={`settings-switch-side${advanced ? ' on' : ''}`}>
              Advanced
            </span>
          </div>
        </Section>
      </div>
    </div>
  );
}
