// The block at the bottom of the map (NM4-66), in a real browser with made-up scenes (no backend):
//   1. The bar of the selection and the timeline are one panel, one grip, and as wide as each other.
//   2. The row of dates: first, before, "<", shown, ">", after, last; "<" and ">" go a step; no date twice.
//   3. A small red "x" at the top right, over no button; it hides the block and leaves the ticks alone; a click on a scene
//      or an opened group in the list brings it back.
//   4. The block (not moved and moved) stays where it is when a panel opens and closes.
//   5. A narrow window: nothing of the row of dates lies outside the block.
// Light and dark theme, a wide and a narrow window; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/selection-block.cjs            # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-selection-block');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const DAYS = ['2026-07-07', '2026-07-06', '2026-07-05', '2026-07-04', '2026-07-03', '2026-07-02', '2026-07-01'];

const near = (a, b, d = 0.6) => Math.abs(a - b) <= d;

async function run(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.on('pageerror', (error) => problems.push(`pageerror ${error.message}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(async (days) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const { buildSections } = await import('/src/sections.ts');
    const caps = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
    const datasets = datasetsFrom([
      {
        id: 'synthetic',
        title: 'Synthetic',
        'earthx:format': 'cog',
        'earthx:capabilities': caps,
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['datetime'] },
        'earthx:default_render': { title: 'Grey', assets: ['data'], rescale: [[0, 1]], colormap_name: null, expression: null, resampling: 'nearest' },
      },
    ]);
    const features = days.map((d) => ({ id: `S_${d}`, collection: 'synthetic', bbox: [-20, 30, 40, 60], properties: { datetime: `${d}T10:00:00Z` }, assets: {} }));
    const { sections } = buildSections(features, datasets.filter((d) => d.viewable), { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    const open = sections[0];
    useAppStore.setState({
      datasets,
      sections,
      openSectionId: open.datasetId,
      datasetId: open.datasetId,
      selectedDatasetIds: [open.datasetId],
      items: open.items,
      groups: open.groups,
      activeGroupIndex: 3,
      expandedGroupIndex: 3,
      selectedIds: [],
      selectionBlockClosed: false,
      dock: null,
      flyToView: { center: [10, 45], zoom: 3 },
    });
  }, DAYS);

  const box = (selector) => page.locator(selector).first().boundingBox();
  const cells = () => page.locator('.time-dates > *').evaluateAll((els) => els.map((e) => e.textContent ?? ''));
  const state = (expr) => page.evaluate(async (e) => { const { useAppStore } = await import('/src/store.ts'); return new Function('s', `return ${e}`)(useAppStore.getState()); }, expr);

  // --- the timeline alone: nothing is ticked ------------------------------------------------------------------------
  await page.waitForSelector('.time-slider');
  if ((await page.locator('.download-bar').count()) !== 0) problems.push('the bar shows with nothing ticked');
  if ((await page.locator('.close-x').count()) !== 1) problems.push('no "x" on the timeline alone');
  await page.screenshot({ path: path.join(OUT, `${name} timeline.png`) });

  // --- tick a scene in the list: one block --------------------------------------------------------------------------
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().toggleSelected('S_2026-07-04'));
  await page.waitForSelector('.download-bar');
  const blocks = await page.locator('.selection-block').count();
  if (blocks !== 1) problems.push(`${blocks} blocks`);
  if ((await page.locator('.drag-grip').count()) !== 1 || (await page.locator('.selection-block .panel, .selection-block.panel').count()) > 1) problems.push('more than one grip or panel');
  const [blockBox, barBox, timeBox] = [await box('.selection-block'), await box('.download-bar'), await box('.time-slider')];
  if (!near(barBox.width, timeBox.width) || !near(barBox.width, blockBox.width - 2) || !near(barBox.x, timeBox.x)) {
    problems.push(`bar ${barBox.width} x ${barBox.x}, timeline ${timeBox.width} x ${timeBox.x}, block ${blockBox.width}: not one width`);
  }
  if (blockBox.x < 0 || blockBox.x + blockBox.width > win.width + 0.5) problems.push(`the block lies outside the window: ${blockBox.x} + ${blockBox.width}`);

  // The "x": top right, over no button of the bar.
  const x = await box('.selection-block .close-x');
  if (x.x + x.width > blockBox.x + blockBox.width || x.y < blockBox.y || x.x < blockBox.x + blockBox.width / 2) problems.push('the "x" is not at the top right of the block');
  const buttons = await page.locator('.download-bar button').evaluateAll((els) => els.map((e) => e.getBoundingClientRect().toJSON()));
  for (const b of buttons) {
    if (x.x < b.right && x.x + x.width > b.left && x.y < b.bottom && x.y + x.height > b.top) problems.push('the "x" lies over a button of the bar');
  }
  const colour = await page.locator('.close-x').evaluate((e) => getComputedStyle(e).color);
  if (!/^rgb\((255, 90, 110|198, 40, 64)\)$/.test(colour)) problems.push(`the "x" is ${colour}, not red`);
  if ((await page.locator('.close-x').getAttribute('title')) !== 'Close') problems.push('the "x" has no tooltip "Close"');

  // --- the row of dates ---------------------------------------------------------------------------------------------
  // activeGroupIndex 3 of 7 (newest first): shown 2026-07-04.
  let row = await cells();
  const expectRow = ['2026-07-01', '2026-07-03', '<', '2026-07-04', '>', '2026-07-05', '2026-07-07'];
  if (JSON.stringify(row) !== JSON.stringify(expectRow)) problems.push(`row ${JSON.stringify(row)}`);
  // Nothing of the row lies outside the block, wide or narrow; the date shown is always there.
  const outside = await page.locator('.time-dates > *').evaluateAll((els) => {
    const block = document.querySelector('.selection-block').getBoundingClientRect();
    return els.filter((e) => e.textContent && getComputedStyle(e).visibility !== 'hidden').filter((e) => { const r = e.getBoundingClientRect(); return r.left < block.left - 0.5 || r.right > block.right + 0.5; }).map((e) => e.textContent);
  });
  if (outside.length) problems.push(`outside the block: ${outside}`);
  const clipped = await page.locator('.time-dates strong').evaluate((e) => e.scrollWidth > e.clientWidth + 1);
  if (clipped) problems.push('the date shown is clipped');
  const hiddenNow = await page.locator('.time-dates > *').evaluateAll((els) => els.map((e) => getComputedStyle(e).visibility === 'hidden' && !!e.textContent));
  await page.screenshot({ path: path.join(OUT, `${name} block.png`) });
  if (viewport === 'wide' && hiddenNow.some(Boolean)) problems.push('a date is hidden in the wide window');
  if (viewport === 'narrow') console.log(`  ${name}: hidden dates at ${Math.round(blockBox.width)} px:`, hiddenNow.map((h, i) => (h ? row[i] : null)).filter(Boolean).join(' '));

  await page.getByRole('button', { name: 'Previous step' }).click();
  if ((await page.locator('.time-dates strong').innerText()) !== '2026-07-03') problems.push('"<" did not go to the step before');
  if ((await state('s.activeGroupIndex')) !== 4) problems.push('the step is not 4 of 7 in the store');
  await page.getByRole('button', { name: 'Next step' }).click();
  await page.getByRole('button', { name: 'Next step' }).click();
  if ((await page.locator('.time-dates strong').innerText()) !== '2026-07-05') problems.push('">" did not go to the step after');
  // At the ends the arrow is not there, and the other elements keep their place.
  const before = await page.locator('.time-dates strong').evaluate((e) => e.getBoundingClientRect().x);
  for (let i = 0; i < 6; i++) if (await page.getByRole('button', { name: 'Next step' }).count()) await page.getByRole('button', { name: 'Next step' }).click();
  if ((await page.getByRole('button', { name: 'Next step' }).count()) !== 0) problems.push('">" at the newest step');
  if ((await page.locator('.time-dates strong').innerText()) !== '2026-07-07') problems.push('not at the newest step');
  const after = await page.locator('.time-dates strong').evaluate((e) => e.getBoundingClientRect().x);
  if (!near(before, after, 80) && viewport === 'wide') problems.push(`the date shown moved from ${before} to ${after}`);
  row = await cells();
  if (row[0] !== '2026-07-01' || row[6] !== '' || row[1] !== '2026-07-06') problems.push(`row at the newest step ${JSON.stringify(row)}`);
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().setActiveGroupIndex(3));

  // --- the "x" and what brings the block back -----------------------------------------------------------------------
  const ticks = await state('s.selectedIds.join()');
  await page.locator('.selection-block .close-x').click();
  if ((await page.locator('.selection-block').count()) !== 0) problems.push('the block is still there after the "x"');
  if ((await state('s.selectedIds.join()')) !== ticks) problems.push('closing changed the ticks');
  // Open the list of results: a click on a scene shows the block again. In a narrow window the list lies over the whole
  // map and over the block (the block does not give way); the "x" is then closed again with the list closed.
  const dock = (d) => page.evaluate(async (v) => (await import('/src/store.ts')).useAppStore.setState({ dock: v }), d);
  await dock('results');
  await page.waitForSelector('.result-row');
  await page.locator('.result-row .result-date').first().click();
  await page.waitForSelector('.selection-block');
  await dock(null);
  await page.locator('.selection-block .close-x').click();
  // An opened group does too.
  await dock('results');
  await page.locator('.result-group-head').nth(1).click();
  await page.waitForSelector('.selection-block');
  // A group that is closed does not.
  await dock(null);
  await page.locator('.selection-block .close-x').click();
  await dock('results');
  const open = await state('s.expandedGroupIndex');
  await page.locator('.result-group-head').nth(open).click();
  if ((await state('s.expandedGroupIndex')) !== null) problems.push('the open group did not close');
  if ((await page.locator('.selection-block').count()) !== 0) problems.push('closing a group showed the block');
  // And a tick shows it again.
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().toggleSelected('S_2026-07-02'));
  await page.waitForSelector('.selection-block');
  await dock(null);

  // --- the block does not give way to a panel -------------------------------------------------------------------------
  const rect = async () => (await box('.selection-block'));
  const rest = await rect();
  for (const dock of ['controls', 'layers', 'results', 'jobs', null]) {
    await page.evaluate(async (d) => (await import('/src/store.ts')).useAppStore.setState({ dock: d }), dock);
    await page.waitForTimeout(120);
    const now = await rect();
    if (!near(now.x, rest.x) || !near(now.y, rest.y) || !near(now.width, rest.width)) problems.push(`the block moved with the panel ${dock}: ${rest.x},${rest.y} -> ${now.x},${now.y}`);
  }
  // Moved by hand with the mouse (the grip, or any part that is no control), it stays where it was put.
  const g = await box('.draggable[data-band="selection"] .drag-grip');
  await page.mouse.move(g.x + g.width / 2, g.y + 1);
  await page.mouse.down();
  await page.mouse.move(g.x + g.width / 2 - 60, g.y - 120, { steps: 6 });
  await page.mouse.up();
  const put = await rect();
  if (near(put.y, rest.y, 20)) problems.push('the block did not move when dragged');
  for (const dock of ['controls', 'results', null]) {
    await page.evaluate(async (d) => (await import('/src/store.ts')).useAppStore.setState({ dock: d }), dock);
    await page.waitForTimeout(120);
    const now = await rect();
    if (!near(now.x, put.x) || !near(now.y, put.y)) problems.push(`the moved block moved with the panel ${dock}`);
  }
  await page.screenshot({ path: path.join(OUT, `${name} moved.png`) });

  await context.close();
  return { name, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = false;
  const only = process.env.CASE;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      if (only && only !== `${theme} ${viewport}`) continue;
      const { name, problems } = await run(browser, theme, viewport);
      console.log(`${problems.length ? 'FAIL' : 'ok  '} ${name}`);
      for (const p of problems) console.log(`   - ${p}`);
      failed ||= problems.length > 0;
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
