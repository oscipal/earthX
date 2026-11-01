// Layout check of the layer manager (UI-01d): in a real browser, every row has the same places — the
// same x for each button, with or without "Download" — and the same height, nothing overlaps or leaves the
// panel; and the view of a result lies at the foot of the map without overlap. Light and dark theme, a wide
// and a narrow window; writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/layer-rows.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-layer-rows');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, middle: { width: 1000, height: 760 }, narrow: { width: 360, height: 740 } };
const COLUMNS = ['grip', 'eye', 'name', 'opacity', 'up', 'down', 'process', 'download', 'note', 'remove'];

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

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
  await page.waitForSelector('.dataset-toggle, .app-rail');
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const restore = { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: ['scene'], groupItemIds: [['scene']], aoi: null, cropToAoi: false, datasetId: null };
    const base = { visible: true, opacity: 1, overlays: [{ kind: 'raster', tileUrl: 'https://t/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=180%2C1900', bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }] };
    const result = (over) => ({ jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: future, gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null, ...over });
    useAppStore.setState({
      dock: 'layers',
      layers: [
        { ...base, id: 'scene', name: 'Optical · a scene with a download', restore },
        { ...base, id: 'bare', name: 'Optical · no scenes', restore: { ...restore, itemIds: [] } },
        { ...base, id: 'preview', name: 'Preview · NDVI', derived: 'preview', restore },
        { ...base, id: 'result', name: 'Result · Band math', derived: 'result', result: result({}), restore },
        { ...base, id: 'old', name: 'Result · expired and resampled', derived: 'result', result: result({ expired: true, resampled: true }), restore },
        { ...base, id: 'long', name: 'Optical · a very long name that cannot fit into the place the layer has in the list', restore },
      ],
    });
  });
  await page.waitForSelector('.layer-row');
  const rows = await page.$$eval('.layer-row', (rowNodes) =>
    rowNodes.map((row) => ({
      box: row.getBoundingClientRect().toJSON(),
      cells: [...row.children].map((c) => ({ col: c.getAttribute('data-col'), box: c.getBoundingClientRect().toJSON() })),
    })),
  );
  const panel = await page.$eval('.layer-manager', (el) => el.getBoundingClientRect().toJSON());
  if (rows.length !== 6) problems.push(`${rows.length} rows, six expected`);
  const first = rows[0];
  rows.forEach((row, i) => {
    if (row.cells.map((c) => c.col).join() !== COLUMNS.join()) problems.push(`row ${i}: places ${row.cells.map((c) => c.col)}`);
    if (Math.abs(row.box.height - first.box.height) > 0.5) problems.push(`row ${i}: height ${row.box.height} against ${first.box.height}`);
    row.cells.forEach((cell, j) => {
      if (Math.abs(cell.box.x - first.cells[j].box.x) > 0.5) problems.push(`row ${i}: ${cell.col} at x=${cell.box.x}, first row at ${first.cells[j].box.x}`);
      if (Math.abs(cell.box.width - first.cells[j].box.width) > 0.5) problems.push(`row ${i}: ${cell.col} ${cell.box.width} wide, first row ${first.cells[j].box.width}`);
      if (cell.box.x + cell.box.width > panel.x + panel.width + 0.5) problems.push(`row ${i}: ${cell.col} leaves the panel`);
      for (const other of row.cells.slice(j + 1)) if (overlap(cell.box, other.box)) problems.push(`row ${i}: ${cell.col} overlaps ${other.col}`);
    });
  });
  await page.screenshot({ path: path.join(OUT, `rows ${name}.png`) });

  // The view of a result at the foot of the map.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().selectLayer('result');
  });
  await page.waitForSelector('.result-controls');
  const view = await page.$eval('.result-controls', (el) => el.getBoundingClientRect().toJSON());
  const inner = await page.$$eval('.result-controls .vc-render > *, .result-controls .vc-head > *', (nodes) =>
    nodes.map((n) => ({ text: n.textContent.trim().slice(0, 20), box: n.getBoundingClientRect().toJSON() })),
  );
  const window = VIEWPORTS[viewport];
  if (view.x < -0.5 || view.x + view.width > window.width + 0.5 || view.y + view.height > window.height + 0.5) problems.push(`the view of the result leaves the window: ${JSON.stringify(view)}`);
  // The foot of the map (the view of a result, the time slider, the bar of the selection) lies between the rail or
  // the panel and the right edge, with the panel open and shut.
  for (const dock of ['layers', null]) {
    await page.evaluate(async (d) => (await import('/src/store.ts')).useAppStore.setState({ dock: d }), dock);
    const bottom = await page.$eval('.overlay.bottom', (el) => el.getBoundingClientRect().toJSON());
    if (bottom.x < 48 - 0.5 || bottom.x + bottom.width > window.width + 0.5) problems.push(`the foot of the map (dock ${dock}) reaches over an edge: x=${bottom.x}, right=${bottom.x + bottom.width}, window ${window.width}`);
  }
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: 'layers' }));
  inner.forEach((cell, i) => {
    if (cell.box.x + cell.box.width > view.x + view.width + 0.5) problems.push(`view: "${cell.text}" leaves the view`);
    for (const other of inner.slice(i + 1)) if (overlap(cell.box, other.box)) problems.push(`view: "${cell.text}" overlaps "${other.text}"`);
  });
  await page.screenshot({ path: path.join(OUT, `view ${name}.png`) });

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
