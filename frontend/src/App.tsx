import { useEffect, useRef, useState } from 'react';

import AppRail from './components/AppRail';
import BasemapMenu from './components/BasemapMenu';
import ControlPanel from './components/ControlPanel';
import DownloadDialog from './components/DownloadDialog';
import Inspector from './components/Inspector';
import JobsWindow from './components/JobsWindow';
import LayerManager from './components/LayerManager';
import MapView from './components/MapView';
import PreviewBadge from './components/PreviewBadge';
import ProcessingPanel from './components/ProcessingPanel';
import ResultsPanel from './components/ResultsPanel';
import SelectionBlock from './components/SelectionBlock';
import StatusBar from './components/StatusBar';
import TipLayer from './components/TipLayer';
import { dockPanelId } from './dock';
import { inspectorKindOf } from './inspectorKind';
import { openPermalinkInAddress } from './permalink';
import { useProcessingStore } from './processingStore';
import { ticksOfSearch, useAppStore } from './store';

// Under 900 px the settings bar, the processing panel and the jobs are sheets from the bottom and cover each other: the one opened last is on top.
function useJobsInFront(managerOpen: boolean, inspectorOpen: boolean, processingOpen: boolean): boolean {
  const [jobsFront, setJobsFront] = useState(true);
  const was = useRef({ managerOpen, inspectorOpen, processingOpen });
  useEffect(() => {
    const before = was.current;
    if (managerOpen && !before.managerOpen) setJobsFront(true);
    else if ((inspectorOpen && !before.inspectorOpen) || (processingOpen && !before.processingOpen)) setJobsFront(false);
    was.current = { managerOpen, inspectorOpen, processingOpen };
  }, [managerOpen, inspectorOpen, processingOpen]);
  return jobsFront;
}

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
  // "Zoom to selection" zooms to the AOI, else the pinned layer images;
  // with neither, it stays visibly disabled (store.ts::zoomToView).
  const canZoom = useAppStore((s) => !!s.aoi || s.layers.length > 0);
  const theme = useAppStore((s) => s.theme);
  const toggleTheme = useAppStore((s) => s.toggleTheme);
  const processingOpen = useProcessingStore((s) => s.open);
  const managerOpen = useProcessingStore((s) => s.managerOpen);
  const jobsFront = useJobsInFront(managerOpen, inspectorOpen, processingOpen);
  const resumeJobs = useProcessingStore((s) => s.resumeJobs);

  // `?permalink=` is opened once the datasets are there: loading them resets the selection.
  useEffect(() => {
    void loadDatasets().then(openPermalinkInAddress);
  }, [loadDatasets]);

  // The jobs of this tab, kept across a reload (M4-13 F5 (1)).
  useEffect(() => {
    resumeJobs();
  }, [resumeJobs]);

  return (
    <div className={`app${inspectorOpen && !processingOpen ? ' has-inspector' : ''}${managerOpen && jobsFront ? ' jobs-front' : ''}`} data-theme={theme}>
      <MapView />

      <AppRail />
      <TipLayer />

      {/* The control menu, the layer manager and the results stay mounted (what they hold survives a change
          of panel). The jobs are a floating window of their own, below. */}
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
      </div>

      <div className={`overlay top-right${processingOpen ? ' beside-sheet' : ''}`}>
        <button
          type="button"
          className="panel zoom-btn"
          onClick={() => zoomToView()}
          disabled={!canZoom}
          title="Zoom the map to fit the AOI, or the pinned layer images"
        >
          ⤢ Zoom to selection
        </button>
        <BasemapMenu />
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

      {/* Beside the processing side bar, not under it: the time slider picks the pass of an order. */}
      <div className={`overlay bottom${processingOpen ? ' beside-sheet' : ''}`}>
        {focusMode ? (
          <SelectionBlock bar={tickedBesideView} timeline={false} />
        ) : resultView ? (
          <SelectionBlock bar={hasSelection} timeline={false} />
        ) : (
          <SelectionBlock bar={hasSelection} timeline={hasGroups} />
        )}
      </div>

      <Inspector />

      {managerOpen && <JobsWindow />}

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
