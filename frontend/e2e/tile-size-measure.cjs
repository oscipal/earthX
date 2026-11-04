// Measurement of NM4-29b in a real browser on the real tiler: the NDVI mosaic of 12 scenes on a 1920 x 1080 map at zoom 11.5
// (`docs/plans/querschnitt/nm4-29-kacheln-512.md` §7.2, §17 Umfang 3). Counts the mosaic tiles the browser asks for, the time
// from the map move to the last tile, and the size of the pictures; run it on `main` (before) and on the change (after).
//
//   source .venv/bin/activate; set -a; source .env.test; set +a                     # Postgres, as for scripts/tile-bench
//   python -I scripts/tile-bench/slow_source.py <cog-dir> --log /dev/null &          # the far source (port 9100)
//   PYTHONPATH=backend python scripts/tile-bench/run_tiler.py --source http://127.0.0.1:9100 --log /dev/null &   # the tiler (8101)
//   cd frontend && VITE_TILER_PROXY=http://127.0.0.1:8101 npm run dev &              # the dev server (5173)
//   TAG=after node e2e/tile-size-measure.cjs                                         # BASE=http://localhost:5173 RUNS=1 MBIT=
//
// Add `--mbit 100` to `slow_source.py` for a line of 100 Mbit/s. Only `/collections` goes to the tiler; every other answer is
// made up or refused, so that nothing leaves the machine. Playwright and Chromium are not a dependency of the project.

const { chromium } = require('playwright');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const TAG = process.env.TAG ?? 'run';
const RUNS = Number(process.env.RUNS ?? 1);
const SCENES = Array.from({ length: 12 }, (_, i) => `SYNTH_T32TPT_202608${String(i + 1).padStart(2, '0')}T102039_L2A`);
const FOOTPRINT = [10.3119, 46.8326, 11.8028, 47.8459];
const CENTRE = [11.05, 47.35];
const NDVI = ['NDVI', 'Normalized Difference Vegetation Index', '(nir - red) / (nir + red)', 'rdylgn', '(N - R)/(N + R)'];

async function measure(browser) {
  const context = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await context.newPage();
  page.setDefaultTimeout(15_000);
  const tiles = [];
  const asked = new Map();
  await page.route('**/*', (route) => {
    const url = new URL(route.request().url());
    if (url.origin !== BASE) return route.abort();
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    if (url.pathname.startsWith('/collections/')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  page.on('request', (request) => {
    if (request.url().includes('/mosaic/tiles/')) asked.set(request, performance.now());
  });
  page.on('response', async (response) => {
    const request = response.request();
    if (!asked.has(request)) return;
    const body = await response.body().catch(() => Buffer.alloc(0));
    tiles.push({ at: performance.now(), status: response.status(), bytes: body.length, body, url: request.url() });
  });
  page.on('pageerror', (error) => console.error(`the page failed: ${error.message.slice(0, 200)}`));

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  await page.evaluate(
    async ({ scenes, footprint, ndvi }) => {
      const { useAppStore } = await import('/src/store.ts');
      const { datasetsFrom } = await import('/src/datasets.ts');
      const info = (id) => ({
        datasetId: 'sentinel-2-c1-l2a',
        tileUrl: `/collections/sentinel-2-c1-l2a/items/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}?asset=visual`,
        bounds: footprint, asset: 'visual', minZoom: 0, maxZoom: 19,
      });
      const COG = 'image/tiff; application=geotiff; profile=cloud-optimized';
      const items = scenes.map((id) => ({
        id, collection: 'sentinel-2-c1-l2a', bbox: footprint, properties: { datetime: '2026-08-01T10:20:39Z', gsd: 10 },
        assets: Object.fromEntries(['red', 'nir', 'visual'].map((k) => [k, { href: `https://example.org/${k}.tif`, type: COG, 'raster:bands': [{ data_type: 'uint16', nodata: 0 }] }])),
      }));
      const [name, title, expression, colormap_name, formula] = ndvi;
      const collection = {
        id: 'sentinel-2-c1-l2a', title: 'Sentinel-2 L2A', 'earthx:format': 'cog', 'earthx:capabilities': { roi: true, time_range: true, band_math: true, interpolation: true },
        'earthx:default_render': { title: 'True colour', assets: ['visual'], rescale: [[0, 3000]], colormap_name: null, expression: null, resampling: 'nearest' },
        'earthx:viewer': { group_by: ['datetime'], min_zoom: 0, max_zoom: 19, browse: 'quicklook', quicklook_nodata_max: null, results_group_by: ['datetime'] },
        'earthx:true_color': ['red', 'green', 'blue'], 'earthx:license_flags': { tier: 'processing', license: 'CC-BY-4.0' },
        'earthx:index_presets': [{ name, title, expression, rescale: [[-1, 1]], colormap_name, formula, reference: 'https://example.org/formula' }],
      };
      useAppStore.setState({
        datasets: datasetsFrom([collection]), datasetId: 'sentinel-2-c1-l2a', items, groups: [{ key: ['a'], label: '2026-08-01', items }], activeGroupIndex: 0,
        selectedIds: scenes, downloaded: Object.fromEntries(scenes.map((id) => [id, info(id)])), focusMode: true, cropToAoi: false, viewAoi: null, aoi: null,
        showDownloaded: true, dock: null, appliedRender: { index: name, colormapName: colormap_name, rescale: '-1,1' }, layers: [], mosaics: {}, error: null,
        flyToView: { center: [5, 5], zoom: 2 },
      });
      await useAppStore.getState().loadMosaics();
    },
    { scenes: SCENES, footprint: FOOTPRINT, ndvi: NDVI },
  );
  await page.waitForTimeout(1500);
  tiles.length = 0;
  asked.clear();
  const start = performance.now();
  await page.evaluate(async ({ centre }) => (await import('/src/store.ts')).useAppStore.setState({ flyToView: { center: centre, zoom: 11.5 } }), { centre: CENTRE });
  // Done when every tile asked for has come and none was asked for in the last 4 s.
  let last = performance.now();
  let seen = 0;
  while (performance.now() - start < 240_000) {
    await page.waitForTimeout(500);
    if (asked.size !== seen) [seen, last] = [asked.size, performance.now()];
    if (asked.size > 0 && tiles.length >= asked.size && performance.now() - last > 4000) break;
  }
  // The size of the pictures as the browser decodes them, whatever the format.
  const sizes = await page.evaluate(async (pictures) => {
    const out = new Set();
    for (const base64 of pictures) {
      try {
        const bitmap = await createImageBitmap(new Blob([Uint8Array.from(atob(base64), (c) => c.charCodeAt(0))]));
        out.add(`${bitmap.width}x${bitmap.height}`);
      } catch {
        out.add('unreadable');
      }
    }
    return [...out];
  }, tiles.filter((t) => t.status === 200).map((t) => t.body.toString('base64')));
  const done = tiles.map((t) => t.at - start);
  const result = {
    tag: TAG,
    asked: asked.size,
    answered: tiles.length,
    failed: tiles.filter((t) => t.status !== 200).length,
    first_s: +(Math.min(...done) / 1000).toFixed(1),
    median_s: +(done.sort((a, b) => a - b)[Math.floor(done.length / 2)] / 1000).toFixed(1),
    last_s: +(Math.max(...done) / 1000).toFixed(1),
    megabytes: +(tiles.reduce((sum, t) => sum + t.bytes, 0) / 1e6).toFixed(1),
    picture_px: sizes,
    tilesize: [...new Set(tiles.map((t) => new URL(t.url).searchParams.get('tilesize') ?? 'none'))],
    bands: [...new Set(tiles.map((t) => new URL(t.url).searchParams.get('band') ?? 'none'))],
    levels: [...new Set(tiles.map((t) => t.url.split('/WebMercatorQuad/')[1].split('/')[0]))],
  };
  await context.close();
  return result;
}

(async () => {
  const browser = await chromium.launch();
  for (let run = 0; run < RUNS; run++) console.log(JSON.stringify(await measure(browser)));
  await browser.close();
})();
