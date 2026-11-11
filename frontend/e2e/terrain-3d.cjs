// Browser check of UI-06 (`docs/plans/vp3/ui-06-3d-und-nordpfeil.md`): the compass, zoom and "3D" at the bottom right of the map, in a
// real browser on the real app and the real `api` (the one made-up answer is `POST /stac/search`, as in `map-gl6.cjs`). It does what a
// user does and fails when
//   1. the group is not compass, zoom in, zoom out, 3D from top to bottom, its buttons differ in size, leave the window, or lie under
//      the buttons at the top right; the compass is missing in 2D, or its needle does not point up;
//   2. the map turns or tilts in 2D (a right drag on the map, Shift and the arrows, a drag on the compass): D27 holds in 2D;
//   3. "3D" does not lay the map over the terrain, tilt it to 50°, lift the tilt to 60° and name the elevation tiles in the attribution;
//   4. in 3D a right drag does not turn and tilt the map, the tilt goes past 60°, the needle does not follow the turn, a drag on the
//      compass or ←/→ on it do not turn the map, or a click on it does not turn north and lay the map flat;
//   5. a change of the projection or the overlay "Relief" takes the terrain away;
//   6. the coverage is asked for the extent to the horizon instead of the flat one (F10);
//   7. the Point and Polygon tools set no AOI while the map is tilted;
//   8. "3D" off does not turn north, lay the map flat, take the terrain away and lock the tilt again;
//   9. a reload does not open in 3D after 3D was left on (F12), or a permalink view does not open flat (F11).
// Light and dark theme, 1280, 360 and 320 px, mouse and touch (a tap where a finger taps; the gestures of two fingers are MapLibre's own
// and are not driven here). Screenshots of each theme and size in 2D and in 3D.
//
//   (the api as in the header of no-aoi-in-url.cjs)   cd frontend && npm run dev &
//   node e2e/terrain-3d.cjs                            # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The elevation tiles
// come from s3.amazonaws.com, which the cloud session can reach.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(os.tmpdir(), 'earthx-terrain-3d');
const FIXTURE = path.join(__dirname, '../../backend/tests/fixtures/earth_search/search_page_1.json');
const THEMES = { light: 'normal', dark: 'tech' };
const CONFIGS = [
  { name: 'light wide mouse', theme: 'light', viewport: { width: 1280, height: 800 }, touch: false },
  { name: 'dark wide mouse', theme: 'dark', viewport: { width: 1280, height: 800 }, touch: false },
  { name: 'dark narrow touch', theme: 'dark', viewport: { width: 360, height: 740 }, touch: true },
  { name: 'light smallest touch', theme: 'light', viewport: { width: 320, height: 640 }, touch: true },
];
const ALPS = [10.5, 47];
const near = (a, b, tolerance = 0.5) => Math.abs(a - b) <= tolerance;

(async () => {
  const answered = await fetch(`${BASE}/stac/collections`, { signal: AbortSignal.timeout(10000) }).then((response) => response.ok, () => false);
  if (!answered) {
    console.error(`nothing answers /stac/collections at ${BASE}: start the dev server and the api as in the header`);
    process.exit(2);
  }
  fs.mkdirSync(OUT, { recursive: true });
  const fixture = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
  const problems = [];
  const browser = await chromium.launch();

  for (const config of CONFIGS.filter((_, index) => process.env.ONLY === undefined || process.env.ONLY === String(index))) {
    const tag = config.name;
    const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${tag}: expected ${what}${detail ? ` (${detail})` : ''}`); };
    const context = await browser.newContext({ viewport: config.viewport, hasTouch: config.touch, isMobile: false });
    await context.addInitScript((t) => { if (!sessionStorage.getItem('earthx.e2e')) { localStorage.clear(); localStorage.setItem('earthx.theme', t); sessionStorage.setItem('earthx.e2e', '1'); } }, THEMES[config.theme]);
    const page = await context.newPage();
    page.setDefaultTimeout(15000);
    page.on('pageerror', (error) => problems.push(`${tag}: the page failed: ${error.message.slice(0, 200)}`));
    await page.route('**/stac/search', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) }));
    const shot = (name) => page.screenshot({ path: path.join(OUT, `${config.name.replace(/ /g, '-')}-${name}.png`) });
    const store = (fn, arg) => page.evaluate(async ([src, data]) => {
      const { useAppStore } = await import('/src/store.ts');
      return (0, eval)(`(${src})`)(useAppStore, data);
    }, [fn.toString(), arg]);

    // Under 900 px a panel of the rail covers the whole map (UI-03), the buttons too: it is closed to reach them.
    const dock = async (openIt) => {
      const rail = page.getByRole('button', { name: 'Search and area' });
      if ((await rail.getAttribute('aria-expanded')) !== String(openIt)) await rail.click();
    };
    const open = async () => {
      await page.goto(BASE);
      await page.waitForSelector('.maplibregl-canvas');
      await page.waitForSelector('.map-controls');
      await page.waitForSelector('.dataset-toggle');
      await dock(false);
    };
    await open();
    // The map of the app: its ref lives in the hooks of `MapView`; nothing of the app is changed to reach it.
    const mapHandle = () => page.evaluateHandle(() => {
      let fiber = document.querySelector('.maplibregl-map')[Object.keys(document.querySelector('.maplibregl-map')).find((k) => k.startsWith('__reactFiber$'))];
      for (; fiber; fiber = fiber.return) {
        for (let hook = fiber.memoizedState; hook && typeof hook === 'object'; hook = hook.next) {
          const held = hook.memoizedState?.current;
          if (held && typeof held.getStyle === 'function') return held;
        }
      }
      return null;
    });
    let map = await mapHandle();
    const camera = () => page.evaluate((m) => ({ pitch: m.getPitch(), bearing: m.getBearing(), maxPitch: m.getMaxPitch(), terrain: m.getTerrain()?.source ?? null }), map);
    const settle = () => page.evaluate((m) => new Promise((resolve) => {
      const timer = setTimeout(resolve, 8000);
      const done = () => { clearTimeout(timer); resolve(); };
      if (m.isMoving()) m.once('moveend', () => m.once('idle', done)); else m.once('idle', done);
      m.triggerRepaint();
    }), map);
    const jump = (lon, lat, zoom) => page.evaluate(([m, args]) => { m.jumpTo({ center: [args[0], args[1]], zoom: args[2] }); }, [map, [lon, lat, zoom]]);
    const press = async (locator) => { if (config.touch) await locator.tap(); else await locator.click(); };
    const needle = () => page.locator('.compass-needle').evaluate((svg) => svg.style.transform);
    // The browser shortens the number in the style: compared as a number.
    const needleAt = async (degrees) => near(Number(/rotate\((-?[\d.e-]+)deg\)/.exec(await needle())?.[1]), degrees, 0.01);
    const button = (selector) => page.locator(`.map-controls ${selector}`);
    const compass = button('.map-compass');
    const three = button('.map-3d');
    const box = await page.locator('.maplibregl-canvas').boundingBox();
    const at = (fx, fy) => ({ x: box.x + box.width * fx, y: box.y + box.height * fy });
    const rightDrag = async (dx, dy) => {
      const from = at(0.5, 0.5);
      await page.mouse.move(from.x, from.y);
      await page.mouse.down({ button: 'right' });
      await page.mouse.move(from.x + dx, from.y + dy, { steps: 12 });
      await page.mouse.up({ button: 'right' });
    };
    const compassDrag = async () => {
      const b = await compass.boundingBox();
      const c = { x: b.x + b.width / 2, y: b.y + b.height / 2 };
      // Inside the round button, a third of its size from its centre: right of it, then below it.
      await page.mouse.move(c.x + b.width / 3, c.y);
      await page.mouse.down();
      await page.mouse.move(c.x, c.y + b.height / 3, { steps: 8 });
      await page.mouse.up();
    };

    await jump(...ALPS, 9);
    await settle();

    // 1. The group, in 2D.
    const names = await page.locator('.map-controls > button').evaluateAll((all) => all.map((b) => b.getAttribute('aria-label') ?? b.textContent));
    expect('compass, zoom in, zoom out and 3D from top to bottom', JSON.stringify(names) === JSON.stringify(['Reset north and tilt', 'Zoom in', 'Zoom out', '3D']), names.join(', '));
    const boxes = await page.locator('.map-controls > button').evaluateAll((all) => all.map((b) => { const r = b.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
    const height = config.touch || config.viewport.width < 900 ? 44 : 28;
    expect(`buttons of ${height} px, all the same`, boxes.every((b) => near(b.w, height, 1) && near(b.h, height, 1)), JSON.stringify(boxes.map((b) => [b.w, b.h])));
    expect('the buttons in one column, top to bottom', boxes.every((b, i) => i === 0 || (b.y > boxes[i - 1].y && near(b.x, boxes[0].x, 1))));
    expect('the group inside the window', boxes.every((b) => b.x >= 0 && b.y >= 0 && b.x + b.w <= config.viewport.width && b.y + b.h <= config.viewport.height));
    const top = await page.locator('.overlay.top-right').boundingBox();
    expect('the group below the buttons at the top right', !top || boxes[0].y >= top.y + top.height);
    expect('the compass is there in 2D and points up', (await compass.isVisible()) && (await needle()) === 'rotate(0deg)', await needle());
    const round = await compass.evaluate((b) => getComputedStyle(b).borderTopLeftRadius);
    expect('the compass to be round', round === '50%' || parseFloat(round) >= height / 2 - 1, round);
    const colours = await page.evaluate(() => ['.compass-north', '.compass-south'].map((s) => getComputedStyle(document.querySelector(s)).fill));
    expect('a red north half and a south half of another colour', colours[0] !== colours[1] && /rgb/.test(colours[0]), colours.join(' / '));
    await shot('2d');

    // 2. No turn and no tilt in 2D (D27).
    if (!config.touch) {
      await rightDrag(120, -80);
      await page.locator('.maplibregl-canvas').focus();
      await page.keyboard.press('Shift+ArrowRight');
      await page.keyboard.press('Shift+ArrowUp');
      await compassDrag();
      await settle();
    }
    let now = await camera();
    expect('no turn and no tilt in 2D', now.pitch === 0 && now.bearing === 0 && now.maxPitch === 0 && now.terrain === null, JSON.stringify(now));
    await press(compass);
    expect('the compass not locked in 2D', (await compass.getAttribute('aria-disabled')) === null);

    // 3. 3D on.
    await press(three);
    await settle();
    now = await camera();
    expect('"3D" pressed', (await three.getAttribute('aria-pressed')) === 'true');
    expect('3D tilts to 50° over the terrain, with a tilt up to 60°', near(now.pitch, 50) && now.terrain === 'terrain' && now.maxPitch === 60, JSON.stringify(now));
    // Filled in the accent, also with the pointer on it (MapLibre's own hover of a button in its controls must not reach it).
    if (!config.touch) await three.hover();
    const filled = await three.evaluate((b) => {
      const probe = document.createElement('div');
      probe.style.background = 'var(--accent)';
      b.closest('.app').appendChild(probe);
      const accent = getComputedStyle(probe).backgroundColor;
      probe.remove();
      return [getComputedStyle(b).backgroundColor, accent];
    });
    expect('"3D" filled in the accent while on', filled[0] === filled[1], filled.join(' / '));
    const attribution = await page.locator('.maplibregl-ctrl-attrib').innerText();
    expect('the attribution names the elevation tiles', /Terrain:/.test(attribution), attribution.slice(0, 120));
    expect('the choice kept in the browser', (await page.evaluate(() => localStorage.getItem('earthx.terrain'))) === 'on');
    await shot('3d');

    // 4. Turning and tilting in 3D.
    if (!config.touch) {
      await rightDrag(160, -200);
      await settle();
      now = await camera();
      expect('a right drag turns the map in 3D', !near(now.bearing, 0, 1), JSON.stringify(now));
      expect('the tilt not past 60°', now.pitch <= 60.01, JSON.stringify(now));
      expect('the needle turned against the map', await needleAt(-now.bearing), `${await needle()} at ${now.bearing}`);
      await press(compass);
      await settle();
      now = await camera();
      expect('a click on the compass turns north and lays the map flat, still in 3D', near(now.bearing, 0, 0.01) && near(now.pitch, 0, 0.01) && now.terrain === 'terrain', JSON.stringify(now));
      await compassDrag();
      await settle();
      now = await camera();
      expect('a drag on the compass turns the map a quarter', near(Math.abs(now.bearing), 90, 3), JSON.stringify(now));
      await press(compass);
      await settle();
      await compass.focus();
      await page.keyboard.press('ArrowRight');
      await settle();
      now = await camera();
      expect('→ on the compass turns by 15°', near(now.bearing, 15, 0.5), JSON.stringify(now));
      await page.evaluate((m) => m.easeTo({ pitch: 50, duration: 0 }), map);
      await settle();
    } else {
      await page.evaluate((m) => m.jumpTo({ bearing: 40 }), map);
      await settle();
      expect('the needle turned against the map', await needleAt(-40), await needle());
      await press(compass);
      await settle();
      now = await camera();
      expect('a tap on the compass turns north and lays the map flat', near(now.bearing, 0, 0.01) && near(now.pitch, 0, 0.01), JSON.stringify(now));
      await page.evaluate((m) => m.jumpTo({ pitch: 50 }), map);
    }
    now = await page.evaluate((m) => { m.jumpTo({ pitch: 85 }); return m.getPitch(); }, map);
    expect('the tilt held at 60°', near(now, 60, 0.01), String(now));
    await page.evaluate((m) => m.jumpTo({ pitch: 50 }), map);

    // 5. The projection and the relief keep the terrain.
    for (const [group, name] of [['Projection', /Globe/], ['Overlays', /Relief/], ['Projection', /Mercator/], ['Overlays', /Relief/]]) {
      await store((s, [g, n]) => {
        const st = s.getState();
        if (g === 'Projection') st.setProjection(n);
        else st.setOverlay('relief', !st.overlays.relief);
      }, [group, name.source.toLowerCase()]);
      await settle();
      expect(`the terrain after ${group} ${name.source}`, (await camera()).terrain === 'terrain');
    }

    // 6. The coverage asks for the flat extent of a tilted map.
    await jump(...ALPS, 8);
    await settle();
    const extents = await page.evaluate(async (m) => {
      const { useAppStore } = await import('/src/store.ts');
      const b = m.getBounds();
      return { told: useAppStore.getState().viewportBbox, horizon: [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()] };
    }, map);
    const span = (bbox) => (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]);
    expect('the coverage told a smaller, flat extent than the horizon', extents.told && span(extents.told) < span(extents.horizon), JSON.stringify(extents));

    // 7. The AOI tools on a tilted map.
    const tool = (name) => page.getByRole('group', { name: 'Area of interest tools' }).getByRole('button', { name, exact: true });
    const aoi = () => store((s) => s.getState().aoi);
    const pick = async (name) => { await dock(true); if ((await tool(name).getAttribute('aria-pressed')) !== 'true') await tool(name).click(); await dock(false); };
    const tap = async (p) => { if (config.touch) await page.touchscreen.tap(p.x, p.y); else await page.mouse.click(p.x, p.y); };
    await pick('Point');
    await tap(at(0.5, 0.6));
    await page.waitForTimeout(600);
    expect('the Point tool sets an AOI on a tilted map', (await aoi())?.type === 'Polygon');
    await settle();
    await page.evaluate((m) => m.jumpTo({ pitch: 50 }), map);
    await dock(true);
    await tool('Clear AOI').click();
    await pick('Polygon');
    const corners = [at(0.4, 0.55), at(0.6, 0.55), at(0.5, 0.75)];
    for (const c of corners) { await tap(c); await page.waitForTimeout(250); }
    if (config.touch) { await page.touchscreen.tap(corners[2].x, corners[2].y); await page.waitForTimeout(80); await page.touchscreen.tap(corners[2].x, corners[2].y); } else await page.mouse.dblclick(corners[2].x, corners[2].y);
    await page.waitForTimeout(600);
    const polygon = await aoi();
    expect('the Polygon tool sets a polygon on a tilted map', polygon?.type === 'Polygon' && polygon.coordinates[0].length >= 4, JSON.stringify(polygon)?.slice(0, 80));
    await settle();
    await shot('3d-aoi');
    await dock(true);
    await tool('Clear AOI').click();
    await dock(false);

    // 9a. A reload opens in 3D.
    await open();
    map = await mapHandle();
    await settle();
    now = await camera();
    expect('a reload opens in 3D, tilted to 50°', now.terrain === 'terrain' && near(now.pitch, 50), JSON.stringify(now));

    // 8. 3D off.
    await page.evaluate((m) => m.jumpTo({ bearing: 30 }), map);
    await press(three);
    await settle();
    now = await camera();
    expect('"3D" off turns north, lays the map flat, takes the terrain away and locks the tilt', now.pitch === 0 && near(now.bearing, 0, 0.01) && now.terrain === null && now.maxPitch === 0, JSON.stringify(now));
    expect('"3D" not pressed', (await three.getAttribute('aria-pressed')) === 'false');

    // 9b. A permalink view opens flat and keeps the choice.
    await press(three);
    await settle();
    await store((s) => s.getState().showSharedLook({ basemap: 'satellite', projection: 'mercator' }));
    await settle();
    now = await camera();
    expect('a permalink view opens flat', now.terrain === null && now.pitch === 0, JSON.stringify(now));
    expect('a permalink leaves the kept choice', (await page.evaluate(() => localStorage.getItem('earthx.terrain'))) === 'on');
    await context.close();
  }
  await browser.close();
  if (problems.length) {
    console.error(problems.join('\n'));
    process.exit(1);
  }
  console.log(`all checks passed; screenshots in ${OUT}`);
})();
