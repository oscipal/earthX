// @vitest-environment jsdom
//
// The two steps of the tooltips (UI-04 part 3b, Otto, 4.11.2026).

import { describe, expect, it } from 'vitest';

import { currentTipLevel, DEFAULT_TIP_LEVEL, isCut, setTipLevel, tipShown, TIP_LEVELS } from './tipLevel';

const element = (html: string): Element => {
  const holder = document.createElement('div');
  holder.innerHTML = html;
  return holder.firstElementChild as Element;
};

describe('tipShown', () => {
  it('shows every tip in the advanced step', () => {
    expect(tipShown(element('<span data-tip="x" data-tip-level="advanced"></span>'), 'advanced')).toBe(true);
    expect(tipShown(element('<span data-tip="x"></span>'), 'advanced')).toBe(true);
  });

  it('shows in the simple step only the tips without a step, and holds back an advanced one', () => {
    expect(tipShown(element('<span data-tip="x"></span>'), 'simple')).toBe(true);
    expect(tipShown(element('<span data-tip="x" data-tip-level="advanced"></span>'), 'simple')).toBe(false);
  });

  it('shows the reason of a locked control in the simple step, whatever step its tip carries (a)', () => {
    expect(tipShown(element('<button disabled data-tip="Why" data-tip-level="advanced"></button>'), 'simple')).toBe(true);
    expect(tipShown(element('<button aria-disabled="true" data-tip="Why" data-tip-level="advanced"></button>'), 'simple')).toBe(true);
    expect(tipShown(element('<button aria-disabled="false" data-tip="Why" data-tip-level="advanced"></button>'), 'simple')).toBe(false);
    expect(tipShown(element('<button data-tip="What it does" data-tip-level="advanced"></button>'), 'simple')).toBe(false);
  });

  it('knows two steps, and starts in the simple one (Otto, 4.11.2026), which the setting changes', () => {
    expect(TIP_LEVELS).toEqual(['simple', 'advanced']);
    expect(DEFAULT_TIP_LEVEL).toBe('simple');
    expect(currentTipLevel()).toBe('simple');
    setTipLevel('advanced');
    expect(currentTipLevel()).toBe('advanced');
    setTipLevel('simple');
    expect(currentTipLevel()).toBe('simple');
  });
});

// jsdom does not lay anything out: the sizes are set by hand, as a browser would measure them.
const measured = (html: string, sizes: { scrollWidth: number; clientWidth: number }, inner?: { scrollWidth: number; clientWidth: number }): Element => {
  const el = element(html);
  Object.defineProperties(el, { scrollWidth: { value: sizes.scrollWidth }, clientWidth: { value: sizes.clientWidth } });
  const child = el.querySelector('.cut');
  if (child && inner) Object.defineProperties(child, { scrollWidth: { value: inner.scrollWidth }, clientWidth: { value: inner.clientWidth } });
  return el;
};

describe('a tip with the full text of a cut-off text (UI-04 part 4, Otto, 4.11.2026)', () => {
  it('shows only while the text is cut: wider than its box (scrollWidth over clientWidth)', () => {
    expect(isCut(measured('<span data-tip="Name" data-tip-cut></span>', { scrollWidth: 140, clientWidth: 100 }))).toBe(true);
    expect(isCut(measured('<span data-tip="Name" data-tip-cut></span>', { scrollWidth: 100, clientWidth: 100 }))).toBe(false);
    expect(isCut(measured('<span data-tip="Name" data-tip-cut></span>', { scrollWidth: 60, clientWidth: 100 }))).toBe(false);
  });

  it.each(['simple', 'advanced'] as const)('holds the same in the %s step: shown when cut, not shown when whole', (level) => {
    expect(tipShown(measured('<span data-tip="Name" data-tip-cut></span>', { scrollWidth: 140, clientWidth: 100 }), level)).toBe(true);
    expect(tipShown(measured('<span data-tip="Name" data-tip-cut></span>', { scrollWidth: 100, clientWidth: 100 }), level)).toBe(false);
  });

  it('measures the element that the attribute names, where the tip sits on a button around a cut span', () => {
    const cut = { scrollWidth: 200, clientWidth: 120 };
    const whole = { scrollWidth: 120, clientWidth: 120 };
    const button = (box: { scrollWidth: number; clientWidth: number }, inner: { scrollWidth: number; clientWidth: number }) =>
      measured('<button data-tip="Job title" data-tip-cut=".cut"><span class="cut">Job title</span></button>', box, inner);
    // The button itself is not wider than its content, so only the span says.
    expect(tipShown(button(whole, cut), 'simple')).toBe(true);
    expect(tipShown(button(cut, whole), 'simple')).toBe(false);
  });

  it('is not shown when the element to measure is not there', () => {
    expect(tipShown(measured('<button data-tip="x" data-tip-cut=".gone"></button>', { scrollWidth: 200, clientWidth: 100 }), 'advanced')).toBe(false);
  });

  it('is not in the way of the other tips: without the attribute a wide element shows by its step', () => {
    expect(tipShown(measured('<span data-tip="x" data-tip-level="advanced"></span>', { scrollWidth: 50, clientWidth: 500 }), 'advanced')).toBe(true);
    expect(tipShown(measured('<span data-tip="x"></span>', { scrollWidth: 50, clientWidth: 500 }), 'simple')).toBe(true);
  });
});
