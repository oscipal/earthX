// Browser check of ⚙ at the layer of a result (NM4-05b), in a real browser with made-up answers of the platform:
//   1. The layer manager: ⚙ in the row of a result with the order of its job, active; no ⚙ (the place stays empty) without one.
//   2. The panel it opens: the result as an entity of its own, with the bands of its output as its bands and no steps shown; the
//      area choice of the panel of a scene ("Whole scene" is the result, "AOI only" an AOI cut to it), "Load recipe…", no "Run as"; no mask
//      where the output lacks the layer; a band the output did not keep cannot be read; "RGB" in "Show"; "Review" and
//      "Start job" send one order with all the steps, and the job it makes lies beside the old one.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/process-result.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-process-result');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const NEW_JOBS = ['QrStUvWxYzAbCdEfGhIj_-', 'AaBbCcDdEeFfGgHhIiJj_-', 'KkLlMmNnOoPpQqRrSsTt_-'];

const STAT = { count: 900, min: 0.01, max: 0.9, percentile_2: 0.05, percentile_98: 0.7, unit: null };

const COLLECTION = {
  id: 'sentinel-2-c1-l2a',
  'earthx:format': 'cog',
  'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { interpolation: true },
  'earthx:true_color': ['red', 'green', 'blue'],
  'earthx:mask': { asset: 'scl', band: 'scl', classes: [{ value: 3, label: 'CLOUD_SHADOWS' }], suggested: [3], reference: 'https://example.org/scl', note: '' },
};

async function open(browser, theme, viewport) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const posted = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/estimate')) {
      return json({ estimate: { size: 4e6, duration: 'PT3.4S', outputPixels: 1e6, inputPixels: 2e6, inputBytes: 4e6, assets: 4, units: 1 }, skippedItems: [] });
    }
    if (url.pathname.endsWith('/execution')) {
      posted.push(JSON.parse(route.request().postData()).inputs.recipe);
      return json({ processID: 'recipe', type: 'process', jobID: NEW_JOBS[posted.length - 1] ?? NEW_JOBS[0], status: 'accepted', message: '', progress: 0, created: '2026-10-31T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    if (url.pathname.endsWith('/statistics')) return json({ b1: STAT, b2: STAT });
    if (url.pathname === `/results/${RESULT}/WebMercatorQuad/tilejson.json`) return json({ bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: [] });
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page, posted };
}

// A scene, a finished job with the order it was started with, and its result as a layer.
async function setUp(page, withOrder) {
  await page.evaluate(
    async ({ collection, job, result, withOrder }) => {
      const { useAppStore } = await import('/src/store.ts');
      const { useProcessingStore } = await import('/src/processingStore.ts');
      const { jobEntry } = await import('/src/fixtures/jobEntries.ts');
      const bbox = [10, 50, 11, 51];
      const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
      const aoi = { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] };
      const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
      const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
      const item = {
        id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox, geometry: polygon,
        properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
        assets: { red: asset(), green: asset(), blue: asset(), nir: asset(), scl: asset() },
      };
      useAppStore.setState({
        datasets: [{
          id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
          browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection,
        }],
        datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
        activeGroupIndex: 0, selectedIds: [], aoi: null, aoiPoint: null, layers: [], focusMode: false, error: null,
      });
      const order = {
        recipe_version: 2,
        inputs: [{ name: 'input', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
        aoi,
        steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'NDVI' } }],
        output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI', 'red', 'green', 'blue'] },
      };
      useProcessingStore.setState({
        jobs: [jobEntry(1, {
          jobID: job, expires: new Date(Date.now() + 86_400_000).toISOString(), phase: 'successful', title: 'NDVI of a field',
          tiles: { href: `/results/${result}/WebMercatorQuad/tilejson.json`, width: 1000, gsd: 10 }, order: withOrder ? order : null,
        })],
      });
      useAppStore.setState({ dock: 'layers' });
      await useProcessingStore.getState().showResultOnMap(job);
    },
    { collection: COLLECTION, job: JOB, result: RESULT, withOrder },
  );
  await page.waitForSelector('.layer-row [data-col="process"]', { timeout: 10000 });
}

const gear = (page) => page.locator('.layer-row [data-col="process"]');

async function check(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  fs.mkdirSync(OUT, { recursive: true });

  // 1. Without the order of the job: no ⚙, the place stays empty.
  {
    const { context, page } = await open(browser, theme, viewport);
    await setUp(page, false);
    if ((await gear(page).evaluate((e) => e.tagName)) !== 'SPAN') problems.push('there is a ⚙ without the order of the job');
    if ((await page.locator('.layer-row').first().locator(':scope > *').count()) !== 10) problems.push('the row lost a place without ⚙');
    await context.close();
  }

  // 2. With it.
  const { context, page, posted } = await open(browser, theme, viewport);
  await setUp(page, true);
  if (await gear(page).isDisabled()) problems.push('the ⚙ is locked with the order of the job');
  if ((await gear(page).getAttribute('title')) !== 'Process further') problems.push(`the ⚙ says ${await gear(page).getAttribute('title')}`);
  await gear(page).click();
  await page.waitForSelector('.processing-panel section[aria-label="Selection"] [aria-label="Area"]', { timeout: 10000 });

  const panel = page.locator('.processing-panel');
  if ((await panel.locator('.pp-step').count()) !== 0) problems.push('the steps of the job are shown as steps');
  const chips = async (selector) => page.$$eval(selector, (c) => c.map((x) => x.textContent));
  if ((await chips('section[aria-label="Bands"] .pp-chip')).join() !== 'NDVI,red,green,blue') problems.push(`the bands on top are ${await chips('section[aria-label="Bands"] .pp-chip')}`);
  if ((await panel.getByRole('button', { name: '＋ Mask' }).count()) !== 0) problems.push('a mask is offered without its layer in the output');
  // The same area choice as the panel of a scene: "Whole scene" is the area of the result, "AOI only" an AOI inside it.
  if ((await panel.getByRole('button', { name: 'Whole scene' }).getAttribute('aria-pressed')) !== 'true') problems.push('"Whole scene" is not the start');
  if (await panel.getByRole('button', { name: 'AOI only' }).isDisabled()) problems.push('"AOI only" is locked although the map has an AOI');
  if ((await panel.locator('[aria-label="Run as"]').count()) !== 0) problems.push('"Run as" is offered');
  if ((await panel.getByText('Load recipe').count()) !== 1) problems.push('"Load recipe…" is not offered');
  if ((await panel.getByText('From result').count()) !== 0) problems.push('the panel has a line "From result"');
  if ((await panel.locator('.pp-area .tip').count()) !== 0) problems.push('the area has a tooltip of the chain');
  const labels = await page.$$eval('section[aria-label="Output"] .pp-chip-row .pp-help', (e) => e.map((x) => x.textContent));
  if (labels.join() !== 'Data') problems.push(`the groups of the output are ${labels}`);

  // The bands of the job are listed in "Data", none of them checked; "Start job" waits for one.
  const stored = () => page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().output);
  if ((await stored()).length !== 0) problems.push(`the output starts with ${await stored()}`);
  if ((await page.$$('section[aria-label="Output"] [aria-label="Bands of the data"] .pp-chip[aria-pressed="true"]')).length !== 0) problems.push('a band of the result is checked');
  if (!(await panel.locator('button.primary-btn', { hasText: 'Start job' }).isDisabled())) problems.push('"Start job" is active with nothing checked');
  for (const name of ['NDVI', 'red', 'green', 'blue']) await panel.locator('section[aria-label="Output"] [aria-label="Bands of the data"]').getByRole('button', { name, exact: true }).click();
  // RGB is on offer once the three bands are in the output.
  const options = await page.$$eval('.pp-show select option', (o) => o.map((x) => x.value));
  if (options.join() !== '@rgb,NDVI,red,green,blue') problems.push(`"Show" offers ${options}`);
  if ((await stored()).join() !== 'NDVI,red,green,blue') problems.push(`the output is ${await stored()}`);

  // A new step reads the bands of the job, not the stock it did not keep.
  await panel.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('nir * 2');
  if ((await page.locator('.pp-step .hint-text.error').first().textContent()) !== "'nir' is not a band name") problems.push('a band outside the output can be read');
  await page.locator('textarea[id$="-expression"]').fill('NDVI * 2');
  const earlier = await chips('[aria-label="Results of earlier steps"] .pp-chip');
  if (earlier.join() !== 'NDVI') problems.push(`the new step offers the chips ${earlier}`);

  const layout = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const root = document.querySelector('.processing-panel');
    const body = root.querySelector('.pp-body');
    const section = root.querySelector('section[aria-label="Selection"]');
    return {
      theme: document.querySelector('.app')?.dataset.theme,
      panel: box(root),
      scrolls: body.scrollWidth > body.clientWidth + 1,
      leaves: [...section.querySelectorAll('p, span.pp-fixed, .pp-toggle')].map((e) => ({ what: e.tagName.toLowerCase(), ...box(e) })).filter((c) => c.width > 0),
    };
  });
  for (let i = 0; i < layout.leaves.length; i++) {
    const leaf = layout.leaves[i];
    if (leaf.x < layout.panel.x - 0.5 || leaf.x + leaf.width > layout.panel.x + layout.panel.width + 0.5) problems.push(`${leaf.what} leaves the panel`);
  }
  if (layout.theme !== THEMES[theme]) problems.push(`the app shows the theme ${layout.theme}`);
  if (layout.scrolls) problems.push('the panel scrolls sideways');
  await page.waitForTimeout(500);
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_panel.png`) });

  // Review and start: one order, the steps in order, a new job beside the old one.
  await panel.getByRole('button', { name: 'Review', exact: true }).click();
  await page.waitForSelector('.processing-panel button.primary-btn:not([disabled])', { timeout: 10000 });
  await panel.locator('button.primary-btn', { hasText: 'Start job' }).click();
  await page.waitForTimeout(800);
  if (posted.length !== 1) problems.push(`${posted.length} orders were sent`);
  else {
    const order = posted[0];
    if (order.steps.map((s) => s.params.name).join() !== 'NDVI,result') problems.push(`the steps are ${order.steps.map((s) => s.params.name)}`);
    if (order.output.bands.join() !== 'NDVI,result,red,green,blue') problems.push(`the output is ${order.output.bands}`);
    if (order.inputs[0].groups[0].join() !== 'S2B_A') problems.push('the scenes are not those of the job');
    if (!order.aoi) problems.push('the order has no area');
  }
  // "AOI only": another AOI inside the result is the area of the next order; one that misses it is turned away.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().setAoi({ type: 'Polygon', coordinates: [[[10.7, 50.7], [10.9, 50.7], [10.9, 50.9], [10.7, 50.9], [10.7, 50.7]]] });
  });
  await panel.getByRole('button', { name: 'AOI only' }).click();
  if (!(await panel.getByText('The AOI does not meet the result.').count())) problems.push('an AOI that misses the result is not turned away');
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().setAoi({ type: 'Polygon', coordinates: [[[10.45, 50.45], [10.5, 50.45], [10.5, 50.5], [10.45, 50.5], [10.45, 50.45]]] });
  });
  await page.waitForTimeout(300);
  if (await panel.getByText('The AOI does not meet the result.').count()) problems.push('an AOI inside the result is turned away');
  await panel.getByRole('button', { name: 'Review', exact: true }).click();
  await page.waitForSelector('.processing-panel button.primary-btn:not([disabled])', { timeout: 10000 });
  await panel.locator('button.primary-btn', { hasText: 'Start job' }).click();
  await page.waitForTimeout(800);
  if (posted.length !== 2 || posted[1].aoi.coordinates[0][0].join() !== '10.45,50.45') problems.push(`the second order has the area ${JSON.stringify(posted[1]?.aoi)}`);
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_inner.png`) });
  // The preview lies above the result, with the entry "Results".
  if ((await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().resultsAt)) !== 0) problems.push('the preview lies below the result');
  // An AOI that covers part of the result: only that part is the area of the order.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().setAoi({ type: 'Polygon', coordinates: [[[10.5, 50.5], [10.8, 50.5], [10.8, 50.8], [10.5, 50.8], [10.5, 50.5]]] });
  });
  await page.waitForTimeout(300);
  if (await panel.getByText('The AOI does not meet the result.').count()) problems.push('an AOI that covers part of the result is turned away');
  await panel.getByRole('button', { name: 'Review', exact: true }).click();
  await page.waitForSelector('.processing-panel button.primary-btn:not([disabled])', { timeout: 10000 });
  await panel.locator('button.primary-btn', { hasText: 'Start job' }).click();
  await page.waitForTimeout(800);
  const part = (posted[2]?.aoi?.coordinates?.[0] ?? []).flat();
  const xs = part.filter((_, i) => i % 2 === 0);
  const ys = part.filter((_, i) => i % 2 === 1);
  if (posted.length !== 3 || Math.max(...xs) > 10.6 + 1e-9 || Math.max(...ys) > 50.6 + 1e-9 || Math.min(...xs) < 10.5 - 1e-9) problems.push(`the part of the AOI is ${JSON.stringify(posted[2]?.aoi)}`);

  const jobs = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().jobs.map((j) => [j.jobID, j.title]));
  if (jobs.length !== 4 || jobs[3][0] !== JOB) problems.push(`the jobs are ${JSON.stringify(jobs)}`);
  if (jobs[2]?.[1] !== 'NDVI of a field → Band math') problems.push(`the new job is called ${jobs[0]?.[1]}`);
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const { name, problems } = await check(browser, theme, viewport);
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
      for (const problem of problems) console.log(`       - ${problem}`);
      if (problems.length > 0) failed = true;
    }
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
