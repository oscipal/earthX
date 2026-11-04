// A reason or an explanation as a tooltip (UI-01 §4, "wenig Text"): it shows on hover and on keyboard
// focus, and a screen reader reads it as the name of the symbol. It is the (i) beside a text; a tooltip on a control is its `data-tip`.

import { InfoIcon, WarningIcon } from './icons';

// "warn" draws the warning, otherwise the (i).
export default function Tip({ text, tone }: { text: string; tone?: 'warn' }) {
  return (
    <span className={`tip${tone ? ` ${tone}` : ''}`} role="img" tabIndex={0} aria-label={text} data-tip={text}>
      {tone === 'warn' ? <WarningIcon /> : <InfoIcon />}
    </span>
  );
}
