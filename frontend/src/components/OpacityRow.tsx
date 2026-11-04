// The opacity in the settings bar: the same row for a result, a layer of scenes (NM4-54 part 5, Otto, 1.11.2026) and the view of the
// search, which is no layer and has an opacity of its own (Otto, 2.11.2026; replaces the locked row of the same day).

import { useAppStore } from '../store';
import type { MapLayer } from '../layers';

export default function OpacityRow({ layer }: { layer?: MapLayer }) {
  const setLayerOpacity = useAppStore((s) => s.setLayerOpacity);
  const viewOpacity = useAppStore((s) => s.viewOpacity);
  const setViewOpacity = useAppStore((s) => s.setViewOpacity);
  const opacity = layer ? layer.opacity : viewOpacity;
  const title = `Opacity ${Math.round(opacity * 100)}%`;
  return (
    <div className="vc-opacity">
      <label className="vc-field" data-tip={title}>
        <span>Opacity</span>
        <input
          type="range"
          className="lm-opacity"
          min={0}
          max={1}
          step={0.05}
          value={opacity}
          data-tip={title}
          onChange={(e) => {
            const value = Number(e.target.value);
            if (layer) setLayerOpacity(layer.id, value);
            else setViewOpacity(value);
          }}
        />
      </label>
    </div>
  );
}
