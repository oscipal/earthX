// Browser check of the choice of bands and files in the download dialog (NM4-75): the real dialog of the real app, with made-up
// scenes and made-up answers of the platform. Checked in the light and the dark theme, at a wide and a narrow window:
//   crop       the list of bands from the scene, "None" locks "Download", the form, the common resolution with its (i), the factor
//              for one file per band only, the request that "Download" sends (form, assets, common_resolution), Esc closes nothing
//   whole      "Download full scene" waits for "Download"; one file per resolution shows the estimate and places a job with the
//              layout and without an AOI; the resampling warning comes first where the platform resamples
//   layout     nothing overlaps or leaves the dialog, the list scrolls inside it, controls are as high as the others (28 px, 44 px
//              on the narrow window); a screenshot per case
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/band-download.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots, not in the repository>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const os = require('node:os');
const path = require('node:path');
const fs = require('node:fs');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(os.tmpdir(), 'earthx-band-download');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const JOB = 'AAAAAAAAAAAAAAAAAAAAAA';
const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';

const SPECS = [
  ['a_blue', 'B02', 'blue', 0.49, 10], ['a_green', 'B03', 'green', 0.56, 10], ['a_red', 'B04', 'red', 0.665, 10], ['a_nir', 'B08', 'nir', 0.842, 10],
  ['a_edge1', 'B05', 'rededge', 0.704, 20], ['a_edge2', 'B06', 'rededge', 0.74, 20], ['a_swir', 'B11', 'swir16', 1.61, 20],
  ['a_coast', 'B01', 'coastal', 0.443, 60], ['a_vapour', 'B09', 'nir09', 0.945, 60], ['scl', 'scl', null, null, 20], ['aerosol', 'aerosol', null, null, 20],
];

function item(id, host) {
  const assets = {};
  for (const [key, , , , gsd] of SPECS) assets[key] = { href: `${host}/${id}/${key}.tif`, type: COG, roles: ['data'], gsd, 'file:size': 1_000_000 };
  assets.visual = { href: `${host}/${id}/visual.tif`, type: COG, roles: ['visual'], gsd: 10 };
  return { id, collection: 'e2e', bbox: [10, 50, 11, 51], properties: { datetime: '2026-07-02T10:15:00Z' }, assets };
}

// What the platform answers to `POST /collections/{dataset}/bands`: the table of bands of the scenes.
const bandsAnswer = () => ({
  bands: SPECS.map(([key, name, common, wavelength, gsd]) => ({
    asset: key, name, common_name: common, wavelength_um: wavelength, resolution_m: gsd, data_type: 'uint16', scale: null, offset: null, nodata: 0,
    unit: key === 'scl' ? null : '1', categorical: key === 'scl', preselected: wavelength !== null || key === 'scl',
  })),
});

const collection = (host) => ({
  id: 'e2e', title: 'Made-up multispectral',
  'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, single_coverage_product: false },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, browse: 'quicklook', quicklook_nodata_max: 16, results_group_by: ['datetime'] },
  'earthx:format': 'cog', 'earthx:access': { cors: false }, 'earthx:source': { asset_hosts: [new URL(host).hostname] },
  'earthx:band_units': Object.fromEntries([...SPECS.map(([key]) => [key, key === 'scl' ? null : '1']), ['visual', null]]),
  'earthx:auxiliary_assets': ['visual'],
  'earthx:mask': { asset: 'scl', band: 'scl', classes: [{ value: 0, label: 'No data' }, { value: 4, label: 'Vegetation' }], suggested: [4], reference: '', note: '' },
  'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:license_flags': {
    spdx_id: null, name: 'Made-up notice', url: 'https://example.org/n', commercial_use: true, distribution: true, derivatives: true, share_alike: false,
    attribution_required: true, tier: 'processing', attribution_modified: 'Contains modified made-up data {year}', attribution_unmodified: 'Made-up data {year}',
    terms_url: 'https://example.org/n', terms_notice: { en: 'Subject to {terms_url}.' },
  },
});

const AOI = { type: 'Polygon', coordinates: [[[10.1, 50.1], [10.2, 50.1], [10.2, 50.2], [10.1, 50.2], [10.1, 50.1]]] };
const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
const expectEq = (problems, what, got, want) => {
  if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`);
};

async function openApp(browser, { theme, viewport, resampling }) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport], acceptDownloads: true });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const problems = [];
  const seen = { download: [], estimate: [], execution: [] };
  page.on('pageerror', (e) => problems.push(`page error: ${e.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const req = route.request();
    const url = new URL(req.url());
    if (url.origin !== BASE) return route.abort();
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.endsWith('/bands')) return json(bandsAnswer());
    if (url.pathname.endsWith('/download')) {
      seen.download.push(JSON.parse(req.postData() ?? '{}'));
      return route.fulfill({ status: 200, contentType: 'application/zip', headers: { 'x-total-groups': '1', 'x-skipped-groups': '0' }, body: 'PK' });
    }
    if (url.pathname.endsWith('/estimate')) {
      seen.estimate.push(JSON.parse(req.postData() ?? '{}'));
      const estimate = { size: 3_400_000, duration: 'PT12S', outputPixels: 1, inputPixels: 1, inputBytes: 1, assets: 1, units: 1 };
      return json({ estimate, skippedItems: [], ...(resampling ? { resampling: { grid: { resolution: 10, crs: 'EPSG:4326' }, method: 'mixed', bands: [{ band: 'a_edge1', resolution: 20, crs: null }], scenes: null } } : {}) });
    }
    if (url.pathname.endsWith('/execution')) {
      seen.execution.push(JSON.parse(req.postData() ?? '{}'));
      return json({ jobID: JOB, status: 'accepted', message: '', progress: 0, expires: '2099-01-01T00:00:00Z' });
    }
    if (url.pathname.endsWith(`/jobs/${JOB}`)) return json({ jobID: JOB, status: 'successful', message: '', progress: 100, expires: '2099-01-01T00:00:00Z' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.evaluate(async ({ aoi, scenes, collection }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    useAppStore.setState({
      datasets: datasetsFrom([collection]), datasetId: 'e2e', items: scenes, groups: [{ key: ['2026-07-02'], label: '2026-07-02', items: scenes }],
      activeGroupIndex: 0, selectedIds: scenes.map((s) => s.id), dock: null, aoi, layers: [], error: null,
    });
  }, { aoi: AOI, scenes: [item('S_A', BASE), item('S_B', BASE)], collection: collection(BASE) });
  return { context, page, problems, seen };
}

async function layout(page, label, problems, narrow) {
  const found = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const panel = document.querySelector('.dialog-panel');
    const parts = [...panel.querySelectorAll('button, select, .dialog-band, .dialog-forms button')].map((e) => ({ what: (e.textContent || e.tagName).trim().slice(0, 24), ...box(e) }));
    const body = document.querySelector('.dialog-body');
    return { panel: box(panel), parts, scrolls: body.scrollWidth > body.clientWidth + 1, window: { width: innerWidth, height: innerHeight } };
  });
  const high = narrow ? 44 : 28;
  for (const part of found.parts) {
    if (part.x < found.panel.x - 0.5 || part.x + part.width > found.panel.x + found.panel.width + 0.5) problems.push(`${label}: ${part.what} leaves the dialog`);
    // The red x is the one control that is small by rule (CloseButton); the rest is as high as the others.
    if (part.height + 0.5 < high && part.width > 24) problems.push(`${label}: ${part.what} is ${part.height}px high, less than ${high}`);
  }
  const seg = found.parts.filter((p) => /^One /.test(p.what));
  for (let i = 0; i < seg.length; i += 1) for (let j = i + 1; j < seg.length; j += 1) if (overlap(seg[i], seg[j])) problems.push(`${label}: ${seg[i].what} overlaps ${seg[j].what}`);
  const p = found.panel;
  if (p.x < -0.5 || p.x + p.width > found.window.width + 0.5 || p.y < -0.5 || p.y + p.height > found.window.height + 0.5) problems.push(`${label}: the dialog leaves the window`);
  if (found.scrolls) problems.push(`${label}: the dialog scrolls sideways`);
}

const openDialog = async (page, kind) => {
  await page.evaluate((k) => import('/src/store.ts').then(({ useAppStore }) => useAppStore.getState().openDownloadForSelection(k)), kind);
  await page.waitForSelector('.dialog-panel');
  await page.waitForSelector('.dialog-bands');
};
const shot = (page, name, selector = '.dialog-download') => page.locator(selector).screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });

async function caseCrop(browser, { theme, viewport }) {
  const label = `crop ${theme} ${viewport}`;
  const { context, page, problems, seen } = await openApp(browser, { theme, viewport });
  fs.mkdirSync(OUT, { recursive: true });
  await openDialog(page, 'crop');
  expectEq(problems, `${label}: title`, await page.textContent('.dialog-panel h2'), 'Download crop');
  expectEq(problems, `${label}: bands`, await page.$$eval('.dialog-band-name', (e) => e.map((x) => x.textContent)), SPECS.map(([, name]) => name));
  expectEq(problems, `${label}: ticked`, await page.$$eval('.dialog-band input', (e) => e.filter((x) => x.checked).length), 10);
  await layout(page, `${label} bands`, problems, viewport === 'narrow');
  await shot(page, `${label}-bands`);
  // None locks Download.
  await page.getByRole('button', { name: 'None', exact: true }).click();
  if (!(await page.getByRole('button', { name: 'Download', exact: true }).isDisabled())) problems.push(`${label}: Download is open with no band`);
  await page.getByRole('button', { name: 'All', exact: true }).click();
  // The factor is for one file per band only.
  if (!(await page.locator('.dialog-resolution').count())) problems.push(`${label}: no factor for one file per band`);
  await page.getByRole('button', { name: 'One file per resolution' }).click();
  if (await page.locator('.dialog-resolution').count()) problems.push(`${label}: a factor with one file per resolution`);
  await page.getByRole('button', { name: 'One multi-band file' }).click();
  expectEq(problems, `${label}: resolutions`, await page.$$eval('.dialog-common option', (e) => e.map((x) => x.textContent)), ['10 m', '20 m', '60 m']);
  const tip = await page.getAttribute('.dialog-common .tip', 'data-tip');
  if (!tip?.includes('Converted to 10 m')) problems.push(`${label}: the (i) does not say what is converted: ${JSON.stringify(tip)}`);
  await page.hover('.dialog-common .tip');
  await page.waitForSelector('.tip-layer', { timeout: 3000 }).catch(() => problems.push(`${label}: no tooltip layer on hover`));
  await layout(page, `${label} multi-band`, problems, viewport === 'narrow');
  await shot(page, `${label}-multi-band`);
  // Escape closes nothing.
  await page.keyboard.press('Escape');
  if (!(await page.locator('.dialog-panel').count())) problems.push(`${label}: Escape closed the dialog`);
  await page.selectOption('.dialog-common select', '20');
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  await page.waitForFunction(() => !document.querySelector('.dialog-panel'), null, { timeout: 5000 }).catch(() => problems.push(`${label}: the dialog stays after the download`));
  expectEq(problems, `${label}: requests`, seen.download.length, 1);
  const body = seen.download[0] ?? {};
  expectEq(problems, `${label}: form`, [body.form, body.common_resolution, body.resolution], ['multi_band', 20, 1]);
  // "All" was pressed above: every band of the scene.
  expectEq(problems, `${label}: assets`, body.assets, SPECS.map(([key]) => key));
  await context.close();
  return { label, problems };
}

async function caseWhole(browser, { theme, viewport, resampling }) {
  const label = `whole ${theme} ${viewport}${resampling ? ' resampled' : ''}`;
  const { context, page, problems, seen } = await openApp(browser, { theme, viewport, resampling });
  await openDialog(page, 'originals');
  expectEq(problems, `${label}: title`, await page.textContent('.dialog-panel h2'), 'Download full scenes');
  if (await page.locator('.dialog-original-row').count()) problems.push(`${label}: the download started by itself`);
  await shot(page, `${label}-before`);
  await page.getByRole('button', { name: 'One file per resolution' }).click();
  await page.waitForFunction(() => /About 3\.4 MB/.test(document.querySelector('.dialog-body')?.textContent ?? ''), null, { timeout: 5000 }).catch(() => problems.push(`${label}: no estimate in the dialog`));
  await layout(page, `${label} job`, problems, viewport === 'narrow');
  await shot(page, `${label}-job`);
  await page.getByRole('button', { name: 'Download', exact: true }).click();
  if (resampling) {
    await page.waitForSelector('[role="alertdialog"]');
    if (seen.execution.length) problems.push(`${label}: a job was placed before the warning was answered`);
    await shot(page, `${label}-warning`, '.resampling-dialog');
    await page.getByRole('button', { name: 'Continue' }).click();
  }
  await page.waitForFunction(() => !document.querySelector('.dialog-panel'), null, { timeout: 8000 }).catch(() => problems.push(`${label}: the dialog stays after the job`));
  expectEq(problems, `${label}: jobs placed`, seen.execution.length, 1);
  const recipe = seen.execution[0]?.inputs?.recipe;
  if (recipe && 'aoi' in recipe) problems.push(`${label}: the order carries an AOI`);
  expectEq(problems, `${label}: layout`, recipe?.output?.layout, { form: 'per_resolution' });
  expectEq(problems, `${label}: groups`, recipe?.inputs?.[0]?.groups, [['S_A', 'S_B']]);
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
      results.push(await caseWhole(browser, { theme, viewport, resampling: false }));
    }
  }
  results.push(await caseWhole(browser, { theme: 'light', viewport: 'wide', resampling: true }));
  await browser.close();
  for (const { label, problems } of results) console.log(`${problems.length ? 'FAIL' : 'ok  '} ${label}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
