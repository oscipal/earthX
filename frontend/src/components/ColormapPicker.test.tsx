// @vitest-environment jsdom
//
// Colormaps (UI-03d, Otto, 2.11.2026): the field offers a few and "More…"; "More…" opens all of them in a bar of their own at the right
// edge, by group, with a preview, a search and "Reverse"; a click chooses and goes back, "‹" goes back without a choice, Esc closes
// nothing; "Reverse" beside the field turns the scale round as the tiler's `_r`. The list comes from the tiler.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { baseOf, forgetColormaps, gradientOf, parseColormaps, shortList, withReverse } from '../colormaps';
import { useColormapPicker } from '../colormapPicker';
import { parseView, viewOf } from '../permalink';
import ColormapField from './ColormapField';
import ColormapPicker from './ColormapPicker';
import { tipOf } from '../fixtures/tips';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

const LOOK = { basemap: 'satellite', projection: 'mercator' } as const;
const entry = (name: string, colors = ['#000000', '#ffffff']) => ({ name, reversed: `${name}_r`, colors });
const LIST = {
  groups: [
    { name: 'sequential', colormaps: [entry('viridis', ['#440154', '#fde724']), entry('magma'), entry('rocket'), entry('gray')] },
    { name: 'diverging', colormaps: [entry('rdylgn'), entry('rdbu')] },
    { name: 'other', colormaps: [entry('terrain'), entry('jet')] },
  ],
};

let container: HTMLDivElement;
let root: Root;
let value = '';
const fetchMock = vi.fn(async (url: string) => (url.endsWith('/colormaps') ? new Response(JSON.stringify(LIST), { status: 200 }) : new Response('{}', { status: 404 })));

function mount() {
  act(() =>
    root.render(
      <>
        <ColormapField value={value} onChange={(name) => ((value = name), mount())} />
        <ColormapPicker />
      </>,
    ),
  );
}

const settle = () => act(async () => { for (let i = 0; i < 5; i++) await Promise.resolve(); });
const select = () => container.querySelector<HTMLSelectElement>('.vc-colormap select')!;
const reverse = () => container.querySelector<HTMLButtonElement>('.vc-colormap .vc-reverse')!;
const picker = () => container.querySelector<HTMLElement>('aside.colormap-picker');
const items = () => [...container.querySelectorAll<HTMLButtonElement>('.cm-item')];
const choose = (text: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')!.set!.call(select(), [...select().options].find((o) => o.textContent === text)!.value);
    select().dispatchEvent(new Event('change', { bubbles: true }));
  });

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  forgetColormaps();
  fetchMock.mockClear();
  vi.stubGlobal('fetch', fetchMock);
  value = 'viridis';
  act(() => useColormapPicker.setState({ request: null }));
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe('the field "Colormap"', () => {
  it('offers "none", a few colormaps the tiler has, and "More…" last', async () => {
    mount();
    await settle();
    expect([...select().options].map((o) => o.textContent)).toEqual(['— none —', 'gray', 'viridis', 'magma', 'rdylgn', 'rdbu', 'terrain', 'More…']);
    expect(fetchMock.mock.calls.filter(([u]) => String(u).endsWith('/colormaps'))).toHaveLength(1);
  });

  it('leaves out a colormap of the few the tiler does not have', () => {
    const groups = parseColormaps({ groups: [{ name: 'sequential', colormaps: [entry('viridis')] }] });
    expect(shortList(groups, '')).toEqual(['viridis']);
    // Counter-check: before the list is in, the few are offered as they are.
    expect(shortList(null, '')).toEqual(['gray', 'viridis', 'magma', 'rdylgn', 'rdbu', 'terrain']);
  });

  it('shows a colormap chosen from the whole list in the dropdown while it is chosen', async () => {
    value = 'rocket_r';
    mount();
    await settle();
    expect(select().value).toBe('rocket');
    expect([...select().options].map((o) => o.textContent)).toContain('rocket');
    value = 'magma';
    mount();
    expect([...select().options].map((o) => o.textContent)).not.toContain('rocket');
  });

  it('reverses the colormap with "Reverse", shows it on, and keeps it when another colormap is chosen', async () => {
    mount();
    await settle();
    expect(reverse().getAttribute('aria-pressed')).toBe('false');
    act(() => reverse().click());
    expect(value).toBe('viridis_r');
    expect(reverse().getAttribute('aria-pressed')).toBe('true');
    choose('magma');
    expect(value).toBe('magma_r');
    act(() => reverse().click());
    expect(value).toBe('magma');
  });

  it('locks "Reverse" while no colormap is chosen, and says why', () => {
    value = '';
    mount();
    expect(reverse().disabled).toBe(true);
    expect(tipOf(reverse())).toBe('Choose a colormap to reverse');
  });
});

describe('"More…" and the list of all colormaps', () => {
  it('opens a bar of its own with every colormap by group, each with its preview', async () => {
    mount();
    await settle();
    choose('More…');
    await settle();
    expect(picker()).not.toBeNull();
    expect(value).toBe('viridis'); // nothing chosen yet
    expect([...picker()!.querySelectorAll('.insp-heading')].map((h) => h.textContent)).toEqual(['Sequential', 'Diverging', 'Other']);
    expect(items().map((b) => b.textContent)).toEqual(['viridis', 'magma', 'rocket', 'gray', 'rdylgn', 'rdbu', 'terrain', 'jet']);
    expect(items()[0].getAttribute('aria-pressed')).toBe('true');
    expect(items()[0].querySelector<HTMLElement>('.cm-strip')!.style.background).toContain('linear-gradient');
  });

  it('chooses with a click and goes back; the choice stands in the field', async () => {
    mount();
    await settle();
    choose('More…');
    await settle();
    act(() => items().find((b) => b.textContent === 'jet')!.click());
    expect(value).toBe('jet');
    expect(picker()).toBeNull();
    expect(select().value).toBe('jet');
  });

  it('finds by name, and chooses reversed with its "Reverse", which starts as the field is', async () => {
    value = 'viridis_r';
    mount();
    await settle();
    choose('More…');
    await settle();
    const own = picker()!.querySelector<HTMLButtonElement>('.vc-reverse')!;
    expect(own.getAttribute('aria-pressed')).toBe('true');
    const search = picker()!.querySelector<HTMLInputElement>('input[type="search"]')!;
    act(() => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(search, 'rd');
      search.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(items().map((b) => b.textContent)).toEqual(['rdylgn', 'rdbu']);
    act(() => items()[1].click());
    expect(value).toBe('rdbu_r');
  });

  it('goes back with "‹" and chooses nothing; Esc closes nothing', async () => {
    mount();
    await settle();
    choose('More…');
    await settle();
    act(() => void picker()!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    act(() => void document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    expect(picker()).not.toBeNull();
    const back = picker()!.querySelector<HTMLButtonElement>('button[aria-label="Back"]')!;
    expect(tipOf(back)).toBe('Back');
    expect(picker()!.querySelector('.close-x')).toBeNull();
    act(() => back.click());
    expect(picker()).toBeNull();
    expect(value).toBe('viridis');
  });

  it('says so where the tiler gives no list, and offers the few all the same', async () => {
    fetchMock.mockImplementation(async () => new Response('{}', { status: 503 }));
    mount();
    await settle();
    expect([...select().options].map((o) => o.textContent)).toEqual(['— none —', 'gray', 'viridis', 'magma', 'rdylgn', 'rdbu', 'terrain', 'More…']);
    choose('More…');
    await settle();
    expect(picker()!.textContent).toContain('The colormaps could not be loaded.');
  });
});

describe('the helpers', () => {
  it('turn names round and back', () => {
    expect(withReverse('viridis', true)).toBe('viridis_r');
    expect(withReverse('viridis_r', true)).toBe('viridis_r');
    expect(withReverse('viridis_r', false)).toBe('viridis');
    expect(withReverse('', true)).toBe('');
    expect(baseOf('rdbu_r')).toBe('rdbu');
    expect(gradientOf(['#000000', '#ffffff'], true)).toBe('linear-gradient(to right, #ffffff, #000000)');
  });

  it('refuse a list that is none', () => {
    expect(parseColormaps(null)).toBeNull();
    expect(parseColormaps({ groups: [{ name: 'x', colormaps: [{ name: 'a', colors: ['red'] }] }] })).toBeNull();
    expect(parseColormaps({ groups: [{ name: 'x', colormaps: 'a' }] })).toBeNull();
  });

  it('carry a reversed colormap in the permalink', () => {
    const view = viewOf([10, 50, 11, 51], 9, { vmin: '0', vmax: '1', colormap: 'viridis_r' }, LOOK);
    expect(parseView(JSON.parse(JSON.stringify(view)))?.range?.colormap).toBe('viridis_r');
  });
});
