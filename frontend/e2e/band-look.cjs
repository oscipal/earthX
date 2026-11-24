// Browser check of the look of a band (M5-60 PR 2, Otto 21.11.2026), with the collections as the registry writes them
// (`band-look-collections.json`: Sentinel-2, Sentinel-1, MeteoSwiss, swissALTI3D, ESA WorldCover, trimmed to what the view reads) and
// made-up scenes and measures. In the light and the dark theme, at 1280×800, 1280×360 and 360×740, it fails when
//   - a band chosen in the view does not start with the colormap and range of its look (a fixed range at once, in stored values where the
//     band is scaled; a measured one from the measure), or what is typed by hand does not hold until the next band;
//   - a bar of the histogram is not in the colour of its value (the end colours outside the range), or does not follow a change of the
//     colormap or the range at once, or that change asks for a measure;
//   - the bar of the legend over the map is not in the colours of the colormap, or its ends are not physical values with the unit;
//   - a class layer (WorldCover) has a histogram or no class legend;
//   - a result band of the source whose values no step changed does not keep its look, or one Band math made takes one;
//   - the legend scrolls, or the settings scroll at 1280×800 (below that they do on main already, with or without a histogram).
// It writes a screenshot per dataset.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/band-look.cjs                  # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-band-look');
const COLLECTIONS = JSON.parse(fs.readFileSync(path.join(__dirname, 'band-look-collections.json'), 'utf8'));
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, low: { width: 1280, height: 360 }, narrow: { width: 360, height: 740 } };

// A few colours of each colormap, as the tiler lists them for the previews (made up, not the tiler's).
const STOPS = {
  viridis: ['#440154', '#3b528b', '#21918c', '#5ec962', '#fde725'],
  magma: ['#000004', '#51127c', '#b73779', '#fc8961', '#fcfdbf'],
  rdbu: ['#67001f', '#d6604d', '#f7f7f7', '#4393c3', '#053061'],
  terrain: ['#333399', '#0294fa', '#24d36d', '#fefe98', '#82694d', '#ffffff'],
  gray: ['#000000', '#ffffff'],
  greys: ['#ffffff', '#000000'],
  rdylgn: ['#a50026', '#ffffbf', '#006837'],
};
const COLORMAPS = { groups: [{ name: 'Made up', colormaps: Object.entries(STOPS).map(([name, colors]) => ({ name, reversed: `${name}_r`, colors })) }] };
const ends = (name) => {
  const colors = STOPS[name.replace(/_r$/, '')];
  return name.endsWith('_r') ? [colors.at(-1), colors[0]] : [colors[0], colors.at(-1)];
};

// The measure of a band in the values its tiles draw: a histogram reaching beyond the range on both sides.
function histogram(low, high, bins = 12) {
  const edges = Array.from({ length: bins + 1 }, (_, i) => low + ((high - low) * i) / bins);
  return [Array.from({ length: bins }, (_, i) => 10 + 30 * Math.sin((Math.PI * (i + 0.5)) / bins)), edges];
}
const MEASURES = {
  red: { min: 0, max: 6000, percentile_2: 1200, percentile_98: 3400, histogram: histogram(0, 6000) },
  cloud: { min: 0, max: 100, percentile_2: 0, percentile_98: 90, histogram: histogram(-10, 110) },
  vh: { min: 0, max: 800, percentile_2: 60, percentile_98: 500, histogram: histogram(0, 800) },
  TminD: { min: -30, max: 40, percentile_2: -8, percentile_98: 22, histogram: histogram(-30, 40) },
  SrelD: { min: -10, max: 110, percentile_2: 5, percentile_98: 95, histogram: histogram(-10, 110) },
  dtm_2m: { min: -500, max: 5500, percentile_2: 400, percentile_98: 2400, histogram: histogram(-500, 5500) },
};
const measureOf = (asset) => ({ count: 900, unit: null, ...(MEASURES[asset] ?? MEASURES.red) });

// The scenes, by dataset: the assets of one band each the view offers, the scaling of Sentinel-2 reflectance (adr/0017 §3.4).
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const cog = (bands = [{ data_type: 'uint16' }]) => ({ href: 'https://data.example.org/b.tif', type: COG, roles: ['data'], 'raster:bands': bands });
const refs = { href: 'https://data.example.org/q.nc', type: 'application/x-netcdf', roles: ['data'], 'earthx:refs': { etag: '"a"' }, 'raster:bands': [{ data_type: 'float32' }] };
const REFLECTANCE = [{ data_type: 'uint16', scale: 0.0001, offset: -0.1 }];
const ASSETS = {
  'sentinel-2-c1-l2a': { visual: cog([{}, {}, {}]), red: cog(REFLECTANCE), green: cog(REFLECTANCE), blue: cog(REFLECTANCE), nir: cog(REFLECTANCE), cloud: cog(), scl: cog() },
  'sentinel-1-grd': { vv: cog(), vh: cog() },
  'meteoswiss-daily-1km': { TabsD: refs, TminD: refs, TmaxD: refs, SrelD: refs },
  swissalti3d: { dtm: cog([{ data_type: 'float32' }]), dtm_2m: cog([{ data_type: 'float32' }]) },
  'esa-worldcover-2021': { map: cog([{ data_type: 'uint8' }]) },
};

// What each dataset is checked with: the band chosen, its colormap and fields, the ends of the legend and its unit.
const CASES = [
  { dataset: 'sentinel-2-c1-l2a', band: 'red', colormap: 'viridis', fields: ['1200', '3400'], legend: [0.02, 0.24], unit: null },
  { dataset: 'sentinel-2-c1-l2a', band: 'cloud', colormap: 'viridis', fields: ['0', '100'], legend: [0, 100], unit: '%' },
  { dataset: 'sentinel-1-grd', band: 'vh', colormap: 'greys_r', fields: ['60', '500'], legend: [60, 500], unit: null },
  { dataset: 'meteoswiss-daily-1km', band: 'TminD', colormap: 'rdbu_r', fields: ['-20', '30'], legend: [-20, 30], unit: '°C' },
  { dataset: 'meteoswiss-daily-1km', band: 'SrelD', colormap: 'viridis', fields: ['0', '100'], legend: [0, 100], unit: '%' },
  { dataset: 'swissalti3d', band: 'dtm_2m', colormap: 'terrain', fields: ['0', '5000'], legend: [0, 5000], unit: 'm' },
];

const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';

const rgb = (hex) => `rgb(${parseInt(hex.slice(1, 3), 16)}, ${parseInt(hex.slice(3, 5), 16)}, ${parseInt(hex.slice(5, 7), 16)})`;

async function open(browser, theme, viewport, problems) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  const asked = [];
  await page.route('**/*', async (r) => {
    const url = new URL(r.request().url());
    const json = (body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return r.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets|e2e)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return r.continue();
    if (url.pathname === '/colormaps') return json(COLORMAPS);
    if (url.pathname.endsWith('/statistics')) {
      asked.push(url.pathname);
      return json({ b1: measureOf(url.searchParams.get('asset')) });
    }
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname === `/processing/jobs/${JOB}`) return json({ jobID: JOB, status: 'successful', message: '', progress: 100, expires: new Date(Date.now() + 86_400_000).toISOString() });
    if (url.pathname === `/processing/jobs/${JOB}/results`) {
      const band = (name, unit, measure) => ({ name, ...(unit ? { unit } : {}), statistics: { count: 900, minimum: measure.min, maximum: measure.max, percentile_2: measure.p2, percentile_98: measure.p98, histogram: histogram(measure.min, measure.max) } });
      return json({
        result: { href: `/processing/jobs/${JOB}/results/result.tif`, type: COG, width: 100, length: 4e5, properties: { bands: [
          band('NDVI', null, { min: -0.2, max: 0.9, p2: -0.1, p98: 0.8 }),
          band('red', null, { min: 0, max: 0.5, p2: 0.02, p98: 0.3 }),
          band('cloud', '%', { min: 0, max: 100, p2: 3, p98: 80 }),
        ] } },
        tiles: { href: `/results/${RESULT}/WebMercatorQuad/tilejson.json` },
      });
    }
    if (url.pathname === `/results/${RESULT}/WebMercatorQuad/tilejson.json`) return json({ bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: [] });
    return r.fulfill({ status: 404, body: '' });
  });
  await page.goto(BASE);
  await page.locator('.app-rail').waitFor();
  // The stores, for the waits: a wait reads them at once.
  await page.evaluate(async () => {
    window.appStore = (await import('/src/store.ts')).useAppStore;
    window.processingStore = (await import('/src/processingStore.ts')).useProcessingStore;
  });
  // The page restores the jobs of its tab at the start; what is set before that is lost.
  await page.waitForTimeout(1200);
  return { context, page, asked };
}

// The view of one scene of `dataset`, opened as "View full selection" does.
async function openView(page, dataset) {
  await page.evaluate(async ({ collection, assets }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const bbox = [10, 46, 11, 47];
    const geometry = { type: 'Polygon', coordinates: [[[10, 46], [11, 46], [11, 47], [10, 47], [10, 46]]] };
    const item = { id: `${collection.id}-scene`, collection: collection.id, bbox, geometry, properties: { datetime: '2026-07-01T10:00:00Z', 'earthx:state': '2026', start_datetime: '2021-01-01T00:00:00Z' }, assets };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: collection.id, items: [item], groups: [{ key: ['a'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: [item.id], aoi: null, layers: [], resultsAt: 0, focusMode: false, error: null, notice: null,
    });
    await useAppStore.getState().enterFocus(false, false);
  }, { collection: COLLECTIONS[dataset], assets: ASSETS[dataset] });
  await page.locator('.viewer-controls').waitFor();
  await page.waitForTimeout(400);
}

const field = (page, name) => page.locator('.viewer-controls .vc-render label').filter({ has: page.locator(`span:text-is("${name}")`) }).first();
const fills = (page) => page.locator('.inspector .range-hist-bars rect').evaluateAll((rects) => rects.map((rect) => rect.style.fill || rect.getAttribute('class')));
const legendNumbers = async (page) => (await page.locator('.map-legend .legend-ends span').allTextContents()).map((text) => text);
const legendBar = (page) => page.locator('.map-legend .legend-bar').evaluate((el) => getComputedStyle(el).backgroundImage).catch(() => '');
const scrolls = (page, selector) => page.locator(selector).first().evaluate((el) => el.scrollHeight - el.clientHeight > 1).catch(() => false);
const settle = (page) => page.waitForFunction(() => !window.appStore.getState().focusLoading).then(() => page.waitForTimeout(250));

async function checkBand(page, asked, { dataset, band, colormap, fields, legend, unit }, say) {
  await field(page, 'Band').locator('select').selectOption(`band:${band}`);
  await settle(page);
  const state = await page.evaluate(async () => {
    const s = (await import('/src/store.ts')).useAppStore.getState();
    return [s.pendingColormapName, s.pendingVmin, s.pendingVmax];
  });
  if (JSON.stringify(state) !== JSON.stringify([colormap, ...fields])) say(`${band}: the fields start with ${JSON.stringify(state)}, not ${JSON.stringify([colormap, ...fields])}`);
  const [low, high] = ends(colormap);
  let bars = await fills(page);
  if (bars.length === 0) say(`${band}: no histogram`);
  else if (bars[0] !== rgb(low) || bars.at(-1) !== rgb(high)) say(`${band}: the bars outside the range are ${bars[0]} and ${bars.at(-1)}, not the end colours`);
  else if (new Set(bars).size < 3) say(`${band}: the bars are not in the colours of their values (${new Set(bars).size} colours)`);

  // A change of the colormap and of the range colours the bars at once, without a measure.
  // A reversed colormap stays reversed: "Reverse" is a switch of its own.
  const other = colormap.endsWith('_r') ? 'magma_r' : 'magma';
  const measured = asked.length;
  await field(page, 'Colormap').locator('select').selectOption('magma');
  await page.waitForTimeout(120);
  bars = await fills(page);
  if (bars[0] !== rgb(ends(other)[0])) say(`${band}: the bars did not take ${other} (${bars[0]})`);
  const vmin = page.locator('.viewer-controls .vc-num input[type=number]').first();
  const middle = String((Number(fields[0]) + Number(fields[1])) / 2);
  await vmin.fill(middle);
  await page.waitForTimeout(120);
  const moved = await fills(page);
  if (JSON.stringify(moved) === JSON.stringify(bars)) say(`${band}: the bars did not follow vmin`);
  if (asked.length !== measured) say(`${band}: a change of the colormap or the range asked for ${asked.length - measured} measures`);

  // Applied: the legend over the map in the same colours and in physical values.
  await page.locator('.viewer-controls .vc-apply').click();
  await page.waitForTimeout(300);
  const bar = await legendBar(page);
  if (!bar.includes(rgb(STOPS.magma[0])) || !bar.includes(rgb(STOPS.magma.at(-1)))) say(`${band}: the bar of the legend is not in ${other}`);
  const texts = await legendNumbers(page);
  const at = (text) => Number(text.split(' ')[0]);
  const physical = (stored) => (dataset === 'sentinel-2-c1-l2a' && band !== 'cloud' ? stored * 0.0001 - 0.1 : stored);
  const expected = [physical(Number(middle)), legend[1]];
  if (texts.length !== 2 || texts.some((text, i) => Math.abs(at(text) - expected[i]) > 1e-6 * Math.max(1, Math.abs(expected[i])))) say(`${band}: the legend says ${JSON.stringify(texts)}, not ${expected}`);
  if (texts.some((text) => (unit ? !text.endsWith(` ${unit}`) : text.includes(' ')))) say(`${band}: the unit of the legend is wrong: ${JSON.stringify(texts)}`);

  // "Auto-scale" goes back to the range of the look; the colormap chosen stays.
  await page.locator('.viewer-controls .vc-auto').click();
  await settle(page);
  const back = await page.evaluate(async () => {
    const s = (await import('/src/store.ts')).useAppStore.getState();
    return [s.pendingColormapName, s.pendingVmin, s.pendingVmax];
  });
  if (JSON.stringify(back) !== JSON.stringify([other, ...fields])) say(`${band}: "Auto-scale" gives ${JSON.stringify(back)}`);
  if (legend[0] !== undefined && texts.length === 2) {
    await page.locator('.viewer-controls .vc-apply').click();
    await page.waitForTimeout(200);
    const applied = (await legendNumbers(page)).map(at);
    if (Math.abs(applied[0] - legend[0]) > 1e-6 * Math.max(1, Math.abs(legend[0]))) say(`${band}: the legend starts at ${applied[0]}, not ${legend[0]}`);
  }
}

async function checkWorldCover(page, say) {
  await openView(page, 'esa-worldcover-2021');
  if ((await page.locator('.inspector .range-hist').count()) !== 0) say('WorldCover: a class layer has a histogram');
  if ((await page.locator('.map-legend .legend-classes li').count()) !== 11) say('WorldCover: the legend does not list the eleven classes');
}

// A finished job on Sentinel-2: NDVI by Band math and the bands red and cloud kept as they are, masked by the scene classification.
async function checkResult(page, say) {
  await page.evaluate(async ({ collection, job }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const { jobEntry } = await import('/src/fixtures/jobEntries.ts');
    useAppStore.setState({ datasets: datasetsFrom([collection]), datasetId: collection.id, layers: [], resultsAt: 0, focusMode: false, downloaded: {} });
    useProcessingStore.getState().ensureDescription(collection.id);
    const order = {
      recipe_version: 2,
      inputs: [{ name: 'input', dataset: collection.id, groups: [['s']] }],
      aoi: { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] },
      steps: [{ op: 'band_math', op_version: 2, params: { expression: '(nir - red) / (nir + red)', name: 'NDVI' } }, { op: 'mask', op_version: 1, params: { source: 'scl', classes: [3] } }],
      output: { kind: 'raster', format: 'cog', dtype: 'float32', bands: ['NDVI', 'red', 'cloud'] },
    };
    useProcessingStore.setState({ jobs: [jobEntry(1, { jobID: job, expires: new Date(Date.now() + 86_400_000).toISOString(), phase: 'active', title: 'Kept bands', order })] });
  }, { collection: COLLECTIONS['sentinel-2-c1-l2a'], job: JOB });
  await page.waitForFunction(() => window.processingStore.getState().descriptions['sentinel-2-c1-l2a']?.state === 'ready');
  await page.evaluate(async (job) => (await import('/src/processingStore.ts')).useProcessingStore.getState().followJob(job), JOB);
  await page.waitForFunction(() => (window.processingStore.getState().jobs[0]?.bands?.length ?? 0) === 3, null, { timeout: 15000 });
  const looks = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().jobs[0].bands.map((b) => b.look ?? null));
  const want = [null, { colormap: 'viridis', scale: 'measured' }, { colormap: 'viridis', scale: 'fixed', low: 0, high: 100 }];
  if (JSON.stringify(looks) !== JSON.stringify(want)) say(`result: the bands have the looks ${JSON.stringify(looks)}`);
  await page.evaluate(async (job) => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    await useProcessingStore.getState().showResultOnMap(job);
    const layer = useAppStore.getState().layers[0];
    useProcessingStore.getState().chooseResultBand(layer.id, 2);
  }, JOB);
  await page.waitForTimeout(300);
  const tile = await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers[0].overlays[0].tileUrl);
  const query = new URL(tile, BASE).searchParams;
  if (query.get('colormap_name') !== 'viridis' || query.get('rescale') !== '0,100') say(`result: cloud is drawn with ${query.get('colormap_name')} ${query.get('rescale')}, not viridis 0,100`);
  const texts = await legendNumbers(page);
  if (JSON.stringify(texts) !== JSON.stringify(['0 %', '100 %'])) say(`result: the legend says ${JSON.stringify(texts)}`);
}

async function check(browser, theme, viewport) {
  const problems = [];
  const { context, page, asked } = await open(browser, theme, viewport, problems);
  const name = `${theme} ${viewport}`;
  for (const one of CASES) {
    const say = (text) => problems.push(`${name}: ${one.dataset}: ${text}`);
    await openView(page, one.dataset);
    await checkBand(page, asked, one, say);
    // The settings scroll below a certain height on main already (1280×360, 360×740); the histogram adds nothing to them.
    if (viewport === 'wide' && (await scrolls(page, '.inspector .insp-body'))) say(`${one.band}: the settings scroll`);
    if (await scrolls(page, '.map-legend .legend')) say(`${one.band}: the legend scrolls`);
    await page.screenshot({ path: path.join(OUT, `band-look-${one.dataset}-${one.band}-${theme}-${viewport}.png`) });
  }
  await checkWorldCover(page, (text) => problems.push(`${name}: ${text}`));
  await page.screenshot({ path: path.join(OUT, `band-look-worldcover-${theme}-${viewport}.png`) });
  await checkResult(page, (text) => problems.push(`${name}: ${text}`));
  await page.screenshot({ path: path.join(OUT, `band-look-result-${theme}-${viewport}.png`) });
  await context.close();
  return problems;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const all = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) all.push(...(await check(browser, theme, viewport)));
  await browser.close();
  console.log(all.length === 0 ? `ok: the looks of the bands, the histogram and the legend in their colours (light and dark, 1280×800, 1280×360, 360×740); screenshots in ${OUT}` : `FAIL\n${all.join('\n')}`);
  process.exit(all.length === 0 ? 0 : 1);
})();
