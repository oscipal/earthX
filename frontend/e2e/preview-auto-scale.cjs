// "Auto-scale" of the preview in the processing panel through Otto's path (check in the browser, 11.11.2026): a Sentinel-2 scene, one Band
// math step, the preview appears, "Review", "Start job", the job runs, the job ends — with the output type the panel chooses and with uint16
// chosen by hand, which after Band math gives way to float32 (Otto, 11.11.2026).
// Light and dark theme, a wide and a narrow window. Fails when "Auto-scale" is locked at any of these points, or when, with a range set by
// hand while the job runs or after it ended, it does not put the measured range back into the fields and on the map.
// It writes a screenshot of the preview per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/preview-auto-scale.cjs         # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-preview-auto-scale');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const JOB = 'QrStUvWxYzAbCdEfGhIj_-';
// The measure over the AOI (made up) lies in −1…1 and comes from Band math: an index, drawn at −1…1 (`render.ts::scaleOf`).
const MEASURED = ['-1', '1'];

async function check(browser, { dtype, theme, viewport }) {
  const label = `${dtype ?? 'automatic'} ${theme} ${viewport}`;
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  let phase = 'running';
  const sent = [];
  await page.route('**/*', async (route) => {
    const r = route.request(); const url = new URL(r.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: [] });
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/estimate')) return json({ estimate: { size: 4e6, duration: 'PT3.4S', outputPixels: 1e6, inputPixels: 2e6, inputBytes: 4e6, assets: 2, units: 1 }, skippedItems: [] });
    if (url.pathname.endsWith('/execution')) sent.push(JSON.parse(r.postData()).inputs.recipe.output.dtype);
    if (url.pathname.endsWith('/execution')) return json({ processID: 'recipe', type: 'process', jobID: JOB, status: 'accepted', message: '', progress: 0, created: new Date().toISOString(), expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    if (url.pathname === `/processing/jobs/${JOB}`) return json({ processID: 'recipe', type: 'process', jobID: JOB, status: phase, message: '', progress: phase === 'running' ? 40 : 100, created: new Date().toISOString(), expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), links: [] });
    if (r.method() === 'POST' && url.pathname.endsWith('/statistics')) return json({ bands: [{ name: 'result', statistics: { minimum: -0.3, maximum: 0.9, count: 900, percentile_2: 0.1, percentile_98: 0.8, valid_percent: 100 } }], exact: true, factor: 1 });
    if (url.pathname.endsWith('/statistics')) return json({ result: { count: 900, min: -0.3, max: 0.9, percentile_2: 0.1, percentile_98: 0.8, unit: null } });
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: [10, 50, 11, 51], minzoom: 8, maxzoom: 14 });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForTimeout(300);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const aoi = { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const band = { data_type: 'uint16', nodata: 0 };
    const item = { id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox: [10, 50, 11, 51], geometry: polygon, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
      assets: { red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [band] }, nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [band] } } };
    useAppStore.setState({ datasets: [{ id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
        collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true, band_math: true } } }],
      datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }], activeGroupIndex: 0, selectedIds: ['S2B_A'], aoi, aoiPoint: null, layers: [], focusMode: false, error: null });
    useProcessingStore.getState().openProcessing();
  });
  const panel = page.locator('.processing-panel');
  const problems = [];
  const preview = page.locator('section[aria-label="Preview on the map"]');
  const auto = preview.getByRole('button', { name: 'Auto-scale', exact: true });
  const fields = () => preview.locator('.pp-range input').evaluateAll((inputs) => inputs.map((i) => i.value));
  const free = async (when) => {
    if ((await auto.count()) !== 1) problems.push(`${when}: no "Auto-scale"`);
    else if (await auto.isDisabled()) problems.push(`${when}: "Auto-scale" is locked`);
  };
  // A range by hand, then "Auto-scale": the measured range is back.
  const backToMeasure = async (when) => {
    await preview.locator('.pp-range input').first().fill('0');
    await preview.locator('.pp-range button.vc-apply').click();
    await page.waitForTimeout(500);
    await free(`${when}, range by hand`);
    if ((await auto.count()) === 1 && !(await auto.isDisabled())) await auto.click();
    await page.waitForTimeout(900);
    const got = (await fields()).slice(0, 2);
    if (JSON.stringify(got) !== JSON.stringify(MEASURED)) problems.push(`${when}: "Auto-scale" leaves ${JSON.stringify(got)}, not ${JSON.stringify(MEASURED)}`);
  };
  await page.getByRole('button', { name: 'AOI only' }).click();
  await page.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  await page.waitForTimeout(1500);
  if (dtype) {
    await page.evaluate(async (d) => (await import('/src/processingStore.ts')).useProcessingStore.getState().setDtype(d), dtype);
    await page.waitForTimeout(1200);
  }
  await free('the first preview');
  await panel.getByRole('button', { name: 'Review', exact: true }).click();
  await page.waitForSelector('.processing-panel button.btn.primary:not([disabled])', { timeout: 10000 });
  await free('after "Review"');
  await panel.locator('button.btn.primary', { hasText: 'Start job' }).click();
  await page.waitForTimeout(1500);
  const jobPhase = () => page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().jobs.map((j) => j.phase).join());
  if ((await jobPhase()) !== 'active') problems.push(`the job is ${await jobPhase()}, not active`);
  // After Band math only float32 makes sense: a choice of uint16 gives way to it (Otto, 11.11.2026).
  if (JSON.stringify(sent) !== '["float32"]') problems.push(`the job was sent as ${JSON.stringify(sent)}, not float32`);
  await free('while the job runs');
  await backToMeasure('while the job runs');
  phase = 'successful';
  await page.waitForFunction(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().jobs.every((j) => j.phase === 'successful'), null, { timeout: 15000 }).catch(() => problems.push('the job did not end'));
  await free('after the job ended');
  await backToMeasure('after the job ended');
  await preview.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}.png`) });
  await context.close();
  return { label, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const dtype of [null, 'uint16']) for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) {
    const result = await check(browser, { dtype, theme, viewport });
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.label}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : '"Auto-scale" of the preview can be pressed through the whole path and puts the measured range back');
  process.exit(failed ? 1 : 0);
})();
