// The small line under the title of a view or a layer (Otto, 3.11.2026, zu #282): a click copies the names of its original scenes.
// "Copied" says it was done for a moment. Without scenes there is no line.

import { useEffect, useRef, useState } from 'react';

import { COPIED_LABEL, COPY_FAILED_LABEL, COPY_LABEL, copyNames, copyTip } from '../sceneNames';

const SHOWN_MS = 1500;

export default function CopySceneNames({ names, write }: { names: readonly string[]; write?: (text: string) => Promise<void> }) {
  const [done, setDone] = useState<'copied' | 'failed' | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);
  const count = new Set(names).size;
  if (count === 0) return null;
  const click = async () => {
    const ok = await copyNames(names, write);
    setDone(ok ? 'copied' : 'failed');
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setDone(null), SHOWN_MS);
  };
  return (
    <button type="button" className="vc-scene-names" data-tip-level="advanced" data-tip={copyTip(count)} onClick={() => void click()}>
      {done === 'copied' ? COPIED_LABEL : done === 'failed' ? COPY_FAILED_LABEL : COPY_LABEL}
    </button>
  );
}
