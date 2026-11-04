// UI-04 part 6, backlog item 58: the rules of the narrow window that a browser script (`e2e/narrow-windows.cjs`, `e2e/range-layout.cjs`)
// proves in a real browser, held here as rules of the sheet so that a relapse shows in the unit tests too. Each has its counter-check.

import { describe, expect, it } from 'vitest';

import index from './index.css?raw';

const withoutComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//gu, '');
const css = withoutComments(index);

// The declarations of the first rule whose selector is exactly `selector`, outside any media query when `inMedia` is not given.
export function ruleOf(sheet: string, selector: string, inMedia?: string): string {
  const scope = inMedia ? (sheet.slice(sheet.indexOf(inMedia)).match(/^[^{]*\{([\s\S]*?\n\})/u)?.[1] ?? '') : sheet;
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&');
  return new RegExp(`(?:^|\\n)\\s*${escaped}\\s*\\{([^}]*)\\}`, 'u').exec(scope)?.[1] ?? '';
}

const zIndex = (sheet: string, selector: string): number => Number(/z-index:\s*(\d+)/u.exec(ruleOf(sheet, selector))?.[1] ?? Number.NaN);

describe('the message of the status bar in a narrow window', () => {
  it('lies over the panel of the rail, the settings bar and the sheet, and under the rail', () => {
    const status = zIndex(css, '.status');
    expect(status).toBeGreaterThan(zIndex(css, '.dock'));
    expect(status).toBeGreaterThan(zIndex(css, '.inspector.panel'));
    expect(status).toBeLessThan(zIndex(css, '.app-rail'));
  });

  it('stands under the buttons at the top right below 900 px, one control high and one gap below them', () => {
    const top = ruleOf(css, '.overlay.status', '@media (max-width: 899px)');
    expect(top).toContain('top: calc(var(--space-4) + var(--control-height) + var(--space-2))');
    // The wide window keeps its place at the top.
    expect(ruleOf(css, '.status')).toContain('top: 16px');
  });

  it('is opaque: a message over a panel does not show the panel through', () => {
    expect(ruleOf(css, '.toast')).toMatch(/background:\s*linear-gradient\(var\(--panel-bg\), var\(--panel-bg\)\), var\(--map-bg\)/u);
  });

  it('is no wider than the map right of the rail', () => {
    expect(ruleOf(css, '.status')).toContain('width: min(560px, calc(100vw - var(--rail-width) - 16px))');
  });
});

describe('the fields of a range in a narrow window', () => {
  const MINIMUM = 'minmax(var(--number-field-width), 1fr)';

  it('keep room for "-0.123456": the fields have a minimum and the switch beside them gives way', () => {
    const fields = css.match(/\.inspector \.vc-scale-fields \{([^}]*)\}/u)?.[1] ?? '';
    expect(fields).toContain(`grid-template-columns: ${MINIMUM} ${MINIMUM} minmax(0, auto)`);
    const channels = css.match(/\.inspector \.vc-channels \{([^}]*)\}/u)?.[1] ?? '';
    expect(channels).toContain(`grid-template-columns: auto ${MINIMUM} ${MINIMUM} minmax(0, auto)`);
  });

  it('do not give the room back to the content of the switch (the old rule, which cut the number)', () => {
    const OLD = /\.vc-scale-fields \{[^}]*grid-template-columns:\s*minmax\(0, 1fr\) minmax\(0, 1fr\) auto/u;
    expect(css).not.toMatch(OLD);
    expect(OLD.test('.inspector .vc-scale-fields { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto; }')).toBe(true);
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
