// Browser check of NM4-57 (M4 Q8): no URL the browser asks for carries the coordinates of an AOI, and the coverage of an
// AOI is a POST. It does what a user does with an area: sets it, shows the coverage map, searches, looks at the previews of
// the results, ticks a scene for the view, and then takes the area away and moves the map. Every request of the page is
// recorded with its method, URL, status and body, and the check fails when
//   - a coordinate of the AOI stands in a URL (path, query, in any spelling a browser sends: plain or percent-encoded);
//   - the coverage of the AOI is not a POST, or its body does not carry the box of the AOI;
//   - the coverage of the map extent (no AOI) is refused (a 400 means the extent is off the grid the route knows);
//   - the page address itself carries the AOI.
//
//   cd frontend && npm run dev &            # the dev server, with `api` (8000) and `tiler` (8001) behind it
//   node e2e/no-aoi-in-url.cjs              # BASE=http://localhost:5173 OUT=<directory for the screenshots>
//
// The one answer that is made up is `POST /stac/search`: the source of the datasets is not reachable from every machine
// (the gateway connects without a proxy), and the previews and the view need results. The answer is the synthetic fixture
// of `backend/tests/fixtures/earth_search/search_page_1.json`. Everything else goes to the real processes. Playwright and
// Chromium are not a dependency of the project (CI does not run this); the cloud session has both. The screenshots stay
// out of the repository.

const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');

const BASE = process.env.BASE ?? 'http://localhost:5173';
const OUT = process.env.OUT ?? path.join(require('node:os').tmpdir(), 'earthx-no-aoi-in-url');
const FIXTURE = path.join(__dirname, '../../backend/tests/fixtures/earth_search/search_page_1.json');
const DATASET = 'sentinel-2-c1-l2a';
// Made up, inside the footprint of the fixture's first scene. The digits are the ones to look for.
const AOI = { type: 'Polygon', coordinates: [[[9.3412, 48.3317], [9.6218, 48.3317], [9.6218, 48.5624], [9.3412, 48.5624], [9.3412, 48.3317]]] };
const SECRETS = ['9.3412', '9.6218', '48.3317', '48.5624'];
const ASSETS = /^\/(src|@|node_modules)/;

(async () => {
  const problems = [];
  const expect = (what, ok, detail = '') => { if (!ok) problems.push(`${what}${detail ? `: ${detail}` : ''}`); };
  const browser = await chromium.launch();
  const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 } })).newPage();
  page.setDefaultTimeout(15000);
  const asked = [];
  const answers = new Map();
  page.on('request', (request) => asked.push({ method: request.method(), url: request.url(), body: request.postData(), request }));
  page.on('response', (response) => answers.set(response.request(), response.status()));
  page.on('pageerror', (error) => problems.push(`the page failed: ${error.message.slice(0, 200)}`));
  const fixture = JSON.parse(fs.readFileSync(FIXTURE, 'utf8'));
  // The fixture is the shape of a source's answer; the grouping of the results also wants the datatake of a Sentinel-2 scene.
  fixture.features.forEach((item, index) => { item.properties['s2:datatake_id'] = `SYNTH_DATATAKE_${index}`; });
  await page.route('**/stac/search', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(fixture) }));
  const store = (fn, arg) => page.evaluate(async ([src, data]) => {
    const { useAppStore } = await import('/src/store.ts');
    return (0, eval)(`(${src})`)(useAppStore, data);
  }, [fn.toString(), arg]);
  const settle = (ms = 1500) => page.waitForTimeout(ms);
  fs.mkdirSync(OUT, { recursive: true });
  const shot = (name) => page.screenshot({ path: path.join(OUT, `${name}.png`) });

  await page.goto(BASE);
  await page.waitForSelector('.dataset-toggle');
  await page.locator('.dataset-toggle', { hasText: 'Sentinel-2' }).first().click();

  // 1. An AOI, and the coverage map of its dataset.
  await store((s, aoi) => { s.getState().setAoi(aoi); s.getState().flyTo([9.2, 48.2, 9.8, 48.7]); }, AOI);
  await settle();
  await store((s, id) => s.getState().showCoverageFor(id), DATASET);
  await settle(4000);
  await shot('1-coverage-with-aoi');

  // 2. Search with a period, then the previews of the results on the map and a ticked scene for the view.
  await store((s) => { s.getState().setDateFrom('2024-06-01'); s.getState().setDateTo('2024-06-30'); });
  await page.getByRole('button', { name: 'Search', exact: true }).click();
  await page.waitForSelector('.results-panel');
  await settle(3000);
  await shot('2-results-with-previews');
  const first = fixture.features[0].id;
  await store((s, id) => s.getState().toggleSelected(id), first);
  await settle();
  await page.getByRole('button', { name: 'Crop to AOI' }).click();
  await settle(5000);
  await shot('3-view-cropped-to-the-aoi');

  // 3. The area goes, the map moves: the coverage of the map extent asks by GET.
  await store((s) => s.getState().clearAoi());
  await settle();
  for (const extent of [[-20, 30, 40, 65], [8, 46, 12, 50], [9.4, 48.3, 9.6, 48.5]]) {
    await store((s, box) => s.getState().flyTo(box), extent);
    await settle(2500);
  }
  await shot('5-extent-without-aoi');
  await browser.close();

  // The check.
  const mine = asked.filter(({ url }) => {
    const u = new URL(url);
    return u.origin === new URL(BASE).origin && !ASSETS.test(u.pathname) && u.pathname !== '/';
  });
  const text = (url) => decodeURIComponent(url);
  for (const { url, method } of mine) {
    for (const secret of SECRETS) expect('a URL carries a coordinate of the AOI', !text(url).includes(secret), `${method} ${text(url).slice(0, 140)}`);
  }
  expect('the address of the page carries the AOI', !SECRETS.some((secret) => text(page.url()).includes(secret)), page.url());
  const coverage = mine.filter(({ url }) => new URL(url).pathname.startsWith('/coverage/'));
  const posts = coverage.filter(({ method }) => method === 'POST');
  const gets = coverage.filter(({ method }) => method === 'GET');
  expect('no POST of the coverage of the AOI', posts.length > 0);
  for (const { body, url } of posts) {
    const sent = JSON.parse(body ?? '{}');
    expect('the body of a coverage POST does not carry the box of the AOI', JSON.stringify(sent.bbox) === JSON.stringify([9.3412, 48.3317, 9.6218, 48.5624]), body ?? 'no body');
    expect('a coverage POST has a query string', new URL(url).search === '', new URL(url).search);
  }
  expect('no GET of the coverage of a map extent', gets.length > 0);
  for (const { request, url } of coverage) {
    const status = answers.get(request);
    expect('the coverage is refused as a bad request', status !== 400 && status !== 422, `${request.method()} ${status} ${text(url).slice(0, 120)}`);
  }
  for (const { url } of gets) expect('a coverage GET carries the box of an area', !SECRETS.some((s) => text(url).includes(s)), text(url));
  const paths = mine.map(({ method, url }) => `${method} ${new URL(url).pathname}`);
  expect('no request to the tiler for the scene in view', paths.some((p) => p.includes('/collections/')), 'the view asked for no tiles');

  console.log(`${mine.length} requests of the page to this server, ${posts.length} coverage POST, ${gets.length} coverage GET`);
  for (const { method, url, request } of mine) console.log(`  ${method} ${answers.get(request) ?? '-'} ${new URL(url).pathname}${new URL(url).search.slice(0, 90)}`);
  console.log(problems.length ? `FAILED\n- ${problems.join('\n- ')}` : 'OK: no coordinate of the AOI in any URL');
  console.log(`screenshots in ${OUT}`);
  process.exit(problems.length ? 1 : 0);
})();
