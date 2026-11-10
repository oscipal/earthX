// DS-04c in a real browser, with made-up scenes and no backend (Otto's browser check of 9.11.2026):
//   1. After a search a Sentinel-1-like dataset shows its preview: the tiles of the band each scene carries (`vv` for a
//      VV scene, `hh` for an HH scene, `first_present`), not the thumbnail in radar geometry the map cannot place (the
//      results list still shows it beside the scene).
//   2. Its notices are no mark anywhere (Otto, 10.11.2026): not in the results, not in the head of the view, not in the list
//      of the Data catalogue; its details say them in the row "Limitations", and name the row "Citation" where there is no DOI.
//   3. "Crop and merge to AOI" over two scenes of one pass draws one outline around the merged picture and no scene
//      boundary across it: two Sentinel-1 slices whose footprints almost meet (the double line Otto saw), and two
//      Sentinel-2 tiles that overlap.
// Light and dark theme, a wide and a narrow window; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/s1-pass.cjs                    # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-s1-pass');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const PNG = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==', 'base64');

// Two slices of one pass in the shape Earth Search gives them (synthetic numbers): the top edge of the southern one and
// the bottom edge of the northern one lie a few thousandths of a degree apart, now overlapping, now leaving a gap.
const SOUTH = [[[10, 47], [13, 47.3], [12.9, 48.5], [11.5, 48.35], [9.9, 48.2], [10, 47]]];
const NORTH = [[[9.904, 48.197], [10.7, 48.2785], [11.497, 48.354], [12.904, 48.498], [12.8, 49.7], [9.8, 49.4], [9.904, 48.197]]];
const AOI = { type: 'Polygon', coordinates: [[[10.5, 47.8], [12.5, 47.8], [12.5, 49], [10.5, 49], [10.5, 47.8]]] };
const LIMITATIONS = [
  'Placed only by the ground control points of each scene, without terrain correction; this holds for every pixel, not only the preview.',
  'Values are uncalibrated digital numbers (DN), not calibrated backscatter.',
];
const NOTICES = [
  { code: 'approximate_geolocation', label: 'Approximate geolocation', tooltip: "Placed by the scene's own ground control points without terrain correction." },
  { code: 'uncalibrated_dn', label: 'Uncalibrated (DN)', tooltip: 'Values are the digital numbers of the GRD product, not calibrated backscatter.' },
];

async function run(browser, theme, viewport, results) {
  const name = `${theme} ${viewport}`;
  const problems = [];
  const win = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: win });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  const tiles = [];
  const thumbnails = [];
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.pathname.endsWith('quick-look.png')) {
      thumbnails.push(url.pathname);
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    }
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: [9.8, 47, 13, 49.7], minzoom: 7, maxzoom: 14, 'earthx:order': [] });
    if (url.pathname.includes('/statistics')) return json({ '1': { min: 0, max: 900, percentile_2: 80, percentile_98: 260, count: 9 } });
    if (url.pathname.includes('/tiles/')) {
      tiles.push(`${url.pathname.split('/items/')[1]?.split('/')[0] ?? 'mosaic'} ${url.searchParams.get('asset')}`);
      return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');

  await page.evaluate(async ({ south, north, notices, LIMITATIONS }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const bbox = (ring) => [Math.min(...ring.map((p) => p[0])), Math.min(...ring.map((p) => p[1])), Math.max(...ring.map((p) => p[0])), Math.max(...ring.map((p) => p[1]))];
    const host = 'https://assets.example.org';
    const radarItem = (id, coordinates, bands, day = '2026-10-18') => ({
      id, collection: 'radar', bbox: bbox(coordinates[0]), geometry: { type: 'Polygon', coordinates },
      properties: { datetime: `${day}T16:58:00Z`, 's1:datatake_id': day === '2026-10-18' ? '1' : '2' },
      assets: {
        ...Object.fromEntries(bands.map((band) => [band, { href: `${host}/${id}/${band}.tif`, type: COG }])),
        thumbnail: { href: `${host}/${id}/preview/quick-look.png`, type: 'image/png', roles: ['thumbnail'] },
      },
    });
    const pass = [radarItem('SLICE_SOUTH', south, ['vv', 'vh']), radarItem('SLICE_NORTH', north, ['vv', 'vh'])];
    const polar = [radarItem('SLICE_HH', south, ['hh', 'hv'], '2026-10-19')];
    const items = [...pass, ...polar];
    const radar = {
      id: 'radar', title: 'Sentinel-1 GRD', 'earthx:category': 'radar', 'earthx:format': 'cog',
      'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'Co-polarisation (VV or HH)', assets: ['vv', 'hh'], rescale: [[90, 250], [70, 750]], colormap_name: null, expression: null, resampling: 'nearest', asset_selection: 'first_present' },
      'earthx:viewer': { group_by: ['datetime', 's1:datatake_id'], min_zoom: 7, max_zoom: 14, browse: 'preview_tiles', quicklook_nodata_max: null, results_group_by: ['datetime', 's1:datatake_id'] },
      'earthx:license_flags': { tier: 'processing', license: 'proprietary' },
      'earthx:source': { asset_hosts: ['assets.example.org'] },
      'earthx:notices': notices,
      description: 'Sentinel-1 C-band SAR, Level-1 Ground Range Detected, in radar geometry.',
      'earthx:limitations': LIMITATIONS,
      'sci:doi': null,
      'sci:citation': 'Copernicus Sentinel-1 Level-1 GRD',
      extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2014-10-10T00:00:00Z', null]] } },
    };
    const groups = [
      { key: ['2026-10-18', '1'], label: '18 Oct 2026', items: pass },
      { key: ['2026-10-19', '2'], label: '19 Oct 2026', items: polar },
    ];
    useAppStore.setState({
      datasets: datasetsFrom([radar]), addedDatasetIds: ['radar'], selectedDatasetIds: ['radar'], datasetId: 'radar', openSectionId: 'radar',
      sections: [{ datasetId: 'radar', items, groups, notes: [] }], items, groups, activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: [],
      resultsOnMap: true, focusMode: false, downloaded: {}, layers: [], mosaics: {}, error: null, aoi: null, dock: 'results',
      flyToView: { center: [11.4, 48.3], zoom: 7.5 },
    });
  }, { south: SOUTH, north: NORTH, notices: NOTICES, LIMITATIONS });

  const st = (expr) => page.evaluate(async (e) => { const { useAppStore } = await import('/src/store.ts'); return new Function('s', `return ${e}`)(useAppStore.getState()); }, expr);
  const set = (patch) => page.evaluate(async (p) => { const { useAppStore } = await import('/src/store.ts'); useAppStore.setState(p); }, patch);
  const shot = (what) => page.screenshot({ path: path.join(OUT, `${name} ${what}.png`) });
  // The map of the app: its ref lives in the hooks of `MapView`; nothing of the app is changed to reach it (as `map-gl6.cjs`).
  const map = await page.evaluateHandle(() => {
    const el = document.querySelector('.maplibregl-map');
    let fiber = el[Object.keys(el).find((k) => k.startsWith('__reactFiber$'))];
    for (; fiber; fiber = fiber.return) {
      for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
        const held = hook.memoizedState?.current;
        if (held && typeof held.getStyle === 'function') return held;
      }
    }
    return null;
  });
  // The outline of the merged pass: its rings, and its corners that lie inside the AOI. Both scenes together cover the
  // whole AOI, so the outline is the edge of the AOI alone: a corner inside it is a scene boundary drawn across the picture
  // (a second ring, or a slit cut into the one ring, both seen as a double line).
  const outline = () => page.evaluate(([m, aoi]) => {
    const features = m.getSource('mosaicsel-src')?.serialize().data?.features ?? [];
    const rings = features.flatMap((f) => (f.geometry.type === 'Polygon' ? f.geometry.coordinates : f.geometry.coordinates.flat()));
    const [[x0, y0], , [x1, y1]] = aoi.coordinates[0];
    const inside = rings.flat().filter(([x, y]) => x > x0 + 1e-9 && x < x1 - 1e-9 && y > y0 + 1e-9 && y < y1 - 1e-9);
    return { rings: rings.length, inside: inside.length };
  }, [map, AOI]);

  // --- 1. the preview after the search -----------------------------------------------------------------------------
  await page.waitForTimeout(1500);
  const asked = (scene, band) => tiles.some((t) => t === `${scene} ${band}`);
  if (!asked('SLICE_SOUTH', 'vv') || !asked('SLICE_NORTH', 'vv')) problems.push(`no preview tiles of vv for the VV pass (asked: ${[...new Set(tiles)].join(', ') || 'none'})`);
  // The results list shows the thumbnail beside each scene; the map places none of it.
  const placed = await page.evaluate((m) => Object.values(m.getStyle().sources).filter((source) => source.type === 'image').length, map);
  if (placed > 0) problems.push(`the thumbnail in radar geometry lies on the map (${placed} image sources)`);
  if (thumbnails.length === 0) problems.push('the results list shows no thumbnail');
  await shot('preview vv');
  await set({ activeGroupIndex: 1, expandedGroupIndex: 1 });
  await page.waitForTimeout(1200);
  if (!asked('SLICE_HH', 'hh')) problems.push('no preview tiles of hh for the HH scene');
  if (tiles.some((t) => t === 'SLICE_HH vv')) problems.push('the HH scene was asked for vv');

  // --- 2. the notices ------------------------------------------------------------------------------------------------
  // No text of a notice anywhere in the page, whatever element would hold it.
  const expectNoNotices = async (where) => {
    const text = await page.evaluate(() => document.body.innerText);
    for (const notice of NOTICES) if (text.includes(notice.label) || text.toUpperCase().includes(notice.label.toUpperCase())) problems.push(`${where}: "${notice.label}" is shown`);
  };
  await expectNoNotices('results');
  await shot('results');

  // --- 3. "Crop and merge to AOI" over the two slices of one pass ------------------------------------------------------
  await set({ activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: ['SLICE_SOUTH', 'SLICE_NORTH'], aoi: AOI });
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().enterFocus(true));
  await page.waitForSelector('.inspector .vc-head');
  await page.waitForTimeout(800);
  const viewed = await st('Object.values(s.downloaded).map((d) => d.asset).join()');
  if (viewed !== 'vv,vv') problems.push(`the view draws ${viewed}`);
  const merged = await outline();
  if (merged.rings !== 1 || merged.inside > 0) problems.push(`the outline of the merged pass has ${merged.rings} rings and ${merged.inside} corners inside the AOI (a scene boundary across it)`);
  await expectNoNotices('view');
  await page.evaluate((m) => m.jumpTo({ center: [11.5, 48.4], zoom: 8 }), map);
  await page.waitForTimeout(800);
  await shot('merged pass');

  // The same for two tiles of an optical pass that overlap (Sentinel-2): one ring, as before.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const s = useAppStore.getState();
    s.exitFocus();
    const tile = (id, x0) => ({ ...s.items[0], id, bbox: [x0, 47.5, x0 + 1.2, 48.6], geometry: { type: 'Polygon', coordinates: [[[x0, 47.5], [x0 + 1.2, 47.5], [x0 + 1.2, 48.6], [x0, 48.6], [x0, 47.5]]] } });
    const pass = [tile('TILE_WEST', 10.6), tile('TILE_EAST', 11.6)];
    const groups = [{ key: ['2026-10-18', '1'], label: '18 Oct 2026', items: pass }];
    useAppStore.setState({ items: pass, groups, sections: [{ datasetId: 'radar', items: pass, groups, notes: [] }], selectedIds: ['TILE_WEST', 'TILE_EAST'], activeGroupIndex: 0, expandedGroupIndex: 0 });
    await useAppStore.getState().enterFocus(true);
  });
  await page.waitForTimeout(800);
  const tiles2 = await outline();
  if (tiles2.rings !== 1) problems.push(`the outline of two overlapping tiles has ${tiles2.rings} rings`);

  // --- the Data catalogue -------------------------------------------------------------------------------------------------
  await page.evaluate(async () => { const { useAppStore } = await import('/src/store.ts'); useAppStore.getState().exitFocus(); useAppStore.setState({ catalogueOpen: true }); });
  await page.waitForSelector('#data-catalogue');
  const entry = page.locator('.catalogue-entry', { hasText: 'Sentinel-1 GRD' });
  await entry.locator('.catalogue-entry-name').click();
  // The list holds no notice; the details say the limitations, one sentence each, and "Citation" for a dataset without a DOI.
  if ((await page.locator('.catalogue-entry .badge').count()) !== 0) problems.push('the list of the catalogue shows a mark');
  const row = (label) => page.locator('.catalogue-row-pair').filter({ has: page.locator('dt', { hasText: new RegExp(`^${label}$`) }) });
  const limits = await row('Limitations').locator('dd .catalogue-value').allInnerTexts();
  if (JSON.stringify(limits) !== JSON.stringify(LIMITATIONS)) problems.push(`the row "Limitations" says ${JSON.stringify(limits)}`);
  if ((await row('DOI').count()) !== 0) problems.push('a row "DOI" without a DOI');
  if ((await row('Citation').innerText()).indexOf('Copernicus Sentinel-1 Level-1 GRD') < 0) problems.push('no row "Citation"');
  for (const label of NOTICES.map((n) => n.label)) {
    if ((await page.locator('#data-catalogue').innerText()).toUpperCase().includes(label.toUpperCase())) problems.push(`the catalogue shows "${label}"`);
  }
  await shot('catalogue');

  results.push({ name, problems });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  for (const theme of Object.keys(THEMES)) for (const viewport of Object.keys(VIEWPORTS)) await run(browser, theme, viewport, results);
  await browser.close();
  for (const { name, problems } of results) console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ''}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
