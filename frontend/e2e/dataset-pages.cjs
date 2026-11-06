// Browser check of UI-05 part 1 (Otto, 06.11.2026): the panel "Search and area" with pages of datasets, "Advanced search"
// always there, the date fields held to the days of the chosen datasets, and no explanation as text in the panel. With
// nine made-up datasets it does the clicks of a user in a real browser and fails when
//   - a page holds more than six buttons, or more rows than fit: the scrolling part of the panel scrolls while it shows
//     more than one row, or shows fewer rows than the room it has;
//   - the counter does not read "1 / n" for the pages there are, an arrow at the edge is not locked with its reason, or
//     turning the pages misses a dataset or shows one twice;
//   - the arrows and the counter do not stand small at the right of the heading "Datasets", in its row, before "Select
//     multiple datasets" and above the grid (Otto's review of part 1), or overlap one of them;
//   - the grid of the last page is lower than a full page (the panel jumps);
//   - a dataset picked on another page is not shown when a lower window shrinks the page;
//   - "Advanced search" is missing without a dataset, is not locked with its reason, or opens anything;
//   - a choice of datasets does not fill the date fields with their first and last day (an open end being today), a day
//     typed does not stay until the next choice, or the fields offer days outside the extent, or are not locked with the
//     acquisition period in their tooltip for
//     the dataset without a time axis; "No time axis" or "Scenes counted …" stand as text in the panel;
//   - something leaves the panel, or the page scrolls sideways;
// and writes a screenshot per step.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/dataset-pages.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-dataset-pages');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = {
  wide: { width: 1280, height: 800 },
  'wide and low': { width: 1280, height: 560 },
  narrow: { width: 360, height: 740 },
  'very narrow': { width: 320, height: 640 },
};

const CAPABILITIES = { roi: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false };
const viewer = (browse, groupBy) => ({ group_by: groupBy, min_zoom: 0, max_zoom: 14, browse, quicklook_nodata_max: null, results_group_by: groupBy });
const collection = (id, title, interval, timeAxis = true) => ({
  id, type: 'Collection', title, description: 'made up', license: 'proprietary', links: [],
  extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [interval] } },
  'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { ...CAPABILITIES, time_range: timeAxis, single_coverage_product: !timeAxis },
  'earthx:viewer': timeAxis ? viewer('quicklook', ['datetime']) : viewer('full_resolution', ['start_datetime']),
  'earthx:search_filters': [],
});
const COLLECTIONS = [
  collection('optical', 'Optical (made up)', ['2015-06-27T10:25:31Z', null]),
  collection('dem', 'Elevation (made up)', ['2010-12-01T00:00:00Z', '2015-01-31T23:59:59Z'], false),
  ...Array.from({ length: 7 }, (_, i) => collection(`extra-${i}`, `Extra ${i}`, [`201${i}-01-01T00:00:00Z`, '2020-12-31T23:59:59Z'])),
];
const TITLES = COLLECTIONS.map((c) => c.title);
const TODAY = new Date().toISOString().slice(0, 10);

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
  const store = (fn, arg) => page.evaluate(async ([src, data]) => {
    const { useAppStore } = await import('/src/store.ts');
    return (0, eval)(`(${src})`)(useAppStore, data);
  }, [fn.toString(), arg]);
  const scroll = page.locator('.control-scroll');
  const grid = page.locator('.dataset-list');
  const toggles = page.locator('.dataset-list .dataset-toggle');
  const previous = page.locator('.dataset-pages [aria-label="Previous page"]');
  const next = page.locator('.dataset-pages [aria-label="Next page"]');
  const counter = page.locator('.dataset-page-count');
  const tip = page.locator('#tip-layer');
  const rect = (locator) => locator.evaluate((el) => el.getBoundingClientRect().toJSON());
  const titles = async () => (await toggles.locator('.dataset-toggle-title').allTextContents()).map((t) => t.trim());
  // The pointer comes from outside, as a user's would after a click elsewhere.
  const tipOnHover = async (locator) => {
    await page.mouse.move(0, 0);
    await page.waitForTimeout(100);
    await locator.hover({ force: true });
    await page.waitForTimeout(250);
    return (await tip.count()) ? (await tip.textContent())?.trim() : null;
  };
  const rows = async () => {
    const boxes = await toggles.evaluateAll((els) => els.map((el) => Math.round(el.getBoundingClientRect().top)));
    return new Set(boxes).size;
  };
  const scrolls = () => scroll.evaluate((el) => el.scrollHeight > el.clientHeight + 1);

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await page.waitForTimeout(400);

  // 1. A page: at most six, as many rows as fit; the panel does not scroll unless it is down to one row.
  const shownRows = await rows();
  const size = await toggles.count();
  expect('more than six on a page', size <= 6, `${size}`);
  expect('a page is not two buttons a row', size === Math.min(TITLES.length, shownRows * 2), `${size} in ${shownRows} rows`);
  if (shownRows > 1) expect('the panel scrolls with more than one row', !(await scrolls()));
  const slack = await scroll.evaluate((el) => {
    const last = el.lastElementChild.getBoundingClientRect().bottom - el.getBoundingClientRect().top + el.scrollTop;
    return el.clientHeight - last - parseFloat(getComputedStyle(el).paddingBottom);
  });
  if (shownRows < 3) expect('a row more would have fitted', slack < 46, `${Math.round(slack)} px free`);
  const pages = Math.ceil(TITLES.length / size);
  expect('the counter', (await counter.textContent())?.replace(/\s+/g, ' ').trim() === `1 / ${pages}`, await counter.textContent());
  expect('the first arrow is not locked', (await previous.getAttribute('aria-disabled')) === 'true');
  expect('the reason of the first arrow', (await tipOnHover(previous)) === 'Already on the first page');
  const heading = await rect(page.locator('.dataset-label'));
  const word = await page.locator('.dataset-label > span:first-child').evaluate((el) => {
    const range = document.createRange();
    range.selectNodeContents(el.firstChild);
    return range.getBoundingClientRect().toJSON();
  });
  const arrows = await rect(page.locator('.dataset-pages'));
  const multi = await rect(page.locator('.multi-select-toggle'));
  expect('the pages are not in the row of the heading', arrows.y >= heading.y - 1 && arrows.y + arrows.height <= heading.y + heading.height + 1, JSON.stringify(arrows));
  expect('the pages are not right of "Datasets"', arrows.x >= word.x + word.width, `${Math.round(arrows.x)} < ${Math.round(word.x + word.width)}`);
  expect('the pages overlap "Select multiple datasets"', arrows.x + arrows.width <= multi.x + 0.5, `${Math.round(arrows.x + arrows.width)} > ${Math.round(multi.x)}`);
  expect('the pages are not above the grid', arrows.y + arrows.height <= (await rect(grid)).y);
  expect('the pages are not small', arrows.height <= 24, `${arrows.height} px`);
  await shot('1-first-page');

  // 2. Turning the pages shows every dataset once; the last page is as high as a full one; the last arrow is locked.
  const fullHeight = (await rect(grid)).height;
  const seen = [...(await titles())];
  for (let i = 1; i < pages; i++) {
    await next.click();
    seen.push(...(await titles()));
  }
  expect('the pages miss or repeat a dataset', JSON.stringify(seen) === JSON.stringify(TITLES), seen.join(', '));
  expect('the last page is lower than a full one', Math.abs((await rect(grid)).height - fullHeight) < 1);
  expect('the last arrow is not locked', (await next.getAttribute('aria-disabled')) === 'true');
  expect('the reason of the last arrow', (await tipOnHover(next)) === 'Already on the last page');
  await next.click({ force: true });
  expect('a locked arrow turned the page', (await counter.textContent())?.replace(/\s+/g, ' ').trim() === `${pages} / ${pages}`);
  await shot('2-last-page');

  // 3. A dataset on the last page picked, the window lower: its page is shown.
  await toggles.last().click();
  const pickedTitle = TITLES.at(-1);
  if (viewport === 'wide') {
    await page.setViewportSize({ width: 1280, height: 520 });
    await page.waitForTimeout(400);
    expect('the picked dataset is not on the page shown', (await titles()).includes(pickedTitle), (await titles()).join(', '));
    if ((await rows()) > 1) expect('the panel scrolls in the lower window', !(await scrolls()));
    await shot('3-lower-window');
    await page.setViewportSize(VIEWPORTS[viewport]);
    await page.waitForTimeout(400);
  }
  await store((s) => s.setState({ selectedDatasetIds: [], datasetId: null, lastPickedDatasetId: null }));

  // 4. "Advanced search" without a dataset: there, locked, with the reason; a click opens nothing.
  const advanced = page.locator('.advanced-btn');
  expect('no "Advanced search" without a dataset', (await advanced.count()) === 1);
  expect('"Advanced search" is not locked', (await advanced.getAttribute('aria-disabled')) === 'true');
  expect('the reason of "Advanced search"', (await tipOnHover(advanced)) === 'Choose a dataset to see its filters');
  await advanced.click({ force: true });
  expect('a locked "Advanced search" opened', (await page.locator('.advanced-popup').count()) === 0);
  await shot('4-advanced-locked');

  // 5. The dates: filled with and held to the days of the optical dataset; a typed day stays until the next choice; locked
  // with the period for the elevation one; an (i) for both.
  await store((s) => { s.getState().setMultiSelect(true); s.getState().toggleDatasetSelected('optical'); });
  const from = page.locator('input[aria-label="From date"]');
  const to = page.locator('input[aria-label="To date"]');
  const filled = async () => [await from.inputValue(), await to.inputValue()].join(' → ');
  expect('the choice did not fill the dates', (await filled()) === `2015-06-27 → ${TODAY}`, await filled());
  await from.fill('2020-05-05');
  await to.focus();
  expect('a day typed did not stay', (await from.inputValue()) === '2020-05-05', await from.inputValue());
  expect('the first day offered', (await from.getAttribute('min')) === '2015-06-27', await from.getAttribute('min'));
  expect('the last day offered', (await from.getAttribute('max')) === TODAY, await from.getAttribute('max'));
  await from.fill('2001-01-01');
  await page.locator('input[aria-label="To date"]').focus();
  expect('a day before the extent stayed', (await from.inputValue()) === '2015-06-27', await from.inputValue());
  await store((s) => s.getState().toggleDatasetSelected('dem'));
  expect('no (i) at the dates with the elevation dataset ticked as well', (await page.locator('.date-label .tip').count()) === 1);
  expect('the next choice did not fill the dates anew', (await filled()) === `2015-06-27 → ${TODAY}`, await filled());
  await store((s) => s.getState().toggleDatasetSelected('optical'));
  expect('the dates are not locked without a time axis', await from.isDisabled());
  expect('the locked dates do not show the period', (await filled()) === '2010-12-01 → 2015-01-31', await filled());
  expect('the period is not in the tooltip of the locked dates', (await tipOnHover(from)) === 'No time axis – acquired Dec 2010 to Jan 2015', await tipOnHover(from));
  const panelText = await page.locator('.control-panel').innerText();
  for (const phrase of ['No time axis', 'Scenes counted by their center point']) expect('an explanation as text in the panel', !panelText.includes(phrase), phrase);
  await shot('5-dates');

  // 6. Nothing leaves the panel; no sideways scroll.
  const panel = await rect(page.locator('.control-panel'));
  for (const part of [grid, page.locator('.dataset-pages'), advanced]) {
    const box = await rect(part);
    expect('a part leaves the panel', box.x >= panel.x - 1 && box.x + box.width <= panel.x + panel.width + 1, JSON.stringify(box));
  }
  expect('the page scrolls sideways', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));

  await context.close();
  return { label, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const result = await check(browser, { theme, viewport });
      console.log(`${result.problems.length === 0 ? 'PASS' : 'FAIL'}  ${result.label}`);
      for (const problem of result.problems.slice(0, 8)) console.log(`      - ${problem.slice(0, 200)}`);
      failed ||= result.problems.length > 0;
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
