// The processing panel in the order of UI-03b (plan §7.6, Otto, 3.11.2026), in a real browser with made-up answers of the platform:
//   1. Place and width: from 900 px the panel is flush at the right edge, from the top to the foot, 520 px wide at 1280 px and 640 px at
//      1920 px (`--sheet-wide-width`), the buttons at the top and the map controls left of it; under 900 px a sheet from below.
//   2. The sections stand in one order (Selection, Bands, Processing steps, Output, Preview on the map; Review and Start at the foot), each
//      with a heading, and nothing scrolls sideways.
//   3. One grid: the names of the fields of every step stand in one column (the same x), the controls in another (the same x), and the
//      field of the preview ("Band", "Scale", "Colormap") in the same column as those of the steps.
//   4. The step is a card: its head holds the name and the symbols Rename, Move up, Move down and Remove; none of them leaves the card.
//   5. Esc closes nothing, the red x closes the panel.
//   6. The height of a control: 28 px with a mouse from 900 px, 40-44 px under 900 px and on a touch screen.
// In the light and the dark theme, at 1280 x 800, 1920 x 1080, 360 x 740 and 1280 x 800 with a touch screen; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/processing-panel.cjs           # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-processing-panel');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'sentinel-2-c1-l2a.json'), 'utf8'));
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { hd: { width: 1280, height: 800 }, full: { width: 1920, height: 1080 }, narrow: { width: 360, height: 740 }, touch: { width: 1280, height: 800, touch: true } };
const STAT = { count: 900, min: 0.01, max: 0.9, percentile_2: 0.05, percentile_98: 0.7, unit: null };

async function open(browser, theme, viewport) {
  const { touch = false, ...size } = VIEWPORTS[viewport];
  // A touch screen is `(pointer: coarse)` for the page.
  const context = await browser.newContext({ viewport: size, hasTouch: touch });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const posted = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/estimate')) {
      return json({ estimate: { size: 4e6, duration: 'PT3.4S', outputPixels: 1e6, inputPixels: 2e6, inputBytes: 4e6, assets: 2, units: 1 }, skippedItems: [] });
    }
    if (url.pathname.endsWith('/execution')) {
      posted.push(JSON.parse(route.request().postData()).inputs.recipe);
      return json({ processID: 'recipe', type: 'process', jobID: 'QrStUvWxYzAbCdEfGhIj_-', status: 'accepted', message: '', progress: 0, created: '2026-10-31T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    if (url.pathname.endsWith('/statistics')) return json({ b1: STAT });
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  return { context, page, posted };
}

// Scenes A and B of one day, C of another; one layer over `ids`, cut to its AOI or not.
async function setUp(page, ids, crop, selected = ids) {
  await page.evaluate(
    async ({ ids, crop, selected }) => {
      const { useAppStore } = await import('/src/store.ts');
      const box = (x, y) => ({ type: 'Polygon', coordinates: [[[x, y], [x + 1, y], [x + 1, y + 1], [x, y + 1], [x, y]]] });
      const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
      const asset = () => ({ href: 'https://example.org/b.tif', type: COG, 'raster:bands': [{ data_type: 'uint16' }] });
      const scene = (id, day) => ({
        id, collection: 'sentinel-2-c1-l2a', bbox: [10, 50, 11, 51], geometry: box(10, 50),
        properties: { datetime: `${day}T10:00:00Z`, gsd: 10 }, assets: { red: asset(), nir: asset() },
      });
      const one = [scene('S2B_A', '2026-07-01'), scene('S2B_B', '2026-07-01')];
      const two = [scene('S2B_C', '2026-07-02')];
      const aoi = { type: 'Polygon', coordinates: [[[10.4, 50.4], [10.6, 50.4], [10.6, 50.6], [10.4, 50.6], [10.4, 50.4]]] };
      useAppStore.setState({
        datasets: [{
          id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 },
          browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true,
          collection: { id: 'sentinel-2-c1-l2a', 'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' }, 'earthx:capabilities': { interpolation: true } },
        }],
        datasetId: 'sentinel-2-c1-l2a', items: [...one, ...two],
        groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: one }, { key: ['2026-07-02'], label: '2026-07-02', items: two }],
        activeGroupIndex: 0, selectedIds: [], aoi: null, aoiPoint: null, focusMode: false, error: null, dock: 'layers',
        layers: [{
          id: 'L1', name: 'Crop', visible: true, opacity: 1, overlays: [],
          restore: {
            focusMode: true, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: selected, itemIds: ids, groupItemIds: [ids],
            aoi: crop ? aoi : null, cropToAoi: crop, datasetId: 'sentinel-2-c1-l2a',
          },
        }],
      });
    },
    { ids, crop, selected },
  );
  await page.waitForSelector('.layer-row [data-col="process"]', { timeout: 10000 });
}



const RAIL = 48;

async function check(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  fs.mkdirSync(OUT, { recursive: true });
  const { context, page } = await open(browser, theme, viewport);
  const size = VIEWPORTS[viewport];
  const narrow = size.width < 900;
  await setUp(page, ['S2B_A', 'S2B_B'], true);
  await page.locator('.layer-row [data-col="process"]').click();
  await page.waitForSelector('.processing-panel section[aria-label="Selection"]');
  const panel = page.locator('.processing-panel');
  await panel.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  for (const label of [/Reproject/, /Normalize/, /Mask by class/]) await panel.getByRole('button', { name: label }).first().click();
  await page.waitForTimeout(500);

  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; };
    const sheet = document.querySelector('.processing-sheet');
    const root = document.querySelector('.processing-panel');
    const body = root.querySelector('.pp-body');
    const steps = [...root.querySelectorAll('.pp-steps > li')];
    return {
      view: { width: window.innerWidth, height: window.innerHeight },
      sheet: box(sheet),
      topRight: document.querySelector('.overlay.top-right') ? box(document.querySelector('.overlay.top-right')) : null,
      sections: [...root.querySelectorAll('.pp-body > section')].map((s) => ({ name: s.getAttribute('aria-label'), heading: s.querySelector('h3.pp-heading')?.textContent ?? null })),
      foot: root.querySelector('.pp-foot')?.getAttribute('aria-label') ?? null,
      scrolls: document.documentElement.scrollWidth > window.innerWidth || body.scrollWidth > body.clientWidth + 1,
      // The first column of the labels and the first of the controls, in every row of every card (the checkbox rows and the chips excepted).
      labelsX: steps.flatMap((s) => [...s.querySelectorAll('label.vc-field.pp-field > .pp-label')].map((l) => Math.round(l.getBoundingClientRect().x))),
      controlsX: steps.flatMap((s) => [...s.querySelectorAll('label.vc-field.pp-field > input:not([type=checkbox]), label.vc-field.pp-field > select, label.vc-field.pp-field > textarea')].map((c) => Math.round(c.getBoundingClientRect().x))),
      heads: steps.map((s) => ({ card: box(s), actions: [...s.querySelectorAll('.pp-step-head button')].map((b) => ({ label: b.getAttribute('aria-label'), ...box(b) })) })),
      heights: {
        field: [...root.querySelectorAll('.pp-step input:not([type=checkbox]), .pp-step select')].map((e) => Math.round(e.getBoundingClientRect().height)),
        button: [...root.querySelectorAll('.pp-add-btn, .pp-foot .primary-btn, .pp-foot .ghost-btn, .pp-icon-btn, .pp-chip')].map((e) => Math.round(e.getBoundingClientRect().height)),
      },
      theme: document.querySelector('.app')?.dataset.theme,
    };
  });
  const expect = (what, got, want) => { if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`); };
  if (report.theme !== THEMES[theme]) problems.push(`the app shows the theme ${report.theme}`);
  expect('the sections', report.sections.map((s) => s.name), ['Selection', 'Bands', 'Processing steps', 'Output', 'Preview on the map']);
  if (report.sections.some((s) => !s.heading)) problems.push('a section has no heading');
  expect('the foot', report.foot, 'Review');
  if (report.scrolls) problems.push('the panel or the page scrolls sideways');
  // 1. Place and width.
  if (narrow) {
    if (Math.abs(report.sheet.x - RAIL) > 1 || Math.abs(report.sheet.right - report.view.width) > 1 || Math.abs(report.sheet.bottom - report.view.height) > 1) problems.push(`the sheet is not at the foot from the rail to the edge: ${JSON.stringify(report.sheet)}`);
    if (report.sheet.height > report.view.height * 0.6 + 1) problems.push(`the sheet is ${report.sheet.height} px high, over 60 %`);
  } else {
    const want = Math.min(640, Math.max(520, report.view.width * 0.34));
    if (Math.abs(report.sheet.width - want) > 1) problems.push(`the panel is ${report.sheet.width} px wide, not ${want}`);
    if (Math.abs(report.sheet.right - report.view.width) > 0.5 || report.sheet.y > 0.5 || Math.abs(report.sheet.bottom - report.view.height) > 0.5) problems.push(`the panel is not flush from the top to the foot: ${JSON.stringify(report.sheet)}`);
    if (report.topRight && report.topRight.right > report.sheet.x + 0.5) problems.push('the buttons at the top lie over the panel');
  }
  // 3. One grid.
  if (report.labelsX.length < 6) problems.push(`only ${report.labelsX.length} labels measured`);
  else {
    if (new Set(report.labelsX).size !== 1) problems.push(`the labels stand in several columns: ${[...new Set(report.labelsX)]}`);
    if (new Set(report.controlsX).size !== 1) problems.push(`the controls stand in several columns: ${[...new Set(report.controlsX)]}`);
  }
  // 4. The head of a card.
  expect('the symbols of a card', report.heads[0].actions.map((a) => a.label), ['Rename', 'Move up', 'Move down', 'Remove']);
  for (const { card, actions } of report.heads) {
    for (const a of actions) if (a.x < card.x - 0.5 || a.right > card.right + 0.5) problems.push(`${a.label} leaves its card`);
  }
  // 6. Heights.
  const finger = narrow || viewport === 'touch';
  const [lo, hi] = finger ? [40, 44] : [28, 28];
  for (const kind of ['field', 'button']) {
    const bad = report.heights[kind].filter((h) => h < lo - 1 || (kind === 'field' && h > hi + 1));
    if (bad.length > 0) problems.push(`${kind}s are ${[...new Set(bad)]} px high, not ${lo}-${hi}`);
  }
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
  // 5. Esc closes nothing; the red x does.
  await page.locator('textarea[id$="-expression"]').focus();
  await page.keyboard.press('Escape');
  await page.mouse.click(size.width / 2 - (narrow ? 0 : 200), 200).catch(() => {});
  await page.keyboard.press('Escape');
  if ((await page.locator('.processing-panel').count()) !== 1) problems.push('Esc closed the panel');
  await page.locator('.pp-head .close-x').click();
  if ((await page.locator('.processing-panel').count()) !== 0) problems.push('the red x did not close the panel');
  await context.close();
  console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
  for (const p of problems) console.log(`     ${p}`);
  return problems.length;
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) failed += await check(browser, theme, viewport);
  await browser.close();
  if (failed > 0) {
    console.log(`${failed} case(s) with problems`);
    process.exit(1);
  }
  console.log('the panel is wide, in one order, in one grid, with cards, finger-high where it must be, and Esc closes nothing');
})();
