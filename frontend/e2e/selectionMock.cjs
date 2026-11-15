// The part of the tiler that creates the selection of a mosaic (`POST /collections/{dataset}/mosaic`, adr/0032 §10.2), for the browser
// checks that stand in for the backend: the id is the hash of the dataset, the assets and the scenes, as the tiler makes it, and the
// tiles and the TileJSON are under it. A check answers the TileJSON and the tiles itself, as it did.
//
//   if (answersSelection(route, url)) return;
//   const scenes = scenesOfSelection(url);      // the scenes of the selection a TileJSON or a tile names, in sorted order
//
// And the footprint selection of the hits of a search (`POST /collections/{dataset}/overview/footprints`, adr/0032 Nachtrag 15.11.2026):
//   if (answersFootprints(route, url)) return;  // the id is the hash of the dataset and the sorted ids
//   const hits = hitsOfFootprints(url);          // the hits of the selection an overview tile names
//   isFootprintTile(url.href);                   // a tile of the overview of a footprint selection

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

const footprints = new Map();

function answersFootprints(route, url) {
  const request = route.request();
  if (request.method() !== 'POST' || !/^\/collections\/[^/]+\/overview\/footprints$/.test(url.pathname)) return false;
  const { items = [] } = JSON.parse(request.postData() ?? '{}');
  const sorted = [...new Set(items)].sort();
  const dataset = decodeURIComponent(url.pathname.split('/')[2]);
  const id = createHash('sha256').update(JSON.stringify({ kind: 'footprints', dataset, items: sorted })).digest('hex').slice(0, 32);
  footprints.set(id, sorted);
  route.fulfill({
    status: 201,
    contentType: 'application/json',
    body: JSON.stringify({ id, tiles: `/collections/${dataset}/overview/${id}/tiles/WebMercatorQuad/{z}/{x}/{y}` }),
  });
  return true;
}

const hitsOfFootprints = (url) => footprints.get(/\/overview\/([0-9a-f]{32})\/tiles\//.exec(url.pathname)?.[1]) ?? [];

const isFootprintTile = (href) => /\/overview\/[0-9a-f]{32}\/tiles\//.test(href);

module.exports = { answersSelection, isSelectionTile, scenesOfSelection, answersFootprints, hitsOfFootprints, isFootprintTile };
