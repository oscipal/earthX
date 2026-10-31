import { useEffect, useMemo, useRef, useState } from 'react';

import type { DatasetOption } from '../datasets';
import {
  acquisitionYears,
  canExportLicense,
  linkListText,
  noProcessingLicence,
  type DownloadPass,
  type OriginalFileLink,
} from '../download';
import { linksOf, scenesOf, type OriginalScene, type Way } from '../originals';
import { browserDeps } from '../originalsClient';
import { runOriginals, type SceneState } from '../originalsRun';
import { formatBytes } from '../processingOrder';
import MosaicJobs, { type Started } from './MosaicJobs';

// The original files of a selection (NM4-33, plan section 6.14): one click starts the download of every scene, one
// after the other, as one ZIP per scene built in the browser from the files of the source (no byte passes through
// the platform), or, where the browser or the source does not allow that, as single files. The rows tell how far each
// scene is. Where a pass holds two or more scenes there is also "Merged per pass (job)", which makes one merged file
// per pass on the platform (M4-12b, Zusatz 1a) and does not stop the download. Closing the dialog stops the run.

interface Props {
  dataset: DatasetOption | undefined;
  // `null` while the layer's scenes are still being fetched.
  links: OriginalFileLink[] | null;
  passes: DownloadPass[] | null;
}

function saveLinkList(datasetId: string, links: readonly OriginalFileLink[]): void {
  const url = URL.createObjectURL(new Blob([linkListText(links)], { type: 'text/plain' }));
  const a = document.createElement('a');
  a.href = url;
  a.download = `${datasetId}-original-links.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

const WAY_NOTES: Record<Exclude<Way, 'zip'>, { text: string; why: string }> = {
  files: {
    text: 'The files come one by one.',
    why: 'This browser cannot build a ZIP here, so every file is saved under the name of its scene.',
  },
  navigate: {
    text: 'Your browser downloads each file.',
    why: 'The source does not let this page read its files, so your browser downloads each one itself, under the name the source gives it.',
  },
};

function rowText(state: SceneState): string {
  switch (state.status) {
    case 'waiting':
      return 'Waiting';
    case 'running':
      return state.total ? `Loading ${Math.min(100, Math.floor((state.loaded / state.total) * 100))} %` : 'Loading…';
    case 'done':
      return 'Done';
    case 'started':
      return 'Started in your browser';
    case 'failed':
      return `Failed: ${state.reason}`;
    case 'cancelled':
      return 'Cancelled';
  }
}

const isOpen = (state: SceneState) => state.status === 'waiting' || state.status === 'running';
const isRetryable = (state: SceneState) => state.status === 'failed' || state.status === 'cancelled';

function SceneRows({ dataset, scenes }: { dataset: DatasetOption; scenes: OriginalScene[] }) {
  const collection = dataset.collection;
  const [states, setStates] = useState<SceneState[]>(() => scenes.map(() => ({ status: 'waiting' })));
  const [way, setWay] = useState<{ way: Way; reason: string | null }>({ way: 'zip', reason: null });
  const [attempt, setAttempt] = useState(0);
  const control = useRef<AbortController | null>(null);
  const latest = useRef(states);
  latest.current = states;
  const retry = useRef<number[] | undefined>(undefined);

  // What a run reads is taken from here when it starts; only another selection or "Retry failed" starts one, never a
  // new object for the same scenes (the dataset list may be loaded again while the dialog is open).
  const input = useRef({ collection, datasetId: dataset.id, scenes, years: acquisitionYears(scenes.map((scene) => scene.item)) });
  input.current = { collection, datasetId: dataset.id, scenes, years: acquisitionYears(scenes.map((scene) => scene.item)) };
  const selection = scenes.map((scene) => scene.item.id).join('\n');

  useEffect(() => {
    const { collection, datasetId, scenes, years } = input.current;
    if (scenes.length === 0) return;
    let current = true;
    const abort = new AbortController();
    control.current = abort;
    const only = retry.current;
    retry.current = undefined;
    const { deps, dispose } = browserDeps();
    runOriginals({
      collection,
      datasetId,
      scenes,
      only,
      years,
      deps,
      signal: abort.signal,
      onScene: (index, state) => {
        if (current) setStates((all) => all.map((was, i) => (i === index ? state : was)));
      },
      onWay: (next, reason) => {
        if (current) setWay({ way: next, reason });
      },
    }).catch(() => {
      // Whatever the run could not foresee: the rows do not stay on "Waiting".
      if (current) setStates((all) => all.map((was) => (isOpen(was) ? { status: 'failed', reason: 'The download failed.' } : was)));
    });
    return () => {
      // Closing the dialog, or a run that is being replaced: nothing more is read from the source, and what the page
      // put into itself for the downloads goes.
      current = false;
      abort.abort();
      dispose();
    };
  }, [selection, attempt]);

  const running = states.some(isOpen);
  const failed = states.some(isRetryable);
  const note = way.way === 'zip' ? null : WAY_NOTES[way.way];

  return (
    <>
      <ul className="dialog-original-rows">
        {scenes.map((scene, index) => {
          const state = states[index] ?? { status: 'waiting' };
          return (
            <li key={scene.item.id} className={`dialog-original-row ${state.status}`}>
              <span className="dialog-original-name" title={scene.groupLabel}>
                {way.way === 'zip' ? scene.zipName : scene.item.id}
              </span>
              <span className="dialog-original-state">{rowText(state)}</span>
              {state.status === 'running' && state.total ? (
                <progress max={state.total} value={state.loaded} aria-label={`Progress of ${scene.item.id}`} />
              ) : null}
            </li>
          );
        })}
      </ul>
      {note && (
        <p className="hint-text" title={way.reason ? `${note.why} ${way.reason}` : note.why}>
          {note.text}
        </p>
      )}
      <p className="dialog-original-buttons">
        {running && (
          <button
            type="button"
            className="lm-btn"
            title="Stop the download. Files already saved stay."
            onClick={() => control.current?.abort()}
          >
            Cancel
          </button>
        )}
        {!running && failed && (
          <button
            type="button"
            className="lm-btn"
            title="Load the scenes that did not finish again, each from the start."
            onClick={() => {
              retry.current = latest.current.flatMap((state, index) => (isRetryable(state) ? [index] : []));
              setAttempt((n) => n + 1);
            }}
          >
            Retry failed
          </button>
        )}
      </p>
    </>
  );
}

export default function OriginalFiles({ dataset, links, passes }: Props) {
  const [merged, setMerged] = useState(false);
  const [started, setStarted] = useState<Record<number, Started>>({});
  const scenes = useMemo(
    () => (dataset && passes ? scenesOf(dataset.collection, passes) : []),
    [dataset, passes],
  );

  if (links === null) return <p className="hint-text">Loading the original files…</p>;
  if (!dataset || scenes.every((scene) => scene.entries.length === 0)) {
    return <p className="hint-text">No original file of this selection could be linked directly from the source.</p>;
  }

  const asks = (passes ?? []).some((pass) => pass.items.length > 1);
  const mergeAllowed = canExportLicense(dataset.collection['earthx:license_flags']);
  const noMerge = noProcessingLicence(dataset);
  const all = linksOf(scenes);
  const byGroup = new Map<string, OriginalFileLink[]>();
  for (const link of all) byGroup.set(link.groupLabel, [...(byGroup.get(link.groupLabel) ?? []), link]);
  const bytes = scenes.flatMap((scene) => scene.entries).reduce((sum, entry) => sum + (entry.size ?? 0), 0);

  return (
    <div className="dialog-originals">
      <p className="hint-text">
        {scenes.length} scene{scenes.length === 1 ? '' : 's'}
        {bytes > 0 ? ` · ${formatBytes(bytes)}` : ''}
      </p>
      <SceneRows dataset={dataset} scenes={scenes} />
      <p className="dialog-original-buttons">
        {asks && (
          <button
            type="button"
            className="lm-btn"
            disabled={!mergeAllowed}
            aria-pressed={merged}
            title={mergeAllowed ? 'One merged file per pass, made as a job on the platform' : noMerge}
            onClick={() => setMerged((on) => !on)}
          >
            Merged per pass (job)
          </button>
        )}
        {all.length > 1 && (
          <button
            type="button"
            className="lm-btn"
            title="A text file with one address per line, for a download manager."
            onClick={() => saveLinkList(dataset.id, all)}
          >
            Save link list
          </button>
        )}
      </p>
      {merged && (
        <MosaicJobs
          dataset={dataset}
          passes={passes ?? []}
          links={links}
          started={started}
          onStarted={(index, run) => setStarted((s) => ({ ...s, [index]: run }))}
        />
      )}
      <details>
        <summary>Links to the files</summary>
        <ul className="dialog-original-links">
          {[...byGroup.entries()].map(([groupLabel, groupLinks]) => (
            <li key={groupLabel}>
              <span className="dialog-original-group">{groupLabel}</span>
              <ul>
                {groupLinks.map((link) => (
                  <li key={`${link.itemId}:${link.asset}`}>
                    <a href={link.href} download rel="noopener noreferrer" target="_blank">
                      {link.itemId} · {link.asset}
                    </a>
                  </li>
                ))}
              </ul>
            </li>
          ))}
        </ul>
      </details>
    </div>
  );
}
