// The block at the bottom of the map (NM4-66, Otto, 31.10.2026): the bar of the selection and the timeline under it are
// one panel with one grip, one place and one "x". The timeline is as wide as the bar. With no scene ticked the block keeps its width and
// says "Select a scene" in the place of the buttons (Otto, 2.11.2026); with no time steps, it is the bar alone.
//
// With the search results hidden on the map (the eye of the entry "Search results" off) the whole block is not shown, the bar and the
// timeline (Otto, 1.11.2026, replaces the timeline that stayed). The ticks and the time step stay as they are; the block is back with the
// eye, also when a scene is ticked (zu #221).
//
// With a view open the block is there as well, as long as the results are shown (Otto, 3.11.2026, zu #282): "Select a scene" with nothing ticked
// beside the view, else the buttons; "Crop to AOI" then adds the scenes to the view.
//
// The "x" only hides the block: the ticks, the results on the map and the layers stay as they are. A click on a scene,
// an opened group or new results bring it back (`store.ts::selectionBlockClosed`).

import { useAppStore } from '../store';
import CloseButton from './CloseButton';
import Draggable from './Draggable';
import TimeSlider from './TimeSlider';
import ViewBar from './ViewBar';

export const SELECT_A_SCENE = 'Select a scene';

// What the block shows (the one place that says): the buttons of the ticked scenes or "Select a scene", and the timeline.
//  - a result of a job is open: the buttons of the ticks, no timeline (the time slider picks the pass of an order, not here);
//  - a view is open: the buttons of the scenes ticked beside it (those are what "Crop to AOI" adds), else "Select a scene"; the
//    timeline where the search has time steps (Otto, 3.11.2026, zu #282);
//  - otherwise browsing: the buttons of the ticks, the timeline where there are time steps.
export function selectionBlockModeOf(s: { focusMode: boolean; resultView: boolean; hasSelection: boolean; tickedBesideView: boolean; hasGroups: boolean }): { bar: boolean; timeline: boolean } {
  if (s.focusMode) return { bar: s.tickedBesideView, timeline: s.hasGroups };
  if (s.resultView) return { bar: s.hasSelection, timeline: false };
  return { bar: s.hasSelection, timeline: s.hasGroups };
}

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
            {SELECT_A_SCENE}
          </p>
        )}
        {timeline && <TimeSlider />}
      </div>
    </Draggable>
  );
}
