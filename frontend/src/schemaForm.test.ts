import { describe, expect, it } from 'vitest';

import { initialValues, paramsForm, paramsFrom, type Field } from './schemaForm';

function fields(schema: unknown, defs = {}): Field[] {
  const form = paramsForm(schema, defs);
  if (!form.supported) throw new Error(form.reason);
  return form.fields;
}

const PARAMS = {
  type: 'object',
  additionalProperties: false,
  properties: {
    text: { type: 'string', minLength: 2, maxLength: 4, pattern: '^[a-z]+$' },
    count: { type: 'integer', minimum: 1, maximum: 3 },
    size: { type: 'number', exclusiveMinimum: 0, exclusiveMaximum: 10 },
    flag: { type: 'boolean', default: true },
    pick: { type: 'string', enum: ['a', 'b'] },
    fixed: { const: 7 },
    note: { type: 'string', default: 'hi' },
  },
  required: ['text', 'count', 'size', 'pick'],
};

describe('paramsForm', () => {
  it('reads each supported kind with its constraints', () => {
    const f = fields(PARAMS);
    expect(f.map((x) => [x.name, x.kind, x.required])).toEqual([
      ['text', 'string', true],
      ['count', 'integer', true],
      ['size', 'number', true],
      ['flag', 'boolean', false],
      ['pick', 'enum', true],
      ['fixed', 'const', false],
      ['note', 'string', false],
    ]);
    expect(f[0]).toMatchObject({ minLength: 2, maxLength: 4, pattern: '^[a-z]+$' });
    expect(f[2]).toMatchObject({ exclusiveMinimum: 0, exclusiveMaximum: 10 });
  });

  it('resolves a $ref into $defs', () => {
    const f = fields({ $ref: '#/$defs/P' }, { P: { type: 'object', properties: { x: { $ref: '#/$defs/X' } } }, X: { type: 'number' } });
    expect(f[0]).toMatchObject({ name: 'x', kind: 'number' });
  });

  it.each([
    ['oneOf', { type: 'object', properties: { x: { oneOf: [{ type: 'string' }, { type: 'number' }] } } }],
    ['a nested object', { type: 'object', properties: { x: { type: 'object', properties: {} } } }],
    ['an array', { type: 'object', properties: { x: { type: 'array', items: { type: 'number' } } } }],
    ['a keyword on the object', { type: 'object', properties: {}, if: {} }],
    ['an enum of numbers', { type: 'object', properties: { x: { enum: [1, 2] } } }],
    ['a $ref outside the document', { type: 'object', properties: { x: { $ref: 'https://example.org/s.json' } } }],
    ['a $ref to nothing', { type: 'object', properties: { x: { $ref: '#/$defs/Missing' } } }],
    ['no schema', undefined],
    ['parameters that are not an object', { type: 'string' }],
  ])('marks %s as not supported, with the reason', (_, schema) => {
    const form = paramsForm(schema);
    expect(form.supported).toBe(false);
    if (!form.supported) expect(form.reason).toMatch(/^not supported by this panel: /);
  });
});

describe('initialValues', () => {
  it('starts from the defaults and leaves the rest empty, also a choice without default', () => {
    expect(initialValues(fields(PARAMS))).toEqual({ text: '', count: '', size: '', flag: true, pick: '', note: 'hi' });
  });
});

describe('paramsFrom', () => {
  const f = fields(PARAMS);
  const good = { text: 'ab', count: '2', size: '0.5', flag: false, pick: 'b', note: '' };

  it('builds the params with numbers as numbers, the const, and no empty optional field', () => {
    expect(paramsFrom(f, good)).toEqual({
      params: { text: 'ab', count: 2, size: 0.5, flag: false, pick: 'b', fixed: 7 },
      errors: {},
    });
  });

  it.each([
    ['a missing required field', { text: '' }, 'text', 'Required.'],
    ['a text too short', { text: 'a' }, 'text', 'At least 2 characters.'],
    ['a text too long', { text: 'abcde' }, 'text', 'At most 4 characters.'],
    ['a text off the pattern', { text: 'AB' }, 'text', 'Does not match ^[a-z]+$.'],
    ['a fraction for an integer', { count: '1.5' }, 'count', 'Enter a whole number.'],
    ['a number under the minimum', { count: '0' }, 'count', 'At least 1.'],
    ['a number over the maximum', { count: '4' }, 'count', 'At most 3.'],
    ['no number at all', { size: 'ten' }, 'size', 'Enter a number.'],
    ['the exclusive minimum itself', { size: '0' }, 'size', 'More than 0.'],
    ['the exclusive maximum itself', { size: '10' }, 'size', 'Less than 10.'],
    ['an option the enum does not list', { pick: 'c' }, 'pick', 'Pick one of the options.'],
    ['infinity', { size: 'Infinity' }, 'size', 'Enter a number.'],
  ])('reports %s', (_, change, name, message) => {
    expect(paramsFrom(f, { ...good, ...change }).errors).toEqual({ [name]: message });
  });

  it('counts characters, not UTF-16 units, as the server does', () => {
    const one = fields({ type: 'object', properties: { t: { type: 'string', maxLength: 2 } } });
    expect(paramsFrom(one, { t: '😀😀' }).errors).toEqual({});
  });

  it('leaves a pattern this browser cannot compile to the server', () => {
    const odd = fields({ type: 'object', properties: { t: { type: 'string', pattern: '(?P<x>a)' } } });
    expect(paramsFrom(odd, { t: 'anything' }).errors).toEqual({});
  });
});
