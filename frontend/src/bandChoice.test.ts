import { describe, expect, it } from 'vitest';

import {
  BANDS_COLUMNS,
  bandsFileText,
  chosenBands,
  commonResolutionOf,
  conversionTip,
  conversionsOf,
  defaultBandKeys,
  finestResolution,
  formatG,
  formatResolution,
  layoutBlock,
  layoutOf,
  perBandFileNames,
  resamplingFor,
  resolutionsOf,
  type DownloadBand,
} from './bandChoice';
import { parseBands } from './api';
import { bandsResponse, bandsTable } from './fixtures/bandsScene';
import goldenInput from '../../backend/tests/fixtures/bands/golden_input.json?raw';
import golden from '../../backend/tests/fixtures/bands/golden_per_band.txt?raw';

const table = bandsTable;
const band = (over: Partial<DownloadBand> = {}): DownloadBand => ({
  asset: 'x',
  name: 'x',
  commonName: null,
  wavelength: null,
  resolution: null,
  categorical: false,
  dataType: null,
  scale: null,
  offset: null,
  nodata: null,
  unit: null,
  preselected: false,
  ...over,
});

describe('the table of bands is the answer of the platform', () => {
  it('keeps the rows in the order of the answer, with name, common name, wavelength, resolution and what the item says of the values', () => {
    expect(table().map((b) => b.asset)).toEqual(['a_blue', 'a_red', 'a_edge', 'a_coast', 'scl', 'aerosol']);
    expect(table().find((b) => b.asset === 'a_red')).toEqual({
      asset: 'a_red', name: 'B04', commonName: 'red', wavelength: 0.665, resolution: 10, categorical: false,
      dataType: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0, unit: '1', preselected: true,
    });
  });

  it('marks the class layer the platform names, and nothing else', () => {
    expect(table().filter((b) => b.categorical).map((b) => b.asset)).toEqual(['scl']);
  });

  it('reads what is not there as unknown, a name that is not there as the asset key, and leaves out a row with no asset', () => {
    const found = parseBands({ bands: [{ asset: 'x' }, { name: 'no asset' }, 'text', null, { asset: 'y', name: 'Y', resolution_m: 'ten', scale: Number.NaN }] });
    expect(found.map((b) => b.asset)).toEqual(['x', 'y']);
    expect(found[0]).toEqual({ asset: 'x', name: 'x', commonName: null, wavelength: null, resolution: null, categorical: false, dataType: null, scale: null, offset: null, nodata: null, unit: null, preselected: false });
    expect(found[1]).toMatchObject({ name: 'Y', resolution: null, scale: null });
  });

  it('is empty for a dataset with no file per band, and an error for an answer that is no list', () => {
    expect(parseBands({ bands: [] })).toEqual([]);
    expect(() => parseBands({})).toThrow(/cannot read/);
    expect(() => parseBands(null)).toThrow(/cannot read/);
    expect(() => parseBands({ bands: 'x' })).toThrow(/cannot read/);
  });

  it('takes "true" for a class layer or a preselected band and nothing else', () => {
    const [row] = parseBands({ bands: [{ asset: 'a', categorical: 1, preselected: 'true' }] });
    expect(row.categorical).toBe(false);
    expect(row.preselected).toBe(false);
  });
});

describe('what is ticked when the dialog opens', () => {
  it('is what the platform preselects: the spectral bands and the layer of the mask', () => {
    expect(defaultBandKeys(table())).toEqual(['a_blue', 'a_red', 'a_edge', 'a_coast', 'scl']);
    expect(bandsResponse().bands.find((row) => row.asset === 'aerosol')?.preselected).toBe(false);
  });

  it('is nothing the frontend adds to or takes from: a table with no preselected band ticks none', () => {
    expect(defaultBandKeys([band({ asset: 'elevation' })])).toEqual([]);
    expect(defaultBandKeys([band({ asset: 'elevation', preselected: true }), band({ asset: 'slope' })])).toEqual(['elevation']);
  });

  it('the ticked bands come in the order of the item, whatever order they were ticked in', () => {
    expect(chosenBands(table(), ['scl', 'a_red', 'a_blue']).map((b) => b.asset)).toEqual(['a_blue', 'a_red', 'scl']);
  });
});

describe('the common resolution', () => {
  it('offers the resolutions that occur among the bands of the dataset, finest first, once each', () => {
    expect(resolutionsOf(table())).toEqual([10, 20, 60]);
  });

  it('is the finest of the ticked bands unless one is picked', () => {
    const chosen = chosenBands(table(), ['a_edge', 'a_coast', 'scl']);
    expect(finestResolution(chosen)).toBe(20);
    expect(commonResolutionOf(chosen, null)).toBe(20);
    expect(commonResolutionOf(chosen, 60)).toBe(60);
  });

  it('is unknown where no ticked band has a pixel size', () => {
    expect(commonResolutionOf([band()], null)).toBeNull();
  });
});

describe('how a band is brought to the common resolution', () => {
  const measured = band({ resolution: 20 });
  const classes = band({ resolution: 20, categorical: true });

  it('finer pixels repeat the value (nearest); coarser ones average a measurement and take the most frequent class', () => {
    // A band of 20 m brought to 10 m: the new pixels repeat the old ones, for a measurement and for classes alike.
    expect(resamplingFor(measured, 10)).toBe('nearest');
    expect(resamplingFor(classes, 10)).toBe('nearest');
    // Brought to 60 m: many pixels become one.
    expect(resamplingFor(measured, 60)).toBe('average');
    expect(resamplingFor(classes, 60)).toBe('mode');
  });

  it('a band that is there already, or has no known pixel size, is not converted', () => {
    expect(resamplingFor(measured, 20)).toBe('none');
    expect(resamplingFor(band(), 20)).toBe('none');
    expect(resamplingFor(measured, null)).toBe('none');
  });

  it('names which ticked bands are converted and how, grouped by the method', () => {
    const found = conversionsOf(table(), 20);
    expect(found.average.map((b) => b.asset)).toEqual(['a_blue', 'a_red']);
    expect(found.nearest.map((b) => b.asset)).toEqual(['a_coast']);
    expect(found.mode).toEqual([]);
    const finer = conversionTip(table(), 10);
    expect(finer).toContain('Converted to 10 m');
    expect(finer).toContain('To a finer grid, nearest neighbour (values stay): B05 (20 m), B01 (60 m), scl (20 m), AOT (20 m)');
    expect(finer).not.toContain('average');
    const coarser = conversionTip(table(), 60);
    expect(coarser).toContain('To a coarser grid, average: B02 (10 m), B04 (10 m), B05 (20 m), AOT (20 m)');
    expect(coarser).toContain('To a coarser grid, most frequent class: scl (20 m)');
    expect(coarser).not.toContain('nearest');
  });

  it('says that nothing is converted when every band has the resolution already', () => {
    expect(conversionTip(chosenBands(table(), ['a_blue', 'a_red']), 10)).toBe('No band is converted: all are 10 m already.');
  });
});

describe('what stops a download', () => {
  it('no ticked band', () => {
    expect(layoutBlock('per_band', [], null)).toBe('Tick at least one band.');
  });

  it('one multi-band file needs the pixel size of every ticked band; the other forms do not', () => {
    const unknown = [band({ resolution: 10 }), band({ asset: 'y' })];
    expect(layoutBlock('multi_band', unknown, 10)).toMatch(/no known pixel size/);
    expect(layoutBlock('per_band', unknown, 10)).toBeNull();
    expect(layoutBlock('per_resolution', unknown, 10)).toBeNull();
    expect(layoutBlock('multi_band', chosenBands(table(), ['a_red']), 10)).toBeNull();
  });

  it('the layout names the common resolution for one multi-band file only', () => {
    expect(layoutOf('multi_band', 20)).toEqual({ form: 'multi_band', resolution_m: 20 });
    expect(layoutOf('per_resolution', 20)).toEqual({ form: 'per_resolution' });
    expect(layoutOf('per_band', 20)).toEqual({ form: 'per_band' });
  });
});

describe('numbers as the server writes them', () => {
  it.each([
    [10, '10'],
    [12.5, '12.5'],
    [0.0001, '0.0001'],
    [10.0000001, '10'],
  ])('a resolution of %s is %s', (value, text) => expect(formatResolution(value)).toBe(text));

  it.each([
    [0, '0'],
    [1, '1'],
    [0.665, '0.665'],
    [-0.1, '-0.1'],
    [0.0001, '0.0001'],
    [0.00001, '1e-05'],
    [1234567, '1.23457e+06'],
    [123456, '123456'],
    [65535, '65535'],
  ])('%s is written %s (Python %%g)', (value, text) => expect(formatG(value)).toBe(text));
});

describe('the names of the files', () => {
  const names = (...bands: DownloadBand[]) => [...perBandFileNames(bands).values()];

  it('name, common name and resolution: B04_red_10m.tif, scl_20m.tif', () => {
    const all = chosenBands(table(), ['a_blue', 'a_red', 'a_edge', 'a_coast', 'scl', 'aerosol']);
    expect(names(...all)).toEqual(['B02_blue_10m.tif', 'B04_red_10m.tif', 'B05_rededge_20m.tif', 'B01_coastal_60m.tif', 'scl_20m.tif', 'AOT_20m.tif']);
  });

  it('leaves out a common name that only repeats the name, whatever the case', () => {
    expect(names(band({ name: 'Red', commonName: 'red', resolution: 10 }))).toEqual(['Red_10m.tif']);
  });

  it('leaves out a resolution that is not known, and writes one that is not a whole number as it is', () => {
    expect(names(band({ name: 'B01' }))).toEqual(['B01.tif']);
    expect(names(band({ name: 'B01', resolution: 12.5 }))).toEqual(['B01_12.5m.tif']);
  });

  it('turns every run of other characters into one underscore and trims the dots and underscores at the ends', () => {
    // As on the server: the underscore that joins the parts is a character of its own, next to the one a run of others became.
    expect(names(band({ name: '  ..B 04/x?? ', resolution: 10 }))).toEqual(['B_04_x__10m.tif']);
    expect(names(band({ name: '../..' }))).toEqual(['asset.tif']);
  });

  it('two bands of one name get the asset key added', () => {
    const found = perBandFileNames([band({ asset: 'one', name: 'B04', resolution: 10 }), band({ asset: 'two', name: 'B04', resolution: 10 }), band({ asset: 'three', name: 'B05', resolution: 10 })]);
    expect([...found.values()]).toEqual(['B04_10m_one.tif', 'B04_10m_two.tif', 'B05_10m.tif']);
  });
});

describe('BANDS.txt', () => {
  const red = band({ asset: 'a_red', name: 'B04', commonName: 'red', wavelength: 0.665, resolution: 10, dataType: 'uint16', scale: 0.0001, offset: -0.1, nodata: 0, unit: '1' });

  it('is the list of the files with one line for each band, in the format of the server', () => {
    const text = bandsFileText({
      title: 'Made-up multispectral',
      form: 'per_band',
      files: [{ path: 'exports/B04_red_10m.tif', bands: [{ band: red, resampling: 'none', exportResolution: 10 }] }],
    });
    expect(text).toBe(
      [
        'EarthX band list',
        'Dataset: Made-up multispectral',
        'Layout: one file per band',
        '',
        'File: exports/B04_red_10m.tif',
        BANDS_COLUMNS,
        '1 | B04 | red | 0.665 | 10 | 10 | none | uint16 | 0.0001 | -0.1 | 0 | 1',
        '',
      ].join('\n'),
    );
    expect(BANDS_COLUMNS).toBe(
      'Band | Name | Common name | Wavelength (um) | Source resolution (m) | Export resolution (m) | Resampling | Data type | Scale | Offset | Nodata | Unit',
    );
  });

  it('writes - for what the item does not say, scale 1 and offset 0 where it names none, and a blank line between the files', () => {
    const text = bandsFileText({
      title: 'x',
      form: 'per_resolution',
      files: [
        { path: 'exports/bands_20m.tif', bands: [{ band: band({ name: 'scl' }), resampling: 'none', exportResolution: null }] },
        { path: 'exports/bands_10m.tif', bands: [{ band: red, resampling: 'none', exportResolution: 10 }] },
      ],
    });
    const lines = text.split('\n');
    expect(lines[2]).toBe('Layout: one file per resolution');
    expect(lines[6]).toBe('1 | scl | - | - | - | - | none | - | 1 | 0 | - | -');
    expect(lines[7]).toBe('');
    expect(lines[8]).toBe('File: exports/bands_10m.tif');
  });

  it('the bands of a file are numbered from 1', () => {
    const text = bandsFileText({
      title: 'x',
      form: 'multi_band',
      files: [{ path: 'exports/bands_10m.tif', bands: [red, red].map((b) => ({ band: b, resampling: 'nearest' as const, exportResolution: 10 })) }],
    });
    expect(text).toContain('Layout: one multi-band file');
    expect(text).toMatch(/\n1 \| B04 .*\n2 \| B04 /);
  });

  // The server writes the same text (`backend/tests/earthx/access/test_bands_golden.py`): it reads one synthetic item and gives the
  // golden file byte for byte. The browser reads the same bands from the answer of the platform for that item.
  const responses = import.meta.glob('../../backend/tests/fixtures/bands/golden_bands_response.json', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
  const response = Object.values(responses)[0];
  it.skipIf(response === undefined)('writes the text the server writes for the same bands', () => {
    const answer = JSON.parse(response) as unknown;
    const bands = parseBands(Array.isArray(answer) ? { bands: answer } : answer);
    const names = perBandFileNames(bands);
    const text = bandsFileText({
      title: (JSON.parse(goldenInput) as { title: string }).title,
      form: 'per_band',
      files: bands.map((one) => ({
        path: `exports/${names.get(one.asset)}`,
        bands: [{ band: one, resampling: 'none' as const, exportResolution: one.resolution }],
      })),
    });
    expect(text).toBe(golden);
    expect(text).not.toContain('visual');
  });
});
