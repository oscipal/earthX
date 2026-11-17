// The parameters of a step preset a person may change right under "Quick processing" (Otto, 17.11.2026, M5-14): the registry names them
// (`adjustable`), the form of the operator says what they can be. A choice is a row of segment buttons; an angle from north (0 to 360°)
// a dial; any other number with two bounds a slider with its value. Nothing here knows a product or a dataset; a change is drawn at once.

import { useEffect, useState } from 'react';

import { describeDataset, knownFieldsOf } from '../presetLooks';
import { paramsOfPreset, type PresetParam, type QuickPreset } from '../quickPresets';
import { controlOf } from '../paramControls';
import type { Field } from '../schemaForm';
import AngleDial from './AngleDial';

const capitalised = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);
const unitText = (field: Field): string => (field.unit === 'deg' ? '°' : '');

export default function PresetParamControls({
  datasetId,
  preset,
  onChange,
}: {
  datasetId: string;
  // The preset with the values the fields stand for.
  preset: QuickPreset;
  onChange: (name: string, value: PresetParam) => void;
}) {
  // The form of the operator comes with the description of the dataset, asked for once.
  const [, described] = useState(0);
  useEffect(() => {
    let live = true;
    void describeDataset(datasetId).then(() => {
      if (live) described((n) => n + 1);
    });
    return () => {
      live = false;
    };
  }, [datasetId]);
  const values = paramsOfPreset(preset);
  const offered = knownFieldsOf(datasetId, preset).flatMap((field) => {
    const control = controlOf(field);
    return control && field.name in values ? [{ field, control }] : [];
  });
  if (offered.length === 0) return null;
  return (
    <div className="vc-params">
      {offered.map(({ field, control }) => {
        const value = values[field.name];
        if (control === 'choice') {
          return (
            <div key={field.name} className="vc-param" role="group" aria-label={field.title}>
              <span className="vc-param-label">{field.title}</span>
              <span className="vc-param-choices">
                {field.options!.map((option) => (
                  <button
                    key={option}
                    type="button"
                    className="btn seg"
                    aria-pressed={value === option}
                    data-tip-level="advanced"
                    data-tip={field.optionHelp?.[option] ?? field.description}
                    onClick={() => {
                      if (value !== option) onChange(field.name, option);
                    }}
                  >
                    {capitalised(option)}
                  </button>
                ))}
              </span>
            </div>
          );
        }
        const number = typeof value === 'number' ? value : Number(value);
        if (control === 'dial') {
          return (
            <div key={field.name} className="vc-param">
              <span className="vc-param-label">{field.title}</span>
              <AngleDial value={number} label={field.title} tip={field.description} onChange={(angle) => onChange(field.name, angle)} />
            </div>
          );
        }
        return (
          <label key={field.name} className="vc-param" data-tip-level="advanced" data-tip={field.description}>
            <span className="vc-param-label">{field.title}</span>
            <input
              type="range"
              min={field.minimum}
              max={field.maximum}
              step={1}
              value={number}
              aria-valuetext={`${number}${unitText(field)}`}
              onChange={(event) => onChange(field.name, Number(event.target.value))}
            />
            <span className="vc-param-value">
              {number}
              {unitText(field)}
            </span>
          </label>
        );
      })}
    </div>
  );
}
