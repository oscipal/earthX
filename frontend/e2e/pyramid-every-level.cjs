// A dataset with an overview pyramid (GLO-30, WorldCover; registry `viewer.overview: pyramid`, M5-30b part 9) keeps its picture when
// zoomed out, in a real browser, on the real `mapLayers.ts` and the real AOI clip, with a made-up tiler. A dataset released from z7
// in "Crop and merge to AOI" shows its mosaic from z7 (a 512-px mosaic of level 7 is drawn from map zoom 6.5) and the picture of its
// own pyramid below, over its scenes only: on the overview of their footprint selection, `/collections/{dataset}/overview/{id}/tiles/…`
// (M5-56, Otto 18.11.2026), never on the route of the whole area; the map zooms out from z10 to z0. It fails when
//   1. a tile is not asked for at the route of its level (the pyramid below 6.5, the mosaic from there on, the first step excepted);
//   2. a step draws nothing where the area lies (the area is 5 degrees wide: more than a pixel from z3 on);
//   3. the attribution line does not name the dataset's own text for modified data below 6.5, or names it above;
//   4. the loading display fails while the overview tiles come slowly: no busy toast with "Loading data" 0.6 s after a zoom out (also
//      with the layer manager open, MANAGER=open, where no row shows a loading mark since UI-09), or the toast stays when the tiles are in;
//   5. the mark "Overview" over the map (Otto, 16.11.2026, UI-08) is missing below 6.5 or there from 6.5 on, has another tooltip than the
//      one of a job's result, or another element that is not a tooltip says "overview".
//
//   cd frontend && npm run dev &            # a FRESH dev server; no backend is needed, the tiles are made up here
//   node e2e/pyramid-every-level.cjs        # BASE=http://localhost:5173 TILE_MS=900 MANAGER=open OUT=<directory for the screenshots>
//
// A second view, the search results (no "Crop and merge", adr/0032 Nachtrag 15.11.2026: a picture never disappears, in any view):
// four hits of the dataset on the map, the same zoom out from z10 to z0. Below 6.5 the picture is the overview of a footprint selection
// (`POST /collections/relief/overview/footprints`, then `/overview/{id}/tiles/…`, never the route without an id), from 6.5 on the hits'
// own tiles. It fails when
//   6. a tile is asked for at another route than that of its level, or the overview tile names another selection than the one the
//      tiler made for the four hits (sorted, made once), or the route without a selection is asked;
//   7. a step draws nothing where the hits lie, or the attribution line is not the pyramid's below 6.5 and none above, or the mark
//      "Overview" is not there below 6.5 and only there.
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersFootprints, answersSelection, hitsOfFootprints, isFootprintTile, isSelectionTile } = require('./selectionMock.cjs');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-pyramid-every-level');
const TILE_MS = Number(process.env.TILE_MS ?? 900);
const MANAGER_OPEN = process.env.MANAGER === 'open';
const TEXT = '© made up for the test; produced using made-up data';
const AOI_BOX = [6, 44, 11, 48];
const AOI = { type: 'Polygon', coordinates: [[[6, 44], [11, 44], [11, 48], [6, 48], [6, 44]]] };
const CENTRE = [8.5, 46];
const ZOOMS = [10, 8, 7, 6.5, 6, 5, 4, 3, 2, 1, 0];
const MOSAIC_FROM = 6.5;
// The one tooltip of the mark "Overview" (`components/PreviewBadge.tsx::OVERVIEW_TITLE`).
const OVERVIEW_TIP = 'Drawn coarser than the original data: zoom in for full resolution.';
const SCENES_FROM = 5.5;
const later = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function solid(rgba, size = 256) {
  const chunk = (type, data) => {
    const head = Buffer.alloc(8);
    head.writeUInt32BE(data.length, 0);
    head.write(type, 4, 'ascii');
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(zlib.crc32(Buffer.concat([head.subarray(4), data])), 0);
    return Buffer.concat([head, data, crc]);
  };
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: size }, () => rgba).flat())]);
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header.set([8, 6, 0, 0, 0], 8);
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: size }, () => row)))), chunk('IEND', Buffer.alloc(0))]);
}

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

async function run(browser, theme, results) {
  const problems = [];
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), theme);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  let asked = [];
  // The footprint selections made, by the part of the check that made them: the hits of the search, or the view ("Crop and merge").
  const posts = [];
  let phase = 'hits';
  let slow = false;
  const green = solid([0, 200, 0, 255]);
  const blue = solid([0, 0, 255, 255]);
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (answersSelection(route, url)) return;
    if (answersFootprints(route, url)) {
      posts.push({ phase, items: JSON.parse(route.request().postData() ?? '{}').items });
      return;
    }
    if (isFootprintTile(url.href)) {
      asked.push({ route: 'masked', z: Number(/\/tiles\/WebMercatorQuad\/(\d+)\//.exec(url.pathname)?.[1]), hits: hitsOfFootprints(url), selection: /\/overview\/([0-9a-f]{32})\//.exec(url.pathname)?.[1] });
      if (slow) await later(TILE_MS);
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: green });
    }
    if (/\/items\/[^/]+\/tiles\//.test(url.pathname)) {
      asked.push({ route: 'scene', z: Number(/\/tiles\/WebMercatorQuad\/(\d+)\//.exec(url.pathname)?.[1]) });
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: blue });
    }
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: [...AOI_BOX], minzoom: 7, maxzoom: 15, 'earthx:order': [] });
    const z = Number(/\/tiles\/WebMercatorQuad\/(\d+)\//.exec(url.pathname)?.[1]);
    if (url.pathname.includes('/overview/tiles/')) {
      asked.push({ route: 'overview', z });
      if (slow) await later(TILE_MS);
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: green });
    }
    if (isSelectionTile(url.href)) {
      asked.push({ route: 'mosaic', z });
      return route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body: blue });
    }
    if (url.pathname.includes('/statistics')) return json({ '1': { min: 0, max: 4000, percentile_2: 0, percentile_98: 3000, count: 9 } });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');
  await page.evaluate(async ({ aoi, open, text }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const items = Array.from({ length: 4 }, (_, i) => {
      const [x, y] = [6 + (i % 2) * 2.5, 44 + Math.floor(i / 2) * 2];
      return {
        id: `CELL_${i}`, collection: 'relief', bbox: [x, y, x + 2.5, y + 2],
        geometry: { type: 'Polygon', coordinates: [[[x, y], [x + 2.5, y], [x + 2.5, y + 2], [x, y + 2], [x, y]]] },
        properties: { datetime: '2021-01-01T00:00:00Z', 'earthx:state': 'latest' },
        assets: { data: { href: `https://assets.example.org/${i}.tif`, type: 'image/tiff; application=geotiff; profile=cloud-optimized' } },
      };
    });
    const collection = {
      id: 'relief', title: 'Relief model', 'earthx:format': 'cog',
      'earthx:capabilities': { roi: true, time_range: false, band_math: true, interpolation: true },
      'earthx:default_render': { title: 'Height', assets: ['data'], rescale: [[0, 4000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
      'earthx:viewer': { group_by: ['earthx:state'], min_zoom: 7, max_zoom: 15, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['earthx:state'], overview: 'pyramid', overview_resampling: 'average', overview_substitute: null },
      'earthx:license_flags': { tier: 'processing', attribution_required: true, attribution_modified: text, attribution_unmodified: text },
      extent: { spatial: { bbox: [[-180, -90, 180, 84]] }, temporal: { interval: [['2019-01-01T00:00:00Z', '2023-12-31T00:00:00Z']] } },
    };
    const groups = [{ key: ['latest'], label: 'latest', items }];
    useAppStore.setState({
      datasets: datasetsFrom([collection]), selectedDatasetIds: ['relief'], datasetId: 'relief', openSectionId: 'relief',
      sections: [{ datasetId: 'relief', items, groups, notes: [], groupingError: null, origin: 'search', incomplete: false }],
      items, groups, activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: items.map((it) => it.id), resultsOnMap: true,
      focusMode: false, downloaded: {}, layers: [], mosaics: {}, aoi, error: null, notice: null, dock: open ? 'layers' : null,
      flyToView: { center: [8.5, 46], zoom: 9 },
    });
  }, { aoi: AOI, open: MANAGER_OPEN, text: TEXT });
  await page.waitForTimeout(1500);
  phase = 'view';
  await page.evaluate(async () => (await import('/src/store.ts')).useAppStore.getState().enterFocus(true));
  await page.waitForTimeout(2500);

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
  const blueOrGreen = async () => {
    const points = await page.evaluate(([m, b]) => {
      const rect = m.getCanvas().getBoundingClientRect();
      const [w, s, e, n] = b;
      const out = [];
      for (let i = 1; i <= 5; i++) for (let j = 1; j <= 5; j++) {
        const p = m.project([w + ((e - w) * i) / 6, s + ((n - s) * j) / 6]);
        const [x, y] = [rect.left + p.x, rect.top + p.y];
        if (x > rect.left + 2 && x < rect.right - 2 && y > rect.top + 2 && y < rect.bottom - 2 && document.elementFromPoint(x, y) === m.getCanvas()) out.push([x, y]);
      }
      return out;
    }, [map, AOI_BOX]);
    const colours = [];
    for (const [x, y] of points) colours.push(await pixelAt(page, Math.round(x), Math.round(y)));
    return { points: points.length, drawn: colours.filter(([r, g, b]) => (b > 150 && r < 80 && g < 80) || (g > 150 && r < 80 && b < 80)).length };
  };
  // The mark "Overview" over the map: its tooltip, or null where there is none.
  const overviewMark = () => page.evaluate(() => {
    const badge = [...document.querySelectorAll('.preview-badge-dock .badge')].find((el) => el.textContent.trim() === 'Overview');
    return badge ? badge.getAttribute('data-tip') : null;
  });
  const markProblem = async (label, zoom) => {
    const tip = await overviewMark();
    if (zoom < MOSAIC_FROM && tip === null) return `${label}: no mark "Overview" below ${MOSAIC_FROM}`;
    if (zoom < MOSAIC_FROM && tip !== OVERVIEW_TIP) return `${label}: the mark "Overview" says ${JSON.stringify(tip)}`;
    if (zoom >= MOSAIC_FROM && tip !== null) return `${label}: the mark "Overview" is there from ${MOSAIC_FROM} on`;
    return null;
  };
  const attribution = () => page.$$eval('.maplibregl-ctrl-attrib-inner', (els) => els.map((el) => el.textContent).join(' '));

  for (const zoom of ZOOMS) {
    asked = [];
    await page.evaluate(([m, lon, lat, z]) => m.jumpTo({ center: [lon, lat], zoom: z }), [map, ...CENTRE, zoom]);
    await page.waitForTimeout(500);
    // Below the first level the view draws the overview of the footprint selection of its scenes, not of the whole area (M5-56).
    const wanted = zoom < MOSAIC_FROM ? 'masked' : 'mosaic';
    // A tile that an earlier step loaded is not asked for again: a request is certain only at a whole level the steps before did not draw.
    // Its first request can come later than 0.5 s when the page is busy (the layer manager open, M5-61): up to 3 s, then it fails.
    const certain = Number.isInteger(zoom) && zoom !== ZOOMS[0] && zoom >= 2;
    for (const until = Date.now() + 2500; certain && Date.now() < until && asked.every((request) => request.route !== wanted); ) await later(50);
    if (certain && asked.every((request) => request.route !== wanted)) problems.push(`z${zoom}: no tile of the ${wanted} was asked for`);
    const wrong = asked.filter((request) => request.route !== wanted && !(zoom === ZOOMS[0] && request.route === 'masked'));
    if (wrong.length) problems.push(`z${zoom}: tiles of the ${wrong[0].route} (z${wrong[0].z}) were asked for where the ${wanted} draws`);
    if (asked.some((request) => request.route === 'overview')) problems.push(`z${zoom}: the crop view asked for the overview of the whole area, not of its scenes`);
    if (zoom >= 3) {
      const seen = await blueOrGreen();
      if (seen.points === 0) problems.push(`z${zoom}: the area is not on the screen`);
      else if (seen.drawn < seen.points) problems.push(`z${zoom}: the map draws the area at ${seen.drawn} of ${seen.points} places`);
    }
    const mark = await markProblem(`z${zoom}`, zoom);
    if (mark) problems.push(mark);
    const credit = await attribution();
    if (zoom < MOSAIC_FROM && !credit.includes(TEXT)) problems.push(`z${zoom}: the attribution line does not name the dataset: ${JSON.stringify(credit.slice(0, 80))}`);
    if (zoom >= MOSAIC_FROM && credit.includes(TEXT)) problems.push(`z${zoom}: the attribution line names the pyramid above its levels`);
  }

  // The loading display with slow overview tiles: a zoom out to a level nothing was asked for yet.
  slow = true;
  await page.evaluate(([m, lon, lat]) => m.jumpTo({ center: [lon, lat], zoom: 8 }), [map, ...CENTRE]);
  await page.waitForTimeout(800);
  const shown = async () => (await page.$$eval('.status-stack .toast.busy', (els) => els.map((el) => el.textContent.trim()))).filter((t) => t === 'Loading data').length;
  const rows = () => page.locator('.layer-row [role="status"]:visible').count();
  for (const until = Date.now() + 8000; Date.now() < until && (await shown()) > 0; ) await later(100);
  // Tiles no step has loaded yet: one scene leaves the view, whose picture below the first level is then the overview of another
  // footprint selection (M5-56), and the map is zoomed out to a level of the overview.
  await page.evaluate((m) => m.jumpTo({ center: [8.5, 46], zoom: 4.2 }), map);
  await page.waitForTimeout(TILE_MS + 800);
  const begun = Date.now();
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    const { CELL_3: _left, ...rest } = useAppStore.getState().downloaded;
    useAppStore.setState({ downloaded: rest });
    await useAppStore.getState().loadMosaics();
  });
  let toast;
  let row = 0;
  for (const until = begun + TILE_MS + 3000; Date.now() < until; await later(50)) {
    if (toast === undefined && (await shown()) > 0) toast = Date.now() - begun;
    if (MANAGER_OPEN) row = Math.max(row, await rows());
  }
  if (toast === undefined) problems.push('after a zoom out onto slow overview tiles there was no "Loading data" toast');
  else if (toast < 450 || toast > 2500) problems.push(`the "Loading data" toast came after ${toast} ms (the threshold is 0.6 s; map-loading.cjs judges it closely)`);
  if (MANAGER_OPEN && row > 0) problems.push('the layer manager is open and a row shows a loading mark, which UI-09 took out of the rows');
  await page.waitForTimeout(TILE_MS + 800);
  if ((await shown()) > 0) problems.push('the "Loading data" toast stays when the overview tiles are in');
  slow = false;
  // Away from the area, so that no level of the search results below is loaded before it is looked at.
  await page.evaluate((m) => m.jumpTo({ center: [-100, 20], zoom: 4.2 }), map);
  console.log(`${theme}${MANAGER_OPEN ? ' (manager open)' : ''}: toast after ${toast ?? '-'} ms, row mark ${MANAGER_OPEN ? (row > 0 ? 'yes' : 'no') : 'not looked at'}`);

  // The search results: leave the full-resolution view, the four hits are on the map as the results of a search.
  await page.evaluate(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().exitFocus();
    useAppStore.setState({ resultsOnMap: true, downloaded: {}, mosaics: {} });
  });
  phase = 'hits';
  const ofView = posts.filter((post) => post.phase === 'view').map((post) => post.items);
  if (!ofView.some((items) => JSON.stringify(items) === JSON.stringify(Array.from({ length: 4 }, (_, i) => `CELL_${i}`)))) problems.push(`the view made no footprint selection of its four scenes: ${JSON.stringify(ofView)}`);
  await page.waitForTimeout(1500);
  const hitIds = Array.from({ length: 4 }, (_, i) => `CELL_${i}`).sort();
  for (const zoom of ZOOMS) {
    asked = [];
    await page.evaluate(([m, lon, lat, z]) => m.jumpTo({ center: [lon, lat], zoom: z }), [map, ...CENTRE, zoom]);
    await page.waitForTimeout(600);
    const label = `search results z${zoom}`;
    const wanted = zoom < MOSAIC_FROM ? 'masked' : 'scene';
    if (Number.isInteger(zoom) && zoom !== ZOOMS[0] && zoom >= 2 && asked.every((request) => request.route !== wanted)) problems.push(`${label}: no tile of the ${wanted} was asked for`);
    // The hits' own previews are 256-px tiles of level 7: asked for from map zoom 5.5, under the overview until it steps aside at 6.5.
    const allowed = (request) => (request.route === 'masked' ? zoom < MOSAIC_FROM || zoom === ZOOMS[0] : zoom >= SCENES_FROM);
    const wrong = asked.filter((request) => !allowed(request));
    if (wrong.length) problems.push(`${label}: tiles of the ${wrong[0].route} (z${wrong[0].z}) were asked for where the ${wanted} draws`);
    for (const request of asked.filter((r) => r.route === 'masked')) {
      if (JSON.stringify(request.hits) !== JSON.stringify(hitIds)) problems.push(`${label}: the overview tile names a selection of ${JSON.stringify(request.hits)}, not of the four hits`);
    }
    if (zoom >= 3) {
      const seen = await blueOrGreen();
      if (seen.points === 0) problems.push(`${label}: the hits are not on the screen`);
      else if (seen.drawn < seen.points) problems.push(`${label}: the map draws the hits at ${seen.drawn} of ${seen.points} places`);
    }
    const mark = await markProblem(label, zoom);
    if (mark) problems.push(mark);
    const credit = await attribution();
    if (zoom < MOSAIC_FROM && !credit.includes(TEXT)) problems.push(`${label}: the attribution line does not name the dataset`);
    if (zoom >= MOSAIC_FROM && credit.includes(TEXT)) problems.push(`${label}: the attribution line names the pyramid above its levels`);
  }
  const ofHits = posts.filter((post) => post.phase === 'hits').map((post) => post.items);
  if (ofHits.length === 0) problems.push('search results: no footprint selection was made for the hits');
  if (ofHits.some((items) => JSON.stringify(items) !== JSON.stringify(hitIds))) problems.push(`search results: a footprint selection was made for ${JSON.stringify(ofHits)}, not for the four hits sorted`);
  if (ofHits.length > 1) problems.push(`search results: the footprint selection was made ${ofHits.length} times for the same hits`);
  console.log(`${theme}${MANAGER_OPEN ? ' (manager open)' : ''}: search results, ${ofHits.length} footprint selection(s) for ${hitIds.length} hits`);

  // One mark only: nothing else that is not a tooltip says "overview".
  await page.evaluate(([m, lon, lat]) => m.jumpTo({ center: [lon, lat], zoom: 3 }), [map, ...CENTRE]);
  await page.waitForTimeout(600);
  const texts = await page.evaluate(() =>
    [...document.querySelectorAll('body *')]
      .filter((el) => el.children.length === 0 && /overview/i.test(el.textContent ?? '') && !el.closest('[data-tip]') && !el.closest('.preview-badge-dock'))
      .map((el) => el.textContent.trim().slice(0, 60)),
  );
  if (texts.length) problems.push(`the page says overview elsewhere: ${JSON.stringify(texts)}`);
  await page.screenshot({ path: path.join(OUT, `${theme}-z3.png`) });
  results.push({ name: theme, problems });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch({ args: ['--use-angle=swiftshader', '--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] });
  const results = [];
  for (const theme of ['normal', 'tech']) await run(browser, theme, results);
  await browser.close();
  for (const { name, problems } of results) console.log(`${problems.length === 0 ? 'ok  ' : 'FAIL'} ${name}${problems.length ? `\n  - ${problems.join('\n  - ')}` : ` (${ZOOMS.length} levels, z10 to z0)`}`);
  console.log(`screenshots: ${OUT}`);
  process.exit(results.some((r) => r.problems.length) ? 1 : 0);
})();
