// Browser check of the index buttons (NM4-14b), in a real browser with made-up answers of the tiler:
//   1. The row "Index" under "Add step": a button for each preset of the dataset, in a row that wraps and leaves the panel
//      alone; no row for a dataset without presets (DEM); a click adds an ordinary Band math step named like the index,
//      a second click numbers it, and the tooltip holds title and formula.
//   2. The preview of a preset: whatever the tiler measures (values far beyond -1…1 here), the picture asks for the range and
//      colormap of the preset (`-1,1`, `rdbu` for NDWI), the fields show it, and a typed expression that differs falls
//      back to the measured 2–98 % in viridis.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/index-buttons.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-index-buttons');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const TIP_NDVI = 'Normalized Difference Vegetation Index: (N - R)/(N + R). Formula: Awesome Spectral Indices.';
// Snow, water and clouds beyond -1…1: the rule of an index would not call this one.
const WIDE = { b1: { count: 900, min: -4, max: 9, percentile_2: -2.5, percentile_98: 6, unit: null } };

const PRESETS = [
  ['NDVI', 'Normalized Difference Vegetation Index', '(nir - red) / (nir + red)', 'rdylgn', '(N - R)/(N + R)'],
  ['NDWI', 'Normalized Difference Water Index (McFeeters 1996)', '(green - nir) / (green + nir)', 'rdbu', '(G - N) / (G + N)'],
  ['NDSI', 'Normalized Difference Snow Index', '(green - swir16) / (green + swir16)', 'rdbu', '(G - S1) / (G + S1)'],
  ['NBR', 'Normalized Burn Ratio', '(nir - swir22) / (nir + swir22)', 'rdylgn', '(N - S2) / (N + S2)'],
  ['EVI', 'Enhanced Vegetation Index', '2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)', 'rdylgn', 'g * (N - R) / (N + C1 * R - C2 * B + L)'],
].map(([name, title, expression, colormap_name, formula]) => ({ name, title, expression, rescale: [[-1, 1]], colormap_name, formula, reference: 'https://example.org/formula' }));

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function open(browser, theme, viewport) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/statistics')) return json(WIDE);
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page };
}

async function selectScene(page, presets) {
  await page.evaluate(async (presets) => {
    const { useAppStore } = await import('/src/store.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
    const item = {
      id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox, geometry: polygon,
      properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
      assets: { blue: asset(), green: asset(), red: asset(), nir: asset(), swir16: asset(), swir22: asset() },
    };
    useAppStore.setState({
      datasets: [{
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
        browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
        collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true }, 'earthx:index_presets': presets },
      }],
      datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['S2B_A'], aoi: polygon, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
  }, presets);
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().openProcessing());
}

const row = (page) => page.locator('[role="group"][aria-label="Add index"]');

// 1. The row.
async function checkRow(browser, theme, viewport) {
  const name = `row ${theme} ${viewport}`;
  const problems = [];
  const { context, page } = await open(browser, theme, viewport);
  await selectScene(page, PRESETS);
  await row(page).waitFor({ timeout: 15000 });
  const labels = await row(page).locator('button').allTextContents();
  if (labels.join('|') !== '＋ NDVI|＋ NDWI|＋ NDSI|＋ NBR|＋ EVI') problems.push(`the buttons are ${labels}`);
  const tip = await row(page).locator('button').first().getAttribute('title');
  if (tip !== TIP_NDVI) problems.push(`the tooltip of NDVI is ${tip}`);
  const aria = await row(page).locator('button').first().getAttribute('aria-label');
  if (aria !== `NDVI. ${TIP_NDVI}`) problems.push(`the aria-label of NDVI is ${aria}`);
  // Under "Add step", nothing between, nothing beside the buttons.
  const order = await page.evaluate(() => {
    const add = document.querySelector('[role="group"][aria-label="Add step"]');
    return add?.nextElementSibling?.getAttribute('aria-label');
  });
  if (order !== 'Add index') problems.push(`the row does not follow "Add step" (it is ${order})`);
  const text = await row(page).innerText();
  if (text.replace(/\s+/g, ' ').trim() !== 'Index: ＋ NDVI ＋ NDWI ＋ NDSI ＋ NBR ＋ EVI') problems.push(`the row says ${JSON.stringify(text)}`);

  const report = await page.evaluate(() => {
    const group = document.querySelector('[role="group"][aria-label="Add index"]');
    const panel = document.querySelector('.processing-panel');
    const body = document.querySelector('.pp-body') ?? panel;
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    return {
      theme: document.querySelector('.app')?.dataset.theme,
      panel: box(panel),
      scrolls: body.scrollWidth > body.clientWidth + 1,
      leaves: [...group.querySelectorAll('button')].map((e) => ({ what: e.textContent, ...box(e) })),
      lines: new Set([...group.querySelectorAll('button')].map((e) => Math.round(e.getBoundingClientRect().y))).size,
    };
  });
  for (let i = 0; i < report.leaves.length; i++) {
    for (let j = i + 1; j < report.leaves.length; j++) if (overlap(report.leaves[i], report.leaves[j])) problems.push(`${report.leaves[i].what} overlaps ${report.leaves[j].what}`);
    const leaf = report.leaves[i];
    if (leaf.x < report.panel.x - 0.5 || leaf.x + leaf.width > report.panel.x + report.panel.width + 0.5) problems.push(`${leaf.what} leaves the panel`);
  }
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}`);
  if (report.scrolls) problems.push('the panel scrolls sideways');

  // A click adds an ordinary step named like the index; a second click numbers it.
  await page.getByRole('button', { name: /^NDVI\./ }).click();
  await page.getByRole('button', { name: /^NDVI\./ }).click();
  const names = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().steps.map((s) => `${s.op}:${s.values.name}:${s.values.expression}`));
  if (names.join('|') !== 'band_math:NDVI:(nir - red) / (nir + red)|band_math:NDVI_2:(nir - red) / (nir + red)') problems.push(`the steps are ${names}`);
  const fieldsShown = await page.locator('textarea[id$="-expression"]').count();
  if (fieldsShown !== 2) problems.push(`${fieldsShown} expression fields, not 2`);

  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('section[aria-label="Processing steps"]').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  await context.close();
  return { name, problems };
}

// 2. No row without presets (the DEM has none).
async function checkNoRow(browser, theme, viewport) {
  const name = `dem ${theme} ${viewport}`;
  const problems = [];
  const { context, page } = await open(browser, theme, viewport);
  await selectScene(page, []);
  await page.getByRole('group', { name: 'Add step' }).waitFor({ timeout: 15000 });
  if ((await row(page).count()) !== 0) problems.push('a dataset without presets shows the row');
  if ((await page.getByText('Index:').count()) !== 0) problems.push('the label "Index:" is there');
  await context.close();
  return { name, problems };
}

// 3. The preview of a preset.
async function checkPreview(browser, theme, viewport) {
  const name = `preview ${theme} ${viewport}`;
  const problems = [];
  const { context, page } = await open(browser, theme, viewport);
  await selectScene(page, PRESETS);
  await row(page).waitFor({ timeout: 15000 });
  await page.getByRole('button', { name: /^NDWI\./ }).click();
  await page.waitForSelector('.pp-range input[type=number]', { timeout: 15000 });
  await page.waitForTimeout(1200);
  const fields = () => page.$$eval('.pp-range input[type=number]', (i) => i.map((x) => x.value));
  const colormap = () => page.$eval('.pp-range .vc-field:not(.pp-show) select', (s) => s.value);
  if ((await fields()).join() !== '-1,1') problems.push(`the fields of NDWI say ${await fields()}, not -1,1`);
  if ((await colormap()) !== 'rdbu') problems.push(`NDWI is drawn in ${await colormap()}, not rdbu`);
  const tile = await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const url = new URL(useProcessingStore.getState().preview?.scenes[0]?.url ?? 'http://x/', 'http://localhost');
    return { rescale: url.searchParams.get('rescale'), colormap: url.searchParams.get('colormap_name'), band: url.searchParams.get('band') };
  });
  if (tile.rescale !== '-1,1' || tile.colormap !== 'rdbu' || tile.band !== 'NDWI') problems.push(`the tile asks for ${JSON.stringify(tile)}`);

  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('section[aria-label="Preview on the map"]').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });

  // The expression changed: the measured 2–98 % in viridis.
  await page.locator('textarea[id$="-expression"]').fill('(nir - green) / (nir + green)');
  await page.waitForTimeout(1400);
  if ((await fields()).join() !== '-2.5,6') problems.push(`the fields of the changed expression say ${await fields()}, not -2.5,6`);
  if ((await colormap()) !== 'viridis') problems.push(`the changed expression is drawn in ${await colormap()}, not viridis`);
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      results.push(await checkRow(browser, theme, viewport));
      results.push(await checkNoRow(browser, theme, viewport));
      results.push(await checkPreview(browser, theme, viewport));
    }
  }
  await browser.close();
  let failed = 0;
  for (const { name, problems } of results) {
    console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
    for (const problem of problems) console.log(`       ${problem}`);
    failed += problems.length;
  }
  console.log(`screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
