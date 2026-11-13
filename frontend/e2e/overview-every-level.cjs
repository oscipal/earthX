// No dataset loses its picture when zoomed out (plan M5-30b §8.8, finding of 13.11.2026), in a real browser, on the real
// `mapLayers.ts` and the real AOI clip, with a made-up tiler: swissALTI3D (released from z13) in "Crop and merge to AOI" shows
// its mosaic from z13 and the picture of its substitute below, and the map zooms out step by step from z14 to z0. It fails when
//   1. a whole level has no tile of the layer asked for and answered (the substitute below z12.5, the mosaic from there on);
//   2. a step, whole or half level, draws nothing where the area cropped to lies (only the background colour, magenta, there);
//   3. a request is not for the route of its level: the mosaic below z12.5, the substitute from there on.
// Once for an area around a city (requests at every step; the picture is checked from z5, where the area is more than a pixel) and
// once for a region as large as the dataset (the picture at every step, z0 included).
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the tiles are made up here
//   node e2e/overview-every-level.cjs       # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-overview-every-level');
const CITY = { type: 'Polygon', coordinates: [[[8.3, 47.2], [8.8, 47.2], [8.8, 47.6], [8.3, 47.6], [8.3, 47.2]]] };
const REGION = { type: 'Polygon', coordinates: [[[5.95, 45.75], [10.45, 45.75], [10.45, 47.75], [5.95, 47.75], [5.95, 45.75]]] };
const AREAS = {
  city: { aoi: CITY, centre: [8.55, 47.4], pictureFrom: 5 },
  region: { aoi: REGION, centre: [8.2, 46.75], pictureFrom: 0 },
};
const EMPTY = [255, 0, 255];
// The levels the map is zoomed out through: whole and half levels from 14 to 0, as a person's wheel gives.
const ZOOMS = Array.from({ length: 29 }, (_, i) => 14 - i / 2);
// From this map zoom a 512-px mosaic of level 13 is drawn and the substitute steps aside (`tileSize.ts`, `overviewSubstitute.ts`).
const MOSAIC_FROM = 12.5;

// A solid opaque green tile of 512 px, as the tiler's tile of a mosaic and of a substitute is.
function solidPng(size = 512) {
  const chunk = (type, data) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, 'ascii');
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, crc]);
  };
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: size }, () => [0, 200, 0, 255]).flat())]);
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', header),
    chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: size }, () => row)))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}

async function run(browser, name, { aoi, centre, pictureFrom }, results) {
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  const problems = [];
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  const tile = solidPng();
  let asked = [];
  await page.route('**/collections/terrain/**', (route) => {
    const url = new URL(route.request().url());
    const match = /\/collections\/terrain\/(overview|mosaic\/[0-9a-f]{32})\/tiles\/WebMercatorQuad\/(\d+)\/\d+\/\d+/.exec(url.pathname);
    if (!match) return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
    asked.push({ route: match[1] === 'overview' ? 'substitute' : 'mosaic', z: Number(match[2]) });
    return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: tile });
  });
  await page.goto(`${BASE}/e2e/harness.html`);
  await page.evaluate(() => window.h.loaded);
  await page.evaluate((a) => window.h.swissCrop(a), aoi);

  for (const zoom of ZOOMS) {
    asked = [];
    await page.evaluate(([lon, lat, z]) => window.h.jump(lon, lat, z), [...centre, zoom]);
    await page.waitForTimeout(150);
    const label = `z${zoom}`;
    const wanted = zoom < MOSAIC_FROM ? 'substitute' : 'mosaic';
    // A tile loaded at the step before (the same level at a half zoom) is not asked for again: only at a whole level is a request certain.
    if (Number.isInteger(zoom) && asked.every((request) => request.route !== wanted)) problems.push(`${label}: no tile of the ${wanted} was asked for`);
    const wrong = asked.filter((request) => request.route !== wanted);
    if (wrong.length) problems.push(`${label}: tiles of the ${wrong[0].route} were asked for where the ${wanted} draws`);
    if (zoom >= pictureFrom) {
      const block = await page.evaluate(([lon, lat]) => window.h.blockAt(lon, lat), centre);
      if (block.every((pixel) => pixel.every((v, i) => v === EMPTY[i]))) problems.push(`${label}: nothing is drawn where the area lies`);
    }
    if ([0, 4, 8, 12, 14].includes(zoom)) await page.screenshot({ path: path.join(OUT, `${name}-z${zoom}.png`) });
  }
  results.push({ name, problems });
  await page.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  for (const [name, area] of Object.entries(AREAS)) await run(browser, name, area, results);
  await browser.close();
  for (const { name, problems } of results) console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ` (${ZOOMS.length} levels, z14 to z0)`}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
