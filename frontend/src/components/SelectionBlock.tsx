// The block at the bottom of the map (NM4-66, Otto, 31.10.2026): the bar of the selection and the timeline under it are
// one panel with one grip, one place and one "x". The timeline is as wide as the bar. With no scene ticked the block is
// the timeline alone; with no time steps, the bar alone.
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

export default function SelectionBlock({ bar, timeline }: { bar: boolean; timeline: boolean }) {
  const closed = useAppStore((s) => s.selectionBlockClosed);
  const close = useAppStore((s) => s.closeSelectionBlock);
  const resultsOnMap = useAppStore((s) => s.resultsOnMap);
  const showBar = bar;
  if (closed || !resultsOnMap || (!showBar && !timeline)) return null;
  return (
    <Draggable id="selection" className={showBar ? 'fill' : 'time-only'}>
      <div className="panel selection-block" data-testid="selection-block">
        <div className="block-head">
          <CloseButton onClick={close} />
        </div>
        {showBar && <ViewBar />}
        {timeline && <TimeSlider />}
      </div>
    </Draggable>
  );
}
