// @vitest-environment jsdom
//
// Review finding on M3-17: the original files download straight from the
// source at the "Katalogeintrag" licence tier (KLAERUNGEN B11: "Link bzw.
// Weiterleitung zum Download bei der Quelle" is already what that tier
// permits, no "Processing" tier needed) — but the attribution the licence
// still requires has to actually reach the dialog, next to the links, not
// only exist as text somewhere in `download.ts`. This mounts the real
// component (not just its pure helpers, already covered in
// `download.test.ts`) to prove it renders.

import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { useAppStore } from '../store';
import DownloadDialog from './DownloadDialog';

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
});

afterEach(() => {
  act(() => {
    root.unmount();
  });
  container.remove();
});

function show(): HTMLElement {
  act(() => {
    root.render(<DownloadDialog />);
  });
  return container;
}

describe('the originals dialog shows attribution and terms next to the links', () => {
  beforeEach(() => {
    useAppStore.setState({
      datasets: [
        {
          id: 'sentinel-2-c1-l2a',
          title: 'Sentinel-2 L2A',
          viewable: true,
          groupBy: ['datetime'],
          zoom: { min: 0, max: 19 },
          collection: {
            id: 'sentinel-2-c1-l2a',
            title: 'Sentinel-2 L2A',
            'earthx:format': 'cog',
            'earthx:license_flags': {
              spdx_id: null,
              name: 'Sentinel Data Legal Notice',
              url: 'https://example.org/legal-notice',
              commercial_use: true,
              distribution: true,
              derivatives: true,
              share_alike: false,
              attribution_required: true,
              tier: 'catalog',
              attribution_modified: 'Contains modified Copernicus Sentinel data {year}',
              attribution_unmodified: 'Copernicus Sentinel data {year}',
              terms_url: 'https://example.org/legal-notice',
              terms_notice: { en: 'Subject to {terms_url}.' },
            },
          },
        },
      ],
      datasetId: 'sentinel-2-c1-l2a',
      downloadDialogLayerId: null,
      downloadSelection: true,
      downloadOutcome: 'originals',
      downloadSkippedGroupsNotice: null,
      downloadOriginalLinks: [
        { itemId: 'S1', groupLabel: 'Overpass A', asset: 'visual', href: 'https://data.test/S1.tif' },
      ],
      downloading: false,
      error: null,
      notice: null,
    });
  });

  it('shows the unmodified attribution text (not the modified one), never a licence-tier gate', () => {
    const el = show();
    const text = el.textContent ?? '';
    expect(text).toContain('Copernicus Sentinel data');
    expect(text).not.toContain('Contains modified Copernicus Sentinel data');
    // Katalogeintrag: B11 already permits a link at this tier — no
    // "licence does not permit a data export" message, no disabled Download
    // button gate as the crop view has.
    expect(text).not.toContain('does not permit a data export');
  });

  it('shows the terms notice and the terms URL', () => {
    const el = show();
    expect(el.textContent).toContain('Subject to https://example.org/legal-notice.');
  });

  it('renders each original file as its own clickable, direct link', () => {
    const el = show();
    const link = el.querySelector<HTMLAnchorElement>('a[href="https://data.test/S1.tif"]');
    expect(link).not.toBeNull();
    expect(link?.getAttribute('download')).not.toBeNull();
    expect(link?.getAttribute('rel')).toContain('noopener');
    expect(link?.textContent).toContain('S1');
    expect(link?.textContent).toContain('visual');
  });

  it('loading (fetch for a pinned layer still in flight) says so instead of an empty list', () => {
    useAppStore.setState({ downloadOriginalLinks: null });
    const el = show();
    expect(el.textContent).toContain('Loading the original files');
  });

  it('no reachable link at all says so, plainly, rather than showing nothing', () => {
    useAppStore.setState({ downloadOriginalLinks: [] });
    const el = show();
    expect(el.textContent).toContain('No original file');
  });
});
