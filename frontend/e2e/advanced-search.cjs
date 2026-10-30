// Browser check of DS-02c: the button "Advanced search" above "Search" and the pop-up it opens. With made-up answers of
// the search and the coverage (the server below applies the filters it is sent, so the results and the coverage count
// show their effect), it does the clicks of a user in a real browser and fails when
//   - the button is there for the DEM alone, is missing for a dataset with filters, or is not right above "Search" and as wide;
//   - the pop-up is cut off by the panel or the window, a filter of the 13 the registry offers cannot be reached (also at
//     320 px wide), or "Done" and the dataset box do not stay in view while the fields scroll;
//   - the filters do not stand under the headings of the registry, in its order;
//   - the search, "Load more"-style repeat or the coverage map do not carry the filters of their own dataset
//     (and only those), or carry a filter whose field is wrong;
//   - Escape, "Done" or a click beside the pop-up lose a value, or Escape in the list of datasets closes the pop-up too;
//   - a wrong field (also half-typed text such as "20-") is not marked, or "Search" is not held back, also after "Done";
//   - "Clear search results" drops the filters, or "Reset filters" does not;
//   - a field, the unit or the box overlaps another or leaves the pop-up; the page scrolls sideways;
//   - an item id or the AOI shows up in a URL the browser asks for (the filters go in the body of a POST);
// and writes a screenshot per step. The requests of the search and the coverage go to <OUT>/requests.json, so that
// the backend's own reader can be run over them.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/advanced-search.cjs            # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-advanced-search');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };
const AOI = { type: 'Polygon', coordinates: [[[10.3, 47.3], [10.7, 47.3], [10.7, 47.7], [10.3, 47.7], [10.3, 47.3]]] };
const SECRETS = ['10.3', '47.7', 'SCENE_'];

// The filters of Sentinel-2 L2A as the registry publishes them (`earthx:search_filters`, written from
// `earthx.catalog.collection` on 30.10.2026) and one made-up filter of the radar dataset below.
const SENTINEL_2_FILTERS = [
  {"property": "eo:cloud_cover", "kind": "range", "title": "Cloud cover", "description": "Share of the whole scene (about 110 × 110 km) covered by clouds, as reported by the source.", "unit": "%", "within_aoi": true, "group": "Clouds", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:thin_cirrus_percentage", "kind": "range", "title": "Thin cirrus", "description": "Share of the scene covered by thin cirrus clouds. Part of the cloud cover.", "unit": "%", "within_aoi": false, "group": "Clouds", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:cloud_shadow_percentage", "kind": "range", "title": "Cloud shadow", "description": "Share of the scene lying in the shadow of clouds. Not part of the cloud cover.", "unit": "%", "within_aoi": false, "group": "Clouds", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:nodata_pixel_percentage", "kind": "range", "title": "No data", "description": "Share of the scene tile without image data, e.g. at the edge of a swath.", "unit": "%", "within_aoi": false, "group": "Scene", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:snow_ice_percentage", "kind": "range", "title": "Snow and ice", "description": "Share of the scene classified as snow or ice.", "unit": "%", "within_aoi": false, "group": "Scene", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:water_percentage", "kind": "range", "title": "Water", "description": "Share of the scene classified as water.", "unit": "%", "within_aoi": false, "group": "Scene", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:vegetation_percentage", "kind": "range", "title": "Vegetation", "description": "Share of the scene classified as vegetation.", "unit": "%", "within_aoi": false, "group": "Scene", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:not_vegetated_percentage", "kind": "range", "title": "Not vegetated", "description": "Share of the scene classified as not vegetated, e.g. bare ground or built-up areas.", "unit": "%", "within_aoi": false, "group": "Scene", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "s2:degraded_msi_data_percentage", "kind": "range", "title": "Degraded data", "description": "Share of the scene whose sensor data the source marks as degraded.", "unit": "%", "within_aoi": false, "group": "Scene", "type": "number", "minimum": 0.0, "maximum": 100.0},
  {"property": "platform", "kind": "values", "title": "Satellite", "description": "The satellite that took the scene.", "unit": null, "within_aoi": false, "group": "Acquisition", "type": "string", "oneOf": [{"const": "sentinel-2a", "title": "Sentinel-2A"}, {"const": "sentinel-2b", "title": "Sentinel-2B"}, {"const": "sentinel-2c", "title": "Sentinel-2C"}]},
  {"property": "view:sun_elevation", "kind": "range", "title": "Sun elevation", "description": "Height of the sun above the horizon when the scene was taken. Low values mean long shadows.", "unit": "°", "within_aoi": false, "group": "Acquisition", "type": "number", "minimum": 0.0, "maximum": 90.0},
  {"property": "view:sun_azimuth", "kind": "range", "title": "Sun azimuth", "description": "Direction of the sun when the scene was taken, in degrees clockwise from north.", "unit": "°", "within_aoi": false, "group": "Acquisition", "type": "number", "minimum": 0.0, "maximum": 360.0},
  {"property": "s2:processing_baseline", "kind": "values", "title": "Processing baseline", "description": "Version of the ESA processing that made the scene. A new version comes every few months.", "unit": null, "within_aoi": false, "group": "Acquisition", "type": "string", "oneOf": [{"const": "05.00", "title": "05.00"}, {"const": "05.09", "title": "05.09"}, {"const": "05.10", "title": "05.10"}, {"const": "05.11", "title": "05.11"}, {"const": "05.12", "title": "05.12"}, {"const": "05.13", "title": "05.13"}]},
];
const ORBIT = { property: 'sat:relative_orbit', kind: 'range', title: 'Relative orbit', group: 'Acquisition', description: 'The orbit track the scene lies on.', unit: null, within_aoi: false, type: 'integer', minimum: 1, maximum: 175 };

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
  collection('sentinel-2-c1-l2a', 'Sentinel-2 L2A', SENTINEL_2_FILTERS),
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
  const key = (name) => page.keyboard.press(name);
  const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${what}${detail ? `: ${detail}` : ''}`); };
  // Runs a function on the store of the page; `arg` is handed over as data.
  const store = (fn, arg) => page.evaluate(async ([src, data]) => {
    const { useAppStore } = await import('/src/store.ts');
    return (0, eval)(`(${src})`)(useAppStore, data);
  }, [fn.toString(), arg]);
  const popup = page.locator('.advanced-popup');
  const fields = (name) => popup.locator(`input[aria-label="${name}"]`);
  const button = page.locator('.advanced-btn');
  const searchButton = page.getByRole('button', { name: 'Search', exact: true });
  const searchCount = () => requests.search.length;
  const settle = () => page.waitForTimeout(900); // the debounce of the coverage map is 400 ms
  const search = async () => {
    const before = searchCount();
    await searchButton.click();
    for (let i = 0; i < 50 && searchCount() === before; i++) await page.waitForTimeout(100);
    await page.waitForTimeout(500);
  };
  const done = () => popup.getByRole('button', { name: 'Done' }).click();
  const rect = (locator) => locator.evaluate((el) => el.getBoundingClientRect().toJSON());
  const inside = (inner, outer, slack = 1) => inner.x >= outer.x - slack && inner.y >= outer.y - slack && inner.x + inner.width <= outer.x + outer.width + slack && inner.y + inner.height <= outer.y + outer.height + slack;
  const pick = (title) => page.locator('.dataset-toggle', { hasText: title }).first().click();
  const view = VIEWPORTS[viewport];

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await store((s, aoi) => { s.getState().setAoi(aoi); s.getState().flyTo([9.2, 46.6, 12.2, 48.4]); }, AOI);

  // 1. The DEM alone has no filters: no button, nothing greyed out in its place.
  await pick('Copernicus DEM');
  expect('a button for the DEM alone', (await button.count()) === 0);
  await shot('1-dem-only');

  // 2. Sentinel-2: the button is there, right above "Search" and as wide, in the footer that stays in view.
  await pick('Sentinel-2 L2A');
  expect('no button for Sentinel-2', (await button.count()) === 1);
  const b = await rect(button);
  const sb = await rect(searchButton);
  expect('the button is not as wide as "Search"', Math.abs(b.width - sb.width) <= 1 && Math.abs(b.x - sb.x) <= 1, `${b.width} against ${sb.width}`);
  expect('the button is not right above "Search"', sb.y - (b.y + b.height) >= 0 && sb.y - (b.y + b.height) <= 12, `${sb.y - (b.y + b.height)} px apart`);
  expect('the button is out of view', b.y + b.height <= view.height && b.y >= 0);
  expect('the button has a count before a filter is set', (await button.textContent()) === 'Advanced search', await button.textContent());
  await shot('2-button');

  // 3. The pop-up: over the map (not inside the panel, not cut off), under the registry's headings, every filter reachable.
  await button.click();
  await popup.waitFor();
  expect('the pop-up is no dialog', (await popup.getAttribute('role')) === 'dialog');
  expect('the pop-up lies in the panel, which cuts it off', await popup.evaluate((el) => !el.closest('.control-panel')));
  const p = await rect(popup);
  expect('the pop-up leaves the window', inside(p, { x: 0, y: 0, width: view.width, height: view.height }), JSON.stringify(p));
  expect('the pop-up is not as wide as the button', Math.abs(p.width - b.width) <= 2, `${p.width} against ${b.width}`);
  const headings = await popup.locator('.filter-group-title').allTextContents();
  expect('the headings', JSON.stringify(headings) === JSON.stringify(['Clouds', 'Scene', 'Acquisition']), JSON.stringify(headings));
  const titles = await popup.locator('.filter-title').allTextContents();
  const expectedTitles = SENTINEL_2_FILTERS.map((f) => f.title);
  expect('the filters of Sentinel-2 in the order of the registry', JSON.stringify(titles) === JSON.stringify(expectedTitles), JSON.stringify(titles));
  expect('the tooltip of Cloud cover', (await popup.locator('.filter-title').first().getAttribute('title')) === SENTINEL_2_FILTERS[0].description);
  expect('the placeholders are the bounds', (await fields('Cloud cover, from').getAttribute('placeholder')) === '0' && (await fields('Cloud cover, to').getAttribute('placeholder')) === '100');
  expect('the unit of the sun elevation', (await popup.locator('.filter-range', { has: page.locator('input[aria-label="Sun elevation, to"]') }).locator('.filter-unit').textContent()) === '°');
  expect('the focus is not in the pop-up', await popup.evaluate((el) => el.contains(document.activeElement)));
  await shot('3-open');

  // Every field can be reached by scrolling the fields, with the dataset box above and "Done" below staying in view.
  const frame = await rect(popup.locator('.advanced-fields'));
  const dialogRect = await rect(popup);
  for (const title of expectedTitles) {
    const target = popup.locator('.filter-field', { has: page.locator(`.filter-title:text-is("${title}")`) });
    await target.scrollIntoViewIfNeeded();
    const t = await rect(target);
    expect(`"${title}" cannot be reached in the pop-up`, inside(t, frame, 2), `${JSON.stringify(t)} in ${JSON.stringify(frame)}`);
  }
  const box = await rect(popup.locator('.dataset-select'));
  const doneRect = await rect(popup.getByRole('button', { name: 'Done' }));
  expect('the dataset box is not at the top of the pop-up', inside(box, dialogRect, 12));
  expect('"Done" is out of view', inside(doneRect, dialogRect, 12) && doneRect.y + doneRect.height <= view.height);
  await shot('3b-scrolled');
  await popup.locator('.advanced-fields').evaluate((el) => { el.scrollTop = 0; });

  // 4. Layout: the fields, the unit and the box stay inside the pop-up and apart; the page does not scroll sideways.
  for (const row of await popup.locator('.filter-range').all()) {
    const cells = await row.evaluate((el) => [...el.children].map((c) => c.getBoundingClientRect().toJSON()));
    for (const [i, a] of cells.entries()) {
      expect(`cell ${i} of a range row leaves the pop-up sideways`, a.x >= p.x - 1 && a.x + a.width <= p.x + p.width + 1, JSON.stringify(a));
      for (const c of cells.slice(i + 1)) expect('two cells of a range row overlap', !overlap(a, c));
    }
  }
  expect('a part of the pop-up leaves it', await popup.evaluate((el) => [...el.querySelectorAll('*')].filter((c) => c.closest('.advanced-fields') ? false : c.getBoundingClientRect().right > el.getBoundingClientRect().right + 1).length === 0));
  expect('the page scrolls sideways', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));

  // 5. The coverage map of Sentinel-2 asks without filters; a filter changes it at once, and only the filters of its dataset.
  await key('Escape');
  await page.getByRole('button', { name: 'Coverage', exact: true }).click();
  await settle();
  const first = requests.coverage.at(-1);
  expect('the coverage asked with a filter before any was set', first && first.query === null, JSON.stringify(first));
  await button.click();
  await fields('Cloud cover, to').fill('20');
  await settle();
  const filtered = requests.coverage.at(-1);
  expect('the coverage does not follow the filter', JSON.stringify(filtered) === JSON.stringify({ dataset: 'sentinel-2-c1-l2a', query: { 'eo:cloud_cover': { lte: 20 } } }), JSON.stringify(filtered));
  // Only the scene with 5 % clouds is left of the three.
  const counted = await page.locator('.legend-scale-labels span').last().textContent();
  expect('the coverage count does not narrow', counted === '1', counted);
  await popup.locator('.filter-check', { hasText: 'Sentinel-2A' }).scrollIntoViewIfNeeded();
  await popup.locator('.filter-check', { hasText: 'Sentinel-2A' }).click();
  await settle();
  expect('the coverage with two filters', JSON.stringify(requests.coverage.at(-1).query) === JSON.stringify({ 'eo:cloud_cover': { lte: 20 }, platform: { in: ['sentinel-2a'] } }), JSON.stringify(requests.coverage.at(-1)));
  await shot('4-coverage');

  // 6. The button counts the filters set, closed too; the tooltip names them.
  expect('the count on the button', (await button.textContent()) === 'Advanced search · 2', await button.textContent());
  expect('the tooltip of the button', (await button.getAttribute('title')) === 'Sentinel-2 L2A: Cloud cover, Satellite', await button.getAttribute('title'));

  // 7. A wrong field is marked, "Done" closes the pop-up all the same, "Search" stays held back, the coverage goes without it.
  await popup.locator('.advanced-fields').evaluate((el) => { el.scrollTop = 0; });
  await fields('Cloud cover, to').fill('500');
  await settle();
  expect('"Search" is not held back', await searchButton.isDisabled());
  expect('the wrong field is not marked', (await fields('Cloud cover, to').getAttribute('aria-invalid')) === 'true');
  expect('the message under the field', (await popup.locator('.filter-field .hint-text.error').textContent()) === 'Between 0 and 100');
  expect('the coverage asked with the wrong field', JSON.stringify(requests.coverage.at(-1).query) === JSON.stringify({ platform: { in: ['sentinel-2a'] } }), JSON.stringify(requests.coverage.at(-1)));
  await shot('5-wrong');
  await done();
  expect('"Done" did not close the pop-up', (await popup.count()) === 0);
  expect('"Search" is not held back after "Done"', await searchButton.isDisabled());
  expect('the button is not red', (await button.getAttribute('class')).includes('wrong'));
  expect('the hint under "Search"', (await page.locator('.control-footer').textContent()).includes('Correct the filters in Advanced search.'));
  await shot('5b-done-wrong');
  await button.click();
  expect('the wrong value is gone after reopening', (await fields('Cloud cover, to').inputValue()) === '500');
  // Typed key by key, as a user does: "20-" is no number, and the field says so instead of dropping the filter.
  await fields('Cloud cover, to').fill('');
  await fields('Cloud cover, to').pressSequentially('20-');
  expect('half-typed text is not marked', (await fields('Cloud cover, to').getAttribute('aria-invalid')) === 'true' && (await popup.locator('.filter-field .hint-text.error').textContent()) === 'Enter a number');
  expect('half-typed text does not hold "Search" back', await searchButton.isDisabled());
  await fields('Cloud cover, from').fill('50');
  await fields('Cloud cover, to').fill('20');
  expect('"from above to" is not marked on both', (await fields('Cloud cover, from').getAttribute('aria-invalid')) === 'true' && (await fields('Cloud cover, to').getAttribute('aria-invalid')) === 'true');
  await fields('Cloud cover, from').fill('');
  await fields('Cloud cover, to').fill('40');
  expect('"Search" is still held back once the fields are right', !(await searchButton.isDisabled()));

  // 8. Escape and a click beside the pop-up close it; the values stay; the focus goes back to the button.
  await key('Escape');
  expect('Escape did not close the pop-up', (await popup.count()) === 0);
  expect('the focus is not on the button after Escape', await button.evaluate((el) => el === document.activeElement));
  await button.press('Enter');
  await popup.waitFor();
  expect('the value was lost with Escape', (await fields('Cloud cover, to').inputValue()) === '40');
  await fields('Cloud cover, to').press('Tab');
  expect('Tab closed the pop-up', (await popup.count()) === 1);
  const q = await rect(popup);
  await page.mouse.click(q.x + q.width / 2, Math.max(2, q.y / 2));
  expect('a click beside the pop-up did not close it', (await popup.count()) === 0, JSON.stringify(q));
  await button.click();
  expect('the value was lost with a click beside', (await fields('Cloud cover, to').inputValue()) === '40');
  await done();

  // 9. The search carries the filters; the made-up source narrows, and the list shows it.
  await search();
  const body = requests.search.at(-1);
  expect('the search body', JSON.stringify(body.query_by_collection) === JSON.stringify({ 'sentinel-2-c1-l2a': { 'eo:cloud_cover': { lte: 40 }, platform: { in: ['sentinel-2a'] } } }) && !('query' in body), JSON.stringify(body));
  await page.waitForSelector('.results-panel');
  // Of the three scenes the source holds, the cloud limit and the satellite leave one.
  const listed = await page.locator('.results-panel .rg-count').first().textContent();
  expect('the scenes after the filters', listed === '1', listed);
  await shot('6-results');

  // 10. "Clear search results" keeps the filters.
  await page.getByRole('button', { name: /Clear search results/ }).click();
  await page.waitForSelector('.control-panel');
  expect('the count after "Clear search results"', (await button.textContent()) === 'Advanced search · 2', await button.textContent());

  // 11. A second dataset with filters of its own: the box offers it, the DEM stays out of it, the values stay apart.
  await store((s) => s.getState().setMultiSelect(true));
  await pick('Radar (made up)');
  await pick('Copernicus DEM');
  await button.click();
  const dataset = popup.locator('.dataset-select-box');
  await page.waitForSelector('.advanced-popup .dataset-select-box:not([disabled])');
  await dataset.click();
  const entries = await page.locator('.dataset-select-list [role="option"]').allTextContents();
  expect('the datasets in the box', JSON.stringify(entries) === JSON.stringify(['Sentinel-2 L2A', 'Radar (made up)']), JSON.stringify(entries));
  expect('the dot of the dataset with filters', (await page.locator('.dataset-select-list [role="option"] .filter-dot').count()) === 1);
  await shot('7-box');
  await key('Escape');
  expect('Escape in the list closed the pop-up too', (await popup.count()) === 1 && (await page.locator('.dataset-select-list').count()) === 0);
  await dataset.click();
  await page.locator('.dataset-select-list [role="option"]', { hasText: 'Radar' }).click();
  expect('a click in the list closed the pop-up', (await popup.count()) === 1);
  expect('the values of Sentinel-2 show up in the radar', (await popup.locator('.filter-title').allTextContents()).join() === 'Relative orbit');
  expect('a heading for the one group of the radar', (await popup.locator('.filter-group-title').count()) === 0);
  expect('the radar field is not empty', (await fields('Relative orbit, from').inputValue()) === '');
  await fields('Relative orbit, from').fill('22.5');
  expect('a fraction for whole numbers is not marked', (await popup.locator('.hint-text.error').textContent()) === 'Whole numbers only');
  await fields('Relative orbit, from').fill('22');
  await fields('Relative orbit, to').fill('22');
  expect('the button counts three filters', (await button.textContent()) === 'Advanced search · 3', await button.textContent());
  await shot('8-two-datasets');
  await done();
  await search();
  const two = requests.search.at(-1);
  expect('the filters of each dataset', JSON.stringify(two.query_by_collection) === JSON.stringify({
    'sentinel-2-c1-l2a': { 'eo:cloud_cover': { lte: 40 }, platform: { in: ['sentinel-2a'] } },
    'radar-made-up': { 'sat:relative_orbit': { gte: 22, lte: 22 } },
  }), JSON.stringify(two));

  // 12. "Reset filters" takes back the dataset shown and leaves the other.
  await page.getByRole('button', { name: 'Clear search results' }).click().catch(() => {});
  await page.waitForSelector('.control-panel');
  await button.click();
  await popup.getByRole('button', { name: 'Reset filters' }).click();
  expect('"Reset filters" left values', (await fields('Relative orbit, from').inputValue()) === '' && (await popup.getByRole('button', { name: 'Reset filters' }).count()) === 0);
  expect('"Reset filters" took back the other dataset too', (await button.textContent()) === 'Advanced search · 2', await button.textContent());
  await done();

  // 13. No scene name, no AOI, no filter in a URL the browser asked for. The one place an AOI is in a URL is the `bbox` of
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
      for (const problem of result.problems.slice(0, 8)) console.log(`      - ${problem.slice(0, 200)}`);
      failed ||= result.problems.length > 0;
    }
  }
  fs.writeFileSync(path.join(OUT, 'requests.json'), JSON.stringify(all, null, 1));
  await browser.close();
  console.log(`screenshots and requests in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
