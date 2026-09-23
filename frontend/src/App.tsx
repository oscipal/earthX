import { useEffect } from 'react';

import ControlPanel from './components/ControlPanel';
import Draggable from './components/Draggable';
import DownloadDialog from './components/DownloadDialog';
import LayerManager from './components/LayerManager';
import MapView from './components/MapView';
import ResultsPanel from './components/ResultsPanel';
import StatusBar from './components/StatusBar';
import TimeSlider from './components/TimeSlider';
import ViewBar from './components/ViewBar';
import ViewerControls from './components/ViewerControls';
import { useAppStore } from './store';

export default function App() {
  const loadDatasets = useAppStore((s) => s.loadDatasets);
  const panelCollapsed = useAppStore((s) => s.panelCollapsed);
  const togglePanel = useAppStore((s) => s.togglePanel);
  const focusMode = useAppStore((s) => s.focusMode);
  const zoomToView = useAppStore((s) => s.zoomToView);
  const hasGroups = useAppStore((s) => s.groups.length > 0);
  const hasSelection = useAppStore((s) => s.selectedIds.length > 0);
  // "Zoom to selection" zooms to the AOI, else the pinned layer images;
  // with neither, it stays visibly disabled (store.ts::zoomToView).
  const canZoom = useAppStore((s) => !!s.aoi || s.layers.length > 0);
  const toggleLayerManager = useAppStore((s) => s.toggleLayerManager);
  const layerCount = useAppStore((s) => s.layers.length);
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const projection = useAppStore((s) => s.projection);
  const toggleProjection = useAppStore((s) => s.toggleProjection);

  useEffect(() => {
    loadDatasets();
  }, [loadDatasets]);

  return (
    <div className="app" data-theme={theme}>
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
          title="Zoom the map to fit the AOI, or the pinned layer images"
        >
          ⤢ Zoom to selection
        </button>
        <button
          type="button"
          className="panel zoom-btn"
          onClick={() => toggleLayerManager()}
          title="Open the layer manager"
        >
          ☰ Layers{layerCount ? ` (${layerCount})` : ''}
        </button>
        <button
          type="button"
          className="panel zoom-btn"
          onClick={() => toggleProjection()}
          title={projection === 'globe' ? 'Switch to the Mercator map' : 'Switch to the globe'}
          aria-pressed={projection === 'globe'}
        >
          {projection === 'globe' ? '🗺 Mercator' : '🌐 Globe'}
        </button>
        <button
          type="button"
          className="panel zoom-btn"
          onClick={() => toggleTheme()}
          title={theme === 'tech' ? 'Switch to the light theme' : 'Switch to the dark theme'}
          aria-pressed={theme === 'normal'}
        >
          {theme === 'tech' ? '☀ Light' : '☾ Dark'}
        </button>
      </div>

      <div className="overlay layermgr">
        <LayerManager />
      </div>

      {!focusMode && hasGroups && (
        <div className="overlay right">
          <Draggable className="dock-results">
            <ResultsPanel />
          </Draggable>
        </div>
      )}

      <div className="overlay bottom">
        {focusMode ? (
          <Draggable>
            <ViewerControls />
          </Draggable>
        ) : (
          <>
            {hasSelection && (
              <Draggable>
                <ViewBar />
              </Draggable>
            )}
            {hasGroups && (
              <Draggable>
                <TimeSlider />
              </Draggable>
            )}
          </>
        )}
      </div>

      <div className="overlay status">
        <StatusBar />
      </div>

      <DownloadDialog />
    </div>
  );
}
