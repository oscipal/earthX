// The mark of a map layer that is loading (plan M5-30 §8.7, Otto, 13.11.2026): the one spinner of the page (`.spinner`, as in the status
// bar), a symbol and no text (`docs/ui/leitfaden.md` §9). It sits in the place of the note of the row (`LayerManager.tsx`) and goes when
// the tiles are there or have failed (`useLayerLoading.ts`).

import { LOADING_MARK_TIP } from './useLayerLoading';

export default function LoadingMark({ col }: { col: string }) {
  return <span className="spinner loading-mark" data-col={col} role="status" aria-label={LOADING_MARK_TIP} data-tip-level="advanced" data-tip={LOADING_MARK_TIP} />;
}
