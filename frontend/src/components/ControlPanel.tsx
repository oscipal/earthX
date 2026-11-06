import { useCallback, useLayoutEffect, useRef, useState, type CSSProperties } from 'react';

import type { CoverageHistogramPoint, PlaceResult } from '../api';
import { readAoiFile } from '../aoiFile';
import { completenessNote } from '../coverage';
import { DATASETS_PER_ROW, MAX_DATASET_ROWS, pageCount, pageOf, pageSlice, rowsThatFit } from '../datasetPages';
import { clampDay, dateBounds, todayUtc, type DayBounds } from '../dateBounds';
import { acquisitionNote, maturityLabel, maturityNote } from '../datasets';
import { bufferPointToPolygon, polygonBbox } from '../geoUtils';
import { PLACE_SEARCH_PROVENANCE, placeAoi, searchPlaces } from '../placeSearch';
import { focusFirstItem } from '../popover';
import { totalItems } from '../sections';
import { searchFiltersInvalid, useAppStore } from '../store';
import AdvancedSearch from './AdvancedSearch';
import ClearableInput from './ClearableInput';
import { ChevronLeftIcon, ChevronRightIcon, CoverageIcon, HistoryIcon, UploadIcon } from './icons';
import Popover from './Popover';
import Tip from './Tip';
import Toolbar from './Toolbar';
import { counted } from '../plural';

// A date input plus a transparent button covering its calendar icon
// (V-5). The tech theme draws its own icon and hides the native
// `::-webkit-calendar-picker-indicator` behind `padding-right`, but that
// padding also pushes the engine's real (invisible) hit-box for the
// indicator inward, out from under the icon we draw at a fixed offset —
// clicking the visible icon then misses the part that actually opens the
// picker. `showPicker()` sidesteps the mismatch instead of chasing it
// pixel by pixel.
//
// UI-05 §3.3: the calendar offers only the days of the chosen datasets (`min`/`max`); a day typed outside them is moved
// onto the nearest one when the field is left.
function DateField({
  value,
  onChange,
  label,
  disabled,
  bounds,
  lockReason,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  disabled?: boolean;
  bounds: DayBounds | null;
  lockReason?: string;
}) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <div className="date-field">
      <input autoComplete="off"
        ref={ref}
        type="date"
        value={value}
        min={bounds?.min ?? undefined}
        max={bounds?.max ?? undefined}
        onChange={(e) => onChange(e.target.value)}
        onBlur={(e) => {
          const day = clampDay(e.target.value, bounds);
          if (day !== e.target.value) onChange(day);
        }}
        aria-label={label}
        disabled={disabled}
        data-tip={disabled ? lockReason : undefined}
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
// dataset picked may well have a time axis), but are locked. With several datasets
// ticked (M3-10) the window still means something for those that have a time axis,
// so the fields lock only when *none* of the ticked ones has one.
//
// UI-05 (Otto, 06.11.2026): no text under the fields. Locked, the acquisition period stands in their tooltip; with some
// of the ticked datasets without a time axis, behind an (i) at the label. The days offered are those of the ticked
// datasets with one (`dateBounds`).
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
  const notes = withoutTimeAxis.map((d) => {
    const note = acquisitionNote(d.collection) ?? 'No time axis';
    return ticked.length > 1 ? `${d.title}: ${note}` : note;
  });
  const reason = notes.join('\n');
  const bounds = dateBounds(datasets, selectedDatasetIds, todayUtc());
  return (
    <>
      <div className="field-label date-label">
        <span>Acquisition date</span>
        {!locked && notes.length > 0 && <Tip text={reason} />}
      </div>
      <div className="date-row">
        <DateField value={dateFrom} onChange={setDateFrom} label="From date" disabled={locked} bounds={bounds} lockReason={reason} />
        <span>→</span>
        <DateField value={dateTo} onChange={setDateTo} label="To date" disabled={locked} bounds={bounds} lockReason={reason} />
      </div>
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
  const rowRef = useRef<HTMLDivElement>(null);
  const resultsRef = useRef<HTMLDivElement>(null);
  const closeResults = useCallback(() => setShowResults(false), []);

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

  // The attribution of the place picked (UI-05, F8: behind an (i) at the field, not as a line under it) only holds while
  // the store's AOI is still (by identity) the geometry this field handed to `setAoi` — a redraw, an upload or "Clear"
  // replaces that object, so the (i) goes without this field having to know why the AOI changed.
  const stillActive = !!picked && currentAoi === picked.geometry;

  return (
    <div className="place-search">
      <div className="place-search-row" ref={rowRef}>
        <ClearableInput
          value={query}
          onChange={setQuery}
          onClear={closeResults}
          clearLabel="Clear place name"
          onKeyDown={(e) => {
            if (e.key === 'Enter') void runSearch();
            if (e.key === 'ArrowDown' && showResults) {
              e.preventDefault();
              focusFirstItem(resultsRef.current);
            }
          }}
          placeholder="Place name"
          aria-label="Place"
          maxLength={200}
        />
        <button
          type="button"
          className="btn"
          aria-busy={searching}
          disabled={searching || !query.trim()}
          data-tip-level="advanced" data-tip={searching ? 'Looking for the place…' : !query.trim() ? 'Type a place name first' : 'Find the place on the map'}
          onClick={() => void runSearch()}
        >
          {searching ? 'Finding…' : 'Find'}
        </button>
        {stillActive && picked && <Tip text={`${picked.name} · ${PLACE_SEARCH_PROVENANCE.attribution}`} />}
      </div>
      <Popover anchorRef={rowRef} open={showResults} onClose={closeResults} className="place-results" ariaLabel="Places found">
        <div ref={resultsRef}>
          {results.length === 0 && <p className="hint">No place found.</p>}
          {results.map((r, i) => (
            <button
              key={`${r.display_name}-${i}`}
              type="button"
              className="place-result"
              data-tip-level="advanced" data-tip={r.outline_simplified ? 'Outline simplified' : undefined}
              onClick={() => choose(r)}
            >
              <span className="place-result-name">{r.name}</span>
              <span className="place-result-kind">{r.kind.split('/')[0]}</span>
              <span className="place-result-display">{r.display_name}</span>
            </button>
          ))}
          {attribution && (
            <p className="hint place-attribution">
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
      </Popover>
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
        className="btn"
        aria-busy={uploading}
        data-tip-level="advanced" data-tip="Upload a GeoJSON, KML or zipped Shapefile (max. 1 MB) as the AOI"
      >
        <input
          type="file"
          accept=".geojson,.json,.kml,.zip"
          onChange={onFile}
          disabled={uploading}
          hidden
        />
        <span>
          <UploadIcon size={14} lead />{uploading ? 'Reading…' : 'Upload AOI'}
        </span>
      </label>
      <button
        type="button"
        className="btn"
        disabled={!lastAoi}
        data-tip-level="advanced" data-tip={lastAoi ? 'Reuse the previous AOI' : 'No earlier AOI in this browser'}
        onClick={() => applyLastAoi()}
      >
        <span>
          <HistoryIcon size={14} lead />Last AOI
        </span>
      </button>
    </div>
  );
}

// How settled the source of each ticked dataset is (D23: "staging" must not be
// something a user finds out only once the source disappears): a warning at the
// label "Datasets", not a paragraph (UI-05, Otto 06.11.2026); the chip on the button stays.
//
// No "last checked" date is shown next to it: `earthx:health` carries only
// `status` (M2-08-3, 2026-09-23) — the field it used to carry alongside dated only
// the onboarding check, not an actual health check, and stating that would claim
// something the platform does not know. A real check date comes with the health
// checks in M5.
function MaturityTip() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const ticked = datasets.filter((d) => selectedDatasetIds.includes(d.id));
  const notes = ticked.flatMap((d) => {
    const maturity = maturityNote(d.collection);
    return maturity ? [ticked.length > 1 ? `${d.title}: ${maturity}` : maturity] : [];
  });
  if (notes.length === 0) return null;
  return <Tip tone="warn" text={notes.join('\n')} />;
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
      <ClearableInput
        id="scene-name-input"
        value={query}
        placeholder="e.g. S2C_T32TNT_20260920T103025_L2A"
        onChange={setQuery}
        clearLabel="Clear scene name"
        onKeyDown={(e) => {
          if (e.key === 'Enter') onSubmit();
        }}
      />
    </div>
  );
}

// The small "Select multiple datasets" check box beside the "Datasets" label (M4-29).
function MultiSelectToggle() {
  const multiSelect = useAppStore((s) => s.multiSelect);
  const setMultiSelect = useAppStore((s) => s.setMultiSelect);
  const busy = useAppStore((s) => s.searching || s.sceneLookupLoading);
  return (
    <label className="multi-select-toggle" data-tip-level="advanced" data-tip="Choose several datasets and search them together">
      <input type="checkbox" checked={multiSelect} disabled={busy} onChange={(e) => setMultiSelect(e.target.checked)} />
      Select multiple datasets
    </label>
  );
}

// The dataset choice (M3-10, M4-29): one button per dataset from
// `/stac/collections`. Nothing is picked at the start; a click picks exactly that
// dataset (drawn highlighted) and drops the one before; a click on the chosen one
// drops it. Only with "Select multiple datasets" on can several be picked, and
// then every picked dataset is searched together, also those on another page.
// A dataset that cannot be shown stays listed, disabled, with the reason.
//
// UI-05 (Otto, 06.11.2026): pages of at most six buttons, two a row, with as many rows as the panel holds without
// scrolling (measured, at least one), and "‹ 1 / 3 ›" under them, also with one page. The grid keeps the height of a full
// page, so that the last page does not let the panel jump. When the size of a page changes, the page of the dataset
// picked last is shown.
function DatasetPicker() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const anchorId = useAppStore((s) => s.lastPickedDatasetId ?? s.selectedDatasetIds[0] ?? null);
  const toggle = useAppStore((s) => s.toggleDatasetSelected);
  const busy = useAppStore((s) => s.searching || s.sceneLookupLoading);
  const listRef = useRef<HTMLDivElement>(null);
  const [rows, setRows] = useState(MAX_DATASET_ROWS);
  const [page, setPage] = useState(0);
  const pageSize = rows * DATASETS_PER_ROW;
  // Only a new page size moves the page, to the one of the dataset picked last; a pick on the page shown leaves it.
  const [sizeSeen, setSizeSeen] = useState(pageSize);
  if (sizeSeen !== pageSize) {
    setSizeSeen(pageSize);
    const index = datasets.findIndex((d) => d.id === anchorId);
    if (index >= 0) setPage(pageOf(index, pageSize));
  }
  const pages = pageCount(datasets.length, pageSize);
  const shownPage = Math.min(page, pages - 1);
  const drawnRows = Math.min(rows, Math.ceil(datasets.length / DATASETS_PER_ROW));

  useLayoutEffect(() => {
    const list = listRef.current;
    const scroll = list?.closest('.control-scroll');
    if (!list || !scroll || typeof ResizeObserver === 'undefined') return;
    const measure = () => {
      const grid = getComputedStyle(list);
      const step = parseFloat(grid.gridAutoRows) + parseFloat(grid.rowGap);
      const last = scroll.lastElementChild;
      const bottom = last ? last.getBoundingClientRect().bottom : scroll.getBoundingClientRect().top;
      const content = bottom - scroll.getBoundingClientRect().top + scroll.scrollTop + parseFloat(getComputedStyle(scroll).paddingBottom);
      setRows(rowsThatFit(drawnRows, scroll.clientHeight - content, step));
    };
    const observer = new ResizeObserver(measure);
    observer.observe(scroll);
    for (const child of scroll.children) observer.observe(child);
    return () => observer.disconnect();
  });


  if (datasets.length === 0) return null;
  const first = shownPage === 0;
  const last = shownPage === pages - 1;
  return (
    <>
      <div
        ref={listRef}
        className="dataset-list"
        role="group"
        aria-label="Datasets"
        style={{ '--dataset-rows': drawnRows } as CSSProperties}
      >
        {pageSlice(datasets, shownPage, pageSize).map((d) => {
          const picked = selectedDatasetIds.includes(d.id);
          const label = d.viewable ? maturityLabel(d.collection) : null;
          return (
            <button
              key={d.id}
              type="button"
              className="btn dataset-toggle"
              data-tip={d.viewable ? undefined : `${d.title} — not viewable: ${d.reason}`}
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
      <div className="dataset-pages" role="group" aria-label="Pages of datasets">
        <button
          type="button"
          className="icon-btn sm"
          aria-label="Previous page"
          aria-disabled={first || undefined}
          data-tip-level="advanced"
          data-tip={first ? 'Already on the first page' : 'Previous page'}
          onClick={() => {
            if (!first) setPage(shownPage - 1);
          }}
        >
          <ChevronLeftIcon size={14} />
        </button>
        <span className="dataset-page-count">
          {shownPage + 1} / {pages}
        </span>
        <button
          type="button"
          className="icon-btn sm"
          aria-label="Next page"
          aria-disabled={last || undefined}
          data-tip-level="advanced"
          data-tip={last ? 'Already on the last page' : 'Next page'}
          onClick={() => {
            if (!last) setPage(shownPage + 1);
          }}
        >
          <ChevronRightIcon size={14} />
        </button>
      </div>
    </>
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
            data-tip-level="advanced" data-tip={`${month}: ${bucket.n}`}
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
      <p className="hint coverage-dataset-name">
        Coverage · {title}
        {coverage && <Tip text="Scenes counted by their center point in the cell" />}
      </p>
      {coverageLoading && <p className="hint">Loading coverage…</p>}
      {coverageError && <p className="error">{coverageError}</p>}
      {coverage && (
        <div className="coverage-legend">
          <div className="legend-scale">
            <span className="legend-gradient" />
            <span className="legend-scale-labels">
              <span>1</span>
              <span>{coverage.max_count}</span>
            </span>
          </div>
          {note && <p className="hint coverage-note">{note}</p>}
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
// apart from them. One dataset picked: a click shows its coverage (or hides it
// again). Several picked: the click first offers the choice of which dataset,
// lying over what is below — nothing is drawn until one is chosen. The choice holds only datasets (UI-04 part 4, Otto,
// 4.11.2026): the map is switched on and off with the buttons, not with an entry of the choice. Beside "Coverage",
// "Hide coverage", on only while a coverage map is shown; the two fill the panel's width. Off by default (M2-07c).
function CoverageButton() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const showCoverage = useAppStore((s) => s.showCoverage);
  const coverageDatasetId = useAppStore((s) => s.coverageDatasetId);
  const showCoverageFor = useAppStore((s) => s.showCoverageFor);
  const hideCoverage = useAppStore((s) => s.hideCoverage);
  const [choosing, setChoosing] = useState(false);
  const rowRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setChoosing(false), []);
  const picked = datasets.filter((d) => selectedDatasetIds.includes(d.id));

  const onClick = () => {
    if (picked.length === 0) return;
    if (picked.length > 1) {
      setChoosing((v) => !v);
      return;
    }
    if (showCoverage) hideCoverage();
    else showCoverageFor(picked[0].id);
  };
  const chosen = (act: () => void) => {
    act();
    setChoosing(false);
    buttonRef.current?.focus();
  };

  return (
    <div className="coverage-button-wrap" ref={rowRef}>
      <button
        ref={buttonRef}
        type="button"
        className="btn"
        aria-pressed={showCoverage}
        aria-haspopup={picked.length > 1 ? 'menu' : undefined}
        aria-expanded={picked.length > 1 ? choosing : undefined}
        disabled={picked.length === 0}
        data-tip-level="advanced" data-tip={
          picked.length === 0
            ? 'Choose a dataset to see its coverage'
            : showCoverage
              ? 'Coverage map on — click to change or hide it'
              : 'Show how densely a dataset covers the world'
        }
        onClick={onClick}
        onKeyDown={(e) => {
          if (picked.length > 1 && e.key === 'ArrowDown') {
            e.preventDefault();
            setChoosing(true);
          }
        }}
      >
        <CoverageIcon size={14} />
        <span>Coverage</span>
      </button>
      <button
        type="button"
        className="btn"
        disabled={!showCoverage}
        data-tip-level="advanced" data-tip={showCoverage ? 'Hide the coverage map' : 'No coverage map is shown'}
        onClick={() => hideCoverage()}
      >
        Hide coverage
      </button>
      <Popover
        anchorRef={rowRef}
        open={choosing && picked.length > 1}
        onClose={close}
        className="coverage-choice"
        role="menu"
        ariaLabel="Coverage of which dataset"
        focusOnOpen
      >
        {picked.map((d) => (
          <button
            key={d.id}
            type="button"
            role="menuitemradio"
            aria-checked={showCoverage && coverageDatasetId === d.id}
            className={`coverage-choice-item${showCoverage && coverageDatasetId === d.id ? ' active' : ''}`}
            onClick={() => chosen(() => showCoverageFor(d.id))}
          >
            {d.title}
          </button>
        ))}
      </Popover>
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
  const filtersWrong = useAppStore(searchFiltersInvalid);

  // One button for both lookups (M2-17, Otto's redesign): a scene name in the
  // field above takes it, an AOI otherwise — the usual bbox/date search
  // (`runSearch`) is untouched either way, this only decides which of the two
  // it calls. A name takes priority over an AOI rather than requiring both,
  // since the name lookup needs neither AOI nor date range (adr/0001 Z1).
  const hasSceneName = sceneNameQuery.trim().length > 0;
  const busy = searching || sceneLookupLoading;
  // The scene-name lookup and the search both ask every ticked dataset.
  // The filters of "Advanced search" belong to the search of an area; the lookup of a name does not read them.
  const canSearch = !busy && !!datasetId && selectedCount > 0 && (hasSceneName || (!!aoi && !filtersWrong));
  // Why "Search" is held back, for its tooltip (UI-04: a locked control says why).
  const searchBlock = busy
    ? 'A search is running'
    : selectedCount === 0 || !datasetId
      ? 'Choose a dataset to search'
      : hasSceneName
        ? null
        : !aoi
          ? 'Choose a tool to define an AOI, or enter a scene name'
          : filtersWrong
            ? 'Correct the filters in Advanced search'
            : null;
  const search = () => {
    if (!canSearch) return;
    if (hasSceneName) void findSceneByName();
    else void runSearch();
  };

  return (
    <div className="panel dock-panel control-panel">
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

        <div className="field-label dataset-label">
          <span>
            Datasets
            <MaturityTip />
          </span>
          <MultiSelectToggle />
        </div>
        <DatasetPicker />
        <CoverageButton />

        <CoverageLegend />

        <AcquisitionDateFields />
      </div>

      {/* Outside the scrolling part, so "Search" is on screen at any window height. */}
      <div className="control-footer">
        <AdvancedSearch />
        <button type="button" className="btn primary" disabled={!canSearch} data-tip={canSearch ? undefined : (searchBlock ?? undefined)} onClick={search}>
          {sceneLookupLoading ? 'Finding…' : searching ? 'Searching…' : 'Search'}
        </button>

        {count > 0 && <p className="result-count">{counted(count, 'scene')} found</p>}
        {filtersWrong && !hasSceneName && <p className="error">Correct the filters in Advanced search.</p>}
      </div>
    </div>
  );
}
