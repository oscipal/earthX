import { describe, expect, it } from 'vitest';

import { betweenParts, betweenText, hasComma, oneNumber, refineMaskValues, valuesAfterConditionChange } from './maskValues';

function refine(condition: string, values: number[]) {
  const params: Record<string, unknown> = { band: 'NDVI', condition, values };
  const errors: Record<string, string> = {};
  refineMaskValues(params, errors);
  return { values: params.values, errors };
}

describe('the numbers a condition takes', () => {
  it.each(['lt', 'gt'])('takes exactly one number for %s', (condition) => {
    expect(refine(condition, [0.2])).toEqual({ values: [0.2], errors: {} });
    expect(refine(condition, []).errors.values).toBe('Enter one number.');
    expect(refine(condition, [1, 2]).errors.values).toBe('Enter one number.');
  });

  it('takes two numbers for between, the lower first', () => {
    expect(refine('between', [0.2, 0.8])).toEqual({ values: [0.2, 0.8], errors: {} });
    expect(refine('between', [0.2]).errors.values).toBe('Enter two numbers: from and to.');
    expect(refine('between', [1, 2, 3]).errors.values).toBe('Enter two numbers: from and to.');
    expect(refine('between', [0.8, 0.2]).errors.values).toContain('must be below');
    expect(refine('between', [0.5, 0.5]).errors.values).toContain('must be below');
  });

  it('writes the numbers of eq ascending and each once, as the server insists', () => {
    expect(refine('eq', [9, 3, 8, 3])).toEqual({ values: [3, 8, 9], errors: {} });
    expect(refine('eq', [-1, -1])).toEqual({ values: [-1], errors: {} });
  });

  it('allows 64 numbers for eq, not 65', () => {
    expect(refine('eq', Array.from({ length: 64 }, (_, i) => i)).errors).toEqual({});
    expect(refine('eq', Array.from({ length: 65 }, (_, i) => i)).errors.values).toBe('At most 64 values.');
    // The duplicates do not count: the server sees the list without them.
    expect(refine('eq', [...Array.from({ length: 64 }, (_, i) => i), 0]).errors).toEqual({});
  });

  it('leaves a step alone whose condition or numbers are not there yet', () => {
    const params: Record<string, unknown> = { band: 'x', condition: 'sideways', values: [1] };
    const errors: Record<string, string> = {};
    refineMaskValues(params, errors);
    expect(errors).toEqual({});
    expect(params.values).toEqual([1]);
  });
});

describe('the text of the numbers', () => {
  it('keeps what fits when the condition changes', () => {
    expect(valuesAfterConditionChange('0.2', 'between')).toBe('0.2; ');
    expect(valuesAfterConditionChange('0.2; 0.8', 'lt')).toBe('0.2');
    expect(valuesAfterConditionChange('3, 8, 9', 'between')).toBe('3; 8');
    expect(valuesAfterConditionChange('3, 8, 9', 'gt')).toBe('3');
    expect(valuesAfterConditionChange('0.2; 0.8', 'eq')).toBe('0.2; 0.8');
    expect(valuesAfterConditionChange('', 'between')).toBe('');
  });

  it('splits between into its two boxes by position', () => {
    expect(betweenParts('0.2; 0.8')).toEqual(['0.2', '0.8']);
    expect(betweenParts('; 0.8')).toEqual(['', '0.8']);
    expect(betweenParts('0.2; ')).toEqual(['0.2', '']);
    // A recipe lists the numbers with commas.
    expect(betweenParts('0.2, 0.8')).toEqual(['0.2', '0.8']);
    expect(betweenParts('')).toEqual(['', '']);
    expect(betweenText('', '')).toBe('');
    expect(betweenText('', '0.8')).toBe('; 0.8');
  });

  it('keeps a box for one number free of separators and tells a comma', () => {
    expect(oneNumber(' 0.2; ')).toBe('0.2');
    expect(oneNumber('0,2')).toBe('0,2');
    expect(hasComma('0,2')).toBe(true);
    expect(hasComma('0.2')).toBe(false);
  });
});
