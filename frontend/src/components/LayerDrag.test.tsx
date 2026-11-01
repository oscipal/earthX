// @vitest-environment jsdom
//
// NM4-65 part 1 (Otto, 31.10.2026): at the far left of every row of the layer manager — "Results" too — a grip of 2 × 3 small
// dots takes the row with the mouse (or a finger) to another place; ▲/▼ stay for the keyboard and screen readers. The map
// follows the list (NM4-59), which is the list of the store. jsdom has no layout: the rows are given places by hand.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import CSS from '../index.css?raw';
import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import LayerManager from './LayerManager';
import { rowAt } from './useRowDrag';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

const layer = (id: string): MapLayer => ({
  id,
  name: `Layer ${id}`,
  visible: true,
  opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], minZoom: 0, maxZoom: 12 }],
  restore: { datasetId: null, itemIds: [] } as never,
});

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  useAppStore.setState({ layers: [], sections: [], resultsAt: 0 });
});

const rows = () => [...container.querySelectorAll<HTMLElement>('.layer-row')];
const order = () => useAppStore.getState().layers.map((l) => l.id).join('');
const grip = (i: number) => rows()[i].querySelector<HTMLElement>('.lm-grip')!;

// Every row is 30 px high, the list starts at 0.
function lay() {
  rows().forEach((row, i) => {
    row.getBoundingClientRect = () => ({ top: i * 30, bottom: i * 30 + 30, left: 0, right: 100, width: 100, height: 30, x: 0, y: i * 30, toJSON: () => ({}) });
  });
  container.querySelector('.layer-list')!.getBoundingClientRect = () => ({ top: 0, bottom: rows().length * 30, left: 0, right: 100, width: 100, height: rows().length * 30, x: 0, y: 0, toJSON: () => ({}) });
}

const pointer = (type: string, init: { clientY?: number; button?: number } = {}) => {
  const event = new MouseEvent(type, { bubbles: true, cancelable: true, button: init.button ?? 0, clientY: init.clientY ?? 0 });
  Object.assign(event, { pointerId: 1, pointerType: 'mouse' });
  return event;
};
const fire = (el: Element, type: string, init?: { clientY?: number; button?: number }) => act(() => el.dispatchEvent(pointer(type, init)));

function mount(ids: string[], extra: Partial<ReturnType<typeof useAppStore.getState>> = {}) {
  useAppStore.setState({ layers: ids.map(layer), dock: 'layers', resultsAt: 0, sections: [], ...extra });
  act(() => root.render(<LayerManager />));
  lay();
}

describe('the grip of a row', () => {
  it('is the first place of every row, 2 × 3 dots, and no tab stop', () => {
    mount(['A', 'B', 'C']);
    for (const row of rows()) {
      const first = row.firstElementChild as HTMLElement;
      expect(first.getAttribute('data-col')).toBe('grip');
      expect(first.querySelectorAll('circle')).toHaveLength(6);
      expect(first.getAttribute('aria-hidden')).toBe('true');
      expect(first.getAttribute('tabindex')).toBeNull();
    }
    const dots = [...grip(0).querySelectorAll('circle')].map((c) => [c.getAttribute('cx'), c.getAttribute('cy')].join());
    expect(new Set(dots.map((d) => d.split(',')[0])).size).toBe(2);
    expect(new Set(dots.map((d) => d.split(',')[1])).size).toBe(3);
  });

  it('is not there for a lone row, which has nowhere to go: the place stays empty', () => {
    mount(['A']);
    expect(rows()[0].querySelector('.lm-grip')).toBeNull();
    expect(rows()[0].firstElementChild?.getAttribute('data-col')).toBe('grip');
    expect(rows()[0].firstElementChild?.getAttribute('aria-hidden')).toBe('true');
  });

  it('is on the entry "Results" too', () => {
    mount(['A', 'B'], { sections: [{ datasetId: 's2', items: [{ id: 'x', collection: 's2', properties: {}, assets: {} }], groups: [] } as never], resultsAt: 1 });
    expect(rows()).toHaveLength(3);
    expect(rows()[1].classList.contains('results-row')).toBe(true);
    expect(rows()[1].querySelector('.lm-grip')).not.toBeNull();
  });

  it('keeps ▲ and ▼ working', () => {
    mount(['A', 'B', 'C']);
    act(() => rows()[2].querySelector<HTMLButtonElement>('button[title="Move up"]')!.click());
    expect(order()).toBe('ACB');
  });
});

describe('dragging a row by its grip', () => {
  it('moves it to the row where the pointer is let go, down', () => {
    mount(['A', 'B', 'C', 'D']);
    fire(grip(0), 'pointerdown', { clientY: 10 });
    fire(grip(0), 'pointermove', { clientY: 75 });
    fire(grip(0), 'pointerup', { clientY: 75 });
    expect(order()).toBe('BCAD');
  });

  it('and up', () => {
    mount(['A', 'B', 'C', 'D']);
    fire(grip(3), 'pointerdown', { clientY: 100 });
    fire(grip(3), 'pointermove', { clientY: 5 });
    fire(grip(3), 'pointerup', { clientY: 5 });
    expect(order()).toBe('DABC');
  });

  it('shows where the row will stand while it is held: it is lifted, a line marks the place, and the list is unchanged', () => {
    mount(['A', 'B', 'C', 'D']);
    fire(grip(0), 'pointerdown', { clientY: 10 });
    fire(grip(0), 'pointermove', { clientY: 95 });
    expect(rows()[0].classList.contains('dragging')).toBe(true);
    expect(rows()[3].classList.contains('drop-below')).toBe(true);
    expect(container.querySelector('.layer-list')!.classList.contains('is-dragging')).toBe(true);
    expect(order()).toBe('ABCD');
    fire(grip(0), 'pointermove', { clientY: 35 });
    expect(rows()[3].classList.contains('drop-below')).toBe(false);
    expect(rows()[1].classList.contains('drop-below')).toBe(true);
    fire(grip(0), 'pointerup', { clientY: 35 });
    expect(container.querySelector('.dragging, .drop-above, .drop-below, .is-dragging')).toBeNull();
  });

  it('puts the line above the row where the dragged row comes from below', () => {
    mount(['A', 'B', 'C']);
    fire(grip(2), 'pointerdown', { clientY: 70 });
    fire(grip(2), 'pointermove', { clientY: 5 });
    expect(rows()[0].classList.contains('drop-above')).toBe(true);
  });

  it('takes a place beyond the ends of the list as the first or the last row', () => {
    mount(['A', 'B', 'C']);
    fire(grip(1), 'pointerdown', { clientY: 40 });
    fire(grip(1), 'pointermove', { clientY: 900 });
    fire(grip(1), 'pointerup', { clientY: 900 });
    expect(order()).toBe('ACB');
    fire(grip(2), 'pointerdown', { clientY: 70 });
    fire(grip(2), 'pointermove', { clientY: -400 });
    fire(grip(2), 'pointerup', { clientY: -400 });
    expect(order()).toBe('BAC');
  });

  it('changes nothing when the row is let go where it is, or when Escape is pressed', () => {
    mount(['A', 'B', 'C']);
    fire(grip(0), 'pointerdown', { clientY: 10 });
    fire(grip(0), 'pointerup', { clientY: 10 });
    expect(order()).toBe('ABC');
    fire(grip(0), 'pointerdown', { clientY: 10 });
    fire(grip(0), 'pointermove', { clientY: 75 });
    act(() => window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' })));
    expect(container.querySelector('.dragging')).toBeNull();
    fire(grip(0), 'pointerup', { clientY: 75 });
    expect(order()).toBe('ABC');
  });

  it('drops nothing when the pointer is cancelled', () => {
    mount(['A', 'B', 'C']);
    fire(grip(0), 'pointerdown', { clientY: 10 });
    fire(grip(0), 'pointermove', { clientY: 75 });
    fire(grip(0), 'pointercancel');
    expect(order()).toBe('ABC');
    expect(container.querySelector('.dragging')).toBeNull();
  });

  it('is not started by the other buttons of the mouse', () => {
    mount(['A', 'B', 'C']);
    fire(grip(0), 'pointerdown', { clientY: 10, button: 2 });
    fire(grip(0), 'pointermove', { clientY: 75 });
    fire(grip(0), 'pointerup', { clientY: 75 });
    expect(order()).toBe('ABC');
  });

  it('is not started by moves of a pointer that was never put down on a grip', () => {
    mount(['A', 'B', 'C']);
    fire(grip(0), 'pointermove', { clientY: 75 });
    fire(grip(0), 'pointerup', { clientY: 75 });
    expect(order()).toBe('ABC');
  });

  it('moves the entry "Results" among the layers, and the layers over it', () => {
    mount(['A', 'B', 'C'], { sections: [{ datasetId: 's2', items: [{ id: 'x', collection: 's2', properties: {}, assets: {} }], groups: [] } as never], resultsAt: 1 });
    // Rows: A [Results] B C. "Results" to the end.
    fire(grip(1), 'pointerdown', { clientY: 40 });
    fire(grip(1), 'pointermove', { clientY: 100 });
    fire(grip(1), 'pointerup', { clientY: 100 });
    expect(useAppStore.getState().resultsAt).toBe(3);
    expect(order()).toBe('ABC');
    // Rows: A B C [Results]. C to the top, over the other layers: "Results" stays under all three.
    fire(grip(2), 'pointerdown', { clientY: 70 });
    fire(grip(2), 'pointermove', { clientY: 5 });
    fire(grip(2), 'pointerup', { clientY: 5 });
    expect(order()).toBe('CAB');
    expect(useAppStore.getState().resultsAt).toBe(3);
    // Rows: C A B [Results]. A onto the place of "Results": it takes the place, "Results" is one place up.
    fire(grip(1), 'pointerdown', { clientY: 40 });
    fire(grip(1), 'pointermove', { clientY: 100 });
    fire(grip(1), 'pointerup', { clientY: 100 });
    expect(order()).toBe('CBA');
    expect(useAppStore.getState().resultsAt).toBe(2);
  });
});

describe('the place under the pointer', () => {
  const rects = [0, 1, 2].map((i) => ({ top: i * 30, bottom: i * 30 + 30 }));
  it('is the row the pointer is in, the first above the list and the last below it', () => {
    expect(rowAt(rects, 0)).toBe(0);
    expect(rowAt(rects, 29.9)).toBe(0);
    expect(rowAt(rects, 30)).toBe(1);
    expect(rowAt(rects, -50)).toBe(0);
    expect(rowAt(rects, 5000)).toBe(2);
  });

  it('is none for an empty list', () => {
    expect(rowAt([], 10)).toBe(-1);
  });
});

describe('the look of the drag in index.css', () => {
  const rule = (selector: string) => {
    const start = CSS.indexOf(`\n${selector} {`);
    expect(start, selector).toBeGreaterThanOrEqual(0);
    return CSS.slice(start, CSS.indexOf('}', start));
  };
  it('gives the grip its own column at the left of the row, and a finger no scrolling over it', () => {
    expect(rule('.layer-row')).toContain('grid-template-columns: 14px var(--lm-button) minmax(0, 1fr)');
    expect(rule('.lm-grip')).toContain('touch-action: none');
    expect(rule('.lm-grip')).toContain('cursor: grab');
  });
  it('marks the place with a line in the accent colour that takes no part in the click', () => {
    expect(rule('.layer-row.drop-above::before,\n.layer-row.drop-below::after')).toContain('pointer-events: none');
    expect(rule('.layer-row.drop-above::before,\n.layer-row.drop-below::after')).toContain('background: var(--accent)');
  });
});
