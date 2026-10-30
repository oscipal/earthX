// Playing the timeline (NM4-18), in a real browser with made-up tiles of the tiler that are slow on purpose:
//   1. Every step takes 0.8 s to load: the map changes to the next step only once its tiles are in, never shows the basemap
//      between two steps, and the timeline names the step by its date (the key of the group goes on with a scene).
//   2. One step takes 3 s: the picture before it stays until it is there, the slider says "Loading…".
//   3. One step never loads: it is skipped after the timeout with a notice, the picture stays, and playing goes on.
// Each step is one solid colour, and the pixel in the middle of the map is read every 40 ms: any other colour is the
// basemap (or a step half drawn). Light and dark theme, a wide and a narrow window; a screenshot per case.
// SLOW_BASEMAP=<ms> makes the answers for everything outside the page slow; DEBUG=1 prints the samples around a gap;
// CASE='<name> <theme> <viewport>' runs one case; SECONDS=<s> plays longer.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/play-steps.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-play-steps');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
// Newest first, as the groups are; the slider plays from the oldest, so the colours run from the last to the first.
const COLOURS = [
  [230, 40, 40],
  [40, 180, 60],
  [50, 90, 230],
  [240, 160, 20],
  [150, 50, 200],
];
const NEVER = Number.POSITIVE_INFINITY;

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

// The 2 x 2 pixels at the middle of the map as one PNG; its colour is read in the page.
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

async function run(browser, { theme, viewport, name: caseName, delays, seconds, expect }) {
  const name = `${caseName} ${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.on('pageerror', (error) => console.log('pageerror', error.message));
  const open = COLOURS.map(() => 0); // tiles of a step asked for and not answered yet
  const asked = COLOURS.map(() => 0);
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const tile = /\/items\/SYNTH_20260(\d)01\/tiles\//.exec(url.pathname);
    if (tile) {
      const i = 8 - Number(tile[1]);
      asked[i]++;
      open[i]++;
      const delay = delays[i] ?? 0;
      if (delay === NEVER) return; // never answered; the page is closed at the end
      await new Promise((resolve) => setTimeout(resolve, delay));
      open[i]--;
      return route.fulfill({ status: 200, contentType: 'image/png', body: solidPng(COLOURS[i]) });
    }
    // SLOW_BASEMAP=<ms>: the basemap's tiles are slow (a slow network) and must not hold a step up, which waits for its own tiles only.
    if (url.origin !== BASE) {
      if (process.env.SLOW_BASEMAP) await new Promise((resolve) => setTimeout(resolve, Number(process.env.SLOW_BASEMAP)));
      return route.abort();
    }
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
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['datetime', 's2:datatake_id'] },
        'earthx:default_render': { title: 'Grey', assets: ['data'], rescale: [[0, 1]], colormap_name: null, expression: null, resampling: 'nearest' },
      },
    ]);
    const features = [1, 2, 3, 4, 5].map((n) => ({
      id: `SYNTH_20260${9 - n}01`,
      collection: 'synthetic',
      bbox: [-20, 30, 40, 60],
      properties: { datetime: `2026-0${9 - n}-01T10:00:00Z`, 's2:datatake_id': `GS2A_SCENE_NAME_${n}` },
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
      activeGroupIndex: open.groups.length - 1,
      expandedGroupIndex: open.groups.length - 1,
      selectedIds: [],
      dock: null,
      flyToView: { center: [10, 45], zoom: 3 },
    });
  });
  await page.waitForSelector('.time-slider');
  // The first picture (the oldest step) is on the map before playing starts.
  const x = Math.round(win.width * 0.6);
  const y = Math.round(win.height * 0.4);
  let first = null;
  for (let t = 0; t < 15000 && first === null; t += 100) {
    const c = await colourAt(page, x, y);
    if (near(c, COLOURS[4])) first = c;
    else await page.waitForTimeout(100);
  }
  if (first === null) problems.push('the first step never came on the map');

  await page.locator('.play-btn').dispatchEvent('click'); // in a narrow window the rail lies over the button, as it does in the app
  const t0 = Date.now();
  const samples = [];
  const labels = new Set();
  let sawLoading = false;
  let notice = null;
  while (Date.now() - t0 < (Number(process.env.SECONDS) || seconds) * 1000) {
    const c = await colourAt(page, x, y);
    const step = COLOURS.findIndex((k) => near(c, k));
    samples.push({ t: Date.now() - t0, step, c, openNow: [...open] });
    labels.add(await page.locator('.time-labels strong').innerText());
    if ((await page.locator('.time-count').innerText()) === 'Loading…') sawLoading = true;
    const toast = page.locator('.toast.notice');
    if ((await toast.count()) > 0) notice = await toast.first().innerText();
    await page.waitForTimeout(40);
  }
  await page.screenshot({ path: path.join(OUT, `${name}.png`) });

  // 1. Never the basemap, never a half-drawn step: every sample is the colour of a step.
  const gaps = samples.filter((s) => s.step === -1);
  if (gaps.length > 0 && process.env.DEBUG) {
    const i = samples.indexOf(gaps[0]);
    console.log(samples.slice(Math.max(0, i - 4), i + 5).map((x) => `${x.t}:${x.step}`).join(' '));
  }
  if (gaps.length > 0) problems.push(`${gaps.length} samples show something else than a step (${JSON.stringify(gaps[0].c)} at ${gaps[0].t} ms)`);
  // 2. A step comes on the map only when all its tiles are in.
  let last = 4;
  for (const s of samples) {
    if (s.step !== -1 && s.step !== last) {
      if (s.openNow[s.step] > 0) problems.push(`step ${s.step} was on the map with ${s.openNow[s.step]} tiles still on their way, at ${s.t} ms`);
      last = s.step;
    }
  }
  // 3. The name of a step is its date.
  for (const label of labels) if (!/^\d{4}-\d{2}-\d{2}$/.test(label)) problems.push(`the timeline names a step "${label}"`);
  const order = samples.map((s) => s.step).filter((s, i, all) => s !== -1 && s !== all[i - 1]);
  const when = samples.filter((s, i, all) => s.step !== -1 && s.step !== all[i - 1]?.step).map((s) => `${s.step}@${(s.t / 1000).toFixed(1)}`);
  if (expect.loading && !sawLoading) problems.push('no "Loading…" while a step was on its way');
  if (expect.loading === false && sawLoading) problems.push('"Loading…" although every step was in time');
  if (expect.skipped && !/Skipped a step/.test(notice ?? '')) problems.push(`no notice for the skipped step: ${notice}`);
  if (expect.steps && order.length < expect.steps) problems.push(`only ${order.length} changes of step in ${seconds} s: ${order.join(',')}`);
  if (expect.never !== undefined && order.includes(expect.never)) problems.push(`step ${expect.never} never loads, but was shown`);
  console.log(`     ${name}: steps ${when.join(' → ')}; asked ${asked.join('/')}`);
  await context.close();
  return { name, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  const cases = [
    { name: 'quick', delays: COLOURS.map(() => 800), seconds: 9, expect: { steps: 3, loading: false } },
    { name: 'slow', delays: [800, 800, 800, 3000, 800], seconds: 9, expect: { loading: true, steps: 2 } },
    { name: 'stuck', delays: [800, 800, 800, NEVER, 800], seconds: 18, expect: { skipped: true, steps: 2, never: 3 } },
  ];
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const c of cases) {
        // The stuck step takes long: once per theme, in the wide window.
        if (c.name === 'stuck' && viewport === 'narrow') continue;
        if (process.env.CASE && !`${c.name} ${theme} ${viewport}`.startsWith(process.env.CASE)) continue;
        const { name, problems } = await run(browser, { theme, viewport, ...c });
        console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
        for (const problem of problems) console.log(`       ${problem}`);
        failed += problems.length;
      }
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
