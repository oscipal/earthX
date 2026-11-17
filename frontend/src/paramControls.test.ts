// What a parameter of a step preset is offered as (M5-14, Otto, 17.11.2026), and the arithmetic of the dial: north up, clockwise, whole
// degrees from 0 to 359, arrows ±1°, with Shift ±15°.

import { describe, expect, it } from 'vitest';

import dem from './fixtures/processes/cop-dem-glo-30.json';
import { angleAfterKey, angleAt, controlOf } from './paramControls';
import type { ProcessDescription } from './processing';
import { processInfo } from './processingOrder';
import type { Field } from './schemaForm';

const form = processInfo(dem as unknown as ProcessDescription).operators.find((o) => o.op === 'terrain')!.form;
if (!form.supported) throw new Error(form.reason);
const FIELDS = form.fields;
const field = (name: string): Field => FIELDS.find((f) => f.name === name)!;

describe('the control of a parameter', () => {
  it('is a dial for the azimuth, a slider for the altitude and segments for the unit of the slope, from the form of terrain alone', () => {
    expect([controlOf(field('azimuth')), controlOf(field('altitude')), controlOf(field('slope_unit'))]).toEqual(['dial', 'slider', 'choice']);
    expect(field('azimuth').unit).toBe('deg');
    expect(field('altitude')).toMatchObject({ unit: 'deg', minimum: 0, maximum: 90 });
  });

  it('is none for a number without two bounds or a choice of one', () => {
    expect(controlOf(field('z_factor'))).toBeNull();
    expect(controlOf({ name: 'x', kind: 'enum', title: 'X', required: true, options: ['only'] })).toBeNull();
    expect(controlOf({ name: 'x', kind: 'string', title: 'X', required: true })).toBeNull();
  });

  it('is a slider, not a dial, for an angle that is no full circle or has no unit of degrees', () => {
    expect(controlOf({ name: 'a', kind: 'number', title: 'A', required: true, minimum: 0, exclusiveMaximum: 360 })).toBeNull();
    expect(controlOf({ name: 'a', kind: 'number', title: 'A', required: true, unit: 'deg', minimum: 0, maximum: 180 })).toBe('slider');
  });
});

describe('the dial', () => {
  it('has north up and grows clockwise', () => {
    expect([angleAt(0, -10), angleAt(10, 0), angleAt(0, 10), angleAt(-10, 0), angleAt(-10, -10)]).toEqual([0, 90, 180, 270, 315]);
  });

  it('gives whole degrees from 0 to 359, and 0 at the centre itself', () => {
    expect(angleAt(-0.001, -10)).toBe(0);
    expect(angleAt(0, 0)).toBe(0);
  });

  it('steps one degree per arrow and fifteen with Shift, round the circle', () => {
    expect(angleAfterKey(315, 'ArrowRight', false)).toBe(316);
    expect(angleAfterKey(315, 'ArrowUp', false)).toBe(316);
    expect(angleAfterKey(315, 'ArrowLeft', true)).toBe(300);
    expect(angleAfterKey(355, 'ArrowRight', true)).toBe(10);
    expect(angleAfterKey(0, 'ArrowDown', false)).toBe(359);
  });

  it('takes no other key', () => {
    expect(angleAfterKey(315, 'Enter', false)).toBeNull();
    expect(angleAfterKey(315, 'a', true)).toBeNull();
  });
});
