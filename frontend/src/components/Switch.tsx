// The switch (UI-04 part 4, Otto, 4.11.2026): for something that is on or off, and nothing else — a choice of one of several is a row of segment
// buttons (`.btn.seg`), and a thing that can be on beside others is a button that is pressed (`aria-pressed`). A switch has a name for
// a screen reader (`aria-label`) and says what it does in a tooltip; `on` is the right-hand position.

interface Props {
  on: boolean;
  onChange: (on: boolean) => void;
  // The name of the switch for a screen reader: what is on when it is on ("Advanced tooltips").
  label: string;
  tip?: string;
}

export default function Switch({ on, onChange, label, tip }: Props) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={on}
      aria-label={label}
      data-tip-level={tip ? 'advanced' : undefined}
      data-tip={tip}
      onClick={() => onChange(!on)}
    >
      <span className="switch-thumb" aria-hidden="true" />
    </button>
  );
}
