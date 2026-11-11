// Results of whole numbers in the layer settings (Otto's check in the browser, 11.11.2026): only a band of classes is drawn as it is; any
// other result of whole numbers has the settings of a float one — range with histogram, vmin/vmax, absolute/percentile, Auto-scale, band,
// colormap. Three made-up results, each in a job of its own: Sentinel-2-like reflectance as uint16 (two bands), heights as int16, and the
// class map of a land-cover dataset as uint8 (its `earthx:mask` band). Light and dark theme, a wide and a narrow window. Fails when
//   - the reflectance or the heights have no vmin/vmax, no colormap, no unit switch, no histogram or no usable "Auto-scale", or are drawn
//     without a range, or "Auto-scale" does not put the 2–98 % of the statistics back (the statistics count no nodata, M5-28);
//   - the classes are drawn with a range, or offer a range, a colormap or "Auto-scale", or do not say why;
//   - a field leaves the settings or overlaps another;
// it writes a screenshot of the settings per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/whole-numbers.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-whole-numbers');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const CLASSES_TIP = 'A layer of classes is drawn as it is: it has no range or colormap to set.';

// The 64 bins of a histogram over [low, high] as the tiler writes one (`[counts, edges]`).
const histogram = (low, high) => [Array.from({ length: 64 }, (_, i) => 10 + ((i * 7) % 23)), Array.from({ length: 65 }, (_, i) => low + ((high - low) * i) / 64)];
const stats = (low, high, p2, p98) => ({ minimum: low, maximum: high, mean: (low + high) / 2, count: 1000, valid_percent: 100, percentile_2: p2, percentile_98: p98 });
// The result ids: 22 characters of the URL-safe alphabet.
const CASES = {
  'reflectance uint16': { id: 'Reflectance_uint16_AAA', dataType: 'uint16', bands: [['red', stats(1, 9000, 180, 2400)], ['nir', stats(1, 9000, 300, 4200)]], classes: false, range: ['180', '2400'] },
  'heights int16': { id: 'Heights_int16_AAAAAAAA', dataType: 'int16', bands: [['data', stats(-400, 4800, -20, 3100)]], classes: false, range: ['-20', '3100'] },
  'land cover uint8': { id: 'LandCover_uint8_AAAAAA', dataType: 'uint8', bands: [['map', stats(10, 100, 10, 95)]], classes: true, range: null },
};

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function check(browser, { name, theme, viewport }) {
  const spec = CASES[name];
  const label = `${name} ${theme} ${viewport}`;
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const tiles = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === `/results/${spec.id}/WebMercatorQuad/tilejson.json`) return json({ bounds: [10, 50, 11, 51], minzoom: 0, maxzoom: 14, data_type: spec.dataType, tiles: ['x'] });
    if (url.pathname === `/results/${spec.id}/statistics`) {
      return json({ bands: spec.bands.map(([band, s]) => ({ name: band, data_type: spec.dataType, statistics: { ...s, histogram: histogram(s.minimum, s.maximum) } })) });
    }
    if (url.pathname.startsWith(`/results/${spec.id}/tiles/`)) {
      tiles.push(url.search);
      return route.fulfill({ status: 204 });
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.evaluate(async (spec) => {
    const { useAppStore } = await import('/src/store.ts');
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const { resultStats } = await import('/src/resultLayer.ts');
    const mask = { asset: 'map', band: 'map', classes: [{ value: 10, label: 'Tree cover' }, { value: 80, label: 'Permanent water bodies' }], suggested: [], reference: '', note: '' };
    const dataset = { id: 'land', title: 'Land', viewable: true, collection: { id: 'land', 'earthx:mask': mask } };
    const order = { recipe_version: 2, inputs: [{ name: 'input', dataset: 'land', groups: [['T1']] }], steps: [], output: { kind: 'raster', format: 'cog', dtype: spec.dataType, bands: spec.bands.map(([band]) => band) } };
    const bands = spec.bands.map(([band, s]) => ({ name: band, stats: resultStats({ bands: [{ name: band, data_type: spec.dataType, statistics: s }] }), expression: null }));
    const expires = new Date(Date.now() + 6 * 86_400_000).toISOString();
    const job = {
      jobID: 'Job0000000000000000001', expires, title: 'Result', titleDefault: 'Result', createdAt: new Date().toISOString(), archived: false, groupId: null, batchId: null,
      part: null, range: null, bandRanges: {}, shownBand: null, dates: null, order, status: null, phase: 'successful', archive: 'result.zip', bytes: null, resampled: null,
      failure: null, failureKind: null, normalize: null, error: null, cancelling: false, retrying: false, retryRefused: false, retryError: null, deleting: false,
      deletedUntil: null, serverDeleted: false, lost: false, superseded: false, expired: false,
      tiles: { href: `/results/${spec.id}/WebMercatorQuad/tilejson.json`, width: 1000, gsd: 10 },
      statistics: bands[0].stats, bands,
    };
    useAppStore.setState({ datasets: [dataset], layers: [], dock: 'layers' });
    useProcessingStore.setState({ jobs: [job] });
    await useProcessingStore.getState().showResultOnMap(job.jobID);
    if (useAppStore.getState().layers.length === 0) throw new Error(`no layer of the result: ${useProcessingStore.getState().jobs[0]?.error}`);
  }, spec);
  // The settings of the layer, as a click on its name in the layer manager opens them.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().selectLayer(useAppStore.getState().layers[0].id);
  });
  await page.waitForSelector('.result-controls');
  await page.waitForTimeout(600);
  const report = await page.evaluate(() => {
    const view = document.querySelector('.result-controls');
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const fieldOf = (text) => [...view.querySelectorAll('label')].find((l) => l.querySelector('span')?.textContent === text)?.querySelector('input, select');
    const auto = [...view.querySelectorAll('button')].find((b) => b.textContent.trim() === 'Auto-scale');
    const leaves = [...view.querySelectorAll('.vc-render input:not([type=range]), .vc-render select, .vc-render button')].map((e) => ({ what: e.getAttribute('aria-label') ?? e.textContent.trim(), ...box(e) }));
    return {
      vmin: fieldOf('vmin')?.value ?? null,
      vmax: fieldOf('vmax')?.value ?? null,
      colormap: fieldOf('Colormap')?.value ?? null,
      unit: view.querySelector('.vc-unit') !== null,
      histogram: view.querySelector('.range-hist') !== null,
      auto: auto ? { disabled: auto.disabled } : null,
      tip: view.querySelector('.vc-head .tip')?.getAttribute('data-tip') ?? null,
      leaves,
      panel: box(view),
    };
  });
  const problems = [];
  const expect = (what, got, want) => { if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`); };
  const drawn = tiles.at(-1) ?? '';
  if (spec.classes) {
    expect('vmin/vmax', [report.vmin, report.vmax], [null, null]);
    expect('the colormap', report.colormap, null);
    expect('"Auto-scale"', report.auto, null);
    expect('the reason', report.tip, CLASSES_TIP);
    if (/rescale|colormap_name/.test(drawn)) problems.push(`the classes are drawn with ${drawn}`);
  } else {
    expect('vmin/vmax', [report.vmin, report.vmax], spec.range);
    expect('the colormap', report.colormap, 'viridis');
    expect('the unit switch', report.unit, true);
    expect('the histogram', report.histogram, true);
    expect('"Auto-scale"', report.auto, { disabled: false });
    expect('a reason not to set it', report.tip, null);
    if (!/rescale=/.test(drawn)) problems.push(`drawn without a range: ${drawn || 'no tile asked'}`);
    if (report.vmin !== null) {
      await page.locator('.result-controls label', { hasText: 'vmin' }).locator('input').fill('0');
      await page.getByRole('button', { name: 'Auto-scale' }).click();
      const after = await page.locator('.result-controls label', { hasText: 'vmin' }).locator('input').inputValue();
      expect('vmin after "Auto-scale"', after, spec.range[0]);
    }
  }
  const { leaves, panel } = report;
  for (let i = 0; i < leaves.length; i++) {
    for (let j = i + 1; j < leaves.length; j++) if (overlap(leaves[i], leaves[j])) problems.push(`${leaves[i].what} overlaps ${leaves[j].what}`);
    if (leaves[i].x < panel.x - 0.5 || leaves[i].x + leaves[i].width > panel.x + panel.width + 0.5) problems.push(`${leaves[i].what} leaves the settings`);
  }
  await page.locator('.result-controls').screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}.png`) });
  await context.close();
  return { label, problems };
}

(async () => {
  require('node:fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const name of Object.keys(CASES)) for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) {
    const result = await check(browser, { name, theme, viewport });
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.label}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : 'whole numbers have the settings of a float result; classes are drawn as they are and say why');
  process.exit(failed ? 1 : 0);
})();
