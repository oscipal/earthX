import { useId, useMemo, useState } from 'react';

import type { DatasetOption } from '../datasets';
import {
  filterError,
  searchFiltersOf,
  setFilters,
  type FilterInput,
  type SearchFilterDescription,
} from '../searchFilters';
import { useAppStore } from '../store';
import DatasetSelect from './DatasetSelect';

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
  const bounds = { min: filter.minimum, max: filter.maximum, step: filter.integer ? 1 : 'any', inputMode: 'decimal' } as const;
  const edit = (next: { from?: string; to?: string }) => onChange({ kind: 'range', from, to, ...next });
  return (
    <div className="filter-field">
      <span className="filter-title" title={filter.description}>
        {filter.title}
      </span>
      <div className="filter-range">
        <span>from</span>
        <input
          type="number"
          {...bounds}
          value={from}
          placeholder={String(filter.minimum)}
          aria-label={`${filter.title}, from`}
          aria-invalid={error?.field === 'from' || error?.field === 'both'}
          aria-describedby={error ? errorId : undefined}
          onChange={(e) => edit({ from: e.target.value })}
        />
        <span>to</span>
        <input
          type="number"
          {...bounds}
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

// "Advanced search" (DS-02c, Otto 28.10.2026): the filters the registry offers for the ticked datasets, one dataset
// at a time. Each dataset has its own values (nothing is shared across datasets), a dataset without filters is not
// in the box, and the whole section is there only while a ticked dataset has some. What a filter does is the
// registry's: this knows no property and no dataset.
export default function AdvancedSearch() {
  const datasets = useAppStore((s) => s.datasets);
  const selectedDatasetIds = useAppStore((s) => s.selectedDatasetIds);
  const searchFilters = useAppStore((s) => s.searchFilters);
  const setSearchFilter = useAppStore((s) => s.setSearchFilter);
  const resetSearchFilters = useAppStore((s) => s.resetSearchFilters);
  const [open, setOpen] = useState(false);
  const [shownId, setShownId] = useState<string | null>(null);
  const bodyId = useId();

  const offers = useMemo<Offer[]>(
    () =>
      datasets
        .filter((d) => d.viewable && selectedDatasetIds.includes(d.id))
        .map((dataset) => ({ dataset, filters: searchFiltersOf(dataset.collection) }))
        .filter((offer) => offer.filters.length > 0),
    [datasets, selectedDatasetIds],
  );
  if (offers.length === 0) return null;

  const shown = offers.find((o) => o.dataset.id === shownId) ?? offers[0];
  const setOf = (offer: Offer) => setFilters(offer.filters, searchFilters[offer.dataset.id]);
  const active = offers.filter((offer) => setOf(offer).length > 0);
  const wrong = offers.some((offer) => offer.filters.some((f) => filterError(f, searchFilters[offer.dataset.id]?.[f.property])));
  const tooltip =
    active.length > 0
      ? active.map((offer) => `${offer.dataset.title}: ${setOf(offer).map((f) => f.title).join(', ')}`).join('\n')
      : 'Narrow the search by what the scenes of a dataset say about themselves';
  const own = searchFilters[shown.dataset.id];

  return (
    <div className="advanced-search">
      <button
        type="button"
        className="advanced-head"
        aria-expanded={open}
        aria-controls={bodyId}
        title={tooltip}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="rg-caret">{open ? '▾' : '▸'}</span>
        <span>Advanced search</span>
        {active.length > 0 && (
          <span className="advanced-count">
            · {active.length} {active.length === 1 ? 'dataset' : 'datasets'}
          </span>
        )}
        {wrong && <span className="advanced-count wrong">· check input</span>}
      </button>
      {open && (
        <div className="advanced-body" id={bodyId}>
          <DatasetSelect
            className="plain"
            label="Dataset"
            labelId={`${bodyId}-dataset`}
            listLabel="Datasets with filters"
            choices={offers.map((offer) => ({
              id: offer.dataset.id,
              content: <OfferLine offer={offer} set={setOf(offer).length > 0} />,
            }))}
            shownId={shown.dataset.id}
            onChoose={setShownId}
          />
          {shown.filters.map((filter) => {
            const input = own?.[filter.property];
            const onChange = (next: FilterInput) => setSearchFilter(shown.dataset.id, filter.property, next);
            return filter.kind === 'range' ? (
              <RangeField key={filter.property} filter={filter} input={input} onChange={onChange} />
            ) : (
              <ValuesField key={filter.property} filter={filter} input={input} onChange={onChange} />
            );
          })}
          {setOf(shown).length > 0 && (
            <button type="button" className="ghost-btn reset-filters" onClick={() => resetSearchFilters(shown.dataset.id)}>
              Reset filters
            </button>
          )}
        </div>
      )}
    </div>
  );
}
