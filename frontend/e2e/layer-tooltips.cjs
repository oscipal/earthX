// The tooltips of the layer manager (Otto's check in the browser, 11.11.2026), in the step "Simple" (the default): a row of a dataset, of
// a result, of a result of a deleted job, of an expired result and "Search results", treated alike. The pointer goes to each control and the
// one tooltip (`TipLayer`) is read. Light and dark theme, a wide and a narrow window. Fails when
//   - a control a deleted job locks (eye, rename, opacity, band, "+", download) does not show the one reason "Job deleted: restore it first";
//   - the band of an expired result does not show its reason;
//   - "Process" does not say "Process layer" for the layer of a dataset and of a result alike;
//   - the controls the rows share (grip, eye, arrows) do not answer alike in the step "Simple".
// It writes a screenshot of the layer manager per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/layer-tooltips.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-layer-tooltips');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const LOCKED = 'Job deleted: restore it first';
const EXPIRED = 'Expired: start the job again';
const PROCESS = 'Process layer';

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    // No message over the panel: in a narrow window it would lie over the first row.
    if (url.pathname === '/stac/collections') return route.fulfill({ status: 200, contentType: 'application/json', body: '{"collections":[]}' });
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.waitForSelector('.app-rail');
  await page.waitForTimeout(300);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const DAY = 86_400_000;
    const datasets = datasetsFrom([{
      id: 'optical', title: 'Optical', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { time_range: true },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    }]);
    const order = { recipe_version: 2, inputs: [{ name: 'input', dataset: 'optical', groups: [['a']] }], steps: [], output: { kind: 'raster', format: 'cog', dtype: 'uint16', bands: ['red', 'nir'] } };
    const expires = new Date(Date.now() + 6 * DAY).toISOString();
    const job = (n, over) => ({
      jobID: `Job${String(n).padStart(19, '0')}`, expires, title: `Job ${n}`, titleDefault: `Job ${n}`, createdAt: new Date().toISOString(), archived: false, groupId: null,
      batchId: null, part: null, range: null, bandRanges: {}, shownBand: null, dates: null, order, status: null, phase: 'successful', archive: 'result.zip', bytes: null,
      resampled: null, failure: null, failureKind: null, normalize: null, error: null, cancelling: false, retrying: false, retryRefused: false, retryError: null,
      deleting: false, deletedUntil: null, serverDeleted: false, lost: false, superseded: false, expired: false, tiles: null, statistics: null, bands: [], ...over,
    });
    useProcessingStore.setState({ jobs: [job(1), job(2, { phase: 'dismissed', deletedUntil: new Date(Date.now() + DAY).toISOString(), serverDeleted: true }), job(3)] });
    const restore = (itemIds) => ({ focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds, groupItemIds: [itemIds], aoi: null, cropToAoi: false, datasetId: 'optical' });
    const overlays = [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}?tilesize=256', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }];
    const bands = [{ name: 'red', stats: null }, { name: 'nir', stats: null }];
    const result = (id, n, over) => ({
      id, name: `Result · ${id}`, visible: true, opacity: 1, overlays, derived: 'result', restore: restore([]),
      result: { jobID: `Job${String(n).padStart(19, '0')}`, expires, gsd: 10, resampled: null, expired: false, dataType: 'uint16', stats: null, bands, band: 0, ...over },
    });
    const section = { datasetId: 'optical', items: [{ id: 'a' }], groups: [], notes: [], groupingError: null, origin: 'search', incomplete: false };
    useAppStore.setState({
      datasets, sections: [section], resultsAt: 2, dock: 'layers',
      layers: [
        { id: 'view', name: 'Optical · 24 Jul', visible: true, opacity: 1, overlays, restore: restore(['a']) },
        result('live', 1, {}),
        result('deleted', 2, { deleted: true }),
        result('expired', 3, { expired: true }),
      ],
    });
  });
  await page.waitForSelector('.layer-row');
  const problems = [];
  // The tooltip the pointer in the middle of `locator` gets.
  const tipAt = async (locator) => {
    await page.mouse.move(0, VIEWPORTS[viewport].height - 1);
    await page.waitForTimeout(60);
    if ((await locator.count()) === 0) return '(not there)';
    await locator.scrollIntoViewIfNeeded().catch(() => undefined);
    const box = await locator.boundingBox();
    if (!box) return '(not there)';
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    await page.waitForTimeout(150);
    return (await page.locator('.tip-layer').textContent({ timeout: 500 }).catch(() => null)) ?? '(no tooltip)';
  };
  const row = (name) => page.locator('.layer-row', { has: page.locator(`[data-col="name"]:text-is("${name}")`) });
  const expect = async (what, locator, want) => {
    const got = await tipAt(locator);
    if (got !== want) problems.push(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`);
  };
  for (const col of ['eye', 'rename', 'opacity', 'download']) await expect(`deleted ${col}`, row('Result · deleted').locator(`[data-col="${col}"]`), LOCKED);
  await expect('deleted band', row('Result · deleted').locator('.lm-band select'), LOCKED);
  await expect('deleted "+"', row('Result · deleted').locator('.lm-add-band'), LOCKED);
  await expect('expired band', row('Result · expired').locator('.lm-band select'), EXPIRED);
  await expect('"Process" of a dataset layer', row('Optical · 24 Jul').locator('[data-col="process"]'), PROCESS);
  await expect('"Process" of a result layer', row('Result · live').locator('[data-col="process"]'), PROCESS);
  // In the step "Simple" the obvious controls say nothing, in every kind of row alike.
  for (const col of ['eye', 'down']) {
    const said = [];
    for (const r of [row('Optical · 24 Jul'), row('Result · live'), page.locator('.results-row')]) said.push(await tipAt(r.locator(`[data-col="${col}"]`)));
    if (new Set(said).size !== 1) problems.push(`${col} answers differently in the rows: ${JSON.stringify(said)}`);
  }
  await page.mouse.move(0, VIEWPORTS[viewport].height - 1);
  await page.locator('.layer-manager').screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}.png`) });
  await context.close();
  return { label, problems };
}

(async () => {
  require('node:fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) {
    const result = await check(browser, { theme, viewport });
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.label}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : 'every locked control of the layer manager says why in "Simple"; "Process" has one name; the rows answer alike');
  process.exit(failed ? 1 : 0);
})();
