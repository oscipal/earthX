// Browser check of DS-03c: "Evaluate: per pass / per scene" and the filter "AOI coverage" in "Advanced search". With made-up
// answers it does the clicks of a user in a real browser and fails when
//   - "Evaluate" is missing at the top of the pop-up of Sentinel-2, is there for a dataset that does not offer it, is not
//     two segment buttons with "per pass" first and pressed, or does not keep the choice;
//   - the (i) beside it does not hold the explanation with its example, or the explanation stands as a paragraph;
//   - "AOI coverage" is missing, is not a slider with a field that say the same, is not locked with the reason in its tooltip
//     without an AOI and for a point, wants a date range, or keeps its value when the AOI goes;
//   - the search does not ask `earthx:evaluate` (per pass) and `earthx:aoi_coverage`, asks the first per scene, or sends the
//     AOI in a URL;
//   - the coverage map is asked the coverage;
//   - the DEM alone does not show the coverage and nothing else;
//   - the pop-up overlaps or leaves the window, the page scrolls sideways, in light and dark, wide and narrow.
// and writes a screenshot per step.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/evaluate-coverage.cjs          # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-evaluate-coverage');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };
const AOI = { type: 'Polygon', coordinates: [[[10.3, 47.3], [10.7, 47.3], [10.7, 47.7], [10.3, 47.7], [10.3, 47.3]]] };
const SECRETS = ['10.3', '47.7'];

const S2 = 'sentinel-2-c1-l2a';
const DEM = 'cop-dem-glo-30';
const share = (property, title, group, within, areaBased = true) => ({ property, kind: 'range', title, description: `${title}.`, unit: '%', within_aoi: within, area_based: areaBased, group, type: 'number', minimum: 0, maximum: 100 });
const FILTERS = [
  share('eo:cloud_cover', 'Cloud cover', 'Clouds', 'earthx:aoi_cloud_cover'),
  share('s2:thin_cirrus_percentage', 'Thin cirrus', 'Clouds', 'earthx:aoi_thin_cirrus'),
  share('s2:nodata_pixel_percentage', 'No data', 'Scene', 'earthx:aoi_nodata'),
  share('s2:water_percentage', 'Water', 'Scene', 'earthx:aoi_water'),
  share('s2:degraded_msi_data_percentage', 'Degraded data', 'Scene', null),
  { property: 'platform', kind: 'values', title: 'Satellite', description: 'The satellite.', unit: null, within_aoi: null, area_based: false, group: 'Acquisition', type: 'string', oneOf: [{ const: 'sentinel-2a', title: 'Sentinel-2A' }, { const: 'sentinel-2b', title: 'Sentinel-2B' }] },
];
const MASK = {
  asset: 'scl', band: 'scl', suggested: [3, 8, 9, 10], reference: 'https://example.invalid/classes', note: '',
  classes: [{ value: 0, label: 'No data' }, { value: 6, label: 'Water' }, { value: 8, label: 'Cloud medium probability' }, { value: 10, label: 'Thin cirrus' }],
  cloud_classes: [8, 9, 10], cloud_note: "Sen2Cor's classification can miss thin cirrus.",
  share_classes: { 'earthx:aoi_thin_cirrus': [10], 'earthx:aoi_water': [6] },
};
const CAPABILITIES = { roi: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false };
const viewer = (browse, groupBy) => ({ group_by: groupBy, min_zoom: 0, max_zoom: 14, browse, quicklook_nodata_max: null, results_group_by: groupBy });
const collection = (id, title, extra) => ({
  id, type: 'Collection', title, description: 'made up', license: 'proprietary', links: [],
  extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2015-06-27T00:00:00Z', null]] } },
  'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { ...CAPABILITIES, time_range: true, single_coverage_product: false },
  'earthx:viewer': viewer('quicklook', ['datetime', 's2:datatake_id']),
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 255]], colormap_name: null, expression: null, resampling: 'nearest' },
  ...extra,
});
const COLLECTIONS = [
  collection(S2, 'Sentinel-2 L2A', { 'earthx:search_filters': FILTERS, 'earthx:mask': MASK, 'earthx:search_capabilities': { evaluate: true, aoi_coverage: true } }),
  collection(DEM, 'Copernicus DEM', {
    'earthx:search_filters': [], 'earthx:search_capabilities': { evaluate: false, aoi_coverage: true },
    'earthx:capabilities': { ...CAPABILITIES, time_range: false, single_coverage_product: true },
    'earthx:viewer': viewer('full_resolution', ['start_datetime']),
  }),
];

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
      requests.search.push(JSON.parse(route.request().postData() ?? '{}'));
      return json({
        type: 'FeatureCollection', features: [], numberReturned: 0, links: [],
        'earthx:aoi_filter': { checked: 12, found: 0, unreadable: 0, limit_reached: false },
      });
    }
    if (url.pathname.startsWith('/coverage/')) {
      requests.coverage.push({ query: url.searchParams.get('query') });
      return json({
        dataset_id: S2, grid: 'geotile', level: 4, counting: 'centroid', cells: [], counted: 0, total_count: 0,
        completeness: 'complete', max_count: 0, histogram: [], histogram_interval: 'month', footprints_advised: false, from_cache: false, extent: null, area: null, ignored_filters: [],
      });
    }
    return json({ detail: 'not made up' }, 404);
  });
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${what}${detail ? `: ${detail}` : ''}`); };
  const store = (fn, arg) => page.evaluate(async ([src, data]) => {
    const { useAppStore } = await import('/src/store.ts');
    return (0, eval)(`(${src})`)(useAppStore, data);
  }, [fn.toString(), arg]);
  const popup = page.locator('.advanced-popup');
  const button = page.locator('.advanced-btn');
  const choice = popup.locator('.evaluate-choice');
  const coverage = popup.locator('.filter-coverage');
  const slider = coverage.locator('input[type="range"]');
  const number = coverage.locator('input[type="text"]');
  const searchButton = page.getByRole('button', { name: 'Search', exact: true });
  const rect = (locator) => locator.evaluate((el) => el.getBoundingClientRect().toJSON());
  const inside = (inner, outer, slack = 1) => inner.x >= outer.x - slack && inner.y >= outer.y - slack && inner.x + inner.width <= outer.x + outer.width + slack && inner.y + inner.height <= outer.y + outer.height + slack;
  const text = async (locator) => ((await locator.textContent()) ?? '').replace(/\s+/g, ' ').trim();
  const view = VIEWPORTS[viewport];
  const close = () => popup.locator('.advanced-top .close-x').click();
  const until = async (what, test, ms = 8000) => {
    for (let waited = 0; waited < ms; waited += 100) {
      if (await test()) return true;
      await page.waitForTimeout(100);
    }
    expect(what, false);
    return false;
  };

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await page.locator('.dataset-toggle', { hasText: 'Sentinel-2 L2A' }).first().click();

  // 1. "Evaluate": two segment buttons at the top, per pass first and pressed; the explanation behind the (i).
  await button.click();
  await popup.waitFor();
  expect('"Evaluate" is missing', (await choice.count()) === 1);
  const buttons = choice.locator('.btn.seg');
  expect('"Evaluate" is not "per pass", "per scene"', JSON.stringify(await buttons.allTextContents()) === JSON.stringify(['per pass', 'per scene']), JSON.stringify(await buttons.allTextContents()));
  expect('"per pass" is not pressed at first', (await buttons.nth(0).getAttribute('aria-pressed')) === 'true' && (await buttons.nth(1).getAttribute('aria-pressed')) === 'false');
  expect('"Evaluate" is not a group', (await choice.getAttribute('role')) === 'group');
  const order = await popup.locator('.advanced-popup-body').evaluate((el) => [...el.children].map((c) => c.className.split(' ')[0]));
  expect('"Evaluate" is not between the dataset box and the switch', JSON.stringify(order) === JSON.stringify(['advanced-top', 'evaluate-choice', 'within-aoi-row', 'advanced-fields', 'advanced-actions']), JSON.stringify(order));
  const evaluateTip = (await choice.locator('.tip').getAttribute('data-tip')) ?? '';
  expect('the (i) of "Evaluate" has no example', /Per pass/.test(evaluateTip) && /Per scene/.test(evaluateTip) && /Example/.test(evaluateTip) && /merged/.test(evaluateTip), evaluateTip);
  expect('the explanation of "Evaluate" stands as a paragraph', !(await text(popup)).includes('Example'));
  const rows = [await rect(choice), await rect(popup.locator('.within-aoi-row')), await rect(popup.locator('.advanced-fields'))];
  expect('"Evaluate" overlaps the switch or the fields', !overlap(rows[0], rows[1]) && !overlap(rows[0], rows[2]), JSON.stringify(rows));
  const p = await rect(popup);
  expect('the pop-up leaves the window', inside(p, { x: 0, y: 0, width: view.width, height: view.height }), JSON.stringify(p));
  expect('"Evaluate" leaves the pop-up', inside(rows[0], p, 2), JSON.stringify(rows[0]));
  await shot('1-evaluate');

  // 2. "AOI coverage": locked without an AOI, with the reason; free with an AOI and no dates; locked for a point.
  expect('"AOI coverage" is missing', (await coverage.count()) === 1);
  expect('"AOI coverage" is not locked without an AOI', (await slider.isDisabled()) && (await number.isDisabled()));
  expect('the reason it is locked', (await coverage.getAttribute('data-tip')) === 'Draw an AOI to use this filter', await coverage.getAttribute('data-tip'));
  expect('the (i) of "AOI coverage" does not say outlines are not pixels', /outlines/.test((await popup.locator('.filter-title .tip').last().getAttribute('data-tip')) ?? '') && /not the valid pixels/.test((await popup.locator('.filter-title .tip').last().getAttribute('data-tip')) ?? ''));
  await shot('2-coverage-locked');
  await close();
  await store((s, aoi) => { s.getState().setAoi(aoi); s.getState().flyTo([9.2, 46.6, 12.2, 48.4]); }, AOI);
  await button.click();
  expect('"AOI coverage" wants a date range', !(await slider.isDisabled()) && !(await number.isDisabled()));
  await close();
  await store((s) => s.setState({ aoiPoint: { type: 'Point', coordinates: [10.5, 47.5] } }));
  await button.click();
  expect('"AOI coverage" is free for a point', await number.isDisabled());
  expect('the reason for a point', (await coverage.getAttribute('data-tip')) === 'Draw an area to use this filter', await coverage.getAttribute('data-tip'));
  await close();
  await store((s) => s.setState({ aoiPoint: null }));

  // 3. Slider and field say the same; "0" is no filter.
  await button.click();
  await slider.evaluate((el) => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set.call(el, '65'); el.dispatchEvent(new Event('input', { bubbles: true })); });
  await until('the field did not follow the slider', async () => (await number.inputValue()) === '65');
  await number.fill('40');
  expect('the slider did not follow the field', (await slider.inputValue()) === '40', await slider.inputValue());
  await number.fill('150');
  expect('a number above 100 is not marked', (await number.getAttribute('aria-invalid')) === 'true');
  expect('"Search" is not held back by a wrong coverage', await searchButton.isDisabled());
  await number.fill('60');
  expect('the button does not count the coverage', (await text(button)) === 'Advanced search · 1', await text(button));
  await shot('3-coverage-set');
  const q = await rect(coverage);
  expect('the coverage leaves the pop-up', inside(q, await rect(popup), 2), JSON.stringify(q));
  expect('the page scrolls sideways', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await close();

  // 3b. The coverage map is not asked the coverage.
  await page.getByRole('button', { name: 'Coverage', exact: true }).click();
  await page.waitForTimeout(900);
  const last = requests.coverage.at(-1);
  expect('the coverage map was asked the coverage of the AOI', !last || last.query === null || !last.query.includes('earthx:aoi_coverage'), JSON.stringify(last));
  await page.getByRole('button', { name: 'Coverage', exact: true }).click().catch(() => {});

  // 4. The search per pass: both keys in the body, the AOI in no URL.
  const before = requests.search.length;
  await searchButton.click();
  await until('the search was not asked', async () => requests.search.length > before);
  const perPass = requests.search.at(-1);
  expect('the search per pass does not carry earthx:evaluate', perPass['earthx:evaluate'] === 'pass', JSON.stringify(perPass['earthx:evaluate']));
  expect('the coverage is not in the query', JSON.stringify(perPass.query_by_collection) === JSON.stringify({ [S2]: { 'earthx:aoi_coverage': { gte: 60 } } }), JSON.stringify(perPass.query_by_collection));
  expect('the coverage wanted a date range', !('datetime' in perPass), JSON.stringify(perPass.datetime));

  // 5. Per scene: no earthx:evaluate, the coverage stays.
  await store((s) => { s.getState().clearSearchResults(); s.setState({ dock: 'controls' }); });
  await page.waitForSelector('.control-panel');
  await button.click();
  await buttons.nth(1).click();
  expect('"per scene" is not pressed', (await buttons.nth(1).getAttribute('aria-pressed')) === 'true' && (await buttons.nth(0).getAttribute('aria-pressed')) === 'false');
  await shot('4-per-scene');
  await close();
  const second = requests.search.length;
  await searchButton.click();
  await until('the search per scene was not asked', async () => requests.search.length > second);
  const perScene = requests.search.at(-1);
  expect('the search per scene carries earthx:evaluate', !('earthx:evaluate' in perScene), JSON.stringify(perScene['earthx:evaluate']));
  expect('the coverage went with the search per scene', JSON.stringify(perScene.query_by_collection) === JSON.stringify({ [S2]: { 'earthx:aoi_coverage': { gte: 60 } } }), JSON.stringify(perScene.query_by_collection));

  // 7. The coverage goes with the AOI.
  await store((s) => { s.getState().clearSearchResults(); s.setState({ dock: 'controls', aoi: null }); });
  await page.waitForSelector('.control-panel');
  await button.click();
  expect('the coverage kept its number without an AOI', (await number.inputValue()) === '', await number.inputValue());
  expect('"AOI coverage" is not locked without an AOI', await number.isDisabled());
  await close();

  // 8. The DEM alone: the coverage and nothing else.
  await page.locator('.dataset-toggle', { hasText: 'Sentinel-2 L2A' }).first().click();
  await page.locator('.dataset-toggle', { hasText: 'Copernicus DEM' }).first().click();
  await button.click();
  await popup.waitFor();
  expect('"Evaluate" for the DEM', (await choice.count()) === 0);
  expect('the DEM shows more than the coverage', JSON.stringify(await popup.locator('.filter-title').allTextContents()) === JSON.stringify(['AOI coverage']), JSON.stringify(await popup.locator('.filter-title').allTextContents()));
  await shot('5-dem');
  await close();

  const leaked = urls.filter((u) => SECRETS.some((secret) => u.includes(secret)));
  expect('the AOI is in a URL', leaked.length === 0, leaked.join(' ').slice(0, 200));
  await context.close();
  return { label, problems, requests };
}

(async () => {
  const browser = await chromium.launch();
  const all = [];
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      if (process.env.ONLY && process.env.ONLY !== `${theme} ${viewport}`) continue;
      const result = await check(browser, { theme, viewport });
      all.push({ label: result.label, requests: result.requests });
      console.log(`${result.problems.length === 0 ? 'PASS' : 'FAIL'}  ${result.label}`);
      for (const problem of result.problems.slice(0, 10)) console.log(`      - ${problem.slice(0, 220)}`);
      failed ||= result.problems.length > 0;
    }
  }
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'requests.json'), JSON.stringify(all, null, 1));
  await browser.close();
  console.log(`screenshots and requests in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
