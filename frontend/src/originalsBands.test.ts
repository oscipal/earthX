// @vitest-environment node
//
// "Download full scene" with a choice of bands, one file per band (NM4-75): only the ticked bands are loaded from the source, they lie
// in the folder `exports/` of the ZIP under the name of their content, with `exports/BANDS.txt`; the files about the scene stay where
// they were. Where the files are saved one by one the names are those of before.

import { describe, expect, it, vi } from 'vitest';

import { bandsCollection, bandsItem, HOST } from './fixtures/bandsScene';
import { sceneBandsText, sceneOriginals, scenesOf, zipJobOf, zipPathOf } from './originals';
import { runOriginals, type RunDeps, type ZipChannel } from './originalsRun';
import type { ZipJob } from './originalsZip';

const PICK = ['a_red', 'scl'];

describe('the entries of a scene with a choice of bands', () => {
  it('are the ticked bands, named by content, and the files about the scene', () => {
    const scene = sceneOriginals(bandsCollection(), bandsItem('S'), 'P', PICK);
    expect(scene.entries.map((e) => [e.asset, e.kind, e.exportName ?? null])).toEqual([
      ['a_red', 'data', 'B04_red_10m.tif'],
      ['scl', 'data', 'scl_20m.tif'],
      ['granule_metadata', 'metadata', null],
    ]);
    expect(zipPathOf(scene.entries[0])).toBe('exports/B04_red_10m.tif');
    expect(zipPathOf(scene.entries[2])).toBe(scene.entries[2].name);
    expect(scene.entries[0].name).toBe('S_a_red.tif');
  });

  it('are in the order of the item, not of the ticking', () => {
    const scene = sceneOriginals(bandsCollection(), bandsItem('S'), 'P', ['scl', 'a_blue', 'a_red']);
    expect(scene.entries.filter((e) => e.kind === 'data').map((e) => e.asset)).toEqual(['a_blue', 'a_red', 'scl']);
  });

  it('leave out what was not ticked, the auxiliary picture too, and name a ticked key the scene lacks as missing', () => {
    const item = bandsItem('S');
    delete item.assets.a_edge;
    const scene = sceneOriginals(bandsCollection(), item, 'P', ['a_edge', 'a_red', 'visual']);
    expect(scene.entries.filter((e) => e.kind === 'data').map((e) => e.asset)).toEqual(['a_red']);
    expect(scene.missing).toEqual(['a_edge', 'visual']);
  });

  it('are all the original files as before without a choice, with no name by content', () => {
    const scene = sceneOriginals(bandsCollection(), bandsItem('S'), 'P');
    expect(scene.entries.some((e) => e.exportName !== undefined || e.band !== undefined)).toBe(false);
  });

  it('a source address on a foreign host is not linked, ticked or not', () => {
    const item = bandsItem('S');
    item.assets.a_red.href = 'https://elsewhere.invalid/x.tif';
    const scene = sceneOriginals(bandsCollection(), item, 'P', PICK);
    expect(scene.entries.map((e) => e.asset)).not.toContain('a_red');
    expect(scene.missing).toContain('a_red');
  });
});

describe('the ZIP job of a scene with a choice', () => {
  const scene = sceneOriginals(bandsCollection(), bandsItem('S'), 'P', PICK);
  const sizes = new Map(scene.entries.map((e) => [e.href, e.size ?? 0]));

  it('puts the bands in exports/ beside BANDS.txt, and the scene files at the root', () => {
    const job = zipJobOf(scene, 'attribution', sizes, sceneBandsText(bandsCollection(), scene));
    expect(job.files.map((f) => f.name)).toEqual(['exports/B04_red_10m.tif', 'exports/scl_20m.tif', 'S_granule_metadata.xml']);
    expect(job.texts.map((t) => t.name)).toEqual(['ATTRIBUTION.txt', 'item.json', 'exports/BANDS.txt']);
  });

  it('keeps the bytes of the source: the address and the size of each file are the source`s', () => {
    const job = zipJobOf(scene, 'attribution', sizes, 'x');
    expect(job.files[0]).toEqual({ name: 'exports/B04_red_10m.tif', url: `https://${HOST}/S/a_red.tif`, size: 1000 });
  });

  it('has no BANDS.txt and no folder without a choice, as in NM4-33', () => {
    const plain = sceneOriginals(bandsCollection(), bandsItem('S'), 'P');
    const job = zipJobOf(plain, 'attribution', new Map(plain.entries.map((e) => [e.href, 1])));
    expect(job.texts.map((t) => t.name)).toEqual(['ATTRIBUTION.txt', 'item.json']);
    expect(job.files.every((f) => !f.name.includes('/'))).toBe(true);
  });

  it('BANDS.txt lists each band in its own file, nothing resampled, with what the item says of it', () => {
    const text = sceneBandsText(bandsCollection(), scene);
    expect(text.split('\n').slice(0, 3)).toEqual(['EarthX band list', 'Dataset: Made-up multispectral', 'Layout: one file per band']);
    expect(text).toContain('File: exports/B04_red_10m.tif');
    expect(text).toContain('1 | B04 | red | 0.665 | 10 | 10 | none | uint16 | 0.0001 | -0.1 | 0 | 1');
    expect(text).toContain('File: exports/scl_20m.tif');
    expect(text).toContain('1 | scl | - | - | 20 | 20 | none | uint8 | 1 | 0 | 0 | -');
    expect(text).not.toContain('granule');
  });
});

describe('the run with a choice', () => {
  function harness(zip: ZipChannel | null) {
    const requested: string[] = [];
    const jobs: ZipJob[] = [];
    const saved: string[] = [];
    const navigated: string[] = [];
    const fetchFn = vi.fn(async (url: string, init?: RequestInit) => {
      requested.push(`${init?.method ?? 'GET'} ${url.split('/').slice(-1)[0]}`);
      return new Response(init?.method === 'HEAD' ? null : new Uint8Array(1000), { headers: { 'content-length': '1000' } });
    });
    const deps: RunDeps = {
      fetch: fetchFn as unknown as typeof fetch,
      zip: zip ?? null,
      saveBlob: (name) => saved.push(name),
      navigate: (href) => navigated.push(href),
      now: () => new Date('2026-10-30T12:00:00Z'),
    };
    return { deps, jobs, saved, navigated, requested };
  }
  const go = (h: ReturnType<typeof harness>, collection = bandsCollection()) => {
    const scenes = scenesOf(collection, [{ label: 'P', items: [bandsItem('S')] }], PICK);
    return runOriginals({
      collection,
      datasetId: 'made-up-bands',
      scenes,
      years: '2026',
      deps: h.deps,
      signal: new AbortController().signal,
      onScene: () => undefined,
      onWay: () => undefined,
    });
  };

  it('hands the worker only the ticked bands and writes BANDS.txt and ATTRIBUTION.txt with exports/ paths', async () => {
    const h = harness({ run: async (job) => void h.jobs.push(job) });
    await go(h);
    expect(h.jobs).toHaveLength(1);
    expect(h.jobs[0].files.map((f) => f.name)).toEqual(['exports/B04_red_10m.tif', 'exports/scl_20m.tif', 'S_granule_metadata.xml']);
    expect(h.jobs[0].texts.map((t) => t.name)).toContain('exports/BANDS.txt');
    const attribution = h.jobs[0].texts.find((t) => t.name === 'ATTRIBUTION.txt')!.content;
    expect(attribution).toContain('exports/B04_red_10m.tif (S, asset a_red)');
    expect(attribution).not.toContain('a_blue');
    // Nothing of the bands that were not ticked is asked of the source.
    expect(h.requested.every((r) => !/a_blue|a_edge|a_coast|aerosol|visual/.test(r))).toBe(true);
  });

  it('without a stream the files are saved one by one under the names of before, the ticked ones only', async () => {
    const h = harness(null);
    await go(h);
    expect(h.saved.filter((name) => name.endsWith('.tif')).sort()).toEqual(['S_a_red.tif', 'S_scl.tif']);
    expect(h.saved.some((name) => name.includes('exports') || name.includes('BANDS'))).toBe(false);
  });
});
