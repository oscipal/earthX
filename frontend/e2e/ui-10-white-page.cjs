// UI-10 (Otto, 16.11.2026): a white page after a search of Sentinel-2 with a cloud range and ticked scenes, in a real browser. The map
// drew the quicklooks of the ticked scenes as image sources, whose `tiles` are an object, and the mark "Overview" (`overviewMark.ts`)
// called `tiles.some` on it in every event of the map: the error rose into the change of the layers and React left a white page.
// The flow, as a user does it, in the light and the dark theme:
//   1. choose "Sentinel-2 L2A", set "Cloud cover, to" to 30 in "Advanced search", search;
//   2. tick the scenes in the list (their quicklooks are drawn on the map), zoom the map;
//   3. "Crop to AOI", add the view to the layers and remove that layer again;
// after each step: no error of the page and none in the console, the map is still there, no note "ran into an error".
// The search asks for the cloud range. A screenshot per step and theme. Red on the state before UI-10 ("tiles?.some is not a function",
// the page white at "Crop and merge to AOI"); with only the guard of the map events (`mapGuard.ts`) the flow goes through and the
// error is logged; green with the fix.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/ui-10-white-page.cjs           # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-ui-10');
const THEMES = { light: 'normal', dark: 'tech' };
const S2 = 'sentinel-2-c1-l2a';

// A quicklook of 64 px in one colour, as the source publishes a JPEG thumbnail beside the data.
const PNG = (() => {
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 64 }, () => [40, 160, 90, 255]).flat())]);
  const chunk = (type, data) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, 'ascii');
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(64, 0);
  header.writeUInt32BE(64, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: 64 }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
})();

const CLOUD_FILTER = { property: 'eo:cloud_cover', kind: 'range', title: 'Cloud cover', description: 'Share of the whole scene covered by clouds.', unit: '%', within_aoi: null, group: 'Clouds', type: 'number', minimum: 0, maximum: 100 };
const COLLECTION = {
  id: S2, type: 'Collection', title: 'Sentinel-2 L2A', description: 'made up', license: 'proprietary', links: [],
  extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2015-06-27T00:00:00Z', null]] } },
  'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { roi: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, time_range: true, single_coverage_product: false },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:search_filters': [CLOUD_FILTER],
};
const polygon = (b) => ({ type: 'Polygon', coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] });
// Four tiles of 110 km in UTM zone 32N, side by side, placed by `proj:transform` as the quicklooks of Sentinel-2 are (`quicklookCoords`).
const SCENES = [0, 1, 2, 3].map((i) => {
  const bbox = [9 + i * 0.6, 46, 10.4 + i * 0.6, 47];
  const west = 500000 + i * 46000;
  return {
    type: 'Feature', stac_version: '1.0.0', id: `S2_SCENE_${i}`, collection: S2, bbox, geometry: polygon(bbox),
    properties: { datetime: `2026-07-${String(10 + i).padStart(2, '0')}T10:00:00Z`, 'eo:cloud_cover': 5 + i * 6, 'proj:code': 'EPSG:32632' },
    assets: {
      thumbnail: { href: `${BASE}/thumbnails/${i}.png`, type: 'image/png', roles: ['thumbnail'] },
      visual: { href: `https://assets.example.org/${i}.tif`, type: 'image/tiff; application=geotiff; profile=cloud-optimized', roles: ['visual'], 'proj:transform': [10, 0, west, 0, -10, 5200020], 'proj:shape': [10980, 10980] },
    },
    links: [],
  };
});

async function run(browser, theme) {
  const problems = [];
  const searches = [];
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  page.on('console', (message) => {
    if (message.type() === 'error' && !/Failed to load resource/.test(message.text())) problems.push(`console: ${message.text().slice(0, 200)}`);
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: [COLLECTION] });
    if (url.pathname === '/stac/search') {
      searches.push(JSON.parse(route.request().postData() ?? '{}'));
      return json({ type: 'FeatureCollection', features: SCENES, numberMatched: SCENES.length, numberReturned: SCENES.length, links: [] });
    }
    if (url.pathname.startsWith('/thumbnails/') || url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (url.pathname.includes('/statistics')) return json({ visual_b1: { min: 0, max: 255, percentile_2: 10, percentile_98: 240, count: 9 } });
    return json({ detail: 'not made up' }, 404);
  });

  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${theme}_${step}.png`) });
  const healthy = async (step) => {
    await page.waitForTimeout(600);
    if ((await page.locator('.maplibregl-canvas').count()) === 0) problems.push(`${step}: the map is gone`);
    if ((await page.locator('.error-note').count()) > 0) problems.push(`${step}: the page shows "ran into an error"`);
    if ((await page.locator('#root').innerHTML()).trim() === '') problems.push(`${step}: the page is white`);
    await shot(step);
  };

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await page.locator('.dataset-toggle', { hasText: 'Sentinel-2 L2A' }).first().click();
  await page.locator('.advanced-btn').click();
  await page.locator('.advanced-popup input[aria-label="Cloud cover, to"]').fill('30');
  await page.locator('.advanced-popup .advanced-top .close-x').click();
  // The AOI as a drawn rectangle leaves it (`store.setAoi`); the drawing itself is not what this checks.
  await page.evaluate(async (aoi) => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().setAoi(aoi, null);
    useAppStore.getState().flyTo([9, 46, 11.8, 47]);
  }, polygon([9.2, 46.2, 11.5, 46.8]));
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.waitForSelector('.results-panel .result-row');
  const asked = JSON.stringify(searches.at(-1)?.query_by_collection ?? {});
  if (!asked.includes('"eo:cloud_cover":{"lte":30}')) problems.push(`the search did not ask the cloud range: ${asked}`);
  await healthy('1-searched');

  await page.getByText(/^Select all/).click();
  await page.waitForTimeout(1500);
  const map = await page.evaluateHandle(() => {
    const el = document.querySelector('.maplibregl-map');
    let fiber = el[Object.keys(el).find((k) => k.startsWith('__reactFiber$'))];
    for (; fiber; fiber = fiber.return) {
      for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
        const held = hook.memoizedState?.current;
        if (held && typeof held.getStyle === 'function') return held;
      }
    }
    return null;
  });
  // The quicklooks on the map: image sources, whose `tiles` are no list of URLs.
  const drawn = await page.evaluate((m) => (m ? m.getLayersOrder().filter((id) => m.getSource(m.getLayer(id).source)?.type === 'image').length : null), map);
  if (!drawn) problems.push('no quicklook drawn as an image source: the flow does not reach the case of the error');
  await healthy('2-ticked');
  await page.mouse.move(800, 400);
  await page.mouse.wheel(0, -400);
  await healthy('3-zoomed');

  await page.getByRole('button', { name: /^Crop (and merge )?to AOI$/ }).click();
  await healthy('4-view');
  const add = page.getByRole('button', { name: 'Add to layers', exact: true }).first();
  if ((await add.count()) === 0) problems.push('no button that adds the view to the layers');
  else {
    await add.click();
    await healthy('5-added');
    await page.locator('.app-rail button[aria-label^="Layers"]').click();
    const remove = page.locator('button[aria-label="Remove layer"]:visible').first();
    if ((await remove.count()) === 0) problems.push('no button "Remove layer"');
    else {
      await remove.click();
      await healthy('6-removed');
    }
  }
  await context.close();
  return { problems, drawn };
}

(async () => {
  const browser = await chromium.launch();
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    const { problems, drawn } = await run(browser, theme);
    console.log(`${theme}: ${problems.length === 0 ? 'ok' : 'FAILED'}${drawn === null ? '' : ` (quicklooks drawn: ${drawn})`}`);
    for (const problem of [...new Set(problems)]) console.log(`  - ${problem}`);
    failed ||= problems.length > 0;
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
