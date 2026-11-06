// Browser check of UI-05 part 2 (Otto, 06.11.2026): the Data catalogue. With made-up collections (or, with
// COLLECTIONS=<file>, the answer of `/stac/collections` in that file) it does the clicks of a user in a real browser and
// fails when
//   - the symbol "Data catalogue" is not the second of the rail, or does not open and close the window;
//   - Esc or a click on the map beside the window closes it, or the red x does not;
//   - the window leaves the browser window, covers the rail, covers an open panel of the dock in a wide window, or the
//     page scrolls sideways;
//   - the groups are not in the order of `earthx:category`;
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
  'earthx:source': { asset_hosts: ['assets.example.org'], endpoint: 'https://stac.example.org/v1', source_collection_id: id, data_region: 'unknown' },
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
const COLLECTIONS = process.env.COLLECTIONS ? JSON.parse(fs.readFileSync(process.env.COLLECTIONS, 'utf8')).collections : MADE_UP;
const ORDER = ['optical', 'radar', 'elevation', 'land_cover', 'weather_climate'];

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: COLLECTIONS });
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

  const groups = await page.locator('.catalogue-group').evaluateAll((els) => els.map((el) => el.getAttribute('aria-label')));
  const titles = { optical: 'Optical', radar: 'Radar', elevation: 'Elevation', land_cover: 'Land cover', weather_climate: 'Weather and climate' };
  const expected = ORDER.filter((c) => COLLECTIONS.some((x) => x['earthx:category'] === c)).map((c) => titles[c]);
  expect('the groups follow the order of the field', JSON.stringify(groups) === JSON.stringify(expected), `${groups.join(', ')} ≠ ${expected.join(', ')}`);

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
