// The Data catalogue (UI-05 §4, Otto 06.11.2026): a window over the map, opened and closed with its symbol in the rail
// and closed with the red x as well; Esc and a click beside it close nothing (leitfaden §5). The list at the left holds
// the entries of each category, full and listed ones together (M5-40), with "Add" or "Remove" for "Search and area" or
// the link "Source"; each group loads its entries a page at a time, the next one when the end of the group shows in the
// window. The details of the chosen entry stand at the right, and below 900 px on a stage of their own with "Back". The
// head is its own area: the search of `adr/0026` comes in as a second row later (F6).

import { useEffect, useRef, useState } from 'react';

import { fetchCataloguePage } from '../api';
import {
  accountOf,
  CATALOGUE_GROUPS,
  catalogueRows,
  isListed,
  listedSourceOf,
  notAddableReason,
  prototypeNote,
  sourceRow,
  type LinkText,
} from '../catalogue';
import { datasetsFrom, maturityLabel, type DatasetOption } from '../datasets';
import { CATALOGUE_ID } from '../dock';
import { useAppStore } from '../store';
import Badge from './Badge';
import CloseButton from './CloseButton';
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
  loading: boolean;
  loaded: boolean;
  error: string | null;
}

const EMPTY: GroupState = { entries: [], next: null, matched: null, loading: false, loaded: false, error: null };

// One category: its first page when the window opens, the next one when the end of the list shows (M5-40 plan §9).
function Group({
  id,
  title,
  shownId,
  onShow,
}: {
  id: string;
  title: string;
  shownId: string | null;
  onShow: (dataset: DatasetOption) => void;
}) {
  const [state, setState] = useState<GroupState>(EMPTY);
  const [isOpen, setOpen] = useState(true);
  const end = useRef<HTMLLIElement | null>(null);
  const busy = useRef(false);

  const load = async (token: string | null) => {
    if (busy.current) return;
    busy.current = true;
    setState((s) => ({ ...s, loading: true, error: null }));
    try {
      const page = await fetchCataloguePage(id, token, PAGE);
      setState((s) => ({
        entries: [...(token ? s.entries : []), ...datasetsFrom(page.collections)],
        next: page.next,
        matched: token ? s.matched : page.matched,
        loading: false,
        loaded: true,
        error: null,
      }));
    } catch (e) {
      setState((s) => ({ ...s, loading: false, loaded: true, error: (e as Error).message }));
    } finally {
      busy.current = false;
    }
  };

  useEffect(() => {
    void load(null);
    // The first page once per opening of the window.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

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
  return (
    <section className="catalogue-group" aria-label={title}>
      <button type="button" className="catalogue-group-head" aria-expanded={isOpen} onClick={() => setOpen(!isOpen)}>
        {isOpen ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
        <span className="catalogue-group-name">{title}</span>
        {state.matched !== null && <span className="catalogue-group-count">{state.matched}</span>}
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

export default function DataCatalogue() {
  const open = useAppStore((s) => s.catalogueOpen);
  const toggleCatalogue = useAppStore((s) => s.toggleCatalogue);
  const dockOpen = useAppStore((s) => s.dock !== null);
  const [shown, setShown] = useState<DatasetOption | null>(null);
  if (!open) return null;
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
      <div className="catalogue-body">
        <div className="catalogue-list">
          {CATALOGUE_GROUPS.map((group) => (
            <Group key={group.id} id={group.id} title={group.title} shownId={shown?.id ?? null} onShow={setShown} />
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
