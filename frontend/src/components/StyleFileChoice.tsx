// "Style file" of the download dialog (M5-64 plan §12, Otto 27.11.2026): the style beside each raster of the ZIP, so that the file
// opens as the app draws it. One row in the form of "Resolution" (`.dialog-style-file`, styled like `.dialog-common`); the choice is
// kept in the browser.

import { useId } from 'react';

import type { StyleFormat } from '../preferences';
import { useAppStore } from '../store';

const LABELS: Record<StyleFormat, string> = { qml: 'QGIS (.qml)', sld: 'SLD', none: 'None' };

export const STYLE_FILE_TIP =
  'A style beside each file, so that it opens as drawn here. SLD (OGC 1.0) is for map servers; it stretches an RGB image to the values of its file.';

export default function StyleFileChoice({ disabled }: { disabled: boolean }) {
  const id = useId();
  const format = useAppStore((s) => s.downloadStyleFormat);
  const setFormat = useAppStore((s) => s.setDownloadStyleFormat);
  return (
    <div className="dialog-style-file" data-tip-level="advanced" data-tip={STYLE_FILE_TIP}>
      <label htmlFor={`${id}-style`}>Style file</label>
      <select id={`${id}-style`} value={format} disabled={disabled} onChange={(e) => setFormat(e.target.value as StyleFormat)}>
        {(Object.keys(LABELS) as StyleFormat[]).map((value) => (
          <option key={value} value={value}>
            {LABELS[value]}
          </option>
        ))}
      </select>
    </div>
  );
}
