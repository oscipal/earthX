// One step of the processing panel: the form built from its operator's
// parameter schema (`schemaForm.ts`). A help while typing; the server's own
// refusal of this step is shown below it.

import type { Operator } from '../processingOrder';
import type { Field, FieldValue } from '../schemaForm';

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
  const describedBy = field.description ? `${inputId}-help` : undefined;
  const help = (
    <>
      {field.description && (
        <span id={describedBy} className="pp-help">
          {field.description}
        </span>
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
            if (e.key === 'Enter') e.preventDefault();
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
  onChange: (name: string, value: FieldValue) => void;
  onMove: (direction: -1 | 1) => void;
  onRemove: () => void;
}) {
  const fields = operator?.form.supported ? operator.form.fields.filter((f) => f.kind !== 'const') : [];
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
        return (
          <FieldInput
            key={field.name}
            field={field}
            value={value}
            error={showErrors || touched ? errors[field.name] : undefined}
            inputId={`pp-step-${stepKey}-${field.name}`}
            bandTarget={operator?.op === 'band_math' && field.name === 'expression' ? stepKey : undefined}
            onChange={(v) => onChange(field.name, v)}
          />
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
