// A map layer that loads for a long time (plan M5-30 §8.7, finding of Otto, 13.11.2026: 124 swissALTI3D tiles, "Crop and merge to AOI",
// and the map stayed empty for a very long time), in a real browser with a made-up tiler that is slow the way the real one is: the tiles of the
// mosaic come one after the other, about a second each (CPU-bound, plan §8.6), the tiles of the substitute at once. It fails when
//   1. the loading mark (a symbol, `role="status"`, no text) is in the row of the layer manager before 0.6 s of waiting, or not there after;
//   2. the map is empty (only the background) before the first tile of the mosaic has come: the substitute has to be drawn over level 13;
//   3. the mark is still there when the last tile has come, or the substitute still lies over the mosaic's picture then;
// It prints the times from the click to each step: the selection, the TileJSON, the first and the last tile, the mark.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/layer-loading.cjs              # BASE=http://localhost:5173 TILE_MS=1100 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersSelection, isSelectionTile } = require('./selectionMock.cjs');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-layer-loading');
const TILE_MS = Number(process.env.TILE_MS ?? 1100);
const SUBSTITUTE_MS = 150;
const WEST = 7.40;
const SOUTH = 46.92;
const STEP = 0.013;
const AOI_BOX = [7.43, 46.93, 7.50, 46.99];
const AOI = { type: 'Polygon', coordinates: [[[AOI_BOX[0], AOI_BOX[1]], [AOI_BOX[2], AOI_BOX[1]], [AOI_BOX[2], AOI_BOX[3]], [AOI_BOX[0], AOI_BOX[3]], [AOI_BOX[0], AOI_BOX[1]]]] };
const GREEN = [0, 200, 0];
const BLUE = [0, 0, 255];
const later = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const near = (pixel, colour) => pixel.every((v, i) => Math.abs(v - colour[i]) < 40);

function solid(colour, size = 256) {
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: size }, () => [...colour, 255]).flat())]);
  const chunk = (type, data) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, 'ascii');
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: size }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
}

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


// The colour of the map at the middle of the AOI, which lies on the screen.
async function middleColour(page) {
  const point = await page.evaluate((b) => {
    const el = document.querySelector('.maplibregl-map');
    let fiber = el[Object.keys(el).find((k) => k.startsWith('__reactFiber$'))];
    for (; fiber; fiber = fiber.return) {
      for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
        const held = hook.memoizedState?.current;
        if (held && typeof held.getStyle === 'function') {
          const rect = held.getCanvas().getBoundingClientRect();
          const p = held.project([(b[0] + b[2]) / 2, (b[1] + b[3]) / 2]);
          return [rect.left + p.x, rect.top + p.y];
        }
      }
    }
    return null;
  }, AOI_BOX);
  return point ? pixelAt(page, Math.round(point[0]), Math.round(point[1])) : null;
}

const marks = (page) => page.locator('.layer-row [role="status"][aria-label="Loading the image"]').count();

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  const at = {};
  let t0 = 0;
  const stamp = (name) => { if (!(name in at)) at[name] = Date.now() - t0; };
  let mosaicTiles = 0;
  let mosaicDone = 0;
  let queue = Promise.resolve();
  const green = solid(GREEN, 512);
  const blue = solid(BLUE, 512);
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (answersSelection(route, url)) { stamp('selection'); return; }
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) {
      stamp('tilejson');
      return json({ tilejson: '3.0.0', bounds: [WEST, SOUTH, WEST + 10 * STEP, SOUTH + 7 * STEP], minzoom: 13, maxzoom: 20, 'earthx:order': [] });
    }
    if (isSelectionTile(url.href)) {
      stamp('mosaic tile asked');
      mosaicTiles += 1;
      // One after the other: the reading of a tile is bound by the CPU, and a second tile waits for the first.
      const mine = queue.then(() => later(TILE_MS));
      queue = mine;
      await mine;
      mosaicDone += 1;
      stamp(mosaicDone === 1 ? 'first mosaic tile' : 'next mosaic tile');
      at['last mosaic tile'] = Date.now() - t0;
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: blue });
    }
    if (url.pathname.includes('/overview/tiles/')) {
      stamp('substitute tile asked');
      await later(SUBSTITUTE_MS);
      stamp('first substitute tile');
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: green });
    }
    if (url.pathname.includes('/statistics')) return json({ '1': { min: 400, max: 900, percentile_2: 450, percentile_98: 850, count: 9 } });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');

  await page.evaluate(async ({ aoi, west, south, step }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { LIST } = await import('/src/fixtures/swissalti.ts');
    const items = Array.from({ length: 70 }, (_, i) => {
      const [x, y] = [west + (i % 10) * step, south + Math.floor(i / 10) * step];
      return {
        id: `TILE_${String(i).padStart(3, '0')}`, collection: 'terrain', bbox: [x, y, x + step, y + step],
        geometry: { type: 'Polygon', coordinates: [[[x, y], [x + step, y], [x + step, y + step], [x, y + step], [x, y]]] },
        properties: { datetime: '2021-01-01T00:00:00Z', 'earthx:state': 'latest' },
        assets: { dtm: { href: `https://assets.example.org/${i}.tif`, type: 'image/tiff; application=geotiff; profile=cloud-optimized' } },
      };
    });
    const groups = [{ key: ['latest'], label: 'latest', items }];
    useAppStore.setState({
      datasets: LIST, selectedDatasetIds: ['terrain'], datasetId: 'terrain', openSectionId: 'terrain',
      sections: [{ datasetId: 'terrain', items, groups, notes: [], groupingError: null, origin: 'search', incomplete: false }],
      items, groups, activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: items.map((it) => it.id), resultsOnMap: true,
      focusMode: false, downloaded: {}, layers: [], mosaics: {}, aoi, error: null, notice: null, dock: 'layers',
      flyToView: { center: [7.465, 46.96], zoom: 13.4 },
    });
  }, { aoi: AOI, west: WEST, south: SOUTH, step: STEP });
  await page.waitForTimeout(1500);
  for (const key of ['selection', 'tilejson', 'mosaic tile asked', 'substitute tile asked', 'first substitute tile', 'first mosaic tile']) delete at[key];
  mosaicTiles = 0;
  mosaicDone = 0;

  // "Crop and merge to AOI", then watch the mark and the middle of the AOI every 100 ms until the last tile has come and the map is at rest.
  t0 = Date.now();
  void page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().enterFocus(true));
  const seen = [];
  while (Date.now() - t0 < 4000 + TILE_MS * 6) {
    const [mark, colour] = [await marks(page), await middleColour(page)];
    seen.push({ t: Date.now() - t0, mark, colour });
    if (mosaicTiles > 0 && mosaicDone === mosaicTiles && Date.now() - t0 > 1500 && seen.length > 5 && Date.now() - (at['last mosaic tile'] ?? 0) - t0 > 600 && at['last mosaic tile']) break;
    await later(100);
  }
  await page.screenshot({ path: path.join(OUT, 'after.png') });

  const firstMark = seen.find((s) => s.mark > 0)?.t;
  const markGone = seen.find((s) => firstMark !== undefined && s.t > firstMark && s.mark === 0)?.t;
  const firstPicture = seen.find((s) => s.colour && (near(s.colour, GREEN) || near(s.colour, BLUE)))?.t;
  const last = seen.at(-1);
  const markWhileWaiting = seen.filter((s) => s.t < 600 && s.mark > 0);
  if (markWhileWaiting.length) problems.push(`the mark was there at ${markWhileWaiting[0].t} ms, before 600 ms`);
  if (firstMark === undefined) problems.push('no mark in the layer manager while the mosaic loaded');
  else if (firstMark > 1500) problems.push(`the mark came late, after ${firstMark} ms`);
  if (markGone === undefined) problems.push('the mark did not go');
  const substituteShown = seen.find((s) => s.colour && near(s.colour, GREEN));
  if (!substituteShown) problems.push(`the map showed no picture before the first tile of the mosaic (${at['first mosaic tile']} ms)`);
  else if (substituteShown.t > 1500) problems.push(`the substitute came late, after ${substituteShown.t} ms`);
  if (markGone !== undefined && markGone < (at['last mosaic tile'] ?? 0) - 300) problems.push(`the mark went at ${markGone} ms, before the last tile (${at['last mosaic tile']} ms)`);
  if (!last || !last.colour || !near(last.colour, BLUE)) problems.push(`at the end the middle of the AOI is ${JSON.stringify(last?.colour)}, not the mosaic`);
  if (last && last.mark > 0) problems.push('the mark is still there at the end');
  console.log(JSON.stringify({ ms: at, firstMark, markGone, firstPicture, mosaicTiles }));
  await browser.close();
  console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} layer loading${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(problems.length ? 1 : 0);
})();
