// Browser check of "Run again" and the rename in the details of a job (NM4-34): the symbol ↻ on a failed, a cancelled and an
// expired job and on the batch row, one request for the order, the new job in the place of the old one, "Superseded" under
// "All", the symbol left out for an order that would fail again, and the title renamed in the details and seen in the manager.
// Runs in the light and the dark theme at three widths; fails when a symbol overlaps another or leaves its row; writes a
// screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/job-retry.cjs                  # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-job-retry');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 }, 'very narrow': { width: 320, height: 640 } };

const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const posted = [];
  let made = 0;
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    const doc = (id, status) => ({ processID: 'recipe', type: 'process', jobID: id, status, message: '', progress: 0, created: new Date().toISOString(), expires: new Date(Date.now() + 7 * 86400000).toISOString(), recipeID: 'r', links: [] });
    if (route.request().method() === 'POST' && url.pathname === '/processing/processes/recipe/execution') {
      posted.push(JSON.parse(route.request().postData()));
      await new Promise((resolve) => setTimeout(resolve, 150));
      made += 1;
      return json(doc(`New${String(made).padStart(19, '0')}`, 'accepted'), 201);
    }
    const job = /^\/processing\/jobs\/(New\d{19})$/.exec(url.pathname);
    if (job) return json(doc(job[1], 'accepted'));
    return json({ detail: 'not made up' }, 404);
  });
  page.setDefaultTimeout(8000);
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const order = (dataset) => ({ recipe_version: 1, inputs: [{ name: 'a', dataset, groups: [['S1']], assets: ['red'] }], steps: [], output: { kind: 'raster', format: 'cog', dtype: 'float32' } });
    const day = 86400000;
    const base = (n, over) => ({
      jobID: `Old${String(n).padStart(19, '0')}`, expires: new Date(Date.now() + 7 * day).toISOString(), title: `Job ${n} with a title that is rather long to read`, titleDefault: null,
      createdAt: new Date(Date.now() - n * 60000).toISOString(), archived: false, groupId: null, batchId: null, part: null, range: null, order: order('sentinel-2-c1-l2a'),
      deletedUntil: null, serverDeleted: false, lost: false, superseded: false,
      status: null, phase: 'failed', archive: null, bytes: null, resampled: null, failure: 'The source failed', failureKind: 'source_5xx', error: null, cancelling: false,
      retrying: false, retryRefused: false, retryError: null, deleting: false, expired: false, tiles: null, statistics: null, ...over,
    });
    const batch = 'b'.repeat(32);
    useProcessingStore.setState({
      batches: [{ id: batch, title: 'Batch of scenes', titleDefault: 'Batch of scenes', createdAt: new Date(Date.now() - 10 * 60000).toISOString(), archived: false, groupId: null, refused: [] }],
      jobs: [
        base(1, {}),
        base(2, { phase: 'dismissed' }),
        base(3, { phase: 'successful', expired: true, expires: new Date(Date.now() - day).toISOString() }),
        base(4, { failureKind: 'aoi_outside_inputs' }),
        base(5, { order: null }),
        base(6, { batchId: batch, part: 'S1' }),
        base(7, { batchId: batch, part: 'S2', phase: 'dismissed' }),
        base(8, { batchId: batch, part: 'S3', phase: 'successful', archive: 'result.zip' }),
      ].map((j) => ({ ...j, status: { jobID: j.jobID, status: j.phase === 'dismissed' ? 'dismissed' : j.phase === 'successful' ? 'successful' : 'failed', message: '', progress: 100, expires: j.expires } })),
    });
  });
  // Through the rail, as a user does; the page sets its own panel at the start, so this waits for that to settle.
  await page.waitForTimeout(1500);
  const rail = page.locator('nav[aria-label="Main"] button[aria-label^="Processing jobs"]');
  if ((await rail.getAttribute('aria-expanded')) !== 'true') await rail.click();
  await page.waitForSelector('.processing-manager .pm-row');

  // The row, the symbols and the layout.
  const symbols = () => page.evaluate(() => [...document.querySelectorAll('.pm-rows > .pm-row')].map((row) => [row.querySelector('.pm-title')?.textContent?.slice(0, 7), !!row.querySelector(':scope > .pm-line > button[aria-label^="Run again"], :scope > .pm-line > button[aria-label^="Retry failed parts"]')]));
  const found = await symbols();
  const want = [['Job 1 w', true], ['Job 2 w', true], ['Job 4 w', false], ['Job 5 w', false], ['Batch o', true]];
  if (JSON.stringify(found) !== JSON.stringify(want)) problems.push(`the symbols under "Active": ${JSON.stringify(found)}, not ${JSON.stringify(want)}`);
  const layout = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    return [...document.querySelectorAll('.pm-rows > .pm-row > .pm-line')].map((line) => ({ line: box(line), leaves: [...line.children].map((e) => ({ what: e.getAttribute('aria-label') ?? e.textContent?.slice(0, 12), ...box(e) })), scrolls: line.scrollWidth > line.clientWidth + 1 }));
  });
  for (const row of layout) {
    for (let i = 0; i < row.leaves.length; i++) {
      for (let j = i + 1; j < row.leaves.length; j++) if (overlap(row.leaves[i], row.leaves[j])) problems.push(`${row.leaves[i].what} overlaps ${row.leaves[j].what}`);
      if (row.leaves[i].x < row.line.x - 0.5 || row.leaves[i].x + row.leaves[i].width > row.line.x + row.line.width + 0.5) problems.push(`${row.leaves[i].what} leaves its row`);
    }
    if (row.scrolls) problems.push('a row scrolls sideways');
  }
  // The error toast of the map (its tiles cannot be fetched here) is wider than a narrow window in any case; the manager is what is checked.
  if ((await page.evaluate(() => { const m = document.querySelector('.processing-manager'); return m.scrollWidth > m.clientWidth + 1 || m.getBoundingClientRect().right > window.innerWidth + 1; }))) problems.push('the manager scrolls sideways or leaves the window');
  const theme_ = await page.evaluate(() => document.querySelector('.app')?.dataset.theme);
  if (theme_ !== THEMES[theme]) problems.push(`the app shows the theme ${theme_}, not ${THEMES[theme]}`);
  fs.mkdirSync(OUT, { recursive: true });
  const file = (name) => path.join(OUT, `${label.replace(/ /g, '_')}_${name}.png`);
  await page.locator('.processing-manager').screenshot({ path: file('manager') });

  // A double click on one job: one request, and the new job stands where the old one stood.
  const symbol = page.locator('.pm-rows > .pm-row').nth(0).locator(':scope > .pm-line > button[aria-label^="Run again"]');
  await symbol.dblclick({ delay: 10 }).catch(() => undefined);
  await page.waitForFunction(() => !document.querySelector('.pm-rows > .pm-row:nth-child(1) > .pm-line > button[aria-label^="Run again"]'));
  if (posted.length !== 1) problems.push(`${posted.length} requests for a double click, not 1`);
  const order = posted[0]?.inputs?.recipe;
  if (!order || order.inputs[0].dataset !== 'sentinel-2-c1-l2a' || order.recipe_version !== 1) problems.push('the request does not hold the kept order');
  const afterOne = await page.evaluate(() => [...document.querySelectorAll('.pm-rows > .pm-row')].map((row) => `${row.querySelector('.pm-title')?.textContent?.slice(0, 7)}:${row.querySelector('.pm-state')?.textContent}`));
  if (afterOne[0] !== 'Job 1 w:Waiting') problems.push(`the new job is not in the place of the old one: ${JSON.stringify(afterOne)}`);
  await page.locator('.processing-manager').screenshot({ path: file('after-one') });

  // The batch: only the failed and the cancelled part start again, and they stay in the batch.
  await page.locator('.pm-rows > .pm-row').last().locator(':scope > .pm-line > button[aria-label^="Retry failed parts"]').click();
  await page.waitForFunction(() => !document.querySelector('.pm-rows > .pm-row:last-child > .pm-line > button[aria-label^="Retry failed parts"]'));
  if (posted.length !== 3) problems.push(`${posted.length} requests after the batch, not 3`);
  await page.locator('.pm-rows > .pm-row').last().locator('.pm-chevron').click();
  const parts = await page.evaluate(() => [...document.querySelectorAll('.pm-parts > .pm-row')].map((row) => `${row.querySelector('.pm-title')?.textContent}:${row.querySelector('.pm-state')?.textContent}`));
  if (JSON.stringify(parts) !== JSON.stringify(['S1:Waiting', 'S2:Waiting', 'S3:Finished'])) problems.push(`the parts: ${JSON.stringify(parts)}`);
  await page.locator('.processing-manager').screenshot({ path: file('batch') });

  // "All" keeps the old jobs, set aside.
  await page.getByRole('button', { name: 'All', exact: true }).click();
  const tags = await page.evaluate(() => [...document.querySelectorAll('.pm-rows > .pm-row .pm-tag')].map((t) => t.textContent));
  if (!tags.includes('Superseded')) problems.push('"Superseded" is not shown under "All"');
  await page.getByRole('button', { name: 'Active', exact: true }).click();

  // The details: the title is renamed in place and the manager shows it.
  await page.locator('.pm-rows > .pm-row').nth(3).locator('.pm-open').click();
  await page.waitForSelector('[aria-label="Job"] .pm-title-text');
  await page.locator('[aria-label="Job"] .pm-title-text button').click();
  const field = page.locator('[aria-label="Job"] input.pm-rename');
  await field.fill('Renamed in the details');
  await page.screenshot({ path: file('rename-editing') });
  await field.press('Enter');
  const managerTitle = await page.evaluate(() => [...document.querySelectorAll('.pm-rows > .pm-row .pm-title')].map((e) => e.textContent));
  if (!managerTitle.includes('Renamed in the details')) problems.push(`the manager shows ${JSON.stringify(managerTitle)}`);
  await page.locator('[aria-label="Job"] .pm-title-text button').click();
  await page.locator('[aria-label="Job"] input.pm-rename').fill('Dropped');
  await page.locator('[aria-label="Job"] input.pm-rename').press('Escape');
  const kept = await page.locator('[aria-label="Job"] .pm-title-text').textContent();
  if (kept !== 'Renamed in the details') problems.push(`Escape kept "${kept}"`);
  await page.screenshot({ path: file('details') });

  await context.close();
  return { label, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) {
    if (process.env.ONLY && process.env.ONLY !== `${theme} ${viewport}`) continue;
    const result = await check(browser, { theme, viewport }).catch((error) => ({ label: `${theme} ${viewport}`, problems: [String(error).split('\n').slice(0, 6).join(' | ')] }));
    failed += result.problems.length > 0 ? 1 : 0;
    console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.label}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
  }
  await browser.close();
  console.log(failed ? `${failed} case(s) with problems` : 'all cases as expected');
  process.exit(failed ? 1 : 0);
})();
