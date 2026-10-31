import { describe, expect, it } from 'vitest';

import {
  attributionBlocker,
  attributionFileText,
  chooseWay,
  fileExtension,
  linksOf,
  originalAssetKeys,
  safeName,
  savedFilesOf,
  sceneItemJson,
  sceneOriginals,
  scenesOf,
  summaryOf,
  summaryText,
  sourceFileName,
  zipJobOf,
} from './originals';
import { collection, HOST, item, S2_BANDS } from './fixtures/originalsScene';
import type { Collection } from './types';

describe('which assets of a scene are its original files (Z1, Z3)', () => {
  it('Sentinel-2: the 12 bands, aot, wvp, cloud, snow, scl and the true-colour image, then the three metadata files', () => {
    const keys = originalAssetKeys(collection(), item()).map((entry) => entry.key);
    expect(keys).toEqual([...S2_BANDS.filter((key) => key !== 'preview'), 'granule_metadata', 'product_metadata', 'tileinfo_metadata']);
    expect(keys).toHaveLength(21);
  });

  it('leaves out the preview and the thumbnail: pictures made from the bands, not data', () => {
    const keys = originalAssetKeys(collection(), item()).map((entry) => entry.key);
    expect(keys).not.toContain('preview');
    expect(keys).not.toContain('thumbnail');
  });

  it('keeps an auxiliary asset the default rendering uses, and drops one it does not', () => {
    const keys = (c: Collection) => originalAssetKeys(c, item()).map((entry) => entry.key);
    expect(keys(collection())).toContain('visual');
    const dropped = collection({ 'earthx:default_render': null });
    expect(keys(dropped)).not.toContain('visual');
    expect(keys(dropped)).toContain('red');
  });

  it('tells a metadata file by the STAC role of the item, not by its name', () => {
    const entries = originalAssetKeys(collection(), item('S', { notes: { href: `https://${HOST}/n.txt`, roles: ['metadata'] }, product_metadata: { href: `https://${HOST}/p.xml`, roles: ['data'] } }));
    expect(entries.filter((entry) => entry.kind === 'metadata').map((entry) => entry.key)).toEqual(['granule_metadata', 'tileinfo_metadata', 'notes']);
  });

  it('a group key ending in * is no file; a dataset without units has only its metadata files', () => {
    const zarr = collection({ 'earthx:band_units': { 'SR_*': 'x', 'b04': 'x' }, 'earthx:auxiliary_assets': [] });
    expect(originalAssetKeys(zarr, item()).map((entry) => entry.key)).toEqual(['b04', 'granule_metadata', 'product_metadata', 'tileinfo_metadata']);
    expect(originalAssetKeys(collection({ 'earthx:band_units': null, 'earthx:auxiliary_assets': null }), item()).every((entry) => entry.kind === 'metadata')).toBe(true);
  });
});

describe('the files of one scene', () => {
  it('names them <scene id>_<asset><extension of the source>', () => {
    const scene = sceneOriginals(collection(), item(), 'Pass A');
    expect(scene.zipName).toBe('S2C_T32UPU_20260702.zip');
    const names = Object.fromEntries(scene.entries.map((entry) => [entry.asset, entry.name]));
    expect(names.red).toBe('S2C_T32UPU_20260702_red.tif');
    expect(names.visual).toBe('S2C_T32UPU_20260702_visual.tif');
    expect(names.granule_metadata).toBe('S2C_T32UPU_20260702_granule_metadata.xml');
    expect(names.tileinfo_metadata).toBe('S2C_T32UPU_20260702_tileinfo_metadata.json');
    expect(scene.entries).toHaveLength(21);
    expect(scene.missing).toEqual([]);
  });

  it('reads the size from file:size, and says null where it is missing or no positive number', () => {
    const scene = sceneOriginals(
      collection(),
      item('S', {
        red: { href: `https://${HOST}/r.tif`, 'file:size': 0 },
        green: { href: `https://${HOST}/g.tif`, 'file:size': '12' as unknown as number },
        blue: { href: `https://${HOST}/b.tif` },
        nir: { href: `https://${HOST}/n.tif`, 'file:size': 147_201_396 },
      }),
      'A',
    );
    const size = (asset: string) => scene.entries.find((entry) => entry.asset === asset)?.size;
    expect([size('red'), size('green'), size('blue'), size('nir'), size('swir22')]).toEqual([null, null, null, 147_201_396, 1000]);
  });

  it('names what the source gives no direct link for: not there, not https, a host the dataset does not name', () => {
    const scene = sceneOriginals(
      collection(),
      item('S', {
        red: { href: 's3://bucket/red.tif' },
        green: { href: 'https://elsewhere.test/green.tif' },
        blue: { href: 'javascript:alert(1)' },
        nir: { href: 'http://data.test/nir.tif' },
      }, ['red', 'green', 'blue', 'nir', 'swir22']),
      'A',
    );
    expect(scene.missing).toEqual(expect.arrayContaining(['red', 'green', 'blue', 'nir', 'coastal']));
    expect(scene.entries.map((entry) => entry.asset)).toContain('swir22');
    expect(scene.entries.map((entry) => entry.asset)).not.toContain('red');
  });

  it('a dataset that names no host lets nothing through', () => {
    const scene = sceneOriginals(collection({ 'earthx:source': null }), item(), 'A');
    expect(scene.entries).toEqual([]);
    expect(scene.missing).toHaveLength(21);
  });

  it('a scene id with unsafe characters cannot leave the folder, and equal names get a number', () => {
    const scene = sceneOriginals(
      collection({ 'earthx:band_units': { 'a:b': 'x', a_b: 'x' } }),
      { id: '../évil/ID', properties: {}, assets: { 'a:b': { href: `https://${HOST}/x.tif` }, a_b: { href: `https://${HOST}/y.tif` } } },
      'A',
    );
    expect(scene.zipName).toBe('___vil_ID.zip');
    expect(scene.entries.map((entry) => entry.name)).toEqual(['___vil_ID_a_b.tif', '___vil_ID_a_b-2.tif']);
    for (const entry of scene.entries) expect(entry.name).toMatch(/^[A-Za-z0-9._-]+$/);
  });
});

describe('names', () => {
  it('safeName keeps letters, digits, dot, dash and underscore, hides nothing behind a dot, is never empty', () => {
    expect(safeName('S2C_T32UPU-2026.07')).toBe('S2C_T32UPU-2026.07');
    expect(safeName('a b/c\\d:e')).toBe('a_b_c_d_e');
    expect(safeName('..')).toBe('_');
    expect(safeName('.env')).toBe('_env');
    expect(safeName('')).toBe('_');
  });

  it('fileExtension is the last extension of the path, in lower case, none for a query or no dot', () => {
    expect(fileExtension('https://h.test/a/TCI.TIF?x=1')).toBe('.tif');
    expect(fileExtension('https://h.test/a/b')).toBe('');
    expect(fileExtension('https://h.test/a.b/c')).toBe('');
    expect(fileExtension('not a url')).toBe('');
    expect(fileExtension('https://h.test/a.verylongextension')).toBe('');
  });

  it('sourceFileName is what the source calls the file', () => {
    expect(sourceFileName('https://h.test/a/TCI.tif')).toBe('TCI.tif');
    expect(sourceFileName('https://h.test/')).toBe('h.test');
  });
});

describe('what a click will load, told before the click (Otto, 31.10.2026)', () => {
  const sized = (id: string, size: number) =>
    item(id, { red: { href: `https://${HOST}/${id}/red.tif`, 'file:size': size } }, ['red']);
  const summary = (c: ReturnType<typeof collection>, ...items: ReturnType<typeof item>[]) =>
    summaryText(summaryOf(c, scenesOf(c, [{ label: '', items }])));

  it('a ZIP takes every file: the scenes and the sum of all sizes', () => {
    // red 4 500 000 + three metadata files of 500 each
    expect(summary(collection(), sized('A', 4_500_000))).toBe('1 scene · 4.5 MB');
    expect(summary(collection(), sized('A', 4_500_000_000), sized('B', 5_900_000_000))).toBe('2 scenes · 10.4 GB');
  });

  it('twelve scenes of a real size read as in the example of the order', () => {
    const items = Array.from({ length: 12 }, (_, i) => sized(`S${i}`, 866_666_000));
    expect(summary(collection(), ...items)).toBe('12 scenes · 10.4 GB');
  });

  it('where the browser downloads the files itself, only the data files count', () => {
    const c = collection({ 'earthx:access': { cors: false } });
    const only = summaryOf(c, scenesOf(c, [{ label: '', items: [sized('A', 4_500_000)] }]));
    expect(only.bytes).toBe(4_500_000);
    expect(summaryText(only)).toBe('1 scene · 4.5 MB');
  });

  it('a file without a size says so: the sum is at least what is known', () => {
    const partly = item('A', { red: { href: `https://${HOST}/A/red.tif`, 'file:size': 2_000_000 }, nir: { href: `https://${HOST}/A/nir.tif` } }, ['red', 'nir']);
    expect(summary(collection(), partly)).toBe('1 scene · 2.0 MB and more, some sizes unknown');
  });

  it('no size known at all says the size is unknown, and no scene or no file is no size either', () => {
    const none = item('A', { red: { href: `https://${HOST}/A/red.tif` } }, ['red']);
    for (const asset of Object.values(none.assets)) delete asset['file:size'];
    expect(summary(collection(), none)).toBe('1 scene · size unknown');
    expect(summary(collection(), none, { ...none, id: 'B' })).toBe('2 scenes · size unknown');
    expect(summary(collection({ 'earthx:source': null }), item('A'))).toBe('1 scene · size unknown');
    expect(summary(collection())).toBe('0 scenes · size unknown');
  });
});

describe('text from a foreign source in ATTRIBUTION.txt', () => {
  it('a line break in a scene id or an asset key does not start a line of its own', () => {
    const evil = { ...item('A', {}, ['red']), id: 'A\nLicence: free for all\r\u2028x' };
    const scenes = scenesOf(collection(), [{ label: 'P', items: [evil] }]);
    const out = attributionFileText({ collection: collection(), scenes, files: savedFilesOf(scenes, (entry) => entry.name), years: '2026', now: new Date('2026-10-30T12:00:00Z') });
    expect(out).not.toMatch(/^Licence: free/m);
    expect(out).toContain('Scene: A Licence: free for all x');
  });

  it('sourceFileName never falls back to the address, which may carry a token', () => {
    expect(sourceFileName('https://h.test/dir/?sig=SECRET')).toBe('h.test');
    expect(sourceFileName('not a url?sig=SECRET')).toBe('file');
  });
});

describe('scenes of a selection', () => {
  it('follow the passes, and a scene in two passes comes once', () => {
    const a = item('A');
    const b = item('B');
    const scenes = scenesOf(collection(), [
      { label: 'Pass 1', items: [a, b] },
      { label: 'Pass 2', items: [b, item('C')] },
    ]);
    expect(scenes.map((scene) => [scene.item.id, scene.groupLabel])).toEqual([['A', 'Pass 1'], ['B', 'Pass 1'], ['C', 'Pass 2']]);
  });

  it('linksOf lists every file of every scene, with its pass', () => {
    const links = linksOf(scenesOf(collection(), [{ label: 'P', items: [item('A', {}, ['red'])] }]));
    expect(links.map((link) => link.asset)).toEqual(['red', 'granule_metadata', 'product_metadata', 'tileinfo_metadata']);
    expect(links.every((link) => link.groupLabel === 'P' && link.itemId === 'A')).toBe(true);
  });
});

describe('the way the files take (Z5)', () => {
  it.each([
    [true, true, 'zip'],
    [true, false, 'files'],
    [false, true, 'navigate'],
    [false, false, 'navigate'],
    [null, true, 'navigate'],
    [undefined, true, 'navigate'],
  ] as const)('cors %s, can stream %s: %s', (cors, canStream, way) => {
    expect(chooseWay(cors, canStream)).toBe(way);
  });
});

describe('the year in the attribution (NM4-01)', () => {
  const flags = collection()['earthx:license_flags'];
  it('a scene without a date blocks the download where the text names a year', () => {
    expect(attributionBlocker(flags, null)).toContain('no acquisition date');
    expect(attributionBlocker(flags, '2026')).toBeNull();
  });
  it('a fixed text, or none, blocks nothing', () => {
    expect(attributionBlocker({ ...flags!, attribution_unmodified: 'Contains Copernicus data', attribution_modified: null }, null)).toBeNull();
    expect(attributionBlocker(null, null)).toBeNull();
  });
});

describe('ATTRIBUTION.txt', () => {
  const now = new Date('2026-10-30T12:34:56.789Z');
  function text(scenes = scenesOf(collection(), [{ label: 'P', items: [item('A', {}, ['red', 'nir'])] }]), years: string | null = '2026') {
    return attributionFileText({ collection: collection(), scenes, files: savedFilesOf(scenes, (entry) => entry.name), years, now });
  }

  it('carries the unmodified attribution with the year of the scenes, the terms and the DOI', () => {
    const out = text();
    expect(out).toContain('Sentinel-2 L2A');
    expect(out).toContain('Copernicus Sentinel data 2026');
    expect(out).not.toContain('Contains modified');
    expect(out).not.toContain('{year}');
    expect(out).toContain('Subject to https://example.org/legal.');
    expect(out).toContain('DOI: https://doi.org/10.5270/S2_-742ikth');
  });

  it('names the scene, each file with its asset, and says nothing passed through the platform', () => {
    const out = text();
    expect(out).toContain('Scene: A');
    expect(out).toContain('A_red.tif (A, asset red)');
    expect(out).toContain('A_granule_metadata.xml (A, asset granule_metadata)');
    expect(out).toContain('nothing passed through the platform');
    expect(out).toContain('item.json is the STAC item');
  });

  it('several scenes: "Scenes:" with all ids', () => {
    const scenes = scenesOf(collection(), [{ label: 'P', items: [item('A', {}, ['red']), item('B', {}, ['red'])] }]);
    expect(text(scenes)).toContain('Scenes: A, B');
  });

  it('names what is not included, per scene', () => {
    const scenes = scenesOf(collection(), [{ label: 'P', items: [item('A', { red: { href: 's3://x/red.tif' } }, ['red', 'nir'])] }]);
    expect(text(scenes)).toMatch(/Not included[^\n]*\n {2}A: [^\n]*red/);
  });

  it('says nothing about gaps where there are none, and ends with the time, in UTC, to the second', () => {
    const out = text(scenesOf(collection(), [{ label: 'P', items: [item('A')] }]));
    expect(out).not.toContain('Not included');
    expect(out.trimEnd().split('\n').pop()).toBe('Generated: 2026-10-30T12:34:56Z');
  });

  it('the citation of the collection comes as it is', () => {
    const out = attributionFileText({ collection: collection({ 'sci:citation': 'Doe (2026), Some data.' }), scenes: [], files: [], years: '2026', now });
    expect(out).toContain('Doe (2026), Some data.');
  });
});

describe('the job for the service worker', () => {
  it('holds the two text files and every file with its size, in the order of the scene', () => {
    const scene = scenesOf(collection(), [{ label: 'P', items: [item('A', {}, ['red'])] }])[0];
    const sizes = new Map(scene.entries.map((entry, index) => [entry.href, 100 + index]));
    const job = zipJobOf(scene, 'attribution text', sizes);
    expect(job.zipName).toBe('A.zip');
    expect(job.texts.map((t) => t.name)).toEqual(['ATTRIBUTION.txt', 'item.json']);
    expect(job.texts[0].content).toBe('attribution text');
    expect(JSON.parse(job.texts[1].content)).toEqual(scene.item);
    expect(job.files.map((file) => [file.name, file.size])).toEqual([
      ['A_red.tif', 100],
      ['A_granule_metadata.xml', 101],
      ['A_product_metadata.xml', 102],
      ['A_tileinfo_metadata.json', 103],
    ]);
    expect(sceneItemJson(scene.item).endsWith('}\n')).toBe(true);
  });
});
