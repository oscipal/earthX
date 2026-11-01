// The view of scenes steps through its images (NM4-53, Otto, 31.10.2026, zu #257): two overpasses of a Sentinel-2 like
// dataset (three bands, RGB) and one elevation tile, ticked, then "Crop & merge to AOI". Each scene is one solid colour,
// and the pixel in the middle of the map is read:
//   1. the view opens with the image of the group that is open (green, the later overpass); the head says the date only (no satellite)
//      between the title and the eye, with the dataset to choose, and the title has no date;
//   2. "‹" shows the earlier overpass (red), "›" the later again; the arrows are greyed out at the ends;
//   3. the arrow keys step while an arrow has the focus;
//   4. the dropdown shows the elevation tile (blue); the box of the colormap is where it was for both, offering RGB and nothing else
//      for the Sentinel-2 images, and the arrows are greyed out for a dataset of one image;
//   5. "Add to layers" pins the image shown, "Add all to layers" every image, one layer each;
//   6. the head, the dropdown and the buttons stay inside the panel, and the panel inside the window; "Apply to all" is always there;
//   7. in a wide window the panel is the head and two rows (all its buttons in one row), and wider than high.
// Light and dark theme, a wide and a narrow window.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/view-steps.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-view-steps');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const COLOURS = { S2_A: [230, 40, 40], S2_B: [40, 180, 60], DEM_1: [50, 90, 230] };
const NAMES = { S2_A: 'red (2025-07-29)', S2_B: 'green (2025-08-03)', DEM_1: 'blue (elevation)' };

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

async function colourAt(page, x, y) {
  const shot = await page.screenshot({ clip: { x, y, width: 1, height: 1 }, type: 'png' });
  return page.evaluate(async (b64) => {
    const img = new Image();
    img.src = `data:image/png;base64,${b64}`;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = c.height = 1;
    const ctx = c.getContext('2d');
    ctx.drawImage(img, 0, 0);
    return [...ctx.getImageData(0, 0, 1, 1).data].slice(0, 3);
  }, shot.toString('base64'));
}

const near = (a, b) => a.every((v, i) => Math.abs(v - b[i]) <= 28);

async function run(browser, { theme, viewport }) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.on('pageerror', (error) => console.log('pageerror', error.message));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const tile = /\/items\/(S2_A|S2_B|DEM_1)\/tiles\//.exec(url.pathname);
    if (tile) return route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(COLOURS[tile[1]]) });
    if (url.pathname.endsWith('/statistics')) {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ b1: { min: 0, max: 255, percentile_2: 5, percentile_98: 250 } }) });
    }
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const { buildSections } = await import('/src/sections.ts');
    const caps = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
    const viewer = (groupBy) => ({ group_by: [groupBy], min_zoom: 0, max_zoom: 14, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: [groupBy] });
    const datasets = datasetsFrom([
      {
        id: 's2',
        title: 'Sentinel-2 L2A',
        'earthx:capabilities': caps,
        'earthx:viewer': viewer('datetime'),
        'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255], [0, 255], [0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
        'earthx:true_color': ['red', 'green', 'blue'],
        'earthx:search_filters': [
          { property: 'platform', kind: 'values', title: 'Satellite', group: 'Acquisition', description: 'The satellite.', oneOf: [{ const: 'sentinel-2a', title: 'Sentinel-2A' }, { const: 'sentinel-2b', title: 'Sentinel-2B' }] },
        ],
      },
      {
        id: 'dem',
        title: 'Copernicus DEM',
        'earthx:capabilities': { ...caps, time_range: false },
        'earthx:viewer': viewer('start_datetime'),
        'earthx:default_render': { title: 'Elevation', assets: ['data'], rescale: [[0, 5000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
      },
    ]);
    const bbox = [-90, -70, 100, 84];
    const features = [
      { id: 'S2_A', collection: 's2', bbox, properties: { datetime: '2025-07-29T10:00:00Z', platform: 'sentinel-2a' }, assets: {} },
      { id: 'S2_B', collection: 's2', bbox, properties: { datetime: '2025-08-03T10:00:00Z', platform: 'sentinel-2b' }, assets: {} },
      { id: 'DEM_1', collection: 'dem', bbox, properties: { start_datetime: '2011-01-01T00:00:00Z' }, assets: {} },
    ];
    const { sections } = buildSections(features, datasets.filter((d) => d.viewable), { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    const open = sections.find((s) => s.datasetId === 's2');
    useAppStore.setState({
      datasets,
      selectedDatasetIds: ['s2', 'dem'],
      sections,
      openSectionId: open.datasetId,
      datasetId: open.datasetId,
      items: open.items,
      groups: open.groups,
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
      selectedIds: ['S2_A', 'S2_B', 'DEM_1'],
      aoi: { type: 'Polygon', coordinates: [[[-60, -60], [80, -60], [80, 80], [-60, 80], [-60, -60]]] },
      layers: [],
      dock: null,
      flyToView: { center: [10, 35], zoom: 3 },
    });
  });
  const x = Math.round(win.width * 0.5);
  const y = Math.round(win.height * 0.2);
  const settle = async (want) => {
    let c = [0, 0, 0];
    for (let t = 0; t < 8000; t += 100) {
      c = await colourAt(page, x, y);
      if (near(c, COLOURS[want])) return c;
      await page.waitForTimeout(100);
    }
    return c;
  };
  const expectColour = async (what, want) => {
    const c = await settle(want);
    if (!near(c, COLOURS[want])) problems.push(`${what}: expected ${NAMES[want]}, the map shows ${JSON.stringify(c)}`);
  };
  const read = (expr) => page.evaluate(async (e) => { const { useAppStore } = await import('/src/store.ts'); return new Function('s', `return ${e}`)(useAppStore.getState()); }, expr);
  const text = (selector) => page.locator(selector).first().textContent();

  // 1. Crop & merge over two overpasses and the elevation tile.
  await page.getByRole('button', { name: 'Crop & merge to AOI' }).click();
  await page.waitForSelector('.vc-head .vc-stepper');
  await expectColour('the open group (the later overpass) first', 'S2_B');
  const row = () => text('.vc-step-text');
  if ((await row()) !== '2025-08-03') problems.push(`the switcher says ${JSON.stringify(await row())}, expected "2025-08-03"`);
  if (/\d{4}-\d{2}-\d{2}/.test(await page.locator('.vc-title').first().textContent())) problems.push('the title of the head has a date');
  const order = await page.evaluate(() => [...document.querySelector('.vc-head').children].map((el) => el.className.split(' ')[0]));
  if (order.join() !== 'vc-title,vc-dataset,vc-stepper,vc-eye') problems.push(`the head holds ${order.join(', ')}`);
  if ((await page.getByRole('button', { name: 'Apply to all' }).count()) !== 1) problems.push('"Apply to all" is not there');
  const colormapBox = () => page.evaluate(() => {
    const label = [...document.querySelectorAll('.vc-field')].find((l) => l.querySelector('span')?.textContent === 'Colormap');
    if (!label) return null;
    const r = label.getBoundingClientRect();
    return { x: Math.round(r.x), y: Math.round(r.y), options: [...label.querySelectorAll('option')].map((o) => o.textContent) };
  });
  const rgbBox = await colormapBox();
  if (!rgbBox || rgbBox.options.join() !== 'RGB') problems.push(`the box of the colormap for RGB says ${JSON.stringify(rgbBox)}`);
  await page.screenshot({ path: path.join(OUT, `first ${name}.png`) });

  // 2. Arrows.
  await page.getByRole('button', { name: 'Previous image' }).click();
  await expectColour('"‹" shows the earlier overpass', 'S2_A');
  if ((await row()) !== '2025-07-29') problems.push(`the switcher says ${JSON.stringify(await row())} after "‹"`);
  if ((await page.getByRole('button', { name: 'Previous image' }).getAttribute('aria-disabled')) !== 'true') problems.push('"‹" is not greyed out at the first image');
  await page.getByRole('button', { name: 'Next image' }).click();
  await expectColour('"›" shows the later overpass again', 'S2_B');
  if ((await page.getByRole('button', { name: 'Next image' }).getAttribute('aria-disabled')) !== 'true') problems.push('"›" is not greyed out at the last image');

  // 3. Keys while an arrow has the focus.
  await page.getByRole('button', { name: 'Next image' }).focus();
  await page.keyboard.press('ArrowLeft');
  await expectColour('the left key steps back', 'S2_A');
  await page.keyboard.press('ArrowRight');
  await expectColour('the right key steps on', 'S2_B');

  // 4. The dataset.
  await page.selectOption('select[aria-label="Dataset"]', 'dem');
  await expectColour('the dropdown shows the elevation tile', 'DEM_1');
  if (!((await page.locator('.vc-title').first().getAttribute('title')) ?? '').includes('Copernicus DEM')) problems.push('the tooltip of the head does not name the elevation model');
  const demBox = await colormapBox();
  if (!demBox || demBox.options[0] !== '— none —') problems.push(`the elevation image has no colormap box: ${JSON.stringify(demBox)}`);
  if (demBox && rgbBox && (Math.abs(demBox.x - rgbBox.x) > 1 || Math.abs(demBox.y - rgbBox.y) > 1)) problems.push(`the colormap box moved: ${JSON.stringify(rgbBox)} -> ${JSON.stringify(demBox)}`);
  if (!(await row())) problems.push('a dataset of one image has no date');
  for (const name of ['Previous image', 'Next image']) {
    if ((await page.getByRole('button', { name }).getAttribute('aria-disabled')) !== 'true') problems.push(`"${name}" is not greyed out for a dataset of one image`);
  }
  if ((await page.getByRole('button', { name: 'Apply to all' }).getAttribute('aria-disabled')) !== 'true') problems.push('"Apply to all" is not locked for a dataset of one image');
  if (!(await page.getByRole('button', { name: 'Apply to all' }).getAttribute('title')).includes('only one image')) problems.push('"Apply to all" does not say why it is locked');
  await page.screenshot({ path: path.join(OUT, `dem ${name}.png`) });
  await page.selectOption('select[aria-label="Dataset"]', 's2');
  await expectColour('back to the first overpass of the dataset', 'S2_A');

  // 5. Apply keeps to one image; "Apply to all" opens with a change and takes it for the dataset.
  await page.locator('.vc-num input').first().fill('10');
  await page.getByRole('button', { name: 'Apply', exact: true }).click();
  await page.getByRole('button', { name: 'Next image' }).click();
  const rescale = await read('s.appliedRender.rescale');
  if (rescale !== '0,255') problems.push(`the next image took the look of the previous one: ${rescale}`);
  await page.getByRole('button', { name: 'Apply to all' }).click();
  const saved = await read('JSON.stringify(s.savedLooks.s2)');
  if (!saved || !saved.includes('255')) problems.push(`"Apply to all" did not save a look for the dataset: ${saved}`);

  // 6. Layers.
  await page.getByRole('button', { name: '＋ Add to layers' }).click();
  if ((await read('s.layers.length')) !== 1) problems.push('"Add to layers" did not pin exactly the image shown');
  await page.getByRole('button', { name: '＋ Add all to layers' }).click();
  const names = await read('s.layers.map((l) => l.name)');
  if (names.length !== 4) problems.push(`"Add all to layers" left ${names.length} layers, expected 4`);
  if (!names.some((n) => n.includes('S2B'))) problems.push(`no layer is named after the satellite: ${JSON.stringify(names)}`);
  await page.screenshot({ path: path.join(OUT, `layers ${name}.png`) });

  // 7. Head and two rows: all the buttons of the second row lie in one row, and in a wide window the panel is wider than high.
  const shape = await page.evaluate(() => {
    const panel = document.querySelector('.scene-view').getBoundingClientRect();
    const tops = [...document.querySelectorAll('.scene-view .vc-actions > *')].map((b) => Math.round(b.getBoundingClientRect().top));
    const heads = [...document.querySelectorAll('.scene-view .vc-head, .scene-view .vc-render, .scene-view .vc-actions')].map((r) => Math.round(r.getBoundingClientRect().top));
    return { width: panel.width, height: panel.height, oneRow: new Set(tops).size === 1, rows: new Set(heads).size };
  });
  if (win.width >= 600) {
    if (!shape.oneRow) problems.push('the buttons of the second row are not in one row');
    if (shape.height >= shape.width) problems.push(`the panel is not wider than high (${shape.width} x ${shape.height})`);
    if (shape.rows !== 3) problems.push(`the panel is not the head and two rows (${shape.rows} rows)`);
  }
  await page.screenshot({ path: path.join(OUT, `shape ${name}.png`) });

  // 8. Everything inside the panel and the panel inside the window.
  const fit = await page.evaluate(() => {
    const panel = document.querySelector('.scene-view');
    const box = panel.getBoundingClientRect();
    const bad = [];
    for (const el of panel.querySelectorAll('.vc-head, .vc-head *, .vc-actions > *, .vc-render > *')) {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && (r.left < box.left - 1 || r.right > box.right + 1)) bad.push(el.className || el.tagName);
    }
    const wide = [...document.querySelectorAll('body *')].filter((el) => !el.closest('.status') && el.getBoundingClientRect().right > innerWidth + 1 && getComputedStyle(el).position !== 'fixed').slice(0, 5).map((el) => `${el.tagName}.${String(el.className).slice(0, 40)}`);
    return { bad, wide, panelRight: box.right, panelLeft: box.left, window: innerWidth, scroll: document.documentElement.scrollWidth };
  });
  if (fit.bad.length) problems.push(`outside the panel: ${fit.bad.join(', ')}`);
  if (fit.panelRight > fit.window + 1 || fit.panelLeft < -1) problems.push(`the panel is outside the window (${fit.panelLeft}..${fit.panelRight} of ${fit.window})`);
  // The toast of the status bar is not part of the view and is left out of this check.
  if (fit.wide.length > 0) problems.push(`the page scrolls sideways (${fit.scroll} > ${fit.window}): ${fit.wide.join(' | ')}`);
  await context.close();
  return { name, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const { name, problems } = await run(browser, { theme, viewport });
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
      for (const problem of problems) console.log(`       ${problem}`);
      failed += problems.length;
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
