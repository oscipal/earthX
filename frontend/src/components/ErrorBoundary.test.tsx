// @vitest-environment jsdom
//
// UI-10: a part that fails while it renders or in an effect shows a short note with "Reload", never a white page.

import { act, useEffect } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useAppStore } from '../store';
import ErrorBoundary from './ErrorBoundary';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.spyOn(console, 'error').mockImplementation(() => {});
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
});

function FailsInRender(): never {
  throw new TypeError('tiles?.some is not a function');
}

function FailsInEffect() {
  useEffect(() => {
    throw new TypeError('tiles?.some is not a function');
  }, []);
  return <p>map</p>;
}

describe('ErrorBoundary', () => {
  it('shows what it holds while nothing fails', () => {
    act(() => root.render(<ErrorBoundary what="The map"><p>map</p></ErrorBoundary>));
    expect(container.textContent).toBe('map');
    expect(container.querySelector('[role="alert"]')).toBeNull();
  });

  it('shows a note with "Reload" for an error in render, and logs it', () => {
    act(() => root.render(<ErrorBoundary what="The map"><FailsInRender /></ErrorBoundary>));
    expect(container.querySelector('[role="alert"]')?.textContent).toContain('The map ran into an error.');
    expect(container.querySelector('button')?.textContent).toBe('Reload');
    expect(console.error).toHaveBeenCalledWith('The map failed', expect.any(TypeError), expect.any(String));
  });

  it('shows the note for an error in an effect, which is what blanked the page', () => {
    act(() => root.render(<ErrorBoundary what="The map"><FailsInEffect /></ErrorBoundary>));
    expect(container.querySelector('[role="alert"]')).not.toBeNull();
    expect(container.querySelector('p')?.textContent).toBe('The map ran into an error.');
  });

  it('keeps what lies beside the failed part: only the map gives way, the panels stay', () => {
    act(() =>
      root.render(
        <div>
          <ErrorBoundary what="The map"><FailsInRender /></ErrorBoundary>
          <nav>panels</nav>
        </div>,
      ),
    );
    expect(container.querySelector('nav')?.textContent).toBe('panels');
  });

  it('reloads the page with "Reload"', () => {
    const reload = vi.fn();
    vi.spyOn(window, 'location', 'get').mockReturnValue({ ...window.location, reload });
    act(() => root.render(<ErrorBoundary what="The page"><FailsInRender /></ErrorBoundary>));
    act(() => container.querySelector('button')!.click());
    expect(reload).toHaveBeenCalledOnce();
  });

  it('outside the app, brings the theme of the app along', () => {
    useAppStore.setState({ theme: 'normal' });
    act(() => root.render(<ErrorBoundary what="The page" themed><FailsInRender /></ErrorBoundary>));
    const page = container.querySelector('.app.error-page');
    expect(page?.getAttribute('data-theme')).toBe('normal');
    expect(page?.textContent).toContain('The page ran into an error.');
  });
});
