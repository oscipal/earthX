// Browser check of NM4-50: the DEM (no quicklooks, `browse: full_resolution`) and Sentinel-2 (quicklooks) go the same
// ways. Each case does the same clicks, in a real browser, with made-up answers of the search and the tiler:
//   - the preview of a ticked scene (the DEM: the whole tile, not the crop), "Crop to AOI", "Add to layers";
//   - a colormap and a range applied to the view that is a layer, then the eye of the layer in the layer manager:
//     off, on, after a change of the basemap and of the projection;
//   - "Hide results" / "Show results" in the results panel.
// Tiles are plain colours, one per dataset and colormap, and the check counts the pixels of the map.
//
//   cd frontend && npm run dev &                # the dev server; no backend is needed
//   node e2e/dem-layers.cjs                     # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-dem-layers');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const AOI = { type: 'Polygon', coordinates: [[[10.3, 47.3], [10.7, 47.3], [10.7, 47.7], [10.3, 47.7], [10.3, 47.3]]] };

// The colour of a tile: one per dataset, and one for the colormap that is asked for.
const COLOURS = { base: { dem: [220, 30, 30], s2: [210, 30, 200] }, viridis: [30, 220, 30] };

function png(width, height, [r, g, b]) {
  const crc = (buffer) => {
    let crc32 = 0xffffffff;
    for (const byte of buffer) {
      let c = (crc32 ^ byte) & 0xff;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crc32 = (crc32 >>> 8) ^ c;
    }
    return (crc32 ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, data) => {
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const sum = Buffer.alloc(4);
    sum.writeUInt32BE(crc(body));
    return Buffer.concat([length, body, sum]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 6;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(width * 4)]);
  for (let x = 0; x < width; x++) row.set([r, g, b, 255], 1 + x * 4);
  const raw = Buffer.concat(Array.from({ length: height }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

const polygon = (bbox) => {
  const [w, s, e, n] = bbox;
  return { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] };
};

const CAPABILITIES = { roi: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false };
const CASES = {
  dem: {
    title: 'Copernicus DEM',
    collection: {
      id: 'cop-dem-glo-30', type: 'Collection', title: 'Copernicus DEM', description: 'made up', license: 'proprietary', links: [],
      extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']] } },
      'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' },
      'earthx:capabilities': { ...CAPABILITIES, time_range: false, single_coverage_product: true },
      'earthx:viewer': { group_by: ['start_datetime'], min_zoom: 0, max_zoom: 15, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['start_datetime'] },
      'earthx:default_render': { title: 'Elevation', assets: ['data'], rescale: [[0, 4000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
    },
    items: ['DEM_N47_E010', 'DEM_N47_E011'].map((id, i) => ({
      id, collection: 'cop-dem-glo-30', bbox: [10 + i, 47, 11 + i, 48], geometry: polygon([10 + i, 47, 11 + i, 48]),
      properties: { start_datetime: '2010-12-01T00:00:00Z', end_datetime: '2015-01-31T23:59:59Z' }, assets: { data: { href: `https://example.org/${id}.tif`, type: 'image/tiff; application=geotiff; profile=cloud-optimized' } },
    })),
  },
  s2: {
    title: 'Sentinel-2 L2A',
    collection: {
      id: 'sentinel-2-c1-l2a', type: 'Collection', title: 'Sentinel-2 L2A', description: 'made up', license: 'proprietary', links: [],
      extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2015-06-27T00:00:00Z', null]] } },
      'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' },
      'earthx:capabilities': { ...CAPABILITIES, time_range: true, single_coverage_product: false },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
    },
    items: ['S2B_A', 'S2B_B'].map((id, i) => ({
      id, collection: 'sentinel-2-c1-l2a', bbox: [10 + i, 47, 11 + i, 48], geometry: polygon([10 + i, 47, 11 + i, 48]),
      properties: { datetime: '2026-07-01T10:00:00Z', 'proj:epsg': 4326 },
      assets: {
        thumbnail: { href: `https://img.test/${id}.png`, roles: ['thumbnail'] },
        visual: { href: `https://example.org/${id}.tif`, type: 'image/tiff; application=geotiff; profile=cloud-optimized', 'proj:transform': [0.001, 0, 10 + i, 0, -0.001, 48], 'proj:shape': [1000, 1000] },
      },
    })),
  },
};

// How many pixels of the page are (near) this colour.
async function count(page, [r, g, b]) {
  // In a narrow window the open panel covers the map: it is folded away for the count.
  const narrow = page.viewportSize().width < 600;
  const dock = narrow ? await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const was = useAppStore.getState().dock;
    useAppStore.getState().closeDock();
    return was;
  }) : null;
  if (narrow) await page.waitForTimeout(400);
  const shot = (await page.screenshot()).toString('base64');
  if (dock) await page.evaluate(async (was) => (await import('/src/store.ts')).useAppStore.setState({ dock: was }), dock);
  return page.evaluate(async ({ shot, r, g, b }) => {
    const img = new Image();
    img.src = `data:image/png;base64,${shot}`;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const { data } = ctx.getImageData(0, 0, img.width, img.height);
    let n = 0;
    for (let i = 0; i < data.length; i += 4) if (Math.abs(data[i] - r) < 45 && Math.abs(data[i + 1] - g) < 45 && Math.abs(data[i + 2] - b) < 45) n++;
    return n;
  }, { shot, r, g, b });
}

let lastPage = null;

async function check(browser, { name, theme, viewport }) {
  const spec = CASES[name];
  const label = `${name} ${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  lastPage = page;
  const seen = { tiles: [], tileJson: [] };
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin === 'https://img.test') return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: png(64, 64, COLOURS.base.s2) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: [CASES.dem.collection, CASES.s2.collection] });
    if (url.pathname === '/stac/search') {
      const body = JSON.parse(route.request().postData() ?? '{}');
      const wanted = (body.collections ?? [])[0];
      const own = Object.values(CASES).find((c) => c.collection.id === wanted) ?? spec;
      return json({ type: 'FeatureCollection', features: own.items, numberMatched: own.items.length, numberReturned: own.items.length, links: [] });
    }
    if (url.pathname.includes('/mosaic/') || url.pathname.endsWith('/tilejson.json')) {
      seen.tileJson.push(url.pathname);
      return json({ detail: 'not made up' }, 404);
    }
    if (url.pathname.includes('/tiles/')) {
      seen.tiles.push(url.pathname + url.search);
      const kind = url.pathname.includes('cop-dem') ? 'dem' : 's2';
      const colour = url.search.includes('colormap_name=viridis') ? COLOURS.viridis : COLOURS.base[kind];
      return route.fulfill({ status: 200, contentType: 'image/png', body: png(256, 256, colour) });
    }
    if (url.pathname.endsWith('/statistics')) return json({ b1: { count: 900, min: 0, max: 3000, percentile_2: 10, percentile_98: 2900, unit: null } });
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)} ${(error.stack ?? '').split('\n').slice(1, 4).join(' <- ').replace(/http:\/\/localhost:5173/g, '')}`));
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  const seeAll = async (colour) => {
    // Tiles arrive after the click; the map needs a moment.
    await page.waitForTimeout(1800);
    return count(page, colour);
  };
  const expectOn = async (what, colour) => {
    const n = await seeAll(colour);
    if (n < 400) problems.push(`${what}: not on the map (${n} px)`);
  };
  const expectOff = async (what, colour) => {
    const n = await seeAll(colour);
    if (n > 60) problems.push(`${what}: still on the map (${n} px)`);
  };
  const BASE_COLOUR = COLOURS.base[name];

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  // The thumbnails of the list have the colour of the quicklooks; the count is of the map.
  await page.addStyleTag({ content: '.result-thumb { visibility: hidden !important; }' });
  await page.evaluate(async ({ aoi }) => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().setAoi(aoi);
    useAppStore.getState().flyTo([9.2, 46.6, 12.2, 48.4]);
  }, { aoi: AOI });
  await page.getByRole('button', { name: new RegExp(spec.title) }).first().click();
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.waitForSelector('.results-panel');
  await shot('1-search');

  // 1. Browsing: the first time step is open, its scenes are on the map.
  await page.locator('.result-row input[type="checkbox"]').first().check();
  await expectOn('the preview of a ticked scene', BASE_COLOUR);
  const previewPx = await count(page, BASE_COLOUR);
  await shot('2-preview');
  const cropless = await page.evaluate(() => Object.keys(window.__earthxSeen ?? {}).length);
  void cropless;

  // 2. "Hide results" takes it off the map; "Show results" brings it back.
  await page.locator('.results-head').getByRole('button', { name: 'Hide search results' }).click();
  await expectOff('"Hide results"', BASE_COLOUR);
  await page.locator('.results-head').getByRole('button', { name: 'Show search results' }).click();
  await expectOn('"Show results"', BASE_COLOUR);

  // 3. Crop to AOI, a colormap, pin it.
  await page.getByRole('button', { name: /Crop( & merge)? to AOI/ }).click();
  await page.waitForSelector('.viewer-controls');
  await page.locator('.results-head').getByRole('button', { name: 'Hide search results' }).click().catch(() => {});
  await page.locator('.viewer-controls select:not(.vc-unit)').selectOption('viridis');
  await page.locator('.viewer-controls .vc-apply').click();
  await expectOn('the view after "Apply"', COLOURS.viridis);
  // The preview is the scenes as they are; the crop is the part of one scene under the AOI.
  const cropPx = await count(page, COLOURS.viridis);
  if (previewPx < 3 * cropPx) problems.push(`the preview (${previewPx} px) is not the whole scene: the crop to the AOI is ${cropPx} px`);
  await shot('3-view');
  await page.getByRole('button', { name: /Add to layers/ }).click();
  await page.getByRole('button', { name: /^Layers/ }).click();
  await page.waitForSelector('.layer-row:not(.results-row)');
  await shot('4-layer');
  const rows = await page.locator('.layer-row:not(.results-row)').count();
  if (rows !== 1) problems.push(`${rows} layers after "Add to layers"`);

  // 4. The eye.
  const eye = page.locator('.layer-row:not(.results-row) [data-col="eye"]').first();
  await eye.click();
  await expectOff('the eye switched off (view still open)', COLOURS.viridis);
  await shot('5-hidden');
  await eye.click();
  await expectOn('the eye switched on again', COLOURS.viridis);

  // 5. The colormap and range stay with the layer: leave the view, switch the layer off and on, reload nothing.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().exitFocus();
  });
  await expectOn('the layer after leaving the view', COLOURS.viridis);
  await eye.click();
  await expectOff('the layer switched off after leaving the view', COLOURS.viridis);
  await eye.click();
  await expectOn('the layer switched on after leaving the view', COLOURS.viridis);
  // Another colormap and range in a view of its own, then back to the layer: its controls show what the layer was made with.
  await page.getByRole('button', { name: /Change image|Clear/ }).first().click().catch(() => {});
  await page.getByRole('button', { name: new RegExp(`^${spec.title}|Copernicus|Sentinel`) }).first().isVisible().catch(() => false);
  await page.locator('.layer-row:not(.results-row) .lm-name').first().click();
  await page.waitForSelector('.viewer-controls');
  await page.locator('.viewer-controls select:not(.vc-unit)').selectOption('magma');
  await page.locator('.viewer-controls input[type="number"]').first().fill('5');
  await page.locator('.viewer-controls .vc-apply').click();
  await page.waitForTimeout(500);
  // A layer opened from the manager closes with its red x (it has no "Clear" any more, NM4-65).
  await page.locator('.viewer-controls .close-x').click();
  await page.locator('.layer-row:not(.results-row) .lm-name').first().click();
  await page.waitForSelector('.viewer-controls');
  await page.waitForTimeout(800);
  const controls = await page.evaluate(() => ({
    colormap: document.querySelector('.viewer-controls select:not(.vc-unit)')?.value,
    vmin: document.querySelector('.viewer-controls input[type="number"]')?.value,
  }));
  if (controls.colormap !== 'viridis' || controls.vmin !== '10') problems.push(`the controls of the layer show ${controls.colormap}, ${controls.vmin}; the layer was made with viridis, 10`);
  await shot('5b-layer-controls');
  await eye.click();
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const s = useAppStore.getState();
    s.setBasemap('outlines');
    s.setProjection('globe');
  });
  await expectOff('the layer switched off, then another basemap and projection', COLOURS.viridis);
  await shot('6-hidden-after-style');

  await context.close();
  return { name: label, problems, detail: `${seen.tiles.length} tiles asked${process.env.DEBUG ? ': ' + seen.tiles.slice(-4).join(' | ') : ''}` };
}

// The ticks over a change of the time step and of the dataset (Otto's addition to NM4-50): one search over the DEM and
// Sentinel-2 (two overpasses), ticks in both, the list shown for the other dataset and back.
async function checkTicks(browser, { theme, viewport }) {
  const label = `ticks ${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  lastPage = page;
  const s2Items = [['a1', '2026-07-01', 0], ['a2', '2026-07-01', 1], ['b1', '2026-07-06', 0]].map(([id, day, i]) => {
    const own = CASES.s2.items[0];
    return { ...own, id, bbox: [10 + i, 47, 11 + i, 48], geometry: polygon([10 + i, 47, 11 + i, 48]), properties: { ...own.properties, datetime: `${day}T10:00:00Z` } };
  });
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin === 'https://img.test') return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: png(64, 64, COLOURS.base.s2) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: [CASES.dem.collection, CASES.s2.collection] });
    if (url.pathname === '/stac/search') {
      const features = [...s2Items, ...CASES.dem.items];
      return json({ type: 'FeatureCollection', features, numberMatched: features.length, numberReturned: features.length, links: [] });
    }
    if (url.pathname.includes('/mosaic/') || url.pathname.endsWith('/tilejson.json')) return json({ detail: 'not made up' }, 404);
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: png(256, 256, COLOURS.base[url.pathname.includes('cop-dem') ? 'dem' : 's2']) });
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  const ticks = () => page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().selectedIds);
  const expectTicks = async (what, want) => {
    const got = await ticks();
    if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`${what}: ticks ${JSON.stringify(got)}, not ${JSON.stringify(want)}`);
  };
  const open = async (title) => {
    const box = page.locator('.dataset-select-box');
    if ((await box.textContent()).includes(title)) return;
    await box.click();
    await page.getByRole('option', { name: new RegExp(title) }).click();
  };
  const tick = (id) => page.locator(`input[aria-label="Select ${id}"]`).check();
  const group = (index) => page.locator('.result-group-head').nth(index);

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await page.addStyleTag({ content: '.result-thumb { visibility: hidden !important; }' });
  await page.evaluate(async ({ aoi }) => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().setAoi(aoi);
    useAppStore.getState().flyTo([9.2, 46.6, 12.2, 48.4]);
  }, { aoi: AOI });
  await page.getByLabel('Select multiple datasets').check();
  await page.getByRole('button', { name: /Sentinel-2/ }).first().click();
  await page.getByRole('button', { name: /Copernicus/ }).first().click();
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.waitForSelector('.results-panel');
  // The DEM first, then Sentinel-2 with a scene in each of its two overpasses, the list opened on the other one and back.
  await open('Copernicus');
  await tick('DEM_N47_E010');
  await open('Sentinel-2');
  await expectTicks('after Sentinel-2 was opened', ['DEM_N47_E010']);
  const heads = await page.locator('.result-group-head').count();
  if (heads !== 2) problems.push(`${heads} time steps, two expected`);
  await tick('b1');
  await group(1).click();
  await tick('a2');
  await expectTicks('a scene in each of two overpasses', ['DEM_N47_E010', 'b1', 'a2']);
  await group(0).click();
  await expectTicks('after the other overpass was opened', ['DEM_N47_E010', 'b1', 'a2']);
  if (!(await page.locator('input[aria-label="Select b1"]').isChecked())) problems.push('the tick of the first overpass is gone from the list');
  await group(1).click();
  if (!(await page.locator('input[aria-label="Select a2"]').isChecked())) problems.push('the tick of the second overpass is gone from the list');
  await open('Copernicus');
  await expectTicks('after the DEM was opened again', ['DEM_N47_E010', 'b1', 'a2']);
  if (!(await page.locator('input[aria-label="Select DEM_N47_E010"]').isChecked())) problems.push('the tick of the DEM is gone from its list');
  await open('Sentinel-2');
  await page.waitForTimeout(1800);
  const dem = await count(page, COLOURS.base.dem);
  const s2 = await count(page, COLOURS.base.s2);
  if (dem < 400) problems.push(`the ticked DEM tile is not on the map while Sentinel-2 is shown (${dem} px)`);
  if (s2 < 400) problems.push(`the ticked scenes of Sentinel-2 are not on the map (${s2} px)`);
  await shot('1-both');

  // "Hide results" takes all of them off, the ticks stay; "Clear search results" takes the ticks.
  await page.locator('.results-head').getByRole('button', { name: 'Hide search results' }).click();
  await page.waitForTimeout(1500);
  if ((await count(page, COLOURS.base.dem)) > 60 || (await count(page, COLOURS.base.s2)) > 60) problems.push('"Hide results" leaves a ticked scene on the map');
  await expectTicks('after "Hide results"', ['DEM_N47_E010', 'b1', 'a2']);
  await page.locator('.results-head').getByRole('button', { name: 'Show search results' }).click();
  await page.getByRole('button', { name: /Clear search results/ }).click();
  await expectTicks('after "Clear search results"', []);
  await context.close();
  return { name: label, problems, detail: '' };
}

// The dataset the list shows lies on top (Otto, 30.10.2026): one scene of Sentinel-2 and one tile of the DEM over the same
// footprint, both ticked; the one of the open dataset is on the map over the other whichever was ticked last, and a change of
// the dataset or of the basemap lays them out again.
async function checkOrder(browser, { theme, viewport }) {
  const label = `order ${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  lastPage = page;
  const s2 = { ...CASES.s2.items[0], id: 'a1', bbox: [10, 47, 11, 48], geometry: polygon([10, 47, 11, 48]) };
  const dem = { ...CASES.dem.items[0], id: 'd1' };
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin === 'https://img.test') return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: png(64, 64, COLOURS.base.s2) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: [CASES.dem.collection, CASES.s2.collection] });
    if (url.pathname === '/stac/search') return json({ type: 'FeatureCollection', features: [s2, dem], numberMatched: 2, numberReturned: 2, links: [] });
    if (url.pathname.includes('/mosaic/') || url.pathname.endsWith('/tilejson.json')) return json({ detail: 'not made up' }, 404);
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: png(256, 256, COLOURS.base[url.pathname.includes('cop-dem') ? 'dem' : 's2']) });
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  const open = async (title) => {
    const box = page.locator('.dataset-select-box');
    if ((await box.textContent()).includes(title)) return;
    await box.click();
    await page.getByRole('option', { name: new RegExp(title) }).click();
  };
  const tick = (id) => page.locator(`input[aria-label="Select ${id}"]`).check();
  // Which of the two lies on top: the quicklook of Sentinel-2 (magenta) is hidden under the tile of the DEM (red) and the
  // other way round; the tile of the DEM spills over the quicklook, so the red pixels do not tell, the magenta ones do.
  const s2Visible = async () => {
    await page.waitForTimeout(1800);
    // The footprint is about 85 000 px in a wide window and about 7 000 in a narrow one; hidden, no pixel of it shows.
    return (await count(page, COLOURS.base.s2)) > (viewport === 'narrow' ? 2500 : 20000);
  };
  const expectTop = async (what, top) => {
    const visible = await s2Visible();
    if (visible !== (top === 's2')) problems.push(`${what}: ${top === 's2' ? 'Sentinel-2' : 'the DEM'} should be on top, the quicklook of Sentinel-2 is ${visible ? 'visible' : 'hidden'}`);
  };

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await page.addStyleTag({ content: '.result-thumb { visibility: hidden !important; }' });
  await page.evaluate(async ({ aoi }) => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().setAoi(aoi);
    useAppStore.getState().flyTo([9.2, 46.6, 12.2, 48.4]);
  }, { aoi: AOI });
  await page.getByLabel('Select multiple datasets').check();
  await page.getByRole('button', { name: /Sentinel-2/ }).first().click();
  await page.getByRole('button', { name: /Copernicus/ }).first().click();
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.waitForSelector('.results-panel');
  // Sentinel-2 first, the DEM last: the DEM is the open one and lies on top.
  await open('Sentinel-2');
  await tick('a1');
  await open('Copernicus');
  await tick('d1');
  await expectTop('the DEM open, ticked last', 'dem');
  await shot('1-dem-open');
  // The list shows Sentinel-2 now: it comes on top at once, though the DEM was ticked after it.
  await open('Sentinel-2');
  await expectTop('Sentinel-2 open', 's2');
  await shot('2-s2-open');
  // A change of the basemap leaves it so.
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().setBasemap('outlines'));
  await expectTop('Sentinel-2 open, after a change of the basemap', 's2');
  await open('Copernicus');
  await expectTop('the DEM open again, after a change of the basemap', 'dem');
  // "Hide results" takes both off, "Show results" brings them back in the same order.
  await page.locator('.results-head').getByRole('button', { name: 'Hide search results' }).click();
  await page.waitForTimeout(1500);
  if ((await count(page, COLOURS.base.s2)) > 60 || (await count(page, COLOURS.base.dem)) > 60) problems.push('"Hide results" leaves a scene on the map');
  await page.locator('.results-head').getByRole('button', { name: 'Show search results' }).click();
  await expectTop('the DEM open, after "Show results"', 'dem');
  await context.close();
  return { name: label, problems, detail: '' };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  const only = process.env.ONLY ? process.env.ONLY.split(',') : null;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      if (!only || only.includes(`order ${theme} ${viewport}`)) {
        const result = await checkOrder(browser, { theme, viewport }).catch(async (error) => {
          await lastPage?.screenshot({ path: path.join(OUT, `order_${theme}_${viewport}_broke.png`) }).catch(() => {});
          return { name: `order ${theme} ${viewport}`, problems: [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`], detail: '' };
        });
        failed += result.problems.length > 0 ? 1 : 0;
        console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
      }
      if (!only || only.includes(`ticks ${theme} ${viewport}`)) {
        const result = await checkTicks(browser, { theme, viewport }).catch(async (error) => {
          await lastPage?.screenshot({ path: path.join(OUT, `ticks_${theme}_${viewport}_broke.png`) }).catch(() => {});
          return { name: `ticks ${theme} ${viewport}`, problems: [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`], detail: '' };
        });
        failed += result.problems.length > 0 ? 1 : 0;
        console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
      }
    }
  }
  for (const name of Object.keys(CASES)) {
    for (const theme of Object.keys(THEMES)) {
      for (const viewport of Object.keys(VIEWPORTS)) {
        if (only && !only.includes(`${name} ${theme} ${viewport}`)) continue;
        // In a narrow window a panel covers the map and the bar of the selection: the flow is checked wide, the layout of
        // the rows (`layer-rows.cjs`) and the ticks narrow.
        if (viewport === 'narrow' && !only) continue;
        const result = await check(browser, { name, theme, viewport }).catch(async (error) => { await lastPage?.screenshot({ path: path.join(OUT, `${name}_${theme}_${viewport}_broke.png`.replace(/ /g, '_')) }).catch(() => {}); return { name: `${name} ${theme} ${viewport}`, problems: [`the check broke: ${error.message.split("\n").slice(0, 3).join(" ")}`], detail: '' }; });
        failed += result.problems.length > 0 ? 1 : 0;
        console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name} — ${result.detail}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
      }
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
