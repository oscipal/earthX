// What of the search results is on the map (`mapResults.ts`, Otto 27.10.2026): the one function of the state.

import { describe, expect, it } from 'vitest';

import { resultsOnMapOf, type ResultsState } from './mapResults';
import type { StacItem, TimeStepGroup } from './types';

const item = (id: string): StacItem => ({ id, collection: 'c', bbox: [0, 0, 1, 1], properties: { datetime: '2026-07-24T10:00:00Z' }, assets: {} });
const group = (label: string, ids: string[]): TimeStepGroup => ({ label, key: label, items: ids.map(item) }) as unknown as TimeStepGroup;
const groups = [group('day 1', ['a1', 'a2']), group('day 2', ['b1', 'b2'])];

function state(over: Partial<ResultsState> = {}): ResultsState {
  return { resultsOnMap: true, focusMode: false, groups, expandedGroupIndex: 0, selectedIds: [], downloaded: {}, ...over };
}
const ids = (items: StacItem[]) => items.map((it) => it.id);

describe('resultsOnMapOf, browsing', () => {
  it('shows the open time step with the results on the map', () => {
    expect(ids(resultsOnMapOf(state()).quicklooks)).toEqual(['a1', 'a2']);
  });

  it('shows nothing with the results hidden and nothing ticked', () => {
    const shown = resultsOnMapOf(state({ resultsOnMap: false }));
    expect(shown.quicklooks).toEqual([]);
    expect(shown.overlay).toEqual([]);
    expect(shown.highlight).toEqual([]);
    expect(shown.clickable).toEqual([]);
  });

  it('shows nothing with the results hidden, a ticked scene included: its tick stays (Otto, 28.10.2026)', () => {
    const shown = resultsOnMapOf(state({ resultsOnMap: false, selectedIds: ['b2', 'a1'] }));
    expect(shown.quicklooks).toEqual([]);
    expect(shown.overlay).toEqual([]);
    expect(shown.highlight).toEqual([]);
    expect(shown.clickable).toEqual([]);
  });

  it('lists the ticked scenes in the order they were ticked, the last one on top', () => {
    expect(ids(resultsOnMapOf(state({ selectedIds: ['b2', 'a1', 'b1'] })).highlight)).toEqual(['b2', 'a1', 'b1']);
    expect(ids(resultsOnMapOf(state({ selectedIds: ['a1', 'b2'] })).highlight)).toEqual(['a1', 'b2']);
  });

  it('shows the open step and a ticked scene of another one with the results on the map', () => {
    expect(ids(resultsOnMapOf(state({ selectedIds: ['b1'] })).quicklooks).sort()).toEqual(['a1', 'a2', 'b1']);
  });

  it('shows nothing from a list with all time steps closed, but the ticked scenes', () => {
    expect(resultsOnMapOf(state({ expandedGroupIndex: null })).quicklooks).toEqual([]);
    expect(ids(resultsOnMapOf(state({ expandedGroupIndex: null, selectedIds: ['a1'] })).quicklooks)).toEqual(['a1']);
  });

  it('ignores a tick on a scene that is not in the results', () => {
    const shown = resultsOnMapOf(state({ resultsOnMap: false, selectedIds: ['ghost'] }));
    expect(shown.quicklooks).toEqual([]);
    expect(shown.highlight).toEqual([]);
    expect(shown.clickable).toEqual([]);
  });

  it('is the same for any list, empty or without a time step open', () => {
    expect(resultsOnMapOf(state({ groups: [], resultsOnMap: false })).quicklooks).toEqual([]);
    expect(resultsOnMapOf(state({ groups: [], expandedGroupIndex: 5 })).quicklooks).toEqual([]);
  });
});

describe('resultsOnMapOf, over a full-resolution view', () => {
  const view = (over: Partial<ResultsState> = {}) => state({ focusMode: true, downloaded: { a1: {} }, ...over });

  it('draws no quicklook of browsing, the view draws its scenes', () => {
    expect(resultsOnMapOf(view()).quicklooks).toEqual([]);
  });

  it('lays the open time step over the view with the results on the map', () => {
    expect(ids(resultsOnMapOf(view()).overlay)).toEqual(['a1', 'a2']);
  });

  it('lays nothing over it with the results hidden and nothing ticked', () => {
    expect(resultsOnMapOf(view({ resultsOnMap: false })).overlay).toEqual([]);
  });

  it('lays a ticked scene over it with the results shown: also one the view is made of, once it is ticked again after a crop', () => {
    expect(ids(resultsOnMapOf(view({ selectedIds: ['a1'] })).overlay)).toContain('a1');
    expect(ids(resultsOnMapOf(view({ selectedIds: ['a1', 'b1'] })).overlay).sort()).toEqual(['a1', 'a2', 'b1']);
  });

  it('lays nothing over it, a ticked scene included, while the results are hidden (Otto, 28.10.2026)', () => {
    expect(resultsOnMapOf(view({ resultsOnMap: false, selectedIds: ['a1', 'b1'] })).overlay).toEqual([]);
    expect(resultsOnMapOf(view({ resultsOnMap: false, selectedIds: ['a1', 'b1'] })).highlight).toEqual([]);
  });

  it('lets a click pick the scenes that are drawn while the results are shown: those of the view and what lies over it', () => {
    expect(ids(resultsOnMapOf(view({ selectedIds: ['b1'] })).clickable).sort()).toEqual(['a1', 'a2', 'b1']);
  });

  it('offers the scenes of the results before the scenes of the view, which lie under them: the view\'s own scene must not take the click on its neighbour', () => {
    // a1 is the view; a2 lies beside it in the open group and comes after it in the list.
    const order = ids(resultsOnMapOf(view({})).clickable);
    expect(order.indexOf('a2')).toBeLessThan(order.indexOf('a1'));
    expect(order[order.length - 1]).toBe('a1');
    // Where only the view's scene is under the point, it is still the one that answers: it can be dropped like any other.
    expect(order).toContain('a1');
  });

  it('lets a click pick nothing while the results are hidden, the scenes of the view and the ticked ones included (Otto, 3.11.2026)', () => {
    expect(resultsOnMapOf(view({ resultsOnMap: false, selectedIds: ['b1'] })).clickable).toEqual([]);
    expect(resultsOnMapOf(view({ resultsOnMap: false })).clickable).toEqual([]);
    // Shown again, they answer again.
    expect(ids(resultsOnMapOf(view({ resultsOnMap: true })).clickable).length).toBeGreaterThan(0);
  });

  it('lets a click pick nothing while no group is open, whatever is drawn: the ticked scenes and those of the view included (Otto, 3.11.2026)', () => {
    expect(resultsOnMapOf(view({ expandedGroupIndex: null, selectedIds: ['b1'] })).clickable).toEqual([]);
    expect(resultsOnMapOf(state({ expandedGroupIndex: null, selectedIds: ['b1'] })).clickable).toEqual([]);
    // What is drawn is not what is clickable: the ticked scene is still outlined.
    expect(ids(resultsOnMapOf(state({ expandedGroupIndex: null, selectedIds: ['b1'] })).highlight)).toEqual(['b1']);
    // With a group open the scenes answer again.
    expect(ids(resultsOnMapOf(state({ expandedGroupIndex: 0 })).clickable)).toEqual(['a1', 'a2']);
  });

  it('outlines the ticked scenes only', () => {
    expect(ids(resultsOnMapOf(view({ selectedIds: ['a2', 'b2'] })).highlight).sort()).toEqual(['a2', 'b2']);
  });

  it('lists no scene twice', () => {
    const shown = resultsOnMapOf(view());
    expect(new Set(ids(shown.clickable)).size).toBe(shown.clickable.length);
  });
});
