// Browser check of UI-05 part 2 (Otto, 06.11.2026) and M5-40 PR 2 (Otto, 15.11.2026): the Data catalogue. With made-up
// answers of the API (full entries, listed ones, pages per category by POST, `/catalogue/categories` and `/regions`) it
// does the clicks of a user in a real browser and fails when
//   - the symbol "Data catalogue" is not the second of the rail, or does not open and close the window;
//   - Esc or a click on the map beside the window closes it, or the red x does not;
//   - the window leaves the browser window, covers the rail, covers an open panel of the dock in a wide window, or the
//     page scrolls sideways;
//   - the groups are not those of `/catalogue/categories` in their order, or a group without entries shows;
//   - a group does not load its next page when its end is scrolled into view, or loads past its last;
//   - a listed entry has a mark or no link "Source", or its details show a row "Keywords" (UI-12: they are gone);
//   - search field and "Filters" are not in the head of the window, or the pop-up "Filters" leaves the browser window;
//   - "Filter by search panel" is not locked without an AOI, or a field of the pop-up has no "×" that empties it;
//   - choosing a category shows other groups, or a region is not sent with the next request;
//   - a text in the search field does not show the hits, listed entries among them, in place of the groups, or its "×"
//     does not bring them back;
//   - the search panel has no tile "Add dataset" after its datasets, or the tile does not open the window;
//   - "Add" does not put the dataset into "Search and area" and turn the pages to it, or "Remove" does not take it out;
//   - in a narrow window the details are not a stage of their own with "Back";
//   - a value of the details runs out of its column;
// and writes a screenshot per step.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/data-catalogue.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-data-catalogue');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

const CAPABILITIES = { roi: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, time_range: true, single_coverage_product: false };
const VIEWER = { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] };
const collection = (id, title, category, extra = {}) => ({
  id, type: 'Collection', title, description: `${title}, made up for this check.`, license: 'proprietary', links: [],
  extent: { spatial: { bbox: [[-180, -60, 180, 84]] }, temporal: { interval: [['2015-06-27T10:25:31Z', null]] } },
  providers: [{ name: 'Made-up agency', roles: ['producer', 'licensor'], url: 'https://example.org' }, { name: 'Made-up host', roles: ['host'] }],
  summaries: { gsd: [10, 20, 60] },
  'earthx:category': category, 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing', name: 'Made-up licence', url: 'https://example.org/licence' },
  'earthx:capabilities': CAPABILITIES, 'earthx:viewer': VIEWER, 'earthx:search_filters': [],
  'earthx:source': { asset_hosts: ['assets.example.org'], endpoint: 'https://stac.example.org/v1', page_url: 'https://viewer.example.org/collections/' + id, source_collection_id: id, data_region: 'unknown' },
  ...extra,
});
const MADE_UP = [
  collection('relief', 'Relief (made up)', 'elevation'),
  collection('optical-b', 'Optical B (made up)', 'optical'),
  collection('optical-a', 'Optical A (made up)', 'optical'),
  collection('landcover', 'Land cover (made up)', 'land_cover'),
  collection('closed', 'Closed radar (made up)', 'radar', { 'earthx:access': { cors: null, account: 'free_account' } }),
  collection('proto', 'Prototype radar (made up)', 'radar', { 'earthx:legal_status': 'unclear', 'earthx:legal_note': 'No terms published (made up)' }),
];
const listed = (id, title, category) => ({
  id, type: 'Collection', title, description: `${title}, a made-up listed entry.`, license: 'CC-BY-4.0',
  keywords: ['made up', 'listed', 'gauges'], links: [{ rel: 'via', href: `https://data.example.org/${id}` }],
  extent: { spatial: { bbox: [[6, 47, 15, 55]] }, temporal: { interval: [[null, null]] } },
  providers: [{ name: 'Made-up office', roles: ['producer'] }],
  'earthx:entry': 'listed', 'earthx:category': category, 'earthx:regions': ['DE', 'DE-BY'],
  'earthx:access': { account: 'paid', account_provider: 'shop', delivery: 'order' },
  'earthx:license_flags': { tier: 'catalog', name: 'CC BY 4.0', url: 'https://example.org/licence' },
  'earthx:listing': { source_url: `https://data.example.org/${id}`, publisher: 'Made-up office', approved_on: '2026-11-10' },
});
const LISTED = [
  ...Array.from({ length: 130 }, (_, i) => listed(`gauge-${i}`, `Gauge ${String(i).padStart(3, '0')} (made up)`, 'water')),
  listed('aerial', 'Aerial photos 1950 (made up)', 'optical'),
];
const COLLECTIONS = [...MADE_UP, ...LISTED];
const CATEGORIES = [
  ['optical', 'Optical imagery'], ['radar', 'Radar'], ['elevation', 'Elevation'], ['land_cover', 'Land cover and land use'],
  ['weather_climate', 'Weather and climate'], ['water', 'Water and sea'], ['nature', 'Nature and environment'],
  ['geology_soil', 'Geology and soil'], ['boundaries', 'Boundaries, addresses and cadastre'],
  ['infrastructure', 'Buildings, transport and utilities'], ['population', 'Population and society'],
  ['agriculture', 'Agriculture and forestry'], ['other', 'Other'],
].map(([id, title]) => ({ id, title }));
const REGIONS = [
  { code: 'AT', name: 'Austria', level: 'state' }, { code: 'DE', name: 'Germany', level: 'state' },
  { code: 'DE-BY', name: 'Bayern', level: 'subdivision', state: 'DE' }, { code: 'DE-BE', name: 'Berlin', level: 'subdivision', state: 'DE' },
];

// One page of `/stac/collections` as the API gives it: by title, a token in the body of the next link, a count.
function pageOf(body) {
  if (typeof body.q === 'string') {
    // The search with text: full and listed entries (M5-42), 20 a page by offset; here the title holds the text.
    const found = COLLECTIONS.filter((c) => c.title.toLowerCase().includes(body.q.toLowerCase()) && (!body.category || c['earthx:category'] === body.category));
    const offset = body.offset ?? 0;
    return {
      collections: found.slice(offset, offset + 20),
      links: offset + 20 < found.length ? [{ rel: 'next', method: 'POST', href: '/stac/collections', body: { ...body, offset: offset + 20 } }] : [],
      numberMatched: found.length,
    };
  }
  let hits = COLLECTIONS.filter((c) => c['earthx:category'] === body.category);
  if (body.region) hits = hits.filter((c) => (c['earthx:regions'] ?? []).some((r) => body.region.includes(r)));
  hits.sort((a, b) => (a.title.toLowerCase() < b.title.toLowerCase() ? -1 : 1));
  const start = Number(body.token ?? 0);
  const end = start + (body.limit ?? 100);
  return {
    collections: hits.slice(start, end),
    links: end < hits.length ? [{ rel: 'next', method: 'POST', href: '/stac/collections', body: { ...body, token: String(end) } }] : [],
    ...(body.token ? {} : { numberMatched: hits.length }),
  };
}

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const asked = [];
  page.setDefaultTimeout(10000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/catalogue/categories') return json({ categories: CATEGORIES });
    if (url.pathname === '/catalogue/regions') return json({ regions: REGIONS });
    if (url.pathname === '/stac/collections' && route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData() ?? '{}');
      asked.push(body);
      return json(pageOf(body));
    }
    if (url.pathname === '/stac/collections') return json({ collections: MADE_UP, links: [] });
    return json({ detail: 'not made up' }, 404);
  });
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${what}${detail ? `: ${detail}` : ''}`); };
  const box = (selector) => page.locator(selector).first().boundingBox();
  const panelTitles = () => page.locator('.dataset-toggle-title').allTextContents();

  await page.goto(BASE);
  await page.locator('.app-rail').waitFor();
  const railIds = await page.locator('.app-rail button').evaluateAll((els) => els.map((el) => el.id));
  expect('the symbol is the second of the rail', railIds[1] === 'rail-catalogue', railIds.join(', '));
  const symbol = page.locator('#rail-catalogue');
  const win = page.locator('#data-catalogue');

  await symbol.click();
  await win.waitFor();
  await shot('1-open');
  const size = VIEWPORTS[viewport];
  const w = await box('#data-catalogue');
  const rail = await box('.app-rail');
  expect('the window stays in the browser window', w && w.x >= 0 && w.y >= 0 && w.x + w.width <= size.width + 0.5 && w.y + w.height <= size.height + 0.5, JSON.stringify(w));
  expect('the window leaves the rail free', w && rail && w.x >= rail.x + rail.width - 0.5, JSON.stringify({ w, rail }));
  if (viewport === 'wide') {
    const dock = await box('.dock');
    expect('the window stands beside the open panel', !dock || w.x >= dock.x + dock.width - 0.5, JSON.stringify({ w, dock }));
  }
  const sideways = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect('the page does not scroll sideways', !sideways);

  await win.locator('.catalogue-group').first().waitFor();
  await page.waitForTimeout(300);
  const groups = await page.locator('.catalogue-group').evaluateAll((els) => els.map((el) => el.getAttribute('aria-label')));
  const expected = CATEGORIES.filter((c) => COLLECTIONS.some((x) => x['earthx:category'] === c.id)).map((c) => c.title);
  expect('the groups follow the categories of the API', JSON.stringify(groups) === JSON.stringify(expected), `${groups.join(', ')} ≠ ${expected.join(', ')}`);

  // The head: search field and "Filters" inside the window.
  const inside = (b) => b && w && b.x >= w.x - 0.5 && b.x + b.width <= w.x + w.width + 0.5 && b.y >= w.y - 0.5;
  expect('the search field is in the head of the window', inside(await box('.catalogue-head .catalogue-search')), JSON.stringify(await box('.catalogue-head .catalogue-search')));
  expect('"Filters" is in the head of the window', inside(await box('.catalogue-head .catalogue-filters-btn')), JSON.stringify(await box('.catalogue-head .catalogue-filters-btn')));
  expect('there is no fixed row of filters', (await win.locator('.catalogue-head + .catalogue-filters').count()) === 0);
  await shot('1b-head');

  // Paging: the water group has 130 entries, 50 a page; scrolling its end into view loads the next page, up to the last.
  const water = win.locator('.catalogue-group[aria-label="Water and sea"]');
  const waterCount = () => water.locator('.catalogue-entry').count();
  expect('a group starts with one page', (await waterCount()) === 50, String(await waterCount()));
  expect('its head counts every entry', (await water.locator('.catalogue-group-count').textContent()) === '130');
  for (let i = 0; i < 4; i += 1) {
    await water.locator('.catalogue-entry').last().scrollIntoViewIfNeeded();
    await page.waitForTimeout(400);
  }
  expect('scrolling loads the next pages up to the last', (await waterCount()) === 130, String(await waterCount()));
  expect('no request asks past the last page', asked.filter((b) => b.category === 'water').length === 3, String(asked.filter((b) => b.category === 'water').length));
  await shot('1c-paged');

  // A listed entry: "Source", no mark, no keywords in its details (UI-12).
  const gauge = win.locator('.catalogue-entry', { hasText: 'Gauge 000 (made up)' });
  expect('a listed entry links to its source', (await gauge.locator('a.catalogue-action').textContent()) === 'Source');
  expect('a listed entry has no mark', (await gauge.locator('.badge').count()) === 0);
  await gauge.locator('.catalogue-entry-name').click();
  await win.locator('.catalogue-details').waitFor();
  const labels = await win.locator('.catalogue-row-pair dt').allTextContents();
  expect('the details have no row "Keywords"', labels.length > 0 && !labels.includes('Keywords'), labels.join(', '));
  await shot('1d-listed-details');
  if (viewport === 'narrow') await win.locator('.catalogue-back').click();

  // The pop-up "Filters": inside the browser window, the switch locked without an AOI, each field with its "×".
  const popup = page.locator('.catalogue-filters-popup');
  const openFilters = async () => {
    await win.locator('.catalogue-filters-btn').click();
    await popup.waitFor();
    await page.waitForTimeout(200);
  };
  await openFilters();
  const p = await box('.catalogue-filters-popup');
  expect('the pop-up stays in the browser window', p && p.x >= 0 && p.y >= 0 && p.x + p.width <= size.width + 0.5 && p.y + p.height <= size.height + 0.5, JSON.stringify(p));
  const panelSwitch = popup.locator('.catalogue-search-panel input[role="switch"]');
  expect('"Filter by search panel" is locked without an AOI', (await panelSwitch.getAttribute('aria-disabled')) === 'true');
  expect('the switch says why', (await popup.locator('label.locked').getAttribute('data-tip')) === 'Draw an AOI to use this filter');
  await shot('1e-filters');

  // Category, then its "×".
  await popup.locator('select[aria-label="Category"]').selectOption('water');
  await page.waitForTimeout(300);
  const onlyWater = await page.locator('.catalogue-group').evaluateAll((els) => els.map((el) => el.getAttribute('aria-label')));
  expect('a category shows only its group', JSON.stringify(onlyWater) === '["Water and sea"]', onlyWater.join(', '));
  expect('the button counts the filter', (await win.locator('.catalogue-filters-btn').textContent()) === 'Filters · 1');
  await shot('1f-category');
  await popup.locator('button[aria-label="Clear category"]').click();
  // The groups ask again without a category; their requests have to be in before the next step is recorded.
  await page.waitForTimeout(500);
  asked.length = 0;
  await popup.locator('select[aria-label="Region"]').selectOption('DE-BY');
  await page.waitForTimeout(300);
  expect('the region goes with every request', asked.length > 0 && asked.every((b) => JSON.stringify(b.region) === '["DE-BY"]'), JSON.stringify(asked.slice(0, 2)));
  await popup.locator('input[aria-label="From date"]').fill('2020-01-01');
  await page.waitForTimeout(300);
  await shot('1g-region');
  for (const label of ['Clear region', 'Clear from date']) await popup.locator(`button[aria-label="${label}"]`).click();
  await page.waitForTimeout(300);
  expect('the "×" empty every field', (await win.locator('.catalogue-filters-btn').textContent()) === 'Filters');
  // A click beside the pop-up closes it.
  await win.locator('.catalogue-head h2').click();
  await page.waitForTimeout(200);
  expect('a click beside the pop-up closes it', !(await popup.isVisible()));

  // The search field: hits in rank order instead of the groups; its "×" brings the groups back.
  const search = win.locator('.catalogue-search input');
  await search.fill('photos');
  await page.waitForTimeout(700);
  const hits = await win.locator('.catalogue-hits .catalogue-entry-title').allTextContents();
  // In the order the API ranks them (here: the order of the made-up list), not by title.
  const ranked = COLLECTIONS.filter((c) => c.title.toLowerCase().includes('photos')).map((c) => c.title);
  expect('the hits stand in place of the groups, in the order of the API', hits.join('|') === ranked.join('|') && (await win.locator('.catalogue-group').count()) === 0, hits.join(', '));
  expect('a listed entry is among the hits', hits.includes('Aerial photos 1950 (made up)'), hits.join(', '));
  expect('the text goes to the search', asked.some((b) => b.q === 'photos'));
  await shot('1h-search');
  await win.locator('.catalogue-search .clear-btn').click();
  await page.waitForTimeout(500);
  expect('the "×" of the search brings the groups back', (await win.locator('.catalogue-group').count()) > 0);
  const sidewaysAfter = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect('the page does not scroll sideways with the filters', !sidewaysAfter);

  await page.keyboard.press('Escape');
  await win.locator('.catalogue-head').click();
  await page.keyboard.press('Escape');
  expect('Esc closes nothing', await win.isVisible());
  if (viewport === 'wide') {
    await page.mouse.click(size.width - 10, size.height / 2);
    expect('a click beside the window closes nothing', await win.isVisible());
  }

  // "Remove" and "Add" of the first entry that is in the panel.
  const first = win.locator('.catalogue-entry').filter({ has: page.locator('.catalogue-action', { hasText: 'Remove' }) }).first();
  const firstTitle = await first.locator('.catalogue-entry-title').textContent();
  await first.locator('.catalogue-action').click();
  await symbol.click();
  await page.locator('#rail-controls').click().catch(() => {});
  if (!(await page.locator('.control-panel').first().isVisible())) await page.locator('#rail-controls').click();
  expect('"Remove" takes the dataset out of the panel', !(await panelTitles()).includes(firstTitle), firstTitle);
  await symbol.click();
  await win.locator('.catalogue-entry', { hasText: firstTitle }).locator('.catalogue-action').click();
  await shot('2-added');
  await symbol.click();
  if (!(await page.locator('.control-panel').first().isVisible())) await page.locator('#rail-controls').click();
  expect('"Add" puts it back and turns the pages to it', (await panelTitles()).includes(firstTitle), (await panelTitles()).join(', '));
  await shot('3-panel');
  // "Add dataset" after the datasets of the search panel, drawn like one; it opens the window.
  const tiles = await page.locator('.dataset-list .dataset-toggle').evaluateAll((els) => els.map((el) => el.textContent.trim()));
  expect('"Add dataset" stands after the datasets', tiles.at(-1) === 'Add dataset' || (await page.locator('.dataset-pages [aria-label="Next page"]').getAttribute('aria-disabled')) !== 'true', tiles.join(', '));
  const addTile = page.locator('.dataset-list .add-dataset');
  if (await addTile.count()) {
    await addTile.click();
    expect('"Add dataset" opens the Data catalogue', await win.isVisible());
    await shot('3b-add-dataset');
    await symbol.click();
  }

  // The details.
  await symbol.click();
  await win.locator('.catalogue-entry-name').first().click();
  await win.locator('.catalogue-details').waitFor();
  await shot('4-details');
  if (viewport === 'narrow') {
    expect('the list gives way to the details', !(await win.locator('.catalogue-list').isVisible()));
    await win.locator('.catalogue-back').click();
    expect('"Back" shows the list again', await win.locator('.catalogue-list').isVisible());
  } else {
    expect('list and details stand side by side', await win.locator('.catalogue-list').isVisible());
    expect('"Back" is not there in a wide window', !(await win.locator('.catalogue-back').isVisible()));
  }
  const overflow = await page.evaluate(() =>
    [...document.querySelectorAll('.catalogue-row-pair dd')].filter((dd) => dd.scrollWidth > dd.clientWidth + 1).map((dd) => dd.textContent.slice(0, 40)),
  );
  expect('no value runs out of its column', overflow.length === 0, overflow.join(' | '));

  await win.locator('.catalogue-head .close-x').click();
  expect('the red x closes the window', !(await win.isVisible()));
  await symbol.click();
  await symbol.click();
  expect('a second click on the symbol closes it', !(await win.isVisible()));

  await context.close();
  return problems;
}

(async () => {
  const browser = await chromium.launch();
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const problems = await check(browser, { theme, viewport });
      console.log(`${problems.length === 0 ? 'PASS' : 'FAIL'}  ${theme} ${viewport}`);
      for (const problem of problems) console.log(`      ${problem}`);
      failed ||= problems.length > 0;
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
