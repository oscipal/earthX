import { useRef } from 'react';

import type { CoverageHistogramPoint } from '../api';
import { parseAoiFile } from '../aoiFile';
import { completenessNote } from '../coverage';
import { maturityLabel, maturityNote } from '../datasets';
import { bufferPointToPolygon, polygonBbox } from '../geoUtils';
import { useAppStore } from '../store';
import Toolbar from './Toolbar';

// A date input plus a transparent button covering its calendar icon
// (V-5). The tech theme draws its own icon and hides the native
// `::-webkit-calendar-picker-indicator` behind `padding-right`, but that
// padding also pushes the engine's real (invisible) hit-box for the
// indicator inward, out from under the icon we draw at a fixed offset —
// clicking the visible icon then misses the part that actually opens the
// picker. `showPicker()` sidesteps the mismatch instead of chasing it
// pixel by pixel.
function DateField({
  value,
  onChange,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="date-field">
      <input
        ref={ref}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
      />
      <button
        type="button"
        className="date-icon-btn"
        tabIndex={-1}
        aria-label={`Open the ${label.toLowerCase()} calendar`}
        onClick={() => {
          const input = ref.current;
          if (!input) return;
          if (typeof input.showPicker === 'function') input.showPicker();
          else input.focus();
        }}
      />
    </div>
  );
}

function AoiExtras() {
  const setAoi = useAppStore((s) => s.setAoi);
  const flyTo = useAppStore((s) => s.flyTo);
  const applyLastAoi = useAppStore((s) => s.useLastAoi);
  const lastAoi = useAppStore((s) => s.lastAoi);
  const config = useAppStore((s) => s.config);
  const setError = useAppStore((s) => s.setError);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    try {
      let geom = parseAoiFile(file.name, await file.text());
      if (!geom) {
        setError(`Could not read an AOI geometry from "${file.name}".`);
        return;
      }
      // M3-08 F5a: same split as the draw tool (MapView.tsx) — the point itself
      // is what a search asks with, the buffer square is what stays on screen.
      let point: GeoJSON.Point | null = null;
      if (geom.type === 'Point') {
        point = geom;
        const [lon, lat] = geom.coordinates;
        geom = bufferPointToPolygon(lon, lat, config?.point_buffer_deg ?? 0.05);
      }
      setAoi(geom, point);
      const bb = polygonBbox(geom);
      if (bb) flyTo(bb);
    } catch (err) {
      setError(`Failed to load AOI file: ${(err as Error).message}`);
    }
  };

  return (
    <div className="aoi-extras">
      <label className="tool-btn ghost" title="Upload a KML or GeoJSON to use as the AOI">
        <input
          type="file"
          accept=".kml,.json,.geojson,application/json,application/vnd.google-earth.kml+xml"
          onChange={onFile}
          hidden
        />
        <span>⤒ Upload KML/JSON</span>
      </label>
      <button
        type="button"
        className="tool-btn ghost"
        disabled={!lastAoi}
        title="Reuse the previous area of interest"
        onClick={() => applyLastAoi()}
      >
        <span>↺ Last AOI</span>
      </button>
    </div>
  );
}

// How settled the source of the selected dataset is (D23: "staging" must not be
// something a user finds out only once the source disappears).
//
// No "last checked" date is shown next to it: `earthx:health` carries only
// `status` (M2-08-3, 2026-09-23) — the field it used to carry alongside dated only
// the onboarding check, not an actual health check, and stating that would claim
// something the platform does not know. A real check date comes with the health
// checks in M5.
function DatasetNotes() {
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const dataset = datasets.find((d) => d.id === datasetId);
  if (!dataset) return null;
  const maturity = maturityNote(dataset.collection);
  if (!maturity) return null;
  return (
    <div className="dataset-notes">
      <p className="hint-text warn">{maturity}</p>
    </div>
  );
}

// Not a heuristic bolted onto a generic search box: the scene-name syntax
// differs per dataset, and there is nothing else a free-text field here could
// mean today (location search is hidden until M3, F1) — so no guessing which
// one the user typed (M2-17). One field, no button of its own — the single
// "Search" button below decides which of the two lookups to run (M2-17,
// Otto's redesign 23.09.2026: merged into the ordinary search action instead
// of a separate "Find").
function SceneNameField({ onSubmit }: { onSubmit: () => void }) {
  const query = useAppStore((s) => s.sceneNameQuery);
  const setQuery = useAppStore((s) => s.setSceneNameQuery);
  return (
    <div className="scene-name-field">
      <label className="field-label" htmlFor="scene-name-input">
        Scene name
      </label>
      <input
        id="scene-name-input"
        type="text"
        value={query}
        placeholder="e.g. S2C_T32TNT_20260920T103025_L2A"
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSubmit();
        }}
      />
    </div>
  );
}

function DatasetSelector() {
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const setDatasetId = useAppStore((s) => s.setDatasetId);
  if (datasets.length === 0) return null;
  return (
    <div className="level-select" role="group" aria-label="Dataset">
      {datasets.map((d) => {
        const maturity = d.viewable ? maturityNote(d.collection) : null;
        const label = d.viewable ? maturityLabel(d.collection) : null;
        return (
          <button
            key={d.id}
            type="button"
            className={`level-btn${datasetId === d.id ? ' active' : ''}`}
            title={d.viewable ? (maturity ? `${d.title} — ${maturity}` : d.title) : `${d.title} — not viewable: ${d.reason}`}
            aria-pressed={datasetId === d.id}
            disabled={!d.viewable}
            onClick={() => setDatasetId(d.id)}
          >
            {d.title}
            {label && <span className="maturity-chip">{label}</span>}
          </button>
        );
      })}
    </div>
  );
}

// A bare bar row, one bar per monthly bucket (D22 — Earth Search ignores a
// finer interval). `dateFrom`/`dateTo` are `YYYY-MM-DD` or empty; a bucket
// counts as "in range" by comparing year-month, since that is exactly the
// bucket's own resolution.
function CoverageHistogram({
  histogram,
  dateFrom,
  dateTo,
}: {
  histogram: CoverageHistogramPoint[];
  dateFrom: string;
  dateTo: string;
}) {
  const max = Math.max(1, ...histogram.map((b) => b.n));
  const fromMonth = dateFrom.slice(0, 7);
  const toMonth = dateTo.slice(0, 7);
  return (
    <div className="coverage-histogram" role="img" aria-label="Acquisitions per month">
      {histogram.map((bucket) => {
        const month = bucket.t.slice(0, 7);
        const inRange = (!fromMonth || month >= fromMonth) && (!toMonth || month <= toMonth);
        return (
          <span
            key={bucket.t}
            className={`histogram-bar${inRange ? ' in-range' : ''}`}
            style={{ height: `${Math.max(2, (bucket.n / max) * 100)}%` }}
            title={`${month}: ${bucket.n}`}
          />
        );
      })}
    </div>
  );
}

// Off by default, switched on from the layer manager ("Layers" button) —
// the legend/histogram here only ever appear once that toggle is on.
function CoverageControls() {
  const showCoverage = useAppStore((s) => s.showCoverage);
  const coverage = useAppStore((s) => s.coverage);
  const coverageLoading = useAppStore((s) => s.coverageLoading);
  const coverageError = useAppStore((s) => s.coverageError);
  const dateFrom = useAppStore((s) => s.dateFrom);
  const dateTo = useAppStore((s) => s.dateTo);
  const datasetId = useAppStore((s) => s.datasetId);
  if (!datasetId || !showCoverage) return null;

  const note = coverage ? completenessNote(coverage) : null;

  return (
    <div className="coverage-controls">
      {coverageLoading && <p className="hint-text">Loading coverage…</p>}
      {coverageError && <p className="hint-text error">{coverageError}</p>}
      {coverage && (
        <div className="coverage-legend">
          <div className="legend-scale">
            <span className="legend-gradient" />
            <span className="legend-scale-labels">
              <span>1</span>
              <span>{coverage.max_count}</span>
            </span>
          </div>
          {/* English, matching the rest of the UI (D25; adr/0004 §5.3 nachtrag
              22.09.2026 lifts the earlier German-terms default). */}
          <p className="hint-text">Scenes counted by their center point in the cell</p>
          {note && <p className="hint-text coverage-note">{note}</p>}
          {coverage.histogram.length > 0 && (
            <CoverageHistogram histogram={coverage.histogram} dateFrom={dateFrom} dateTo={dateTo} />
          )}
        </div>
      )}
    </div>
  );
}

export default function ControlPanel() {
  const aoi = useAppStore((s) => s.aoi);
  const dateFrom = useAppStore((s) => s.dateFrom);
  const dateTo = useAppStore((s) => s.dateTo);
  const setDateFrom = useAppStore((s) => s.setDateFrom);
  const setDateTo = useAppStore((s) => s.setDateTo);
  const searching = useAppStore((s) => s.searching);
  const sceneLookupLoading = useAppStore((s) => s.sceneLookupLoading);
  const runSearch = useAppStore((s) => s.runSearch);
  const findSceneByName = useAppStore((s) => s.findSceneByName);
  const sceneNameQuery = useAppStore((s) => s.sceneNameQuery);
  const count = useAppStore((s) => s.items.length);
  const datasetId = useAppStore((s) => s.datasetId);

  // One button for both lookups (M2-17, Otto's redesign): a scene name in the
  // field above takes it, an AOI otherwise — the usual bbox/date search
  // (`runSearch`) is untouched either way, this only decides which of the two
  // it calls. A name takes priority over an AOI rather than requiring both,
  // since the name lookup needs neither AOI nor date range (adr/0001 Z1).
  const hasSceneName = sceneNameQuery.trim().length > 0;
  const busy = searching || sceneLookupLoading;
  const canSearch = !busy && !!datasetId && (hasSceneName || !!aoi);
  const search = () => {
    if (!canSearch) return;
    if (hasSceneName) void findSceneByName();
    else void runSearch();
  };

  return (
    <div className="panel control-panel">
      <div className="brand">
        <span className="brand-mark" />
        <div>
          <h1>EarthX</h1>
          <p>Geo and satellite data viewer</p>
        </div>
      </div>

      <SceneNameField onSubmit={search} />

      <label className="field-label">Area of interest</label>
      <Toolbar />
      <AoiExtras />

      <label className="field-label">Dataset</label>
      <DatasetSelector />
      <DatasetNotes />

      <CoverageControls />

      <label className="field-label">Acquisition date</label>
      <div className="date-row">
        <DateField value={dateFrom} onChange={setDateFrom} label="From date" />
        <span>→</span>
        <DateField value={dateTo} onChange={setDateTo} label="To date" />
      </div>

      <button type="button" className="primary-btn" disabled={!canSearch} onClick={search}>
        {sceneLookupLoading ? 'Finding…' : searching ? 'Searching…' : 'Search'}
      </button>

      {count > 0 && <p className="result-count">{count} scene(s) found</p>}
      {!aoi && !hasSceneName && <p className="hint-text">Pick a tool to define an area of interest, or enter a scene name above.</p>}
    </div>
  );
}
