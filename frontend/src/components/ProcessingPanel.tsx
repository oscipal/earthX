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
  auxiliaryAssetsOf,
  formatBytes,
  formatDuration,
  formatMegapixels,
  insertName,
  isArea,
  lonelyBand,
  namesInExpression,
  processBlockReason,
  selectableAssets,
  selectAllBands,
  shownUnit,
  uniqueNames,
  type Area,
  type BandSource,
} from '../processingOrder';
import {
  furtherNote,
  MAX_PREVIEW_ASSETS,
  planPreview,
  previewUnit,
  rescaleOf,
} from '../processingPreview';
import {
  bandMathExpressions,
  orderView,
  type PartOutcome,
  selectionState,
  useProcessingStore,
  type OrderView,
} from '../processingStore';
import { MAX_RECIPE_BYTES } from '../recipeFile';
import { COLORMAPS } from '../render';
import { useAppStore } from '../store';
import type { StacItem } from '../types';
import JobDetails from './JobDetails';
import ShareLink from './ShareLink';
import StepForm from './StepForm';

const PASS_NOTE = 'One job covers the scenes of one pass; the scenes of another pass need a job of their own.';

// The expression field that has the cursor, if one has: only into that field a
// band chip inserts its name (Otto, 12.10.2026).
function focusedExpression(): HTMLTextAreaElement | null {
  const active = document.activeElement;
  return active instanceof HTMLTextAreaElement && active.dataset.bandTarget !== undefined ? active : null;
}

// "Load recipe…" (M4-19d): the steps and the data type of a `recipe.json` of the user's
// own, onto the current selection. The file is read here, nothing leaves the browser.
function RecipeLoader() {
  const load = useProcessingStore((s) => s.loadRecipe);
  const [outcome, setOutcome] = useState<{ ok: boolean; message: string } | null>(null);
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
        ? { ok: true, message: ['Recipe loaded.', ...result.notes].join(' ') }
        : { ok: false, message: result.reason },
    );
  };

  return (
    <div className="pp-recipe">
      <label className={`ghost-btn pp-recipe-btn${busy ? ' disabled' : ''}`} title="Take the steps and the data type from a recipe.json, onto the current selection">
        ⬆ Load recipe…
        <input type="file" accept=".json,application/json" hidden disabled={busy} onChange={(e) => void pick(e)} />
      </label>
      {outcome && (
        <p className={outcome.ok ? 'pp-help' : 'hint-text error'} role="status">
          {outcome.message}
        </p>
      )}
    </div>
  );
}

function Bands({ view }: { view: OrderView }) {
  const steps = useProcessingStore((s) => s.steps);
  const picked = useProcessingStore((s) => s.picked);
  const togglePick = useProcessingStore((s) => s.togglePick);
  const setPicked = useProcessingStore((s) => s.setPicked);
  const updateStep = useProcessingStore((s) => s.updateStep);
  // Where the cursor goes once the expression has its new text: a controlled
  // field moves it to the end when its value changes, so it is set after the commit.
  const caret = useRef<{ field: HTMLTextAreaElement; at: number } | null>(null);
  useLayoutEffect(() => {
    const pending = caret.current;
    caret.current = null;
    if (pending?.field.isConnected) pending.field.setSelectionRange(pending.at, pending.at);
  });
  const [limitNote, setLimitNote] = useState<string | null>(null);
  const unique = uniqueNames(view.sources);
  const selectable = selectableAssets(view.sources, auxiliaryAssetsOf(view.dataset?.collection), view.maskLayer?.asset ?? null);
  // A dataset or scene with one band has it picked on opening, once: a later "Clear" stays cleared.
  const lonely = lonelyBand(selectable, view.sources);
  const autoPicked = useRef<string | null>(null);
  useEffect(() => {
    if (lonely === null || autoPicked.current === lonely) return;
    autoPicked.current = lonely;
    if (picked.length === 0) setPicked([lonely]);
  }, [lonely, picked.length, setPicked]);
  const hasBandMath = steps.some((s) => s.op === 'band_math');
  const named = new Set(bandMathExpressions(steps).flatMap((e) => [...namesInExpression(e)]));
  if (!view.pass) return null;
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
    if (source.asset === view.maskAsset?.asset) return;
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
    const byMask = pressed && source.asset === view.maskAsset?.asset;
    const byExpression = pressed && !byMask && !picked.includes(source.asset);
    const label = name !== null && unique.get(name) === source.asset ? name : source.asset;
    const unit = shownUnit(name === null ? source.unit : source.units[source.names.indexOf(name)]);
    return (
      <button
        key={`${source.asset}/${name ?? ''}`}
        type="button"
        className={`pp-chip${pressed ? ' on' : ''}`}
        aria-pressed={pressed}
        title={
          byMask
            ? `${source.asset} is the layer of the mask step: remove that step to leave it out`
            : byExpression
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
        {unit && <span className="pp-chip-unit"> · {unit}</span>}
      </button>
    );
  };

  // "Select all" takes every band or says why not; it never takes a part of them in silence.
  const selectAll = () => {
    const needed = view.maskAsset ? [view.maskAsset.asset] : [];
    const result = selectAllBands(view.sources, selectable, bandMathExpressions(steps), needed, view.info?.maxAssets ?? 16);
    if ('reason' in result) {
      setLimitNote(result.reason);
      return;
    }
    setLimitNote(null);
    setPicked(result.assets);
  };
  const clear = () => {
    setLimitNote(null);
    setPicked([]);
  };

  return (
    <section className="pp-section" aria-label="Bands">
      <div className="pp-bands-head">
        <h3 className="pp-heading">Bands</h3>
        <button
          type="button"
          className="link-btn"
          disabled={selectable.length === 0}
          title="Pick every band of the data. Pictures such as the true-colour preview and the mask layer are not bands."
          onClick={selectAll}
        >
          Select all bands
        </button>
        <button
          type="button"
          className="link-btn"
          disabled={picked.length === 0}
          title="Leave out the bands you picked. Bands named in an expression or needed by a step stay."
          onClick={clear}
        >
          Clear
        </button>
      </div>
      {limitNote && (
        <p className="pp-help" role="status">
          {limitNote}
        </p>
      )}
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
  const plan = planPreview(steps, view.info);
  const range = rescaleOf(rangeDraft);
  const sceneCount = view.pass?.items.length ?? 0;
  return (
    <section className="pp-section" aria-label="Preview on the map">
      <h3 className="pp-heading">
        Preview on the map{' '}
        {preview && (
          <span className="pp-badge">
            Preview
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
              disabled={!rangeByHand && !rangeEdited && rangeNote === null}
              title="Use the range measured on the first scene (the 2nd to 98th percentile, or −1 to 1 for an index)"
              onClick={() => autoStretch()}
            >
              Auto stretch
            </button>
          </div>
          {'problem' in range && <p className="hint-text error">{range.problem}</p>}
          {rangeNote && <p className="hint-text">{rangeNote}</p>}
          {view.assets.length === 0 && (
            <p className="hint-text">Pick a band, or name it in the expression, to see the preview.</p>
          )}
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
    <p className="pp-help">The order also reads the mask layer {mask.asset}; it is not in the result.</p>
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
  if (!open) return null;
  if (p.detailJobID) return <JobDetails />;

  const dataset = app.datasets.find((d) => d.id === app.datasetId);
  // The same rule as the button in the ViewBar: scenes picked by hand.
  const reason = processBlockReason(dataset, app.selectedIds.length);
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
  const startTitle = startReady
    ? view.runAs === 'one'
      ? 'Start this order as a job'
      : 'Start the jobs the server took'
    : batch
      ? 'The server refused every job'
      : 'Review the order first';
  const showErrors = p.reviewAsked;
  const sceneCount = view.pass?.items.length ?? 0;
  // A refusal belongs to the order it refused; a changed draft hides it.
  const refusals = [p.reviewError, p.startError].filter((r) => r !== null && r.key === view.key);
  const refusalAt = (index: number) => refusals.find((r) => r!.step === index)?.message ?? null;
  const orderRefusals = refusals.filter((r) => r!.step === null);
  const tooLarge =
    p.area === 'scene' &&
    (refusals.some((r) => r!.status === 413) || (batch?.some((part) => part.refusal?.status === 413) ?? false));
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
                            latitude={latitude}
                            maskLayer={view.maskLayer}
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

                <section className="pp-section" aria-label="Output">
                  <h3 className="pp-heading">Output</h3>
                  <p className="pp-summary" aria-label="Data type">
                    Data type: <strong>{view.dtype}</strong>
                    {view.dtypeChosen ? ' (your choice)' : ' (chosen automatically)'}
                  </p>
                  {view.dtypeAutomatic && !view.dtypeChosen && (
                    <span className="pp-help">{view.dtypeAutomatic.reason}</span>
                  )}
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
                    {view.dtypeOptions.find((o) => o.disabledReason) && (
                      <span className="pp-help">
                        {view.dtypeOptions.find((o) => o.disabledReason)!.disabledReason} These types are not offered.
                      </span>
                    )}
                  </details>
                </section>

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
              disabled={p.reviewing || p.starting || !!crsBlock}
              title={crsBlock ?? 'Ask the server what this job is expected to cost'}
              onClick={() => void p.reviewOrder()}
            >
              {p.reviewing ? 'Reviewing…' : 'Review'}
            </button>
            <button
              type="button"
              className="primary-btn"
              disabled={!startReady || p.starting || !!crsBlock}
              title={crsBlock ?? startTitle}
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
