// The row "Index" under "Add step" (NM4-14): one button for each index the dataset offers. A button adds an ordinary Band math
// step with the expression and the name of the preset (`addStep`); from then on it is a step like any other.

import { indexPresetsOf, presetTip, type IndexPreset } from '../indexPresets';
import type { ProcessInfo } from '../processingOrder';
import type { Collection } from '../types';

export default function IndexButtons({
  collection,
  info,
  count,
  nameBlock,
  onAdd,
}: {
  collection: Collection | undefined;
  info: ProcessInfo;
  // The steps of the draft.
  count: number;
  // Why no step may be added now (a name that breaks a rule), or `null`.
  nameBlock: string | null;
  onAdd: (preset: IndexPreset, opVersion: number) => void;
}) {
  const presets = indexPresetsOf(collection);
  const operator = info.operators.find((o) => o.op === 'band_math' && o.opVersion === 2);
  // Hidden, not locked, where there is nothing to offer: the dataset has no presets, or does not run Band math.
  if (presets.length === 0 || !operator) return null;
  const reason = !operator.form.supported ? operator.form.reason : count >= info.maxSteps ? `At most ${info.maxSteps} steps` : nameBlock;
  return (
    <div className="pp-add" role="group" aria-label="Add index">
      <span className="pp-help">Index:</span>
      {presets.map((preset) => {
        const tip = presetTip(preset);
        return (
          <button
            key={preset.name}
            type="button"
            className="ghost-btn pp-add-btn"
            disabled={reason !== null}
            title={reason ?? tip}
            aria-label={`${preset.name}. ${reason ?? tip}`}
            onClick={() => onAdd(preset, operator.opVersion)}
          >
            ＋ {preset.name}
          </button>
        );
      })}
    </div>
  );
}
