// Browser check of the range measured over the AOI (NM4-19b): with "AOI only" the preview posts the order of the job and
// takes its colour scale from the answer; where the answer is a coarser read, or fails, the tooltip of "Preview" says so.
// Runs in the light and the dark theme at three widths with answers made up here, and fails when
//   - the AOI or the order is in any URL the browser asks for, or the POST has a query,
//   - the range fields, the tooltip or the unit are not what the case expects,
//   - a field, the unit, the colormap or a button of the range row overlaps another or leaves the panel;
// it writes a screenshot of the range row per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/area-range.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-area-range');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };
const COORDINATES = ['10.4', '10.6', '50.4', '50.6', 'recipe_version', 'coordinates'];
const SCENE_HINT = 'Range measured over the first whole scene';
const COARSE_HINT = 'Range measured on a coarser read; the result may differ';

// What the tiler would answer over the AOI, and for the first whole scene.
const band = (values) => ({ name: 'b1', ...(values.unit ? { unit: values.unit } : {}), statistics: { mean: 0.3, valid_percent: 100, ...values.statistics } });
const NDVI = { statistics: { minimum: -1.3, maximum: 1.5, count: 900, percentile_2: 0, percentile_98: 0.91 } };
const DEM = { unit: 'm', statistics: { minimum: -11000, maximum: 8848.86, count: 900, percentile_2: -10000, percentile_98: 8000 } };
const SCENE = { b1: { count: 900, min: 100, max: 2500, percentile_2: 120, percentile_98: 2400, unit: null } };

// What the panel must show for each case: the range fields, the unit, the tooltip of "Preview", the colormap.
const CASES = {
  'exact index with outliers': { area: { status: 200, body: { bands: [band(NDVI)], exact: true, factor: 1 } }, fields: ['-1', '1'], unit: null, hint: null, colormap: 'rdylgn' },
  'coarser read of a DEM': { area: { status: 200, body: { bands: [band(DEM)], exact: false, factor: 4 } }, fields: ['-10000', '8000'], unit: 'm', hint: COARSE_HINT, colormap: 'viridis' },
  'order refused (413)': { area: { status: 413, body: { detail: 'too many files' } }, fields: ['120', '2400'], unit: null, hint: SCENE_HINT, colormap: 'viridis' },
  'tiler down (502)': { area: { status: 502, body: { detail: 'down' } }, fields: ['120', '2400'], unit: null, hint: SCENE_HINT, colormap: 'viridis' },
};

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function check(browser, { name, theme, viewport }) {
  const spec = CASES[name];
  const label = `${name} ${theme} ${viewport}`;
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const urls = [];
  const posts = [];
  page.on('request', (request) => {
    urls.push(request.url());
    if (request.method() === 'POST') posts.push({ url: request.url(), body: request.postData() ?? '' });
  });
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (request.method() === 'POST' && url.pathname === '/collections/sentinel-2-c1-l2a/statistics') return json(spec.area.body, spec.area.status);
    if (url.pathname.endsWith('/statistics')) return json(SCENE);
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const bbox = [10, 50, 11, 51];
    const polygon = { type: 'Polygon', coordinates: [[[10, 50], [11, 50], [11, 51], [10, 51], [10, 50]]] };
    const aoi = { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] };
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
      activeGroupIndex: 0, selectedIds: ['S2B_A'], aoi, aoiPoint: null, layers: [], focusMode: false, error: null,
    });
    useProcessingStore.getState().openProcessing();
  });
  await page.getByRole('button', { name: 'AOI only' }).click();
  await page.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  await page.waitForSelector('.pp-range input[type=number]', { timeout: 15000 });
  await page.waitForTimeout(900);
  const report = await page.evaluate(() => {
    const row = document.querySelector('.pp-range');
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const leaves = [
      ...[...row.querySelectorAll('input')].map((e) => ({ what: `field ${e.value}`, e })),
      ...[...row.querySelectorAll('.pp-unit')].map((e) => ({ what: `unit ${e.textContent}`, e })),
      ...[...row.querySelectorAll('select')].map((e) => ({ what: 'colormap', e })),
      ...[...row.querySelectorAll('button')].map((e) => ({ what: `button ${e.textContent}`, e })),
    ].map(({ what, e }) => ({ what, ...box(e), cutOff: e.tagName === 'INPUT' && e.scrollWidth > e.clientWidth }));
    const body = row.closest('.pp-body') ?? document.querySelector('.processing-panel');
    const badge = document.querySelector('section[aria-label="Preview on the map"] .pp-heading .pp-badge:not(.loading)');
    return {
      theme: document.querySelector('.app')?.dataset.theme,
      leaves,
      panel: box(body),
      scrolls: body.scrollWidth > body.clientWidth + 1,
      unit: row.querySelector('.pp-unit')?.textContent ?? null,
      fields: [...row.querySelectorAll('input')].map((e) => e.value),
      colormap: row.querySelector('select')?.value,
      hint: badge?.getAttribute('title') ?? null,
      badge: badge ? box(badge) : null,
      heading: box(document.querySelector('section[aria-label="Preview on the map"] .pp-heading')),
    };
  });
  const problems = [];
  const expect = (what, got, want) => { if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`); };
  expect('the range fields', report.fields, spec.fields);
  expect('the unit', report.unit, spec.unit);
  expect('the colormap', report.colormap, spec.colormap);
  expect('the tooltip of "Preview"', report.hint, spec.hint);
  if (!report.badge) problems.push('no "Preview" badge');
  else if (report.badge.x + report.badge.width > report.heading.x + report.heading.width + 0.5) problems.push('the badge leaves its heading');
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}, not ${THEMES[theme]}`);
  if (report.scrolls) problems.push('the panel scrolls sideways');
  const { leaves, panel } = report;
  for (let i = 0; i < leaves.length; i++) {
    for (let j = i + 1; j < leaves.length; j++) if (overlap(leaves[i], leaves[j])) problems.push(`${leaves[i].what} overlaps ${leaves[j].what}`);
    if (leaves[i].x < panel.x - 0.5 || leaves[i].x + leaves[i].width > panel.x + panel.width + 0.5) problems.push(`${leaves[i].what} leaves the panel`);
    if (leaves[i].cutOff) problems.push(`${leaves[i].what} is cut off`);
  }
  // The AOI goes in the body of the one POST and nowhere else: no URL names it, and the POST has no query.
  if (posts.length !== 1) problems.push(`${posts.length} POSTs, not 1`);
  for (const post of posts) {
    if (new URL(post.url).pathname !== '/collections/sentinel-2-c1-l2a/statistics' || new URL(post.url).search !== '') problems.push(`the POST goes to ${new URL(post.url).pathname}${new URL(post.url).search}`);
    if (!post.body.includes('10.4')) problems.push('the AOI is not in the body of the POST');
  }
  for (const url of urls) for (const word of COORDINATES) if (decodeURIComponent(url).includes(word)) problems.push(`a URL names ${word}`);
  fs.mkdirSync(OUT, { recursive: true });
  await page.locator('section[aria-label="Preview on the map"]').first().screenshot({ path: path.join(OUT, `${label.replace(/[ ()]/g, '_')}.png`) });
  await context.close();
  return { label, problems, report };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const name of Object.keys(CASES)) for (const theme of ['light', 'dark']) for (const viewport of Object.keys(VIEWPORTS)) {
    const result = await check(browser, { name, theme, viewport });
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.label} [${result.report.fields.join(' … ')}] ${JSON.stringify(result.report.hint)}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : 'every case as expected; the AOI only in the body of the POST; nothing overlaps or leaves the panel');
  process.exit(failed ? 1 : 0);
})();
