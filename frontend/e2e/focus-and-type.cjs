// UI-04 part 3b (Otto, 4.11.2026): in a real browser, light and dark theme, a wide and a narrow window, the control menu shows
//  1. one sign of the focus: a control that takes the keyboard focus gets the ring and nothing else (no second frame, no shadow), and no
//     box around it (a section) changes; counter-check: a stylesheet with the old `input:focus` frame is found;
//  2. one family: every visible text has the family of `--font` (the monospace one is for the band math only); counter-check: a node in
//     Arial is found;
//  3. no autofill of the browser: every field that takes text has autocomplete off, and the rules for a filled-in field are in the sheet.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/focus-and-type.cjs             # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-focus-and-type');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };

// What changes when each control takes the keyboard focus: its own signs (ring, border colour, shadow) and those of the boxes around it.
async function focusAudit(page) {
  await page.keyboard.down('Shift');
  await page.keyboard.up('Shift'); // a key was used: a focus by script is a focus from the keyboard
  return page.evaluate(() => {
    const snap = (el) => {
      const c = getComputedStyle(el);
      return { ring: c.outlineStyle !== 'none' && parseFloat(c.outlineWidth) > 0, border: c.borderTopColor + c.borderRightColor + c.borderBottomColor + c.borderLeftColor, shadow: c.boxShadow };
    };
    const name = (el) => `${el.tagName.toLowerCase()}.${String(el.className).split(' ').filter(Boolean).slice(0, 3).join('.')}${el.getAttribute('aria-label') ? `[${el.getAttribute('aria-label').slice(0, 20)}]` : ''}`;
    const controls = [...document.querySelectorAll('button, input, select, textarea, a[href], summary, [tabindex]:not([tabindex="-1"])')].filter(
      (e) => e.getBoundingClientRect().width > 0 && !e.closest('.maplibregl-map') && !e.disabled,
    );
    const faults = [];
    for (const el of controls) {
      const chain = [];
      for (let n = el; n && n !== document.body && n !== document.documentElement; n = n.parentElement) chain.push(n);
      const before = chain.map(snap);
      el.focus({ preventScroll: true });
      const after = chain.map(snap);
      const own = [after[0].ring && 'ring', before[0].border !== after[0].border && 'border', before[0].shadow !== after[0].shadow && 'shadow'].filter(Boolean);
      if (own.length > 1) faults.push(`${name(el)}: ${own.join(' + ')}`);
      for (let i = 1; i < chain.length; i += 1) {
        const changed = [after[i].ring && !before[i].ring && 'ring', before[i].border !== after[i].border && 'border', before[i].shadow !== after[i].shadow && 'shadow'].filter(Boolean);
        if (changed.length) faults.push(`${name(el)}: the box ${name(chain[i])} shows ${changed.join(' + ')}`);
      }
      el.blur();
    }
    return { checked: controls.length, faults };
  });
}

// The family of every visible text, against the one of the page.
const families = (page) =>
  page.evaluate(() => {
    const page = getComputedStyle(document.body).fontFamily;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    const wrong = new Set();
    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
      const el = node.parentElement;
      if (!el || !node.textContent.trim() || el.closest('script, style, noscript') || el.getBoundingClientRect().width === 0) continue;
      const family = getComputedStyle(el).fontFamily;
      if (family !== page) wrong.add(`${el.tagName.toLowerCase()}.${String(el.className).split(' ')[0]} "${node.textContent.trim().slice(0, 20)}" in ${family.slice(0, 30)}`);
    }
    return { page, wrong: [...wrong] };
  });

async function check(browser, { theme, viewport }) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: 'controls' }));
  await page.locator('.field-label >> visible=true').first().waitFor();

  // 1. the focus
  const focus = await focusAudit(page);
  if (focus.checked < 10) problems.push(`only ${focus.checked} controls were checked`);
  for (const fault of focus.faults) problems.push(`focus: ${fault}`);
  // Counter-check: the old frame at `:focus` is found by the same audit.
  await page.addStyleTag({ content: "input[type='text']:focus { border-color: red; box-shadow: 0 0 8px red; }" });
  const old = await focusAudit(page);
  if (old.faults.length === 0) problems.push('counter-check: the audit did not find the old frame at :focus');
  // The same as a mouse click on a button: no ring.
  await page.locator('.tool-btn').first().click();
  const afterClick = await page.evaluate(() => getComputedStyle(document.activeElement).outlineStyle);
  if (afterClick !== 'none') problems.push(`a click on a button leaves a ring (${afterClick})`);
  await page.keyboard.press('Escape');
  await page.screenshot({ path: path.join(OUT, `focus ${name}.png`) });

  // 2. the family
  await page.reload();
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.setState({ dock: 'controls' }));
  await page.locator('.field-label >> visible=true').first().waitFor();
  const type = await families(page);
  if (!/system-ui/.test(type.page)) problems.push(`the page is not in the system family: ${type.page}`);
  for (const wrong of type.wrong) problems.push(`family: ${wrong}`);
  await page.evaluate(() => {
    const span = document.createElement('span');
    span.textContent = 'Arial node';
    span.style.fontFamily = 'Arial';
    document.querySelector('.control-panel').append(span);
  });
  if (!(await families(page)).wrong.some((w) => w.includes('Arial node'))) problems.push('counter-check: a node in Arial was not found');

  // 3. no autofill
  const fields = await page.$$eval('input, textarea', (els) =>
    els.filter((e) => !['checkbox', 'radio', 'range', 'file', 'hidden'].includes(e.type) && e.getBoundingClientRect().width > 0).map((e) => `${e.tagName.toLowerCase()}[${e.getAttribute('aria-label') ?? e.type}] ${e.getAttribute('autocomplete')}`),
  );
  if (fields.length < 3) problems.push(`only ${fields.length} fields were found`);
  for (const field of fields) if (!field.endsWith(' off')) problems.push(`autocomplete: ${field}`);
  const rules = await page.evaluate(() => {
    const found = [];
    const walk = (list) => {
      for (const rule of list) {
        if (rule.cssRules && !rule.selectorText) walk(rule.cssRules);
        if (rule.selectorText && /autofill/.test(rule.selectorText)) found.push({ selector: rule.selectorText, fill: rule.style.getPropertyValue('-webkit-text-fill-color'), shadow: rule.style.getPropertyValue('box-shadow') });
      }
    };
    for (const sheet of document.styleSheets) {
      try { walk(sheet.cssRules); } catch { /* another origin */ }
    }
    return found;
  });
  for (const pseudo of [':-webkit-autofill', ':autofill']) {
    const rule = rules.find((r) => r.selector.includes(`input${pseudo}`));
    if (!rule) problems.push(`no rule for ${pseudo}`);
    else if (!rule.fill.includes('var(--text)') || !rule.shadow.includes('var(--input-bg)')) problems.push(`the rule for ${pseudo} does not use the colours of the field: ${JSON.stringify(rule)}`);
  }

  await context.close();
  return { name, problems };
}

(async () => {
  require('node:fs').mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const { name, problems } = await check(browser, { theme, viewport });
      console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}`);
      for (const problem of problems) console.log(`       ${problem}`);
      failed += problems.length;
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed === 0 ? 0 : 1);
})();
