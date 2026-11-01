import { clampResultsAt } from '../resultsEntry';
import { useAppStore } from '../store';

export const RESULTS_TO_TOP_TIP = 'Put search results on top of the layers';
export const RESULTS_ON_TOP_TIP = 'Search results are on top of the layers already';

// Puts the entry "Results" on top of the layer manager (Otto, 30.10.2026, zu #249): new layers go over it, this brings it
// back over all of them. Already on top, it stays where it is, greyed out, with the reason in its tooltip.
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
      <svg viewBox="0 0 24 24" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round">
        <path d="M5 4h14" />
        <path d="M12 20V8" />
        <path d="M7 13l5-5 5 5" />
      </svg>
    </button>
  );
}
