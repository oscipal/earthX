// A layer recovers by itself from a restart of the services (UI-08, Otto, 16.11.2026), in a real browser, Otto's way:
//   1. a job of today stands in the list of jobs (kept in the browser); the page is reloaded while the services are away (`502` from the
//      dev server's proxy for the job API and the tiles);
//   2. the services come back: the job API and the TileJSON answer, the tiles still answer `503` for 2 s (the object store starts last);
//   3. "Add to layers" in the list of jobs: the layer is made while its tiles fail;
//   4. without a reload of the page, every tile that failed is asked again and drawn: the pixel in the middle of the map is the colour of
//      the tiles, and no tile in view stays failed;
//   5. a zoom in loads the tiles of the new level.
// In the light and the dark theme, at 1280 x 800; a screenshot per theme. Without the fix (`tileRetry.ts`) step 4 fails: MapLibre never
// asks again for a tile that failed while it stays in view.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/tile-retry.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-tile-retry');
const THEMES = { light: 'normal', dark: 'tech' };
const JOB = 'AbCdEfGhIjKlMnOpQrSt_-';
const RESULT = 'ZyXwVuTsRqPoNmLkJiHg_-';
const CENTRE = [10.5, 50.5];
const COLOUR = [230, 40, 160];

// A PNG of 256 x 256 px in one colour.
function solid([r, g, b]) {
  const crc = (buf) => {
    let c = ~0;
    for (const byte of buf) {
      c ^= byte;
      for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1));
    }
    return ~c >>> 0;
  };
  const chunk = (type, data) => {
    const head = Buffer.alloc(4);
    head.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const tail = Buffer.alloc(4);
    tail.writeUInt32BE(crc(body));
    return Buffer.concat([head, body, tail]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(256, 0);
  ihdr.writeUInt32BE(256, 4);
  ihdr.set([8, 6, 0, 0, 0], 8);
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 256 }, () => [r, g, b, 255]).flat())]);
  const raw = Buffer.concat(Array.from({ length: 256 }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

async function pixelAt(page, x, y) {
  const png = await page.screenshot({ clip: { x, y, width: 1, height: 1 } });
  let at = 8;
  const data = [];
  while (at < png.length) {
    const length = png.readUInt32BE(at);
    if (png.toString('ascii', at + 4, at + 8) === 'IDAT') data.push(png.subarray(at + 8, at + 8 + length));
    at += 12 + length;
  }
  const raw = zlib.inflateSync(Buffer.concat(data));
  return [raw[1], raw[2], raw[3]];
}

async function run(browser, theme) {
  const problems = [];
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const expires = new Date(Date.now() + 5 * 86_400_000).toISOString();
  await context.addInitScript(({ t, job, expires }) => {
    localStorage.setItem('earthx.theme', t);
    if (!localStorage.getItem('earthx.processing.manager')) {
      localStorage.setItem('earthx.processing.manager', JSON.stringify({ v: 1, jobs: [{ jobID: job, expires, createdAt: new Date().toISOString(), title: 'NDVI today' }], batches: [], groups: [] }));
    }
  }, { t: THEMES[theme], job: JOB, expires });
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  // 'down': everything behind the proxy answers 502; 'starting': the tiles 503; 'up': all answers.
  let services = 'up';
  const tiles = new Map();
  const tile = solid(COLOUR);
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    const tileAt = /\/results\/[^/]+\/tiles\/WebMercatorQuad\/(\d+\/\d+\/\d+)/.exec(url.pathname)?.[1];
    if (services === 'down' && (url.pathname.startsWith('/processing/') || url.pathname.startsWith('/results/'))) return route.fulfill({ status: 502, body: '' });
    if (tileAt) {
      const status = services === 'starting' ? 503 : 200;
      tiles.set(tileAt, [...(tiles.get(tileAt) ?? []), status]);
      return status === 200 ? route.fulfill({ status, contentType: 'image/png', body: tile }) : route.fulfill({ status, body: '' });
    }
    if (url.pathname === `/results/${RESULT}/WebMercatorQuad/tilejson.json`) return json({ bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 19, data_type: 'float32', tiles: [] });
    if (url.pathname.startsWith(`/processing/jobs/${JOB}`)) {
      if (url.pathname.endsWith('/events')) return json({ detail: 'no stream here' }, 404);
      if (url.pathname.endsWith('/results')) {
        const stats = { min: -1, max: 1, mean: 0, stddev: 0.5, count: 100, valid_percent: 100, percentile_2: -0.9, percentile_98: 0.9 };
        return json({ result: { href: '/x', width: 1000, length: 100, properties: { gsd: 10, bands: [{ name: 'NDVI', data_type: 'float32', statistics: stats }] } }, tiles: { href: `/results/${RESULT}/WebMercatorQuad/tilejson.json` } });
      }
      return json({ processID: 'recipe', type: 'process', jobID: JOB, status: 'successful', message: '', progress: 100, created: new Date().toISOString(), expires, links: [] });
    }
    if (url.pathname === '/colormaps') return json({ groups: [] });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');
  // 1. The reload while the services are away.
  services = 'down';
  await page.reload();
  await page.waitForSelector('.maplibregl-canvas');
  await page.waitForTimeout(1500);
  // 2. Back, but the tiles not yet.
  services = 'starting';
  // The map of the page after the reload.
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
  await page.evaluate(([m, centre]) => m.jumpTo({ center: centre, zoom: 12 }), [map, CENTRE]);
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: 'jobs' }));
  const plus = page.locator('button[aria-label="Add to layers: NDVI today"]');
  await plus.waitFor({ timeout: 10000 });
  // 3. "Add to layers" while the tiles fail.
  await plus.click();
  await page.waitForTimeout(1500);
  const failed = [...tiles.entries()].filter(([, answers]) => answers.includes(503)).map(([at]) => at);
  if (failed.length === 0) problems.push('no tile failed while the services were starting: the case was not made');
  services = 'up';
  // 4. No reload: the failed tiles are asked again and drawn.
  await page.waitForTimeout(6000);
  const stillFailed = failed.filter((at) => tiles.get(at).at(-1) !== 200);
  const inView = await page.evaluate(([m]) => {
    const manager = Object.entries(m.style.tileManagers ?? m.style.sourceCaches ?? {}).find(([id]) => id.startsWith('layer-src-'))?.[1];
    return manager ? manager.getIds().map((id) => manager.getTileByID(id)).filter((t) => t.state === 'errored').map((t) => `${t.tileID.canonical.z}/${t.tileID.canonical.x}/${t.tileID.canonical.y}`) : null;
  }, [map]);
  if (stillFailed.length > 0) problems.push(`${stillFailed.length} of ${failed.length} failed tiles were not asked again: ${stillFailed.slice(0, 4).join(', ')}`);
  if (inView && inView.length > 0) problems.push(`tiles in view stay failed: ${inView.slice(0, 4).join(', ')}`);
  const middle = await pixelAt(page, 900, 400);
  if (middle.some((v, i) => Math.abs(v - COLOUR[i]) > 40)) problems.push(`the middle of the map is ${middle}, not the colour of the layer ${COLOUR}`);
  await page.screenshot({ path: path.join(OUT, `tile-retry-${theme}.png`) });
  // 5. A zoom in loads the next level.
  await page.evaluate(([m, centre]) => m.jumpTo({ center: centre, zoom: 13 }), [map, CENTRE]);
  await page.waitForTimeout(2500);
  if (![...tiles.keys()].some((at) => at.startsWith('13/'))) problems.push('no tile of zoom 13 was asked after zooming in');
  console.log(`${theme}: ${failed.length} tiles failed while the services started, ${failed.length - stillFailed.length} drawn again without a reload`);
  await context.close();
  return problems;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failedRuns = 0;
  for (const theme of Object.keys(THEMES)) {
    const problems = await run(browser, theme).catch((error) => [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`]);
    failedRuns += problems.length > 0 ? 1 : 0;
    console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} tile retry, ${theme}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failedRuns ? 1 : 0);
})();
