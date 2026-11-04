import { useState, type MouseEvent } from 'react';

import { CheckIcon, CopyIcon } from './icons';

// The copy button of the results list (V-6) and of the link under "Share" (M4-19e): the text goes to
// the clipboard and the icon turns into a tick for a moment.
export default function CopyButton({ text, title, label }: { text: string; title: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const copy = (e: MouseEvent) => {
    e.stopPropagation();
    navigator.clipboard
      .writeText(text)
      .then(() => {
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1200);
      })
      .catch(() => {
        // Clipboard unavailable (no permission, insecure context) — the text
        // stays visible to select and copy by hand.
      });
  };

  return (
    <button type="button" className="icon-btn sm quiet" data-tip={title} aria-label={label} onClick={copy}>
      {copied ? <CheckIcon /> : <CopyIcon />}
    </button>
  );
}
