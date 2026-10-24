// One step of the processing panel: the form built from its operator's
// parameter schema (`schemaForm.ts`). A help while typing; the server's own
// refusal of this step is shown below it.

import { Fragment } from 'react';

import type { Operator } from '../processingOrder';
import { integersIn, type Field, type FieldValue } from '../schemaForm';
import type { EarthxMask } from '../types';
import { CellSize, CrsRefusal } from './CellSize';
import { useCrsLookup } from './useCrsLookup';

function FieldInput({
  field,
  value,
  error,
  inputId,
  bandTarget,
  onChange,
}: {
  field: Field;
  value: FieldValue | undefined;
  error: string | undefined;
  inputId: string;
  // Set on the expression of a band-math step: the key of its step. A band chip
  // inserts its name only into the field that has the cursor and carries this.
  bandTarget?: number;
  onChange: (value: FieldValue) => void;
}) {
  const helpId = field.description ? `${inputId}-help` : undefined;
  const optionsId = field.optionHelp ? `${inputId}-options` : undefined;
  const describedBy = [helpId, optionsId].filter(Boolean).join(' ') || undefined;
  const help = (
    <>
      {field.description && (
        <span id={helpId} className="pp-help">
          {field.description}
        </span>
      )}
      {field.optionHelp && (
        // One sentence per option, from the operator's schema (M4-24); no option is recommended.
        <ul id={optionsId} className="pp-help pp-options">
          {field.options
            ?.filter((option) => field.optionHelp?.[option])
            .map((option) => (
              <li key={option}>
                <strong>{option}</strong>: {field.optionHelp?.[option]}
              </li>
            ))}
        </ul>
      )}
      {error && <span className="hint-text error">{error}</span>}
    </>
  );
  if (field.kind === 'boolean') {
    return (
      <label className="pp-check">
        <input
          id={inputId}
          type="checkbox"
          checked={value === true}
          aria-describedby={describedBy}
          onChange={(e) => onChange(e.target.checked)}
        />
        {field.title}
        {help}
      </label>
    );
  }
  const text = typeof value === 'string' ? value : '';
  return (
    <label className="vc-field pp-field" htmlFor={inputId}>
      {field.title}
      {field.required ? '' : ' (optional)'}
      {field.kind === 'enum' ? (
        <select
          id={inputId}
          value={text}
          aria-describedby={describedBy}
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
          aria-describedby={describedBy}
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
          aria-describedby={describedBy}
          aria-invalid={!!error}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {help}
    </label>
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
  inputId,
  onChange,
}: {
  field: Field;
  layer: EarthxMask;
  value: FieldValue | undefined;
  error: string | undefined;
  inputId: string;
  onChange: (value: FieldValue) => void;
}) {
  const ticked = new Set(integersIn(typeof value === 'string' ? value : '') ?? []);
  const toggle = (klass: number) => {
    const next = new Set(ticked);
    if (!next.delete(klass)) next.add(klass);
    onChange([...next].sort((a, b) => a - b).join(', '));
  };
  return (
    <fieldset className="pp-classes" aria-describedby={`${inputId}-help`}>
      <legend>Classes to hide</legend>
      {layer.classes.map((entry) => (
        <label key={entry.value} className="pp-check">
          <input type="checkbox" checked={ticked.has(entry.value)} onChange={() => toggle(entry.value)} />
          {entry.value} · {entry.label}
          {layer.suggested.includes(entry.value) && <span className="pp-help"> (suggested)</span>}
        </label>
      ))}
      <span id={`${inputId}-help`} className="pp-help">
        {field.description ?? 'Pixels of the ticked classes are hidden in every band.'} The layer {layer.band} is read
        for it and left out of the result.
        {layer.note && ` ${layer.note}`}
        {layer.reference && (
          <>
            {' '}
            <a href={layer.reference} target="_blank" rel="noreferrer noopener">
              Class table
            </a>
          </>
        )}
      </span>
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
  return (
    <li className="pp-step" aria-label={`Step ${index + 1}: ${operator?.title ?? 'unknown operator'}`}>
      <div className="pp-step-head">
        <span className="pp-step-title">
          {index + 1}. {operator?.title ?? 'Unknown operator'}
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
              inputId={`pp-step-${stepKey}-${field.name}`}
              onChange={(v) => onChange(field.name, v)}
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
              bandTarget={operator?.op === 'band_math' && field.name === 'expression' ? stepKey : undefined}
              onChange={(v) => onChange(field.name, v)}
            />
            {reprojects && field.name === 'crs' && <CrsRefusal code={values.crs} />}
            {reprojects && field.name === 'resolution' && (
              <CellSize code={values.crs} resolution={values.resolution} latitude={latitude} />
            )}
          </Fragment>
        );
      })}
      {refusal && (
        <p className="hint-text error" role="alert">
          {refusal}
        </p>
      )}
    </li>
  );
}
