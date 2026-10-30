// Browser check of DS-02c: "Advanced search" in the control menu. With made-up answers of the search and the coverage
// (the server below applies the filters it is sent, so the results and the coverage count show their effect), it
// does the clicks of a user in a real browser and fails when
//   - the section is there for the DEM alone, or is missing for a dataset with filters;
//   - the dataset box lists the DEM, or the values of one dataset show up in another;
//   - the search, "Load more"-style repeat or the coverage map do not carry the filters of their own dataset
//     (and only those), or carry a filter whose field is wrong;
//   - a wrong field (also half-typed text such as "20-") is not marked, or "Search" is not held back;
//   - "Clear search results" drops the filters, or "Reset filters" does not;
//   - a field, the unit or the box overlaps another or leaves the panel; the page scrolls sideways;
//   - an item id or the AOI shows up in a URL the browser asks for (the filters go in the body of a POST);
// and writes a screenshot per step. The requests of the search and the coverage go to <OUT>/requests.json, so that
// the backend's own reader can be run over them.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/advanced-search.cjs            # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-advanced-search');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };
const AOI = { type: 'Polygon', coordinates: [[[10.3, 47.3], [10.7, 47.3], [10.7, 47.7], [10.3, 47.7], [10.3, 47.3]]] };
const SECRETS = ['10.3', '47.7', 'SCENE_'];

// The filters as the registry publishes them (`earthx:search_filters`, dumped from `earthx.catalog.collection`).
const CLOUD = { property: 'eo:cloud_cover', kind: 'range', title: 'Cloud cover', description: 'Share of the whole scene (about 110 × 110 km) covered by clouds, as reported by the source.', unit: '%', within_aoi: true, type: 'number', minimum: 0, maximum: 100 };
const NODATA = { property: 's2:nodata_pixel_percentage', kind: 'range', title: 'No data', description: 'Share of the scene tile without image data, e.g. at the edge of a swath.', unit: '%', within_aoi: false, type: 'number', minimum: 0, maximum: 100 };
const SATELLITE = { property: 'platform', kind: 'values', title: 'Satellite', description: 'The satellite that took the scene.', unit: null, within_aoi: false, type: 'string', oneOf: [{ const: 'sentinel-2a', title: 'Sentinel-2A' }, { const: 'sentinel-2b', title: 'Sentinel-2B' }, { const: 'sentinel-2c', title: 'Sentinel-2C' }] };
const ORBIT = { property: 'sat:relative_orbit', kind: 'range', title: 'Relative orbit', description: 'The orbit track the scene lies on.', unit: null, within_aoi: false, type: 'integer', minimum: 1, maximum: 175 };

const CAPABILITIES = { roi: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false };
const viewer = (browse, groupBy) => ({ group_by: groupBy, min_zoom: 0, max_zoom: 14, browse, quicklook_nodata_max: null, results_group_by: groupBy });
const collection = (id, title, filters, extra = {}) => ({
  id, type: 'Collection', title, description: 'made up', license: 'proprietary', links: [],
  extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2015-06-27T00:00:00Z', null]] } },
  'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { ...CAPABILITIES, time_range: true, single_coverage_product: false },
  'earthx:viewer': viewer('quicklook', ['datetime']),
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:search_filters': filters,
  ...extra,
});
const COLLECTIONS = [
  collection('sentinel-2-c1-l2a', 'Sentinel-2 L2A', [CLOUD, NODATA, SATELLITE]),
  collection('radar-made-up', 'Radar (made up)', [ORBIT]),
  collection('cop-dem-glo-30', 'Copernicus DEM', [], {
    'earthx:capabilities': { ...CAPABILITIES, time_range: false, single_coverage_product: true },
    'earthx:viewer': viewer('full_resolution', ['start_datetime']),
  }),
];

const polygon = (b) => ({ type: 'Polygon', coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] });
// Three scenes of the optical dataset and their properties; the made-up server filters by them.
const SCENES = [
  { id: 'SCENE_A', cloud: 5, platform: 'sentinel-2a' },
  { id: 'SCENE_B', cloud: 35, platform: 'sentinel-2b' },
  { id: 'SCENE_C', cloud: 80, platform: 'sentinel-2c' },
].map((s, i) => ({
  id: s.id, collection: 'sentinel-2-c1-l2a', bbox: [10 + i * 0.01, 47, 11, 48], geometry: polygon([10 + i * 0.01, 47, 11, 48]),
  properties: { datetime: `2026-07-0${i + 1}T10:00:00Z`, 'eo:cloud_cover': s.cloud, platform: s.platform, 's2:nodata_pixel_percentage': 1 },
  assets: {},
}));

// What the made-up source does with a query of the STAC extension.
function matches(item, query) {
  return Object.entries(query ?? {}).every(([property, operators]) => {
    const value = item.properties[property];
    return Object.entries(operators).every(([op, bound]) => (op === 'gte' ? value >= bound : op === 'lte' ? value <= bound : op === 'in' ? bound.includes(value) : false));
  });
}

const box = (el) => el.boundingBox();
const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const problems = [];
  const requests = { search: [], coverage: [] };
  const urls = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('request', (request) => urls.push(request.url()));
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: COLLECTIONS });
    if (url.pathname === '/stac/search') {
      const body = JSON.parse(route.request().postData() ?? '{}');
      requests.search.push(body);
      const own = body.query_by_collection?.['sentinel-2-c1-l2a'];
      const wanted = body.collections ?? [];
      const features = wanted.includes('sentinel-2-c1-l2a') ? SCENES.filter((item) => matches(item, own)) : [];
      return json({ type: 'FeatureCollection', features, numberMatched: features.length, numberReturned: features.length, links: [] });
    }
    if (url.pathname.startsWith('/coverage/')) {
      const dataset = decodeURIComponent(url.pathname.split('/')[2]);
      const query = url.searchParams.get('query');
      requests.coverage.push({ dataset, query: query === null ? null : JSON.parse(query) });
      const n = dataset === 'sentinel-2-c1-l2a' ? SCENES.filter((item) => matches(item, query && JSON.parse(query))).length : 9;
      return json({
        dataset_id: dataset, grid: 'geotile', level: 4, counting: 'centroid', cells: n ? [{ k: '4/8/5', n }] : [], counted: n, total_count: n,
        completeness: 'complete', max_count: n, histogram: [], histogram_interval: 'month', footprints_advised: false, from_cache: false, extent: null, area: null, ignored_filters: [],
      });
    }
    return json({ detail: 'not made up' }, 404);
  });
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${what}${detail ? `: ${detail}` : ''}`); };
  // Runs a function on the store of the page; `arg` is handed over as data.
  const store = (fn, arg) => page.evaluate(async ([src, data]) => {
    const { useAppStore } = await import('/src/store.ts');
    return (0, eval)(`(${src})`)(useAppStore, data);
  }, [fn.toString(), arg]);
  const fields = (name) => page.locator(`.advanced-body input[aria-label="${name}"]`);
  const sections = () => page.locator('.advanced-search').count();
  const searchCount = () => requests.search.length;
  const settle = () => page.waitForTimeout(900); // the debounce of the coverage map is 400 ms
  const search = async () => {
    const before = searchCount();
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    for (let i = 0; i < 50 && searchCount() === before; i++) await page.waitForTimeout(100);
    await page.waitForTimeout(500);
  };

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await store((s, aoi) => { s.getState().setAoi(aoi); s.getState().flyTo([9.2, 46.6, 12.2, 48.4]); }, AOI);
  const pick = (title) => page.locator('.dataset-toggle', { hasText: title }).first().click();

  // 1. The DEM alone has no filters: no section, nothing greyed out in its place.
  await pick('Copernicus DEM');
  expect('a section for the DEM alone', (await sections()) === 0);
  await shot('1-dem-only');

  // 2. Sentinel-2 alone: the section is there, closed; opened it shows the three filters of the registry.
  await pick('Sentinel-2 L2A');
  expect('no section for Sentinel-2', (await sections()) === 1);
  await page.locator('.advanced-head').scrollIntoViewIfNeeded();
  await shot('2-closed');
  await page.locator('.advanced-head').click();
  const titles = await page.locator('.advanced-body .filter-title').allTextContents();
  expect('the filters of Sentinel-2', JSON.stringify(titles) === JSON.stringify(['Cloud cover', 'No data', 'Satellite']), JSON.stringify(titles));
  const tip = await page.locator('.advanced-body .filter-title').first().getAttribute('title');
  expect('the tooltip of Cloud cover', tip === CLOUD.description, tip);
  expect('the placeholders are the bounds', (await fields('Cloud cover, from').getAttribute('placeholder')) === '0' && (await fields('Cloud cover, to').getAttribute('placeholder')) === '100');
  await page.locator('.advanced-body').scrollIntoViewIfNeeded();
  await shot('3-open');

  // 3. Layout: the fields, the unit and the box stay inside the panel and apart; the page does not scroll sideways.
  const panel = await box(page.locator('.control-scroll'));
  const row = await page.locator('.advanced-body .filter-range').first().evaluate((el) => [...el.children].map((c) => c.getBoundingClientRect().toJSON()));
  for (const [i, a] of row.entries()) {
    expect(`cell ${i} of the range row leaves the panel`, a.x >= panel.x - 1 && a.x + a.width <= panel.x + panel.width + 1, JSON.stringify(a));
    for (const b of row.slice(i + 1)) expect(`two cells of the range row overlap`, !overlap(a, b));
  }
  // Nothing of the section leaves the panel. (At 320 px the toolbar buttons above it do, by 8 px, with or without the
  // section: not DS-02c's, so the panel as a whole is not asked to fit.)
  const outside = await page.locator('.advanced-search').evaluate((el) => {
    const right = el.closest('.control-scroll').getBoundingClientRect().right;
    return [...el.querySelectorAll('*')].filter((c) => c.getBoundingClientRect().width > 0 && c.getBoundingClientRect().right > right + 0.5).map((c) => c.className || c.tagName);
  });
  expect('a part of the section leaves the panel', outside.length === 0, outside.join(', '));
  expect('the page scrolls sideways', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));

  // 4. The coverage map of Sentinel-2 asks without filters; a filter changes it at once, and only the filters of its dataset.
  await page.getByRole('button', { name: 'Coverage', exact: true }).click();
  await settle();
  const first = requests.coverage.at(-1);
  expect('the coverage asked with a filter before any was set', first && first.query === null, JSON.stringify(first));
  await fields('Cloud cover, to').fill('20');
  await settle();
  const filtered = requests.coverage.at(-1);
  expect('the coverage does not follow the filter', JSON.stringify(filtered) === JSON.stringify({ dataset: 'sentinel-2-c1-l2a', query: { 'eo:cloud_cover': { lte: 20 } } }), JSON.stringify(filtered));
  // Only the scene with 5 % clouds is left of the three.
  const counted = await page.locator('.legend-scale-labels span').last().textContent();
  expect('the coverage count does not narrow', counted === '1', counted);
  await shot('4-coverage');
  await page.locator('.advanced-body .filter-check', { hasText: 'Sentinel-2A' }).click();
  await settle();
  expect('the coverage with two filters', JSON.stringify(requests.coverage.at(-1).query) === JSON.stringify({ 'eo:cloud_cover': { lte: 20 }, platform: { in: ['sentinel-2a'] } }), JSON.stringify(requests.coverage.at(-1)));

  // 5. The head says for how many datasets filters are set, closed too.
  expect('the head', (await page.locator('.advanced-head').textContent()).includes('· 1 dataset'), await page.locator('.advanced-head').textContent());
  expect('the tooltip of the head', (await page.locator('.advanced-head').getAttribute('title')) === 'Sentinel-2 L2A: Cloud cover, Satellite');

  // 6. A wrong field is marked and holds "Search" back; the coverage goes without it.
  await fields('Cloud cover, to').fill('500');
  await settle();
  expect('"Search" is not held back', await page.getByRole('button', { name: 'Search', exact: true }).isDisabled());
  expect('the wrong field is not marked', (await fields('Cloud cover, to').getAttribute('aria-invalid')) === 'true');
  expect('the message under the field', (await page.locator('.advanced-body .hint-text.error').textContent()) === 'Between 0 and 100');
  expect('the coverage asked with the wrong field', JSON.stringify(requests.coverage.at(-1).query) === JSON.stringify({ platform: { in: ['sentinel-2a'] } }), JSON.stringify(requests.coverage.at(-1)));
  await page.locator('.advanced-body').scrollIntoViewIfNeeded();
  await shot('5-wrong');
  // Typed key by key, as a user does: "20-" is no number, and the field says so instead of dropping the filter.
  await fields('Cloud cover, to').fill('');
  await fields('Cloud cover, to').pressSequentially('20-');
  expect('half-typed text is not marked', (await fields('Cloud cover, to').getAttribute('aria-invalid')) === 'true' && (await page.locator('.advanced-body .hint-text.error').textContent()) === 'Enter a number');
  expect('half-typed text does not hold "Search" back', await page.getByRole('button', { name: 'Search', exact: true }).isDisabled());
  expect('half-typed text was dropped from the head', (await page.locator('.advanced-head').textContent()).includes('· 1 dataset'), await page.locator('.advanced-head').textContent());
  await fields('Cloud cover, from').fill('50');
  await fields('Cloud cover, to').fill('20');
  expect('"from above to" is not marked on both', (await fields('Cloud cover, from').getAttribute('aria-invalid')) === 'true' && (await fields('Cloud cover, to').getAttribute('aria-invalid')) === 'true');
  await fields('Cloud cover, from').fill('');
  await fields('Cloud cover, to').fill('40');
  expect('"Search" is still held back once the fields are right', !(await page.getByRole('button', { name: 'Search', exact: true }).isDisabled()));

  // 7. The search carries the filters; the made-up source narrows, and the list shows it.
  await search();
  const body = requests.search.at(-1);
  expect('the search body', JSON.stringify(body.query_by_collection) === JSON.stringify({ 'sentinel-2-c1-l2a': { 'eo:cloud_cover': { lte: 40 }, platform: { in: ['sentinel-2a'] } } }) && !('query' in body), JSON.stringify(body));
  await page.waitForSelector('.results-panel');
  // Of the three scenes the source holds, the cloud limit and the satellite leave one.
  const listed = await page.locator('.results-panel .rg-count').first().textContent();
  expect('the scenes after the filters', listed === '1', listed);
  await shot('6-results');

  // 8. "Clear search results" keeps the filters.
  await page.getByRole('button', { name: /Clear search results/ }).click();
  await page.waitForSelector('.control-panel');
  await page.locator('.advanced-body').scrollIntoViewIfNeeded();
  expect('the filters after "Clear search results"', (await fields('Cloud cover, to').inputValue()) === '40');

  // 9. A second dataset with filters of its own: the box offers it, the DEM stays out of it, the values stay apart.
  await store((s) => s.getState().setMultiSelect(true));
  await pick('Radar (made up)');
  await pick('Copernicus DEM');
  await page.waitForSelector('.advanced-body .dataset-select-box:not([disabled])');
  await page.locator('.advanced-body .dataset-select-box').click();
  const entries = await page.locator('.dataset-select-list [role="option"]').allTextContents();
  expect('the datasets in the box', JSON.stringify(entries) === JSON.stringify(['Sentinel-2 L2A', 'Radar (made up)']), JSON.stringify(entries));
  expect('the dot of the dataset with filters', (await page.locator('.dataset-select-list [role="option"] .filter-dot').count()) === 1);
  await shot('7-box');
  await page.locator('.dataset-select-list [role="option"]', { hasText: 'Radar' }).click();
  expect('the values of Sentinel-2 show up in the radar', (await page.locator('.advanced-body .filter-title').allTextContents()).join() === 'Relative orbit');
  expect('the radar field is not empty', (await fields('Relative orbit, from').inputValue()) === '');
  await fields('Relative orbit, from').fill('22.5');
  expect('a fraction for whole numbers is not marked', (await page.locator('.advanced-body .hint-text.error').textContent()) === 'Whole numbers only');
  await fields('Relative orbit, from').fill('22');
  await fields('Relative orbit, to').fill('22');
  expect('the head counts two datasets', (await page.locator('.advanced-head').textContent()).includes('· 2 datasets'), await page.locator('.advanced-head').textContent());
  await shot('8-two-datasets');
  await search();
  const two = requests.search.at(-1);
  expect('the filters of each dataset', JSON.stringify(two.query_by_collection) === JSON.stringify({
    'sentinel-2-c1-l2a': { 'eo:cloud_cover': { lte: 40 }, platform: { in: ['sentinel-2a'] } },
    'radar-made-up': { 'sat:relative_orbit': { gte: 22, lte: 22 } },
  }), JSON.stringify(two));

  // 10. "Reset filters" takes back the dataset shown and leaves the other.
  await page.getByRole('button', { name: 'Clear search results' }).click().catch(() => {});
  await page.waitForSelector('.control-panel');
  await page.getByRole('button', { name: 'Reset filters' }).click();
  expect('"Reset filters" left values', (await fields('Relative orbit, from').inputValue()) === '' && (await page.locator('.reset-filters').count()) === 0);
  expect('"Reset filters" took back the other dataset too', (await page.locator('.advanced-head').textContent()).includes('· 1 dataset'), await page.locator('.advanced-head').textContent());

  // 11. No scene name, no AOI, no filter in a URL the browser asked for. The one place an AOI is in a URL is the `bbox` of
  // `GET /coverage` (M3-19, existing behaviour, not touched by DS-02c): it is left out here, the rest of that URL is checked.
  for (const url of urls) {
    const asked = new URL(url);
    if (asked.pathname.startsWith('/src/') || asked.pathname.startsWith('/node_modules/') || asked.pathname.startsWith('/@')) continue;
    if (asked.pathname.startsWith('/coverage/')) asked.searchParams.delete('bbox');
    const text = decodeURIComponent(asked.pathname + asked.search);
    for (const secret of SECRETS) expect('a URL carries something it should not', !text.includes(secret), `${secret} in ${text.slice(0, 120)}`);
    if (asked.pathname === '/stac/search') expect('the search has a query string', asked.search === '', asked.search.slice(0, 80));
  }
  await context.close();
  return { label, problems, requests };
}

(async () => {
  const browser = await chromium.launch();
  const all = [];
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const result = await check(browser, { theme, viewport });
      all.push({ label: result.label, requests: result.requests });
      console.log(`${result.problems.length === 0 ? 'PASS' : 'FAIL'}  ${result.label}`);
      for (const problem of result.problems) console.log(`      - ${problem}`);
      failed ||= result.problems.length > 0;
    }
  }
  fs.writeFileSync(path.join(OUT, 'requests.json'), JSON.stringify(all, null, 1));
  await browser.close();
  console.log(`screenshots and requests in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
