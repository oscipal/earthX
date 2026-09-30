// @vitest-environment jsdom
//
// M3-10 (Otto, 30.09.2026): the backdrop behind the globe is a theme token —
// dark in the tech theme, white in the light one — not a fixed colour.

import { describe, expect, it, vi } from 'vitest';

import CSS from './index.css?raw';
import { applyMapBackground, baseMapStyle, mapBackgroundOf } from './mapStyles';

// The declarations of one theme's token block, e.g. `.app[data-theme='normal']`.
function tokenBlock(theme: string): string {
  const start = CSS.indexOf(`.app[data-theme='${theme}'] {`);
  expect(start).toBeGreaterThanOrEqual(0);
  return CSS.slice(start, CSS.indexOf('}', start));
}
function mapBg(block: string): string | null {
  return /--map-bg:\s*([^;]+);/.exec(block)?.[1].trim() ?? null;
}

describe('the map backdrop is a theme token', () => {
  it('is defined in both themes, dark in the tech one and white in the light one', () => {
    expect(mapBg(tokenBlock('tech'))).toMatch(/^#0[0-9a-f]{5}$/i);
    expect(mapBg(tokenBlock('normal'))?.toLowerCase()).toBe('#ffffff');
  });

  it('is what the app paints behind the map, and nothing paints a fixed dark colour there', () => {
    const app = CSS.slice(CSS.indexOf('.app {'), CSS.indexOf('}', CSS.indexOf('.app {')));
    expect(app).toContain('background: var(--map-bg)');
    const body = CSS.slice(CSS.indexOf('body {'), CSS.indexOf('}', CSS.indexOf('body {')));
    expect(body).not.toMatch(/background:\s*#/);
  });

  it('is read off the element that carries the theme', () => {
    const app = document.createElement('div');
    app.style.setProperty('--map-bg', ' #ffffff ');
    document.body.append(app);
    expect(mapBackgroundOf(app)).toBe('#ffffff');
    app.remove();
  });

  it('is undefined without an element or without the token', () => {
    expect(mapBackgroundOf(null)).toBeUndefined();
    expect(mapBackgroundOf(document.createElement('div'))).toBeUndefined();
  });
});

describe('baseMapStyle', () => {
  it('puts the colour into the background layer and the globe sky', () => {
    const style = baseMapStyle('#ffffff');
    const background = style.layers.find((l) => l.id === 'background');
    expect(background?.type === 'background' && background.paint?.['background-color']).toBe('#ffffff');
    expect(style.sky).toMatchObject({ 'sky-color': '#ffffff', 'horizon-color': '#ffffff', 'fog-color': '#ffffff', 'atmosphere-blend': 0 });
  });

  it('carries no colour of its own without a token colour', () => {
    const style = baseMapStyle();
    expect(style.sky).toBeUndefined();
    expect(JSON.stringify(style)).not.toMatch(/#04070a/i);
  });

  it('returns a fresh copy every time', () => {
    expect(baseMapStyle('#fff')).not.toBe(baseMapStyle('#fff'));
  });
});

describe('applyMapBackground', () => {
  it('re-tints the background layer and the sky of a running map', () => {
    const map = { getLayer: vi.fn(() => ({})), setPaintProperty: vi.fn(), setSky: vi.fn() };
    applyMapBackground(map, '#04070a');
    expect(map.setPaintProperty).toHaveBeenCalledWith('background', 'background-color', '#04070a');
    expect(map.setSky).toHaveBeenCalledWith(expect.objectContaining({ 'sky-color': '#04070a' }));
  });

  it('still sets the sky when the style has no background layer', () => {
    const map = { getLayer: vi.fn(() => undefined), setPaintProperty: vi.fn(), setSky: vi.fn() };
    applyMapBackground(map, '#ffffff');
    expect(map.setPaintProperty).not.toHaveBeenCalled();
    expect(map.setSky).toHaveBeenCalled();
  });
});
