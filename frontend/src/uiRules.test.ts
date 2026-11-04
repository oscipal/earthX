// UI-04 §7.5: checks that find a relapse of the rules of the guide (`docs/ui/leitfaden.md`) in the source of the interface.
// Each rule has its counter-check: the same function finds the fault in a made-up line.

import { describe, expect, it } from 'vitest';

import CSS from './index.css?raw';

const SOURCES = import.meta.glob(['./**/*.ts', './**/*.tsx', '!./**/*.test.ts', '!./**/*.test.tsx', '!./fixtures/**'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const file = (path: string) => path.replace(/^\.\//u, '');
const sources = Object.entries(SOURCES).map(([path, text]) => [file(path), text] as const);

// The code without its comments: a rule is about what the interface says and does, not about what a comment says of it.
export function withoutComments(text: string): string {
  return text.replace(/\/\*[\s\S]*?\*\//gu, '').replace(/(^|[^:'"`\\])\/\/[^\n]*/gu, '$1');
}

// What the interface can show: the text between JSX tags and every string literal.
export function texts(text: string): string[] {
  const code = withoutComments(text);
  const found: string[] = [];
  // Not after `=>` or `->`, and no code in it: an arrow and a generic are no tag.
  for (const m of code.matchAll(/(?<![=-])>([^<>{}=;]*[A-Za-z✕×✖][^<>{}=;]*)</gu)) found.push(m[1].trim());
  for (const m of code.matchAll(/'((?:[^'\\\n]|\\.)*)'|"((?:[^"\\\n]|\\.)*)"|`((?:[^`\\]|\\.)*)`/gu)) found.push(m[1] ?? m[2] ?? m[3]);
  return found.filter((t) => t.length > 0);
}

// The styles without their comments, for the same reason.
const withoutCssComments = (css: string) => css.replace(/\/\*[\s\S]*?\*\//gu, '');

const where = (test: (code: string) => boolean) => sources.filter(([, text]) => test(withoutComments(text))).map(([path]) => path).sort();

describe('closing (§7.5 no. 1): one way, the red x of CloseButton', () => {
  // A class it draws with (not one a selector looks for) or the name of the button.
  const CLOSE_X = /className=[{"'`][^>\n]*\bclose-x\b|aria-label="Close"|aria-label=\{'Close'\}/u;
  // What stands where a close would: the glyphs of an x as the content of a button, and the old name of the x of a message.
  const X_GLYPH = />\s*[✕×✖]\s*</u;

  it('draws the red x and names "Close" only in CloseButton', () => {
    expect(where((code) => CLOSE_X.test(code))).toEqual(['components/CloseButton.tsx']);
    expect(CLOSE_X.test('<button className="close-x" />')).toBe(true);
    expect(CLOSE_X.test("el.querySelector('button:not(.close-x)')")).toBe(false);
  });

  it('has no "Dismiss"', () => {
    expect(where((code) => /\bDismiss\b/u.test(code))).toEqual([]);
    expect(/\bDismiss\b/u.test('aria-label="Dismiss"')).toBe(true);
  });

  it('has no x character as the content of a button: removing and emptying have their own icons', () => {
    expect(where((code) => X_GLYPH.test(code))).toEqual([]);
    expect(X_GLYPH.test('<button type="button">\n  ✕\n</button>')).toBe(true);
    expect(X_GLYPH.test('<span>10 m × 10 m</span>')).toBe(false);
  });
});

describe('icons (§7.5 no. 3): one source, no character of the text for an icon', () => {
  // The characters that stood for an icon: download, pencil, close, gear, plus, more, carets, triangles, retry, restore, upload, swap, (i),
  // warning, tick, play and pause, zoom, sun and moon, back and forth, and the arrows of the keys. Left to the text: "…", "—", "·", "–", "→"
  // between two dates, "×" in a size, "µ".
  const SYMBOL = /[⇩⇊⬆⬇✎✏✕✖✗✓✔⚙＋⋯⋮▾▴▸◂▼▲▶❚↻↺⟳⤒⤓⤢⇄ⓘⓧ⚠☀☾‹›⏵⏸↑↓←🗑]/u;
  const IMPORT_LUCIDE = /from\s+['"]lucide-react['"]/u;
  // The line of a drawing: only the chart of a histogram is one; every icon is one of `icons.ts`.
  const OWN_SVG = /<svg\b/u;

  it('has no such character in the code of the interface (a comment may name one)', () => {
    expect(where((code) => SYMBOL.test(code))).toEqual([]);
    for (const glyph of ['⇩', '✎', '＋', '⋯', '▾', '↻', '⚠', '✓', '▶']) expect(SYMBOL.test(`<button>${glyph} Download</button>`)).toBe(true);
    for (const kept of ['10 m × 10 m', 'a … b', '— none —', '2026-01-01 → 2026-02-01', 'µm', 'a · b', '3–5']) expect(SYMBOL.test(kept)).toBe(false);
    expect(SYMBOL.test(withoutComments('// the ⇩ of a layer\nconst a = 1;'))).toBe(false);
  });

  it('has no such character in the styles (a tick of a menu is an icon, not a `content`)', () => {
    expect(SYMBOL.test(withoutCssComments(CSS))).toBe(false);
    expect(SYMBOL.test("content: '✓';")).toBe(true);
  });

  it('imports lucide-react only in icons.ts', () => {
    expect(where((code) => IMPORT_LUCIDE.test(code))).toEqual(['components/icons.ts']);
    expect(IMPORT_LUCIDE.test("import { Eye } from 'lucide-react';")).toBe(true);
    expect(IMPORT_LUCIDE.test("import { Eye } from './icons';")).toBe(false);
  });

  it('draws no icon of its own: the only svg is the chart of the histogram', () => {
    expect(where((code) => OWN_SVG.test(code))).toEqual(['components/RangeHistogram.tsx']);
    expect(OWN_SVG.test('<svg viewBox="0 0 24 24"><path d="M0 0" /></svg>')).toBe(true);
    expect(OWN_SVG.test('<DownloadIcon />')).toBe(false);
  });
});

describe('Esc (§7.5 no. 2): closes nothing', () => {
  // The exceptions (Otto, 02.11.2026, and UI-04 §7.0 no. 2): Cancel in a question, the end of "Flip through layers"; and two that close
  // nothing either: Esc drops a rename and a row that is being dragged.
  const ALLOWED = ['components/AppRail.tsx', 'components/InlineRename.tsx', 'components/LayerManager.tsx', 'components/ResamplingDialog.tsx', 'components/useRowDrag.ts'];
  it('is read only by the exceptions', () => {
    expect(where((code) => /['"]Escape['"]|['"]Esc['"]/u.test(code))).toEqual(ALLOWED);
    expect(/['"]Escape['"]/u.test("if (event.key === 'Escape') close();")).toBe(true);
  });
});

describe('no unit at "Scale" (§7.5 no. 6, Otto, 03.11.2026)', () => {
  const SCALE = ['components/RenderFields.tsx', 'components/ScaleHistograms.tsx', 'components/RangeHistogram.tsx', 'components/ViewerControls.tsx', 'components/ResultControls.tsx', 'components/ProcessingPanel.tsx'];
  // The unit of the data as the range once showed it: an element of its own, or the unit of a measure put beside the fields.
  const UNIT = /pp-unit"|Unit of the range|previewUnit|measure\??\.unit\b/u;
  it('the places that set a range show no unit of the data', () => {
    const found = sources.filter(([path, text]) => SCALE.includes(path) && UNIT.test(withoutComments(text))).map(([path]) => path);
    expect(found).toEqual([]);
    expect(UNIT.test('<span className="pp-unit" aria-label="Unit of the range">{unit}</span>')).toBe(true);
  });
});

describe('one name for one thing (§7.5 no. 7, the list of terms in §7.4)', () => {
  // Each with the word the guide uses instead.
  const FORBIDDEN: [RegExp, string][] = [
    [/\bDismiss\b/u, 'Close'],
    [/\bpictures?\b/iu, 'image'],
    [/\bPin(?:ned)? (?:this|the|all|it)\b/u, 'Add … to the layers'],
    [/^Try again$/u, 'Retry'],
    [/\bAuto stretch\b/iu, 'Auto-scale'],
    [/^auto-scale$/u, 'Auto-scale'],
    [/\b\w+\(s\)/u, 'the singular or the plural, after the count'],
    [/ & /u, 'and'],
    [/\.\.\./u, '…'],
    [/\bPick (?:a|an|one|at|several|the)\b/u, 'Choose'],
    [/^Clear$/u, 'Clear AOI'],
    [/^Results \(/u, 'Search results'],
    [/^Processing jobs$/u, 'Jobs'],
    [/\b(?:Previous|Next|First|Last) step\b/u, 'time step'],
  ];
  const faults = (text: string) =>
    texts(text).flatMap((shown) => FORBIDDEN.filter(([word]) => word.test(shown)).map(([word, instead]) => `"${shown}" (${String(word)} → ${instead})`));

  it.each(sources.map(([path]) => path))('%s', (path) => {
    expect(faults(SOURCES[`./${path}`])).toEqual([]);
  });

  it.each([
    ['<button aria-label="Dismiss">', 'Close'],
    ["title: 'This picture has one band'", 'image'],
    ["title={'Pin this image into the layer manager'}", 'Add … to the layers'],
    ['<button>\n  Try again\n</button>', 'Retry'],
    ['`${n} scene(s) found`', 'the singular or the plural, after the count'],
    ["'Crop & merge to AOI'", 'and'],
    ["'Load recipe...'", '…'],
    ['<span>Clear</span>', 'Clear AOI'],
    ['<h2>Results (0/1)</h2>', 'Search results'],
    ["title=\"Previous step\"", 'time step'],
  ])('finds the old word in %j', (line, instead) => {
    expect(faults(line).join()).toContain(instead);
  });

  it('reads no comment as text', () => {
    expect(faults('// The picture of the view (an old comment)\nconst a = 1;')).toEqual([]);
    expect(faults("/* Pin this */ const b = 'x';")).toEqual([]);
  });
});

// UI-04 part 3a: the tooltip, the shapes of a button, one dimming and one focus ring.
// The opening tags of the elements (`<button …>`) of a source, with their name: the attributes are what a rule looks at.
export function openingTags(text: string): { tag: string; attributes: string }[] {
  const code = withoutComments(text);
  const found: { tag: string; attributes: string }[] = [];
  for (const start of code.matchAll(/<([a-z][a-z0-9]*)(?=[\s/>])/gu)) {
    let depth = 0;
    let quote = '';
    let at = start.index + start[0].length;
    for (; at < code.length; at += 1) {
      const c = code[at];
      if (quote) {
        if (c === '\\') at += 1;
        else if (c === quote) quote = '';
      } else if ((depth === 0 && (c === '"' || c === "'")) || (depth > 0 && (c === '"' || c === "'" || c === '`'))) quote = c;
      else if (c === '{') depth += 1;
      else if (c === '}') depth -= 1;
      else if (c === '>' && depth === 0 && code[at - 1] !== '=') break;
    }
    found.push({ tag: start[1], attributes: code.slice(start.index + start[0].length, at) });
  }
  return found;
}

// The attributes of an element at its own level, not those inside a `{…}`.
const topLevel = (attributes: string): string => {
  let depth = 0;
  let quote = '';
  let out = '';
  for (const c of attributes) {
    if (quote) {
      if (c === quote) quote = '';
    } else if (c === '"' || c === "'") quote = c;
    else if (c === '{') depth += 1;
    else if (c === '}') depth -= 1;
    else if (depth === 0) out += c;
  }
  return out;
};

describe('the one tooltip (UI-04 part 3a, Otto, 3.11.2026): data-tip, drawn by TipLayer, no title', () => {
  // `<option>` is the one place: a native list shows no tooltip of ours, so its own `title` is what the browser can draw.
  const withTitle = (text: string) => openingTags(text).filter(({ tag, attributes }) => tag !== 'option' && /(?:^|\s)title=/u.test(topLevel(attributes))).map(({ tag }) => tag);

  it('has no element with a title but an option', () => {
    expect(sources.flatMap(([path, text]) => withTitle(text).map((tag) => `${path} <${tag}>`))).toEqual([]);
    expect(withTitle('<button type="button" title="Close">x</button>')).toEqual(['button']);
    expect(withTitle('<span\n  className="a"\n  title={tip}\n>')).toEqual(['span']);
    expect(withTitle('<option value="a" title="Why">A</option>')).toEqual([]);
    expect(withTitle('<InspectorSection title="Display">')).toEqual([]);
    expect(withTitle('<button data-tip="a title=b">x</button>')).toEqual([]);
  });
});

describe('the shapes of a button (UI-04 part 3a): .btn, .btn.primary, .btn.danger, .icon-btn and .link-btn', () => {
  // The families that the four shapes replace: each had its own padding, colours, focus and dimming.
  const OLD = /(?<![\w-])(?:ghost-btn|primary-btn|lm-btn|lm-eye|vc-eye|vc-step|zoom-btn|coverage-btn|play-btn|pp-icon-btn|delete-btn|copy-btn|vc-pencil|vc-back|lm-pencil)(?![\w-])/u;

  it('has none of the old classes in the code or the styles', () => {
    expect(where((code) => OLD.test(code))).toEqual([]);
    expect(OLD.test(withoutCssComments(CSS))).toBe(false);
    expect(OLD.test('<button className="ghost-btn danger">')).toBe(true);
    expect(OLD.test('.lm-btn:hover { }')).toBe(true);
    expect(OLD.test('<span className="vc-step-text">')).toBe(false);
  });
});

describe('one dimming for a locked control (UI-04 part 3a): --disabled-opacity', () => {
  // The rules of a locked control, or of a locked row: whatever dimming they use must be the token.
  const lockedRules = (css: string) =>
    [...withoutCssComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/gu)]
      .filter(([, selector]) => /:disabled|\[aria-disabled|\.locked|\.disabled/u.test(selector))
      // A rule may take the dimming away (`opacity: 1`, the box of the one dataset) or use the token; no other number.
      .filter(([, , body]) => /(?:^|;|\s)opacity:/u.test(body) && !/opacity:\s*(?:var\(--disabled-opacity\)|1)\s*(?:;|$)/u.test(body))
      .map(([, selector]) => selector.trim());

  it('has no hard opacity in a rule of a locked control', () => {
    expect(lockedRules(CSS)).toEqual([]);
    expect(lockedRules('.x:disabled { opacity: 0.45; }')).toEqual(['.x:disabled']);
    expect(lockedRules(".y[aria-disabled='true'] { cursor: x; opacity: 0.3 }")).toHaveLength(1);
    expect(lockedRules('.x:disabled { opacity: var(--disabled-opacity); }')).toEqual([]);
    expect(lockedRules('.z { opacity: 0.45; }')).toEqual([]);
    expect(lockedRules('.x:disabled { opacity: 1; }')).toEqual([]);
  });

  it('dims locked controls in one rule, for the disabled attribute and aria-disabled', () => {
    expect(withoutCssComments(CSS)).toMatch(/:disabled,\s*:is\([^)]*\)\[aria-disabled='true'\] \{\s*opacity: var\(--disabled-opacity\);/u);
  });
});

describe('one focus ring (UI-04 part 3a): the token --focus, for everything that can be operated', () => {
  // The rules that set an outline: the ring for all, and what draws a ring of its own on purpose.
  const outlines = (css: string) =>
    [...withoutCssComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/gu)].filter(([, , body]) => /(?:^|;|\s)outline(?:-[a-z]+)?:/u.test(body)).map(([, selector]) => selector.trim().replace(/\s+/gu, ' '));
  const ALLOWED = [
    // The ring for all controls.
    ":is(a[href], button, input, select, textarea, summary, [role='button'], [role='menuitem'], [role='menuitemradio'], [tabindex]):focus-visible",
    // A slider that draws its ring on its thumb, and the container of a pop-up that is not an operated control.
    ".inspector .range-hist input[type='range']:focus-visible",
    '.popover:focus-within',
    // The dashed line where a row is dropped.
    '.pm-group.drop',
  ];

  it('has no ring of its own for a button, a link or a field', () => {
    const found = outlines(CSS).filter((selector) => !ALLOWED.some((allowed) => selector.startsWith(allowed)));
    expect(found).toEqual([]);
    expect(outlines('.x:focus-visible { outline: 1px solid red; }')).toEqual(['.x:focus-visible']);
    expect(outlines('.y:hover { outline: none; }')).toEqual(['.y:hover']);
    expect(outlines('.z { color: red; }')).toEqual([]);
  });

  it('draws the one ring with the token', () => {
    expect(withoutCssComments(CSS)).toMatch(/\[tabindex\]\):focus-visible \{\s*outline: 2px solid var\(--focus\);/u);
  });
});
