// UI-03 §7.4: the tokens exist in both themes, and the areas that use them hold no hard spacing, size or radius.

import { describe, expect, it } from 'vitest';

import { hardValues } from './cssTokens';
import index from './index.css?raw';
import tokens from './tokens.css?raw';

// The areas already moved onto the tokens; UI-04 adds the other panels here. The processing manager (UI-03c) is every `.pm-…` class of
// its rows, heads and menu; the details of a job (`.pm-detail-title`, `.pm-facts`, …) are checked with the processing panel below (UI-03b).
const MANAGER = [
  '.processing-manager',
  '.pm-head', '.pm-tools', '.pm-filter', '.pm-note', '.pm-new-group', '.pm-empty', '.pm-list',
  '.pm-group', '.pm-group-head', '.pm-group-name', '.pm-rows', '.pm-parts', '.pm-row', '.pm-line', '.pm-open', '.pm-meta',
  '.pm-state', '.pm-until', '.pm-tag', '.pm-title', '.pm-icon', '.pm-progress', '.pm-fault', '.pm-menu', '.pm-menu-list',
  '.pm-menu-items', '.pm-key', '.pm-fold', '.pm-chevron', '.pm-count', '.pm-rename',
] as const;
// The processing panel (UI-03b) is the `.processing-…` classes, every `.pp-…` class of the sheet and the details of a job in it;
// `.pp-badge` is shared with the mark of the preview on the map and waits for UI-04.
const PANEL = [
  '.processing-sheet', '.processing-panel',
  '.pm-detail-title', '.pm-title-text', '.pm-title-edit', '.pm-facts', '.pm-steps', '.pm-step-values',
  ...new Set(index.match(/\.pp-[a-z-]+/gu) ?? []),
].filter((selector) => selector !== '.pp-badge');
const CHECKED_AREAS = ['.btn', '.icon-btn', '.close-x', '.inspector', ...PANEL, ...MANAGER] as const;

const ROOT_TOKENS = [
  '--space-1', '--space-2', '--space-3', '--space-4', '--space-5', '--space-6',
  '--text-xs', '--text-sm', '--text-md', '--text-lg', '--text-xl',
  '--leading-tight', '--leading', '--weight-regular', '--weight-semibold',
  '--radius-sm', '--radius-md', '--radius-full', '--line-width',
  '--control-height', '--control-height-sm', '--control-height-touch',
  '--icon-size', '--icon-size-sm', '--icon-size-rail', '--disabled-opacity',
  '--rail-width', '--dock-width', '--inspector-width', '--sheet-wide-width',
  '--font', '--font-mono',
];
const THEME_TOKENS = [
  '--panel-bg', '--panel-border', '--accent', '--accent-2', '--text', '--muted', '--input-bg', '--glow', '--row-hover', '--map-bg',
  '--line', '--line-soft', '--surface-2', '--danger', '--focus', '--on-accent', '--channel-red', '--channel-green', '--channel-blue',
];

// The declarations of the first block that opens with `selector {`.
function block(css: string, selector: string): string {
  const start = css.indexOf(`${selector} {`);
  if (start < 0) return '';
  return css.slice(start, css.indexOf('}', start));
}

describe('tokens.css', () => {
  it.each(ROOT_TOKENS)('defines %s in :root', (name) => {
    expect(block(tokens, ':root')).toMatch(new RegExp(`\\s${name}:\\s*\\S`, 'u'));
  });

  it.each(['tech', 'normal'])('defines every colour token in the %s theme', (theme) => {
    const body = block(tokens, `.app[data-theme='${theme}']`);
    for (const name of THEME_TOKENS) expect(body, name).toMatch(new RegExp(`\\s${name}:\\s*\\S`, 'u'));
  });

  it('holds the values of the plan', () => {
    const root = block(tokens, ':root');
    expect(root).toContain('--space-3: 12px');
    expect(root).toContain('--text-xs: 11px');
    expect(root).toContain('--control-height: 28px');
    expect(root).toContain('--sheet-wide-width: clamp(520px, 34vw, 640px)');
  });

  // Otto, 2.11.2026: on a touch screen and under 900 px a control is 40–44 px high, from a token of its own.
  it('makes every control as high as the touch token on a touch screen and under 900 px', () => {
    const touch = Number(/--control-height-touch:\s*(\d+)px/u.exec(block(tokens, ':root'))?.[1]);
    expect(touch).toBeGreaterThanOrEqual(40);
    expect(touch).toBeLessThanOrEqual(44);
    const media = /@media \(pointer: coarse\), \(max-width: 899px\) \{\s*:root \{([^}]*)\}/u.exec(tokens);
    expect(media?.[1]).toContain('--control-height: var(--control-height-touch)');
    // Nothing else sets the height for touch: the plain value stays the one of a mouse.
    expect(block(tokens, ':root')).toContain('--control-height: 28px');
    expect(tokens.match(/--control-height:/gu)).toHaveLength(2);
    expect(index).not.toMatch(/--control-height(?:-touch)?:/u);
  });

  it('is the only place of the theme blocks, the rail width and the families', () => {
    expect(index).not.toMatch(/^\.app\[data-theme='(?:tech|normal)'\] \{[^}]*--panel-bg/mu);
    expect(index).not.toMatch(/--(?:rail|dock)-width:/u);
    expect(index).not.toMatch(/var\(--(?:mono|sans)\)/u);
  });

  it('keeps the monospace family for code only', () => {
    const uses = index.split('\n').filter((line) => line.includes('var(--font-mono)'));
    expect(uses).toHaveLength(1);
    expect(block(index, '.pp-field textarea')).toContain('var(--font-mono)');
  });
});

describe('hard values in the checked areas of index.css', () => {
  it('finds none in the shared controls, the settings bar, the processing panel and the processing manager', () => {
    expect(hardValues(index, CHECKED_AREAS)).toEqual([]);
  });

  it('sets the close cross in one colour token for both themes', () => {
    expect(block(index, '.close-x')).toContain('color: var(--danger)');
    expect(index).not.toMatch(/\.app\[data-theme='normal'\] \.close-x/u);
  });
});

describe('hardValues', () => {
  const areas = ['.btn'];

  it('reports one hard padding and nothing else', () => {
    expect(hardValues('.btn { padding: 5px }', areas)).toEqual(['.btn { padding: 5px }']);
  });

  it('ignores tokens, zero and other units', () => {
    const css = '.btn { padding: var(--space-2); margin: 0; gap: 0px; font-size: 1em; border-radius: 50%; width: 20px; }';
    expect(hardValues(css, areas)).toEqual([]);
  });

  it('reports a hard length next to a token', () => {
    expect(hardValues('.btn { padding: 4px var(--space-2) }', areas)).toHaveLength(1);
    expect(hardValues('.btn { margin: -2px }', areas)).toHaveLength(1);
    expect(hardValues('.btn { font-size: 0.75rem }', areas)).toHaveLength(1);
    expect(hardValues('.btn { padding-left: 3px !important }', areas)).toHaveLength(1);
  });

  it('lets a calculation with a token pass, not one without', () => {
    expect(hardValues('.btn { padding: calc(var(--space-2) + 2px) }', areas)).toEqual([]);
    expect(hardValues('.btn { padding: calc(4px + 2px) }', areas)).toHaveLength(1);
  });

  it('reads every checked property and its longhands', () => {
    const css = '.btn { margin-top: 1px; row-gap: 2px; border-top-left-radius: 3px; border-radius: 4px; }';
    expect(hardValues(css, areas)).toHaveLength(4);
  });

  it('ignores a hard value in a comment', () => {
    expect(hardValues('/* .btn { padding: 5px } */ .btn { /* padding: 6px; */ color: red }', areas)).toEqual([]);
  });

  it('reads each selector of a list and the rules in a media query', () => {
    expect(hardValues('.a, .btn:hover, .b { gap: 3px }', areas)).toEqual(['.btn:hover { gap: 3px }']);
    expect(hardValues('.a, .b { gap: 3px }', areas)).toEqual([]);
    expect(hardValues('@media (max-width: 900px) { .btn { padding: 5px } .other { padding: 5px } }', areas)).toHaveLength(1);
    expect(hardValues('@media (max-width: 900px) { .btn { padding: var(--space-1) } }', areas)).toEqual([]);
  });

  it('matches a whole class name at the start of a selector', () => {
    expect(hardValues('.ghost-btnx { padding: 5px }', areas)).toEqual([]);
    expect(hardValues('.load-more .btn { padding: 5px }', areas)).toEqual([]);
    expect(hardValues('.btn.danger { padding: 5px }', areas)).toHaveLength(1);
    expect(hardValues('.btn[aria-disabled="true"] { padding: 5px }', areas)).toHaveLength(1);
  });

  it('survives a comma or a semicolon inside a string or a URL, and a missing last semicolon', () => {
    const css = ".a[data-x='1,2'], .btn { background: url(\"data:image/svg+xml;utf8,<svg/>\"); padding: 2px }";
    expect(hardValues(css, areas)).toHaveLength(1);
  });

  it('copes with empty and broken input', () => {
    expect(hardValues('', areas)).toEqual([]);
    expect(hardValues('} } .btn { padding: 2px', areas)).toHaveLength(1);
    expect(hardValues('.btn { padding: 2px }', [])).toEqual([]);
  });
});
