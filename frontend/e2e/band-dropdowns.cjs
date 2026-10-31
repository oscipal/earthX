// Browser check of the two dropdowns that pick a band (NM4-43e PR 2), in a real browser with made-up answers of the tiler:
//   1. "Show" in the preview: with two bands in the output the preview asks for the first result (`band=`, the assets that
//      band needs), the dropdown stands left of min and max, and choosing a band of the data asks the tiler again for
//      that band alone, measures it, and draws it with its own scale.
//   2. "Band" in the row of a result layer of three bands: it stands under the row, inside the dock, and choosing a band
//      draws the layer from that band (`bidx`) with the scale of its statistics.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/band-dropdowns.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-band-dropdowns');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';

// What the tiler measures, by the band asked: an index, and reflectance that lies within -1…1 as well.
const MEASURES = {
  result: { b1: { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null } },
  red: { b1: { count: 900, min: 0.01, max: 0.9, percentile_2: 0.05, percentile_98: 0.7, unit: null } },
};
const stat = (minimum, maximum, p2, p98) => ({ minimum, maximum, mean: 0, count: 1000, valid_percent: 100, percentile_2: p2, percentile_98: p98 });
const RESULT_PROPERTIES = {
  'processing:expression': { format: 'numexpr', expression: '(nir - red) / (nir + red)', name: 'ndvi' },
  bands: [
    { name: 'ndvi', data_type: 'float32', statistics: stat(-0.3, 0.9, -0.05, 0.8) },
    { name: 'red', data_type: 'float32', statistics: stat(0.01, 0.9, 0.05, 0.7) },
    { name: 'a_long_name_of_a_band_of_the_data', data_type: 'float32', statistics: stat(100, 2400, 180, 1900) },
  ],
};

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function open(browser, theme, viewport) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const asked = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    asked.push(url.pathname + url.search);
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/statistics')) return json(MEASURES[url.searchParams.get('band')] ?? MEASURES.result);
    if (url.pathname === `/results/${RESULT}/WebMercatorQuad/tilejson.json`) return json({ bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: [] });
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page, asked };
}

async function selectScene(page) {
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
    const item = {
      id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox, geometry: polygon,
      properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
      assets: { red: asset(), green: asset(), nir: asset() },
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
  });
}

// 1. "Show" in the preview.
async function checkShow(browser, theme, viewport) {
  const name = `show ${theme} ${viewport}`;
  const problems = [];
  const { context, page, asked } = await open(browser, theme, viewport);
  await selectScene(page);
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().openProcessing());
  await page.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  await page.waitForSelector('.pp-range input[type=number]', { timeout: 15000 });
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().setOutput(['result', 'red', 'green']));
  await page.waitForSelector('.pp-show select', { timeout: 5000 });
  await page.waitForTimeout(900);
  const lastStatistics = () => asked.filter((u) => u.includes('/statistics?')).at(-1) ?? '';
  const query = (u) => new URL(u, BASE).searchParams;
  const first = query(lastStatistics());
  if (first.get('band') !== 'result') problems.push(`the first picture asks for band ${first.get('band')}, not the result`);
  if (first.getAll('asset').join() !== 'red,nir') problems.push(`the first picture reads ${first.getAll('asset')}, not red,nir`);
  const options = await page.$$eval('.pp-show select option', (o) => o.map((x) => x.value));
  if (options.join() !== 'result,red,green') problems.push(`the options are ${options}`);
  const fields = () => page.$$eval('.pp-range input[type=number]', (i) => i.map((x) => x.value));
  if ((await fields()).join() !== '-1,1') problems.push(`the fields of the result say ${await fields()}, not -1,1`);

  await page.selectOption('.pp-show select', 'red');
  await page.waitForTimeout(1200);
  const second = query(lastStatistics());
  if (second.get('band') !== 'red') problems.push(`after the choice the statistics ask for band ${second.get('band')}`);
  if (second.getAll('asset').join() !== 'red') problems.push(`after the choice the picture reads ${second.getAll('asset')}, not red alone`);
  if ((await fields()).join() !== '0.05,0.7') problems.push(`the fields of red say ${await fields()}, not 0.05,0.7`);
  const colormap = await page.$eval('.pp-range .vc-field:not(.pp-show) select', (s) => s.value);
  if (colormap !== 'viridis') problems.push(`red is drawn in ${colormap}, not viridis`);

  const report = await page.evaluate(() => {
    const row = document.querySelector('.pp-range');
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const body = row.closest('.pp-body') ?? document.querySelector('.processing-panel');
    return { theme: document.querySelector('.app')?.dataset.theme, panel: box(body), scrolls: body.scrollWidth > body.clientWidth + 1, leaves: [...row.querySelectorAll('input, select, button')].map((e) => ({ what: e.tagName.toLowerCase(), ...box(e) })) };
  });
  for (let i = 0; i < report.leaves.length; i++) {
    for (let j = i + 1; j < report.leaves.length; j++) if (overlap(report.leaves[i], report.leaves[j])) problems.push(`${report.leaves[i].what} overlaps ${report.leaves[j].what}`);
    const leaf = report.leaves[i];
    if (leaf.x < report.panel.x - 0.5 || leaf.x + leaf.width > report.panel.x + report.panel.width + 0.5) problems.push(`${leaf.what} leaves the panel`);
  }
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}`);
  if (report.scrolls) problems.push('the panel scrolls sideways');
  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('section[aria-label="Preview on the map"]').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  await context.close();
  return { name, problems };
}

// 2. "Band" in the row of a result layer.
async function checkLayer(browser, theme, viewport) {
  const name = `layer ${theme} ${viewport}`;
  const problems = [];
  const { context, page } = await open(browser, theme, viewport);
  await page.evaluate(
    async ({ job, result, properties }) => {
      const { useAppStore } = await import('/src/store.ts');
      const { useProcessingStore } = await import('/src/processingStore.ts');
      const { jobEntry } = await import('/src/fixtures/jobEntries.ts');
      const { resultBands } = await import('/src/resultLayer.ts');
      const order = { recipe_version: 2, inputs: [{ name: 'in', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }], steps: [{ op: 'band_math', op_version: 2, params: { expression: 'a', name: 'ndvi' } }], output: { kind: 'raster' } };
      useProcessingStore.setState({
        jobs: [jobEntry(1, {
          jobID: job, expires: new Date(Date.now() + 86_400_000).toISOString(), phase: 'successful', title: 'Band math · Sentinel-2 L2A',
          tiles: { href: `/results/${result}/WebMercatorQuad/tilejson.json`, width: 1000, gsd: 10 }, order, bands: resultBands(properties, order),
        })],
      });
      useAppStore.setState({ dock: 'layers' });
      await useProcessingStore.getState().showResultOnMap(job);
    },
    { job: JOB, result: RESULT, properties: RESULT_PROPERTIES },
  );
  await page.waitForSelector('.layer-row .lm-band select', { timeout: 10000 });
  const urlOfLayer = () =>
    page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers[0].overlays[0].tileUrl);
  const first = new URL(await urlOfLayer(), BASE).searchParams;
  if (first.get('bidx') !== '1' || first.get('rescale') !== '-1,1') problems.push(`the layer starts with bidx ${first.get('bidx')}, rescale ${first.get('rescale')}`);
  const options = await page.$$eval('.layer-row .lm-band select option', (o) => o.map((x) => x.textContent));
  if (options.join() !== 'ndvi,red,a_long_name_of_a_band_of_the_data') problems.push(`the options are ${options}`);

  await page.selectOption('.layer-row .lm-band select', '2');
  const third = new URL(await urlOfLayer(), BASE).searchParams;
  if (third.get('bidx') !== '3' || third.get('rescale') !== '180,1900' || third.get('colormap_name') !== 'viridis') {
    problems.push(`the third band is drawn with bidx ${third.get('bidx')}, ${third.get('rescale')}, ${third.get('colormap_name')}`);
  }
  await page.selectOption('.layer-row .lm-band select', '1');
  const second = new URL(await urlOfLayer(), BASE).searchParams;
  if (second.get('bidx') !== '2' || second.get('rescale') !== '0.05,0.7' || second.get('colormap_name') !== 'viridis') {
    problems.push(`red is drawn with bidx ${second.get('bidx')}, ${second.get('rescale')}, ${second.get('colormap_name')}`);
  }

  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const row = document.querySelector('.layer-row');
    const list = document.querySelector('.layer-list');
    const select = row.querySelector('.lm-band select');
    return {
      theme: document.querySelector('.app')?.dataset.theme,
      list: box(list),
      cells: [...row.children].map((e) => ({ what: e.dataset.col ?? e.className, ...box(e) })).filter((c) => c.width > 0),
      select: box(select),
      scrolls: list.scrollWidth > list.clientWidth + 1,
    };
  });
  const band = report.cells.find((c) => c.what.includes('lm-band'));
  for (const cell of report.cells) {
    if (cell !== band && overlap(cell, band)) problems.push(`the band dropdown overlaps ${cell.what}`);
    if (cell.x < report.list.x - 0.5 || cell.x + cell.width > report.list.x + report.list.width + 0.5) problems.push(`${cell.what} leaves the list`);
  }
  if (report.select.width < 60) problems.push(`the dropdown is only ${Math.round(report.select.width)} px wide`);
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}`);
  if (report.scrolls) problems.push('the list scrolls sideways');
  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('.layer-row').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const check of [checkShow, checkLayer]) for (const theme of ['light', 'dark']) for (const viewport of Object.keys(VIEWPORTS)) {
    const result = await check(browser, theme, viewport);
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : 'both dropdowns pick their band, ask for it by name, and fit in both themes and at 360 px');
  process.exit(failed ? 1 : 0);
})();
