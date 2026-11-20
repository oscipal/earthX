// Browser check of M5-62 PR 2: the legend "Classes" of a layer of classes and the table Value | Class | Colour of the Data catalogue.
// With a made-up land cover collection whose band carries the eleven classes of ESA WorldCover (names and colours as the registry
// gives them), in the light and the dark theme, in a wide window, a map 360 px high and a narrow window, it fails when
//   - the field "Colormap" of the view is no button "Classes", or the button does not open and close the legend;
//   - the legend leaves the browser window, scrolls, or lacks a class, or a swatch is not in the colour of its class;
//   - the legend says anything but the names of the classes;
//   - opening the legend makes the settings bar or the page scroll or grow;
//   - the Data catalogue lacks the table of classes, a hex or a swatch, or a value runs out of the window;
// and writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/class-legend.cjs               # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-class-legend');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, low: { width: 1280, height: 360 }, narrow: { width: 360, height: 740 } };

const CLASSES = [
  [10, 'Tree cover', '006400'], [20, 'Shrubland', 'FFBB22'], [30, 'Grassland', 'FFFF4C'], [40, 'Cropland', 'F096FF'],
  [50, 'Built-up', 'FA0000'], [60, 'Bare / sparse vegetation', 'B4B4B4'], [70, 'Snow and ice', 'F0F0F0'],
  [80, 'Permanent water bodies', '0064C8'], [90, 'Herbaceous wetland', '0096A0'], [95, 'Mangroves', '00CF75'],
  [100, 'Moss and lichen', 'FAE6A0'],
].map(([value, title, hint]) => ({ value, name: title.toLowerCase().replace(/[^a-z]+/g, '_'), title, color_hint: hint }));
const rgb = (hint) => `rgb(${parseInt(hint.slice(0, 2), 16)}, ${parseInt(hint.slice(2, 4), 16)}, ${parseInt(hint.slice(4), 16)})`;

const COLLECTION = {
  id: 'landcover', type: 'Collection', title: 'Land cover (made up)', description: 'Land cover, made up for this check.', license: 'CC-BY-4.0', links: [],
  extent: { spatial: { bbox: [[-180, -60, 180, 84]] }, temporal: { interval: [['2021-01-01T00:00:00Z', '2021-12-31T23:59:59Z']] } },
  'earthx:category': 'land_cover', 'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: false, interpolation: false, quad_pol: false, single_coverage_product: true, ml_processing: false },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'own', overview_resampling: null, overview_substitute: null },
  'earthx:source': { asset_hosts: ['assets.example.org'], endpoint: 'https://stac.example.org/v1', page_url: 'https://viewer.example.org/collections/landcover', source_collection_id: 'landcover', data_region: 'unknown' },
  'earthx:default_render': { title: 'Land cover', assets: ['map'], rescale: null, colormap_name: 'esa-worldcover', expression: null, resampling: 'nearest' },
  'earthx:band_units': { map: null },
  'earthx:bands': [{ name: 'map', description: 'Land cover class (made up)', 'classification:classes': CLASSES }],
  'earthx:search_filters': [],
};

const inWindow = (box, viewport) => box.x >= -0.5 && box.y >= -0.5 && box.x + box.width <= viewport.width + 0.5 && box.y + box.height <= viewport.height + 0.5;

async function route(page) {
  await page.route('**/*', async (r) => {
    const url = new URL(r.request().url());
    const json = (body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return r.continue();
    if (url.pathname === '/catalogue/categories') return json({ categories: [{ id: 'land_cover', title: 'Land cover and land use' }] });
    if (url.pathname === '/catalogue/regions') return json({ regions: [] });
    if (url.pathname === '/stac/collections' && r.request().method() === 'POST') return json({ collections: [COLLECTION], links: [], numberMatched: 1 });
    if (url.pathname === '/stac/collections') return json({ collections: [COLLECTION], links: [] });
    return json({ detail: 'not made up' }, 404);
  });
}

async function legend(browser, theme, viewport) {
  const problems = [];
  const size = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: size });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await route(page);
  await page.goto(BASE);
  await page.evaluate(async (collection) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const info = { datasetId: 'landcover', tileUrl: '/t/{z}/{x}/{y}', bounds: [0, 0, 1, 1], asset: 'map', minZoom: 0, maxZoom: 14 };
    useAppStore.setState({ datasets: datasetsFrom([collection]), datasetId: 'landcover', focusMode: true, cropToAoi: false, downloaded: { s0: info }, showDownloaded: true, pendingColormapName: '', pendingVmin: '', pendingVmax: '', focusLoading: false, groups: [], selectedIds: [] });
  }, COLLECTION);
  const button = page.locator('button.vc-classes');
  await button.waitFor({ timeout: 10000 }).catch(() => problems.push('no button "Classes" in the settings bar'));
  if (problems.length > 0) {
    await context.close();
    return problems;
  }
  if ((await button.textContent()) !== 'Classes') problems.push(`the button says "${await button.textContent()}"`);
  const bar = page.locator('.inspector .insp-body');
  const before = await bar.evaluate((el) => ({ scroll: el.scrollHeight, client: el.clientHeight, page: document.documentElement.scrollHeight }));
  await button.click();
  const popup = page.locator('.classes-popup');
  await popup.waitFor({ timeout: 5000 }).catch(() => problems.push('the legend does not open'));
  if (await popup.count()) {
    const box = await popup.boundingBox();
    if (!box || !inWindow(box, size)) problems.push(`the legend leaves the window: ${JSON.stringify(box)}`);
    const scrolls = await popup.evaluate((el) => el.scrollHeight > el.clientHeight + 1);
    if (scrolls) problems.push('the legend scrolls');
    const lines = await popup.locator('li').evaluateAll((items) => items.map((li) => ({ text: li.textContent, colour: getComputedStyle(li.querySelector('.class-swatch')).backgroundColor })));
    const expected = CLASSES.map((c) => ({ text: c.title, colour: rgb(c.color_hint) }));
    if (JSON.stringify(lines) !== JSON.stringify(expected)) problems.push(`the lines are not the classes: ${JSON.stringify(lines)}`);
    const text = await popup.textContent();
    if (text !== CLASSES.map((c) => c.title).join('')) problems.push(`the legend says more than the names: "${text}"`);
    const after = await bar.evaluate((el) => ({ scroll: el.scrollHeight, client: el.clientHeight, page: document.documentElement.scrollHeight }));
    if (JSON.stringify(after) !== JSON.stringify(before)) problems.push(`opening the legend changes the settings bar or the page: ${JSON.stringify(before)} -> ${JSON.stringify(after)}`);
    await page.screenshot({ path: path.join(OUT, `legend-${theme}-${viewport}.png`) });
    await button.click();
    if (await popup.count()) problems.push('a second click does not close the legend');
  }
  await context.close();
  return problems;
}

async function catalogue(browser, theme, viewport) {
  const problems = [];
  const size = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: size });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await route(page);
  await page.goto(BASE);
  await page.locator('#rail-catalogue').click();
  await page.locator('.catalogue-entry-name', { hasText: 'Land cover (made up)' }).first().click();
  const table = page.locator('table.catalogue-classes');
  await table.waitFor({ timeout: 10000 }).catch(() => problems.push('no table of classes in the details'));
  if (await table.count()) {
    if ((await table.locator('caption').textContent()) !== 'map') problems.push('the table is not headed by the band');
    const rows = await table.locator('tbody tr').evaluateAll((trs) =>
      trs.map((tr) => ({ cells: [...tr.children].map((cell) => cell.textContent), colour: getComputedStyle(tr.querySelector('.class-swatch')).backgroundColor })),
    );
    const expected = CLASSES.map((c) => ({ cells: [String(c.value), c.title, `#${c.color_hint.toLowerCase()}`], colour: rgb(c.color_hint) }));
    if (JSON.stringify(rows) !== JSON.stringify(expected)) problems.push(`the rows are not the classes: ${JSON.stringify(rows)}`);
    await table.scrollIntoViewIfNeeded();
    const box = await table.boundingBox();
    if (!box || box.x + box.width > size.width + 0.5) problems.push(`the table runs out of the window: ${JSON.stringify(box)}`);
    const sideways = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    if (sideways) problems.push('the page scrolls sideways');
    await page.screenshot({ path: path.join(OUT, `catalogue-${theme}-${viewport}.png`) });
  }
  await context.close();
  return problems;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const [name, run] of [['legend', legend], ['catalogue', catalogue]]) {
        if (name === 'catalogue' && viewport === 'low') continue;
        const problems = await run(browser, theme, viewport);
        failed += problems.length;
        console.log(`${problems.length ? 'FAIL' : 'ok  '} ${name} ${theme} ${viewport}${problems.map((p) => `\n     - ${p}`).join('')}`);
      }
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
