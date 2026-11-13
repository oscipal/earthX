// The loading mark on the map (plan M5-30 §8.7, Otto, 13.11.2026), in a real browser with a made-up tiler whose tiles come slowly, one after
// the other (the way a mosaic of 124 scenes does). A layer that loads for longer than 0.6 s shows ONE spinner on the map, a symbol without
// text, above the buttons at the bottom right, with the layer manager CLOSED. The check fails when
//   1. the mark is missing 0.6 s after the first load began (the click on "Crop and merge to AOI"), or is there before 0.6 s;
//   2. the mark is missing 0.6 s after a zoom in, or after a pan, each of which asks the tiler for new tiles;
//   3. the mark is still there when the tiles of that step have come, or has text, or lies over a button of the map or outside the window;
//   4. a row of the layer manager shows a mark here: the manager is closed (its rows are in the page but hidden), so the mark on the map is the only one seen.
// It prints the times from each step to the mark and its going.
//
//   cd frontend && npm run dev &            # a FRESH dev server for each run; no backend is needed
//   node e2e/map-loading.cjs                # BASE=http://localhost:5173 TILE_MS=1100 OUT=<directory for the screenshots>
//   MANAGER=open node e2e/map-loading.cjs   # the same with the layer manager open: the mark in its row has to come at each step too
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersSelection, isSelectionTile } = require('./selectionMock.cjs');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-map-loading');
const TILE_MS = Number(process.env.TILE_MS ?? 1100);
const AFTER_MS = 600;
// MANAGER=open opens the layer manager: the mark in the row of "Search results" has to be there as well, at each step.
const MANAGER_OPEN = process.env.MANAGER === 'open';
const WEST = 7.4;
const SOUTH = 46.92;
const STEP = 0.013;
const AOI_BOX = [7.43, 46.93, 7.5, 46.99];
const AOI = { type: 'Polygon', coordinates: [[[AOI_BOX[0], AOI_BOX[1]], [AOI_BOX[2], AOI_BOX[1]], [AOI_BOX[2], AOI_BOX[3]], [AOI_BOX[0], AOI_BOX[3]], [AOI_BOX[0], AOI_BOX[1]]]] };
const later = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function solid(colour, size = 512) {
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

// Runs `fn(map, arg)` in the page on the MapLibre map of the app, found through React's fibre of its container.
const onMap = (page, fn, arg) =>
  page.evaluate(
    ({ source, arg: given }) => {
      const el = document.querySelector('.maplibregl-map');
      let fiber = el[Object.keys(el).find((k) => k.startsWith('__reactFiber$'))];
      for (; fiber; fiber = fiber.return) {
        for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
          const held = hook.memoizedState?.current;
          if (held && typeof held.getStyle === 'function') return new Function('map', 'arg', `return (${source})(map, arg)`)(held, given);
        }
      }
      return null;
    },
    { source: fn.toString(), arg },
  );

const MARK = '.map-loading[role="status"]';
const rowMarks = (page) => page.locator('.layer-row [role="status"]:visible').count();
// The marks in the rows of the manager that are in the page, seen or not: a closed manager still has them, in a hidden panel.
const rowMarksInPage = (page) => page.locator('.layer-row [role="status"]').count();
const layerManagerOpen = (page) => page.locator('.layer-row:visible').count();

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  let asked = 0;
  let came = 0;
  let queue = Promise.resolve();
  const blue = solid([0, 0, 255]);
  const green = solid([0, 200, 0]);
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (answersSelection(route, url)) return;
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) {
      return json({ tilejson: '3.0.0', bounds: [WEST, SOUTH, WEST + 10 * STEP, SOUTH + 7 * STEP], minzoom: 13, maxzoom: 20, 'earthx:order': [] });
    }
    if (isSelectionTile(url.href)) {
      asked += 1;
      const mine = queue.then(() => later(TILE_MS));
      queue = mine;
      await mine;
      came += 1;
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: blue });
    }
    if (url.pathname.includes('/overview/tiles/')) {
      await later(100);
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: green });
    }
    if (url.pathname.includes('/statistics')) return json({ '1': { min: 400, max: 900, percentile_2: 450, percentile_98: 850, count: 9 } });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');

  await page.evaluate(async ({ aoi, west, south, step, open }) => {
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
    // The layer manager is closed (`dock: null`): its rows are hidden, so no row mark is seen either.
    useAppStore.setState({
      datasets: LIST, selectedDatasetIds: ['terrain'], datasetId: 'terrain', openSectionId: 'terrain',
      sections: [{ datasetId: 'terrain', items, groups, notes: [], groupingError: null, origin: 'search', incomplete: false }],
      items, groups, activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: items.map((it) => it.id), resultsOnMap: true,
      focusMode: false, downloaded: {}, layers: [], mosaics: {}, aoi, error: null, notice: null, dock: open ? 'layers' : null,
      flyToView: { center: [7.465, 46.96], zoom: 13.4 },
    });
  }, { aoi: AOI, west: WEST, south: SOUTH, step: STEP, open: MANAGER_OPEN });
  await page.waitForTimeout(1500);
  // Whatever the map was still loading when the page came up (the first run on a dev server compiles its files) ends before the steps start.
  const loadingNow = () => page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().mapLoading.join(','));
  for (const until = Date.now() + 8000; Date.now() < until && ((await loadingNow()) !== '' || (await page.locator(MARK).count()) > 0); ) await later(100);
  await later(1000);
  console.log(`before the first step: loading rows [${await loadingNow()}], mark ${await page.locator(MARK).count()}`);
  if (((await layerManagerOpen(page)) > 0) !== MANAGER_OPEN) problems.push(`the layer manager is ${MANAGER_OPEN ? 'closed' : 'open'}, the check is for it ${MANAGER_OPEN ? 'open' : 'closed'}`);

  // One step: `act` is what the user does; watch the mark every 50 ms until the tiles it asked for are all in and the map is at rest.
  const step = async (name, act, { expectMark = true } = {}) => {
    asked = 0;
    came = 0;
    const t0 = Date.now();
    await act();
    const seen = [];
    let lastCame = 0;
    for (;;) {
      const [mark, rows, inPage] = [await page.locator(MARK).count(), await rowMarks(page), await rowMarksInPage(page)];
      const now = Date.now() - t0;
      seen.push({ t: now, mark, rows, inPage });
      if (came !== lastCame) lastCame = came;
      const settled = asked > 0 && came === asked && now > 1000;
      const idle = !settled && asked === 0 && now > 2500;
      if ((settled && seen.filter((s) => s.t > now - 700).every((s) => s.mark === 0) && now > 3000) || idle || now > 20000) break;
      if (settled && now > 1500 && seen.at(-1).mark === 0 && seen.some((s) => s.mark > 0)) break;
      await later(50);
    }
    const first = seen.find((s) => s.mark > 0)?.t;
    const gone = seen.find((s) => first !== undefined && s.t > first && s.mark === 0)?.t;
    console.log(`${name}: tiles asked ${asked}, came ${came}; mark after ${first ?? '-'} ms, gone after ${gone ?? '-'} ms; row marks in the page ${seen.some((s) => s.inPage > 0) ? 'yes' : 'no'}, seen ${seen.some((s) => s.rows > 0) ? 'yes' : 'no'}`);
    if (!expectMark) return { first, gone };
    if (asked === 0) problems.push(`${name}: the map asked for no tile, there is nothing to load`);
    if (first === undefined) problems.push(`${name}: no mark on the map while tiles loaded for ${asked * TILE_MS} ms`);
    else {
      if (first < AFTER_MS - 120) problems.push(`${name}: the mark came after ${first} ms, before the 0.6 s`);
      if (first > AFTER_MS + 900) problems.push(`${name}: the mark came late, after ${first} ms`);
    }
    if (gone === undefined) problems.push(`${name}: the mark did not go`);
    if (!MANAGER_OPEN && seen.some((s) => s.rows > 0)) problems.push(`${name}: a row of the layer manager has a mark, the manager is closed`);
    const rowFirst = seen.find((s) => s.rows > 0)?.t;
    if (MANAGER_OPEN) {
      console.log(`  row mark after ${rowFirst ?? '-'} ms`);
      if (rowFirst === undefined) problems.push(`${name}: no mark in the row of "Search results" with the manager open`);
    }
    const last = seen.at(-1);
    if (last.mark > 0) problems.push(`${name}: the mark is still there at the end`);
    return { first, gone };
  };

  // Where the mark stands: inside the window, not over a button.
  const place = async (name) => {
    const box = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const rect = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
      return { mark: rect(el), text: el.textContent, buttons: [...document.querySelectorAll('.map-controls button')].map(rect), window: [innerWidth, innerHeight] };
    }, MARK);
    if (!box) return;
    if (box.text.trim() !== '') problems.push(`${name}: the mark has text: ${JSON.stringify(box.text)}`);
    const m = box.mark;
    if (m.x < 0 || m.y < 0 || m.x + m.w > box.window[0] || m.y + m.h > box.window[1]) problems.push(`${name}: the mark lies outside the window`);
    for (const b of box.buttons) {
      if (m.x < b.x + b.w && m.x + m.w > b.x && m.y < b.y + b.h && m.y + m.h > b.y) problems.push(`${name}: the mark lies over a button of the map`);
    }
  };

  // 1. The first load: "Crop and merge to AOI".
  await step('first load', async () => { void page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().enterFocus(true)); });
  // The next steps start from a map at rest with the picture drawn.
  await later(500);
  await page.screenshot({ path: path.join(OUT, 'after-first-load.png') });

  // 2. A zoom in by one level: the tiles of the new level are not in the map yet.
  await step('zoom in', async () => {
    await onMap(page, (map) => map.zoomTo(map.getZoom() + 1, { duration: 0 }));
  });
  await later(500);
  // 3. A pan: new tiles at the edge.
  await step('pan', async () => {
    await onMap(page, (map) => map.panBy([420, 0], { duration: 0 }));
  });
  await later(500);
  // 4. A zoom out, to a level whose tiles are all there: no mark is wanted, nothing loads. (A level that was loaded before is in the cache.)
  asked = 0;
  await onMap(page, (map) => map.zoomTo(map.getZoom() - 1, { duration: 0 }));
  await later(AFTER_MS + 600);
  if (asked === 0 && (await page.locator(MARK).count()) > 0) problems.push('zoom out onto tiles that are there: the mark shows with nothing loading');

  // Where the mark stands, seen with a slow tile in flight.
  asked = 0;
  await onMap(page, (map) => map.zoomTo(map.getZoom() + 2, { duration: 0 }));
  const deadline = Date.now() + 4000;
  while (Date.now() < deadline && (await page.locator(MARK).count()) === 0) await later(50);
  await page.screenshot({ path: path.join(OUT, 'mark-on-map.png') });
  if ((await page.locator(MARK).count()) === 0) problems.push('placement: no mark to look at');
  await place('placement');

  await browser.close();
  console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} map loading mark${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(problems.length ? 1 : 0);
})();
