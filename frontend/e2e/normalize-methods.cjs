// Browser check of "Normalize" with its methods in the processing panel (NM4-11b), in a real browser with made-up answers of
// the server (the process description of the fixtures and the statistics over the AOI):
//   1. The step: four methods, the fields of each in one row, the explanations only as tooltips, a comma told at the field.
//   2. The measure: "Measuring…" with "Review" and "Start job" held and the reason as their tooltip, then the numbers, then
//      the failure with "Retry".
//   3. The locks: without an AOI the three methods that measure are off, with the reason.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/normalize-methods.cjs          # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-normalize-methods');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const STATISTICS = {
  minimum: 100, maximum: 9000, mean: 2000, stddev: 500, count: 1000, valid_percent: 100,
  percentile_1: 150, percentile_2: 200, percentile_5: 300, percentile_25: 1500, percentile_50: 1900,
  percentile_75: 2400, percentile_95: 5000, percentile_98: 6000, percentile_99: 7000,
};

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

// `state.statistics`: what the route answers next: 'ok', 'fail', or 'hold' (no answer until `state.release()`).
async function open(browser, theme, viewport, state) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: status === 200 ? 'application/json' : 'application/problem+json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    if (url.pathname.endsWith('/statistics') && route.request().method() === 'POST') {
      state.asked.push(JSON.parse(route.request().postData()));
      if (state.statistics === 'hold') await new Promise((resolve) => (state.release = resolve));
      if (state.statistics === 'fail') return json({ detail: 'The area is too large to measure.' }, 422);
      const bands = state.asked.at(-1).output.bands;
      return json({ bands: bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact: true, factor: 1 });
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page };
}

async function selectScene(page, withAoi) {
  await page.evaluate(async (aoi) => {
    const { useAppStore } = await import('/src/store.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const asset = { href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] };
    const id = 'sentinel-2-c1-l2a';
    const item = { id: 'ITEM_A', collection: id, bbox, geometry: polygon, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { red: asset, nir: asset } };
    const collection = { id, 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } };
    useAppStore.setState({
      datasets: [{ id, title: id, viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection }],
      datasetId: id, items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['ITEM_A'], aoi: aoi ? { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] } : null,
      aoiPoint: null, layers: [], focusMode: false, error: null,
    });
  }, withAoi);
  await page.evaluate(async (aoi) => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().openProcessing();
    if (aoi) useProcessingStore.getState().setArea('aoi');
  }, withAoi);
  await page.getByRole('button', { name: '＋ Normalize' }).waitFor({ timeout: 15000 });
}

// Whether the leaves of the step stay inside the panel and do not lie on each other.
async function layout(page, problems) {
  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const step = document.querySelector('li.pp-step');
    const body = step.closest('.pp-body') ?? document.querySelector('.processing-panel');
    return {
      theme: document.querySelector('.app')?.dataset.theme,
      panel: box(body),
      scrolls: body.scrollWidth > body.clientWidth + 1,
      leaves: [...step.querySelectorAll('input, select')].filter((e) => e.offsetParent).map((e) => ({ what: e.getAttribute('aria-label') ?? e.id ?? e.tagName.toLowerCase(), ...box(e) })),
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

async function shot(step, name, suffix) {
  fs.mkdirSync(OUT, { recursive: true });
  await step.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_${suffix}.png`) });
}

async function checkMethods(browser, theme, viewport) {
  const name = `methods ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'ok', asked: [] };
  const { context, page } = await open(browser, theme, viewport, state);
  await selectScene(page, true);
  await page.getByRole('button', { name: '＋ Normalize' }).click();
  const step = page.locator('li.pp-step').first();
  await step.locator('fieldset .pp-chip', { hasText: 'red' }).click();
  const options = await step.locator('select[id$="-method"] option').allTextContents();
  if (options.join() !== 'Fixed range,Percentile stretch,Z-score,Robust (median, IQR)') problems.push(`the methods are ${options.join()}`);
  const shown = () => step.evaluate((s) => [...s.querySelectorAll('input, select')].filter((e) => e.offsetParent).map((e) => e.getAttribute('aria-label') ?? e.id.replace(/^pp-step-\d+-/, '')).join());
  if ((await shown()) !== 'method,From min,From max,Target min,Target max,clip') problems.push(`fixed range shows ${await shown()}`);
  await step.locator('input[aria-label="From min"]').fill('0,2');
  if (!(await step.innerText()).includes('Use . for decimals.')) problems.push('a comma is not told');
  await step.locator('input[aria-label="From min"]').fill('0.2');
  await layout(page, problems);
  await shot(step, name, 'fixed');
  const tips = await step.locator('[data-tip]').evaluateAll((t) => t.map((x) => x.getAttribute('data-tip')).join(' '));
  if (!tips.includes('NDVI −1…1 → 0…1') || !tips.includes('(x − from) / (to − from)')) problems.push('the tooltip has no example or formula');
  await step.locator('select[id$="-method"]').selectOption('percentile');
  await step.locator('text=Measured over the AOI ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('the numbers were not measured'));
  if ((await shown()) !== 'method,range,Target min,Target max,clip') problems.push(`percentile shows ${await shown()}`);
  if ((await step.locator('select[id$="-range"]').inputValue()) !== '2–98 %') problems.push('the range does not start at 2–98 %');
  const body = state.asked[0];
  if (!body || body.output.dtype !== 'float64' || body.steps.length !== 0 || JSON.stringify(body.output.bands) !== '["red"]') problems.push(`the question is ${JSON.stringify(body?.output)}`);
  const numbers = await step.locator('[data-tip]').evaluateAll((t) => t.map((x) => x.getAttribute('data-tip')).join(' '));
  if (!numbers.includes('p_low 200, p_high 6000')) problems.push('the numbers are not in the tooltip');
  await layout(page, problems);
  await shot(step, name, 'percentile');
  for (const method of ['zscore', 'robust']) {
    await step.locator('select[id$="-method"]').selectOption(method);
    if ((await shown()) !== 'method') problems.push(`${method} shows ${await shown()}`);
  }
  await layout(page, problems);
  await shot(step, name, 'robust');
  const report = await layout(page, problems);
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}`);
  await context.close();
  return { name, problems };
}

async function checkWaiting(browser, theme, viewport) {
  const name = `waiting ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'hold', asked: [], release: null };
  const { context, page } = await open(browser, theme, viewport, state);
  await selectScene(page, true);
  await page.getByRole('button', { name: '＋ Normalize' }).click();
  const step = page.locator('li.pp-step').first();
  await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().setOutput(['red']);
    const key = useProcessingStore.getState().steps[0].key;
    useProcessingStore.getState().updateStep(key, 'bands', 'red');
  });
  await step.locator('select[id$="-method"]').selectOption('zscore');
  await step.locator('text=Measuring…').waitFor({ timeout: 5000 }).catch(() => problems.push('no "Measuring…"'));
  for (const label of ['Review', 'Start job']) {
    const button = page.getByRole('button', { name: label, exact: true });
    if (!(await button.isDisabled())) problems.push(`${label} is not held`);
    if ((await button.getAttribute('title')) !== 'Normalize: measuring the bands…') problems.push(`${label} says ${await button.getAttribute('title')}`);
  }
  await layout(page, problems);
  await shot(step, name, 'measuring');
  state.statistics = 'ok';
  state.release();
  await step.locator('text=Measured over the AOI ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('the held question was not answered'));
  if (await page.getByRole('button', { name: 'Review', exact: true }).isDisabled()) problems.push('Review stays held after the numbers came');
  await shot(step, name, 'measured');
  // A failure: the reason of the route, and "Retry".
  state.statistics = 'fail';
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.5, 50.4], [10.5, 50.5], [10.4, 50.5], [10.4, 50.4]]] } });
  });
  await step.locator('text=Not measured.').waitFor({ timeout: 5000 }).catch(() => problems.push('a failure is not told'));
  const title = await page.getByRole('button', { name: 'Review', exact: true }).getAttribute('title');
  if (!title?.startsWith('Normalize: the measurement failed: ') || !title.includes('The area is too large to measure.')) problems.push(`the failure says ${title}`);
  await layout(page, problems);
  await shot(step, name, 'failed');
  state.statistics = 'ok';
  await step.getByRole('button', { name: 'Retry' }).click();
  await step.locator('text=Measured over the AOI ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('Retry did not measure again'));
  await context.close();
  return { name, problems };
}

async function checkLocked(browser, theme, viewport) {
  const name = `locked ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'ok', asked: [] };
  const { context, page } = await open(browser, theme, viewport, state);
  await selectScene(page, false);
  await page.getByRole('button', { name: '＋ Normalize' }).click();
  const step = page.locator('li.pp-step').first();
  const off = await step.locator('select[id$="-method"] option').evaluateAll((o) => o.map((x) => `${x.value}:${x.disabled}`).join());
  if (off !== 'linear:false,percentile:true,zscore:true,robust:true') problems.push(`the options are ${off}`);
  const tips = await step.locator('[data-tip]').evaluateAll((t) => t.map((x) => x.getAttribute('data-tip')).join(' '));
  if (!tips.includes('Draw an AOI; the values are measured over it')) problems.push('the reason is not in a tooltip');
  if (state.asked.length > 0) problems.push('a question was asked without an AOI');
  await layout(page, problems);
  await shot(step, name, 'locked');
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      results.push(await checkMethods(browser, theme, viewport));
      results.push(await checkWaiting(browser, theme, viewport));
      results.push(await checkLocked(browser, theme, viewport));
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
