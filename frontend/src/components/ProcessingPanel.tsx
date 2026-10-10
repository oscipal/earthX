// The processing panel (M4-13b): an order for the current selection — one
// scene, the AOI, steps from the operators the dataset allows — reviewed with
// an estimate before it starts as a job; then the jobs of this tab. Built from
// the schema of `/processing/processes/recipe?dataset=…`, nothing per dataset
// here. The map preview of the steps comes with M4-13c.

import { useShallow } from 'zustand/react/shallow';

import { groupIndexOfItem } from '../grouping';
import {
  formatBytes,
  formatDuration,
  formatMegapixels,
  namesInExpression,
  processBlockReason,
  uniqueNames,
} from '../processingOrder';
import { bandMathExpressions, orderView, selectionState, useProcessingStore, type OrderView } from '../processingStore';
import { useAppStore } from '../store';
import JobList from './JobList';
import StepForm from './StepForm';

const SCENE_NOTE = 'The result covers only this scene; several scenes in one job come with a later version.';

function Bands({ view }: { view: OrderView }) {
  const steps = useProcessingStore((s) => s.steps);
  const picked = useProcessingStore((s) => s.picked);
  const togglePick = useProcessingStore((s) => s.togglePick);
  const insertBand = useProcessingStore((s) => s.insertBand);
  const unique = uniqueNames(view.sources);
  const hasBandMath = steps.some((s) => s.op === 'band_math');
  const named = new Set(bandMathExpressions(steps).flatMap((e) => [...namesInExpression(e)]));
  if (!view.item) return null;
  if (view.sources.length === 0) {
    return (
      <section className="pp-section" aria-label="Bands">
        <h3 className="pp-heading">Bands</h3>
        <p className="hint-text">This scene lists no band the panel can offer.</p>
      </section>
    );
  }
  return (
    <section className="pp-section" aria-label="Bands">
      <h3 className="pp-heading">Bands</h3>
      <div className="pp-chips">
        {view.sources.flatMap((source) => {
          const pressed = view.assets.includes(source.asset);
          if (source.names.length === 0) {
            return [
              <button
                key={source.asset}
                type="button"
                className={`pp-chip${pressed ? ' on' : ''}`}
                aria-pressed={pressed}
                title="This asset does not describe its bands: it goes into the order, but offers no name to insert"
                onClick={() => togglePick(source.asset)}
              >
                {source.asset}
              </button>,
            ];
          }
          // With a band-math step a click inserts the name, except on a band
          // picked by hand that no expression names: that click leaves it out.
          const pickedOnly = picked.includes(source.asset) && !source.names.some((n) => named.has(n));
          return source.names.map((name) => {
            const insertable = unique.get(name) === source.asset && !pickedOnly;
            return (
              <button
                key={`${source.asset}/${name}`}
                type="button"
                className={`pp-chip${pressed ? ' on' : ''}`}
                aria-pressed={pressed}
                title={
                  hasBandMath && insertable
                    ? `Insert ${name} into the expression`
                    : `${pressed ? 'Leave out' : 'Use'} ${source.asset}`
                }
                onClick={() => (hasBandMath && insertable ? insertBand(name) : togglePick(source.asset))}
              >
                {insertable ? name : source.asset}
              </button>
            );
          });
        })}
      </div>
      <p className="pp-help">
        {view.assets.length} of at most {view.info?.maxAssets ?? 16} bands in the order
        {hasBandMath ? '; a click inserts the name into the expression.' : '.'}
      </p>
    </section>
  );
}

export default function ProcessingPanel() {
  const open = useProcessingStore((s) => s.open);
  const close = useProcessingStore((s) => s.closeProcessing);
  const app = useAppStore(useShallow(selectionState));
  const p = useProcessingStore();
  if (!open) return null;

  const dataset = app.datasets.find((d) => d.id === app.datasetId);
  // The same rule as the button in the ViewBar: scenes picked by hand.
  const reason = processBlockReason(dataset, app.aoi, app.selectedIds.length);
  const description = app.datasetId ? p.descriptions[app.datasetId] : undefined;
  const view = orderView(app, p);
  const info = view.info;
  const built = view.built;
  const estimate = p.estimate && p.estimate.key === view.key ? p.estimate.doc : null;
  const showErrors = p.reviewAsked;
  const group = view.item ? app.groups[groupIndexOfItem(app.groups, view.item.id)] : undefined;
  // A refusal belongs to the order it refused; a changed draft hides it.
  const refusals = [p.reviewError, p.startError].filter((r) => r !== null && r.key === view.key);
  const refusalAt = (index: number) => refusals.find((r) => r!.step === index)?.message ?? null;
  const orderRefusals = refusals.filter((r) => r!.step === null);

  return (
    <div className="panel processing-panel" role="dialog" aria-label="Processing">
      <div className="vc-head">
        <span className="vc-title">PROCESSING</span>
        <button type="button" className="link-btn" title="Close the panel" onClick={close}>
          ✕
        </button>
      </div>

      {reason ? (
        <p className="hint-text">{reason}</p>
      ) : (
        <>
          <section className="pp-section" aria-label="Selection">
            <p className="pp-summary">
              {[dataset?.title ?? app.datasetId, group?.label, view.item?.id].filter(Boolean).join(' · ')}
            </p>
            {view.candidates.length === 0 && <p className="hint-text error">No selected scene meets the AOI.</p>}
            {view.candidates.length > 1 && (
              <>
                <label className="vc-field pp-field">
                  Scene
                  <select value={view.item?.id ?? ''} onChange={(e) => p.chooseItem(e.target.value)}>
                    <option value="">— choose one scene —</option>
                    {view.candidates.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.id}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="hint-text warn">{SCENE_NOTE}</p>
              </>
            )}
          </section>

          {description?.state === 'loading' && <p className="hint-text">Loading the operators…</p>}
          {description?.state === 'error' && (
            <p className="hint-text error">
              The operators could not be loaded: {description.message}{' '}
              <button type="button" className="link-btn" onClick={() => app.datasetId && p.ensureDescription(app.datasetId)}>
                Retry
              </button>
            </p>
          )}

          {info && (
            <>
              <Bands view={view} />

              <section className="pp-section" aria-label="Steps">
                <h3 className="pp-heading">Steps</h3>
                {p.steps.length > 0 && (
                  <ol className="pp-steps">
                    {p.steps.map((step, index) => {
                      const operator = info.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion);
                      const problem = built?.stepProblems[index];
                      return (
                        <StepForm
                          key={step.key}
                          index={index}
                          count={p.steps.length}
                          stepKey={step.key}
                          operator={operator}
                          values={step.values}
                          errors={problem?.errors ?? {}}
                          unsupported={problem?.unsupported}
                          showErrors={showErrors}
                          refusal={refusalAt(index)}
                          onChange={(name, value) => p.updateStep(step.key, name, value)}
                          onFocus={() => p.setActiveStep(step.key)}
                          onMove={(direction) => p.moveStep(step.key, direction)}
                          onRemove={() => p.removeStep(step.key)}
                        />
                      );
                    })}
                  </ol>
                )}
                <div className="pp-add" role="group" aria-label="Add step">
                  <span className="pp-help">Add step:</span>
                  {info.operators.length === 0 && <span className="hint-text">No operator runs on this dataset.</span>}
                  {info.operators.map((operator) => {
                    const full = p.steps.length >= info.maxSteps;
                    const why = !operator.form.supported
                      ? operator.form.reason
                      : full
                        ? `At most ${info.maxSteps} steps`
                        : (operator.description ?? operator.title);
                    return (
                      <button
                        key={`${operator.op}/${operator.opVersion}`}
                        type="button"
                        className="ghost-btn pp-add-btn"
                        disabled={!operator.form.supported || full}
                        title={why}
                        onClick={() => p.addStep(operator.op, operator.opVersion)}
                      >
                        ＋ {operator.title}
                      </button>
                    );
                  })}
                </div>
                {info.operators.map((o) =>
                  o.form.supported ? null : (
                    <p key={`${o.op}/${o.opVersion}`} className="hint-text">
                      {o.title}: {o.form.reason}
                    </p>
                  ),
                )}
              </section>

              <section className="pp-section" aria-label="Output">
                <h3 className="pp-heading">Output</h3>
                <label className="vc-field pp-field">
                  Data type
                  <select value={view.dtype} onChange={(e) => p.setDtype(e.target.value)}>
                    <option value="">— choose —</option>
                    {info.dtypes.map((dtype) => (
                      <option key={dtype} value={dtype}>
                        {dtype}
                      </option>
                    ))}
                  </select>
                </label>
              </section>

              <section className="pp-section" aria-label="Review">
                {showErrors && built && built.problems.length > 0 && (
                  <p className="hint-text error">{built.problems.join(' ')}</p>
                )}
                <div className="vc-actions">
                  <button
                    type="button"
                    className="ghost-btn"
                    disabled={p.reviewing}
                    title="Ask the server what this job is expected to cost"
                    onClick={() => void p.reviewOrder()}
                  >
                    {p.reviewing ? 'Reviewing…' : 'Review'}
                  </button>
                  <button
                    type="button"
                    className="primary-btn"
                    disabled={!estimate || p.starting}
                    title={estimate ? 'Start this order as a job' : 'Review the order first'}
                    onClick={() => void p.startJob()}
                  >
                    {p.starting ? 'Starting…' : 'Start job'}
                  </button>
                </div>
                {estimate && (
                  <div className="pp-estimate" aria-label="Estimate">
                    <p>
                      about {formatMegapixels(estimate.estimate.outputPixels)}, {formatBytes(estimate.estimate.size)},{' '}
                      {formatDuration(estimate.estimate.duration)}, {estimate.estimate.units.toFixed(1)} units
                    </p>
                    {estimate.skippedItems.length > 0 && (
                      <p className="hint-text warn">Left out (the AOI misses them): {estimate.skippedItems.join(', ')}</p>
                    )}
                    <p className="pp-help">An estimate, not a promise.</p>
                  </div>
                )}
                {orderRefusals.map((refusal, index) => (
                  <p key={index} className="hint-text error" role="alert">
                    {refusal!.message}
                  </p>
                ))}
              </section>
            </>
          )}
        </>
      )}

      <JobList />
    </div>
  );
}
