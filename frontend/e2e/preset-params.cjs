// The parameters of a step of "Quick processing" in a real browser (M5-14, Otto, 17.11.2026): the dial of the azimuth, the slider of the
// altitude and the switch of the unit of the slope, on the real components and styles (`preset-params-harness.html`), dark and light. It fails
// when
//   1. a control is missing, or the box of the settings bar (320 px) has to scroll sideways or down for them;
//   2. dragging the dial round its circle does not give north 0°, east 90°, south 180° and west 270° in the number beside it;
//   3. the arrows do not step 1°, with Shift 15°, round the circle;
//   4. the hand, the ring or the north tick is not drawn in the colours of the theme (`--accent`, `--line`, `--muted`) of that theme;
//   5. the slider leaves 0 to 90, or the unit of the slope does not switch.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/preset-params.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-preset-params');
const problems = [];
const check = (ok, text) => {
  if (!ok) problems.push(text);
};

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 800, height: 400 }, deviceScaleFactor: 2 });
  page.on('pageerror', (error) => problems.push(`page error: ${error.message}`));
  await page.goto(`${BASE}/e2e/preset-params-harness.html`);
  await page.waitForSelector('#panel-normal .angle-dial-face');

  for (const theme of ['tech', 'normal']) {
    const panel = `#panel-${theme}`;
    const dial = page.locator(`${panel} .angle-dial-face`);
    const number = page.locator(`${panel} .vc-param-number input`).first();
    const value = { textContent: async () => `${await number.inputValue()}°` };
    // 1. the controls, and no scrolling in the width of the settings bar
    check((await page.locator(`${panel} .vc-param`).count()) === 3, `${theme}: three controls (azimuth, altitude, unit)`);
    const overflow = await page.$eval(panel, (box) => ({ x: box.scrollWidth - box.clientWidth, y: box.scrollHeight - box.clientHeight }));
    check(overflow.x <= 0 && overflow.y <= 0, `${theme}: the box scrolls (${overflow.x} px sideways, ${overflow.y} px down)`);
    check((await value.textContent()) === '315°', `${theme}: the dial starts at 315°, shows ${await value.textContent()}`);

    // 2. dragging round the circle
    const box = await dial.boundingBox();
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    const r = box.width / 2 - 4;
    await page.mouse.move(cx, cy - r);
    await page.mouse.down();
    check((await value.textContent()) === '0°', `${theme}: north is 0°, shows ${await value.textContent()}`);
    for (const [dx, dy, want] of [[r, 0, '90°'], [0, r, '180°'], [-r, 0, '270°']]) {
      await page.mouse.move(cx + dx, cy + dy, { steps: 4 });
      check((await value.textContent()) === want, `${theme}: dragged to ${want}, shows ${await value.textContent()}`);
    }
    await page.mouse.up();

    // 3. the keys
    await dial.focus();
    await page.keyboard.press('ArrowRight');
    check((await value.textContent()) === '271°', `${theme}: ArrowRight gives 271°, shows ${await value.textContent()}`);
    await page.keyboard.press('Shift+ArrowRight');
    await page.keyboard.press('Shift+ArrowRight');
    await page.keyboard.press('Shift+ArrowRight');
    await page.keyboard.press('Shift+ArrowRight');
    await page.keyboard.press('Shift+ArrowRight');
    await page.keyboard.press('Shift+ArrowRight');
    check((await value.textContent()) === '1°', `${theme}: six times Shift+ArrowRight round north gives 1°, shows ${await value.textContent()}`);

    // 4. the colours of the theme
    const colours = await page.$eval(panel, (box) => {
      const style = getComputedStyle(box.closest('.app'));
      const probe = document.createElement('span');
      box.append(probe);
      const resolve = (token) => {
        probe.style.color = style.getPropertyValue(token).trim();
        return getComputedStyle(probe).color;
      };
      const tokens = { accent: resolve('--accent'), line: resolve('--line'), muted: resolve('--muted') };
      probe.remove();
      const of = (selector, what) => getComputedStyle(box.querySelector(selector))[what];
      return { tokens, hand: of('.angle-dial-hand', 'stroke'), ring: of('.angle-dial-ring', 'stroke'), north: of('.angle-dial-north', 'stroke'), knob: of('.angle-dial-knob', 'fill') };
    });
    check(colours.hand === colours.tokens.accent && colours.knob === colours.tokens.accent, `${theme}: the hand is not --accent (${colours.hand}, ${colours.tokens.accent})`);
    check(colours.ring === colours.tokens.line, `${theme}: the ring is not --line (${colours.ring}, ${colours.tokens.line})`);
    check(colours.north === colours.tokens.muted, `${theme}: the north tick is not --muted (${colours.north}, ${colours.tokens.muted})`);

    // 5. the slider and the unit
    const slider = page.locator(`${panel} .vc-param input[type="range"]`);
    check((await slider.getAttribute('min')) === '0' && (await slider.getAttribute('max')) === '90', `${theme}: the altitude is not 0 to 90`);
    await slider.focus();
    await page.keyboard.press('End');
    check((await page.locator(`${panel} .vc-param-number input`).nth(1).inputValue()) === '90', `${theme}: the altitude stops at 90°`);
    const percent = page.locator(`${panel} .vc-param-choices button`, { hasText: 'Percent' });
    await percent.click();
    check((await percent.getAttribute('aria-pressed')) === 'true', `${theme}: the slope did not switch to percent`);
  }

  await page.locator('#root').screenshot({ path: path.join(OUT, 'preset-params.png') });
  await browser.close();
  if (problems.length > 0) {
    console.error(problems.map((text) => `FAIL ${text}`).join('\n'));
    process.exit(1);
  }
  console.log(`ok: dial, slider and unit in the dark and the light theme; screenshot in ${OUT}`);
})();
