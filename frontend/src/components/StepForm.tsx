// One step of the processing panel: the form built from its operator's
// parameter schema (`schemaForm.ts`). What a field means is the tooltip of an ⓘ beside its label, not a text in the
// box (Otto, 30.10.2026); an error of the field and the server's own refusal of this step are shown below it.

import { Fragment, useEffect, useRef, useState, type ReactNode } from 'react';

import type { Operator } from '../processingOrder';
import { integersIn, namesIn, type Field, type FieldValue } from '../schemaForm';
import type { EarthxMask } from '../types';
import { CellSize, CellSizeError, CrsRefusal } from './CellSize';
import Tip from './Tip';
import { useCellSizeTip } from './useCellSizeTip';
import { useCrsLookup } from './useCrsLookup';

function FieldInput({
  field,
  value,
  error,
  inputId,
  bandTarget,
  extraTip,
  labelNote,
  onChange,
}: {
  field: Field;
  value: FieldValue | undefined;
  error: string | undefined;
  inputId: string;
  // Set on the expression of a band-math step: the key of its step. A band chip
  // inserts its name only into the field that has the cursor and carries this.
  bandTarget?: number;
  // More for the tooltip of the label, after what the schema says of the field.
  extraTip?: string | null;
  // Small beside the title, before the ⓘ: the unit of the resolution.
  labelNote?: ReactNode;
  onChange: (value: FieldValue) => void;
}) {
  // One sentence per option, from the operator's schema (M4-24); no option is recommended.
  const options = field.options
    ?.filter((option) => field.optionHelp?.[option])
    .map((option) => `${option}: ${field.optionHelp?.[option]}`)
    .join(' ');
  const tip = [field.description, options, extraTip].filter(Boolean).join(' ');
  const label = (
    <span className="pp-label">
      {field.title}
      {field.required || field.kind === 'boolean' ? '' : ' (optional)'}
      {labelNote}
      {tip && <Tip text={tip} />}
    </span>
  );
  const problem = error && <span className="hint-text error">{error}</span>;
  if (field.kind === 'boolean') {
    return (
      <label className="pp-check">
        <input id={inputId} type="checkbox" checked={value === true} onChange={(e) => onChange(e.target.checked)} />
        {label}
        {problem}
      </label>
    );
  }
  const text = typeof value === 'string' ? value : '';
  return (
    <label className="vc-field pp-field" htmlFor={inputId}>
      {label}
      {field.kind === 'enum' ? (
        <select
          id={inputId}
          value={text}
          aria-invalid={!!error}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">— choose —</option>
          {field.options?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : bandTarget !== undefined ? (
        // A band-math expression: wraps in the wide panel (M4-13c §3.1), but stays
        // one line — Enter adds none, and a pasted line break becomes a space.
        <textarea
          id={inputId}
          rows={2}
          value={text}
          maxLength={field.maxLength}
          spellCheck={false}
          aria-invalid={!!error}
          data-band-target={bandTarget}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.nativeEvent.isComposing) e.preventDefault();
          }}
          onChange={(e) => onChange(e.target.value.replace(/[\r\n]+/gu, ' '))}
        />
      ) : (
        <input
          id={inputId}
          type="text"
          inputMode={field.kind === 'number' || field.kind === 'integer' ? 'decimal' : undefined}
          value={text}
          maxLength={field.maxLength}
          spellCheck={false}
          aria-invalid={!!error}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {problem}
    </label>
  );
}

// The name a band math step gives its band. What is typed is the field's own until the person leaves it (or presses
// Enter) with a name that breaks no rule: only then do the steps and the output follow (review of #250). A name that
// breaks a rule is told at once, in a hint under the field, and holds back the steps, "Review" and "Start job".
function NameInput({
  field,
  value,
  inputId,
  tip,
  check,
  onCommit,
  onProblem,
}: {
  field: Field;
  value: string;
  inputId: string;
  tip: string | undefined;
  check: (name: string) => string | null;
  onCommit: (name: string) => void;
  onProblem: (reason: string | null) => void;
}) {
  const [draft, setDraft] = useState(value);
  useEffect(() => setDraft(value), [value]);
  const problem = check(draft);
  const report = useRef(onProblem);
  report.current = onProblem;
  useEffect(() => {
    report.current(problem);
  }, [problem]);
  useEffect(() => () => report.current(null), []);
  const commit = () => {
    if (problem === null && draft !== value) onCommit(draft);
  };
  return (
    <label className="vc-field pp-field" htmlFor={inputId}>
      <span className="pp-label">
        {field.title}
        {tip && <Tip text={tip} />}
      </span>
      <input
        id={inputId}
        type="text"
        value={draft}
        maxLength={field.maxLength}
        spellCheck={false}
        aria-invalid={problem !== null}
        aria-describedby={problem ? `${inputId}-problem` : undefined}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.nativeEvent.isComposing) commit();
        }}
      />
      {problem && (
        <span id={`${inputId}-problem`} className="hint-text error">
          {problem}
        </span>
      )}
    </label>
  );
}

// "Bands" of a normalize step: the bands it converts, chosen from the bands of the data and the results of the steps
// before it. The value is the list as text, like the classes of a mask.
function BandChoice({
  field,
  names,
  value,
  error,
  onChange,
}: {
  field: Field;
  names: readonly string[];
  value: FieldValue | undefined;
  error: string | undefined;
  onChange: (value: FieldValue) => void;
}) {
  const chosen = namesIn(typeof value === 'string' ? value : '');
  const toggle = (name: string) => onChange((chosen.includes(name) ? chosen.filter((n) => n !== name) : [...chosen, name]).join(', '));
  // A band the list names that cannot be offered here (typed in a recipe, or taken from this selection) stays visible.
  const shown = [...names, ...chosen.filter((name) => !names.includes(name))];
  return (
    <fieldset className="pp-classes">
      <legend>
        {field.title}
        {field.description && <Tip text={field.description} />}
      </legend>
      <div className="pp-chips">
        {shown.map((name) => (
          <button
            key={name}
            type="button"
            className={`pp-chip${chosen.includes(name) ? ' on' : ''}`}
            aria-pressed={chosen.includes(name)}
            onClick={() => toggle(name)}
          >
            {name}
          </button>
        ))}
      </div>
      {error && <span className="hint-text error">{error}</span>}
    </fieldset>
  );
}

// "Classes to hide" of a mask step: one box per class the layer knows, with the name the registry
// gives it. The recipe lists exactly the classes ticked, ascending (the text of the field is the
// list). The classes the dataset suggests are ticked when the step is added, nothing is applied
// unseen.
function ClassPicker({
  field,
  layer,
  value,
  error,
  onChange,
}: {
  field: Field;
  layer: EarthxMask;
  value: FieldValue | undefined;
  error: string | undefined;
  onChange: (value: FieldValue) => void;
}) {
  const ticked = new Set(integersIn(typeof value === 'string' ? value : '') ?? []);
  const toggle = (klass: number) => {
    const next = new Set(ticked);
    if (!next.delete(klass)) next.add(klass);
    onChange([...next].sort((a, b) => a - b).join(', '));
  };
  return (
    <fieldset className="pp-classes">
      <legend>
        Classes to hide
        <Tip
          text={[
            field.description ?? 'Pixels of the ticked classes are hidden in every band.',
            `The layer ${layer.band} is read for it.`,
            layer.note,
          ]
            .filter(Boolean)
            .join(' ')}
        />
        {layer.reference && (
          <a className="pp-class-table" href={layer.reference} target="_blank" rel="noreferrer noopener">
            Class table
          </a>
        )}
      </legend>
      {layer.classes.map((entry) => (
        <label key={entry.value} className="pp-check">
          <input type="checkbox" checked={ticked.has(entry.value)} onChange={() => toggle(entry.value)} />
          {entry.value} · {entry.label}
          {layer.suggested.includes(entry.value) && <span className="pp-help"> (suggested)</span>}
        </label>
      ))}
      {error && <span className="hint-text error">{error}</span>}
    </fieldset>
  );
}

export default function StepForm({
  index,
  count,
  stepKey,
  operator,
  values,
  errors,
  showErrors,
  unsupported,
  refusal,
  latitude,
  maskLayer,
  earlier,
  dataBands,
  onInsert,
  checkName,
  onRename,
  onNameProblem,
  onChange,
  onMove,
  onRemove,
}: {
  index: number;
  count: number;
  stepKey: number;
  operator: Operator | undefined;
  values: Record<string, FieldValue>;
  errors: Record<string, string>;
  // Errors of empty fields only after a review was asked for; a field the user
  // has typed into shows its error at once.
  showErrors: boolean;
  unsupported?: string;
  refusal: string | null;
  // The middle latitude of the area the order covers, for the size of a cell in degrees.
  latitude: number | null;
  // `earthx:mask` of the dataset, for the classes of a mask step.
  maskLayer: EarthxMask | null;
  // The names of the bands the steps before this one add, and the bands of the data a step may name (adr/0020 §14).
  earlier: readonly string[];
  dataBands: readonly string[];
  // A name put into this step's expression.
  onInsert: (name: string) => void;
  // The name of a band math step: what is wrong with a name, taking it over, and telling what is wrong with the one typed.
  checkName: (name: string) => string | null;
  onRename: (name: string) => void;
  onNameProblem: (reason: string | null) => void;
  onChange: (name: string, value: FieldValue) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}) {
  // A mask step names its layer from the registry (`source`), the user ticks classes instead.
  const masks = operator?.op === 'mask' && maskLayer !== null;
  const fields = operator?.form.supported
    ? operator.form.fields.filter((f) => f.kind !== 'const' && !(masks && f.name === 'source'))
    : [];
  // `reproject` (M4-13c-3): what the target CRS and the resolution mean.
  const reprojects = operator?.op === 'reproject';
  useCrsLookup(reprojects ? values.crs : undefined);
  const cellTip = useCellSizeTip(values.crs, values.resolution, latitude);
  const bandMath = operator?.op === 'band_math';
  // The title is the number and the name of the step: the band a band math step adds, or "Mask_1" and the like for a
  // step that adds none (adr/0020 §14).
  const own = operator ? operator.op.charAt(0).toUpperCase() + operator.op.slice(1) : 'Unknown operator';
  const name = bandMath ? (typeof values.name === 'string' && values.name !== '' ? values.name : '…') : `${own}_${index + 1}`;
  return (
    <li className="pp-step" aria-label={`Step ${index + 1}: ${operator?.title ?? 'unknown operator'}`}>
      <div className="pp-step-head">
        <span className="pp-step-title">
          {index + 1}. {name}
          {operator && <span className="pp-step-op"> {operator.title.toLowerCase()}</span>}
        </span>
        <span className="pp-step-actions">
          <button type="button" className="link-btn" title="Move this step up" disabled={index === 0} onClick={() => onMove(-1)}>
            ↑ Up
          </button>
          <button
            type="button"
            className="link-btn"
            title="Move this step down"
            disabled={index === count - 1}
            onClick={() => onMove(1)}
          >
            ↓ Down
          </button>
          <button type="button" className="link-btn" title="Remove this step" onClick={onRemove}>
            ✕ Remove
          </button>
        </span>
      </div>
      {unsupported && <p className="hint-text error">{unsupported}</p>}
      {fields.map((field) => {
        const value = values[field.name];
        const touched = typeof value === 'string' && value !== '';
        if (masks && field.name === 'classes') {
          return (
            <ClassPicker
              key={field.name}
              field={field}
              layer={maskLayer}
              value={value}
              error={showErrors || touched ? errors[field.name] : undefined}
              onChange={(v) => onChange(field.name, v)}
            />
          );
        }
        if (field.kind === 'names') {
          return (
            <BandChoice
              key={field.name}
              field={field}
              names={[...earlier, ...dataBands.filter((band) => !earlier.includes(band))]}
              value={value}
              error={showErrors || touched ? errors[field.name] : undefined}
              onChange={(v) => onChange(field.name, v)}
            />
          );
        }
        if (bandMath && field.name === 'name') {
          return (
            <NameInput
              key={field.name}
              field={field}
              value={typeof value === 'string' ? value : ''}
              inputId={`pp-step-${stepKey}-${field.name}`}
              tip={field.description}
              check={checkName}
              onCommit={onRename}
              onProblem={onNameProblem}
            />
          );
        }
        return (
          <Fragment key={field.name}>
            <FieldInput
              field={field}
              value={value}
              error={showErrors || touched ? errors[field.name] : undefined}
              inputId={`pp-step-${stepKey}-${field.name}`}
              bandTarget={bandMath && field.name === 'expression' ? stepKey : undefined}
              extraTip={reprojects && field.name === 'resolution' ? cellTip : undefined}
              labelNote={reprojects && field.name === 'resolution' ? <CellSize code={values.crs} /> : undefined}
              onChange={(v) => onChange(field.name, v)}
            />
            {reprojects && field.name === 'crs' && <CrsRefusal code={values.crs} />}
            {reprojects && field.name === 'resolution' && <CellSizeError code={values.crs} />}
          </Fragment>
        );
      })}
      {bandMath && earlier.length > 0 && (
        <div className="pp-chips" role="group" aria-label="Results of earlier steps">
          {earlier.map((band) => (
            <button
              key={band}
              type="button"
              className="pp-chip"
              // Keep the cursor where it is: a click on a button would take the focus, and with it the field.
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onInsert(band)}
            >
              {band}
            </button>
          ))}
        </div>
      )}
      {refusal && (
        <p className="hint-text error" role="alert">
          {refusal}
        </p>
      )}
    </li>
  );
}
