// The tooltip of the app (NM4-52): in a real browser, the tooltip of a symbol in the layer manager, of the view of
// a result and of the rail lies over every other box and entirely inside the window (8 px margin). Light and dark
// theme, a wide and a narrow window; writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/tooltips.cjs                   # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-tooltips');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

async function check(browser, { theme, viewport }) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const restore = { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: ['scene'], groupItemIds: [['scene']], aoi: null, cropToAoi: false, datasetId: null };
    const base = { visible: true, opacity: 1, overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=180%2C1900', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }] };
    const result = (over) => ({ jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: future, gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, ...over });
    useAppStore.setState({
      dock: 'layers',
      layers: [
        { ...base, id: 'result', name: 'Result · Band math', derived: 'result', result: result({ dataType: 'uint8' }), restore },
        { ...base, id: 'old', name: 'Result · expired and resampled', derived: 'result', result: result({ expired: true, resampled: true }), restore },
      ],
    });
  });
  await page.waitForSelector('.layer-row');

  const probe = async (label, locator) => {
    await locator.hover();
    const tip = page.locator('.tip-layer');
    await tip.waitFor();
    await page.waitForTimeout(50);
    const box = await tip.evaluate((el) => el.getBoundingClientRect().toJSON());
    if (box.x < 8 - 0.5 || box.y < 8 - 0.5 || box.x + box.width > win.width - 8 + 0.5 || box.y + box.height > win.height - 8 + 0.5) problems.push(`${label}: outside the window ${JSON.stringify(box)}`);
    await tip.evaluate((el) => (el.style.pointerEvents = 'auto')); // elementFromPoint skips `none`
    const top = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.className, { x: box.x + box.width / 2, y: box.y + box.height / 2 });
    if (top !== 'tip-layer') problems.push(`${label}: covered by "${top}"`);
    await page.screenshot({ path: path.join(OUT, `${label} ${name}.png`) });
    await page.keyboard.press('Escape');
    if ((await page.locator('.tip-layer').count()) !== 0) problems.push(`${label}: Esc did not close it`);
    await page.mouse.move(0, win.height - 1);
  };

  await probe('layer-manager', page.locator('.layer-row .lm-note .tip').first());
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: null })); // in a narrow window the panel covers the rail
  await probe('rail', page.locator('.rail-btn').first());
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: 'layers' }));
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().selectLayer('result'));
  await page.waitForSelector('.result-controls .vc-head .tip', { state: 'attached' }).catch(() => problems.push('view: no tip in the head of the view'));
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: null })); // in a narrow window the panel covers the view
  if ((await page.locator('.result-controls .vc-head .tip').count()) > 0) await probe('view-bar', page.locator('.result-controls .vc-head .tip').first());

  await context.close();
  return { name, problems };
}

(async () => {
  require('node:fs').mkdirSync(OUT, { recursive: true });
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
