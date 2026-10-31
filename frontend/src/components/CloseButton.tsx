// The one way to close a panel, a pop-up or a window: a small red "x" with the tooltip "Close" (NM4-65 part 8, Otto,
// 31.10.2026: "consistency!!"). What removes something (a layer, a step, a link) or empties a list is no close and keeps
// its own button.

interface Props {
  onClick: () => void;
  // More than "Close", where closing has a consequence the person should know.
  title?: string;
  className?: string;
}

export default function CloseButton({ onClick, title = 'Close', className = '' }: Props) {
  return (
    <button type="button" className={`close-x ${className}`.trim()} title={title} aria-label="Close" onClick={onClick}>
      <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true" focusable="false">
        <path d="M1.5 1.5l7 7M8.5 1.5l-7 7" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    </button>
  );
}
