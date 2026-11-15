// The Data catalogue (UI-05 §4, Otto 06.11.2026): a window over the map, opened and closed with its symbol in the rail
// and closed with the red x as well; Esc and a click beside it close nothing (leitfaden §5). The list at the left holds
// the entries of each category, full and listed ones together (M5-40), with "Add" or "Remove" for "Search and area" or
// the link "Source"; each group loads its entries a page at a time, the next one when the end of the group shows in the
// window. The details of the chosen entry stand at the right, and below 900 px on a stage of their own with "Back". The
// head is its own area: the search of `adr/0026` comes in as a second row later (F6).

import { useEffect, useRef, useState } from 'react';

import { fetchCataloguePage, type CatalogueFilter } from '../api';
import { LOCK_NEEDS_AOI } from '../aoiFilter';
import {
  accountOf,
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
import CloseButton from './CloseButton';
import { DateField } from './ControlPanel';
import { ArrowLeftIcon, ChevronDownIcon, ChevronRightIcon, PlusIcon, TrashIcon } from './icons';
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
            <dd>
              <Links values={row.values} />
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}

// Entries per page of a group.
const PAGE = 50;
interface GroupState {
  entries: DatasetOption[];
  next: string | null;
  matched: number | null;
  loaded: boolean;
  error: string | null;
}

const EMPTY: GroupState = { entries: [], next: null, matched: null, loaded: false, error: null };

// One category within the filters: its first page when it mounts, the next one when the end of the list shows (M5-40
// plan §9). A new filter mounts it anew.
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
  const [state, setState] = useState<GroupState>(EMPTY);
  const [isOpen, setOpen] = useState(true);
  const end = useRef<HTMLLIElement | null>(null);
  const busy = useRef(false);

  const load = async (token: string | null) => {
    if (busy.current) return;
    busy.current = true;
    try {
      const page = await fetchCataloguePage(id, token, PAGE, filter);
      setState((s) => ({
        entries: [...(token ? s.entries : []), ...datasetsFrom(page.collections)],
        next: page.next,
        matched: token ? s.matched : page.matched,
        loaded: true,
        error: null,
      }));
      if (!token) onLoaded(id, page.collections.length > 0);
    } catch (e) {
      setState((s) => ({ ...s, loaded: true, error: (e as Error).message }));
      if (!token) onLoaded(id, true);
    } finally {
      busy.current = false;
    }
  };

  useEffect(() => {
    void load(null);
    // The first page once per mount; a new filter mounts the group anew.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const target = end.current;
    if (!target || !state.next || !isOpen || typeof IntersectionObserver === 'undefined') return;
    const observer = new IntersectionObserver((seen) => {
      if (seen.some((e) => e.isIntersecting)) void load(state.next);
    });
    observer.observe(target);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state.next, isOpen]);

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
            <li key={d.id} className="catalogue-entry" aria-current={d.id === shownId || undefined}>
              <button type="button" className="catalogue-entry-name" onClick={() => onShow(d)}>
                <span className="catalogue-entry-title">{d.title}</span>
                <Marks dataset={d} />
              </button>
              <RowAction dataset={d} />
            </li>
          ))}
          {state.error && <li className="hint catalogue-error">Could not load: {state.error}</li>}
          {state.next && <li ref={end} className="catalogue-more" aria-hidden="true" />}
        </ul>
      )}
    </section>
  );
}

// The second row of the head (M5-40 H1): "Only datasets in AOI" (H2, off until switched on, adr/0026 F6), the region,
// the period and the category. Kept for the session in the store; they act on every group.
function Filters() {
  const filter = useAppStore((s) => s.catalogueFilter);
  const set = useAppStore((s) => s.setCatalogueFilter);
  const hasAoi = useAppStore((s) => s.aoi !== null);
  const regions = useAppStore((s) => s.catalogueRegions);
  const categories = useAppStore((s) => s.catalogueCategories);
  const loadRegions = useAppStore((s) => s.loadCatalogueRegions);
  useEffect(() => {
    void loadRegions();
  }, [loadRegions]);
  const aoiLock = hasAoi ? null : LOCK_NEEDS_AOI;
  return (
    <div className="catalogue-filters">
      <label className={`within-aoi catalogue-aoi${aoiLock ? ' locked' : ''}`} data-tip={aoiLock ?? undefined}>
        <input
          type="checkbox"
          role="switch"
          checked={filter.aoiOnly && !aoiLock}
          aria-disabled={aoiLock ? true : undefined}
          onChange={() => {
            if (!aoiLock) set({ aoiOnly: !filter.aoiOnly });
          }}
        />
        Only datasets in AOI
      </label>
      <select aria-label="Region" className="catalogue-region" value={filter.region} onChange={(e) => set({ region: e.target.value })}>
        <option value="">All regions</option>
        {(regions ?? []).map((r) => (
          <option key={r.code} value={r.code}>
            {r.level === 'subdivision' ? `\u00a0\u00a0\u00a0${r.name}` : r.name}
          </option>
        ))}
      </select>
      <div className="date-row catalogue-dates">
        <DateField value={filter.from} onChange={(from) => set({ from })} label="From date" bounds={{ min: null, max: filter.to || null }} />
        <span>→</span>
        <DateField value={filter.to} onChange={(to) => set({ to })} label="To date" bounds={{ min: filter.from || null, max: null }} />
      </div>
      <select aria-label="Category" className="catalogue-category" value={filter.category} onChange={(e) => set({ category: e.target.value })}>
        <option value="">All categories</option>
        {withOther(categories).map((c) => (
          <option key={c.id} value={c.id}>
            {c.title}
          </option>
        ))}
      </select>
    </div>
  );
}

export default function DataCatalogue() {
  const open = useAppStore((s) => s.catalogueOpen);
  const toggleCatalogue = useAppStore((s) => s.toggleCatalogue);
  const dockOpen = useAppStore((s) => s.dock !== null);
  const categories = useAppStore((s) => s.catalogueCategories);
  const fields = useAppStore((s) => s.catalogueFilter);
  const aoi = useAppStore((s) => s.aoi);
  const [shown, setShown] = useState<DatasetOption | null>(null);
  const [loaded, setLoaded] = useState<Record<string, boolean>>({});
  if (!open) return null;
  const filter: CatalogueFilter = {
    area: fields.aoiOnly && aoi ? aoi : null,
    region: fields.region || null,
    from: fields.from || null,
    to: fields.to || null,
  };
  const groups = withOther(categories).filter((c) => !fields.category || c.id === fields.category);
  // A new filter mounts every group anew: their pages belong to the filter they were asked with.
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
        <CloseButton onClick={toggleCatalogue} />
      </div>
      <Filters />
      <div className="catalogue-body">
        <div className="catalogue-list">
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
