import { useRef, useState } from 'react';

// A name edited in place: Enter or leaving the field keeps it, Escape drops it. An empty name is the
// caller's to read (the job manager brings the default title back).
export default function InlineRename({
  value,
  label,
  maxLength,
  onSave,
  onCancel,
}: {
  value: string;
  label: string;
  maxLength: number;
  onSave: (name: string) => void;
  onCancel: () => void;
}) {
  const [text, setText] = useState(value);
  const finished = useRef(false);
  const finish = (save: boolean) => {
    if (finished.current) return;
    finished.current = true;
    if (save) onSave(text);
    else onCancel();
  };
  return (
    <input
      type="text"
      className="pm-rename"
      aria-label={label}
      value={text}
      maxLength={maxLength}
      autoFocus
      onChange={(e) => setText(e.target.value)}
      onBlur={() => finish(true)}
      onKeyDown={(e) => {
        if (e.key === 'Enter') finish(true);
        else if (e.key === 'Escape') {
          // Only the edit ends; the panel around it stays.
          e.preventDefault();
          e.stopPropagation();
          finish(false);
        }
      }}
    />
  );
}
