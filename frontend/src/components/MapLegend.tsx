// The legend over the map (M5-62, Otto 24.11.2026): one box at the bottom left, beside the panel of the rail, always there, titled
// "Legend". It shows the topmost visible layer with a legend (`mapLegend.ts`), in the order of the layer manager; the dropdown in its
// head chooses another until the layers change, and then it is the topmost again (`chooseLegend`). Without one the box keeps its title
// and says nothing else. It never scrolls: a long list of classes takes two
// columns, and the title folds it. It stands above what lies at the bottom of the map (the marks of `PreviewBadge`, the bar of the time
// steps), never over it.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { useLegendStore } from '../legendStore';
import { chooseLegend, layersSignature, legendEntries } from '../mapLegend';
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
  const lifted = useRef(0);
  lifted.current = lift;

  // Measured again whenever the legend or the bar at the bottom change size, a mark comes or goes, and with the window.
  useLayoutEffect(() => {
    const legends = ref.current;
    if (!legends) return;
    const measure = () => {
      const lifting = liftOver(legends, lifted.current);
      if (Math.abs(lifting - lifted.current) >= 1) setLift(lifting);
    };
    measure();
    const app = legends.closest('.app');
    const marks = app && typeof MutationObserver !== 'undefined' ? new MutationObserver(measure) : null;
    if (app) marks?.observe(app, { childList: true });
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
    const lifting = liftOver(legends, lifted.current);
    if (Math.abs(lifting - lifted.current) >= 1) setLift(lifting);
  }, [shown, folded]);

  const open = !folded;
  return (
    <div ref={ref} className="overlay map-legend" style={{ ['--legend-lift' as string]: `${lift}px` }}>
      <section className="legend" role="region" aria-label={LEGEND}>
        <div className="legend-head">
          <button type="button" className="legend-title" aria-expanded={open} onClick={toggleFolded}>
            {open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
            <span className="legend-title-text">{LEGEND}</span>
          </button>
          {shown && (
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
