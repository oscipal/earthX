// Layout check of the range row of the preview (M4-19c, with "Show" since NM4-43e PR 2): in a real browser, with DEM-like
// and NDVI-like values, with and without the dropdown "Show" left of the range, in the light and the dark theme, at a wide
// and a narrow panel. Fails when a field, the unit, the colormap or a
// button overlaps another, leaves the panel, or cuts a value off; writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/range-layout.cjs               # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-range-layout');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));

// What the tiler would measure: a DEM from the Dead Sea to Everest, and an index.
const MEASURES = {
  'DEM-like': { b1: { count: 900, min: -11000, max: 8848.86, percentile_2: -11000, percentile_98: 8848.86, unit: 'm' } },
  'NDVI-like': { b1: { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null } },
};
// What a user may type into the fields.
const TYPED = { 'DEM-like': ['-11000', '8848.86'], 'NDVI-like': ['-0.123456', '0.987654'] };
// The app's two themes: `tech` is the dark HUD, `normal` the light one (`preferences.ts`).
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function check(browser, { measure, theme, viewport, values, show }) {
  const name = `${measure} ${theme} ${viewport} ${values} ${show}`;
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/statistics')) return json(MEASURES[measure]);
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const item = {
      id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox, geometry: polygon,
      properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
      assets: {
        red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
        nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      },
    };
    useAppStore.setState({
      datasets: [{
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
        browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
        collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } },
      }],
      datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['S2B_A'], aoi: polygon, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
    useProcessingStore.getState().openProcessing();
  });
  await page.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  await page.waitForSelector('.pp-range input[type=number]', { timeout: 15000 });
  // A second band in the output brings the dropdown "Show" (the names of the bands are long on purpose).
  if (show === 'with') await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().setOutput(['result', 'red']));
  await page.waitForTimeout(700);
  if (values === 'typed') {
    const [low, high] = TYPED[measure];
    const inputs = page.locator('.pp-range input[type=number]');
    await inputs.nth(0).fill(low);
    await inputs.nth(1).fill(high);
  }
  const report = await page.evaluate(() => {
    const row = document.querySelector('.pp-range');
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const leaves = [
      ...[...row.querySelectorAll('input')].map((e) => ({ what: `field ${e.value}`, e })),
      ...[...row.querySelectorAll('.pp-unit')].map((e) => ({ what: `unit ${e.textContent}`, e })),
      ...[...row.querySelectorAll('select')].map((e) => ({ what: e.closest('.pp-show') ? 'show' : 'colormap', e })),
      ...[...row.querySelectorAll('button')].map((e) => ({ what: `button ${e.textContent}`, e })),
    ].map(({ what, e }) => ({ what, ...box(e), cutOff: e.tagName === 'INPUT' && e.scrollWidth > e.clientWidth }));
    const panel = document.querySelector('.processing-panel');
    const body = row.closest('.pp-body') ?? panel;
    return { theme: document.querySelector('.app')?.dataset.theme, leaves, panel: box(body), scrolls: body.scrollWidth > body.clientWidth + 1, unit: row.querySelector('.pp-unit')?.textContent ?? null, fields: [...row.querySelectorAll('input')].map((e) => e.value) };
  });
  const problems = [];
  const { leaves, panel } = report;
  for (let i = 0; i < leaves.length; i++) {
    for (let j = i + 1; j < leaves.length; j++) if (overlap(leaves[i], leaves[j])) problems.push(`${leaves[i].what} overlaps ${leaves[j].what}`);
    if (leaves[i].x < panel.x - 0.5 || leaves[i].x + leaves[i].width > panel.x + panel.width + 0.5) problems.push(`${leaves[i].what} leaves the panel`);
    if (leaves[i].cutOff) problems.push(`${leaves[i].what} is cut off`);
  }
  const named = (what) => leaves.find((leaf) => leaf.what === what || leaf.what.startsWith(`${what} `));
  if (show === 'with') {
    const dropdown = named('show');
    const first = leaves.find((leaf) => leaf.what.startsWith('field'));
    if (!dropdown) problems.push('the dropdown "Show" is missing');
    else if (!(dropdown.y < first.y - 0.5 || dropdown.x + dropdown.width <= first.x + 0.5)) problems.push('"Show" does not stand left of min');
  } else if (named('show')) problems.push('"Show" is there with one band in the output');
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}, not ${THEMES[theme]}`);
  if (report.scrolls) problems.push('the panel scrolls sideways');
  if (measure === 'DEM-like' && report.unit !== 'm') problems.push(`the unit is ${JSON.stringify(report.unit)}, not "m"`);
  if (measure === 'NDVI-like' && values === 'measured' && report.unit !== null) problems.push('a unit is shown beside an index');
  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('.pp-range').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  await context.close();
  return { name, problems, fields: report.fields };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const measure of Object.keys(MEASURES)) for (const theme of ['light', 'dark']) for (const viewport of Object.keys(VIEWPORTS)) for (const values of ['measured', 'typed']) for (const show of ['without', 'with']) {
    const result = await check(browser, { measure, theme, viewport, values, show });
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name} [${result.fields.join(' … ')}]${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : 'no overlap, nothing cut off, nothing outside the panel');
  process.exit(failed ? 1 : 0);
})();
