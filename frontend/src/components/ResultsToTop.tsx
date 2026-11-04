import { clampResultsAt } from '../resultsEntry';
import { useAppStore } from '../store';
import { ArrowUpToLineIcon } from './icons';

export const RESULTS_TO_TOP_TIP = 'Put search results on top of the layers';
export const RESULTS_ON_TOP_TIP = 'Search results are on top of the layers already';

// Puts the entry "Results" on top of the layer manager (Otto, 30.10.2026, zu #249): moved down by the user, this brings it back
// over all layers (it stays on top otherwise, Otto, 2.11.2026). Already on top, it stays where it is, greyed out, with the reason in
// its tooltip.
export default function ResultsToTop() {
  const onTop = useAppStore((s) => clampResultsAt(s.resultsAt, s.layers) === 0);
  const toTop = useAppStore((s) => s.resultsToTop);
  const tip = onTop ? RESULTS_ON_TOP_TIP : RESULTS_TO_TOP_TIP;
  return (
    <button
      type="button"
      className="lm-eye results-to-top"
      title={tip}
      aria-label={RESULTS_TO_TOP_TIP}
      aria-disabled={onTop || undefined}
      onClick={() => {
        if (!onTop) toTop();
      }}
    >
      <ArrowUpToLineIcon size={14} />
    </button>
  );
}
