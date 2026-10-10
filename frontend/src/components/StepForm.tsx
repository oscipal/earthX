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
  onChange,
  onFocus,
}: {
  field: Field;
  value: FieldValue | undefined;
  error: string | undefined;
  inputId: string;
  onChange: (value: FieldValue) => void;
  onFocus: () => void;
}) {
  const describedBy = field.description || error ? `${inputId}-help` : undefined;
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
          onFocus={onFocus}
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
          onFocus={onFocus}
        >
          <option value="">— choose —</option>
          {field.options?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
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
          onFocus={onFocus}
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
  onFocus,
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
  onFocus: () => void;
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
            onChange={(v) => onChange(field.name, v)}
            onFocus={onFocus}
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
