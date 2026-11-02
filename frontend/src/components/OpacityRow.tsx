// The opacity of a layer in the settings bar: the same row for a result and for a layer of scenes (NM4-54 part 5, Otto, 1.11.2026).
// The view of the search is no layer and has none: the row stays, locked, with the reason (Otto, 2.11.2026).

import { useAppStore } from '../store';
import type { MapLayer } from '../layers';

export const OPACITY_LOCKED_TIP = 'Add to layers to set the opacity';
// The image of the view is pinned already: its layer has the opacity, set where the layer is opened from the layer manager.
export const OPACITY_PINNED_TIP = 'Open this layer from the layer manager to set its opacity';

export default function OpacityRow({ layer, locked }: { layer?: MapLayer; locked?: string }) {
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const opacity = layer?.opacity ?? 1;
  const title = locked ?? `Opacity ${Math.round(opacity * 100)}%`;
  return (
    <div className="vc-opacity">
      <label className="vc-field" title={title}>
        <span>Opacity</span>
        <input
          type="range"
          className="lm-opacity"
          min={0}
          max={1}
          step={0.05}
          value={opacity}
          title={title}
          disabled={locked !== undefined}
          onChange={(e) => {
            if (layer) setOpacity(layer.id, Number(e.target.value));
          }}
        />
      </label>
    </div>
  );
}
