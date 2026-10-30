// Playing the timeline (NM4-18): the map goes on to the next time step only once that step is on the map. The step
// is asked for as soon as the one before is shown, loads out of sight over it (`mapLayers.ts`, `Hold`), and is shown
// at the end of its minimum time or when it has loaded, whichever is later. A step that does not load in time is
// skipped, with a notice; the picture on the map stays all the while.

import { useAppStore } from './store';
import type { TimeStepGroup } from './types';

// How long a step stays on the map at least.
export const STEP_DWELL_MS = 1400;
// How long after its minimum time a step is not yet on the map before the timeline says "Loading…": a step that is just
// about to be shown is not announced as late.
export const STEP_LATE_AFTER_MS = 500;
// How long a step may take to load, after it could have been shown, before it is skipped. Under the 10 s after which
// the map shows a step that has not loaded (`mapLayers.ts`, `RETIRE_AFTER_MS`).
export const STEP_LOAD_TIMEOUT_MS = 6000;
// Steps that fail one after the other before the playing stops.
export const MAX_SKIPPED_IN_A_ROW = 3;

export const SKIPPED_NOTICE = 'Skipped a step that did not load.';
export const STOPPED_NOTICE = 'Playback stopped: the next steps do not load.';

const DATE = /^\d{4}-\d{2}-\d{2}/;

// What the timeline names a step by, playing or not: the date of the pass, and nothing of the scene it was made of
// (the key of a group can go on after its date, with a scene or data take). A key without a date keeps its label.
export function stepLabel(group: TimeStepGroup | undefined): string {
  if (!group) return '';
  const first = group.key[0] ?? '';
  return DATE.test(first) ? first.slice(0, 10) : group.label;
}

// Runs from the moment "Play" is pressed until the returned function is called. Goes to the next-older step of the
// timeline — the slider runs from oldest to newest, `groups` is newest first — and round at the end.
export function runPlayback(now: () => number = Date.now): () => void {
  const { getState, setState, subscribe } = useAppStore;
  // The steps it plays: a new search, another dataset or more results are another list, and the playing starts again.
  const groups = getState().groups;
  let shownAt = now();
  let skipped = 0;
  let waiting = false;
  // The state changes of `request` itself are no word of the map: after a skip the step asked for can be the one on it.
  let asking = false;
  let loadTimer: ReturnType<typeof setTimeout> | undefined;

  const request = () => {
    const s = getState();
    if (s.groups !== groups || s.groups.length < 2) return;
    const next = (s.activeGroupIndex - 1 + s.groups.length) % s.groups.length;
    const notBefore = shownAt + STEP_DWELL_MS;
    asking = true;
    setState({ revealNotBefore: notBefore });
    s.setActiveGroupIndex(next);
    asking = false;
    waiting = true;
    clearTimeout(loadTimer);
    loadTimer = setTimeout(onTimeout, Math.max(0, notBefore - now()) + STEP_LOAD_TIMEOUT_MS);
  };
  const onShown = () => {
    waiting = false;
    clearTimeout(loadTimer);
    skipped = 0;
    shownAt = now();
    request();
  };
  const onTimeout = () => {
    skipped++;
    if (skipped >= MAX_SKIPPED_IN_A_ROW) {
      waiting = false;
      getState().setPlaying(false);
      getState().setNotice(STOPPED_NOTICE);
      return;
    }
    getState().setNotice(SKIPPED_NOTICE);
    request();
  };

  setState({ shownGroupIndex: getState().activeGroupIndex });
  const unsubscribe = subscribe((s) => {
    if (waiting && !asking && s.playing && s.groups === groups && s.shownGroupIndex === s.activeGroupIndex) onShown();
  });
  request();
  return () => {
    unsubscribe();
    clearTimeout(loadTimer);
    setState({ shownGroupIndex: null, revealNotBefore: 0 });
  };
}
