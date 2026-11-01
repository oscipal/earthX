// Browser check of NM4-29b, in a real browser with made-up answers of the tiler (`docs/plans/querschnitt/nm4-29-kacheln-512.md` §17):
//   1. The tiles of a mosaic ask for `tilesize=512` and come as pictures of 512 px; the tiles of a scene ask for no size and come as
//      pictures of 256 px.
//   2. The mosaic starts at level 8 and is asked for from map zoom 7.5; the scenes under it are drawn up to there and not from
//      there (the scenes' tiles of 256 px would have been asked for from 6.5). Never both, never neither.
//   3. "AOI only" cuts a mosaic tile of 512 px at the AOI, the same place as it cuts the tiles of 256 px of the scenes.
// In the light and the dark theme, at a wide and a narrow window (360 px); a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/tile-size.cjs                  # BASE=http://localhost:5173 OUT=<directory for the screenshots> ONLY=checkEdges
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-tile-size');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const FOOTPRINT = [10, 46, 12, 48];
const CENTRE = [11, 47];
const SCENES = ['SYNTH_A', 'SYNTH_B', 'SYNTH_C'];
const HALF_LON = 0.04;
const HALF_LAT = 0.025;
const ZOOM = 10.5;
// The map is centred a little south of the AOI, so that a window as narrow as 360 px shows the AOI above its panel.
const MAP_CENTRE = [CENTRE[0], CENTRE[1] - 0.02];

// A picture of one opaque colour, `size` x `size` px: green, which neither basemap has.
function png(size) {
  const table = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buffer) => (buffer.reduce((sum, byte) => table[(sum ^ byte) & 0xff] ^ (sum >>> 8), 0xffffffff) ^ 0xffffffff) >>> 0;
  const chunk = (type, data) => {
    const body = Buffer.concat([Buffer.from(type), data]);
    const length = Buffer.alloc(4);
    const sum = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    sum.writeUInt32BE(crc(body));
    return Buffer.concat([length, body, sum]);
  };
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8;
  header[9] = 2;
  const row = Buffer.concat([Buffer.from([0]), Buffer.from(Array.from({ length: size }, () => [20, 200, 60]).flat())]);
  return Buffer.concat([
    Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]),
    chunk('IHDR', header),
    chunk('IDAT', zlib.deflateSync(Buffer.concat(Array.from({ length: size }, () => row)))),
    chunk('IEND', Buffer.alloc(0)),
  ]);
}
const PICTURES = { 256: png(256), 512: png(512) };
const AOI = {
  type: 'Polygon',
  coordinates: [[[CENTRE[0] - HALF_LON, CENTRE[1] - HALF_LAT], [CENTRE[0] + HALF_LON, CENTRE[1] - HALF_LAT], [CENTRE[0] + HALF_LON, CENTRE[1] + HALF_LAT], [CENTRE[0] - HALF_LON, CENTRE[1] + HALF_LAT], [CENTRE[0] - HALF_LON, CENTRE[1] - HALF_LAT]]],
};

async function open(browser, theme, viewport, scenario) {
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  const problems = [];
  const tiles = { mosaic: [], scene: [] };
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const json = (body, status = 200) => route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.includes('/mosaic/') && url.pathname.endsWith('/tilejson.json')) {
      if (scenario === 'scenes') return json({ detail: 'refused' }, 422);
      return json({ tilejson: '3.0.0', bounds: FOOTPRINT, minzoom: 8, maxzoom: 14, 'earthx:order': SCENES });
    }
    if (url.pathname.includes('/tiles/')) {
      const kind = url.pathname.includes('/mosaic/') ? 'mosaic' : 'scene';
      // What the tiler does: the size the tile asks for, else 256 px.
      const size = url.searchParams.get('tilesize') === '512' ? 512 : 256;
      tiles[kind].push({ size, search: url.search });
      return route.fulfill({ status: 200, contentType: 'image/png', body: PICTURES[size] });
    }
    return json({ detail: 'not made up' }, 404);
  });
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  await page.evaluate(
    async ({ scenes, footprint, aoi }) => {
      const { useAppStore } = await import('/src/store.ts');
      const { datasetsFrom } = await import('/src/datasets.ts');
      const info = (id) => ({ datasetId: 'optical', tileUrl: `/collections/optical/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`, bounds: footprint, asset: 'visual', minZoom: 0, maxZoom: 14 });
      const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
      const items = scenes.map((id) => ({ id, collection: 'optical', bbox: footprint, properties: { datetime: '2026-07-01T10:00:00Z', gsd: 10 }, assets: { visual: { href: 'https://example.org/v.tif', type: COG, 'raster:bands': [{ data_type: 'uint8', nodata: 0 }] } } }));
      const collection = {
        id: 'optical', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, interpolation: true },
        'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: null, colormap_name: null, expression: null, resampling: 'nearest' },
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 14, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
        'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
      };
      useAppStore.setState({
        datasets: datasetsFrom([collection]), datasetId: 'optical', items, groups: [{ key: ['a'], label: '2026-07-01', items }], activeGroupIndex: 0,
        selectedIds: scenes, downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: true, viewAoi: aoi, aoi,
        showDownloaded: true, dock: null, appliedRender: {}, layers: [], mosaics: {}, error: null, flyToView: { center: [5, 5], zoom: 3 },
      });
      await useAppStore.getState().loadMosaics();
    },
    { scenes: SCENES, footprint: FOOTPRINT, aoi: AOI },
  );
  fs.mkdirSync(OUT, { recursive: true });
  return { context, page, problems, tiles };
}

const PX = 512 * 2 ** ZOOM;
const mercator = (lat) => Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) * (PX / (2 * Math.PI));
const fly = async (page, zoom, centre = MAP_CENTRE) => {
  await page.evaluate(async ({ zoom, centre }) => (await import('/src/store.ts')).useAppStore.setState({ flyToView: { center: centre, zoom } }), { zoom, centre });
  await page.waitForTimeout(2200);
};

// The edges of the green picture on the lines through the AOI's middle, in px from the middle of the map: [west, east, north, south].
async function edgesOf(page, aoiRow) {
  const canvas = await page.locator('canvas.maplibregl-canvas').boundingBox();
  const shot = await page.screenshot({ clip: canvas });
  return page.evaluate(async ({ base64, aoiRow }) => {
    const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))]));
    const surface = new OffscreenCanvas(bitmap.width, bitmap.height).getContext('2d');
    surface.drawImage(bitmap, 0, 0);
    const [mx, my] = [Math.round(bitmap.width / 2), Math.round(bitmap.height / 2)];
    const row = my + aoiRow;
    const green = (x, y) => {
      const [r, g, b] = surface.getImageData(x, y, 1, 1).data;
      return g > r + 80 && g > b + 60;
    };
    const along = (length, at, pixel) => {
      const hits = Array.from({ length }, (_, i) => i).filter((i) => pixel(i, at));
      return hits.length === 0 ? [null, null] : [Math.min(...hits), Math.max(...hits)];
    };
    const [west, east] = along(bitmap.width, row, (i, at) => green(i, at));
    const [north, south] = along(bitmap.height, mx, (i, at) => green(at, i));
    return [west === null ? null : west - mx, east === null ? null : east - mx, north === null ? null : north - my, south === null ? null : south - my];
  }, { base64: shot.toString('base64'), aoiRow });
}

// 1 and 2: the sizes, and the zoom at which the mosaic takes over. A page of its own for each zoom: the map keeps the tiles it has.
async function checkSizes(browser, theme, viewport) {
  const name = `sizes ${theme} ${viewport}`;
  const problems = [];
  const at = {};
  for (const zoom of [7.4, 7.6, ZOOM]) {
    const opened = await open(browser, theme, viewport, 'mosaic');
    problems.push(...opened.problems);
    await fly(opened.page, zoom);
    at[zoom] = { mosaic: opened.tiles.mosaic.length, scene: opened.tiles.scene.length };
    if (opened.tiles.mosaic.some((t) => t.size !== 512 || new URLSearchParams(t.search).get('tilesize') !== '512')) problems.push(`at zoom ${zoom} a mosaic tile is not asked for tilesize=512`);
    if (opened.tiles.scene.some((t) => t.size !== 256 || t.search.includes('tilesize'))) problems.push(`at zoom ${zoom} a scene tile names a size`);
    if (zoom === ZOOM) await opened.page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}.png`) });
    await opened.context.close();
  }
  if (at[7.4].mosaic !== 0 || at[7.4].scene === 0) problems.push(`at zoom 7.4: ${at[7.4].mosaic} mosaic and ${at[7.4].scene} scene tiles, the scenes should be drawn alone`);
  if (at[7.6].mosaic === 0 || at[7.6].scene !== 0) problems.push(`at zoom 7.6: ${at[7.6].mosaic} mosaic and ${at[7.6].scene} scene tiles, the mosaic should be drawn alone`);
  if (at[ZOOM].mosaic === 0 || at[ZOOM].scene !== 0) problems.push(`at zoom ${ZOOM}: ${at[ZOOM].mosaic} mosaic and ${at[ZOOM].scene} scene tiles`);
  return { name, problems, detail: `tiles asked at 7.4 ${JSON.stringify(at[7.4])}, at 7.6 ${JSON.stringify(at[7.6])}, at ${ZOOM} ${JSON.stringify(at[ZOOM])}` };
}

// 3: the edge of "AOI only", where it must be.
async function checkEdges(browser, theme, viewport) {
  const name = `edges ${theme} ${viewport}`;
  const found = {};
  const problems = [];
  for (const scenario of ['mosaic', 'scenes']) {
    const opened = await open(browser, theme, viewport, scenario);
    problems.push(...opened.problems);
    await fly(opened.page, ZOOM);
    found[scenario] = await edgesOf(opened.page, Math.round(-(mercator(CENTRE[1]) - mercator(MAP_CENTRE[1]))));
    await opened.page.screenshot({ path: path.join(OUT, `${name.replace(/ /g, '_')}_${scenario}.png`) });
    if (scenario === 'mosaic' && opened.tiles.mosaic.length === 0) problems.push('the mosaic asked for no tile');
    await opened.context.close();
  }
  // Where the edges of the AOI are, in px from the middle of the map (512 px at zoom 0).
  const expected = [-(HALF_LON / 360) * PX, (HALF_LON / 360) * PX, -(mercator(CENTRE[1] + HALF_LAT) - mercator(MAP_CENTRE[1])), -(mercator(CENTRE[1] - HALF_LAT) - mercator(MAP_CENTRE[1]))];
  for (const scenario of ['mosaic', 'scenes']) {
    const edges = found[scenario];
    // At 360 px the panel of the view lies over the south edge: three edges are seen there.
    if (edges.slice(0, viewport === 'narrow' ? 3 : 4).some((e) => e === null)) {
      problems.push(`${scenario}: no green picture at the middle of the map (${JSON.stringify(edges)})`);
      continue;
    }
    edges.slice(0, viewport === 'narrow' ? 3 : 4).forEach((edge, i) => {
      if (Math.abs(edge - expected[i]) > 4) problems.push(`${scenario}: edge ${['west', 'east', 'north', 'south'][i]} is at ${edge} px, the AOI is at ${expected[i].toFixed(0)} px`);
    });
  }
  return { name, problems, detail: `AOI edges at ${expected.map((e) => e.toFixed(0))}, mosaic ${found.mosaic}, scenes ${found.scenes}` };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const check of [checkSizes, checkEdges].filter((c) => !process.env.ONLY || c.name === process.env.ONLY)) {
        const result = await check(browser, theme, viewport);
        failed += result.problems.length > 0 ? 1 : 0;
        console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name} — ${result.detail}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
      }
    }
  }
  await browser.close();
  process.exit(failed ? 1 : 0);
})();
