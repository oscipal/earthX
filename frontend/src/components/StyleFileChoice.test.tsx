// @vitest-environment jsdom

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useAppStore } from '../store';
import StyleFileChoice, { STYLE_FILE_TIP } from './StyleFileChoice';

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}

let container: HTMLDivElement;
let root: Root;

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  container = document.createElement('div');
  document.body.append(container);
  root = createRoot(container);
  useAppStore.setState({ downloadStyleFormat: 'qml' });
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  useAppStore.getState().setDownloadStyleFormat('qml');
});

const show = (disabled = false) => {
  act(() => root.render(<StyleFileChoice disabled={disabled} />));
  return container.querySelector<HTMLSelectElement>('select')!;
};

describe('"Style file" of the download dialog (M5-64 §12)', () => {
  it('offers QGIS, SLD and none, QGIS first and chosen', () => {
    const select = show();
    expect(container.querySelector('label')?.textContent).toBe('Style file');
    expect([...select.options].map((option) => [option.value, option.textContent])).toEqual([
      ['qml', 'QGIS (.qml)'],
      ['sld', 'SLD'],
      ['none', 'None'],
    ]);
    expect(select.value).toBe('qml');
  });

  it('keeps the choice in the store and in the browser, for downloads without a dialog', () => {
    const select = show();
    act(() => {
      select.value = 'sld';
      select.dispatchEvent(new Event('change', { bubbles: true }));
    });
    expect(useAppStore.getState().downloadStyleFormat).toBe('sld');
    expect(localStorage.getItem('earthx.stylefile')).toBe('sld');
  });

  it('says in its tooltip, not as a text, what SLD does with an RGB image', () => {
    show();
    expect(container.querySelector('.dialog-style-file')?.getAttribute('data-tip')).toBe(STYLE_FILE_TIP);
    expect(STYLE_FILE_TIP).toContain('RGB image');
    expect(container.textContent).toBe('Style fileQGIS (.qml)SLDNone');
  });

  it('is locked while a download runs', () => {
    expect(show(true).disabled).toBe(true);
  });
});
