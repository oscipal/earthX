// Browser check of "Style file" in the download dialog (M5-64 plan §12, Otto 27.11.2026): the real dialog with the made-up scenes and
// answers of `band-download.cjs`, in the light and the dark theme, at 1280×800 and 360×740. It fails when
//   crop    the field is missing, does not offer QGIS (.qml), SLD and None with QGIS chosen, or the dialog then scrolls (sideways, or
//           its body as a whole: only the list of bands scrolls inside it); "SLD" does not send `style_format: "sld"` with the look,
//           "None" not `none`, or the choice is not kept for the next dialog
//   whole   one file per resolution (a job) has no field, or its order lacks `styleFormat` beside `exportStyle`; one file per band
//           (loaded in the browser, plan F5) shows one
// It writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up
//   node e2e/m5-64-qgis-style.cjs           # BASE=http://localhost:5173 OUT=<directory for the screenshots, not in the repository>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const { OUT, STYLE, openApp, openDialog, applyLook, layout, expectEq, shot } = require('./band-download.cjs');

const FIELD = '.dialog-style-file select';

async function bodyScrolls(page) {
  return page.evaluate(() => {
    const body = document.querySelector('.dialog-body');
    return body.scrollHeight > body.clientHeight + 1;
  });
}

async function caseCrop(browser, { theme, viewport }) {
  const label = `crop ${theme} ${viewport}`;
  const { context, page, problems, seen } = await openApp(browser, { theme, viewport });
  await openDialog(page, 'crop');
  if (!(await page.locator(FIELD).count())) problems.push(`${label}: no field "Style file"`);
  expectEq(problems, `${label}: options`, await page.$$eval(`${FIELD} option`, (o) => o.map((x) => x.textContent)), ['QGIS (.qml)', 'SLD', 'None']);
  expectEq(problems, `${label}: default`, await page.inputValue(FIELD), 'qml');
  await layout(page, `${label} style file`, problems, viewport === 'narrow');
  if (await bodyScrolls(page)) problems.push(`${label}: the dialog scrolls with the field`);
  await page.locator(FIELD).scrollIntoViewIfNeeded();
  await shot(page, `style-${label}`);
  await page.selectOption(FIELD, 'sld');
  await applyLook(page);
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('.dialog-panel'), null, { timeout: 5000 }).catch(() => problems.push(`${label}: the dialog stays`));
  expectEq(problems, `${label}: sld`, [seen.download[0]?.style_format, seen.download[0]?.style], ['sld', STYLE]);
  // The choice holds for the next dialog; "None" sends none.
  await openDialog(page, 'crop');
  expectEq(problems, `${label}: kept`, await page.inputValue(FIELD), 'sld');
  await page.selectOption(FIELD, 'none');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('.dialog-panel'), null, { timeout: 5000 }).catch(() => problems.push(`${label}: the dialog stays`));
  expectEq(problems, `${label}: none`, seen.download[1]?.style_format, 'none');
  await context.close();
  return { label, problems };
}

async function caseWhole(browser, { theme, viewport }) {
  const label = `whole ${theme} ${viewport}`;
  const { context, page, problems, seen } = await openApp(browser, { theme, viewport });
  await openDialog(page, 'originals');
  if (await page.locator(FIELD).count()) problems.push(`${label}: a field for files loaded in the browser`);
  await page.getByRole('button', { name: 'One file per resolution' }).click();
  await page.waitForSelector(FIELD, { timeout: 5000 }).catch(() => problems.push(`${label}: no field for a job`));
  await page.waitForFunction(() => /About 3\.4 MB/.test(document.querySelector('.dialog-body')?.textContent ?? ''), null, { timeout: 5000 }).catch(() => problems.push(`${label}: no estimate`));
  await layout(page, `${label} style file`, problems, viewport === 'narrow');
  if (await bodyScrolls(page)) problems.push(`${label}: the dialog scrolls with the field`);
  await page.selectOption(FIELD, 'sld');
  await shot(page, `style-${label}`);
  await applyLook(page);
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('.dialog-panel'), null, { timeout: 8000 }).catch(() => problems.push(`${label}: the dialog stays after the job`));
  const inputs = seen.execution[0]?.inputs ?? {};
  expectEq(problems, `${label}: order`, [inputs.styleFormat, inputs.exportStyle], ['sld', STYLE]);
  if (JSON.stringify(inputs.recipe ?? {}).includes('sld')) problems.push(`${label}: the style file is in the recipe`);
  await context.close();
  return { label, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  const results = [];
  for (const theme of ['light', 'dark']) {
    for (const viewport of ['wide', 'narrow']) {
      results.push(await caseCrop(browser, { theme, viewport }));
      results.push(await caseWhole(browser, { theme, viewport }));
    }
  }
  await browser.close();
  for (const { label, problems } of results) console.log(`${problems.length ? 'FAIL' : 'ok  '} ${label}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
