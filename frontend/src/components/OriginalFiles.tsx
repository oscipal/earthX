import { useState } from 'react';

import type { DatasetOption } from '../datasets';
import {
  canExportLicense,
  linkListText,
  noProcessingLicence,
  type DownloadPass,
  type OriginalFileLink,
} from '../download';
import MosaicJobs, { type Started } from './MosaicJobs';

// The original files of a selection (M3-17, Zusatz 1a): the links, unless a
// pass holds two or more scenes — only then there is something to merge, and the
// dialog asks first how they are loaded: each scene as the file the source holds
// ("Each scene separately": the links, nothing passes through the platform), or
// merged per pass as a job on the platform. No choice is preselected (K12).
// Scenes that are all alone in their pass (Otto, 15.10.2026) show the links.

type Mode = 'each' | 'merged';

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

export default function OriginalFiles({ dataset, links, passes }: Props) {
  const [mode, setMode] = useState<Mode | null>(null);
  const [started, setStarted] = useState<Record<number, Started>>({});

  if (links === null) return <p className="hint-text">Loading the original files…</p>;

  const asks = (passes ?? []).some((pass) => pass.items.length > 1);
  const shown = asks ? mode : 'each';
  const mergeAllowed = canExportLicense(dataset?.collection['earthx:license_flags']);
  const noMerge = dataset ? noProcessingLicence(dataset) : 'This dataset’s licence does not permit processing.';

  const byGroup = new Map<string, OriginalFileLink[]>();
  for (const link of links) byGroup.set(link.groupLabel, [...(byGroup.get(link.groupLabel) ?? []), link]);

  return (
    <div className="dialog-originals">
      {asks && shown === null && (
        <div role="group" aria-label="How to load the original files">
          <p>How do you want the original files?</p>
          <button type="button" className="lm-btn" onClick={() => setMode('each')}>
            Each scene separately
          </button>{' '}
          <button
            type="button"
            className="lm-btn"
            disabled={!mergeAllowed}
            title={mergeAllowed ? 'One merged file per pass, made as a job on the platform' : noMerge}
            onClick={() => setMode('merged')}
          >
            Merged per pass (job)
          </button>
          {!mergeAllowed && <p className="hint-text">{noMerge}</p>}
        </div>
      )}
      {asks && shown !== null && (
        <p className="hint-text">
          {shown === 'each' ? 'Each scene separately' : 'Merged per pass (job)'} ·{' '}
          <button type="button" className="link-btn" onClick={() => setMode(null)}>
            Change
          </button>
        </p>
      )}
      {shown === 'each' && (
        <>
          {links.length === 0 && (
            <p className="hint-text">No original file of this selection could be linked directly from the source.</p>
          )}
          {links.length > 0 && (
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
          )}
          {links.length > 1 && dataset && (
            <p>
              <button type="button" className="lm-btn" onClick={() => saveLinkList(dataset.id, links)}>
                Save link list
              </button>{' '}
              <span className="hint-text">A text file with one address per line, for a download manager.</span>
            </p>
          )}
        </>
      )}
      {shown === 'merged' && (
        <MosaicJobs
          dataset={dataset}
          passes={passes ?? []}
          links={links}
          started={started}
          onStarted={(index, run) => setStarted((s) => ({ ...s, [index]: run }))}
        />
      )}
    </div>
  );
}
