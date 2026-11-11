// The dropdown that picks one band to look at: "Show" beside the range of the preview, "Band" in the row of a result
// layer (NM4-43e PR 2, adr/0020 §10). One block for both, so that they look and answer alike.

export interface BandOption {
  value: string;
  label: string;
  // The line between two kinds of entries (the bands above it, the presets below): not a choice.
  separator?: boolean;
  // What the entry is, as the tooltip of the entry (the formula of an index).
  title?: string;
  // Shown, not to be picked: the index of "Quick processing" while it is drawn (UI-03d).
  disabled?: boolean;
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
    // Locked, the tooltip is the reason and shows in both steps (`tipLevel.ts`): the label is not the locked field, so it says so itself.
    <label className={`vc-field band-select ${className}`.trim()} data-tip-level={disabled ? undefined : 'advanced'} data-tip={title}>
      <span>{label}</span>
      <select value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        {options.map((option) =>
          option.separator ? (
            <option key={option.value} value={option.value} disabled>
              ──────────
            </option>
          ) : (
            <option key={option.value} value={option.value} title={option.title} disabled={option.disabled}>
              {option.label}
            </option>
          ),
        )}
      </select>
    </label>
  );
}
