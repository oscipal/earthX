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
    expect([...container.querySelectorAll('button')].map((b) => b.getAttribute('aria-label'))).toEqual(['Previous step', 'Play']);
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
  // The row of dates, cell by cell: first, before, previous button, shown, next button, after, last. The buttons draw a chevron and have no text; what is not there is empty.
  const cells = () => [...container.querySelectorAll('.time-dates > *')].map((el) => el.textContent ?? '');
  const shown = () => container.querySelector('.time-dates strong')!.textContent;

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
    // At the oldest step: no step before it, the last one is named, the one after it too.
    expect(cells()).toEqual(['', '', '', '2026-07-23', '', '2026-07-24', '2026-07-25']);
    expect(container.textContent).not.toMatch(/GS2/);
  });

  it('names them by their date only while it plays as well', () => {
    act(() => root.render(<TimeSlider />));
    act(() => useAppStore.setState({ playing: true }));
    expect(cells().filter(Boolean)).toEqual(['2026-07-23', '2026-07-24', '2026-07-25']);
    expect(container.textContent).not.toMatch(/GS2/);
  });

  it('names the step that is on the map, not the one the slider is at, and says it is loading', () => {
    act(() => root.render(<TimeSlider />));
    act(() => useAppStore.setState({ playing: true }));
    // The playing has asked for the next step (index 1) and the map still shows the one it started at (index 2).
    expect(useAppStore.getState().activeGroupIndex).toBe(1);
    expect(shown()).toBe('2026-07-23');
    act(() => useAppStore.setState({ shownGroupIndex: 1 }));
    expect(shown()).toBe('2026-07-24');
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
    expect(shown()).toBe('2026-07-24');
    expect(container.querySelector('.time-count')?.textContent).toBe('2/3');
  });
});

// NM4-66 (Otto, 31.10.2026): the row of dates names the first, the one before, the one shown, the one after and the last
// step; "<" and ">" between the one shown and its neighbours go a step.
describe('the row of dates', () => {
  // Seven steps, newest first: 07-07 is the last on the line, 07-01 the first.
  const SEVEN = [7, 6, 5, 4, 3, 2, 1].map((d) => ({ key: [`2026-07-0${d}`], label: `2026-07-0${d}`, items: [item(`s${d}`)] }));
  const cells = () => [...container.querySelectorAll('.time-dates > *')].map((el) => el.textContent ?? '');
  const arrow = (label: string) => container.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
  const at = (position: number) => act(() => useAppStore.setState({ groups: SEVEN, activeGroupIndex: SEVEN.length - 1 - position, expandedGroupIndex: SEVEN.length - 1 - position }));

  it('names five steps in the middle: the first, the one before, the one shown, the one after, the last', () => {
    at(3);
    expect(cells()).toEqual(['2026-07-01', '2026-07-03', '', '2026-07-04', '', '2026-07-05', '2026-07-07']);
  });

  it('names no date twice: the end that is the neighbour is named once', () => {
    at(1);
    expect(cells()).toEqual(['', '2026-07-01', '', '2026-07-02', '', '2026-07-03', '2026-07-07']);
    at(5);
    expect(cells()).toEqual(['2026-07-01', '2026-07-05', '', '2026-07-06', '', '2026-07-07', '']);
  });

  it('has the round button and the chevron of the stepper in the view of an image, not a button of its own', () => {
    at(3);
    for (const [label, direction] of [['Previous step', 'left'], ['Next step', 'right']] as const) {
      const button = arrow(label)!;
      expect(button.className).toBe('vc-step');
      expect(button.querySelector('svg path')!.getAttribute('d')).toBe(direction === 'left' ? 'M9 2.5 4.5 7 9 11.5' : 'M5 2.5 9.5 7 5 11.5');
      expect(button.textContent).toBe('');
    }
    expect(CSS).not.toContain('.time-step');
  });

  it('names the neighbour in the tooltip of its arrow, where a narrow block has no room to print it', () => {
    at(3);
    expect(arrow('Previous step')!.title).toBe('Previous step: 2026-07-03');
    expect(arrow('Next step')!.title).toBe('Next step: 2026-07-05');
  });

  it('has no arrow where there is no step, and keeps the place so that nothing moves', () => {
    at(0);
    expect(arrow('Previous step')).toBeNull();
    expect(arrow('Next step')).not.toBeNull();
    const count = container.querySelectorAll('.time-dates > *').length;
    at(6);
    expect(arrow('Previous step')).not.toBeNull();
    expect(arrow('Next step')).toBeNull();
    expect(container.querySelectorAll('.time-dates > *')).toHaveLength(count);
    // What is not there is hidden from everyone, also from a screen reader.
    expect([...container.querySelectorAll('.time-dates .gone')].every((el) => el.getAttribute('aria-hidden') === 'true' && el.textContent === '' || el.getAttribute('aria-hidden') === 'true')).toBe(true);
  });

  it('shows the one date of a single step and no arrows', () => {
    act(() => useAppStore.setState({ groups: [SEVEN[0]], activeGroupIndex: 0, expandedGroupIndex: 0 }));
    expect(cells().filter(Boolean)).toEqual(['2026-07-07']);
    expect(container.querySelectorAll('.vc-step:not(.gone)')).toHaveLength(0);
  });

  it('goes one step to the older with "<" and one to the newer with ">", and the list follows', () => {
    at(3);
    act(() => arrow('Previous step')!.click());
    expect(useAppStore.getState().activeGroupIndex).toBe(SEVEN.length - 1 - 2);
    expect(useAppStore.getState().expandedGroupIndex).toBe(SEVEN.length - 1 - 2);
    expect(cells()[3]).toBe('2026-07-03');
    act(() => arrow('Next step')!.click());
    act(() => arrow('Next step')!.click());
    expect(cells()[3]).toBe('2026-07-05');
    expect(container.querySelector('.time-count')?.textContent).toBe('3/7');
  });

  it('goes on from the step that is on the map while it plays, and ends the playing', () => {
    vi.useFakeTimers();
    try {
      at(3);
      // Playing asks for the step after (position 4) at once; the map still shows position 3.
      act(() => useAppStore.setState({ playing: true }));
      expect(useAppStore.getState().activeGroupIndex).toBe(SEVEN.length - 1 - 4);
      expect(cells()[3]).toBe('2026-07-04');
      act(() => arrow('Previous step')!.click());
      expect(useAppStore.getState().playing).toBe(false);
      // One step before the one on the map (position 2), not before the one asked for.
      expect(useAppStore.getState().activeGroupIndex).toBe(SEVEN.length - 1 - 2);
    } finally {
      act(() => useAppStore.setState({ playing: false }));
      vi.useRealTimers();
    }
  });

  it('gives way when the block gets narrow: the ends first, then the neighbours, never the date shown', () => {
    const rule = (query: string) => CSS.slice(CSS.indexOf(query), CSS.indexOf('\n}\n', CSS.indexOf(query)));
    expect(CSS).toContain('container-type: inline-size');
    expect(rule('@container (max-width: 459px)')).toMatch(/\.time-end \{\s*visibility: hidden/u);
    expect(rule('@container (max-width: 319px)')).toMatch(/\.time-near \{\s*visibility: hidden/u);
    expect(rule('@container (max-width: 319px)')).not.toMatch(/strong|\.vc-step/u);
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
