// The icon "Settings" of the rail at the left (UI-04 part 4, Otto, 3.11.2026): "Settings 6 Line" of MingCute, the one icon of the
// interface that does not come from Lucide (`docs/ui/leitfaden.md` §3).
//
// Source:  MingCute Icon, npm package `mingcute_icon` 2.9.72, file `svg/system/settings_6_line.svg`,
//          repository https://github.com/Richard9394/MingCute, licence Apache-2.0 (text and origin in `frontend/THIRD_PARTY_NOTICES.md`).
// CHANGED: This is not the original file (Apache-2.0 §4(b)). The original is a filled shape with lines of 2 px on a 24 px grid; so that the
//          stroke and the size fit the Lucide icons next to it (1.5 px at every size, round ends), it is redrawn as strokes on the same
//          24 px grid with the same geometry: three lines, the knobs at x = 16, 8 and 16 on the rows y = 5, 12 and 19, each knob a ring
//          that breaks its line. Nothing but the geometry is taken from the original.

// The shape `createLucideIcon` takes (`icons.ts` hands it on; only that file imports `lucide-react`).
type Part = [element: 'path' | 'circle', attributes: Record<string, string>];

const KNOB = 2.25;

// One row: a line from x = 4 to x = 20 with a ring at `at` that interrupts it.
const row = (y: number, at: number): Part[] => [
  ['path', { d: `M4 ${y}H${at - KNOB}` }],
  ['circle', { cx: String(at), cy: String(y), r: String(KNOB) }],
  ['path', { d: `M${at + KNOB} ${y}H20` }],
];

export const SETTINGS_ICON_NODE: Part[] = [...row(5, 16), ...row(12, 8), ...row(19, 16)];
