import { describe, expect, it } from 'vitest';

import { initialValues, integersIn, namesIn, numbersIn, paramsForm, paramsFrom, type Field } from './schemaForm';

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

  it('reads a oneOf of documented text constants as a choice with one sentence per option (M4-24)', () => {
    const f = fields({
      type: 'object',
      properties: {
        how: {
          type: 'string',
          description: 'No default.',
          oneOf: [
            { const: 'near', title: 'near', description: 'Nearest pixel.' },
            { const: 'far', title: 'far' },
          ],
        },
      },
      required: ['how'],
    });
    expect(f[0]).toMatchObject({ kind: 'enum', options: ['near', 'far'], optionHelp: { near: 'Nearest pixel.' } });
    expect(f[0].description).toBe('No default.');
    expect(paramsFrom(f, { how: 'far' })).toEqual({ params: { how: 'far' }, errors: {} });
    expect(paramsFrom(f, { how: 'other' }).errors).toEqual({ how: 'Pick one of the options.' });
    const bare = fields({ type: 'object', properties: { how: { oneOf: [{ const: 'a' }, { const: 'b' }] } } });
    expect(bare[0]).toMatchObject({ kind: 'enum', options: ['a', 'b'] });
    expect(bare[0].optionHelp).toBeUndefined();
  });

  it.each([
    ['oneOf', { type: 'object', properties: { x: { oneOf: [{ type: 'string' }, { type: 'number' }] } } }],
    ['a oneOf of numbers', { type: 'object', properties: { x: { oneOf: [{ const: 1 }, { const: 2 }] } } }],
    ['a oneOf with more than constants', { type: 'object', properties: { x: { oneOf: [{ const: 'a', pattern: 'a' }] } } }],
    ['an empty oneOf', { type: 'object', properties: { x: { oneOf: [] } } }],
    ['a oneOf naming a constant twice', { type: 'object', properties: { x: { oneOf: [{ const: 'a' }, { const: 'a' }] } } }],
    ['a oneOf next to an enum', { type: 'object', properties: { x: { enum: ['a'], oneOf: [{ const: 'a' }] } } }],
    ['a oneOf of type number', { type: 'object', properties: { x: { type: 'number', oneOf: [{ const: 'a' }] } } }],
    ['a nested object', { type: 'object', properties: { x: { type: 'object', properties: {} } } }],
    ['an array of objects', { type: 'object', properties: { x: { type: 'array', items: { type: 'object' } } } }],
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

// A list of whole numbers, as `mask` takes its classes (M4-18c).
describe('a list of whole numbers', () => {
  const LIST = {
    type: 'object',
    properties: {
      classes: {
        type: 'array',
        title: 'Classes',
        items: { type: 'integer', minimum: 0, maximum: 65535 },
        minItems: 1,
        maxItems: 4,
      },
    },
    required: ['classes'],
  };
  const read = (text: string) => paramsFrom(fields(LIST), { classes: text });

  it('is read with the bounds of the list and of each value', () => {
    expect(fields(LIST)[0]).toMatchObject({
      kind: 'integers',
      required: true,
      minItems: 1,
      maxItems: 4,
      itemMinimum: 0,
      itemMaximum: 65535,
    });
  });

  it('writes the numbers ascending and each once, as one recipe has one way to say it', () => {
    expect(read('10, 3,3 8;9').params).toEqual({ classes: [3, 8, 9, 10] });
    expect(read(' 7 ').params).toEqual({ classes: [7] });
  });

  it('asks for the list when it is empty', () => {
    expect(read('').errors.classes).toBe('Required.');
    expect(read(' , ').errors.classes).toBe('At least 1 values.');
  });

  it.each(['3, x', '1.5', '3 8e1', '-', '0x10', '1e2', '٣'])('refuses %j: not whole numbers', (text) => {
    expect(read(text).errors.classes).toBe('Enter whole numbers separated by commas.');
  });

  it('refuses a value outside the bounds of an item, naming it', () => {
    expect(read('3, 65536').errors.classes).toBe('65536 is outside 0 to 65535.');
    expect(read('-1').errors.classes).toBe('-1 is outside 0 to 65535.');
  });

  it('refuses more values than the list takes, counting each once', () => {
    expect(read('1 2 3 4 5').errors.classes).toBe('At most 4 values.');
    expect(read('1 1 1 1 1 2').errors.classes).toBeUndefined();
  });

  it('refuses a number too large to be exact', () => {
    expect(integersIn('9007199254740993')).toBeNull();
    expect(integersIn('')).toEqual([]);
  });

  it('starts from the default of the schema, written as the field is edited', () => {
    const withDefault = { ...LIST, properties: { classes: { ...LIST.properties.classes, default: [3, 8] } } };
    expect(initialValues(fields(withDefault))).toEqual({ classes: '3, 8' });
    expect(initialValues(fields(LIST))).toEqual({ classes: '' });
  });

  it.each([
    ['items that are neither numbers nor texts', { type: 'array', items: { type: 'object' } }],
    ['items that are booleans', { type: 'array', items: { type: 'boolean' } }],
    ['items with a keyword it does not know', { type: 'array', items: { type: 'integer', multipleOf: 2 } }],
    ['no items', { type: 'array' }],
    ['a list of lists', { type: 'array', items: { type: 'array', items: { type: 'integer' } } }],
  ])('stays "not supported by this panel" for %s', (_, property) => {
    const form = paramsForm({ type: 'object', properties: { x: property } });
    expect(form.supported).toBe(false);
  });
});

// A list of numbers, as `mask_values` takes its values (DS-06b).
describe('a list of numbers', () => {
  const LIST = {
    type: 'object',
    properties: {
      values: { type: 'array', items: { type: 'number', minimum: -100, maximum: 100 }, minItems: 1, maxItems: 3, title: 'Values' },
    },
    required: ['values'],
  };
  const fields = () => {
    const form = paramsForm(LIST);
    if (!form.supported) throw new Error(form.reason);
    return form.fields;
  };

  it('is a field of its own kind, with the bounds of the list and of each number', () => {
    expect(fields()[0]).toMatchObject({ kind: 'numbers', minItems: 1, maxItems: 3, itemMinimum: -100, itemMaximum: 100 });
  });

  it('reads the numbers as typed, with a point for the decimal mark', () => {
    expect(numbersIn('0.2, -3;  .5 1e2 +4.')).toEqual([0.2, -3, 0.5, 100, 4]);
    expect(numbersIn('')).toEqual([]);
  });

  it.each(['0,2x', 'abc', '1 2e', 'Infinity', '0x10', '--1', '1e999', 'NaN', '1_0'])('rejects %s as a number', (text) => {
    expect(numbersIn(text)).toBeNull();
  });

  it('builds the list in the order typed', () => {
    expect(paramsFrom(fields(), { values: '2, 1.5' })).toEqual({ params: { values: [2, 1.5] }, errors: {} });
  });

  it.each([
    ['', 'Required.'],
    ['abc', 'Enter numbers separated by commas.'],
    [',', 'Enter numbers separated by commas.'],
    ['1, x', 'Enter numbers separated by commas.'],
    ['101', 'Too large or too small.'],
    ['-100.5', 'Too large or too small.'],
    ['1, 2, 3, 4', 'At most 3 values.'],
  ])('refuses %j with a reason', (text, reason) => {
    expect(paramsFrom(fields(), { values: text }).errors).toEqual({ values: reason });
  });

  it('is initialised empty, or from a default', () => {
    expect(initialValues(fields())).toEqual({ values: '' });
  });
});

// A list of texts, as `normalize` takes its bands (adr/0020 §6).
describe('a list of texts', () => {
  const LIST = {
    type: 'object',
    properties: {
      bands: { type: 'array', title: 'Bands', items: { type: 'string' }, minItems: 1, maxItems: 3 },
    },
    required: ['bands'],
  };
  const read = (text: string) => paramsFrom(fields(LIST), { bands: text });

  it('is read as the names field, with the bounds of the list', () => {
    expect(fields(LIST)[0]).toMatchObject({ kind: 'names', required: true, minItems: 1, maxItems: 3 });
  });

  it('writes the names in the order typed and each once', () => {
    expect(read('nir, red;nir  red').params).toEqual({ bands: ['nir', 'red'] });
    expect(read(' NDVI ').params).toEqual({ bands: ['NDVI'] });
    expect(namesIn('b, a b,,')).toEqual(['b', 'a']);
    expect(namesIn('')).toEqual([]);
  });

  it('asks for the list when it is required and empty', () => {
    expect(read('').errors.bands).toBe('Pick at least one band.');
    expect(read(' , ').errors.bands).toBe('Pick at least one band.');
  });

  it('leaves an optional list empty out of the params', () => {
    const optional = fields({ type: 'object', properties: { bands: { type: 'array', items: { type: 'string' } } } });
    expect(paramsFrom(optional, { bands: '' })).toEqual({ params: {}, errors: {} });
  });

  it('refuses more names than the list takes, counting each once', () => {
    expect(read('a b c d').errors.bands).toBe('At most 3 bands.');
    expect(read('a a a a b').errors.bands).toBeUndefined();
  });

  it('starts from the default of the schema, written as the field is edited', () => {
    const withDefault = { ...LIST, properties: { bands: { ...LIST.properties.bands, default: ['red', 'nir'] } } };
    expect(initialValues(fields(withDefault))).toEqual({ bands: 'red, nir' });
    expect(initialValues(fields(LIST))).toEqual({ bands: '' });
  });

  it('stays "not supported by this panel" for items with a keyword it does not know', () => {
    const form = paramsForm({ type: 'object', properties: { x: { type: 'array', items: { type: 'string', minLength: 2 } } } });
    expect(form.supported).toBe(false);
  });
});
