// A selection of thousands of 1-degree tiles over the antimeridian (M5-56, Otto's browser check of 18.11.2026: GLO-30 over
// Russia), in a real browser with made-up tiles and no backend. 2500 tiles, more than a selection of the tiler takes (2000), so
// every view draws them one by one. It fails when
//   1. after the search (pages of 100, "Load more" to the end) and "Select all" not every tile has its outline;
//   2. "Crop and merge to AOI" keeps the outline of each tile instead of one ring over the antimeridian (one feature, merged);
//   3. the view draws nothing at zoom 8 where the map looks, far from where the list starts (the tiles in view are asked for);
//   4. the preview of the processing panel (Band math, a dataset of the same tiles) asks for no tile in view at zoom 8, or for
//      the first 40 of the list instead (adr/0032 §10.4).
//
//   cd frontend && npm run dev &            # a dev server; no backend is needed
//   node e2e/large-selection.cjs            # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersFootprints, answersSelection } = require('./selectionMock.cjs');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-large-selection');
const TILES = 2500;
const COLUMNS = 60;
// 60 columns from 150° E over the antimeridian to 150° W, rows from 40° N.
const tileAt = (i) => {
  const west = ((150 + (i % COLUMNS) + 180) % 360) - 180;
  const south = 40 + Math.floor(i / COLUMNS);
  return [west, south, west + 1, south + 1];
};
const TOP = 40 + Math.ceil(TILES / COLUMNS);
const AOI = { type: 'MultiPolygon', coordinates: [[[[150, 40], [180, 40], [180, TOP], [150, TOP], [150, 40]]], [[[-180, 40], [-150, 40], [-150, TOP], [-180, TOP], [-180, 40]]]] };
// Where the map is taken to: west of the antimeridian, rows away from the first tiles of the list.
const LOOK = [-165.5, 70.5];

function solid(rgba) {
  const chunk = (type, data) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, 'ascii');
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, crc]);
  };
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 256 }, () => rgba).flat())]);
  const header = Buffer.alloc(13);
  header.writeUInt32BE(256, 0);
  header.writeUInt32BE(256, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: 256 }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
}
const BLUE = solid([0, 0, 255, 255]);
const GREEN = solid([0, 200, 0, 255]);

const ITEMS = Array.from({ length: TILES }, (_, i) => {
  const [w, s, e, n] = tileAt(i);
  return {
    id: `TILE_${String(i).padStart(4, '0')}`, collection: 'cop-dem-glo-30', bbox: [w, s, e, n],
    geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
    properties: { datetime: '2021-04-22T00:00:00Z', start_datetime: '2021-04-22T00:00:00Z', gsd: 30 },
    assets: { data: { href: `https://assets.example.org/${i}.tif`, type: 'image/tiff; application=geotiff; profile=cloud-optimized', 'raster:bands': [{ data_type: 'float32' }] } },
  };
});
// The tiles that meet a view (west, south, east, north), by id.
const meeting = (view) => new Set(ITEMS.filter(({ bbox }) => bbox[0] <= view[2] && bbox[2] >= view[0] && bbox[1] <= view[3] && bbox[3] >= view[1]).map((it) => it.id));

async function run(browser, results) {
  const problems = [];
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  const scenes = [];
  const description = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'cop-dem-glo-30.json'), 'utf8'));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (url.pathname.endsWith('/processes/recipe')) return json(description);
    if (url.pathname.endsWith('/stac/collections')) return json({ collections: [collection()] });
    if (url.pathname.endsWith('/stac/search')) {
      const body = JSON.parse(route.request().postData() ?? '{}');
      const start = Number(body.token ?? 0);
      const features = ITEMS.slice(start, start + (body.limit ?? 100));
      const next = start + features.length < ITEMS.length ? String(start + features.length) : null;
      return json({ type: 'FeatureCollection', features, numberMatched: ITEMS.length, numberReturned: features.length, links: next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: next } }] : [] });
    }
    if (url.pathname.endsWith('/scene-order')) return json({ order: JSON.parse(route.request().postData() ?? '{}').items ?? [] });
    if (answersSelection(route, url) || answersFootprints(route, url)) return;
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    if (url.pathname.endsWith('/statistics')) return json({ b1: { count: 9, min: 0, max: 4000, percentile_2: 0, percentile_98: 3000 } });
    if (url.pathname.includes('/overview/')) return route.fulfill({ status: 200, contentType: 'image/png', body: GREEN });
    const scene = /\/items\/([^/]+)\/tiles\/WebMercatorQuad\/(\d+)\//.exec(url.pathname);
    if (scene) {
      scenes.push({ id: decodeURIComponent(scene[1]), z: Number(scene[2]), operator: url.searchParams.has('op') });
      return route.fulfill({ status: 200, contentType: 'image/png', body: BLUE });
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');
  // The list of datasets the app asks for at start is in before the state is put in place.
  await page.waitForTimeout(1500);
  const map = await page.evaluateHandle(() => {
    const el = document.querySelector('.maplibregl-map');
    let fiber = el[Object.keys(el).find((k) => k.startsWith('__reactFiber$'))];
    for (; fiber; fiber = fiber.return) {
      for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
        const held = hook.memoizedState?.current;
        if (held && typeof held.getStyle === 'function') return held;
      }
    }
    return null;
  });
  const store = (fn, arg) => page.evaluate(async ([body, a]) => new Function('s', 'a', body)((await import('/src/store.ts')).useAppStore, a), [fn, arg]);
  const outlines = () => page.evaluate(async (m) => {
    const data = await m.getSource('mosaicsel-src').getData();
    return { count: data.features.length, merged: data.features.filter((f) => f.properties?.fallback === false).length };
  }, map);
  const lookAt = async () => {
    await store('s.setState({ flyToView: { center: a, zoom: 8 } })', LOOK);
    await page.waitForTimeout(3000);
    return page.evaluate((m) => { const b = m.getBounds(); return [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]; }, map);
  };

  // 1. The search, page by page to the end, and "Select all".
  await store(`s.setState({
    datasets: a.datasets, selectedDatasetIds: ['cop-dem-glo-30'], datasetId: 'cop-dem-glo-30', selectedIds: [], resultsOnMap: true,
    focusMode: false, downloaded: {}, layers: [], mosaics: {}, aoi: a.aoi, error: null, notice: null, dock: null,
    flyToView: { center: [180, 60], zoom: 2.5 },
  })`, { aoi: AOI, datasets: await page.evaluate(async (c) => (await import('/src/datasets.ts')).datasetsFrom([c]), collection()) });
  await store('return s.getState().runSearch()');
  for (let i = 0; i < 40 && (await store('return s.getState().searchContext?.nextToken ?? null')) !== null; i++) {
    await store('return s.getState().loadMore()');
    await page.waitForTimeout(300);
  }
  const loaded = await store('return s.getState().items.length');
  if (loaded !== TILES) problems.push(`the search loaded ${loaded} of ${TILES} tiles`);
  fs.mkdirSync(OUT, { recursive: true });
  await store("s.setState({ dock: 'results' })");
  await page.locator('.selection-row input[type="checkbox"]').check().catch(async (error) => {
    problems.push(`no "Select all": ${error.message.split('\n')[0]}`);
    await page.screenshot({ path: path.join(OUT, '1-no-select-all.png') });
  });
  await page.waitForTimeout(1000);
  const ticked = await outlines();
  if (ticked.count !== TILES) problems.push(`after "Select all" ${ticked.count} of ${TILES} tiles have their outline`);
  await page.screenshot({ path: path.join(OUT, '1-select-all.png') });

  // 2. "Crop and merge to AOI": one ring over the antimeridian.
  await page.getByRole('button', { name: 'Crop and merge to AOI' }).click();
  await page.waitForTimeout(3000);
  const ring = await outlines();
  if (ring.count !== 1 || ring.merged !== 1) problems.push(`after the crop the outline is ${ring.count} features, ${ring.merged} merged, not one ring`);
  await page.screenshot({ path: path.join(OUT, '2-crop.png') });

  // 3. Zoom 8 where the list does not start: the tiles in view are asked for.
  scenes.length = 0;
  const view = await lookAt();
  const inView = meeting(view);
  const viewAsked = scenes.filter((s) => !s.operator && s.z >= 7);
  if (viewAsked.length === 0) problems.push('the view asked for no tile at zoom 8');
  if (viewAsked.some((s) => !inView.has(s.id))) problems.push('the view asked for tiles out of view');
  await page.screenshot({ path: path.join(OUT, '3-view-z8.png') });

  // 4. The preview of the processing panel at the same place: the tiles in view, not the first 40 of the list.
  await store('s.getState().exitFocus()');
  await store(`s.setState({ selectedIds: s.getState().items.map((it) => it.id), flyToView: { center: [180, 60], zoom: 2.5 } })`);
  await page.waitForTimeout(1500);
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().openProcessing());
  await page.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('data * 2');
  await page.waitForTimeout(2500);
  scenes.length = 0;
  const previewView = await lookAt();
  const previewInView = meeting(previewView);
  const previewAsked = scenes.filter((s) => s.operator && s.z >= 7);
  if (previewAsked.length === 0) problems.push('the preview asked for no tile at zoom 8');
  if (previewAsked.some((s) => !previewInView.has(s.id))) problems.push(`the preview asked for tiles out of view: ${[...new Set(previewAsked.filter((s) => !previewInView.has(s.id)).map((s) => s.id))].slice(0, 3).join(', ')}`);
  await page.screenshot({ path: path.join(OUT, '4-preview-z8.png') });

  results.push({ name: 'large selection', problems, detail: `${ticked.count} outlines, ${viewAsked.length} view tiles, ${previewAsked.length} preview tiles at z8` });
  await context.close();
}

// A dataset like GLO-30: a pyramid below z7, its own files from z7 on, one group.
function collection() {
  return {
    id: 'cop-dem-glo-30', title: 'Elevation model', 'earthx:format': 'cog',
    'earthx:capabilities': { roi: true, time_range: false, band_math: true, interpolation: true },
    'earthx:default_render': { title: 'Height', assets: ['data'], rescale: [[0, 4000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
    'earthx:viewer': { group_by: ['start_datetime'], min_zoom: 7, max_zoom: 15, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['start_datetime'], overview: 'pyramid', overview_resampling: 'average', overview_substitute: null },
    'earthx:license_flags': { tier: 'processing', attribution_required: true, attribution_modified: 'made up', attribution_unmodified: 'made up' },
    extent: { spatial: { bbox: [[-180, -90, 180, 84]] }, temporal: { interval: [['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z']] } },
  };
}

(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  await run(browser, results);
  await browser.close();
  for (const { name, problems, detail } of results) console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name} — ${detail}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
