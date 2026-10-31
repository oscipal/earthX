// Browser check of the crop as one object (NM4-06), in a real browser with made-up answers of the platform:
//   1. ⚙ at a layer merged and cut to its AOI: the panel has no "Run as" and no choice of the area (a lock says "AOI only");
//      "Review" and "Start job" send one order, the scenes of the layer on its AOI.
//   2. A layer of scenes of several passes: a small choice "This pass only" (the pass in view) or "All passes (n jobs)", no
//      "Run as"; one order for the pass in view, or one for every pass on the same AOI.
//   3. A layer that is not cut to its AOI keeps "Run as" and the choice of the area.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/process-crop.cjs               # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-process-crop');
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
      return json({ estimate: { size: 4e6, duration: 'PT3.4S', outputPixels: 1e6, inputPixels: 2e6, inputBytes: 4e6, assets: 2, units: 1 }, skippedItems: [] });
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

  // 1. A crop of one pass: one object.
  {
    const { context, page, posted } = await open(browser, theme, viewport);
    await setUp(page, ['S2B_A', 'S2B_B'], true);
    await page.locator('.layer-row [data-col="process"]').click();
    await page.waitForSelector('.processing-panel section[aria-label="Selection"] .pp-fixed', { timeout: 10000 });
    const panel = page.locator('.processing-panel');
    if ((await panel.locator('[aria-label="Run as"]').count()) !== 0) problems.push('"Run as" is offered for the crop');
    if ((await panel.getByRole('button', { name: 'Whole scene' }).count()) + (await panel.getByRole('button', { name: 'AOI only' }).count()) !== 0) problems.push('the area can be chosen for the crop');
    if (!(await panel.locator('.pp-fixed').textContent())?.includes('AOI only')) problems.push('the area is not shown as AOI only');
    if ((await panel.locator('.pp-fixed').getAttribute('title')) !== 'Fixed by the crop.') problems.push('the lock has no tooltip');
    const layout = await page.evaluate(() => {
      const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
      const root = document.querySelector('.processing-panel');
      return { theme: document.querySelector('.app')?.dataset.theme, panel: box(root), scrolls: root.querySelector('.pp-body').scrollWidth > root.querySelector('.pp-body').clientWidth + 1, fixed: box(root.querySelector('.pp-fixed')) };
    });
    if (layout.fixed.x < layout.panel.x - 0.5 || layout.fixed.x + layout.fixed.width > layout.panel.x + layout.panel.width + 0.5) problems.push('the lock leaves the panel');
    if (layout.theme !== THEMES[theme]) problems.push(`the app shows the theme ${layout.theme}`);
    if (layout.scrolls) problems.push('the panel scrolls sideways');
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_crop.png`) });
    await panel.getByRole('button', { name: /Band math/ }).first().click();
    await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
    await panel.getByRole('button', { name: 'Review', exact: true }).click();
    await page.waitForSelector('.processing-panel button.primary-btn:not([disabled])', { timeout: 10000 });
    await panel.locator('button.primary-btn', { hasText: 'Start job' }).click();
    await page.waitForTimeout(800);
    if (posted.length !== 1) problems.push(`${posted.length} orders were sent`);
    else {
      if (JSON.stringify(posted[0].inputs[0].groups) !== '[["S2B_A","S2B_B"]]') problems.push(`the scenes are ${JSON.stringify(posted[0].inputs[0].groups)}`);
      if (!posted[0].aoi) problems.push('the order has no area');
    }
    await context.close();
  }

  // 2. A crop of two passes: the pass in view, or every pass.
  {
    const { context, page, posted } = await open(browser, theme, viewport);
    await setUp(page, ['S2B_A', 'S2B_B', 'S2B_C'], true, ['S2B_C']);
    await page.locator('.layer-row [data-col="process"]').click();
    await page.waitForSelector('.processing-panel [aria-label="Passes"]', { timeout: 10000 });
    const panel = page.locator('.processing-panel');
    const choices = await panel.locator('[aria-label="Passes"] button').allTextContents();
    if (choices.join() !== 'This pass only,All passes (2 jobs)') problems.push(`the choices are ${choices}`);
    if ((await panel.locator('[aria-label="Run as"]').count()) !== 0) problems.push('"Run as" is offered for the crop');
    const picked = await panel.locator('select').first().evaluate((e) => e.selectedOptions[0].textContent);
    if (!picked.includes('2026-07-02')) problems.push(`the pass in view is not the default: ${picked}`);
    const frame = await panel.boundingBox();
    const box = await panel.locator('[aria-label="Passes"]').boundingBox();
    if (box.x < frame.x - 0.5 || box.x + box.width > frame.x + frame.width + 0.5) problems.push('the choice leaves the panel');
    await page.waitForTimeout(500);
    await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_passes.png`) });
    await panel.getByRole('button', { name: /Band math/ }).first().click();
    await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
    await panel.getByRole('button', { name: 'Review', exact: true }).click();
    await page.waitForSelector('.processing-panel button.primary-btn:not([disabled])', { timeout: 10000 });
    await panel.locator('button.primary-btn', { hasText: 'Start job' }).click();
    await page.waitForTimeout(800);
    if (posted.length !== 1 || JSON.stringify(posted[0].inputs[0].groups) !== '[["S2B_C"]]') problems.push(`"This pass only" sent ${JSON.stringify(posted.map((o) => o.inputs[0].groups))}`);
    await panel.getByRole('button', { name: 'All passes (2 jobs)' }).click();
    await panel.getByRole('button', { name: 'Review', exact: true }).click();
    await page.waitForSelector('.processing-panel button.primary-btn:has-text("Start 2 jobs"):not([disabled])', { timeout: 10000 });
    await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_all.png`) });
    await panel.locator('button.primary-btn', { hasText: 'Start 2 jobs' }).click();
    await page.waitForTimeout(1500);
    const groups = posted.slice(1).map((o) => JSON.stringify(o.inputs[0].groups)).sort();
    if (groups.join() !== '[["S2B_A","S2B_B"]],[["S2B_C"]]' || posted.slice(1).some((o) => !o.aoi)) problems.push(`"All passes" sent ${groups}`);
    await context.close();
  }

  // 3. A layer that is not cut to its AOI: as it was.
  {
    const { context, page } = await open(browser, theme, viewport);
    await setUp(page, ['S2B_A', 'S2B_B'], false);
    await page.locator('.layer-row [data-col="process"]').click();
    await page.waitForSelector('.processing-panel section[aria-label="Selection"]', { timeout: 10000 });
    const panel = page.locator('.processing-panel');
    if ((await panel.getByRole('button', { name: 'Whole scene' }).count()) !== 1) problems.push('"Whole scene" is not offered for a layer that is not cut');
    if ((await panel.locator('[aria-label="Run as"]').count()) !== 1) problems.push('"Run as" is not offered for a layer that is not cut');
    await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_whole.png`) });
    await context.close();
  }
  return { name, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const { name, problems } = await check(browser, theme, viewport);
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
      for (const problem of problems) console.log(`       - ${problem}`);
      if (problems.length > 0) failed = true;
    }
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
