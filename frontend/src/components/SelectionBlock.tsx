// The block at the bottom of the map (NM4-66, Otto, 31.10.2026): the bar of the selection and the timeline under it are
// one panel with one grip, one place and one "x". The timeline is as wide as the bar. With no scene ticked the block keeps its width and
// says "Select a scene" in the place of the buttons (Otto, 2.11.2026); with no time steps, it is the bar alone.
//
// With the search results hidden on the map (the eye of the entry "Search results" off) the whole block is not shown, the bar and the
// timeline (Otto, 1.11.2026, replaces the timeline that stayed). The ticks and the time step stay as they are; the block is back with the
// eye, also when a scene is ticked (zu #221).
//
// The "x" only hides the block: the ticks, the results on the map and the layers stay as they are. A click on a scene,
// an opened group or new results bring it back (`store.ts::selectionBlockClosed`).

import { useAppStore } from '../store';
import CloseButton from './CloseButton';
import Draggable from './Draggable';
import TimeSlider from './TimeSlider';
import ViewBar from './ViewBar';

export const SELECT_A_SCENE = 'Select a scene';

export default function SelectionBlock({ bar, timeline }: { bar: boolean; timeline: boolean }) {
  const closed = useAppStore((s) => s.selectionBlockClosed);
  const close = useAppStore((s) => s.closeSelectionBlock);
  const resultsOnMap = useAppStore((s) => s.resultsOnMap);
  const showBar = bar;
  if (closed || !resultsOnMap || (!showBar && !timeline)) return null;
  return (
    <Draggable id="selection" className="fill">
      <div className="panel selection-block" data-testid="selection-block">
        <div className="block-head">
          <CloseButton onClick={close} />
        </div>
        {showBar ? (
          <ViewBar />
        ) : (
          <p className="select-hint" role="status">
            <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true" focusable="false">
              <rect x="2" y="2" width="12" height="12" rx="3" fill="none" stroke="currentColor" strokeWidth="1.5" />
              <path d="M5 8.2l2 2 4-4.4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            {SELECT_A_SCENE}
          </p>
        )}
        {timeline && <TimeSlider />}
      </div>
    </Draggable>
  );
}
