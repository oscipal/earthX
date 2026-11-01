// The settings box of every layer is one box (NM4-54 part 5, Otto, 1.11.2026), in a real browser: a job's result, a pinned view
// ("Crop to AOI") and the view of the search, each drawn as RGB, as one band and as an index. Measured: the box and its fields.
//   1. The form does not change with the picture: for each kind of layer the box has the same size, and every field the same
//      place, whether RGB, a band or an index is drawn (the colormap of RGB stays, locked, with its reason in the tooltip).
//   2. The three kinds are the same box: the same width, and the fields and the buttons in the same places (the view of the search
//      has the row of its buttons under them, a layer has its opacity under them).
// In the light and the dark theme, at 1280 and 360 px; a screenshot per case (the table of sizes is printed).
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/settings-box.cjs               # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-settings-box');
const THEMES = process.env.ONLY ? { light: 'normal' } : { light: 'normal', dark: 'tech' };
const VIEWPORTS = process.env.ONLY ? { wide: { width: 1280, height: 800 } } : { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const FOOTPRINT = [10, 50, 11, 51];
const SCENES = ['SYNTH_A', 'SYNTH_B'];
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
const PRESETS = [['NDVI', 'Normalized Difference Vegetation Index', '(nir - red) / (nir + red)', 'rdylgn', '(N - R)/(N + R)']].map(([name, title, expression, colormap_name, formula]) => ({
  name, title, expression, rescale: [[-1, 1]], colormap_name, formula, reference: 'https://example.org/formula',
}));

async function open(browser, theme, viewport) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': SCENES });
    if (url.pathname.includes('/statistics')) return json({ b1: { min: 0, max: 4000, percentile_2: 100, percentile_98: 2900 } });
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  return { context, page, problems };
}

// The store of the page: the view of the search with the dataset, then whatever the case needs.
async function seed(page) {
  await page.evaluate(async ({ scenes, footprint, presets }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 8, maxZoom: 14 });
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const aoi = { type: 'Polygon', coordinates: [[[10.2, 50.2], [10.8, 50.2], [10.8, 50.8], [10.2, 50.8], [10.2, 50.2]]] };
    const tiff = (n) => ({ href: 'https://example.org/x.tif', type: COG, 'raster:bands': Array.from({ length: n }, () => ({ data_type: 'uint16', nodata: 0 })) });
    const items = scenes.map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { visual: tiff(3), B04: tiff(1), B08: tiff(1) } }));
    const collection = {
      id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:true_color': ['red', 'green', 'blue'], 'earthx:auxiliary_assets': ['visual'],
      'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
      'earthx:index_presets': presets,
    };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', items, groups: [{ key: ['a'], label: '2026-07-01', items }], activeGroupIndex: 0,
      selectedIds: scenes, downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: true, viewAoi: aoi, aoi, showDownloaded: true, dock: null,
      appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', layers: [], mosaics: {}, error: null, mapZoom: 12,
      flyToView: { center: [10.5, 50.5], zoom: 10 },
    });
    await useAppStore.getState().loadMosaics();
  }, { scenes: SCENES, footprint: FOOTPRINT, presets: PRESETS });
  await page.waitForSelector('.scene-view .vc-apply');
}

const pick = (page, value) => page.locator('.scene-view .vc-render label', { hasText: /^Band/ }).locator('select').selectOption(value);
const settle = (page) => page.waitForTimeout(600);

// The look of the view of the search: RGB, a band, an index (chosen and applied).
async function look(page, what) {
  if (what === 'rgb') return;
  await pick(page, what === 'band' ? 'band:B04' : 'index:NDVI');
  await settle(page);
  await page.locator('.scene-view .vc-apply').click();
  await settle(page);
}

// The result layer of a job with the bands red, green, blue and NDVI, drawn as RGB, as the band "red" or as the band "NDVI".
async function resultBox(page, what) {
  await page.evaluate(async ({ what }) => {
    const { useAppStore } = await import('/src/store.ts');
    const band = what === 'rgb' ? '@rgb' : what === 'band' ? 0 : 3;
    useAppStore.setState({
      focusMode: false, downloaded: {}, viewOfLayer: false, resultViewLayerId: 'R1', dock: 'layers',
      layers: [{
        id: 'R1', name: 'Result · bands', visible: true, opacity: 1, derived: 'result', restore: { datasetId: null, itemIds: [] },
        overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
        result: {
          jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null,
          bands: ['red', 'green', 'blue', 'NDVI'].map((name) => ({ name, stats: null })), band, colour: [0, 1, 2],
        },
      }],
    });
  }, { what });
  await page.waitForSelector('.result-controls .vc-apply');
}

// The view of a layer pinned from the view of the search (opened again from the layer manager).
async function pinnedBox(page, what) {
  await look(page, what);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().addCurrentToLayers();
    await new Promise((resolve) => setTimeout(resolve, 600));
    const [layer] = useAppStore.getState().layers;
    useAppStore.getState().exitFocus();
    useAppStore.getState().selectLayer(layer.id);
  });
  await page.waitForSelector('.scene-view .vc-apply');
}

// What the box measures: itself and the places of its parts.
async function measure(page) {
  return page.evaluate(() => {
    const rect = (e) => (e ? (({ x, y, width, height }) => ({ x: Math.round(x * 10) / 10, y: Math.round(y * 10) / 10, w: Math.round(width * 10) / 10, h: Math.round(height * 10) / 10 }))(e.getBoundingClientRect()) : null);
    const box = document.querySelector('.scene-view');
    const field = (name) => [...box.querySelectorAll('.vc-render label')].find((l) => l.querySelector('span')?.textContent === name);
    const base = rect(box);
    // Places are counted from the end of the head: the head of the view of the search holds more (the dataset, the arrows, the
    // eye) and wraps in a narrow window; the rest of the box is what has to be alike.
    const headEnd = rect(box.querySelector('.vc-head')).y + rect(box.querySelector('.vc-head')).h - base.y;
    const rel = (e, fromHead = true) => {
      const r = rect(e);
      return r && { x: Math.round((r.x - base.x) * 10) / 10, y: Math.round((r.y - base.y - (fromHead ? headEnd : 0)) * 10) / 10, w: r.w, h: r.h };
    };
    const colormap = field('Colormap')?.querySelector('select');
    return {
      box: { w: base.w, h: base.h },
      head: rel(box.querySelector('.vc-head'), false),
      band: rel(field('Band')),
      vmin: rel(field('vmin')),
      vmax: rel(field('vmax')),
      colormap: rel(field('Colormap')),
      buttons: rel(box.querySelector('.vc-buttons')),
      opacity: rel(box.querySelector('.vc-opacity')),
      actions: rel(box.querySelector('.vc-actions')),
      colormapLocked: colormap ? colormap.disabled : null,
      colormapTitle: field('Colormap')?.title ?? null,
      escapes: [...box.querySelectorAll('*')].some((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > base.x + base.w + 1 || r.left < base.x - 1); }),
    };
  });
}

const KINDS = { job: resultBox, pinned: pinnedBox, search: async (page, what) => look(page, what) };
const PARTS = ['band', 'vmin', 'vmax', 'colormap', 'buttons'];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const problems = [];
  const rows = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const found = {};
      for (const kind of Object.keys(KINDS)) {
        for (const what of ['rgb', 'band', 'index']) {
          const { context, page, problems: own } = await open(browser, theme, viewport);
          await seed(page);
          await KINDS[kind](page, what);
          await settle(page);
          found[`${kind}/${what}`] = await measure(page);
          await page.locator('.scene-view').screenshot({ path: path.join(OUT, `${kind}_${what}_${theme}_${viewport}.png`) });
          problems.push(...own.map((p) => `${kind}/${what} ${theme} ${viewport}: ${p}`));
          await context.close();
        }
      }
      const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
      for (const kind of Object.keys(KINDS)) {
        const [rgb, band, index] = ['rgb', 'band', 'index'].map((what) => found[`${kind}/${what}`]);
        const tag = `${kind} ${theme} ${viewport}`;
        // 1. The form does not change with the picture.
        for (const [name, other] of [['band', band], ['index', index]]) {
          if (!same(rgb.box, other.box)) problems.push(`${tag}: the box is ${JSON.stringify(rgb.box)} at RGB and ${JSON.stringify(other.box)} at ${name}`);
          for (const part of PARTS) if (!same(rgb[part], other[part])) problems.push(`${tag}: "${part}" is at ${JSON.stringify(rgb[part])} at RGB and ${JSON.stringify(other[part])} at ${name}`);
        }
        if (rgb.colormap === null || rgb.colormapLocked !== true || !rgb.colormapTitle) problems.push(`${tag}: the colormap of RGB is not there locked with its reason (${JSON.stringify([rgb.colormap, rgb.colormapLocked, rgb.colormapTitle])})`);
        if (band.colormapLocked !== false) problems.push(`${tag}: the colormap of a band is locked`);
        for (const [what, m] of [['rgb', rgb], ['band', band], ['index', index]]) if (m.escapes) problems.push(`${tag}/${what}: something is outside the box`);
        rows.push(`${theme.padEnd(5)} ${viewport.padEnd(6)} ${kind.padEnd(7)} head ${rgb.head.h} box ${rgb.box.w} x ${rgb.box.h}   opacity row ${rgb.opacity ? 'yes' : 'no '}  actions row ${rgb.actions ? 'yes' : 'no '}`);
      }
      // 2. The three kinds are the same box.
      const [job, pinned, search] = ['job', 'pinned', 'search'].map((kind) => found[`${kind}/rgb`]);
      const tag = `${theme} ${viewport}`;
      if (viewport === 'wide' && !(job.head.h === pinned.head.h && pinned.head.h === search.head.h)) problems.push(`${tag}: the heads are ${job.head.h}, ${pinned.head.h} and ${search.head.h} high`);
      if (viewport === 'wide' && !(job.box.h === pinned.box.h && pinned.box.h === search.box.h)) problems.push(`${tag}: the boxes are ${job.box.h}, ${pinned.box.h} and ${search.box.h} high`);
      if (!(job.box.w === pinned.box.w && pinned.box.w === search.box.w)) problems.push(`${tag}: the boxes are ${job.box.w}, ${pinned.box.w} and ${search.box.w} wide`);
      for (const part of ['vmin', 'vmax', 'colormap', 'buttons']) {
        for (const [name, other] of [['pinned', pinned], ['search', search]]) {
          if (!same(job[part], other[part])) problems.push(`${tag}: "${part}" of the job layer is at ${JSON.stringify(job[part])}, of the ${name} view at ${JSON.stringify(other[part])}`);
        }
      }
    }
  }
  await browser.close();
  console.log(rows.join('\n'));
  console.log(problems.length === 0 ? 'ok: one box' : `FAIL\n${problems.join('\n')}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(problems.length === 0 ? 0 : 1);
})();
