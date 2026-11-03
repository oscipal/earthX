// UI-04 §7.5: checks that find a relapse of the rules of the guide (`docs/ui/leitfaden.md`) in the source of the interface.
// Each rule has its counter-check: the same function finds the fault in a made-up line.

import { describe, expect, it } from 'vitest';

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

  // The x of these is no close: it removes a step, a link or the results, or empties a field. Teil 2 gives them their Lucide symbols
  // (`trash-2`, `circle-x`) and empties this list.
  const UNTIL_PART_2 = ['components/ClearableInput.tsx', 'components/ResultsPanel.tsx', 'components/ShareLink.tsx', 'components/StepForm.tsx'];
  it('has an x glyph in a button only where it removes or empties, until part 2', () => {
    expect(where((code) => X_GLYPH.test(code))).toEqual(UNTIL_PART_2);
    expect(X_GLYPH.test('<button type="button">\n  ✕\n</button>')).toBe(true);
    expect(X_GLYPH.test('<span>10 m × 10 m</span>')).toBe(false);
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
