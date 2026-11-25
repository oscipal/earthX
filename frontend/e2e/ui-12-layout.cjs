// Browser check of UI-12 PR 2 (Otto, 25.11.2026): the status line (3), the settings bar that never scrolls (12), the pages of "Quick
// processing" (4) and what stands on the map in every view of a narrow and a low window (2). With made-up answers of the API, at 1280 x 800,
// 1280 x 360 and 360 x 740, light and dark. For each view (no panel, each panel of the rail, the view of the search with its time steps and
// its settings bar, the processing panel, the Data catalogue) it fails when
//   - the status line, with an error and "Loading data" in it, is not at the foot right of the rail, one row high, or something covers it;
//   - the settings bar scrolls (its body is taller or wider than it shows), or "Display" is folded while nothing was opened by hand;
//   - two things on the map cover each other: the buttons at the top right, the map controls, the legend, the time steps, the marks at the
//     bottom left and the attribution (where an open panel covers one, it does not count);
//   - something leaves the window or the page scrolls sideways;
//   - "Quick processing" does not show "‹ 1 / n ›", or its page holds more rows than fit;
// and opens a folded section by its head: it stays open, and the bar still does not scroll.
// A screenshot per window, theme and view: <OUT>/layout-<theme>-<size>-<view>.png.
//
//   cd frontend && npm run dev &            # a FRESH dev server (one that saw no edits): the check imports the store
//   node e2e/ui-12-layout.cjs               # BASE=http://localhost:5173 OUT=<directory for the screenshots> ONLY="dark narrow"
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersSelection } = require('./selectionMock.cjs');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-ui-12-layout');
const ONLY = process.env.ONLY;
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, low: { width: 1280, height: 360 }, narrow: { width: 360, height: 740 } };
const FOOTPRINT = [10, 50, 11, 51];
const SCENES = ['SYNTH_A', 'SYNTH_B'];
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
const PRESETS = ['NDVI', 'NDWI', 'NDSI', 'NBR', 'EVI', 'SAVI', 'MSAVI', 'NDMI'].map((name) => ({ name, title: name, expression: '(nir - red) / (nir + red)', rescale: [[-1, 1]], colormap_name: 'rdylgn', formula: '(N - R)/(N + R)', reference: 'https://example.org/formula' }));
const bell = (low, high, centre) => [Array.from({ length: 64 }, (_, i) => Math.round(1000 * Math.exp(-(((i - centre) / 9) ** 2)))), Array.from({ length: 65 }, (_, i) => low + ((high - low) * i) / 64)];
const band = (low, high, centre) => ({ min: low, max: high, percentile_2: low, percentile_98: high, histogram: bell(low, high, centre) });
const VISUAL = { b1: band(0, 2000, 20), b2: band(0, 2500, 28), b3: band(0, 3000, 36) };
const areaAnswer = { bands: Object.entries(VISUAL).map(([name, { min, max, ...rest }]) => ({ name, unit: null, statistics: { minimum: min, maximum: max, mean: 1, valid_percent: 100, ...rest } })), exact: true, factor: 1 };
const overlaps = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

// What stands where, read in the page.
const READ = () => {
  const box = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
  const shown = (el) => el && !el.closest('[hidden]') && getComputedStyle(el).visibility !== 'hidden' && el.getClientRects().length > 0 && box(el).width > 0 && box(el).height > 0;
  // An element not wholly under an open panel (a panel may cover what is on the map in a narrow window).
  const panels = [...document.querySelectorAll('.dock:not([hidden]), .inspector.panel:not([hidden]), .processing-sheet, .catalogue')].filter(shown).map(box);
  // What lies wholly outside the window (lifted over a sheet that fills the map) is not seen.
  const seen = (b) => b.y + b.height > 0 && b.x + b.width > 0 && b.y < innerHeight && b.x < innerWidth;
  const inside = (b, p) => b.x >= p.x - 0.5 && b.y >= p.y - 0.5 && b.x + b.width <= p.x + p.width + 0.5 && b.y + b.height <= p.y + p.height + 0.5;
  const free = (b) => seen(b) && !panels.some((p) => inside(b, p));
  const onMap = [
    ['buttons at the top', '.overlay.top-right > *'],
    ['map controls', '.map-controls'],
    ['legend', '.map-legend .legend'],
    ['time steps', '.overlay.bottom > *'],
    ['marks', '.preview-badge-dock > *'],
    ['attribution', '.maplibregl-ctrl-attrib'],
  ].flatMap(([name, selector]) => [...document.querySelectorAll(selector)].filter(shown).map((el) => ({ name, ...box(el) })).filter(free));
  const status = document.querySelector('.overlay.status');
  const sb = box(status);
  const hit = document.elementFromPoint(sb.x + sb.width / 2, sb.y + sb.height / 2);
  const body = document.querySelector('.inspector.panel:not([hidden]) .insp-body');
  const quick = document.querySelector('.inspector .vc-quick');
  return {
    win: { width: innerWidth, height: innerHeight },
    pageScroll: document.documentElement.scrollWidth - innerWidth,
    rail: box(document.querySelector('.app-rail')),
    status: { ...sb, covered: !hit || !status.contains(hit), text: status.textContent.trim().slice(0, 60) },
    controlHeight: parseFloat(getComputedStyle(document.querySelector('.app')).getPropertyValue('--control-height')),
    onMap,
    bar: body ? {
      scrollsDown: body.scrollHeight > body.clientHeight + 1,
      scrollsSide: body.scrollWidth > body.clientWidth + 1,
      sections: [...body.querySelectorAll(':scope > .insp-section')].map((s) => ({ title: s.dataset.title, open: !s.classList.contains('folded') })),
      quickCount: document.querySelector('.inspector .quick-pages .dataset-page-count')?.textContent ?? null,
      quickRows: quick ? Math.ceil(quick.children.length / 3) : 0,
    } : null,
  };
};

async function seedView(page) {
  await page.evaluate(async ({ scenes, footprint, presets }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 8, maxZoom: 14 });
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const aoi = { type: 'Polygon', coordinates: [[[10.2, 50.2], [10.8, 50.2], [10.8, 50.8], [10.2, 50.8], [10.2, 50.2]]] };
    const tiff = (n) => ({ href: 'https://example.org/x.tif', type: COG, 'raster:bands': Array.from({ length: n }, () => ({ data_type: 'uint16', nodata: 0 })) });
    const items = scenes.map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { visual: tiff(3), B04: tiff(1), B08: tiff(1) } }));
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
      selectedIds: scenes, downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: true, viewAoi: aoi, aoi, showDownloaded: true, dock: null,
      appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', pendingChannels: [], pendingIndex: '', pendingBand: '', enhance: null,
      layers: [], mosaics: {}, error: null, mapZoom: 12, flyToView: { center: [10.5, 50.5], zoom: 10 },
    });
    await useAppStore.getState().loadMosaics();
  }, { scenes: SCENES, footprint: FOOTPRINT, presets: PRESETS });
  await page.waitForSelector('.inspector .insp-body');
}

const setStore = (page, state) => page.evaluate(async (s) => (await import('/src/store.ts')).useAppStore.setState(s), state);
const setProcessing = (page, open) => page.evaluate(async (o) => (await import('/src/processingStore.ts')).useProcessingStore.setState({ open: o }), open);

async function run(browser, theme, size) {
  const label = `${theme} ${size}`;
  const problems = [];
  const fail = (what) => problems.push(what);
  const context = await browser.newContext({ viewport: VIEWPORTS[size] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => fail(`the page failed: ${error.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (answersSelection(route, url)) return;
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': SCENES });
    if (route.request().method() === 'POST' && url.pathname.endsWith('/statistics')) return json(areaAnswer);
    if (url.pathname.includes('/statistics')) return json(VISUAL);
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    if (url.pathname.endsWith('/catalogue/categories')) return json({ categories: [{ id: 'water', title: 'Water' }] });
    if (url.pathname.endsWith('/stac/collections')) return json({ collections: [], links: [] });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.app-rail');
  await seedView(page);

  const views = [
    ['view', async () => {}],
    ['view-controls', () => setStore(page, { dock: 'controls' })],
    ['view-layers', () => setStore(page, { dock: 'layers' })],
    ['view-jobs', () => setStore(page, { dock: 'jobs' })],
    ['view-settings', () => setStore(page, { dock: 'settings' })],
    ['processing', async () => { await setStore(page, { dock: null }); await setProcessing(page, true); }],
    ['catalogue', async () => { await setProcessing(page, false); await setStore(page, { catalogueOpen: true }); }],
    ['map', () => setStore(page, { catalogueOpen: false, focusMode: false, selectedIds: [] })],
  ];
  let openedByHand = false;
  for (const [name, arrange] of views) {
    await arrange();
    await setStore(page, { error: 'The search could not be completed because the catalogue answered with an error that has a long text', mapLoading: ['x'] });
    await page.waitForTimeout(900);
    const seen = await page.evaluate(READ);
    const where = `${label}, ${name}`;
    if (seen.pageScroll > 0) fail(`${where}: the page scrolls sideways by ${seen.pageScroll}px`);
    const s = seen.status;
    if (Math.abs(s.x - seen.rail.width) > 1 || Math.abs(s.x + s.width - seen.win.width) > 1 || Math.abs(s.y + s.height - seen.win.height) > 1) fail(`${where}: the status line is not at the foot right of the rail: ${JSON.stringify(s)}`);
    if (Math.abs(s.height - seen.controlHeight) > 1) fail(`${where}: the status line is ${s.height}px high, not one row (${seen.controlHeight}px)`);
    if (s.covered && name !== 'catalogue') fail(`${where}: something covers the status line`);
    if (!s.text.startsWith('The search could not')) fail(`${where}: the status line shows "${s.text}"`);
    for (const item of seen.onMap) {
      if (item.x < -0.5 || item.y < -0.5 || item.x + item.width > seen.win.width + 0.5 || item.y + item.height > s.y + 0.5) fail(`${where}: the ${item.name} leave the map: ${JSON.stringify(item)}`);
    }
    for (let i = 0; i < seen.onMap.length; i++) {
      for (let j = i + 1; j < seen.onMap.length; j++) {
        const [a, b] = [seen.onMap[i], seen.onMap[j]];
        if (a.name !== b.name && overlaps(a, b)) fail(`${where}: the ${a.name} and the ${b.name} cover each other`);
      }
    }
    if (seen.bar) {
      if (seen.bar.scrollsDown || seen.bar.scrollsSide) fail(`${where}: the settings bar scrolls (${JSON.stringify(seen.bar)})`);
      if (!openedByHand && seen.bar.sections[0]?.open === false) fail(`${where}: "Display" is folded though nothing was opened by hand`);
      const quick = seen.bar.sections.find((x) => x.title === 'Quick processing');
      if (quick?.open && !/^1 \/ \d+$/.test(seen.bar.quickCount ?? '')) fail(`${where}: "Quick processing" shows no pages ("${seen.bar.quickCount}")`);
    }
    await page.screenshot({ path: path.join(OUT, `layout-${theme}-${size}-${name}.png`) });
    if (name === 'view') {
      // A folded section opens by its head and stays open; the bar still does not scroll.
      const folded = page.locator('.inspector .insp-section.folded .insp-fold').first();
      if (await folded.count()) {
        const title = await folded.textContent();
        await folded.click();
        openedByHand = true;
        await page.waitForTimeout(600);
        const after = await page.evaluate(READ);
        const opened = after.bar.sections.find((x) => x.title === title);
        if (!opened?.open) fail(`${where}: "${title}" did not stay open when its head was clicked`);
        if (after.bar.scrollsDown || after.bar.scrollsSide) fail(`${where}: the settings bar scrolls after "${title}" was opened`);
        await page.screenshot({ path: path.join(OUT, `layout-${theme}-${size}-${name}-opened.png`) });
      }
    }
  }
  await context.close();
  console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${label}`);
  for (const p of problems) console.log(`     ${p}`);
  return problems.length;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const size of Object.keys(VIEWPORTS)) {
      if (ONLY && ONLY !== `${theme} ${size}`) continue;
      failed += await run(browser, theme, size);
    }
  }
  await browser.close();
  console.log(failed === 0 ? `screenshots in ${OUT}` : `${failed} problems; screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
