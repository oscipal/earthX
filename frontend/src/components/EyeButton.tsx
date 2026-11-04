// The eye: the one button that shows or hides something (layer, image, search results). One component, one colour (the text's), and what is
// hidden is the eye crossed out, not another colour (UI-04 part 3a, Otto, 4.11.2026). A hidden or locked thing shows `EyeOffIcon`.

import { EyeIcon, EyeOffIcon } from './icons';

interface Props {
  // Whether the thing is shown now; the tooltip says what a click does.
  shown: boolean;
  tip: string;
  onToggle: () => void;
  // In a row of a list: 22 px and a 14 px icon, as the other buttons of the row.
  row?: boolean;
  // Cannot be switched (a result of a deleted job): stays where it is, and the tip says why.
  locked?: boolean;
  // The place of the button in a row of the layer manager (`data-col`).
  col?: string;
}

export default function EyeButton({ shown, tip, onToggle, row = false, locked = false, col }: Props) {
  return (
    <button
      type="button"
      className={`icon-btn eye${row ? ' sm' : ''}`}
      data-col={col}
      data-tip={tip}
      aria-label={tip}
      aria-pressed={locked ? undefined : shown}
      aria-disabled={locked || undefined}
      onClick={() => {
        if (!locked) onToggle();
      }}
    >
      {shown && !locked ? <EyeIcon size={row ? 14 : 16} /> : <EyeOffIcon size={row ? 14 : 16} />}
    </button>
  );
}
