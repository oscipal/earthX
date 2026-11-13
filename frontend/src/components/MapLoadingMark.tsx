// The mark on the map for a layer that loads for long (plan M5-30 §8.7, Otto, 13.11.2026): the one spinner of the page (`.spinner`), a symbol
// and no text, above the buttons at the bottom right (`docs/ui/leitfaden.md` §9). It shows for every layer, at the first load and after a zoom or a
// pan, whether the layer manager is open or not, and goes when all tiles are there or have failed (`useMapLoading.ts`).

import useMapLoading from './useMapLoading';
import { LOADING_MARK_TIP } from './useLayerLoading';

export default function MapLoadingMark() {
  if (!useMapLoading()) return null;
  return (
    <span className="map-loading" role="status" aria-label={LOADING_MARK_TIP}>
      <span className="spinner" aria-hidden="true" />
    </span>
  );
}
