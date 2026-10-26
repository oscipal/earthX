// UI-01 §1 point 12: a finished job offers "Download (ZIP)" and nothing else. The methods text stays in the
// ZIP; no part of the frontend reads it, links it or copies it. The rendered rows are checked where they are
// tested (`ProcessingManager.test.tsx`, `JobDetails.test.tsx`, `ProcessingPanel.test.tsx`); this reads the code.

import { describe, expect, it } from 'vitest';

const sources = import.meta.glob(['./**/*.ts', './**/*.tsx', '!./**/*.test.ts', '!./**/*.test.tsx'], {
  eager: true,
  query: '?raw',
  import: 'default',
}) as Record<string, string>;

describe('the frontend code', () => {
  it('has a source to read', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(40);
  });

  it('has no "Methods" as the text of an element, also on a line of its own', () => {
    const found = Object.entries(sources)
      .filter(([, text]) => /^\s*Methods\s*$/mu.test(text) || />\s*Methods\s*</u.test(text))
      .map(([file]) => file);
    expect(found).toEqual([]);
  });

  it.each(['methods.txt', 'fetchMethodsText', 'METHODS_FILE', 'CopyMethods', "'Methods'", '>Methods<'])(
    'has nothing that reads, links or copies the methods text: %s',
    (needle) => {
      const found = Object.entries(sources)
        .filter(([, text]) => text.includes(needle))
        .map(([file]) => file);
      expect(found).toEqual([]);
    },
  );
});
