// What a legend shows (M5-62): classes as a list (colour, value, name) or a band with a colour scale as a bar with its ends and unit;
// the same in the legend over the map and under a layer of the layer manager.

import { entryOf, gradientOf, isReversed } from '../colormaps';
import type { LegendContent } from '../mapLegend';
import { formatNumber } from '../numberFormat';
import { useColormapGroups } from './useColormapGroups';

// From this many classes on, a list over the map takes two columns (one under 900 px, `index.css`).
const TWO_COLUMNS = 7;

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

function Classes({ content, columns }: { content: Extract<LegendContent, { kind: 'classes' }>; columns: boolean }) {
  return (
    <ul className={`legend-classes${columns && content.classes.length >= TWO_COLUMNS ? ' two-columns' : ''}`}>
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

// `columns`: a long list may take two columns (over the map); in the narrow layer manager it keeps one, so that no name is cut.
export default function LegendBody({ content, columns }: { content: LegendContent; columns: boolean }) {
  return content.kind === 'bar' ? <Bar content={content} /> : <Classes content={content} columns={columns} />;
}
