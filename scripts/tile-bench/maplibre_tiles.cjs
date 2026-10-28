// Which tiles MapLibre asks for one view, with tileSize 256 and 512 (NM4-29), in the session's Chromium.
//
//   node scripts/tile-bench/maplibre_tiles.cjs
//
// A blank style with one raster source over the footprint of `view.py`'s scene, the map of the app's MapLibre
// (`frontend/node_modules`), mercator and globe. Every tile request is answered with a 1 x 1 PNG and counted. Per
// viewport and map zoom one JSON line: the level asked and the number of tiles, per tile size and projection.
const path = require('path');
const { chromium } = require('playwright');

const FRONTEND = path.resolve(__dirname, '../../frontend');
const MAPLIBRE = path.join(FRONTEND, 'node_modules/maplibre-gl/dist');
const CENTRE = [11.05, 47.35];
const FOOTPRINT = [10.3119, 46.8326, 11.8028, 47.8459];
const PNG = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
  'base64',
);
const VIEWS = [
  [1280, 800, 10.2],
  [1280, 800, 13],
  [1920, 1080, 11.5],
  [1920, 1080, 13],
  [360, 640, 11.5],
  [360, 640, 13],
];

async function count(browser, [width, height, zoom], tileSize, projection) {
  const page = await browser.newPage({ viewport: { width, height } });
  const asked = new Set();
  await page.route('http://tiles.test/**', (route) => {
    asked.add(new URL(route.request().url()).pathname);
    return route.fulfill({ status: 200, contentType: 'image/png', body: PNG });
  });
  await page.route('http://app.test/**', (route) => {
    const file = new URL(route.request().url()).pathname.slice(1);
    if (file === 'index.html') {
      return route.fulfill({
        contentType: 'text/html',
        body: `<!doctype html><html><head><link rel="stylesheet" href="maplibre-gl.css">
          <style>html,body,#map{margin:0;width:100%;height:100%}</style></head>
          <body><div id="map"></div><script src="maplibre-gl.js"></script></body></html>`,
      });
    }
    return route.fulfill({ path: path.join(MAPLIBRE, file) });
  });
  await page.goto('http://app.test/index.html');
  await page.evaluate(
    ({ tileSize, projection, zoom, centre, bounds }) =>
      new Promise((resolve) => {
        const map = new maplibregl.Map({
          container: 'map',
          center: centre,
          zoom,
          fadeDuration: 0,
          style: {
            version: 8,
            projection: { type: projection },
            sources: { s: { type: 'raster', tiles: ['http://tiles.test/{z}/{x}/{y}.png'], tileSize, bounds } },
            layers: [{ id: 'l', type: 'raster', source: 's', paint: { 'raster-fade-duration': 0 } }],
          },
        });
        map.once('idle', resolve);
      }),
    { tileSize, projection, zoom, centre: CENTRE, bounds: FOOTPRINT },
  );
  await page.close();
  const levels = [...new Set([...asked].map((p) => p.split('/')[1]))];
  return { tiles: asked.size, levels: levels.join(',') };
}

(async () => {
  const browser = await chromium.launch({ args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'] });
  for (const view of VIEWS) {
    const line = { viewport: `${view[0]}x${view[1]}`, mapZoom: view[2] };
    for (const projection of ['mercator', 'globe']) {
      for (const tileSize of [256, 512]) line[`${projection}_${tileSize}`] = await count(browser, view, tileSize, projection);
    }
    console.log(JSON.stringify(line));
  }
  await browser.close();
})();
