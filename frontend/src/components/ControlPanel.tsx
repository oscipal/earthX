import type { CoverageHistogramPoint } from '../api';
import { parseAoiFile } from '../aoiFile';
import { completenessNote } from '../coverage';
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

function DatasetSelector() {
  const datasets = useAppStore((s) => s.datasets);
  const datasetId = useAppStore((s) => s.datasetId);
  const setDatasetId = useAppStore((s) => s.setDatasetId);
  if (datasets.length === 0) return null;
  return (
    <div className="level-select" role="group" aria-label="Dataset">
      {datasets.map((d) => (
        <button
          key={d.id}
          type="button"
          className={`level-btn${datasetId === d.id ? ' active' : ''}`}
          title={d.viewable ? d.title : `${d.title} — not viewable: ${d.reason}`}
          aria-pressed={datasetId === d.id}
          disabled={!d.viewable}
          onClick={() => setDatasetId(d.id)}
        >
          {d.title}
        </button>
      ))}
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

function CoverageControls() {
  const showCoverage = useAppStore((s) => s.showCoverage);
  const toggleCoverage = useAppStore((s) => s.toggleCoverage);
  const coverage = useAppStore((s) => s.coverage);
  const coverageLoading = useAppStore((s) => s.coverageLoading);
  const coverageError = useAppStore((s) => s.coverageError);
  const dateFrom = useAppStore((s) => s.dateFrom);
  const dateTo = useAppStore((s) => s.dateTo);
  const datasetId = useAppStore((s) => s.datasetId);
  if (!datasetId) return null;

  const note = coverage ? completenessNote(coverage) : null;

  return (
    <div className="coverage-controls">
      <label className="coverage-toggle">
        <input type="checkbox" checked={showCoverage} onChange={() => toggleCoverage()} />
        Coverage heatmap
      </label>
      {showCoverage && coverageLoading && <p className="hint-text">Loading coverage…</p>}
      {showCoverage && coverageError && <p className="hint-text error">{coverageError}</p>}
      {showCoverage && coverage && (
        <div className="coverage-legend">
          <div className="legend-scale">
            <span className="legend-gradient" />
            <span className="legend-scale-labels">
              <span>1</span>
              <span>{coverage.max_count}</span>
            </span>
          </div>
          <p className="hint-text">Aufnahmen mit Mittelpunkt in der Zelle</p>
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
          <p>Geo- und Satellitendaten-Viewer</p>
        </div>
      </div>

      <label className="field-label">Area of interest</label>
      <Toolbar />
      <AoiExtras />

      <label className="field-label">Dataset</label>
      <DatasetSelector />

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
