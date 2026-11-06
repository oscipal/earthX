// The block at the bottom of the map (`components/SelectionBlock.tsx`): what it shows is said here, in one place.

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
