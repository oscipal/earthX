// @vitest-environment jsdom
//
// The small line "Copy original scene name" (Otto, 3.11.2026, zu #282): one click copies the names, "Copied" says it for a moment, and the
// names go to the clipboard and nowhere else.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CopySceneNames from './CopySceneNames';
import { tipOf } from '../fixtures/tips';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  vi.useFakeTimers();
  fetchMock = vi.fn();
  vi.stubGlobal('fetch', fetchMock);
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

const render = (names: string[], write?: (text: string) => Promise<void>) => act(() => root.render(<CopySceneNames names={names} write={write} />));
const link = () => container.querySelector<HTMLButtonElement>('.vc-scene-names');
const press = async () => {
  await act(async () => {
    link()!.click();
  });
};

describe('the line', () => {
  it('says "Copy original scene name", and the tooltip for one scene says what it copies', () => {
    render(['S2A_1']);
    expect(link()!.textContent).toBe('Copy original scene name');
    expect(tipOf(link()!)).toBe('Copy the name of the original scene');
  });

  it('has "n scenes" as the tooltip for several', () => {
    render(['S2A_1', 'S2A_2', 'S2B_1']);
    expect(tipOf(link()!)).toBe('3 scenes');
  });

  it('is not there without scenes: the order is gone, or there is no scene', () => {
    render([]);
    expect(link()).toBeNull();
    expect(container.innerHTML).toBe('');
  });
});

describe('a click', () => {
  it('copies every name, one to a line, and says "Copied" for a moment, then the line is as it was', async () => {
    const write = vi.fn(async () => undefined);
    render(['S2A_1', 'S2A_2', 'S2B_1'], write);
    await press();
    expect(write).toHaveBeenCalledWith('S2A_1\nS2A_2\nS2B_1');
    expect(link()!.textContent).toBe('Copied');
    act(() => {
      vi.advanceTimersByTime(2000);
    });
    expect(link()!.textContent).toBe('Copy original scene name');
  });

  it('copies the one name of one scene', async () => {
    const write = vi.fn(async () => undefined);
    render(['S2A_1'], write);
    await press();
    expect(write).toHaveBeenCalledWith('S2A_1');
  });

  it('says so where the browser does not allow it, and does not say "Copied"', async () => {
    render(['S2A_1'], async () => Promise.reject(new Error('denied')));
    await press();
    expect(link()!.textContent).toBe('Could not copy');
  });

  it('goes only to the clipboard: not into the address, not to the network, not to the console', async () => {
    const write = vi.fn(async () => undefined);
    const log = vi.spyOn(console, 'log').mockImplementation(() => undefined);
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const error = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const before = window.location.href;
    render(['S2A_1', 'S2A_2'], write);
    await press();
    expect(window.location.href).toBe(before);
    expect(fetchMock).not.toHaveBeenCalled();
    expect([log, warn, error].every((spy) => spy.mock.calls.length === 0)).toBe(true);
    expect(link()!.getAttribute('href')).toBeNull();
  });
});
