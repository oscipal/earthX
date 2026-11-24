// The legends over the map (M5-62, Otto 24.11.2026): at the bottom left, beside the panel of the rail, one for each visible layer drawn
// with a colour scale or as classes (`mapLegend.ts`), the topmost layer first. They never scroll: a long list of classes takes two
// columns, and the title folds a legend away, for each layer on its own. They stand above what lies at the bottom of the map (the
// marks of `PreviewBadge`, the bar of the time steps), never over it.

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';

import { entryOf, gradientOf, isReversed } from '../colormaps';
import { legendEntries, type LegendContent } from '../mapLegend';
import { formatNumber } from '../numberFormat';
import { useAppStore } from '../store';
import { viewLayerOf, viewShown, layersForMap } from '../viewLayer';
import { ChevronDownIcon, ChevronRightIcon } from './icons';
import { useColormapGroups } from './useColormapGroups';

// From this many classes on, a list takes two columns.
const TWO_COLUMNS = 7;
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

function Bar({ content }: { content: Extract<LegendContent, { kind: 'bar' }> }) {
  const read = useColormapGroups();
  const groups = read === 'failed' ? null : read;
  const entry = entryOf(groups, content.colormap || 'gray');
  const label = (value: number) => (content.unit ? `${formatNumber(value)} ${content.unit}` : formatNumber(value));
  return (
    <div className="legend-scale">
      <span className="legend-bar" style={{ background: entry ? gradientOf(entry.colors, isReversed(content.colormap)) : undefined }} aria-hidden="true" />
      <span className="legend-ends">
        <span>{label(content.min)}</span>
        <span>{label(content.max)}</span>
      </span>
    </div>
  );
}

function Classes({ content }: { content: Extract<LegendContent, { kind: 'classes' }> }) {
  return (
    <ul className={`legend-classes${content.classes.length >= TWO_COLUMNS ? ' two-columns' : ''}`}>
      {content.classes.map((entry) => (
        <li key={entry.value}>
          <span className="class-swatch" style={{ background: entry.colour }} aria-hidden="true" />
          <span className="legend-value">{entry.value}</span>
          <span className="legend-name">{entry.name}</span>
        </li>
      ))}
    </ul>
  );
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
  const [folded, setFolded] = useState<Record<string, boolean>>({});
  const ref = useRef<HTMLDivElement>(null);
  const [lift, setLift] = useState(0);
  const lifted = useRef(0);
  lifted.current = lift;
  const shown = entries.length > 0;

  // Measured again whenever the legends or the bar at the bottom change size, a mark comes or goes, and with the window.
  useLayoutEffect(() => {
    const legends = ref.current;
    if (!legends) return;
    const measure = () => {
      const next = liftOver(legends, lifted.current);
      if (Math.abs(next - lifted.current) >= 1) setLift(next);
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
  }, [shown]);
  useEffect(() => {
    const legends = ref.current;
    if (!legends) return;
    const next = liftOver(legends, lifted.current);
    if (Math.abs(next - lifted.current) >= 1) setLift(next);
  }, [entries, folded]);

  if (entries.length === 0) return null;
  return (
    <div ref={ref} className="overlay map-legend" role="region" aria-label="Legend" style={{ ['--legend-lift' as string]: `${lift}px` }}>
      {entries.map((entry) => {
        const open = !folded[entry.id];
        return (
          <section key={entry.id} className="legend">
            <button
              type="button"
              className="legend-title"
              aria-expanded={open}
              onClick={() => setFolded((was) => ({ ...was, [entry.id]: open }))}
            >
              {open ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
              <span className="legend-title-text">{entry.title}</span>
            </button>
            {open && (entry.content.kind === 'bar' ? <Bar content={entry.content} /> : <Classes content={entry.content} />)}
          </section>
        );
      })}
    </div>
  );
}
