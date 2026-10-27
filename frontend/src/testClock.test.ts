// The jobs of `fixtures/jobEntries.ts` are dated by a fixed `NOW` and expire 7 days after it. A test that
// builds them and lets the code read the real clock goes red on the day they expire (27 Oct 2026, 21 tests
// of `ResultControls.test.tsx`). Such a test sets the clock to `NOW`: `vi.useFakeTimers({ toFake: ['Date'], now: NOW })`.

import { describe, expect, it } from 'vitest';

const tests = import.meta.glob(['./**/*.test.ts', './**/*.test.tsx', '!./testClock.test.ts'], {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>;

const USES_FIXTURE = /from '(\.\.?\/)+fixtures\/jobEntries'/u;
const PINS_CLOCK = /useFakeTimers\(|setSystemTime\(/u;

// Tests of pure functions that get `NOW` as an argument and never read the clock.
const PASSES_NOW = ['./components/jobView.test.ts'];

describe('the tests that use the jobs of the fixture', () => {
  it('have tests to read', () => {
    expect(Object.keys(tests).length).toBeGreaterThan(40);
  });

  it('set the clock to NOW, or give NOW to what they call', () => {
    const unpinned = Object.entries(tests)
      .filter(([file, text]) => USES_FIXTURE.test(text) && !PINS_CLOCK.test(text) && !PASSES_NOW.includes(file))
      .map(([file]) => file);
    expect(unpinned).toEqual([]);
  });

  it('name no file in the list of pure tests that does not use the fixture any more', () => {
    expect(PASSES_NOW.filter((file) => !USES_FIXTURE.test(tests[file] ?? ''))).toEqual([]);
  });

  it('catches a test that builds the jobs and leaves the clock alone', () => {
    const text = "import { finished } from '../fixtures/jobEntries';\nit('x', () => finished(1));";
    expect(USES_FIXTURE.test(text) && !PINS_CLOCK.test(text)).toBe(true);
    expect(PINS_CLOCK.test(`${text}\nvi.useFakeTimers({ toFake: ['Date'], now: NOW });`)).toBe(true);
  });
});
