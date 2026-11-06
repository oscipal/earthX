// "Zoom to selection" (UI-04 part 4, Otto, 4.11.2026) in a real browser, on the real map: it zooms to the AOI, the open view and the layers that
// are shown, together, and over the antimeridian the shorter way. It fails when
//   1. the button is not locked with its reason where nothing is chosen;
//   2. an AOI in Switzerland and a layer on Tenerife are not both in the picture after the click (the AOI used to win);
//   3. a layer that is switched off pulls the box to itself;
//   4. an AOI on one side of the antimeridian and a layer on the other zoom out to the whole world instead of to the few degrees between them
//      (Fiji), or leave one of the two out of the picture;
//   5. the image of an open view is not counted (and is not once its image is hidden).
// Light and dark theme, 1280 and 360 px; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/zoom-selection.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-zoom-selection');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const NOTHING = 'Nothing to zoom to: draw an AOI, open an image or show a layer';

const SWITZERLAND = [6, 45.8, 10.5, 47.8];
const TENERIFE = [-16.9, 28, -16.1, 28.6];
const FIJI_EAST = [177, -19, 179.9, -16];
const FIJI_WEST = [-179.5, -18, -178, -16];

const polygon = (b) => ({ type: 'Polygon', coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] });
const layer = (id, b, visible = true) => ({
  id, name: id, visible, opacity: 1,
  overlays: [{ kind: 'raster', tileUrl: 'https://t.invalid/{z}/{x}/{y}', bounds: b, minZoom: 0, maxZoom: 14 }],
  restore: { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null },
});

async function check(browser, { theme, viewport }) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.maplibregl-canvas');
  await page.waitForTimeout(800);
  // The panel covers the map on a narrow window, and the message of the made-up server lies over the buttons: both are closed.
  const first = page.locator('nav[aria-label="Main"] button').first();
  if ((await first.getAttribute('aria-expanded')) === 'true') await first.click();
  const message = page.locator('.status .close-x');
  if (await message.count()) await message.first().click();

  const map = await page.evaluateHandle(() => {
    let fiber = document.querySelector('.maplibregl-map')[Object.keys(document.querySelector('.maplibregl-map')).find((k) => k.startsWith('__reactFiber$'))];
    for (; fiber; fiber = fiber.return) {
      for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
        const held = hook.memoizedState?.current;
        if (held && typeof held.getStyle === 'function') return held;
      }
    }
    return null;
  });
  const store = (fn, arg) => page.evaluate(async ([src, data]) => {
    const { useAppStore } = await import('/src/store.ts');
    return (0, eval)(`(${src})`)(useAppStore, data);
  }, [fn.toString(), arg]);
  const button = page.getByRole('button', { name: 'Zoom to selection' });
  const zoomed = async () => {
    await button.click();
    await page.evaluate((m) => new Promise((resolve) => { const timer = setTimeout(resolve, 4000); m.once('idle', () => { clearTimeout(timer); resolve(); }); }), map);
    await page.waitForTimeout(1300); // the flight takes 900 ms
    await page.evaluate((m) => new Promise((resolve) => { const timer = setTimeout(resolve, 3000); m.once('idle', () => { clearTimeout(timer); resolve(); }); m.triggerRepaint(); }), map);
  };
  // Where a lon/lat lies on the screen of the map: the longitude is taken the way the camera was centred, so that a box over the antimeridian
  // has its points inside (`project` copes with any copy of the world).
  const onScreen = async (box) => page.evaluate(([m, b]) => {
    const canvas = m.getCanvas().getBoundingClientRect();
    const centre = m.getCenter().lng;
    const wrap = (lon) => lon + 360 * Math.round((centre - lon) / 360);
    const corners = [[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]]].map(([lon, lat]) => m.project([wrap(lon), lat]));
    return corners.every((p) => p.x >= -1 && p.y >= -1 && p.x <= canvas.width + 1 && p.y <= canvas.height + 1);
  }, [map, box]);
  const camera = () => page.evaluate((m) => ({ zoom: m.getZoom(), lng: m.getCenter().lng, lat: m.getCenter().lat }), map);
  const shot = (label) => page.screenshot({ path: path.join(OUT, `${label} ${name}.png`) });

  // 1. Nothing chosen.
  if (!(await button.isDisabled())) problems.push('1: the button is free with nothing chosen');
  if ((await button.getAttribute('data-tip')) !== NOTHING) problems.push(`1: the reason is ${JSON.stringify(await button.getAttribute('data-tip'))}`);

  // 2. An AOI in Switzerland and a layer on Tenerife.
  await store((s, d) => s.setState({ aoi: d.aoi, layers: [d.layer] }), { aoi: polygon(SWITZERLAND), layer: layer('tenerife', TENERIFE) });
  await page.waitForTimeout(200);
  if (await button.isDisabled()) problems.push('2: the button is locked with an AOI and a layer');
  await zoomed();
  if (!(await onScreen(SWITZERLAND))) problems.push('2: the AOI is not in the picture');
  if (!(await onScreen(TENERIFE))) problems.push('2: the layer on Tenerife is not in the picture');
  const both = await camera();
  if (both.zoom > 5) problems.push(`2: it zooms in too far for both: zoom ${both.zoom.toFixed(1)}`);
  await shot('aoi and layer');

  // 3. A layer that is switched off does not count.
  await store((s, d) => s.setState({ layers: [d] }), layer('tenerife', TENERIFE, false));
  await page.waitForTimeout(200);
  await zoomed();
  if (!(await onScreen(SWITZERLAND))) problems.push('3: the AOI is out of the picture');
  const alone = await camera();
  if (alone.zoom < both.zoom + 0.5) problems.push(`3: a layer that is off still pulls: zoom ${alone.zoom.toFixed(1)} against ${both.zoom.toFixed(1)}`);
  if (Math.abs(alone.lng - 8.25) > 3) problems.push(`3: the centre is not the AOI's: ${alone.lng.toFixed(1)}`);

  // 4. Over the antimeridian.
  await store((s, d) => s.setState({ aoi: d.aoi, layers: [d.layer] }), { aoi: polygon(FIJI_EAST), layer: layer('fiji', FIJI_WEST) });
  await page.waitForTimeout(200);
  await zoomed();
  const fiji = await camera();
  if (fiji.zoom < 3.5) problems.push(`4: it zooms out to the world for Fiji: zoom ${fiji.zoom.toFixed(1)}`);
  if (!(Math.abs(Math.abs(fiji.lng) - 180) < 5)) problems.push(`4: the centre is not at the antimeridian: ${fiji.lng.toFixed(1)}`);
  if (!(await onScreen(FIJI_EAST))) problems.push('4: the AOI east of the line is not in the picture');
  if (!(await onScreen(FIJI_WEST))) problems.push('4: the layer west of the line is not in the picture');
  await shot('fiji');

  // 5. The open view.
  await store((s, d) => s.setState({ aoi: null, layers: [], focusMode: true, showDownloaded: true, downloaded: { a: { datasetId: 'd', tileUrl: 'https://t.invalid/{z}/{x}/{y}', bounds: d, asset: 'visual', minZoom: 0, maxZoom: 14 } } }), TENERIFE);
  await page.waitForTimeout(300);
  if (await button.isDisabled()) problems.push('5: the open view is not counted');
  else {
    await zoomed();
    if (!(await onScreen(TENERIFE)) || Math.abs((await camera()).lat - 28.3) > 3) problems.push('5: the open view is not in the picture');
  }
  await store((s) => s.setState({ showDownloaded: false }));
  await page.waitForTimeout(200);
  if (!(await button.isDisabled())) problems.push('5: a view whose image is hidden still counts');

  if (errors.length) problems.push(`the page failed: ${errors.join(' | ').slice(0, 200)}`);
  await context.close();
  return { name, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const { name, problems } = await check(browser, { theme, viewport });
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
      for (const problem of problems) console.log(`       ${problem}`);
      failed += problems.length;
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
