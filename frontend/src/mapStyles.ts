// The style of the map (V-1, UI-02a): the backdrop in the theme colour and the globe's sky, which are the app's own,
// and one basemap from `basemaps.ts` under the app's layers. A basemap is changed on the running map with a style diff
// (`applyBasemap`): the sources and layers of the app (AOI, coverage, pictures, tiles of orders, the drawing tool) are
// carried over untouched, so no picture blinks out. The dark HUD panels are HTML overlays on top.

import type { StyleSpecification, TransformStyleFunction } from 'maplibre-gl';

import { BASEMAP_PREFIX, BASEMAPS, DEFAULT_BASEMAP, OPENFREEMAP_ATTRIBUTION, type BasemapId } from './basemaps';
import { RELIEF_OVERLAY_ID, reliefLayer, reliefSource } from './relief';
import { GRATICULE_SOURCE, graticuleData, graticuleLayers, NO_OVERLAYS, OVERLAY_IDS, OVERLAY_PREFIX, type Overlays } from './overlays';

// The attribution is always open (Otto, 27.10.2026, UI-02 question 4): the OSMF guidelines ask for it to be visible
// without interaction, which the collapsed "i" button of V-7 was not.
export const ATTRIBUTION_CONTROL = { compact: false } as const;

// The colour behind the globe and behind the imagery comes from the theme token
// `--map-bg` (`index.css`): dark in the tech theme, white in the light one. A
// style paints with plain values and cannot read a CSS variable, so the token is
// read off the app element and put into the style — at creation and on every
// theme switch (`applyMapBackground`).
export const MAP_BACKGROUND_TOKEN = '--map-bg';

export function mapBackgroundOf(element: Element | null): string | undefined {
  if (!element) return undefined;
  const value = getComputedStyle(element).getPropertyValue(MAP_BACKGROUND_TOKEN).trim();
  return value || undefined;
}

// What MapLibre paints behind the globe (V-1's projection switch, D27):
// `sky`'s defaults (`sky-color` a light blue, `horizon-color`/`fog-color`
// white) leave the map behind the sphere looking white. Set to the token colour
// instead. `drawSky` (the full-screen gradient quad, unconditional whenever
// `style.sky` is set) isn't gated on `atmosphere-blend` — that value only skips
// the separate glow/halo pass (`drawAtmosphere`), which stays off here (0) so the
// globe doesn't pick up a colored rim. The WebGL canvas clears to transparent
// every frame before the sky is drawn, so anything the sky quad does not cover
// falls through to the page: `.app`'s own background (the same token) is the
// actual guarantee, this is the belt to that braces.
function skyOf(background: string) {
  return {
    'sky-color': background,
    'horizon-color': background,
    'fog-color': background,
    'atmosphere-blend': 0,
  };
}

type Layer = StyleSpecification['layers'][number];

const hasBasemapPrefix = (id: string): boolean => id.startsWith(BASEMAP_PREFIX);
const isComposed = (id: string): boolean => hasBasemapPrefix(id) || id.startsWith(OVERLAY_PREFIX);

// The app's own layers and sources are all those that are neither a basemap's nor an overlay's nor the backdrop
// (`background`).
const isOwnLayer = (layer: Layer): boolean => layer.id !== 'background' && !isComposed(layer.id);

// The names on a map are its `symbol` layers.
const isLabel = (layer: Layer): boolean => layer.type === 'symbol';
const hasLabels = (style: StyleSpecification): boolean => (style.layers ?? []).some(isLabel);

// Where the overlays go among the app's layers: right under the area of interest, over every picture
// (`mapLayers.ts`, the marker `overlays-base` sits just under it).
const OVERLAYS_BEFORE = 'aoi-fill';

// A basemap without names of its own (Satellite, Outlines) takes those of `from`, a published style (Grey): its
// symbol layers, their vector source (the basemap's own, if it has the same tiles), glyphs and sprite.
function withLabelsOf(next: StyleSpecification, from: StyleSpecification): StyleSpecification {
  const sources = { ...next.sources };
  const renamed = new Map<string, string>();
  const labels = (from.layers ?? []).filter(isLabel);
  for (const layer of labels) {
    const key = 'source' in layer ? layer.source : undefined;
    const source = key === undefined ? undefined : from.sources[key];
    if (key === undefined || source === undefined || renamed.has(key)) continue;
    const same = Object.entries(next.sources ?? {}).find(([, own]) => own.type === 'vector' && source.type === 'vector' && own.url === source.url);
    renamed.set(key, same?.[0] ?? `labels-${key}`);
    if (!same) sources[`labels-${key}`] = source.type === 'vector' ? { ...source, attribution: OPENFREEMAP_ATTRIBUTION } : source;
  }
  const layers = labels.map((layer) => ({ ...layer, id: `labels-${layer.id}`, ...('source' in layer && layer.source !== undefined ? { source: renamed.get(layer.source) } : {}) }) as Layer);
  return { ...next, sources, layers: [...(next.layers ?? []), ...layers], glyphs: from.glyphs, sprite: from.sprite };
}

// What the map has of its own, which a basemap's style does not replace.
const MAP_OWN = ['sky', 'projection', 'light', 'terrain', 'center', 'zoom', 'bearing', 'pitch'] as const;

// `next` (a basemap's style) under the app's layers of `previous`: the backdrop first, then the basemap's layers
// with a prefix on their ids and sources, then everything of the app, with the overlays just under its area of
// interest. The names of the basemap (its `symbol` layers) are among the overlays: over the app's pictures, hidden
// unless Labels is on. What is the map's rather than the basemap's (the camera, the globe's sky, the projection)
// comes from `previous`: a published style has its own camera and none of the others, and a missing projection
// would reset the globe. `labelStyle` is where a basemap without names takes them from when Labels is on.
export function composeStyle(
  previous: StyleSpecification | undefined,
  next: StyleSpecification,
  id: BasemapId,
  overlays: Overlays = NO_OVERLAYS,
  labelStyle?: StyleSpecification,
): StyleSpecification {
  const basemap = overlays.labels && labelStyle && !hasLabels(next) ? withLabelsOf(next, labelStyle) : next;
  const ownLayers = (previous?.layers ?? []).filter(isOwnLayer);
  const ownSources = Object.fromEntries(Object.entries(previous?.sources ?? {}).filter(([key]) => !isComposed(key)));
  const sources: StyleSpecification['sources'] = {};
  for (const [key, source] of Object.entries(basemap.sources ?? {})) {
    // A published OpenFreeMap style names its attribution in the TileJSON it points at: set the wording the provider
    // asks for, so that a change in that TileJSON can not drop it.
    sources[BASEMAP_PREFIX + key] =
      source.type === 'vector' && (id === 'streets' || id === 'grey') ? { ...source, attribution: OPENFREEMAP_ATTRIBUTION } : source;
  }
  const prefixed = (layer: Layer, prefix: string): Layer =>
    'source' in layer && layer.source !== undefined
      ? { ...layer, id: prefix + layer.id, source: BASEMAP_PREFIX + layer.source }
      : { ...layer, id: prefix + layer.id };
  const names = (basemap.layers ?? []).filter(isLabel).map((layer): Layer => {
    const named = prefixed(layer, OVERLAY_PREFIX);
    return overlays.labels ? named : { ...named, layout: { ...named.layout, visibility: 'none' } };
  });
  const layers = (basemap.layers ?? []).filter((layer) => !isLabel(layer)).map((layer) => prefixed(layer, BASEMAP_PREFIX));
  if (overlays.graticule) sources[GRATICULE_SOURCE] = { type: 'geojson', data: graticuleData() };
  // The shading lies over the basemap and under all the app's layers; the basemap "Relief" is the shading already.
  const shading = overlays.relief && id !== 'relief';
  if (shading) sources[RELIEF_OVERLAY_ID] = reliefSource();
  const over = [...(overlays.graticule ? graticuleLayers() : []), ...names];
  const split = ownLayers.findIndex((layer) => layer.id === OVERLAYS_BEFORE);
  const at = split < 0 ? ownLayers.length : split;
  const backdrop = (previous?.layers ?? []).filter((layer) => layer.id === 'background');
  const { sky: _sky, projection: _projection, light: _light, terrain: _terrain, center: _center, zoom: _zoom, bearing: _bearing, pitch: _pitch, ...rest } = basemap;
  const kept: Partial<StyleSpecification> = {};
  for (const key of MAP_OWN) if (previous?.[key] !== undefined) Object.assign(kept, { [key]: previous[key] });
  return {
    ...rest,
    ...kept,
    sources: { ...sources, ...ownSources },
    layers: [...backdrop, ...layers, ...(shading ? [reliefLayer(RELIEF_OVERLAY_ID, RELIEF_OVERLAY_ID, 'overlay')] : []), ...ownLayers.slice(0, at), ...over, ...ownLayers.slice(at)],
  };
}

// `background` is the resolved token colour; without one (no DOM to read it from)
// the style gets no explicit colour of its own beyond MapLibre's defaults.
// A basemap with a published style (Streets, Grey) is not in the first style: it is applied once the map is up.
export function baseMapStyle(background?: string, basemap: BasemapId = DEFAULT_BASEMAP): StyleSpecification {
  const empty: StyleSpecification = {
    version: 8,
    name: 'earthx',
    sources: {},
    layers: [{ id: 'background', type: 'background', paint: background ? { 'background-color': background } : {} }],
  };
  if (background) empty.sky = skyOf(background);
  const style = BASEMAPS[basemap].style;
  return typeof style === 'string' ? empty : composeStyle(empty, style, basemap);
}

// Whether `baseMapStyle` already holds the basemap, or `applyBasemap` has to fetch it.
export const isInFirstStyle = (basemap: BasemapId): boolean => typeof BASEMAPS[basemap].style !== 'string';

// Re-tints a map that is already up (a theme switch): the `background` layer and
// the globe's sky.
export function applyMapBackground(
  map: { getLayer(id: string): unknown; setPaintProperty(layer: string, prop: string, value: unknown): void; setSky(sky: object): void },
  background: string,
): void {
  if (map.getLayer('background')) map.setPaintProperty('background', 'background-color', background);
  map.setSky(skyOf(background));
}

// The map as far as `applyBasemap` and `applyProjection` need it.
interface StyleMap {
  setStyle(style: StyleSpecification, options: { diff: boolean; transformStyle: TransformStyleFunction }): unknown;
}
interface ProjectionMap {
  setProjection(projection: { type: 'mercator' | 'globe' }): unknown;
}

export function applyProjection(map: ProjectionMap, projection: 'mercator' | 'globe'): void {
  map.setProjection({ type: projection });
}

// Answers of the style server that are not a style.
const isStyle = (value: unknown): value is StyleSpecification =>
  !!value && typeof value === 'object' && (value as { version?: unknown }).version === 8 && Array.isArray((value as { layers?: unknown }).layers);

// The published styles fetched so far: a change of an overlay puts the same basemap under the app's layers again and
// need not ask the style server a second time. A failed fetch is not kept.
const published = new Map<string, StyleSpecification>();
export const forgetPublishedStyles = (): void => published.clear();

async function fetchStyle(url: string): Promise<StyleSpecification> {
  const known = published.get(url);
  if (known) return known;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`the style server answered ${response.status}`);
  const body: unknown = await response.json();
  if (!isStyle(body)) throw new Error('the answer is not a map style');
  published.set(url, body);
  return body;
}

// The latest request: an answer that arrives after a newer choice is dropped.
let latest = 0;

// Puts the basemap and the overlays under and over the app's layers of the running map. A published style is fetched
// here, not by MapLibre, so that a failure can be told to the user; `onError` gets the reason. Names on a basemap
// that has none of its own (Satellite, Outlines) come from the style of Grey. Resolves when the style is handed to
// the map (its tiles load afterwards), to `false` when it was not (failed, or overtaken by a newer choice).
export async function applyBasemap(
  map: StyleMap,
  id: BasemapId,
  onError: (reason: string) => void = () => {},
  overlays: Overlays = NO_OVERLAYS,
): Promise<boolean> {
  const ticket = ++latest;
  const source = BASEMAPS[id].style;
  let what = `${BASEMAPS[id].name} basemap`;
  let next: StyleSpecification;
  let labelStyle: StyleSpecification | undefined;
  try {
    next = typeof source === 'string' ? await fetchStyle(source) : source;
    if (overlays.labels && !hasLabels(next)) {
      what = 'labels';
      labelStyle = await fetchStyle(BASEMAPS.grey.style as string);
    }
  } catch (error) {
    if (ticket === latest) onError(`The ${what} could not be loaded: ${error instanceof Error ? error.message : String(error)}.`);
    return false;
  }
  if (ticket !== latest) return false;
  map.setStyle(next, { diff: true, transformStyle: (previous, style) => composeStyle(previous, style, id, overlays, labelStyle) });
  return true;
}

// Keeps track of which basemap and overlays the map shows, so that a choice is not applied twice and a failed one is
// taken back. `initial` is the basemap in the first style (null when that style holds none yet); `onFailure` gets the
// reason and the basemap and overlays the map still shows (null and none if it shows no basemap), which is what the
// choice goes back to.
export function createBasemapSwitcher(
  map: StyleMap,
  initial: BasemapId | null,
  onFailure: (reason: string, keep: BasemapId | null, overlays: Overlays) => void,
) {
  type Look = { basemap: BasemapId; overlays: Overlays };
  let shown: Look | null = initial && { basemap: initial, overlays: NO_OVERLAYS };
  let requested = shown;
  return {
    show(basemap: BasemapId, overlays: Overlays = NO_OVERLAYS): void {
      if (requested?.basemap === basemap && OVERLAY_IDS.every((overlay) => requested?.overlays[overlay] === overlays[overlay])) return;
      const look = { basemap, overlays };
      requested = look;
      void applyBasemap(
        map,
        basemap,
        (reason) => {
          requested = shown;
          onFailure(reason, shown?.basemap ?? null, shown?.overlays ?? NO_OVERLAYS);
        },
        overlays,
      ).then((handedOver) => {
        if (handedOver) shown = look;
      });
    },
  };
}
