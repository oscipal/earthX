import { useEffect } from 'react';

import ControlPanel from './components/ControlPanel';
import Draggable from './components/Draggable';
import LayerManager from './components/LayerManager';
import MapView from './components/MapView';
import ResultsPanel from './components/ResultsPanel';
import StatusBar from './components/StatusBar';
import TimeSlider from './components/TimeSlider';
import { useAppStore } from './store';

export default function App() {
  const loadDatasets = useAppStore((s) => s.loadDatasets);
  const panelCollapsed = useAppStore((s) => s.panelCollapsed);
  const togglePanel = useAppStore((s) => s.togglePanel);
  const zoomToView = useAppStore((s) => s.zoomToView);
  const hasGroups = useAppStore((s) => s.groups.length > 0);
  const canZoom = useAppStore((s) => !!s.aoi || s.groups.length > 0);
  const toggleLayerManager = useAppStore((s) => s.toggleLayerManager);
  const layerCount = useAppStore((s) => s.layers.length);

  useEffect(() => {
    loadDatasets();
  }, [loadDatasets]);

  return (
    <div className="app" data-theme="tech">
      <MapView />

      <div className={`overlay top-left panel-dock${panelCollapsed ? ' collapsed' : ''}`}>
        <ControlPanel />
        <button
          type="button"
          className="panel-toggle"
          onClick={togglePanel}
          title={panelCollapsed ? 'Show controls' : 'Hide controls'}
          aria-label={panelCollapsed ? 'Show controls' : 'Hide controls'}
          aria-expanded={!panelCollapsed}
        >
          {panelCollapsed ? '›' : '‹'}
        </button>
      </div>

      <div className="overlay top-right">
        <button
          type="button"
          className="panel zoom-btn"
          onClick={() => zoomToView()}
          disabled={!canZoom}
          title="Zoom the map to fit the selection (or the active time step)"
        >
          ⤢ Zoom to selection
        </button>
        <button
          type="button"
          className="panel zoom-btn"
          onClick={() => toggleLayerManager()}
          title="Open the layer manager"
        >
          ▤ Layers{layerCount ? ` (${layerCount})` : ''}
        </button>
      </div>

      <div className="overlay layermgr">
        <LayerManager />
      </div>

      {hasGroups && (
        <div className="overlay right">
          <Draggable className="dock-results">
            <ResultsPanel />
          </Draggable>
        </div>
      )}

      <div className="overlay bottom">
        {hasGroups && (
          <Draggable>
            <TimeSlider />
          </Draggable>
        )}
      </div>

      <div className="overlay status">
        <StatusBar />
      </div>
    </div>
  );
}
