// The free area of the map (Otto, 14.11.2026): what an open panel takes from it, as classes of `.app`. `index.css` turns them into the two edges
// `--map-left` (the rail, and the dock beside it while it is open) and `--map-right` (the settings bar or the wide sheet while one is open), and
// the status box is centred between them. The Data catalogue is a window that may cover the box, so it is not one of them.

export interface OpenPanels {
  // A panel of the rail is open at the left (`dock`).
  dock: boolean;
  // The settings bar shows (a view, a layer or a result) at the right.
  inspector: boolean;
  // The processing panel is open: the wide sheet at the right, which takes the column of the settings bar.
  processing: boolean;
}

export function mapEdgeClasses({ dock, inspector, processing }: OpenPanels): string {
  const names = [dock && 'has-dock', inspector && !processing && 'has-inspector', processing && 'has-sheet'].filter(Boolean);
  return names.length > 0 ? ` ${names.join(' ')}` : '';
}
