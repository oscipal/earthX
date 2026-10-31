// The fields that say how a picture is drawn, in one order and under one set of names wherever they appear: the view of
// scenes, the settings of a result layer and the preview of the processing panel (NM4-65 part 6, Otto, 31.10.2026):
// Band · Index · vmin · vmax · colormap. A field a place does not offer is left out, the others keep their order. The
// block is a fragment, so that each place keeps its own layout around it.

import { useId, type ReactNode } from 'react';

import { UNIT_LABELS, UNIT_TIP, type RangeUnit } from '../percentRange';
import { COLORMAPS } from '../render';
import BandSelect, { type BandOption } from './BandSelect';

export interface IndexOption {
  name: string;
  tip: string;
}

interface Props {
  // The band the picture shows; left out where the place has only one.
  band?: { value: string; options: readonly BandOption[]; onChange: (value: string) => void; title?: string; className?: string; disabled?: boolean };
  // The index a dataset offers in place of a band; left out where there is none.
  index?: { value: string; options: readonly IndexOption[]; tip: string; onChange: (name: string | null) => void };
  vmin: { value: string; onChange: (value: string) => void };
  vmax: { value: string; onChange: (value: string) => void; after?: ReactNode };
  // A colormap to pick, or a fixed one-entry box (a picture of three bands is "RGB"); left out with `null`.
  colormap: { value: string; onChange: (value: string) => void } | { fixed: string; title: string } | null;
  // What the empty ends of the range say.
  placeholder?: string;
  // The switch "value / %" of the range (NM4-65 part 4): with "%" the two fields hold percentiles. Left out where a place has
  // no statistics to read them from.
  unit?: { value: RangeUnit; onChange: (unit: RangeUnit) => void };
}

export default function RenderFields({ band, index, vmin, vmax, colormap, placeholder, unit }: Props) {
  const percent = unit?.value === 'percent';
  const hint = percent ? undefined : placeholder;
  return (
    <>
      {band && <BandSelect label="Band" {...band} />}
      {index && (
        <label className="vc-field" title={index.tip}>
          <span>Index</span>
          <select value={index.value} onChange={(e) => index.onChange(e.target.value || null)}>
            <option value="">— none —</option>
            {index.options.map((option) => (
              <option key={option.name} value={option.name} title={option.tip}>
                {option.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="vc-field vc-num">
        <span>vmin</span>
        <input type="number" value={vmin.value} placeholder={hint} {...(percent ? PERCENT_INPUT : {})} onChange={(e) => vmin.onChange(e.target.value)} />
      </label>
      {vmax.after ? (
        <div className="pp-bound">
          <VmaxField vmax={vmax} placeholder={hint} percent={percent} unit={unit} />
          {vmax.after}
        </div>
      ) : (
        <VmaxField vmax={vmax} placeholder={hint} percent={percent} unit={unit} />
      )}
      {colormap && (
        <label className="vc-field">
          <span>Colormap</span>
          {'fixed' in colormap ? (
            <select value="" title={colormap.title} onChange={() => undefined}>
              <option value="">{colormap.fixed}</option>
            </select>
          ) : (
            <select value={colormap.value} onChange={(e) => colormap.onChange(e.target.value)}>
              <option value="">— none —</option>
              {COLORMAPS.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          )}
        </label>
      )}
    </>
  );
}

// Whole percents: the arrows of the field step by one, and the browser keeps it to 0…100.
const PERCENT_INPUT = { min: 0, max: 100, step: 1 };

// The field "vmax" carries the switch of the range in its label line, to the right of the word and no further right than the
// field itself (Otto, 1.11.2026).
function VmaxField({ vmax, placeholder, percent, unit }: { vmax: Props['vmax']; placeholder?: string; percent: boolean; unit: Props['unit'] }) {
  const nameId = useId();
  return (
    <label className="vc-field vc-num">
      <span id={nameId}>vmax</span>
      <input type="number" aria-labelledby={nameId} value={vmax.value} placeholder={placeholder} {...(percent ? PERCENT_INPUT : {})} onChange={(e) => vmax.onChange(e.target.value)} />
      {unit && (
        // After the field, so that the label names the field and not the switch; the style puts it in the line of the label.
        <select className="vc-unit" aria-label="Range unit" title={UNIT_TIP} value={unit.value} onChange={(e) => unit.onChange(e.target.value as RangeUnit)}>
          <option value="value">{UNIT_LABELS.value}</option>
          <option value="percent">{UNIT_LABELS.percent}</option>
        </select>
      )}
    </label>
  );
}
