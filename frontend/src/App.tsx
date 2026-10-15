import { useEffect } from 'react';

import ControlPanel from './components/ControlPanel';
import Draggable from './components/Draggable';
import DownloadDialog from './components/DownloadDialog';
import JobList from './components/JobList';
import LayerManager from './components/LayerManager';
import MapView from './components/MapView';
import ProcessingPanel from './components/ProcessingPanel';
import ResultsPanel from './components/ResultsPanel';
import StatusBar from './components/StatusBar';
import TimeSlider from './components/TimeSlider';
import ViewBar from './components/ViewBar';
import ViewerControls from './components/ViewerControls';
import { useProcessingStore } from './processingStore';
import { hasResultsPanel } from './sections';
import { useAppStore } from './store';

export default function App() {
  const loadDatasets = useAppStore((s) => s.loadDatasets);
  const panelCollapsed = useAppStore((s) => s.panelCollapsed);
  const togglePanel = useAppStore((s) => s.togglePanel);
  const resultsPanelCollapsed = useAppStore((s) => s.resultsPanelCollapsed);
  const toggleResultsPanel = useAppStore((s) => s.toggleResultsPanel);
  const focusMode = useAppStore((s) => s.focusMode);
  const zoomToView = useAppStore((s) => s.zoomToView);
  const hasGroups = useAppStore((s) => s.groups.length > 0);
  const hasResults = useAppStore((s) => hasResultsPanel(s.sections));
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
  const processingOpen = useProcessingStore((s) => s.open);
  const jobsOpen = useProcessingStore((s) => s.jobsOpen);
  const openJobs = useProcessingStore((s) => s.openJobs);
  const jobCount = useProcessingStore((s) => s.jobs.length);
  const resumeJobs = useProcessingStore((s) => s.resumeJobs);

  useEffect(() => {
    loadDatasets();
  }, [loadDatasets]);

  // The jobs of this tab, kept across a reload (M4-13 F5 (1)).
  useEffect(() => {
    resumeJobs();
  }, [resumeJobs]);

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
        {jobCount > 0 && !jobsOpen && (
          <button
            type="button"
            className="panel zoom-btn"
            onClick={() => openJobs()}
            title="Show the jobs of this tab"
          >
            ⚙ Jobs ({jobCount})
          </button>
        )}
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

      {/* The processing side bar lies over the results list: folded away while it is open. */}
      {!focusMode && hasResults && (
        <div className={`overlay right results-dock${resultsPanelCollapsed || processingOpen ? ' collapsed' : ''}`}>
          <ResultsPanel />
          {!processingOpen && (
            <button
              type="button"
              className="results-toggle"
              onClick={() => toggleResultsPanel()}
              title={resultsPanelCollapsed ? 'Show results' : 'Hide results'}
              aria-label={resultsPanelCollapsed ? 'Show results' : 'Hide results'}
              aria-expanded={!resultsPanelCollapsed}
            >
              {resultsPanelCollapsed ? '‹' : '›'}
            </button>
          )}
        </div>
      )}

      {/* Beside the processing side bar, not under it: the time slider picks the pass of an order. */}
      <div className={`overlay bottom${processingOpen ? ' beside-sheet' : ''}`}>
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

      {processingOpen && (
        <div className="overlay processing-sheet">
          <ProcessingPanel />
        </div>
      )}

      {jobsOpen && (
        <div className={`overlay jobs-dock${processingOpen ? ' beside-sheet' : ''}`}>
          <Draggable>
            <JobList />
          </Draggable>
        </div>
      )}

      <div className="overlay status">
        <StatusBar />
      </div>

      <DownloadDialog />
    </div>
  );
}
