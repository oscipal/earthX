// The panel "Settings" at the bottom of the rail (UI-04 part 4, Otto, 4.11.2026), in a real browser:
//   1. The symbol is the last one of the rail, at its bottom edge, 20 px, with three rings; its tooltip "Settings" shows in the simple step.
//   2. It opens a panel beside the rail like the other panels: the same width, from the top to the foot, a head with the title and no x (a panel
//      of the rail is opened and closed with its symbol, not with Esc); under 900 px it covers the map from the rail to the right edge, as they do. Sections Basemap,
//      Overlays, Projection, Appearance and Tooltips; "Relief" is an overlay and no basemap.
//   3. Every choice is a segment button (the chosen one filled), all of one size (the width of one of four columns, the height of a control), an
//      overlay is a button of that form that is pressed while it is on, "Simple" and "Advanced" are two boxes as well; no list of ticks, no switch.
//   4. Light, Dark and System change the theme at once; System follows the colour scheme of the system while the page is open.
//   5. Tooltips: in the simple step a tip of the other step does not show, the reason of a locked button does; with "Advanced" all show; and a tip
//      that is drawn goes when the step is put back to "Simple" (it used to stay).
//   6. The choices are kept per browser (a reload), and a browser with a locked storage still takes them for the visit.
//   7. A browser that kept the basemap "relief" opens with the default basemap and the overlay Relief.
//   8. The full text of a cut-off text shows only while it is cut (measured in the layout of the page), in both steps.
//   9. The old buttons "Basemap" and Light/Dark at the top right are gone.
// In the light and the dark theme, at 1280 x 800 and 360 x 740; a screenshot per case (not in the repository).
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/settings-panel.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-settings-panel');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

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
const panel = (page) => page.locator('.settings-panel');
const seg = (page, group, name) => panel(page).getByRole('group', { name: group }).getByRole('button', { name, exact: true });
// A panel of the rail is closed with its symbol (Otto, 4.11.2026).
const closePanel = async (page) => { if ((await settings(page).getAttribute('aria-expanded')) === 'true') await settings(page).click(); };
// The panel is open: the symbol opens it, and the panel that was open before gives way.
const openPanel = async (page) => {
  if ((await settings(page).getAttribute('aria-expanded')) !== 'true') await settings(page).click();
  await panel(page).waitFor();
  await page.waitForTimeout(150);
};

async function layout(browser, theme, viewport) {
  const name = `${theme} ${viewport}`;
  const win = VIEWPORTS[viewport];
  const { context, page, errors } = await open(browser, { viewport, theme });
  fs.mkdirSync(OUT, { recursive: true });

  // 1. The symbol.
  const buttons = page.locator('nav[aria-label="Main"] button');
  const count = await buttons.count();
  expect(`${name}: six symbols in the rail (the Data catalogue second, UI-05)`, count === 6, String(count));
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

  // 9. The old buttons.
  const top = await page.locator('.top-right button').allTextContents();
  expect(`${name}: only "Zoom to selection" at the top right`, top.length === 1 && top[0].includes('Zoom to selection'), JSON.stringify(top));

  // 2. The panel, like the others. The widths of the others are measured with the layers panel.
  await page.locator('#rail-layers').click();
  await page.locator('.layer-manager').waitFor();
  const layers = await box(page.locator('.dock'));
  await openPanel(page);
  const dock = await box(page.locator('.dock'));
  const p = await box(panel(page));
  expect(`${name}: the panel stands at the rail, from the top to the foot`, Math.abs(p.x - rail.right) < 1 && p.y < 1 && Math.abs(p.bottom - win.height) < 1, JSON.stringify({ p, rail }));
  expect(`${name}: it is as wide as the other panels`, Math.abs(p.width - layers.width) < 1 && Math.abs(dock.width - layers.width) < 1, JSON.stringify({ p: p.width, layers: layers.width }));
  if (win.width < 900) expect(`${name}: under 900 px it covers the map to the right edge, as the others do`, Math.abs(p.right - win.width) < 1, JSON.stringify(p));
  else expect(`${name}: from 900 px it is 340 px wide`, Math.abs(p.width - 340) < 1, String(p.width));
  const head = await panel(page).locator('.results-head').evaluate((e) => ({ title: e.querySelector('h2')?.textContent, buttons: e.querySelectorAll('button').length }));
  expect(`${name}: the head has the title and no x`, head.title === 'Settings' && head.buttons === 0 && (await panel(page).locator('.close-x').count()) === 0, JSON.stringify(head));
  const others = [];
  // The panels of the dock; the Data catalogue (second symbol) is a window with its own red x (UI-05).
  for (const id of ['controls', 'layers', 'jobs']) {
    await page.locator(`#rail-${id}`).click();
    others.push(await page.locator('.dock .close-x').count());
  }
  expect(`${name}: no panel of the rail has an x in its head`, others.every((n) => n === 0), JSON.stringify(others));
  await openPanel(page);
  const sections = await panel(page).locator('.settings-heading').allTextContents();
  expect(`${name}: the five sections`, JSON.stringify(sections) === JSON.stringify(['Basemap', 'Overlays', 'Projection', 'Appearance', 'Tooltips']), JSON.stringify(sections));
  const basemaps = await panel(page).getByRole('group', { name: 'Basemap' }).getByRole('button').allTextContents();
  expect(`${name}: Relief is no basemap`, !basemaps.includes('Relief') && basemaps.length === 4, JSON.stringify(basemaps));
  const overlays = await panel(page).getByRole('group', { name: 'Overlays' }).getByRole('button').allTextContents();
  expect(`${name}: Relief is an overlay`, overlays.includes('Relief'), JSON.stringify(overlays));
  const inside = await panel(page).evaluate((e) => { const r = e.getBoundingClientRect(); return [...e.querySelectorAll('button, [role="switch"]')].every((b) => { const q = b.getBoundingClientRect(); return q.left >= r.left - 0.5 && q.right <= r.right + 0.5 && q.width > 0; }); });
  expect(`${name}: every button lies inside the panel`, inside);
  const sideways = await panel(page).locator('.settings-body').evaluate((e) => e.scrollWidth > e.clientWidth + 1);
  expect(`${name}: nothing scrolls sideways`, !sideways);

  // 3. Buttons, not ticks.
  expect(`${name}: no tick, no menu, no checkbox`, (await panel(page).locator('[role^="menuitem"], [role="menu"], .menu-tick, input[type="checkbox"], input[type="radio"]').count()) === 0);
  const segs = await panel(page).locator('.settings-row button').evaluateAll((els) => els.map((e) => [e.className, e.hasAttribute('aria-pressed')]));
  expect(`${name}: every choice is a .btn.seg with a pressed state`, segs.length === 14 && segs.every(([c, p]) => c === 'btn seg' && p), JSON.stringify(segs));
  const fills = await panel(page).evaluate((e) => {
    const pick = (el) => ({ bg: getComputedStyle(el).backgroundColor, color: getComputedStyle(el).color });
    const on = e.querySelector('[aria-label="Basemap"] [aria-pressed="true"]');
    const off = e.querySelector('[aria-label="Basemap"] [aria-pressed="false"]');
    const accent = getComputedStyle(e.closest('.app')).getPropertyValue('--accent').trim();
    const probe = document.createElement('i'); probe.style.color = accent; document.body.append(probe);
    const accentRgb = getComputedStyle(probe).color; probe.remove();
    return { on: pick(on), off: pick(off), accentRgb };
  });
  expect(`${name}: the chosen one is filled with the accent, the others are not`, fills.on.bg === fills.accentRgb && fills.off.bg !== fills.accentRgb, JSON.stringify(fills));
  await page.screenshot({ path: path.join(OUT, `panel ${name}.png`) });

  // Esc closes nothing; the symbol closes it, and opens it again.
  await page.keyboard.press('Escape');
  expect(`${name}: Esc leaves the panel open`, (await panel(page).count()) === 1 && (await panel(page).isVisible()));
  await settings(page).click();
  expect(`${name}: a second click on the symbol closes the panel`, !(await panel(page).isVisible()));
  await settings(page).click();
  expect(`${name}: the symbol opens it`, await panel(page).isVisible());
  await openPanel(page);

  // 4. The appearance. The panel stays open while a choice is made.
  const theme_ = () => page.locator('.app').getAttribute('data-theme');
  const stored = () => page.evaluate(() => localStorage.getItem('earthx.theme'));
  await seg(page, 'Appearance', 'Light').click();
  expect(`${name}: Light`, (await theme_()) === 'normal' && (await stored()) === 'normal');
  expect(`${name}: the panel stays open after a choice`, await panel(page).isVisible());
  await page.screenshot({ path: path.join(OUT, `panel light ${viewport} (chosen in ${theme}).png`) });
  await seg(page, 'Appearance', 'Dark').click();
  expect(`${name}: Dark`, (await theme_()) === 'tech' && (await stored()) === 'tech');
  await seg(page, 'Appearance', 'System').click();
  await page.emulateMedia({ colorScheme: 'light' });
  await page.waitForTimeout(150);
  expect(`${name}: System follows a light system`, (await theme_()) === 'normal' && (await stored()) === 'system');
  await page.emulateMedia({ colorScheme: 'dark' });
  await page.waitForTimeout(150);
  expect(`${name}: System follows the system when it turns dark while the page is open`, (await theme_()) === 'tech');
  await seg(page, 'Appearance', 'Dark').click();
  await page.emulateMedia({ colorScheme: 'light' });
  await page.waitForTimeout(150);
  expect(`${name}: Dark does not follow the system`, (await theme_()) === 'tech');
  await seg(page, 'Appearance', THEMES[theme] === 'normal' ? 'Light' : 'Dark').click();
  await page.emulateMedia({ colorScheme: null });

  // The overlay "Relief" is a button that is pressed while it is on, and it leaves the basemap.
  const before = await store(page, (s) => s.getState().basemap);
  await seg(page, 'Overlays', 'Relief').click();
  const after = await store(page, (s) => ({ basemap: s.getState().basemap, relief: s.getState().overlays.relief }));
  expect(`${name}: the overlay Relief leaves the basemap`, after.basemap === before && after.relief === true, JSON.stringify(after));
  expect(`${name}: the button of an overlay that is on is pressed`, (await seg(page, 'Overlays', 'Relief').getAttribute('aria-pressed')) === 'true');
  await seg(page, 'Overlays', 'Relief').click();
  expect(`${name}: and not pressed when it is off`, (await seg(page, 'Overlays', 'Relief').getAttribute('aria-pressed')) === 'false');

  // 3 (sizes). Every box is as wide as one of four columns and as high as every other, and its text fits in it.
  const sizes = await panel(page).locator('.settings-row button').evaluateAll((els) => els.map((e) => { const r = e.getBoundingClientRect(); return { w: Math.round(r.width * 10) / 10, h: Math.round(r.height * 10) / 10, cut: e.scrollWidth > e.clientWidth + 1 }; }));
  expect(`${name}: all the boxes are of one size`, new Set(sizes.map((x) => x.w)).size === 1 && new Set(sizes.map((x) => x.h)).size === 1, JSON.stringify([...new Set(sizes.map((x) => `${x.w}x${x.h}`))]));
  expect(`${name}: the text of no box is cut off`, sizes.every((x) => !x.cut), JSON.stringify(sizes.filter((x) => x.cut)));
  const tipsRow = await panel(page).getByRole('group', { name: 'Tooltips' }).getByRole('button').allTextContents();
  expect(`${name}: Simple and Advanced are two boxes`, JSON.stringify(tipsRow) === JSON.stringify(['Simple', 'Advanced']) && (await panel(page).locator('[role="switch"]').count()) === 0, JSON.stringify(tipsRow));
  expect(`${name}: Simple is chosen`, (await seg(page, 'Tooltips', 'Simple').getAttribute('aria-pressed')) === 'true');

  // 5. The steps of the tooltips. The panel is closed to reach the map.
  await closePanel(page);
  const message = page.locator('.status .close-x');
  if (await message.count()) await message.first().click();
  await page.waitForTimeout(200);
  const zoom = page.getByRole('button', { name: 'Zoom to selection' });
  await zoom.hover({ force: true });
  await page.locator('.tip-layer').waitFor({ timeout: 2000 });
  expect(`${name}: the locked "Zoom to selection" says why in the simple step`, (await page.locator('.tip-layer').textContent()) === 'Nothing to zoom to: draw an AOI, open an image or show a layer', await page.locator('.tip-layer').textContent());
  await page.mouse.move(win.width / 2, win.height / 2);
  await page.waitForTimeout(100);
  await store(page, (s) => s.setState({ aoi: { type: 'Polygon', coordinates: [[[10, 47], [11, 47], [11, 48], [10, 48], [10, 47]]] } }));
  await page.waitForTimeout(100);
  await zoom.hover();
  await page.waitForTimeout(250);
  expect(`${name}: the tip of the free button is held back in the simple step`, (await page.locator('.tip-layer').count()) === 0);
  await page.mouse.move(win.width / 2, win.height / 2);
  await openPanel(page);
  await seg(page, 'Tooltips', 'Advanced').click();
  expect(`${name}: Advanced is chosen and kept`, (await seg(page, 'Tooltips', 'Advanced').getAttribute('aria-pressed')) === 'true' && (await page.evaluate(() => localStorage.getItem('earthx.tooltips'))) === 'advanced');
  await page.screenshot({ path: path.join(OUT, `panel advanced ${name}.png`) });
  await closePanel(page);
  await zoom.hover();
  // On a narrow window the red x of the panel lay where the button is now: the pointer is moved off, as a browser tells of a hover only on a move.
  await page.mouse.move(win.width / 2, win.height / 2);
  await zoom.hover();
  await page.locator('.tip-layer').waitFor({ timeout: 2000 });
  expect(`${name}: the same tip shows with Advanced`, /^Zoom the map to fit/.test((await page.locator('.tip-layer').textContent()) ?? ''));
  await page.mouse.move(win.width / 2, win.height / 2);
  await openPanel(page);
  // A tip that is drawn goes when the step is put back to "Simple" and the pointer leaves (Otto, 4.11.2026: it stayed).
  await seg(page, 'Tooltips', 'Advanced').hover();
  await page.locator('.tip-layer').waitFor({ timeout: 2000 });
  await seg(page, 'Tooltips', 'Simple').click();
  await page.mouse.move(win.width - 40, win.height / 2);
  await page.waitForTimeout(300);
  expect(`${name}: the tip is gone after "Simple" and a move of the pointer`, (await page.locator('.tip-layer').count()) === 0);
  await seg(page, 'Tooltips', 'Advanced').click();
  await seg(page, 'Tooltips', 'Simple').hover();
  await page.locator('.tip-layer').waitFor({ timeout: 2000 });
  await seg(page, 'Tooltips', 'Simple').click();
  await page.waitForTimeout(300);
  expect(`${name}: and also while the pointer stays on the box that was clicked`, (await page.locator('.tip-layer').count()) === 0);
  expect(`${name}: Simple is kept`, (await page.evaluate(() => localStorage.getItem('earthx.tooltips'))) === 'simple');
  await closePanel(page);

  // 8. The full text of a cut-off text.
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
  // 6. Kept per browser: a reload keeps the choices.
  const { context, page, errors } = await open(browser, { viewport });
  await openPanel(page);
  await seg(page, 'Appearance', 'Light').click();
  await seg(page, 'Basemap', 'Outlines').click();
  await seg(page, 'Projection', 'Globe').click();
  await seg(page, 'Overlays', 'Graticule').click();
  await seg(page, 'Tooltips', 'Advanced').click();
  await page.reload({ waitUntil: 'domcontentloaded' });
  await page.waitForSelector('nav[aria-label="Main"] button');
  const state = await store(page, (s) => ({ appearance: s.getState().appearance, theme: s.getState().theme, basemap: s.getState().basemap, projection: s.getState().projection, graticule: s.getState().overlays.graticule, tips: s.getState().tipLevel }));
  expect(`kept ${viewport}: after a reload`, JSON.stringify(state) === JSON.stringify({ appearance: 'light', theme: 'normal', basemap: 'outlines', projection: 'globe', graticule: true, tips: 'advanced' }), JSON.stringify(state));
  expect(`kept ${viewport}: the page is light`, (await page.locator('.app').getAttribute('data-theme')) === 'normal');
  await openPanel(page);
  const pressed = await panel(page).locator('.settings-row [aria-pressed="true"]').allTextContents();
  expect(`kept ${viewport}: the panel marks what was chosen`, JSON.stringify(pressed) === JSON.stringify(['Outlines', 'Graticule', 'Globe', 'Light', 'Advanced']), JSON.stringify(pressed));
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
  await openPanel(locked.page);
  await seg(locked.page, 'Appearance', 'Light').click();
  await seg(locked.page, 'Basemap', 'Outlines').click();
  await seg(locked.page, 'Tooltips', 'Advanced').click();
  const lockedState = await store(locked.page, (s) => ({ theme: s.getState().theme, basemap: s.getState().basemap, tips: s.getState().tipLevel }));
  expect(`locked storage ${viewport}: the choices hold for the visit`, JSON.stringify(lockedState) === JSON.stringify({ theme: 'normal', basemap: 'outlines', tips: 'advanced' }), JSON.stringify(lockedState));
  expect(`locked storage ${viewport}: no error on the page`, locked.errors.length === 0, locked.errors.join(' | '));
  await locked.context.close();
}

async function relief(browser) {
  // 7. A browser that kept the basemap "relief".
  const { context, page, errors } = await open(browser, { viewport: 'wide', init: [() => {
    if (!sessionStorage.getItem('seeded')) { sessionStorage.setItem('seeded', '1'); localStorage.setItem('earthx.basemap', 'relief'); }
  }] });
  const state = await store(page, (s) => ({ basemap: s.getState().basemap, relief: s.getState().overlays.relief }));
  expect('old Relief basemap: opens with the default basemap and the overlay', state.basemap === 'satellite' && state.relief === true, JSON.stringify(state));
  const stored = await page.evaluate(() => [localStorage.getItem('earthx.basemap'), localStorage.getItem('earthx.overlays')]);
  expect('old Relief basemap: the entry is rewritten once', stored[0] === 'satellite' && JSON.parse(stored[1]).relief === true, JSON.stringify(stored));
  await openPanel(page);
  expect('old Relief basemap: the button of the overlay is pressed', (await seg(page, 'Overlays', 'Relief').getAttribute('aria-pressed')) === 'true');
  await seg(page, 'Overlays', 'Relief').click();
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
