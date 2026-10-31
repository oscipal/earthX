// Browser check of "Mask by value" in the processing panel (DS-06b), in a real browser with made-up answers of the server:
//   1. Sentinel-2: both buttons, the step after a band math (the result first in "Band", then the bands of the data), the
//      boxes of each condition in one row, the explanations only as tooltips, a mistake told at the field.
//   2. The DEM: "Mask by value" alone; no sentence about a missing classification layer.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/mask-values.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-mask-values');
const read = (name) => JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', `${name}.json`), 'utf8'));
const DESCRIPTIONS = { 'sentinel-2-c1-l2a': read('sentinel-2-c1-l2a'), 'cop-dem-glo-30': read('cop-dem-glo-30') };
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const SCL = {
  asset: 'scl', band: 'scl', suggested: [3, 8, 9, 10], reference: null, note: null,
  classes: ['NO_DATA', 'SATURATED_OR_DEFECTIVE', 'CAST_SHADOWS', 'CLOUD_SHADOWS'].map((label, value) => ({ value, label })),
};

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function open(browser, theme, viewport) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTIONS[url.searchParams.get('dataset')]);
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page };
}

async function selectScene(page, dem) {
  await page.evaluate(async (isDem) => {
    const { useAppStore } = await import('/src/store.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const asset = (type = 'uint16') => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: type }] });
    const id = isDem ? 'cop-dem-glo-30' : 'sentinel-2-c1-l2a';
    const item = {
      id: 'ITEM_A', collection: id, bbox, geometry: polygon, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
      assets: isDem ? { data: asset('float32') } : { red: asset(), nir: asset(), scl: asset('uint8') },
    };
    const collection = isDem
      ? { id, 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:band_units': { data: 'm' } }
      : { id, 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true }, 'earthx:mask': window.__scl };
    useAppStore.setState({
      datasets: [{ id, title: id, viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection }],
      datasetId: id, items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['ITEM_A'], aoi: polygon, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
  }, dem);
}

// Whether the leaves of the step stay inside the panel and do not lie on each other.
async function layout(page, problems) {
  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const step = document.querySelectorAll('li.pp-step')[1] ?? document.querySelector('li.pp-step');
    const body = step.closest('.pp-body') ?? document.querySelector('.processing-panel');
    return {
      theme: document.querySelector('.app')?.dataset.theme,
      panel: box(body),
      scrolls: body.scrollWidth > body.clientWidth + 1,
      leaves: [...step.querySelectorAll('input, select')].filter((e) => e.offsetParent).map((e) => ({ what: e.getAttribute('aria-label') ?? e.tagName.toLowerCase(), ...box(e) })),
    };
  });
  for (let i = 0; i < report.leaves.length; i++) {
    for (let j = i + 1; j < report.leaves.length; j++) if (overlap(report.leaves[i], report.leaves[j])) problems.push(`${report.leaves[i].what} overlaps ${report.leaves[j].what}`);
    const leaf = report.leaves[i];
    if (leaf.x < report.panel.x - 0.5 || leaf.x + leaf.width > report.panel.x + report.panel.width + 0.5) problems.push(`${leaf.what} leaves the panel`);
  }
  if (report.scrolls) problems.push('the panel scrolls sideways');
  return report;
}

async function checkS2(browser, theme, viewport) {
  const name = `sentinel-2 ${theme} ${viewport}`;
  const problems = [];
  const { context, page } = await open(browser, theme, viewport);
  await page.evaluate((scl) => { window.__scl = scl; }, SCL);
  await selectScene(page, false);
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().openProcessing());
  await page.getByRole('button', { name: '＋ Band math' }).waitFor({ timeout: 15000 });
  for (const label of ['＋ Mask by class', '＋ Mask by value']) if ((await page.getByRole('button', { name: label }).count()) !== 1) problems.push(`no button ${label}`);
  if ((await page.getByText('no classification layer').count()) > 0) problems.push('the panel talks of a missing classification layer');
  await page.locator('textarea[id$="-expression"]').waitFor({ state: 'detached' }).catch(() => {});
  await page.getByRole('button', { name: '＋ Band math' }).click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  await page.getByRole('button', { name: '＋ Mask by value' }).click();
  const step = page.locator('li.pp-step').nth(1);
  const groups = await step.locator('optgroup').evaluateAll((g) => g.map((x) => [x.label, [...x.querySelectorAll('option')].map((o) => o.value).join()]));
  if (JSON.stringify(groups) !== JSON.stringify([['Results', 'result'], ['Data', 'red,nir']])) problems.push(`the options of Band are ${JSON.stringify(groups)}`);
  if ((await step.locator('select[id$="-band"]').inputValue()) !== 'result') problems.push('the band is not the last result');
  const row = step.locator('.pp-where');
  const shown = async () => row.evaluate((r) => [...r.querySelectorAll('input, select')].map((e) => e.getAttribute('aria-label')).join());
  if ((await shown()) !== 'Condition,Value') problems.push(`below shows ${await shown()}`);
  await step.locator('input[aria-label="Value"]').fill('0.2');
  await layout(page, problems);
  await step.locator('select[aria-label="Condition"]').selectOption('between');
  if ((await shown()) !== 'Condition,From,To') problems.push(`between shows ${await shown()}`);
  if ((await step.locator('input[aria-label="From"]').inputValue()) !== '0.2') problems.push('the number was not kept for between');
  await step.locator('input[aria-label="To"]').fill('0.1');
  const message = await step.locator('.hint-text.error').allTextContents();
  if (message.join() !== '“from” must be below “to”.') problems.push(`the mistake is told as ${JSON.stringify(message)}`);
  await layout(page, problems);
  fs.mkdirSync(OUT, { recursive: true });
  await step.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_between.png`) });
  await step.locator('select[aria-label="Condition"]').selectOption('eq');
  if ((await shown()) !== 'Condition,Values') problems.push(`equal to shows ${await shown()}`);
  await step.locator('input[aria-label="Values"]').fill('3, 8, 9');
  const report = await layout(page, problems);
  const tips = await step.locator('[data-tip]').evaluateAll((t) => t.map((x) => x.getAttribute('data-tip')).join(' '));
  if (!tips.includes('Pixels are hidden in every band') || !tips.includes("data type")) problems.push('the tooltips do not explain');
  if ((await step.innerText()).includes('data type')) problems.push('the explanation stands in the step, not in the tooltip');
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}`);
  fs.mkdirSync(OUT, { recursive: true });
  await step.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  await context.close();
  return { name, problems };
}

async function checkDem(browser, theme, viewport) {
  const name = `dem ${theme} ${viewport}`;
  const problems = [];
  const { context, page } = await open(browser, theme, viewport);
  await selectScene(page, true);
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().openProcessing());
  await page.getByRole('button', { name: '＋ Mask by value' }).waitFor({ timeout: 15000 });
  if ((await page.getByRole('button', { name: '＋ Mask by class' }).count()) !== 0) problems.push('the DEM is offered a mask by class');
  if ((await page.getByText('classification layer').count()) > 0) problems.push('the panel talks of a classification layer');
  await page.getByRole('button', { name: '＋ Mask by value' }).click();
  const step = page.locator('li.pp-step').first();
  await step.locator('select[id$="-band"]').selectOption('data');
  if ((await step.locator('.pp-unit').textContent()) !== 'in m') problems.push('the unit of the band is not beside "Hide where"');
  await step.locator('select[aria-label="Condition"]').selectOption('gt');
  await step.locator('input[aria-label="Value"]').fill('2000');
  await layout(page, problems);
  fs.mkdirSync(OUT, { recursive: true });
  await step.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      results.push(await checkS2(browser, theme, viewport));
      results.push(await checkDem(browser, theme, viewport));
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
