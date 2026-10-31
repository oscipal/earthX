// The fields of a "Mask by value" step (DS-06b): the band that decides and the condition on its values. The schema
// gives a list of numbers, which the panel shows as the boxes the chosen condition needs; `maskValues.ts` holds the rules.

import type { FieldValue } from '../schemaForm';
import {
  CONDITIONS,
  betweenParts,
  betweenText,
  hasComma,
  oneNumber,
  valuesAfterConditionChange,
} from '../maskValues';
import Tip from './Tip';

const BAND_TIP = 'The band whose values decide. Pixels are hidden in every band.';
const WHERE_TIP =
  'Hides the pixels where the band is below or above the value, between the two (both included), or equal to one of the values. ' +
  "Compared in the band's data type. Pixels where the band has no value are hidden too.";

export default function MaskValuesFields({
  stepKey,
  values,
  errors,
  showErrors,
  earlier,
  dataBands,
  units,
  onChange,
}: {
  stepKey: number;
  values: Record<string, FieldValue>;
  errors: Record<string, string>;
  showErrors: boolean;
  // The results of the steps before this one, and the bands of the data: what the band may be.
  earlier: readonly string[];
  dataBands: readonly string[];
  // The unit of each band of the data that has one.
  units: Readonly<Record<string, string>>;
  onChange: (name: string, value: FieldValue) => void;
}) {
  const band = typeof values.band === 'string' ? values.band : '';
  const condition = typeof values.condition === 'string' ? values.condition : '';
  const text = typeof values.values === 'string' ? values.values : '';
  const [from, to] = betweenParts(text);
  const data = dataBands.filter((name) => !earlier.includes(name));
  // A band the step names that cannot be offered here (typed in a recipe) stays visible, with its error.
  const strange = band !== '' && !earlier.includes(band) && !data.includes(band);
  const unit = units[band];
  // Two boxes are one entry: it is told when both are filled, the rest only after a review was asked for.
  const valuesTouched = condition === 'between' ? from !== '' && to !== '' : text !== '';
  const bandError = showErrors || band !== '' ? errors.band : undefined;
  const comma = condition === 'between' ? hasComma(from) || hasComma(to) : (condition === 'lt' || condition === 'gt') && hasComma(text);
  const valuesError = comma ? 'Use . for decimals.' : showErrors || valuesTouched ? errors.values : undefined;
  const id = `pp-step-${stepKey}`;
  const number = (label: string, value: string, set: (value: string) => void) => (
    <input
      type="text"
      inputMode="decimal"
      aria-label={label}
      aria-invalid={!!valuesError}
      value={value}
      maxLength={24}
      spellCheck={false}
      onChange={(e) => set(oneNumber(e.target.value))}
    />
  );
  return (
    <>
      <label className="vc-field pp-field" htmlFor={`${id}-band`}>
        <span className="pp-label">
          Band
          <Tip text={BAND_TIP} />
        </span>
        <select id={`${id}-band`} value={band} aria-invalid={!!bandError} onChange={(e) => onChange('band', e.target.value)}>
          <option value="">— choose —</option>
          {strange && <option value={band}>{band}</option>}
          {earlier.length > 0 && (
            <optgroup label="Results">
              {earlier.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </optgroup>
          )}
          {earlier.length > 0 ? (
            <optgroup label="Data">
              {data.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </optgroup>
          ) : (
            data.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))
          )}
        </select>
        {bandError && <span className="hint-text error">{bandError}</span>}
      </label>
      <div className="vc-field pp-field" role="group" aria-labelledby={`${id}-where`}>
        <span className="pp-label" id={`${id}-where`}>
          Hide where
          {unit && <span className="pp-unit">in {unit}</span>}
          <Tip text={WHERE_TIP} />
        </span>
        <div className="pp-where">
          <select
            aria-label="Condition"
            value={condition}
            aria-invalid={!!errors.condition && (showErrors || condition !== '')}
            onChange={(e) => {
              onChange('condition', e.target.value);
              onChange('values', valuesAfterConditionChange(text, e.target.value));
            }}
          >
            <option value="">— choose —</option>
            {CONDITIONS.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
          {(condition === 'lt' || condition === 'gt') && number('Value', text, (value) => onChange('values', value))}
          {condition === 'between' && (
            <>
              {number('From', from, (value) => onChange('values', betweenText(value, to)))}
              <span className="pp-help">and</span>
              {number('To', to, (value) => onChange('values', betweenText(from, value)))}
            </>
          )}
          {condition === 'eq' && (
            <input
              type="text"
              aria-label="Values"
              aria-invalid={!!valuesError}
              placeholder="3, 8, 9"
              value={text}
              spellCheck={false}
              onChange={(e) => onChange('values', e.target.value)}
            />
          )}
        </div>
        {errors.condition && (showErrors || condition !== '') && <span className="hint-text error">{errors.condition}</span>}
        {valuesError && <span className="hint-text error">{valuesError}</span>}
      </div>
    </>
  );
}
