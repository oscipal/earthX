// Browser check of NM4-65 (package "display and layers"): in a real browser, with made-up answers of the search and the
// tiler, light and dark theme, a wide and a narrow window, a screenshot per case.
//   part 1  the grip: a row is taken by its grip with the real mouse and put somewhere else; Escape drops nothing; ▲/▼ still work
//   part 3  the acquisition date is in the row of a layer: a day, a span, none
//   part 5  the opacity slider of the settings of a layer reaches its right end (the thumb at the end of the track at 1)
//   part 8  every closing is the same small red "x" with the tooltip "Close"
//   part 2  "Add band as layer": the button at the end of the line of the band, the new layer named after the band, with the date
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/nm4-65.cjs                     # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. If the page
// shows no layers after files were changed, restart the dev server (Vite stamps changed modules, and the script would import
// a second copy of the store).

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-nm4-65');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

const state = (page, expression) => page.evaluate(async (code) => new Function('s', `return (${code})`)((await import('/src/store.ts')).useAppStore.getState()), expression);

async function seed(page, viewport) {
  await page.evaluate(async (narrow) => {
    const { useAppStore } = await import('/src/store.ts');
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const restore = { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null };
    const raster = { kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 };
    const base = { visible: true, opacity: 1, overlays: [raster], restore };
    useAppStore.setState({
      dock: narrow ? null : 'layers',
      layers: [
        { ...base, id: 'one', name: 'Optical · one day', date: '2026-07-01' },
        { ...base, id: 'two', name: 'Optical · a span of days', date: '2026-07-01 – 2026-07-06' },
        { ...base, id: 'dem', name: 'Elevation · no time axis' },
        { ...base, id: 'res', name: 'Result · Band math', derived: 'result', date: '2026-07-06', opacity: 1,
          result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: future, gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null } },
      ],
    });
  }, viewport === 'narrow');
}

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 404, body: '' });
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  await seed(page, viewport);
  // A narrow window is covered by the panel: open the layer manager by the rail, as a person does.
  if (viewport === 'narrow') await state(page, "(s.toggleDock('layers'), 1)");
  await page.waitForSelector('.layer-row');

  // --- part 3: the dates
  const dates = await page.$$eval('.layer-row', (rows) => rows.map((row) => row.querySelector('.lm-date')?.textContent ?? null));
  if (JSON.stringify(dates) !== JSON.stringify(['2026-07-01', '2026-07-01 – 2026-07-06', null, '2026-07-06'])) problems.push(`dates in the rows: ${JSON.stringify(dates)}`);
  const dateBox = await page.locator('.layer-row .lm-date').first().boundingBox();
  const nameBox = await page.locator('.layer-row .lm-name').first().boundingBox();
  const panelBox = await page.locator('.layer-manager').boundingBox();
  if (dateBox.y < nameBox.y + nameBox.height - 1) problems.push('the date is not under the name');
  if (Math.abs(dateBox.x - nameBox.x) > 1.5) problems.push(`the date starts at x=${dateBox.x}, the name at x=${nameBox.x}`);
  if (dateBox.x + dateBox.width > panelBox.x + panelBox.width + 0.5) problems.push('the date leaves the panel');
  await shot('1-rows');

  // --- part 1: the grip, with the real mouse
  const rowCount = await page.locator('.layer-row').count();
  const grips = await page.locator('.layer-row .lm-grip').count();
  if (grips !== rowCount) problems.push(`${grips} grips for ${rowCount} rows`);
  const first = await page.locator('.layer-row .lm-grip').nth(0).boundingBox();
  const rowBox = await page.locator('.layer-row').nth(0).boundingBox();
  if (first.x > rowBox.x + 14) problems.push(`the grip is not at the far left of its row: x=${first.x}, row x=${rowBox.x}`);
  const order = () => state(page, "s.layers.map((l) => l.id).join()");
  const centre = async (i, which = '.lm-grip') => {
    const box = await page.locator(`.layer-row ${which}`).nth(i).boundingBox();
    return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
  };
  const from = await centre(0);
  const to = await centre(2, '.lm-name');
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(from.x, (from.y + to.y) / 2, { steps: 5 });
  await page.mouse.move(from.x, to.y, { steps: 5 });
  const held = await page.$$eval('.layer-row', (rows) => rows.map((row) => row.className));
  if (!held[0].includes('dragging')) problems.push(`the row that is held is not marked: ${held[0]}`);
  if (!held[2].includes('drop-below')) problems.push(`the place it will take is not marked: ${held[2]}`);
  await shot('2-held');
  if ((await order()) !== 'one,two,dem,res') problems.push('the list changed while the row was only held');
  await page.mouse.up();
  if ((await order()) !== 'two,dem,one,res') problems.push(`after the drop: ${await order()}`);
  if ((await page.locator('.layer-row.dragging, .layer-row.drop-above, .layer-row.drop-below').count()) !== 0) problems.push('a mark of the drag is left after the drop');
  await shot('3-dropped');

  // Escape drops nothing.
  const again = await centre(2);
  const up = await centre(0, '.lm-name');
  await page.mouse.move(again.x, again.y);
  await page.mouse.down();
  await page.mouse.move(up.x, up.y, { steps: 6 });
  await page.keyboard.press('Escape');
  await page.mouse.up();
  if ((await order()) !== 'two,dem,one,res') problems.push(`Escape did not drop nothing: ${await order()}`);
  // ▲/▼ stay for the keyboard.
  await page.locator('.layer-row').nth(1).locator('button[title="Move up"]').click();
  if ((await order()) !== 'dem,two,one,res') problems.push(`▲ after the drag: ${await order()}`);
  // The map follows the list: the stacking order is the list's (NM4-59).
  const stacked = await state(page, "s.layers.map((l) => l.id).join()");
  if (stacked !== 'dem,two,one,res') problems.push(`the store's list: ${stacked}`);

  // --- part 5: the opacity slider of the settings reaches its end
  // A narrow window is covered by the open panel: the settings are looked at with it shut.
  if (viewport === 'narrow') await state(page, '(s.closeDock(), 1)');
  await state(page, "(s.selectLayer('res'), 1)");
  await page.waitForSelector('.result-controls');
  const slider = page.locator('.result-controls input[type=range]');
  const sliderBox = await slider.boundingBox();
  const thumb = await slider.evaluate((el) => {
    const r = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return { padding: style.paddingLeft + style.paddingRight, border: style.borderLeftWidth + style.borderRightWidth, width: r.width };
  });
  if (thumb.padding !== '0px0px' || thumb.border !== '0px0px') problems.push(`the slider still has a padding or a frame: ${JSON.stringify(thumb)}`);
  await page.mouse.move(sliderBox.x + sliderBox.width / 2, sliderBox.y + sliderBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(sliderBox.x + sliderBox.width + 30, sliderBox.y + sliderBox.height / 2, { steps: 5 });
  await page.mouse.up();
  const value = await slider.inputValue();
  if (value !== '1') problems.push(`the slider reads ${value} at the right end`);
  await shot('4-settings');

  // --- part 8: the close x
  const close = page.locator('.result-controls .close-x');
  if ((await close.count()) !== 1) problems.push('no close x in the settings of the layer');
  else {
    if ((await close.getAttribute('title')) !== 'Close') problems.push(`tooltip of the x: ${await close.getAttribute('title')}`);
    const colour = await close.evaluate((el) => getComputedStyle(el).color);
    const [r, g, b] = colour.match(/\d+/g).map(Number);
    if (!(r > g + 60 && r > b + 40)) problems.push(`the x is not red: ${colour}`);
    const box = await close.boundingBox();
    if (box.width > 24 || box.height > 24) problems.push(`the x is not small: ${box.width}×${box.height}`);
    await close.click();
    if ((await page.locator('.result-controls').count()) !== 0) problems.push('the x did not close the settings');
  }
  if ((await page.getByRole('button', { name: '‹ Close' }).count()) !== 0) problems.push('"‹ Close" is still there');

  // --- part 2: "Add band as layer"
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const restore = { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null };
    const bands = ['red', 'green', 'blue'].map((name) => ({ name, stats: null }));
    useAppStore.setState({
      resultViewLayerId: null,
      layers: [{ id: 'multi', name: 'Result · three bands', visible: true, opacity: 1, derived: 'result', date: '2026-07-06', restore,
        overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&bidx=2&colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
        result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: future, gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, bands, band: 1 } }],
    });
  });
  if (viewport === 'narrow') await state(page, "(s.toggleDock('layers'), 1)");
  await page.waitForSelector('.layer-row .lm-band');
  const select = await page.locator('.layer-row .lm-band').boundingBox();
  const add = page.locator('.layer-row .lm-add-band');
  const addBox = await add.boundingBox();
  const removeBox = await page.locator('.layer-row [data-col="remove"]').boundingBox();
  if (Math.abs(addBox.y + addBox.height / 2 - (select.y + select.height / 2)) > 3) problems.push('"Add band as layer" is not in the line of the band');
  if (Math.abs(addBox.x - removeBox.x) > 1.5) problems.push(`"Add band as layer" is not under the remove button: x=${addBox.x}, remove x=${removeBox.x}`);
  if (select.x + select.width > addBox.x + 0.5) problems.push('the band dropdown runs into the button');
  if ((await add.getAttribute('title')) !== 'Add this band as a layer of its own') problems.push(`tooltip: ${await add.getAttribute('title')}`);
  await shot('5-band-line');
  await add.click();
  const names = await page.$$eval('.layer-row .lm-name', (n) => n.map((x) => x.textContent));
  if (JSON.stringify(names) !== JSON.stringify(['green', 'Result · three bands'])) problems.push(`layers after "Add band as layer": ${JSON.stringify(names)}`);
  const dated = await page.$$eval('.layer-row', (rows) => rows.map((row) => row.querySelector('.lm-date')?.textContent ?? null));
  if (JSON.stringify(dated) !== JSON.stringify(['2026-07-06', '2026-07-06'])) problems.push(`dates of the two layers: ${JSON.stringify(dated)}`);
  await shot('6-band-layer');

  await context.close();
  return { name: label, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const result = await check(browser, { theme, viewport }).catch((error) => ({ name: `${theme} ${viewport}`, problems: [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`] }));
      failed += result.problems.length > 0 ? 1 : 0;
      console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
