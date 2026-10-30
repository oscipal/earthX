// Browser check of "Download full scenes" (NM4-33): one click on the real button of the real app, and the files come as
// the plan says (docs/plans/querschnitt/nm4-33-originale-ein-klick.md, section 6.14). The sources are two local HTTPS
// servers with made-up bytes, one with CORS and one without; Chromium downloads for real (a service worker streams the
// ZIPs). Checked, in the light and the dark theme at a wide and a narrow window:
//   zip        two scenes -> two ZIPs, one after the other: STORE, every CRC, every byte, ATTRIBUTION.txt, item.json,
//              no preview or thumbnail, the metadata files in
//   no CORS    a dataset without CORS, and a source that does not allow it: the files are downloads of the browser,
//              ATTRIBUTION.txt beside them, the metadata files left out
//   no worker  service workers blocked: single files under their names, item.json and ATTRIBUTION.txt beside them
//   a failure  a source answering 500: that scene fails with its reason, the others finish, "Retry failed" loads it
//   cancel     "Cancel" and the ✕ of the dialog stop the download, and the source sends nothing more
//   layout     nothing overlaps or leaves the dialog; a screenshot per case
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/originals-one-click.cjs        # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// With REAL_ITEM=<path of a STAC item of Earth Search sentinel-2-c1-l2a> the one case that runs is a whole real scene
// (about 0.9 GB) through the real app, with the memory of the browser measured; HTTPS_PROXY is used when set.
//
// Playwright, Chromium, openssl and python3 are not a dependency of the project (CI does not run this); the cloud
// session has them.

const { chromium } = require('playwright');
const https = require('node:https');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync, execSync } = require('node:child_process');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(os.tmpdir(), 'earthx-originals');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const PORTS = { cors: 5391, plain: 5392 };

// --- the sources: made-up bytes that depend on the path, so that a ZIP can be compared byte by byte ---

const ASSETS = { red: 1_200_000, nir: 900_000, scl: 200_000, visual: 400_000, preview: 6_000, granule_metadata: 50_000 };
const control = { fail: new Set(), slowMs: 0, sent: new Map() };

function bytesOf(file, size) {
  const seed = crypto.createHash('sha256').update(file).digest();
  const out = Buffer.alloc(size);
  for (let i = 0; i < size; i += 1) out[i] = (seed[i % 32] + i * 7) & 255;
  return out;
}

function startSource(port, cors, tls) {
  const server = https.createServer(tls, async (req, res) => {
    const file = req.url.slice(1);
    const [scene, asset] = file.replace(/\.[a-z]+$/, '').split('/');
    const size = ASSETS[asset];
    const headers = cors ? { 'access-control-allow-origin': '*', 'access-control-allow-headers': 'range' } : {};
    if (req.method === 'OPTIONS') return res.writeHead(204, headers).end();
    if (!scene || size === undefined || control.fail.has(file)) return res.writeHead(control.fail.has(file) ? 500 : 404, headers).end();
    res.writeHead(200, { ...headers, 'content-length': size, 'content-type': asset === 'granule_metadata' ? 'application/xml' : 'image/tiff' });
    if (req.method === 'HEAD') return res.end();
    const data = bytesOf(file, size);
    for (let at = 0; at < size && !res.destroyed; at += 65_536) {
      const chunk = data.subarray(at, at + 65_536);
      if (control.slowMs) await new Promise((resolve) => setTimeout(resolve, control.slowMs));
      if (res.destroyed) break;
      res.write(chunk);
      control.sent.set(file, (control.sent.get(file) ?? 0) + chunk.length);
    }
    res.end();
  });
  return new Promise((resolve) => server.listen(port, () => resolve(server)));
}

// --- what the page is given ---

function sceneSpec(id, origin) {
  const ext = { granule_metadata: 'xml' };
  const assets = Object.fromEntries(
    Object.entries(ASSETS).map(([key, size]) => [
      key,
      { href: `${origin}/${id}/${key}.${ext[key] ?? 'tif'}`, 'file:size': size, roles: key === 'visual' ? ['visual'] : key === 'preview' ? ['overview'] : key === 'granule_metadata' ? ['metadata'] : ['data'] },
    ]),
  );
  return { id, collection: 'e2e', properties: { datetime: '2026-07-01T10:00:00Z' }, assets };
}

async function openApp(browser, { theme, viewport, cors, sceneIds, origin, blockWorkers, items }) {
  const context = await browser.newContext({
    viewport: VIEWPORTS[viewport],
    acceptDownloads: true,
    ignoreHTTPSErrors: true,
    serviceWorkers: blockWorkers ? 'block' : 'allow',
  });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  const problems = [];
  page.on('pageerror', (e) => problems.push(`page error: ${e.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE) return url.hostname === 'localhost' && Object.values(PORTS).includes(Number(url.port)) ? route.continue() : route.abort();
    if (/^\/(src|@|node_modules|assets|__originals)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(
    async ({ cors, scenes }) => {
      const { useAppStore } = await import('/src/store.ts');
      const collection = {
        id: 'e2e',
        title: 'Made-up Sentinel-2',
        'earthx:format': 'cog',
        'earthx:access': { cors },
        'earthx:source': { asset_hosts: ['localhost'] },
        'earthx:band_units': { red: 'x', nir: 'x', scl: null, visual: null, preview: null },
        'earthx:auxiliary_assets': ['visual', 'preview'],
        'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
        'earthx:license_flags': {
          spdx_id: null, name: 'Made-up notice', url: 'https://example.org/notice', commercial_use: true, distribution: true, derivatives: true, share_alike: false,
          attribution_required: true, tier: 'processing', attribution_modified: 'Contains modified made-up data {year}', attribution_unmodified: 'Made-up data {year}',
          terms_url: 'https://example.org/notice', terms_notice: { en: 'Subject to {terms_url}.' },
        },
      };
      useAppStore.setState({
        datasets: [{ id: 'e2e', title: 'Made-up Sentinel-2', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection }],
        datasetId: 'e2e',
        items: scenes,
        groups: [{ key: ['2026-07-01'], label: '2026-07-01', items: scenes }],
        activeGroupIndex: 0,
        selectedIds: scenes.map((scene) => scene.id),
        dock: null,
        aoi: null,
        layers: [],
        error: null,
      });
    },
    { cors, scenes: items ?? sceneIds.map((id) => sceneSpec(id, origin)) },
  );
  return { context, page, problems };
}

// --- what the browser did ---

function collectDownloads(page) {
  const list = [];
  page.on('download', (download) => {
    const entry = { name: download.suggestedFilename(), failure: undefined, file: undefined };
    list.push(entry);
    entry.done = download.failure().then(async (failure) => {
      entry.failure = failure;
      if (!failure) entry.file = await download.path();
    });
  });
  return list;
}

const settled = (list) => Promise.all(list.map((entry) => entry.done));

function zipEntries(file) {
  const out = execFileSync(
    'python3',
    [
      '-I',
      '-c',
      `import zipfile, sys, json, hashlib
z = zipfile.ZipFile(sys.argv[1])
bad = z.testzip()
print(json.dumps({"bad": bad, "entries": [{"name": i.filename, "size": i.file_size, "stored": i.compress_type == 0, "sha": hashlib.sha256(z.read(i.filename)).hexdigest()} for i in z.infolist()], "attribution": z.read("ATTRIBUTION.txt").decode() if "ATTRIBUTION.txt" in z.namelist() else None, "item": z.read("item.json").decode() if "item.json" in z.namelist() else None}))`,
      file,
    ],
    { maxBuffer: 1 << 26 },
  ).toString();
  return JSON.parse(out);
}

const sha = (buffer) => crypto.createHash('sha256').update(buffer).digest('hex');
const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
const rowStates = (page) => page.$$eval('.dialog-original-row', (rows) => rows.map((row) => row.querySelector('.dialog-original-state')?.textContent ?? ''));
const waitRows = (page, test, timeout = 60_000) =>
  page.waitForFunction((src) => new Function('states', `return (${src})(states)`)([...document.querySelectorAll('.dialog-original-row .dialog-original-state')].map((e) => e.textContent)), test.toString(), { timeout });

async function layout(page, label, problems) {
  const found = await page.evaluate(() => {
    const box = (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, width: r.width, height: r.height }; };
    const panel = document.querySelector('.dialog-panel');
    const body = document.querySelector('.dialog-body');
    const buttons = [...document.querySelectorAll('.dialog-original-buttons button')].map((b) => ({ what: b.textContent, ...box(b) }));
    const rows = [...document.querySelectorAll('.dialog-original-row')].map((r) => ({ what: r.textContent.slice(0, 20), ...box(r) }));
    return { panel: box(panel), buttons, rows, scrolls: body.scrollWidth > body.clientWidth + 1, window: { width: innerWidth, height: innerHeight } };
  });
  for (let i = 0; i < found.buttons.length; i += 1) {
    for (let j = i + 1; j < found.buttons.length; j += 1) if (overlap(found.buttons[i], found.buttons[j])) problems.push(`${label}: ${found.buttons[i].what} overlaps ${found.buttons[j].what}`);
  }
  for (const part of [...found.buttons, ...found.rows]) {
    if (part.x < found.panel.x - 0.5 || part.x + part.width > found.panel.x + found.panel.width + 0.5) problems.push(`${label}: ${part.what} leaves the dialog`);
  }
  if (found.panel.x < -0.5 || found.panel.x + found.panel.width > found.window.width + 0.5 || found.panel.y < -0.5 || found.panel.y + found.panel.height > found.window.height + 0.5) problems.push(`${label}: the dialog leaves the window`);
  if (found.scrolls) problems.push(`${label}: the dialog scrolls sideways`);
}

const downloadButton = (page) => page.getByRole('button', { name: /^⇩ Download full scenes?$/ });

function expectEq(problems, what, got, want) {
  if (JSON.stringify(got) !== JSON.stringify(want)) problems.push(`${what}: ${JSON.stringify(got)}, not ${JSON.stringify(want)}`);
}

// --- the cases ---

async function caseZip(browser, { theme, viewport }) {
  const label = `zip ${theme} ${viewport}`;
  const { context, page, problems } = await openApp(browser, { theme, viewport, cors: true, sceneIds: ['S2_A', 'S2_B'], origin: `https://localhost:${PORTS.cors}` });
  const downloads = collectDownloads(page);
  control.slowMs = 25;
  await downloadButton(page).click();
  await page.waitForSelector('.dialog-original-row');
  await waitRows(page, (s) => s.some((t) => /^Loading/.test(t)));
  fs.mkdirSync(OUT, { recursive: true });
  await layout(page, `${label} while loading`, problems);
  await page.locator('.dialog-panel').screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}-loading.png`) });
  await waitRows(page, (s) => s.every((t) => t === 'Done'));
  control.slowMs = 0;
  await settled(downloads);
  await layout(page, `${label} done`, problems);
  await page.locator('.dialog-panel').screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}-done.png`) });

  expectEq(problems, `${label}: the files that came`, downloads.map((d) => d.name), ['S2_A.zip', 'S2_B.zip']);
  expectEq(problems, `${label}: failures`, downloads.map((d) => d.failure), [null, null]);
  const wanted = ['nir', 'red', 'scl', 'visual', 'granule_metadata'];
  for (const [index, id] of ['S2_A', 'S2_B'].entries()) {
    if (!downloads[index]?.file) continue;
    const zip = zipEntries(downloads[index].file);
    expectEq(problems, `${label}: ${id} CRC`, zip.bad, null);
    expectEq(problems, `${label}: ${id} entries`, zip.entries.map((e) => e.name).sort(), ['ATTRIBUTION.txt', 'item.json', ...wanted.map((k) => `${id}_${k}.${k === 'granule_metadata' ? 'xml' : 'tif'}`)].sort());
    expectEq(problems, `${label}: ${id} all stored`, zip.entries.every((e) => e.stored), true);
    for (const key of wanted) {
      const ext = key === 'granule_metadata' ? 'xml' : 'tif';
      const entry = zip.entries.find((e) => e.name === `${id}_${key}.${ext}`);
      if (entry?.sha !== sha(bytesOf(`${id}/${key}.${ext}`, ASSETS[key]))) problems.push(`${label}: ${id}_${key} differs from what the source sent`);
    }
    if (!zip.attribution?.includes('Made-up data 2026')) problems.push(`${label}: ${id} ATTRIBUTION.txt has no attribution`);
    if (zip.attribution?.includes('Contains modified')) problems.push(`${label}: ${id} ATTRIBUTION.txt names modified data`);
    if (!zip.attribution?.includes(`Scene: ${id}`) || zip.attribution.includes(`${id === 'S2_A' ? 'S2_B' : 'S2_A'}`)) problems.push(`${label}: ${id} ATTRIBUTION.txt does not name this scene alone`);
    if (JSON.parse(zip.item ?? '{}').id !== id) problems.push(`${label}: ${id} item.json is not the item`);
  }
  expectEq(problems, `${label}: rows`, await rowStates(page), ['Done', 'Done']);
  const names = await page.$$eval('.dialog-original-name', (els) => els.map((e) => e.textContent));
  expectEq(problems, `${label}: row names`, names, ['S2_A.zip', 'S2_B.zip']);
  const theme_ = await page.evaluate(() => document.querySelector('.app')?.dataset.theme);
  if (theme_ !== THEMES[theme]) problems.push(`${label}: the app shows the theme ${theme_}`);
  await context.close();
  return { label, problems };
}

async function caseNoCors(browser, { why, cors, origin }) {
  const label = `no CORS (${why})`;
  const { context, page, problems } = await openApp(browser, { theme: 'light', viewport: 'wide', cors, sceneIds: ['S2_A', 'S2_B'], origin });
  const downloads = collectDownloads(page);
  await downloadButton(page).click();
  await waitRows(page, (s) => s.every((t) => t === 'Started in your browser'));
  await new Promise((resolve) => setTimeout(resolve, 2500));
  await settled(downloads);
  const names = downloads.map((d) => d.name).sort();
  // The files a browser would show instead of saving (the metadata) and the picture made from the bands are not sent.
  expectEq(problems, `${label}: files`, names, ['e2e_ATTRIBUTION.txt', ...Array(2).fill(['nir.tif', 'red.tif', 'scl.tif', 'visual.tif']).flat()].sort());
  expectEq(problems, `${label}: failures`, downloads.map((d) => d.failure).filter(Boolean), []);
  const attribution = downloads.find((d) => d.name.endsWith('_ATTRIBUTION.txt'));
  const text = attribution?.file ? fs.readFileSync(attribution.file, 'utf8') : '';
  if (!text.includes('Scenes: S2_A, S2_B') || !text.includes('red.tif (S2_A, asset red)') || text.includes('granule_metadata')) problems.push(`${label}: ATTRIBUTION.txt is not as expected`);
  const note = await page.locator('.dialog-originals .hint-text').nth(1).textContent();
  if (!/downloads each file/.test(note ?? '')) problems.push(`${label}: no note on the way, got ${JSON.stringify(note)}`);
  await layout(page, label, problems);
  await page.locator('.dialog-panel').screenshot({ path: path.join(OUT, `no-cors-${why.replace(/\W+/g, '_')}.png`) });
  await context.close();
  return { label, problems };
}

async function caseNoWorker(browser) {
  const label = 'no worker';
  const { context, page, problems } = await openApp(browser, { theme: 'light', viewport: 'wide', cors: true, sceneIds: ['S2_A'], origin: `https://localhost:${PORTS.cors}`, blockWorkers: true });
  const downloads = collectDownloads(page);
  await downloadButton(page).click();
  await waitRows(page, (s) => s.every((t) => t === 'Done'));
  await new Promise((resolve) => setTimeout(resolve, 1500));
  await settled(downloads);
  expectEq(problems, `${label}: files`, downloads.map((d) => d.name).sort(), ['S2_A_item.json', 'S2_A_nir.tif', 'S2_A_red.tif', 'S2_A_scl.tif', 'S2_A_visual.tif', 'S2_A_granule_metadata.xml', 'e2e_ATTRIBUTION.txt'].sort());
  const nir = downloads.find((d) => d.name === 'S2_A_nir.tif');
  if (nir?.file && sha(fs.readFileSync(nir.file)) !== sha(bytesOf('S2_A/nir.tif', ASSETS.nir))) problems.push(`${label}: S2_A_nir.tif differs from what the source sent`);
  const note = await page.locator('.dialog-originals .hint-text').nth(1).textContent();
  if (!/one by one/.test(note ?? '')) problems.push(`${label}: no note on the way, got ${JSON.stringify(note)}`);
  await layout(page, label, problems);
  await page.locator('.dialog-panel').screenshot({ path: path.join(OUT, 'no-worker.png') });
  await context.close();
  return { label, problems };
}

async function caseFailure(browser) {
  const label = 'a failure and a retry';
  const { context, page, problems } = await openApp(browser, { theme: 'light', viewport: 'wide', cors: true, sceneIds: ['S2_A', 'S2_B'], origin: `https://localhost:${PORTS.cors}` });
  const downloads = collectDownloads(page);
  control.fail.add('S2_A/red.tif');
  await downloadButton(page).click();
  await waitRows(page, (s) => s.every((t) => t === 'Done' || /^Failed/.test(t)));
  expectEq(problems, `${label}: rows`, await rowStates(page), ['Failed: The source answered 500.', 'Done']);
  control.fail.delete('S2_A/red.tif');
  await page.getByRole('button', { name: 'Retry failed' }).click();
  await waitRows(page, (s) => s.every((t) => t === 'Done'));
  await new Promise((resolve) => setTimeout(resolve, 500));
  await settled(downloads);
  const good = downloads.filter((d) => !d.failure).map((d) => d.name);
  if (!good.includes('S2_B.zip') || good.filter((n) => n === 'S2_A.zip').length !== 1) problems.push(`${label}: the ZIPs that finished are ${JSON.stringify(good)}`);
  if (good.filter((n) => n === 'S2_B.zip').length !== 1) problems.push(`${label}: the scene that finished was loaded again`);
  if (downloads.filter((d) => d.failure).length < 1) problems.push(`${label}: the browser did not report the broken ZIP as failed`);
  if (await page.getByRole('button', { name: 'Retry failed' }).count()) problems.push(`${label}: "Retry failed" stays after everything finished`);
  await context.close();
  return { label, problems };
}

async function caseStop(browser, how) {
  const label = `stop by ${how}`;
  const { context, page, problems } = await openApp(browser, { theme: 'light', viewport: 'wide', cors: true, sceneIds: ['S2_A', 'S2_B'], origin: `https://localhost:${PORTS.cors}` });
  const downloads = collectDownloads(page);
  control.slowMs = 60;
  control.sent.clear();
  await downloadButton(page).click();
  await waitRows(page, (s) => s.some((t) => /^Loading [1-9]/.test(t)));
  if (how === 'Cancel') {
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await waitRows(page, (s) => s.every((t) => t === 'Cancelled'), 10_000);
    expectEq(problems, `${label}: rows`, await rowStates(page), ['Cancelled', 'Cancelled']);
    if (!(await page.getByRole('button', { name: 'Retry failed' }).count())) problems.push(`${label}: no "Retry failed" after the stop`);
  } else {
    await page.getByTitle(/stops a download/).click();
  }
  const sentThen = [...control.sent.values()].reduce((a, b) => a + b, 0);
  await new Promise((resolve) => setTimeout(resolve, 1500));
  const sentLater = [...control.sent.values()].reduce((a, b) => a + b, 0);
  control.slowMs = 0;
  await settled(downloads);
  if (sentLater - sentThen > 200_000) problems.push(`${label}: the source went on sending (${sentLater - sentThen} bytes after the stop)`);
  if ([...control.sent.keys()].some((file) => file.startsWith('S2_B'))) problems.push(`${label}: the second scene was started`);
  if (downloads.some((d) => !d.failure)) problems.push(`${label}: a ZIP finished though it was stopped`);
  if (downloads.length !== 1) problems.push(`${label}: ${downloads.length} downloads, one expected`);
  await context.close();
  return { label, problems };
}

async function caseManyScenes(browser) {
  const label = 'many scenes (layout)';
  const ids = Array.from({ length: 14 }, (_, i) => `S2_${String.fromCharCode(65 + i)}`);
  const { context, page, problems } = await openApp(browser, { theme: 'dark', viewport: 'narrow', cors: false, sceneIds: ids, origin: `https://localhost:${PORTS.plain}` });
  await downloadButton(page).click();
  await page.waitForSelector('.dialog-original-row');
  await new Promise((resolve) => setTimeout(resolve, 800));
  await layout(page, label, problems);
  const rows = await page.$$eval('.dialog-original-row', (r) => r.length);
  expectEq(problems, `${label}: rows`, rows, 14);
  const list = await page.evaluate(() => { const l = document.querySelector('.dialog-original-rows'); return { scrolls: l.scrollHeight > l.clientHeight, fits: l.getBoundingClientRect().bottom <= innerHeight }; });
  if (!list.scrolls || !list.fits) problems.push(`${label}: the list does not scroll inside the window (${JSON.stringify(list)})`);
  await page.locator('.dialog-panel').screenshot({ path: path.join(OUT, 'many-scenes.png') });
  await context.close();
  return { label, problems };
}

async function caseRealScene(browser, itemFile) {
  const label = 'a whole real scene';
  const item = JSON.parse(fs.readFileSync(itemFile, 'utf8'));
  const host = new URL(item.assets.visual.href).hostname;
  const context = await browser.newContext({ viewport: VIEWPORTS.wide, acceptDownloads: true, ignoreHTTPSErrors: true });
  const page = await context.newPage();
  const problems = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE) return url.hostname === host ? route.continue() : route.abort();
    if (/^\/(src|@|node_modules|assets|__originals)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  await page.goto(BASE);
  await page.evaluate(
    async ({ item, host }) => {
      const { useAppStore } = await import('/src/store.ts');
      const units = ['coastal', 'blue', 'green', 'red', 'rededge1', 'rededge2', 'rededge3', 'nir', 'nir08', 'nir09', 'swir16', 'swir22', 'aot', 'wvp', 'cloud', 'snow', 'scl', 'visual', 'preview'];
      const collection = {
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', 'sci:doi': '10.5270/S2_-742ikth', 'earthx:format': 'cog', 'earthx:access': { cors: true },
        'earthx:source': { asset_hosts: [host] },
        'earthx:band_units': Object.fromEntries(units.map((k) => [k, k === 'visual' || k === 'preview' ? null : 'x'])),
        'earthx:auxiliary_assets': ['visual', 'preview'],
        'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
        'earthx:license_flags': { spdx_id: null, name: 'Sentinel Data Legal Notice', url: 'https://example.org/n', commercial_use: true, distribution: true, derivatives: true, share_alike: false, attribution_required: true, tier: 'processing', attribution_modified: 'Contains modified Copernicus Sentinel data {year}', attribution_unmodified: 'Copernicus Sentinel data {year}', terms_url: 'https://example.org/n', terms_notice: { en: 'Subject to {terms_url}.' } },
      };
      useAppStore.setState({
        datasets: [{ id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', viewable: true, groupBy: ['datetime'], zoom: { min: 8, max: 14 }, browse: 'quicklook', quicklookNodataMax: null, resultsGroupBy: ['datetime'], hasTimeAxis: true, collection }],
        dock: null, datasetId: 'sentinel-2-c1-l2a', items: [item], groups: [{ key: ['x'], label: 'x', items: [item] }], activeGroupIndex: 0, selectedIds: [item.id], aoi: null, layers: [], error: null,
      });
    },
    { item, host },
  );
  const downloads = collectDownloads(page);
  const rss = () => execSync("ps -eo rss,args | grep -E 'chrom(e|ium)' | grep -v grep || true").toString().split('\n').filter(Boolean).reduce((sum, line) => sum + Number(line.trim().split(/\s+/)[0]), 0) / 1024;
  const base = rss();
  let peak = base;
  const sampler = setInterval(() => (peak = Math.max(peak, rss())), 1000);
  const t0 = Date.now();
  await downloadButton(page).click();
  await waitRows(page, (s) => s.every((t) => t === 'Done' || /^Failed/.test(t)), 30 * 60_000);
  await settled(downloads);
  clearInterval(sampler);
  const seconds = (Date.now() - t0) / 1000;
  const zip = downloads[0]?.file ? zipEntries(downloads[0].file) : null;
  console.log(JSON.stringify({ case: label, files: downloads.map((d) => ({ name: d.name, failure: d.failure })), seconds, baseRssMB: Math.round(base), peakRssMB: Math.round(peak), entries: zip?.entries.length, crc: zip && zip.bad === null ? 'ok' : zip?.bad, stored: zip?.entries.every((e) => e.stored), zipMB: downloads[0]?.file ? Math.round(fs.statSync(downloads[0].file).size / 1e6) : null }));
  if (!zip || zip.bad !== null || !zip.entries.every((e) => e.stored)) problems.push(`${label}: the ZIP is not valid`);
  await context.close();
  return { label, problems };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'earthx-originals-tls-'));
  execFileSync('openssl', ['req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost', '-days', '2', '-keyout', path.join(dir, 'k.pem'), '-out', path.join(dir, 'c.pem')], { stdio: 'ignore' });
  const tls = { key: fs.readFileSync(path.join(dir, 'k.pem')), cert: fs.readFileSync(path.join(dir, 'c.pem')) };
  const servers = [await startSource(PORTS.cors, true, tls), await startSource(PORTS.plain, false, tls)];
  const proxy = process.env.REAL_ITEM && process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY, bypass: 'localhost,127.0.0.1' } : undefined;
  const browser = await chromium.launch({ proxy, args: ['--ignore-certificate-errors'] });
  const results = [];
  if (process.env.REAL_ITEM) {
    results.push(await caseRealScene(browser, process.env.REAL_ITEM));
  } else {
    for (const theme of ['light', 'dark']) for (const viewport of ['wide', 'narrow']) results.push(await caseZip(browser, { theme, viewport }));
    results.push(await caseNoCors(browser, { why: 'a dataset without CORS', cors: false, origin: `https://localhost:${PORTS.plain}` }));
    results.push(await caseNoCors(browser, { why: 'a source that does not allow it', cors: true, origin: `https://localhost:${PORTS.plain}` }));
    results.push(await caseNoWorker(browser));
    results.push(await caseFailure(browser));
    results.push(await caseStop(browser, 'Cancel'));
    results.push(await caseStop(browser, 'closing the dialog'));
    results.push(await caseManyScenes(browser));
  }
  await browser.close();
  for (const server of servers) server.close();
  for (const { label, problems } of results) console.log(`${problems.length ? 'FAIL' : 'ok  '} ${label}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
