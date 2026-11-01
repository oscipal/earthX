// The fields of a "Normalize" step of version 4 (NM4-11b, NM4-71): the method, the bands, and what the method takes. The fields
// depend on the method, which the schema cannot say, so the panel lays them out (`normalizeMethods.ts` holds the rules).
// Little text: what a method does, its formula and an example are the tooltip of the "Method" label.

import type { FieldValue } from '../schemaForm';
import type { MeasureStatus } from '../processingOrder';
import { METHODS, RANGES, isMethod, isStatistical, methodTip, rangeLabel } from '../normalizeMethods';
import { hasComma, oneNumber } from '../maskValues';
import Tip from './Tip';

const CLIP_TIP = 'Limit the result to the target range. Without it the values continue along the same line.';

export default function NormalizeFields({
  stepKey,
  values,
  errors,
  showErrors,
  locked,
  measure,
  onRetry,
  bands,
  onChange,
}: {
  stepKey: number;
  values: Record<string, FieldValue>;
  errors: Record<string, string>;
  showErrors: boolean;
  // Why the methods that measure cannot be chosen here (after a reprojection), or `null`.
  locked: string | null;
  // Where the measure of a statistical method stands: it is for the preview, the job measures itself.
  measure: MeasureStatus | undefined;
  onRetry: () => void;
  // The chips for the bands (the same block as in the other steps).
  bands: React.ReactNode;
  onChange: (name: string, value: FieldValue) => void;
}) {
  const method = typeof values.method === 'string' ? values.method : '';
  const text = (name: string) => (typeof values[name] === 'string' ? values[name] : '');
  const id = `pp-step-${stepKey}`;
  const shown = (name: string) => (showErrors || text(name) !== '' ? errors[name] : undefined);
  const comma = (names: string[]) => names.some((name) => hasComma(text(name)));
  const number = (name: string, label: string) => (
    <input
      type="text"
      inputMode="decimal"
      aria-label={label}
      aria-invalid={!!shown(name) || hasComma(text(name))}
      value={text(name)}
      maxLength={24}
      spellCheck={false}
      onChange={(e) => onChange(name, oneNumber(e.target.value))}
    />
  );
  const problem = (names: string[]) => {
    const message = comma(names) ? 'Use . for decimals.' : names.map(shown).find(Boolean);
    return message && <span className="hint-text error">{message}</span>;
  };
  const range = RANGES.find((r) => String(r.low) === text('low') && String(r.high) === text('high'));
  const target = (
    <div className="vc-field pp-field" role="group" aria-labelledby={`${id}-to`}>
      <span className="pp-label" id={`${id}-to`}>
        To
        <Tip text="The target range: the start becomes “min”, the end “max”. A larger “min” turns the values round." />
      </span>
      <div className="pp-where">
        {number('out_min', 'Target min')}
        <span className="pp-help">to</span>
        {number('out_max', 'Target max')}
      </div>
      {problem(['out_min', 'out_max'])}
    </div>
  );
  const clip = (
    <label className="pp-check">
      <input id={`${id}-clip`} type="checkbox" checked={values.clip === true} onChange={(e) => onChange('clip', e.target.checked)} />
      <span className="pp-label">
        Clip
        <Tip text={CLIP_TIP} />
      </span>
    </label>
  );
  return (
    <>
      <label className="vc-field pp-field" htmlFor={`${id}-method`}>
        <span className="pp-label">
          Method
          <Tip text={methodTip(method)} />
          {locked && <Tip tone="warn" text={locked} symbol="⚠" />}
        </span>
        <select
          id={`${id}-method`}
          value={method}
          aria-invalid={!!shown('method')}
          onChange={(e) => onChange('method', e.target.value)}
        >
          {!isMethod(method) && <option value="">— choose —</option>}
          {METHODS.map((m) => (
            <option key={m.value} value={m.value} disabled={locked !== null && isStatistical(m.value) && m.value !== method} title={m.formula}>
              {m.label}
            </option>
          ))}
        </select>
        {shown('method') && <span className="hint-text error">{shown('method')}</span>}
      </label>
      {bands}
      {method === 'linear' && (
        <div className="vc-field pp-field" role="group" aria-labelledby={`${id}-from`}>
          <span className="pp-label" id={`${id}-from`}>
            From
            <Tip text="The values that become “min” and “max” of the target range." />
          </span>
          <div className="pp-where">
            {number('in_min', 'From min')}
            <span className="pp-help">to</span>
            {number('in_max', 'From max')}
          </div>
          {problem(['in_min', 'in_max'])}
        </div>
      )}
      {method === 'percentile' && (
        <label className="vc-field pp-field" htmlFor={`${id}-range`}>
          <span className="pp-label">
            Range
            <Tip text="The values at these percentiles of the AOI become “min” and “max” of the target range. 0–100 % is the lowest to the highest value." />
          </span>
          <select
            id={`${id}-range`}
            value={range ? rangeLabel(range) : ''}
            aria-invalid={!!shown('low') || !!shown('high')}
            onChange={(e) => {
              const chosen = RANGES.find((r) => rangeLabel(r) === e.target.value);
              if (!chosen) return;
              onChange('low', String(chosen.low));
              onChange('high', String(chosen.high));
            }}
          >
            {!range && <option value="">— choose —</option>}
            {RANGES.map((r) => (
              <option key={rangeLabel(r)} value={rangeLabel(r)}>
                {rangeLabel(r)}
              </option>
            ))}
          </select>
          {problem(['low', 'high'])}
        </label>
      )}
      {(method === 'linear' || method === 'percentile') && (
        <>
          {target}
          {clip}
        </>
      )}
      {isStatistical(method) && measure && (
        <p className="pp-measure hint-text" role="status">
          {measure.state === 'measuring' && 'Measuring…'}
          {measure.state === 'ready' && (
            <>
              Preview measured ✓<Tip text={measure.text} />
            </>
          )}
          {measure.state === 'failed' && (
            <>
              <span className="error">Not measured.</span> <Tip tone="warn" text={measure.text} symbol="⚠" />{' '}
              {!measure.final && (
                <button type="button" className="link-btn" onClick={onRetry}>
                  Retry
                </button>
              )}
            </>
          )}
        </p>
      )}
    </>
  );
}
