// The field "Colormap" of a layer of classes (M5-62, F3 and F8): the button "Classes" opens the legend over the map, one line per class
// with its colour and name, as the tiles draw them; it lies left of the settings bar where there is room. Nothing but the classes, and
// nothing in the panel that could make it scroll.

import { useRef, useState } from 'react';

import type { BandClass } from '../bandClasses';
import Popover from './Popover';

export const CLASSES = 'Classes';

export default function ClassesField({ classes, title }: { classes: readonly BandClass[]; title: string }) {
  const anchor = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  return (
    <div className="vc-field">
      <span>Colormap</span>
      <button
        ref={anchor}
        type="button"
        className="btn vc-classes"
        aria-haspopup="dialog"
        aria-expanded={open}
        data-tip-level="advanced"
        data-tip={title}
        onClick={() => setOpen((was) => !was)}
      >
        {CLASSES}
      </button>
      <Popover anchorRef={anchor} open={open} onClose={() => setOpen(false)} className="classes-popup" role="dialog" ariaLabel={CLASSES} beside>
        <ul className="classes-legend">
          {classes.map((entry) => (
            <li key={entry.value}>
              <span className="class-swatch" style={{ background: entry.colour }} aria-hidden="true" />
              {entry.name}
            </li>
          ))}
        </ul>
      </Popover>
    </div>
  );
}
