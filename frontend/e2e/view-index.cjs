// Browser check of the quick calculation of an index in the view (NM4-14b, review of Otto 31.10.2026), in a real browser with
// made-up answers of the tiler:
//   1. The dropdown "Band" (with the presets under a line) stands first in the settings of the view, the settings keep their grid (no overlap, nothing over the
//      edge, the buttons as high as the fields); a dataset without presets has none and the row is as before.
//   2. Choosing an index puts it into the fields; "Apply" draws it, through the tile route with an operator (the mosaic of the pass here): the tiles ask for
//      `op=band_math`, the band named like the index, the range and colormap of the preset, and no raw asset.
//   3. Zoomed out the choice stays and a short note says "Zoom in to compute NDWI", with the explanation in its tooltip; no tile is
//      asked for; zoomed in the note is gone and the tiles come.
//   4. "Add to layers" pins the index as a layer whose tiles compute it. The view of a layer has the dropdown locked. Its ⇩ downloads
//      the index as a Processing job would give it (the job API is made up here): the dialog shows the estimate, a file comes, and no
//      Processing panel opens and no job stands in the list of jobs. Its ⚙ opens the panel with the index as the one band.
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

const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const JOB = 'AAAAAAAAAAAAAAAAAAAAAA';
const JOB_STATUS = (status, progress) => ({ jobID: JOB, status, progress, message: '', expires: '2099-12-01T00:00:00Z' });

const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
const within = (inner, outer) => inner.x >= outer.x - 0.5 && inner.x + inner.width <= outer.x + outer.width + 0.5;

async function open(browser, theme, viewport, presets) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  const tiles = [];
  const jobs = { placed: [] };
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': SCENES });
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname === '/processing/processes/recipe/estimate') return json({ estimate: { size: 12_400_000, duration: 'PT9.2S', outputPixels: 1e6, inputPixels: 4e6, inputBytes: 8e6, assets: 2, units: 1 }, skippedItems: [] });
    if (url.pathname === '/processing/processes/recipe/execution') {
      jobs.placed.push(route.request().postDataJSON());
      return json(JOB_STATUS('accepted', 0));
    }
    if (url.pathname === `/processing/jobs/${JOB}`) return json(JOB_STATUS('successful', 100));
    if (url.pathname === `/processing/jobs/${JOB}/results/result.zip`) return route.fulfill({ status: 200, contentType: 'application/zip', body: 'PK\x05\x06' + '\0'.repeat(18) });
    if (url.pathname.includes('/tiles/')) {
      tiles.push(decodeURIComponent(url.pathname) + url.search);
      // A tile that loads, so that the raw view the map keeps until the new picture is there goes (as it does with a real tiler).
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
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
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const aoi = { type: 'Polygon', coordinates: [[[10.2, 50.2], [10.8, 50.2], [10.8, 50.8], [10.2, 50.8], [10.2, 50.2]]] };
    const items = scenes.map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: Object.fromEntries(['red', 'green', 'blue', 'nir', 'swir16', 'swir22', 'visual'].map((k) => [k, { href: `https://example.org/${k}.tif`, type: COG, 'raster:bands': [{ data_type: 'uint16', nodata: 0 }] }])) }));
    const collection = {
      id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:true_color': ['red', 'green', 'blue'],
      'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
      'earthx:band_units': { red: 'reflectance', green: 'reflectance', blue: 'reflectance', nir: 'reflectance', visual: null },
      'earthx:index_presets': presets,
    };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', items, groups: [{ key: ['a'], label: '2026-07-01', items }], activeGroupIndex: 0,
      selectedIds: scenes, downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: true, viewAoi: aoi, aoi, showDownloaded: true, dock: null,
      appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', layers: [], mosaics: {}, error: null,
      flyToView: { center: [10.5, 50.5], zoom: 9 },
    });
    await useAppStore.getState().loadMosaics();
  }, { presets, scenes: SCENES, footprint: FOOTPRINT });
  await page.waitForSelector('.scene-view .vc-apply');
  fs.mkdirSync(OUT, { recursive: true });
  return { context, page, problems, tiles, jobs };
}

const field = (page) => page.locator('.scene-view .vc-render label', { hasText: /^Band/ });
const fly = async (page, zoom, center = [10.5, 50.5]) => {
  await page.evaluate(async ({ zoom, center }) => (await import('/src/store.ts')).useAppStore.setState({ flyToView: { center, zoom } }), { zoom, center });
  await page.waitForTimeout(1800);
};

// 1. The layout.
async function checkLayout(browser, theme, viewport) {
  const name = `layout ${theme} ${viewport}`;
  const { context, page, problems } = await open(browser, theme, viewport, PRESETS);
  const labels = await page.locator('.scene-view .vc-render > label > span').allTextContents();
  if (labels.join('|') !== 'Band|vmin|vmax|Colormap') problems.push(`the fields are ${labels}`);
  const options = await field(page).locator('option').allTextContents();
  if (options.join('|') !== 'RGB|──────────|NDVI|NDWI|NDSI|NBR|EVI') problems.push(`the options are ${options}`);
  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const view = document.querySelector('.scene-view');
    const leaves = [...document.querySelectorAll('.scene-view .vc-render > *')].map((e) => ({ what: e.textContent.trim().slice(0, 12), ...box(e) }));
    const inputs = [...document.querySelectorAll('.scene-view .vc-render .vc-field select:not(.vc-unit), .scene-view .vc-render .vc-field input')].map((e) => box(e).height);
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
  if (labels.join('|') !== 'vmin|vmax|Colormap') problems.push(`the fields are ${labels}`);
  await context.close();
  return { name, problems };
}

// 2 to 4. Drawing, the note, "Add to layers".
async function checkDraw(browser, theme, viewport) {
  const name = `draw ${theme} ${viewport}`;
  const { context, page, problems, tiles, jobs } = await open(browser, theme, viewport, PRESETS);
  await page.waitForTimeout(1500);
  tiles.length = 0;
  await field(page).locator('select').selectOption('index:NDWI');
  // Chosen, not drawn: nothing of the index is asked for before "Apply".
  await page.waitForTimeout(1500);
  if (tiles.some((t) => t.includes('op=band_math'))) problems.push('the index was drawn before "Apply"');
  if ((await page.locator('.scene-view .vc-apply').getAttribute('aria-disabled')) === 'true') problems.push('"Apply" stays locked after an index was chosen');
  await page.locator('.scene-view .vc-apply').click();
  await page.waitForTimeout(2500);
  // Tiles of the raw view that were in flight when the index was chosen may still arrive; none follows the first of the index.
  const first = tiles.findIndex((t) => t.includes('op=band_math'));
  const mine = tiles.slice(Math.max(0, first)).filter((t) => t.includes('/mosaic/'));
  if (first < 0 || mine.length === 0) problems.push('the index asked for no tile of the mosaic');
  const query = new URLSearchParams(mine[0]?.split('?')[1] ?? '');
  if (query.getAll('op').join() !== 'band_math') problems.push(`the tile asks for op=${query.getAll('op')}`);
  if (query.get('band') !== 'NDWI') problems.push(`the tile asks for band=${query.get('band')}`);
  if (query.getAll('asset').join() !== 'green,nir') problems.push(`the tile reads the assets ${query.getAll('asset')}`);
  if (query.get('rescale') !== '-1,1' || query.get('colormap_name') !== 'rdbu') problems.push(`the tile asks for ${query.get('rescale')} in ${query.get('colormap_name')}`);
  if (query.getAll('item').join() !== SCENES.join()) problems.push(`the tile names the scenes ${query.getAll('item')}`);
  if ((await field(page).getAttribute('title')) !== TIP_NDWI) problems.push(`the tooltip is ${await field(page).getAttribute('title')}`);
  if ((await page.locator('.scene-view .vc-note').count()) !== 0) problems.push('a note at zoom 9');
  if ((await page.locator('.scene-view .vc-render .vc-field select:not(.vc-unit)').nth(1).inputValue()) !== 'rdbu') problems.push('the colormap field does not show rdbu');
  await page.locator('.scene-view').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_drawn.png`) });

  // Settled, a map that moves asks for tiles of the index alone: the raw view (which stays on the map until the index has loaded) is gone.
  // The map keeps the raw view under a new picture until it is idle, at most 10 s (`mapLayers.ts::RETIRE_AFTER_MS`); the basemap of
  // this run never is, so the wait is the longest.
  await page.waitForTimeout(10500);
  tiles.length = 0;
  await fly(page, 10, [10.3, 50.3]);
  if (!tiles.some((t) => t.includes('band=NDWI'))) problems.push('no tile of the index after moving the map');
  if (tiles.some((t) => t.includes('asset=visual') && !t.includes('op='))) problems.push(`a raw band is asked for under the index after it has settled: ${JSON.stringify(tiles.map((t) => (t.includes('op=') ? 'I' : 'R') + t.split('?')[0].split('/').slice(-3).join('/') + (t.includes('/mosaic/') ? 'm' : 's')))}`);

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
  if ((await field(page).locator('select').inputValue()) !== 'index:NDWI') problems.push('the choice did not stay');
  if (tiles.some((t) => t.includes('/tiles/') && !t.includes('op=band_math'))) problems.push('a raw band is drawn while the index waits for the zoom');
  const noteBox = await note.boundingBox();
  const viewBox = await page.locator('.scene-view').boundingBox();
  if (noteBox && !within(noteBox, viewBox)) problems.push('the note leaves the view');
  await page.locator('.scene-view').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_note.png`) });

  // Zoomed in again: the note goes, the tiles come.
  tiles.length = 0;
  await fly(page, 9, [10.7, 50.7]);
  if ((await note.count()) !== 0) problems.push('the note stays after zooming in');

  // "Process" in the view: the bands of the scenes, the index being only a picture there (Otto, 1.11.2026).
  await page.locator('.scene-view').getByRole('button', { name: /Process/ }).click();
  await page.locator('.processing-panel').waitFor({ timeout: 8000 }).catch(() => problems.push('the panel did not open from the view'));
  await page.waitForTimeout(800);
  const viewChips = await page.locator('.processing-panel section[aria-label="Bands"] .pp-chip').allTextContents();
  if (viewChips.some((c) => c.startsWith('NDWI')) || !viewChips.some((c) => c.startsWith('red'))) problems.push(`the panel of the view has the bands ${viewChips}`);
  if ((await page.locator('.processing-panel [aria-label="Area"] button').allTextContents()).join() !== 'Whole scene,AOI only') problems.push('the area of the cropped view is not to choose');
  await page.locator('.processing-panel .close-x').click();
  await page.waitForTimeout(300);
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: null }));

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
  const started = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().jobs.length);
  if (started !== 0) problems.push(`${started} job(s) were started`);

  // The layer manager: the view of the layer shows its index, locked.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().exitFocus();
    useAppStore.setState({ dock: 'layers' });
  });
  await page.locator('.layer-row [data-col="name"]').first().click({ force: true });
  await page.waitForSelector('.scene-view .vc-apply');
  // The box of every layer (NM4-54 part 5): the dropdown keeps its place, locked.
  if ((await field(page).locator('select').isDisabled()) !== true) problems.push('the dropdown "Band" of a layer is not locked');
  if ((await page.locator('.scene-view .vc-render > label > span').allTextContents()).join('|') !== 'Band|vmin|vmax|Colormap') problems.push('the settings of the layer are not the fields of every layer');
  await page.locator('.scene-view').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_layer.png`) });

  // Its ⇩: the index as a Processing job would give it, with no panel and no job to see.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().exitFocus();
    useAppStore.setState({ dock: 'layers' });
  });
  const download = page.locator('.layer-row [data-col="download"]').first();
  if ((await download.getAttribute('title')) !== 'Download the NDWI of the AOI crop, computed as a Processing job would') problems.push(`the ⇩ says ${await download.getAttribute('title')}`);
  await download.click({ force: true });
  const dialog = page.locator('.dialog-panel');
  await dialog.waitFor();
  const dialogText = await dialog.innerText();
  if (!/NDWI \(\(G - N\) \/ \(G \+ N\)\)/.test(dialogText)) problems.push(`the dialog does not name the index: ${dialogText.slice(0, 160)}`);
  if (await dialog.locator('.dialog-resolution').count()) problems.push('the dialog offers a resolution for an index');
  await dialog.locator('.hint-text', { hasText: 'About 12.4 MB' }).waitFor({ timeout: 8000 }).catch(() => problems.push(`the dialog shows no estimate: ${dialogText.slice(0, 120)}`));
  await dialog.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_dialog.png`) });
  const [file] = await Promise.all([page.waitForEvent('download', { timeout: 15000 }).catch(() => null), dialog.locator('.primary').click()]);
  if (!file) problems.push('no file came');
  else if (file.suggestedFilename() !== 'result.zip') problems.push(`the file is called ${file.suggestedFilename()}`);
  await page.waitForTimeout(500);
  if (jobs.placed.length !== 1) problems.push(`${jobs.placed.length} orders were placed`);
  else {
    const body = JSON.stringify(jobs.placed[0]);
    if (!body.includes('"band_math"') || !body.includes('(green - nir) / (green + nir)') || !body.includes('"NDWI"')) problems.push('the order does not compute the index');
  }
  if ((await page.locator('.processing-panel').count()) !== 0) problems.push('the Processing panel opened');
  const listed = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().jobs.length + document.querySelectorAll('.job-row, .pm-row').length);
  if (listed !== 0) problems.push('a job stands in the list of jobs');
  if ((await page.locator('.dialog-panel').count()) !== 0) problems.push('the dialog stays after the download');

  // Its ⚙: the panel with the index as the one band, not the raw bands.
  await page.locator('.layer-row [data-col="process"]').first().click({ force: true });
  await page.locator('.processing-panel').waitFor({ timeout: 8000 }).catch(() => problems.push('the panel did not open'));
  await page.waitForTimeout(800);
  const chips = await page.locator('.processing-panel section[aria-label="Bands"] .pp-chip').allTextContents();
  if (chips.join('|') !== 'NDWI') problems.push(`the bands of the panel are ${chips}`);
  await page.locator('.processing-panel').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_panel.png`) });
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      if (process.env.ONLY === 'draw') results.push(await checkDraw(browser, theme, viewport));
      else {
        results.push(await checkLayout(browser, theme, viewport));
        results.push(await checkNone(browser, theme, viewport));
        results.push(await checkDraw(browser, theme, viewport));
      }
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
