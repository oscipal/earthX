// Browser check of UI-12 PR 1 (Otto, 25.11.2026), with made-up answers of the API, at 1280 x 800, 1280 x 360 and 360 x 740, in the light
// and the dark theme, with a German browser (`de-DE`). It fails when
//   5. a place found while "Rectangle" is chosen leaves the tool on (pressed), or the next click on the map still draws;
//   6. the AOI "Point" is a point on the map (the colour of the AOI at the point, none on a ring round it where the square was);
//   7. "Add dataset" does not open the Data catalogue with "Addable only" on in the pop-up "Filters" ("Filters · 1", `entry=full` in the
//      request), or its "×" does not take it off again (the next request without `entry`);
//   8. a date field shows anything but "YYYY-MM-DD" in a German browser, or its calendar is not in English, Monday first, inside the window;
//   9. the Data catalogue scrolls with another bar than the processing panel, or with the browser's own;
//  11. "Add dataset" looks like a dataset: no dashed edge, the text in the colour of a dataset.
// A screenshot per window and theme: <OUT>/ui-12-<theme>-<size>-<step>.png.
//
//   cd frontend && npm run dev &            # a FRESH dev server (one that saw no edits): the check imports the store
//   node e2e/ui-12-search-panel.cjs         # BASE=http://localhost:5173 OUT=<directory for the screenshots> ONLY="dark narrow"
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-ui-12');
const ONLY = process.env.ONLY;
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, low: { width: 1280, height: 360 }, narrow: { width: 360, height: 740 } };
const PLACE = { name: 'Bern', display_name: 'Bern, Switzerland', kind: 'city', bbox: [7.29, 46.91, 7.5, 46.99], outline: null, outline_simplified: false };
const entries = (n) => Array.from({ length: n }, (_, i) => ({ id: `made-up-${i}`, title: `Made up ${i}`, description: 'x', 'earthx:entry': i % 2 ? 'listed' : 'full', links: [] }));

// The colours of a screenshot at some points, read in the page (no decoder in the project).
async function coloursAt(page, png, points) {
  return page.evaluate(async ({ data, points: at }) => {
    const img = new Image();
    img.src = `data:image/png;base64,${data}`;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);
    return at.map(([x, y]) => [...ctx.getImageData(x, y, 1, 1).data.slice(0, 3)]);
  }, { data: png.toString('base64'), points });
}
const near = (a, b) => a.every((v, i) => Math.abs(v - b[i]) < 40);
const AOI_COLOUR = [0x19, 0xe0, 0xff];

async function run(browser, theme, size) {
  const label = `${theme} ${size}`;
  const problems = [];
  const fail = (what) => problems.push(what);
  const narrow = VIEWPORTS[size].width < 900;
  const context = await browser.newContext({ viewport: VIEWPORTS[size], locale: 'de-DE' });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => fail(`the page failed: ${error.message.slice(0, 160)}`));
  const bodies = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.endsWith('/geocode')) return json({ results: [PLACE], attribution: 'Data © OpenStreetMap contributors', attribution_url: 'https://www.openstreetmap.org/copyright' });
    if (url.pathname.endsWith('/catalogue/categories')) return json({ categories: [{ id: 'water', title: 'Water' }] });
    if (url.pathname.endsWith('/catalogue/regions')) return json({ regions: [] });
    if (url.pathname.endsWith('/stac/collections') && route.request().method() === 'GET') return json({ collections: [], links: [] });
    if (url.pathname.endsWith('/stac/collections') && route.request().method() === 'POST') {
      const body = JSON.parse(route.request().postData() ?? '{}');
      bodies.push(body);
      const found = entries(40).filter((e) => body.entry !== 'full' || e['earthx:entry'] === 'full');
      return json({ collections: found, links: [], numberMatched: found.length });
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.app-rail');
  const shot = (step) => page.screenshot({ path: path.join(OUT, `ui-12-${theme}-${size}-${step}.png`) });
  const store = (fn, arg) => page.evaluate(fn, arg);
  const open = async (dock) => store(async (d) => (await import('/src/store.ts')).useAppStore.setState({ dock: d, catalogueOpen: false, error: null }), dock);

  // 11. "Add dataset" is an action.
  await open('controls');
  const tile = page.locator('.dataset-list .add-dataset');
  const look = await tile.evaluate((el) => {
    const s = getComputedStyle(el);
    const muted = getComputedStyle(document.querySelector('.app')).getPropertyValue('--muted').trim();
    const probe = document.createElement('span');
    probe.style.color = muted;
    document.body.append(probe);
    const mutedRgb = getComputedStyle(probe).color;
    probe.remove();
    return { border: s.borderTopStyle, colour: s.color, muted: mutedRgb };
  });
  if (look.border !== 'dashed') fail(`"Add dataset" has a ${look.border} edge, not a dashed one`);
  if (look.colour !== look.muted) fail(`"Add dataset" is written in ${look.colour}, not in the muted colour ${look.muted}`);

  // 8. The date fields in a German browser.
  const day = page.locator('.date-row .date-field input').first();
  await store(async () => (await import('/src/store.ts')).useAppStore.setState({ dateFrom: '2026-03-15', dateTo: '2026-04-01' }));
  if ((await day.inputValue()) !== '2026-03-15') fail(`the date field shows "${await day.inputValue()}"`);
  if ((await day.getAttribute('type')) !== 'text') fail('the date field is the browser\'s own');
  await page.locator('.date-row .date-icon-btn').first().click();
  const calendar = page.locator('.day-calendar');
  await calendar.waitFor();
  const month = await calendar.locator('.day-calendar-month').textContent();
  const heads = await calendar.locator('.day-calendar-weekday').allTextContents();
  if (month !== 'March 2026') fail(`the calendar names its month "${month}"`);
  if (heads.join(' ') !== 'Mon Tue Wed Thu Fri Sat Sun') fail(`the calendar heads read "${heads.join(' ')}"`);
  const box = await page.locator('.day-calendar-popup').boundingBox();
  if (box.x < 0 || box.y < 0 || box.x + box.width > VIEWPORTS[size].width + 0.5 || box.y + box.height > VIEWPORTS[size].height + 0.5) fail(`the calendar leaves the window: ${JSON.stringify(box)}`);
  const sunday = await calendar.locator('.day-calendar-weekday').last().boundingBox();
  if (sunday.x + sunday.width > box.x + box.width + 0.5) fail('the calendar cuts off its last column');
  const popupScrolls = await page.locator('.day-calendar-popup').evaluate((el) => el.scrollHeight > el.clientHeight + 1);
  if (popupScrolls) fail('the calendar scrolls');
  await shot('8-calendar');
  await calendar.locator('[aria-label="2026-03-20"]').click();
  await page.waitForTimeout(150);
  if ((await day.inputValue()) !== '2026-03-20') fail(`a day chosen in the calendar shows "${await day.inputValue()}"`);

  // 5. Rectangle, then a place.
  await page.getByRole('button', { name: 'Rectangle' }).click();
  await open('controls');
  await page.getByPlaceholder('Place name').fill('Bern');
  await page.keyboard.press('Enter');
  await page.locator('.place-results [role=option], .place-results button, .place-results li').first().click();
  await page.waitForTimeout(300);
  const pressed = await page.getByRole('button', { name: 'Rectangle' }).getAttribute('aria-pressed');
  if (pressed !== 'false') fail('"Rectangle" is still pressed after a place was found');
  const tool = await store(async () => (await import('/src/store.ts')).useAppStore.getState().toolMode);
  if (tool !== 'none') fail(`the tool "${tool}" is still on after a place was found`);
  await shot('5-place');

  // 6. A point is a point.
  await page.getByRole('button', { name: 'Point' }).click();
  await open(null);
  await page.waitForTimeout(300);
  const mapBox = await page.locator('.maplibregl-canvas').boundingBox();
  const at = [Math.round(mapBox.x + mapBox.width / 2), Math.round(mapBox.y + mapBox.height / 2)];
  await page.mouse.click(at[0], at[1]);
  await page.waitForTimeout(400);
  await open(null);
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ flyToBbox: null }));
  await page.waitForTimeout(1500);
  const point = await store(async () => (await import('/src/store.ts')).useAppStore.getState().aoi);
  if (point?.type !== 'Point') fail('the tool "Point" gave no point');
  else {
    // Where the point now stands on the screen after the map flew to it.
    const png = await page.screenshot();
    const centre = [Math.round(mapBox.x + mapBox.width / 2), Math.round(mapBox.y + mapBox.height / 2)];
    const ring = Math.min(mapBox.width, mapBox.height) / 2 - 12;
    const around = Array.from({ length: 32 }, (_, i) => [Math.round(centre[0] + Math.cos(i / 5) * ring * (0.3 + (i % 8) / 10)), Math.round(centre[1] + Math.sin(i / 5) * ring * (0.3 + (i % 8) / 10))]);
    const [mid, ...rest] = await coloursAt(page, png, [centre, ...around]);
    if (!near(mid, AOI_COLOUR)) fail(`no point drawn in the middle of the map (colour ${mid})`);
    if (rest.some((c) => near(c, AOI_COLOUR))) fail('the colour of the AOI shows away from the point: a square round it?');
    await shot('6-point');
  }

  // 7. "Add dataset" opens the catalogue with "Addable only".
  await open('controls');
  bodies.length = 0;
  await page.locator('.dataset-list .add-dataset').click();
  await page.locator('.catalogue').waitFor();
  await page.waitForTimeout(400);
  const button = page.locator('.catalogue-filters-btn');
  if ((await button.textContent()) !== 'Filters · 1') fail(`the button reads "${await button.textContent()}" after "Add dataset"`);
  if (bodies.length === 0 || bodies.some((b) => b.entry !== 'full')) fail(`the catalogue asked ${JSON.stringify(bodies.map((b) => b.entry ?? null))}, not only the full entries`);
  await button.click();
  const addable = page.locator('.catalogue-filters-popup .catalogue-addable input[role="switch"]');
  if (!(await addable.isChecked())) fail('"Addable only" is off in the pop-up');
  await shot('7-addable');
  bodies.length = 0;
  await page.locator('.catalogue-filters-popup button[aria-label="Clear addable only"]').click();
  await page.waitForTimeout(400);
  if (await addable.isChecked()) fail('the "×" left "Addable only" on');
  if (bodies.length === 0 || bodies.some((b) => 'entry' in b)) fail('after the "×" the catalogue still asks for the full entries only');
  await page.mouse.click(VIEWPORTS[size].width - 5, VIEWPORTS[size].height - 5);

  // 9. One scroll bar for the catalogue and the processing panel.
  await store(async () => (await import('/src/processingStore.ts')).useProcessingStore.setState({ open: true }));
  await page.waitForTimeout(300);
  const bars = await page.evaluate(() => ['.catalogue-list', '.pp-body'].map((s) => (document.querySelector(s) ? getComputedStyle(document.querySelector(s)).scrollbarColor : null)));
  if (!bars[0] || bars[0] === 'auto') fail(`the Data catalogue scrolls with the browser's own bar (${bars[0]})`);
  if (bars[1] && bars[0] !== bars[1]) fail(`the bars differ: catalogue ${bars[0]}, processing panel ${bars[1]}`);
  if (!narrow) await shot('9-scroll');

  await context.close();
  console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${label}`);
  for (const p of problems) console.log(`     ${p}`);
  return problems.length;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const size of Object.keys(VIEWPORTS)) {
      if (ONLY && ONLY !== `${theme} ${size}`) continue;
      failed += await run(browser, theme, size);
    }
  }
  await browser.close();
  console.log(failed === 0 ? `screenshots in ${OUT}` : `${failed} problems; screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
