// Narrow windows (UI-04 part 6, backlog item 58): in a real browser, at 320, 360 and 1280 px, in the light and the dark theme,
//  1. the AOI tools of the control panel do not reach beyond their box (no horizontal scroll in the panel),
//  2. a message of the status bar lies inside the window, under the buttons at the top right, and above an open panel,
//  3. the fields of a range (vmin, vmax and the switch beside them) in the settings bar of a view, of a layer and of a result layer keep
//     the room of "-0.123456": no value cut off, nothing out of the bar, the bar does not scroll sideways (the preview of the processing
//     panel is held by range-layout.cjs; the download dialog has no such field),
//  4. a message of the status bar can be read and closed with a panel of the rail open (control panel, layers, search results, jobs,
//     settings), and a long message wraps instead of reaching beyond the edge.
// Fails on any of them; writes a screenshot per case. A deliberate fault (the old rules) fails the checks: set FAULT=1.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/narrow-windows.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-narrow-windows');
const FAULT = process.env.FAULT === '1';
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { 'very narrow': { width: 320, height: 640 }, narrow: { width: 360, height: 740 }, wide: { width: 1280, height: 800 } };
const PANELS = ['controls', 'layers', 'results', 'jobs', 'settings'];
const LONG = 'The search could not be completed because the catalogue answered with an error that has a long text, which has to wrap and must not reach beyond the window';

const inside = (box, win) => box.x >= -0.5 && box.y >= -0.5 && box.x + box.width <= win.width + 0.5 && box.y + box.height <= win.height + 0.5;
const overlaps = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;


// The old rules, put back after the load (FAULT=1): the status at the top under the panels, the fields of a range given back to the content
// of their switch beside a column for the name. The checks must fail on them.
async function injectFault(page) {
  if (!FAULT) return;
  await page.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => {
      const style = document.createElement('style');
      style.textContent = `@media (max-width: 899px) { .overlay.status { top: 16px !important; z-index: 10 !important; } }
        .inspector .vc-scale { grid-template-columns: var(--form-label-width) minmax(0, 1fr) !important; }
        .inspector .vc-scale-fields { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto !important; }
        .inspector .vc-channels { grid-template-columns: auto minmax(0, 1fr) minmax(0, 1fr) auto !important; }`;
      document.head.append(style);
    });
  });
}

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

// The fields of a range of the open settings bar, with "-0.123456" typed in: what is cut off, out of the bar or over another control.
async function fieldsFit(page, what, problems) {
  const inputs = page.locator('.inspector .vc-scale-fields input[type=number]');
  const found = await inputs.first().waitFor({ timeout: 6000 }).then(() => true, () => false);
  if (!found) {
    problems.push(`${what}: no field of a range in the bar (${await page.evaluate(() => [...document.querySelectorAll('.inspector')].map((e) => e.className).join(' | ') || 'no settings bar')})`);
    return;
  }
  for (let i = 0; i + 1 < (await inputs.count()); i += 2) {
    await inputs.nth(i).fill('-0.123456');
    await inputs.nth(i + 1).fill('0.987654');
  }
  await page.waitForTimeout(150);
  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const bar = document.querySelector('.inspector');
    const leaves = [...bar.querySelectorAll('.vc-scale-fields input, .vc-scale-fields select')].map((e) => ({ what: `${e.tagName.toLowerCase()} ${e.value || e.getAttribute('aria-label') || ''}`.trim(), ...box(e), cut: e.tagName === 'INPUT' && e.scrollWidth > e.clientWidth, scroll: e.scrollWidth }));
    return { bar: box(bar), leaves, scrolls: bar.scrollWidth > bar.clientWidth + 1 };
  });
  for (const [i, a] of report.leaves.entries()) {
    if (a.cut) problems.push(`${what}: ${a.what} is cut off (box ${Math.round(a.width)} px, text needs ${a.scroll} px)`);
    if (a.x < report.bar.x - 0.5 || a.x + a.width > report.bar.x + report.bar.width + 0.5) problems.push(`${what}: ${a.what} leaves the bar`);
    for (const b of report.leaves.slice(i + 1)) if (overlaps(a, b)) problems.push(`${what}: ${a.what} overlaps ${b.what}`);
  }
  if (report.scrolls) problems.push(`${what}: the bar scrolls sideways`);
  if (report.leaves.length === 0) problems.push(`${what}: no field of a range found`);
}

// A view of the search, a layer and a result layer, one after the other.
async function checkRanges(browser, { theme, viewport }) {
  const name = `${theme} ${viewport} ranges`;
  const win = VIEWPORTS[viewport];
  const problems = [];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.endsWith('/statistics')) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ bands: [{ name: 'a', data_type: 'float32', statistics: { minimum: 0, maximum: 1000, count: 100, percentile_3: 30, percentile_97: 970 } }] }) });
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await injectFault(page);
  await page.goto(BASE);
  await page.waitForSelector('.app-rail');
  await page.evaluate(async ({ cog }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const footprint = [10, 50, 11, 51];
    const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 8, maxZoom: 14 });
    const items = ['SYNTH_A'].map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: Object.fromEntries(['red', 'green', 'blue', 'nir', 'visual'].map((k) => [k, { href: `https://example.org/${k}.tif`, type: cog, 'raster:bands': [{ data_type: 'uint16', nodata: 0 }] }])) }));
    const collection = {
      id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['datetime'], min_zoom: 8, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
      'earthx:true_color': ['red', 'green', 'blue'], 'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' }, 'earthx:band_units': { red: 'reflectance', visual: null },
    };
    const future = new Date(Date.now() + 86_400_000).toISOString();
    const restore = { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null };
    const raster = { kind: 'raster', tileUrl: '/results/AbCdEfGhIjKlMnOpQrSt_-/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256&colormap_name=viridis&rescale=0%2C1', bounds: footprint, minZoom: 0, maxZoom: 14 };
    const base = { visible: true, opacity: 1, overlays: [raster], restore };
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'optical', items, groups: [{ key: ['a'], label: '2026-07-01', items }], activeGroupIndex: 0,
      selectedIds: ['SYNTH_A'], downloaded: { SYNTH_A: info('SYNTH_A') }, focusMode: true, showDownloaded: true, dock: null, error: null,
      appliedRender: { rescale: '0,3000' }, pendingColormapName: '', pendingVmin: '0', pendingVmax: '3000', flyToView: { center: [10.5, 50.5], zoom: 9 },
      layers: [
        { ...base, id: 'res', name: 'Result · Band math', derived: 'result', date: '2026-07-06', result: { jobID: 'AbCdEfGhIjKlMnOpQrSt_-', expires: future, gsd: 10, resampled: null, expired: false, dataType: 'float32', stats: null } },
      ],
    });
  }, { cog: COG });
  const close = async () => { for (const x of await page.locator('.toast .close-x').all()) await x.click().catch(() => undefined); };
  await close();
  await page.waitForSelector('.scene-view .vc-scale-fields');
  await fieldsFit(page, 'view', problems);
  await page.screenshot({ path: path.join(OUT, `view ${name}.png`) });
  // The view is added to the layers as a person does; its layer is the one that is not the made-up result.
  await page.locator('.scene-view .vc-actions button', { hasText: 'Add to layers' }).first().click();
  await close();
  const pinned = await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().layers.find((l) => l.id !== 'res')?.id ?? null);
  if (pinned === null) problems.push('the view was not added to the layers');
  for (const [id, what] of [[pinned, 'layer'], ['res', 'result layer']]) {
    if (id === null) continue;
    await page.evaluate(async (layer) => {
      const { useAppStore } = await import('/src/store.ts');
      const s = useAppStore.getState();
      s.exitFocus();
      useAppStore.setState({ dock: null });
      useAppStore.getState().selectLayer(layer);
    }, id);
    await close();
    await fieldsFit(page, what, problems);
    await page.screenshot({ path: path.join(OUT, `${what} ${name}.png`) });
  }
  await context.close();
  return { name, problems };
}

async function check(browser, { theme, viewport }) {
  const name = `${theme} ${viewport}`;
  const win = VIEWPORTS[viewport];
  const problems = [];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await injectFault(page);
  await page.goto(BASE);
  await page.waitForSelector('.control-panel');

  for (const panel of PANELS) {
    await page.evaluate(async (dock) => {
      const { useAppStore } = await import('/src/store.ts');
      useAppStore.setState({ dock, error: null, notice: null });
    }, panel);
    await page.waitForTimeout(100);

    // 1. The tools of the control panel.
    if (panel === 'controls') {
      const tools = await page.evaluate(() => {
        const bar = document.querySelector('.toolbar');
        const scroller = document.querySelector('.control-scroll');
        return { bar: bar?.getBoundingClientRect().toJSON(), barScroll: bar ? bar.scrollWidth - bar.clientWidth : 0, scrollerOverflow: scroller ? scroller.scrollWidth - scroller.clientWidth : 0, buttons: [...document.querySelectorAll('.toolbar > *')].map((el) => el.getBoundingClientRect().toJSON()) };
      });
      if (tools.barScroll > 0.5) problems.push(`controls: the toolbar is ${tools.barScroll}px wider than its box`);
      if (tools.scrollerOverflow > 0.5) problems.push(`controls: the panel scrolls sideways by ${tools.scrollerOverflow}px`);
      for (const [i, b] of tools.buttons.entries()) if (b.x + b.width > tools.bar.x + tools.bar.width + 0.5) problems.push(`controls: tool ${i} reaches beyond the toolbar`);
    }

    // 2./3. A long error and a notice.
    await page.evaluate(async (long) => {
      const { useAppStore } = await import('/src/store.ts');
      useAppStore.setState({ error: long, notice: 'Done' });
    }, LONG);
    await page.waitForSelector('.toast.error');
    await page.waitForTimeout(150);
    const seen = await page.evaluate(() => {
      const box = (el) => el?.getBoundingClientRect().toJSON() ?? null;
      const toast = document.querySelector('.toast.error');
      const status = document.querySelector('.overlay.status');
      const point = toast ? { x: toast.getBoundingClientRect().x + 20, y: toast.getBoundingClientRect().y + toast.getBoundingClientRect().height / 2 } : null;
      const top = point ? document.elementFromPoint(point.x, point.y) : null;
      return {
        toast: box(toast),
        all: [...document.querySelectorAll('.status-stack > .toast')].map(box),
        zoom: box(document.querySelector('.top-right .btn')),
        topRight: box(document.querySelector('.top-right')),
        covered: top ? !top.closest('.overlay.status') : true,
        closeX: box(toast?.querySelector('.close-x')),
        pageScroll: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        statusBox: box(status),
      };
    });
    for (const [i, box] of seen.all.entries()) if (!inside(box, win)) problems.push(`${panel}: toast ${i} reaches beyond the window ${JSON.stringify(box)}`);
    if (seen.covered) problems.push(`${panel}: the message is covered by another box`);
    if (seen.closeX && !inside(seen.closeX, win)) problems.push(`${panel}: the red x of the message is outside the window`);
    if (seen.pageScroll > 0) problems.push(`${panel}: the page scrolls sideways by ${seen.pageScroll}px`);
    // The message stands under the buttons at the top right, not over them.
    if (seen.zoom && seen.toast && overlaps(seen.zoom, seen.toast)) problems.push(`${panel}: the message lies over "Zoom to selection"`);
    await page.screenshot({ path: path.join(OUT, `${panel} ${name}.png`) });

    // The message closes with its red x.
    const closed = await page.locator('.toast.error .close-x').click({ timeout: 2000 }).then(() => true, () => false);
    if (!closed) problems.push(`${panel}: the red x cannot be clicked (something lies over it)`);
    // Close it by the store when a box covers it, so that the next panel starts clean.
    await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ error: null, notice: null }));
    if (closed && (await page.locator('.toast.error').count()) !== 0) problems.push(`${panel}: the red x does not close the message`);
  }
  await context.close();
  return { name, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = false;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const run of [check, checkRanges]) {
        const { name, problems } = await run(browser, { theme, viewport });
        console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
        for (const p of problems) console.log(`       ${p}`);
        if (problems.length > 0) failed = true;
      }
    }
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
