// The look of the band a step preset adds (adr/0035, M5-14 F1): told by the operator in the process description of the dataset
// (`x-earthx-looks`), read once per dataset. The view asks for it when a step preset is chosen; once it is in, `knownLookOf` gives it at
// once, so that "Auto-scale" can take the range the look calls for.

import type { BandStatistics } from './api';
import { lookOfStep, type DisplayLook } from './displayLook';
import { fetchProcess } from './processing';
import { processInfo, type ProcessInfo } from './processingOrder';
import type { QuickPreset } from './quickPresets';
import type { ResultStats } from './render';
import type { Field } from './schemaForm';

const asked = new Map<string, Promise<ProcessInfo | null>>();
const known = new Map<string, ProcessInfo>();

function infoOf(datasetId: string): Promise<ProcessInfo | null> {
  let answer = asked.get(datasetId);
  if (!answer) {
    answer = fetchProcess(datasetId)
      .then((description) => {
        const info = processInfo(description);
        known.set(datasetId, info);
        return info;
      })
      // A failed question is asked again with the next click.
      .catch(() => {
        asked.delete(datasetId);
        return null;
      });
    asked.set(datasetId, answer);
  }
  return answer;
}

function lookIn(info: ProcessInfo | undefined | null, preset: QuickPreset): DisplayLook | null {
  const [step] = preset.steps;
  if (preset.kind !== 'step' || !info || !step) return null;
  const operator = info.operators.find((o) => o.op === step.op && o.opVersion === step.opVersion);
  return operator ? lookOfStep(operator.looks, step.params) : null;
}

// The look of the step preset, once the description of the dataset is in; `null` for another kind of preset or where the description
// says none.
export async function lookOfStepPreset(datasetId: string, preset: QuickPreset): Promise<DisplayLook | null> {
  return preset.kind === 'step' ? lookIn(await infoOf(datasetId), preset) : null;
}

// The same, without asking: `null` where the description has not come yet.
export const knownLookOf = (datasetId: string, preset: QuickPreset): DisplayLook | null => lookIn(known.get(datasetId), preset);

// The fields of the parameters a person may change at the step preset (Otto, 17.11.2026), as the form of its operator describes them
// (bounds, choices, unit), in the order of the registry; none before the description is in or where the operator has no form.
export function knownFieldsOf(datasetId: string, preset: QuickPreset): Field[] {
  const [step] = preset.steps;
  const operator = known.get(datasetId)?.operators.find((o) => o.op === step?.op && o.opVersion === step?.opVersion);
  if (preset.kind !== 'step' || !operator?.form.supported) return [];
  const fields = operator.form.fields;
  return preset.adjustable.flatMap((name) => fields.filter((field) => field.name === name));
}

// The description of the dataset, asked for once; resolves when it is in (or failed).
export const describeDataset = (datasetId: string): Promise<unknown> => infoOf(datasetId);

// Forget what was read (tests).
export function forgetPresetLooks(): void {
  asked.clear();
  known.clear();
}

const finite = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);

// The statistics of the tiler (`min`, `max`, `percentile_2`, `percentile_98` by band) as a look reads them.
export function statsOfTiler(stats: Record<string, BandStatistics>): ResultStats | null {
  const bands = Object.values(stats).map((band) => ({
    minimum: finite(band.min),
    maximum: finite(band.max),
    percentile2: finite(band.percentile_2),
    percentile98: finite(band.percentile_98),
  }));
  return bands.some((band) => band.minimum !== null && band.maximum !== null) ? { bands, expression: false } : null;
}
