// Browser check of the legends over the map (M5-62, Otto 24.11.2026). With one, two and three made-up layers (the eleven classes of
// ESA WorldCover, heights in metres on a colour scale, the twelve classes of a scene classification), the panel of the rail open and
// closed, in the light and the dark theme, at 1280×800, 1280×360 and 360×740, it fails when
//   - there is not one legend per layer, in the order of the layers, titled by the layer;
//   - a legend leaves the window, scrolls, or is cut off where folding the legends would have made room;
//   - a legend covers a control: the rail, the panel of the rail (where the map is beside it), the settings, the map buttons, the
//     button at the top right or the marks at the bottom;
//   - the legends do not stand beside the panel of the rail at the bottom left, moving with it;
//   - a list of seven classes or more is not in two columns (one under 900 px), a class name is cut off, or a bar has not the
//     colours of its colormap;
// and writes a screenshot per case.
//
//   cd frontend && npm run dev &            # the dev server; no backend is needed, the answers are made up here
//   node e2e/map-legend.cjs                 # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// Playwright and Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The
// screenshots stay out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-map-legend');
const THEMES = { light: 'normal', dark: 'tech' };
const VIEWPORTS = { wide: { width: 1280, height: 800 }, low: { width: 1280, height: 360 }, narrow: { width: 360, height: 740 } };

const WORLDCOVER = [
  [10, 'Tree cover', '#006400'], [20, 'Shrubland', '#ffbb22'], [30, 'Grassland', '#ffff4c'], [40, 'Cropland', '#f096ff'],
  [50, 'Built-up', '#fa0000'], [60, 'Bare / sparse vegetation', '#b4b4b4'], [70, 'Snow and ice', '#f0f0f0'],
  [80, 'Permanent water bodies', '#0064c8'], [90, 'Herbaceous wetland', '#0096a0'], [95, 'Mangroves', '#00cf75'],
  [100, 'Moss and lichen', '#fae6a0'],
].map(([value, name, colour]) => ({ value, name, colour }));
const SCL = [
  'Saturated or defective', 'Topographic shadows', 'Cloud shadows', 'Vegetation', 'Not vegetated', 'Water', 'Unclassified',
  'Cloud medium probability', 'Cloud high probability', 'Thin cirrus', 'Snow or ice',
].map((name, i) => ({ value: i + 1, name, colour: ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf', '#aec7e8'][i] }));
const TERRAIN = ['#333399', '#0294fa', '#24d36d', '#fefe98', '#82694d', '#ffffff'];
const COLORMAPS = { groups: [{ name: 'other', colormaps: [{ name: 'terrain', reversed: 'terrain_r', colors: TERRAIN }, { name: 'gray', reversed: 'gray_r', colors: ['#000000', '#ffffff'] }] }] };

// The layers, the topmost first: what the layer manager lists.
const LAYERS = [
  { id: 'L1', name: 'Land cover · 2021', query: '&colormap=x', legend: WORLDCOVER },
  { id: 'L2', name: 'Heights', query: '&colormap_name=terrain&rescale=0%2C2900', unit: 'm' },
  { id: 'L3', name: 'Scene classification', query: '&colormap=x', legend: SCL },
];
const rgb = (hex) => `rgb(${parseInt(hex.slice(1, 3), 16)}, ${parseInt(hex.slice(3, 5), 16)}, ${parseInt(hex.slice(5, 7), 16)})`;
const overlap = (a, b) => a.x < b.x + b.width - 0.5 && b.x < a.x + a.width - 0.5 && a.y < b.y + b.height - 0.5 && b.y < a.y + a.height - 0.5;
const inWindow = (box, size) => box.x >= -0.5 && box.y >= -0.5 && box.x + box.width <= size.width + 0.5 && box.y + box.height <= size.height + 0.5;

async function check(browser, { count, panel, theme, viewport }) {
  const problems = [];
  const size = VIEWPORTS[viewport];
  const context = await browser.newContext({ viewport: size });
  await context.addInitScript((t) => localStorage.setItem('earthx.theme', t), THEMES[theme]);
  const page = await context.newPage();
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  await page.route('**/*', async (r) => {
    const url = new URL(r.request().url());
    const json = (body, status = 200) => r.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
    if (url.origin !== BASE) return r.fulfill({ status: 404, body: '' });
    if (/^\/(src|@|node_modules|assets)/.test(url.pathname) || url.pathname === '/' || url.pathname.endsWith('.svg')) return r.continue();
    if (url.pathname === '/colormaps') return json(COLORMAPS);
    if (url.pathname.startsWith('/results/')) return r.fulfill({ status: 404, body: '' });
    return json({ detail: 'not made up' }, 404);
  });
  await page.goto(BASE);
  await page.locator('.app-rail').waitFor();
  await page.evaluate(async ({ layers, panel }) => {
    const { useAppStore } = await import('/src/store.ts');
    const made = layers.map((l) => ({
      id: l.id, name: l.name, visible: true, opacity: 1, derived: 'result', restore: { datasetId: null, itemIds: [] },
      overlays: [{ kind: 'raster', tileUrl: `/results/AbCdEfGhIjKlMnOpQr${l.id}/tiles/WebMercatorQuad/{z}/{x}/{y}?tilesize=256${l.query}`, bounds: [10, 50, 11, 51], minZoom: 0, maxZoom: 14 }],
      result: { jobID: `AbCdEfGhIjKlMnOpQr${l.id}`, expires: new Date(Date.now() + 86_400_000).toISOString(), gsd: 10, resampled: null, expired: false, dataType: 'uint8', stats: null, ...(l.legend ? { classes: true, legend: l.legend } : {}), ...(l.unit ? { unit: l.unit } : {}) },
    }));
    useAppStore.setState({ layers: made, resultsAt: made.length, dock: panel ? 'controls' : null });
  }, { layers: LAYERS.slice(0, count), panel });
  const legends = page.locator('.map-legend .legend');
  await legends.first().waitFor({ timeout: 10000 }).catch(() => problems.push('no legend over the map'));
  await page.waitForTimeout(150);

  const titles = await page.locator('.legend-title').allTextContents();
  const expected = LAYERS.slice(0, count).map((l) => l.name);
  if (JSON.stringify(titles) !== JSON.stringify(expected)) problems.push(`the titles are ${JSON.stringify(titles)}, not ${JSON.stringify(expected)}`);

  // Two columns for the long lists, the colours of the classes and of the colormap.
  for (const [index, layer] of LAYERS.slice(0, count).entries()) {
    const legend = legends.nth(index);
    if (layer.legend) {
      // Two columns where the window is wide, one under 900 px, where two would cut the names.
      const columns = await legend.locator('.legend-classes').evaluate((el) => getComputedStyle(el).gridTemplateColumns.split(' ').length);
      if (columns !== (size.width >= 900 ? 2 : 1)) problems.push(`${layer.name}: ${layer.legend.length} classes in ${columns} columns`);
      const cutNames = await legend.locator('.legend-name').evaluateAll((els) => els.filter((el) => el.scrollWidth > el.clientWidth + 1).map((el) => el.textContent));
      if (cutNames.length > 0) problems.push(`${layer.name}: names cut off: ${cutNames.join(', ')}`);
      const swatches = await legend.locator('.class-swatch').evaluateAll((els) => els.map((el) => getComputedStyle(el).backgroundColor));
      if (JSON.stringify(swatches) !== JSON.stringify(layer.legend.map((c) => rgb(c.colour)))) problems.push(`${layer.name}: the swatches are not the colours of the classes`);
    } else {
      const background = await legend.locator('.legend-bar').evaluate((el) => getComputedStyle(el).backgroundImage);
      if (!background.includes(rgb(TERRAIN[0])) || !background.includes(rgb(TERRAIN.at(-1)))) problems.push(`${layer.name}: the bar is not in the colours of terrain`);
      const ends = await legend.locator('.legend-ends span').allTextContents();
      if (JSON.stringify(ends) !== JSON.stringify(['0 m', '2900 m'])) problems.push(`${layer.name}: the ends say ${JSON.stringify(ends)}`);
    }
  }

  // Never scrolling; where the legends are cut off, folding them from the bottom up must make room.
  const box = page.locator('.map-legend');
  const cut = () => box.evaluate((el) => el.scrollHeight > el.clientHeight + 1);
  const scrolls = await box.evaluate((el) => getComputedStyle(el).overflowY);
  if (scrolls === 'auto' || scrolls === 'scroll') problems.push('the legends scroll');
  let folded = 0;
  while ((await cut()) && folded < count) {
    await page.locator('.legend-title').nth(count - 1 - folded).click();
    folded += 1;
  }
  if (await cut()) problems.push('the legends are cut off even with every one folded');
  const own = await box.boundingBox();
  if (!own || !inWindow(own, size)) problems.push(`the legends leave the window: ${JSON.stringify(own)}`);

  // Beside the panel of the rail, at the bottom left, moving with it (a wide window: the map is beside the panel).
  const wide = size.width >= 900;
  const rail = await page.locator('.app-rail').boundingBox();
  const dock = panel ? await page.locator('.dock').boundingBox() : null;
  const left = (wide && dock ? dock.x + dock.width : rail.x + rail.width) + 16;
  if (own && Math.abs(own.x - left) > 1) problems.push(`the legends stand at x=${own.x}, not beside the panel at ${left}`);

  // Over no control. Below 900 px an open panel covers the map, and the legends with it: they lie under it, not over it.
  const controls = ['.app-rail', '.inspector', '.map-controls-host', '.overlay.top-right > *', '.preview-badge-dock > *', '.overlay.bottom > *', ...(wide ? ['.dock'] : [])];
  for (const selector of controls) {
    for (const other of await page.locator(selector).all()) {
      const b = await other.boundingBox();
      if (b && own && b.width > 0 && overlap(own, b)) problems.push(`the legends cover ${selector}: ${JSON.stringify(b)}`);
    }
  }
  if (!wide && panel && own) {
    const onTop = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('.dock') !== null, { x: own.x + own.width / 2, y: own.y + own.height / 2 });
    if (!onTop) problems.push('in a narrow window the legends lie over the open panel');
  }
  await page.screenshot({ path: path.join(OUT, `legend-${count}-${panel ? 'panel' : 'nopanel'}-${theme}-${viewport}.png`) });
  if (folded) console.log(`     (${count} layers, ${viewport}: ${folded} folded to fit)`);
  await context.close();
  return problems;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await chromium.launch();
  let failed = 0;
  for (const theme of Object.keys(THEMES)) {
    for (const viewport of Object.keys(VIEWPORTS)) {
      for (const panel of [true, false]) {
        for (const count of [1, 2, 3]) {
          const problems = await check(browser, { count, panel, theme, viewport });
          failed += problems.length;
          const name = `${count} layer${count > 1 ? 's' : ''} ${panel ? 'panel open' : 'panel closed'} ${theme} ${viewport}`;
          console.log(`${problems.length ? 'FAIL' : 'ok  '} ${name}${problems.map((p) => `\n     - ${p}`).join('')}`);
        }
      }
    }
  }
  await browser.close();
  console.log(`screenshots in ${OUT}`);
  process.exit(failed ? 1 : 0);
})();
