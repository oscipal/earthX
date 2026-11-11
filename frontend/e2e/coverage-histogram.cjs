// The bars under the coverage map with many dates (Otto, 10.11.2026), in a real browser with a made-up answer and no backend:
//   1. The row keeps a fixed, small height and lies inside the panel, however many months the source counts.
//   2. Many months make coarser bars (quarters, then years), never more of them than fit: the panel does not scroll for it,
//      neither across nor down.
//   3. The tooltip of a bar names its period and its count; the bars of the chosen dates are marked.
// 30 months (one bar each), 60 (quarters) and 146 (years, Sentinel-1 since October 2014); light and dark theme, a wide
// and a narrow window; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/coverage-histogram.cjs         # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-coverage-histogram');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const SERIES = [
  { months: 30, start: [2024, 1], step: 'month', bars: 30 },
  { months: 60, start: [2021, 1], step: 'quarter', bars: 20 },
  { months: 146, start: [2014, 10], step: 'year', bars: 13 },
];
const MAX_HEIGHT = 40;

function coverageOf({ months, start }) {
  const histogram = Array.from({ length: months }, (_, i) => {
    const total = start[0] * 12 + start[1] - 1 + i;
    return { t: `${Math.floor(total / 12)}-${String((total % 12) + 1).padStart(2, '0')}-01T00:00:00Z`, n: 50 + ((i * 37) % 200) };
  });
  return {
    dataset_id: 'radar', grid: 'geotile', level: 3, counting: 'center', cells: [], counted: 1000, total_count: 1000,
    completeness: 'complete', max_count: 12, histogram, histogram_interval: 'month', footprints_advised: false,
    from_cache: false, extent: null, area: null, ignored_filters: [],
  };
}

async function run(browser, theme, viewport, results) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  // The answer of the coverage route for the series shown; the map asks again whenever it moves.
  let answer = null;
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.startsWith('/coverage/') && answer) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(answer) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: 'not made up' }) });
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');

  for (const series of SERIES) {
    answer = coverageOf(series);
    await page.evaluate(async ({ coverage }) => {
      const { useAppStore } = await import('/src/store.ts');
      const { datasetsFrom } = await import('/src/datasets.ts');
      const collection = {
        id: 'radar', title: 'Sentinel-1 GRD', 'earthx:category': 'radar', 'earthx:format': 'cog',
        'earthx:capabilities': { roi: true, time_range: true },
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 7, max_zoom: 14, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime'] },
        extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2014-10-10T00:00:00Z', null]] } },
      };
      useAppStore.setState({
        datasets: datasetsFrom([collection]), addedDatasetIds: ['radar'], selectedDatasetIds: ['radar'], datasetId: 'radar',
        showCoverage: true, coverageDatasetId: 'radar', coverage, coverageLoading: false, coverageError: null,
        dateFrom: '2025-01-01', dateTo: '2025-12-31', dock: 'controls', sections: [],
      });
    }, { coverage: answer });
    await page.waitForSelector('.coverage-histogram');
    await page.waitForTimeout(300);
    const where = `${series.months} months`;
    const seen = await page.evaluate(() => {
      const row = document.querySelector('.coverage-histogram');
      const scroll = document.querySelector('.control-scroll');
      const box = row.getBoundingClientRect();
      const panel = scroll.getBoundingClientRect();
      const bars = [...row.querySelectorAll('.histogram-bar')];
      return {
        height: box.height, left: box.left, right: box.right, panelLeft: panel.left, panelRight: panel.right,
        across: scroll.scrollWidth - scroll.clientWidth,
        bars: bars.length, narrowest: Math.min(...bars.map((bar) => bar.getBoundingClientRect().width)),
        label: row.getAttribute('aria-label'), tips: bars.map((bar) => bar.getAttribute('data-tip')),
        marked: bars.filter((bar) => bar.classList.contains('in-range')).map((bar) => bar.getAttribute('data-tip').split(':')[0]),
      };
    });
    if (seen.height > MAX_HEIGHT) problems.push(`${where}: the row is ${seen.height} px high`);
    if (seen.right > seen.panelRight + 1 || seen.left < seen.panelLeft - 1) problems.push(`${where}: the row lies outside the panel`);
    if (seen.across > 0) problems.push(`${where}: the panel scrolls across by ${seen.across} px`);
    if (seen.bars !== series.bars) problems.push(`${where}: ${seen.bars} bars, not ${series.bars}`);
    if (seen.narrowest < 1) problems.push(`${where}: a bar is narrower than a pixel`);
    if (seen.label !== `Acquisitions per ${series.step}`) problems.push(`${where}: the row says "${seen.label}"`);
    if (!seen.tips.every((tip) => /^\d{4}(-\d{2}| Q[1-4])?: \d+$/.test(tip))) problems.push(`${where}: a tooltip says ${seen.tips.find((t) => !/^\d{4}/.test(t))}`);
    const wantMarked = { month: 12, quarter: 4, year: 1 }[series.step];
    if (seen.marked.length !== wantMarked) problems.push(`${where}: ${seen.marked.length} bars marked for 2025, not ${wantMarked}`);
    await page.locator('.coverage-controls').screenshot({ path: path.join(OUT, `${name} ${series.months} months.png`) });
  }

  results.push({ name, problems });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) await run(browser, theme, viewport, results);
  await browser.close();
  for (const { name, problems } of results) console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
