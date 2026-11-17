// A round dial for an angle from north (M5-14, Otto, 17.11.2026): the direction of the light of a hillshade, set as in QGIS. North is up, the
// angle grows clockwise; drag around the circle, or use the keys (arrows ±1°, with Shift ±15°); the value stands beside it in degrees. The one
// drawing of its own besides the histogram and the needle of the compass (`docs/ui/leitfaden.md` §3, third exception); its colours are
// tokens, so it follows the light and the dark theme.

import { useRef } from 'react';

import { angleAfterKey, angleAt } from '../paramControls';

const SIZE = 40;
const CENTRE = SIZE / 2;
const RADIUS = CENTRE - 3;

export default function AngleDial({
  value,
  label,
  tip,
  onChange,
  beside,
}: {
  value: number;
  label: string;
  tip?: string;
  onChange: (angle: number) => void;
  // What stands beside the dial instead of its value in degrees (a field to type it, `PresetParamControls`).
  beside?: React.ReactNode;
}) {
  const ref = useRef<SVGSVGElement>(null);
  const dragging = useRef(false);
  const angle = ((value % 360) + 360) % 360;
  const set = (event: React.PointerEvent<SVGSVGElement>) => {
    const box = ref.current?.getBoundingClientRect();
    if (!box) return;
    const next = angleAt(event.clientX - (box.left + box.width / 2), event.clientY - (box.top + box.height / 2));
    if (next !== angle) onChange(next);
  };
  const radians = (angle * Math.PI) / 180;
  const tipX = CENTRE + RADIUS * Math.sin(radians);
  const tipY = CENTRE - RADIUS * Math.cos(radians);
  return (
    <span className="angle-dial" data-tip-level="advanced" data-tip={tip}>
      <svg
        ref={ref}
        className="angle-dial-face"
        width={SIZE}
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        role="slider"
        tabIndex={0}
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={359}
        aria-valuenow={Math.round(angle)}
        aria-valuetext={`${Math.round(angle)}°`}
        onPointerDown={(event) => {
          dragging.current = true;
          event.currentTarget.setPointerCapture?.(event.pointerId);
          set(event);
        }}
        onPointerMove={(event) => {
          if (dragging.current) set(event);
        }}
        onPointerUp={(event) => {
          dragging.current = false;
          event.currentTarget.releasePointerCapture?.(event.pointerId);
        }}
        onPointerCancel={() => {
          dragging.current = false;
        }}
        onKeyDown={(event) => {
          const next = angleAfterKey(angle, event.key, event.shiftKey);
          if (next === null) return;
          event.preventDefault();
          onChange(next);
        }}
      >
        <circle className="angle-dial-ring" cx={CENTRE} cy={CENTRE} r={RADIUS} />
        <line className="angle-dial-north" x1={CENTRE} y1={CENTRE - RADIUS} x2={CENTRE} y2={CENTRE - RADIUS + 5} />
        <line className="angle-dial-hand" x1={CENTRE} y1={CENTRE} x2={tipX} y2={tipY} />
        <circle className="angle-dial-knob" cx={tipX} cy={tipY} r={3} />
      </svg>
      {beside ?? <span className="angle-dial-value">{Math.round(angle)}°</span>}
    </span>
  );
}
