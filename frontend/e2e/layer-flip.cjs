// Browser check of "Flip through layers" (NM4-65 part 9), with the real map: three layers that cover the map, each one plain colour.
// The list has red on top, then green, then blue; the check counts the pixels of the map.
//   - on: the clicked layer is the colour of the map, wherever it stands in the list; the list is not moved
//   - ↓/↑ and the mouse wheel over the list step to the next layer; the wheel over the map zooms and does not step
//   - a layer that is switched off is passed by
//   - Esc ends it: the map shows red again
// Light and dark theme, a wide and a narrow window; a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed
//   node e2e/layer-flip.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. If the page
// shows no layers after files were changed, restart the dev server (Vite stamps changed modules).

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const zlib = require('node:zlib');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-layer-flip');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, narrow: { width: 360, height: 740 } };
const COLOURS = { red: [230, 30, 30], green: [30, 200, 40], blue: [40, 60, 230] };

function png(rgb) {
  const crcTable = Array.from({ length: 256 }, (_, n) => {
    let c = n;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    return c >>> 0;
  });
  const crc = (buffer) => {
    let c = 0xffffffff;
    for (const byte of buffer) c = crcTable[(c ^ byte) & 0xff] ^ (c >>> 8);
    return (c ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, data) => {
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length);
    const body = Buffer.concat([Buffer.from(type), data]);
    const sum = Buffer.alloc(4);
    sum.writeUInt32BE(crc(body));
    return Buffer.concat([length, body, sum]);
  };
  const size = 256;
  const header = Buffer.alloc(13);
  header.writeUInt32BE(size, 0);
  header.writeUInt32BE(size, 4);
  header[8] = 8;
  header[9] = 6;
  const row = Buffer.concat([Buffer.from([0]), Buffer.alloc(size * 4)]);
  for (let x = 0; x < size; x++) row.set([...rgb, 255], 1 + x * 4);
  const raw = Buffer.concat(Array.from({ length: size }, () => row));
  return Buffer.concat([Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk('IHDR', header), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

const store = (page, code) => page.evaluate(async (c) => new Function('s', `return (${c})`)((await import('/src/store.ts')).useAppStore.getState()), code);

// The colour that most of the map is, by counting the pixels of the page that are (near) one of the three.
async function dominant(page) {
  const narrow = page.viewportSize().width < 600;
  const dock = narrow ? await store(page, 's.dock') : null;
  if (narrow) await store(page, '(s.closeDock(), 1)');
  if (narrow) await page.waitForTimeout(1200);
  else await page.waitForTimeout(1200);
  const shot = (await page.screenshot()).toString('base64');
  if (narrow && dock) await store(page, `(s.toggleDock(${JSON.stringify(dock)}), 1)`);
  return page.evaluate(async ({ shot, colours }) => {
    const img = new Image();
    img.src = `data:image/png;base64,${shot}`;
    await img.decode();
    const canvas = document.createElement('canvas');
    canvas.width = img.width;
    canvas.height = img.height;
    const ctx = canvas.getContext('2d');
    ctx.drawImage(img, 0, 0);
    const { data } = ctx.getImageData(0, 0, img.width, img.height);
    const counts = Object.fromEntries(Object.keys(colours).map((name) => [name, 0]));
    for (let i = 0; i < data.length; i += 4) {
      for (const [name, [r, g, b]] of Object.entries(colours)) if (Math.abs(data[i] - r) < 40 && Math.abs(data[i + 1] - g) < 40 && Math.abs(data[i + 2] - b) < 40) counts[name]++;
    }
    const best = Object.entries(counts).sort((a, b) => b[1] - a[1]);
    return { best: best[0][1] > 2000 ? best[0][0] : 'none', counts };
  }, { shot, colours: COLOURS });
}

async function check(browser, { theme, viewport }) {
  const label = `${theme} ${viewport}`;
  const problems = [];
  const context = await browser.newContext({ viewport: VIEWPORTS[viewport] });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.setDefaultTimeout(8000);
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 160)}`));
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    const colour = /^\/flip-(red|green|blue)\//.exec(url.pathname)?.[1];
    if (url.origin === BASE && colour) return route.fulfill({ status: 200, contentType: 'image/png', body: png(COLOURS[colour]) });
    if (url.origin !== BASE || /^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return route.continue();
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"detail":"not made up"}' });
  });
  let stage = 'start';
  try {
  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle, .app-rail');
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (step) => page.screenshot({ path: path.join(OUT, `${label.replace(/ /g, '_')}_${step}.png`) });
  await page.evaluate(async (narrow) => {
    const { useAppStore } = await import('/src/store.ts');
    const restore = { focusMode: false, downloaded: {}, appliedRender: {}, activeGroupIndex: 0, selectedIds: [], itemIds: [], groupItemIds: [], aoi: null, cropToAoi: false, datasetId: null };
    const make = (id, name) => ({
      id, name, visible: true, opacity: 1, restore,
      overlays: [{ kind: 'raster', tileUrl: `${location.origin}/flip-${id}/{z}/{x}/{y}.png`, bounds: [-180, -85, 180, 85], minZoom: 0, maxZoom: 14 }],
    });
    useAppStore.setState({ dock: narrow ? null : 'layers', layers: [make('red', 'Red'), make('green', 'Green'), make('blue', 'Blue')], flyToView: { center: [10, 48], zoom: 5 } });
  }, viewport === 'narrow');
  if (viewport === 'narrow') await store(page, "(s.toggleDock('layers'), 1)");
  await page.waitForSelector('.layer-row');
  const order = () => store(page, "s.layers.map((l) => l.id).join()");
  // The keys go to the manager where the focus is: a narrow window folds it away for the count, so the focus is given back.
  const press = async (name) => {
    await page.locator('.layer-row.flip .lm-name').focus();
    await page.keyboard.press(name);
  };
  // Tiles arrive one by one: the map is looked at again, up to six times, until it is (almost) all the colour asked for.
  const expectColour = async (step, want) => {
    let seen;
    for (let attempt = 0; attempt < 6; attempt++) {
      seen = await dominant(page);
      const total = Object.values(seen.counts).reduce((a, b) => a + b, 0);
      if (seen.best === want && seen.counts[want] > 0.95 * total) return;
      await page.waitForTimeout(600);
    }
    problems.push(`${step}: the map is ${seen.best}, expected ${want} (${JSON.stringify(seen.counts)})`);
  };

  await expectColour('before', 'red');
  stage = 'toggle on';
  const toggle = page.locator('.lm-flip');
  if ((await toggle.getAttribute('title')) !== 'Flip through layers (↑/↓ or the mouse wheel over the list, Esc to stop)') problems.push(`tooltip: ${await toggle.getAttribute('title')}`);
  await toggle.click();
  if ((await toggle.getAttribute('aria-pressed')) !== 'true') problems.push('the toggle does not show that it is on');
  await expectColour('on, first layer', 'red');
  await page.locator('.layer-row .lm-name').nth(2).click();
  await expectColour('clicked the layer at the bottom of the list', 'blue');
  if ((await order()) !== 'red,green,blue') problems.push(`the list moved: ${await order()}`);
  const marked = await page.$$eval('.layer-row', (rows) => rows.map((row) => row.classList.contains('flip')));
  if (JSON.stringify(marked) !== '[false,false,true]') problems.push(`the row that is on top is not marked: ${JSON.stringify(marked)}`);
  await shot('1-blue-on-top');

  stage = 'keys';
  // Keys: from the name button that holds the focus.
  await press('ArrowUp');
  await expectColour('↑', 'green');
  await press('ArrowUp');
  await expectColour('↑ again', 'red');
  await press('ArrowUp');
  await expectColour('↑ at the top stops', 'red');
  await press('ArrowDown');
  await expectColour('↓', 'green');
  await shot('2-green-on-top');

  stage = 'wheel';
  // The mouse wheel over the list steps; over the map it zooms.
  const list = await page.locator('.layer-list').boundingBox();
  await page.mouse.move(list.x + list.width / 2, list.y + 20);
  await page.mouse.wheel(0, 120);
  await expectColour('wheel down over the list', 'blue');
  await page.waitForTimeout(300);
  await page.mouse.wheel(0, -120);
  await expectColour('wheel up over the list', 'green');
  if (viewport === 'wide') {
    const zoom = () => store(page, 's.mapZoom');
    const before = await zoom();
    await page.mouse.move(800, 400);
    await page.mouse.wheel(0, -300);
    await page.waitForTimeout(800);
    const after = await zoom();
    if (!(after > before)) problems.push(`the wheel over the map did not zoom: ${before} → ${after}`);
    if ((await store(page, 's.flipLayerId')) !== 'green') problems.push('the wheel over the map stepped through the layers');
  }

  stage = 'eye';
  // A layer that is switched off is passed by.
  await page.locator('.layer-row .lm-eye').nth(2).click();
  await page.locator('.layer-row .lm-name').nth(1).click();
  await press('ArrowDown');
  if ((await store(page, 's.flipLayerId')) !== 'green') problems.push(`↓ went to the layer that is switched off: ${await store(page, 's.flipLayerId')}`);
  await page.locator('.layer-row .lm-eye').nth(2).click();

  stage = 'esc';
  // Esc ends it.
  await page.keyboard.press('Escape');
  if ((await toggle.getAttribute('aria-pressed')) !== 'false') problems.push('Esc did not end it');
  await expectColour('after Esc', 'red');
  await shot('3-off');
  stage = 'toggle off';
  // The toggle ends it too.
  await toggle.click();
  await page.locator('.layer-row .lm-name').nth(1).click();
  await expectColour('on again', 'green');
  await toggle.click();
  await expectColour('off by the toggle', 'red');
  if ((await order()) !== 'red,green,blue') problems.push(`the list moved: ${await order()}`);

  } catch (error) {
    problems.push(`the check broke at "${stage}": ${error.message.split('\n').slice(0, 6).join(' ')}`);
  }
  await context.close();
  return { name: label, problems };
}

(async () => {
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      const result = await check(browser, { theme, viewport }).catch((error) => ({ name: `${theme} ${viewport}`, problems: [`the check broke: ${error.message.split('\n').slice(0, 3).join(' ')}`] }));
      failed += result.problems.length > 0 ? 1 : 0;
      console.log(`${result.problems.length ? 'FAIL' : 'ok  '} ${result.name}${result.problems.length ? '\n     ' + result.problems.join('\n     ') : ''}`);
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
