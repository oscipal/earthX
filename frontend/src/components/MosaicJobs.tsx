import { useEffect, useState } from 'react';

import type { DatasetOption } from '../datasets';
import { defaultRenderOf } from '../datasets';
import { attributionText, canExportLicense, type DownloadPass } from '../download';
import { chooseDtype } from '../processingDefaults';
import { bandSources, buildMosaicOrder } from '../processingOrder';
import { useProcessingStore } from '../processingStore';
import { JobRow } from './JobList';

// "Merge scenes of this pass (job)" in the download dialog's list of original
// files (M4-12b): one job per pass of two or more scenes, the whole scenes and
// no AOI, merged into one COG on the platform. The status is the row of the
// processing panel (M4-13b), not a poll of its own; the job also stays in the
// panel's list ("Jobs") when the dialog is closed.

type Started = { state: 'starting' } | { state: 'placed'; jobID: string } | { state: 'refused'; message: string };

export default function MosaicJobs({ dataset, passes }: { dataset: DatasetOption | undefined; passes: DownloadPass[] }) {
  const datasetId = dataset?.id;
  const description = useProcessingStore((s) => (datasetId ? s.descriptions[datasetId] : undefined));
  const ensureDescription = useProcessingStore((s) => s.ensureDescription);
  const placeMosaic = useProcessingStore((s) => s.placeMosaic);
  const jobs = useProcessingStore((s) => s.jobs);
  const [started, setStarted] = useState<Record<number, Started>>({});

  const mosaics = passes.map((pass, index) => ({ pass, index })).filter(({ pass }) => pass.items.length > 1);
  useEffect(() => {
    if (datasetId && mosaics.length > 0) ensureDescription(datasetId);
  }, [datasetId, mosaics.length, ensureDescription]);

  const flags = dataset?.collection['earthx:license_flags'];
  const asset = dataset?.viewable ? defaultRenderOf(dataset.collection)?.assets[0] : undefined;
  if (!dataset || !asset || mosaics.length === 0) return null;

  const allowed = canExportLicense(flags);
  const info = description?.state === 'ready' ? description.info : null;
  // A mosaic is derived data: the text for modified data, as for a crop.
  const attribution = allowed ? attributionText(flags, new Date().getFullYear()) : null;

  const start = async (index: number, pass: DownloadPass) => {
    if (!info) return;
    const bands = bandSources(pass.items[0], dataset.collection['earthx:format'] ?? null, null).filter(
      (source) => source.asset === asset,
    );
    const dtype = chooseDtype({ steps: [], bands, allowed: info.dtypes }).value;
    setStarted((s) => ({ ...s, [index]: { state: 'starting' } }));
    const answer = await placeMosaic(
      buildMosaicOrder({ datasetId: dataset.id, itemIds: pass.items.map((i) => i.id), assets: [asset], dtype }),
    );
    setStarted((s) => ({
      ...s,
      [index]: 'jobID' in answer ? { state: 'placed', jobID: answer.jobID } : { state: 'refused', message: answer.message },
    }));
  };

  const why = !allowed
    ? `${dataset.title}’s licence does not permit processing.`
    : description?.state === 'error'
      ? 'The platform could not be asked what a job takes.'
      : !info
        ? 'Loading what a job takes…'
        : null;

  return (
    <section className="dialog-mosaics" aria-label="Mosaic jobs">
      <h3>Merged mosaic of a pass</h3>
      <p className="hint-text">
        A job on the platform merges the whole scenes of one pass into one COG. Scenes in another UTM zone are resampled
        (nearest neighbour) to the zone most scenes lie in.
      </p>
      {attribution && <p className="dialog-attribution">{attribution}</p>}
      {why && <p className="hint-text">{why}</p>}
      <ul>
        {mosaics.map(({ pass, index }) => {
          const run = started[index];
          const job = run?.state === 'placed' ? jobs.find((j) => j.jobID === run.jobID) : undefined;
          return (
            <li key={index}>
              <span className="dialog-original-group">
                {pass.label} · {pass.items.length} scenes
              </span>{' '}
              <button
                type="button"
                className="lm-btn"
                disabled={!allowed || !info || run?.state === 'starting' || !!job}
                title={why ?? 'Merge the scenes of this pass into one file, as a job'}
                onClick={() => void start(index, pass)}
              >
                {run?.state === 'starting' ? 'Starting…' : 'Merge scenes of this pass (job)'}
              </button>
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
