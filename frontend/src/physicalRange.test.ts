// M5-68: every range of the page is physical; only where a tile URL of stored numbers is built does it become a stored one, with the
// scaling of the band that tile draws. Tested here across the modules that meet at that one place.

import { describe, expect, it } from 'vitest';

import { buildTileUrl, scalingOfRaster } from './mapLayers';
import { appliedRenderFrom, physicalRender } from './render';
import type { Bbox, DownloadedInfo, EarthxDefaultRender } from './types';

const S2 = { scale: 0.0001, offset: -0.1 };
const SCENE = '/collections/s2/items/i/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=red';
const rescalesOf = (url: string) => new URLSearchParams(url.slice(url.indexOf('?') + 1)).getAll('rescale');

describe('buildTileUrl: the one place a physical range becomes a stored one', () => {
  it('turns the range of a scaled band into the stored numbers its tile draws', () => {
    expect(rescalesOf(buildTileUrl(SCENE, { colormapName: 'viridis', rescale: '0.02,0.24' }, S2))).toEqual(['1200,3400']);
  });

  it('turns each of three ranges', () => {
    expect(rescalesOf(buildTileUrl(SCENE, { rescale: '0,0.1;0.02,0.24;-0.1,0' }, S2))).toEqual(['1000,2000', '1200,3400', '0,1000']);
  });

  it('leaves a tile with steps or an expression alone: it computes in physical values', () => {
    const operator = '/collections/s2/items/i/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=red&op=band_math&op_version=2';
    expect(rescalesOf(buildTileUrl(operator, { rescale: '0.02,0.24' }, S2))).toEqual(['0.02,0.24']);
    expect(rescalesOf(buildTileUrl(`${SCENE}&expression=red`, { rescale: '0.02,0.24' }, S2))).toEqual(['0.02,0.24']);
    expect(rescalesOf(buildTileUrl(SCENE, { rescale: '0.02,0.24', expression: 'red/2' }, S2))).toEqual(['0.02,0.24']);
  });

  it('leaves a range the registry gives in stored numbers, and one of a picture without scaling', () => {
    expect(rescalesOf(buildTileUrl(SCENE, { rescale: '1200,3400', stored: true }, S2))).toEqual(['1200,3400']);
    expect(rescalesOf(buildTileUrl(SCENE, { rescale: '0,100' }))).toEqual(['0,100']);
    expect(rescalesOf(buildTileUrl(SCENE, { rescale: '0,100' }, null))).toEqual(['0,100']);
  });

  it('writes no marker into the URL', () => {
    expect(buildTileUrl(SCENE, { rescale: '1200,3400', stored: true }, S2)).not.toContain('stored');
  });
});

describe('scalingOfRaster', () => {
  const scene = { tileUrl: SCENE, bounds: [0, 0, 1, 1] as Bbox, minZoom: 8, maxZoom: 14 };

  it('is a mosaic’s or an overview’s own, else that of the asset a scene is drawn from', () => {
    expect(scalingOfRaster({ ...scene, scaling: S2 })).toEqual(S2);
    const info: DownloadedInfo = { ...scene, asset: 'red', datasetId: 's2', scalings: { red: S2 } };
    expect(scalingOfRaster(info)).toEqual(S2);
    expect(scalingOfRaster({ ...info, asset: 'cloud' })).toBeNull();
    expect(scalingOfRaster(scene)).toBeNull();
  });
});

describe('the standard picture of the registry', () => {
  const standard = { assets: ['red'], rescale: [[1200, 3400]], colormap_name: 'viridis', expression: null } as unknown as EarthxDefaultRender;

  it('keeps its range in stored numbers and says so, so that a browse preview draws it as it is', () => {
    const render = appliedRenderFrom(standard);
    expect(render).toMatchObject({ rescale: '1200,3400', stored: true });
    expect(rescalesOf(buildTileUrl(SCENE, render, S2))).toEqual(['1200,3400']);
  });

  it('is lifted into physical values for the view, and draws the same tile', () => {
    const lifted = physicalRender(appliedRenderFrom(standard), S2);
    expect(lifted).toEqual({ colormapName: 'viridis', rescale: '0.02,0.24', expression: undefined });
    expect(rescalesOf(buildTileUrl(SCENE, lifted, S2))).toEqual(['1200,3400']);
  });

  it('only loses the marker where the band is not scaled', () => {
    expect(physicalRender(appliedRenderFrom(standard), null)).toEqual({ colormapName: 'viridis', rescale: '1200,3400', expression: undefined });
  });

  it('leaves a physical look as it is, the same object', () => {
    const look = { rescale: '0.02,0.24' };
    expect(physicalRender(look, S2)).toBe(look);
  });

  it('says nothing without a range', () => {
    expect(appliedRenderFrom({ ...standard, rescale: null } as unknown as EarthxDefaultRender).stored).toBeUndefined();
  });
});
