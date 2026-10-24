import { useState, type MouseEvent } from 'react';

// Two overlapping rounded rectangles — the same copy glyph Claude's own
// interface uses, in place of the earlier "⧉" character glyph, which
// rendered inconsistently and didn't read as "copy" at a glance (V-6).
// `currentColor` so `.copy-btn`'s own color (and its `:hover` accent) still
// drive it.
function CopyIcon({ copied }: { copied: boolean }) {
  if (copied) {
    return (
      <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M20 6 9 17l-5-5" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="9" y="9" width="13" height="13" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

// The copy button of the results list (V-6) and of the link under "Share" (M4-19e): the text goes to
// the clipboard and the glyph turns into a tick for a moment.
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
    <button type="button" className="copy-btn" title={title} aria-label={label} onClick={copy}>
      <CopyIcon copied={copied} />
    </button>
  );
}
