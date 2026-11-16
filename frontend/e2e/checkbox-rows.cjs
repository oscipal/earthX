// A checkbox switches only at its box and its text, not at a click anywhere in its row (UI-08, Otto, 16.11.2026; Leitfaden §7), in a
// real browser:
//   1. the processing panel of a relief model with a "Terrain" step on "hillshade": "Four lights" (`.pp-check`);
//   2. the control panel: "Select multiple datasets" (`.multi-select-toggle`).
// For each label of a checkbox that is shown: a click in its row right of the text (where nothing else is) leaves the box as it was, a
// click on the text switches it, a click on the box switches it back. In the light and the dark theme, at 1280 x 800 and 360 x 740; a
// screenshot of the panel with "Four lights" per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/checkbox-rows.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-checkbox-rows');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'cop-dem-glo-30.json'), 'utf8'));
const DATASET = 'cop-dem-glo-30';

// Every label of a checkbox in `scope` that is shown: its text, and up to three points of its row right of the end of its text where nothing
// else is (on the label itself or on the row: none where the row ends with the text).
const LABELS = (scope) => {
  for (const marked of document.querySelectorAll('[data-check-row]')) delete marked.dataset.checkRow;
  return [...document.querySelectorAll(`${scope} label`)]
    .filter((label) => label.querySelector('input[type="checkbox"]') && label.getClientRects().length > 0)
    .map((label, index) => {
      label.dataset.checkRow = String(index);
      const own = label.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(label);
      const textEnd = Math.max(...[...range.getClientRects()].map((r) => r.right));
      const row = label.parentElement.getBoundingClientRect();
      const y = own.y + own.height / 2;
      const free = [];
      for (let x = textEnd + 8; x < row.right - 2; x += 12) {
        const hit = document.elementFromPoint(x, y);
        const control = hit?.closest('label, button, input, select, a, [role="button"], [tabindex]');
        if (hit && (!control || control === label)) free.push(x);
      }
      const step = Math.max(1, Math.floor(free.length / 3));
      return { index, text: label.textContent.trim().slice(0, 40), free: free.filter((_, i) => i % step === 0).slice(0, 3), y, textEnd: textEnd - own.x, rowWidth: row.width };
    });
};

async function checkLabels(page, scope, where) {
  const problems = [];
  const labels = await page.evaluate(LABELS, scope);
  if (labels.length === 0) problems.push(`${where}: no checkbox found`);
  for (const label of labels) {
    const box = page.locator(`label[data-check-row="${label.index}"] input[type="checkbox"]`);
    const what = `${where}, "${label.text}"`;
    const before = await box.isChecked();
    for (const x of label.free) {
      await page.mouse.click(x, label.y);
      if ((await box.isChecked()) !== before) {
        problems.push(`${what}: a click in the row at x ${Math.round(x)}, right of its text, switched it (row ${Math.round(label.rowWidth)} px)`);
        await box.click();
      }
    }
    await page.locator(`label[data-check-row="${label.index}"]`).click({ position: { x: label.textEnd - 4, y: 6 } });
    if ((await box.isChecked()) === before) problems.push(`${what}: a click on its text did not switch it`);
    await box.click();
    if ((await box.isChecked()) !== before) problems.push(`${what}: a click on the box did not switch it back`);
  }
  return { problems, count: labels.length };
}

async function run(browser, theme, size) {
  const label = `${theme} ${size}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[size] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname === '/colormaps') return json({ groups: [] });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.app-rail');

  // 2. The control panel.
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: 'controls' }));
  await page.waitForSelector('.multi-select-toggle');
  const controls = await checkLabels(page, '.dock', `${label}, control panel`);
  problems.push(...controls.problems);

  // 1. The processing panel with a terrain step on "hillshade".
  await page.evaluate(async (dataset) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const item = {
      id: 'CELL_0', collection: dataset, bbox: [8, 46, 9, 47],
      geometry: { type: 'Polygon', coordinates: [[[8, 46], [9, 46], [9, 47], [8, 47], [8, 46]]] },
      properties: { datetime: '2021-01-01T00:00:00Z', 'earthx:state': 'latest', gsd: 30 },
      assets: { data: { href: 'https://assets.example.org/0.tif', type: COG, 'raster:bands': [{ data_type: 'float32', nodata: -9999, unit: 'm' }] } },
    };
    const collection = {
      id: dataset, title: 'Relief model', 'earthx:format': 'cog',
      'earthx:capabilities': { roi: true, time_range: false, band_math: true, interpolation: true, reprojection: true, terrain: true },
      'earthx:default_render': { title: 'Height', assets: ['data'], rescale: [[0, 4000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['earthx:state'], min_zoom: 7, max_zoom: 15, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['earthx:state'], overview: null, overview_resampling: null, overview_substitute: null },
      'earthx:license_flags': { tier: 'processing' },
      extent: { spatial: { bbox: [[-180, -90, 180, 84]] }, temporal: { interval: [['2019-01-01T00:00:00Z', '2023-12-31T00:00:00Z']] } },
    };
    const groups = [{ key: ['latest'], label: 'latest', items: [item] }];
    useAppStore.setState({
      datasets: datasetsFrom([collection]), selectedDatasetIds: [dataset], datasetId: dataset, openSectionId: dataset,
      sections: [{ datasetId: dataset, items: [item], groups, notes: [], groupingError: null, origin: 'search', incomplete: false }],
      items: [item], groups, activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: [item.id], focusMode: false, downloaded: {}, layers: [], dock: null,
    });
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().openProcessing();
  }, DATASET);
  await page.waitForTimeout(1200);
  await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().addStep('terrain', 1);
    const { key } = useProcessingStore.getState().steps.at(-1);
    useProcessingStore.getState().updateStep(key, 'product', 'hillshade');
  });
  const four = page.locator('.processing-panel label.pp-check', { hasText: 'Four lights' });
  await four.waitFor();
  await four.scrollIntoViewIfNeeded();
  const panel = await checkLabels(page, '.processing-panel', `${label}, processing panel`);
  problems.push(...panel.problems);
  if (!(await page.evaluate(() => [...document.querySelectorAll('.processing-panel label')].some((l) => l.textContent.includes('Four lights'))))) {
    problems.push(`${label}: "Four lights" is not there`);
  }
  await four.scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(OUT, `checkbox-rows-${theme}-${size}.png`) });
  console.log(`${label}: ${controls.count} checkbox(es) in the control panel, ${panel.count} in the processing panel`);
  await context.close();
  return problems;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const size of Object.keys(VIEWPORTS)) {
      const problems = await run(browser, theme, size).catch((error) => [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`]);
      failed += problems.length > 0 ? 1 : 0;
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} checkbox rows, ${theme} ${size}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
    }
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
