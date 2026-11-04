// The field "Colormap" wherever a colormap is chosen (the settings bar, a result layer, the preview of the processing panel; UI-03d,
// Otto, 2.11.2026): a few colormaps, the one chosen where it is another, and "More…" for the whole list; "Reverse" beside it turns the
// scale round. The value is the tiler's name, `_r` for the reversed one.

import { baseOf, isReversed, shortList, withReverse } from '../colormaps';
import { useColormapPicker } from '../colormapPicker';
import { ArrowLeftRightIcon } from './icons';
import { useColormapGroups } from './useColormapGroups';

export const NONE = '— none —';
export const MORE = 'More…';
const MORE_VALUE = '\u0000more';
export const REVERSE_TIP = 'Reverse the colormap';
const NO_REVERSE_TIP = 'Choose a colormap to reverse';

interface Props {
  value: string;
  onChange: (name: string) => void;
}

export default function ColormapField({ value, onChange }: Props) {
  const read = useColormapGroups();
  const groups = read === 'failed' ? null : read;
  const open = useColormapPicker((s) => s.open);
  const reversed = isReversed(value);
  const base = baseOf(value);
  return (
    // A label around both, so that the name names the dropdown; the button inside takes its own clicks.
    <label className="vc-field vc-colormap">
      <span>Colormap</span>
      <div className="vc-colormap-row">
        <select
          value={base}
          onChange={(e) => {
            if (e.target.value === MORE_VALUE) open(value, onChange);
            else onChange(withReverse(e.target.value, reversed));
          }}
        >
          <option value="">{NONE}</option>
          {shortList(groups, value).map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
          <option value={MORE_VALUE} title="All colormaps, with a preview">
            {MORE}
          </option>
        </select>
        <button
          type="button"
          className={`ghost-btn vc-reverse${reversed ? ' on' : ''}`}
          aria-pressed={reversed}
          aria-label={REVERSE_TIP}
          title={base === '' ? NO_REVERSE_TIP : REVERSE_TIP}
          disabled={base === ''}
          onClick={() => onChange(withReverse(value, !reversed))}
        >
          <ArrowLeftRightIcon />
        </button>
      </div>
    </label>
  );
}
