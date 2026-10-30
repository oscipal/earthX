// The heads of the groups in the results list (NM4-09): in a real browser, the head of the open group stays at the
// top of the list while its scenes scroll, the head of the next group pushes it out, no scene is hidden under it, and
// the "Load more" row stays reachable. Light and dark theme, a wide and a narrow window; writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the scenes are made up here
//   node e2e/group-heads.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-group-heads');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

async function check(browser, { theme, viewport }) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const { buildSections } = await import('/src/sections.ts');
    const caps = { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false };
    const datasets = datasetsFrom([
      {
        id: 'optical',
        title: 'Optical imagery',
        'earthx:capabilities': caps,
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      },
    ]);
    // Two passes of 40 and 30 scenes, much longer than the list is high, and 25 of one scene: enough closed heads below
    // that the next head can reach the top of the list.
    const sizes = [40, 30, ...Array(25).fill(1)];
    const features = sizes.flatMap((n, g) =>
      Array.from({ length: n }, (_, i) => ({
        id: `scene-${g}-${i}`,
        collection: 'optical',
        bbox: [0, 0, 1, 1],
        properties: { datetime: new Date(Date.UTC(2026, 6, 31 - g, 10, i)).toISOString() },
        assets: {},
      })),
    );
    const { sections } = buildSections(features, datasets.filter((d) => d.viewable), { ignoredFilters: [], ignoredFiltersByCollection: {}, incompleteCollections: [] });
    const open = sections[0];
    useAppStore.setState({
      datasets,
      sections,
      openSectionId: open.datasetId,
      datasetId: open.datasetId,
      items: open.items,
      groups: open.groups,
      activeGroupIndex: 0,
      expandedGroupIndex: 0,
      selectedIds: [],
      dock: 'results',
      searchContext: { nextToken: 'next', numberMatched: 99, openCollections: ['optical'] },
    });
  });
  await page.waitForSelector('.result-group-row');

  const list = page.locator('.results-list');
  const rects = () =>
    page.evaluate(() => {
      const top = (el) => el.getBoundingClientRect().top;
      const bottom = (el) => el.getBoundingClientRect().bottom;
      const listEl = document.querySelector('.results-list');
      const rows = [...document.querySelectorAll('.result-group-row')];
      return {
        listTop: top(listEl),
        listHeight: listEl.clientHeight,
        scrollHeight: listEl.scrollHeight,
        heads: rows.map((r) => ({ top: top(r), bottom: bottom(r) })),
        // The first scene row that is at least half inside the list, and where it lies against the open head.
        firstRowTop: [...document.querySelectorAll('.result-row')].map((r) => top(r)).filter((t) => t > top(listEl) - 1).sort((a, b) => a - b)[0] ?? null,
      };
    });
  const scrollTo = (y) => list.evaluate((el, v) => (el.scrollTop = v), y);
  const near = (a, b) => Math.abs(a - b) <= 1;

  // 1. At rest the head is where it always was; scrolled into the group it stays at the top of the list.
  const rest = await rects();
  if (rest.scrollHeight <= rest.listHeight) problems.push('the list does not scroll, the check proves nothing');
  await scrollTo(200);
  let r = await rects();
  if (!near(r.heads[0].top, r.listTop)) problems.push(`open head did not stay: ${r.heads[0].top} vs list ${r.listTop}`);
  const solid = await page.evaluate(() => getComputedStyle(document.querySelector('.result-group-row')).backgroundColor);
  if (/rgba\(.*,\s*0(\.\d+)?\)$/.test(solid) || solid === 'transparent') problems.push(`head is see-through: ${solid}`);
  await page.screenshot({ path: path.join(OUT, `stuck ${name}.png`) });

  // 2. At the end of the group the next head pushes it out of the list.
  // Where the second head lies in the content of the list, from the top of the content (not of the window).
  const nextTop = await page.evaluate(() => {
    const listEl = document.querySelector('.results-list');
    return document.querySelectorAll('.result-group-row')[1].getBoundingClientRect().top - listEl.getBoundingClientRect().top + listEl.scrollTop;
  });
  const headHeight = rest.heads[0].bottom - rest.heads[0].top;
  await scrollTo(nextTop - headHeight / 2);
  r = await rects();
  if (!(r.heads[0].top < r.listTop - 1)) problems.push(`next head did not push the open one out: ${r.heads[0].top} vs list ${r.listTop}`);
  if (!(r.heads[1].top > r.listTop - 1 && r.heads[1].top < r.listTop + headHeight)) problems.push(`next head is not at the top: ${r.heads[1].top}`);
  await page.screenshot({ path: path.join(OUT, `pushed ${name}.png`) });

  // 3. Open the second group: its head takes over, the first one is a plain line that scrolls away.
  await page.locator('.result-group-head').nth(1).click();
  await scrollTo(150);
  r = await rects();
  const second = await page.evaluate(() => document.querySelectorAll('.result-group-row')[1].getBoundingClientRect().top - document.querySelector('.results-list').getBoundingClientRect().top);
  if (!near(second, 0)) problems.push(`second group's head did not stay: ${second}`);
  await page.screenshot({ path: path.join(OUT, `second ${name}.png`) });

  // 4. A scene reached by the keyboard is not left under the head.
  await scrollTo(0);
  await page.locator('.result-row input[type=checkbox]').nth(20).focus();
  const covered = await page.evaluate(() => {
    const head = document.querySelectorAll('.result-group-row')[1].getBoundingClientRect();
    const row = document.activeElement.closest('.result-row').getBoundingClientRect();
    return row.top < head.bottom - 1 && row.bottom > head.top + 1 && row.top < head.top + 1 ? 'under' : row.top < head.bottom - 1 ? 'overlaps' : null;
  });
  if (covered) problems.push(`focused scene is covered by the head: ${covered}`);

  // 5. The last scene can be reached and "Load more" is still there.
  await scrollTo(1e6);
  const end = await page.evaluate(() => {
    const listEl = document.querySelector('.results-list').getBoundingClientRect();
    const last = [...document.querySelectorAll('.result-row')].at(-1);
    const more = [...document.querySelectorAll('button')].find((b) => b.textContent === 'Load more');
    return { lastBottom: last ? last.getBoundingClientRect().bottom : null, listBottom: listEl.bottom, more: more ? more.getBoundingClientRect().bottom : null, windowHeight: innerHeight };
  });
  if (end.lastBottom !== null && end.lastBottom > end.listBottom + 1) problems.push(`last scene out of reach: ${JSON.stringify(end)}`);
  if (end.more === null) problems.push('"Load more" is gone');
  else if (end.more > end.windowHeight + 1) problems.push(`"Load more" is out of the window: ${JSON.stringify(end)}`);

  await context.close();
  return { name, problems };
}

(async () => {
  require('node:fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const { name, problems } = await check(browser, { theme, viewport });
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
      for (const problem of problems) console.log(`       ${problem}`);
      failed += problems.length;
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
