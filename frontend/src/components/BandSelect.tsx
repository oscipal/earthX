// The dropdown that picks one band to look at: "Show" beside the range of the preview, "Band" in the row of a result
// layer (NM4-43e PR 2, adr/0020 §10). One block for both, so that they look and answer alike.

export interface BandOption {
  value: string;
  label: string;
  // The line between two kinds of entries (the bands above it, the presets below): not a choice.
  separator?: boolean;
  // What the entry is, as the tooltip of the entry (the formula of an index).
  title?: string;
}

interface Props {
  label: string;
  value: string;
  options: readonly BandOption[];
  onChange: (value: string) => void;
  className?: string;
  title?: string;
  disabled?: boolean;
}

export default function BandSelect({ label, value, options, onChange, className = '', title, disabled }: Props) {
  return (
    <label className={`vc-field band-select ${className}`.trim()} title={title}>
      <span>{label}</span>
      <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) =>
          option.separator ? (
            <option key={option.value} value={option.value} disabled>
              ──────────
            </option>
          ) : (
            <option key={option.value} value={option.value} title={option.title}>
              {option.label}
            </option>
          ),
        )}
      </select>
    </label>
  );
}
