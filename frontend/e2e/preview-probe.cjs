// Browser check of NM4-26, in a real browser against the real tiler over a synthetic source:
//   1. opening the app asks no search page;
//   2. a search with 340 matches asks the pages (none), p2, p3, each once;
//   3. an NDVI preview of the scenes asks its probe, its statistics once, and real tiles, all answered;
//   4. a half-typed expression is refused by the probe: no statistics and no tiles of it, the panel says why.
// In the light and the dark theme, at a wide and a narrow window; a screenshot per case.
//
// The tiler of `scripts/tile-bench`, over the COGs of its `make_cogs.py` (PG* variables as for the bench):
//   python -I scripts/tile-bench/slow_source.py <cog-dir> --rtt-ms 40 &
//   PYTHONPATH=backend python scripts/tile-bench/run_tiler.py --source http://127.0.0.1:9100 --item-ms 50 &
//   cd frontend && VITE_TILER_PROXY=http://127.0.0.1:8101 npm run dev &
//   node e2e/preview-probe.cjs                  # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// The search answers and the process description are made up here; tiles, TileJSON and statistics come from the
// tiler. Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-preview-probe');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
// The footprint of the synthetic scene of `scripts/tile-bench` (UTM 32N, 600000/5300040, 10980 px of 10 m).
const FOOTPRINT = [10.3119, 46.8326, 11.8028, 47.8459];
const SCENES = ['SYNTH_T32TPT_20260801T102039_L2A', 'SYNTH_T32TPT_20260802T102039_L2A', 'SYNTH_T32TPT_20260803T102039_L2A'];

function searchPage(token) {
  const sizes = { '': 100, p2: 100, p3: 100, p4: 40 };
  const next = { '': 'p2', p2: 'p3', p3: 'p4', p4: null }[token];
  const [w, s, e, n] = FOOTPRINT;
  const features = Array.from({ length: sizes[token] }, (_, i) => ({
    type: 'Feature', stac_version: '1.0.0', id: `SYNTH_T32TPT_${token || 'p1'}_${i}`, collection: 'sentinel-2-c1-l2a',
    bbox: FOOTPRINT, geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
    properties: { datetime: '2026-08-01T10:20:39Z' }, assets: {}, links: [],
  }));
  const links = next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: next } }] : [];
  return { type: 'FeatureCollection', features, links, numberMatched: 340 };
}

async function check(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const seen = { searches: [], statistics: [], probes: [], tiles: [] };
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/search') {
      const token = JSON.parse(request.postData() ?? '{}').token ?? '';
      seen.searches.push(token || '(none)');
      return json(searchPage(token));
    }
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.startsWith('/collections/')) {
      const params = url.searchParams.getAll('params').join('|');
      if (url.pathname.endsWith('/statistics')) seen.statistics.push(params);
      else if (url.pathname.endsWith('/tilejson.json')) seen.probes.push(params);
      else if (url.pathname.includes('/tiles/')) seen.tiles.push(params);
      return route.continue();
    }
    return json({ detail: 'not made up' }, 404);
  });
  page.on('response', (response) => {
    const url = new URL(response.url());
    if (url.pathname.startsWith('/collections/') && response.status() >= 500) problems.push(`${response.status()} for ${url.pathname}`);
  });

  await page.goto(BASE);
  await page.waitForTimeout(2000);
  if (seen.searches.length !== 0) problems.push(`opening the app asked ${seen.searches.length} search page(s)`);

  // 2. A search of 340 matches: the store walks the pages as the Search button does.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const aoi = { type: 'Polygon', coordinates: [[[10.9, 47.2], [11.2, 47.2], [11.2, 47.5], [10.9, 47.5], [10.9, 47.2]]] };
    useAppStore.setState({
      datasets: [{
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
        browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
        collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } },
      }],
      datasetId: 'sentinel-2-c1-l2a', selectedDatasetIds: ['sentinel-2-c1-l2a'], aoi, aoiPoint: null, error: null,
    });
    await useAppStore.getState().runSearch();
  });
  const pages = seen.searches.join(',');
  if (pages !== '(none),p2,p3') problems.push(`the search asked the pages ${pages}, not (none),p2,p3`);

  // 3. An NDVI preview over three scenes of the synthetic source.
  await page.evaluate(async ({ footprint, scenes }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const [w, s, e, n] = footprint;
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const band = { data_type: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0 };
    const items = scenes.map((id) => ({
      id, collection: 'sentinel-2-c1-l2a', bbox: footprint,
      geometry: { type: 'Polygon', coordinates: [[[w, s], [e, s], [e, n], [w, n], [w, s]]] },
      properties: { datetime: '2026-08-01T10:20:39Z', gsd: 10 },
      assets: {
        red: { href: `https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/synth/${id}/B04.tif`, type: COG, 'raster:bands': [band] },
        nir: { href: `https://e84-earth-search-sentinel-data.s3.us-west-2.amazonaws.com/synth/${id}/B08.tif`, type: COG, 'raster:bands': [band] },
      },
    }));
    useAppStore.setState({
      items, groups: [{ key: ['2026-08-01'], label: '2026-08-01', items }], activeGroupIndex: 0,
      selectedIds: scenes, layers: [], focusMode: false, error: null,
      flyToView: { center: [11.05, 47.35], zoom: 10 },
    });
    useProcessingStore.getState().openProcessing();
  }, { footprint: FOOTPRINT, scenes: SCENES });
  await page.getByRole('button', { name: /Band math/ }).first().click();
  const expression = page.locator('textarea[id$="-expression"]');
  const started = Date.now();
  await expression.fill('(nir - red) / (nir + red)');
  let last = 0;
  for (let i = 0; i < 60; i++) {
    await page.waitForTimeout(500);
    if (seen.tiles.length > 0 && seen.tiles.length === last) break;
    last = seen.tiles.length;
  }
  await page.waitForLoadState('networkidle').catch(() => {});
  const seconds = ((Date.now() - started) / 1000).toFixed(1);
  const valid = seen.statistics.filter((p) => p.includes('nir+red') || p.includes('nir + red'));
  if (seen.probes.length < 1) problems.push('the valid expression asked no probe');
  if (valid.length !== 1) problems.push(`the valid expression asked its statistics ${valid.length} times, not once`);
  if (seen.tiles.length === 0) problems.push('the valid expression drew no tile');
  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_preview.png`) });
  const tilesBefore = seen.tiles.length;
  const statisticsBefore = seen.statistics.length;

  // 4. A half-typed expression: the probe refuses it, nothing else of it goes out.
  await expression.fill('(nir - red) / (nir +');
  await page.waitForTimeout(2500);
  const note = await page.evaluate(() => document.querySelector('.processing-panel')?.textContent ?? '');
  if (!/No preview: /.test(note)) problems.push('the panel does not say why there is no preview');
  if (seen.statistics.slice(statisticsBefore).some((p) => p.includes('(nir +"'))) problems.push('the refused expression asked statistics');
  // The refused expression ends in `+`; the tiles of the valid one may still be arriving.
  if (seen.tiles.slice(tilesBefore).some((p) => p.includes('(nir +"'))) problems.push('the refused expression asked tiles');
  const scroll = await page.evaluate(() => {
    const panel = document.querySelector('.processing-panel');
    return panel ? panel.scrollWidth > panel.clientWidth + 1 : false;
  });
  if (scroll) problems.push('the panel scrolls sideways');
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_refused.png`) });
  const shown = page.locator('.processing-panel p.hint-text', { hasText: 'No preview: ' });
  if ((await shown.count()) === 1) {
    await shown.scrollIntoViewIfNeeded();
    if (!(await shown.isVisible())) problems.push('the refusal cannot be scrolled into view');
    await shown.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_note.png`) });
  } else problems.push('the refusal is not one line of the panel');
  await context.close();
  return { name, problems, detail: `${seen.tiles.length} tiles, ${seen.probes.length} probes, ${seen.statistics.length} statistics, preview ${seconds} s` };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) {
    const result = await check(browser, theme, viewport);
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name} — ${result.detail}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
