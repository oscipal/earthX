// A text field with a small "×" at its right edge that empties it (Otto,
// 30.09.2026). The "×" shows only while there is something to delete and hands
// the focus back to the field.

import { useRef, type InputHTMLAttributes } from 'react';

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange' | 'type'> & {
  value: string;
  onChange: (value: string) => void;
  // What else goes with the text (e.g. a list of results for it).
  onClear?: () => void;
  clearLabel: string;
};

export default function ClearableInput({ value, onChange, onClear, clearLabel, className, ...input }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <span className={`clearable${className ? ` ${className}` : ''}`}>
      <input ref={ref} type="text" value={value} onChange={(e) => onChange(e.target.value)} {...input} />
      {value !== '' && !input.disabled && (
        <button
          type="button"
          className="clear-btn"
          aria-label={clearLabel}
          title={clearLabel}
          onClick={() => {
            onChange('');
            onClear?.();
            ref.current?.focus();
          }}
        >
          ×
        </button>
      )}
    </span>
  );
}
