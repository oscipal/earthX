// @vitest-environment jsdom
//
// The time slider (UI-01g, Otto, 26.10.2026): the slider with play and the position, and nothing else: no
// "select all frames", no "add to layers", no "N images" line below it.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { STEP_DWELL_MS, STEP_LATE_AFTER_MS } from '../playback';
import { useAppStore } from '../store';
import type { StacItem } from '../types';
import TimeSlider from './TimeSlider';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const item = (id: string): StacItem => ({ id, collection: 'd', bbox: [0, 0, 1, 1], properties: {}, assets: {} });

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({
    groups: [
      { key: ['2026-07-25'], label: '2026-07-25', items: [item('a'), item('b')] },
      { key: ['2026-07-24'], label: '2026-07-24', items: [item('c')] },
    ],
    activeGroupIndex: 0,
    playing: false,
    shownGroupIndex: null,
  });
  act(() => root.render(<TimeSlider />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('the time slider', () => {
  it('has play, the slider and the position, and no link or image count', () => {
    expect([...container.querySelectorAll('button')].map((b) => b.getAttribute('aria-label'))).toEqual(['Play']);
    expect(container.querySelector('input[type="range"]')).not.toBeNull();
    expect(container.querySelector('.time-count')?.textContent).toBe('1/2');
    expect(container.textContent).not.toMatch(/select all frames|add to layers|image/i);
  });

  it('shows no image count for a group of several scenes or of one', () => {
    for (const index of [0, 1]) {
      act(() => useAppStore.setState({ activeGroupIndex: index }));
      expect(container.textContent).not.toMatch(/\d+ images?|covering ROI/);
    }
  });
});

// NM4-18 (Otto): playing, the timeline names a step by the date of the pass and nothing of the scene, and says so when
// the picture on the map is behind the slider.
describe('the time slider while it plays', () => {
  const NAMED = [
    { key: ['2026-07-25', 'GS2B_SCENE_NAME_C'], label: '2026-07-25 · GS2B_SCENE_NAME_C', items: [item('a')] },
    { key: ['2026-07-24', 'GS2A_SCENE_NAME_B'], label: '2026-07-24 · GS2A_SCENE_NAME_B', items: [item('b')] },
    { key: ['2026-07-23', 'GS2A_SCENE_NAME_A'], label: '2026-07-23 · GS2A_SCENE_NAME_A', items: [item('c')] },
  ];
  const labels = () => [...container.querySelectorAll('.time-labels > *')].map((el) => el.textContent);

  beforeEach(() => {
    vi.useFakeTimers();
    useAppStore.setState({ groups: NAMED, activeGroupIndex: 2, expandedGroupIndex: 2 });
  });
  afterEach(() => {
    act(() => useAppStore.setState({ playing: false }));
    vi.useRealTimers();
  });

  it('names the steps by their full label while it does not', () => {
    act(() => root.render(<TimeSlider />));
    expect(labels()).toEqual(['2026-07-23 · GS2A_SCENE_NAME_A', '2026-07-23 · GS2A_SCENE_NAME_A', '2026-07-25 · GS2B_SCENE_NAME_C']);
  });

  it('names them by their date only: both ends and the step on the map', () => {
    act(() => root.render(<TimeSlider />));
    act(() => useAppStore.setState({ playing: true }));
    expect(labels()).toEqual(['2026-07-23', '2026-07-23', '2026-07-25']);
    expect(container.textContent).not.toMatch(/GS2/);
  });

  it('names the step that is on the map, not the one the slider is at, and says it is loading', () => {
    act(() => root.render(<TimeSlider />));
    act(() => useAppStore.setState({ playing: true }));
    // The playing has asked for the next step (index 1) and the map still shows the one it started at (index 2).
    expect(useAppStore.getState().activeGroupIndex).toBe(1);
    expect(labels()[1]).toBe('2026-07-23');
    act(() => useAppStore.setState({ shownGroupIndex: 1 }));
    expect(labels()[1]).toBe('2026-07-24');
  });

  it('says "Loading…" only when the step is late: its minimum time has passed a while ago and it is not on the map', () => {
    act(() => root.render(<TimeSlider />));
    act(() => useAppStore.setState({ playing: true }));
    const count = () => container.querySelector('.time-count');
    // Asked for, but the picture on the map has not had its time yet: the step is on its way as planned.
    expect(count()?.textContent).toBe('2/3');
    act(() => vi.advanceTimersByTime(STEP_DWELL_MS + STEP_LATE_AFTER_MS - 1));
    expect(count()?.textContent).toBe('2/3');
    act(() => vi.advanceTimersByTime(1));
    expect(count()?.textContent).toBe('Loading…');
    expect(count()?.getAttribute('title')).toMatch(/stays/);
    // On the map, and the one after it is asked for: not late yet.
    act(() => useAppStore.setState({ shownGroupIndex: 1 }));
    expect(count()?.textContent).toBe('1/3');
  });

  it('has the full label again, and no "Loading…", when it is paused', () => {
    act(() => root.render(<TimeSlider />));
    act(() => useAppStore.setState({ playing: true }));
    act(() => container.querySelector<HTMLButtonElement>('.play-btn')!.click());
    expect(useAppStore.getState().playing).toBe(false);
    expect(labels()[1]).toMatch(/GS2A_SCENE_NAME_B/);
    expect(container.querySelector('.time-count')?.textContent).toBe('2/3');
  });
});
