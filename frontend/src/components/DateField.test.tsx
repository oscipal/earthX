// @vitest-environment jsdom
// UI-12 (8): a date field writes and takes the day as "2026-12-03" whatever the language of the browser, with a calendar of its own in
// English that offers only the days of its bounds.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { DateField } from './DateField';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;
let value: string;
const onChange = vi.fn((v: string) => {
  value = v;
});

const BOUNDS = { min: '2014-10-03', max: '2021-12-23' };
const render = (bounds = BOUNDS, disabled = false) =>
  act(() => root.render(<DateField value={value} onChange={onChange} label="From date" bounds={bounds} disabled={disabled} lockReason="No time axis" />));
const input = () => container.querySelector<HTMLInputElement>('.date-field input')!;
const type = (text: string) =>
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(input(), text);
    input().dispatchEvent(new Event('input', { bubbles: true }));
  });
const leave = () => act(() => input().dispatchEvent(new FocusEvent('focusout', { bubbles: true })));
const calendar = () => document.querySelector<HTMLElement>('.day-calendar');
const openCalendar = () => act(() => container.querySelector<HTMLButtonElement>('.date-icon-btn')!.click());

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  value = '2020-03-15';
  onChange.mockClear();
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('a date field', () => {
  it('is a text field with the day as "YYYY-MM-DD", not the date field of the browser', () => {
    render();
    expect(input().type).toBe('text');
    expect(input().value).toBe('2020-03-15');
    expect(input().placeholder).toBe('YYYY-MM-DD');
    expect(input().getAttribute('autocomplete')).toBe('off');
    expect([input().min, input().max]).toEqual(['2014-10-03', '2021-12-23']);
  });

  it('takes a whole day as it is typed, and nothing in between', () => {
    render();
    type('2019-0');
    expect(onChange).not.toHaveBeenCalled();
    type('2019-07-04');
    expect(onChange).toHaveBeenLastCalledWith('2019-07-04');
  });

  it.each(['04.07.2019', '07/04/2019', '2019-02-30', 'yesterday'])('goes back to the last day when "%s" is left in it', (text) => {
    render();
    type(text);
    leave();
    expect(onChange).not.toHaveBeenCalled();
    expect(input().value).toBe('2020-03-15');
  });

  it('moves a day outside its bounds onto the nearest one when it is left', () => {
    render();
    type('2001-01-01');
    leave();
    expect(onChange).toHaveBeenLastCalledWith('2014-10-03');
    expect(input().value).toBe('2014-10-03');
  });

  it('can be emptied', () => {
    render();
    type('');
    leave();
    expect(onChange).toHaveBeenLastCalledWith('');
  });

  it('when locked, locks its calendar too and names the reason', () => {
    render(BOUNDS, true);
    expect(input().disabled).toBe(true);
    expect(input().getAttribute('data-tip')).toBe('No time axis');
    expect(container.querySelector<HTMLButtonElement>('.date-icon-btn')!.disabled).toBe(true);
  });
});

describe('its calendar', () => {
  it('opens on the month of the day, in English, Monday first, with the day pressed', () => {
    render();
    openCalendar();
    expect(calendar()!.querySelector('.day-calendar-month')?.textContent).toBe('March 2020');
    expect([...calendar()!.querySelectorAll('.day-calendar-weekday')].map((h) => h.textContent)).toEqual(['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']);
    expect(calendar()!.querySelector('[aria-pressed="true"]')?.getAttribute('aria-label')).toBe('2020-03-15');
  });

  it('chooses a day with a click and closes', () => {
    render();
    openCalendar();
    act(() => calendar()!.querySelector<HTMLButtonElement>('[aria-label="2020-03-20"]')!.click());
    expect(onChange).toHaveBeenLastCalledWith('2020-03-20');
    expect(calendar()).toBeNull();
  });

  it('offers no day and no month outside the bounds', () => {
    value = '2014-10-10';
    render();
    openCalendar();
    expect(calendar()!.querySelector<HTMLButtonElement>('[aria-label="2014-10-02"]')!.disabled).toBe(true);
    expect(calendar()!.querySelector<HTMLButtonElement>('[aria-label="2014-10-03"]')!.disabled).toBe(false);
    const previous = calendar()!.querySelector<HTMLButtonElement>('[aria-label="Previous month"]')!;
    expect(previous.getAttribute('aria-disabled')).toBe('true');
    act(() => previous.click());
    expect(calendar()!.querySelector('.day-calendar-month')?.textContent).toBe('October 2014');
    act(() => calendar()!.querySelector<HTMLButtonElement>('[aria-label="Next month"]')!.click());
    expect(calendar()!.querySelector('.day-calendar-month')?.textContent).toBe('November 2014');
  });
});
