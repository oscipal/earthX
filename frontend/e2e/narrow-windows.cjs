// Narrow windows (UI-04 part 6, backlog item 58): in a real browser, at 320, 360 and 1280 px, in the light and the dark theme,
//  1. the AOI tools of the control panel do not reach beyond their box (no horizontal scroll in the panel),
//  2. a message of the status bar lies inside the window, under the buttons at the top right, and above an open panel,
//  3. a message of the status bar can be read and closed with a panel of the rail open (control panel, layers, search results, jobs,
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
  if (FAULT) {
    // The old rules, put back after the load: the status at the top, under the dock.
    await page.addInitScript(() => {
      document.addEventListener('DOMContentLoaded', () => {
        const style = document.createElement('style');
        style.textContent = '@media (max-width: 899px) { .overlay.status { top: 16px !important; z-index: 10 !important; } }';
        document.head.append(style);
      });
    });
  }
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
      const { name, problems } = await check(browser, { theme, viewport });
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
      for (const p of problems) console.log(`       ${p}`);
      if (problems.length > 0) failed = true;
    }
  }
  await browser.close();
  console.log(`screenshots: ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
