// UI-03e (Otto, 3.11.2026, zu #282) in a real browser, with made-up scenes and no backend:
//   1. With a view open the block at the bottom is there as long as "Search results" are shown: "Select a scene" and the timeline with nothing
//      ticked beside the view, the buttons ("Crop to AOI") with a scene ticked. It goes with the eye of the results and comes back with it.
//   2. A click on the map picks nothing while no group is open, and nothing while the results are hidden; with a group open it picks the scene.
//   3. "Crop to AOI" with a view open adds the scene to it: the same pass is merged into the same image, another day is a new step; the view
//      stays one view (no second inspector, no second layer).
//   4. "Copy original scene name" under the title of the view: a click puts the names on the clipboard, one to a line, "Copied" says it;
//      the tooltip says "2 scenes" for two; the address stays as it is.
// Light and dark theme, a wide and a narrow window (the clicks on the map in the wide one); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/view-merge.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-view-merge');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const FOOTPRINT = [10, 50, 11, 51];
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');

async function run(browser, theme, viewport, results) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win, permissions: ['clipboard-read', 'clipboard-write'] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': [] });
    if (url.pathname.includes('/statistics')) return json({ '1': { min: 0, max: 255, percentile_2: 5, percentile_98: 250, count: 9 } });
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');

  await page.evaluate(async (footprint) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const tiff = () => ({ href: 'https://example.org/x.tif', type: COG, 'raster:bands': Array.from({ length: 3 }, () => ({ data_type: 'uint8', nodata: 0 })) });
    const item = (id, day) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: `${day}T10:00:00Z` }, assets: { visual: tiff() } });
    const day1 = [item('SCENE_A1', '2026-07-01'), item('SCENE_A2', '2026-07-01')];
    const day2 = [item('SCENE_B1', '2026-07-02')];
    const items = [...day1, ...day2];
    const collection = {
      id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
    };
    const aoi = { type: 'Polygon', coordinates: [[[10.2, 50.2], [10.8, 50.2], [10.8, 50.8], [10.2, 50.8], [10.2, 50.2]]] };
    const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 8, maxZoom: 14 });
    const groups = [{ key: ['2026-07-01'], label: '2026-07-01', items: day1 }, { key: ['2026-07-02'], label: '2026-07-02', items: day2 }];
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', openSectionId: null, sections: [], items, groups, activeGroupIndex: 0, expandedGroupIndex: 0,
      selectedIds: [], selectionBlockClosed: false, resultsOnMap: true, downloaded: { SCENE_A1: info('SCENE_A1') }, focusMode: true, cropToAoi: true, viewAoi: aoi, aoi,
      showDownloaded: true, dock: null, appliedRender: { rescale: '0,255' }, pendingVmin: '0', pendingVmax: '255', pendingChannels: [], layers: [], mosaics: {}, error: null,
      flyToView: { center: [10.5, 50.5], zoom: 10 },
    });
  }, FOOTPRINT);
  await page.waitForSelector('.inspector .vc-head');
  await page.waitForTimeout(800);

  const st = (expr) => page.evaluate(async (e) => { const { useAppStore } = await import('/src/store.ts'); return new Function('s', `return ${e}`)(useAppStore.getState()); }, expr);
  const set = (patch) => page.evaluate(async (p) => { const { useAppStore } = await import('/src/store.ts'); useAppStore.setState(p); }, patch);
  const shot = (what) => page.screenshot({ path: path.join(OUT, `${name} ${what}.png`) });
  const inside = (selector) => page.locator(selector).evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { right: r.right, left: r.left }; }));

  // --- 1. the block with a view open --------------------------------------------------------------------------------
  if ((await page.locator('.selection-block .select-hint').textContent()) !== 'Select a scene') problems.push('no "Select a scene" with a view open and nothing ticked');
  if ((await page.locator('.selection-block .time-slider').count()) !== 1) problems.push('no timeline with a view open');
  if ((await page.locator('.download-bar').count()) !== 0) problems.push('the buttons show with nothing ticked beside the view');
  for (const b of await inside('.selection-block')) if (b.right > win.width + 1 || b.left < -1) problems.push('the block lies outside the window');
  await shot('select a scene');

  // --- 2. the clicks on the map (the wide window: the map is free there) ---------------------------------------------------
  if (viewport === 'wide') {
    const canvas = await page.locator('.maplibregl-canvas').first().boundingBox();
    const at = { x: canvas.x + canvas.width / 2 - 120, y: canvas.y + canvas.height / 2 - 120 };
    // No group open: a click picks nothing, and nothing is shown.
    await set({ expandedGroupIndex: null });
    await page.mouse.click(at.x, at.y);
    await page.waitForTimeout(300);
    if ((await st('s.selectedIds.length')) !== 0) problems.push('a click with no group open picked a scene');
    if ((await st('s.resultsOnMap')) !== true) problems.push('a click with no group open changed the results');
    // Hidden results: a click picks nothing and shows nothing, whatever group is open.
    await set({ expandedGroupIndex: 1, resultsOnMap: false });
    await page.mouse.click(at.x, at.y);
    await page.waitForTimeout(300);
    if ((await st('s.selectedIds.length')) !== 0) problems.push('a click with the results hidden picked a scene');
    if ((await st('s.resultsOnMap')) !== false) problems.push('a click with the results hidden showed them');
    if ((await page.locator('.selection-block').count()) !== 0) problems.push('the block is there with the results hidden');
    // Shown again, with a group open: a click picks the scene of that group.
    await set({ resultsOnMap: true });
    await page.waitForSelector('.selection-block');
    await page.mouse.click(at.x, at.y);
    await page.waitForTimeout(300);
    const picked = await st('s.selectedIds');
    if (picked.join() !== 'SCENE_B1') problems.push(`a click with a group open picked ${picked}`);
    await page.waitForSelector('.download-bar');
    if ((await page.locator('.selection-block .select-hint').count()) !== 0) problems.push('"Select a scene" stays with a scene ticked');
    await shot('ticked beside the view');

    // --- 3. "Crop to AOI" adds the scene to the view --------------------------------------------------------------------------
    await page.getByRole('button', { name: 'Crop to AOI' }).click();
    await page.waitForFunction(async () => { const { useAppStore } = await import('/src/store.ts'); return Object.keys(useAppStore.getState().downloaded).length === 2; });
    const ids = await st('Object.keys(s.downloaded).sort().join()');
    if (ids !== 'SCENE_A1,SCENE_B1') problems.push(`the view holds ${ids}`);
    if ((await page.locator('.inspector').count()) !== 1) problems.push('more than one inspector');
    if ((await st('s.layers.length')) !== 0) problems.push('a layer was made');
    if ((await page.locator('.inspector .vc-stepper').count()) < 1) problems.push('no stepper for the two steps');
    await shot('merged as a new step');

    // --- 4. "Copy original scene name" ----------------------------------------------------------------------------------------
    const url = page.url();
    const line = page.locator('.inspector .vc-scene-names');
    if ((await line.textContent()) !== 'Copy original scene name') problems.push(`the line says ${await line.textContent()}`);
    await line.click();
    await page.waitForFunction(() => document.querySelector('.inspector .vc-scene-names')?.textContent === 'Copied', null, { timeout: 1200 }).catch(() => problems.push(`after the click the line says ${'not "Copied"'}`));
    const shown = await page.evaluate(() => navigator.clipboard.readText());
    if (shown !== 'SCENE_B1') problems.push(`the clipboard holds ${JSON.stringify(shown)} for the step that was added`);
    await page.waitForTimeout(1800);
    if ((await line.textContent()) !== 'Copy original scene name') problems.push('"Copied" does not go');
    // The same pass: SCENE_A2 joins the image of SCENE_A1, and both names are copied, one to a line.
    await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().stepImage(-1));
    await set({ expandedGroupIndex: 0, selectedIds: ['SCENE_A2'], resultsOnMap: true });
    await page.waitForSelector('.download-bar');
    await page.getByRole('button', { name: 'Crop to AOI' }).click();
    await page.waitForFunction(async () => { const { useAppStore } = await import('/src/store.ts'); return Object.keys(useAppStore.getState().downloaded).length === 3; });
    const merged = await st('s.shownImage');
    if (!merged) problems.push('no image shown after the merge');
    await page.waitForTimeout(400);
    if ((await line.getAttribute('title')) !== '2 scenes') problems.push(`the tooltip says ${await line.getAttribute('title')}`);
    await line.click();
    const both = await page.evaluate(() => navigator.clipboard.readText());
    if (both !== 'SCENE_A1\nSCENE_A2') problems.push(`the clipboard holds ${JSON.stringify(both)} for the merged image`);
    if (page.url() !== url) problems.push('the address changed');
    await shot('copied');
  } else {
    // The narrow window: the line stands under the title and nothing lies outside the bar.
    const line = page.locator('.inspector .vc-scene-names');
    if ((await line.count()) !== 1) problems.push('no line "Copy original scene name"');
    const box = await line.boundingBox();
    const bar = await page.locator('.inspector').boundingBox();
    if (box && (box.x + box.width > bar.x + bar.width + 1 || box.x < bar.x - 1)) problems.push('the line lies outside the bar');
    await shot('narrow');
  }

  results.push({ name, problems });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) await run(browser, theme, viewport, results);
  await browser.close();
  for (const { name, problems } of results) console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
