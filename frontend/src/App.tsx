import { useEffect } from 'react';

import AppRail from './components/AppRail';
import ControlPanel from './components/ControlPanel';
import DownloadDialog from './components/DownloadDialog';
import ColormapPicker from './components/ColormapPicker';
import { ZoomToSelectionIcon } from './components/icons';
import Inspector from './components/Inspector';
import LayerManager from './components/LayerManager';
import MapView from './components/MapView';
import PreviewBadge from './components/PreviewBadge';
import ProcessingManager from './components/ProcessingManager';
import ProcessingPanel from './components/ProcessingPanel';
import ResultsPanel from './components/ResultsPanel';
import SettingsPanel from './components/SettingsPanel';
import SelectionBlock from './components/SelectionBlock';
import { selectionBlockModeOf } from './selectionBlockMode';
import StatusBar from './components/StatusBar';
import TipLayer from './components/TipLayer';
import { dockPanelId } from './dock';
import { inspectorKindOf } from './inspectorKind';
import { openPermalinkInAddress } from './permalink';
import { forgetJobsWindow } from './preferences';
import { useProcessingStore } from './processingStore';
import { ticksOfSearch, useAppStore } from './store';
import { NOTHING_TO_ZOOM, zoomBoxes } from './zoomSelection';

export default function App() {
  const loadDatasets = useAppStore((s) => s.loadDatasets);
  const dock = useAppStore((s) => s.dock);
  const focusMode = useAppStore((s) => s.focusMode);
  const resultView = useAppStore((s) => s.resultViewLayerId !== null);
  const inspectorOpen = useAppStore((s) => inspectorKindOf(s) !== null);
  const zoomToView = useAppStore((s) => s.zoomToView);
  const hasGroups = useAppStore((s) => s.groups.length > 0);
  const hasSelection = useAppStore((s) => ticksOfSearch(s).length > 0);
  // A scene ticked in the list while a view is open that the view does not draw: the bar of the selection shows
  // above the controls of the view, as it does after any click on a result.
  const tickedBesideView = useAppStore((s) => ticksOfSearch(s).some((id) => !(id in s.downloaded)));
  // "Zoom to selection" zooms to the AOI, the open view and the layers that are shown together;
  // with none of them, it stays disabled and says why (`zoomSelection.ts`).
  const canZoom = useAppStore((s) => zoomBoxes(s).length > 0);
  const theme = useAppStore((s) => s.theme);
  const followSystemTheme = useAppStore((s) => s.followSystemTheme);
  const processingOpen = useProcessingStore((s) => s.open);
  const resumeJobs = useProcessingStore((s) => s.resumeJobs);

  // `?permalink=` is opened once the datasets are there: loading them resets the selection.
  useEffect(() => {
    void loadDatasets().then(openPermalinkInAddress);
  }, [loadDatasets]);

  // "System" in the settings: the theme follows the system's colour scheme, also while the page is open.
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return undefined;
    const query = window.matchMedia('(prefers-color-scheme: light)');
    const follow = () => followSystemTheme(!query.matches);
    follow();
    query.addEventListener('change', follow);
    return () => query.removeEventListener('change', follow);
  }, [followSystemTheme]);

  // The old place of the floating window of the jobs is of no use any more.
  useEffect(() => {
    forgetJobsWindow();
  }, []);

  // The jobs of this tab, kept across a reload (M4-13 F5 (1)).
  useEffect(() => {
    resumeJobs();
  }, [resumeJobs]);

  return (
    <div className={`app${inspectorOpen && !processingOpen ? ' has-inspector' : ''}${processingOpen ? ' has-sheet' : ''}`} data-theme={theme}>
      <MapView />

      <AppRail />
      <TipLayer />

      {/* The control menu, the layer manager and the results stay mounted (what they hold survives a change
          of panel); the job manager follows jobs, so it exists only while it is open. */}
      <div className="overlay dock" hidden={!dock}>
        <div className="dock-slot" id={dockPanelId('controls')} hidden={dock !== 'controls'}>
          <ControlPanel />
        </div>
        <div className="dock-slot" id={dockPanelId('layers')} hidden={dock !== 'layers'}>
          <LayerManager />
        </div>
        <div className="dock-slot" id={dockPanelId('results')} hidden={dock !== 'results'}>
          <ResultsPanel />
        </div>
        <div className="dock-slot" id={dockPanelId('settings')} hidden={dock !== 'settings'}>
          <SettingsPanel />
        </div>
        {dock === 'jobs' && (
          <div className="dock-slot" id={dockPanelId('jobs')}>
            <ProcessingManager />
          </div>
        )}
      </div>

      <div className={`overlay top-right${processingOpen ? ' beside-sheet' : ''}`}>
        <button
          type="button"
          className="panel btn"
          onClick={() => zoomToView()}
          disabled={!canZoom}
          data-tip-level="advanced" data-tip={canZoom ? 'Zoom the map to fit the AOI, the open image and the layers that are shown' : NOTHING_TO_ZOOM}
        >
          <ZoomToSelectionIcon lead />Zoom to selection
        </button>
      </div>

      {/* Beside the processing side bar, not under it: the time slider picks the pass of an order. */}
      <div className={`overlay bottom${processingOpen ? ' beside-sheet' : ''}`}>
        <SelectionBlock {...selectionBlockModeOf({ focusMode, resultView, hasSelection, tickedBesideView, hasGroups })} />
      </div>

      <Inspector />
      <ColormapPicker />

      {processingOpen && (
        <div className="overlay processing-sheet">
          <ProcessingPanel />
        </div>
      )}

      <PreviewBadge />

      <div className="overlay status">
        <StatusBar />
      </div>

      <DownloadDialog />
    </div>
  );
}
