// @vitest-environment jsdom
//
// NM4-66 (Otto, 31.10.2026): the bar of the selection and the timeline are one block with one grip, one place and one
// "x". The "x" hides the block and changes nothing else; a click on a scene, an opened group or new results bring it back.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useBandPositions } from '../bandPositions';
import CSS from '../index.css?raw';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import type { StacItem } from '../types';
import SelectionBlock from './SelectionBlock';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const item = (id: string, day: string): StacItem => ({
  id,
  collection: 'd',
  bbox: [10, 50, 11, 51],
  properties: { datetime: `${day}T10:00:00Z` },
  assets: { visual: { href: `https://data.test/${id}.tif` } },
});
const GROUPS = [
  { key: ['2026-07-25'], label: '2026-07-25', items: [item('a', '2026-07-25')] },
  { key: ['2026-07-24'], label: '2026-07-24', items: [item('b', '2026-07-24')] },
  { key: ['2026-07-23'], label: '2026-07-23', items: [item('c', '2026-07-23')] },
];

let container: HTMLDivElement;
let root: Root;
const state = () => useAppStore.getState();
const render = (bar: boolean, timeline: boolean) => act(() => root.render(<SelectionBlock bar={bar} timeline={timeline} />));
const block = () => container.querySelector('.selection-block');
const closeButton = () => container.querySelector<HTMLButtonElement>('.selection-block .close-x');

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  useBandPositions.setState({ places: {} });
  useAppStore.setState({
    groups: GROUPS,
    items: GROUPS.flatMap((g) => g.items),
    activeGroupIndex: 0,
    expandedGroupIndex: 0,
    selectedIds: ['a'],
    selectionBlockClosed: false,
    playing: false,
    resultsOnMap: true,
    layers: [{ id: 'layer-1' } as unknown as MapLayer],
    focusMode: false,
    datasets: [],
  });
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('one block', () => {
  it('holds the bar and the timeline in one panel, the bar over the timeline, with one grip and one place', () => {
    render(true, true);
    const parts = [...container.querySelectorAll('.selection-block > *')].map((el) => el.className.split(' ')[0]);
    expect(parts).toEqual(['block-head', 'download-bar', 'time-slider']);
    expect(container.querySelectorAll('.panel')).toHaveLength(1);
    expect(container.querySelectorAll('.drag-grip')).toHaveLength(1);
    expect(container.querySelectorAll('.draggable')).toHaveLength(1);
    expect(container.querySelector('.draggable')!.getAttribute('data-band')).toBe('selection');
  });

  it('makes the timeline as wide as the bar: both fill the block, and neither has a width or a minimum of its own', () => {
    const rule = (selector: string) => CSS.slice(CSS.indexOf(`\n${selector} {`), CSS.indexOf('}', CSS.indexOf(`\n${selector} {`)));
    render(true, true);
    expect(container.querySelector('.draggable')!.classList.contains('fill')).toBe(true);
    expect(rule('.draggable.fill')).toContain('width: 100%');
    expect(rule('.selection-block')).toContain('width: 100%');
    expect(rule('.time-slider')).toContain('width: 100%');
    expect(rule('.time-slider')).not.toMatch(/min-width|max-width/u);
    expect(rule('.download-bar')).not.toMatch(/\bwidth:|min-width|max-width/u);
  });

  it('is the timeline alone with nothing ticked, and the bar alone where there are no time steps', () => {
    render(false, true);
    expect(container.querySelector('.download-bar')).toBeNull();
    expect(container.querySelector('.time-slider')).not.toBeNull();
    expect(container.querySelector('.draggable')!.classList.contains('time-only')).toBe(true);
    render(true, false);
    expect(container.querySelector('.download-bar')).not.toBeNull();
    expect(container.querySelector('.time-slider')).toBeNull();
    expect(container.querySelector('.draggable')!.classList.contains('fill')).toBe(true);
  });

  it('is not there with neither', () => {
    render(false, false);
    expect(container.innerHTML).toBe('');
  });

  it('keeps its place when the timeline comes to the bar or goes: one place for the block', () => {
    render(false, true);
    act(() => useBandPositions.getState().move('selection', { x: 120, y: 90 }));
    render(true, true);
    expect(useBandPositions.getState().places.selection).toEqual({ x: 120, y: 90 });
    expect(Object.keys(useBandPositions.getState().places)).toEqual(['selection']);
  });

  it('has its "x" in a head of its own, over no button of the bar', () => {
    render(true, true);
    const head = container.querySelector('.block-head')!;
    expect(head.querySelectorAll('button')).toHaveLength(1);
    expect(head.querySelector('button')!.title).toBe('Close');
    expect(container.querySelector('.download-bar .close-x')).toBeNull();
  });
});

describe('the "x"', () => {
  it('hides the block, and ticks, results on the map and layers stay as they are', () => {
    render(true, true);
    const before = { ids: state().selectedIds, results: state().resultsOnMap, layers: state().layers, group: state().activeGroupIndex };
    act(() => closeButton()!.click());
    expect(state().selectionBlockClosed).toBe(true);
    expect(block()).toBeNull();
    expect(state().selectedIds).toBe(before.ids);
    expect(state().resultsOnMap).toBe(before.results);
    expect(state().layers).toBe(before.layers);
    expect(state().activeGroupIndex).toBe(before.group);
  });

  it('leaves hidden results hidden: closing shows nothing and hides nothing', () => {
    act(() => useAppStore.setState({ resultsOnMap: false }));
    render(true, true);
    act(() => closeButton()!.click());
    expect(state().resultsOnMap).toBe(false);
  });

  it('ends the playing, which has no button left to stop it', () => {
    act(() => useAppStore.setState({ playing: true }));
    render(true, true);
    act(() => closeButton()!.click());
    expect(state().playing).toBe(false);
  });

  it('closes the timeline alone as well', () => {
    render(false, true);
    act(() => closeButton()!.click());
    expect(block()).toBeNull();
  });
});

describe('what shows the block again', () => {
  const closed = () => {
    render(true, true);
    act(() => closeButton()!.click());
    expect(block()).toBeNull();
  };

  it('a tick on a scene, in the list or on the map', () => {
    closed();
    act(() => state().toggleSelected('b'));
    expect(block()).not.toBeNull();
  });

  it('a click that unticks a scene as well: it is a click on a scene', () => {
    closed();
    act(() => state().toggleSelected('a'));
    expect(block()).not.toBeNull();
  });

  it('the box of a group, "Select all" and "Select all in the group"', () => {
    for (const act1 of [() => state().toggleGroupSelected(1), () => state().selectAllLoaded(), () => state().selectAllInActiveGroup()]) {
      closed();
      act(act1);
      expect(block(), String(act1)).not.toBeNull();
    }
  });

  it('a group opened in the list, and a scene that is focused', () => {
    closed();
    act(() => state().toggleResultsGroup(2));
    expect(block()).not.toBeNull();
    closed();
    act(() => state().focusItem('b'));
    expect(block()).not.toBeNull();
  });

  it('new results, and none', () => {
    closed();
    act(() => state().clearSearchResults());
    expect(state().selectionBlockClosed).toBe(false);
  });

  // The other way round: what is no click on a scene and opens no group leaves it closed.
  it('does not: a group that is closed, the playing that moves on, "Clear selection"', () => {
    act(() => useAppStore.setState({ expandedGroupIndex: 1, activeGroupIndex: 1 }));
    closed();
    act(() => state().toggleResultsGroup(1)); // closes the open group
    expect(state().expandedGroupIndex).toBeNull();
    expect(block()).toBeNull();
    act(() => state().setActiveGroupIndex(2)); // what the playing does
    expect(block()).toBeNull();
    act(() => state().clearSelection());
    expect(block()).toBeNull();
    expect(state().selectionBlockClosed).toBe(true);
  });
});

// NM4-65 (Otto, 1.11.2026): "Wenn die results ausgeblendet sind dann soll auch nicht die box erscheinen mit „crop and merge to AOI“".
describe('with the results hidden on the map', () => {
  const hide = () => act(() => useAppStore.setState({ resultsOnMap: false }));
  const bar = () => container.querySelector('.download-bar');

  it('has no bar of the selection: nothing of it is on the map to act on', () => {
    render(true, false);
    expect(bar()).not.toBeNull();
    hide();
    expect(block()).toBeNull();
    expect(bar()).toBeNull();
  });

  it('keeps the timeline alone, and brings the bar back with the results', () => {
    render(true, true);
    expect(bar()).not.toBeNull();
    hide();
    expect(bar()).toBeNull();
    expect(block()).not.toBeNull();
    expect(block()!.querySelector('.close-x')).not.toBeNull();
    act(() => useAppStore.setState({ resultsOnMap: true }));
    expect(bar()).not.toBeNull();
  });

  it('is the same beside a view: the bar of the ticked scenes is gone, the view is not touched', () => {
    render(true, false);
    hide();
    expect(bar()).toBeNull();
  });
});
