// @vitest-environment jsdom
//
// The hint below a dataset's lowest released level, rendered (M2-10).
//
// A render test and not a check of `zoomFloorHint` alone, because the bug this
// covers was never in the rule: the hint sat in the control panel, which
// `runSearch` slides off screen, so it was never once on screen in the
// situation it is for (found locally by Otto, 22.09.2026). Only mounting the
// component that is always visible shows that.
//
// Rendered into a real document rather than to static markup, and this one file
// asks for a DOM (`@vitest-environment jsdom`) while the rest of the suite stays
// on plain node: zustand hands a server render its *initial* state, so a static
// render would show this component an empty store no matter what the test sets.

import { act } from 'react';
import { createRoot } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { datasetsFrom } from '../datasets';
import { useAppStore } from '../store';
import type { Collection, StacItem } from '../types';
import StatusBar from './StatusBar';

const ZARR_LIKE: Collection = {
  id: 'sentinel-2-l2a-zarr3',
  title: 'Sentinel-2 L2A (Zarr3)',
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14 },
};

const COG_LIKE: Collection = {
  id: 'sentinel-2-c1-l2a',
  title: 'Sentinel-2 L2A',
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19 },
};

const SCENE: StacItem = {
  id: 'S2B_1',
  bbox: [10, 47, 11, 48],
  properties: { datetime: '2026-07-24T10:00:00Z' },
  assets: {},
};

let container: HTMLDivElement;

function show(collection: Collection, mapZoom: number, withResults = true): HTMLElement {
  act(() => {
    useAppStore.setState({
      datasets: datasetsFrom([collection]),
      datasetId: collection.id,
      mapZoom,
      groups: withResults ? [{ key: ['2026-07-24'], label: '2026-07-24', items: [SCENE] }] : [],
      error: null,
      notice: null,
      searching: false,
      downloading: false,
      // Exactly as `runSearch` leaves it. The panel that used to carry this hint
      // is off screen in this state, which is the whole point of the case.
      panelCollapsed: true,
    });
    createRoot(container).render(<StatusBar />);
  });
  return container;
}

describe('StatusBar: below a dataset’s lowest released level', () => {
  beforeEach(() => {
    container = document.createElement('div');
    document.body.append(container);
  });

  afterEach(() => {
    container.remove();
  });

  it('says why the map is empty, with the control panel collapsed', () => {
    const text = show(ZARR_LIKE, 5).textContent ?? '';
    expect(text).toContain('Zoom in to level 8');
    expect(text).toContain('Sentinel-2 L2A (Zarr3)');
    expect(text).toContain('coverage layer');
  });

  it('says nothing at or above the floor', () => {
    expect(show(ZARR_LIKE, 8).textContent).not.toContain('Zoom in to level');
  });

  it('says nothing well above the floor', () => {
    expect(show(ZARR_LIKE, 12).textContent).not.toContain('Zoom in to level');
  });

  it('says nothing for a dataset released from z0', () => {
    expect(show(COG_LIKE, 2).textContent).not.toContain('Zoom in to level');
  });

  it('says nothing before a search has anything to show', () => {
    expect(show(ZARR_LIKE, 5, false).textContent).not.toContain('Zoom in to level');
  });

  it('is a state, not an event: no dismiss button, and announced as a status', () => {
    const root = show(ZARR_LIKE, 5);
    const hint = root.querySelector('[role="status"]');
    expect(hint).not.toBeNull();
    expect(hint?.querySelector('button')).toBeNull();
  });
});
