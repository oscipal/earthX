// Browser check of the map after the step to maplibre-gl 6 (NM4-44b), in a real browser on the real app and the real `api`
// (the one made-up answer is `POST /stac/search`: the fixture of the backend, as in `no-aoi-in-url.cjs`). It does what a user
// does and fails when
//   1. the map does not start (WebGL2 is required since 6), or the page throws;
//   2. the attribution is not open, loses its credit, or keeps a dangerous attribute of a source's attribution (the hole that
//      made the step necessary: 5.24 kept the second of two event attributes in a row, 6.x keeps none);
//   3. the zoom limits or the no-tilt rule of the map have moved (levels 0 to 22, pitch 0);
//   4. "Globe" and "Mercator" in the menu do not change the projection of the map;
//   5. the basemap "Relief" (the one basemap whose host the cloud session can reach) draws no shading over mountains;
//   6. the Point, Rectangle and Polygon tools set no AOI, an upload sets none or a wrong file changes the AOI;
//   7. the outline of a ticked scene is not on the map.
// Light and dark theme, 1280 and 360 px, mouse and touch. The basemaps Satellite, Streets, Grey and Outlines come from hosts
// that the cloud session cannot reach: they are asked for and their failure is counted, but not judged (the app must say so for
// Streets and Grey). Run against 5.24.0 the check fails on the attribution (point 2) and on nothing else.
//
//   (the api as in the header of no-aoi-in-url.cjs)   cd frontend && npm run dev &
//   node e2e/map-gl6.cjs                               # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(os.tmpdir(), 'earthx-map-gl6');
const FIXTURE = path.join(__dirname, '../../backend/tests/fixtures/earth_search/search_page_1.json');
const THEMES = { light: 'normal', dark: 'tech' };
const CONFIGS = [
  { name: 'light wide mouse', theme: 'light', viewport: { width: 1280, height: 800 }, touch: false },
  { name: 'dark wide touch', theme: 'dark', viewport: { width: 1280, height: 800 }, touch: true },
  { name: 'light narrow touch', theme: 'light', viewport: { width: 360, height: 740 }, touch: true },
  { name: 'dark narrow mouse', theme: 'dark', viewport: { width: 360, height: 740 }, touch: false },
];
const ALPS = [10.5, 47];
const ATLANTIC = [-30, 5];
// What a source's attribution may not bring through: two event attributes in a row, a script address, a data address.
const HOSTILE = '<a href="https://example.org/credit" onclick="window.__hit=1" onmouseover="window.__hit=2">Credit</a> '
  + '<a href="javascript:window.__hit=3">script</a> <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" onerror="window.__hit=4">';
const UPLOAD = { type: 'Polygon', coordinates: [[[10.0, 47.2], [10.3, 47.2], [10.3, 47.4], [10.0, 47.4], [10.0, 47.2]]] };

(async () => {
  const answered = await fetch(`${BASE}/stac/collections`, { signal: AbortSignal.timeout(10000) }).then((response) => response.ok, () => false);
  if (!answered) {
    console.error(`nothing answers /stac/collections at ${BASE}: start the dev server and the api as in the header`);
    process.exit(2);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const fixture = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
  fixture.features.forEach((item, index) => { item.properties['s2:datatake_id'] = `SYNTH_DATATAKE_${index}`; });
  const problems = [];
  const browser = await chromium.launch();

  for (const config of CONFIGS.filter((_, index) => process.env.ONLY === undefined || process.env.ONLY === String(index))) {
    const tag = config.name;
    const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${tag}: expected ${what}${detail ? ` (${detail})` : ''}`); };
    const context = await browser.newContext({ viewport: config.viewport, hasTouch: config.touch, isMobile: false });
    await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[config.theme]);
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    const hosts = { terrain: [], other: 0, told: [] };
    page.on('pageerror', (error) => problems.push(`${tag}: the page failed: ${error.message.slice(0, 200)}`));
    page.on('response', (response) => { if (response.url().startsWith('https://s3.amazonaws.com/elevation-tiles-prod/')) hosts.terrain.push(response.status()); });
    page.on('requestfailed', () => { hosts.other += 1; });
    await page.route('**/stac/search', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) }));
    const shot = (name) => page.screenshot({ path: path.join(OUT, `${config.name.replace(/ /g, '-')}-${name}.png`) });
    const store = (fn, arg) => page.evaluate(async ([src, data]) => {
      const { useAppStore } = await import('/src/store.ts');
      return (0, eval)(`(${src})`)(useAppStore, data);
    }, [fn.toString(), arg]);

    await page.goto(BASE);
    await page.waitForSelector('.maplibregl-canvas');
    await page.waitForSelector('.dataset-toggle');
    // The map of the app: its ref lives in the hooks of `MapView`; nothing of the app is changed to reach it.
    const map = await page.evaluateHandle(() => {
      let fiber = document.querySelector('.maplibregl-map')[Object.keys(document.querySelector('.maplibregl-map')).find((k) => k.startsWith('__reactFiber$'))];
      for (; fiber; fiber = fiber.return) {
        for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
          const held = hook.memoizedState?.current;
          if (held && typeof held.getStyle === 'function') return held;
        }
      }
      return null;
    });
    const idle = () => page.evaluate((m) => new Promise((resolve) => { const timer = setTimeout(resolve, 6000); m.once('idle', () => { clearTimeout(timer); resolve(); }); m.triggerRepaint(); }), map);
    // Under 900 px the panel covers the whole window (UI-03): it is closed to reach the map and opened for its buttons.
    const dock = async (open) => {
      const rail = page.getByRole('button', { name: 'Search and area' });
      if ((await rail.getAttribute('aria-expanded')) !== String(open)) await rail.click();
    };
    const jump = (lon, lat, zoom) => page.evaluate(([m, args]) => { m.jumpTo({ center: [args[0], args[1]], zoom: args[2] }); }, [map, [lon, lat, zoom]]);

    // 1. The map runs on WebGL2, as 6 needs.
    const webgl = await page.evaluate((m) => ({ gl2: m.getCanvas().getContext('webgl2') !== null, size: [m.getCanvas().width, m.getCanvas().height] }), map);
    expect('the canvas of the map is WebGL2', webgl.gl2);
    expect('the canvas has a size', webgl.size[0] > 100 && webgl.size[1] > 100, webgl.size.join('x'));

    // 2. The attribution: open, with the credit of the basemap, and sanitised.
    const attribution = page.locator('.maplibregl-ctrl-attrib');
    const attributionBox = await attribution.boundingBox();
    expect('the attribution is open (not the collapsed "i")', !(await attribution.evaluate((el) => el.classList.contains('maplibregl-compact'))));
    expect('the attribution names Esri, the credit of the default basemap', /Esri/.test(await attribution.innerText()));
    expect('the attribution lies inside the window', !!attributionBox && attributionBox.x >= 0 && attributionBox.x + attributionBox.width <= config.viewport.width + 0.5);
    await page.evaluate(([m, html]) => {
      m.addSource('hostile-src', { type: 'geojson', data: { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [0, 0] } }] }, attribution: html });
      m.addLayer({ id: 'hostile-lyr', type: 'circle', source: 'hostile-src' });
    }, [map, HOSTILE]);
    await idle();
    const inner = await page.locator('.maplibregl-ctrl-attrib-inner').innerHTML();
    expect('no event attribute of a source to come through the attribution', !/ on[a-z]+=/i.test(inner), inner.slice(0, 160));
    expect('no script or data address of a source to come through the attribution', !/javascript:|data:/i.test(inner), inner.slice(0, 160));
    expect('the plain credit link of a source to stay in the attribution', /href="https:\/\/example\.org\/credit"/.test(inner));
    // Whatever of an attribute is left must not run: the event is fired on the links (a window-wide panel may cover them).
    await page.evaluate(() => document.querySelectorAll('.maplibregl-ctrl-attrib-inner a').forEach((a) => a.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }))));
    expect('no hostile attribute to run', (await page.evaluate(() => window.__hit)) === undefined);
    await page.evaluate((m) => { m.removeLayer('hostile-lyr'); m.removeSource('hostile-src'); }, map);

    // 3. The limits of the map (the same ones as with 5.24).
    const limits = await page.evaluate((m) => {
      m.jumpTo({ zoom: 30, pitch: 60, bearing: 40 });
      const high = { zoom: m.getZoom(), pitch: m.getPitch() };
      m.jumpTo({ zoom: -5 });
      return { maxZoom: m.getMaxZoom(), minZoom: m.getMinZoom(), high, low: m.getZoom(), maxPitch: m.getMaxPitch() };
    }, map);
    expect('the map zooms to 22 and not beyond', limits.maxZoom === 22 && limits.high.zoom === 22, JSON.stringify(limits));
    // MapLibre's own floor is -2; the world fills the window long before, so the map stops where it fits.
    expect('the map keeps MapLibre\'s floor of -2 and does not zoom out past the world', limits.minZoom === -2 && limits.low >= 0 && limits.low < 2, JSON.stringify(limits));
    expect('the map cannot be tilted', limits.maxPitch === 0 && limits.high.pitch === 0, JSON.stringify(limits));
    await jump(10.5, 30, 1.6);

    // 4. The basemap "Relief" and the projection, through the menu.
    const menu = async (group, name) => {
      await dock(false);
      const opener = page.getByRole('button', { name: 'Basemap', exact: true });
      if ((await opener.getAttribute('aria-expanded')) !== 'true') await opener.click();
      await page.getByRole('group', { name: group }).getByRole('menuitemradio', { name }).click();
      await opener.click(); // the menu stays open after a choice, over the map: closed with its button (Esc closes nothing)
      await idle();
    };
    // Relief: shading over mountains, none over the sea (the one basemap whose host the cloud session reaches).
    const stddev = async (fx = 0.5, fy = 0.5, size = 160) => {
      const png = (await page.locator('.maplibregl-canvas').screenshot()).toString('base64');
      return page.evaluate(async ([data, fx, fy, size]) => {
        const image = new Image();
        image.src = `data:image/png;base64,${data}`;
        await image.decode();
        const canvas = document.createElement('canvas');
        canvas.width = size; canvas.height = size;
        const ctx = canvas.getContext('2d');
        ctx.drawImage(image, image.width * fx - size / 2, image.height * fy - size / 2, size, size, 0, 0, size, size);
        const px = ctx.getImageData(0, 0, size, size).data;
        let sum = 0; let sq = 0;
        for (let i = 0; i < px.length; i += 4) { const l = 0.3 * px[i] + 0.59 * px[i + 1] + 0.11 * px[i + 2]; sum += l; sq += l * l; }
        const n = px.length / 4;
        return Math.sqrt(Math.max(0, sq / n - (sum / n) ** 2));
      }, [png, fx, fy, size]);
    };
    await menu('Basemap', /Relief/);
    await jump(...ALPS, 7);
    await idle();
    await page.waitForTimeout(1500);
    const over = await stddev();
    await jump(...ATLANTIC, 5);
    await idle();
    await page.waitForTimeout(1500);
    const sea = await stddev();
    expect('the terrain tiles are asked for and come', hosts.terrain.length > 0 && hosts.terrain.every((status) => status === 200), hosts.terrain.slice(0, 5).join(','));
    expect('the shading over the Alps varies more than over the sea', over > 3 * sea + 2, `Alps ${over.toFixed(1)}, sea ${sea.toFixed(1)}`);
    await jump(...ALPS, 7);
    await idle();
    await page.waitForTimeout(1500);
    await shot('relief');
    await menu('Projection', /Globe/);
    await jump(10, 20, 0.8);
    await idle();
    await page.waitForTimeout(1500);
    expect('"Globe" gives the globe', (await page.evaluate((m) => m.getProjection()?.type, map)) === 'globe');
    // The sphere (about 280 px across at this zoom) is there, and below it lies the plain backdrop.
    const [globeCentre, backdrop] = [await stddev(0.5, 0.5, 100), await stddev(0.5, 0.82, 60)];
    expect('the globe is drawn over a plain backdrop', globeCentre > 1 && backdrop < 0.5, `globe ${globeCentre.toFixed(2)}, backdrop ${backdrop.toFixed(2)}`);
    await shot('globe');
    await menu('Projection', /Mercator/);
    expect('"Mercator" gives Mercator back', (await page.evaluate((m) => m.getProjection()?.type, map)) === 'mercator');
    const dismiss = async () => {
      const button = page.getByRole('alert').getByRole('button', { name: 'Dismiss' });
      while (await button.count()) await button.first().click();
    };
    await page.evaluate(async () => {
      const { useAppStore } = await import('/src/store.ts');
      window.__told = new Set();
      useAppStore.subscribe((st) => { if (st.error) window.__told.add(st.error); });
    });
    for (const name of ['Satellite', 'Streets', 'Grey', 'Outlines']) {
      await dismiss();
      await menu('Basemap', new RegExp(name));
      await page.waitForTimeout(3000);
    }
    // The two published styles come from a host the cloud session cannot reach: the app says so and keeps what it shows.
    await page.waitForFunction(() => [...window.__told].filter((text) => /basemap could not be loaded/.test(text)).length >= 2, null, { timeout: 30000 }).catch(() => undefined);
    const told = await page.evaluate(() => [...window.__told].map((text) => text.slice(0, 70)));
    hosts.told.push(...told);
    expect('the app to tell of the basemaps it could not load (Streets, Grey)', ['Streets', 'Grey'].every((name) => told.some((text) => text.includes(name))), told.join(' | '));
    await dismiss();
    expect('the basemap to be one the map can show after the failures', ['satellite', 'streets', 'grey', 'outlines', 'relief'].includes(await store((st) => st.getState().basemap)));
    await menu('Basemap', /Satellite/);
    await page.keyboard.press('Tab');

    // 6. The AOI: the three tools, the upload, a wrong file.
    const box = await page.locator('.maplibregl-canvas').boundingBox();
    const at = (fx, fy) => ({ x: box.x + box.width * fx, y: box.y + box.height * fy });
    const aoi = () => store((s) => s.getState().aoi);
    const pick = async (name) => {
      const button = tool(name);
      if ((await button.getAttribute('aria-pressed')) !== 'true') await button.click();
    };
    const tool = (name) => page.getByRole('group', { name: 'Area of interest tools' }).getByRole('button', { name, exact: true });
    const clear = async () => { await dock(true); await tool('Clear').click(); };
    await dock(true);
    await pick('Point');
    await dock(false);
    const spot = at(0.5, 0.45);
    if (config.touch) await page.touchscreen.tap(spot.x, spot.y);
    else await page.mouse.click(spot.x, spot.y);
    await page.waitForTimeout(500);
    expect('the Point tool sets an AOI', (await aoi())?.type === 'Polygon');
    await clear();
    if (!config.touch) {
      await dock(true);
      await pick('Rectangle');
      await dock(false);
      const a = at(0.4, 0.35); const b = at(0.55, 0.5);
      await page.mouse.click(a.x, a.y); await page.mouse.move(b.x, b.y, { steps: 6 }); await page.mouse.click(b.x, b.y);
      await page.waitForTimeout(500);
      expect('the Rectangle tool sets a box', (await aoi())?.type === 'Polygon' && (await aoi()).coordinates[0].length === 5);
      await clear();
    }
    await dock(true);
    await pick('Polygon');
    await dock(false);
    const corners = [at(0.4, 0.35), at(0.55, 0.35), at(0.5, 0.5)];
    for (const c of corners) {
      if (config.touch) await page.touchscreen.tap(c.x, c.y);
      else await page.mouse.click(c.x, c.y);
      await page.waitForTimeout(250);
    }
    if (config.touch) { await page.touchscreen.tap(corners[2].x, corners[2].y); await page.waitForTimeout(80); await page.touchscreen.tap(corners[2].x, corners[2].y); } else await page.mouse.dblclick(corners[2].x, corners[2].y);
    await page.waitForTimeout(600);
    const polygon = await aoi();
    expect('the Polygon tool sets a polygon', polygon?.type === 'Polygon' && polygon.coordinates[0].length >= 4, JSON.stringify(polygon)?.slice(0, 80));
    await shot('polygon');
    await clear();
    expect('"Clear" takes the AOI away', (await aoi()) === null);

    await dock(true);
    const input = page.locator('.aoi-extras input[type=file]');
    await input.setInputFiles({ name: 'area.geojson', mimeType: 'application/geo+json', buffer: Buffer.from(JSON.stringify({ type: 'Feature', properties: {}, geometry: UPLOAD })) });
    await page.waitForFunction(async () => (await import('/src/store.ts')).useAppStore.getState().aoi !== null);
    await idle();
    const uploaded = await aoi();
    expect('the upload sets the AOI of the file', uploaded?.type === 'Polygon' && Math.abs(uploaded.coordinates[0][0][0] - 10.0) < 1e-6, JSON.stringify(uploaded)?.slice(0, 80));
    const drawn = await page.evaluate((m) => m.getSource('aoi-src')?.serialize().data?.features?.length ?? 0, map);
    expect('the AOI is on the map', drawn === 1, String(drawn));
    const view = await page.evaluate((m) => ({ lon: m.getCenter().lng, lat: m.getCenter().lat, zoom: m.getZoom() }), map);
    expect('the map flew to the uploaded area', Math.abs(view.lon - 10.15) < 0.3 && Math.abs(view.lat - 47.3) < 0.3 && view.zoom > 7, JSON.stringify(view));
    await shot('upload');
    await input.setInputFiles({ name: 'notes.json', mimeType: 'application/json', buffer: Buffer.from('{"not":"geometry"}') });
    await page.waitForTimeout(1500);
    expect('a wrong file leaves the AOI as it was', JSON.stringify(await aoi()) === JSON.stringify(uploaded));
    expect('a wrong file is told to the user', typeof (await store((s) => s.getState().error)) === 'string');

    // 7. The outline of a ticked scene.
    await page.locator('.dataset-toggle', { hasText: 'Sentinel-2' }).first().click();
    await store((s) => { s.getState().setDateFrom('2024-06-01'); s.getState().setDateTo('2024-06-30'); });
    await dock(true);
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await page.waitForSelector('.results-panel');
    await page.waitForTimeout(1500);
    await store((s, id) => s.getState().toggleSelected(id), fixture.features[0].id);
    await idle();
    const outline = await page.evaluate((m) => m.getSource('mosaicsel-src')?.serialize().data?.features?.length ?? 0, map);
    expect('the outline of the ticked scene is on the map', outline >= 1, String(outline));
    expect('the outline layer is drawn', await page.evaluate((m) => m.getLayoutProperty('mosaicsel-line', 'visibility') !== 'none', map));
    await shot('outline');

    console.log(`${tag}: done (blocked or failed requests: ${hosts.other}); ${hosts.told.join(' | ')}`);
    await context.close();
  }
  await browser.close();
  console.log(problems.length ? `FAILED\n- ${problems.join('\n- ')}` : 'OK: the map behaves in every case');
  console.log(`screenshots in ${OUT}`);
  process.exit(problems.length ? 1 : 0);
})();
