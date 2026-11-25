// Browser check of M5-69: an AOI "Point" is a point everywhere. With made-up answers it does the clicks of a user in a real
// browser and fails when
//   1. the tool "Point" does not give a point as the AOI;
//   2. the search with "AOI coverage" is not asked with the point as `intersects` (or carries it in a URL);
//   3. "Download crop" does not send the point as the AOI;
//   4. a processing job with one step ("AOI only") is not ordered on the point;
//   5. "Crop to AOI" does not ask the pixel of the point, does not come close to it, or shows the picture outside that one
//      pixel: the made-up tiles are pure red, so red at the point and nothing red one pixel beside it;
//   6. the page scrolls sideways;
// at 1280 × 800 and 360 × 740, with a screenshot per step.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/m5-69-point.cjs                # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-m5-69-point');
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const S2 = 'sentinel-2-c1-l2a';
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', `${S2}.json`), 'utf8'));
// Half a pixel of about 10 m, in degrees.
const HALF = [0.00007, 0.000045];

const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
const COLLECTION = {
  id: S2, type: 'Collection', title: 'Sentinel-2 L2A', description: 'made up', license: 'proprietary', links: [],
  extent: { spatial: { bbox: [[-180, -90, 180, 90]] }, temporal: { interval: [['2015-06-27T00:00:00Z', null]] } },
  'earthx:format': 'cog', 'earthx:license_flags': { tier: 'processing' },
  'earthx:capabilities': { roi: true, band_math: true, interpolation: true, ml_processing: true, quad_pol: false, time_range: true, single_coverage_product: false },
  'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 22, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['datetime'] },
  'earthx:default_render': { title: 'Red', assets: ['red'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
  'earthx:search_filters': [],
  'earthx:search_capabilities': { evaluate: false, aoi_coverage: true },
  'earthx:band_units': { red: '1', nir: '1' },
};
const BANDS = {
  bands: [['red', 'B04', 'red', 0.665], ['nir', 'B08', 'nir', 0.842]].map(([asset, name, common, wavelength]) => ({
    asset, name, common_name: common, wavelength_um: wavelength, resolution_m: 10, data_type: 'uint16', scale: null, offset: null, nodata: 0,
    unit: '1', categorical: false, preselected: true,
  })),
};

// A tile of pure red, 256 px.
const PNG = (() => {
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: 256 }, () => [255, 0, 0, 255]).flat())]);
  const chunk = (type, data) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, 'ascii');
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, crc]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(256, 0);
  header.writeUInt32BE(256, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: 256 }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
})();

async function pixelAt(page, x, y) {
  const png = await page.screenshot({ clip: { x, y, width: 1, height: 1 } });
  let at = 8;
  let colourType = 2;
  const data = [];
  while (at < png.length) {
    const length = png.readUInt32BE(at);
    const type = png.toString('ascii', at + 4, at + 8);
    if (type === 'IHDR') colourType = png[at + 8 + 9];
    if (type === 'IDAT') data.push(png.subarray(at + 8, at + 8 + length));
    at += 12 + length;
  }
  const raw = zlib.inflateSync(Buffer.concat(data));
  return colourType === 6 || colourType === 2 ? [raw[1], raw[2], raw[3]] : [raw[1], raw[1], raw[1]];
}
const red = ([r, g, b]) => r > 200 && g < 60 && b < 60;

async function check(browser, viewport) {
  const problems = [];
  const seen = { search: [], pixel: [], download: [], execution: [], urls: [] };
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  page.on('request', (request) => seen.urls.push(request.url()));
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/stac/collections') return json({ collections: [COLLECTION] });
    if (url.pathname === '/stac/search') {
      const body = JSON.parse(request.postData() ?? '{}');
      seen.search.push(body);
      const [x, y] = body.intersects?.coordinates ?? [0, 0];
      const box = [x - 0.4, y - 0.4, x + 0.4, y + 0.4];
      const asset = (key) => ({ href: `https://example.invalid/${key}.tif`, type: COG, gsd: 10, 'raster:bands': [{ data_type: 'uint16', nodata: 0 }] });
      const scene = {
        type: 'Feature', id: 'S2B_POINT', collection: S2, bbox: box,
        geometry: { type: 'Polygon', coordinates: [[[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]], [box[0], box[1]]]] },
        properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { red: asset('red'), nir: asset('nir') }, links: [],
      };
      return json({ type: 'FeatureCollection', features: [scene], numberReturned: 1, links: [], 'earthx:aoi_filter': { checked: 1, found: 1, unreadable: 0, limit_reached: false } });
    }
    if (url.pathname.startsWith('/coverage/')) {
      return json({ dataset_id: S2, grid: 'geotile', level: 4, counting: 'centroid', cells: [], counted: 0, total_count: 0, completeness: 'complete', max_count: 0, histogram: [], histogram_interval: 'month', footprints_advised: false, from_cache: false, extent: null, area: null, ignored_filters: [] });
    }
    if (url.pathname === `/collections/${S2}/pixel`) {
      const body = JSON.parse(request.postData() ?? '{}');
      seen.pixel.push(body);
      const [x, y] = body.point.coordinates;
      const ring = [[x - HALF[0], y - HALF[1]], [x + HALF[0], y - HALF[1]], [x + HALF[0], y + HALF[1]], [x - HALF[0], y + HALF[1]], [x - HALF[0], y - HALF[1]]];
      return json({ pixels: body.groups.map(() => ({ type: 'Polygon', coordinates: [ring] })) });
    }
    if (url.pathname.endsWith('/bands')) return json(BANDS);
    if (url.pathname.endsWith('/download')) {
      seen.download.push(JSON.parse(request.postData() ?? '{}'));
      return route.fulfill({ status: 200, contentType: 'application/zip', headers: { 'x-total-groups': '1', 'x-skipped-groups': '0' }, body: 'PK' });
    }
    if (url.pathname.includes('/tiles/')) return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (url.pathname.endsWith('/estimate')) {
      return json({ estimate: { size: 8, duration: 'PT1S', outputPixels: 1, inputPixels: 1, inputBytes: 4, assets: 2, units: 1 }, skippedItems: [] });
    }
    if (url.pathname.endsWith('/execution')) {
      seen.execution.push(JSON.parse(request.postData() ?? '{}').inputs.recipe);
      return json({ processID: 'recipe', type: 'process', jobID: 'QrStUvWxYzAbCdEfGhIj_-', status: 'accepted', message: '', progress: 0, created: '2026-11-25T10:00:00Z', expires: new Date(Date.now() + 7 * 86_400_000).toISOString(), recipeID: 'r', links: [] }, 201);
    }
    return json({ detail: 'not made up' }, 404);
  });
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${viewport}_${step}.png`) });
  const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${what}${detail ? `: ${detail}` : ''}`); };
  const store = (fn, arg) => page.evaluate(async ([src, data]) => {
    const { useAppStore } = await import('/src/store.ts');
    return (0, eval)(`(${src})`)(useAppStore, data);
  }, [fn.toString(), arg]);
  const until = async (what, test, ms = 10000) => {
    for (let waited = 0; waited < ms; waited += 150) {
      if (await test()) return true;
      await page.waitForTimeout(150);
    }
    expect(what, false);
    return false;
  };
  const dock = async (open) => store((s, o) => s.setState({ dock: o ? 'controls' : null }), open);

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await page.locator('.dataset-toggle', { hasText: 'Sentinel-2 L2A' }).first().click();
  await store((s) => s.getState().flyTo([7.3, 46.8, 7.6, 47.0]));
  await page.waitForTimeout(1500);

  // 1. The tool "Point" gives a point.
  await page.getByRole('group', { name: 'Area of interest tools' }).getByRole('button', { name: 'Point', exact: true }).click();
  await dock(false);
  await page.waitForTimeout(300);
  const canvas = await page.locator('.maplibregl-canvas').boundingBox();
  await page.mouse.click(Math.round(canvas.x + canvas.width / 2), Math.round(canvas.y + canvas.height / 2));
  await page.waitForTimeout(500);
  const aoi = await store((s) => s.getState().aoi);
  expect('the tool "Point" gives a point as the AOI', aoi?.type === 'Point', JSON.stringify(aoi));
  await shot('1-point');

  // 2. A search with "AOI coverage" asks with the point.
  await dock(true);
  await page.locator('.advanced-btn').click();
  const coverage = page.locator('.advanced-popup .filter-coverage');
  await coverage.waitFor();
  expect('"AOI coverage" is free for a point', !(await coverage.locator('input[type="text"]').isDisabled()));
  await coverage.locator('input[type="text"]').fill('50');
  await coverage.locator('input[type="text"]').press('Enter');
  await page.locator('.advanced-popup .advanced-top .close-x').click();
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await until('the search is asked', () => seen.search.length > 0);
  const asked = seen.search[0] ?? {};
  expect('the search asks with the point', asked.intersects?.type === 'Point' && !asked.bbox, JSON.stringify(asked.intersects ?? asked.bbox));
  expect('the search asks "AOI coverage"', JSON.stringify(asked).includes('earthx:aoi_coverage'), JSON.stringify(asked.query_by_collection ?? asked.query));
  await until('the scene is found', async () => (await store((s) => s.getState().items.length)) === 1);
  await shot('2-search');

  // 3. "Download crop" sends the point.
  await store((s) => s.setState({ selectedIds: ['S2B_POINT'], dock: null }));
  await page.getByRole('button', { name: 'Download crop' }).click();
  const confirm = page.locator('.dialog-actions button.btn.primary', { hasText: 'Download' }).first();
  await until('the dialog can download', async () => (await confirm.count()) > 0 && !(await confirm.isDisabled()));
  await shot('3-download');
  await confirm.click();
  await until('the crop is asked', () => seen.download.length > 0);
  expect('the crop is asked for the point', seen.download[0]?.aoi?.type === 'Point', JSON.stringify(seen.download[0]?.aoi));
  await page.keyboard.press('Escape');
  await store((s) => s.setState({ selectedIds: ['S2B_POINT'], downloadDialogLayerId: null, downloadSelection: false }));

  // 4. A processing job with one step, "AOI only", is ordered on the point.
  await page.getByRole('button', { name: 'Process' }).click();
  const panel = page.locator('.processing-panel');
  await panel.waitFor();
  const only = panel.getByRole('button', { name: 'AOI only' });
  if ((await only.count()) > 0) await only.click();
  await panel.getByRole('button', { name: /Band math/ }).first().click();
  await page.locator('textarea[id$="-expression"]').fill('(nir - red) / (nir + red)');
  await shot('4-processing');
  await panel.getByRole('button', { name: 'Review', exact: true }).click();
  await until('the job can start', async () => (await panel.locator('button.btn.primary:not([disabled])', { hasText: 'Start job' }).count()) > 0);
  await panel.locator('button.btn.primary', { hasText: 'Start job' }).click();
  await until('the job is placed', () => seen.execution.length > 0);
  expect('the job is ordered on the point', seen.execution[0]?.aoi?.type === 'Point', JSON.stringify(seen.execution[0]?.aoi));
  await page.evaluate(async () => (await import('/src/processingStore.ts')).useProcessingStore.getState().closeProcessing());

  // 5. "Crop to AOI" shows the one pixel at the point.
  await store((s) => s.setState({ selectedIds: ['S2B_POINT'], dock: null }));
  await page.getByRole('button', { name: 'Crop to AOI' }).click();
  await until('the pixel of the point is asked', () => seen.pixel.length > 0);
  expect('the pixel is asked with the point in the body', seen.pixel[0]?.point?.type === 'Point' && !seen.urls.some((u) => /point|coordinates/.test(new URL(u).search)));
  await until('the map comes close to the pixel', async () => (await store((s) => s.getState().pixelOutlines)) > 0);
  // In a narrow window the sheet of the settings lies over the map; it is folded down to see the pixel.
  const fold = page.getByRole('button', { name: 'Fold the settings down' });
  if (viewport === 'narrow' && (await fold.count()) > 0) await fold.click();
  await page.waitForTimeout(3500);
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
  const spots = await page.evaluate(([m, p, half]) => {
    const rect = m.getCanvas().getBoundingClientRect();
    const at = (lon, lat) => { const q = m.project([lon, lat]); return [Math.round(rect.left + q.x), Math.round(rect.top + q.y)]; };
    const [x, y] = p.coordinates;
    // Inside the pixel, beside the circle that marks the point.
    return { zoom: m.getZoom(), centre: at(x + 0.6 * half[0], y + 0.6 * half[1]), east: at(x + 3 * half[0], y), south: at(x, y - 3 * half[1]), width: at(x + half[0], y)[0] - at(x - half[0], y)[0] };
  }, [map, aoi, HALF]);
  expect('the map comes close enough to see the pixel', spots.width >= 20, JSON.stringify(spots));
  expect('the picture is there at the point', red(await pixelAt(page, ...spots.centre)), JSON.stringify(spots));
  expect('the picture ends with the pixel (east)', !red(await pixelAt(page, ...spots.east)));
  expect('the picture ends with the pixel (south)', !red(await pixelAt(page, ...spots.south)));
  expect('the page scrolls sideways', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1));
  await shot('5-crop-one-pixel');

  await context.close();
  return problems.map((problem) => `${viewport}: ${problem}`);
}

(async () => {
  const browser = await chromium.launch();
  const problems = [];
  for (const viewport of Object.keys(VIEWPORTS)) problems.push(...(await check(browser, viewport)));
  await browser.close();
  if (problems.length > 0) {
    console.error(problems.join('\n'));
    process.exit(1);
  }
  console.log(`m5-69-point: all checks passed; screenshots in ${OUT}`);
})();
