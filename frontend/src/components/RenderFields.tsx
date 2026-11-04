// The fields that say how a picture is drawn, in one order and under one set of names wherever they appear: the view of
// scenes, the settings of a result layer and the preview of the processing panel (NM4-65 part 6, Otto, 31.10.2026):
// Band · Index · vmin · vmax · colormap. A field a place does not offer is left out, the others keep their order. The
// block is a fragment, so that each place keeps its own layout around it.

import { Fragment, useId, type ReactNode } from 'react';

import { CHANNEL_NAMES, type ChannelRange } from '../channels';

import { UNIT_LABELS, UNIT_TIP, type RangeUnit } from '../percentRange';
import BandSelect, { type BandOption } from './BandSelect';
import ColormapField from './ColormapField';

// What the box of the colormap says where a picture of three bands has none: it stays in its place, locked, and says "none" (Otto, 1.11.2026).
export const NO_COLORMAP = '— none —';

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
  // The settings bar (Otto, 2.11.2026): vmin and vmax side by side in one row "Scale", the switch of the range after them.
  scale?: boolean;
  // A colour picture (UI-03d): a row of vmin and vmax for each channel in place of the one. With `onUnit` every row has its own switch
  // "absolute / percentile" and shows the pair of its channel where that one is in percentiles (UI-03e); without it the one switch of
  // the range stands in the first row, and the rows are those of values.
  channels?: {
    values: readonly ChannelRange[];
    onChange: (channel: number, end: 'vmin' | 'vmax', text: string) => void;
    onPercent?: (channel: number, end: 'low' | 'high', text: string) => void;
    onUnit?: (channel: number, unit: RangeUnit) => void;
  };
  // What stands under the fields of "Scale": the histograms with their sliders.
  histograms?: ReactNode;
}

export default function RenderFields({ band, index, vmin, vmax, colormap, placeholder, unit, scale = false, channels, histograms }: Props) {
  const percent = unit?.value === 'percent';
  const hint = percent ? undefined : placeholder;
  const range = scale ? (
    <ScaleRow vmin={vmin} vmax={vmax} placeholder={hint} percent={percent} unit={unit} channels={channels?.onUnit || !percent ? channels : undefined} below={histograms} />
  ) : (
    <>
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
    </>
  );
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
      {range}
      {colormap &&
        ('fixed' in colormap ? (
          // Not left out: the field keeps its place whatever band is drawn, locked, and its tooltip says why (NM4-54 part 5).
          <label className="vc-field" title={colormap.title}>
            <span>Colormap</span>
            <select value="" disabled aria-label="Colormap" title={colormap.title} onChange={() => undefined}>
              <option value="">{colormap.fixed}</option>
            </select>
          </label>
        ) : (
          // One field wherever a colormap is chosen, with "More…" and "Reverse" (UI-03d).
          <ColormapField value={colormap.value} onChange={colormap.onChange} />
        ))}
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

function UnitSelect({ unit, label = 'Range unit' }: { unit: NonNullable<Props['unit']>; label?: string }) {
  return (
    <select className="vc-unit" aria-label={label} title={UNIT_TIP} value={unit.value} onChange={(e) => unit.onChange(e.target.value as RangeUnit)}>
      <option value="value">{UNIT_LABELS.value}</option>
      <option value="percent">{UNIT_LABELS.percent}</option>
    </select>
  );
}

function NumberField({ name, value, placeholder, percent, onChange }: { name: string; value: string; placeholder?: string; percent: boolean; onChange: (value: string) => void }) {
  const short = name.split(' ').pop() ?? name;
  return (
    <label className="vc-field vc-num" title={placeholder ? `${name}; empty: ${placeholder}` : name}>
      <span className="sr-only">{name}</span>
      <input type="number" value={value} placeholder={short} {...(percent ? PERCENT_INPUT : {})} onChange={(e) => onChange(e.target.value)} />
    </label>
  );
}

// One row "Scale": vmin and vmax side by side, each with its name as placeholder and as a label for a screen reader, and the switch of
// the range after them, not over a field (Otto, 2.11.2026). An empty field is measured; its tooltip says so. A colour picture in
// values has a row for each channel, the switch in the first (UI-03d); the histograms stand under the fields.
function ScaleRow({ vmin, vmax, placeholder, percent, unit, channels, below }: { vmin: Props['vmin']; vmax: Props['vmax']; placeholder?: string; percent: boolean; unit: Props['unit']; channels?: Props['channels']; below?: ReactNode }) {
  const nameId = useId();
  return (
    <div className="vc-field vc-scale" role="group" aria-labelledby={nameId}>
      <span id={nameId}>Scale</span>
      <div className="vc-scale-body">
        {channels ? (
          <div className="vc-scale-fields vc-channels">
            {CHANNEL_NAMES.map((channel, index) => {
              const own = channels.values[index];
              const typed = channels.onUnit && own?.percent ? own.percent : null;
              return (
                <Fragment key={channel}>
                  <span className={`vc-chip vc-chip-${channel}`} title={channel}>
                    {channel[0].toUpperCase()}
                  </span>
                  <NumberField
                    name={`${channel} ${typed ? 'low percentile' : 'vmin'}`}
                    value={typed ? typed.low : (own?.vmin ?? vmin.value)}
                    placeholder={typed ? undefined : placeholder}
                    percent={typed !== null}
                    onChange={(text) => (typed ? channels.onPercent?.(index, 'low', text) : channels.onChange(index, 'vmin', text))}
                  />
                  <NumberField
                    name={`${channel} ${typed ? 'high percentile' : 'vmax'}`}
                    value={typed ? typed.high : (own?.vmax ?? vmax.value)}
                    placeholder={typed ? undefined : placeholder}
                    percent={typed !== null}
                    onChange={(text) => (typed ? channels.onPercent?.(index, 'high', text) : channels.onChange(index, 'vmax', text))}
                  />
                  {channels.onUnit ? (
                    <UnitSelect label={`${channel} range unit`} unit={{ value: typed ? 'percent' : 'value', onChange: (next) => channels.onUnit?.(index, next) }} />
                  ) : index === 0 && unit ? (
                    <UnitSelect unit={unit} />
                  ) : (
                    <span />
                  )}
                </Fragment>
              );
            })}
          </div>
        ) : (
          <div className="vc-scale-fields">
            <NumberField name="vmin" value={vmin.value} placeholder={placeholder} percent={percent} onChange={vmin.onChange} />
            <NumberField name="vmax" value={vmax.value} placeholder={placeholder} percent={percent} onChange={vmax.onChange} />
            {unit && <UnitSelect unit={unit} />}
          </div>
        )}
        {vmax.after}
        {below}
      </div>
    </div>
  );
}
