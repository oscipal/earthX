// The places of the settings bar (UI-03a, `Inspector.tsx`): the same head for the view of the search, the pinned view and the settings
// of a result, so that a field stands at the same height whichever is open. Row 1: title, mark, eye, red x. Row 2: the dataset and the
// time step of a view, the date of a layer. Then the sections "Display" and "Actions" (Otto, 2.11.2026).

import { useState, type KeyboardEventHandler, type ReactNode } from 'react';

import Chevron from './Chevron';
import CloseButton from './CloseButton';
import { PencilIcon } from './Icons';
import InlineRename from './InlineRename';

export const ONE_IMAGE_TIP = 'A layer holds one image';

interface HeadProps {
  title: string;
  // The title in full, where the line cuts it short.
  tip: string;
  // The mark beside the title ("Temporary", the note of a result of whole numbers).
  mark?: ReactNode;
  eye?: ReactNode;
  onClose: () => void;
  // The tooltip of the x, where closing does more than close.
  closeTitle?: string;
  // Small under the title, before row 2: "Copy original scene name" (Otto, 3.11.2026); no row without it.
  copy?: ReactNode;
  // Row 2; the row keeps its height when it is empty.
  children?: ReactNode;
  // A layer is renamed here (Otto, 2.11.2026): a click on the title or on the pencil; `name` is the name as kept, without the date
  // the title adds. `onRename` refuses an empty name.
  rename?: { name: string; onRename: (name: string) => boolean };
}

export const RENAME_TIP = 'Rename layer';
const EMPTY_NAME_TIP = 'A layer needs a name: an empty one keeps the name it had';

export function InspectorHead({ title, tip, mark, eye, onClose, closeTitle, copy, children, rename }: HeadProps) {
  const [editing, setEditing] = useState(false);
  return (
    <div className="vc-head">
      <div className="insp-row">
        {rename && editing ? (
          <span className="vc-title vc-rename" title={EMPTY_NAME_TIP}>
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
            <button type="button" className="vc-title vc-title-btn" title={tip} onClick={() => setEditing(true)}>
              {title}
            </button>
            <button type="button" className="vc-pencil" title={RENAME_TIP} aria-label={RENAME_TIP} onClick={() => setEditing(true)}>
              <PencilIcon />
            </button>
          </>
        ) : (
          <span className="vc-title" title={tip}>
            {title}
          </span>
        )}
        {mark}
        {eye}
        <CloseButton onClick={onClose} title={closeTitle} />
      </div>
      {copy}
      <div className="insp-row insp-row2">{children}</div>
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

// `‹ date ›`. At the first or the last of several the arrow stays, locked, and says why in its tooltip.
export function Stepper({ text, tip, previous, next, onKeyDown, single = false }: StepperProps) {
  if (single) {
    return (
      <div className="vc-stepper" role="group" aria-label="Time step">
        <span className="vc-step-text" title={tip}>
          {text}
        </span>
      </div>
    );
  }
  return (
    <div className="vc-stepper" role="group" aria-label="Time step" onKeyDown={onKeyDown}>
      <button type="button" className="vc-step" aria-label="Previous image" aria-disabled={previous.disabled || undefined} title={previous.title} onClick={previous.onClick}>
        <Chevron direction="left" />
      </button>
      <span className="vc-step-text" title={tip}>
        {text}
      </span>
      <button type="button" className="vc-step" aria-label="Next image" aria-disabled={next.disabled || undefined} title={next.title} onClick={next.onClick}>
        <Chevron direction="right" />
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
