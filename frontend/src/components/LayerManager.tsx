import { canDownloadLayer } from '../download';
import { useAppStore } from '../store';
import Draggable from './Draggable';

export default function LayerManager() {
  const open = useAppStore((s) => s.layerManagerOpen);
  const layers = useAppStore((s) => s.layers);
  const toggle = useAppStore((s) => s.toggleLayerManager);
  const remove = useAppStore((s) => s.removeLayer);
  const toggleVis = useAppStore((s) => s.toggleLayerVisible);
  const setOpacity = useAppStore((s) => s.setLayerOpacity);
  const move = useAppStore((s) => s.moveLayer);
  const select = useAppStore((s) => s.selectLayer);
  const openDownload = useAppStore((s) => s.openDownloadDialog);
  const datasetId = useAppStore((s) => s.datasetId);
  const showCoverage = useAppStore((s) => s.showCoverage);
  const toggleCoverage = useAppStore((s) => s.toggleCoverage);

  // `Draggable` stays mounted regardless of `open` and is only hidden with
  // CSS: unmounting it (the previous `if (!open) return null`) threw away
  // its drag offset every time the panel closed, so a moved panel snapped
  // back to its original spot the next time it opened.
  return (
    <Draggable className={`layer-dock${open ? '' : ' layer-dock-hidden'}`}>
      <div className="panel layer-manager">
        <div className="results-head">
          <h2>Layers</h2>
          <div className="results-head-right">
            <span>{layers.length}</span>
            <button type="button" className="link-btn" title="Close" onClick={() => toggle()}>
              ✕
            </button>
          </div>
        </div>

        {/* Off by default (M2-07c); a plain toggle row rather than a list
            entry, since it isn't a pinned layer and has no opacity/order. */}
        {datasetId && (
          <div className="layer-row coverage-row">
            <button
              type="button"
              className={`lm-eye${showCoverage ? '' : ' off'}`}
              title={showCoverage ? 'Hide' : 'Show'}
              onClick={() => toggleCoverage()}
            >
              {showCoverage ? '●' : '○'}
            </button>
            <span className="lm-name">Coverage heatmap</span>
          </div>
        )}

        {layers.length === 0 ? (
          <p className="hint-text lm-empty">
            No layers yet — select an image and “Add to layers”.
          </p>
        ) : (
          <ul className="layer-list">
            {layers.map((l, i) => (
              <li key={l.id} className="layer-row">
                <button
                  type="button"
                  className={`lm-eye${l.visible ? '' : ' off'}`}
                  title={l.visible ? 'Hide' : 'Show'}
                  onClick={() => toggleVis(l.id)}
                >
                  {l.visible ? '●' : '○'}
                </button>
                <button
                  type="button"
                  className="lm-name"
                  title="View this layer / continue working on it"
                  onClick={() => select(l.id)}
                >
                  {l.name}
                </button>
                <input
                  type="range"
                  className="lm-opacity"
                  min={0}
                  max={1}
                  step={0.05}
                  value={l.opacity}
                  title={`Opacity ${Math.round(l.opacity * 100)}%`}
                  onChange={(e) => setOpacity(l.id, Number(e.target.value))}
                />
                <button
                  type="button"
                  className="lm-btn"
                  title="Move up"
                  disabled={i === 0}
                  onClick={() => move(l.id, 'up')}
                >
                  ▲
                </button>
                <button
                  type="button"
                  className="lm-btn"
                  title="Move down"
                  disabled={i === layers.length - 1}
                  onClick={() => move(l.id, 'down')}
                >
                  ▼
                </button>
                {canDownloadLayer(l) && (
                  <button
                    type="button"
                    className="lm-btn"
                    title="Download the AOI crop for this layer"
                    onClick={() => openDownload(l.id)}
                  >
                    ⇩
                  </button>
                )}
                <button
                  type="button"
                  className="lm-btn danger"
                  title="Remove layer"
                  onClick={() => remove(l.id)}
                >
                  ✕
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Draggable>
  );
}
