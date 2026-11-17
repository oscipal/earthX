// The settings bar stays still while a parameter of a step changes (M5-14, Browserprüfung Otto, 17.11.2026): turning the dial of the hillshade
// made the histogram vanish and come back at every degree, and the panel jumped. On the real `ViewerControls`, store and styles
// (`view-params-harness.html`), dark and light, it fails when
//   1. while the dial is dragged round, the dial, the histogram or the section "Quick processing" moves by a pixel, or the histogram is gone
//      in a frame;
//   2. the statistics are asked for at every degree instead of once the drag rests;
//   3. the numbers beside dial and slider do not follow them, or a number typed (Enter, leaving the field) does not move them, or one outside
//      the bounds is not held at the bound;
//   4. the panel needs a scroll bar for the controls.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/view-params.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-view-params');
const problems = [];
const check = (ok, text) => {
  if (!ok) problems.push(text);
};

async function places(page) {
  return page.evaluate(() => {
    const top = (selector) => {
      const element = document.querySelector(selector);
      return element ? Math.round(element.getBoundingClientRect().top * 10) / 10 : null;
    };
    return { dial: top('.angle-dial-face'), histogram: top('.range-hists'), quick: top('.vc-quick'), slider: top('.vc-param input[type="range"]') };
  });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  for (const theme of ['tech', 'normal']) {
    const page = await browser.newPage({ viewport: { width: 1000, height: 800 }, deviceScaleFactor: 2 });
    page.on('pageerror', (error) => problems.push(`${theme}: page error: ${error.message}`));
    await page.goto(`${BASE}/e2e/view-params-harness.html?theme=${theme}`);
    await page.getByRole('button', { name: 'Hillshade', exact: true }).click();
    await page.waitForFunction(() => window.app.getState().pendingVmin === '1');
    await page.locator('.vc-apply').click();
    await page.waitForSelector('.range-hists');
    await page.waitForSelector('.angle-dial-face');
    await page.waitForTimeout(600);

    // 1. and 2.: a slow drag round half the circle, sampled at every step
    const before = await places(page);
    check(Object.values(before).every((top) => top !== null), `${theme}: a control or the histogram is missing: ${JSON.stringify(before)}`);
    const asked = await page.evaluate(() => window.statisticsAsked.length);
    const box = await page.locator('.angle-dial-face').boundingBox();
    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;
    const r = box.width / 2 - 4;
    const at = (degrees) => [cx + r * Math.sin((degrees * Math.PI) / 180), cy - r * Math.cos((degrees * Math.PI) / 180)];
    await page.mouse.move(...at(315));
    await page.mouse.down();
    const moved = new Set();
    for (let degrees = 315; degrees <= 495; degrees += 5) {
      await page.mouse.move(...at(degrees % 360));
      await page.waitForTimeout(40);
      const now = await places(page);
      for (const [what, top] of Object.entries(now)) if (top !== before[what]) moved.add(`${what} ${before[what]} → ${top} at ${degrees % 360}°`);
    }
    await page.mouse.up();
    check(moved.size === 0, `${theme}: the layout moved while the dial turned: ${[...moved].slice(0, 4).join('; ')}`);
    const during = (await page.evaluate(() => window.statisticsAsked.length)) - asked;
    check(during === 0, `${theme}: the statistics were asked ${during} times while the dial turned`);
    await page.waitForTimeout(1200);
    const after = (await page.evaluate(() => window.statisticsAsked.length)) - asked;
    check(after >= 1 && after <= 3, `${theme}: after the drag rested the statistics were asked ${after} times, not once or twice`);
    check(JSON.stringify(await places(page)) === JSON.stringify(before), `${theme}: the layout moved once the new range came`);
    const azimuth = await page.locator('.vc-param-number input').first().inputValue();
    check(azimuth === '135', `${theme}: the number beside the dial shows ${azimuth}, not 135`);
    check((await page.evaluate(() => window.app.getState().appliedRender.presetParams?.azimuth)) === 135, `${theme}: the picture is not drawn with 135°`);

    // 3. typed numbers
    const [field, height] = [page.locator('.vc-param-number input').nth(0), page.locator('.vc-param-number input').nth(1)];
    await field.fill('400');
    await field.press('Enter');
    check((await page.locator('.angle-dial-face').getAttribute('aria-valuenow')) === '0', `${theme}: 400° typed is not held at north`);
    await height.fill('30');
    await page.locator('.angle-dial-face').focus();
    check((await page.locator('.vc-param input[type="range"]').inputValue()) === '30', `${theme}: the slider did not follow 30 typed and left`);
    await page.locator('.angle-dial-face').press('Shift+ArrowRight');
    check((await field.inputValue()) === '15', `${theme}: the number did not follow the dial (shows ${await field.inputValue()})`);

    // 4. no scroll bar for the controls
    const scroll = await page.$eval('.inspector .insp-body', (body) => body.scrollHeight - body.clientHeight);
    check(scroll <= 0, `${theme}: the panel scrolls by ${scroll} px`);
    await page.waitForTimeout(800);
    await page.locator('.inspector').screenshot({ path: path.join(OUT, `view-params-${theme}.png`) });
    await page.close();
  }
  await browser.close();
  if (problems.length > 0) {
    console.error(problems.map((text) => `FAIL ${text}`).join('\n'));
    process.exit(1);
  }
  console.log(`ok: the bar stays still while the dial turns, the numbers follow, dark and light; screenshots in ${OUT}`);
})();
