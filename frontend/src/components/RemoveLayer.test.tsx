// @vitest-environment jsdom
//
// UI-09 (Otto, 16.11.2026): the bin of a layer asks before the layer is removed, in the layer manager and in the settings bar.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { confirmRemoval } from '../fixtures/confirmRemoval';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';
import { REMOVE_TITLE } from './RemoveLayerButton';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const restore = { datasetId: 'ds', itemIds: ['s'], groupItemIds: [['s']], aoi: null, cropToAoi: false } as unknown as MapLayer['restore'];
const layer = (id: string): MapLayer => ({ id, name: `Layer ${id}`, visible: true, opacity: 1, overlays: [], restore });
const dialog = () => document.body.querySelector<HTMLElement>('[role="alertdialog"]');
const ids = () => useAppStore.getState().layers.map((l) => l.id);
const bin = (row = 0) => container.querySelectorAll<HTMLButtonElement>('.layer-row [data-col="remove"]')[row];
const answer = (text: string) => [...dialog()!.querySelectorAll('button')].find((b) => b.textContent === text)!;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({ datasets: [], layers: [layer('a'), layer('b')], dock: 'layers' });
  act(() => root.render(<LayerManager />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('the bin of a layer row', () => {
  it('asks first and removes nothing yet', () => {
    act(() => bin().click());
    expect(dialog()?.textContent).toContain(REMOVE_TITLE);
    expect(dialog()?.textContent).toContain('Layer a');
    expect(ids()).toEqual(['a', 'b']);
  });

  it('puts the focus on "Cancel", so that a slip of the Enter key removes nothing', () => {
    act(() => bin().click());
    expect(document.activeElement).toBe(answer('Cancel'));
  });

  it('removes the layer on "Remove" and closes the question', () => {
    act(() => bin(1).click());
    confirmRemoval();
    expect(ids()).toEqual(['a']);
    expect(dialog()).toBeNull();
  });

  it.each([
    ['Cancel', () => act(() => answer('Cancel').click())],
    ['Escape', () => act(() => void dialog()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))],
    ['a click beside the dialog', () => act(() => void document.body.querySelector<HTMLElement>('.dialog-backdrop')!.click())],
  ])('keeps the layer on %s', (_, leave) => {
    act(() => bin().click());
    leave();
    expect(ids()).toEqual(['a', 'b']);
    expect(dialog()).toBeNull();
  });

  it('keeps the focus between the two answers on Tab', () => {
    act(() => bin().click());
    act(() => void dialog()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true })));
    expect(document.activeElement).toBe(answer('Remove'));
    act(() => void dialog()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true })));
    expect(document.activeElement).toBe(answer('Cancel'));
  });

  it('does not close on a click inside the dialog', () => {
    act(() => bin().click());
    act(() => void dialog()!.querySelector<HTMLElement>('.dialog-body')!.click());
    expect(dialog()).not.toBeNull();
    expect(ids()).toEqual(['a', 'b']);
  });

  it('has the bin as the last place of the row, right after the download or its note', () => {
    for (const row of container.querySelectorAll('.layer-row')) {
      const places = [...row.children].map((c) => c.getAttribute('data-col'));
      expect(places.at(-1)).toBe('remove');
      expect(places.at(-2)).toBe('download');
    }
  });
});
