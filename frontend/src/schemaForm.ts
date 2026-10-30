// A small form built from an operator's parameter schema (M4-13 F1 (1)): only
// the JSON Schema keywords the flat parameters of today's operators use. A
// schema with anything else is "not supported by this panel" — the operator
// stays in the menu, disabled, with the reason, instead of a form that would
// silently drop what it cannot show.
//
// Checks here are a help while typing; the server decides (`422`/`400` with a
// text shown at the step). No `eval`, no `new Function`.

import type { JsonSchema } from './processing';

export type FieldKind = 'string' | 'number' | 'integer' | 'integers' | 'names' | 'boolean' | 'enum' | 'const';

export interface Field {
  name: string;
  kind: FieldKind;
  title: string;
  description?: string;
  required: boolean;
  default?: unknown;
  options?: string[];
  // One sentence per option, from a `oneOf` of documented constants (M4-24).
  optionHelp?: Record<string, string>;
  constValue?: unknown;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  minimum?: number;
  maximum?: number;
  exclusiveMinimum?: number;
  exclusiveMaximum?: number;
  // `integers` and `names`: a list of whole numbers or of texts, with the bounds of the list (and of each number).
  minItems?: number;
  maxItems?: number;
  itemMinimum?: number;
  itemMaximum?: number;
}

export type ParamsForm = { supported: true; fields: Field[] } | { supported: false; reason: string };

// What a field's value is while it is edited: text for text and number
// inputs, a boolean for a checkbox.
export type FieldValue = string | boolean;

const OBJECT_KEYWORDS = new Set(['type', 'title', 'description', 'properties', 'required', 'additionalProperties']);
const FIELD_KEYWORDS = new Set([
  'type',
  'title',
  'description',
  'default',
  'enum',
  'oneOf',
  'const',
  'minLength',
  'maxLength',
  'pattern',
  'minimum',
  'maximum',
  'exclusiveMinimum',
  'exclusiveMaximum',
  'items',
  'minItems',
  'maxItems',
]);

const isObject = (value: unknown): value is JsonSchema =>
  !!value && typeof value === 'object' && !Array.isArray(value);

// `$ref` within the same document only (`#/$defs/<name>`), one level deep.
function resolve(schema: JsonSchema, defs: JsonSchema): JsonSchema | string {
  const ref = schema.$ref;
  if (ref === undefined) return schema;
  if (Object.keys(schema).length !== 1) return '$ref next to other keywords';
  if (typeof ref !== 'string' || !ref.startsWith('#/$defs/')) return `$ref ${String(ref)}`;
  const target = defs[ref.slice('#/$defs/'.length)];
  if (!isObject(target) || target.$ref !== undefined) return `$ref ${ref}`;
  return target;
}

function unsupported(reason: string): ParamsForm {
  return { supported: false, reason: `not supported by this panel: ${reason}` };
}

function numberOrUndefined(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined;
}

function fieldOf(name: string, schema: JsonSchema, required: boolean): Field | string {
  const extra = Object.keys(schema).find((key) => !FIELD_KEYWORDS.has(key));
  if (extra) return `keyword ${extra} in ${name}`;
  const base = {
    name,
    title: typeof schema.title === 'string' ? schema.title : name,
    ...(typeof schema.description === 'string' ? { description: schema.description } : {}),
    required,
    ...('default' in schema ? { default: schema.default } : {}),
  };
  if ('const' in schema) return { ...base, kind: 'const', constValue: schema.const };
  if ('oneOf' in schema) return documentedChoice(name, schema, base);
  if ('enum' in schema) {
    const options = schema.enum;
    if (!Array.isArray(options) || options.length === 0 || !options.every((o) => typeof o === 'string')) {
      return `enum of ${name} is not a list of texts`;
    }
    if (schema.type !== undefined && schema.type !== 'string') return `enum of type ${String(schema.type)}`;
    return { ...base, kind: 'enum', options: options as string[] };
  }
  switch (schema.type) {
    case 'string':
      return {
        ...base,
        kind: 'string',
        minLength: numberOrUndefined(schema.minLength),
        maxLength: numberOrUndefined(schema.maxLength),
        ...(typeof schema.pattern === 'string' ? { pattern: schema.pattern } : {}),
      };
    case 'number':
    case 'integer':
      return {
        ...base,
        kind: schema.type,
        minimum: numberOrUndefined(schema.minimum),
        maximum: numberOrUndefined(schema.maximum),
        exclusiveMinimum: numberOrUndefined(schema.exclusiveMinimum),
        exclusiveMaximum: numberOrUndefined(schema.exclusiveMaximum),
      };
    case 'boolean':
      return { ...base, kind: 'boolean' };
    case 'array':
      return listField(name, schema, base);
    default:
      return `type ${JSON.stringify(schema.type ?? null)} of ${name}`;
  }
}

// A list of whole numbers, as `mask` takes its classes: `items` is an integer with bounds, nothing
// else. It is edited as text, "3, 8, 9, 10". Or a list of texts, as `normalize` takes its bands: `items` is a plain
// string, and the panel offers the names to pick from (`StepForm`).
const ITEM_KEYWORDS = new Set(['type', 'minimum', 'maximum']);

function listField(name: string, schema: JsonSchema, base: Omit<Field, 'kind'>): Field | string {
  const items = schema.items;
  if (isObject(items) && items.type === 'string' && Object.keys(items).length === 1) {
    return { ...base, kind: 'names', minItems: numberOrUndefined(schema.minItems), maxItems: numberOrUndefined(schema.maxItems) };
  }
  if (!isObject(items) || items.type !== 'integer' || Object.keys(items).some((key) => !ITEM_KEYWORDS.has(key))) {
    return `items of ${name} are not whole numbers`;
  }
  return {
    ...base,
    kind: 'integers',
    minItems: numberOrUndefined(schema.minItems),
    maxItems: numberOrUndefined(schema.maxItems),
    itemMinimum: numberOrUndefined(items.minimum),
    itemMaximum: numberOrUndefined(items.maximum),
  };
}

// The numbers of a list field's text, in the order typed; `null` where a part is not a whole number.
export function integersIn(text: string): number[] | null {
  const parts = text.split(/[\s,;]+/u).filter((part) => part !== '');
  const numbers = parts.map((part) => (/^[+-]?\d+$/u.test(part) ? Number(part) : NaN));
  return numbers.every(Number.isSafeInteger) ? numbers : null;
}

// The names of a list field's text ("a, b"), each once, in the order typed.
export function namesIn(text: string): string[] {
  return [...new Set(text.split(/[\s,;]+/u).filter((part) => part !== ''))];
}

// A choice written as `oneOf` of constants, each with its own `title` and
// `description` (JSON Schema 2020-12), as `reproject` describes its methods:
// an enum whose options carry a sentence each. Any other `oneOf` is not supported.
const OPTION_KEYWORDS = new Set(['const', 'title', 'description']);

function documentedChoice(name: string, schema: JsonSchema, base: Omit<Field, 'kind'>): Field | string {
  const variants = schema.oneOf;
  if (schema.type !== undefined && schema.type !== 'string') return `oneOf of type ${String(schema.type)}`;
  if ('enum' in schema) return `enum next to oneOf in ${name}`;
  if (!Array.isArray(variants) || variants.length === 0) return `oneOf of ${name} is not a list of constants`;
  const options: string[] = [];
  const optionHelp: Record<string, string> = {};
  for (const variant of variants) {
    if (
      !isObject(variant) ||
      typeof variant.const !== 'string' ||
      Object.keys(variant).some((key) => !OPTION_KEYWORDS.has(key)) ||
      (variant.description !== undefined && typeof variant.description !== 'string')
    ) {
      return `oneOf of ${name} is not a list of text constants`;
    }
    if (options.includes(variant.const)) return `oneOf of ${name} names ${variant.const} twice`;
    options.push(variant.const);
    if (typeof variant.description === 'string') optionHelp[variant.const] = variant.description;
  }
  return { ...base, kind: 'enum', options, ...(Object.keys(optionHelp).length > 0 ? { optionHelp } : {}) };
}

// The form for one step's `params` schema, `defs` being the `$defs` of the
// order's schema.
export function paramsForm(schema: unknown, defs: JsonSchema = {}): ParamsForm {
  if (!isObject(schema)) return unsupported('no parameter schema');
  const resolved = resolve(schema, defs);
  if (typeof resolved === 'string') return unsupported(resolved);
  const extra = Object.keys(resolved).find((key) => !OBJECT_KEYWORDS.has(key));
  if (extra) return unsupported(`keyword ${extra}`);
  if (resolved.type !== 'object') return unsupported(`parameters of type ${JSON.stringify(resolved.type ?? null)}`);
  const properties = resolved.properties ?? {};
  if (!isObject(properties)) return unsupported('properties is not an object');
  const required = Array.isArray(resolved.required) ? resolved.required : [];
  const fields: Field[] = [];
  for (const [name, raw] of Object.entries(properties)) {
    if (!isObject(raw)) return unsupported(`property ${name}`);
    const property = resolve(raw, defs);
    if (typeof property === 'string') return unsupported(property);
    const field = fieldOf(name, property, required.includes(name));
    if (typeof field === 'string') return unsupported(field);
    fields.push(field);
  }
  return { supported: true, fields };
}

// The values a fresh step starts with: the schema's `default` where it has one,
// empty otherwise — including a choice like `resampling` that has none on
// purpose ("the choice changes the values", B10).
export function initialValues(fields: readonly Field[]): Record<string, FieldValue> {
  const values: Record<string, FieldValue> = {};
  for (const field of fields) {
    if (field.kind === 'boolean') values[field.name] = field.default === true;
    else if (field.kind === 'const') continue;
    else if (Array.isArray(field.default)) values[field.name] = field.default.join(', ');
    else if (field.default !== undefined && field.default !== null) values[field.name] = String(field.default);
    else values[field.name] = '';
  }
  return values;
}

// What to say of a text that does not fit a pattern the panel knows, instead of the pattern itself.
const PATTERN_HINTS: Readonly<Record<string, string>> = {
  '^EPSG:[0-9]{4,6}$': 'Needs to be in the format "EPSG:3035"',
};

function compiled(pattern: string): RegExp | null {
  try {
    return new RegExp(pattern, 'u');
  } catch {
    return null; // a pattern this browser cannot compile is left to the server
  }
}

function parseNumber(field: Field, text: string): number | string {
  const value = Number(text);
  if (text.trim() === '' || !Number.isFinite(value)) return 'Enter a number.';
  if (field.kind === 'integer' && !Number.isInteger(value)) return 'Enter a whole number.';
  if (field.minimum !== undefined && value < field.minimum) return `At least ${field.minimum}.`;
  if (field.maximum !== undefined && value > field.maximum) return `At most ${field.maximum}.`;
  if (field.exclusiveMinimum !== undefined && value <= field.exclusiveMinimum) {
    return `More than ${field.exclusiveMinimum}.`;
  }
  if (field.exclusiveMaximum !== undefined && value >= field.exclusiveMaximum) {
    return `Less than ${field.exclusiveMaximum}.`;
  }
  return value;
}

// The value a field contributes to `params`, `undefined` for an optional field
// left empty, or a message why the input does not fit.
function valueOf(field: Field, raw: FieldValue | undefined): { value?: unknown; error?: string } {
  if (field.kind === 'const') return { value: field.constValue };
  if (field.kind === 'boolean') return { value: raw === true };
  const text = typeof raw === 'string' ? raw : '';
  if (text === '') return field.required ? { error: field.kind === 'names' ? 'Pick at least one band.' : 'Required.' } : {};
  switch (field.kind) {
    case 'enum':
      return field.options?.includes(text) ? { value: text } : { error: 'Pick one of the options.' };
    case 'number':
    case 'integer': {
      const value = parseNumber(field, text);
      return typeof value === 'string' ? { error: value } : { value };
    }
    case 'integers': {
      const numbers = integersIn(text);
      if (numbers === null) return { error: 'Enter whole numbers separated by commas.' };
      const out = numbers.find(
        (n) => (field.itemMinimum !== undefined && n < field.itemMinimum) || (field.itemMaximum !== undefined && n > field.itemMaximum),
      );
      if (out !== undefined) return { error: `${out} is outside ${field.itemMinimum ?? '-∞'} to ${field.itemMaximum ?? '∞'}.` };
      // One way to write a list: ascending, each value once (the server insists on it, K3 of M4-18).
      const value = [...new Set(numbers)].sort((a, b) => a - b);
      if (field.minItems !== undefined && value.length < field.minItems) return { error: `At least ${field.minItems} values.` };
      if (field.maxItems !== undefined && value.length > field.maxItems) return { error: `At most ${field.maxItems} values.` };
      return { value };
    }
    case 'names': {
      const value = namesIn(text);
      if (field.minItems !== undefined && value.length < field.minItems) return { error: 'Pick at least one band.' };
      if (field.maxItems !== undefined && value.length > field.maxItems) return { error: `At most ${field.maxItems} bands.` };
      return { value };
    }
    case 'string': {
      const length = [...text].length;
      if (field.minLength !== undefined && length < field.minLength) return { error: `At least ${field.minLength} characters.` };
      if (field.maxLength !== undefined && length > field.maxLength) return { error: `At most ${field.maxLength} characters.` };
      const pattern = field.pattern ? compiled(field.pattern) : null;
      if (pattern && !pattern.test(text)) return { error: PATTERN_HINTS[field.pattern ?? ''] ?? `Does not match ${field.pattern}.` };
      return { value: text };
    }
  }
}

export interface ParamsResult {
  params: Record<string, unknown>;
  errors: Record<string, string>;
}

export function paramsFrom(fields: readonly Field[], values: Readonly<Record<string, FieldValue>>): ParamsResult {
  const params: Record<string, unknown> = {};
  const errors: Record<string, string> = {};
  for (const field of fields) {
    const { value, error } = valueOf(field, values[field.name]);
    if (error) errors[field.name] = error;
    else if (value !== undefined) params[field.name] = value;
  }
  return { params, errors };
}
