import { useAppStore } from '../store';
import { EyeIcon, EyeOffIcon } from './icons';

export const HIDE_RESULTS_TIP = 'Hide search results on the map';
export const SHOW_RESULTS_TIP = 'Show search results on the map';

// The eye of the search results on the map (NM4-59, Otto, 30.10.2026): one switch, in the entry "Results" of the layer
// manager and in the head of the results list. Besides it, a search and a tick show the results, a crop hides them
// (`store.ts::setResultsOnMap`).
export default function ResultsEye() {
  const on = useAppStore((s) => s.resultsOnMap);
  const toggle = useAppStore((s) => s.toggleResultsOnMap);
  const tip = on ? HIDE_RESULTS_TIP : SHOW_RESULTS_TIP;
  return (
    <button type="button" className={`icon-btn sm${on ? '' : ' off'}`} data-col="eye" title={tip} aria-label={tip} aria-pressed={on} onClick={() => toggle()}>
      {on ? <EyeIcon size={14} /> : <EyeOffIcon size={14} />}
    </button>
  );
}
