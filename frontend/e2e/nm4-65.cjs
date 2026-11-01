// Browser check of NM4-65 (package "display and layers"): in a real browser, with made-up answers of the search and the
// tiler, light and dark theme, a wide and a narrow window, a screenshot per case.
//   part 1  the grip: a row is taken by its grip with the real mouse and put somewhere else; Escape drops nothing; ▲/▼ still work
//   part 3  the acquisition date is in the name of a layer (a day, a span, none); the buttons of a row stand under its title
//   part 5  the opacity slider of the settings of a layer reaches its right end (the thumb at the end of the track at 1)
//   part 4  "absolute value / percentile" over vmin in the settings of a result: the dropdown stays over its field, "Apply" in percentiles asks the statistics
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
    if (url.pathname.endsWith('/statistics')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ bands: [{ name: 'a', data_type: 'float32', statistics: { minimum: 0, maximum: 1000, count: 100, percentile_3: 30, percentile_97: 970 } }] }) });
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

  // --- part 3: the dates are in the names, the buttons of a row are under its title
  const names0 = await page.$$eval('.layer-row .lm-name', (n) => n.map((x) => x.textContent));
  if (JSON.stringify(names0) !== JSON.stringify(['Optical · one day · 2026-07-01', 'Optical · a span of days · 2026-07-01 – 2026-07-06', 'Elevation · no time axis', 'Result · Band math · 2026-07-06'])) problems.push(`names of the rows: ${JSON.stringify(names0)}`);
  if ((await page.locator('.lm-date').count()) !== 0) problems.push('a date is still a line of its own');
  const nameBox = await page.locator('.layer-row .lm-name').first().boundingBox();
  const eyeBox = await page.locator('.layer-row [data-col="eye"]').first().boundingBox();
  const removeBox0 = await page.locator('.layer-row [data-col="remove"]').first().boundingBox();
  const sliderBox0 = await page.locator('.layer-row [data-col="opacity"]').first().boundingBox();
  const panelBox = await page.locator('.layer-manager').boundingBox();
  if (eyeBox.y < nameBox.y + nameBox.height - 1) problems.push('the buttons are not under the title');
  if (Math.abs(removeBox0.y - eyeBox.y) > 3) problems.push('the buttons are not in one line');
  if (sliderBox0.width < 60) problems.push(`the slider is only ${sliderBox0.width} px wide`);
  if (nameBox.width < panelBox.width - 60) problems.push(`the title is only ${nameBox.width} px of ${panelBox.width} px`);
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

  // --- part 4: "absolute value / percentile" in the settings of a result, with the statistics route made up here
  const unit = page.locator('.result-controls .vc-unit');
  if ((await unit.count()) !== 1) problems.push('no dropdown "absolute value / percentile" in the settings of the result');
  else {
    const options = await unit.locator('option').allTextContents();
    if (options.join() !== 'absolute,percentile') problems.push(`the options of the unit: ${options}`);
    // In the label line of the field vmax, to the right of its word and no further right than its box (Otto, 1.11.2026).
    const unitBox = await unit.boundingBox();
    const vmaxLabel = page.locator('.result-controls .vc-num').nth(1);
    // The box of the word itself (the span is as wide as the field): the range of its text.
    const vmaxWord = await vmaxLabel.locator('span').evaluate((el) => { const range = document.createRange(); range.selectNodeContents(el); const r = range.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; });
    const vmaxInput = await vmaxLabel.locator('input').boundingBox();
    if (unitBox.y + unitBox.height > vmaxInput.y + 0.5) problems.push('the unit dropdown is not in the label line of vmax');
    if (Math.abs(unitBox.y + unitBox.height / 2 - (vmaxWord.y + vmaxWord.height / 2)) > 8) problems.push('the unit dropdown is not in the row of the word vmax');
    if (unitBox.x + unitBox.width > vmaxInput.x + vmaxInput.width + 0.5) problems.push(`the unit dropdown reaches beyond the box of vmax: ${unitBox.x + unitBox.width} against ${vmaxInput.x + vmaxInput.width}`);
    if (unitBox.x < vmaxWord.x + vmaxWord.width - 0.5) problems.push('the unit dropdown covers the word vmax');
    const text = await unit.evaluate((el) => el.selectedOptions[0].textContent);
    if (text !== 'absolute') problems.push(`the unit starts as "${text}"`);
    await unit.selectOption('percent');
    const fields = await page.locator('.result-controls .vc-num input').evaluateAll((els) => els.map((e) => e.value));
    if (fields.join() !== '2,98') problems.push(`the fields in percentiles: ${fields}`);
    await page.locator('.result-controls .vc-num input').nth(0).fill('3');
    await page.locator('.result-controls .vc-num input').nth(1).fill('97');
    await shot('4b-percent');
    await page.locator('.result-controls .vc-apply').click();
    await page.waitForTimeout(600);
    const url = await state(page, "s.layers.find((l) => l.id === 'res').overlays[0].tileUrl");
    if (!url.includes('rescale=30%2C970')) problems.push(`"Apply" in percentiles drew ${url}`);
    if ((await state(page, "s.layers.find((l) => l.id === 'res').result.percent.low")) !== '3') problems.push('the layer did not keep what was typed');
  }

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
  if (JSON.stringify(names) !== JSON.stringify(['green · 2026-07-06', 'Result · three bands · 2026-07-06'])) problems.push(`layers after "Add band as layer": ${JSON.stringify(names)}`);
  const named = await page.$$eval('.layer-row .lm-name', (n) => n.map((x) => x.textContent));
  if (JSON.stringify(named) !== JSON.stringify(['green · 2026-07-06', 'Result · three bands · 2026-07-06'])) problems.push(`the names with their dates: ${JSON.stringify(named)}`);
  await shot('6-band-layer');

  // --- the box of a layer opened from the layer manager has no row of buttons; a view still open from the search keeps all of it
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const downloaded = { s0: { datasetId: 'optical', tileUrl: '/collections/optical/items/s0/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 } };
    const collection = {
      id: 'optical', title: 'Optical', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'Colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
    };
    const { datasetsFrom } = await import('/src/datasets.ts');
    window.__boxSeed = { downloaded, collection };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', focusMode: true, cropToAoi: false, showDownloaded: true, dock: null,
      downloaded, appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', resultViewLayerId: null, viewOfLayer: true, viewLayerId: 'S1',
      layers: [{
        id: 'S1', name: 'Optical · a crop', date: '2026-07-01', visible: true, opacity: 1, overlays: [],
        restore: { focusMode: true, downloaded, appliedRender: { rescale: '0,3000' }, activeGroupIndex: 0, selectedIds: ['s0'], itemIds: ['s0'], groupItemIds: [['s0']], aoi: null, cropToAoi: false, datasetId: 'optical' },
      }],
    });
  });
  await page.waitForSelector('.scene-view .vc-apply');
  if ((await page.locator('.scene-view .vc-actions').count()) !== 0) problems.push('a layer opened from the manager has a row of buttons');
  if ((await page.locator('.scene-view .vc-head .close-x').count()) !== 1) problems.push('no red x in the box of the layer');
  // The box of every layer (NM4-54 part 5): the opacity of the layer is its row under the fields.
  if ((await page.locator('.scene-view .vc-opacity input[type="range"]').count()) !== 1) problems.push('the box of the layer has no row for its opacity');
  const children = await page.locator('.scene-view > *').evaluateAll((els) => els.map((e) => e.className.split(' ')[0]));
  if (children.join() !== 'vc-head,vc-render,vc-opacity') problems.push(`the box of the layer holds ${children}, not the head, the fields and the opacity`);
  const title = await page.locator('.scene-view .vc-title').textContent();
  if (title !== 'OPTICAL · A CROP · 2026-07-01') problems.push(`the title of the box: ${title}`);
  const boxBox = await page.locator('.scene-view').boundingBox();
  const closeBox = await page.locator('.scene-view .vc-head .close-x').boundingBox();
  if (closeBox.x + closeBox.width > boxBox.x + boxBox.width + 0.5) problems.push('the red x leaves the box');
  await shot('7-layer-box');
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ viewOfLayer: false }));
  await page.waitForSelector('.scene-view .vc-actions');
  if ((await page.locator('.scene-view .vc-actions > *').count()) < 4) problems.push('the view still open from the search lost its buttons');
  await shot('8-view-open');

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
