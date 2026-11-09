// The Data catalogue (UI-05 §4, Otto 06.11.2026): a window over the map, opened and closed with its symbol in the rail
// and closed with the red x as well; Esc and a click beside it close nothing (leitfaden §5). The list at the left holds
// every dataset in its group, with "Add" or "Remove" for "Search and area"; the details of the chosen one stand at the
// right, and below 900 px on a stage of their own with "Back". The head is its own area: the search of `adr/0026` comes
// in as a second row later (F6).

import { useState } from 'react';

import {
  accountOf,
  catalogueGroups,
  catalogueRows,
  notAddableReason,
  prototypeNote,
  sourceRow,
  type LinkText,
} from '../catalogue';
import { maturityLabel, type DatasetOption } from '../datasets';
import { CATALOGUE_ID } from '../dock';
import { useAppStore } from '../store';
import Badge from './Badge';
import CloseButton from './CloseButton';
import { ArrowLeftIcon, ChevronDownIcon, ChevronRightIcon, PlusIcon, TrashIcon } from './icons';
import NoticeBadges from './NoticeBadges';
import Tip from './Tip';

function Marks({ dataset }: { dataset: DatasetOption }) {
  const maturity = maturityLabel(dataset.collection);
  return (
    <>
      {prototypeNote(dataset.collection) && <Badge>Prototype</Badge>}
      {accountOf(dataset.collection) && <Badge>Account</Badge>}
      {maturity && <Badge>{maturity}</Badge>}
      <NoticeBadges collection={dataset.collection} />
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

export default function DataCatalogue() {
  const open = useAppStore((s) => s.catalogueOpen);
  const toggleCatalogue = useAppStore((s) => s.toggleCatalogue);
  const datasets = useAppStore((s) => s.datasets);
  const dockOpen = useAppStore((s) => s.dock !== null);
  const [shownId, setShownId] = useState<string | null>(null);
  const [folded, setFolded] = useState<string[]>([]);
  if (!open) return null;
  const shown = datasets.find((d) => d.id === shownId) ?? null;
  const groups = catalogueGroups(datasets);
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
          {groups.length === 0 && <p className="hint">No datasets to show</p>}
          {groups.map((group) => {
            const isOpen = !folded.includes(group.id);
            return (
              <section key={group.id} className="catalogue-group" aria-label={group.title}>
                <button
                  type="button"
                  className="catalogue-group-head"
                  aria-expanded={isOpen}
                  onClick={() => setFolded(isOpen ? [...folded, group.id] : folded.filter((id) => id !== group.id))}
                >
                  {isOpen ? <ChevronDownIcon size={14} /> : <ChevronRightIcon size={14} />}
                  <span className="catalogue-group-name">{group.title}</span>
                  <span className="catalogue-group-count">{group.datasets.length}</span>
                </button>
                {isOpen && (
                  <ul className="catalogue-entries">
                    {group.datasets.map((d) => (
                      <li key={d.id} className="catalogue-entry" aria-current={d.id === shownId || undefined}>
                        <button type="button" className="catalogue-entry-name" onClick={() => setShownId(d.id)}>
                          <span className="catalogue-entry-title">{d.title}</span>
                          <Marks dataset={d} />
                        </button>
                        <RowAction dataset={d} />
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            );
          })}
        </div>
        {shown ? (
          <Details dataset={shown} onBack={() => setShownId(null)} />
        ) : (
          <p className="hint catalogue-empty">Choose a dataset to see its details</p>
        )}
      </div>
    </div>
  );
}
