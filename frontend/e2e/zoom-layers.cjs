// Zoom and switch checks of the layers (UI-01a, Otto 25.10.2026), in a real browser, on the real tiler and the real
// `mapLayers.ts`: a job's result is on the map at every zoom and as detailed as the file when zoomed in, and the view
// keeps its picture until the next one has loaded.
//
//   PYTHONPATH=backend python scripts/serve-result-fixture.py --port 8001      # prints the result as JSON on its first line
//   cd frontend && VITE_TILER_PROXY=http://127.0.0.1:8001 npm run dev          # the dev server (5173)
//   FIXTURE='<that JSON>' node e2e/zoom-layers.cjs
//
// BASE=http://localhost:5173  the frontend to check; BASE_OLD=<another dev server on the code before the change> adds
// the same hand-over check there, to show what it fixes. OUT=<directory for the screenshots>.
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const BASE_OLD = process.env.BASE_OLD;
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-zoom-layers');
const FIXTURE = JSON.parse(process.env.FIXTURE ?? '');
const [LON, LAT] = FIXTURE.center;
// What the code before the change drew a result with: rio-tiler's levels of this 3072-pixel file (9 and 13) and one more.
const BEFORE = { minZoom: 9, maxZoom: 14 };

fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail) => {
  results.push({ name, ok, detail });
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
};

// A solid 256-pixel tile.
function solidPng([r, g, b]) {
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 256 }, () => [r, g, b, 255]).flat())]);
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
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: 256 }, () => row)))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

async function open(browser, base, viewport = { width: 800, height: 600 }) {
  const page = await browser.newPage({ viewport });
  page.on('pageerror', (error) => console.log('pageerror', error.message));
  await page.goto(`${base}/e2e/harness.html`);
  await page.evaluate(() => window.h.loaded);
  return page;
}

const shot = (page, name, size = 360) =>
  page.screenshot({
    path: path.join(OUT, `${name}.png`),
    clip: { x: 400 - size / 2, y: 300 - size / 2, width: size, height: size },
  });

// 1. As detailed as the file: zoomed in past the finest level the result used to be asked at, the tiler is asked for
//    the file's own pixels (hard edges), where it used to be a stretched tile (a smooth gradient).
async function detail(browser) {
  const page = await open(browser, BASE);
  const edges = {};
  for (const zoom of [15, 16, 17, 18]) {
    edges[zoom] = {};
    for (const [name, levels] of [['before', BEFORE], ['after', {}]]) {
      await page.evaluate(([id, levels]) => window.h.showResult(id, levels.minZoom, levels.maxZoom), [FIXTURE.result_id, levels]);
      await page.evaluate(([lon, lat, z]) => window.h.jump(lon, lat, z), [LON, LAT, zoom]);
      edges[zoom][name] = await page.evaluate(() => window.h.edges(240));
      await shot(page, `detail-z${zoom}-${name}`);
    }
    const ratio = edges[zoom].after / Math.max(edges[zoom].before, 1e-9);
    check(`detail at zoom ${zoom}`, ratio >= 1.5, `hard pixel edges ${edges[zoom].before.toFixed(4)} -> ${edges[zoom].after.toFixed(4)} (x${ratio.toFixed(1)})`);
  }
  await page.close();
}

// 2. On the map at every zoom, in and out, with tiles that arrive late.
async function sweep(browser) {
  const page = await open(browser, BASE);
  await page.route('**/results/**/tiles/**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 300));
    await route.continue();
  });
  const zooms = [4, 5, 6, 7, 8, 9, 10, 12, 14, 16, 18];
  const path = [...zooms, ...[...zooms].reverse().slice(1)];
  for (const [name, levels] of [['before', BEFORE], ['after', {}]]) {
    await page.evaluate(([id, levels]) => window.h.showResult(id, levels.minZoom, levels.maxZoom), [FIXTURE.result_id, levels]);
    await page.evaluate(([lon, lat]) => window.h.jump(lon, lat, 12), [LON, LAT]);
    const empty = [];
    for (const zoom of path) {
      await page.evaluate(([lon, lat, z]) => window.h.jump(lon, lat, z), [LON, LAT, zoom]);
      if (await page.evaluate(() => window.h.isEmpty())) empty.push(zoom);
      if (name === 'after' && zoom === 5) await shot(page, 'sweep-z5-after', 360);
    }
    if (name === 'after') check('result on the map at every zoom, in and out', empty.length === 0, empty.length ? `empty at ${empty}` : `${path.length} steps`);
    else console.log(`     (before the change: empty at zoom ${[...new Set(empty)]})`);
  }
  await page.close();
}

// 3. The view keeps its picture until the next one has loaded: the browse preview (blue, quick) goes over to the full
//    resolution (green, 700 ms late) with no frame of the background (magenta) between.
async function handOver(browser, base, label, mustHold) {
  const page = await open(browser, base);
  await page.route('**/collections/**', async (route) => {
    const full = !route.request().url().includes('rescale');
    if (full) await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(full ? [0, 255, 0] : [0, 0, 255]) });
  });
  const name = ([r, g, b]) => (r > 200 && b > 200 ? 'empty' : g > 200 ? 'full' : b > 200 ? 'browse' : `?${r},${g},${b}`);
  await page.evaluate(() => window.h.jump(10.5, 47.5, 9));
  await page.evaluate(() => window.h.browse());
  const frames = [];
  const watch = async (ms) => {
    const until = Date.now() + ms;
    while (Date.now() < until) {
      frames.push(name(await page.evaluate(() => window.h.centre())));
      await page.waitForTimeout(30);
    }
  };
  await watch(800);
  const before = frames.length;
  await page.evaluate(() => window.h.full());
  await watch(1800);
  const after = frames.slice(before);
  const sequence = after.filter((frame, i) => i === 0 || frame !== after[i - 1]).join(' > ');
  await shot(page, `handover-${label}`, 200);
  const blank = after.filter((frame) => frame === 'empty').length;
  if (mustHold) {
    check(`hand-over ${label}: no frame of the background between the pictures`, blank === 0 && after.at(-1) === 'full', sequence);
  } else {
    console.log(`     (${label}: ${blank} of ${after.length} frames empty, ${sequence})`);
  }
  await page.close();
}

// 4. A layer pinned from a scene with a quicklook, whose tiles start at z8 and load late (700 ms): zoomed in and out in
//    jumps, there is a picture (the quicklook, blue, or the tiles, green) right after every jump, never the background.
async function scene(browser, quicklook = true) {
  const page = await open(browser, BASE);
  await page.route('https://example.invalid/**', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: solidPng([0, 0, 255]) }),
  );
  await page.route('**/collections/**', async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 700));
    await route.fulfill({ status: 200, contentType: 'image/png', body: solidPng([0, 255, 0]) });
  });
  const kinds = await page.evaluate((quicklook) => window.h.pinScene(quicklook), quicklook);
  if (quicklook) check('the pinned scene layer holds its quicklook under its tiles', kinds.join() === 'image,raster', kinds.join());
  const [lon, lat] = [9.33, 47.36];
  await page.evaluate(([lon, lat]) => window.h.jump(lon, lat, 4), [lon, lat]);
  await page.waitForTimeout(400);
  const empty = [];
  const zooms = [4, 6, 8, 9, 12, 16, 12, 9, 8, 6, 4, 3, 5, 14, 5];
  for (const zoom of zooms) {
    await page.evaluate(([lon, lat, z]) => window.h.jump(lon, lat, z), [lon, lat, zoom]);
    await page.waitForTimeout(60);
    if (await page.evaluate(() => window.h.isEmpty())) empty.push(zoom);
    if (zoom === 4) await shot(page, 'scene-z4', 200);
  }
  if (quicklook) check('scene layer: a picture after every jump in and out', empty.length === 0, empty.length ? `empty after jumping to ${empty}` : `${zooms.length} jumps`);
  else console.log(`     (the same layer without the quicklook: empty after jumping to ${[...new Set(empty)]})`);
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  await detail(browser);
  await sweep(browser);
  await scene(browser);
  await scene(browser, false);
  await handOver(browser, BASE, 'after', true);
  if (BASE_OLD) await handOver(browser, BASE_OLD, 'before', false);
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(results.every((r) => r.ok) ? 0 : 1);
})();
