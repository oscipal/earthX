// The numbers of a "Mask by value" step (DS-06b): what each condition takes, and how the text of the field becomes the
// `values` of the step. The server decides (`422`); this is the help while typing.

export const CONDITIONS = [
  { value: 'lt', label: 'below' },
  { value: 'gt', label: 'above' },
  { value: 'between', label: 'between' },
  { value: 'eq', label: 'equal to' },
] as const;

export type Condition = (typeof CONDITIONS)[number]['value'];

export const isCondition = (value: unknown): value is Condition => CONDITIONS.some((c) => c.value === value);

// What the server takes as the list of an `eq` condition.
export const MAX_EQUAL_VALUES = 64;

const PARTS = /[\s,;]+/u;

// The text of the numbers when the condition changes: `below` and `above` keep the first, `between` the first two.
export function valuesAfterConditionChange(text: string, next: string): string {
  const parts = text.split(PARTS).filter((part) => part !== '');
  if (next === 'lt' || next === 'gt') return parts[0] ?? '';
  if (next === 'between') return parts.length === 0 ? '' : betweenText(parts[0], parts[1] ?? '');
  return text;
}

// The two boxes of `between`: "from" and "to", by position ("; 0.8" is a "to" without a "from"). The panel writes
// "from; to", a recipe's list comes as "from, to": a comma inside a box ("0,2") is then still told as the mistake it is.
export function betweenParts(text: string): [string, string] {
  const [from = '', to = ''] = text.split(text.includes(';') ? ';' : ',').map((part) => part.trim());
  return [from, to];
}

export const betweenText = (from: string, to: string): string => (from === '' && to === '' ? '' : `${from}; ${to}`);

// What a box for one number keeps: no separator of a list, no blanks.
export const oneNumber = (text: string): string => text.replace(/[;\s]+/gu, '');

// A comma in a box for one number: most likely a decimal mark, which the server would read as a list.
export const hasComma = (text: string): boolean => text.includes(',');

// The `values` of the step as the condition wants them, or the reason they do not fit. `params.values` is the list as
// typed; `eq` is written ascending and each number once (K3 of M4-18), `between` needs the lower number first.
export function refineMaskValues(params: Record<string, unknown>, errors: Record<string, string>): void {
  const values = params.values;
  const condition = params.condition;
  if (!Array.isArray(values) || !isCondition(condition)) return;
  const numbers = values as number[];
  if (condition === 'lt' || condition === 'gt') {
    if (numbers.length !== 1) errors.values = 'Enter one number.';
  } else if (condition === 'between') {
    if (numbers.length !== 2) errors.values = 'Enter two numbers: from and to.';
    else if (numbers[0] >= numbers[1]) errors.values = '“from” must be below “to”.';
  } else {
    const sorted = [...new Set(numbers)].sort((a, b) => a - b);
    if (sorted.length > MAX_EQUAL_VALUES) errors.values = `At most ${MAX_EQUAL_VALUES} values.`;
    else params.values = sorted;
  }
}
