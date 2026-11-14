// Whether the row `owner` of the layer manager shows its loading mark: its layer is loading (`layerLoading.ts`) and has been for the wait every
// loading mark of the page keeps (`usePreviewLoading.ts::LOADING_AFTER_MS`).

import { isOwnerLoading } from '../layerLoading';
import { useAppStore } from '../store';
import { useAfterDelay } from './usePreviewLoading';

export const LOADING_MARK_TIP = 'Loading the image';

export default function useLayerLoading(owner: string): boolean {
  return useAfterDelay(useAppStore((s) => isOwnerLoading(s, owner)));
}
