import { useEffect, useRef, useState } from 'react';

import type { CoverageHistogramPoint, PlaceResult } from '../api';
import { readAoiFile } from '../aoiFile';
import { completenessNote } from '../coverage';
import { acquisitionNote, maturityLabel, maturityNote } from '../datasets';
import { bufferPointToPolygon, polygonBbox } from '../geoUtils';
import { PLACE_SEARCH_PROVENANCE, placeAoi, searchPlaces } from '../placeSearch';
import { totalItems } from '../sections';
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
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  disabled?: boolean;
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
        disabled={disabled}
      />
      <button
        type="button"
        className="date-icon-btn"
        tabIndex={-1}
        aria-label={`Open the ${label.toLowerCase()} calendar`}
        disabled={disabled}
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

// M3-12, F6 (Otto, 26.09.2026): a dataset without a time axis
// (`capabilities.time_range=False`, the DEM) answers a search the same for
// any chosen window — the fields stay visible and keep their values (the next
// dataset picked may well have a time axis), but are locked rather than
// bedienbar, with the acquisition period underneath explaining why a filter
// would not narrow anything.
//
// M3-10: with several datasets ticked the window still means something for those
// that have a time axis, so the fields lock only when *none* of the ticked ones
// has one; each one without says so under the fields, named by title.
function AcquisitionDateFields() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const dateFrom = useAppStore((s) => s.dateFrom);
  const dateTo = useAppStore((s) => s.dateTo);
  const setDateFrom = useAppStore((s) => s.setDateFrom);
  const setDateTo = useAppStore((s) => s.setDateTo);
  const ticked = datasets.filter((d) => selectedDatasetIds.includes(d.id));
  const withoutTimeAxis = ticked.filter((d) => d.viewable && !d.hasTimeAxis);
  const locked = ticked.length > 0 && withoutTimeAxis.length === ticked.length;
  const notes = withoutTimeAxis.flatMap((d) => {
    const note = acquisitionNote(d.collection);
    if (!note) return [];
    return [{ id: d.id, text: ticked.length > 1 ? `${d.title}: ${note}` : note }];
  });
  return (
    <>
      <label className="field-label">Acquisition date</label>
      <div className="date-row">
        <DateField value={dateFrom} onChange={setDateFrom} label="From date" disabled={locked} />
        <span>→</span>
        <DateField value={dateTo} onChange={setDateTo} label="To date" disabled={locked} />
      </div>
      {notes.map((n) => (
        <p key={n.id} className="hint-text">
          {n.text}
        </p>
      ))}
    </>
  );
}

// M3-07b: a place name resolved to an AOI via `POST /geocode` (M3-07a). Search
// only fires on Enter/"Find" — Nominatim's usage policy forbids an
// autocomplete-style client (M3-07a §2.1), so there is deliberately no
// on-keystroke suggestion here, unlike a typical search box.
function PlaceSearchField() {
  const setAoi = useAppStore((s) => s.setAoi);
  const flyTo = useAppStore((s) => s.flyTo);
  const currentAoi = useAppStore((s) => s.aoi);
  const setError = useAppStore((s) => s.setError);
  const [query, setQuery] = useState('');
  const [searching, setSearching] = useState(false);
  const [showResults, setShowResults] = useState(false);
  const [results, setResults] = useState<PlaceResult[]>([]);
  const [attribution, setAttribution] = useState<{ text: string; url?: string } | null>(null);
  const [picked, setPicked] = useState<{ name: string; geometry: GeoJSON.Geometry } | null>(null);
  // Guards against an earlier, slower request overwriting the list a newer
  // one already filled in (plan §4: "eine noch laufende ältere Anfrage, die
  // später ankommt, wird verworfen").
  const requestRef = useRef(0);

  const runSearch = async () => {
    const q = query.trim();
    if (!q || searching) return;
    const requestId = ++requestRef.current;
    setSearching(true);
    const outcome = await searchPlaces(q);
    if (requestId !== requestRef.current) return;
    setSearching(false);
    if (outcome.error) {
      setShowResults(false);
      setResults([]);
      setAttribution(null);
      setError(outcome.error);
      return;
    }
    setResults(outcome.results ?? []);
    setAttribution(outcome.attribution ? { text: outcome.attribution, url: outcome.attributionUrl } : null);
    setShowResults(true);
  };

  const choose = (result: PlaceResult) => {
    const geometry = placeAoi(result);
    setAoi(geometry);
    setPicked({ name: result.name, geometry });
    setShowResults(false);
    flyTo(result.bbox);
  };

  // The "picked from here" line only holds while the store's AOI is still
  // (by identity) the geometry this field handed to `setAoi` — a redraw, an
  // upload or "Clear" replaces that object, so the line disappears without
  // this field having to know why the AOI changed.
  const stillActive = !!picked && currentAoi === picked.geometry;

  return (
    <div className="place-search">
      <div className="place-search-row">
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void runSearch();
            if (e.key === 'Escape') setShowResults(false);
          }}
          placeholder="Place name"
          aria-label="Place"
          maxLength={200}
        />
        <button
          type="button"
          className="tool-btn ghost"
          aria-busy={searching}
          disabled={searching || !query.trim()}
          onClick={() => void runSearch()}
        >
          {searching ? 'Finding…' : 'Find'}
        </button>
      </div>
      {showResults && (
        <div className="place-results">
          {results.length === 0 && <p className="hint-text">No place found.</p>}
          {results.map((r, i) => (
            <button
              key={`${r.display_name}-${i}`}
              type="button"
              className="place-result"
              title={r.outline_simplified ? 'Outline simplified' : undefined}
              onClick={() => choose(r)}
            >
              <span className="place-result-name">{r.name}</span>
              <span className="place-result-kind">{r.kind.split('/')[0]}</span>
              <span className="place-result-display">{r.display_name}</span>
            </button>
          ))}
          {attribution && (
            <p className="hint-text place-attribution">
              {attribution.url?.startsWith('https://') ? (
                <a href={attribution.url} target="_blank" rel="noopener noreferrer">
                  {attribution.text}
                </a>
              ) : (
                attribution.text
              )}
            </p>
          )}
        </div>
      )}
      {stillActive && picked && (
        <p className="hint-text place-attribution">
          {picked.name} · {PLACE_SEARCH_PROVENANCE.attribution}
        </p>
      )}
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
  // M3-06b: the request to the backend (M3-06a's `POST /aoi/upload`) takes
  // longer than the old in-browser parse; this locks the control against a
  // double-click firing two uploads while one is in flight.
  const [uploading, setUploading] = useState(false);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    setUploading(true);
    try {
      const { geometry, error } = await readAoiFile(file);
      if (error) {
        setError(error);
        return;
      }
      let geom = geometry as GeoJSON.Geometry;
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
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="aoi-extras">
      <label
        className="tool-btn ghost"
        aria-busy={uploading}
        title="Upload a GeoJSON, KML or zipped Shapefile (max. 1 MB) as the AOI"
      >
        <input
          type="file"
          accept=".geojson,.json,.kml,.zip"
          onChange={onFile}
          disabled={uploading}
          hidden
        />
        <span>⤒ {uploading ? 'Reading…' : 'Upload AOI'}</span>
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

// How settled the source of each ticked dataset is (D23: "staging" must not be
// something a user finds out only once the source disappears).
//
// No "last checked" date is shown next to it: `earthx:health` carries only
// `status` (M2-08-3, 2026-09-23) — the field it used to carry alongside dated only
// the onboarding check, not an actual health check, and stating that would claim
// something the platform does not know. A real check date comes with the health
// checks in M5.
function DatasetNotes() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const ticked = datasets.filter((d) => selectedDatasetIds.includes(d.id));
  const notes = ticked.flatMap((d) => {
    const maturity = maturityNote(d.collection);
    return maturity ? [{ id: d.id, text: ticked.length > 1 ? `${d.title}: ${maturity}` : maturity }] : [];
  });
  if (notes.length === 0) return null;
  return (
    <div className="dataset-notes">
      {notes.map((n) => (
        <p key={n.id} className="hint-text warn">
          {n.text}
        </p>
      ))}
    </div>
  );
}

// Not a heuristic bolted onto a generic search box: the scene-name syntax
// differs per dataset, and a place name has its own field now
// (`PlaceSearchField`, M3-07b) — so no guessing which one the user typed
// (M2-17). One field, no button of its own — the single
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

// The dataset choice (M3-10): one toggle button per dataset from
// `/stac/collections`, any number at once — a click picks a dataset (drawn
// highlighted), another click drops it again. Every picked dataset is searched
// together. Four rows are visible; with more the list scrolls. A dataset that
// cannot be shown stays listed, disabled, with the reason.
function DatasetPicker() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const toggle = useAppStore((s) => s.toggleDatasetSelected);
  const busy = useAppStore((s) => s.searching || s.sceneLookupLoading);
  if (datasets.length === 0) return null;
  return (
    <div className="dataset-list" role="group" aria-label="Datasets">
      {datasets.map((d) => {
        const picked = selectedDatasetIds.includes(d.id);
        const maturity = d.viewable ? maturityNote(d.collection) : null;
        const label = d.viewable ? maturityLabel(d.collection) : null;
        return (
          <button
            key={d.id}
            type="button"
            className={`dataset-toggle${picked ? ' active' : ''}`}
            title={
              d.viewable
                ? [d.title, maturity, d.collection.description].filter(Boolean).join(' — ')
                : `${d.title} — not viewable: ${d.reason}`
            }
            aria-pressed={picked}
            disabled={!d.viewable || busy}
            onClick={() => toggle(d.id)}
          >
            <span className="dataset-toggle-title">{d.title}</span>
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

// The legend and histogram of the coverage map, in the scrolling part of the
// panel; the "Coverage" button that switches it on is `CoverageButton` below.
function CoverageLegend() {
  const showCoverage = useAppStore((s) => s.showCoverage);
  const coverage = useAppStore((s) => s.coverage);
  const coverageLoading = useAppStore((s) => s.coverageLoading);
  const coverageError = useAppStore((s) => s.coverageError);
  const dateFrom = useAppStore((s) => s.dateFrom);
  const dateTo = useAppStore((s) => s.dateTo);
  const title = useAppStore((s) => s.datasets.find((d) => d.id === s.coverageDatasetId)?.title ?? s.coverageDatasetId);
  if (!showCoverage) return null;

  const note = coverage ? completenessNote(coverage) : null;
  return (
    <div className="coverage-controls">
      <p className="hint-text coverage-dataset-name">Coverage · {title}</p>
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

// The "Coverage" button (M3-10, Otto 30.09.2026): right under the grid of dataset
// buttons, outside it so it stays in view however that grid scrolls, and set
// apart from them. The choice of dataset opens below it, in the panel's flow. One dataset picked: a click
// shows its coverage (or hides it again). Several picked: the click first offers
// the choice of which dataset — nothing is drawn until one is chosen. Off by
// default (M2-07c).
function CoverageButton() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const showCoverage = useAppStore((s) => s.showCoverage);
  const coverageDatasetId = useAppStore((s) => s.coverageDatasetId);
  const showCoverageFor = useAppStore((s) => s.showCoverageFor);
  const hideCoverage = useAppStore((s) => s.hideCoverage);
  const [choosing, setChoosing] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const picked = datasets.filter((d) => selectedDatasetIds.includes(d.id));

  useEffect(() => {
    if (!choosing) return;
    const away = (e: PointerEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setChoosing(false);
    };
    const escape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setChoosing(false);
    };
    document.addEventListener('pointerdown', away);
    document.addEventListener('keydown', escape);
    return () => {
      document.removeEventListener('pointerdown', away);
      document.removeEventListener('keydown', escape);
    };
  }, [choosing]);

  const onClick = () => {
    if (picked.length === 0) return;
    if (picked.length > 1) {
      setChoosing((v) => !v);
      return;
    }
    if (showCoverage) hideCoverage();
    else showCoverageFor(picked[0].id);
  };

  return (
    <div className="coverage-button-wrap" ref={rootRef}>
      <button
        type="button"
        className={`coverage-btn${showCoverage ? ' active' : ''}`}
        aria-pressed={showCoverage}
        aria-haspopup={picked.length > 1 ? 'menu' : undefined}
        aria-expanded={picked.length > 1 ? choosing : undefined}
        disabled={picked.length === 0}
        title={
          picked.length === 0
            ? 'Pick a dataset to see its coverage'
            : showCoverage
              ? 'Coverage map on — click to change or hide it'
              : 'Show how densely a dataset covers the world'
        }
        onClick={onClick}
      >
        <svg viewBox="0 0 16 16" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.4" aria-hidden="true">
          <rect x="2" y="2" width="5" height="5" />
          <rect x="9" y="2" width="5" height="5" fill="currentColor" fillOpacity="0.45" />
          <rect x="2" y="9" width="5" height="5" fill="currentColor" fillOpacity="0.2" />
          <rect x="9" y="9" width="5" height="5" fill="currentColor" fillOpacity="0.75" />
        </svg>
        <span>Coverage</span>
      </button>
      {choosing && picked.length > 1 && (
        <div className="coverage-choice" role="menu" aria-label="Coverage of which dataset">
          {picked.map((d) => (
            <button
              key={d.id}
              type="button"
              role="menuitemradio"
              aria-checked={showCoverage && coverageDatasetId === d.id}
              className={`coverage-choice-item${showCoverage && coverageDatasetId === d.id ? ' active' : ''}`}
              onClick={() => {
                showCoverageFor(d.id);
                setChoosing(false);
              }}
            >
              {d.title}
            </button>
          ))}
          {showCoverage && (
            <button
              type="button"
              role="menuitem"
              className="coverage-choice-item off"
              onClick={() => {
                hideCoverage();
                setChoosing(false);
              }}
            >
              Hide coverage
            </button>
          )}
        </div>
      )}
    </div>
  );
}

export default function ControlPanel() {
  const aoi = useAppStore((s) => s.aoi);
  const searching = useAppStore((s) => s.searching);
  const sceneLookupLoading = useAppStore((s) => s.sceneLookupLoading);
  const runSearch = useAppStore((s) => s.runSearch);
  const findSceneByName = useAppStore((s) => s.findSceneByName);
  const sceneNameQuery = useAppStore((s) => s.sceneNameQuery);
  const count = useAppStore((s) => totalItems(s.sections));
  const selectedCount = useAppStore((s) => s.selectedDatasetIds.length);
  const datasetId = useAppStore((s) => s.datasetId);

  // One button for both lookups (M2-17, Otto's redesign): a scene name in the
  // field above takes it, an AOI otherwise — the usual bbox/date search
  // (`runSearch`) is untouched either way, this only decides which of the two
  // it calls. A name takes priority over an AOI rather than requiring both,
  // since the name lookup needs neither AOI nor date range (adr/0001 Z1).
  const hasSceneName = sceneNameQuery.trim().length > 0;
  const busy = searching || sceneLookupLoading;
  // The scene-name lookup and the search both ask every ticked dataset.
  const canSearch = !busy && !!datasetId && selectedCount > 0 && (hasSceneName || !!aoi);
  const search = () => {
    if (!canSearch) return;
    if (hasSceneName) void findSceneByName();
    else void runSearch();
  };

  return (
    <div className="panel control-panel">
      <div className="control-scroll">
        <div className="brand">
          <span className="brand-mark" />
          <div>
            <h1>EarthX</h1>
            <p>Geo and satellite data viewer</p>
          </div>
        </div>

        <SceneNameField onSubmit={search} />

        <label className="field-label">Area of interest</label>
        <PlaceSearchField />
        <Toolbar />
        <AoiExtras />

        <label className="field-label">
          Datasets
          {selectedCount > 0 && <span className="field-label-aside">{selectedCount} selected</span>}
        </label>
        <DatasetPicker />
        <CoverageButton />
        <DatasetNotes />

        <CoverageLegend />

        <AcquisitionDateFields />
      </div>

      {/* Outside the scrolling part, so "Search" is on screen at any window height. */}
      <div className="control-footer">
        <button type="button" className="primary-btn" disabled={!canSearch} onClick={search}>
          {sceneLookupLoading ? 'Finding…' : searching ? 'Searching…' : 'Search'}
        </button>

        {count > 0 && <p className="result-count">{count} scene(s) found</p>}
        {selectedCount === 0 && <p className="hint-text">Select at least one dataset.</p>}
        {!aoi && !hasSceneName && <p className="hint-text">Pick a tool to define an area of interest, or enter a scene name above.</p>}
      </div>
    </div>
  );
}
