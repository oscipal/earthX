// The places of the settings bar (UI-03a, `Inspector.tsx`): the same head for the view of the search, the pinned view and the settings
// of a result, so that a field stands at the same height whichever is open. Row 1: title, mark, eye, red x. Row 2: the dataset and the
// time step of a view, the date of a layer. Then the sections "Display" and "Actions" (Otto, 2.11.2026).

import { useState, type KeyboardEventHandler, type ReactNode } from 'react';

import CloseButton from './CloseButton';
import { ChevronLeftIcon, ChevronRightIcon, PencilIcon } from './icons';
import InlineRename from './InlineRename';

export const ONE_IMAGE_TIP = 'A layer holds one image';

interface HeadProps {
  title: string;
  // The mark beside the title ("Temporary", the note of a result of whole numbers).
  mark?: ReactNode;
  eye?: ReactNode;
  onClose: () => void;
  // The tooltip of the x, where closing does more than close.
  closeTitle?: string;
  // "Copy original scene name" (Otto, 3.11.2026): small, at the end of row 2, in the row of the date.
  copy?: ReactNode;
  // Row 2; the row keeps its height when it is empty.
  children?: ReactNode;
  // A layer is renamed here (Otto, 2.11.2026): a click on the title or on the pencil; `name` is the name as kept, without the date
  // the title adds. `onRename` refuses an empty name.
  rename?: { name: string; onRename: (name: string) => boolean };
}

export const RENAME_TIP = 'Rename layer';
const EMPTY_NAME_TIP = 'A layer needs a name: an empty one keeps the name it had';

export function InspectorHead({ title, mark, eye, onClose, closeTitle, copy, children, rename }: HeadProps) {
  const [editing, setEditing] = useState(false);
  return (
    <div className="vc-head">
      <div className="insp-row">
        {rename && editing ? (
          <span className="vc-title vc-rename" data-tip-level="advanced" data-tip={EMPTY_NAME_TIP}>
            <InlineRename
              value={rename.name}
              label="Layer name"
              maxLength={120}
              onSave={(name) => {
                rename.onRename(name);
                setEditing(false);
              }}
              onCancel={() => setEditing(false)}
            />
          </span>
        ) : rename ? (
          <>
            <button type="button" className="vc-title vc-title-btn" onClick={() => setEditing(true)}>
              {title}
            </button>
            <button type="button" className="icon-btn sm quiet" data-tip-level="advanced" data-tip={RENAME_TIP} aria-label={RENAME_TIP} onClick={() => setEditing(true)}>
              <PencilIcon />
            </button>
          </>
        ) : (
          <span className="vc-title">
            {title}
          </span>
        )}
        {mark}
        {eye}
        <CloseButton onClick={onClose} title={closeTitle} />
      </div>
      <div className="insp-row insp-row2">
        {children}
        {copy}
      </div>
    </div>
  );
}

interface Step {
  title: string;
  disabled: boolean;
  onClick: () => void;
}

interface StepperProps {
  text: string;
  tip?: string;
  previous: Step;
  next: Step;
  onKeyDown?: KeyboardEventHandler<HTMLElement>;
  // One date and nothing to step to: the date alone, without arrows (Otto, 2.11.2026).
  single?: boolean;
}

// `< date >`. At the first or the last of several the arrow stays, locked, and says why in its tooltip.
export function Stepper({ text, tip, previous, next, onKeyDown, single = false }: StepperProps) {
  if (single) {
    return (
      <div className="vc-stepper" role="group" aria-label="Time step">
        <span className="vc-step-text" data-tip-level="advanced" data-tip={tip}>
          {text}
        </span>
      </div>
    );
  }
  return (
    <div className="vc-stepper" role="group" aria-label="Time step" onKeyDown={onKeyDown}>
      <button type="button" className="icon-btn" aria-label="Previous image" aria-disabled={previous.disabled || undefined} data-tip-level="advanced" data-tip={previous.title} onClick={previous.onClick}>
        <ChevronLeftIcon />
      </button>
      <span className="vc-step-text" data-tip-level="advanced" data-tip={tip}>
        {text}
      </span>
      <button type="button" className="icon-btn" aria-label="Next image" aria-disabled={next.disabled || undefined} data-tip-level="advanced" data-tip={next.title} onClick={next.onClick}>
        <ChevronRightIcon />
      </button>
    </div>
  );
}

const NOTHING = () => undefined;

// The date of a layer in the place of the time step of a view: a layer holds one image, so no arrows.
export function LayerStepper({ date }: { date?: string }) {
  const locked = { title: ONE_IMAGE_TIP, disabled: true, onClick: NOTHING };
  return <Stepper text={date ?? ''} tip={date} previous={locked} next={locked} single />;
}

export function InspectorSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="insp-section">
      <h3 className="insp-heading">{title}</h3>
      {children}
    </section>
  );
}
