// The status box (the long box at the top of the map: messages, "Loading data", the search) lies in the free area of the map (Otto,
// 14.11.2026), in a real browser:
//   wide window (1280 x 800): with no panel, a panel of the rail at the left (each of the five), the settings bar at the right, the
//   processing panel (wide sheet) at the right, and a panel at each side, the box (each of its toasts)
//     1. is not over any open panel and not covered by one (`elementFromPoint`),
//     2. lies inside the window,
//     3. is centred in the free area (from the rail or the panel beside it to the panel at the right) within 2 px, and is at least as wide as
//        its minimum and no wider than 560 px, with its text not cut off and its red x inside it;
//   the Data catalogue may cover it: with it open the box stays where it was (no shift), and it is not asked to be uncovered;
//   a panel that closes gives the centre back (the box is where it was with none open).
//   narrow window (360 x 740): the rule of the wide window does not apply (Otto, 14.11.2026: narrow windows are dealt with later). The check
//   only holds that the box stands where it stood before the rule: the same place with a panel at the left, at the right, at both and with
//   none, and the old width and place at the top under the buttons; it records the box, and it is not covered.
// The message is "Loading data" (`mapLoading` of the store, shown after 0.6 s as with slow tiles, see map-loading.cjs), with a long error
// under it for the wrap, in the light and the dark theme. Screenshots with both panels open: <OUT>/status-box-<theme>-<size>-both.png.
//
//   cd frontend && npm run dev &            # a FRESH dev server for each run; no backend is needed, the answers are made up here
//   node e2e/status-box.cjs                 # BASE=http://localhost:5173 OUT=/tmp/claude-0/sb ONLY="dark wide" runs one case
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-status-box');
const ONLY = process.env.ONLY;
const THEME_VALUES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const DOCKS = ['controls', 'layers', 'results', 'jobs', 'settings'];
const MIN_WIDTH = 240;
const MAX_WIDTH = 560;
const RAIL = 48;
const LONG = 'The search could not be completed because the catalogue answered with an error that has a long text, which has to wrap and must not reach beyond the box';
const overlaps = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

// What stands at the left, at the right and at the top, and what the box is, read from the page.
const READ = () => {
  const box = (el) => { const r = el.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
  const shown = (el) => el && !el.hidden && el.getClientRects().length > 0;
  const panels = [];
  const dock = document.querySelector('.dock');
  if (shown(dock)) panels.push({ name: 'dock', side: 'left', ...box(dock) });
  for (const el of document.querySelectorAll('.inspector.panel')) if (shown(el)) panels.push({ name: 'settings bar', side: 'right', ...box(el) });
  const sheet = document.querySelector('.processing-sheet');
  if (shown(sheet)) panels.push({ name: 'processing sheet', side: 'right', ...box(sheet) });
  const status = document.querySelector('.overlay.status');
  const toasts = [...document.querySelectorAll('.status-stack > .toast')].map((el) => {
    const r = el.getBoundingClientRect();
    const mid = document.elementFromPoint(r.x + 12, r.y + r.height / 2);
    const x = el.querySelector('.close-x');
    const text = el.querySelector('span:not(.spinner)') ?? el;
    return { ...box(el), text: el.textContent.trim().slice(0, 40), covered: !mid || !el.contains(mid), cut: text.scrollWidth > text.clientWidth + 1, closeX: x ? box(x) : null };
  });
  return { win: { width: innerWidth, height: innerHeight }, panels, status: box(status), toasts, catalogue: document.querySelector('.catalogue') ? box(document.querySelector('.catalogue')) : null, pageScroll: document.documentElement.scrollWidth - innerWidth };
};

async function setUp(page) {
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const footprint = [10, 50, 11, 51];
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const restore = { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null };
    const raster = { kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0%2C1', bounds: footprint, minZoom: 0, maxZoom: 14 };
    useAppStore.setState({
      layers: [{ id: 'res', name: 'Result', visible: true, opacity: 1, overlays: [raster], restore, derived: 'result', date: '2026-07-06', result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: future, gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null } }],
      dock: null, focusMode: false, resultViewLayerId: null, catalogueOpen: false, error: null, notice: null,
    });
  });
}

// The panels of a case: `left` is a dock panel or null, `right` is 'bar', 'sheet' or null.
async function arrange(page, { left, right, catalogue = false }) {
  await page.evaluate(async ({ left: dock, right: side, catalogue: cat }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.setState({ open: side === 'sheet' });
    useAppStore.setState({ dock, resultViewLayerId: side === 'bar' ? 'res' : null, catalogueOpen: cat });
  }, { left, right, catalogue });
  await page.waitForTimeout(250);
  if (right === 'bar') await page.waitForSelector('.inspector.panel:not([hidden])');
  if (right === 'sheet') await page.waitForSelector('.processing-sheet');
  if (catalogue) await page.waitForSelector('.catalogue');
}

const showMessages = async (page) => {
  await page.evaluate(async (long) => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.setState({ mapLoading: ['search-results'], error: long });
  }, LONG);
  await page.waitForSelector('.toast.busy');
  await page.waitForTimeout(150);
};

async function run(browser, { theme, size }) {
  const label = `${theme} ${size}`;
  const wide = size === 'wide';
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[size] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEME_VALUES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.endsWith('/statistics')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ bands: [{ name: 'a', data_type: 'float32', statistics: { minimum: 0, maximum: 1000, count: 100, percentile_3: 30, percentile_97: 970 } }] }) });
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.waitForSelector('.app-rail');
  await setUp(page);

  const cases = [
    ['none', { left: null, right: null }],
    ...DOCKS.map((d) => [`left ${d}`, { left: d, right: null }]),
    ['right settings bar', { left: null, right: 'bar' }],
    ['right processing sheet', { left: null, right: 'sheet' }],
    ['both dock and settings bar', { left: 'layers', right: 'bar' }],
    ['both dock and processing sheet', { left: 'controls', right: 'sheet' }],
  ];
  let none = null;
  const records = [];
  for (const [name, setup] of cases) {
    await arrange(page, setup);
    await showMessages(page);
    const seen = await page.evaluate(READ);
    const where = `${label}, ${name}`;
    if (seen.toasts.length < 2) problems.push(`${where}: expected the busy and the error toast, got ${seen.toasts.length}`);
    if (seen.pageScroll > 0) problems.push(`${where}: the page scrolls sideways by ${seen.pageScroll}px`);
    records.push(`${name}: x ${seen.status.x.toFixed(1)} y ${seen.status.y.toFixed(1)} w ${seen.status.width.toFixed(1)}`);
    if (name === 'none') none = seen.status;
    const [leftEdge, rightEdge] = [
      Math.max(RAIL, ...seen.panels.filter((p) => p.side === 'left').map((p) => p.x + p.width)),
      Math.min(seen.win.width, ...seen.panels.filter((p) => p.side === 'right').map((p) => p.x)),
    ];
    for (const [i, t] of seen.toasts.entries()) {
      const what = `${where}, toast ${i} "${t.text}"`;
      if (t.covered) problems.push(`${what}: is covered by another box`);
      if (t.x < -0.5 || t.y < -0.5 || t.x + t.width > seen.win.width + 0.5 || t.y + t.height > seen.win.height + 0.5) problems.push(`${what}: lies outside the window`);
      if (t.cut) problems.push(`${what}: the text is cut off`);
      if (t.closeX && (t.closeX.x < t.x - 0.5 || t.closeX.x + t.closeX.width > t.x + t.width + 0.5)) problems.push(`${what}: the red x is outside the toast`);
      if (wide) {
        for (const p of seen.panels) if (overlaps(t, p)) problems.push(`${what}: is over the ${p.name}`);
        if (t.x < leftEdge - 0.5 || t.x + t.width > rightEdge + 0.5) problems.push(`${what}: reaches out of the free area ${leftEdge}..${rightEdge}`);
        if (t.width < MIN_WIDTH - 0.5 || t.width > MAX_WIDTH + 0.5) problems.push(`${what}: ${t.width.toFixed(1)} px wide, wanted ${MIN_WIDTH}..${MAX_WIDTH}`);
        const free = rightEdge - leftEdge;
        if (Math.abs(t.x + t.width / 2 - (leftEdge + rightEdge) / 2) > 2) problems.push(`${what}: centre ${(t.x + t.width / 2).toFixed(1)}, free area ${leftEdge}..${rightEdge} has its centre at ${((leftEdge + rightEdge) / 2).toFixed(1)}`);
        if (t.width < Math.min(MAX_WIDTH, free - 32) - 2) problems.push(`${what}: narrower than the free area allows (${free - 32} px)`);
      }
    }
    if (name === 'both dock and settings bar') await page.screenshot({ path: path.join(OUT, `status-box-${theme}-${size}-both.png`) });
    if (!wide && none && (Math.abs(seen.status.x - none.x) > 0.5 || Math.abs(seen.status.y - none.y) > 0.5 || Math.abs(seen.status.width - none.width) > 0.5)) {
      problems.push(`${where}: the box moved in the narrow window (none: ${JSON.stringify(none)})`);
    }
    if (!wide && name === 'none') {
      // The place from before the rule: centred on the map right of the rail, no wider than it less 16 px, under the buttons at the top right.
      const w = Math.min(MAX_WIDTH, seen.win.width - RAIL - 16);
      const x = (seen.win.width + RAIL) / 2 - w / 2;
      if (Math.abs(seen.status.x - x) > 1 || Math.abs(seen.status.width - w) > 1) problems.push(`${where}: the box is not where it was (x ${seen.status.x}, w ${seen.status.width}; wanted x ${x}, w ${w})`);
    }
  }
  console.log(`${label}: ${records.join(' | ')}`);

  // A panel that closes gives the centre back: none again is where none was.
  await arrange(page, { left: 'layers', right: 'sheet' });
  await arrange(page, { left: null, right: null });
  const again = await page.evaluate(READ);
  if (none && (Math.abs(again.status.x - none.x) > 0.5 || Math.abs(again.status.width - none.width) > 0.5 || Math.abs(again.status.y - none.y) > 0.5)) problems.push(`${label}: after closing both panels the box is not where it was: ${JSON.stringify(again.status)} against ${JSON.stringify(none)}`);
  await arrange(page, { left: 'layers', right: 'bar' });
  await arrange(page, { left: null, right: 'bar' });
  const afterLeft = await page.evaluate(READ);
  await arrange(page, { left: null, right: null });
  const afterBar = await page.evaluate(READ);
  if (wide && afterLeft.panels.some((p) => p.side === 'left')) problems.push(`${label}: the dock is still there after closing it`);
  if (none && Math.abs(afterBar.status.x - none.x) > 0.5) problems.push(`${label}: after closing the settings bar the box is not where it was`);

  // The Data catalogue: it may cover the box, and the box does not shift for it (with and without a panel beside it).
  for (const left of [null, 'layers']) {
    await arrange(page, { left, right: null });
    const before = (await page.evaluate(READ)).status;
    await arrange(page, { left, right: null, catalogue: true });
    await showMessages(page);
    const open = await page.evaluate(READ);
    const what = `${label}, Data catalogue${left ? ' beside the dock' : ''}`;
    if (!open.catalogue) problems.push(`${what}: the catalogue is not there`);
    if (Math.abs(open.status.x - before.x) > 0.5 || Math.abs(open.status.width - before.width) > 0.5 || Math.abs(open.status.y - before.y) > 0.5) {
      problems.push(`${what}: the box moved for the catalogue: ${JSON.stringify(before)} -> ${JSON.stringify(open.status)}`);
    }
    // Wide: the window lies over the box, which is allowed; the screenshot shows it. Narrow: the box lies over the window as before.
    console.log(`${what}: catalogue over the box: ${open.catalogue && open.toasts[0] ? overlaps(open.catalogue, open.toasts[0]) && open.toasts[0].covered : '-'}, box ${JSON.stringify(open.status)}`);
    if (left === 'layers') await page.screenshot({ path: path.join(OUT, `status-box-${theme}-${size}-catalogue.png`) });
    await arrange(page, { left, right: null, catalogue: false });
  }
  await context.close();
  return problems;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  let failed = 0;
  for (const theme of Object.keys(THEME_VALUES)) {
    for (const size of Object.keys(VIEWPORTS)) {
      if (ONLY && ONLY !== `${theme} ${size}`) continue;
      const problems = await run(browser, { theme, size }).catch((error) => [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`]);
      failed += problems.length > 0 ? 1 : 0;
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} status box, ${theme} ${size}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
    }
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
