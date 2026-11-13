// A pass of many scenes after "Crop and merge to AOI" (Otto's browser check of swissALTI3D, 10.11.2026: the map stayed empty, even
// at zoom 14, until it was zoomed in and out again), in a real browser with made-up tiles of 1 km and no backend. Since the
// selection of a mosaic (M5-30b part 3, `adr/0032` §10.2) a pass is one mosaic up to what a selection takes (2000 scenes), so:
//   1. Without a move of the map, the tiles are asked for and drawn: the map is not empty.
//   2. Up to 2000 scenes the pass is one selection: no tile of a single scene and no `?item=` in any URL, whatever the number
//      of scenes. Over 2000 (SCENES=2100) or where the tiler refuses the mosaic (MOSAIC=refuse) the scenes are drawn one by
//      one, the 40 that lie in the view first, and their order comes from `/scene-order`.
// 70 scenes of a dataset released from z14 like swissALTI3D; light and dark theme, a wide and a narrow window.
//
// In the cloud session of 10.11.2026 this did not reproduce Otto's empty map (DS-04 plan §14.6): it runs green there, with
// made-up and with real metadata of swissALTI3D, at z12.5 and z14.2 and with slow answers. It stays as the check of the flow.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/many-scenes.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersSelection, isSelectionTile, scenesOfSelection } = require('./selectionMock.cjs');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-many-scenes');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const SCENES = Number(process.env.SCENES ?? 70);
// Where the map stands when "Crop and merge to AOI" is pressed, and the zoom it is taken to afterwards (as after a search
// over the AOI, below the z14 the dataset starts at, and then zoomed in once).
const START_ZOOM = Number(process.env.START_ZOOM ?? 12.5);
const THEN_ZOOM = Number(process.env.THEN_ZOOM ?? 14.2);
// 10 × 7 tiles of about 1 km near Bern; the AOI covers the middle of them.
const WEST = 7.40;
const SOUTH = 46.92;
const STEP = 0.013;
const AOI_BOX = [7.43, 46.93, 7.50, 46.99];
const AOI = { type: 'Polygon', coordinates: [[[AOI_BOX[0], AOI_BOX[1]], [AOI_BOX[2], AOI_BOX[1]], [AOI_BOX[2], AOI_BOX[3]], [AOI_BOX[0], AOI_BOX[3]], [AOI_BOX[0], AOI_BOX[1]]]] };
// The times the tiler took in Otto's check (about 200 ms a tile); the order and the statistics come later than the first tiles.
const DELAY = {
  tile: Number(process.env.TILE_MS ?? 200),
  order: Number(process.env.ORDER_MS ?? 600),
  statistics: Number(process.env.STATS_MS ?? 400),
  tilejson: Number(process.env.TILEJSON_MS ?? 800),
};
// The tiler gives the mosaic (`ok`) or refuses it (`refuse`), and the view falls back to drawing the scenes one by one.
const MOSAIC = process.env.MOSAIC ?? 'ok';
const later = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
// A tile of pure blue of 256 px: the clip to the AOI (`aoiClip.ts`) works in the pixels of the image it is given, so a tile of one pixel
// would be cut at the edge of the AOI into a pixel of half the colour, and a mosaic tile, which is larger than a scene's, shows it.
const PNG = (() => {
  const zlib = require('node:zlib');
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 256 }, () => [0, 0, 255, 255]).flat())]);
  const chunk = (type, data) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, 'ascii');
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(256, 0);
  header.writeUInt32BE(256, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: 256 }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
})();

// The colour of one pixel of the page, read from a screenshot of it (a PNG of 1 × 1, RGB or RGBA, one IDAT chunk).
async function pixelAt(page, x, y) {
  const png = await page.screenshot({ clip: { x, y, width: 1, height: 1 } });
  let at = 8;
  let colourType = 2;
  const data = [];
  while (at < png.length) {
    const length = png.readUInt32BE(at);
    const type = png.toString('ascii', at + 4, at + 8);
    if (type === 'IHDR') colourType = png[at + 8 + 9];
    if (type === 'IDAT') data.push(png.subarray(at + 8, at + 8 + length));
    at += 12 + length;
  }
  const raw = require('node:zlib').inflateSync(Buffer.concat(data));
  return colourType === 6 || colourType === 2 ? [raw[1], raw[2], raw[3]] : [raw[1], raw[1], raw[1]];
}

// Whether the map draws the made-up tiles (pure blue) at the points of a 7 × 7 grid over the AOI that are on the screen.
async function blueInAoi(page, map, box) {
  const points = await page.evaluate(([m, b]) => {
    const rect = m.getCanvas().getBoundingClientRect();
    const at = (lon, lat) => { const p = m.project([lon, lat]); return [rect.left + p.x, rect.top + p.y]; };
    const [w, s, e, n] = b;
    // On the canvas and not under a panel or a sheet that lies over it.
    const inside = (x, y) => x > rect.left + 2 && x < rect.right - 2 && y > rect.top + 2 && y < rect.bottom - 2 && document.elementFromPoint(x, y) === m.getCanvas();
    const grid = [];
    for (let i = 1; i <= 7; i++) for (let j = 1; j <= 7; j++) grid.push([w + ((e - w) * i) / 8, s + ((n - s) * j) / 8]);
    return grid.map(([lon, lat]) => at(lon, lat)).filter(([x, y]) => inside(x, y));
  }, [map, box]);
  const colours = [];
  for (const [x, y] of points) colours.push(await pixelAt(page, Math.round(x), Math.round(y)));
  return { points: points.length, blue: colours.filter(([r, g, b]) => b > 150 && r < 80 && g < 80).length, colours };
}

async function run(browser, theme, viewport, results) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  const consoleErrors = [];
  page.on('console', (message) => message.type() === 'error' && consoleErrors.push(message.text().slice(0, process.env.FULL ? 4000 : 200)));
  const asked = { scene: 0, mosaic: 0, order: 0, tilejson: 0, item: 0 };
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.searchParams.has('item')) asked.item += 1;
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (url.pathname.endsWith('/scene-order')) {
      asked.order += 1;
      await later(DELAY.order);
      const ids = JSON.parse(route.request().postData() ?? '{}').items ?? [];
      return json({ order: [...ids].sort() });
    }
    if (answersSelection(route, url)) return;
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) {
      asked.tilejson += 1;
      await later(DELAY.tilejson);
      if (MOSAIC === 'refuse') return json({ detail: 'a made-up refusal' }, 422);
      return json({ tilejson: '3.0.0', bounds: [WEST, SOUTH, WEST + 10 * STEP, SOUTH + 7 * STEP], minzoom: 14, maxzoom: 20, 'earthx:order': scenesOfSelection(url) });
    }
    if (isSelectionTile(url.href)) {
      asked.mosaic += 1;
      await later(DELAY.tile);
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    }
    if (url.pathname.includes('/statistics')) await later(DELAY.statistics);
    if (url.pathname.includes('/statistics')) return json({ '1': { min: 400, max: 900, percentile_2: 450, percentile_98: 850, count: 9 } });
    if (url.pathname.includes('/tiles/')) {
      asked.scene += 1;
      await later(DELAY.tile);
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');

  await page.evaluate(async ({ scenes, west, south, step, aoi, startZoom }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const items = Array.from({ length: scenes }, (_, i) => {
      const [x, y] = [west + (i % 10) * step, south + Math.floor(i / 10) * step];
      const bbox = [x, y, x + step, y + step];
      return {
        id: `TILE_${String(i).padStart(3, '0')}`, collection: 'terrain', bbox,
        geometry: { type: 'Polygon', coordinates: [[[x, y], [x + step, y], [x + step, y + step], [x, y + step], [x, y]]] },
        properties: { datetime: '2021-01-01T00:00:00Z', 'earthx:state': 'latest' },
        assets: { dtm: { href: `https://assets.example.org/${i}.tif`, type: COG } },
      };
    });
    const collection = {
      id: 'terrain', title: 'Terrain model', 'earthx:format': 'cog',
      'earthx:capabilities': { roi: true, time_range: false, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'Height', assets: ['dtm'], rescale: [[400, 900]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['earthx:state'], min_zoom: 14, max_zoom: 20, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['earthx:state'] },
      'earthx:license_flags': { tier: 'processing' },
      extent: { spatial: { bbox: [[5.9, 45.8, 10.5, 47.8]] }, temporal: { interval: [['2019-01-01T00:00:00Z', '2023-12-31T00:00:00Z']] } },
    };
    const groups = [{ key: ['latest'], label: 'latest', items }];
    useAppStore.setState({
      datasets: datasetsFrom([collection]), selectedDatasetIds: ['terrain'], datasetId: 'terrain', openSectionId: 'terrain',
      sections: [{ datasetId: 'terrain', items, groups, notes: [] }], items, groups, activeGroupIndex: 0, expandedGroupIndex: 0,
      selectedIds: items.map((it) => it.id), resultsOnMap: true, focusMode: false, downloaded: {}, layers: [], mosaics: {}, aoi,
      error: null, notice: null, dock: null, flyToView: { center: [7.465, 46.96], zoom: startZoom },
    });
  }, { scenes: SCENES, west: WEST, south: SOUTH, step: STEP, aoi: AOI, startZoom: START_ZOOM });
  await page.waitForTimeout(1500);

  // "Crop and merge to AOI", and then the map is left alone.
  const before = { ...asked };
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().enterFocus(true));
  const notice = await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().notice);
  // The preview of the results asks for its tiles in a queue (six at a time per host, each answered after a delay): the view is settled
  // when no tile of a single scene has been asked for during 2 s, not after a fixed time. A page that paints more per frame (a spinner
  // that turns, in the software renderer of this session) drains the queue more slowly, and a fixed 3 s counted the rest as the view's.
  for (let quiet = Date.now(), seen = asked.scene, until = Date.now() + 20000; Date.now() - quiet < 2000 && Date.now() < until; await later(200)) {
    if (asked.scene !== seen) { seen = asked.scene; quiet = Date.now(); }
  }
  // What was asked for before the view settled belongs to the preview of the results, which the crop takes off the map.
  const settled = { ...asked };
  await page.evaluate(async (zoom) => (await import('/src/store.ts')).useAppStore.setState({ flyToView: { center: [7.465, 46.96], zoom } }), THEN_ZOOM);
  await page.waitForTimeout(3000);
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
  const drawn = await page.evaluate((m) => ({ layers: m.getStyle().layers.filter((layer) => /^[mn]-tiles-lyr-/.test(layer.id)).length, zoom: m.getZoom() }), map);
  const seen = await blueInAoi(page, map, AOI_BOX);
  if (seen.points === 0) problems.push('the AOI is not on the screen');
  if (seen.blue < seen.points) problems.push(`the map shows the scenes at ${seen.blue} of ${seen.points} places in the AOI (${JSON.stringify(seen.colours)})`);
  const tilesAsked = asked.scene - before.scene;
  const oneMosaic = SCENES <= 2000;
  if (!oneMosaic && asked.tilejson - before.tilejson > 0) problems.push('a mosaic was asked for over 2000 scenes');
  if (notice && MOSAIC === 'ok') problems.push(`the note says ${JSON.stringify(notice)}`);
  if (asked.item > 0) problems.push(`${asked.item} requests name the scenes in the URL`);
  if (oneMosaic && MOSAIC === 'ok' && asked.scene - settled.scene > 0) problems.push(`${asked.scene - settled.scene} tiles of single scenes were asked for although the pass is one mosaic`);
  const drawnTiles = tilesAsked + (oneMosaic && MOSAIC === 'ok' ? asked.mosaic - before.mosaic : 0);
  if (drawnTiles === 0) problems.push(`nothing was asked for to draw at zoom ${drawn.zoom.toFixed(1)} (${drawn.layers} layers)`);
  // The basemaps come from hosts a cloud session cannot reach (as in `map-gl6.cjs`); their failures are not judged here.
  for (const text of new Set(consoleErrors)) if (!/404|Failed to load resource|arcgisonline|openfreemap|AJAXError: Failed to fetch \(0\)/.test(text)) problems.push(`the console says: ${text}`);
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });

  results.push({ name, problems });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) await run(browser, theme, viewport, results);
  await browser.close();
  for (const { name, problems } of results) console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
