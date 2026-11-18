// The Data catalogue (UI-05 §4, Otto 06.11.2026): a window over the map, opened and closed with its symbol in the rail
// and closed with the red x as well; Esc and a click beside it close nothing (leitfaden §5). The list at the left holds
// the entries of each category, full and listed ones together (M5-40), with "Add" or "Remove" for "Search and area" or
// the link "Source"; each group loads its entries a page at a time, the next one when the end of the group shows in the
// window. The details of the chosen entry stand at the right, and below 900 px on a stage of their own with "Back". The
// head is its own area: the search of `adr/0026` comes in as a second row later (F6).

import { useEffect, useRef, useState, type ReactNode, type RefObject } from 'react';

import { fetchCataloguePage, fetchCatalogueSearch, type CatalogueFilter } from '../api';
import { LOCK_NEEDS_AOI } from '../aoiFilter';
import {
  accountOf,
  type BandLine,
  activeFilters,
  catalogueRows,
  groupCount,
  isListed,
  listedSourceOf,
  notAddableReason,
  prototypeNote,
  sourceRow,
  withOther,
  type LinkText,
} from '../catalogue';
import { datasetsFrom, maturityLabel, type DatasetOption } from '../datasets';
import { CATALOGUE_ID } from '../dock';
import { useAppStore } from '../store';
import Badge from './Badge';
import ClearableInput from './ClearableInput';
import CloseButton from './CloseButton';
import { DateField } from './ControlPanel';
import { ArrowLeftIcon, ChevronDownIcon, ChevronRightIcon, ClearIcon, PlusIcon, SearchIcon, TrashIcon } from './icons';
import Popover from './Popover';
import Tip from './Tip';

function Marks({ dataset }: { dataset: DatasetOption }) {
  // A listed entry carries no mark (M5-40 plan F6).
  if (isListed(dataset.collection)) return null;
  const maturity = maturityLabel(dataset.collection);
  return (
    <>
      {prototypeNote(dataset.collection) && <Badge>Prototype</Badge>}
      {accountOf(dataset.collection) && <Badge>Account</Badge>}
      {maturity && <Badge>{maturity}</Badge>}
    </>
  );
}

function Links({ values }: { values: LinkText[] }) {
  return (
    <>
      {values.map((value, index) => (
        <span key={index} className="catalogue-value">
          {value.href ? (
            <a href={value.href} target="_blank" rel="noopener noreferrer">
              {value.text}
            </a>
          ) : (
            value.text
          )}
        </span>
      ))}
    </>
  );
}

// "Add", "Remove", or the link to the source of a dataset that needs an account (W0).
function RowAction({ dataset }: { dataset: DatasetOption }) {
  const added = useAppStore((s) => s.addedDatasetIds.includes(dataset.id));
  const tickedWhileBusy = useAppStore(
    (s) => s.selectedDatasetIds.includes(dataset.id) && (s.searching || s.sceneLookupLoading),
  );
  const addDataset = useAppStore((s) => s.addDataset);
  const removeDataset = useAppStore((s) => s.removeDataset);
  if (isListed(dataset.collection)) {
    const page = listedSourceOf(dataset.collection);
    return page ? (
      <a className="btn catalogue-action" href={page} target="_blank" rel="noopener noreferrer" data-tip-level="advanced" data-tip="Open at the source">
        Source
      </a>
    ) : null;
  }
  if (added) {
    const reason = tickedWhileBusy ? 'Wait until the search is finished' : null;
    return (
      <button
        type="button"
        className="btn catalogue-action"
        aria-disabled={reason ? true : undefined}
        aria-label={`Remove ${dataset.title}`}
        data-tip-level={reason ? undefined : 'advanced'}
        data-tip={reason ?? 'Remove from Search and area'}
        onClick={() => {
          if (!reason) removeDataset(dataset.id);
        }}
      >
        <TrashIcon lead size={14} />
        Remove
      </button>
    );
  }
  const [source] = sourceRow(dataset.collection);
  if (accountOf(dataset.collection) && source?.href) {
    return (
      <a className="btn catalogue-action" href={source.href} target="_blank" rel="noopener noreferrer" data-tip-level="advanced" data-tip="Needs an account at the source">
        Source
      </a>
    );
  }
  const reason = notAddableReason(dataset);
  return (
    <button
      type="button"
      className="btn catalogue-action"
      aria-disabled={reason ? true : undefined}
      aria-label={`Add ${dataset.title}`}
      data-tip-level={reason ? undefined : 'advanced'}
      data-tip={reason ?? 'Add to Search and area'}
      onClick={() => {
        if (!reason) addDataset(dataset.id);
      }}
    >
      <PlusIcon lead size={14} />
      Add
    </button>
  );
}

// The bands of a dataset: Band | Description | Unit (M5-59). The window scrolls, not the table.
function BandTable({ bands }: { bands: BandLine[] }) {
  return (
    <table className="catalogue-bands">
      <thead>
        <tr>
          <th scope="col">Band</th>
          <th scope="col">Description</th>
          <th scope="col">Unit</th>
        </tr>
      </thead>
      <tbody>
        {bands.map((line) => (
          <tr key={line.band}>
            <th scope="row">{line.band}</th>
            <td>{line.description}</td>
            <td>{line.unit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Details({ dataset, onBack }: { dataset: DatasetOption; onBack: () => void }) {
  const legal = prototypeNote(dataset.collection);
  return (
    <section className="catalogue-details" aria-label={`Details of ${dataset.title}`}>
      <button type="button" className="btn catalogue-back" onClick={onBack}>
        <ArrowLeftIcon lead />
        Back
      </button>
      <h3 className="catalogue-title">
        {dataset.title}
        <Marks dataset={dataset} />
        {legal && <Tip tone="warn" text={legal} />}
      </h3>
      <dl className="catalogue-rows">
        {catalogueRows(dataset).map((row) => (
          <div key={row.label} className="catalogue-row-pair">
            <dt>
              {row.label}
              {row.tip && <Tip text={row.tip} />}
            </dt>
            <dd>{row.bands ? <BandTable bands={row.bands} /> : <Links values={row.values} />}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// Entries per page of a group.
const PAGE = 50;
// How long the search waits after the last key before it asks (ms).
const SEARCH_DELAY = 300;
// The longest text the search takes (`catalog.search.MAX_QUERY_CHARS`).
const MAX_SEARCH_CHARS = 200;

// One entry of a group or of the hits: its name opens the details, at the right "Add", "Remove" or "Source".
function EntryRow({ dataset, shownId, onShow }: { dataset: DatasetOption; shownId: string | null; onShow: (d: DatasetOption) => void }) {
  return (
    <li className="catalogue-entry" aria-current={dataset.id === shownId || undefined}>
      <button type="button" className="catalogue-entry-name" onClick={() => onShow(dataset)}>
        <span className="catalogue-entry-title">{dataset.title}</span>
        <Marks dataset={dataset} />
      </button>
      <RowAction dataset={dataset} />
    </li>
  );
}

interface Pages<K> {
  entries: DatasetOption[];
  next: K | null;
  matched: number | null;
  loaded: boolean;
  error: string | null;
}

// A list that loads its first page when it mounts and the next one when its end shows in the window (M5-40 plan §9).
// What a page is asked with is in `fetchPage`; a new question mounts the list anew.
function usePages<K>(fetchPage: (next: K | null) => Promise<{ collections: DatasetOption['collection'][]; next: K | null; matched?: number | null }>) {
  const [state, setState] = useState<Pages<K>>({ entries: [], next: null, matched: null, loaded: false, error: null });
  const end = useRef<HTMLLIElement | null>(null);
  const busy = useRef(false);
  const load = async (next: K | null) => {
    if (busy.current) return;
    busy.current = true;
    try {
      const page = await fetchPage(next);
      setState((s) => ({
        entries: [...(next !== null ? s.entries : []), ...datasetsFrom(page.collections)],
        next: page.next,
        matched: next !== null ? s.matched : (page.matched ?? null),
        loaded: true,
        error: null,
      }));
    } catch (e) {
      setState((s) => ({ ...s, loaded: true, error: (e as Error).message }));
    } finally {
      busy.current = false;
    }
  };
  useEffect(() => {
    void load(null);
    // The first page once per mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const watch = (active: boolean) => {
    const target = end.current;
    if (!target || state.next === null || !active || typeof IntersectionObserver === 'undefined') return undefined;
    const observer = new IntersectionObserver((seen) => {
      if (seen.some((e) => e.isIntersecting)) void load(state.next);
    });
    observer.observe(target);
    return () => observer.disconnect();
  };
  return { state, end, watch };
}

// One category within the filters (M5-40 plan §9).
function Group({
  id,
  title,
  filter,
  shownId,
  onShow,
  onLoaded,
}: {
  id: string;
  title: string;
  filter: CatalogueFilter;
  shownId: string | null;
  onShow: (dataset: DatasetOption) => void;
  onLoaded: (id: string, hasEntries: boolean) => void;
}) {
  const [isOpen, setOpen] = useState(true);
  const { state, end, watch } = usePages<string>(async (token) => {
    const page = await fetchCataloguePage(id, token, PAGE, filter).catch((e: Error) => {
      if (token === null) onLoaded(id, true);
      throw e;
    });
    if (token === null) onLoaded(id, page.collections.length > 0);
    return page;
  });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => watch(isOpen), [state.next, isOpen]);

  if (!state.loaded || (state.entries.length === 0 && !state.error)) return null;
  const count = groupCount(state);
  return (
    <section className="catalogue-group" aria-label={title}>
      <button type="button" className="catalogue-group-head" aria-expanded={isOpen} onClick={() => setOpen(!isOpen)}>
        {isOpen ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
        <span className="catalogue-group-name">{title}</span>
        {count !== null && <span className="catalogue-group-count">{count}</span>}
      </button>
      {isOpen && (
        <ul className="catalogue-entries">
          {state.entries.map((d) => (
            <EntryRow key={d.id} dataset={d} shownId={shownId} onShow={onShow} />
          ))}
          {state.error && <li className="hint catalogue-error">Could not load: {state.error}</li>}
          {state.next !== null && <li ref={end} className="catalogue-more" aria-hidden="true" />}
        </ul>
      )}
    </section>
  );
}

// The hits of the search field in rank order, no groups (Otto, 16.11.2026), within the filters; more as the end shows.
function SearchHits({
  text,
  filter,
  category,
  shownId,
  onShow,
}: {
  text: string;
  filter: CatalogueFilter;
  category: string | null;
  shownId: string | null;
  onShow: (dataset: DatasetOption) => void;
}) {
  const { state, end, watch } = usePages<number>((offset) => fetchCatalogueSearch(text, offset ?? 0, filter, category));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => watch(true), [state.next]);
  if (!state.loaded) return null;
  if (state.entries.length === 0 && !state.error) return <p className="hint">No datasets to show</p>;
  return (
    <ul className="catalogue-entries catalogue-hits" aria-label="Search results">
      {state.entries.map((d) => (
        <EntryRow key={d.id} dataset={d} shownId={shownId} onShow={onShow} />
      ))}
      {state.error && <li className="hint catalogue-error">Could not load: {state.error}</li>}
      {state.next !== null && <li ref={end} className="catalogue-more" aria-hidden="true" />}
    </ul>
  );
}

// A field of the pop-up "Filters" with its "×" to empty it (Otto, 16.11.2026); the "×" shows while there is a value.
function Clearable({ value, label, onClear, children }: { value: string; label: string; onClear: () => void; children: ReactNode }) {
  return (
    <div className="catalogue-filter-field">
      {children}
      {value !== '' && (
        <button type="button" className="icon-btn sm quiet clear-btn" aria-label={label} data-tip-level="advanced" data-tip={label} onClick={onClear}>
          <ClearIcon size={14} />
        </button>
      )}
    </div>
  );
}

// The button "Filters" in the head and its pop-up (Otto, 16.11.2026; replaces the row of H1): "Filter by search panel"
// takes AOI and period of the search panel and hides region and from/to; without an AOI there it is locked with the
// reason. The category is always there. A click beside the pop-up closes it, Esc does not (leitfaden §5).
function Filters({ searchPanel, anchor }: { searchPanel: boolean; anchor: RefObject<HTMLDivElement | null> }) {
  const filter = useAppStore((s) => s.catalogueFilter);
  const set = useAppStore((s) => s.setCatalogueFilter);
  const hasAoi = useAppStore((s) => s.aoi !== null);
  const regions = useAppStore((s) => s.catalogueRegions);
  const categories = useAppStore((s) => s.catalogueCategories);
  const loadRegions = useAppStore((s) => s.loadCatalogueRegions);
  const [open, setOpen] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) void loadRegions();
  }, [open, loadRegions]);
  const lock = hasAoi ? null : LOCK_NEEDS_AOI;
  const count = activeFilters(filter, searchPanel);
  return (
    <>
      <button
        ref={button}
        type="button"
        className="btn catalogue-filters-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        data-tip-level="advanced"
        data-tip="Narrow the catalogue by area, region, period and category"
        onClick={() => setOpen((v) => !v)}
      >
        Filters{count > 0 && ` · ${count}`}
      </button>
      <Popover anchorRef={anchor} open={open} onClose={() => setOpen(false)} className="catalogue-filters-popup" role="dialog" ariaLabel="Filters" focusOnOpen form>
        <div className="catalogue-filters">
          <label className={`within-aoi catalogue-search-panel${lock ? ' locked' : ''}`} data-tip={lock ?? undefined}>
            <input
              type="checkbox"
              role="switch"
              checked={searchPanel}
              aria-disabled={lock ? true : undefined}
              onChange={() => {
                if (!lock) set({ bySearchPanel: !filter.bySearchPanel });
              }}
            />
            Filter by search panel
          </label>
          {!searchPanel && (
            <>
              <Clearable value={filter.region} label="Clear region" onClear={() => set({ region: '' })}>
                <select aria-label="Region" className="catalogue-region" value={filter.region} onChange={(e) => set({ region: e.target.value })}>
                  <option value="">All regions</option>
                  {(regions ?? []).map((r) => (
                    <option key={r.code} value={r.code}>
                      {r.level === 'subdivision' ? `   ${r.name}` : r.name}
                    </option>
                  ))}
                </select>
              </Clearable>
              <Clearable value={filter.from} label="Clear from date" onClear={() => set({ from: '' })}>
                <DateField value={filter.from} onChange={(from) => set({ from })} label="From date" bounds={{ min: null, max: filter.to || null }} />
              </Clearable>
              <Clearable value={filter.to} label="Clear to date" onClear={() => set({ to: '' })}>
                <DateField value={filter.to} onChange={(to) => set({ to })} label="To date" bounds={{ min: filter.from || null, max: null }} />
              </Clearable>
            </>
          )}
          <Clearable value={filter.category} label="Clear category" onClear={() => set({ category: '' })}>
            <select aria-label="Category" className="catalogue-category" value={filter.category} onChange={(e) => set({ category: e.target.value })}>
              <option value="">All categories</option>
              {withOther(categories).map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>
          </Clearable>
        </div>
      </Popover>
    </>
  );
}

// The search field of the head (Otto, 16.11.2026): the Collection Search with `q`, waiting a moment after the last key.
function SearchField() {
  const stored = useAppStore((s) => s.catalogueSearch);
  const setStored = useAppStore((s) => s.setCatalogueSearch);
  const [text, setText] = useState(stored);
  useEffect(() => {
    if (text === stored) return undefined;
    const timer = window.setTimeout(() => setStored(text), SEARCH_DELAY);
    return () => window.clearTimeout(timer);
  }, [text, stored, setStored]);
  return (
    <span className="catalogue-search">
      <SearchIcon size={14} />
      <ClearableInput
        value={text}
        onChange={setText}
        onClear={() => setStored('')}
        clearLabel="Clear search"
        placeholder="Search datasets"
        aria-label="Search datasets"
        maxLength={MAX_SEARCH_CHARS}
      />
      <Tip text="Finds datasets by name, keywords and category, in English and German; typing errors are fine. The filters apply." />
    </span>
  );
}

export default function DataCatalogue() {
  const open = useAppStore((s) => s.catalogueOpen);
  const toggleCatalogue = useAppStore((s) => s.toggleCatalogue);
  const dockOpen = useAppStore((s) => s.dock !== null);
  const categories = useAppStore((s) => s.catalogueCategories);
  const fields = useAppStore((s) => s.catalogueFilter);
  const searchText = useAppStore((s) => s.catalogueSearch.trim());
  const aoi = useAppStore((s) => s.aoi);
  const panelFrom = useAppStore((s) => s.dateFrom);
  const panelTo = useAppStore((s) => s.dateTo);
  const [shown, setShown] = useState<DatasetOption | null>(null);
  const [loaded, setLoaded] = useState<Record<string, boolean>>({});
  const tools = useRef<HTMLDivElement>(null);
  if (!open) return null;
  // "Filter by search panel" holds only while the search panel has an AOI; locked, region and from/to apply again.
  const searchPanel = fields.bySearchPanel && aoi !== null;
  const filter: CatalogueFilter = searchPanel
    ? { area: aoi, region: null, from: panelFrom || null, to: panelTo || null }
    : { area: null, region: fields.region || null, from: fields.from || null, to: fields.to || null };
  const groups = withOther(categories).filter((c) => !fields.category || c.id === fields.category);
  // A new filter mounts every list anew: their pages belong to the question they were asked with.
  const filterKey = JSON.stringify([filter, fields.category]);
  const done = groups.every((g) => loaded[`${filterKey}|${g.id}`] !== undefined);
  const none = categories.length > 0 && done && groups.every((g) => !loaded[`${filterKey}|${g.id}`]);
  return (
    <div
      id={CATALOGUE_ID}
      className={`overlay panel catalogue${dockOpen ? ' beside-dock' : ''}${shown ? ' showing-details' : ''}`}
      role="region"
      aria-label="Data catalogue"
    >
      <div className="results-head catalogue-head">
        <h2>Data catalogue</h2>
        {/* The pop-up "Filters" hangs under the whole row, as wide as search field and button together. */}
        <div ref={tools} className="catalogue-tools">
          <SearchField />
          <Filters searchPanel={searchPanel} anchor={tools} />
        </div>
        <CloseButton onClick={toggleCatalogue} />
      </div>
      <div className="catalogue-body">
        <div className="catalogue-list">
          {searchText !== '' ? (
            <SearchHits
              key={`${searchText}|${filterKey}`}
              text={searchText}
              filter={filter}
              category={fields.category || null}
              shownId={shown?.id ?? null}
              onShow={setShown}
            />
          ) : (
            <>
              {categories.length === 0 && <p className="hint">Could not load the categories</p>}
              {none && <p className="hint">No datasets to show</p>}
              {categories.length > 0 &&
                groups.map((group) => (
                  <Group
                    key={`${filterKey}|${group.id}`}
                    id={group.id}
                    title={group.title}
                    filter={filter}
                    shownId={shown?.id ?? null}
                    onShow={setShown}
                    onLoaded={(id, hasEntries) => setLoaded((l) => ({ ...l, [`${filterKey}|${id}`]: hasEntries }))}
                  />
                ))}
            </>
          )}
        </div>
        {shown ? (
          <Details dataset={shown} onBack={() => setShown(null)} />
        ) : (
          <p className="hint catalogue-empty">Choose a dataset to see its details</p>
        )}
      </div>
    </div>
  );
}
