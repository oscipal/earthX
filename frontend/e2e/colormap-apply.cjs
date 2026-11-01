// "Apply" of the preview in the processing panel opens for a change of the colormap alone (Otto, 01.11.2026; fixed in #269, checked
// again for NM4-54 #272), in a real browser: in values and in percentiles that are applied already; the tiles are asked for with the
// new colormap. Light and dark theme, 1280 and 360 px.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/colormap-apply.cjs             # BASE=http://localhost:5173
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const MEASURE = { b1: { count: 900, min: -0.2, max: 0.9, percentile_2: -0.1, percentile_98: 0.8, unit: null } };
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

async function check(browser, theme, viewport) {
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/statistics')) return json(MEASURE);
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const item = {
      id: 'S2B_A', collection: 'sentinel-2-c1-l2a', bbox, geometry: polygon,
      properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 },
      assets: {
        red: { href: 'https://example.org/red.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
        nir: { href: 'https://example.org/nir.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] },
      },
    };
    useAppStore.setState({
      datasets: [{
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
        browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
        collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } },
      }],
      datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: [item] }],
      activeGroupIndex: 0, selectedIds: ['S2B_A'], aoi: polygon, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
    useProcessingStore.getState().openProcessing();
  });
  await page.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  await page.waitForSelector('.pp-range input[type=number]', { timeout: 15000 });
  await page.waitForTimeout(700);
  const colormap = page.locator('.pp-range select:not(.vc-unit):not(.band-select select)').last();
  const unit = page.locator('.pp-range select.vc-unit');
  const apply = page.locator('.pp-range .vc-apply');
  const locked = async () => (await apply.isDisabled()) || (await apply.getAttribute('aria-disabled')) === 'true';
  // What the preview is drawn with: the colormap of its range in the store (the tile URL of the scenes carries it).
  const drawn = () => page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const state = useProcessingStore.getState();
    return [state.range.colormap, state.preview ? new URL(state.preview.scenes[0].url, location.origin).searchParams.get('colormap_name') : null];
  });
  const step = async (label, ok) => {
    if (!ok) problems.push(`${theme} ${viewport}: ${label}`);
  };
  // In values.
  await colormap.selectOption('plasma');
  await step('values: "Apply" stays locked after the colormap alone changed', !(await locked()));
  await apply.click();
  await page.waitForTimeout(900);
  const [inStore, inUrl] = await drawn();
  await step(`values: the preview is not drawn with plasma (${inStore}, ${inUrl})`, inStore === 'plasma' && inUrl === 'plasma');
  // In percentiles, applied.
  await unit.selectOption('percent');
  await apply.click();
  await page.waitForTimeout(900);
  await step('percentiles: "Apply" is open although they are applied', await locked());
  await colormap.selectOption('magma');
  await step('percentiles: "Apply" stays locked after the colormap alone changed', !(await locked()));
  await apply.click();
  await page.waitForTimeout(900);
  const [storeAfter, urlAfter] = await drawn();
  await step(`percentiles: the preview is not drawn with magma (${storeAfter}, ${urlAfter})`, storeAfter === 'magma' && urlAfter === 'magma');
  await step('percentiles: "Apply" is open after it was applied', await locked());
  await context.close();
  return problems;
}

(async () => {
  const browser = await chromium.launch();
  const all = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) all.push(...(await check(browser, theme, viewport)));
  await browser.close();
  console.log(all.length === 0 ? 'ok: "Apply" opens for the colormap alone (values and percentiles, light and dark, 1280 and 360 px)' : `FAIL\n${all.join('\n')}`);
  process.exit(all.length === 0 ? 0 : 1);
})();
