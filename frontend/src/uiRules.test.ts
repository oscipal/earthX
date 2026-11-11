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

  // The needle of the compass is the second exception beside "Settings" (UI-06 F17, `docs/ui/leitfaden.md` §3).
  it('draws no icon of its own: the only svgs are the chart of the histogram and the needle of the compass', () => {
    expect(where((code) => OWN_SVG.test(code))).toEqual(['components/CompassNeedle.tsx', 'components/RangeHistogram.tsx']);
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
    [/[\d}] %/u, 'a percent close to its number ("50%")'],
    // The buttons at the bottom right of the map (UI-06).
    [/^(?:North|Reset north|Reset bearing to north)$/u, 'Reset north and tilt'],
    [/^Tilt$/u, 'Reset north and tilt'],
    [/^Terrain$/u, '3D'],
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
    ['`Loading ${n} %`', 'a percent close to its number'],
    ["'Range 2–98 %'", 'a percent close to its number'],
    ['<button aria-label="Reset bearing to north">', 'Reset north and tilt'],
    ["data-tip={'Tilt'}", 'Reset north and tilt'],
    ['<button>Terrain</button>', '3D'],
  ])('finds the old word in %j', (line, instead) => {
    expect(faults(line).join()).toContain(instead);
  });

  it('reads no comment as text', () => {
    expect(faults('// The picture of the view (an old comment)\nconst a = 1;')).toEqual([]);
    expect(faults("/* Pin this */ const b = 'x';")).toEqual([]);
  });
});

describe('numbers and dates (NM4-21, UI-04 part 6): one way to show them', () => {
  // Only `numberFormat.ts` rounds a number or writes a date for the eye. What goes into a file or a name keeps its full value and is listed
  // here with its reason.
  const FORMATTING = /\.(?:toFixed|toPrecision|toExponential|toLocaleString|toLocaleDateString|toLocaleTimeString)\(|\bIntl\.(?:NumberFormat|DateTimeFormat)\b/u;
  const KEPT = new Map([
    ['numberFormat.ts', 'the one place'],
    ['bandChoice.ts', 'the full value of a resolution and of a wavelength in file names and in BANDS.txt (`formatResolution`, `formatG`)'],
  ]);

  it('rounds and dates only in numberFormat.ts (and where a file keeps the full value)', () => {
    expect(where((code) => FORMATTING.test(code)).filter((path) => !KEPT.has(path))).toEqual([]);
    for (const line of ['value.toFixed(1)', 'x.toPrecision(4)', 'n.toExponential(2)', 'd.toLocaleDateString()', 'v.toLocaleString("en-US")', 'new Intl.DateTimeFormat("en-GB")'])
      expect(FORMATTING.test(line)).toBe(true);
    expect(FORMATTING.test('Number(text)')).toBe(false);
  });

  it('keeps the exceptions few: a file that names none of the calls is not an exception', () => {
    for (const path of KEPT.keys()) expect(where((code) => FORMATTING.test(code))).toContain(path);
  });

  it('writes no percent with a space before its sign: "50%", not "50 %"', () => {
    const SPACED = /[\d}] %/u;
    expect(texts(sources.map(([, text]) => text).join('\n')).filter((shown) => SPACED.test(shown))).toEqual([]);
    expect(SPACED.test('2–98 %')).toBe(true);
    expect(SPACED.test('2–98%')).toBe(false);
  });

  it('has no table of month names: a date comes from formatMoment or formatDay', () => {
    expect(where((code) => /'JAN',\s*'FEB'/u.test(code))).toEqual([]);
    expect(/'JAN',\s*'FEB'/u.test("const M = ['JAN', 'FEB', 'MAR'];")).toBe(true);
  });
});

describe('less text (NM4-22, UI-04 part 6): an explanation stands behind the (i), a reason in the tooltip of the locked button', () => {
  // The explanations that were paragraphs: as the text between two tags they would be back.
  const MOVED = [
    'An estimate, not a promise.',
    'Jobs run 2 at a time per source',
    'Choose a dataset to search.',
    'Choose a tool to define an AOI, or enter a scene name above.',
    'The scenes are merged into one mosaic first',
    'One job covers the scenes of one pass',
    'Where scenes overlap, the preview may show another scene',
    'A job on the platform merges the whole scenes of one pass',
    // UI-05 (Otto, 06.11.2026): no explanation in the panel "Search and area".
    'Scenes counted by their center point in the cell',
  ];
  const inTags = (code: string, phrase: string) => new RegExp(`>\\s*${phrase.replace(/[.*+?^${}()|[\]\\]/gu, '\\$&')}`, 'u').test(code);
  // A hint or an error that is one long static sentence is an explanation; a state that asks for an action may stay.
  const LONG_HINT = /<(p|span) className="(?:hint|error)[^"]*"[^>]*>\s*([^<>{}]{60,}?)\s*<\/\1>/gu;
  const STATES = new Set([
    'No layers yet — select an image and “Add to layers”.',
    'No original file of this selection could be linked directly from the source.',
    'The colormaps could not be loaded. Choose from the few of the field, or try again later.',
  ]);
  const longHints = (code: string) => [...code.matchAll(LONG_HINT)].map((m) => m[2].replace(/\s+/gu, ' ').trim()).filter((text) => !STATES.has(text));

  it('shows none of the moved explanations as text between tags', () => {
    expect(where((code) => MOVED.some((phrase) => inTags(code, phrase)))).toEqual([]);
    expect(inTags('<p className="hint">An estimate, not a promise.</p>', MOVED[0])).toBe(true);
    expect(inTags('const ESTIMATE_NOTE = \'An estimate, not a promise.\';', MOVED[0])).toBe(false);
    expect(inTags('<Tip text="An estimate, not a promise." />', MOVED[0])).toBe(false);
  });

  it('has no hint or error of one long static sentence beyond the two listed states', () => {
    expect(sources.flatMap(([path, text]) => longHints(withoutComments(text)).map((hint) => `${path}: ${hint}`))).toEqual([]);
    expect(longHints('<p className="hint">Where scenes overlap, the preview may show another scene than the result.</p>')).toHaveLength(1);
    expect(longHints('<p className="hint">No place found.</p>')).toEqual([]);
    expect(longHints('<p className="hint warn">Left out (the AOI misses them): {skipped.join(\', \')}</p>')).toEqual([]);
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

describe('a locked control over the map (UI-04 part 3a, found in the review)', () => {
  const css = withoutCssComments(CSS);
  it('takes the click: a locked button in an overlay is not made transparent to the pointer', () => {
    expect(css).toMatch(/\.overlay > :is\([^)]*\):disabled\[data-tip\] \{\s*pointer-events: auto;/u);
  });

  it('dims a field that is locked by aria-disabled too (the switch "Filter within AOI only")', () => {
    expect(css).toMatch(/:is\(button, input, select, textarea, a, label,[^)]*\[role='switch'\]\)\[aria-disabled='true'\] \{\s*opacity: var\(--disabled-opacity\);/u);
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

describe('one eye (UI-04 part 3a, Otto, 4.11.2026): EyeButton, in the colour of the text, hidden is the eye crossed out', () => {
  const EYE = /(?<![\w-])Eye(?:Off)?Icon(?![\w-])/u;
  // A rule that gives an eye a colour of its own: its class `.eye` (except to leave it out), or the old `.off` of an icon button.
  const colourRules = (css: string) =>
    [...withoutCssComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/gu)]
      .filter(([, selector, body]) => (/\.eye\b/u.test(selector.replace(/:not\(\.eye\)/gu, '')) || /\.icon-btn\.off\b|\.lm-eye|\.vc-eye/u.test(selector)) && /(?:^|;|\s)color:/u.test(body))
      .map(([, selector]) => selector.trim());

  it('draws the eye in EyeButton only', () => {
    expect(where((code) => EYE.test(code))).toEqual(['components/EyeButton.tsx', 'components/icons.ts']);
    expect(EYE.test('<button>{shown ? <EyeIcon /> : <EyeOffIcon />}</button>')).toBe(true);
    expect(EYE.test('<EyeButton shown={on} />')).toBe(false);
  });

  it('gives the eye no colour of its own, shown or hidden', () => {
    expect(colourRules(CSS)).toEqual([]);
    expect(colourRules('.icon-btn.off { color: var(--muted); }')).toEqual(['.icon-btn.off']);
    expect(colourRules('.eye:hover { color: var(--accent); }')).toEqual(['.eye:hover']);
    expect(colourRules(".icon-btn[aria-pressed='true']:not(.eye) { color: var(--accent); }")).toEqual([]);
  });

  it('has no eye in a class of a place (the old lm-eye, vc-eye) in the code', () => {
    expect(where((code) => /(?<![\w-])(?:lm-eye|vc-eye)(?![\w-])/u.test(code))).toEqual([]);
  });
});

describe('no tooltip at a dataset, a group head or the name of a layer (UI-04 part 3a, Otto, 4.11.2026)', () => {
  // The places of a name: the dataset (the buttons and the lines of its dropdowns, in the view too), the head of a group, the title of a
  // view and the name of a layer. Only a dataset that cannot be chosen has a tooltip: its reason.
  const NAMES = /(?<![\w-])(?:dataset-toggle|dataset-select-title|dataset-select-box|dataset-select-option|vc-dataset|rg-label|rg-select|result-group-head|vc-title|vc-title-btn|lm-name)(?![\w-])/u;
  const withTip = (text: string) =>
    openingTags(text)
      .filter(({ attributes }) => NAMES.test(attributes.match(/className=(?:"[^"]*"|\{`[^`]*`\})/u)?.[0] ?? '') && /(?:^|\s)data-tip=/u.test(topLevel(attributes)))
      .map(({ attributes }) => (attributes.match(/className=(?:"([^"]*)"|\{`([^`]*)`\})/u) ?? [])[1] ?? '');
  // What stays: the tip of a dataset that cannot be chosen (its reason), the note of a layer (the hint of a preview) the name being renamed (its rule) and the entry "Search results" of the layer manager (it explains what the entry holds; it is no layer).
  const ALLOWED = [/not viewable/u, /\bl\.note\b/u, /EMPTY_NAME_TIP|A layer needs a name/u, /RESULTS_ENTRY_TIP/u];
  const faults = (text: string) =>
    openingTags(text)
      .filter(({ attributes }) => NAMES.test(attributes.match(/className=(?:"[^"]*"|\{`[^`]*`\})/u)?.[0] ?? '') && /(?:^|\s)data-tip=/u.test(topLevel(attributes)) && !ALLOWED.some((ok) => ok.test(attributes)))
      .map(({ attributes }) => attributes.trim().slice(0, 60));

  it('has none in the code, but the reason of a dataset that cannot be chosen', () => {
    expect(sources.flatMap(([path, text]) => faults(text).map((fault) => `${path}: ${fault}`))).toEqual([]);
    expect(withTip('<button className="btn dataset-toggle" data-tip={d.viewable ? undefined : `${d.title} — not viewable: ${d.reason}`}>').length).toBe(1);
  });

  it('finds a tooltip at each place of a name (counter-check)', () => {
    for (const line of [
      '<span className="dataset-select-title" data-tip={title}>',
      '<button className="btn dataset-toggle" data-tip={d.description}>',
      '<select className="vc-dataset" aria-label="Dataset" data-tip="Dataset of the image shown">',
      '<span className="rg-label" data-tip={group.label}>',
      '<button type="button" className="result-group-head" data-tip="x">',
      '<span className="vc-title" data-tip={tip}>',
      '<button className="lm-name" data-col="name" data-tip={`${name} — view this layer`}>',
    ]) expect(faults(line), line).toHaveLength(1);
    expect(faults('<button className="btn dataset-toggle" data-tip={d.viewable ? undefined : `${d.title} — not viewable: ${d.reason}`}>')).toEqual([]);
    expect(faults('<button className="lm-name" data-tip={l.note}>')).toEqual([]);
    expect(faults('<span className="result-id" data-tip={item.id}>')).toEqual([]);
    expect(faults('<button className="btn" data-tip="Remove">')).toEqual([]);
  });
});

// UI-04 part 3b: hints, errors and badges as one component each, no hard colour, one family, two steps of tooltips.
describe('one hint, one error, one badge, one choice button (UI-04 part 3b)', () => {
  // The classes the new ones replace: the small lines (`hint-text`, `pp-help`, `vc-note`), the marks (`pp-badge`, `preview-badge`,
  // `vc-temporary`) and the buttons of a choice (`pp-seg`, `pp-chip`). The dock `preview-badge-dock` and `pp-chip-row` stay.
  const OLD = /(?<![\w-])(?:hint-text|pp-help|vc-note|pp-badge|preview-badge|vc-temporary|pp-seg|pp-chip)(?![\w-])/u;

  it('has none of the old classes in the code or the styles', () => {
    expect(where((code) => OLD.test(code))).toEqual([]);
    expect(OLD.test(withoutCssComments(CSS))).toBe(false);
    expect(OLD.test('<p className="hint-text error">')).toBe(true);
    expect(OLD.test('<span className="pp-help">')).toBe(true);
    expect(OLD.test('<span className="pp-badge vc-temporary">')).toBe(true);
    expect(OLD.test('<button className={`pp-seg${on}`}>')).toBe(true);
    expect(OLD.test('<div className="overlay preview-badge-dock">')).toBe(false);
    expect(OLD.test('<div className="pp-chip-row">')).toBe(false);
  });

  it('draws the badge in Badge.tsx only', () => {
    const BADGE = /className=[{"'`][^>\n]*(?<![\w-])badge(?![\w-])/u;
    expect(where((code) => BADGE.test(code))).toEqual(['components/Badge.tsx']);
    expect(BADGE.test('<span className="badge loading">')).toBe(true);
    expect(BADGE.test('<span className="rail-badge">')).toBe(false);
  });

  it('gives the hint, the warning and the error their colours as tokens', () => {
    const css = withoutCssComments(CSS);
    expect(css).toMatch(/\n\.hint \{\s*color: var\(--muted\);/u);
    expect(css).toMatch(/\n\.hint\.warn \{\s*color: var\(--accent-2\);/u);
    expect(css).toMatch(/\n\.error \{\s*color: var\(--danger\);/u);
  });
});

describe('no hard colour outside tokens.css (UI-04 §7.5 no. 4)', () => {
  // A colour is written as `#hex`, `rgb()`, `rgba()`, `hsl()`, `hsla()` or by name. The rules named here may keep theirs, each with its reason.
  const EXCEPTIONS: Record<string, string> = {
    '.legend-gradient': 'the colours of the data: the same palette as the cells of the coverage map (`coverage.ts`), not those of a control',
  };
  const COLOUR = /#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?)\(|(?<![\w-])(?:white|black|red|green|blue|gray|grey|yellow|orange|purple|pink|cyan|magenta)(?![\w-])/u;
  const hardColours = (css: string, exceptions: Record<string, string> = EXCEPTIONS) =>
    [...withoutCssComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/gu)]
      .filter(([, selector, body]) => COLOUR.test(body.replace(/url\([^)]*\)/gu, '')) && !Object.keys(exceptions).includes(selector.trim()))
      .map(([, selector]) => selector.trim().replace(/\s+/gu, ' '));

  it('has none in index.css, but the colours of the data', () => {
    expect(hardColours(CSS)).toEqual([]);
  });

  it('finds a colour in every notation (counter-check)', () => {
    expect(hardColours('.a { color: #fff; }')).toEqual(['.a']);
    expect(hardColours('.a { color: #ff5a6e }')).toEqual(['.a']);
    expect(hardColours('.a { background: rgba(0, 0, 0, 0.5); }')).toEqual(['.a']);
    expect(hardColours('.a { border-color: rgb(1 2 3); }')).toEqual(['.a']);
    expect(hardColours('.a { color: hsl(10 20% 30%); }')).toEqual(['.a']);
    expect(hardColours('.a { color: white; }')).toEqual(['.a']);
    expect(hardColours('@media (max-width: 1px) { .b { color: #123456 } }')).toEqual(['.b']);
  });

  it('lets tokens, color-mix and a named exception pass', () => {
    expect(hardColours('.a { color: var(--text); background: color-mix(in srgb, var(--accent) 22%, transparent); }')).toEqual([]);
    expect(hardColours('.a { color: var(--danger, var(--text)); }')).toEqual([]);
    expect(hardColours('.legend-gradient { background: linear-gradient(#2c7bb6, #d7191c); }')).toEqual([]);
    expect(hardColours('.legend-gradient-2 { background: #2c7bb6; }')).toEqual(['.legend-gradient-2']);
    expect(hardColours('.x { background: url("data:image/svg+xml;utf8,<svg fill=\'red\'/>"); }')).toEqual([]);
  });

  it('names a reason for each exception, and each exception still exists', () => {
    for (const [selector, reason] of Object.entries(EXCEPTIONS)) {
      expect(reason.length, selector).toBeGreaterThan(20);
      expect(CSS, selector).toContain(`${selector} {`);
    }
  });
});

describe('one family (UI-04 part 3b, Otto, 3.11.2026): the font of the page, the monospace one for the band math only', () => {
  // Every `font-family` declaration with the rule it stands in; `font:` is only ever `inherit`.
  const declarations = (css: string, property: RegExp) =>
    [...withoutCssComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/gu)].flatMap(([, selector, body]) =>
      body
        .split(';')
        .map((declaration) => declaration.trim())
        .filter((declaration) => property.test(declaration))
        .map((declaration) => `${selector.trim().replace(/\s+/gu, ' ')} -> ${declaration.replace(/\s+/gu, ' ')}`),
    );
  // The page, the map (MapLibre sets its own), and the formula field.
  const FAMILIES = ['body -> font-family: var(--font)', '.app .maplibregl-map -> font-family: var(--font)', '.pp-field textarea -> font-family: var(--font-mono)'];

  it('names a family in the page, the map and the formula field only', () => {
    expect(declarations(CSS, /^font-family\s*:/u)).toEqual(FAMILIES);
    expect(declarations('.a { font-family: Arial, sans-serif; }', /^font-family\s*:/u)).toEqual(['.a -> font-family: Arial, sans-serif']);
    expect(declarations('.a { color: red; }', /^font-family\s*:/u)).toEqual([]);
  });

  it('writes the shorthand `font` only as `inherit`', () => {
    const shorthand = declarations(CSS, /^font\s*:/u);
    expect(shorthand.length).toBeGreaterThan(0);
    expect(shorthand.filter((declaration) => !declaration.endsWith('font: inherit'))).toEqual([]);
    expect(declarations('.a { font: 12px Arial; }', /^font\s*:/u).filter((declaration) => !declaration.endsWith('font: inherit'))).toHaveLength(1);
  });

  it('lets the controls take the type of the page in one rule', () => {
    expect(withoutCssComments(CSS)).toMatch(/\nbutton,\s*input,\s*select,\s*textarea \{\s*font: inherit;\s*\}/u);
  });

  it('sets no family in the code', () => {
    const FAMILY = /fontFamily|font-family/u;
    expect(where((code) => FAMILY.test(code))).toEqual([]);
    expect(FAMILY.test('<span style={{ fontFamily: "Arial" }}>')).toBe(true);
  });
});

describe('two steps of tooltips (UI-04 part 3b, Otto, 4.11.2026): data-tip-level="advanced", none = simple', () => {
  // The step is written as the literal "advanced", or as an expression that gives 'advanced' or nothing (a tip that is a reason while the
  // control is locked, a description otherwise). There is no literal "simple": no step is simple.
  const levelOf = (attributes: string): string[] | null => {
    const m = /(?:^|\s)data-tip-level=(?:"([^"]*)"|\{((?:[^{}]|\{[^{}]*\})*)\})/u.exec(attributes);
    if (!m) return null;
    if (m[1] !== undefined) return [m[1]];
    return [...m[2].matchAll(/'([^']*)'|"([^"]*)"/gu)].map((s) => s[1] ?? s[2]);
  };
  const tagsWithTip = (text: string) => openingTags(text).filter(({ attributes }) => /(?:^|\s)data-tip=/u.test(topLevel(attributes)));
  const badSteps = (text: string) =>
    openingTags(text).flatMap(({ tag, attributes }) => {
      const levels = levelOf(topLevel(attributes) + attributes);
      if (levels === null) return [];
      const ok = levels.length > 0 && levels.every((l) => l === 'advanced') && /(?:^|\s)data-tip=/u.test(topLevel(attributes));
      return ok ? [] : [`<${tag}> ${attributes.trim().slice(0, 60)}`];
    });

  it('has no step but "advanced", and only beside a data-tip', () => {
    expect(sources.flatMap(([path, text]) => badSteps(text).map((fault) => `${path}: ${fault}`))).toEqual([]);
    expect(badSteps('<button data-tip="x" data-tip-level="advanced">')).toEqual([]);
    expect(badSteps("<button data-tip={a} data-tip-level={a ? undefined : 'advanced'}>")).toEqual([]);
    expect(badSteps('<button data-tip="x" data-tip-level="simple">')).toHaveLength(1);
    expect(badSteps('<button data-tip="x" data-tip-level="Advanced">')).toHaveLength(1);
    expect(badSteps('<button data-tip="x" data-tip-level={a ? "basic" : undefined}>')).toHaveLength(1);
    expect(badSteps('<button data-tip-level="advanced">')).toHaveLength(1);
  });

  // (b) the name of a button with only an icon that is not obvious, (a) and (c) are the unmarked or the locked ones, and what stands behind an (i).
  const NEVER_ADVANCED = [
    { what: 'the (i)', file: 'components/Tip.tsx', test: /./u },
    { what: 'a rail button', file: 'components/AppRail.tsx', test: /\brail-btn\b/u },
    { what: '"Flip through layers"', file: 'components/LayerManager.tsx', test: /\blm-flip\b/u },
    { what: '"Reverse" the colormap', file: 'components/ColormapField.tsx', test: /\bvc-reverse\b/u },
    { what: '"Reverse" in the list of colormaps', file: 'components/ColormapPicker.tsx', test: /\bvc-reverse\b/u },
    { what: '"Process layer"', file: 'components/LayerManager.tsx', test: /PROCESS_LAYER_TEXT/u },
    { what: '"Search results" to the top', file: 'components/ResultsToTop.tsx', test: /RESULTS_TO_TOP_TIP/u },
    { what: 'the actions of a job or a group', file: 'components/ProcessingManager.tsx', test: /Actions for/u },
  ];
  it.each(NEVER_ADVANCED)('does not hold back the tip of $what', ({ file, test }) => {
    const tags = tagsWithTip(SOURCES[`./${file}`]).filter(({ attributes }) => test.test(attributes) || file.endsWith('Tip.tsx'));
    expect(tags.length, file).toBeGreaterThan(0);
    expect(tags.filter(({ attributes }) => levelOf(attributes) !== null).map(({ attributes }) => attributes.trim().slice(0, 50))).toEqual([]);
  });

  it('marks the obvious controls: the red x, the eye, the bin and the badge', () => {
    for (const file of ['components/CloseButton.tsx', 'components/EyeButton.tsx', 'components/Badge.tsx', 'components/ShareLink.tsx']) {
      const tags = tagsWithTip(SOURCES[`./${file}`]);
      expect(tags.length, file).toBeGreaterThan(0);
      expect(tags.some(({ attributes }) => levelOf(attributes)?.includes('advanced')), file).toBe(true);
    }
  });
});

describe('the settings are in one panel (UI-04 part 4, Otto, 3.11.2026 and 4.11.2026)', () => {
  const code = sources.map(([, text]) => withoutComments(text)).join('\n');

  it('has no button "Basemap" and no button for the theme beside it, and no pop-up menu of the settings: nothing of the old places is left', () => {
    expect(code).not.toMatch(/\bBasemapMenu\b|\bSettingsMenu\b|basemap-btn|\btoggleTheme\b|placePopoverBeside/u);
    expect(code).not.toMatch(/Switch to the (?:light|dark) theme/u);
  });

  it('has Relief only as an overlay: no basemap of that name', () => {
    expect(SOURCES['./basemaps.ts']).not.toMatch(/\brelief\b/iu);
  });

  it('keeps the symbol of the panel at the bottom of the rail, after the others', () => {
    expect(CSS).toMatch(/\.rail-settings \{[^}]*margin-top: auto/u);
  });

  it('is a panel of the dock like the others: a slot, the head of a panel without an x, no pop-up', () => {
    expect(SOURCES['./App.tsx']).toMatch(/dockPanelId\('settings'\)/u);
    const panel = SOURCES['./components/SettingsPanel.tsx'];
    expect(panel).toMatch(/className="results-head"/u);
    expect(panel).not.toMatch(/Popover|role="menu|menuitem|MenuTick/u);
  });

  it('has no list of ticks in it: every choice is a segment button, in rows of one size, the two steps of the tooltips too', () => {
    const panel = SOURCES['./components/SettingsPanel.tsx'];
    expect(panel).toMatch(/className="btn seg"/u);
    expect(panel).toMatch(/aria-label="Tooltips"/u);
    expect(panel).not.toMatch(/CheckIcon|aria-checked|type="checkbox"|type="radio"|role="switch"|<Switch\b/u);
    expect(CSS).toMatch(/\.settings-row \{[^}]*grid-template-columns: repeat\(var\(--settings-columns\), minmax\(0, 1fr\)\)/u);
    expect(CSS).toMatch(/\.settings-panel \{[^}]*--settings-columns: 4/u);
  });
});

describe('the panels of the rail have no x (UI-04 part 4, Otto, 4.11.2026): they are opened and closed with their symbol', () => {
  // The red x is for the side bar at the right, dialogs, sheets and messages (`CloseButton`); a panel at the left (Search and area, Layers, Jobs,
  // Search results, Settings) is switched on and off with its symbol in the rail.
  const PANELS = [
    'components/ControlPanel.tsx',
    'components/LayerManager.tsx',
    'components/ProcessingManager.tsx',
    'components/ResultsPanel.tsx',
    'components/SettingsPanel.tsx',
  ];
  const holdsX = (text: string) => /<CloseButton\b|\bclose-x\b|\bcloseDock\b/u.test(withoutComments(text));

  it.each(PANELS)('has no CloseButton, no close-x and no closeDock in %s', (path) => {
    expect(SOURCES[`./${path}`], path).toBeDefined();
    expect(holdsX(SOURCES[`./${path}`]), path).toBe(false);
  });

  it('finds an x in the head of a panel (counter-check)', () => {
    expect(holdsX('<div className="results-head"><h2>Jobs</h2><CloseButton onClick={f} /></div>')).toBe(true);
    expect(holdsX('<button className="close-x">')).toBe(true);
    expect(holdsX('const close = useAppStore((s) => s.closeDock);')).toBe(true);
    expect(holdsX('<div className="results-head"><h2>Jobs</h2></div>')).toBe(false);
  });
});

describe('a segment button is the form of a choice (UI-04 part 4, Otto, 4.11.2026)', () => {
  // A switch (`role="switch"`) is for something that is on or off and nothing else; a choice of one of several, the steps of the tooltips
  // included, is a row of segment buttons, and a thing that is on beside others is a button that is pressed. Today the one switch is the
  // checkbox "Filter within AOI only" (Otto, 4.11.2026: it stays).
  const holders = (text: string) => /role="switch"/u.test(withoutComments(text));
  it('has `role="switch"` only in the filter within the AOI, and no component `Switch`', () => {
    expect(sources.filter(([, text]) => holders(text)).map(([path]) => path)).toEqual(['components/AdvancedSearch.tsx']);
    expect(SOURCES['./components/Switch.tsx']).toBeUndefined();
    expect(holders('<button role="switch" />')).toBe(true);
    expect(holders('<button aria-pressed />')).toBe(false);
  });

  it('fills the segment button that is chosen, and the overlay that is on', () => {
    expect(CSS).toMatch(/\.btn\.seg\[aria-pressed='true'\] \{[^}]*background: var\(--accent\)/u);
    expect(CSS).toMatch(/\.btn\.seg\[aria-pressed='true'\] \{[^}]*color: var\(--on-accent\)/u);
  });
});

describe('the full text of a cut-off text shows only while it is cut (UI-04 part 4, Otto, 4.11.2026): data-tip-cut', () => {
  const cutTags = (text: string) => openingTags(text).filter(({ attributes }) => /(?:^|\s)data-tip-cut(?:=|\s|$)/u.test(topLevel(attributes)));
  const faults = (text: string) =>
    cutTags(text).flatMap(({ tag, attributes }) => {
      const top = topLevel(attributes);
      const problems: string[] = [];
      if (!/(?:^|\s)data-tip=/u.test(top)) problems.push('no data-tip');
      // It holds in both steps: a step beside it would hold the tip back in one of them.
      if (/(?:^|\s)data-tip-level=/u.test(top)) problems.push('has a step');
      // `data-tip-cut` alone would render as "true", which names no element to measure.
      if (/(?:^|\s)data-tip-cut(?=\s|$)/u.test(top)) problems.push('empty without a value');
      return problems.map((problem) => `<${tag}> ${problem}`);
    });

  it('sits only beside a data-tip, never with a step, and always with a value', () => {
    expect(sources.flatMap(([path, text]) => faults(text).map((fault) => `${path}: ${fault}`))).toEqual([]);
    expect(faults('<span data-tip="a" data-tip-cut="">')).toEqual([]);
    expect(faults('<button data-tip={t} data-tip-cut=".pm-title">')).toEqual([]);
  });

  it('finds a fault in each of its three forms (counter-check)', () => {
    expect(faults('<span data-tip-cut="">')).toHaveLength(1);
    expect(faults('<span data-tip="a" data-tip-level="advanced" data-tip-cut="">')).toHaveLength(1);
    expect(faults('<span data-tip="a" data-tip-cut>')).toHaveLength(1);
  });

  // The places where a text is cut with an ellipsis and has the full text as its tip: the title of a job and of a batch, the name of a scene.
  const CUT_TEXTS = [
    { what: 'the title of a job', file: 'components/ProcessingManager.tsx', test: /data-tip=\{title\}/u },
    { what: 'the title of a batch', file: 'components/ProcessingManager.tsx', test: /data-tip=\{batch\.title\}/u },
    { what: 'the name of a scene in the list', file: 'components/ResultsPanel.tsx', test: /data-tip=\{item\.id\}/u },
  ];
  it.each(CUT_TEXTS)('marks $what', ({ file, test }) => {
    const tags = openingTags(SOURCES[`./${file}`]).filter(({ attributes }) => test.test(attributes));
    expect(tags.length, file).toBeGreaterThan(0);
    expect(tags.filter(({ attributes }) => !/(?:^|\s)data-tip-cut=/u.test(topLevel(attributes))).map(({ attributes }) => attributes.trim().slice(0, 50))).toEqual([]);
  });

  it('names an element that the button holds, where the tip sits on a button around the cut text', () => {
    const tags = openingTags(SOURCES['./components/ProcessingManager.tsx']).filter(({ attributes }) => /data-tip-cut="\./u.test(attributes));
    expect(tags.length).toBeGreaterThan(0);
    for (const { attributes } of tags) {
      const selector = /data-tip-cut="\.([\w-]+)"/u.exec(attributes)?.[1];
      expect(selector).toBeTruthy();
      expect(SOURCES['./components/ProcessingManager.tsx']).toContain(`className="${selector}"`);
      // And that element is the one that is cut (`text-overflow: ellipsis`).
      expect(new RegExp(`\\.${selector} \\{[^}]*text-overflow: ellipsis`, 'u').test(CSS)).toBe(true);
    }
  });
});

describe('no rule for a class nobody names (UI-04 part 3b)', () => {
  // Classes the code builds from a part (`range-hist-${channel}`) or that a library puts on its own elements (MapLibre).
  const BUILT = /^(?:range-hist-|vc-chip-|maplibregl-)/u;
  const unused = (css: string, code: string) => {
    const classes = new Set([...withoutCssComments(css).replace(/\{[^{}]*\}/gu, '{}').matchAll(/(?<![\w-])\.([a-zA-Z][\w-]*)/gu)].map((m) => m[1]));
    return [...classes].filter((name) => !BUILT.test(name) && !new RegExp(`(?<![\\w-])${name}(?![\\w-])`, 'u').test(code)).sort();
  };

  it('has none in index.css', () => {
    expect(unused(CSS, sources.map(([, text]) => withoutComments(text)).join('\n'))).toEqual([]);
  });

  it('finds a rule without a user (counter-check)', () => {
    expect(unused('.used { } .gone > .used { } .maplibregl-map { }', '<div className="used" />')).toEqual(['gone']);
  });
});

describe('no autofill of the browser (UI-04 part 3b, Otto, 4.11.2026): autocomplete="off" at every field, and the filled-in colours from the tokens', () => {
  // A field that takes text: a text, a search, a number or a date, and a text area. A tick, a choice, a slider and a file are no such field.
  const NOT_TEXT = /type="(?:checkbox|radio|range|file|hidden|button|submit|reset|image|color)"/u;
  const withoutOff = (text: string) =>
    openingTags(text)
      .filter(({ tag, attributes }) => (tag === 'input' || tag === 'textarea') && !NOT_TEXT.test(attributes))
      .filter(({ attributes }) => !/(?:^|\s)autoComplete="off"/u.test(topLevel(attributes) + attributes))
      .map(({ tag, attributes }) => `<${tag} ${attributes.trim().slice(0, 50)}`);

  it('has autocomplete off at every input and text area that takes text', () => {
    expect(sources.flatMap(([path, text]) => withoutOff(text).map((tag) => `${path}: ${tag}`))).toEqual([]);
    expect(withoutOff('<input type="text" value={v} />')).toHaveLength(1);
    expect(withoutOff('<input value={v} onChange={f} />')).toHaveLength(1);
    expect(withoutOff('<textarea rows={3} />')).toHaveLength(1);
    expect(withoutOff('<input type="number" autoComplete="on" />')).toHaveLength(1);
    expect(withoutOff('<input type="number" autoComplete="off" />')).toEqual([]);
    expect(withoutOff('<input type="checkbox" checked />')).toEqual([]);
    expect(withoutOff('<input type="range" />')).toEqual([]);
    expect(withoutOff('<select autoComplete="x" />')).toEqual([]);
  });

  it('has no input component (the one that takes the props of an input) without it either', () => {
    expect(SOURCES['./components/ClearableInput.tsx']).toMatch(/<input[^>]*autoComplete="off"/u);
  });

  const css = withoutCssComments(CSS);
  it.each([':-webkit-autofill', ':autofill'])('draws a field the browser filled in (%s) with the colours of the field, in both themes', (pseudo) => {
    const start = css.indexOf(`input${pseudo},\ntextarea${pseudo} {`);
    expect(start, pseudo).toBeGreaterThanOrEqual(0);
    const rule = css.slice(start, css.indexOf('}', start));
    expect(rule).toContain('-webkit-text-fill-color: var(--text)');
    expect(rule).toContain('var(--input-bg)');
    expect(rule).toContain('var(--map-bg)');
    expect(rule).toContain('transition: background-color');
  });
});

describe('one frame, one ring (UI-04 part 3b, Otto, 4.11.2026): the ring is at the control, from the keyboard, and nothing else frames the focus', () => {
  // The rules of the focus: what they set, by the pseudo-class they name. A plain `:focus` is also a click of the mouse; `:focus-within` is
  // the whole section that holds the control.
  const FRAME = /(?:^|;|\s)(?:outline(?:-[a-z]+)?|border(?![a-z-]*radius)(?:-[a-z]+)*|box-shadow):/u;
  const rules = (css: string) => [...withoutCssComments(css).matchAll(/([^{}]+)\{([^{}]*)\}/gu)].map(([, selector, body]) => ({ selector: selector.trim().replace(/\s+/gu, ' '), body }));
  const inFocus = (css: string, pseudo: RegExp) => rules(css).filter(({ selector, body }) => pseudo.test(selector) && FRAME.test(body)).map(({ selector }) => selector);
  // What stays: the ring of the slider on its thumb, and the popover, which takes its ring away.
  const KEPT_RING = [
    ":is(a[href], button, input, select, textarea, summary, [role='button'], [role='menuitem'], [role='menuitemradio'], [tabindex]):focus-visible",
    ".inspector .range-hist input[type='range']:focus-visible",
    '.popover:focus-within',
  ];

  it('has no frame, shadow or ring at a plain :focus (the mouse shows it too): the ring is the one sign', () => {
    expect(inFocus(CSS, /:focus(?![-\w])/u)).toEqual([]);
    expect(inFocus('.a input:focus { border-color: red; }', /:focus(?![-\w])/u)).toHaveLength(1);
    expect(inFocus('input:focus { box-shadow: var(--glow); }', /:focus(?![-\w])/u)).toHaveLength(1);
    expect(inFocus('input:focus-visible { box-shadow: var(--glow); }', /:focus(?![-\w])/u)).toEqual([]);
  });

  it('has no second frame beside the ring at :focus-visible: only the ring itself and the thumb of a slider', () => {
    const found = inFocus(CSS, /:focus-visible/u).filter((selector) => !KEPT_RING.some((kept) => selector.startsWith(kept)));
    expect(found).toEqual([]);
    expect(inFocus('.vc-unit:focus-visible { border-color: var(--accent); }', /:focus-visible/u)).toHaveLength(1);
    expect(inFocus('.tip:focus-visible { border-radius: var(--radius-sm); }', /:focus-visible/u)).toEqual([]);
  });

  it('draws nothing around a whole section when the focus is inside it (:focus-within): a row may be tinted, not framed', () => {
    const found = inFocus(CSS, /:focus-within/u).filter((selector) => selector !== '.popover:focus-within');
    expect(found).toEqual([]);
    expect(inFocus('.section:focus-within { outline: 2px solid var(--focus); }', /:focus-within/u)).toHaveLength(1);
    expect(inFocus('.box:focus-within { border-color: var(--accent); }', /:focus-within/u)).toHaveLength(1);
    expect(inFocus('.row:focus-within { box-shadow: inset 2px 0 0 var(--accent); }', /:focus-within/u)).toHaveLength(1);
    expect(inFocus('.row:focus-within { background: var(--row-hover); }', /:focus-within/u)).toEqual([]);
  });

  it('takes the ring away from the popover as a whole', () => {
    expect(withoutCssComments(CSS)).toMatch(/\.popover:focus-within \{\s*outline: none;/u);
  });
});

describe('the layer manager (Otto, 11.11.2026): a row of a dataset, of a result and "Search results" alike', () => {
  // What a row of the manager is made of.
  const ROW_PARTS = ['components/LayerManager.tsx', 'components/BandSelect.tsx', 'components/EyeButton.tsx', 'components/ResultsEye.tsx', 'components/LayerDownload.tsx'];

  // A label that holds its tip back in the step "Simple" whatever the field in it is: a locked field there would not say why, since the label
  // itself is not locked (`tipLevel.ts::tipShown`).
  const lockedInAdvancedLabel = (text: string): string[] => {
    const code = withoutComments(text);
    return [...code.matchAll(/<label\b[^>]*\sdata-tip-level="advanced"[^>]*>/gu)].flatMap((m) => {
      const inside = code.slice(m.index + m[0].length, code.indexOf('</label>', m.index));
      return /\sdisabled[=\s>]/u.test(inside) ? [m[0].slice(0, 60)] : [];
    });
  };

  it('shows the reason of a locked field in a label with a tip in either step', () => {
    expect(ROW_PARTS.flatMap((part) => lockedInAdvancedLabel(SOURCES[`./${part}`]).map((fault) => `${part}: ${fault}`))).toEqual([]);
    expect(lockedInAdvancedLabel('<label className="x" data-tip-level="advanced" data-tip={title}>\n<select disabled={disabled}>')).toHaveLength(1);
    expect(lockedInAdvancedLabel("<label data-tip-level={disabled ? undefined : 'advanced'} data-tip={title}>\n<select disabled={disabled}>")).toEqual([]);
  });

  // The words of the guide (§4) for a deleted job, and one name of "Process" for every layer.
  const OLD_WORDS = [/restore it to show it/u, /^Process this layer$/u, /^Process further$/u, /^Expired: runs everything again from the scenes\.$/u];
  const oldWords = (text: string) => texts(text).filter((t) => OLD_WORDS.some((word) => word.test(t)));

  it('has one reason for a deleted job and one name of "Process" for every layer', () => {
    expect(sources.flatMap(([path, text]) => oldWords(text).map((word) => `${path}: ${word}`))).toEqual([]);
    expect(oldWords("export const DELETED_LAYER_TIP = 'Job deleted: restore it to show it';")).toHaveLength(1);
    expect(oldWords("data-tip={l.result ? 'Process further' : 'Process this layer'}")).toHaveLength(2);
  });

  // Only a band of classes is drawn as it is; a rule by the data type alone (`/^float/`) put every result of whole numbers there.
  const byFloatAlone = (text: string) => /\/\^float\/|startsWith\('float'\)/u.test(withoutComments(text));

  it('does not decide by the data type alone that a result has no range to set', () => {
    expect(where(byFloatAlone)).toEqual([]);
    expect(byFloatAlone("const adjustable = info.dataType !== null && /^float/.test(info.dataType);")).toBe(true);
    expect(byFloatAlone('const adjustable = info.dataType !== null && !info.classes;')).toBe(false);
  });
});

describe('the buttons at the bottom right of the map (UI-06, `docs/ui/leitfaden.md` §9)', () => {
  const NAVIGATION = /\bNavigationControl\b|\bTerrainControl\b/u;
  const CONTROLS = /<MapControls\b/u;

  it('has none of MapLibre\'s own map buttons: `MapControls` has compass, zoom and 3D in one form', () => {
    expect(where((code) => NAVIGATION.test(code))).toEqual([]);
    expect(NAVIGATION.test("map.addControl(new NavigationControl({ showCompass: false }), 'bottom-right');")).toBe(true);
    expect(where((code) => CONTROLS.test(code))).toEqual(['components/MapView.tsx']);
  });

  it('puts "3D" at the map and not into the panel "Settings"', () => {
    const settings = withoutComments(SOURCES['./components/SettingsPanel.tsx']);
    expect(texts(settings).filter((t) => /^(?:3D|Terrain)$/u.test(t))).toEqual([]);
    expect(texts('<button>3D</button>').filter((t) => /^(?:3D|Terrain)$/u.test(t))).toEqual(['3D']);
  });

  it('colours the needle of the compass with tokens only', () => {
    const css = withoutCssComments(CSS);
    expect(css).toMatch(/\.compass-north \{\s*fill: var\(--danger\);/u);
    expect(css).toMatch(/\.compass-south \{\s*fill: var\(--text\);/u);
  });
});

describe('the output types of an order (Otto, 11.11.2026): only those that make sense, by the rule of the registry', () => {
  // The rule is the operators' (`x-earthx-passes-values` of the description): the file that offers the types names no operator or method.
  const OWN_RULE = /['"](?:band_math|normalize|reproject|mask|mask_values|nearest|mode|bilinear)['"]/u;
  // No type is shown locked or marked: what does not make sense is not offered.
  const MARKED = /not recommended|nodata does not fit|These types are not offered|disabledReason/u;

  it('takes the rule from the description, not from a list of its own', () => {
    expect(OWN_RULE.test(withoutComments(SOURCES['./processingDefaults.ts']))).toBe(false);
    expect(OWN_RULE.test("const FLOAT_RESULT = { band_math: 1 }; const PICKING = ['nearest', 'mode'];")).toBe(true);
  });

  it('offers no type it marks or locks', () => {
    expect(where((code) => MARKED.test(code))).toEqual([]);
    expect(MARKED.test('<option disabled={option.disabledReason !== null}>')).toBe(true);
  });
});
