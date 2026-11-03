import { useId } from 'react';

import {
  FORM_CHOICES,
  chosenBands,
  commonResolutionOf,
  conversionTip,
  formatG,
  effectiveForm,
  layoutBlock,
  mixedResolutions,
  metresText,
  resolutionsOf,
  type DownloadBand,
} from '../bandChoice';
import { useAppStore } from '../store';
import Tip from './Tip';

// The choice in the download dialog (NM4-75): which bands, in how many files, and for one multi-band file, at which resolution. The list
// is the bands the scenes themselves describe (`bandChoice.ts`); nothing here names a band.

function detail(band: DownloadBand): string {
  return [band.commonName, band.wavelength === null ? null : `${formatG(band.wavelength)} µm`].filter(Boolean).join(' · ');
}

export default function BandChoice({ table, disabled }: { table: DownloadBand[]; disabled: boolean }) {
  const id = useId();
  const keys = useAppStore((s) => s.downloadBands);
  const form = useAppStore((s) => s.downloadForm);
  const picked = useAppStore((s) => s.downloadCommonResolution);
  const setBands = useAppStore((s) => s.setDownloadBands);
  const setForm = useAppStore((s) => s.setDownloadForm);
  const setCommon = useAppStore((s) => s.setDownloadCommonResolution);

  const bands = chosenBands(table, keys);
  const common = commonResolutionOf(bands, picked);
  const options = resolutionsOf(table);
  // The question of the form is there only for bands of different resolutions; one resolution is one file per resolution.
  const mixed = mixedResolutions(bands);
  const block = layoutBlock(effectiveForm(bands, form), bands, common);

  const toggle = (asset: string, on: boolean) => setBands(on ? [...keys, asset] : keys.filter((key) => key !== asset));

  return (
    <section className="dialog-choice" aria-label="Bands and files">
      <div className="dialog-choice-head">
        <span id={`${id}-bands`} className="dialog-choice-label">
          Bands
        </span>
        <span className="hint-text">
          {bands.length} of {table.length}
        </span>
        <button type="button" className="lm-btn dialog-choice-btn" disabled={disabled} onClick={() => setBands(table.map((band) => band.asset))}>
          All
        </button>
        <button type="button" className="lm-btn dialog-choice-btn" disabled={disabled} onClick={() => setBands([])}>
          None
        </button>
      </div>
      <ul className="dialog-bands" aria-labelledby={`${id}-bands`}>
        {table.map((band) => (
          <li key={band.asset}>
            <label className="dialog-band" title={band.asset}>
              <input type="checkbox" checked={keys.includes(band.asset)} disabled={disabled} onChange={(e) => toggle(band.asset, e.target.checked)} />
              <span className="dialog-band-name">{band.name}</span>
              <span className="dialog-band-detail">{detail(band)}</span>
              <span className="dialog-band-res">{band.resolution === null ? '' : metresText(band.resolution)}</span>
            </label>
          </li>
        ))}
      </ul>
      {mixed && (
        <div className="dialog-forms" role="group" aria-label="Files">
          {FORM_CHOICES.map((choice) => (
            <button
              key={choice.value}
              type="button"
              className={`pp-seg${form === choice.value ? ' on' : ''}`}
              aria-pressed={form === choice.value}
              title={choice.tip}
              disabled={disabled}
              onClick={() => setForm(choice.value)}
            >
              {choice.label}
            </button>
          ))}
        </div>
      )}
      {mixed && form === 'multi_band' && (
        <div className="dialog-common">
          <label htmlFor={`${id}-common`}>Resolution</label>
          <select
            id={`${id}-common`}
            value={common === null ? '' : String(common)}
            disabled={disabled || options.length === 0}
            onChange={(e) => setCommon(Number(e.target.value))}
          >
            {common === null && <option value="">–</option>}
            {options.map((resolution) => (
              <option key={resolution} value={String(resolution)}>
                {metresText(resolution)}
              </option>
            ))}
          </select>
          <Tip text={conversionTip(bands, common)} />
        </div>
      )}
      {block && <p className="hint-text warn">{block}</p>}
    </section>
  );
}
