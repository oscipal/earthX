// The part of the tiler that creates the selection of a mosaic (`POST /collections/{dataset}/mosaic`, adr/0032 §10.2), for the browser
// checks that stand in for the backend: the id is the hash of the dataset, the assets and the scenes, as the tiler makes it, and the
// tiles and the TileJSON are under it. A check answers the TileJSON and the tiles itself, as it did.
//
//   if (answersSelection(route, url)) return;
//   const scenes = scenesOfSelection(url);      // the scenes of the selection a TileJSON or a tile names, in sorted order

const { createHash } = require('node:crypto');

const made = new Map();

function answersSelection(route, url) {
  const request = route.request();
  if (request.method() !== 'POST' || !/^\/collections\/[^/]+\/mosaic$/.test(url.pathname)) return false;
  const { items = [], assets = [] } = JSON.parse(request.postData() ?? '{}');
  const sorted = [...new Set(items)].sort();
  const dataset = decodeURIComponent(url.pathname.split('/')[2]);
  const id = createHash('sha256').update(JSON.stringify({ assets: [...new Set(assets)].sort(), dataset, items: sorted })).digest('hex').slice(0, 32);
  made.set(id, sorted);
  const base = `${url.pathname}/${id}`;
  route.fulfill({
    status: 201,
    contentType: 'application/json',
    body: JSON.stringify({ id, tiles: `${base}/tiles/WebMercatorQuad/{z}/{x}/{y}`, tilejson: `${base}/WebMercatorQuad/tilejson.json` }),
  });
  return true;
}

const scenesOfSelection = (url) => made.get(/\/mosaic\/([0-9a-f]{32})\//.exec(url.pathname)?.[1]) ?? [];

// Whether a request is for a tile of a selection.
const isSelectionTile = (href) => /\/mosaic\/[0-9a-f]{32}\/tiles\//.test(href);

module.exports = { answersSelection, isSelectionTile, scenesOfSelection };
