import type { CoverageHistogramPoint } from '../api';
import { parseAoiFile } from '../aoiFile';
import { completenessNote } from '../coverage';
import { lastCheckedNote, maturityNote } from '../datasets';
import { bufferPointToPolygon, polygonBbox } from '../geoUtils';
import { useAppStore } from '../store';
import Toolbar from './Toolbar';

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
      if (geom.type === 'Point') {
        const [lon, lat] = geom.coordinates;
        geom = bufferPointToPolygon(lon, lat, config?.point_buffer_deg ?? 0.05);
      }
      setAoi(geom);
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

// What the catalogue says about the *source* of the selected dataset, shown
// because both halves are required to be visible and neither was: the maturity
// (D23 — "staging" must not be something a user finds out only once the source
// disappears) and the date of the last successful check (onboarding checklist
// point 10, projektuebersicht.md §7).
function DatasetNotes() {
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const dataset = datasets.find((d) => d.id === datasetId);
  if (!dataset) return null;
  const maturity = maturityNote(dataset.collection);
  const checked = lastCheckedNote(dataset.collection);
  if (!maturity && !checked) return null;
  return (
    <div className="dataset-notes">
      {maturity && <p className="hint-text warn">{maturity}</p>}
      {checked && <p className="hint-text">{checked}</p>}
    </div>
  );
}

// Below the lowest released level the map requests no tiles at all, so the
// dataset simply is not there (adr/0007 §12.10: one tile would show several
// scenes, which is the coverage map's job). Saying so beats an empty map.
function ZoomFloorHint() {
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const mapZoom = useAppStore((s) => s.mapZoom);
  const dataset = datasets.find((d) => d.id === datasetId);
  if (!dataset?.viewable || mapZoom >= dataset.zoom.min) return null;
  return (
    <p className="hint-text">
      Zoom in to level {dataset.zoom.min} to see imagery for this dataset — below it, one tile
      covers several scenes, which is what the coverage layer is for.
    </p>
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
            {maturity && <span className="maturity-chip">{maturity.split(':')[0]}</span>}
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
  const runSearch = useAppStore((s) => s.runSearch);
  const count = useAppStore((s) => s.items.length);
  const datasetId = useAppStore((s) => s.datasetId);

  return (
    <div className="panel control-panel">
      <div className="brand">
        <span className="brand-mark" />
        <div>
          <h1>EarthX</h1>
          <p>Geo and satellite data viewer</p>
        </div>
      </div>

      <label className="field-label">Area of interest</label>
      <Toolbar />
      <AoiExtras />

      <label className="field-label">Dataset</label>
      <DatasetSelector />
      <DatasetNotes />
      <ZoomFloorHint />

      <CoverageControls />

      <label className="field-label">Acquisition date</label>
      <div className="date-row">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          aria-label="From date"
        />
        <span>→</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          aria-label="To date"
        />
      </div>

      <button
        type="button"
        className="primary-btn"
        disabled={!aoi || !datasetId || searching}
        onClick={() => runSearch()}
      >
        {searching ? 'Searching…' : 'Search scenes'}
      </button>

      {count > 0 && <p className="result-count">{count} scene(s) found</p>}
      {!aoi && <p className="hint-text">Pick a tool to define an area of interest.</p>}
    </div>
  );
}
