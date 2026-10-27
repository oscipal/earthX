// Browser check of the band choice of the processing panel (NM4-07): a single band is picked on opening, "Select all
// bands" and "Clear", the auxiliary assets and the mask layer stay out, and a dataset with more bands than an order
// takes gets a reason instead of a part. Runs in the light and the dark theme at three widths; fails when a button
// overlaps another or leaves the panel; writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/band-select.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-band-select');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };
const S2 = ['coastal', 'blue', 'green', 'red', 'rededge1', 'rededge2', 'rededge3', 'nir', 'nir08', 'nir09', 'swir16', 'swir22'];

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

// What each case offers and what the check expects after each click.
const CASES = {
  'sentinel-2': { assets: [...S2, 'visual', 'preview', 'scl'], auxiliary: ['visual', 'preview'], mask: true, opening: [], all: S2 },
  'one band': { assets: ['data'], auxiliary: [], mask: false, opening: ['data'], all: ['data'] },
  '18 bands': { assets: Array.from({ length: 18 }, (_, i) => `b${i + 1}`), auxiliary: [], mask: false, opening: [], all: [] },
  '16 bands': { assets: Array.from({ length: 16 }, (_, i) => `b${i + 1}`), auxiliary: [], mask: false, opening: [], all: Array.from({ length: 16 }, (_, i) => `b${i + 1}`) },
};

async function check(browser, { name, theme, viewport }) {
  const spec = CASES[name];
  const label = `${name} ${theme} ${viewport}`;
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.evaluate(async ({ spec }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const assets = Object.fromEntries(spec.assets.map((key) => [key, { href: `https://example.org/${key}.tif`, type: COG, 'raster:bands': [{ data_type: 'uint16' }] }]));
    const item = { id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox: [10, 50, 11, 51], geometry: polygon, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets };
    const collection = {
      id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true },
      'earthx:auxiliary_assets': spec.auxiliary,
      ...(spec.mask ? { 'earthx:mask': { asset: 'scl', band: 'scl', classes: [{ value: 4, label: 'Vegetation' }], suggested: [] } } : {}),
    };
    useAppStore.setState({
      datasets: [{ id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection }],
      datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['S2B_A'], aoi: polygon, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
    useProcessingStore.getState().openProcessing();
  }, { spec });
  await page.waitForSelector('section[aria-label="Bands"] .pp-chip');
  const pressed = () => page.evaluate(() => [...document.querySelectorAll('section[aria-label="Bands"] .pp-chip[aria-pressed="true"]')].map((c) => c.textContent));
  const problems = [];
  const expect = (what, got, want) => { if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`); };

  expect('on opening', await pressed(), spec.opening);
  await page.locator('section[aria-label="Bands"]').getByRole('button', { name: 'Select all bands' }).click();
  expect('after "Select all bands"', await pressed(), spec.all);
  const note = await page.locator('section[aria-label="Bands"] [role="status"]').allTextContents();
  if (name === '18 bands' && note[0] !== '18 bands are more than the 16 an order takes. Pick the ones you need.') problems.push(`no reason: ${JSON.stringify(note)}`);
  if (name !== '18 bands' && note.length > 0) problems.push(`a reason where none is due: ${JSON.stringify(note)}`);
  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('section[aria-label="Bands"]').screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}.png`) });

  const layout = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const head = document.querySelector('.pp-bands-head');
    const leaves = [...head.children].map((e) => ({ what: e.textContent, ...box(e) }));
    const body = head.closest('.pp-body') ?? document.querySelector('.processing-panel');
    return { theme: document.querySelector('.app')?.dataset.theme, leaves, panel: box(body), scrolls: body.scrollWidth > body.clientWidth + 1 };
  });
  for (let i = 0; i < layout.leaves.length; i++) {
    for (let j = i + 1; j < layout.leaves.length; j++) if (overlap(layout.leaves[i], layout.leaves[j])) problems.push(`${layout.leaves[i].what} overlaps ${layout.leaves[j].what}`);
    if (layout.leaves[i].x < layout.panel.x - 0.5 || layout.leaves[i].x + layout.leaves[i].width > layout.panel.x + layout.panel.width + 0.5) problems.push(`${layout.leaves[i].what} leaves the panel`);
  }
  if (layout.theme !== THEMES[theme]) problems.push(`the app shows the theme ${layout.theme}, not ${THEMES[theme]}`);
  if (layout.scrolls) problems.push('the panel scrolls sideways');

  const clear = page.locator('section[aria-label="Bands"]').getByRole('button', { name: 'Clear', exact: true });
  if ((await pressed()).length > 0) await clear.click();
  else if (!(await clear.isDisabled())) problems.push('"Clear" is active with nothing to clear');
  expect('after "Clear"', await pressed(), []);
  await context.close();
  return { label, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const name of Object.keys(CASES)) for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) {
    const result = await check(browser, { name, theme, viewport });
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.label}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : 'all cases as expected');
  process.exit(failed ? 1 : 0);
})();
