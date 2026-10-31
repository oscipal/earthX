// Browser check of the warning before a job that resamples bands (NM4-65 part 7), in a real browser with made-up answers of the
// platform: the estimate carries `resampling`; "Review" then asks (grid, bands, method, what it means for the values), "Cancel" and
// Escape drop the review so that "Start job" stays shut, "Continue" keeps it and "Start job" sends the order without asking again. The dialog is as wide
// as the window allows, nothing leaves it, and the focus is on "Cancel". Light and dark theme, a wide and a narrow window.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/resampling-warning.cjs         # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-resampling-warning');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const STAT = { count: 900, min: 0.01, max: 0.9, percentile_2: 0.05, percentile_98: 0.7, unit: null };

async function open(browser, theme, viewport) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const posted = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/estimate')) {
      return json({
        estimate: { size: 4e6, duration: 'PT3.4S', outputPixels: 1e6, inputPixels: 2e6, inputBytes: 4e6, assets: 2, units: 1 },
        skippedItems: [],
        resampling: { grid: { resolution: 10, crs: 'EPSG:32632' }, method: 'nearest', bands: [{ band: 'rededge1', resolution: 20, crs: 'EPSG:32632' }, { band: 'swir16', resolution: 60, crs: 'EPSG:32633' }], scenes: { count: 1, of: 2, crs: 'EPSG:32632' } },
      });
    }
    if (url.pathname.endsWith('/execution')) {
      posted.push(JSON.parse(route.request().postData()).inputs.recipe);
      return json({ processID: 'recipe', type: 'process', jobID: 'QrStUvWxYzAbCdEfGhIj_-', status: 'accepted', message: '', progress: 0, created: '2026-10-31T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    if (url.pathname.endsWith('/statistics')) return json({ b1: STAT });
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page, posted };
}

// Scenes A and B of one day, C of another; one layer over `ids`, cut to its AOI or not.
async function setUp(page, ids, crop, selected = ids) {
  await page.evaluate(
    async ({ ids, crop, selected }) => {
      const { useAppStore } = await import('/src/store.ts');
      const box = (x, y) => ({ type: 'Polygon', coordinates: [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]] });
      const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
      const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
      const scene = (id, day) => ({
        id, collection: 'sentinel-2-c1-l2a', bbox: [10, 50, 11, 51], geometry: box(10, 50),
        properties: { datetime: `${day}T10:00:00Z`, gsd: 10 }, assets: { red: asset(), nir: asset() },
      });
      const one = [scene('S2B_A', '2026-07-01'), scene('S2B_B', '2026-07-01')];
      const two = [scene('S2B_C', '2026-07-02')];
      const aoi = { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] };
      useAppStore.setState({
        datasets: [{
          id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
          browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
          collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } },
        }],
        datasetId: 'sentinel-2-c1-l2a', items: [...one, ...two],
        groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: one }, { key: ['2026-07-02'], label: '2026-07-02', items: two }],
        activeGroupIndex: 0, selectedIds: [], aoi: null, aoiPoint: null, focusMode: false, error: null, dock: 'layers',
        layers: [{
          id: 'L1', name: 'Crop', visible: true, opacity: 1, overlays: [],
          restore: {
            focusMode: true, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: selected, itemIds: ids, groupItemIds: [ids],
            aoi: crop ? aoi : null, cropToAoi: crop, datasetId: 'sentinel-2-c1-l2a',
          },
        }],
      });
    },
    { ids, crop, selected },
  );
  await page.waitForSelector('.layer-row [data-col="process"]', { timeout: 10000 });
}



async function check(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  fs.mkdirSync(OUT, { recursive: true });
  const { context, page, posted } = await open(browser, theme, viewport);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  await setUp(page, ['S2B_A', 'S2B_B'], true);
  await page.locator('.layer-row [data-col="process"]').click();
  const panel = page.locator('.processing-panel');
  await panel.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  const review = () => panel.getByRole('button', { name: 'Review', exact: true }).click();
  const start = () => panel.locator('button.primary-btn', { hasText: 'Start job' });
  const dialog = page.locator('[role="alertdialog"]');
  await review();
  await dialog.waitFor({ timeout: 10000 });
  if (posted.length !== 0) problems.push('an order was sent before the warning was answered');
  const text = await dialog.textContent();
  for (const part of ['Values are resampled', 'one grid of 10 m in EPSG:32632, by nearest neighbour', 'rededge1 (20 m)', 'swir16 (60 m, EPSG:32633)', '1 of 2 scenes lie in another UTM zone', 'no new values appear', 'Cancel', 'Continue']) {
    if (!text.includes(part)) problems.push(`the warning does not say "${part}"`);
  }
  if (text.includes('Resampled to a common grid')) problems.push('the old exclamation mark text is still there');
  if ((await page.evaluate(() => document.activeElement?.textContent)) !== 'Cancel') problems.push('the focus is not on "Cancel"');
  const box = await dialog.boundingBox();
  const window = VIEWPORTS[viewport];
  if (box.x < -0.5 || box.y < -0.5 || box.x + box.width > window.width + 0.5 || box.y + box.height > window.height + 0.5) problems.push(`the warning leaves the window: ${JSON.stringify(box)}`);
  if (await dialog.evaluate((el) => el.scrollWidth > el.clientWidth + 1)) problems.push('the warning scrolls sideways');
  const buttons = await dialog.locator('button').evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
  if (buttons[0].x + buttons[0].w > buttons[1].x + 0.5 && Math.abs(buttons[0].y - buttons[1].y) < 2) problems.push('the two buttons overlap');
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_warning.png`) });

  // Escape drops the review: nothing is sent, "Start job" is shut. Cancel does the same.
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  if ((await dialog.count()) !== 0) problems.push('Escape did not close the warning');
  if (!(await start().isDisabled())) problems.push('"Start job" is open after Escape');
  await review();
  await dialog.waitFor();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  if (posted.length !== 0 || (await dialog.count()) !== 0 || !(await start().isDisabled())) problems.push('"Cancel" did not leave things as they were');

  // Continue keeps the review: "Start job" is open and sends one order without asking again.
  await review();
  await dialog.waitFor();
  await dialog.getByRole('button', { name: 'Continue' }).click();
  await page.waitForSelector('.processing-panel button.primary-btn:not([disabled])', { timeout: 10000 });
  await start().click();
  await page.waitForTimeout(800);
  if ((await dialog.count()) !== 0) problems.push('the warning came again at "Start job"');
  if (posted.length !== 1) problems.push(`${posted.length} orders were sent after "Continue"`);
  await context.close();
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const result = await check(browser, theme, viewport).catch((error) => ({ name: `${theme} ${viewport}`, problems: [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`] }));
      failed += result.problems.length > 0 ? 1 : 0;
      console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
