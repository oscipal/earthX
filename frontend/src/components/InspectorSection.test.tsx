// @vitest-environment jsdom
// UI-12 (12): a section of the settings bar folds and opens by its head, so that the bar never scrolls (`inspectorFit.ts`).

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { InspectorFitContext } from '../inspectorFitContext';
import { InspectorSection } from './InspectorParts';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;
const toggle = vi.fn();

const render = (folded: string[]) =>
  act(() =>
    root.render(
      <InspectorFitContext.Provider value={{ folded: new Set(folded), toggle, quickRows: Number.POSITIVE_INFINITY }}>
        <InspectorSection title="Quick processing" extra={<span className="extra">1 / 2</span>}>
          <p className="content">NDVI</p>
        </InspectorSection>
      </InspectorFitContext.Provider>,
    ),
  );
const head = () => container.querySelector<HTMLButtonElement>('.insp-fold')!;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  toggle.mockClear();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('a section of the settings bar', () => {
  it('is open with its content and what stands at the right of its head', () => {
    render([]);
    expect(head().textContent).toBe('Quick processing');
    expect(head().getAttribute('aria-expanded')).toBe('true');
    expect(container.querySelector('.content')).not.toBeNull();
    expect(container.querySelector('.extra')).not.toBeNull();
    expect(container.querySelector('.insp-section')?.getAttribute('data-title')).toBe('Quick processing');
  });

  it('folded, keeps only its head, which says so', () => {
    render(['Quick processing']);
    expect(head().getAttribute('aria-expanded')).toBe('false');
    expect(container.querySelector('.insp-section')?.classList.contains('folded')).toBe(true);
    expect(container.querySelector('.content')).toBeNull();
    expect(container.querySelector('.extra')).toBeNull();
  });

  it('folds and opens by its head, under its title', () => {
    render(['Quick processing']);
    act(() => head().click());
    expect(toggle).toHaveBeenCalledWith('Quick processing');
  });
});
