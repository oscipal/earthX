// The look a layer is drawn with, as an export carries it for the QGIS style beside each file (M5-64, plan
// `plans/m5/m5-64-qgis-stil.md` §3): one band with its colormap (or grey) and range, or a colour picture of three bands with a range
// each, in physical values as every range here is (M5-68). Only what is applied counts (plan A5). `null` where the layer shows nothing
// the files hold: an index, the true-colour picture of an auxiliary asset, a layer of classes (their colours come with the files).

import { channelsOfRescale } from './channels';
import { defaultRenderOf, drawsClasses, showsColormap } from './datasets';
import { presetOfLook } from './quickPresets';
import type { MapLayer } from './layers';
import type { AppliedRender, Collection } from './types';

type Range = [number, number];

export type ExportStyle =
  | { band: string; colormap: string | null; range: Range }
  | { rgb: [string, string, string]; ranges: [Range, Range, Range] };

function rangeOf(pair: string): Range | null {
  const [low, high, ...rest] = pair.split(',').map((end) => (end.trim() === '' ? NaN : Number(end)));
  return rest.length === 0 && Number.isFinite(low) && Number.isFinite(high) && low < high ? [low, high] : null;
}

// One range, or three where the look has one per channel (three equal ones are written as one, `channels.ts`).
function rangesOf(rescale: string | undefined): Range[] | null {
  if (!rescale) return null;
  const channels = channelsOfRescale(rescale);
  const ranges = (channels ? channels.map(({ vmin, vmax }) => `${vmin},${vmax}`) : [rescale]).map(rangeOf);
  return ranges.every((range): range is Range => range !== null) ? ranges : null;
}

function picture(bands: readonly string[], ranges: Range[]): ExportStyle | null {
  if (bands.length !== 3) return null;
  const [red, green, blue] = ranges.length === 3 ? ranges : [ranges[0], ranges[0], ranges[0]];
  return { rgb: [bands[0], bands[1], bands[2]], ranges: [red, green, blue] };
}

// The style of a layer of scenes (the view, or a layer pinned from it) of a dataset with `collection`.
export function exportStyleOf(look: AppliedRender, collection: Collection | undefined): ExportStyle | null {
  if (look.stored || look.expression) return null;
  const ranges = rangesOf(look.rescale);
  if (!ranges) return null;
  if (look.index) {
    // A composite whose channels are bands of the data as they are (`nir`, `red`, `green`) is a colour picture of those bands; one
    // that computes a channel shows something no file holds.
    const preset = presetOfLook(look, collection);
    const sources = preset?.channels ? preset.steps.map((step) => step.params.expression) : [];
    const plain = sources.every((source) => typeof source === 'string' && /^[A-Za-z_][A-Za-z0-9_]*$/u.test(source));
    return plain ? picture(sources as string[], ranges) : null;
  }
  const colormap = look.colormapName ?? null;
  if (look.band) return ranges.length === 1 ? { band: look.band, colormap, range: ranges[0] } : null;
  if (!collection || !showsColormap(collection) || drawsClasses(collection)) return null;
  const asset = defaultRenderOf(collection)?.assets?.[0];
  return asset && ranges.length === 1 ? { band: asset, colormap, range: ranges[0] } : null;
}

// The style of a layer of a job's result, whose bands are named `names` in the order of the file (`bidx` 1 is the first). A
// result of one band takes a style of one band whatever it is called, so its name is not needed.
export function resultStyleOf(look: AppliedRender, names: readonly string[]): ExportStyle | null {
  if (look.colormap) return null; // the colours of its classes: the result names them itself
  const ranges = rangesOf(look.rescale);
  if (!ranges) return null;
  const places = (look.bidx ?? '1').split(',').map((place) => Number(place) - 1);
  if (places.some((place) => !Number.isInteger(place) || place < 0)) return null;
  const bands = places.map((place) => names[place] ?? (names.length === 0 && place === 0 ? 'band' : undefined));
  if (bands.some((band) => band === undefined)) return null;
  if (bands.length === 3) return picture(bands as string[], ranges);
  return bands.length === 1 && ranges.length === 1 ? { band: bands[0]!, colormap: look.colormapName ?? null, range: ranges[0] } : null;
}

// The style of a layer of a job's result, from the tile URL it draws (band, range and colormap) and the names of its bands.
export function resultLayerStyle(layer: Pick<MapLayer, 'overlays' | 'result'>): ExportStyle | null {
  const tileUrl = layer.overlays.find((overlay) => overlay.kind === 'raster')?.tileUrl;
  if (!tileUrl) return null;
  const query = new URLSearchParams(tileUrl.slice(tileUrl.indexOf('?') + 1));
  const bidx = query.getAll('bidx');
  const rescale = query.getAll('rescale');
  const look: AppliedRender = {
    ...(bidx.length > 0 ? { bidx: bidx.join(',') } : {}),
    ...(rescale.length > 0 ? { rescale: rescale.join(';') } : {}),
    ...(query.get('colormap_name') ? { colormapName: query.get('colormap_name')! } : {}),
    ...(query.get('colormap') ? { colormap: query.get('colormap')! } : {}),
  };
  return resultStyleOf(look, layer.result?.bands?.map((band) => band.name) ?? []);
}

// The query of a result's ZIP that carries the style: `?style=…`, or nothing.
export function styleQuery(style: ExportStyle | null): string {
  return style ? `?style=${encodeURIComponent(JSON.stringify(style))}` : '';
}
