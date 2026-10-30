// The processing panel (M4-13b): an order for the current selection — the
// scenes of one pass (a mosaic when there are several, M4-12b), whole or cut to
// the AOI (M4-13c §3.2), steps from the operators the dataset allows — reviewed
// with an estimate before it starts as a job. The same steps can make one job per
// pass or per scene (M4-13c-4). Built from the schema of
// `/processing/processes/recipe?dataset=…`, nothing per dataset here. A side
// bar at the right edge, a sheet from below on narrow screens (M4-13c §3.1);
// the jobs are listed in the processing manager beside the rail, and a click
// on one shows its details here (`JobDetails.tsx`, UI-01). The first step shows
// on the map as a tile preview (M4-13c-2, `processingPreview.ts`).

import { useEffect, useLayoutEffect, useRef, useState, type ChangeEvent } from 'react';
import { useShallow } from 'zustand/react/shallow';

import { crsBlockReason, midLatitude } from '../crsUnit';
import { polygonBbox } from '../geoUtils';
import { totalOf } from '../processingBatch';
import {
  EMPTY_OUTPUT,
  formatBytes,
  formatDuration,
  formatMegapixels,
  insertName,
  isArea,
  processBlockReason,
  type Area,
  type DataBand,
} from '../processingOrder';
import {
  furtherNote,
  MAX_PREVIEW_ASSETS,
  planPreview,
  previewTitle,
  previewUnit,
  rescaleOf,
} from '../processingPreview';
import { isBandMath, nameProblem, resultNameOf } from '../processingBands';
import { orderView, type PartOutcome, selectionState, useProcessingStore, type OrderView } from '../processingStore';
import { CONVERTED_NOTE } from '../recipeUpgrade';
import { MAX_RECIPE_BYTES } from '../recipeFile';
import { COLORMAPS } from '../render';
import { ticksOfOpen, useAppStore } from '../store';
import type { StacItem } from '../types';
import JobDetails from './JobDetails';
import ShareLink from './ShareLink';
import StepForm from './StepForm';
import Tip from './Tip';
import usePreviewLoading, { LOADING_TITLE } from './usePreviewLoading';

// What the server says when the output needs more memory than a job may use (`plan.py`, 413).
const isMemoryRefusal = (message: string): boolean => /\bof memory\b/u.test(message);

const PASS_NOTE = 'One job covers the scenes of one pass; the scenes of another pass need a job of their own.';

// The expression field that has the cursor, if one has: only into that field a
// band chip inserts its name (Otto, 12.10.2026).
function focusedExpression(): HTMLTextAreaElement | null {
  const active = document.activeElement;
  return active instanceof HTMLTextAreaElement && active.dataset.bandTarget !== undefined ? active : null;
}

// A name put into an expression (`insertName`) and the cursor behind it. A controlled field moves its cursor to the end
// when its value changes, so the cursor is set after the commit; the component that calls this renders again then.
function useNameInsert() {
  const updateStep = useProcessingStore((s) => s.updateStep);
  const caret = useRef<{ field: HTMLTextAreaElement; at: number } | null>(null);
  useLayoutEffect(() => {
    const pending = caret.current;
    caret.current = null;
    if (pending?.field.isConnected) pending.field.setSelectionRange(pending.at, pending.at);
  });
  return (field: HTMLTextAreaElement, name: string) => {
    const start = field.selectionStart ?? field.value.length;
    const inserted = insertName(field.value, start, field.selectionEnd ?? start, name);
    caret.current = { field, at: inserted.caret };
    updateStep(Number(field.dataset.bandTarget), 'expression', inserted.text);
  };
}

// "Load recipe…" (M4-19d): the steps and the data type of a `recipe.json` of the user's
// own, onto the current selection. The file is read here, nothing leaves the browser.
function RecipeLoader() {
  const load = useProcessingStore((s) => s.loadRecipe);
  const [outcome, setOutcome] = useState<{ ok: boolean; message: string; converted?: boolean } | null>(null);
  const [busy, setBusy] = useState(false);

  const pick = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file) return;
    if (!file.name.toLowerCase().endsWith('.json')) return setOutcome({ ok: false, message: 'Pick a .json file.' });
    if (file.size > MAX_RECIPE_BYTES) return setOutcome({ ok: false, message: 'The file is larger than 1 MB.' });
    setBusy(true);
    setOutcome(null);
    const result = await load(await file.text());
    setBusy(false);
    setOutcome(
      result.ok
        ? { ok: true, message: ['Recipe loaded.', ...result.notes].join(' '), ...(result.converted ? { converted: true } : {}) }
        : { ok: false, message: result.reason },
    );
  };

  return (
    <div className="pp-recipe">
      <label className={`ghost-btn pp-recipe-btn${busy ? ' disabled' : ''}`} title="Take the steps, the output bands and the data type from a recipe.json, onto the current selection">
        ⬆ Load recipe…
        <input type="file" accept=".json,application/json" hidden disabled={busy} onChange={(e) => void pick(e)} />
      </label>
      {outcome && (
        <p className={outcome.ok ? 'pp-help' : 'hint-text error'} role="status">
          {outcome.message}
          {outcome.converted && <Tip text={CONVERTED_NOTE} />}
        </p>
      )}
    </div>
  );
}

// The bands of the data, for information and as a help to write an expression (adr/0020 §14): a click puts the name into
// the expression that has the cursor, and does nothing otherwise. What the output holds is chosen at the end of the panel.
function Bands({ view, insert }: { view: OrderView; insert: (field: HTMLTextAreaElement, name: string) => void }) {
  if (!view.pass) return null;
  if (view.sources.length === 0) {
    return (
      <section className="pp-section" aria-label="Bands">
        <h3 className="pp-heading">Bands</h3>
        <p className="hint-text">This dataset does not list band names yet.</p>
      </section>
    );
  }
  return (
    <section className="pp-section" aria-label="Bands">
      <div className="pp-bands-head">
        <h3 className="pp-heading">Bands</h3>
        <Tip text="Bands of the data. Click one to put its name into an expression." />
      </div>
      <div className="pp-chips">
        {view.dataBands
          .filter((band) => !band.auxiliary)
          .map((band) => (
            <button
              key={`${band.asset}/${band.name}`}
              type="button"
              className="pp-chip"
              // Keep the cursor where it is: a click on a button would take the focus, and with it the field a name goes into.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => {
                const field = focusedExpression();
                if (field) insert(field, band.name);
              }}
            >
              {band.name}
              {band.unit && <span className="pp-chip-unit"> · {band.unit}</span>}
            </button>
          ))}
      </div>
    </section>
  );
}

// "Select Bands that are processed" (adr/0020 §9, §14): the bands of the output, the results of the steps ("New") and
// the bands of the data ("Data"), a click each. Nothing is checked for the person, but the result of a step and the one
// band of a dataset that has only one.
function OutputBands({ view }: { view: OrderView }) {
  const toggle = useProcessingStore((s) => s.toggleOutput);
  const checkLonely = useProcessingStore((s) => s.checkLonely);
  const setOutput = useProcessingStore((s) => s.setOutput);
  const setDtype = useProcessingStore((s) => s.setDtype);
  // A dataset or scene with one band has it checked on opening, once: a later "None" stays.
  const lonely = view.lonely;
  const checkedOnOpening = useRef<string | null>(null);
  const checked = lonely !== null && view.output.includes(lonely);
  // Not where the steps already add a band: the results are what is in the output then.
  const results = view.results.length;
  useEffect(() => {
    if (lonely === null || checkedOnOpening.current === lonely) return;
    checkedOnOpening.current = lonely;
    if (!checked && results === 0) checkLonely(lonely);
  }, [lonely, checked, results, checkLonely]);

  const on = new Set(view.output);
  const data = view.dataBands.filter((band) => !band.auxiliary || on.has(band.name));
  // What "All" takes: every result and every band of the data that is no layer and no auxiliary asset.
  const everything = [...view.results.map((result) => result.name), ...view.selectable];
  const chip = (name: string, band?: DataBand) => (
    <button key={name} type="button" className={`pp-chip${on.has(name) ? ' on' : ''}`} aria-pressed={on.has(name)} onClick={() => toggle(name)}>
      {name}
      {band?.unit && <span className="pp-chip-unit"> · {band.unit}</span>}
    </button>
  );
  const count = view.output.length;
  return (
    <section className="pp-section" aria-label="Output">
      <div className="pp-bands-head">
        <h3 className="pp-heading">Select Bands that are processed</h3>
        <Tip text="The bands of the result. Click a band to put it into the output or take it out." />
        <span className="pp-help" aria-label="Output summary">
          {count} band{count === 1 ? '' : 's'} · {view.dtype}
        </span>
      </div>
      {view.results.length > 0 && (
        <div className="pp-chip-row" role="group" aria-label="New bands">
          <span className="pp-help">New</span>
          <div className="pp-chips">{view.results.map((result) => chip(result.name))}</div>
        </div>
      )}
      {data.length > 0 && (
        <div className="pp-chip-row" role="group" aria-label="Bands of the data">
          <span className="pp-help">Data</span>
          <div className="pp-chips">{data.map((band) => chip(band.name, band))}</div>
        </div>
      )}
      {(everything.some((name) => !on.has(name)) || count > 0) && (
        <div className="pp-bands-head">
          {everything.some((name) => !on.has(name)) && (
            <button
              type="button"
              className="link-btn"
              title="Put every band into the output"
              onClick={() => setOutput([...everything, ...view.output.filter((name) => !everything.includes(name))])}
            >
              All
            </button>
          )}
          {count > 0 && (
            <button type="button" className="link-btn" title="Take every band out of the output" onClick={() => setOutput([])}>
              None
            </button>
          )}
        </div>
      )}
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
          <select value={view.dtypeChosen ? view.dtype : ''} onChange={(e) => setDtype(e.target.value)}>
            <option value="">Automatic{view.dtypeAutomatic ? `: ${view.dtypeAutomatic.value}` : ''}</option>
            {view.dtypeOptions.map((option) => (
              <option key={option.value} value={option.value} disabled={option.disabledReason !== null} title={option.disabledReason ?? undefined}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        {view.dtypeOptions.find((o) => o.disabledReason) && (
          <span className="pp-help">{view.dtypeOptions.find((o) => o.disabledReason)!.disabledReason} These types are not offered.</span>
        )}
      </details>
    </section>
  );
}

// The middle latitude of what the order covers: the AOI for "AOI only", else the
// scenes of the pass (M4-13c-3); `null` without either.
function areaLatitude(area: Area, aoi: GeoJSON.Geometry | null, scenes: readonly StacItem[]): number | null {
  if (area === 'aoi') {
    const box = aoi ? polygonBbox(aoi) : null;
    return box ? midLatitude([box]) : null;
  }
  return midLatitude(scenes.flatMap((scene) => (scene.bbox ? [scene.bbox] : [])));
}

// "Whole scene" or "AOI only" (M4-13c §3.2, K1, K4).
function AreaChoice({ view, hasAoi }: { view: OrderView; hasAoi: boolean }) {
  const area = useProcessingStore((s) => s.area);
  const setArea = useProcessingStore((s) => s.setArea);
  const scenes = (view.pass?.items.length ?? 0) > 1 ? 'scenes' : 'scene';
  return (
    <div className="pp-area">
      <div className="pp-toggle" role="group" aria-label="Area">
        <span className="pp-help">Area:</span>
        <button
          type="button"
          className={`pp-seg${area === 'scene' ? ' on' : ''}`}
          aria-pressed={area === 'scene'}
          title="Process the whole scenes; no AOI is sent"
          onClick={() => setArea('scene')}
        >
          Whole scene
        </button>
        <button
          type="button"
          className={`pp-seg${area === 'aoi' ? ' on' : ''}`}
          aria-pressed={area === 'aoi'}
          disabled={!hasAoi}
          title={hasAoi ? 'Process only the AOI' : 'Draw an AOI first'}
          onClick={() => setArea('aoi')}
        >
          AOI only
        </button>
      </div>
      {area === 'scene' ? (
        <p className="pp-help">The result covers the whole {scenes}; the mask marks where they have data.</p>
      ) : (
        !hasAoi && <p className="hint-text error">Draw an AOI first, or choose “Whole scene”.</p>
      )}
    </div>
  );
}

// "Run as": one job, or one per pass or scene (M4-13c-4). Only offered where it
// makes a choice; a choice over the limit is greyed out with the reason.
function RunAsChoice({ view }: { view: OrderView }) {
  const setRunAs = useProcessingStore((s) => s.setRunAs);
  if (view.runChoices.length < 2) return null;
  const limits = [...new Set(view.runChoices.flatMap((choice) => (choice.disabled ? [choice.disabled] : [])))];
  return (
    <>
      <div className="pp-toggle" role="group" aria-label="Run as">
        <span className="pp-help">Run as:</span>
        {view.runChoices.map((choice) => (
          <button
            key={choice.value}
            type="button"
            className={`pp-seg${view.runAs === choice.value ? ' on' : ''}`}
            aria-pressed={view.runAs === choice.value}
            disabled={choice.disabled !== null}
            title={choice.disabled ?? undefined}
            onClick={() => setRunAs(choice.value)}
          >
            {choice.label}
          </button>
        ))}
      </div>
      {limits.map((limit) => (
        <p key={limit} className="pp-help">
          {limit}.
        </p>
      ))}
    </>
  );
}

// The review of a batch: the sum over the jobs the server took, and a line for each it refused.
function BatchEstimate({ parts }: { parts: readonly PartOutcome[] }) {
  const taken = parts.flatMap((part) => (part.doc ? [part.doc] : []));
  const refused = parts.filter((part) => part.refusal);
  const skipped = [...new Set(taken.flatMap((doc) => doc.skippedItems))];
  const total = totalOf(taken);
  return (
    <div className="pp-estimate" aria-label="Estimate">
      {taken.length > 0 && (
        <>
          <p>
            {total.jobs} job{total.jobs === 1 ? '' : 's'} · about {formatMegapixels(total.outputPixels)},{' '}
            {formatBytes(total.size)}, {total.units.toFixed(1)} units in total
          </p>
          {total.duration && <p>{formatDuration(total.duration)} of work</p>}
          <p className="pp-help">Jobs run 2 at a time per source; the rest wait.</p>
        </>
      )}
      {skipped.length > 0 && <p className="hint-text warn">Left out (the AOI misses them): {skipped.join(', ')}</p>}
      {refused.map((part) => (
        <p key={part.unit.key} className="hint-text error" role="alert" title={part.refusal!.reason}>
          {part.unit.label}: {part.refusal!.message}
        </p>
      ))}
      <p className="pp-help">An estimate, not a promise.</p>
    </div>
  );
}

// "Preview on the map" (M4-13c-2): the longest start of the steps that runs as tiles, with the range and
// colormap by hand (F3 (1)), and the preview as a layer of its own.
function PreviewSection({ view }: { view: OrderView }) {
  const steps = useProcessingStore((s) => s.steps);
  const preview = useProcessingStore((s) => s.preview);
  const previewNote = useProcessingStore((s) => s.previewNote);
  const rangeDraft = useProcessingStore((s) => s.rangeDraft);
  const setRangeDraft = useProcessingStore((s) => s.setRangeDraft);
  const applyRange = useProcessingStore((s) => s.applyRange);
  const pinPreview = useProcessingStore((s) => s.pinPreview);
  const rangeByHand = useProcessingStore((s) => s.rangeByHand);
  const rangeEdited = useProcessingStore((s) => s.rangeEdited);
  const rangeNote = useProcessingStore((s) => s.rangeNote);
  const measure = useProcessingStore((s) => s.measure);
  const autoStretch = useProcessingStore((s) => s.autoStretch);
  const unit = previewUnit(preview, measure);
  const loading = usePreviewLoading();
  const plan = planPreview(steps, view.info);
  const range = rescaleOf(rangeDraft);
  const sceneCount = view.pass?.items.length ?? 0;
  return (
    <section className="pp-section" aria-label="Preview on the map">
      <h3 className="pp-heading">
        Preview on the map{' '}
        {preview && (
          <span className="pp-badge" title={previewTitle(preview, measure)}>
            Preview
          </span>
        )}
        {loading && (
          <span className="pp-badge loading" title={LOADING_TITLE}>
            Loading…
          </span>
        )}
      </h3>
      {plan.state === 'off' ? (
        plan.reason && <p className="hint-text">{plan.reason}</p>
      ) : (
        <>
          <div className="pp-range" role="group" aria-label="Range and colormap">
            <label className="vc-field vc-num">
              <span>min</span>
              <input type="number" value={rangeDraft.vmin} onChange={(e) => setRangeDraft({ vmin: e.target.value })} />
            </label>
            <div className="pp-bound">
              <label className="vc-field vc-num">
                <span>max</span>
                <input type="number" value={rangeDraft.vmax} onChange={(e) => setRangeDraft({ vmax: e.target.value })} />
              </label>
              {unit && (
                <span className="pp-unit" aria-label="Unit of the range">
                  {unit}
                </span>
              )}
            </div>
            <label className="vc-field">
              <span>Colormap</span>
              <select value={rangeDraft.colormap} onChange={(e) => setRangeDraft({ colormap: e.target.value })}>
                <option value="">— none —</option>
                {COLORMAPS.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <button type="button" className="primary-btn vc-apply" disabled={'problem' in range} onClick={() => applyRange()}>
              Apply
            </button>
            <button
              type="button"
              className="link-btn"
              disabled={!rangeByHand && !rangeEdited && rangeNote === null && measure?.source !== 'fallback'}
              title="Use the measured range (the 2nd to 98th percentile, or −1 to 1 for an index); with AOI only, measured over the AOI"
              onClick={() => autoStretch()}
            >
              Auto stretch
            </button>
          </div>
          {'problem' in range && <p className="hint-text error">{range.problem}</p>}
          {rangeNote && <p className="hint-text">{rangeNote}</p>}
          {view.assets.length === 0 && <p className="hint-text">Pick a band for the output to see the preview.</p>}
          {view.assets.length > MAX_PREVIEW_ASSETS && (
            <p className="hint-text">No preview: the map takes at most {MAX_PREVIEW_ASSETS} bands.</p>
          )}
          {!view.pass && <p className="hint-text">Choose a pass to see the preview.</p>}
          {plan.further && <p className="pp-help">{furtherNote(plan)}</p>}
          {previewNote && <p className="hint-text">{previewNote}</p>}
          {sceneCount > 1 && (
            <p className="pp-help">
              Where scenes overlap, the preview may show another scene than the result: the job follows the mosaic rule of
              the server.
            </p>
          )}
          <div className="vc-actions">
            <button
              type="button"
              className="ghost-btn"
              disabled={!preview}
              title="Pin this preview into the layer manager"
              onClick={() => pinPreview()}
            >
              ＋ Add preview to layers
            </button>
          </div>
        </>
      )}
    </section>
  );
}

// The layer of a mask is part of the order without the user picking it (M4-18c); the review says so,
// or says that the scene has none.
function MaskLayerNote({ view }: { view: OrderView }) {
  const mask = view.maskAsset;
  if (!mask || !view.pass) return null;
  return mask.inOrder ? (
    view.output.includes(view.maskLayer?.band ?? mask.asset) ? null : <p className="pp-help">The order also reads the mask layer {mask.asset}; it is not in the result.</p>
  ) : (
    <p className="hint-text error">The scenes have no mask layer {mask.asset}: the job cannot hide anything.</p>
  );
}

// K2: a whole scene over the cap of one job (`413`) — try the AOI instead.
function TooLarge({ hasAoi }: { hasAoi: boolean }) {
  const setArea = useProcessingStore((s) => s.setArea);
  return (
    <p className="hint-text warn">
      The whole scene is too large for one job.{' '}
      {hasAoi ? (
        <>
          Try “AOI only”.{' '}
          <button type="button" className="link-btn" onClick={() => setArea('aoi')}>
            Use AOI only
          </button>
        </>
      ) : (
        'Draw an AOI to process a part of the scene.'
      )}
    </p>
  );
}

export default function ProcessingPanel() {
  const open = useProcessingStore((s) => s.open);
  const close = useProcessingStore((s) => s.closeProcessing);
  const app = useAppStore(useShallow(selectionState));
  const p = useProcessingStore();
  // Narrow screens only: the sheet from below folds down to its head.
  const [folded, setFolded] = useState(false);
  const insert = useNameInsert();
  if (!open) return null;
  if (p.detailJobID) return <JobDetails />;

  const dataset = app.datasets.find((d) => d.id === app.datasetId);
  // The same rule as the button in the ViewBar: scenes picked by hand.
  const reason = processBlockReason(dataset, ticksOfOpen(app).length);
  const description = app.datasetId ? p.descriptions[app.datasetId] : undefined;
  const view = orderView(app, p);
  const info = view.info;
  const built = view.built;
  const hasAoi = isArea(app.aoi);
  const batch = view.runAs !== 'one' && p.batch && p.batch.key === view.key ? p.batch.parts : null;
  const estimate = view.runAs === 'one' && p.estimate && p.estimate.key === view.key ? p.estimate.doc : null;
  const taken = batch ? batch.filter((part) => part.doc).length : 0;
  const startRefusals = p.batchStartRefusals?.key === view.key ? p.batchStartRefusals.refusals : [];
  const startLabel = p.starting
    ? 'Starting…'
    : view.runAs === 'one'
      ? 'Start job'
      : `Start ${batch && taken < view.parts.length ? `${taken} of ${view.parts.length}` : view.parts.length} jobs`;
  const startReady = view.runAs === 'one' ? !!estimate : taken > 0;
  const showErrors = p.reviewAsked;
  const sceneCount = view.pass?.items.length ?? 0;
  // A refusal belongs to the order it refused; a changed draft hides it.
  const refusals = [p.reviewError, p.startError].filter((r) => r !== null && r.key === view.key);
  const refusalAt = (index: number) => refusals.find((r) => r!.step === index)?.message ?? null;
  // The server's estimate said the output needs more memory than a job may use (adr/0020 §7): the start stays shut and
  // the reason is the tooltip of the button, not a line of the panel.
  const memory = refusals.find((r) => r!.step === null && r!.status === 413 && isMemoryRefusal(r!.message))?.message ?? null;
  const orderRefusals = refusals.filter((r) => r!.step === null && r!.message !== memory);
  const tooLarge =
    p.area === 'scene' &&
    (refusals.some((r) => r!.status === 413 && r!.message !== memory) ||
      (batch?.some((part) => part.refusal?.status === 413 && !isMemoryRefusal(part.refusal.message)) ?? false));
  const startTitle =
    view.output.length === 0
      ? EMPTY_OUTPUT
      : memory
        ? memory
        : startReady
          ? view.runAs === 'one'
            ? 'Start this order as a job'
            : 'Start the jobs the server took'
          : batch
            ? 'The server refused every job'
            : 'Review the order first';
  // A target CRS the server turned away holds the review back (M4-13c-3).
  const crsBlock = crsBlockReason(p.steps, p.crs);
  const latitude = areaLatitude(p.area, hasAoi ? app.aoi : null, view.pass?.items ?? []);

  return (
    <div className={`panel processing-panel${folded ? ' folded' : ''}`} role="dialog" aria-label="Processing">
      <div className="pp-head">
        <button
          type="button"
          className="pp-grip"
          aria-expanded={!folded}
          aria-label={folded ? 'Show the panel' : 'Fold the panel down'}
          title={folded ? 'Show the panel' : 'Fold the panel down'}
          onClick={() => setFolded(!folded)}
        >
          {folded ? '▴' : '▾'}
        </button>
        <div className="vc-head">
          <span className="vc-title">PROCESSING</span>
          <button type="button" className="link-btn" title="Close the panel" onClick={close}>
            ✕
          </button>
        </div>
        {!reason && (
          <section className="pp-section" aria-label="Selection">
            <p className="pp-summary">
              {[
                dataset?.title ?? app.datasetId,
                view.pass?.label,
                view.pass && (sceneCount === 1 ? view.pass.items[0].id : `${sceneCount} scenes`),
              ]
                .filter(Boolean)
                .join(' · ')}
            </p>
            <AreaChoice view={view} hasAoi={hasAoi} />
            <RunAsChoice view={view} />
            <RecipeLoader />
          </section>
        )}
      </div>

      <div className="pp-body">
        {reason ? (
          <p className="hint-text">{reason}</p>
        ) : (
          <>
            <section className="pp-section" aria-label="Scenes">
              {p.area === 'aoi' && hasAoi && view.candidates.length === 0 && (
                <p className="hint-text error">No selected scene meets the AOI.</p>
              )}
              {view.runAs !== 'one' && (
                <p className="pp-help" title={view.pass?.items.map((i) => i.id).join(', ')}>
                  Every {view.runAs} gets a job of its own with the same steps, bands and data type.
                </p>
              )}
              {view.runAs === 'one' && view.pass && sceneCount > 1 && (
                <p className="pp-help" title={view.pass.items.map((i) => i.id).join(', ')}>
                  The scenes are merged into one mosaic first; the steps run on the mosaic.
                </p>
              )}
              {view.runAs === 'one' && view.passes.length > 1 && (
                <>
                  <label className="vc-field pp-field">
                    Pass
                    <select value={view.pass?.key ?? ''} onChange={(e) => p.choosePass(e.target.value)}>
                      <option value="" disabled>
                        — choose one pass —
                      </option>
                      {view.passes.map((c) => (
                        <option key={c.key} value={c.key}>
                          {c.label} ({c.items.length} scene{c.items.length === 1 ? '' : 's'})
                        </option>
                      ))}
                    </select>
                  </label>
                  <p className="hint-text warn">{PASS_NOTE}</p>
                </>
              )}
            </section>

            {description?.state === 'loading' && <p className="hint-text">Loading the operators…</p>}
            {description?.state === 'error' && (
              <p className="hint-text error">
                The operators could not be loaded: {description.message}{' '}
                <button
                  type="button"
                  className="link-btn"
                  onClick={() => app.datasetId && p.ensureDescription(app.datasetId)}
                >
                  Retry
                </button>
              </p>
            )}

            {info && (
              <>
                <Bands view={view} insert={insert} />

                <section className="pp-section" aria-label="Processing steps">
                  <h3 className="pp-heading">Processing steps</h3>
                  {p.steps.length > 0 && (
                    <ol className="pp-steps">
                      {p.steps.map((step, index) => {
                        const operator = info.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion);
                        const problem = built?.stepProblems[index];
                        // The results of the steps before this one: the bands this step may name besides those of the data.
                        const earlier = view.results.slice(0, p.steps.slice(0, index).filter(isBandMath).length).map((r) => r.name);
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
                            latitude={latitude}
                            maskLayer={view.maskLayer}
                            earlier={earlier}
                            dataBands={view.selectable}
                            checkName={(name) =>
                              nameProblem(
                                name,
                                p.steps.filter((other) => other.key !== step.key && isBandMath(other)).map(resultNameOf),
                                view.dataNames,
                              )
                            }
                            onRename={(name) => p.renameResult(step.key, name)}
                            onNameProblem={(reason) => p.setNameProblem(step.key, reason)}
                            // As the chips above: into the expression that has the cursor, nowhere otherwise.
                            onInsert={(name) => {
                              const field = focusedExpression();
                              if (field) insert(field, name);
                            }}
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
                          : (view.nameBlock ?? operator.description ?? operator.title);
                      return (
                        <button
                          key={`${operator.op}/${operator.opVersion}`}
                          type="button"
                          className="ghost-btn pp-add-btn"
                          disabled={!operator.form.supported || full || !!view.nameBlock}
                          title={why}
                          onClick={() => p.addStep(operator.op, operator.opVersion)}
                        >
                          ＋ {operator.title}
                        </button>
                      );
                    })}
                  </div>
                  {!view.maskLayer && !info.operators.some((o) => o.op === 'mask') && (
                    <p className="hint-text">Mask: this dataset has no classification layer to read.</p>
                  )}
                  {info.operators.map((o) =>
                    o.form.supported ? null : (
                      <p key={`${o.op}/${o.opVersion}`} className="hint-text">
                        {o.title}: {o.form.reason}
                      </p>
                    ),
                  )}
                </section>

                <OutputBands view={view} />

                <PreviewSection view={view} />
              </>
            )}
          </>
        )}
      </div>

      {!reason && info && (
        <section className="pp-foot" aria-label="Review">
          {showErrors && built && built.problems.length > 0 && (
            <p className="hint-text error">{built.problems.join(' ')}</p>
          )}
          {view.maskAsset && <MaskLayerNote view={view} />}
          <div className="vc-actions">
            <button
              type="button"
              className="ghost-btn"
              disabled={p.reviewing || p.starting || !!crsBlock || !!view.nameBlock}
              title={crsBlock ?? view.nameBlock ?? 'Ask the server what this job is expected to cost'}
              onClick={() => void p.reviewOrder()}
            >
              {p.reviewing ? 'Reviewing…' : 'Review'}
            </button>
            <button
              type="button"
              className="primary-btn"
              disabled={!startReady || p.starting || !!crsBlock || !!view.nameBlock}
              title={crsBlock ?? view.nameBlock ?? startTitle}
              onClick={() => void p.startJob()}
            >
              {startLabel}
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
          {batch && <BatchEstimate parts={batch} />}
          {startRefusals.map((refusal) => (
            <p key={refusal.label} className="hint-text error" role="alert">
              {refusal.label}: {refusal.message}
            </p>
          ))}
          {orderRefusals.map((refusal, index) => (
            <p key={index} className="hint-text error" role="alert" title={refusal!.reason}>
              {refusal!.message}
            </p>
          ))}
          {tooLarge && <TooLarge hasAoi={hasAoi} />}
          <ShareLink view={view} />
        </section>
      )}
    </div>
  );
}
