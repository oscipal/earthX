// The part of the tiler that makes the selections of a mosaic (M5-30b part 3), for the tests that stub `fetch`: `POST
// /collections/{dataset}/mosaic` answers an id that is the hash of its content, as the real one does, and the TileJSON under
// that id answers what the test says.

export interface CreatedSelection {
  id: string;
  dataset: string;
  items: string[];
  assets: string[];
}

// The id of a content as the tiler makes it: a hash of the sorted content, 32 hex characters. Not the tiler's hash (SHA-256), only one
// with the same property: the same content, the same id; another content, another id.
export function selectionIdOf(dataset: string, assets: readonly string[], items: readonly string[]): string {
  const text = JSON.stringify({ assets: [...new Set(assets)].sort(), dataset, items: [...new Set(items)].sort() });
  return [0x811c9dc5, 0x01000193, 0x9e3779b1, 0x85ebca6b]
    .map((seed) => {
      let hash = seed;
      for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 0x01000193) >>> 0;
      return hash.toString(16).padStart(8, '0');
    })
    .join('');
}

export const json = (body: unknown, status = 200): Response => ({ ok: status < 300, status, statusText: '', json: async () => body }) as Response;

export const TILEJSON = (order: string[]) => ({
  bounds: [9, 46, 12, 49],
  minzoom: 8,
  maxzoom: 19,
  tiles: ['http://tiler.test/tiles'],
  'earthx:order': order,
});

export interface SelectionServerOptions {
  // The answer to the TileJSON of a selection; the default names the scenes, sorted, as their order.
  tilejson?: (selection: CreatedSelection, url: string) => Response | Promise<Response>;
  // The answer to a creation, where it is not the one of a tiler that takes the list.
  create?: (selection: CreatedSelection) => Response | Promise<Response> | undefined;
}

export function selectionServer(options: SelectionServerOptions = {}) {
  const selections = new Map<string, CreatedSelection>();
  const created: CreatedSelection[] = [];
  const tilejsonCalls: string[] = [];
  const answer = async (url: string, init?: RequestInit): Promise<Response | null> => {
    const post = /^\/collections\/([^/?]+)\/mosaic$/.exec(url);
    if (post) {
      if (init?.method !== 'POST') return json({ detail: 'method not allowed' }, 405);
      const body = JSON.parse(String(init.body)) as { items: string[]; assets: string[] };
      const dataset = decodeURIComponent(post[1]);
      const selection = { id: selectionIdOf(dataset, body.assets, body.items), dataset, items: body.items, assets: body.assets };
      created.push(selection);
      const refused = options.create?.(selection);
      if (refused) return refused;
      const known = selections.has(selection.id);
      selections.set(selection.id, selection);
      const base = `/collections/${post[1]}/mosaic/${selection.id}`;
      return json({ id: selection.id, tiles: `${base}/tiles/WebMercatorQuad/{z}/{x}/{y}`, tilejson: `${base}/WebMercatorQuad/tilejson.json` }, known ? 200 : 201);
    }
    const tilejson = /^\/collections\/[^/]+\/mosaic\/([0-9a-f]{32})\/WebMercatorQuad\/tilejson\.json/.exec(url);
    if (tilejson) {
      tilejsonCalls.push(url);
      const selection = selections.get(tilejson[1]);
      if (!selection) return json({ detail: 'no selection: it expired or never existed' }, 410);
      return (options.tilejson ?? ((one) => json(TILEJSON([...one.items].sort()))))(selection, url);
    }
    return null;
  };
  return { answer, selections, created, tilejsonCalls };
}
