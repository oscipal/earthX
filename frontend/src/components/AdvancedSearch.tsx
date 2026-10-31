import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';

import { withinAoiLock, withinAoiTip, withinFilters } from '../aoiFilter';
import type { DatasetOption } from '../datasets';
import {
  filterError,
  groupsOf,
  searchFiltersOf,
  setFilters,
  type FilterInput,
  type SearchFilterDescription,
} from '../searchFilters';
import { useAppStore } from '../store';
import DatasetSelect from './DatasetSelect';
import Popover from './Popover';

type Offer = { dataset: DatasetOption; filters: SearchFilterDescription[] };

function RangeField({
  filter,
  input,
  onChange,
}: {
  filter: SearchFilterDescription;
  input: FilterInput | undefined;
  onChange: (input: FilterInput) => void;
}) {
  const errorId = useId();
  const from = input?.kind === 'range' ? input.from : '';
  const to = input?.kind === 'range' ? input.to : '';
  const error = filterError(filter, input);
  // Text, not `type="number"`: a number field hands over "" for "20-" and keeps showing it, so a half-typed value would
  // silently drop the filter. The keyboard of a phone has no minus on `decimal` and `numeric`.
  const inputMode = filter.minimum < 0 ? 'text' : filter.integer ? 'numeric' : 'decimal';
  const edit = (next: { from?: string; to?: string }) => onChange({ kind: 'range', from, to, ...next });
  return (
    <div className="filter-field">
      <span className="filter-title" title={filter.description}>
        {filter.title}
      </span>
      <div className="filter-range">
        <span>from</span>
        <input
          type="text"
          inputMode={inputMode}
          value={from}
          placeholder={String(filter.minimum)}
          aria-label={`${filter.title}, from`}
          aria-invalid={error?.field === 'from' || error?.field === 'both'}
          aria-describedby={error ? errorId : undefined}
          onChange={(e) => edit({ from: e.target.value })}
        />
        <span>to</span>
        <input
          type="text"
          inputMode={inputMode}
          value={to}
          placeholder={String(filter.maximum)}
          aria-label={`${filter.title}, to`}
          aria-invalid={error?.field === 'to' || error?.field === 'both'}
          aria-describedby={error ? errorId : undefined}
          onChange={(e) => edit({ to: e.target.value })}
        />
        {filter.unit && <span className="filter-unit">{filter.unit}</span>}
      </div>
      {error && (
        <p className="hint-text error" id={errorId}>
          {error.message}
        </p>
      )}
    </div>
  );
}

function ValuesField({
  filter,
  input,
  onChange,
}: {
  filter: SearchFilterDescription;
  input: FilterInput | undefined;
  onChange: (input: FilterInput) => void;
}) {
  const ticked = input?.kind === 'values' ? input.values : [];
  const toggle = (value: string) =>
    onChange({ kind: 'values', values: ticked.includes(value) ? ticked.filter((v) => v !== value) : [...ticked, value] });
  return (
    <fieldset className="filter-field">
      <legend className="filter-title" title={filter.description}>
        {filter.title}
      </legend>
      <div className="filter-values">
        {filter.values.map((option) => (
          <label key={option.value} className="filter-check">
            <input type="checkbox" checked={ticked.includes(option.value)} onChange={() => toggle(option.value)} />
            {option.label}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

// The line of a dataset in the box and in its list: the title, and a dot where it has filters set.
function OfferLine({ offer, set }: { offer: Offer; set: boolean }) {
  return (
    <span className="dataset-select-line">
      <span className="dataset-select-title" title={offer.dataset.title}>
        {offer.dataset.title}
      </span>
      {set && <span className="filter-dot" role="img" aria-label="Filters set" title="Filters set" />}
    </span>
  );
}

// The switch at the top of the pop-up (Otto, 31.10.2026): the filters that depend on the area, which the registry marks
// with `within_aoi`, are measured inside the AOI instead of over the whole scene; the others stay as they are. It needs an
// area and a date range with both ends; without them it is locked (not hidden, Otto 26.10.2026) and shows why, off, as the
// search does not use it either. What it changes and where the classification stops being right is the registry's, read
// into the tooltip.
function WithinAoiSwitch({
  on,
  lock,
  tip,
  onChange,
}: {
  on: boolean;
  lock: string | null;
  tip: string;
  onChange: (on: boolean) => void;
}) {
  const locked = lock !== null;
  return (
    <label className={`within-aoi${locked ? ' locked' : ''}`} title={lock ?? tip}>
      <input
        type="checkbox"
        role="switch"
        checked={on && !locked}
        aria-disabled={locked || undefined}
        onChange={() => {
          if (!locked) onChange(!on);
        }}
      />
      Filter within AOI only
    </label>
  );
}

// One filter of the registry as its fields. The one place a filter is turned into fields.
function FilterRow({
  filter,
  input,
  onChange,
}: {
  filter: SearchFilterDescription;
  input: FilterInput | undefined;
  onChange: (input: FilterInput) => void;
}) {
  return filter.kind === 'range' ? (
    <RangeField filter={filter} input={input} onChange={onChange} />
  ) : (
    <ValuesField filter={filter} input={input} onChange={onChange} />
  );
}

// The button "Advanced search · 2" above "Search" and the pop-up it opens (DS-02c, Otto 30.10.2026): the filters the
// registry offers for the ticked datasets, one dataset at a time, under the headings the registry gives them. Each
// dataset has its own values (nothing is shared across datasets); a dataset without filters is not in the box, and
// the button is there only while a ticked dataset has some. What a filter is and where it stands is the registry's: a
// filter it adds shows up here without a change, and this knows no property and no dataset. The values stay in the
// store when the pop-up closes, whichever way it does.
export default function AdvancedSearch() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const searchFilters = useAppStore((s) => s.searchFilters);
  const searchWithin = useAppStore((s) => s.searchWithin);
  const setSearchWithin = useAppStore((s) => s.setSearchWithin);
  const setSearchFilter = useAppStore((s) => s.setSearchFilter);
  const resetSearchFilters = useAppStore((s) => s.resetSearchFilters);
  const lock = useAppStore((s) => withinAoiLock(s));
  const [open, setOpen] = useState(false);
  const [shownId, setShownId] = useState<string | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const fieldsRef = useRef<HTMLDivElement>(null);
  const close = useCallback(() => setOpen(false), []);
  const dialogId = useId();

  const offers = useMemo<Offer[]>(
    () =>
      datasets
        .filter((d) => d.viewable && selectedDatasetIds.includes(d.id))
        .map((dataset) => ({ dataset, filters: searchFiltersOf(dataset.collection) }))
        .filter((offer) => offer.filters.length > 0),
    [datasets, selectedDatasetIds],
  );
  // The last dataset with filters is unticked while the pop-up is open: it goes, and does not come back with the next.
  useEffect(() => {
    if (offers.length === 0) setOpen(false);
  }, [offers.length]);
  // The area or the dates go while the switch is on: it goes off with them, in every dataset, so that it does not come
  // back on its own with the next area (the search does not use it meanwhile either).
  useEffect(() => {
    if (lock === null) return;
    for (const [datasetId, on] of Object.entries(searchWithin)) if (on) setSearchWithin(datasetId, false);
  }, [lock, searchWithin, setSearchWithin]);
  if (offers.length === 0) return null;

  const shown = offers.find((o) => o.dataset.id === shownId) ?? offers[0];
  const setOf = (offer: Offer) => setFilters(offer.filters, searchFilters[offer.dataset.id]);
  const active = offers.filter((offer) => setOf(offer).length > 0);
  const count = active.reduce((sum, offer) => sum + setOf(offer).length, 0);
  const wrong = offers.some((offer) => offer.filters.some((f) => filterError(f, searchFilters[offer.dataset.id]?.[f.property])));
  const tooltip =
    count > 0
      ? active.map((offer) => `${offer.dataset.title}: ${setOf(offer).map((f) => f.title).join(', ')}`).join('\n')
      : 'Narrow the search by what the scenes of a dataset say about themselves';
  const own = searchFilters[shown.dataset.id];
  const groups = groupsOf(shown.filters);

  return (
    <>
      <button
        ref={buttonRef}
        type="button"
        className={`ghost-btn advanced-btn${wrong ? ' wrong' : ''}`}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? dialogId : undefined}
        title={tooltip}
        onClick={() => setOpen((v) => !v)}
      >
        Advanced search{count > 0 && ` · ${count}`}
      </button>
      <Popover
        anchorRef={buttonRef}
        open={open}
        onClose={close}
        className="advanced-popup"
        role="dialog"
        ariaLabel="Advanced search"
        focusOnOpen
        form
      >
        <div id={dialogId} className="advanced-popup-body">
          <DatasetSelect
            className="plain"
            label="Dataset"
            labelId={`${dialogId}-dataset`}
            listLabel="Datasets with filters"
            choices={offers.map((offer) => ({
              id: offer.dataset.id,
              content: <OfferLine offer={offer} set={setOf(offer).length > 0} />,
            }))}
            shownId={shown.dataset.id}
            onChoose={setShownId}
          />
          {withinFilters(shown.filters).length > 0 && (
            <WithinAoiSwitch
              on={searchWithin[shown.dataset.id] === true}
              lock={lock}
              tip={withinAoiTip(shown.filters, shown.dataset.collection['earthx:mask'])}
              onChange={(on) => setSearchWithin(shown.dataset.id, on)}
            />
          )}
          <div className="advanced-fields" ref={fieldsRef}>
            {groups.map((group) => (
              <section key={group.name} className="filter-group" aria-label={group.name}>
                {groups.length > 1 && <h3 className="filter-group-title">{group.name}</h3>}
                {group.filters.map((filter) => (
                  <FilterRow
                    key={filter.property}
                    filter={filter}
                    input={own?.[filter.property]}
                    onChange={(next) => setSearchFilter(shown.dataset.id, filter.property, next)}
                  />
                ))}
              </section>
            ))}
          </div>
          <div className="advanced-actions">
            {(setOf(shown).length > 0 || searchWithin[shown.dataset.id] === true) && (
              <button
                type="button"
                className="ghost-btn"
                onClick={() => {
                  resetSearchFilters(shown.dataset.id);
                  // The button goes with the filters; the keyboard user stays in the pop-up.
                  fieldsRef.current?.querySelector<HTMLElement>('input')?.focus();
                }}
              >
                Reset filters
              </button>
            )}
            <button
              type="button"
              className="primary-btn"
              onClick={() => {
                close();
                buttonRef.current?.focus();
              }}
            >
              Done
            </button>
          </div>
        </div>
      </Popover>
    </>
  );
}
