// The picture that stays while the cropped view loads follows the AOI (NM4-25), in a real browser, on the real
// `mapLayers.ts` and the real AOI-clip protocol: from the browse preview of a scene (blue, quick) to "Crop to AOI" whose
// tiles come late (green, 2.5 s). Inside the AOI there is a picture at every moment (blue, then green, never the
// background, magenta); outside it, in the scene, the whole-scene preview is gone at once, not when the tiles are in.
//
//   cd frontend && npm run dev                       # the dev server (5173)
//   node e2e/clip-retired.cjs
//
// BASE=http://localhost:5173  the frontend to check; BASE_OLD=<a dev server on the code before the change> adds the same
// run there, to show what it fixes. Playwright and Chromium are not a dependency of the project (CI does not run this).

const { chromium } = require('playwright');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const BASE_OLD = process.env.BASE_OLD;
const results = [];
const check = (name, ok, detail) => {
  results.push(ok);
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

const name = ([r, g, b]) => (r > 200 && b > 200 ? 'empty' : g > 200 ? 'full' : b > 200 ? 'browse' : `?${r},${g},${b}`);

async function run(browser, base, label, mustHold) {
  const page = await browser.newPage({ viewport: { width: 800, height: 600 } });
  page.on('pageerror', (error) => console.log('pageerror', error.message));
  await page.goto(`${base}/e2e/harness.html`);
  await page.evaluate(() => window.h.loaded);
  await page.route('**/collections/**', async (route) => {
    const full = !route.request().url().includes('rescale');
    if (full) await new Promise((resolve) => setTimeout(resolve, 2500));
    await route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(full ? [0, 255, 0] : [0, 0, 255]) });
  });
  await page.evaluate(() => window.h.jump(10.5, 47.5, 9));
  await page.evaluate(() => window.h.browse());
  await page.waitForTimeout(600);
  // In the scene, outside the AOI (0.33 degrees east of the middle), and in the middle of the AOI.
  const outside = [140, 0];
  const inside = [0, 0];
  const before = [name(await page.evaluate((p) => window.h.pixelAt(...p), outside)), name(await page.evaluate((p) => window.h.pixelAt(...p), inside))];
  check(`${label}: the browse preview covers the scene before`, before.join() === 'browse,browse', before.join());

  await page.evaluate(() => window.h.fullCropped());
  const seen = { outside: [], inside: [] };
  const until = Date.now() + 3500;
  const started = Date.now();
  let outsideGoneAt = null;
  while (Date.now() < until) {
    const o = name(await page.evaluate((p) => window.h.pixelAt(...p), outside));
    const i = name(await page.evaluate((p) => window.h.pixelAt(...p), inside));
    seen.outside.push(o);
    seen.inside.push(i);
    if (outsideGoneAt === null && o !== 'browse') outsideGoneAt = Date.now() - started;
    await page.waitForTimeout(40);
  }
  const sequence = (frames) => frames.filter((f, k) => k === 0 || f !== frames[k - 1]).join(' > ');
  console.log(`     ${label}: outside ${sequence(seen.outside)} (browse gone after ${outsideGoneAt} ms), inside ${sequence(seen.inside)}`);
  if (mustHold) {
    check(`${label}: outside the AOI the preview is gone long before the tiles are in`, outsideGoneAt !== null && outsideGoneAt < 1200, `${outsideGoneAt} ms`);
    check(`${label}: outside the AOI nothing else is drawn meanwhile`, seen.outside.slice(0, 3).every((f) => f !== 'full') && !seen.outside.includes('full'), sequence(seen.outside));
    check(`${label}: inside the AOI no frame of the background, and the tiles at the end`, !seen.inside.includes('empty') && seen.inside.at(-1) === 'full', sequence(seen.inside));
  }
  await page.close();
}

(async () => {
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  await run(browser, BASE, 'after', true);
  if (BASE_OLD) await run(browser, BASE_OLD, 'before', false);
  await browser.close();
  process.exit(results.every(Boolean) ? 0 : 1);
})();
