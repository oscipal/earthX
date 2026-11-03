// The processing manager docked at the left (UI-03c, docked again on 3.11.2026 in #283), in a real browser:
//   1. Width: the panel is 340 px wide from 900 px (`--dock-width`, as wide as the other panels), flush from the top to the foot beside the
//      rail; under 900 px it covers the map from the rail to the right edge.
//   2. From 900 px every row of a job is one line: title with its pencil, date, then "＋" (finished jobs), "⇩" ("↻" in its place for a job
//      that failed) and "⋯"; the title, the pencil and the date stand at the same x in every row, the title is cut with "…" and holds its whole
//      text as a tooltip, a group head has its count and "n running" and its menu at the right. There is no column of the state: it stands in
//      the place of the date while a job runs ("70%").
//      The columns have titles over the list (Title, Until) at the x of the places of the row; the date is "8.11-23:48", no "until".
//      A running job has a line of two pixels at the top edge of its row, as wide as the row, with the progress in it.
//   3. Under 900 px (a column of about 260 px, symbols a finger high) the narrow form applies: status and date under the title.
//   4. Nothing scrolls sideways, nothing lies outside the panel, the symbols of a row do not overlap.
// In the light and the dark theme, at 1280 x 800, 1920 x 1080 and 360 x 740; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the jobs are made up here
//   node e2e/jobs-dock.cjs                  # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-jobs-dock');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { hd: { width: 1280, height: 800 }, full: { width: 1920, height: 1080 }, narrow: { width: 360, height: 740 } };
const RAIL = 48;
const overlap = (a, b) => a.x < b.right - 0.5 && b.x < a.right - 0.5 && a.y < b.bottom - 0.5 && b.y < a.bottom - 0.5;

async function check(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  fs.mkdirSync(OUT, { recursive: true });
  const size = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: size });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await page.evaluate(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    const order = { recipe_version: 1, inputs: [{ name: 'a', dataset: 'sentinel-2-c1-l2a', groups: [['S1']], assets: ['red'] }], steps: [], output: { kind: 'raster', format: 'cog', dtype: 'float32' } };
    const day = 86400000;
    const group = 'a'.repeat(32);
    const base = (n, over) => ({
      jobID: `Old${String(n).padStart(19, '0')}`, expires: new Date(Date.now() + 7 * day).toISOString(), title: `Job ${n} with a title that is rather long to read`, titleDefault: null,
      createdAt: new Date(Date.now() - n * 3600000).toISOString(), archived: false, groupId: null, batchId: null, part: null, range: null, order,
      deletedUntil: null, serverDeleted: false, lost: false, superseded: false, status: null, phase: 'failed', archive: null, bytes: null, resampled: null,
      failure: 'The source failed', failureKind: 'source_5xx', error: null, cancelling: false, retrying: false, retryRefused: false, retryError: null,
      deleting: false, expired: false, tiles: null, statistics: null, ...over,
    });
    const jobs = [
      base(1, { phase: 'active', groupId: group, status: { status: 'running', progress: 40 } }),
      base(2, { phase: 'successful', archive: 'result.zip', groupId: group, tiles: { href: '/results/r2/WebMercatorQuad/tilejson.json', width: 1000, gsd: 10 } }),
      base(3, { phase: 'active', status: { status: 'running', progress: 70 } }),
      base(4, { phase: 'successful', archive: 'result.zip', tiles: { href: '/results/r4/WebMercatorQuad/tilejson.json', width: 1000, gsd: 10 } }),
      base(5, {}),
    ].map((j) => ({ ...j, status: j.status ? { jobID: j.jobID, message: '', expires: j.expires, ...j.status } : { jobID: j.jobID, status: j.phase === 'successful' ? 'successful' : 'failed', message: '', progress: 100, expires: j.expires } }));
    useProcessingStore.setState({ groups: [{ id: group, name: 'Field 7' }], jobs });
  });
  const rail = page.locator('nav[aria-label="Main"] button[aria-label^="Processing jobs"]');
  if ((await rail.getAttribute('aria-expanded')) !== 'true') await rail.click();
  await page.waitForSelector('.processing-manager .pm-row');
  await page.waitForTimeout(500);
  const report = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height, right: r.right, bottom: r.bottom }; };
    const panel = document.querySelector('.processing-manager');
    const rows = [...panel.querySelectorAll('.pm-rows > .pm-row')].map((row) => {
      const open = row.querySelector('.pm-open');
      const line = row.querySelector('.pm-line');
      const symbol = (e) => ({ label: e.getAttribute('aria-label') ?? e.textContent, ...box(e) });
      return {
        state: box(row.querySelector('.pm-state')), stateText: row.querySelector('.pm-state').textContent, stateShown: getComputedStyle(row.querySelector('.pm-state')).position !== 'absolute',
        title: box(open.querySelector('.pm-title')), until: box(row.querySelector('.pm-until')), untilShown: getComputedStyle(row.querySelector('.pm-until')).display !== 'none',
        bar: row.querySelector(':scope > .pm-progress') ? box(row.querySelector(':scope > .pm-progress')) : null, rowBox: box(row),
        tooltip: open.title, shown: open.querySelector('.pm-title').textContent,
        edit: row.querySelector('.pm-edit') ? box(row.querySelector('.pm-edit')) : null,
        icons: [...line.querySelectorAll(':scope > .pm-icon')].map(box), line: box(line),
        tail: [...line.children].slice(-3).map(symbol),
      };
    });
    return {
      view: { width: window.innerWidth, height: window.innerHeight }, panel: box(panel), dock: box(document.querySelector('.dock')),
      scrolls: document.documentElement.scrollWidth > window.innerWidth || panel.querySelector('.pm-list').scrollWidth > panel.querySelector('.pm-list').clientWidth + 1,
      rows,
      columns: panel.querySelector('.pm-columns') ? { shown: getComputedStyle(panel.querySelector('.pm-columns')).display !== 'none', texts: [...panel.querySelector('.pm-columns').children].map((c) => c.textContent), title: box(panel.querySelector('.pm-col-title')), until: box(panel.querySelector('.pm-col-until')) } : null,
      dates: [...panel.querySelectorAll('.pm-row:not(.batch) .pm-until')].map((e) => e.textContent),
      opens: [...panel.querySelectorAll('.pm-row:not(.batch) .pm-open')].map(box),
      heads: [...panel.querySelectorAll('.pm-group-head')].map((h) => ({ count: h.querySelector('.pm-count')?.textContent ?? null, running: h.querySelector('.pm-state')?.textContent ?? null, menu: !!h.querySelector('.pm-menu') })),
    };
  });
  const narrow = size.width < 900;
  if (narrow) {
    if (Math.abs(report.dock.x - RAIL) > 1 || Math.abs(report.dock.right - report.view.width) > 1) problems.push(`the panel does not cover the map from the rail: ${JSON.stringify(report.dock)}`);
  } else if (Math.abs(report.dock.width - 340) > 1 || Math.abs(report.dock.x - RAIL) > 1 || report.dock.y > 1 || Math.abs(report.dock.bottom - report.view.height) > 1) {
    problems.push(`the panel is not 340 px wide and flush beside the rail: ${JSON.stringify(report.dock)}`);
  }
  if (report.scrolls) problems.push('the panel or the page scrolls sideways');
  if (report.rows.length !== 5) problems.push(`${report.rows.length} rows, not 5`);
  for (const row of report.rows) {
    if (narrow) {
      if (row.until.y < row.title.bottom - 0.5 || row.state.y < row.title.bottom - 0.5 || !row.stateShown) problems.push('status and date are not under the title in the narrow form');
    } else if (row.untilShown && (row.title.right > row.until.x + 0.5 || Math.abs(row.until.y - row.title.y) > 8)) {
      problems.push(`a row is not one line of title and date: ${JSON.stringify([row.title, row.until].map((b) => [Math.round(b.x), Math.round(b.y)]))}`);
    }
    if (!narrow && row.edit && row.untilShown && (row.edit.x < row.title.right - 0.5 || row.edit.right > row.until.x + 0.5)) problems.push('the pencil is not between the title and the date');
    if (!row.tooltip.startsWith('Job ')) problems.push(`the tooltip of the title is "${row.tooltip}", not its whole text`);
    for (let i = 0; i < row.icons.length; i++) {
      for (let j = i + 1; j < row.icons.length; j++) if (overlap(row.icons[i], row.icons[j])) problems.push('two symbols of a row overlap');
      if (row.icons[i].right > report.panel.right + 0.5) problems.push('a symbol leaves the panel');
    }
  }
  // "＋" before "⇩" before "⋯" in the rows of the finished jobs (the 2nd and the 5th: Job 4 and Job 2).
  for (const index of [1, 4]) {
    const tail = report.rows[index]?.tail.map((t) => (t.label.startsWith('Add to layers') ? '+' : t.label === 'Download (ZIP)' ? 'dl' : t.label === '⋯' ? 'menu' : t.label));
    if (JSON.stringify(tail) !== JSON.stringify(['+', 'dl', 'menu'])) problems.push(`the symbols of row ${index + 1} are ${JSON.stringify(tail)}, not ＋ ⇩ ⋯`);
  }
  if (!narrow) {
    for (const key of ['title', 'until']) {
      const xs = new Set(report.rows.filter((r) => key !== 'until' || r.untilShown).map((r) => Math.round(r[key].x)));
      if (xs.size !== 1) problems.push(`the ${key} stands in several columns: ${[...xs]}`);
    }
  }
  if (JSON.stringify(report.heads.map((h) => [h.count, h.running])) !== JSON.stringify([['3', '1 running'], ['2', '1 running']])) problems.push(`the heads say ${JSON.stringify(report.heads)}`);
  if (!report.columns) problems.push('no titles of the columns');
  else if (narrow) {
    if (report.columns.shown) problems.push('the titles of the columns show in the narrow form');
  } else {
    if (JSON.stringify(report.columns.texts) !== JSON.stringify(['Title', 'Until'])) problems.push(`the columns are ${JSON.stringify(report.columns.texts)}`);
    if (Math.abs(report.columns.title.x - report.opens[0].x) > 1) problems.push(`the title "Title" is at ${report.columns.title.x}, the title of a row at ${report.opens[0].x}`);
    if (Math.abs(report.columns.until.right - report.rows[1].until.right) > 1) problems.push('the title "Until" is not over the date');
  }
  // Running jobs (Job 3 and Job 1): a line of two pixels at the top edge of the row, and the state where the date would stand; nothing like it on the others.
  for (const index of [0, 3]) {
    const row = report.rows[index];
    if (!row.bar) problems.push(`row ${index + 1} has no line of progress`);
    else if (row.bar.height > 3 || Math.abs(row.bar.y - row.rowBox.y) > 1 || Math.abs(row.bar.width - row.rowBox.width) > 1) problems.push(`the line of progress of row ${index + 1} is ${JSON.stringify(row.bar)} in ${JSON.stringify(row.rowBox)}`);
    if (!narrow && (!row.stateShown || !/^\d+%$/.test(row.stateText) || row.untilShown || Math.abs(row.state.right - report.rows[1].until.right) > 1)) problems.push(`row ${index + 1} does not show its state in the place of the date: ${row.stateText}`);
  }
  for (const index of [1, 2, 4]) if (report.rows[index].bar) problems.push(`row ${index + 1} has a line of progress without running`);
  // "Run again" (Job 5) stands where the finished job has its download.
  {
    const failed = report.rows[2].tail[1];
    const done = report.rows[1].tail[1];
    if (!failed.label.startsWith('Run again')) problems.push(`the failed job has "${failed.label}" in the place of the download`);
    else if (Math.abs(failed.x - done.x) > 1) problems.push(`"Run again" is at ${failed.x}, the download at ${done.x}`);
  }
  for (const date of report.dates) if (!/^\d{1,2}\.\d{1,2}-\d{2}:\d{2}$/.test(date)) problems.push(`the date reads "${date}", not 8.11-23:48`);
  if (!report.heads[1].menu) problems.push('the head of a group has no menu');
  await page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
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
  console.log('the jobs are docked, 340 px wide, one line with pencil, ＋, ⇩ and ⋯ from 900 px, the narrow form under it');
})();
