// Browser check of "Normalize" with its methods in the processing panel (NM4-11b, NM4-71), in a real browser with made-up
// answers of the server (the process description of the fixtures, the statistics, the estimate and the results of a job):
//   1. The step: four methods, the fields of each in one row, the explanations only as tooltips (Z-score warns of outliers),
//      a comma told at the field.
//   2. The review: the measure is for the preview alone. "Review" and "Start job" are not held while it runs or has failed; the
//      order the job gets is `normalize` version 4 without numbers.
//   3. Without an AOI the methods that measure can be chosen, the question holds no AOI, the (i) of the step says the preview is
//      an estimate or measured exactly (no line of text for it); after a reprojection they stay off, with the reason.
//   4. A large AOI where the route reads on a coarser raster.
//   5. ⚙ at a result with `earthx:normalize`: the locked step becomes version 3 with the numbers of the result and measures
//      nothing; a band the result lacks keeps the step at version 4.
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

const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const COLLECTION = { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } };
const AOI = { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] };
const ESTIMATE = { estimate: { size: 4e6, duration: 'PT3.4S', outputPixels: 1e6, inputPixels: 2e6, inputBytes: 4e6, assets: 2, units: 1 }, skippedItems: [] };
const ESTIMATED = 'Preview estimated on a coarser read; the job measures exactly.';
const EXACT = 'Preview measured exactly over the AOI.';

// `state.statistics`: what the route answers next: 'ok', 'fail', or 'hold' (no answer until `state.release()`); `state.exact` and
// `state.factor` are what it says of its read; `state.results` is the `earthx:normalize` of the result of the job (or none).
async function open(browser, theme, viewport, state) {
  state.asked = [];
  state.estimates = [];
  state.resultsAsked = 0;
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: status === 200 ? 'application/json' : 'application/problem+json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/estimate')) {
      state.estimates.push(JSON.parse(route.request().postData()).inputs.recipe);
      return json(ESTIMATE);
    }
    if (url.pathname === `/processing/jobs/${JOB}/results`) {
      state.resultsAsked += 1;
      return json({ result: { href: '/r', properties: state.results ? { 'earthx:normalize': state.results } : {} } });
    }
    if (url.pathname === `/results/${RESULT}/WebMercatorQuad/tilejson.json`) return json({ bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: [] });
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    if (url.pathname.endsWith('/statistics') && route.request().method() === 'POST') {
      state.asked.push(JSON.parse(route.request().postData()));
      if (state.statistics === 'hold') await new Promise((resolve) => (state.release = resolve));
      if (state.statistics === 'fail') return json({ detail: 'The area is too large to measure.' }, 422);
      const bands = state.asked.at(-1).output.bands;
      return json({ bands: bands.map((name) => ({ name, unit: null, statistics: STATISTICS })), exact: state.exact ?? true, factor: state.factor ?? 1 });
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page };
}

async function selectScene(page, withAoi, aoi = AOI) {
  await page.evaluate(async ({ aoi, collection }) => {
    const { useAppStore } = await import('/src/store.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const asset = { href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] };
    const id = 'sentinel-2-c1-l2a';
    const item = { id: 'ITEM_A', collection: id, bbox, geometry: polygon, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { red: asset, nir: asset } };
    useAppStore.setState({
      datasets: [{ id, title: id, viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection }],
      datasetId: id, items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['ITEM_A'], aoi, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
  }, { aoi: withAoi ? aoi : null, collection: COLLECTION });
  await page.evaluate(async (aoi) => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().openProcessing();
    if (aoi) useProcessingStore.getState().setArea('aoi');
  }, withAoi);
  await page.getByRole('button', { name: '＋ Normalize' }).waitFor({ timeout: 15000 });
}

// The step with the band `red` chosen and in the output, and the method.
async function withStep(page, method) {
  await page.getByRole('button', { name: '＋ Normalize' }).click();
  await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().setOutput(['red']);
    useProcessingStore.getState().updateStep(useProcessingStore.getState().steps[0].key, 'bands', 'red');
  });
  const step = page.locator('li.pp-step').first();
  if (method) await step.locator('select[id$="-method"]').selectOption(method);
  return step;
}

const tipsOf = (locator) => locator.locator('[data-tip]').evaluateAll((t) => t.map((x) => x.getAttribute('data-tip')).join('\n'));
const review = (page) => page.getByRole('button', { name: 'Review', exact: true });
const start = (page) => page.getByRole('button', { name: 'Start job', exact: true });

// Whether the leaves of the step stay inside the panel and do not lie on each other.
async function layout(page, problems) {
  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const step = document.querySelector('li.pp-step');
    const body = step?.closest('.pp-body') ?? document.querySelector('.processing-panel');
    return {
      theme: document.querySelector('.app')?.dataset.theme,
      panel: box(body),
      scrolls: body.scrollWidth > body.clientWidth + 1,
      leaves: [...(step?.querySelectorAll('input, select') ?? [])].filter((e) => e.offsetParent).map((e) => ({ what: e.getAttribute('aria-label') ?? e.id ?? e.tagName.toLowerCase(), ...box(e) })),
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

async function shot(target, name, suffix) {
  fs.mkdirSync(OUT, { recursive: true });
  await target.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_${suffix}.png`) });
}

async function checkMethods(browser, theme, viewport) {
  const name = `methods ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'ok' };
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
  const tips = await tipsOf(step);
  if (!tips.includes('NDVI −1…1 → 0…1') || !tips.includes('(x − from) / (to − from)')) problems.push('the tooltip has no example or formula');
  if (!tips.includes('Sensitive to outliers, e.g. in indices; prefer Robust (median, IQR) there.')) problems.push('the tooltip of Z-score does not warn of outliers');
  await step.locator('select[id$="-method"]').selectOption('percentile');
  await step.locator('text=Preview measured ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('the numbers were not measured'));
  if ((await shown()) !== 'method,range,Target min,Target max,clip') problems.push(`percentile shows ${await shown()}`);
  if ((await step.locator('select[id$="-range"]').inputValue()) !== '2–98 %') problems.push('the range does not start at 2–98 %');
  const body = state.asked[0];
  if (!body || body.output.dtype !== 'float64' || body.steps.length !== 0 || JSON.stringify(body.output.bands) !== '["red"]') problems.push(`the question is ${JSON.stringify(body?.output)}`);
  const numbers = await tipsOf(step);
  if (!numbers.includes('p_low 200, p_high 6000')) problems.push('the numbers are not in the tooltip');
  if (!numbers.includes(EXACT)) problems.push('the tooltip does not say the preview is measured exactly');
  if ((await step.innerText()).includes(EXACT)) problems.push('the note on the read is a line of text');
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

// "Review" and "Start job" do not wait for the measure of the preview, which runs, fails and is asked again.
async function checkReview(browser, theme, viewport) {
  const name = `review ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'hold', release: null };
  const { context, page } = await open(browser, theme, viewport, state);
  await selectScene(page, true);
  const step = await withStep(page, 'zscore');
  await step.locator('text=Measuring…').waitFor({ timeout: 5000 }).catch(() => problems.push('no "Measuring…"'));
  for (const button of [review(page), start(page)]) {
    if (/measuring/i.test((await button.getAttribute('title')) ?? '')) problems.push(`a button says ${await button.getAttribute('title')}`);
  }
  if (await review(page).isDisabled()) problems.push('Review is held while the measure runs');
  await review(page).click();
  await page.waitForFunction(() => document.querySelector('.pp-estimate') !== null, null, { timeout: 5000 }).catch(() => problems.push('Review did not go to the server while the measure runs'));
  if (await start(page).isDisabled()) problems.push('Start job is held after the review');
  const sent = state.estimates.at(-1)?.steps;
  if (JSON.stringify(sent) !== JSON.stringify([{ op: 'normalize', op_version: 4, params: { method: 'zscore', bands: ['red'] } }])) problems.push(`the job gets ${JSON.stringify(sent)}`);
  await layout(page, problems);
  await shot(step, name, 'measuring');
  state.statistics = 'ok';
  state.release();
  await step.locator('text=Preview measured ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('the held question was not answered'));
  await shot(step, name, 'measured');
  // A failure: the reason of the route behind the (!), "Retry"; nothing is held.
  state.statistics = 'fail';
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.5, 50.4], [10.5, 50.5], [10.4, 50.5], [10.4, 50.4]]] } });
  });
  await step.locator('text=Not measured.').waitFor({ timeout: 5000 }).catch(() => problems.push('a failure is not told'));
  const reason = await tipsOf(step);
  if (!reason.includes('The measurement failed:') || !reason.includes('The area is too large to measure.')) problems.push(`the failure says ${reason}`);
  if (await review(page).isDisabled()) problems.push('Review is held after a failed measure');
  await review(page).click();
  await page.waitForTimeout(300);
  if (state.estimates.length < 2) problems.push('Review does not go to the server after a failed measure');
  await layout(page, problems);
  await shot(step, name, 'failed');
  state.statistics = 'ok';
  await step.getByRole('button', { name: 'Retry' }).click();
  await step.locator('text=Preview measured ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('Retry did not measure again'));
  await context.close();
  return { name, problems };
}

// No AOI: the methods that measure can be chosen; the route reads the whole scenes on a coarser raster.
async function checkNoAoi(browser, theme, viewport) {
  const name = `no-aoi ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'ok', exact: false, factor: 6 };
  const { context, page } = await open(browser, theme, viewport, state);
  await selectScene(page, false);
  const step = await withStep(page, null);
  const off = await step.locator('select[id$="-method"] option').evaluateAll((o) => o.map((x) => `${x.value}:${x.disabled}`).join());
  if (off !== 'linear:false,percentile:false,zscore:false,robust:false') problems.push(`the options are ${off}`);
  if ((await tipsOf(step)).includes('Draw an AOI')) problems.push('a tooltip still asks for an AOI');
  if (state.asked.length > 0) problems.push('a question was asked for a fixed range');
  await step.locator('select[id$="-method"]').selectOption('robust');
  await step.locator('text=Preview measured ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('the whole scenes were not measured'));
  if (state.asked.length !== 1 || 'aoi' in state.asked[0]) problems.push(`the question is ${JSON.stringify(state.asked[0]?.aoi ?? 'without aoi')}`);
  const tips = await tipsOf(step);
  if (!tips.includes(ESTIMATED)) problems.push('the tooltip does not say the preview is an estimate');
  if ((await step.innerText()).includes('coarser')) problems.push('the estimate is a line of text');
  if (await review(page).isDisabled()) problems.push('Review is held');
  await review(page).click();
  await page.waitForFunction(() => document.querySelector('.pp-estimate') !== null, null, { timeout: 5000 }).catch(() => problems.push('Review did not go to the server'));
  const recipe = state.estimates.at(-1);
  if (!recipe || 'aoi' in recipe) problems.push('the job holds an AOI');
  if (JSON.stringify(recipe?.steps) !== JSON.stringify([{ op: 'normalize', op_version: 4, params: { method: 'robust', bands: ['red'] } }])) problems.push(`the job gets ${JSON.stringify(recipe?.steps)}`);
  await layout(page, problems);
  await shot(step, name, 'estimated');
  await context.close();
  return { name, problems };
}

// A large AOI: the route says it read coarser; behind a reprojection the methods stay off, with the reason.
async function checkLarge(browser, theme, viewport) {
  const name = `large ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'ok', exact: false, factor: 3 };
  const { context, page } = await open(browser, theme, viewport, state);
  await selectScene(page, true);
  const step = await withStep(page, 'percentile');
  await step.locator('text=Preview measured ✓').waitFor({ timeout: 5000 }).catch(() => problems.push('the AOI was not measured'));
  if (!(await tipsOf(step)).includes(ESTIMATED)) problems.push('the tooltip does not say the preview is an estimate');
  if (state.asked[0]?.aoi === undefined) problems.push('the question holds no AOI');
  state.exact = true;
  state.factor = 1;
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.setState({ aoi: { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.5, 50.4], [10.5, 50.5], [10.4, 50.5], [10.4, 50.4]]] } });
  });
  await page.waitForFunction((text) => [...document.querySelectorAll('li.pp-step [data-tip]')].some((t) => t.getAttribute('data-tip').includes(text)), EXACT, { timeout: 5000 }).catch(() => problems.push('the tooltip does not say the preview is measured exactly'));
  // Behind a reprojection.
  await page.getByRole('button', { name: /＋ Reproject/ }).click();
  await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const steps = useProcessingStore.getState().steps;
    useProcessingStore.getState().moveStep(steps[1].key, -1);
  });
  const later = page.locator('li.pp-step').nth(1);
  const locked = await later.locator('select[id$="-method"] option').evaluateAll((o) => o.map((x) => `${x.value}:${x.disabled}`).join());
  // The method the step holds stays on offer; the others that measure are off.
  if (locked !== 'linear:false,percentile:false,zscore:true,robust:true') problems.push(`the options behind a reprojection are ${locked}`);
  if (!(await tipsOf(later)).includes('Move Normalize above Reproject')) problems.push('the reason behind a reprojection is not in a tooltip');
  await layout(page, problems);
  await shot(page.locator('.processing-panel'), name, 'panel');
  await context.close();
  return { name, problems };
}

// ⚙ at a result: a locked step of the job. `bands` are the bands of the step, `normalize` what the job wrote to `earthx:normalize`
// (the page reads it from the results of the job, which the made-up server answers).
async function extendCase(browser, theme, viewport, label, { bands, normalize, check }) {
  const name = `extend ${label} ${theme} ${viewport}`;
  const problems = [];
  const state = { statistics: 'ok', results: normalize };
  const { context, page } = await open(browser, theme, viewport, state);
  await page.evaluate(
    async ({ collection, job, result, aoi, bands }) => {
      const { useAppStore } = await import('/src/store.ts');
      const { useProcessingStore } = await import('/src/processingStore.ts');
      const { jobEntry } = await import('/src/fixtures/jobEntries.ts');
      const bbox = [10, 50, 11, 51];
      const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
      const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
      const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
      const item = { id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox, geometry: polygon, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { red: asset(), nir: asset() } };
      useAppStore.setState({
        datasets: [{ id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection }],
        datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
        activeGroupIndex: 0, selectedIds: [], aoi: null, aoiPoint: null, layers: [], focusMode: false, error: null,
      });
      const order = {
        recipe_version: 2,
        inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
        aoi,
        steps: [{ op: 'normalize', op_version: 4, params: { method: 'zscore', bands } }],
        output: { kind: 'raster', format: 'cog', dtype: 'float32', bands },
      };
      useProcessingStore.setState({
        jobs: [jobEntry(1, { jobID: job, expires: new Date(Date.now() + 86_400_000).toISOString(), phase: 'successful', title: 'Normalized', tiles: { href: `/results/${result}/WebMercatorQuad/tilejson.json`, width: 1000, gsd: 10 }, order })],
      });
      useAppStore.setState({ dock: 'layers' });
      await useProcessingStore.getState().showResultOnMap(job);
    },
    { collection: COLLECTION, job: JOB, result: RESULT, aoi: AOI, bands },
  );
  const gear = page.locator('.layer-row [data-col="process"]');
  await gear.waitFor({ timeout: 10000 });
  await gear.click();
  await page.waitForSelector('.processing-panel section[aria-label="Selection"] [aria-label="Area"]', { timeout: 10000 });
  await page.waitForTimeout(600);
  if (await page.locator('.processing-panel li.pp-step').count()) problems.push('the locked step is shown as a step');
  // The bands of the result are in the list of the output; a result of one band has it checked already.
  const red = page.locator('.processing-panel section[aria-label="Output"] .pp-chip', { hasText: 'red' }).first();
  if ((await red.getAttribute('aria-pressed')) !== 'true') await red.click();
  const view = await page.evaluate(async () => {
    const { orderView, selectionState, useProcessingStore } = await import('/src/processingStore.ts');
    const { useAppStore } = await import('/src/store.ts');
    const v = orderView(selectionState(useAppStore.getState()), useProcessingStore.getState());
    return { step: v.built?.order?.steps?.[0] ?? null, text: v.measures[0]?.text ?? null };
  });
  check(view, state, problems);
  if (await review(page).isDisabled()) problems.push('Review is held');
  await review(page).click();
  await page.waitForFunction(() => document.querySelector('.pp-estimate') !== null, null, { timeout: 5000 }).catch(() => problems.push('Review did not go to the server'));
  const sent = state.estimates.at(-1)?.steps?.[0];
  if (JSON.stringify(sent) !== JSON.stringify(view.step)) problems.push(`the job gets ${JSON.stringify(sent)}, the panel built ${JSON.stringify(view.step)}`);
  await layout(page, problems);
  await shot(page.locator('.processing-panel'), name, 'panel');
  await context.close();
  return { name, problems };
}

const checkExtend = async (browser, theme, viewport) => [
  // The result has the numbers: version 3 with them, nothing measured.
  await extendCase(browser, theme, viewport, 'kept', {
    bands: ['red'],
    normalize: [{ step: 0, method: 'zscore', bands: { red: { mean: 11, stddev: 4 } }, exact: true }],
    check: (view, state, problems) => {
      const wanted = { op: 'normalize', op_version: 3, params: { method: 'zscore', bands: ['red'], measured: { factor: 1, bands: { red: { mean: 11, stddev: 4 } } } } };
      if (JSON.stringify(view.step) !== JSON.stringify(wanted)) problems.push(`the locked step is ${JSON.stringify(view.step)}`);
      if (state.resultsAsked !== 1) problems.push(`the results were asked ${state.resultsAsked} times`);
      if (state.asked.some((q) => q.output.dtype === 'float64')) problems.push('the locked step was measured');
    },
  }),
  // The result lacks the numbers of a band: version 4, measured anew in the run (the preview still asks for its numbers).
  await extendCase(browser, theme, viewport, 'band-missing', {
    bands: ['red', 'nir'],
    normalize: [{ step: 0, method: 'zscore', bands: { red: { mean: 11, stddev: 4 } }, exact: true }],
    check: (view, state, problems) => {
      if (view.step?.op_version !== 4 || 'measured' in (view.step?.params ?? {})) problems.push(`the locked step is ${JSON.stringify(view.step)}`);
      if (!view.text?.includes('Measured anew in the run.')) problems.push(`the tooltip says ${view.text}`);
    },
  }),
];

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      results.push(await checkMethods(browser, theme, viewport));
      results.push(await checkReview(browser, theme, viewport));
      results.push(await checkNoAoi(browser, theme, viewport));
      results.push(await checkLarge(browser, theme, viewport));
      results.push(...(await checkExtend(browser, theme, viewport)));
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
