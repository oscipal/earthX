// icons.ts (UI-04 part 2): one stroke at every size, two sizes, no icon that nothing uses.

import { createElement, type ComponentType } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { ICON_SIZES } from './iconSizes';
import * as icons from './icons';
import tokens from '../tokens.css?raw';

const SOURCES = import.meta.glob(['../**/*.ts', '../**/*.tsx', '!../**/*.test.ts', '!../**/*.test.tsx', '!../**/icons.ts'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

const EXPORTS = icons as unknown as Record<string, ComponentType<Record<string, unknown>>>;
const NAMES = Object.keys(EXPORTS).filter((name) => name.endsWith('Icon'));
const render = (name: string, props: Record<string, unknown> = {}) => renderToStaticMarkup(createElement(EXPORTS[name], props));

describe('icons.ts', () => {
  it('exports icons and nothing else', () => {
    expect(NAMES.length).toBeGreaterThan(30);
    expect(Object.keys(EXPORTS)).toEqual(NAMES);
  });

  it.each(NAMES)('%s is 16 px with a stroke of 1.5 px, hidden from screen readers, in the colour of the text', (name) => {
    const markup = render(name);
    expect(markup).toContain('width="16"');
    expect(markup).toContain('height="16"');
    // `absoluteStrokeWidth`: the stroke is scaled so that it is 1.5 px on the screen (1.5 × 24 / 16).
    expect(markup).toContain('stroke-width="2.25"');
    expect(markup).toContain('stroke="currentColor"');
    expect(markup).toContain('aria-hidden="true"');
  });

  it('has a second size, 14 px, with the same stroke on the screen', () => {
    const markup = render('DownloadIcon', { size: 14 });
    expect(markup).toContain('width="14"');
    expect(Number(/stroke-width="([\d.]+)"/u.exec(markup)![1]) * (14 / 24)).toBeCloseTo(1.5, 5);
  });

  it('has a third size, 20 px, for the rail, with the same stroke on the screen', () => {
    const markup = render('SearchIcon', { size: 20 });
    expect(markup).toContain('width="20"');
    expect(Number(/stroke-width="([\d.]+)"/u.exec(markup)![1]) * (20 / 24)).toBeCloseTo(1.5, 5);
  });

  it('has the sizes of the tokens in tokens.css (Otto, 4.11.2026: 20 px on the rail as a token of its own)', () => {
    const token = (name: string) => Number(new RegExp(`${name}:\\s*(\\d+)px`, 'u').exec(tokens)?.[1]);
    expect(token('--icon-size')).toBe(ICON_SIZES.standard);
    expect(token('--icon-size-sm')).toBe(ICON_SIZES.small);
    expect(token('--icon-size-rail')).toBe(20);
    expect(token('--icon-size-rail')).toBe(ICON_SIZES.rail);
  });

  it('keeps its distance from a text only when it is told to', () => {
    expect(render('DownloadIcon')).not.toContain('icon-lead');
    expect(render('DownloadIcon', { lead: true })).toContain('icon-lead');
  });

  it.each(NAMES)('%s is used by the interface', (name) => {
    const used = Object.values(SOURCES).some((text) => new RegExp(`\\b${name}\\b`, 'u').test(text));
    expect(used).toBe(true);
  });
});
