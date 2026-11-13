// Whether the mark on the map shows: any visible layer is loading (`layerLoading.ts::isMapLoading`) and has been for the wait every loading
// mark of the page keeps (`usePreviewLoading.ts::LOADING_AFTER_MS`). A zoom or a pan that asks for new tiles starts the wait again.

import { isMapLoading } from '../layerLoading';
import { useAppStore } from '../store';
import { useAfterDelay } from './usePreviewLoading';

export default function useMapLoading(): boolean {
  return useAfterDelay(useAppStore(isMapLoading));
}
