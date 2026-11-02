// The settings bar at the right edge (UI-03a, Otto, 2.11.2026), in a real browser: a job's result, a pinned view ("Crop to AOI") and the
// view of the search, each drawn as RGB, as one band and as an index. Measured: the bar, its fields and what stands around it.
//   1. Place and size: from 1280 px the bar is flush at the right edge, 320 px wide, from the top to the foot with no gap, the buttons
//      at the top left of it (Otto, 2.11.2026); under 900 px it is a sheet from the
//      bottom, from the rail to the right edge, at most 55 % high.
//   2. The three kinds are one bar: Band, vmin and vmax stand at the same height (counted from the top of the bar) for every kind and every
//      picture; Colormap, Opacity and the row of buttons for every kind of one picture (a colour picture has a row of fields for each
//      channel, UI-03d); "Actions" of a view and a pinned view alike; the colormap of RGB stays, locked, with its reason in the tooltip.
//   3. Nothing lies outside the bar, and nothing scrolls sideways.
//   4. The bar of the selection and the timeline stands in the middle of the free map, not under the bar (under 900 px above the sheet); the
//      zoom buttons are visible and left of the bar (above the sheet).
//   5. A swap (layer to layer), the x, and Esc that closes nothing.
//   6. The height of a control (Otto, 2.11.2026): the fields and the buttons with words are 28 px with a mouse from 900 px, and
//      40–44 px under 900 px and on a touch screen (`--control-height-touch`).
// In the light and the dark theme, at 1280 x 800, 1920 x 1080, 360 x 740 and 1280 x 800 with a touch screen; a screenshot per case (the
// table of places and heights is printed).
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/settings-box.cjs               # BASE=http://localhost:5173 OUT=<directory for the screenshots>, ONLY=1 for one theme and one window
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-settings-box');
const THEMES = process.env.ONLY ? { light: 'normal' } : { light: 'normal', dark: 'tech' };
const VIEWPORTS = process.env.ONLY
  ? { hd: { width: 1280, height: 800 } }
  : { hd: { width: 1280, height: 800 }, full: { width: 1920, height: 1080 }, narrow: { width: 360, height: 740 }, touch: { width: 1280, height: 800, touch: true } };
const RAIL = 48;
const BAR = 320;
const TOP = 0;
const FOOTPRINT = [10, 50, 11, 51];
const SCENES = ['SYNTH_A', 'SYNTH_B'];
// A third scene is ticked and not in the view, so that the bar of the selection stands at the bottom.
const TICKED = 'SYNTH_C';
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
const PRESETS = [['NDVI', 'Normalized Difference Vegetation Index', '(nir - red) / (nir + red)', 'rdylgn', '(N - R)/(N + R)']].map(([name, title, expression, colormap_name, formula]) => ({
  name, title, expression, rescale: [[-1, 1]], colormap_name, formula, reference: 'https://example.org/formula',
}));

async function open(browser, theme, viewport) {
  const { width, height, touch = false } = VIEWPORTS[viewport];
  // A touch screen is `(pointer: coarse)` for the page.
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: touch });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': SCENES });
    if (url.pathname.includes('/statistics')) return json({ b1: { min: 0, max: 4000, percentile_2: 100, percentile_98: 2900 } });
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  return { context, page, problems };
}

// The store of the page: the view of the search with the dataset, then whatever the case needs.
async function seed(page) {
  await page.evaluate(async ({ scenes, ticked, footprint, presets }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 8, maxZoom: 14 });
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const aoi = { type: 'Polygon', coordinates: [[[10.2, 50.2], [10.8, 50.2], [10.8, 50.8], [10.2, 50.8], [10.2, 50.2]]] };
    const tiff = (n) => ({ href: 'https://example.org/x.tif', type: COG, 'raster:bands': Array.from({ length: n }, () => ({ data_type: 'uint16', nodata: 0 })) });
    const items = [...scenes, ticked].map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { visual: tiff(3), B04: tiff(1), B08: tiff(1) } }));
    const collection = {
      id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:true_color': ['red', 'green', 'blue'], 'earthx:auxiliary_assets': ['visual'],
      'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
      'earthx:index_presets': presets,
    };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', items, groups: [{ key: ['a'], label: '2026-07-01', items }], activeGroupIndex: 0,
      selectedIds: [...scenes, ticked], downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: true, viewAoi: aoi, aoi, showDownloaded: true, dock: null,
      appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', layers: [], mosaics: {}, error: null, mapZoom: 12,
      flyToView: { center: [10.5, 50.5], zoom: 10 },
    });
    await useAppStore.getState().loadMosaics();
  }, { scenes: SCENES, ticked: TICKED, footprint: FOOTPRINT, presets: PRESETS });
  await page.waitForSelector('.inspector .vc-apply');
}

const pick = (page, value) => page.locator('.inspector .vc-render label', { hasText: /^Band/ }).locator('select').selectOption(value);
const settle = (page) => page.waitForTimeout(600);

// The look of the view of the search: RGB, a band, an index (chosen and applied).
async function look(page, what) {
  if (what === 'rgb') return;
  // An index is a button of "Quick processing", drawn at once (UI-03d); a band is chosen and applied.
  if (what === 'index') {
    await page.locator('.inspector .vc-quick button', { hasText: 'NDVI' }).click();
    await settle(page);
    return;
  }
  await pick(page, 'band:B04');
  await settle(page);
  await page.locator('.inspector .vc-apply').click();
  await settle(page);
}

// The result layers of a job with the bands red, green, blue and NDVI; the first is drawn as RGB, as the band "red" or as the band "NDVI".
async function resultLayers(page, what) {
  await page.evaluate(async ({ what }) => {
    const { useAppStore } = await import('/src/store.ts');
    const band = what === 'rgb' ? '@rgb' : what === 'band' ? 0 : 3;
    const layer = (id, place) => ({
      id, name: `Result · bands ${id}`, visible: true, opacity: 1, derived: 'result', restore: { datasetId: null, itemIds: [] },
      overlays: [{ kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0%2C1', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
      result: {
        jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null,
        bands: ['red', 'green', 'blue', 'NDVI'].map((name) => ({ name, stats: null })), band: place, colour: [0, 1, 2],
      },
    });
    useAppStore.setState({ focusMode: false, downloaded: {}, viewOfLayer: false, resultViewLayerId: 'R1', dock: 'layers', layers: [layer('R1', band), layer('R2', '@rgb')] });
  }, { what });
  await page.waitForSelector('.result-controls .vc-apply');
}

// The view of a layer pinned from the view of the search (opened again from the layer manager).
async function pinnedBox(page, what) {
  await look(page, what);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().addCurrentToLayers();
    await new Promise((resolve) => setTimeout(resolve, 600));
    const [layer] = useAppStore.getState().layers;
    useAppStore.getState().exitFocus();
    useAppStore.getState().selectLayer(layer.id);
  });
  await page.waitForSelector('.inspector .vc-apply');
}

// What the page measures: the bar, the places of its parts (from its top), what lies outside it, the bands around it.
async function measure(page) {
  return page.evaluate(() => {
    const round = (n) => Math.round(n * 10) / 10;
    const rect = (e) => (e ? (({ x, y, width, height, right, bottom }) => ({ x: round(x), y: round(y), w: round(width), h: round(height), right: round(right), bottom: round(bottom) }))(e.getBoundingClientRect()) : null);
    const bar = document.querySelector('aside.inspector');
    // Under 900 px with controls for a finger the sheet scrolls: measured from its top.
    bar.querySelector('.insp-body').scrollTop = 0;
    const base = rect(bar);
    const field = (name) => [...bar.querySelectorAll('.vc-render label')].find((l) => l.querySelector('span')?.textContent === name);
    const heading = (name) => [...bar.querySelectorAll('.insp-heading')].find((h) => h.textContent === name);
    const at = (e) => {
      const r = rect(e);
      return r && { x: round(r.x - base.x), y: round(r.y - base.y), w: r.w, h: r.h };
    };
    const colormap = field('Colormap')?.querySelector('select');
    const body = bar.querySelector('.insp-body');
    const bottom = document.querySelector('.overlay.bottom .draggable');
    const zoom = document.querySelector('.maplibregl-ctrl-zoom-in');
    const topButtons = rect(document.querySelector('.overlay.top-right'));
    return {
      bar: base,
      scrolls: body.scrollHeight > body.clientHeight + 1,
      sideways: body.scrollWidth > body.clientWidth + 1,
      row1: at(bar.querySelector('.insp-row')),
      row2: at(bar.querySelector('.insp-row2')),
      band: at(field('Band')),
      // A colour picture has a row for each channel (UI-03d): its first row.
      vmin: at(field('vmin') ?? bar.querySelector('.vc-channels .vc-num')),
      vmax: at(field('vmax') ?? bar.querySelectorAll('.vc-channels .vc-num')[1]),
      colormap: at(field('Colormap')),
      opacity: at(field('Opacity')),
      buttons: at(bar.querySelector('.vc-buttons')),
      display: at(heading('Display')),
      actions: at(heading('Actions')),
      colormapLocked: colormap ? colormap.disabled : null,
      colormapTitle: field('Colormap')?.title ?? null,
      outside: [...bar.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > base.right + 1 || r.left < base.x - 1); }).map((e) => e.className || e.tagName).slice(0, 4),
      bands: bottom ? rect(document.querySelector('.overlay.bottom')) : null,
      block: rect(bottom),
      zoom: zoom ? rect(zoom) : null,
      topButtons,
      zoomVisible: zoom ? getComputedStyle(zoom).visibility !== 'hidden' && zoom.getBoundingClientRect().width > 0 : false,
      window: { w: window.innerWidth, h: window.innerHeight },
      // The fields and the buttons with words, in the bar and in the bar of the selection (not the switch of the range, an icon or the grip).
      controls: [...document.querySelectorAll('aside.inspector, .overlay.bottom')]
        .flatMap((root) => [...root.querySelectorAll('select:not(.vc-unit), input[type="number"], input[type="text"], .ghost-btn, .primary-btn, .pp-seg')])
        .filter((e) => e.getBoundingClientRect().height > 0)
        .map((e) => ({ name: (e.textContent || e.getAttribute('aria-label') || e.tagName).trim().slice(0, 24), h: round(e.getBoundingClientRect().height) })),
      // The fields of the bar, one line each: exactly as high as the token.
      fields: [...bar.querySelectorAll('.vc-render select:not(.vc-unit), .vc-render input[type="number"]')].map((e) => round(e.getBoundingClientRect().height)),
    };
  });
}

const KINDS = { job: async (page, what) => resultLayers(page, what), pinned: pinnedBox, search: async (page, what) => look(page, what) };
// The same places for every kind and every picture down to the first row of "Scale"; below it a colour picture is three rows longer and
// has three histograms (UI-03d), so the places below are the same for one picture across the kinds; "Actions" of a result stands
// higher, which has no "Quick processing".
const PLACES = ['row1', 'row2', 'band', 'vmin', 'vmax', 'display'];
const PLACES_OF_A_PICTURE = ['colormap', 'opacity', 'buttons'];
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);

// What one case has to show, whatever the picture and the kind.
function checkCase(tag, m, vp, problems) {
  const narrow = vp.width < 900;
  const { bar } = m;
  if (!narrow) {
    if (bar.right !== vp.width) problems.push(`${tag}: the bar ends at ${bar.right}, not at the right edge (${vp.width})`);
    if (bar.w !== BAR) problems.push(`${tag}: the bar is ${bar.w} wide, not ${BAR}`);
    if (bar.y !== TOP) problems.push(`${tag}: the bar begins at ${bar.y}, not at ${TOP}`);
    if (bar.bottom !== vp.height) problems.push(`${tag}: the bar ends at ${bar.bottom}, not at the foot (${vp.height})`);
    if (!m.topButtons || m.topButtons.right > bar.x) problems.push(`${tag}: the buttons at the top end at ${m.topButtons?.right}, over the bar (${bar.x})`);
  } else {
    if (bar.right !== vp.width || bar.x !== RAIL) problems.push(`${tag}: the sheet spans ${bar.x}…${bar.right}, not ${RAIL}…${vp.width}`);
    if (bar.bottom !== vp.height) problems.push(`${tag}: the sheet ends at ${bar.bottom}, not at the foot (${vp.height})`);
    if (bar.h > vp.height * 0.55 + 1) problems.push(`${tag}: the sheet is ${bar.h} high, more than 55 % of ${vp.height}`);
  }
  if (m.outside.length > 0) problems.push(`${tag}: outside the bar: ${m.outside.join(', ')}`);
  if (m.sideways) problems.push(`${tag}: the bar scrolls sideways`);
  // The bar of the selection stands in the free map, centred, and not under the bar.
  if (!m.bands || !m.block) problems.push(`${tag}: the bar of the selection is not there`);
  else if (!narrow) {
    const centre = (m.bands.x + m.bands.right) / 2;
    const free = (RAIL + bar.x) / 2;
    if (Math.abs(centre - free) > 1.5) problems.push(`${tag}: the bottom bar is centred at ${centre}, the free map at ${free}`);
    if (m.block.right > bar.x) problems.push(`${tag}: the bottom bar ends at ${m.block.right}, under the bar (${bar.x})`);
    if (m.block.x < RAIL) problems.push(`${tag}: the bottom bar begins at ${m.block.x}, over the rail`);
  } else if (m.block.bottom > bar.y + 0.5) problems.push(`${tag}: the bottom bar ends at ${m.block.bottom}, under the sheet (${bar.y})`);
  // The zoom buttons.
  if (!m.zoom) problems.push(`${tag}: no zoom buttons`);
  else if (!m.zoomVisible) problems.push(`${tag}: the zoom buttons are not visible`);
  else if (!narrow && m.zoom.right > bar.x) problems.push(`${tag}: the zoom buttons end at ${m.zoom.right}, under the bar (${bar.x})`);
  else if (narrow && m.zoom.bottom > bar.y + 0.5) problems.push(`${tag}: the zoom buttons end at ${m.zoom.bottom}, under the sheet (${bar.y})`);
  // The height of a control: 28 px for a mouse, 40–44 px for a finger.
  const finger = narrow || vp.touch === true;
  if (m.controls.length === 0) problems.push(`${tag}: no control measured`);
  const low = finger ? 40 : 28;
  const wrong = m.controls.filter(({ h }) => h < low - 0.5);
  if (wrong.length > 0) problems.push(`${tag}: controls lower than ${low} px: ${wrong.slice(0, 4).map((c) => `${c.name} ${c.h}`).join(', ')}`);
  const height = finger ? [40, 44] : [28, 28];
  const off = m.fields.filter((h) => h < height[0] - 0.5 || h > height[1] + 0.5);
  if (m.fields.length === 0 || off.length > 0) problems.push(`${tag}: the fields of the bar are ${JSON.stringify(m.fields)} px high, not ${height.join('–')}`);
}

// A swap, the x, and Esc that closes nothing.
async function behaviour(browser, theme, viewport, problems) {
  const tag = `${theme} ${viewport}`;
  const { context, page, problems: own } = await open(browser, theme, viewport);
  await seed(page);
  await resultLayers(page, 'rgb');
  await page.evaluate(() => { window.__bar = document.querySelector('aside.inspector'); });
  const title = () => page.locator('aside.inspector .vc-title').textContent();
  const first = await title();
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().selectLayer('R2'));
  await settle(page);
  const sameBar = await page.evaluate(() => window.__bar === document.querySelector('aside.inspector') && window.__bar.isConnected);
  if (!sameBar) problems.push(`${tag}: the bar was made again for the next layer`);
  if ((await title()) === first) problems.push(`${tag}: the title did not change with the layer`);
  await page.locator('aside.inspector .close-x').click();
  if ((await page.locator('aside.inspector').count()) !== 0) problems.push(`${tag}: the x did not close the bar of a layer`);
  // Esc closes nothing (Otto, 2.11.2026): not the bar of a layer, not the view of the search, not from a field.
  await resultLayers(page, 'rgb');
  await page.keyboard.press('Escape');
  if ((await page.locator('aside.inspector').count()) !== 1) problems.push(`${tag}: Esc closed the bar of a layer`);
  await seed(page);
  await page.keyboard.press('Escape');
  if ((await page.locator('aside.inspector').count()) !== 1) problems.push(`${tag}: Esc closed the view of the search`);
  await page.locator('aside.inspector .vc-num input').first().focus();
  await page.keyboard.press('Escape');
  if ((await page.locator('aside.inspector').count()) !== 1) problems.push(`${tag}: Esc in a field closed the bar`);
  await page.locator('aside.inspector .close-x').click();
  if ((await page.locator('aside.inspector').count()) !== 0) problems.push(`${tag}: the x did not close the view of the search`);
  problems.push(...own.map((p) => `${tag}: ${p}`));
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const problems = [];
  const rows = [];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const found = {};
      for (const kind of Object.keys(KINDS)) {
        for (const what of ['rgb', 'band', 'index']) {
          const { context, page, problems: own } = await open(browser, theme, viewport);
          await seed(page);
          await KINDS[kind](page, what);
          await settle(page);
          found[`${kind}/${what}`] = await measure(page);
          checkCase(`${kind}/${what} ${theme} ${viewport}`, found[`${kind}/${what}`], VIEWPORTS[viewport], problems);
          await page.screenshot({ path: path.join(OUT, `${kind}_${what}_${theme}_${viewport}.png`) });
          problems.push(...own.map((p) => `${kind}/${what} ${theme} ${viewport}: ${p}`));
          await context.close();
        }
      }
      // The same places for every kind and every picture.
      const reference = found['job/rgb'];
      const tag = `${theme} ${viewport}`;
      for (const [name, m] of Object.entries(found)) {
        for (const place of PLACES) {
          // The rows of a colour picture have the letter of the channel in front (UI-03d): vmin and vmax keep their height, not their x.
          const height = (r) => (r && (place === 'vmin' || place === 'vmax') ? { y: r.y, h: r.h } : r);
          if (!same(height(reference[place]), height(m[place]))) problems.push(`${tag}: "${place}" of ${name} is at ${JSON.stringify(m[place])}, of job/rgb at ${JSON.stringify(reference[place])}`);
        }
        const what = name.split('/')[1];
        const own = found[`job/${what}`];
        for (const place of PLACES_OF_A_PICTURE) if (!same(own[place], m[place])) problems.push(`${tag}: "${place}" of ${name} is at ${JSON.stringify(m[place])}, of job/${what} at ${JSON.stringify(own[place])}`);
        if (name.startsWith('search/') && !same(found[`pinned/${what}`].actions, m.actions)) problems.push(`${tag}: "Actions" of ${name} is at ${JSON.stringify(m.actions)}, of pinned/${what} at ${JSON.stringify(found[`pinned/${what}`].actions)}`);
      }
      for (const kind of Object.keys(KINDS)) {
        const [rgb, band] = ['rgb', 'band'].map((what) => found[`${kind}/${what}`]);
        if (rgb.colormapLocked !== true || !rgb.colormapTitle) problems.push(`${tag}: the colormap of RGB (${kind}) is not locked with its reason (${JSON.stringify([rgb.colormapLocked, rgb.colormapTitle])})`);
        if (band.colormapLocked !== false) problems.push(`${tag}: the colormap of a band (${kind}) is locked`);
        const m = found[`${kind}/rgb`];
        rows.push(`${theme.padEnd(5)} ${viewport.padEnd(6)} ${kind.padEnd(7)} bar ${m.bar.x},${m.bar.y} ${m.bar.w}x${m.bar.h}  band y${m.band.y} vmin y${m.vmin.y} vmax y${m.vmax.y} cmap y${m.colormap.y} opacity y${m.opacity.y} buttons y${m.buttons.y} actions y${m.actions.y}  bottom ${m.block ? `${m.block.x}…${m.block.right} y${m.block.y}` : '-'}  zoom ${m.zoom ? `${m.zoom.x}…${m.zoom.right}` : '-'}  controls ${Math.min(...m.controls.map((c) => c.h))}…${Math.max(...m.controls.map((c) => c.h))}`);
      }
    }
    for (const viewport of Object.keys(VIEWPORTS)) await behaviour(browser, theme, viewport, problems);
  }
  await browser.close();
  console.log(rows.join('\n'));
  console.log(problems.length === 0 ? 'ok: one bar' : `FAIL\n${problems.join('\n')}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(problems.length === 0 ? 0 : 1);
})();
