// The stacking of the view where it falls back to the scenes one by one (NM4-24), in a real browser, on the real
// `mapLayers.ts`: two scenes that overlap completely (A red, B green), ticked in either order, drawn below the first level
// of a mosaic. The scene on top is the same with the mosaic and with the order the tiler gave for a pass without one (A);
// without an order it is the one that was ticked first, as before.
//
//   cd frontend && npm run dev
//   node e2e/fallback-order.cjs        # BASE=http://localhost:5173
//
// Playwright and Chromium are not a dependency of the project (CI does not run this).

const { chromium } = require('playwright');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
let failed = false;
const check = (name, ok, detail) => {
  failed ||= !ok;
  console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${detail ? ` — ${detail}` : ''}`);
};

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

const name = ([r, g, b]) => (r > 200 && g < 60 && b < 60 ? 'A' : g > 200 && r < 60 ? 'B' : r > 200 && b > 200 ? 'empty' : `?${r},${g},${b}`);

(async () => {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  page.on('pageerror', (error) => console.log('pageerror', error.message));
  await page.goto(`${BASE}/e2e/harness.html`);
  await page.evaluate(() => window.h.loaded);
  await page.route('**/collections/**', (route) =>
    route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(route.request().url().includes('/items/A/') ? [255, 0, 0] : [0, 255, 0]) }),
  );
  const top = async (ids, mode) => {
    await page.evaluate(([lon, lat]) => window.h.jump(lon, lat, 6), [10.5, 47.5]);
    await page.evaluate(([ids, mode]) => window.h.overlap(ids, mode), [ids, mode]);
    await page.waitForTimeout(700);
    return name(await page.evaluate(() => window.h.centre()));
  };
  for (const ids of [['A', 'B'], ['B', 'A']]) {
    const label = `ticked ${ids.join(', then ')}`;
    check(`${label}: with the mosaic, A is on top`, (await top(ids, 'mosaic')) === 'A');
    check(`${label}: scene by scene with the order of the tiler, A is on top, the same`, (await top(ids, 'order')) === 'A');
    const none = await top(ids, 'none');
    check(`${label}: scene by scene with no order, the first ticked is on top (as before)`, none === ids[0], none);
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
