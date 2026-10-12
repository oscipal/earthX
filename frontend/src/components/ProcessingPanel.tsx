// The processing panel (M4-13b): an order for the current selection — one
// scene, the AOI, steps from the operators the dataset allows — reviewed with
// an estimate before it starts as a job; then the jobs of this tab. Built from
// the schema of `/processing/processes/recipe?dataset=…`, nothing per dataset
// here. The map preview of the steps comes with M4-13c.

import { useLayoutEffect, useRef } from 'react';
import { useShallow } from 'zustand/react/shallow';

import { groupIndexOfItem } from '../grouping';
import { AFTER_BAND_MATH } from '../processingDefaults';
import {
  formatBytes,
  formatDuration,
  formatMegapixels,
  insertName,
  namesInExpression,
  processBlockReason,
  uniqueNames,
  type BandSource,
} from '../processingOrder';
import { bandMathExpressions, orderView, selectionState, useProcessingStore, type OrderView } from '../processingStore';
import { useAppStore } from '../store';
import JobList from './JobList';
import StepForm from './StepForm';

const SCENE_NOTE = 'The result covers only this scene; several scenes in one job come with a later version.';

// The expression field that has the cursor, if one has: only into that field a
// band chip inserts its name (Otto, 12.10.2026).
function focusedExpression(): HTMLInputElement | null {
  const active = document.activeElement;
  return active instanceof HTMLInputElement && active.dataset.bandTarget !== undefined ? active : null;
}

function Bands({ view }: { view: OrderView }) {
  const steps = useProcessingStore((s) => s.steps);
  const picked = useProcessingStore((s) => s.picked);
  const togglePick = useProcessingStore((s) => s.togglePick);
  const updateStep = useProcessingStore((s) => s.updateStep);
  // Where the cursor goes once the expression has its new text: a controlled
  // field moves it to the end when its value changes, so it is set after the commit.
  const caret = useRef<{ field: HTMLInputElement; at: number } | null>(null);
  useLayoutEffect(() => {
    const pending = caret.current;
    caret.current = null;
    if (pending?.field.isConnected) pending.field.setSelectionRange(pending.at, pending.at);
  });
  const unique = uniqueNames(view.sources);
  const hasBandMath = steps.some((s) => s.op === 'band_math');
  const named = new Set(bandMathExpressions(steps).flatMap((e) => [...namesInExpression(e)]));
  if (!view.item) return null;
  if (view.sources.length === 0) {
    return (
      <section className="pp-section" aria-label="Bands">
        <h3 className="pp-heading">Bands</h3>
        <p className="hint-text">This dataset does not list band names yet.</p>
      </section>
    );
  }

  // A click with the cursor in an expression inserts the name there; any other
  // click adds the band to the order or leaves it out and changes no expression.
  const click = (source: BandSource, name: string | null) => {
    const field = name !== null && unique.get(name) === source.asset ? focusedExpression() : null;
    if (field && name !== null) {
      const start = field.selectionStart ?? field.value.length;
      const inserted = insertName(field.value, start, field.selectionEnd ?? start, name);
      caret.current = { field, at: inserted.caret };
      updateStep(Number(field.dataset.bandTarget), 'expression', inserted.text);
      return;
    }
    const byExpression = source.names.some((n) => named.has(n)) && !picked.includes(source.asset);
    if (!byExpression) togglePick(source.asset);
  };

  const chip = (source: BandSource, name: string | null) => {
    const pressed = view.assets.includes(source.asset);
    const byExpression = pressed && !picked.includes(source.asset);
    const label = name !== null && unique.get(name) === source.asset ? name : source.asset;
    return (
      <button
        key={`${source.asset}/${name ?? ''}`}
        type="button"
        className={`pp-chip${pressed ? ' on' : ''}`}
        aria-pressed={pressed}
        title={
          byExpression
            ? `${source.asset} is named in an expression: take the name out there to leave it out`
            : name === null
              ? `${pressed ? 'Leave out' : 'Add'} ${source.asset} (it describes no band names to insert)`
              : `${pressed ? 'Leave out' : 'Add'} ${source.asset}`
        }
        // Keep the cursor where it is: a click on a button would take the focus,
        // and with it the field a name is inserted into.
        onMouseDown={(e) => e.preventDefault()}
        onClick={() => click(source, name)}
      >
        {label}
      </button>
    );
  };

  return (
    <section className="pp-section" aria-label="Bands">
      <h3 className="pp-heading">Bands</h3>
      <div className="pp-chips">
        {view.sources.flatMap((source) =>
          source.names.length === 0 ? [chip(source, null)] : source.names.map((name) => chip(source, name)),
        )}
      </div>
      <p className="pp-help">
        {view.assets.length} of at most {view.info?.maxAssets ?? 16} bands in the order. A click adds a band to the
        order or leaves it out
        {hasBandMath
          ? "; with the cursor in a band-math expression, it inserts the band's name there instead and changes nothing else."
          : '.'}
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

              <section className="pp-section" aria-label="Processing steps">
                <h3 className="pp-heading">Processing steps</h3>
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
                <p className="pp-summary" aria-label="Data type">
                  Data type: <strong>{view.dtype}</strong>
                  {view.dtypeChosen ? ' (your choice)' : ' (chosen automatically)'}
                </p>
                {view.dtypeAutomatic && !view.dtypeChosen && <span className="pp-help">{view.dtypeAutomatic.reason}</span>}
                {view.dtypeNote && <p className="hint-text warn">{view.dtypeNote}</p>}
                <details className="pp-details">
                  <summary>Change the data type</summary>
                  <label className="vc-field pp-field">
                    Data type
                    <select value={view.dtypeChosen ? view.dtype : ''} onChange={(e) => p.setDtype(e.target.value)}>
                      <option value="">Automatic{view.dtypeAutomatic ? `: ${view.dtypeAutomatic.value}` : ''}</option>
                      {view.dtypeOptions.map((option) => (
                        <option
                          key={option.value}
                          value={option.value}
                          disabled={option.disabledReason !== null}
                          title={option.disabledReason ?? undefined}
                        >
                          {option.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  {view.dtypeOptions.some((o) => o.disabledReason) && (
                    <span className="pp-help">{AFTER_BAND_MATH} These types are not offered.</span>
                  )}
                </details>
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
