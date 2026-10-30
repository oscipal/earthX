// Playing the timeline (NM4-18): the next step is asked for as soon as the one before is on the map, the playing waits
// for the map to say it is there, skips a step that does not load, and stops when none does.

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import {
  MAX_SKIPPED_IN_A_ROW,
  playLabel,
  runPlayback,
  SKIPPED_NOTICE,
  STEP_DWELL_MS,
  STEP_LOAD_TIMEOUT_MS,
  STOPPED_NOTICE,
} from './playback';
import { useAppStore } from './store';
import type { StacItem, TimeStepGroup } from './types';

const item = (id: string): StacItem => ({ id, collection: 'd', bbox: [0, 0, 1, 1], properties: {}, assets: {} });
const group = (key: string[], label = key.join(' · ')): TimeStepGroup => ({ key, label, items: [item(key.join('-'))] });

// Newest first, as the groups are.
const GROUPS = [group(['2026-07-25', 'SCENE_C']), group(['2026-07-24', 'SCENE_B']), group(['2026-07-23', 'SCENE_A'])];
const NOW = new Date('2026-10-30T12:00:00Z').getTime();

let stop: (() => void) | null;

// What the map does when a step is on it: it says so.
const shown = (index: number) => useAppStore.setState({ shownGroupIndex: index });

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  useAppStore.setState({ groups: GROUPS, activeGroupIndex: 2, expandedGroupIndex: 2, playing: true, shownGroupIndex: null, revealNotBefore: 0, notice: null });
  stop = null;
});

afterEach(() => {
  stop?.();
  vi.useRealTimers();
  useAppStore.setState({ playing: false });
});

describe('playLabel', () => {
  it('is the date of the pass, whatever the key goes on with', () => {
    expect(playLabel(group(['2026-07-25', 'GS2B_20260725T103021_N0511']))).toBe('2026-07-25');
    expect(playLabel(group(['2026-07-25T10:30:21Z']))).toBe('2026-07-25');
  });

  it('keeps the label of a key that starts with no date, and of nothing', () => {
    expect(playLabel(group(['orbit 12', '2026-07-25']))).toBe('orbit 12 · 2026-07-25');
    expect(playLabel(group([], 'all'))).toBe('all');
    expect(playLabel(undefined)).toBe('');
  });
});

describe('runPlayback', () => {
  it('asks for the next step at once, to be shown not before the minimum time of the one on the map', () => {
    stop = runPlayback();
    const s = useAppStore.getState();
    // The slider runs from the oldest to the newest: index 2 is the oldest, and the step after it is index 1.
    expect(s.activeGroupIndex).toBe(1);
    expect(s.expandedGroupIndex).toBe(1);
    expect(s.shownGroupIndex).toBe(2);
    expect(s.revealNotBefore).toBe(NOW + STEP_DWELL_MS);
  });

  it('asks for no further step until the map says the one before is on it', () => {
    stop = runPlayback();
    vi.advanceTimersByTime(STEP_LOAD_TIMEOUT_MS - 1);
    expect(useAppStore.getState().activeGroupIndex).toBe(1);
    shown(1);
    expect(useAppStore.getState().activeGroupIndex).toBe(0);
    // The minimum time counts from the moment the step is on the map.
    expect(useAppStore.getState().revealNotBefore).toBe(NOW + STEP_LOAD_TIMEOUT_MS - 1 + STEP_DWELL_MS);
  });

  it('goes round from the newest step to the oldest', () => {
    useAppStore.setState({ activeGroupIndex: 0, expandedGroupIndex: 0 });
    stop = runPlayback();
    expect(useAppStore.getState().activeGroupIndex).toBe(2);
  });

  it('does not take the step it asked for for one that is on the map', () => {
    stop = runPlayback();
    // `activeGroupIndex` is 1 but the map shows 2: nothing more is asked for.
    vi.advanceTimersByTime(STEP_DWELL_MS + 1000);
    expect(useAppStore.getState().activeGroupIndex).toBe(1);
  });

  it('skips a step that has not loaded in time, with a notice, and asks for the next', () => {
    stop = runPlayback();
    vi.advanceTimersByTime(STEP_DWELL_MS + STEP_LOAD_TIMEOUT_MS);
    const s = useAppStore.getState();
    expect(s.activeGroupIndex).toBe(0);
    expect(s.notice).toBe(SKIPPED_NOTICE);
    expect(s.playing).toBe(true);
    // The step on the map is still the one before the skipped one.
    expect(s.shownGroupIndex).toBe(2);
  });

  it('goes on after a skipped step when the next one loads', () => {
    stop = runPlayback();
    vi.advanceTimersByTime(STEP_DWELL_MS + STEP_LOAD_TIMEOUT_MS);
    shown(0);
    expect(useAppStore.getState().activeGroupIndex).toBe(2);
    // The skipped steps are forgotten: three more failures are needed to stop it.
    for (let i = 0; i < MAX_SKIPPED_IN_A_ROW - 1; i++) vi.advanceTimersByTime(STEP_LOAD_TIMEOUT_MS + STEP_DWELL_MS);
    expect(useAppStore.getState().playing).toBe(true);
  });

  it('stops, with a notice, when step after step does not load', () => {
    stop = runPlayback();
    for (let i = 0; i < MAX_SKIPPED_IN_A_ROW; i++) vi.advanceTimersByTime(STEP_DWELL_MS + STEP_LOAD_TIMEOUT_MS);
    const s = useAppStore.getState();
    expect(s.playing).toBe(false);
    expect(s.notice).toBe(STOPPED_NOTICE);
    // Nothing is asked for any more.
    const asked = s.activeGroupIndex;
    vi.advanceTimersByTime(60_000);
    expect(useAppStore.getState().activeGroupIndex).toBe(asked);
  });

  it('follows a step the user picks while it plays: from there on', () => {
    stop = runPlayback();
    useAppStore.getState().setActiveGroupIndex(0);
    shown(0);
    expect(useAppStore.getState().activeGroupIndex).toBe(2);
  });

  it('asks for nothing more once stopped, and leaves nothing of itself in the state', () => {
    stop = runPlayback();
    stop();
    stop = null;
    shown(1);
    vi.advanceTimersByTime(60_000);
    const s = useAppStore.getState();
    expect(s.activeGroupIndex).toBe(1);
    expect(s.revealNotBefore).toBe(0);
    expect(s.notice).toBeNull();
  });
});
