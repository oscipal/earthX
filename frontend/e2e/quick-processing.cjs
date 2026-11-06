// UI-03d in a real browser (Otto, 2.11.2026): "Quick processing", the histograms of "Scale", the list of colormaps and the actions of a
// layer in the settings bar. In the light and the dark theme, at 1280 x 800 and 360 x 740; a screenshot per case.
//   1. "Quick processing" stands between "Display" and "Actions", three buttons in a row, two rows, all of one width; an index goes into
//      the fields, the button is on, and "Apply" draws it (Otto, 3.11.2026); "Enhance contrast" puts a range for each channel into the fields, is on,
//      and "Apply" draws the three ranges (UI-03e). The view measures over the AOI (`POST …/statistics`), as since UI-03e.
//   2. RGB has three histograms (red, green, blue) with a row of vmin and vmax each; an index has one. Nothing lies outside the bar and
//      nothing scrolls sideways.
//   3. "More…" opens the list of all colormaps in the place of the bar, with previews; a click chooses and goes back, the choice stands in
//      the dropdown; "‹" goes back; Esc closes nothing.
//   4. A pinned layer: no arrows beside its date, "Process", "Download", "Add current view to layers" (in full, two lines) and the bin as
//      wide as the others; it is renamed in the head; the row of the layer manager has a bin and a pencil (Otto, 3.11.2026).
//   "Enhance contrast" is there for RGB only, not beside an index (Otto, 3.11.2026).
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/quick-processing.cjs           # BASE=http://localhost:5173 OUT=<directory for the screenshots>, ONLY=1 for one theme and one window,
//                                           # REAL_COLORMAPS=1 for the list of a running tiler (port 8001) instead of a made-up one
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-quick-processing');
const THEMES = process.env.ONLY ? { light: 'normal' } : { light: 'normal', dark: 'tech' };
const VIEWPORTS = process.env.ONLY ? { hd: { width: 1280, height: 800 } } : { hd: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const FOOTPRINT = [10, 50, 11, 51];
const SCENES = ['SYNTH_A', 'SYNTH_B'];
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
const PRESETS = [
  ['NDVI', 'Normalized Difference Vegetation Index', '(nir - red) / (nir + red)', 'rdylgn', '(N - R)/(N + R)'],
  ['NDWI', 'Normalized Difference Water Index', '(green - nir) / (green + nir)', 'rdbu', '(G - N) / (G + N)'],
  ['NDSI', 'Normalized Difference Snow Index', '(green - swir16) / (green + swir16)', 'rdbu', '(G - S1) / (G + S1)'],
  ['NBR', 'Normalized Burn Ratio', '(nir - swir22) / (nir + swir22)', 'rdylgn', '(N - S2) / (N + S2)'],
  ['EVI', 'Enhanced Vegetation Index', '2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)', 'rdylgn', 'g * (N - R) / (N + C1 * R - C2 * B + L)'],
].map(([name, title, expression, colormap_name, formula]) => ({ name, title, expression, rescale: [[-1, 1]], colormap_name, formula, reference: 'https://example.org/formula' }));

// A bell of 64 bins from `low` to `high`, as rio-tiler writes a histogram.
const bell = (low, high, centre) => {
  const edges = Array.from({ length: 65 }, (_, i) => low + ((high - low) * i) / 64);
  const counts = Array.from({ length: 64 }, (_, i) => Math.round(1000 * Math.exp(-(((i - centre) / 9) ** 2))));
  return [counts, edges];
};
const band = (low, high, centre) => ({ min: low, max: high, percentile_2: low + (high - low) * 0.1, percentile_98: low + (high - low) * 0.8, histogram: bell(low, high, centre) });
const VISUAL = { b1: band(0, 2000, 20), b2: band(0, 2500, 28), b3: band(0, 3000, 36) };
const INDEX = { NDVI: band(-0.4, 0.9, 40) };
// The answer of `POST /collections/{dataset}/statistics`, by which the view measures over the AOI since UI-03e: the same bands, by name,
// with `minimum`/`maximum` in the place of `min`/`max`. The order of a band math step asks for the index, any other for the bands.
const areaAnswer = (byBand) => ({
  bands: Object.entries(byBand).map(([name, { min, max, ...rest }]) => ({ name, unit: null, statistics: { minimum: min, maximum: max, mean: (min + max) / 2, valid_percent: 100, ...rest } })),
  exact: true,
  factor: 1,
});
const strip = (from, to) => Array.from({ length: 16 }, (_, i) => `#${[0, 1, 2].map((c) => Math.round(from[c] + ((to[c] - from[c]) * i) / 15).toString(16).padStart(2, '0')).join('')}`);
const entry = (name, from, to) => ({ name, reversed: `${name}_r`, colors: strip(from, to) });
const COLORMAPS = {
  groups: [
    { name: 'sequential', colormaps: [entry('viridis', [68, 1, 84], [253, 231, 36]), entry('magma', [0, 0, 4], [252, 253, 191]), entry('rocket', [3, 5, 26], [250, 235, 221]), entry('mako', [11, 4, 5], [222, 245, 229]), entry('gray', [0, 0, 0], [255, 255, 255])] },
    { name: 'diverging', colormaps: [entry('rdylgn', [165, 0, 38], [0, 104, 55]), entry('rdbu', [103, 0, 31], [5, 48, 97])] },
    { name: 'other', colormaps: [entry('terrain', [51, 51, 153], [255, 255, 255]), entry('jet', [0, 0, 128], [128, 0, 0])] },
  ],
};

async function open(browser, theme, viewport) {
  const { width, height } = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    // REAL_COLORMAPS=1: the list of a tiler that runs behind the dev server (`/colormaps` is proxied to it).
    if (url.pathname === '/colormaps') return process.env.REAL_COLORMAPS ? route.continue() : json(COLORMAPS);
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': SCENES });
    if (route.request().method() === 'POST' && url.pathname.endsWith('/statistics')) {
      const order = JSON.parse(route.request().postData() ?? '{}');
      return json(areaAnswer(order.steps?.some((step) => step.op === 'band_math') ? INDEX : VISUAL));
    }
    if (url.pathname.includes('/statistics')) return json(url.search.includes('op=band_math') ? INDEX : VISUAL);
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  return { context, page, problems };
}

async function seed(page) {
  await page.evaluate(async ({ scenes, footprint, presets }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 8, maxZoom: 14 });
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const aoi = { type: 'Polygon', coordinates: [[[10.2, 50.2], [10.8, 50.2], [10.8, 50.8], [10.2, 50.8], [10.2, 50.2]]] };
    const tiff = (n) => ({ href: 'https://example.org/x.tif', type: COG, 'raster:bands': Array.from({ length: n }, () => ({ data_type: 'uint16', nodata: 0 })) });
    const items = scenes.map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { visual: tiff(3), B04: tiff(1), B08: tiff(1) } }));
    const collection = {
      id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:true_color': ['red', 'green', 'blue'], 'earthx:auxiliary_assets': ['visual'],
      'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
      'earthx:index_presets': presets,
    };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', items, groups: [{ key: ['a'], label: '2026-07-01', items }], activeGroupIndex: 0,
      selectedIds: scenes, downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: true, viewAoi: aoi, aoi, showDownloaded: true, dock: null,
      appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', pendingChannels: [], pendingIndex: '', pendingBand: '', enhance: null,
      layers: [], mosaics: {}, error: null, mapZoom: 12, flyToView: { center: [10.5, 50.5], zoom: 10 },
    });
    await useAppStore.getState().loadMosaics();
  }, { scenes: SCENES, footprint: FOOTPRINT, presets: PRESETS });
  await page.waitForSelector('.inspector .vc-quick');
}

const settle = (page) => page.waitForTimeout(500);
const store = (page, pick) => page.evaluate(async (source) => {
  const { useAppStore } = await import('/src/store.ts');
  return new Function('s', `return (${source})(s)`)(useAppStore.getState());
}, pick.toString());

// What lies outside the open bar, and whether it scrolls sideways.
const bounds = (page, selector) =>
  page.evaluate((sel) => {
    const bar = document.querySelector(sel);
    const base = bar.getBoundingClientRect();
    const body = bar.querySelector('.insp-body');
    return {
      bar: { x: Math.round(base.x), y: Math.round(base.y), w: Math.round(base.width), h: Math.round(base.height) },
      sideways: body.scrollWidth > body.clientWidth + 1 || document.documentElement.scrollWidth > window.innerWidth + 1,
      outside: [...bar.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > base.right + 1 || r.left < base.left - 1); }).map((e) => e.className || e.tagName).slice(0, 4),
    };
  }, selector);

async function runCase(browser, theme, viewport, results) {
  const { context, page, problems } = await open(browser, theme, viewport);
  const tag = `${theme}-${viewport}`;
  const fail = (what) => problems.push(what);
  const shot = (name) => page.screenshot({ path: path.join(OUT, `${tag}-${name}.png`) });
  try {
    await seed(page);
    await settle(page);
    // 1, 2: the colour picture.
    const quick = await page.$$eval('.inspector .vc-quick button', (bs) => bs.map((b) => { const r = b.getBoundingClientRect(); return { text: b.textContent, x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width) }; }));
    if (quick.map((b) => b.text).join('|') !== 'NDVI|NDWI|NDSI|NBR|EVI|Enhance contrast') fail(`quick buttons: ${quick.map((b) => b.text)}`);
    if (new Set(quick.map((b) => b.y)).size !== 2 || new Set(quick.map((b) => b.w)).size !== 1) fail(`quick rows/widths: ${JSON.stringify(quick)}`);
    const headings = await page.$$eval('.inspector .insp-heading', (hs) => hs.map((h) => h.textContent));
    if (headings.join('|') !== 'Display|Quick processing|Actions') fail(`headings: ${headings}`);
    await page.waitForSelector('.inspector .range-hist-blue');
    const hists = await page.$$eval('.inspector .range-hist', (hs) => hs.map((h) => h.className));
    if (hists.length !== 3) fail(`histograms of RGB: ${hists}`);
    if ((await page.$$('.inspector .vc-num input')).length !== 6) fail('RGB has not six fields');
    let b = await bounds(page, 'aside.inspector:not(.colormap-picker)');
    if (b.sideways || b.outside.length) fail(`rgb: ${JSON.stringify(b)}`);
    await shot('rgb');
    // "Enhance contrast" fills the fields like an index; "Apply" draws them (Otto, UI-03e, 3.11.2026).
    await page.locator('.inspector .vc-quick button', { hasText: 'Enhance contrast' }).click();
    await settle(page);
    if ((await store(page, (s) => s.appliedRender.rescale)) !== '0,3000') fail('"Enhance contrast" drew before "Apply"');
    await page.locator('.inspector .vc-apply').click();
    await settle(page);
    const enhanced = await store(page, (s) => s.appliedRender.rescale);
    if (!enhanced || enhanced.split(';').length !== 3) fail(`enhance: ${enhanced}`);
    if ((await page.getAttribute('.inspector .vc-quick button:has-text("Enhance contrast")', 'aria-pressed')) !== 'true') fail('enhance not on');
    await shot('enhanced');
    // An index: into the fields, the button on, one histogram; drawn with "Apply" (Otto, 3.11.2026).
    await page.locator('.inspector .vc-quick button', { hasText: 'NDVI' }).click();
    await settle(page);
    if ((await store(page, (s) => s.appliedRender.index)) === 'NDVI') fail('NDVI drawn before "Apply"');
    await page.locator('.inspector .vc-apply').click();
    await settle(page);
    if ((await store(page, (s) => s.appliedRender.index)) !== 'NDVI') fail('NDVI not drawn with "Apply"');
    if ((await page.$$('.inspector .range-hist')).length !== 1) fail('index has not one histogram');
    if ((await page.getAttribute('.inspector .vc-quick button:has-text("NDVI")', 'aria-pressed')) !== 'true') fail('NDVI not on');
    // "Enhance contrast" is for RGB only (Otto, 3.11.2026).
    if ((await page.locator('.inspector .vc-quick button', { hasText: 'Enhance contrast' }).count()) !== 0) fail('"Enhance contrast" beside an index');
    b = await bounds(page, 'aside.inspector:not(.colormap-picker)');
    if (b.sideways || b.outside.length) fail(`index: ${JSON.stringify(b)}`);
    await shot('index');
    // 3: the list of colormaps.
    const barBefore = b.bar;
    await page.locator('.inspector .vc-colormap select').selectOption({ label: 'More…' });
    await page.waitForSelector('aside.colormap-picker .cm-item');
    const p = await bounds(page, 'aside.colormap-picker');
    if (p.sideways || p.outside.length) fail(`picker: ${JSON.stringify(p)}`);
    if (viewport === 'hd' && (p.bar.x !== barBefore.x || p.bar.w !== barBefore.w)) fail(`picker not in the place of the bar: ${JSON.stringify([p.bar, barBefore])}`);
    await page.keyboard.press('Escape');
    if (!(await page.$('aside.colormap-picker'))) fail('Esc closed the list');
    await shot('colormaps');
    await page.locator('aside.colormap-picker .cm-item', { hasText: 'rocket' }).click();
    await settle(page);
    if (await page.$('aside.colormap-picker')) fail('the list stayed after a choice');
    if ((await page.inputValue('.inspector .vc-colormap select')) !== 'rocket') fail('rocket not in the dropdown');
    await page.locator('.inspector .vc-colormap .vc-reverse').click();
    if ((await store(page, (s) => s.pendingColormapName)) !== 'rocket_r') fail('reverse did not give rocket_r');
    await page.locator('.inspector .vc-colormap select').selectOption({ label: 'More…' });
    await page.waitForSelector('aside.colormap-picker .icon-btn[aria-label="Back"]');
    await page.locator('aside.colormap-picker .icon-btn[aria-label="Back"]').click();
    if (await page.$('aside.colormap-picker')) fail('"‹" did not go back');
    // 4: a pinned layer.
    await page.evaluate(async () => {
      const { useAppStore } = await import('/src/store.ts');
      useAppStore.getState().chooseViewIndex(null);
      await useAppStore.getState().applyRender();
      useAppStore.getState().addCurrentToLayers();
      await new Promise((r) => setTimeout(r, 500));
      const [layer] = useAppStore.getState().layers;
      useAppStore.getState().exitFocus();
      useAppStore.getState().selectLayer(layer.id);
    });
    await page.waitForSelector('.inspector button[aria-label="Rename layer"]');
    if ((await page.$$('.inspector .insp-row2 button[aria-label$=" image"]')).length !== 0) fail('arrows beside the date of a layer');
    const actions = await page.$$eval('.inspector .vc-actions > *', (as) => as.map((a) => a.textContent || a.getAttribute('aria-label')));
    if (actions.join('|') !== 'Process|Download|Add current view to layers|Remove layer') fail(`layer actions: ${actions}`);
    // Otto, 3.11.2026: the bin as wide as the others, the copy read in full (two lines).
    const sizes = await page.$$eval('.inspector .vc-actions > *', (as) => as.map((a) => ({ w: Math.round(a.getBoundingClientRect().width), cut: a.scrollWidth > a.clientWidth + 1 || a.scrollHeight > a.clientHeight + 1 })));
    if (sizes[3].w !== sizes[0].w) fail(`the bin is ${sizes[3].w} px wide, "Process" ${sizes[0].w}`);
    if (sizes[2].cut) fail('"Add current view to layers" is cut');
    // The row of the layer manager: a bin and a pencil.
    await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: 'layers' }));
    await page.waitForSelector('.layer-row [data-col="rename"]');
    if ((await page.getAttribute('.layer-row [data-col="remove"]', 'aria-label')) !== 'Remove layer' || (await page.locator('.layer-row [data-col="remove"] svg').count()) !== 1) fail('no bin in the row of the layer manager');
    await shot('manager');
    await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: null }));
    b = await bounds(page, 'aside.inspector:not(.colormap-picker)');
    if (b.sideways || b.outside.length) fail(`layer: ${JSON.stringify(b)}`);
    await page.locator('.inspector button[aria-label="Rename layer"]').click();
    await page.fill('.inspector input[aria-label="Layer name"]', 'River bend');
    await page.keyboard.press('Enter');
    if ((await store(page, (s) => s.layers[0].name)) !== 'River bend') fail('rename');
    await shot('layer');
  } catch (error) {
    fail(`stopped: ${error.message.split('\n')[0]}`);
    await shot('stopped').catch(() => undefined);
  }
  results.push({ tag, problems: [...problems] });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) await runCase(browser, theme, viewport, results);
  await browser.close();
  for (const { tag, problems } of results) console.log(`${tag}: ${problems.length === 0 ? 'ok' : problems.join('; ')}`);
  console.log(`screenshots in ${OUT}`);
  process.exit(results.every((r) => r.problems.length === 0) ? 0 : 1);
})();
