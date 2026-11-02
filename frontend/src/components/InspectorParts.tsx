// The places of the settings bar (UI-03a, `Inspector.tsx`): the same head for the view of the search, the pinned view and the settings
// of a result, so that a field stands at the same height whichever is open. Row 1: title, mark, eye, red x. Row 2: the dataset and the
// time step of a view, the date of a layer. Then the sections "Display" and "Actions" (Otto, 2.11.2026).

import type { KeyboardEventHandler, ReactNode } from 'react';

import Chevron from './Chevron';
import CloseButton from './CloseButton';

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
  // Row 2; the row keeps its height when it is empty.
  children?: ReactNode;
}

export function InspectorHead({ title, tip, mark, eye, onClose, closeTitle, children }: HeadProps) {
  return (
    <div className="vc-head">
      <div className="insp-row">
        <span className="vc-title" title={tip}>
          {title}
        </span>
        {mark}
        {eye}
        <CloseButton onClick={onClose} title={closeTitle} />
      </div>
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
}

// `‹ date ›`. Where there is no step the arrows stay, locked, and say why in their tooltip.
export function Stepper({ text, tip, previous, next, onKeyDown }: StepperProps) {
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

// The date of a layer in the place of the time step of a view.
export function LayerStepper({ date }: { date?: string }) {
  const locked = { title: ONE_IMAGE_TIP, disabled: true, onClick: NOTHING };
  return <Stepper text={date ?? ''} tip={date} previous={locked} next={locked} />;
}

export function InspectorSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="insp-section">
      <h3 className="insp-heading">{title}</h3>
      {children}
    </section>
  );
}
