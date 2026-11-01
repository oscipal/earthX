// The opacity of a layer in the box of its settings: the same row in the box of a result and in the box of a layer of scenes
// (NM4-54 part 5, Otto, 1.11.2026).

import { useAppStore } from '../store';
import type { MapLayer } from '../layers';

export default function OpacityRow({ layer }: { layer: MapLayer }) {
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  return (
    <div className="vc-opacity">
      <label className="vc-field">
        <span>Opacity</span>
        <input
          type="range"
          className="lm-opacity"
          min={0}
          max={1}
          step={0.05}
          value={layer.opacity}
          title={`Opacity ${Math.round(layer.opacity * 100)}%`}
          onChange={(e) => setOpacity(layer.id, Number(e.target.value))}
        />
      </label>
    </div>
  );
}
