// @vitest-environment jsdom
//
// The time slider (UI-01g, Otto, 26.10.2026): the slider with play and the position, and nothing else: no
// "select all frames", no "add to layers", no "N images" line below it.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { STEP_DWELL_MS, STEP_LATE_AFTER_MS } from '../playback';
import CSS from '../index.css?raw';
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

// NM4-18 (Otto): the timeline names a step by the date of the pass and nothing of the scene, playing or not, and says so
// when the picture on the map is behind the slider.
describe('the labels of the time slider', () => {
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

  it('names the steps by their date only, both ends and the step, while it does not play', () => {
    act(() => root.render(<TimeSlider />));
    expect(labels()).toEqual(['2026-07-23', '2026-07-23', '2026-07-25']);
    expect(container.textContent).not.toMatch(/GS2/);
  });

  it('names them by their date only while it plays as well', () => {
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

  it('has the date only, and no "Loading…", when it is paused', () => {
    act(() => root.render(<TimeSlider />));
    act(() => useAppStore.setState({ playing: true }));
    act(() => container.querySelector<HTMLButtonElement>('.play-btn')!.click());
    expect(useAppStore.getState().playing).toBe(false);
    expect(labels()[1]).toBe('2026-07-24');
    expect(container.querySelector('.time-count')?.textContent).toBe('2/3');
  });
});

// The bands are placed by the browser: what the CSS promises is read off the file, and `Draggable` marks each band.
describe('the bands at the bottom of the map', () => {
  it('lay the block of the selection over the view, also where a moved view stays over the place of the block', () => {
    const start = CSS.indexOf(".draggable[data-band='selection'] {");
    expect(start).toBeGreaterThanOrEqual(0);
    expect(CSS.slice(start, CSS.indexOf('}', start))).toContain('z-index: 1');
    expect(CSS).not.toContain("data-band='timeline'");
  });
});

// NM4-18 (Otto, 30.10.2026): "Play" shows the results that are hidden, and a click on a scene ends the playing.
describe('playing and the results on the map', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useAppStore.setState({
      groups: [
        { key: ['2026-07-25'], label: '2026-07-25', items: [item('a')] },
        { key: ['2026-07-24'], label: '2026-07-24', items: [item('b')] },
      ],
      activeGroupIndex: 1,
      expandedGroupIndex: 1,
      selectedIds: [],
      resultsOnMap: false,
    });
    act(() => root.render(<TimeSlider />));
  });
  afterEach(() => {
    act(() => useAppStore.setState({ playing: false, resultsOnMap: true }));
    vi.useRealTimers();
  });
  const play = () => container.querySelector<HTMLButtonElement>('.play-btn')!;

  it('shows the results that are hidden when "Play" is pressed, and plays', () => {
    act(() => play().click());
    expect(useAppStore.getState().resultsOnMap).toBe(true);
    expect(useAppStore.getState().playing).toBe(true);
  });

  it('leaves the results that are shown alone, and does not hide them on "Pause"', () => {
    act(() => useAppStore.setState({ resultsOnMap: true }));
    act(() => play().click());
    act(() => play().click());
    expect(useAppStore.getState().resultsOnMap).toBe(true);
    expect(useAppStore.getState().playing).toBe(false);
  });

  it('stops when "Select all", a group\'s box or "Clear selection" is used', () => {
    act(() => useAppStore.setState({ resultsOnMap: true, items: useAppStore.getState().groups.flatMap((g) => g.items) }));
    const actions: [string, () => void][] = [
      ['select all', () => useAppStore.getState().selectAllLoaded()],
      ['a group\'s box', () => useAppStore.getState().toggleGroupSelected(0)],
      ['select all in the group', () => useAppStore.getState().selectAllInActiveGroup()],
      ['clear selection', () => useAppStore.getState().clearSelection()],
    ];
    for (const [name, act1] of actions) {
      act(() => play().click());
      expect(useAppStore.getState().playing, `${name}: playing before`).toBe(true);
      act(act1);
      expect(useAppStore.getState().playing, name).toBe(false);
    }
  });

  it('stops when a group is opened or closed in the list, but not when the playing itself moves on', () => {
    act(() => useAppStore.setState({ resultsOnMap: true }));
    act(() => play().click());
    // The playing asked for the next step by itself: it goes on.
    expect(useAppStore.getState().activeGroupIndex).toBe(0);
    expect(useAppStore.getState().playing).toBe(true);
    act(() => useAppStore.getState().toggleResultsGroup(1));
    expect(useAppStore.getState().activeGroupIndex).toBe(1);
    expect(useAppStore.getState().playing).toBe(false);
    act(() => play().click());
    act(() => useAppStore.getState().toggleResultsGroup(useAppStore.getState().expandedGroupIndex!));
    expect(useAppStore.getState().expandedGroupIndex).toBeNull();
    expect(useAppStore.getState().playing).toBe(false);
  });

  it('stops when a scene is clicked, in the list or on the map, ticking or unticking', () => {
    act(() => useAppStore.setState({ resultsOnMap: true }));
    act(() => play().click());
    expect(useAppStore.getState().playing).toBe(true);
    act(() => useAppStore.getState().toggleSelected('a'));
    expect(useAppStore.getState().playing).toBe(false);
    act(() => play().click());
    act(() => useAppStore.getState().toggleSelected('a'));
    expect(useAppStore.getState().playing).toBe(false);
  });
});
