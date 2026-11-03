// The bands a download offers and how they are laid out in files (NM4-75). Pure: the list comes from one item and its collection, so
// no band name is written down in the frontend; the dialog, the request, the job and the BANDS.txt of the browser's own ZIP all read it
// from here. The rules of the file names and of BANDS.txt are those of `backend/earthx/access/band_export.py`.

import type { DownloadForm } from './api';
import { assetGsdMeters, type DownloadRequestInfo } from './download';
import type { ExportLayout } from './processing';
import { auxiliaryAssetsOf, bandSources, bandsOf, maskLayerOf, registryUnit } from './processingOrder';
import type { Collection, StacAsset, StacItem } from './types';

export const DEFAULT_FORM: DownloadForm = 'per_band';

export const FORM_CHOICES: readonly { value: DownloadForm; label: string; tip: string }[] = [
  { value: 'per_band', label: 'One file per band', tip: 'Each band in a GeoTIFF of its own, in its own resolution. Nothing is converted.' },
  { value: 'per_resolution', label: 'One file per resolution', tip: 'One multi-band GeoTIFF for each resolution that occurs. Nothing is converted.' },
  { value: 'multi_band', label: 'One multi-band file', tip: 'All bands in one GeoTIFF with a common resolution. Bands of another resolution are converted.' },
];

export function formText(form: DownloadForm): string {
  return { per_band: 'one file per band', per_resolution: 'one file per resolution', multi_band: 'one multi-band file' }[form];
}

// One asset of the item as a band of the data: what the item says of it, and what the registry says of its kind.
export interface DownloadBand {
  asset: string;
  name: string;
  commonName: string | null;
  // Micrometres, as the item gives it.
  wavelength: number | null;
  // Metres per pixel; `null` where the item does not say.
  resolution: number | null;
  // A classification layer (the registry's mask layer): converted by its most frequent class, never averaged.
  categorical: boolean;
  dataType: string | null;
  scale: number | null;
  offset: number | null;
  nodata: number | null;
  unit: string | null;
}

const text = (value: unknown): string | null => (typeof value === 'string' && value.trim() !== '' ? value.trim() : null);
const finite = (value: unknown): number | null => (typeof value === 'number' && Number.isFinite(value) ? value : null);

function bandOf(collection: Collection, item: StacItem, asset: string, categorical: boolean): DownloadBand {
  const entry: StacAsset = item.assets[asset];
  const eo = Array.isArray(entry['eo:bands']) ? entry['eo:bands'][0] : undefined;
  const raster = bandsOf(entry)?.[0];
  return {
    asset,
    name: text(eo?.name) ?? asset,
    commonName: text(eo?.common_name),
    wavelength: finite(eo?.center_wavelength),
    resolution: assetGsdMeters(item, asset),
    categorical,
    dataType: text(raster?.data_type),
    scale: finite(raster?.scale),
    offset: finite(raster?.offset),
    nodata: finite(raster?.nodata),
    unit: text(raster?.unit) ?? registryUnit(collection, asset),
  };
}

// The bands of an item in its own order: its GeoTIFF assets without the pictures the registry calls auxiliary. The layer of the
// mask (`earthx:mask`) is one of them. Empty where the item has none (a store with no file per band): the dialog then offers no choice.
export function bandTableOf(collection: Collection | undefined, item: StacItem | null | undefined): DownloadBand[] {
  if (!collection || !item) return [];
  const auxiliary = new Set(auxiliaryAssetsOf(collection));
  const mask = maskLayerOf(collection)?.asset ?? null;
  return bandSources(item, 'cog', null, collection)
    .filter((source) => !auxiliary.has(source.asset))
    .map((source) => bandOf(collection, item, source.asset, source.asset === mask));
}

// What is ticked when the dialog opens: the spectral bands (those with a centre wavelength) and the layer of the mask; every band
// where the dataset has neither (an elevation model).
export function defaultBandKeys(table: readonly DownloadBand[]): string[] {
  const picked = table.filter((band) => band.wavelength !== null || band.categorical);
  return (picked.length > 0 ? picked : table).map((band) => band.asset);
}

// The ticked bands in the order of the item, whatever order they were ticked in.
export function chosenBands(table: readonly DownloadBand[], keys: readonly string[]): DownloadBand[] {
  return table.filter((band) => keys.includes(band.asset));
}

const SAME = 1e-6;
const same = (a: number, b: number) => Math.abs(a - b) <= SAME * Math.max(Math.abs(a), Math.abs(b));

// The resolutions that occur among the bands of the dataset, finest first: the choice of a common resolution.
export function resolutionsOf(table: readonly DownloadBand[]): number[] {
  const found: number[] = [];
  for (const { resolution } of table) {
    if (resolution !== null && !found.some((r) => same(r, resolution))) found.push(resolution);
  }
  return found.sort((a, b) => a - b);
}

export function finestResolution(bands: readonly DownloadBand[]): number | null {
  const known = bands.flatMap((band) => (band.resolution === null ? [] : [band.resolution]));
  return known.length > 0 ? Math.min(...known) : null;
}

// The common resolution a download uses: the one picked, else the finest of the ticked bands.
export function commonResolutionOf(bands: readonly DownloadBand[], picked: number | null): number | null {
  return picked ?? finestResolution(bands);
}

export type BandResampling = 'none' | 'nearest' | 'average' | 'mode';

// How a band is brought to `target` metres (`resampling_for` of the server): finer pixels repeat the value (nearest), coarser ones
// average a measurement and take the most frequent class of a classification layer (mode).
export function resamplingFor(band: DownloadBand, target: number | null): BandResampling {
  if (target === null || band.resolution === null || same(band.resolution, target)) return 'none';
  if (band.resolution > target) return 'nearest';
  return band.categorical ? 'mode' : 'average';
}

export interface Conversions {
  nearest: DownloadBand[];
  average: DownloadBand[];
  mode: DownloadBand[];
}

export function conversionsOf(bands: readonly DownloadBand[], target: number | null): Conversions {
  const out: Conversions = { nearest: [], average: [], mode: [] };
  for (const band of bands) {
    const method = resamplingFor(band, target);
    if (method !== 'none') out[method].push(band);
  }
  return out;
}

export const metresText = (resolution: number): string => `${formatResolution(resolution)} m`;

// The tooltip behind (i): which of the ticked bands are converted to the common resolution, and how.
export function conversionTip(bands: readonly DownloadBand[], target: number | null): string {
  if (target === null) return 'The bands have no known pixel size, so they cannot be brought to one resolution.';
  const { nearest, average, mode } = conversionsOf(bands, target);
  const list = (group: DownloadBand[]) => group.map((band) => `${band.name} (${metresText(band.resolution!)})`).join(', ');
  const lines = [
    nearest.length > 0 && `To a finer grid, nearest neighbour (values stay): ${list(nearest)}`,
    average.length > 0 && `To a coarser grid, average: ${list(average)}`,
    mode.length > 0 && `To a coarser grid, most frequent class: ${list(mode)}`,
  ].filter(Boolean);
  return lines.length > 0 ? `Converted to ${metresText(target)}:\n${lines.join('\n')}` : `No band is converted: all are ${metresText(target)} already.`;
}

// The ticked bands that make the form impossible: `multi_band` needs the pixel size of every band.
export function layoutBlock(form: DownloadForm, bands: readonly DownloadBand[], common: number | null): string | null {
  if (bands.length === 0) return 'Tick at least one band.';
  if (form === 'multi_band' && (common === null || bands.some((band) => band.resolution === null))) {
    return 'A band has no known pixel size, so it cannot be brought to one resolution.';
  }
  return null;
}

// What the order of a job or the request of a crop says of the form; `null` for a dataset with no bands to choose.
export function layoutOf(form: DownloadForm, common: number | null): ExportLayout {
  return form === 'multi_band' && common !== null ? { form, resolution_m: common } : { form };
}

// The request of a crop with the bands, the form and the common resolution of the dialog; unchanged for a dataset with no bands to choose.
export function withBandChoice(
  req: DownloadRequestInfo,
  table: readonly DownloadBand[],
  keys: readonly string[],
  form: DownloadForm,
  picked: number | null,
): DownloadRequestInfo {
  if (table.length === 0) return req;
  const bands = chosenBands(table, keys);
  return { ...req, assets: bands.map((band) => band.asset), layout: layoutOf(form, commonResolutionOf(bands, picked)) };
}

// --- numbers and names -----------------------------------------------------------

// `12.5`, `10`: no more digits than the pixel size has (six at most).
export function formatResolution(resolution: number): string {
  return String(Number(resolution.toPrecision(6)));
}

// Python's `%g` (six significant digits, no trailing zeros), the way BANDS.txt writes numbers.
export function formatG(value: number): string {
  if (value === 0) return '0';
  const [mantissa, exponent] = value.toExponential(5).split('e');
  const power = Number(exponent);
  if (power < -4 || power >= 6) {
    const digits = mantissa.includes('.') ? mantissa.replace(/0+$/, '').replace(/\.$/, '') : mantissa;
    return `${digits}e${power < 0 ? '-' : '+'}${String(Math.abs(power)).padStart(2, '0')}`;
  }
  return String(Number(value.toPrecision(6)));
}

const clean = (name: string): string => name.replace(/[^A-Za-z0-9._-]+/g, '_').replace(/^[._]+|[._]+$/g, '');

// `B04_red_10m`: the name, the common name if it adds something, the resolution if it is known.
function bandStem(band: DownloadBand): string {
  const parts = [band.name];
  if (band.commonName && band.commonName.toLowerCase() !== band.name.toLowerCase()) parts.push(band.commonName);
  if (band.resolution !== null) parts.push(`${formatResolution(band.resolution)}m`);
  return clean(parts.join('_')) || 'asset';
}

// The file of each band when every band has its own (asset key to file name, with `.tif`); two bands of one name get their asset key added.
export function perBandFileNames(bands: readonly DownloadBand[]): Map<string, string> {
  const stems = bands.map(bandStem);
  const count = new Map<string, number>();
  for (const stem of stems) count.set(stem, (count.get(stem) ?? 0) + 1);
  return new Map(bands.map((band, i) => [band.asset, `${count.get(stems[i]) === 1 ? stems[i] : clean(`${stems[i]}_${band.asset}`)}.tif`]));
}

// --- BANDS.txt -------------------------------------------------------------------

export const EXPORTS_DIR = 'exports/';
export const BANDS_FILENAME = 'BANDS.txt';
export const BANDS_COLUMNS =
  'Band | Name | Common name | Wavelength (um) | Source resolution (m) | Export resolution (m) | Resampling | Data type | Scale | Offset | Nodata | Unit';

export interface BandsFileEntry {
  // The path in the ZIP.
  path: string;
  bands: { band: DownloadBand; resampling: BandResampling; exportResolution: number | null }[];
}

const cell = (value: string | number | null): string => (value === null ? '-' : typeof value === 'number' ? formatG(value) : value);
const resolutionCell = (value: number | null): string => (value === null ? '-' : formatResolution(value));

// `exports/BANDS.txt`: the list of the files and, by band number, what each band is and what was done to it (the same text the server writes).
export function bandsFileText(args: { title: string; form: DownloadForm; files: readonly BandsFileEntry[] }): string {
  const lines = ['EarthX band list', `Dataset: ${args.title}`, `Layout: ${formText(args.form)}`];
  for (const file of args.files) {
    lines.push('', `File: ${file.path}`, BANDS_COLUMNS);
    file.bands.forEach(({ band, resampling, exportResolution }, index) => {
      lines.push(
        [
          String(index + 1),
          band.name,
          cell(band.commonName),
          cell(band.wavelength),
          resolutionCell(band.resolution),
          resolutionCell(exportResolution),
          resampling,
          cell(band.dataType),
          cell(band.scale ?? 1),
          cell(band.offset ?? 0),
          cell(band.nodata),
          cell(band.unit),
        ].join(' | '),
      );
    });
  }
  return `${lines.join('\n')}\n`;
}
