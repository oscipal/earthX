import { useAppStore } from './store';

// Where the arrow keys do not browse the passes: in a field that takes the cursor, on the slider (it steps itself, one the same
// way), in a list, menu or dialog that uses them for its own choice, and on the compass, which turns the map with them in 3D (UI-06).
const OWN_ARROWS = 'input, textarea, select, [contenteditable=""], [contenteditable="true"], [role="listbox"], [role="menu"], [role="dialog"], [role="slider"], .map-compass';

// ←/→ browse the time steps (passes) like the arrows beside the date (Otto, 05.11.2026): left to the one before, right to the
// one after, as the slider reads, oldest on the left. Ends stay where they are. By hand, a step ends the playing. Taken before
// the map, which would pan with the same keys. Read from the store at the key, so that the handler is never behind.
export function stepWithArrowKeys(event: KeyboardEvent): boolean {
  if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return false;
  if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return false;
  const target = event.target instanceof Element ? event.target : null;
  if (target?.closest(OWN_ARROWS)) return false;
  const { groups, activeGroupIndex, shownGroupIndex, playing, setPlaying, setActiveGroupIndex } = useAppStore.getState();
  if (groups.length < 2) return false;
  // `groups` is newest first: the one before (left) is the next index, the one after (right) the one below.
  const from = playing && shownGroupIndex !== null ? shownGroupIndex : activeGroupIndex;
  const to = event.key === 'ArrowLeft' ? from + 1 : from - 1;
  event.preventDefault();
  event.stopPropagation();
  if (to < 0 || to >= groups.length) return true;
  setPlaying(false);
  setActiveGroupIndex(to);
  return true;
}

