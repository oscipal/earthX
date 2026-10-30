import { useCallback, useRef, useState, type ReactNode } from 'react';

import Popover from './Popover';

export interface DatasetChoice {
  id: string;
  // What the box and the entry of the list show for the dataset.
  content: ReactNode;
}

// The box that names one dataset and opens a list of the others to switch (Otto, 30.09.2026): the dataset whose
// scenes the results show ("Showing dataset", `ResultsPanel`), and the dataset whose filters "Advanced search" shows
// (DS-02c) — one component for both, so that they look and work the same way: the button opens a `Popover` as
// `listbox`, `ArrowDown` opens it, a choice gives the focus back to the button. With one dataset the box is not
// a button to open anything. The list lies over what is below it.
export default function DatasetSelect({
  label,
  labelId,
  listLabel,
  choices,
  shownId,
  onChoose,
  className,
}: {
  label: string;
  // The id of the label, which names the box; one per instance on a page.
  labelId: string;
  // The name of the list, for the screen reader.
  listLabel: string;
  choices: DatasetChoice[];
  shownId: string;
  onChoose: (id: string) => void;
  className?: string;
}) {
  const [listOpen, setListOpen] = useState(false);
  const boxRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setListOpen(false), []);
  const shown = choices.find((choice) => choice.id === shownId) ?? choices[0];

  if (!shown) return null;
  const several = choices.length > 1;
  return (
    <div className={`dataset-select${className ? ` ${className}` : ''}`}>
      <span className="eyebrow" id={labelId}>
        {label}
      </span>
      <button
        ref={boxRef}
        type="button"
        className="dataset-select-box"
        aria-haspopup={several ? 'listbox' : undefined}
        aria-expanded={several ? listOpen : undefined}
        aria-labelledby={labelId}
        disabled={!several}
        onClick={() => setListOpen((v) => !v)}
        onKeyDown={(e) => {
          if (several && e.key === 'ArrowDown') {
            e.preventDefault();
            setListOpen(true);
          }
        }}
      >
        {shown.content}
        {several && <span className="rg-caret">{listOpen ? '▴' : '▾'}</span>}
      </button>
      <Popover
        anchorRef={boxRef}
        open={several && listOpen}
        onClose={close}
        className="dataset-select-list"
        role="listbox"
        ariaLabel={listLabel}
        focusOnOpen
      >
        {choices.map((choice) => (
          <button
            key={choice.id}
            type="button"
            role="option"
            aria-selected={choice.id === shown.id}
            className={`dataset-select-option${choice.id === shown.id ? ' selected' : ''}`}
            onClick={() => {
              onChoose(choice.id);
              setListOpen(false);
              boxRef.current?.focus();
            }}
          >
            {choice.content}
          </button>
        ))}
      </Popover>
    </div>
  );
}
