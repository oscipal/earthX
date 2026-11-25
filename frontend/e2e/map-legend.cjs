// Browser check of the legend over the map and the legends in the layer manager (M5-62, Otto 24.11.2026). With one, two and three
// made-up layers (the eleven classes of ESA WorldCover, heights in metres on a colour scale, the eleven classes of a scene
// classification), the panel of the rail open and closed, in the light and the dark theme, at 1280×800, 1280×360 and 360×740, it fails
// when
//   - the box is not one, titled "Legend", or its dropdown does not list the visible layers with a legend in their order;
//   - it does not show the topmost, or a choice in the dropdown does not show that layer;
//   - it leaves the window, scrolls, or is cut off; covers a control (the rail, the panel of the rail where the map is beside it, the
//     settings, the map buttons, the button at the top right, the marks at the bottom); or does not stand beside the panel;
//   - a list of seven classes or more is not in two columns (one under 900 px), a name is cut off, or a bar has not the colours of its
//     colormap;
// and, once per theme and window size, when
//   - a hidden layer keeps the legend, or a layer dragged to the top in the layer manager does not take it;
//   - a view opened at the top does not take it;
//   - the layer manager with three layers scrolls, or does not show its legends where they fit and fold the rest from the bottom up.
// It writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/map-legend.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-map-legend');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, low: { width: 1280, height: 360 }, narrow: { width: 360, height: 740 } };

const WORLDCOVER = [
  [10, 'Tree cover', '#006400'], [20, 'Shrubland', '#ffbb22'], [30, 'Grassland', '#ffff4c'], [40, 'Cropland', '#f096ff'],
  [50, 'Built-up', '#fa0000'], [60, 'Bare / sparse vegetation', '#b4b4b4'], [70, 'Snow and ice', '#f0f0f0'],
  [80, 'Permanent water bodies', '#0064c8'], [90, 'Herbaceous wetland', '#0096a0'], [95, 'Mangroves', '#00cf75'],
  [100, 'Moss and lichen', '#fae6a0'],
].map(([value, name, colour]) => ({ value, name, colour }));
const SCL = [
  'Saturated or defective', 'Topographic shadows', 'Cloud shadows', 'Vegetation', 'Not vegetated', 'Water', 'Unclassified',
  'Cloud medium probability', 'Cloud high probability', 'Thin cirrus', 'Snow or ice',
].map((name, i) => ({ value: i + 1, name, colour: ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#aec7e8'][i] }));
const TERRAIN = ['#333399', '#0294fa', '#24d36d', '#fefe98', '#82694d', '#ffffff'];
const COLORMAPS = { groups: [{ name: 'other', colormaps: [{ name: 'terrain', reversed: 'terrain_r', colors: TERRAIN }, { name: 'gray', reversed: 'gray_r', colors: ['#000000', '#ffffff'] }] }] };

// The layers, the topmost first: what the layer manager lists.
const LAYERS = [
  { id: 'L1', name: 'Land cover · 2021', query: '&colormap=x', legend: WORLDCOVER },
  { id: 'L2', name: 'Heights', query: '&colormap_name=terrain&rescale=0%2C2900', unit: 'm' },
  { id: 'L3', name: 'Scene classification', query: '&colormap=x', legend: SCL },
];
// A dataset whose view draws its classes, for "a view opened at the top takes the legend".
const COLLECTION = {
  id: 'landcover', type: 'Collection', title: 'Land cover (made up)', description: 'Made up.', license: 'CC-BY-4.0', links: [],
  extent: { spatial: { bbox: [[-180, -60, 180, 84]] }, temporal: { interval: [['2021-01-01T00:00:00Z', '2021-12-31T23:59:59Z']] } },
  'earthx:category': 'land_cover', 'earthx:format': 'cog',
  'earthx:capabilities': { roi: true, time_range: true, band_math: false, interpolation: false, quad_pol: false, single_coverage_product: true, ml_processing: false },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'], overview: 'own', overview_resampling: null, overview_substitute: null },
  'earthx:source': { asset_hosts: ['assets.example.org'], endpoint: 'https://stac.example.org/v1', page_url: 'https://viewer.example.org/collections/landcover', source_collection_id: 'landcover', data_region: 'unknown' },
  'earthx:default_render': { title: 'Land cover', assets: ['map'], rescale: null, colormap_name: 'esa-worldcover', expression: null, resampling: 'nearest' },
  'earthx:band_units': { map: null },
  'earthx:bands': [{ name: 'map', description: 'Land cover class', 'classification:classes': WORLDCOVER.map((c) => ({ value: c.value, name: c.name.toLowerCase().replace(/[^a-z]+/g, '_'), title: c.name, color_hint: c.colour.slice(1).toUpperCase() })) }],
  'earthx:search_filters': [],
};

const rgb = (hex) => `rgb(${parseInt(hex.slice(1, 3), 16)}, ${parseInt(hex.slice(3, 5), 16)}, ${parseInt(hex.slice(5, 7), 16)})`;
const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
const inWindow = (box, size) => box.x >= -0.5 && box.y >= -0.5 && box.x + box.width <= size.width + 0.5 && box.y + box.height <= size.height + 0.5;

async function open(browser, theme, viewport, problems) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.route('**/*', async (r) => {
    const url = new URL(r.request().url());
    const json = (body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return r.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return r.continue();
    if (url.pathname === '/colormaps') return json(COLORMAPS);
    if (url.pathname === '/stac/collections' && r.request().method() === 'POST') return json({ collections: [COLLECTION], links: [], numberMatched: 1 });
    if (url.pathname === '/stac/collections') return json({ collections: [COLLECTION], links: [] });
    if (url.pathname === '/catalogue/categories') return json({ categories: [{ id: 'land_cover', title: 'Land cover and land use' }] });
    if (url.pathname === '/catalogue/regions') return json({ regions: [] });
    if (url.pathname.startsWith('/results/')) return r.fulfill({ status: 404, body: '' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.locator('.app-rail').waitFor();
  return { context, page };
}

// The layers into the store, the panel of the rail as asked.
async function setLayers(page, layers, dock) {
  await page.evaluate(async ({ layers, dock, collection }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const made = layers.map((l) => ({
      id: l.id, name: l.name, visible: true, opacity: 1, derived: 'result', restore: { datasetId: null, itemIds: [] },
      overlays: [{ kind: 'raster', tileUrl: `/results/AbCdEfGhIjKlMnOpQr${l.id}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256${l.query}`, bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
      result: { jobID: `AbCdEfGhIjKlMnOpQr${l.id}`, expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'uint8', stats: null, ...(l.legend ? { classes: true, legend: l.legend } : {}), ...(l.unit ? { unit: l.unit } : {}) },
    }));
    useAppStore.setState({ datasets: datasetsFrom([collection]), layers: made, resultsAt: made.length, dock });
  }, { layers, dock, collection: COLLECTION });
  await page.waitForTimeout(150);
}

const box = (page) => page.locator('.map-legend .legend');
const shownTitle = (page) => page.locator('.legend-choice').evaluate((el) => el.options[el.selectedIndex]?.textContent ?? null).catch(() => null);

async function check(browser, { count, panel, theme, viewport }) {
  const problems = [];
  const size = VIEWPORTS[viewport];
  const { context, page } = await open(browser, theme, viewport, problems);
  const layers = LAYERS.slice(0, count);
  await setLayers(page, layers, panel ? 'controls' : null);
  if ((await box(page).count()) !== 1) problems.push(`${await box(page).count()} boxes instead of one`);
  const title = await page.locator('.map-legend .legend-title').textContent();
  if (title !== 'Legend') problems.push(`the title is "${title}"`);
  const offered = await page.locator('.legend-choice option').allTextContents();
  if (JSON.stringify(offered) !== JSON.stringify(layers.map((l) => l.name))) problems.push(`the dropdown lists ${JSON.stringify(offered)}`);
  if ((await shownTitle(page)) !== layers[0].name) problems.push(`it shows ${await shownTitle(page)}, not the topmost`);

  // Each layer chosen in turn: its classes in their colours, or its bar.
  for (const layer of layers) {
    if (count > 1) await page.locator('.legend-choice').selectOption({ label: layer.name });
    await page.waitForTimeout(60);
    const legend = box(page);
    if (layer.legend) {
      const columns = await legend.locator('.legend-classes').evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' ').length);
      if (columns !== (size.width >= 900 ? 2 : 1)) problems.push(`${layer.name}: ${layer.legend.length} classes in ${columns} columns`);
      const cut = await legend.locator('.legend-name').evaluateAll((els) => els.filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.textContent));
      if (cut.length > 0) problems.push(`${layer.name}: names cut off: ${cut.join(', ')}`);
      const swatches = await legend.locator('.class-swatch').evaluateAll((els) => els.map((el) => getComputedStyle(el).backgroundColor));
      if (JSON.stringify(swatches) !== JSON.stringify(layer.legend.map((c) => rgb(c.colour)))) problems.push(`${layer.name}: the swatches are not the colours of the classes`);
    } else {
      const background = await legend.locator('.legend-bar').evaluate((el) => getComputedStyle(el).backgroundImage).catch(() => '');
      if (!background.includes(rgb(TERRAIN[0])) || !background.includes(rgb(TERRAIN.at(-1)))) problems.push(`${layer.name}: the bar is not in the colours of terrain`);
      const ends = await legend.locator('.legend-ends span').allTextContents();
      if (JSON.stringify(ends) !== JSON.stringify(['0 m', '2900 m'])) problems.push(`${layer.name}: the ends say ${JSON.stringify(ends)}`);
    }
    // Never scrolling, never cut off, in the window, beside the panel, over no control.
    const own = await page.locator('.map-legend').boundingBox();
    const scrolls = await page.locator('.map-legend').evaluate((el) => ['auto', 'scroll'].includes(getComputedStyle(el).overflowY) || el.scrollHeight > el.clientHeight + 1);
    if (scrolls) problems.push(`${layer.name}: the legend scrolls or is cut off`);
    if (!own || !inWindow(own, size)) problems.push(`${layer.name}: the legend leaves the window: ${JSON.stringify(own)}`);
    const wide = size.width >= 900;
    const rail = await page.locator('.app-rail').boundingBox();
    const dock = panel ? await page.locator('.dock').boundingBox() : null;
    const left = (wide && dock ? dock.x + dock.width : rail.x + rail.width) + 16;
    if (own && Math.abs(own.x - left) > 1) problems.push(`${layer.name}: the legend stands at x=${own.x}, not beside the panel at ${left}`);
    const controls = ['.app-rail', '.inspector', '.map-controls-host', '.overlay.top-right > *', '.preview-badge-dock > *', '.overlay.bottom > *', ...(wide ? ['.dock'] : [])];
    for (const selector of controls) {
      for (const other of await page.locator(selector).all()) {
        const b = await other.boundingBox();
        if (b && own && b.width > 0 && overlap(own, b)) problems.push(`${layer.name}: the legend covers ${selector}`);
      }
    }
    if (!wide && panel && own) {
      const under = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('.dock') !== null, { x: own.x + own.width / 2, y: own.y + own.height / 2 });
      if (!under) problems.push(`${layer.name}: in a narrow window the legend lies over the open panel`);
    }
    await page.screenshot({ path: path.join(OUT, `legend-${count}-${panel ? 'panel' : 'nopanel'}-${theme}-${viewport}-${layer.id}.png`) });
  }
  await context.close();
  return problems;
}

// Hiding, dragging in the layer manager, a view at the top, and the legends in the layer manager.
async function follow(browser, { theme, viewport }) {
  const problems = [];
  const size = VIEWPORTS[viewport];
  const { context, page } = await open(browser, theme, viewport, problems);
  await setLayers(page, LAYERS, 'layers');

  // The layer manager with three layers never scrolls: the legends fold from the bottom up where they do not fit.
  const list = page.locator('.layer-list');
  await page.waitForTimeout(200);
  const scrolls = await list.evaluate((el) => el.scrollHeight > el.clientHeight + 1);
  if (scrolls) problems.push('the layer manager scrolls');
  const open3 = await page.locator('.layer-row').evaluateAll((rows) => rows.map((row) => row.querySelector('[data-col="legend"]') !== null));
  const firstFolded = open3.indexOf(false);
  if (firstFolded >= 0 && open3.slice(firstFolded).some(Boolean)) problems.push(`the legends fold not from the bottom up: ${JSON.stringify(open3)}`);
  const cut = await page.locator('.layer-row .legend-name').evaluateAll((els) => els.filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.textContent));
  if (cut.length > 0) problems.push(`names cut off in the layer manager: ${cut.slice(0, 3).join(', ')}`);
  await page.screenshot({ path: path.join(OUT, `manager-${theme}-${viewport}.png`) });
  if (viewport === 'low') console.log(`     (layer manager, ${theme} ${viewport}: legends shown ${JSON.stringify(open3)})`);

  // Hidden with the eye of its row: the topmost visible one takes the legend. Below 900 px the layer manager covers the map; the
  // legend is read all the same.
  // A click on the eye itself: under 900 px the status box ("Loading data" for the made-up tiles) may lie over the list.
  await page.locator('.layer-row').nth(0).locator('[data-col="eye"]').dispatchEvent('click');
  await page.waitForTimeout(100);
  if ((await shownTitle(page)) !== 'Heights') problems.push(`after hiding the topmost layer the legend shows ${await shownTitle(page)}, not Heights`);
  await page.locator('.layer-row').nth(0).locator('[data-col="eye"]').dispatchEvent('click');
  await page.waitForTimeout(100);
  if ((await shownTitle(page)) !== LAYERS[0].name) problems.push(`shown again, the topmost does not take the legend back: ${await shownTitle(page)}`);

  // A choice in the dropdown holds; dragging the third layer to the top in the layer manager hands the legend to it.
  await page.locator('.legend-choice').selectOption({ label: 'Heights' });
  await page.waitForTimeout(60);
  const grip = page.locator('.layer-row').nth(2).locator('.lm-grip');
  const top = await page.locator('.layer-row').nth(0).boundingBox();
  const from = await grip.boundingBox();
  if (from && top) {
    await page.mouse.move(from.x + from.width / 2, from.y + from.height / 2);
    await page.mouse.down();
    await page.mouse.move(from.x + from.width / 2, top.y + 4, { steps: 12 });
    await page.mouse.up();
    await page.waitForTimeout(150);
    const order = await page.locator('.layer-row .lm-name').allTextContents();
    if (order[0] !== 'Scene classification') problems.push(`the drag did not move the layer to the top: ${JSON.stringify(order)}`);
    if ((await shownTitle(page)) !== 'Scene classification') problems.push(`after the drag the legend shows ${await shownTitle(page)}, not the layer dragged to the top`);
  } else problems.push('no grip to drag');
  await page.screenshot({ path: path.join(OUT, `follow-${theme}-${viewport}.png`) });

  // A view opened at the top ("Search results" first): it takes the legend, titled by its dataset.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const info = { datasetId: 'landcover', tileUrl: '/t/{z}/{x}/{y}?assets=map', bounds: [0, 0, 1, 1], asset: 'map', minZoom: 0, maxZoom: 14 };
    useAppStore.setState({ resultsAt: 0, datasetId: 'landcover', focusMode: true, cropToAoi: true, downloaded: { s0: info }, showDownloaded: true, appliedRender: { colormapName: 'esa-worldcover' }, groups: [], selectedIds: [] });
  });
  await page.waitForTimeout(150);
  if ((await shownTitle(page)) !== 'Land cover (made up)') problems.push(`a view opened at the top shows ${await shownTitle(page)} in the legend, not itself`);
  // Where the settings sheet takes the map of a narrow window the legend gives way (UI-12, `.crowded`); otherwise it stays in the window.
  const givesWay = await page.locator('.map-legend.crowded').count();
  if (!givesWay && !(await page.locator('.map-legend').boundingBox().then((b) => b && inWindow(b, size)))) problems.push('with the view the legend leaves the window');
  await page.screenshot({ path: path.join(OUT, `view-${theme}-${viewport}.png`) });
  await context.close();
  return problems;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  const report = (name, problems) => {
    failed += problems.length;
    console.log(`${problems.length ? 'FAIL' : 'ok  '} ${name}${problems.map((p) => `\n     - ${p}`).join('')}`);
  };
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const panel of [true, false]) {
        for (const count of [1, 2, 3]) {
          report(`${count} layer${count > 1 ? 's' : ''} ${panel ? 'panel open' : 'panel closed'} ${theme} ${viewport}`, await check(browser, { count, panel, theme, viewport }));
        }
      }
      report(`hide, drag, view, layer manager ${theme} ${viewport}`, await follow(browser, { theme, viewport }));
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
