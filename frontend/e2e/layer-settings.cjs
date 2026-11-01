// Browser check of the settings of a layer (NM4-50, Otto 29.10.2026 and 30.10.2026, zu #234): in the settings of a result
// layer, of a pinned scene layer and in a view that is no layer's "Apply" stands under "auto-scale" (one button, one width),
// "Save" (in the view: "Apply to all", always there since #257) beside "Apply", and the cluster is no higher than the row of the fields. "Apply" and "Save" are locked while there is nothing to do and
// say why; "Apply" draws the layer with the typed look, what is not saved goes when the settings are closed, "Save" keeps it.
// Light and dark theme, a wide and a narrow window; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the tiles are made up here
//   node e2e/layer-settings.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-layer-settings');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
const within = (inner, outer) => inner.x >= outer.x - 0.5 && inner.y >= outer.y - 0.5 && inner.x + inner.width <= outer.x + outer.width + 0.5 && inner.y + inner.height <= outer.y + outer.height + 0.5;

async function check(browser, { kind, theme, viewport }) {
  const label = `${kind} ${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const tiles = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.includes('/tiles/') || url.pathname.startsWith('/results/')) {
      tiles.push(url.pathname + url.search);
      return route.fulfill({ status: 404, body: '' });
    }
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  await page.evaluate(async ({ kind }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    if (kind === 'result') {
      const future = new Date(Date.now() + 86_400_000).toISOString();
      useAppStore.setState({
        // A narrow window is covered by the open panel: the settings are looked at with it shut.
        dock: window.innerWidth < 600 ? null : 'layers',
        layers: [{
          id: 'R1', name: 'Result · Band math', visible: true, opacity: 1, derived: 'result',
          overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=180%2C1900', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
          result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: future, gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null },
          restore: { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null },
        }],
        resultViewLayerId: 'R1',
      });
    } else {
      const downloaded = { s0: { tileUrl: '/collections/optical/items/s0/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual', bounds: [10, 50, 11, 51], asset: 'visual', minZoom: 8, maxZoom: 14 } };
      const collection = {
        id: 'optical', title: 'Optical', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
        'earthx:default_render': { title: 'Colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      };
      useAppStore.setState({
        datasets: datasetsFrom([collection]), datasetId: 'optical', focusMode: true, cropToAoi: false, showDownloaded: true, dock: null,
        downloaded, appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000',
        flyToView: { center: [10.5, 50.5], zoom: 9 },
        ...(kind === 'layer' ? { viewLayerId: 'S1', layers: [{
          id: 'S1', name: 'Optical · day', visible: true, opacity: 1,
          overlays: [{ kind: 'raster', tileUrl: '/collections/optical/items/s0/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual&rescale=0%2C3000', bounds: [10, 50, 11, 51], minZoom: 8, maxZoom: 14 }],
          restore: { focusMode: true, downloaded, appliedRender: { rescale: '0,3000' }, activeGroupIndex: 0, selectedIds: ['s0'], itemIds: ['s0'], groupItemIds: [['s0']], aoi: null, cropToAoi: false, datasetId: 'optical' },
        }] } : {}),
      });
    }
  }, { kind });
  const root = kind === 'result' ? '.result-controls' : '.scene-view';
  // "Apply to all" is in every view since #257; locked with its reason where it has nothing to do: in a layer's view the layer is
  // saved as it is drawn, in a view of one image there is no other image to draw alike.
  const hasSave = true;
  const lockedSaveTip = { result: 'Nothing to save: the layer is saved as it is drawn', layer: 'Nothing to apply to all: the layer is saved as it is drawn', view: 'Nothing to apply to all: this dataset has only one image in the view' }[kind];
  await page.waitForSelector(`${root} .vc-apply`);
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  const box = (selector) => page.locator(`${root} ${selector}`).first().boundingBox();
  const disabled = (selector) => page.locator(`${root} ${selector}`).first().getAttribute('aria-disabled');
  const tip = (selector) => page.locator(`${root} ${selector}`).first().getAttribute('title');

  // Layout: the cluster under the fields' row height, "Apply" under "auto", "Save" beside "Apply", nothing over the edge.
  const panel = await box('');
  const cluster = await box('.vc-buttons');
  const auto = await box('.vc-buttons > :nth-child(1)');
  const apply = await box('.vc-buttons > :nth-child(2)');
  const save = hasSave ? await box('.vc-buttons > :nth-child(3)') : null;
  if (Math.abs(auto.width - apply.width) > 1) problems.push(`"auto-scale" is ${auto.width.toFixed(1)} px wide, "Apply" ${apply.width.toFixed(1)} px`);
  if ((await page.locator(`${root} .vc-buttons > :nth-child(1)`).textContent())?.trim() !== 'auto-scale') problems.push('the first button is not "auto-scale"');
  const input = await page.locator(`${root} .vc-field input`).first().boundingBox();
  if (Math.abs(cluster.height - input.height) > 1.5) problems.push(`the buttons are ${cluster.height.toFixed(1)} px high, the input of the fields ${input.height.toFixed(1)} px`);
  if (Math.abs(auto.height + apply.height + 4 - cluster.height) > 1.5) problems.push('"auto-scale" and "Apply" together are not as high as the buttons');
  if (Math.abs(auto.height - apply.height) > 1 || Math.abs(auto.width - apply.width) > 1) problems.push('"auto-scale" and "Apply" are not of one size');
  if (hasSave) {
    const saveBox = await box('.vc-buttons > :nth-child(3)');
    if (Math.abs(saveBox.height - cluster.height) > 1.5) problems.push(`"Save" is ${saveBox.height.toFixed(1)} px high, the buttons together ${cluster.height.toFixed(1)} px`);
  }
  // Of one format, and only "Save" blue (the background of a primary button).
  const looks = await page.locator(`${root} .vc-buttons > button`).evaluateAll((els) => els.map((el) => { const c = getComputedStyle(el); return { name: el.textContent.trim(), bg: c.backgroundColor, border: c.borderTopWidth + c.borderTopStyle, size: c.fontSize, radius: c.borderRadius }; }));
  const [lookAuto, lookApply] = looks;
  if (lookAuto.bg !== lookApply.bg || lookAuto.border !== lookApply.border || lookAuto.size !== lookApply.size || lookAuto.radius !== lookApply.radius) problems.push(`"auto-scale" and "Apply" look different: ${JSON.stringify([lookAuto, lookApply])}`);
  if (hasSave && looks[2].bg === lookApply.bg) problems.push('"Save" is not set off from "Apply" by its colour');
  if (apply.y < auto.y + auto.height - 0.5) problems.push('"Apply" is not under "auto"');
  if (save && (save.y > auto.y + 1 || save.y + save.height < apply.y + apply.height - 1)) problems.push('"Save" does not stand beside both "auto-scale" and "Apply"');
  if (save && save.x < apply.x + apply.width - 0.5) problems.push('"Save" is not right of "Apply"');
  if (save && overlap(apply, save)) problems.push('"Apply" and "Save" overlap');
  if (overlap(auto, apply)) problems.push('"auto" and "Apply" overlap');
  for (const [name, b] of [['auto', auto], ['Apply', apply], ['Save', save]]) if (b && !within(b, panel)) problems.push(`"${name}" leaves the panel`);
  if (viewport === 'wide') {
    const fields = await page.locator(`${root} .vc-render > .vc-field`).evaluateAll((els) => els.slice(0, 3).map((el) => el.getBoundingClientRect().toJSON()));
    // By their bottoms: the field vmin has the unit dropdown over its label (NM4-65), so its top is higher.
    if (fields.some((f) => Math.abs(f.y + f.height - (fields[0].y + fields[0].height)) > 4)) problems.push('the three fields are not on one line');
    if (fields.some((f) => f.y + f.height < apply.y + apply.height - 1.5)) problems.push('the buttons stand lower than the fields');
  }
  const sideways = await page.evaluate((sel) => { const el = document.querySelector(sel); return el ? el.scrollWidth > el.clientWidth + 1 : false; }, root);
  if (sideways) problems.push('the panel scrolls sideways');
  await shot('1-opened');

  // Locked while there is nothing to do, with the reason.
  if (await disabled('.vc-apply') !== 'true') problems.push('"Apply" is open though nothing changed');
  if ((await tip('.vc-apply')) !== 'Nothing to apply: the map shows these values') problems.push(`the tooltip of the locked "Apply": ${await tip('.vc-apply')}`);
  if (hasSave) {
    if (await disabled('.vc-save') !== 'true') problems.push('"Save" is open though nothing changed');
    if ((await tip('.vc-save')) !== lockedSaveTip) problems.push(`the tooltip of the locked "Save": ${await tip('.vc-save')}`);
  }

  // Typing opens them; "Apply" draws; the map asks for tiles with the new look.
  const vmax = page.locator(`${root} .vc-field input`).nth(1);
  await vmax.fill('2000');
  if (await disabled('.vc-apply') === 'true') problems.push('"Apply" stays locked after a change');
  // A view of one image has no other image to draw alike: its "Apply to all" stays locked.
  if (kind !== 'view' && await disabled('.vc-save') === 'true') problems.push('"Save" stays locked after a change');
  tiles.length = 0;
  await page.locator(`${root} .vc-apply`).click();
  await page.waitForTimeout(1200);
  if (!tiles.some((t) => t.includes('rescale=') && t.includes('2000'))) problems.push(`no tile asked for the applied look: ${tiles.slice(0, 2).join(' | ')}`);
  if (await disabled('.vc-apply') !== 'true') problems.push('"Apply" is open again right after it was used');
  await shot('2-applied');

  if (kind === 'result') {
    // Not saved: closing it takes the look back, the tiles are asked for with the saved look.
    if (await disabled('.vc-save') === 'true') problems.push('"Save" is locked after "Apply" though nothing is saved');
    tiles.length = 0;
    await page.locator('.result-controls .close-x').click();
    await page.waitForTimeout(1200);
    if (!tiles.some((t) => t.includes('1900'))) problems.push(`the saved look was not drawn again after the settings were closed: ${tiles.slice(0, 2).join(' | ')}`);
    const url = await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers[0].overlays[0].tileUrl);
    if (!url.includes('rescale=180%2C1900')) problems.push(`the layer was not left as saved: ${url}`);
    // Again, and this time saved.
    // The click on the layer's name, as the store takes it.
    await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().selectLayer('R1'));
    await page.waitForSelector(`${root} .vc-apply`);
    await page.locator(`${root} .vc-field input`).nth(1).fill('2100');
    await page.locator(`${root} .vc-save`).click();
    await page.waitForTimeout(800);
    if (await disabled('.vc-save') !== 'true') problems.push('"Save" is open right after it was used');
    await page.locator('.result-controls .close-x').click();
    const kept = await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers[0].overlays[0].tileUrl);
    if (!kept.includes('rescale=180%2C2100')) problems.push(`"Save" did not keep the look: ${kept}`);
    await shot('3-saved');
  }
  if (kind === 'layer') {
    // The settings of a pinned layer: closing them loses what was applied; "Save" keeps it for the layer.
    const layerUrl = () => page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers[0].overlays[0].tileUrl);
    if (!(await layerUrl()).includes('rescale=0%2C3000')) problems.push('"Apply" changed the layer');
    await page.getByRole('button', { name: /Clear/ }).click();
    await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().selectLayer('S1'));
    await page.waitForSelector(`${root} .vc-apply`);
    if ((await page.locator(`${root} .vc-field input`).nth(1).inputValue()) !== '3000') problems.push('the settings show the applied look after they were closed and opened again');
    await page.locator(`${root} .vc-field input`).nth(1).fill('2100');
    await page.locator(`${root} .vc-save`).click();
    await page.waitForTimeout(800);
    if (await disabled('.vc-save') !== 'true') problems.push('"Save" is open right after it was used');
    if (!(await layerUrl()).includes('rescale=0%2C2100')) problems.push(`"Save" did not keep the look for the layer: ${await layerUrl()}`);
    await shot('3-saved');
  }
  await context.close();
  return { name: label, problems, detail: `${tiles.length} tile requests after the last step` };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const kind of ['result', 'layer', 'view']) {
    for (const theme of Object.keys(THEMES)) {
      for (const viewport of Object.keys(VIEWPORTS)) {
        const result = await check(browser, { kind, theme, viewport }).catch((error) => ({ name: `${kind} ${theme} ${viewport}`, problems: [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`], detail: '' }));
        failed += result.problems.length > 0 ? 1 : 0;
        console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name}${result.detail ? ` — ${result.detail}` : ''}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
      }
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
