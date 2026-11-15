// A computed picture keeps its place when the map zooms out (M5-10 part B, Otto 15.11.2026): in a real browser, on the real
// `mapLayers.ts`, `processingPreview.ts` and store, with a made-up tiler. A dataset with a pyramid, released from z7, is shown in five
// views, each with a computation: the preview of the panel (a terrain step), the same preview pinned as a layer, an index in the view
// of the scenes, an index in "Crop and merge to AOI", and an index pinned as a layer. The map zooms from z10 to z0 in each. It fails when
//   1. at a level from z3 on the area is drawn anywhere without a computed tile (a computed tile is one with `op`: blue for the scenes
//      and mosaics, red for the overview; the plain overview is green and a plain tile grey);
//   2. below the first level (map zoom 6.5 for 512-px tiles) no tile of the overview route with the steps was asked for, from z2 on
//      (a tile that an earlier level loaded is not asked for again);
//   3. the preview of the panel or its layer is computed outside its scenes (it is cut to their footprints);
//   4. below the first level the attribution line does not name the source of the overview (for modified data);
//   5. a mark says it: an element of the page that is not a tooltip and says "overview" or "computed from".
//
//   cd frontend && npm run dev &            # a FRESH dev server; no backend is needed, the tiles are made up here
//   node e2e/computed-every-level.cjs       # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const { answersSelection, isSelectionTile } = require('./selectionMock.cjs');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-computed-every-level');
const DESCRIPTION = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'src', 'fixtures', 'processes', 'cop-dem-glo-30.json'), 'utf8'));
const DATASET = 'cop-dem-glo-30';
const AOI_BOX = [6, 44, 11, 48];
const AOI = { type: 'Polygon', coordinates: [[[6, 44], [11, 44], [11, 48], [6, 48], [6, 44]]] };
const CENTRE = [8.5, 46];
const ZOOMS = [10, 9, 8, 7, 6.5, 6, 5, 4, 3, 2, 1, 0];
const FIRST = 6.5;
const MODIFIED = '© made up (modified)';
const VIEWS = ['preview', 'pinned preview', 'scene view', 'crop and merge', 'pinned index'];

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

const computed = ([r, g, b]) => (b > 150 && r < 80 && g < 80) || (r > 150 && g < 80 && b < 80);

async function run(browser, theme, results) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), theme);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const failures = [];
  page.on('pageerror', (error) => failures.push(`the page failed: ${error.message.slice(0, 200)}`));
  let asked = [];
  const tiles = { blue: solid([0, 0, 255, 255]), red: solid([255, 0, 0, 255]), green: solid([0, 200, 0, 255]), grey: solid([128, 128, 128, 255]) };
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    const png = (body) => route.fulfill({ status: 200, contentType: 'image/png', headers: { 'access-control-allow-origin': '*' }, body });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname === '/colormaps') return json({ groups: [] });
    if (url.pathname === '/processing/processes/recipe') return json(DESCRIPTION);
    if (answersSelection(route, url)) return;
    if (url.pathname.endsWith('/tilejson.json')) return json({ tilejson: '3.0.0', bounds: [...AOI_BOX], minzoom: 7, maxzoom: 15, 'earthx:order': [] });
    if (url.pathname.endsWith('/statistics')) return json({ b1: { min: 0, max: 60, percentile_2: 1, percentile_98: 50, count: 9, unit: 'deg' } });
    const steps = url.searchParams.has('op');
    const z = Number(/\/tiles\/WebMercatorQuad\/(\d+)\//.exec(url.pathname)?.[1]);
    if (url.pathname.includes('/overview/')) {
      asked.push({ route: 'overview', steps, z });
      return png(steps ? tiles.red : tiles.green);
    }
    if (isSelectionTile(url.href) || url.pathname.includes('/tiles/')) {
      asked.push({ route: 'scenes', steps, z });
      return png(steps ? tiles.blue : tiles.grey);
    }
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.waitForSelector('.maplibregl-canvas');
  await page.evaluate(async ({ aoi, dataset, modified }) => {
    const { useAppStore } = await import('/src/store.ts');
    const { datasetsFrom } = await import('/src/datasets.ts');
    const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
    const items = Array.from({ length: 4 }, (_, i) => {
      const [x, y] = [6 + (i % 2) * 2.5, 44 + Math.floor(i / 2) * 2];
      return {
        id: `CELL_${i}`, collection: dataset, bbox: [x, y, x + 2.5, y + 2],
        geometry: { type: 'Polygon', coordinates: [[[x, y], [x + 2.5, y], [x + 2.5, y + 2], [x, y + 2], [x, y]]] },
        properties: { datetime: '2021-01-01T00:00:00Z', 'earthx:state': 'latest', gsd: 30 },
        assets: { data: { href: `https://assets.example.org/${i}.tif`, type: COG, 'raster:bands': [{ data_type: 'float32', nodata: -9999, unit: 'm' }] } },
      };
    });
    const collection = {
      id: dataset, title: 'Relief model', 'earthx:format': 'cog',
      'earthx:capabilities': { roi: true, time_range: false, band_math: true, interpolation: true, reprojection: true, terrain: true },
      'earthx:default_render': { title: 'Height', assets: ['data'], rescale: [[0, 4000]], colormap_name: 'terrain', expression: null, resampling: 'nearest' },
      'earthx:index_presets': [{ name: 'double', title: 'Double', expression: 'data * 2', rescale: [[0, 8000]], colormap_name: 'viridis', formula: 'data × 2', reference: 'made up' }],
      'earthx:viewer': { group_by: ['earthx:state'], min_zoom: 7, max_zoom: 15, browse: 'full_resolution', quicklook_nodata_max: null, results_group_by: ['earthx:state'], overview: 'pyramid', overview_resampling: 'average', overview_substitute: null },
      'earthx:license_flags': { tier: 'processing', attribution_required: true, attribution_modified: modified, attribution_unmodified: '© made up' },
      extent: { spatial: { bbox: [[-180, -90, 180, 84]] }, temporal: { interval: [['2019-01-01T00:00:00Z', '2023-12-31T00:00:00Z']] } },
    };
    const groups = [{ key: ['latest'], label: 'latest', items }];
    useAppStore.setState({
      datasets: datasetsFrom([collection]), selectedDatasetIds: [dataset], datasetId: dataset, openSectionId: dataset,
      sections: [{ datasetId: dataset, items, groups, notes: [], groupingError: null, origin: 'search', incomplete: false }],
      items, groups, activeGroupIndex: 0, expandedGroupIndex: 0, selectedIds: items.map((it) => it.id), resultsOnMap: true,
      focusMode: false, downloaded: {}, layers: [], mosaics: {}, aoi, error: null, notice: null, dock: null,
      flyToView: { center: [8.5, 46], zoom: 9 },
    });
  }, { aoi: AOI, dataset: DATASET, modified: MODIFIED });
  await page.waitForTimeout(1500);

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
  const drawnComputed = async () => {
    const points = await page.evaluate(([m, b]) => {
      const rect = m.getCanvas().getBoundingClientRect();
      // The part of the area on the screen, so that a level zoomed in has its points where it looks.
      const view = m.getBounds();
      const [w, s, e, n] = [Math.max(b[0], view.getWest()), Math.max(b[1], view.getSouth()), Math.min(b[2], view.getEast()), Math.min(b[3], view.getNorth())];
      const out = [];
      // Off the outlines of the scenes, which the map draws over them at 8.5° and 46°.
      for (let i = 1; i <= 5; i++) for (let j = 1; j <= 5; j++) {
        const p = m.project([w + ((e - w) * (i - 0.3)) / 5, s + ((n - s) * (j - 0.3)) / 5]);
        const [x, y] = [rect.left + p.x, rect.top + p.y];
        if (x > rect.left + 2 && x < rect.right - 2 && y > rect.top + 2 && y < rect.bottom - 2 && document.elementFromPoint(x, y) === m.getCanvas()) out.push([x, y]);
      }
      return out;
    }, [map, AOI_BOX]);
    const colours = [];
    for (const [x, y] of points) colours.push(await pixelAt(page, Math.round(x), Math.round(y)));
    return { points: points.length, computed: colours.filter(computed).length, sample: colours[0] };
  };
  const store = (code) => page.evaluate(code);

  const zoomOut = async (view) => {
    const problems = [];
    for (const zoom of ZOOMS) {
      asked = [];
      await page.evaluate(([m, lon, lat, z]) => m.jumpTo({ center: [lon, lat], zoom: z }), [map, ...CENTRE, zoom]);
      // Until the map has drawn what it asked for (at most 5 s), then a moment for the paint.
      await page.evaluate((m) => new Promise((done) => { const timer = setTimeout(done, 5000); m.once('idle', () => { clearTimeout(timer); done(); }); }), map);
      await page.waitForTimeout(300);
      if (zoom < FIRST && Number.isInteger(zoom) && zoom >= 2 && !asked.some((r) => r.route === 'overview' && r.steps)) {
        problems.push(`z${zoom}: no tile of the overview with the steps was asked for`);
      }
      if (zoom < FIRST) {
        const credit = await page.$$eval('.maplibregl-ctrl-attrib-inner', (els) => els.map((el) => el.textContent).join(' '));
        if (!credit.includes(MODIFIED)) problems.push(`z${zoom}: the attribution line does not name the source of the overview`);
      }
      if (zoom >= 3) {
        const seen = await drawnComputed();
        if (seen.points === 0) problems.push(`z${zoom}: the area is not on the screen`);
        else if (seen.computed < seen.points) problems.push(`z${zoom}: a computed picture at ${seen.computed} of ${seen.points} places (e.g. rgb ${seen.sample})`);
      }
      if (zoom === 3 && view.includes('preview')) {
        // The preview of a job over these scenes is cut to them below the first level too, not drawn over the whole dataset.
        const outside = await page.evaluate(([m, lonLat]) => {
          const rect = m.getCanvas().getBoundingClientRect();
          const p = m.project(lonLat);
          return [Math.round(rect.left + p.x), Math.round(rect.top + p.y)];
        }, [map, [13.5, 41]]);
        if (computed(await pixelAt(page, ...outside))) problems.push('z3: the preview is computed outside its scenes');
      }
      if (zoom === 3 || zoom === 8) await page.screenshot({ path: path.join(OUT, `${theme}-${view.replace(/ /g, '-')}-z${zoom}.png`) });
    }
    const marks = await page.evaluate(() =>
      [...document.querySelectorAll('body *')]
        .filter((el) => el.children.length === 0 && /overview|computed from/i.test(el.textContent ?? '') && !el.closest('[data-tip]'))
        .map((el) => el.textContent.trim().slice(0, 60)),
    );
    if (marks.length) problems.push(`the page says it: ${JSON.stringify(marks)}`);
    results.push({ name: `${theme} · ${view}`, problems: [...failures.splice(0), ...problems] });
  };

  // 1. The preview of the panel: a slope, the first step.
  await store(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().openProcessing();
  });
  await page.waitForTimeout(1500);
  await store(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().addStep('terrain', 1);
  });
  await page.waitForTimeout(2500);
  await zoomOut(VIEWS[0]);

  // 2. The same preview as a layer, the panel closed; the hits of the search off the map, which lie above a pinned layer.
  await store(async () => {
    const { useProcessingStore } = await import('/src/processingStore.ts');
    useProcessingStore.getState().pinPreview();
    useProcessingStore.getState().closeProcessing();
    (await import('/src/store.ts')).useAppStore.setState({ resultsOnMap: false });
  });
  await page.evaluate(([m, lon, lat]) => m.jumpTo({ center: [lon, lat], zoom: 9 }), [map, ...CENTRE]);
  await page.waitForTimeout(1500);
  await zoomOut(VIEWS[1]);
  await store(async () => (await import('/src/store.ts')).useAppStore.setState({ layers: [], resultsOnMap: true }));

  // 3. An index in the view of the scenes; 4. in "Crop and merge to AOI"; 5. pinned as a layer.
  for (const [view, crop] of [[VIEWS[2], false], [VIEWS[3], true]]) {
    await page.evaluate(([m, lon, lat]) => m.jumpTo({ center: [lon, lat], zoom: 9 }), [map, ...CENTRE]);
    await store(async () => (await import('/src/store.ts')).useAppStore.getState().exitFocus());
    await page.evaluate(async (c) => (await import('/src/store.ts')).useAppStore.getState().enterFocus(c), crop);
    await page.waitForTimeout(2000);
    await store(async () => {
      const { useAppStore } = await import('/src/store.ts');
      useAppStore.getState().chooseViewIndex('double');
      await useAppStore.getState().applyRender();
    });
    await page.waitForTimeout(2500);
    await zoomOut(view);
  }
  await page.evaluate(([m, lon, lat]) => m.jumpTo({ center: [lon, lat], zoom: 9 }), [map, ...CENTRE]);
  await page.waitForTimeout(1000);
  await store(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().addCurrentToLayers();
  });
  await page.waitForTimeout(1500);
  await store(async () => {
    const { useAppStore } = await import('/src/store.ts');
    useAppStore.getState().exitFocus();
    useAppStore.setState({ resultsOnMap: false });
  });
  await page.waitForTimeout(1500);
  await zoomOut(VIEWS[4]);
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
