// Browser check of DS-03b: the switch "Filter within AOI only" at the top of "Advanced search" and what the results list
// says of a search that measures the filters inside the AOI. With made-up answers (a server that checks 100 scenes per answer, finds a few and
// says how far it got), it does the clicks of a user in a real browser and fails when
//   - the switch is missing at the top of the pop-up of Sentinel-2, is there for the DEM, does not name the filters it
//     changes in its tooltip (and none that does not depend on the area), or does not lock, with the reason in its tooltip, without an AOI, without both dates or with a point (and free with all three);
//   - the search does not ask `earthx:aoi_cloud_cover` and `earthx:aoi_nodata` in place of the scene properties, or asks them
//     while the switch is locked;
//   - the search does not go on by itself after answers without a scene, the list head does not say "n found / m checked"
//     after each answer, "Stop" is missing while it goes on or stays after, or "Stop" loses what was found;
//   - "Load more" is offered while the search goes on, is missing after "Stop" (also when nothing was found yet), or does
//     not go on from where it stopped;
//   - the switch is not locked, with the reason, for an AOI with more than 20 000 points;
//   - the list shows a value of the share in a scene or a time step, or a "Sort:" row (Otto, 31.10.2026: both are gone);
//   - the hints of the limit and of scenes that could not be read are missing, or the date fallback runs;
//   - the coverage map asks the cloud range while the switch is in use;
//   - the pop-up or the list head overlaps or leaves the window, the page scrolls sideways, in light and dark, wide and
//     narrow;
//   - the AOI shows up in a URL the browser asks for (it goes in the body of a POST).
// and writes a screenshot per step.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/within-aoi.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-within-aoi');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };
const AOI = { type: 'Polygon', coordinates: [[[10.3, 47.3], [10.7, 47.3], [10.7, 47.7], [10.3, 47.7], [10.3, 47.3]]] };
const SECRETS = ['10.3', '47.7'];

const S2 = 'sentinel-2-c1-l2a';
const CLOUD_FILTER = { property: 'eo:cloud_cover', kind: 'range', title: 'Cloud cover', description: 'Share of the whole scene covered by clouds, as reported by the source.', unit: '%', within_aoi: 'earthx:aoi_cloud_cover', group: 'Clouds', type: 'number', minimum: 0, maximum: 100 };
const NODATA_FILTER = { property: 's2:nodata_pixel_percentage', kind: 'range', title: 'No data', description: 'Share of the scene without image data.', unit: '%', within_aoi: 'earthx:aoi_nodata', group: 'Scene', type: 'number', minimum: 0, maximum: 100 };
const PLATFORM_FILTER = { property: 'platform', kind: 'values', title: 'Satellite', description: 'The satellite that took the scene.', unit: null, within_aoi: null, group: 'Acquisition', type: 'string', oneOf: [{ const: 'sentinel-2a', title: 'Sentinel-2A' }, { const: 'sentinel-2b', title: 'Sentinel-2B' }] };
const MASK = {
  asset: 'scl', band: 'scl', suggested: [3, 8, 9, 10], reference: 'https://example.invalid/classes', note: '',
  classes: [{ value: 0, label: 'No data' }, { value: 3, label: 'Cloud shadows' }, { value: 8, label: 'Cloud medium probability' }, { value: 9, label: 'Cloud high probability' }, { value: 10, label: 'Thin cirrus' }],
  cloud_classes: [8, 9, 10], cloud_note: "Sen2Cor's classification can miss thin cirrus and can take snow or bright ground for clouds.",
};
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
  collection(S2, 'Sentinel-2 L2A', [CLOUD_FILTER, NODATA_FILTER, PLATFORM_FILTER], { 'earthx:mask': MASK }),
  collection('cop-dem-glo-30', 'Copernicus DEM', [], {
    'earthx:capabilities': { ...CAPABILITIES, time_range: false, single_coverage_product: true },
    'earthx:viewer': viewer('full_resolution', ['start_datetime']),
  }),
];

const polygon = (b) => ({ type: 'Polygon', coordinates: [[[b[0], b[1]], [b[2], b[1]], [b[2], b[3]], [b[0], b[3]], [b[0], b[1]]]] });
// Eight scenes the made-up source holds, newest first: the share of clouds in the AOI and the pixels it is made of. The
// scenes of one day are one time step.
const MADE = [
  { id: 'SCENE_1', day: '2026-07-20', cloud: 12, data: 100, dataPercent: 100 },
  { id: 'SCENE_2', day: '2026-07-18', cloud: 2, data: 100, dataPercent: 64 },
  { id: 'SCENE_3', day: '2026-07-18', cloud: 0.4, data: 100, dataPercent: 100 },
  { id: 'SCENE_4', day: '2026-07-15', cloud: 18, data: 100, dataPercent: 100 },
  { id: 'SCENE_5', day: '2026-07-11', cloud: 7, data: 100, dataPercent: 100 },
  { id: 'SCENE_6', day: '2026-07-08', cloud: 19.5, data: 100, dataPercent: 100 },
];
const feature = (s, i) => ({
  id: s.id, collection: S2, bbox: [10 + i * 0.01, 47, 11, 48], geometry: polygon([10 + i * 0.01, 47, 11, 48]),
  properties: {
    datetime: `${s.day}T10:00:00Z`, 'eo:cloud_cover': 50, 'earthx:aoi_cloud_cover': s.cloud,
    'earthx:aoi_measure': { data_percent: s.dataPercent, cloud_pixels: s.cloud, data_pixels: s.data, resolution: 80 },
  },
  assets: {},
});

// The made-up server walks the made-up scenes in answers of its own: the answer to a token is the next step.
//   1: 100 checked, nothing within the limit      2: 200 checked, SCENE_1 to 3     3: (slow) 300 checked, SCENE_4 to 5
//   4: 400 checked, nothing                       5: 500 checked, SCENE_6, limit reached, 2 scenes unreadable
const STEPS = [
  { checked: 100, found: 0, scenes: [], next: 't2' },
  { checked: 200, found: 3, scenes: [0, 1, 2], next: 't3' },
  { checked: 300, found: 5, scenes: [3, 4], next: 't4', slow: 2500 },
  { checked: 400, found: 5, scenes: [], next: 't5' },
  { checked: 500, found: 6, scenes: [5], next: null, limit: true, unreadable: 2 },
];

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const problems = [];
  const observed = [];
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
      const asked = body.query_by_collection?.[S2] ?? {};
      // The made-up server measures whatever stands under a platform property; it applies the cloud range only.
      const measured = Object.keys(asked).some((key) => key.startsWith('earthx:')) ? (asked['earthx:aoi_cloud_cover'] ?? {}) : null;
      if (!measured) return json({ type: 'FeatureCollection', features: [], numberMatched: 0, numberReturned: 0, links: [] });
      const at = body.token ? Number(body.token.slice(1)) - 1 : 0;
      const step = STEPS[at];
      if (step.slow) await new Promise((resolve) => setTimeout(resolve, step.slow));
      const passes = (i) => MADE[i].cloud <= (measured.lte ?? 100);
      const features = step.scenes.filter(passes).map((i) => feature(MADE[i], i));
      // What the server counts is what passes, over the whole search up to this answer.
      const found = STEPS.slice(0, at + 1).flatMap((x) => x.scenes).filter(passes).length;
      return json({
        type: 'FeatureCollection', features, numberReturned: features.length,
        links: step.next ? [{ rel: 'next', href: '/stac/search', method: 'POST', body: { token: step.next } }] : [],
        'earthx:aoi_filter': { checked: step.checked, found, unreadable: step.unreadable ?? 0, limit_reached: step.limit ?? false },
      });
    }
    if (url.pathname.startsWith('/coverage/')) {
      const asked = route.request().method() === 'POST' ? JSON.parse(route.request().postData() ?? '{}').query : url.searchParams.get('query') && JSON.parse(url.searchParams.get('query'));
      requests.coverage.push({ query: asked ?? null });
      return json({
        dataset_id: S2, grid: 'geotile', level: 4, counting: 'centroid', cells: [{ k: '4/8/5', n: 3 }], counted: 3, total_count: 3,
        completeness: 'complete', max_count: 3, histogram: [], histogram_interval: 'month', footprints_advised: false, from_cache: false, extent: null, area: null, ignored_filters: [],
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
  const fields = (name) => popup.locator(`input[aria-label="${name}"]`);
  const button = page.locator('.advanced-btn');
  const within = popup.locator('.within-aoi');
  const searchButton = page.getByRole('button', { name: 'Search', exact: true });
  const rect = (locator) => locator.evaluate((el) => el.getBoundingClientRect().toJSON());
  const inside = (inner, outer, slack = 1) => inner.x >= outer.x - slack && inner.y >= outer.y - slack && inner.x + inner.width <= outer.x + outer.width + slack && inner.y + inner.height <= outer.y + outer.height + slack;
  const view = VIEWPORTS[viewport];
  const text = async (locator) => ((await locator.textContent()) ?? '').replace(/\s+/g, ' ').trim();
  const locked = () => within.evaluate((el) => el.classList.contains('locked'));
  const progress = page.locator('.aoi-progress');
  const stop = page.locator('.aoi-stop');
  const asked = () => requests.search.length;
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

  // 1. Without an AOI and dates the switch is there and locked, with the reason in its tooltip.
  await button.click();
  await popup.waitFor();
  expect('no switch under "Cloud cover"', (await within.count()) === 1);
  expect('the switch is not at the top of the pop-up, over the fields', await within.evaluate((el) => el.nextElementSibling?.classList.contains('advanced-fields') && el.previousElementSibling?.classList.contains('dataset-select')));
  expect('the switch is not named "Filter within AOI only"', (await text(within)) === 'Filter within AOI only', await text(within));
  expect('a second switch', (await popup.locator('.within-aoi').count()) === 1);
  expect('the switch is not locked without AOI and dates', await locked());
  expect('the tooltip of the locked switch', (await within.getAttribute('title')) === 'Draw an AOI and set a date range first', await within.getAttribute('title'));
  await within.locator('input').click({ force: true });
  expect('the locked switch went on', !(await within.locator('input').isChecked()));
  await shot('1-locked');
  await page.keyboard.press('Escape');

  // 2. An AOI is not enough, one date is not enough; a point is no area; AOI and both dates free it.
  await store((s, aoi) => { s.getState().setAoi(aoi); s.getState().flyTo([9.2, 46.6, 12.2, 48.4]); }, AOI);
  await button.click();
  expect('the switch is free with an AOI alone', await locked());
  await page.keyboard.press('Escape');
  await store((s) => s.getState().setDateFrom('2026-07-01'));
  await button.click();
  expect('the switch is free with one date', await locked());
  await page.keyboard.press('Escape');
  await store((s) => s.getState().setDateTo('2026-07-31'));
  await button.click();
  expect('the switch is locked with an AOI and both dates', !(await locked()));
  const tip = await within.getAttribute('title');
  expect('the tooltip names the filters it changes', tip.includes('Cloud cover (classes 8, 9, 10; cloud shadows do not count), No data. Others are unchanged.'), tip);
  expect('the tooltip names a filter that does not depend on the area', !tip.includes('Satellite'), tip);
  expect('the tooltip names the limit', tip.includes('checks up to 500 scenes'), tip);
  expect('the tooltip carries the note of the registry', tip.includes("Sen2Cor's classification can miss thin cirrus"), tip);
  expect('the tooltip names the coverage map', tip.includes('The coverage map shows the scene filter only.'), tip);
  await shot('2-free');
  await page.keyboard.press('Escape');
  await store((s) => s.setState({ aoiPoint: { type: 'Point', coordinates: [10.5, 47.5] } }));
  await button.click();
  expect('the tooltip for a point', (await within.getAttribute('title')) === 'Draw an area to use this filter', await within.getAttribute('title'));
  await page.keyboard.press('Escape');
  await store((s) => s.setState({ aoiPoint: null }));

  // 3. The DEM alone has no switch.
  await page.locator('.dataset-toggle', { hasText: 'Sentinel-2 L2A' }).first().click();
  await page.locator('.dataset-toggle', { hasText: 'Copernicus DEM' }).first().click();
  expect('a button for the DEM alone', (await button.count()) === 0);
  await page.locator('.dataset-toggle', { hasText: 'Copernicus DEM' }).first().click();
  await page.locator('.dataset-toggle', { hasText: 'Sentinel-2 L2A' }).first().click();

  // 4. The switch on, the limit typed: the layout holds and the coverage map asks without the cloud range.
  await button.click();
  await popup.waitFor();
  await within.locator('input').click();
  await fields('Cloud cover, to').fill('20');
  await fields('No data, to').fill('50');
  expect('the switch does not stay on', await within.locator('input').isChecked());
  const p = await rect(popup);
  expect('the pop-up leaves the window', inside(p, { x: 0, y: 0, width: view.width, height: view.height }), JSON.stringify(p));
  const w = await rect(within);
  expect('the switch leaves the pop-up', inside(w, p, 2), JSON.stringify(w));
  const firstField = await rect(popup.locator('.advanced-fields'));
  expect('the switch overlaps the fields', !overlap(w, firstField), `${JSON.stringify(w)} ${JSON.stringify(firstField)}`);
  expect('the page scrolls sideways', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot('3-on');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Coverage', exact: true }).click();
  await page.waitForTimeout(900);
  expect('the coverage asked the cloud range of the scene while the switch is on', JSON.stringify(requests.coverage.at(-1)) === JSON.stringify({ query: null }), JSON.stringify(requests.coverage.at(-1)));
  await page.getByRole('button', { name: 'Coverage', exact: true }).click().catch(() => {});

  // 5. The search: the range under the clouds in the AOI, the walk goes on after an answer without a scene, "found /
  // checked" after each answer, "Stop" while it goes on.
  const before = asked();
  await searchButton.click();
  await until('the first answer did not come', async () => asked() > before);
  const first = requests.search.at(-1);
  expect('the ranges are not under the properties of the AOI', JSON.stringify(first.query_by_collection) === JSON.stringify({ [S2]: { 'earthx:aoi_cloud_cover': { lte: 20 }, 'earthx:aoi_nodata': { lte: 50 } } }), JSON.stringify(first.query_by_collection));
  expect('the search has no date range with both ends', /^2026-07-01T00:00:00Z\/2026-07-31T23:59:59Z$/.test(first.datetime ?? ''), first.datetime);
  expect('the search sends the AOI beside the bbox', !('earthx:aoi' in first));
  await until('the list did not open with the scenes of the second answer', async () => (await page.locator('.results-panel .rg-count').count()) > 0);
  expect('the walk did not go on after an answer without a scene', asked() >= before + 2, String(asked() - before));
  await until('"Stop" is missing while the search goes on', async () => (await stop.count()) > 0);
  const head = await text(progress);
  expect('the head does not say how far it got', /^3 found \/ 200 checked/.test(head), head);
  expect('"Load more" is offered while the search goes on', (await page.locator('.load-more').count()) === 0);
  await shot('4-walking');
  const pr = await rect(progress);
  expect('the progress overlaps its "Stop"', !overlap(await rect(progress.locator('span').first()), await rect(stop)));
  expect('the progress leaves the panel', inside(pr, await rect(page.locator('.results-panel')), 2), JSON.stringify(pr));

  // 6. "Stop" while the slow answer is on its way: what is found stays, "Load more" is there.
  await stop.click();
  await until('"Stop" stays after it was pressed', async () => (await stop.count()) === 0);
  const stopped = await text(progress);
  expect('the head after "Stop"', /^3 found \/ 200 checked$/.test(stopped), stopped);
  expect('the scenes after "Stop"', (await page.locator('.results-panel .result-group').count()) === 2, String(await page.locator('.results-panel .result-group').count()));
  expect('no "Load more" after "Stop"', (await page.locator('.load-more button').count()) === 1);
  await shot('5-stopped');

  // 7. "Load more" goes on from where "Stop" ended, to the limit: the hints, no "Load more" any more, no date fallback.
  await page.locator('.load-more button').click();
  await until('"Load more" did not reach the end', async () => (await page.locator('.load-more button').count()) === 0 && (await stop.count()) === 0, 15000);
  const last = requests.search.at(-1);
  expect('"Load more" did not go on from the token of the answer before', requests.search.some((r) => r.token === 't3') && last.token === 't5', JSON.stringify(requests.search.map((r) => r.token)));
  const end = await text(progress);
  expect('the head at the limit', /^6 found \/ 500 checked$/.test(end), end);
  const notes = await page.locator('.dataset-select-note').allTextContents();
  expect('the hint of the limit', notes.includes('Checked 500 scenes. Narrow the date range to search further.'), JSON.stringify(notes));
  expect('the hint of the unreadable scenes', notes.includes('2 scenes could not be checked'), JSON.stringify(notes));
  await shot('8-limit');
  expect('the date fallback ran', requests.search.every((r) => r.datetime === '2026-07-01T00:00:00Z/2026-07-31T23:59:59Z'));

  // 10. No AOI in a URL.
  for (const url of urls) {
    const asked = new URL(url);
    if (asked.pathname.startsWith('/src/') || asked.pathname.startsWith('/node_modules/') || asked.pathname.startsWith('/@')) continue;
    const text = decodeURIComponent(asked.pathname + asked.search);
    for (const secret of SECRETS) expect('a URL carries something it should not', !text.includes(secret), `${secret} in ${text.slice(0, 120)}`);
    if (asked.pathname === '/stac/search') expect('the search has a query string', asked.search === '', asked.search.slice(0, 80));
  }
  const sideways = () => page.evaluate(() => {
    if (document.documentElement.scrollWidth <= window.innerWidth + 1) return [];
    return [...document.querySelectorAll('body *')]
      .filter((el) => el.getBoundingClientRect().right > window.innerWidth + 1)
      .slice(0, 4)
      .map((el) => `${el.tagName.toLowerCase()}.${String(el.className).slice(0, 30)}`);
  });
  const wide = await sideways();

  // 11. What reaches over the window is told apart from what this task brings: the same search without the switch.
  await page.getByRole('button', { name: /Clear search results/ }).click();
  await page.waitForSelector('.control-panel');
  await button.click();
  await within.locator('input').click();
  await page.keyboard.press('Escape');
  const plain = asked();
  await searchButton.click();
  await until('the plain search did not answer', async () => asked() > plain);
  await page.waitForTimeout(500);
  const baseline = await sideways();
  expect('the page scrolls sideways at the end, in a way the search without the switch does not', wide.every((w) => baseline.includes(w)), `${wide.join('; ')} against ${baseline.join('; ')}`);
  if (wide.length > 0) observed.push(`${label}: the page scrolls sideways at the end (${wide.join(', ')}), as it does after a search without the switch`);

  // 12. "Stop" before a scene was found (Otto, 31.10.2026): the list is there with "0 found / m checked" and "Load more".
  await store((s) => { s.getState().clearSearchResults(); s.setState({ dock: 'controls' }); });
  await page.waitForSelector('.control-panel');
  await button.click();
  await within.locator('input').click();
  await fields('Cloud cover, to').fill('0.1');
  await page.keyboard.press('Escape');
  const none = asked();
  await searchButton.click();
  await until('the third answer was not asked', async () => asked() >= none + 3);
  await page.locator('.toast.busy .aoi-stop').click();
  await until('the list did not open after "Stop"', async () => (await page.locator('.results-panel').count()) > 0);
  expect('the head after "Stop" without a scene', (await text(progress.locator('span').first())) === '0 found / 200 checked', await text(progress));
  expect('"Stop" stays after it was pressed', (await stop.count()) === 0);
  expect('no "Load more" after "Stop" without a scene', (await page.locator('.load-more button').count()) === 1);
  await shot('9-stopped-empty');
  const more = asked();
  await page.locator('.load-more button').click();
  await until('"Load more" did not ask on from the token', async () => asked() > more);
  expect('"Load more" did not go on from the token of the answer before', requests.search[more].token === 't3', String(requests.search[more].token));
  await stop.click().catch(() => {});

  // 13. More than 20 000 points: the switch is locked, with the reason.
  await store((s) => { s.getState().clearSearchResults(); s.setState({ dock: 'controls' }); });
  await page.waitForSelector('.control-panel');
  await store((s) => {
    const ring = Array.from({ length: 20001 }, (_, i) => [10.5 + 0.4 * Math.cos((i / 20001) * 2 * Math.PI), 47.5 + 0.4 * Math.sin((i / 20001) * 2 * Math.PI)]);
    s.setState({ aoi: { type: 'Polygon', coordinates: [[...ring, ring[0]]] } });
  });
  await button.click();
  expect('the switch is not locked for too many points', await locked());
  expect('the tooltip for too many points', (await within.getAttribute('title')) === 'The area has too many points for this filter', await within.getAttribute('title'));
  await shot('10-too-many');
  await context.close();
  return { label, problems, requests, observed };
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
      for (const note of result.observed) console.log(`      (observed) ${note.slice(0, 220)}`);
      failed ||= result.problems.length > 0;
    }
  }
  fs.writeFileSync(path.join(OUT, 'requests.json'), JSON.stringify(all, null, 1));
  await browser.close();
  console.log(`screenshots and requests in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
