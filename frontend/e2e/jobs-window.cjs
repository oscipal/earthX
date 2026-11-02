// The processing manager as a floating window (UI-03c, plan §7.9, Otto, 2.11.2026), in a real browser. Measured:
//   1. First place and size: 480 × 640 (not higher than the window minus 80 px), under the buttons at the top, right of the rail and of an
//      open panel; over the column at the right (the settings bar), under dialogs.
//   2. Drag by the head, the arrow keys on the head, pull to size at the edge and the corner; the head stays reachable; place and size are
//      kept per browser (a reload opens it where it was) and a broken value in the storage gives the first place.
//   3. Closing: the red x and the symbol "Jobs" in the rail; Esc closes nothing. Under 900 px it is a sheet from the bottom, at most 55 % high,
//      with a grip that folds it; nothing to drag.
//   4. Rows: status, title and date stand in the same columns in every row, a batch and a job alike; the symbols at the end do not overlap and
//      stay in the row; nothing scrolls sideways; the controls are 28 px high with a mouse and 40–44 px on a touch screen and under 900 px.
// In the light and the dark theme, at 1280 x 800, 1920 x 1080, 360 x 740 and 1280 x 800 with a touch screen; one screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/jobs-window.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>, ONLY=1 for one theme and one window
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-jobs-window');
const THEMES = process.env.ONLY ? { light: 'normal' } : { light: 'normal', dark: 'tech' };
const VIEWPORTS = process.env.ONLY
  ? { hd: { width: 1280, height: 800 } }
  : { hd: { width: 1280, height: 800 }, full: { width: 1920, height: 1080 }, narrow: { width: 360, height: 740 }, touch: { width: 1280, height: 800, touch: true } };
const KEY = 'earthx.jobsWindow';
const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function seed(page) {
  await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const order = { recipe_version: 1, inputs: [{ name: 'a', dataset: 'sentinel-2-c1-l2a', groups: [['S1']], assets: ['red'] }], steps: [], output: { kind: 'raster', format: 'cog', dtype: 'float32' } };
    const day = 86400000;
    const group = 'a'.repeat(32);
    const batch = 'b'.repeat(32);
    const base = (n, over) => ({
      jobID: `Old${String(n).padStart(19, '0')}`, expires: new Date(Date.now() + 7 * day).toISOString(), title: `Job ${n} with a title that is rather long to read`, titleDefault: null,
      createdAt: new Date(Date.now() - n * 60000).toISOString(), archived: false, groupId: null, batchId: null, part: null, range: null, order,
      deletedUntil: null, serverDeleted: false, lost: false, superseded: false,
      status: null, phase: 'successful', archive: 'result.zip', bytes: 1000, resampled: null, failure: null, failureKind: null, error: null, cancelling: false,
      retrying: false, retryRefused: false, retryError: null, deleting: false, expired: false, tiles: null, statistics: null, ...over,
    });
    const jobs = [
      base(1, { phase: 'active', archive: null, groupId: group }),
      base(2, { groupId: group }),
      base(3, { phase: 'failed', archive: null, failure: 'The source failed', failureKind: 'source_5xx' }),
      base(4, { batchId: batch, part: 'S1' }),
      base(5, { batchId: batch, part: 'S2', phase: 'failed', archive: null, failure: 'The source failed', failureKind: 'source_5xx' }),
    ].map((j) => ({ ...j, status: { jobID: j.jobID, status: j.phase === 'active' ? 'running' : j.phase, message: '', progress: j.phase === 'active' ? 40 : 100, expires: j.expires } }));
    useProcessingStore.setState({
      groups: [{ id: group, name: 'Field 7' }],
      batches: [{ id: batch, title: 'Batch of scenes', titleDefault: 'Batch of scenes', createdAt: new Date(Date.now() - 10 * 60000).toISOString(), archived: false, groupId: null, refused: [] }],
      jobs,
    });
  });
}

async function open(browser, theme, viewport, storage) {
  const { width, height, touch = false } = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: touch });
  await context.addInitScript(([t, kept]) => {
    localStorage.setItem('earthx.theme', t);
    if (kept !== null && !sessionStorage.getItem('seeded')) {
      localStorage.setItem('earthx.jobsWindow', kept);
      sessionStorage.setItem('seeded', '1');
    }
  }, [THEMES[theme], storage]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('.app-rail');
  // The page reads the jobs of this tab once it is up; what is seeded earlier is overwritten.
  await page.waitForTimeout(1200);
  await seed(page);
  return { context, page, problems };
}

const box = (page, selector) => page.evaluate((s) => { const r = document.querySelector(s)?.getBoundingClientRect(); return r ? { x: r.x, y: r.y, width: r.width, height: r.height } : null; }, selector);
const symbol = (page) => page.locator('nav[aria-label="Main"] button[aria-label^="Processing jobs"]');

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const { width, height, touch = false } = VIEWPORTS[viewport];
  const sheet = width < 900;
  const { context, page, problems } = await open(browser, theme, viewport, null);
  const want = (what, ok) => { if (!ok) problems.push(what); };

  // 1. The symbol opens the window; it is no panel of the dock.
  await symbol(page).click();
  await page.waitForSelector('#jobs-window .pm-row');
  want('the symbol is not pressed', (await symbol(page).getAttribute('aria-pressed')) === 'true');
  const first = await box(page, '#jobs-window');
  if (sheet) {
    want(`the sheet is not at the bottom from the rail: ${JSON.stringify(first)}`, Math.abs(first.x - 48) < 1 && Math.abs(first.y + first.height - height) < 1 && first.height <= height * 0.55 + 1);
    want('a sheet has handles or can be dragged', (await page.locator('.jw-handle').count()) === 0 && (await page.locator('.pm-head').getAttribute('tabindex')) === null);
  } else {
    const panelOpen = await page.evaluate(() => !document.querySelector('.dock')?.hidden);
    const left = 48 + (panelOpen ? 340 : 0) + 16;
    want(`first place ${JSON.stringify(first)}, not left ${left}, top 64, 480 × ${Math.min(640, height - 80)}`, Math.abs(first.x - left) < 1 && Math.abs(first.y - 64) < 1 && Math.abs(first.width - 480) < 1 && Math.abs(first.height - Math.min(640, height - 80)) < 1);
    const above = await page.evaluate(() => { const w = document.querySelector('#jobs-window'); const r = w.getBoundingClientRect(); return document.elementFromPoint(r.x + r.width / 2, r.y + 10)?.closest('#jobs-window') === w; });
    want('the window is not on top at its head', above);
  }

  // 4. Rows: the same columns in every row; symbols inside the row, not on top of each other.
  const rows = await page.evaluate(() => [...document.querySelectorAll('.pm-rows > .pm-row')].map((row) => {
    const r = (e) => { const b = e?.getBoundingClientRect(); return b ? { x: b.x, y: b.y, width: b.width, height: b.height } : null; };
    const line = row.querySelector(':scope > .pm-line');
    return { title: row.querySelector('.pm-title')?.textContent?.slice(0, 12), state: r(row.querySelector('.pm-state')), until: r(row.querySelector('.pm-until')), name: r(row.querySelector('.pm-title')), line: r(line), leaves: [...line.children].map((e) => ({ what: e.getAttribute('aria-label') ?? e.className, ...r(e) })).filter((e) => e.width > 0), scrolls: line.scrollWidth > line.clientWidth + 1 };
  }));
  want(`${rows.length} rows, not 3 (two jobs and a batch of the group, one job)`, rows.length >= 3);
  const same = (key) => new Set(rows.filter((r) => r[key]).map((r) => Math.round(r[key].x))).size <= 1;
  if (!sheet) {
    want('the status column does not start at the same place in every row', same('state'));
    want('the title column does not start at the same place in every row', same('name'));
  }
  for (const row of rows) {
    for (let i = 0; i < row.leaves.length; i++) {
      for (let j = i + 1; j < row.leaves.length; j++) if (overlap(row.leaves[i], row.leaves[j])) problems.push(`${row.title}: ${row.leaves[i].what} overlaps ${row.leaves[j].what}`);
      if (row.leaves[i].x < row.line.x - 0.5 || row.leaves[i].x + row.leaves[i].width > row.line.x + row.line.width + 0.5) problems.push(`${row.title}: ${row.leaves[i].what} leaves its row`);
    }
    if (row.scrolls) problems.push(`${row.title}: the row scrolls sideways`);
  }
  const scrolls = await page.evaluate(() => { const l = document.querySelector('.pm-list'); const w = document.querySelector('#jobs-window').getBoundingClientRect(); return l.scrollWidth > l.clientWidth + 1 || w.right > innerWidth + 1 || w.bottom > innerHeight + 1; });
  want('the manager scrolls sideways or leaves the browser window', !scrolls);

  fs.mkdirSync(OUT, { recursive: true });
  await page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '-')}.png`) });

  // The height of a control: 28 px with a mouse, 40–44 px on a touch screen and under 900 px.
  const heights = await page.evaluate(() => [...document.querySelectorAll('#jobs-window .pm-filter button, #jobs-window .pm-tools .ghost-btn, #jobs-window .pm-icon:not([aria-hidden="true"])')].map((e) => Math.round(e.getBoundingClientRect().height)));
  const [low, high] = touch || sheet ? [40, 44] : [28, 28];
  want(`the controls are ${[...new Set(heights)].join('/')} px high, not ${low}–${high}`, heights.length > 0 && heights.every((h) => h >= low && h <= high));

  if (!sheet) {
    // 2. Drag by the head, keys, size; the place is kept.
    const head = await box(page, '#jobs-window .pm-head');
    await page.mouse.move(head.x + 60, head.y + head.height / 2);
    await page.mouse.down();
    await page.mouse.move(head.x + 160, head.y + head.height / 2 + 40, { steps: 5 });
    await page.mouse.up();
    const moved = await box(page, '#jobs-window');
    want(`dragged by (100, 40): ${JSON.stringify(moved)}`, Math.abs(moved.x - first.x - 100) < 2 && Math.abs(moved.y - first.y - 40) < 2);
    await page.locator('#jobs-window .pm-head').focus();
    await page.keyboard.press('ArrowRight');
    await page.keyboard.press('ArrowDown');
    const keyed = await box(page, '#jobs-window');
    want(`arrow keys: ${JSON.stringify(keyed)}`, Math.abs(keyed.x - moved.x - 16) < 1 && Math.abs(keyed.y - moved.y - 16) < 1);
    const corner = { x: keyed.x + keyed.width - 6, y: keyed.y + keyed.height - 6 };
    await page.mouse.move(corner.x, corner.y);
    await page.mouse.down();
    await page.mouse.move(corner.x + 60, corner.y - 40, { steps: 5 });
    await page.mouse.up();
    const sized = await box(page, '#jobs-window');
    want(`corner pulled by (60, -40): ${JSON.stringify(sized)}`, Math.abs(sized.width - keyed.width - 60) < 2 && Math.abs(sized.height - keyed.height + 40) < 2);
    await page.mouse.move(sized.x + sized.width - 2, sized.y + 200);
    await page.mouse.down();
    await page.mouse.move(0, sized.y + 200, { steps: 5 });
    await page.mouse.up();
    want('the width goes under 420 px', (await box(page, '#jobs-window')).width >= 420 - 0.5);
    // The head cannot be dragged out of the window.
    const h2 = await box(page, '#jobs-window .pm-head');
    await page.mouse.move(h2.x + 60, h2.y + 10);
    await page.mouse.down();
    await page.mouse.move(-2000, -2000, { steps: 5 });
    await page.mouse.up();
    const out = await box(page, '#jobs-window');
    want(`the head left the window: ${JSON.stringify(out)}`, out.y >= -0.5 && out.x + out.width >= 119);
    const kept = await page.evaluate((k) => localStorage.getItem(k), KEY);
    want(`nothing kept: ${kept}`, kept !== null && JSON.parse(kept).width >= 420);
    // Kept per browser: a reload opens it where it was.
    await page.reload({ waitUntil: 'domcontentloaded' });
    await page.waitForSelector('.app-rail');
    await page.waitForTimeout(1200);
    await seed(page);
    await symbol(page).click();
    await page.waitForSelector('#jobs-window');
    const back = await box(page, '#jobs-window');
    want(`after a reload ${JSON.stringify(back)}, not ${JSON.stringify(out)}`, Math.abs(back.x - out.x) < 1 && Math.abs(back.y - out.y) < 1 && Math.abs(back.width - out.width) < 1);
    // A browser window that gets smaller pushes it back.
    await page.setViewportSize({ width: 1000, height: 500 });
    await page.waitForTimeout(200);
    const small = await box(page, '#jobs-window');
    want(`not pushed back: ${JSON.stringify(small)}`, small.x <= 1000 - 119 && small.y <= 500 - 43 && small.height <= 500 + 0.5);
    await page.setViewportSize({ width, height });
  }

  // 3. Esc closes nothing; the red x and the symbol close; the focus goes back to the symbol.
  await page.locator('#jobs-window .pm-head').focus();
  await page.keyboard.press('Escape');
  await page.keyboard.press('Tab');
  await page.keyboard.press('Escape');
  want('Esc closed the window', (await page.locator('#jobs-window').count()) === 1);
  await page.locator('#jobs-window .close-x').click();
  want('the red x did not close it', (await page.locator('#jobs-window').count()) === 0);
  want('the focus did not go back to the symbol', await page.evaluate(() => document.activeElement?.getAttribute('aria-label')?.startsWith('Processing jobs') ?? false));
  await symbol(page).click();
  await page.waitForSelector('#jobs-window');
  await symbol(page).click();
  want('the symbol did not close it', (await page.locator('#jobs-window').count()) === 0);

  await context.close();
  return { label, problems };
}

async function broken(browser) {
  const problems = [];
  for (const raw of ['not json', '{"x":-5000,"y":10,"width":500,"height":400}', '{"x":1,"y":1,"width":10,"height":10}', '[]']) {
    const { context, page, problems: found } = await open(browser, 'light', Object.keys(VIEWPORTS)[0], raw);
    await symbol(page).click();
    await page.waitForSelector('#jobs-window');
    const b = await box(page, '#jobs-window');
    if (Math.abs(b.width - 480) > 1 || Math.abs(b.y - 64) > 1) problems.push(`${raw}: opened at ${JSON.stringify(b)}, not the first place`);
    problems.push(...found);
    await context.close();
  }
  return { label: 'broken storage', problems };
}

(async () => {
  const browser = await chromium.launch();
  const results = [await broken(browser)];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) results.push(await check(browser, { theme, viewport }));
  await browser.close();
  let failed = 0;
  for (const { label, problems } of results) {
    console.log(problems.length ? `FAIL ${label}` : `ok   ${label}`);
    for (const p of problems) console.log(`     ${p}`);
    if (problems.length) failed += 1;
  }
  if (failed) {
    console.log(`${failed} case(s) with problems`);
    process.exit(1);
  }
})();
