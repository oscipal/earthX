// The entry "Results" of the layer manager (NM4-59, Otto, 30.10.2026), on a real map. Three scenes of one area in three
// groups, each one solid colour (red newest, green, blue), and a job's result in yellow over the same area; the pixel in the
// middle of the map is read:
//   1. Otto's click path: a group open, nothing ticked, the job pinned (a new layer goes on top: yellow), "Results" put on
//      top by the button left of the eye in the results list (red; the button greyed out then), the eye of "Results" off
//      (yellow) and on again (red), four times, by the eye in the layer manager and by the one in the results list; once
//      with the quicklooks arriving late;
//   2. "Results" moved under the job with ▼: yellow; back with ▲: red;
//   3. a full-resolution view open, a scene of another group ticked, the eye on: the open group lies over the ticked scene.
// Light and dark theme, a wide and a narrow window.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/results-layer.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-results-layer');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const COLOURS = [
  [230, 40, 40],
  [40, 180, 60],
  [50, 90, 230],
];
const JOB = [240, 200, 20];
// The area of the scenes, in UTM 32N, and its corners in degrees.
const BBOX = [7.6, 46.9, 10.4, 48.7];

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

const near = (a, b) => a.every((v, i) => Math.abs(v - b[i]) <= 12);
const store = (page, call, arg) => page.evaluate(async ([c, a]) => (await import('/src/store.ts')).useAppStore.getState()[c](a), [call, arg]);

async function run(browser, { theme, viewport }) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.on('pageerror', (error) => console.log('pageerror', error.message));
  // The quicklooks arrive late while `slow` is set: the order on the map must not depend on when they come.
  let slow = 0;
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const ql = /\/ql\/SYNTH_(\d)\.png/.exec(url.pathname);
    if (ql) {
      const wait = slow * (3 - Number(ql[1]));
      await new Promise((resolve) => setTimeout(resolve, wait));
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: solidPng(COLOURS[Number(ql[1])]) });
    }
    const tile = /\/items\/SYNTH_(\d)\/tiles\//.exec(url.pathname);
    if (tile) return route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(COLOURS[Number(tile[1])]) });
    if (url.pathname.startsWith('/jobtiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(JOB) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(async ({ base, bbox }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const { buildSections } = await import('/src/sections.ts');
    const caps = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
    const datasets = datasetsFrom([
      {
        id: 'synthetic',
        title: 'Synthetic',
        'earthx:capabilities': caps,
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
        'earthx:default_render': { title: 'Grey', assets: ['data'], rescale: [[0, 1]], colormap_name: null, expression: null, resampling: 'nearest' },
      },
    ]);
    const [w, s, e, n] = bbox;
    const features = [0, 1, 2].map((i) => ({
      id: `SYNTH_${i}`,
      collection: 'synthetic',
      bbox,
      geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
      properties: { datetime: `2026-0${7 - i}-01T10:00:00Z`, 'proj:epsg': 32632 },
      assets: {
        thumbnail: { href: `${base}/ql/SYNTH_${i}.png`, type: 'image/png', roles: ['thumbnail'] },
        data: { href: `${base}/data/SYNTH_${i}.tif`, 'proj:transform': [781.25, 0, 400000, 0, -781.25, 5400000], 'proj:shape': [256, 256], roles: ['data'] },
      },
    }));
    const { sections } = buildSections(features, datasets.filter((d) => d.viewable), { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    const open = sections[0];
    useAppStore.setState({
      datasets, sections, openSectionId: open.datasetId, datasetId: open.datasetId, items: open.items, groups: open.groups,
      activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: [], resultsOnMap: true, dock: null,
      flyToView: { center: [9, 47.8], zoom: 7 },
    });
  }, { base: BASE, bbox: BBOX });
  await page.waitForSelector('.time-slider');
  const x = Math.round(win.width * 0.6);
  // High enough to stay clear of the bars of a view, which cover the middle of a narrow window.
  const y = Math.round(win.height * 0.25);
  const settle = async (want) => {
    let c = [0, 0, 0];
    for (let t = 0; t < 6000; t += 100) {
      c = await colourAt(page, x, y);
      if (near(c, want)) return c;
      await page.waitForTimeout(100);
    }
    return c;
  };
  const expectColour = async (what, want) => {
    const c = await settle(want);
    if (!near(c, want)) problems.push(`${what}: expected ${JSON.stringify(want)}, the map shows ${JSON.stringify(c)}`);
  };
  const resultsRow = page.locator('.layer-manager .results-row');
  // A click in a panel of the dock: opened by its symbol on the rail, closed again so that the map is read uncovered
  // (in a narrow window the panel lies over the middle of the map).
  const click = async (panel, locator, what) => {
    await page.locator(`#rail-${panel}`).click();
    if (!(await locator.isVisible())) problems.push(`${what} is not visible`);
    else await locator.click();
    await page.locator(`#rail-${panel}`).click();
  };

  await expectColour('the open group', COLOURS[0]);
  // 1. Otto's click path: the job pinned goes on top, over "Results" (Otto, zu #249).
  await page.evaluate(async (bbox) => {
    (await import('/src/store.ts')).useAppStore.getState().pinDerivedLayer({
      name: 'Job result',
      derived: 'result',
      overlays: [{ kind: 'raster', tileUrl: `${location.origin}/jobtiles/{z}/{x}/{y}.png`, bounds: bbox, minZoom: 0, maxZoom: 14 }],
      itemIds: [],
      cropToAoi: false,
    });
  }, BBOX);
  const rows = await page.locator('.layer-manager .layer-row [data-col="name"]').allTextContents();
  if (rows.join('|') !== 'Job result|Results') problems.push(`the layer manager lists ${rows.join(', ')}`);
  await expectColour('the job pinned over "Results"', JOB);
  await page.locator('#rail-results').click();
  await page.screenshot({ path: path.join(OUT, `to-top button ${name}.png`) });
  await page.locator('#rail-results').click();
  const greyed = () => page.locator('.results-head button[aria-label="Put results on top of the layers"]').getAttribute('aria-disabled');
  if ((await greyed()) !== null) problems.push('the button is greyed out with a layer over "Results"');
  await click('results', page.locator('.results-head button[aria-label="Put results on top of the layers"]'), 'the button "Results" on top');
  if ((await greyed()) !== 'true') problems.push('the button is not greyed out with "Results" on top');
  await page.locator('#rail-results').click();
  await page.screenshot({ path: path.join(OUT, `to-top greyed ${name}.png`) });
  await page.locator('#rail-results').click();
  await expectColour('"Results" on top again', COLOURS[0]);
  await page.screenshot({ path: path.join(OUT, `pinned ${name}.png`) });
  // The eye of the layer manager, then the one of the results list.
  const eyes = [
    ['layers', resultsRow.locator('[data-col="eye"]')],
    ['results', page.locator('.results-head .lm-eye[aria-pressed]')],
  ];
  for (let round = 0; round < 4; round++) {
    if (round === 3) slow = 400;
    const [panel, eye] = eyes[round % 2];
    await click(panel, eye, `the eye in "${panel}" (round ${round})`);
    await expectColour(`eye off (round ${round})`, JOB);
    await click(panel, eye, `the eye in "${panel}" (round ${round})`);
    await expectColour(`eye on again (round ${round})`, COLOURS[0]);
  }
  slow = 0;
  // 2. "Results" under the job, and back.
  await click('layers', resultsRow.locator('[data-col="down"]'), '▼ of "Results"');
  await expectColour('"Results" under the job', JOB);
  await page.locator('#rail-layers').click();
  await page.screenshot({ path: path.join(OUT, `moved ${name}.png`) });
  await page.locator('#rail-layers').click();
  await click('layers', resultsRow.locator('[data-col="up"]'), '▲ of "Results"');
  await expectColour('"Results" over the job again', COLOURS[0]);
  // 3. A view open (another scene, beside the probe), a scene of another group ticked, the eye on.
  await store(page, 'toggleLayerVisible', (await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers[0].id)));
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.setState({
      focusMode: true, cropToAoi: false, showDownloaded: true, appliedRender: {},
      downloaded: { SYNTH_2: { tileUrl: `${location.origin}/collections/synthetic/items/SYNTH_2/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=data`, bounds: [10.2, 46.9, 10.4, 48.7], asset: 'data', minZoom: 0, maxZoom: 14 } },
    });
    useAppStore.getState().toggleSelected('SYNTH_1');
  });
  await expectColour('a view open: the open group over the ticked scene of another group', COLOURS[0]);
  await page.screenshot({ path: path.join(OUT, `view ${name}.png`) });
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
