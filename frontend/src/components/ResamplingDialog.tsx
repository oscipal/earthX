// The warning to confirm before a job whose bands are brought to a common grid (NM4-65 part 7): what is resampled to which grid,
// by which method, and what that means for the values. "Continue" starts the job, "Cancel" (or Escape, or a click beside) does
// not. The facts are the server's, from the estimate of the order (`resamplingWarning.ts`).

import { useEffect, useRef } from 'react';

import { describeResampling, type ResamplingPart } from '../resamplingWarning';

export const RESAMPLING_TITLE = 'Values are resampled';

interface Props {
  parts: readonly ResamplingPart[];
  onContinue: () => void;
  onCancel: () => void;
}

export default function ResamplingDialog({ parts, onContinue, onCancel }: Props) {
  const cancel = useRef<HTMLButtonElement>(null);
  const proceed = useRef<HTMLButtonElement>(null);
  // The safe answer has the focus: a slip of the Enter key does not start the job.
  useEffect(() => cancel.current?.focus(), []);
  const texts = parts.map(describeResampling);
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onCancel();
    } else if (event.key === 'Tab') {
      // Two buttons: the focus stays between them.
      const next = document.activeElement === cancel.current ? proceed.current : cancel.current;
      event.preventDefault();
      next?.focus();
    }
  };

  return (
    <div className="dialog-backdrop" onClick={onCancel}>
      <div
        className="panel dialog-panel resampling-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="resampling-title"
        aria-describedby="resampling-body"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="results-head">
          <h2 id="resampling-title">{RESAMPLING_TITLE}</h2>
        </div>
        <div className="dialog-body" id="resampling-body">
          {texts.map((text, index) => (
            <div key={index} className="resampling-part">
              {text.label && <p className="resampling-label">{text.label}</p>}
              <p>{text.grid}</p>
              {text.bands && <p>{text.bands}</p>}
              {text.scenes && <p>{text.scenes}</p>}
              <p className="hint-text">{text.meaning}</p>
            </div>
          ))}
        </div>
        <div className="dialog-actions">
          <button type="button" className="lm-btn" ref={cancel} onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="lm-btn primary" ref={proceed} onClick={onContinue}>
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
