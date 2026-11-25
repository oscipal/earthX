// UI-04 part 6, backlog item 58: the rules of the narrow window that a browser script (`e2e/narrow-windows.cjs`, `e2e/range-layout.cjs`)
// proves in a real browser, held here as rules of the sheet so that a relapse shows in the unit tests too. Each has its counter-check.

import { describe, expect, it } from 'vitest';

import index from './index.css?raw';
import tokens from './tokens.css?raw';

const withoutComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//gu, '');
const css = withoutComments(index);

// The declarations of the first rule whose selector is exactly `selector`, outside any media query when `inMedia` is not given.
export function ruleOf(sheet: string, selector: string, inMedia?: string): string {
  const scope = inMedia ? (sheet.slice(sheet.indexOf(inMedia)).match(/^[^{]*\{([\s\S]*?\n\})/u)?.[1] ?? '') : sheet;
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');
  return new RegExp(`(?:^|\\n)\\s*${escaped}\\s*\\{([^}]*)\\}`, 'u').exec(scope)?.[1] ?? '';
}

const zIndex = (sheet: string, selector: string): number => Number(/z-index:\s*(\d+)/u.exec(ruleOf(sheet, selector))?.[1] ?? Number.NaN);

// UI-12 (3), F1 and F2 (replaces the message over the panels of a narrow window, backlog item 58): the status is a line at the foot of the
// window, the same in every window. The app ends above it, so no panel covers it and it covers none.
describe('the status line', () => {
  it('stands at the foot right of the rail, one control high, in every window', () => {
    const rule = ruleOf(css, '.overlay.status');
    for (const part of ['position: fixed', 'left: var(--rail-width)', 'right: 0', 'bottom: 0', 'height: var(--status-line-height)']) expect(rule).toContain(part);
    expect(tokens).toMatch(/--status-line-height:\s*var\(--control-height\)/u);
    expect(ruleOf(css, '.overlay.status', '@media (max-width: 899px)')).toBe('');
  });

  it('has a place of its own: the app ends above it, the rail reaches down beside it', () => {
    expect(ruleOf(css, '.app')).toContain('height: calc(100vh - var(--status-line-height))');
    expect(ruleOf(css, '.app-rail')).toContain('bottom: calc(-1 * var(--status-line-height))');
    expect(zIndex(css, '.overlay.status')).toBeGreaterThan(zIndex(css, '.dock'));
    expect(zIndex(css, '.overlay.status')).toBeGreaterThan(zIndex(css, '.inspector.panel'));
  });

  it('is opaque, and cuts a long text in one row instead of growing', () => {
    expect(ruleOf(css, '.overlay.status')).toMatch(/background:\s*linear-gradient\(var\(--panel-bg\), var\(--panel-bg\)\), var\(--map-bg\)/u);
    const text = ruleOf(css, '.status-text');
    for (const part of ['white-space: nowrap', 'text-overflow: ellipsis', 'overflow: hidden']) expect(text).toContain(part);
  });
});

describe('the fields of a range in a narrow window', () => {
  const MINIMUM = 'minmax(var(--number-field-width), 1fr)';
  const FIELDS = (sheet: string, selector: string) => sheet.match(new RegExp(`${selector.replace(/[.*+?^${}()|[\]\\:]/gu, '\\$&')}[^{}]*\\{([^}]*)\\}`, 'u'))?.[1] ?? '';

  // Otto, 4.11.2026: the same number field keeps the same room wherever it stands: the settings bar of a view, a layer and a result, and
  // the preview of the processing panel.
  it.each(['.processing-panel', '.inspector'])('keep room for "-0.123456" in %s: the fields have a minimum and the switch beside them gives way', (area) => {
    const fields = css.match(new RegExp(`\\${area} \\.vc-scale-fields[^{]*\\{([^}]*)\\}`, 'u'))?.[1] ?? '';
    expect(fields).toContain(`grid-template-columns: ${MINIMUM} ${MINIMUM} minmax(0, auto)`);
  });

  it('keep it in the rows of a colour picture too', () => {
    const channels = css.match(/\.inspector \.vc-channels \{([^}]*)\}/u)?.[1] ?? '';
    expect(channels).toContain(`grid-template-columns: auto ${MINIMUM} ${MINIMUM} minmax(0, auto)`);
  });

  it('put the name "Scale" over the fields in the settings bar, which have the width of the bar then', () => {
    const name = css.match(/\.inspector \.vc-scale \{([^}]*)\}/u)?.[1] ?? '';
    expect(name).toContain('grid-template-columns: minmax(0, 1fr)');
    expect(name).not.toContain('--form-label-width');
  });

  it('do not give the room back to the content of the switch (the old rule, which cut the number)', () => {
    const OLD = /\.vc-scale-fields[^{]*\{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1fr\) auto/u;
    expect(css).not.toMatch(OLD);
    expect(css).not.toMatch(/\.vc-channels \{[^}]*grid-template-columns:\s*auto minmax\(0, 1fr\) minmax\(0, 1fr\) auto/u);
    expect(OLD.test('.inspector .vc-scale-fields { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; }')).toBe(true);
  });

  it('read a rule by its selector', () => {
    expect(FIELDS('.a .b { x: 1 } .c { y: 2 }', '.c')).toContain('y: 2');
  });
});

describe('ruleOf', () => {
  it('finds a rule by its selector, and one in a media query', () => {
    const sheet = '.a { top: 1px; }\n@media (max-width: 899px) {\n  .a {\n    top: 2px;\n  }\n}\n';
    expect(ruleOf(sheet, '.a')).toContain('top: 1px');
    expect(ruleOf(sheet, '.a', '@media (max-width: 899px)')).toContain('top: 2px');
    expect(ruleOf(sheet, '.b')).toBe('');
  });
});
