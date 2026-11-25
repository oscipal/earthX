// The legend over the map (M5-62, Otto 24.11.2026): one box at the bottom left, beside the panel of the rail, always there, titled
// "Legend". It shows the topmost visible layer with a legend (`mapLegend.ts`), in the order of the layer manager; the dropdown in its
// head chooses another until the layers change, and then it is the topmost again (`chooseLegend`). Without one the box keeps its title
// and says nothing else. It never scrolls: a long list of classes takes two
// columns, and the title folds it. It stands above what lies at the bottom of the map (the marks of `PreviewBadge`, the bar of the time
// steps), never over it.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { useLegendStore } from '../legendStore';
import { useProcessingStore } from '../processingStore';
import { chooseLegend, layersSignature, legendEntries, legendPlace, type LegendPlace } from '../mapLegend';
import { useAppStore } from '../store';
import { viewLayerOf, viewShown, layersForMap } from '../viewLayer';
import { ChevronDownIcon, ChevronRightIcon } from './icons';
import LegendBody from './LegendBody';

export const LEGEND = 'Legend';
export const ONE_LEGEND_TIP = 'Only one visible layer has a legend';

// What lies at the bottom of the map that a legend must not cover.
const BELOW = ['.preview-badge-dock', '.overlay.bottom > *'];
const GAP = 8;

// How far the legends rise above their place at the bottom (`lifted` is how far they stand now): over every mark or bar at the bottom
// that they would overlap.
function liftOver(legends: HTMLElement, lifted: number): number {
  const own = legends.getBoundingClientRect();
  const foot = own.bottom + lifted;
  let lift = 0;
  for (const selector of BELOW) {
    for (const element of document.querySelectorAll<HTMLElement>(selector)) {
      const box = element.getBoundingClientRect();
      if (box.width === 0 || box.height === 0 || box.right <= own.left || box.left >= own.right) continue;
      lift = Math.max(lift, foot - box.top + GAP);
    }
  }
  return Math.max(0, lift);
}

const px = (style: CSSStyleDeclaration, name: string): number => Number.parseFloat(style.getPropertyValue(name)) || 0;

// The room the legend has at its place: from above what stands at the foot of the map (`lift` over the attribution, and the sheet of the
// settings in a narrow window) up to the buttons at the top, where they stand above it, else to the top of the map.
function roomAt(app: HTMLElement, lift: number, width: number, narrow: boolean): number {
  const style = getComputedStyle(app);
  const box = app.getBoundingClientRect();
  // No layout to measure (jsdom): all the room there is.
  if (box.height === 0) return Number.POSITIVE_INFINITY;
  const sheet = narrow && app.classList.contains('has-inspector') ? px(style, '--inspector-sheet-height') : 0;
  const foot = box.bottom - (px(style, '--attribution-height') || 20) - 4 - sheet - lift;
  const left = box.left + px(style, '--map-left') + 16;
  const row = app.querySelector('.overlay.top-right')?.getBoundingClientRect();
  const top = row && row.left < left + width && row.right > left ? row.bottom : box.top;
  return foot - top - GAP;
}

export default function MapLegend() {
  const layers = useAppStore((s) => s.layers);
  const resultsAt = useAppStore((s) => s.resultsAt);
  const datasets = useAppStore((s) => s.datasets);
  const focusMode = useAppStore((s) => s.focusMode);
  const downloaded = useAppStore((s) => s.downloaded);
  const appliedRender = useAppStore((s) => s.appliedRender);
  const showDownloaded = useAppStore((s) => s.showDownloaded);
  const viewLayerId = useAppStore((s) => s.viewLayerId);
  const cropToAoi = useAppStore((s) => s.cropToAoi);
  const viewAoi = useAppStore((s) => s.viewAoi);
  const entries = useMemo(() => {
    const viewLayer = viewLayerOf(layers, { viewLayerId, focusMode, downloaded, appliedRender, cropToAoi, aoi: viewAoi, showDownloaded });
    const view = focusMode && viewLayer === null && viewShown(viewLayer, showDownloaded) ? { downloaded, render: appliedRender } : null;
    return legendEntries({ layers: layersForMap(layers, viewLayer, showDownloaded), resultsAt, datasets, view });
  }, [layers, resultsAt, datasets, focusMode, downloaded, appliedRender, showDownloaded, viewLayerId, cropToAoi, viewAoi]);
  const signature = useMemo(() => layersSignature(layers, resultsAt, entries), [layers, resultsAt, entries]);
  const choice = useLegendStore((s) => s.choice);
  const setChoice = useLegendStore((s) => s.setChoice);
  const choose = useLegendStore((s) => s.choose);
  const folded = useLegendStore((s) => s.folded);
  const toggleFolded = useLegendStore((s) => s.toggleFolded);
  const next = useMemo(() => chooseLegend(choice, entries, signature), [choice, entries, signature]);
  useEffect(() => {
    if (next.chosen !== choice.chosen || next.signature !== choice.signature) setChoice(next);
  }, [next, choice, setChoice]);
  const shown = entries.find((entry) => entry.id === next.chosen) ?? null;
  const ref = useRef<HTMLDivElement>(null);
  const [lift, setLift] = useState(0);
  const dockOpen = useAppStore((s) => s.dock !== null);
  const processingOpen = useProcessingStore((s) => s.open);
  const [narrow, setNarrow] = useState(() => window.innerWidth < 900);
  const [place, setPlace] = useState<LegendPlace>('open');
  // Opened by its title where it stands folded or docked; it folds again when its place changes.
  const [openHere, setOpenHere] = useState<{ place: LegendPlace; open: boolean }>({ place: 'open', open: false });
  // The heights of its head and of the whole box when open, measured where it stood open (a folded box has no body to measure).
  const sizes = useRef({ head: 30, full: 30, width: 240 });
  // A measurement of the lift asks for a new place.
  const [tick, setTick] = useState(0);
  const lifted = useRef(0);
  lifted.current = lift;

  // Measured again whenever the legend or the bar at the bottom change size, a mark comes or goes, and with the window.
  useLayoutEffect(() => {
    const legends = ref.current;
    if (!legends) return;
    const measure = () => {
      setNarrow(window.innerWidth < 900);
      if (legends.classList.contains('docked')) return;
      const lifting = liftOver(legends, lifted.current);
      if (Math.abs(lifting - lifted.current) >= 1) setLift(lifting);
      setTick((t) => t + 1);
    };
    measure();
    const app = legends.closest('.app');
    const marks = app && typeof MutationObserver !== 'undefined' ? new MutationObserver(measure) : null;
    // A panel that opens or closes moves the legend and the buttons at the top (the classes of `.app`, `mapEdges.ts`).
    if (app) marks?.observe(app, { childList: true, attributes: true, attributeFilter: ['class', 'style'] });
    const sizes = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    sizes?.observe(legends);
    const bottom = document.querySelector('.overlay.bottom');
    if (bottom) sizes?.observe(bottom);
    window.addEventListener('resize', measure);
    return () => {
      marks?.disconnect();
      sizes?.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, []);
  useEffect(() => {
    const legends = ref.current;
    if (!legends) return;
    if (legends.classList.contains('docked')) return;
    const lifting = liftOver(legends, lifted.current);
    if (Math.abs(lifting - lifted.current) >= 1) setLift(lifting);
  }, [shown, folded]);

  // Its place, after every change of what is around it.
  const covered = narrow && (dockOpen || processingOpen);
  useLayoutEffect(() => {
    const legends = ref.current;
    const app = legends?.closest<HTMLElement>('.app');
    if (!legends || !app) return;
    const section = legends.querySelector<HTMLElement>('.legend');
    const head = legends.querySelector<HTMLElement>('.legend-head');
    if (section && head && place !== 'docked') {
      sizes.current.width = section.getBoundingClientRect().width;
      // The head and the padding and edge of the box round it.
      sizes.current.head = head.getBoundingClientRect().height + section.getBoundingClientRect().height - section.clientHeight + 2 * 6;
      if (place === 'open' && !folded) sizes.current.full = section.getBoundingClientRect().height;
    }
    const next = legendPlace({ covered, room: roomAt(app, lift, sizes.current.width, narrow), head: sizes.current.head, full: folded ? sizes.current.head : sizes.current.full });
    if (next !== place) setPlace(next);
  }, [covered, lift, narrow, folded, place, shown, tick]);

  const here = openHere.place === place && openHere.open;
  const open = place === 'open' ? !folded : here;
  const onTitle = () => (place === 'open' ? toggleFolded() : setOpenHere({ place, open: !here }));

  // Docked, the status line leaves room for the title at its left end.
  useLayoutEffect(() => {
    const legends = ref.current;
    const app = legends?.closest<HTMLElement>('.app');
    if (!legends || !app) return undefined;
    if (place === 'docked') app.style.setProperty('--legend-docked-width', `${legends.getBoundingClientRect().width}px`);
    else app.style.removeProperty('--legend-docked-width');
    return () => {
      app.style.removeProperty('--legend-docked-width');
    };
  }, [place, open]);

  return (
    <div ref={ref} className={`overlay map-legend${place === 'open' ? '' : ` ${place}`}${open ? ' unfolded' : ''}`} style={{ ['--legend-lift' as string]: `${lift}px` }}>
      <section className="legend" role="region" aria-label={LEGEND}>
        <div className="legend-head">
          <button type="button" className="legend-title" aria-expanded={open} onClick={onTitle}>
            {open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
            <span className="legend-title-text">{LEGEND}</span>
          </button>
          {shown && (place !== 'docked' || open) && (
            <select
              className="legend-choice"
              aria-label="Layer"
              value={shown.id}
              aria-disabled={entries.length < 2 || undefined}
              data-tip-level="advanced"
              data-tip={entries.length < 2 ? ONE_LEGEND_TIP : undefined}
              onChange={(e) => {
                if (entries.length > 1) choose(e.target.value);
              }}
            >
              {entries.map((entry) => (
                <option key={entry.id} value={entry.id}>
                  {entry.title}
                </option>
              ))}
            </select>
          )}
        </div>
        {open && shown && <LegendBody content={shown.content} columns />}
      </section>
    </div>
  );
}
