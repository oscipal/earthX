// UI-03 §7.4, UI-04 part 6: finds hard values for spacing, type size and radius in the rules of the areas that use the tokens; the area
// `ALL_RULES` stands for every rule of the sheet.

export const ALL_RULES = '*';

// What a token stands for; a "px"/"rem" number in these is a hard value.
const CHECKED = /^(?:padding|margin)(?:-[a-z]+)*$|^(?:row-|column-)?gap$|^font-size$|^border(?:-[a-z]+)*-radius$/u;
const HARD_LENGTH = /(?<![\w.-])-?(?:\d+\.?\d*|\.\d+)(?:px|rem)(?![\w-])/gu;

// Cuts `text` at the top-level `separators`, not inside quotes, parentheses or brackets (a data URL holds `;` and `,`).
function splitTop(text: string, separators: string): string[] {
  const parts: string[] = [];
  let depth = 0;
  let quote = '';
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    const c = text[i];
    if (quote) {
      if (c === '\\') i += 1;
      else if (c === quote) quote = '';
    } else if (c === '"' || c === "'") quote = c;
    else if (c === '(' || c === '[') depth += 1;
    else if (c === ')' || c === ']') depth -= 1;
    else if (depth === 0 && separators.includes(c)) {
      parts.push(text.slice(start, i));
      start = i + 1;
    }
  }
  parts.push(text.slice(start));
  return parts;
}

function startsWithSelector(selector: string, prefix: string): boolean {
  return selector.startsWith(prefix) && !/[\w-]/u.test(selector[prefix.length] ?? '');
}

// A value is clean when no length is hard: a function that takes a variable (`calc(var(--a) + 4px)`) counts as set by the token.
function hardLengths(value: string): string[] {
  let rest = value.replace(/!important/giu, '');
  for (let previous = ''; previous !== rest; ) {
    previous = rest;
    rest = rest.replace(/[\w-]*\((?:[^()]*\bvar\([^()]*\))[^()]*\)/gu, ' ');
  }
  return (rest.match(HARD_LENGTH) ?? []).filter((length) => Number.parseFloat(length) !== 0);
}

// Walks the sheet by braces: the rules in a `@media` block are read like the others, comments are dropped.
// `hardValues('.btn { padding: 5px }', ['.btn'])` is `['.btn { padding: 5px }']`.
export function hardValues(css: string, selectors: readonly string[]): string[] {
  const text = css.replace(/\/\*[\s\S]*?\*\//gu, '');
  const found: string[] = [];
  let index = 0;
  const walk = (inside: string[] | null, top = false): void => {
    while (index < text.length) {
      let end = index;
      let depth = 0;
      let quote = '';
      for (; end < text.length; end += 1) {
        const c = text[end];
        if (quote) {
          if (c === '\\') end += 1;
          else if (c === quote) quote = '';
        } else if (c === '"' || c === "'") quote = c;
        else if (c === '(' || c === '[') depth += 1;
        else if (c === ')' || c === ']') depth -= 1;
        else if (depth <= 0 && (c === '{' || c === '}' || c === ';')) break;
      }
      const head = text.slice(index, end).trim();
      const mark = text[end];
      index = end + 1;
      if (mark === '{') {
        if (head.startsWith('@')) walk(null);
        else {
          const hit = splitTop(head, ',')
            .map((selector) => selector.trim())
            .filter((selector) => selectors.some((prefix) => prefix === ALL_RULES || startsWithSelector(selector, prefix)));
          walk(hit);
        }
      } else {
        if (inside && inside.length > 0 && head.includes(':')) {
          const colon = head.indexOf(':');
          const property = head.slice(0, colon).trim().toLowerCase();
          const value = head.slice(colon + 1).trim();
          if (CHECKED.test(property) && hardLengths(value).length > 0) found.push(`${inside.join(', ')} { ${property}: ${value} }`);
        }
        if (mark === '}' && !top) return;
      }
    }
  };
  walk(null, true);
  return found;
}
