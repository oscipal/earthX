// A reason or an explanation as a tooltip (UI-01 §4, "wenig Text"): it shows on hover and on keyboard
// focus, and a screen reader reads it as the name of the symbol. Plain `title` shows on hover only.

export default function Tip({ text, symbol = 'ⓘ', tone }: { text: string; symbol?: string; tone?: 'warn' }) {
  return (
    <span className={`tip${tone ? ` ${tone}` : ''}`} role="img" tabIndex={0} aria-label={text} data-tip={text}>
      {symbol}
    </span>
  );
}
