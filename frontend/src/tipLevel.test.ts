// @vitest-environment jsdom
//
// The two steps of the tooltips (UI-04 part 3b, Otto, 4.11.2026).

import { describe, expect, it } from 'vitest';

import { currentTipLevel, tipShown, TIP_LEVELS } from './tipLevel';

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

  it('knows two steps, and shows the advanced one until the setting is there', () => {
    expect(TIP_LEVELS).toEqual(['simple', 'advanced']);
    expect(currentTipLevel()).toBe('advanced');
  });
});
