// DS-05a in a real browser: dB of a Sentinel-1 scene (plan `docs/plans/m5/ds-05a-sar-db.md` §8). The collection and the process description
// are the ones the registry writes (`ds-05a-collection.json`, `src/fixtures/processes/sentinel-1-grd.json`); the scenes are synthetic in the
// shape of Earth Search, and the answers of tiler and jobs are made up (no live source from a cloud session, A8). Light and dark theme,
// 1280×800 and 360×740; a screenshot per case. It fails when
//   quick      "Quick processing" of a scene of VV and VH is not "VV dB | VH dB", or a scene of HH and HV shows the section at all
//   look       "VV dB" does not fill the fields with `greys_r` and the measured 2nd to 98th percentile in dB, or "Apply" does not draw the
//              step `sar_db` with them; the legend does not name "dB"; the bar scrolls sideways or something leaves it
//   export     "Download crop" of the view does not place a job with the step and the look of the view as `exportStyle` (QGIS style, M5-64)
//   panel      "Add step" does not offer "SAR dB", or its step does not read vv as vv_db with the quantity fixed and no field for it
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/ds-05a-sar-db.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots, not in the repository>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersSelection } = require('./selectionMock.cjs');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(os.tmpdir(), 'earthx-ds-05a');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const COLLECTION = JSON.parse(fs.readFileSync(path.join(__dirname, 'ds-05a-collection.json'), 'utf8'));
const PROCESS = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-1-grd.json'), 'utf8'));
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');
const JOB = 'AAAAAAAAAAAAAAAAAAAAAA';
const FOOTPRINT = [13.2, 47.1, 16.6, 49.0];
const AOI = { type: 'Polygon', coordinates: [[[14.2, 47.8], [14.6, 47.8], [14.6, 48.1], [14.2, 48.1], [14.2, 47.8]]] };

// A bell of 64 bins from `low` to `high`, as rio-tiler writes a histogram.
const bell = (low, high) => {
  const edges = Array.from({ length: 65 }, (_, i) => low + ((high - low) * i) / 64);
  return [Array.from({ length: 64 }, (_, i) => Math.round(1000 * Math.exp(-(((i - 30) / 9) ** 2)))), edges];
};
// What a VV scene measures: digital numbers, and the same in dB (20·log10).
const DN = { vv: { min: 20, max: 600, percentile_2: 90, percentile_98: 250, histogram: bell(20, 600), unit: 'DN' } };
const DB = { vv_db: { min: 26, max: 55.6, percentile_2: 38, percentile_98: 51, histogram: bell(26, 55.6), unit: 'dB' } };
const areaAnswer = (byBand) => ({
  bands: Object.entries(byBand).map(([name, { min, max, unit, ...rest }]) => ({ name, unit, statistics: { minimum: min, maximum: max, mean: (min + max) / 2, valid_percent: 100, ...rest } })),
  exact: true,
  factor: 1,
});

function scene(id, polarisations) {
  const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
  const assets = Object.fromEntries(polarisations.map((p) => [p, { href: `s3://sentinel-s1-l1c/GRD/${id}/${p}.tiff`, type: COG, roles: ['data'], 'raster:bands': [{ data_type: 'uint16', nodata: 0 }] }]));
  assets.thumbnail = { href: `https://example.org/${id}/preview.png`, type: 'image/png', roles: ['thumbnail'] };
  return {
    id, collection: 'sentinel-1-grd', bbox: FOOTPRINT,
    geometry: { type: 'Polygon', coordinates: [[[13.2, 47.1], [16.6, 47.1], [16.6, 49.0], [13.2, 49.0], [13.2, 47.1]]] },
    properties: { datetime: '2026-11-20T05:10:00Z', 'sar:polarizations': polarisations.map((p) => p.toUpperCase()), 'sar:instrument_mode': 'IW', 's1:datatake_id': '400001' },
    assets,
  };
}
const VV_SCENE = scene('S1A_IW_GRDH_1SDV_20261120T051000_SYNTH', ['vv', 'vh']);
const HH_SCENE = scene('S1A_EW_GRDM_1SDH_20261120T051000_SYNTH', ['hh', 'hv']);

async function open(browser, theme, viewport) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport], acceptDownloads: true });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  const seen = { execution: [], results: [] };
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (answersSelection(route, url)) return;
    if (url.pathname === '/processing/processes/recipe') return json(PROCESS);
    if (url.pathname.endsWith('/estimate')) return json({ estimate: { size: 800_000, duration: 'PT8S', outputPixels: 1, inputPixels: 1, inputBytes: 1, assets: 1, units: 1 }, skippedItems: [] });
    if (url.pathname.endsWith('/execution')) {
      seen.execution.push(JSON.parse(request.postData() ?? '{}'));
      return json({ jobID: JOB, status: 'accepted', message: '', progress: 0, expires: '2099-01-01T00:00:00Z' });
    }
    if (url.pathname.endsWith(`/jobs/${JOB}`)) return json({ jobID: JOB, status: 'successful', message: '', progress: 100, expires: '2099-01-01T00:00:00Z' });
    if (url.pathname.includes(`/jobs/${JOB}/results`)) {
      seen.results.push(url);
      return route.fulfill({ status: 200, contentType: 'application/zip', body: 'PK' });
    }
    if (request.method() === 'POST' && url.pathname.endsWith('/statistics')) {
      const order = JSON.parse(request.postData() ?? '{}');
      return json(areaAnswer(JSON.stringify(order).includes('sar_db') ? DB : DN));
    }
    if (url.pathname.endsWith('/statistics')) return json(url.search.includes('op=sar_db') ? DB : DN);
    if (url.pathname.endsWith('tilejson.json')) return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 0, maxzoom: 19, ...(url.search.includes('op=sar_db') ? { band: 'vv_db', unit: 'dB' } : {}) });
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  // The ZIP of the result is saved through a link, which the browser downloads past the routes above.
  page.on('download', (download) => seen.results.push(new URL(download.url())));
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  return { context, page, problems, seen };
}

// The view of one scene of the search, as after "Show on map" over the AOI.
async function seed(page, item) {
  await page.evaluate(async ({ item, collection, aoi, footprint }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const asset = Object.keys(item.assets)[0];
    const info = { datasetId: 'sentinel-1-grd', tileUrl: `/collections/sentinel-1-grd/items/${item.id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=${asset}`, bounds: footprint, asset, minZoom: 0, maxZoom: 19 };
    const look = { rescale: asset === 'vv' ? '90,250' : '70,750' };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'sentinel-1-grd', items: [item], groups: [{ key: ['2026-11-20'], label: '2026-11-20', items: [item] }], activeGroupIndex: 0,
      selectedIds: [item.id], downloaded: { [item.id]: info }, focusMode: true, cropToAoi: true, viewAoi: aoi, aoi, showDownloaded: true, dock: null, shownImage: null,
      viewLooks: {}, savedLooks: {}, appliedRender: look, pendingColormapName: '', pendingVmin: look.rescale.split(',')[0], pendingVmax: look.rescale.split(',')[1],
      pendingChannels: [], pendingIndex: '', pendingBand: '', enhance: null, layers: [], mosaics: {}, error: null, mapZoom: 10, flyToView: { center: [14.4, 47.95], zoom: 10 },
    });
  }, { item, collection: COLLECTION, aoi: AOI, footprint: FOOTPRINT });
  await page.waitForSelector('.inspector .insp-body');
}

const settle = (page) => page.waitForTimeout(500);
const store = (page, pick) => page.evaluate(async (source) => {
  const { useAppStore } = await import('/src/store.ts');
  return new Function('s', `return (${source})(s)`)(useAppStore.getState());
}, pick.toString());
const headings = (page) => page.$$eval('.inspector .insp-heading', (hs) => hs.map((h) => h.textContent));
const quickButtons = (page) => page.$$eval('.inspector .vc-quick button', (bs) => bs.map((b) => b.textContent));
const expectEq = (fail, what, got, want) => {
  if (JSON.stringify(got) !== JSON.stringify(want)) fail(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`);
};

// What lies outside the open bar, and whether the page or the bar scrolls sideways.
const bounds = (page, selector) =>
  page.evaluate((sel) => {
    const bar = document.querySelector(sel);
    const base = bar.getBoundingClientRect();
    const body = bar.querySelector('.insp-body') ?? bar;
    return {
      sideways: body.scrollWidth > body.clientWidth + 1 || document.documentElement.scrollWidth > window.innerWidth + 1,
      outside: [...bar.querySelectorAll('*')].filter((e) => { const r = e.getBoundingClientRect(); return r.width > 0 && (r.right > base.right + 1 || r.left < base.left - 1); }).map((e) => e.className || e.tagName).slice(0, 4),
    };
  }, selector);

async function legendText(page) {
  const title = page.locator('.map-legend .legend-title');
  if ((await title.count()) && (await title.getAttribute('aria-expanded')) === 'false') await title.click();
  await page.waitForTimeout(200);
  return (await page.locator('.map-legend').textContent().catch(() => '')) ?? '';
}

async function runCase(browser, theme, viewport, results) {
  const { context, page, problems, seen } = await open(browser, theme, viewport);
  const tag = `${theme}-${viewport}`;
  const fail = (what) => problems.push(what);
  const shot = (name) => page.screenshot({ path: path.join(OUT, `${tag}-${name}.png`) });
  try {
    // quick: a scene of VV and VH.
    await seed(page, VV_SCENE);
    await settle(page);
    if (!(await headings(page)).includes('Quick processing')) fail(`no "Quick processing": ${await headings(page)}`);
    expectEq(fail, 'quick buttons', await quickButtons(page), ['VV dB', 'VH dB']);
    // look: "VV dB" into the fields, drawn with "Apply".
    await page.locator('.inspector .vc-quick button', { hasText: 'VV dB' }).click();
    await page.waitForFunction(async () => (await import('/src/store.ts')).useAppStore.getState().pendingColormapName !== '', null, { timeout: 5000 }).catch(() => fail('the look of VV dB did not come'));
    expectEq(fail, 'fields', await store(page, (s) => [s.pendingColormapName, s.pendingVmin, s.pendingVmax]), ['greys_r', '38', '51']);
    await page.locator('.inspector .vc-apply').click();
    await settle(page);
    expectEq(fail, 'drawn', await store(page, (s) => [s.appliedRender.index, s.appliedRender.colormapName, s.appliedRender.rescale]), ['vv_db', 'greys_r', '38,51']);
    const legend = await legendText(page);
    if (!/38\s*dB/.test(legend) || !/51\s*dB/.test(legend)) fail(`the legend does not say dB: ${JSON.stringify(legend.slice(0, 120))}`);
    const b = await bounds(page, 'aside.inspector');
    if (b.sideways || b.outside.length) fail(`bar: ${JSON.stringify(b)}`);
    await shot('vv-db');
    // export: the view pinned as a layer, downloaded as "VV dB" (a job with the step, NM4-14b) with the look of the layer as the QGIS style.
    await page.evaluate(async () => {
      const { useAppStore } = await import('/src/store.ts');
      useAppStore.getState().addCurrentToLayers();
      await new Promise((r) => setTimeout(r, 500));
      const [layer] = useAppStore.getState().layers;
      await useAppStore.getState().openDownloadDialog(layer.id);
    });
    await page.waitForSelector('.dialog-panel');
    await page.evaluate(() => import('/src/store.ts').then(({ useAppStore }) => useAppStore.getState().setDownloadAs('index')));
    await page.waitForFunction(async () => (await import('/src/store.ts')).useAppStore.getState().downloadIndexNote?.state === 'ready', null, { timeout: 5000 }).catch(() => fail('no estimate of VV dB'));
    await shot('download');
    await page.getByRole('button', { name: 'Download', exact: true }).click();
    await page.waitForFunction(() => !document.querySelector('.dialog-panel'), null, { timeout: 8000 }).catch(() => fail('the dialog stays'));
    const inputs = seen.execution[0]?.inputs ?? {};
    if (!JSON.stringify(inputs).includes('"op":"sar_db"')) fail(`the job has no sar_db step: ${JSON.stringify(inputs).slice(0, 200)}`);
    // The look goes with the result's ZIP, not the recipe (M5-64): the one band of the result, grey from 38 to 51 dB.
    for (let waited = 0; seen.results.length === 0 && waited < 8000; waited += 250) await page.waitForTimeout(250);
    const zip = seen.results[0];
    expectEq(fail, 'export style', zip ? [JSON.parse(zip.searchParams.get('style') ?? 'null'), zip.searchParams.get('style_format') ?? 'qml'] : null, [{ band: 'band', colormap: 'greys_r', range: [38, 51] }, 'qml']);
    // panel: "SAR dB" in "Add step".
    await page.evaluate(async () => {
      const { useAppStore } = await import('/src/store.ts');
      useAppStore.getState().chooseViewIndex(null);
      await useAppStore.getState().applyRender();
      const { useProcessingStore } = await import('/src/processingStore.ts');
      useProcessingStore.getState().openProcessing();
    });
    await page.waitForSelector('.processing-panel, [aria-label="Processing"]').catch(() => undefined);
    const add = page.locator('button', { hasText: /^SAR dB$/ });
    await add.first().waitFor({ timeout: 5000 }).catch(() => fail('"Add step" offers no "SAR dB"'));
    if (await add.count()) {
      await add.first().click();
      await settle(page);
      const step = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().steps.find((s) => s.op === 'sar_db')?.values ?? null);
      expectEq(fail, 'step', step && [step.bands, step.name], ['vv', 'vv_db']);
      const preview = await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().preview?.scenes[0]?.url ?? '');
      const params = new URL(preview, 'http://x').searchParams.getAll('params').map((p) => JSON.parse(p));
      expectEq(fail, 'preview step', params.at(-1), { bands: ['vv'], name: 'vv_db', quantity: 'amplitude' });
      if (await page.locator('[id$="-quantity"]').count()) fail('a field for the quantity');
      await page.locator('.pp-step', { hasText: 'vv_db' }).first().scrollIntoViewIfNeeded().catch(() => undefined);
      await shot('panel');
    }
    // quick: a scene of HH and HV shows no "VV dB".
    await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().closeProcessing?.());
    await seed(page, HH_SCENE);
    await settle(page);
    if ((await headings(page)).includes('Quick processing')) fail(`"Quick processing" on a scene of HH and HV: ${await quickButtons(page)}`);
    await shot('hh');
  } catch (error) {
    fail(`stopped: ${error.message.split('\n').slice(0, 3).join(' ')}`);
    await shot('stopped').catch(() => undefined);
  }
  results.push({ tag, problems: [...problems] });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const results = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) await runCase(browser, theme, viewport, results);
  await browser.close();
  for (const { tag, problems } of results) console.log(`${tag}: ${problems.length === 0 ? 'ok' : problems.join('; ')}`);
  console.log(`screenshots in ${OUT}`);
  process.exit(results.every((r) => r.problems.length === 0) ? 0 : 1);
})();
