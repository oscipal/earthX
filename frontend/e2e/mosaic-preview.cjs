// Browser check of NM4-04b, in a real browser with made-up answers of the tiler:
//   1. One job over a pass of four scenes asks the TileJSON of the mosaic (not of a scene), measures the first scene
//      of its order, and draws the mosaic tiles. The first tile of the cold mosaic takes 6 s (Otto, 28.10.2026): the map
//      says "Loading…" in a small badge until it is there, and the badge is gone afterwards.
//   2. A mosaic the tiler refuses is drawn scene by scene; "Preview" carries the hint in its tooltip, the panel none.
// In the light and the dark theme, at a wide and a narrow window; a screenshot per case.
//
//   cd frontend && npm run dev &
//   node e2e/mosaic-preview.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Search answers, process description, TileJSON, statistics and tiles are made up here. Playwright and Chromium are
// not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-mosaic-preview');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const FOOTPRINT = [10.3119, 46.8326, 11.8028, 47.8459];
const SCENES = ['SYNTH_T32TPT_20260801_D', 'SYNTH_T32TPT_20260801_B', 'SYNTH_T32TPT_20260801_A', 'SYNTH_T32TPT_20260801_C'];
// The order the made-up tiler names: the scene that wins where they overlap comes first.
const ORDER = ['SYNTH_T32TPT_20260801_B', 'SYNTH_T32TPT_20260801_C', 'SYNTH_T32TPT_20260801_A', 'SYNTH_T32TPT_20260801_D'];
const COLD_TILE_MS = 6000;
const HINT = 'Preview per scene – may differ from the job where scenes overlap';

// A 256 x 256 PNG of one translucent colour: enough to see that a tile was drawn.
function png() {
  const crc = (buffer) => {
    let c;
    let crc32 = 0xffffffff;
    for (const byte of buffer) {
      c = (crc32 ^ byte) & 0xff;
      for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crc32 = (crc32 >>> 8) ^ c;
    }
    return (crc32 ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, data) => {
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const sum = Buffer.alloc(4);
    sum.writeUInt32BE(crc(body));
    return Buffer.concat([length, body, sum]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(256, 0);
  header.writeUInt32BE(256, 4);
  header[8] = 8;
  header[9] = 6;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(256 * 4)]);
  for (let x = 0; x < 256; x++) row.set([40, 180, 90, 150], 1 + x * 4);
  const raw = Buffer.concat(Array.from({ length: 256 }, () => row));
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header),
    chunk('IDAT', zlib.deflateSync(raw)),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}
const TILE = png();
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function check(browser, theme, viewport, scenario) {
  const name = `${theme} ${viewport} ${scenario}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const seen = { mosaicProbes: [], mosaicTiles: [], itemProbes: [], statistics: [], itemTiles: [] };
  let tilesDelivered = null;
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) {
      seen.mosaicProbes.push(url.search);
      if (scenario === 'refused') return json({ detail: "'sentinel-2-c1-l2a' does not allow reprojection, which a mosaic of scenes may need" }, 422);
      return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': ORDER });
    }
    if (url.pathname.includes('/mosaic/tiles/')) {
      seen.mosaicTiles.push(url.search);
      await sleep(COLD_TILE_MS);
      tilesDelivered = Date.now();
      return route.fulfill({ status: 200, contentType: 'image/png', body: TILE });
    }
    if (url.pathname.endsWith('/tilejson.json')) {
      seen.itemProbes.push(url.pathname);
      return json({ tilejson: '3.0.0' });
    }
    if (url.pathname.endsWith('/statistics')) {
      seen.statistics.push(url.pathname);
      return json({ b1: { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null } });
    }
    if (url.pathname.includes('/tiles/')) {
      seen.itemTiles.push(url.pathname);
      return route.fulfill({ status: 200, contentType: 'image/png', body: TILE });
    }
    return json({ detail: 'not made up' }, 404);
  });

  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.goto(BASE);
  await page.waitForTimeout(1500);
  await page.evaluate(async ({ footprint, scenes }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const [w, s, e, n] = footprint;
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const band = { data_type: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0 };
    const items = scenes.map((id) => ({
      id, collection: 'sentinel-2-c1-l2a', bbox: footprint,
      geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
      properties: { datetime: '2026-08-01T10:20:39Z', gsd: 10 },
      assets: {
        red: { href: `https://example.org/synth/${id}/B04.tif`, type: COG, 'raster:bands': [band] },
        nir: { href: `https://example.org/synth/${id}/B08.tif`, type: COG, 'raster:bands': [band] },
      },
    }));
    useAppStore.setState({
      datasets: [{
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 5, max: 14 },
        browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
        collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } },
      }],
      datasetId: 'sentinel-2-c1-l2a', selectedDatasetIds: ['sentinel-2-c1-l2a'],
      items, groups: [{ key: ['2026-08-01'], label: '2026-08-01', items }], activeGroupIndex: 0,
      selectedIds: scenes, layers: [], focusMode: false, error: null,
      flyToView: { center: [11.05, 47.35], zoom: 10 },
    });
    useProcessingStore.getState().openProcessing();
  }, { footprint: FOOTPRINT, scenes: SCENES });
  await page.getByRole('button', { name: /Band math/ }).first().click({ timeout: 8000 }).catch((error) => {
    problems.push(`no "Band math" button: ${error.message.split('\n')[0]}`);
    return page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_failed.png`) });
  });
  if (problems.length > 0) {
    await context.close();
    return { name, problems, detail: 'the panel did not open' };
  }
  const started = Date.now();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (label) => page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_${label}.png`) });
  const loading = page.locator('.preview-badge-dock .preview-badge.loading');
  const badges = () => page.locator('.preview-badge-dock .preview-badge:not(.loading)');

  if (scenario === 'cold') {
    // 400 ms of debounce, 600 ms before the badge shows: by 1.6 s the wait is on the map and in no line of the panel.
    await page.waitForTimeout(1600);
    if ((await loading.count()) !== 1) problems.push('no "Loading…" badge while the first tile is on its way');
    else {
      const box = await loading.boundingBox();
      const dock = await page.locator('.preview-badge-dock').boundingBox();
      if (box.width > 120 || box.height > 32) problems.push(`the badge takes ${Math.round(box.width)} x ${Math.round(box.height)} px`);
      if (box.x < 0 || box.x + box.width > VIEWPORTS[viewport].width || dock.y + dock.height > VIEWPORTS[viewport].height) problems.push('the badge is not within the window');
      if ((await loading.getAttribute('title')) !== 'Reading the scenes. The first tile of a mosaic can take several seconds.') problems.push('the badge has no explanation in its tooltip');
      await shot('loading');
    }
    // The panel's heading says it too, in a badge: a narrow window hides the map behind the panel.
    const inHeading = page.locator('.processing-panel .pp-heading .pp-badge.loading');
    if ((await inHeading.count()) !== 1) problems.push('no "Loading…" badge in the heading of the preview');
    else {
      await inHeading.scrollIntoViewIfNeeded();
      const box = await inHeading.boundingBox();
      if (box.height > 32 || box.width > 120) problems.push(`the badge in the panel takes ${Math.round(box.width)} x ${Math.round(box.height)} px`);
      await page.locator('.processing-panel section[aria-label="Preview on the map"]').screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_heading.png`) });
    }
    const lines = await page.evaluate(() => [...document.querySelectorAll('.processing-panel p')].map((p) => p.textContent ?? '').filter((t) => /Loading/.test(t) && !/operators/.test(t)));
    if (lines.length > 0) problems.push('the panel says "Loading" in a line of its own');
    for (let i = 0; i < 30 && (await loading.count()) !== 0; i++) await page.waitForTimeout(500);
    if ((await loading.count()) !== 0) problems.push('"Loading…" stays after the tile has come');
    if ((await inHeading.count()) !== 0) problems.push('"Loading…" stays in the heading after the tile has come');
    if (tilesDelivered === null) problems.push('the mosaic tile was never delivered');
    else console.log(`     badge gone ${((Date.now() - tilesDelivered) / 1000).toFixed(1)} s after the first tile`);
    await shot('done');
    if (seen.mosaicProbes.length < 1) problems.push('the TileJSON of the mosaic was not asked');
    if (seen.itemProbes.length !== 0) problems.push(`a scene was asked for its TileJSON ${seen.itemProbes.length} time(s)`);
    if (seen.statistics.length !== 1 || !seen.statistics[0].includes(`/items/${ORDER[0]}/statistics`)) problems.push(`the statistics asked: ${seen.statistics.join(', ')}; not once over ${ORDER[0]}`);
    const first = new URLSearchParams(seen.mosaicTiles[0] ?? '');
    if (JSON.stringify(first.getAll('item')) !== JSON.stringify([...SCENES].sort())) problems.push(`the mosaic tile names the scenes ${first.getAll('item')}`);
    for (const key of first.keys()) if (!['item', 'asset', 'op', 'op_version', 'params', 'rescale', 'colormap_name'].includes(key)) problems.push(`the mosaic tile carries ${key}`);
    if ((await badges().first().getAttribute('title')) !== null) problems.push('"Preview" carries a hint though the mosaic is drawn');
  } else {
    await page.waitForTimeout(2500);
    const badge = badges().first();
    if ((await badge.textContent()) !== 'Preview') problems.push('no "Preview" badge');
    if ((await badge.getAttribute('title')) !== HINT) problems.push('"Preview" over the map has no hint in its tooltip');
    const inPanel = page.locator('.processing-panel .pp-badge:not(.loading)');
    if ((await inPanel.getAttribute('title')) !== HINT) problems.push('"Preview" in the panel has no hint in its tooltip');
    const panel = await page.evaluate(() => document.querySelector('.processing-panel')?.textContent ?? '');
    if (/Preview per scene|may differ from the job/.test(panel)) problems.push('the panel carries the hint as text');
    if (seen.mosaicTiles.length !== 0) problems.push('a refused mosaic asked for tiles');
    if (seen.itemTiles.length === 0) problems.push('no scene was drawn instead');
    if (seen.itemProbes.length < 1) problems.push('the first scene was not asked about the chain');
    // A narrow window hides the map behind the panel: the tooltip of the badge in the panel is the one to look at.
    await (viewport === 'wide' ? badge : inPanel).hover();
    await page.waitForTimeout(1500);
    await shot('hint');
    for (let i = 0; i < 30 && (await loading.count()) !== 0; i++) await page.waitForTimeout(500);
    if ((await loading.count()) !== 0) problems.push('"Loading…" stays though the scenes were drawn');
  }
  const scroll = await page.evaluate(() => {
    const panel = document.querySelector('.processing-panel');
    return panel ? panel.scrollWidth > panel.clientWidth + 1 : false;
  });
  if (scroll) problems.push('the panel scrolls sideways');
  await context.close();
  return {
    name,
    problems,
    detail: `${seen.mosaicProbes.length} mosaic probes, ${seen.mosaicTiles.length} mosaic tiles, ${seen.itemProbes.length} scene probes, ${seen.statistics.length} statistics, ${((Date.now() - started) / 1000).toFixed(1)} s`,
  };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const scenario of ['cold', 'refused']) {
        const result = await check(browser, theme, viewport, scenario);
        failed += result.problems.length > 0 ? 1 : 0;
        console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name} — ${result.detail}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
      }
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
