// Browser check of the quick calculation of an index in the view (NM4-14b, review of Otto 31.10.2026), in a real browser with
// made-up answers of the tiler:
//   1. The dropdown "Index" stands first in the settings of the view, the settings keep their grid (no overlap, nothing over the
//      edge, the buttons as high as the fields); a dataset without presets has none and the row is as before.
//   2. Choosing an index draws it at once through the tile route with an operator (the mosaic of the pass here): the tiles ask for
//      `op=band_math`, the band named like the index, the range and colormap of the preset, and no raw asset.
//   3. Zoomed out the choice stays and a short note says "Zoom in to compute NDWI", with the explanation in its tooltip; no tile is
//      asked for; zoomed in the note is gone and the tiles come.
//   4. "Add to layers" pins the index as a layer whose tiles compute it; "Download crop" is the raw bands' (it takes no look).
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/view-index.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-view-index');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const FOOTPRINT = [10, 50, 11, 51];
const SCENES = ['SYNTH_A', 'SYNTH_B'];
const TIP_NDWI = 'Normalized Difference Water Index (McFeeters 1996): (G - N) / (G + N). Formula: Awesome Spectral Indices.';
const NOTE_TIP = 'The quick calculation works from zoom 8. For whole scenes start a job in Processing.';
const PRESETS = [
  ['NDVI', 'Normalized Difference Vegetation Index', '(nir - red) / (nir + red)', 'rdylgn', '(N - R)/(N + R)'],
  ['NDWI', 'Normalized Difference Water Index (McFeeters 1996)', '(green - nir) / (green + nir)', 'rdbu', '(G - N) / (G + N)'],
  ['NDSI', 'Normalized Difference Snow Index', '(green - swir16) / (green + swir16)', 'rdbu', '(G - S1) / (G + S1)'],
  ['NBR', 'Normalized Burn Ratio', '(nir - swir22) / (nir + swir22)', 'rdylgn', '(N - S2) / (N + S2)'],
  ['EVI', 'Enhanced Vegetation Index', '2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)', 'rdylgn', 'g * (N - R) / (N + C1 * R - C2 * B + L)'],
].map(([name, title, expression, colormap_name, formula]) => ({ name, title, expression, rescale: [[-1, 1]], colormap_name, formula, reference: 'https://example.org/formula' }));

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
const within = (inner, outer) => inner.x >= outer.x - 0.5 && inner.x + inner.width <= outer.x + outer.width + 0.5;

async function open(browser, theme, viewport, presets) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  const tiles = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': SCENES });
    if (url.pathname.includes('/tiles/')) {
      tiles.push(decodeURIComponent(url.pathname) + url.search);
      return route.fulfill({ status: 404, body: '' });
    }
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  await page.evaluate(async ({ presets, scenes, footprint }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 8, maxZoom: 14 });
    const items = scenes.map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z' }, assets: {} }));
    const collection = {
      id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:true_color': ['red', 'green', 'blue'],
      'earthx:index_presets': presets,
    };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', items, groups: [{ key: ['a'], label: '2026-07-01', items }], activeGroupIndex: 0,
      selectedIds: scenes, downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: false, showDownloaded: true, dock: null,
      appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', layers: [], mosaics: {}, error: null,
      flyToView: { center: [10.5, 50.5], zoom: 9 },
    });
    await useAppStore.getState().loadMosaics();
  }, { presets, scenes: SCENES, footprint: FOOTPRINT });
  await page.waitForSelector('.scene-view .vc-apply');
  fs.mkdirSync(OUT, { recursive: true });
  return { context, page, problems, tiles };
}

const field = (page) => page.locator('.scene-view .vc-render label', { hasText: /^Index/ });
const fly = async (page, zoom) => {
  await page.evaluate(async (zoom) => (await import('/src/store.ts')).useAppStore.setState({ flyToView: { center: [10.5, 50.5], zoom } }), zoom);
  await page.waitForTimeout(1800);
};

// 1. The layout.
async function checkLayout(browser, theme, viewport) {
  const name = `layout ${theme} ${viewport}`;
  const { context, page, problems } = await open(browser, theme, viewport, PRESETS);
  const labels = await page.locator('.scene-view .vc-render > label > span').allTextContents();
  if (labels.join('|') !== 'Index|Colormap|vmin|vmax') problems.push(`the fields are ${labels}`);
  const options = await field(page).locator('option').allTextContents();
  if (options.join('|') !== '— none —|NDVI|NDWI|NDSI|NBR|EVI') problems.push(`the options are ${options}`);
  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const view = document.querySelector('.scene-view');
    const leaves = [...document.querySelectorAll('.scene-view .vc-render > *')].map((e) => ({ what: e.textContent.trim().slice(0, 12), ...box(e) }));
    const inputs = [...document.querySelectorAll('.scene-view .vc-render .vc-field select, .scene-view .vc-render .vc-field input')].map((e) => box(e).height);
    return { theme: document.querySelector('.app')?.dataset.theme, view: box(view), leaves, inputs, buttons: box(document.querySelector('.scene-view .vc-buttons')), scrolls: view.scrollWidth > view.clientWidth + 1 };
  });
  for (let i = 0; i < report.leaves.length; i++) {
    const leaf = report.leaves[i];
    if (!within(leaf, report.view)) problems.push(`${leaf.what} leaves the view`);
    for (let j = i + 1; j < report.leaves.length; j++) if (overlap(leaf, report.leaves[j])) problems.push(`${leaf.what} overlaps ${report.leaves[j].what}`);
    if (leaf.width < 40) problems.push(`${leaf.what} is only ${leaf.width.toFixed(0)} px wide`);
  }
  if (new Set(report.inputs.map((h) => Math.round(h))).size !== 1) problems.push(`the fields differ in height: ${report.inputs}`);
  if (Math.abs(report.buttons.height - report.inputs[0]) > 1.5) problems.push(`the buttons are ${report.buttons.height.toFixed(1)} px high, the fields ${report.inputs[0].toFixed(1)}`);
  if (report.scrolls) problems.push('the view scrolls sideways');
  if (report.theme !== THEMES[theme]) problems.push(`the theme is ${report.theme}`);
  await page.locator('.scene-view').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  await context.close();
  return { name, problems };
}

// 1b. No dropdown without presets.
async function checkNone(browser, theme, viewport) {
  const name = `none ${theme} ${viewport}`;
  const { context, page, problems } = await open(browser, theme, viewport, []);
  if ((await field(page).count()) !== 0) problems.push('a dataset without presets has the dropdown');
  const labels = await page.locator('.scene-view .vc-render > label > span').allTextContents();
  if (labels.join('|') !== 'Colormap|vmin|vmax') problems.push(`the fields are ${labels}`);
  await context.close();
  return { name, problems };
}

// 2 to 4. Drawing, the note, "Add to layers".
async function checkDraw(browser, theme, viewport) {
  const name = `draw ${theme} ${viewport}`;
  const { context, page, problems, tiles } = await open(browser, theme, viewport, PRESETS);
  await page.waitForTimeout(1500);
  tiles.length = 0;
  await field(page).locator('select').selectOption('NDWI');
  await page.waitForTimeout(1500);
  const mine = tiles.filter((t) => t.includes('/mosaic/'));
  if (mine.length === 0) problems.push('the index asked for no tile of the mosaic');
  const query = new URLSearchParams(mine[0]?.split('?')[1] ?? '');
  if (query.getAll('op').join() !== 'band_math') problems.push(`the tile asks for op=${query.getAll('op')}`);
  if (query.get('band') !== 'NDWI') problems.push(`the tile asks for band=${query.get('band')}`);
  if (query.getAll('asset').join() !== 'green,nir') problems.push(`the tile reads the assets ${query.getAll('asset')}`);
  if (query.get('rescale') !== '-1,1' || query.get('colormap_name') !== 'rdbu') problems.push(`the tile asks for ${query.get('rescale')} in ${query.get('colormap_name')}`);
  if (query.getAll('item').join() !== SCENES.join()) problems.push(`the tile names the scenes ${query.getAll('item')}`);
  if (tiles.some((t) => t.includes('asset=visual') && !t.includes('op='))) problems.push('a raw band is drawn under the index');
  if ((await field(page).getAttribute('title')) !== TIP_NDWI) problems.push(`the tooltip is ${await field(page).getAttribute('title')}`);
  if ((await page.locator('.scene-view .vc-note').count()) !== 0) problems.push('a note at zoom 9');
  if ((await page.locator('.scene-view .vc-render .vc-field select').nth(1).inputValue()) !== 'rdbu') problems.push('the colormap field does not show rdbu');
  await page.locator('.scene-view').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_drawn.png`) });

  // Zoomed out: the choice stays, a note says what to do, nothing is asked for.
  await fly(page, 3);
  tiles.length = 0;
  await page.waitForTimeout(800);
  const note = page.locator('.scene-view .vc-note');
  if ((await note.count()) !== 1) problems.push('no note when the map is zoomed out');
  else {
    if ((await note.textContent()) !== 'Zoom in to compute NDWI') problems.push(`the note says ${await note.textContent()}`);
    if ((await note.getAttribute('title')) !== NOTE_TIP) problems.push(`the note's tooltip is ${await note.getAttribute('title')}`);
  }
  if ((await field(page).locator('select').inputValue()) !== 'NDWI') problems.push('the choice did not stay');
  if (tiles.some((t) => t.includes('/tiles/') && !t.includes('op=band_math'))) problems.push('a raw band is drawn while the index waits for the zoom');
  const noteBox = await note.boundingBox();
  const viewBox = await page.locator('.scene-view').boundingBox();
  if (noteBox && !within(noteBox, viewBox)) problems.push('the note leaves the view');
  await page.locator('.scene-view').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_note.png`) });

  // Zoomed in again: the note goes, the tiles come.
  tiles.length = 0;
  await fly(page, 9);
  if ((await note.count()) !== 0) problems.push('the note stays after zooming in');
  if (!tiles.some((t) => t.includes('band=NDWI'))) problems.push('no tile of the index after zooming in');

  // "Add to layers": the layer computes the index, with no job.
  await page.getByRole('button', { name: /Add to layers/ }).click();
  await page.waitForTimeout(500);
  const layer = await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const [l] = useAppStore.getState().layers;
    return l ? { look: l.restore.appliedRender, urls: l.overlays.filter((o) => o.kind === 'raster').map((o) => o.tileUrl), images: l.overlays.filter((o) => o.kind === 'image').length } : null;
  });
  if (!layer) problems.push('no layer was added');
  else {
    if (layer.look.index !== 'NDWI') problems.push(`the layer's look is ${JSON.stringify(layer.look)}`);
    if (!layer.urls.every((u) => u.includes('op=band_math') && u.includes('band=NDWI'))) problems.push('the layer does not compute the index');
    if (layer.images !== 0) problems.push('a quicklook lies under the index layer');
  }
  const jobs = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().jobs.length);
  if (jobs !== 0) problems.push(`${jobs} job(s) were started`);
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      results.push(await checkLayout(browser, theme, viewport));
      results.push(await checkNone(browser, theme, viewport));
      results.push(await checkDraw(browser, theme, viewport));
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
