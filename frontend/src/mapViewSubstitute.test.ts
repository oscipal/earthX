// Plan M5-30 §8.7 (13.11.2026): the view's raster sync is given the list of datasets. Without it `overviewSubstitute.ts` finds no substitute
// and the view draws none: nothing below the first level and, over the first level, nothing until the mosaic has arrived. The component
// cannot be rendered here (it needs a WebGL map), the browser check `e2e/layer-loading.cjs` draws it; this keeps the argument from going.

import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

describe('MapView', () => {
  it('hands the list of datasets to the sync of the view, and draws the view again when it changes', () => {
    const source = readFileSync(new URL('./components/MapView.tsx', import.meta.url), 'utf8');
    const call = /syncFocusRaster\(map, \{([\s\S]*?)\}\);\s*\}\s*\}, \[([^\]]*)\]\);/.exec(source);
    expect(call).not.toBeNull();
    expect(call![1]).toMatch(/^\s*datasets,$/m);
    expect(call![2].split(',').map((name) => name.trim())).toContain('datasets');
  });
});
