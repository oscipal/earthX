// Browser check of the choice "RGB" (NM4-64), in a real browser with made-up answers of the tiler:
//   1. "Show" in the preview: with the three bands of the colour picture in the output "RGB" stands on top; it is the start
//      only where the output has no Band math result; the preview asks the tiler for `band=red&band=green&band=blue`, measures
//      the three together, draws them with one range and shows no colormap field; a single band has its colormap again.
//   2. "Band" in the row of a result layer: "RGB" stands on top, the layer starts with it where the result has no Band math
//      result, draws three `bidx` with one range and no colormap, and the view of the layer shows no colormap field.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/rgb.cjs                        # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-rgb');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';

// What the tiler measures, by channel: the three bands of the colour picture, each with a range of its own.
const BANDS = {
  red: { count: 900, min: 0.01, max: 0.9, percentile_2: 0.05, percentile_98: 0.7, unit: null },
  green: { count: 900, min: 0.02, max: 0.8, percentile_2: 0.04, percentile_98: 0.5, unit: null },
  blue: { count: 900, min: 0.005, max: 0.6, percentile_2: 0.02, percentile_98: 0.4, unit: null },
  result: { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null },
};
const stat = (minimum, maximum, p2, p98) => ({ minimum, maximum, mean: 0, count: 1000, valid_percent: 100, percentile_2: p2, percentile_98: p98 });
const RESULT_PROPERTIES = {
  'processing:expression': { format: 'numexpr', expression: '(nir - red) / (nir + red)', name: 'ndvi' },
  bands: [
    { name: 'ndvi', data_type: 'float32', statistics: stat(-0.3, 0.9, -0.05, 0.8) },
    { name: 'blue', data_type: 'float32', statistics: stat(0.005, 0.6, 0.02, 0.4) },
    { name: 'green', data_type: 'float32', statistics: stat(0.02, 0.8, 0.04, 0.5) },
    { name: 'red', data_type: 'float32', statistics: stat(0.01, 0.9, 0.05, 0.7) },
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
    if (url.pathname.endsWith('/statistics')) {
      const bands = url.searchParams.getAll('band');
      return json(Object.fromEntries((bands.length ? bands : ['result']).map((name, i) => [`b${i + 1}`, BANDS[name] ?? BANDS.result])));
    }
    if (url.pathname === `/results/${RESULT}/WebMercatorQuad/tilejson.json`) return json({ bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: [] });
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page, asked };
}

const COLLECTION = {
  id: 'sentinel-2-c1-l2a',
  'earthx:format': 'cog',
  'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { interpolation: true },
  'earthx:true_color': ['red', 'green', 'blue'],
};

async function selectScene(page) {
  await page.evaluate(async (collection) => {
    const { useAppStore } = await import('/src/store.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
    const item = {
      id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox, geometry: polygon,
      properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
      assets: { red: asset(), green: asset(), blue: asset(), nir: asset() },
    };
    useAppStore.setState({
      datasets: [{
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
        browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection,
      }],
      datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['S2B_A'], aoi: polygon, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
  }, COLLECTION);
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
  const fields = () => page.$$eval('.pp-range input[type=number]', (i) => i.map((x) => x.value));
  const colormapField = () => page.$$eval('.pp-range .vc-field:not(.pp-show) select:not(.vc-unit)', (s) => s.length);
  const options = () => page.$$eval('.pp-show select option', (o) => o.map((x) => `${x.value}=${x.textContent}`));
  const tileBands = () =>
    page.evaluate(async () => {
      const { useProcessingStore } = await import('/src/processingStore.ts');
      const url = new URL(useProcessingStore.getState().preview.scenes[0].url, location.origin);
      return { band: url.searchParams.getAll('band'), colormap: url.searchParams.get('colormap_name'), rescale: url.searchParams.getAll('rescale') };
    });

  // Without a result in the output RGB is the start (before anything has been picked).
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().setOutput(['red', 'green', 'blue']));
  await page.waitForSelector('.pp-show select', { timeout: 5000 });
  await page.waitForTimeout(900);
  if ((await page.$eval('.pp-show select', (s) => s.value)) !== '@rgb') problems.push('RGB is not the start without a Band math result in the output');

  // With a result of the step in the output, the result is the start; RGB is on top.
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().setOutput(['result', 'red', 'green', 'blue']));
  await page.waitForTimeout(900);
  if ((await options()).join() !== '@rgb=RGB,result=result,red=red,green=green,blue=blue') problems.push(`the options are ${await options()}`);
  if ((await page.$eval('.pp-show select', (s) => s.value)) !== 'result') problems.push('the result is not the start where the output has one');

  // RGB: three bands, one range, no colormap.
  await page.selectOption('.pp-show select', '@rgb');
  await page.waitForTimeout(1200);
  // The measure of RGB is remembered from the start: some request asked for the three bands, not necessarily the last.
  const colourStatistics = asked
    .filter((u) => u.includes('/statistics?'))
    .map((u) => new URL(u, BASE).searchParams)
    .find((q) => q.getAll('band').join() === 'red,green,blue');
  if (!colourStatistics) problems.push('no statistics asked for red,green,blue');
  else if (colourStatistics.getAll('asset').join() !== 'red,green,blue') problems.push(`the picture reads ${colourStatistics.getAll('asset')}, not red,green,blue`);
  if ((await fields()).join() !== '0.02,0.7') problems.push(`the fields of RGB say ${await fields()}, not 0.02,0.7`);
  if ((await colormapField()) !== 0) problems.push('RGB shows a colormap field');
  const rgb = await tileBands();
  if (rgb.band.join() !== 'red,green,blue' || rgb.colormap !== null || rgb.rescale.join() !== '0.02,0.7') problems.push(`the tiles of RGB ask ${JSON.stringify(rgb)}`);
  const layout = await page.evaluate(() => {
    const row = document.querySelector('.pp-range');
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const body = row.closest('.pp-body') ?? document.querySelector('.processing-panel');
    return { theme: document.querySelector('.app')?.dataset.theme, panel: box(body), scrolls: body.scrollWidth > body.clientWidth + 1, leaves: [...row.querySelectorAll('input, select, button')].map((e) => ({ what: e.tagName.toLowerCase(), ...box(e) })) };
  });
  for (let i = 0; i < layout.leaves.length; i++) {
    for (let j = i + 1; j < layout.leaves.length; j++) if (overlap(layout.leaves[i], layout.leaves[j])) problems.push(`${layout.leaves[i].what} overlaps ${layout.leaves[j].what}`);
    const leaf = layout.leaves[i];
    if (leaf.x < layout.panel.x - 0.5 || leaf.x + leaf.width > layout.panel.x + layout.panel.width + 0.5) problems.push(`${leaf.what} leaves the panel`);
  }
  if (layout.theme !== THEMES[theme]) problems.push(`the app shows the theme ${layout.theme}`);
  if (layout.scrolls) problems.push('the panel scrolls sideways');
  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('section[aria-label="Preview on the map"]').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_rgb.png`) });

  // A single band has its colormap again.
  await page.selectOption('.pp-show select', 'red');
  await page.waitForTimeout(1200);
  if ((await colormapField()) !== 1) problems.push('a single band shows no colormap field');
  const red = await tileBands();
  if (red.band.join() !== 'red' || red.colormap !== 'viridis') problems.push(`the tiles of red ask ${JSON.stringify(red)}`);
  await page.locator('section[aria-label="Preview on the map"]').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_band.png`) });

  // A dataset without a colour picture offers none.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.setState({ datasets: useAppStore.getState().datasets.map((d) => ({ ...d, collection: { ...d.collection, 'earthx:true_color': [] } })) });
  });
  await page.waitForTimeout(600);
  if ((await options()).some((o) => o.startsWith('@rgb'))) problems.push('RGB is offered for a dataset without a colour picture');
  await context.close();
  return { name, problems };
}

// 2. "Band" in the row of a result layer.
async function checkLayer(browser, theme, viewport) {
  const name = `layer ${theme} ${viewport}`;
  const problems = [];
  const { context, page } = await open(browser, theme, viewport);
  await selectScene(page);
  await page.evaluate(
    async ({ job, result, properties }) => {
      const { useAppStore } = await import('/src/store.ts');
      const { useProcessingStore } = await import('/src/processingStore.ts');
      const { jobEntry } = await import('/src/fixtures/jobEntries.ts');
      const { resultBands } = await import('/src/resultLayer.ts');
      const order = {
        recipe_version: 2,
        inputs: [{ name: 'in', dataset: 'sentinel-2-c1-l2a', groups: [['S2B_A']] }],
        steps: [{ op: 'band_math', op_version: 2, params: { expression: 'a', name: 'ndvi' } }],
        output: { kind: 'raster' },
      };
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
  const layerQuery = async () =>
    new URL(await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers[0].overlays[0].tileUrl), BASE).searchParams;
  const options = await page.$$eval('.layer-row .lm-band select option', (o) => o.map((x) => `${x.value}=${x.textContent}`));
  if (options.join() !== '@rgb=RGB,0=ndvi,1=blue,2=green,3=red') problems.push(`the options are ${options}`);
  // The order has a Band math result: it is the start, and RGB is a choice.
  const first = await layerQuery();
  if (first.getAll('bidx').join() !== '1') problems.push(`the layer starts with bidx ${first.getAll('bidx')}, not the result`);

  await page.selectOption('.layer-row .lm-band select', '@rgb');
  const rgb = await layerQuery();
  if (rgb.getAll('bidx').join() !== '4,3,2') problems.push(`RGB is drawn with bidx ${rgb.getAll('bidx')}, not 4,3,2`);
  if (rgb.getAll('rescale').join() !== '0.02,0.7' || rgb.has('colormap_name')) problems.push(`RGB is drawn with ${rgb.getAll('rescale')}, ${rgb.get('colormap_name')}`);

  // The view of the layer: no colormap, the range of the three bands.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.setState({ resultViewLayerId: useAppStore.getState().layers[0].id });
  });
  await page.waitForSelector('.result-controls', { timeout: 5000 });
  const fields = await page.$$eval('.result-controls input[type=number]', (i) => i.map((x) => x.value));
  if (fields.join() !== '0.02,0.7') problems.push(`the view of RGB says ${fields}, not 0.02,0.7`);
  // The settings have the dropdown "Band" now (NM4-65 part 6); only the field "Colormap" must be missing.
  const colormaps = await page.$$eval('.result-controls .vc-field', (fields) => fields.filter((f) => f.querySelector('span')?.textContent === 'Colormap').length);
  if (colormaps !== 0) problems.push('the view of RGB shows a colormap field');
  const view = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const root = document.querySelector('.result-controls');
    return { theme: document.querySelector('.app')?.dataset.theme, panel: box(root), scrolls: root.scrollWidth > root.clientWidth + 1, leaves: [...root.querySelectorAll('input, button')].map((e) => ({ what: e.tagName.toLowerCase() + ':' + (e.textContent || e.type), ...box(e) })).filter((c) => c.width > 0) };
  });
  for (let i = 0; i < view.leaves.length; i++) {
    for (let j = i + 1; j < view.leaves.length; j++) if (overlap(view.leaves[i], view.leaves[j])) problems.push(`${view.leaves[i].what} overlaps ${view.leaves[j].what}`);
    const leaf = view.leaves[i];
    if (leaf.x < view.panel.x - 0.5 || leaf.x + leaf.width > view.panel.x + view.panel.width + 0.5) problems.push(`${leaf.what} leaves the view`);
  }
  if (view.theme !== THEMES[theme]) problems.push(`the app shows the theme ${view.theme}`);
  if (view.scrolls) problems.push('the view scrolls sideways');
  fs.mkdirSync(OUT, { recursive: true });
  await page.waitForTimeout(700);
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_view.png`) });

  // Back to one band: the colormap returns.
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ resultViewLayerId: null }));
  await page.waitForSelector('.layer-row .lm-band select');
  await page.selectOption('.layer-row .lm-band select', '3');
  const red = await layerQuery();
  if (red.getAll('bidx').join() !== '4' || red.get('colormap_name') !== 'viridis') problems.push(`red is drawn with bidx ${red.getAll('bidx')}, ${red.get('colormap_name')}`);

  const row = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const list = document.querySelector('.layer-list');
    const rowEl = document.querySelector('.layer-row');
    return { list: box(list), select: box(rowEl.querySelector('.lm-band select')), scrolls: list.scrollWidth > list.clientWidth + 1 };
  });
  if (row.select.width < 60) problems.push(`the dropdown is only ${Math.round(row.select.width)} px wide`);
  if (row.scrolls) problems.push('the list scrolls sideways');
  await page.locator('.layer-row').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_row.png`) });
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
  console.log(failed ? `${failed} case(s) with problems` : 'RGB is offered, started and drawn as specified, and fits in both themes and at 360 px');
  process.exit(failed ? 1 : 0);
})();
