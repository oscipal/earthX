// UI-02a: a change of the basemap is a style diff, and MapLibre fires `style.load` after it as well. `MapView` lays the
// app's layers on the first load only; this is how it tells the two apart.

import { describe, expect, it } from 'vitest';

import { ensureBaseLayers, hasOwnLayers } from './mapLayers';
import { liveMap } from './fixtures/liveMap';

describe('hasOwnLayers', () => {
  it('is false on a map that has none of the app\'s layers yet (the first style load)', () => {
    const { map } = liveMap([]);
    expect(hasOwnLayers(map as never)).toBe(false);
  });

  it('is true once the base layers are laid, and stays true for every later style load', () => {
    const { map, log } = liveMap([]);
    ensureBaseLayers(map as never);
    expect(hasOwnLayers(map as never)).toBe(true);
    const added = log.sourcesAdded.length;
    ensureBaseLayers(map as never);
    expect(hasOwnLayers(map as never)).toBe(true);
    // Laid again: nothing is added a second time.
    expect(log.sourcesAdded).toHaveLength(added);
  });

  it('is not fooled by a basemap\'s sources', () => {
    const { map } = liveMap([]);
    map.addSource('bm-satellite', { type: 'raster' });
    expect(hasOwnLayers(map as never)).toBe(false);
  });
});
