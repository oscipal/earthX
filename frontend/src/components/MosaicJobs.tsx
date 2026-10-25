import { useEffect } from 'react';

import type { DatasetOption } from '../datasets';
import { defaultRenderOf } from '../datasets';
import {
  acquisitionYears,
  attributionText,
  canExportLicense,
  MAX_JOB_SCENES,
  noProcessingLicence,
  type DownloadPass,
  type OriginalFileLink,
} from '../download';
import { chooseDtype } from '../processingDefaults';
import { bandSources, buildMosaicOrder } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { JobRow } from './JobList';

// "Merged per pass (job)" in the download dialog's choice for original files
// (M4-12b, Zusatz 1a): one job per pass of two or more scenes, the whole scenes
// and no AOI, merged into one COG on the platform. A pass of one scene is its
// own original file: the row links to it instead of a job (K11). The status is
// the row of the processing panel (M4-13b), not a poll of its own; the job also
// stays in the panel's list ("Jobs") when the dialog is closed.

export type Started = { state: 'starting' } | { state: 'placed'; jobID: string } | { state: 'refused'; message: string };

export const TOO_MANY_SCENES = `A job takes at most ${MAX_JOB_SCENES} scenes; select fewer scenes of this pass.`;

interface Props {
  dataset: DatasetOption | undefined;
  passes: DownloadPass[];
  // The links to the single files, for a pass of one scene.
  links: readonly OriginalFileLink[];
  // Kept by the caller, so that a job started stays in sight after going back to the choice.
  started: Record<number, Started>;
  onStarted: (index: number, started: Started) => void;
}

export default function MosaicJobs({ dataset, passes, links, started, onStarted }: Props) {
  const datasetId = dataset?.id;
  const description = useProcessingStore((s) => (datasetId ? s.descriptions[datasetId] : undefined));
  const ensureDescription = useProcessingStore((s) => s.ensureDescription);
  const placeOrder = useProcessingStore((s) => s.placeOrder);
  const jobs = useProcessingStore((s) => s.jobs);

  const hasJobs = passes.some((pass) => pass.items.length > 1);
  useEffect(() => {
    if (datasetId && hasJobs) ensureDescription(datasetId);
  }, [datasetId, hasJobs, ensureDescription]);

  const flags = dataset?.collection['earthx:license_flags'];
  const asset = dataset?.viewable ? defaultRenderOf(dataset.collection)?.assets[0] : undefined;
  if (!dataset || !asset) return null;

  const allowed = canExportLicense(flags);
  const info = description?.state === 'ready' ? description.info : null;
  // A mosaic is derived data: the text for modified data, as for a crop.
  const attribution = allowed && hasJobs ? attributionText(flags, acquisitionYears(passes.flatMap((pass) => pass.items))) : null;

  const why = !allowed
    ? noProcessingLicence(dataset)
    : description?.state === 'error'
      ? 'The platform could not be asked what a job takes.'
      : !info
        ? 'Loading what a job takes…'
        : null;

  const start = async (index: number, pass: DownloadPass) => {
    if (!info || why || pass.items.length > MAX_JOB_SCENES || started[index]?.state === 'starting') return;
    const bands = bandSources(pass.items[0], dataset.collection['earthx:format'] ?? null, null).filter(
      (source) => source.asset === asset,
    );
    const dtype = chooseDtype({ steps: [], bands, allowed: info.dtypes }).value;
    onStarted(index, { state: 'starting' });
    const answer = await placeOrder(
      buildMosaicOrder({ datasetId: dataset.id, itemIds: pass.items.map((i) => i.id), assets: [asset], dtype }),
    );
    onStarted(
      index,
      'jobID' in answer ? { state: 'placed', jobID: answer.jobID } : { state: 'refused', message: answer.message },
    );
  };

  return (
    <section className="dialog-mosaics" aria-label="Mosaic jobs">
      {hasJobs && (
        <p className="hint-text">
          A job on the platform merges the whole scenes of one pass into one COG. Scenes in another UTM zone are
          resampled (nearest neighbour) to the zone most scenes lie in.
        </p>
      )}
      {attribution && <p className="dialog-attribution">{attribution}</p>}
      {hasJobs && why && <p className="hint-text">{why}</p>}
      <ul>
        {passes.map((pass, index) => {
          const run = started[index];
          const job = run?.state === 'placed' ? jobs.find((j) => j.jobID === run.jobID) : undefined;
          const count = `${pass.items.length} scene${pass.items.length === 1 ? '' : 's'}`;
          if (pass.items.length < 2) {
            const own = links.filter((link) => pass.items.some((item) => item.id === link.itemId));
            return (
              <li key={index}>
                <span className="dialog-original-group">
                  {pass.label} · {count}
                </span>{' '}
                {own.length === 0 ? (
                  <span className="hint-text">No direct link to this scene’s file.</span>
                ) : (
                  own.map((link) => (
                    <a
                      key={`${link.itemId}:${link.asset}`}
                      href={link.href}
                      download
                      rel="noopener noreferrer"
                      target="_blank"
                    >
                      {link.itemId} · {link.asset}
                    </a>
                  ))
                )}
              </li>
            );
          }
          const tooMany = pass.items.length > MAX_JOB_SCENES;
          const blocked = tooMany ? TOO_MANY_SCENES : why;
          return (
            <li key={index}>
              <span className="dialog-original-group">
                {pass.label} · {count}
              </span>{' '}
              <button
                type="button"
                className="lm-btn"
                disabled={!!blocked || run?.state === 'starting' || !!job}
                title={blocked ?? 'Merge the scenes of this pass into one file, as a job'}
                onClick={() => void start(index, pass)}
              >
                {run?.state === 'starting' ? 'Starting…' : 'Start job'}
              </button>
              {tooMany && <p className="hint-text">{TOO_MANY_SCENES}</p>}
              {run?.state === 'refused' && (
                <p className="hint-text error" role="alert">
                  {run.message}
                </p>
              )}
              {job && (
                <ul className="pp-jobs">
                  <JobRow job={job} />
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
