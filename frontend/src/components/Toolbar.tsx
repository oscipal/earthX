import type { ReactNode } from 'react';

import { useAppStore } from '../store';
import type { ToolMode } from '../types';
import { MapPinIcon, PentagonIcon, SquareIcon, TrashIcon } from './icons';

const TOOLS: { mode: ToolMode; label: string; hint: string; icon: ReactNode }[] = [
  { mode: 'point', label: 'Point', hint: 'Click the map to drop a point (auto-buffered to a small box)', icon: <MapPinIcon /> },
  { mode: 'rectangle', label: 'Rectangle', hint: 'Click-drag to draw a bounding box', icon: <SquareIcon /> },
  { mode: 'polygon', label: 'Polygon', hint: 'Click to add vertices, double-click to finish', icon: <PentagonIcon /> },
];

export default function Toolbar() {
  const toolMode = useAppStore((s) => s.toolMode);
  const setToolMode = useAppStore((s) => s.setToolMode);
  const aoi = useAppStore((s) => s.aoi);
  const clearAoi = useAppStore((s) => s.clearAoi);

  return (
    <div className="toolbar" role="group" aria-label="Area of interest tools">
      {TOOLS.map((t) => (
        <button
          key={t.mode}
          type="button"
          className="btn tool-btn"
          data-tip={t.hint}
          aria-pressed={toolMode === t.mode}
          onClick={() => setToolMode(toolMode === t.mode ? 'none' : t.mode)}
        >
          {t.icon}
          <span>{t.label}</span>
        </button>
      ))}
      <button
        type="button"
        className="btn tool-wide"
        data-tip={aoi ? 'Clear the AOI' : 'No AOI to clear'}
        aria-label="Clear AOI"
        disabled={!aoi}
        onClick={() => {
          clearAoi();
          setToolMode('none');
        }}
      >
        <TrashIcon />
        <span>Clear AOI</span>
      </button>
    </div>
  );
}
