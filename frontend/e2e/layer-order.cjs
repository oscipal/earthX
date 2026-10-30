// The order of the layers while looking through the results (NM4-55, Otto, 30.10.2026, zu #242): what is looked at lies on
// top. A scene that is ticked in one group does not hide the quicklooks of the group that is opened, nor of the step that is
// played; back in the group of the ticked scene, that scene is over the others of its group.
// Each scene is one solid colour (one scene per group, the same area), and the pixel in the middle of the map is read:
//   1. the scene of the oldest group is ticked, another group is opened: the colour of the opened group is on the map;
//   2. the timeline plays over the ticked scene: every step shows its own colour;
//   3. back in the group of the ticked scene: its colour.
// Light and dark theme, a wide and a narrow window.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/layer-order.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-layer-order');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
// Newest group first, as the groups are: index 0 is the newest, 2 the oldest (the scene that is ticked).
const COLOURS = [
  [230, 40, 40],
  [40, 180, 60],
  [50, 90, 230],
];
const NAMES = ['red (newest)', 'green', 'blue (oldest, ticked)'];

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
    const tile = /\/items\/SYNTH_(\d)\/tiles\//.exec(url.pathname);
    if (tile) return route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(COLOURS[Number(tile[1])]) });
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
    const datasets = datasetsFrom([
      {
        id: 'synthetic',
        title: 'Synthetic',
        'earthx:capabilities': caps,
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['datetime'] },
        'earthx:default_render': { title: 'Grey', assets: ['data'], rescale: [[0, 1]], colormap_name: null, expression: null, resampling: 'nearest' },
      },
    ]);
    const features = [0, 1, 2].map((n) => ({
      id: `SYNTH_${n}`,
      collection: 'synthetic',
      bbox: [-20, 30, 40, 60],
      properties: { datetime: `2026-0${7 - n}-01T10:00:00Z` },
      assets: {},
    }));
    const { sections } = buildSections(features, datasets.filter((d) => d.viewable), { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    const open = sections[0];
    useAppStore.setState({
      datasets,
      sections,
      openSectionId: open.datasetId,
      datasetId: open.datasetId,
      items: open.items,
      groups: open.groups,
      activeGroupIndex: 2,
      expandedGroupIndex: 2,
      selectedIds: ['SYNTH_2'],
      dock: null,
      flyToView: { center: [10, 45], zoom: 3 },
    });
  });
  await page.waitForSelector('.time-slider');
  const x = Math.round(win.width * 0.6);
  const y = Math.round(win.height * 0.4);
  const set = (index) => page.evaluate(async (i) => (await import('/src/store.ts')).useAppStore.getState().setActiveGroupIndex(i), index);
  // The colour on the map once it has settled on `want`, or the last one seen.
  const settle = async (want) => {
    let c = [0, 0, 0];
    for (let t = 0; t < 6000; t += 100) {
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

  await expectColour('the group of the ticked scene is open', 2);
  // 1. Another group opened, the scene of the oldest group ticked: the opened group is on top.
  await set(1);
  await expectColour('green opened over the ticked blue scene', 1);
  await page.screenshot({ path: path.join(OUT, `opened ${name}.png`) });
  await set(0);
  await expectColour('red opened over the ticked blue scene', 0);
  // 2. Playing over the ticked scene: every step shows its own colour, none is hidden by the ticked blue scene.
  await set(2);
  await expectColour('blue back', 2);
  const seen = new Set();
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().setPlaying(true));
  const t0 = Date.now();
  while (Date.now() - t0 < 9000) {
    const c = await colourAt(page, x, y);
    const i = COLOURS.findIndex((k) => near(c, k));
    if (i >= 0) seen.add(i);
    await page.waitForTimeout(60);
  }
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().setPlaying(false));
  if (seen.size < 3) problems.push(`playing over the ticked scene showed only ${[...seen].map((i) => NAMES[i]).join(', ')}`);
  // 3. Back in the group of the ticked scene.
  await set(2);
  await expectColour('back in the group of the ticked scene', 2);
  await page.screenshot({ path: path.join(OUT, `back ${name}.png`) });
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
