// The "Settings" menu at the bottom of the rail (UI-04 part 4, Otto, 4.11.2026), in a real browser:
//   1. The symbol is the last one of the rail, at its bottom edge, 20 px, with three rings; its tooltip "Settings" shows in the simple step.
//   2. The menu opens beside the rail, entirely inside the window (8 px margin), with the groups Basemap, Overlays, Projection, Appearance
//      and Tooltips; "Relief" is an overlay and no basemap.
//   3. Light, Dark and System change the theme at once; System follows the colour scheme of the system while the page is open.
//   4. Tooltips: in the simple step a tip of the other step does not show, the reason of a locked button does; in the advanced one all show.
//   5. The choices are kept per browser (a reload), and a browser with a locked storage still takes them for the visit.
//   6. A browser that kept the basemap "relief" opens with the default basemap and the overlay Relief.
//   7. The full text of a cut-off text shows only while it is cut (measured in the layout of the page), in both steps.
//   8. The old buttons "Basemap" and Light/Dark at the top right are gone.
// In the light and the dark theme, at 1280 x 800 and 360 x 740; a screenshot per case (not in the repository).
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/settings-menu.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-settings-menu');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const MARGIN = 8;

let checks = 0;
const problems = [];
const expect = (what, ok, detail = '') => {
  checks += 1;
  if (!ok) problems.push(`${what}${detail ? `: ${detail}` : ''}`);
};

async function open(browser, { viewport, init = [], theme }) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  if (theme) await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  for (const script of init) await context.addInitScript(script);
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('nav[aria-label="Main"] button');
  await page.waitForTimeout(500);
  // The control menu covers the map on a narrow window and the made-up server has no datasets: the panel is closed with its symbol, and the
  // message that says so with its x, as it lies over the buttons at the top right on a narrow window.
  const first = page.locator('nav[aria-label="Main"] button').first();
  if ((await first.getAttribute('aria-expanded')) === 'true') await first.click();
  const message = page.locator('.status .close-x');
  if (await message.count()) await message.first().click();
  return { context, page, errors };
}

const store = (page, fn, arg) => page.evaluate(async ([source, arg]) => (new Function('s', 'arg', `return (${source})(s, arg)`))((await import('/src/store.ts')).useAppStore, arg), [fn.toString(), arg]);
const box = (locator) => locator.evaluate((e) => e.getBoundingClientRect().toJSON());
const settings = (page) => page.locator('nav[aria-label="Main"] button[aria-label="Settings"]');
const menu = (page) => page.getByRole('menu', { name: 'Settings' });

async function layout(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const win = VIEWPORTS[viewport];
  const { context, page, errors } = await open(browser, { viewport, theme });
  fs.mkdirSync(OUT, { recursive: true });

  // 1. The symbol.
  const buttons = page.locator('nav[aria-label="Main"] button');
  const count = await buttons.count();
  expect(`${name}: five symbols in the rail`, count === 5, String(count));
  expect(`${name}: Settings is the last one`, (await buttons.nth(count - 1).getAttribute('aria-label')) === 'Settings');
  const rail = await box(page.locator('nav[aria-label="Main"]'));
  const symbol = await box(settings(page));
  const previous = await box(buttons.nth(count - 2));
  expect(`${name}: it stands at the bottom edge of the rail`, rail.bottom - symbol.bottom < 20 && symbol.y > previous.bottom, JSON.stringify({ rail, symbol, previous }));
  expect(`${name}: it stands in the middle of the rail`, Math.abs(symbol.x + symbol.width / 2 - (rail.x + rail.width / 2)) < 1);
  const icon = await settings(page).evaluate((e) => ({ w: e.querySelector('svg').getAttribute('width'), circles: e.querySelectorAll('svg circle').length, fill: getComputedStyle(e.querySelector('svg')).fill }));
  expect(`${name}: the icon is 20 px with three rings and no fill`, icon.w === '20' && icon.circles === 3 && icon.fill === 'none', JSON.stringify(icon));
  await settings(page).hover();
  await page.locator('.tip-layer').waitFor({ timeout: 2000 });
  expect(`${name}: the tooltip is "Settings", in the simple step`, (await page.locator('.tip-layer').textContent()) === 'Settings');
  await page.mouse.move(win.width / 2, win.height / 2);

  // 8. The old buttons.
  const top = await page.locator('.top-right button').allTextContents();
  expect(`${name}: only "Zoom to selection" at the top right`, top.length === 1 && top[0].includes('Zoom to selection'), JSON.stringify(top));

  // 2. The menu.
  await settings(page).click();
  await menu(page).waitFor();
  await page.waitForTimeout(150);
  const m = await box(menu(page));
  expect(`${name}: the menu lies right of the rail`, m.x >= rail.right - 0.5, JSON.stringify({ m, rail }));
  expect(`${name}: the menu lies inside the window`, m.x >= MARGIN - 0.5 && m.y >= MARGIN - 0.5 && m.right <= win.width - MARGIN + 0.5 && m.bottom <= win.height - MARGIN + 0.5, JSON.stringify(m));
  expect(`${name}: the menu stands at the symbol, its bottom on the bottom of it`, Math.abs(m.bottom - symbol.bottom) < 4 || m.y < MARGIN + 1, JSON.stringify({ m, symbol }));
  const groups = await menu(page).getByRole('group').evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')));
  expect(`${name}: the five groups`, JSON.stringify(groups) === JSON.stringify(['Basemap', 'Overlays', 'Projection', 'Appearance', 'Tooltips']), JSON.stringify(groups));
  const basemaps = await menu(page).getByRole('group', { name: 'Basemap' }).getByRole('menuitemradio').allTextContents();
  expect(`${name}: Relief is no basemap`, !basemaps.includes('Relief') && basemaps.length === 4, JSON.stringify(basemaps));
  const overlays = await menu(page).getByRole('group', { name: 'Overlays' }).getByRole('menuitemcheckbox').allTextContents();
  expect(`${name}: Relief is an overlay`, overlays.includes('Relief'), JSON.stringify(overlays));
  // Touch-sized rows under 900 px do not all fit a phone window: the menu then scrolls inside the window (never sideways) and every entry is reachable.
  const fit = await menu(page).evaluate((e) => ({ sideways: e.scrollWidth > e.clientWidth + 1, taller: e.scrollHeight > e.clientHeight + 1, overflowY: getComputedStyle(e).overflowY }));
  expect(`${name}: the menu does not scroll sideways, and scrolls up and down only where it is taller than the window`, !fit.sideways && (!fit.taller || fit.overflowY === 'auto'), JSON.stringify(fit));
  await page.screenshot({ path: path.join(OUT, `menu ${name}.png`) });

  // 3. The appearance.
  const theme_ = () => page.locator('.app').getAttribute('data-theme');
  await menu(page).getByRole('menuitemradio', { name: 'Light' }).click();
  expect(`${name}: Light`, (await theme_()) === 'normal' && (await page.evaluate(() => localStorage.getItem('earthx.theme'))) === 'normal');
  await page.screenshot({ path: path.join(OUT, `menu light ${viewport} (chosen in ${theme}).png`) });
  await menu(page).getByRole('menuitemradio', { name: 'Dark' }).click();
  expect(`${name}: Dark`, (await theme_()) === 'tech' && (await page.evaluate(() => localStorage.getItem('earthx.theme'))) === 'tech');
  await menu(page).getByRole('menuitemradio', { name: 'System' }).click();
  await page.emulateMedia({ colorScheme: 'light' });
  await page.waitForTimeout(150);
  expect(`${name}: System follows a light system`, (await theme_()) === 'normal' && (await page.evaluate(() => localStorage.getItem('earthx.theme'))) === 'system');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForTimeout(150);
  expect(`${name}: System follows the system when it turns dark while the page is open`, (await theme_()) === 'tech');
  const bg = await page.locator('.app').evaluate((e) => getComputedStyle(e).backgroundColor);
  expect(`${name}: the page is dark with a dark system`, /^rgb\((\d+), (\d+), (\d+)\)$/.test(bg) && bg.match(/\d+/g).map(Number).every((v) => v < 60), bg);
  await menu(page).getByRole('menuitemradio', { name: 'Dark' }).click();
  await page.emulateMedia({ colorScheme: 'light' });
  await page.waitForTimeout(150);
  expect(`${name}: Dark does not follow the system`, (await theme_()) === 'tech');
  await menu(page).getByRole('menuitemradio', { name: THEMES[theme] === 'normal' ? 'Light' : 'Dark' }).click();
  await page.emulateMedia({ colorScheme: null });

  // The overlay "Relief" and the projection keep the basemap.
  const before = await store(page, (s) => s.getState().basemap);
  await menu(page).getByRole('menuitemcheckbox', { name: 'Relief' }).click();
  const after = await store(page, (s) => ({ basemap: s.getState().basemap, relief: s.getState().overlays.relief }));
  expect(`${name}: the overlay Relief leaves the basemap`, after.basemap === before && after.relief === true, JSON.stringify(after));
  await menu(page).getByRole('menuitemcheckbox', { name: 'Relief' }).click();

  // 4. The steps of the tooltips.
  await page.mouse.click(win.width - 10, win.height - 10); // beside the menu: it closes
  await menu(page).waitFor({ state: 'detached' });
  await page.waitForTimeout(200);
  const zoom = page.getByRole('button', { name: 'Zoom to selection' });
  await zoom.hover({ force: true });
  await page.locator('.tip-layer').waitFor({ timeout: 2000 });
  expect(`${name}: the locked "Zoom to selection" says why in the simple step`, (await page.locator('.tip-layer').textContent()) === 'Nothing to zoom to: draw an AOI, open an image or show a layer', await page.locator('.tip-layer').textContent());
  await page.mouse.move(win.width / 2, win.height / 2);
  await page.waitForTimeout(100);
  // An AOI and a layer: "Zoom to selection" is free, and its tip is of the other step.
  await store(page, (s) => s.setState({ aoi: { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] } }));
  await page.waitForTimeout(100);
  await zoom.hover();
  await page.waitForTimeout(250);
  expect(`${name}: the tip of the free button is held back in the simple step`, (await page.locator('.tip-layer').count()) === 0);
  await page.mouse.move(win.width / 2, win.height / 2);
  await settings(page).click();
  await menu(page).getByRole('menuitemradio', { name: 'Advanced' }).click();
  expect(`${name}: Advanced is kept`, (await page.evaluate(() => localStorage.getItem('earthx.tooltips'))) === 'advanced');
  await page.mouse.click(win.width - 10, win.height - 10);
  await zoom.hover();
  await page.locator('.tip-layer').waitFor({ timeout: 2000 });
  expect(`${name}: the same tip shows in the advanced step`, /^Zoom the map to fit/.test((await page.locator('.tip-layer').textContent()) ?? ''));
  await page.mouse.move(win.width / 2, win.height / 2);
  await settings(page).click();
  await menu(page).getByRole('menuitemradio', { name: 'Simple' }).click();
  expect(`${name}: Simple is kept`, (await page.evaluate(() => localStorage.getItem('earthx.tooltips'))) === 'simple');
  await page.mouse.click(win.width - 10, win.height - 10);

  // 7. The full text of a cut-off text.
  await page.evaluate(() => {
    const host = document.querySelector('.app');
    const make = (id, width, top) => {
      const el = document.createElement('span');
      el.id = id;
      el.textContent = 'A rather long title of a job that does not fit';
      el.setAttribute('data-tip', 'A rather long title of a job that does not fit');
      el.setAttribute('data-tip-cut', '');
      Object.assign(el.style, { position: 'fixed', top: `${top}px`, left: '80px', zIndex: '50', display: 'block', width: `${width}px`, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', background: 'var(--panel-bg)', color: 'var(--text)' });
      host.append(el);
    };
    make('cut', 90, 120);
    make('whole', 600, 170);
  });
  for (const level of ['simple', 'advanced']) {
    await store(page, (s, l) => s.getState().setTipLevel(l), level);
    await page.locator('#cut').hover();
    await page.waitForTimeout(200);
    expect(`${name}: a cut text shows its full text (${level})`, (await page.locator('.tip-layer').count()) === 1 && (await page.locator('.tip-layer').textContent()) === 'A rather long title of a job that does not fit');
    await page.mouse.move(win.width / 2, win.height - 40);
    await page.locator('#whole').hover();
    await page.waitForTimeout(200);
    expect(`${name}: a text that fits shows nothing (${level})`, (await page.locator('.tip-layer').count()) === 0);
    await page.mouse.move(win.width / 2, win.height - 40);
  }
  await page.evaluate(() => document.querySelectorAll('#cut, #whole').forEach((e) => e.remove()));
  await store(page, (s) => s.getState().setTipLevel('simple'));

  expect(`${name}: no error on the page`, errors.length === 0, errors.join(' | '));
  await context.close();
}

async function kept(browser, viewport) {
  // 5. Kept per browser: a reload keeps the choices.
  const { context, page, errors } = await open(browser, { viewport });
  await settings(page).click();
  await menu(page).getByRole('menuitemradio', { name: 'Light' }).click();
  await menu(page).getByRole('menuitemradio', { name: 'Outlines' }).click();
  await menu(page).getByRole('menuitemradio', { name: 'Globe' }).click();
  await menu(page).getByRole('menuitemcheckbox', { name: 'Graticule' }).click();
  await menu(page).getByRole('menuitemradio', { name: 'Advanced' }).click();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('nav[aria-label="Main"] button');
  const state = await store(page, (s) => ({ appearance: s.getState().appearance, theme: s.getState().theme, basemap: s.getState().basemap, projection: s.getState().projection, graticule: s.getState().overlays.graticule, tips: s.getState().tipLevel }));
  expect(`kept ${viewport}: after a reload`, JSON.stringify(state) === JSON.stringify({ appearance: 'light', theme: 'normal', basemap: 'outlines', projection: 'globe', graticule: true, tips: 'advanced' }), JSON.stringify(state));
  expect(`kept ${viewport}: the page is light`, (await page.locator('.app').getAttribute('data-theme')) === 'normal');
  await settings(page).click();
  const checked = await menu(page).getByRole('menuitemradio', { checked: true }).allTextContents();
  expect(`kept ${viewport}: the menu marks what was chosen`, JSON.stringify(checked) === JSON.stringify(['Outlines', 'Globe', 'Light', 'Advanced']), JSON.stringify(checked));
  expect(`kept ${viewport}: no error on the page`, errors.length === 0, errors.join(' | '));
  await context.close();

  // A locked storage: every access throws. The page opens and takes the choices for the visit.
  const locked = await open(browser, {
    viewport,
    init: [() => {
      const deny = () => { throw new DOMException('denied', 'SecurityError'); };
      Object.defineProperty(window, 'localStorage', { get: deny, configurable: true });
    }],
  });
  await locked.page.waitForSelector('nav[aria-label="Main"] button');
  await settings(locked.page).click();
  await menu(locked.page).getByRole('menuitemradio', { name: 'Light' }).click();
  await menu(locked.page).getByRole('menuitemradio', { name: 'Outlines' }).click();
  await menu(locked.page).getByRole('menuitemradio', { name: 'Advanced' }).click();
  const lockedState = await store(locked.page, (s) => ({ theme: s.getState().theme, basemap: s.getState().basemap, tips: s.getState().tipLevel }));
  expect(`locked storage ${viewport}: the choices hold for the visit`, JSON.stringify(lockedState) === JSON.stringify({ theme: 'normal', basemap: 'outlines', tips: 'advanced' }), JSON.stringify(lockedState));
  expect(`locked storage ${viewport}: no error on the page`, locked.errors.length === 0, locked.errors.join(' | '));
  await locked.context.close();
}

async function relief(browser) {
  // 6. A browser that kept the basemap "relief".
  const { context, page, errors } = await open(browser, { viewport: 'wide', init: [() => {
    if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1'); localStorage.setItem('earthx.basemap', 'relief'); }
  }] });
  const state = await store(page, (s) => ({ basemap: s.getState().basemap, relief: s.getState().overlays.relief }));
  expect('old Relief basemap: opens with the default basemap and the overlay', state.basemap === 'satellite' && state.relief === true, JSON.stringify(state));
  const stored = await page.evaluate(() => [localStorage.getItem('earthx.basemap'), localStorage.getItem('earthx.overlays')]);
  expect('old Relief basemap: the entry is rewritten once', stored[0] === 'satellite' && JSON.parse(stored[1]).relief === true, JSON.stringify(stored));
  await settings(page).click();
  await menu(page).getByRole('menuitemcheckbox', { name: 'Relief' }).click();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('nav[aria-label="Main"] button');
  const off = await store(page, (s) => s.getState().overlays.relief);
  expect('old Relief basemap: switched off, it stays off after a reload', off === false);
  expect('old Relief basemap: no error on the page', errors.length === 0, errors.join(' | '));
  await context.close();
}

(async () => {
  const browser = await chromium.launch();
  try {
    for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) await layout(browser, theme, viewport);
    await kept(browser, 'wide');
    await kept(browser, 'narrow');
    await relief(browser);
  } finally {
    await browser.close();
  }
  if (problems.length) {
    console.log(`${problems.length} of ${checks} checks failed:`);
    for (const p of problems) console.log(`  - ${p}`);
    process.exit(1);
  }
  console.log(`ok: ${checks} checks (screenshots in ${OUT})`);
})().catch((e) => {
  console.error(e);
  process.exit(1);
});
