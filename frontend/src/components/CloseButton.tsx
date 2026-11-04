// The one way to close a panel, a pop-up or a window: a small red "x" with the tooltip "Close" (NM4-65 part 8, Otto,
// 31.10.2026: "consistency!!"). What removes something (a layer, a step, a link) or empties a list is no close and keeps
// its own button.

import { XIcon } from './icons';

interface Props {
  onClick: () => void;
  // More than "Close", where closing has a consequence the person should know.
  title?: string;
  className?: string;
}

export default function CloseButton({ onClick, title = 'Close', className = '' }: Props) {
  return (
    <button type="button" className={`close-x ${className}`.trim()} title={title} aria-label="Close" onClick={onClick}>
      <XIcon size={14} />
    </button>
  );
}
