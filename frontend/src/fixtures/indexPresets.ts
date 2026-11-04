// The five presets of Sentinel-2 as the collection serves them (`earthx:index_presets`, NM4-14a), for the tests. The formulas
// and ranges are those of `backend/earthx/catalog/datasets.py`.

export const SENTINEL_2_PRESETS = [
  {
    name: 'NDVI',
    title: 'Normalized Difference Vegetation Index',
    expression: '(nir - red) / (nir + red)',
    rescale: [[-1, 1]],
    colormap_name: 'rdylgn',
    formula: '(N - R)/(N + R)',
    reference: 'https://ntrs.nasa.gov/citations/19740022614',
  },
  {
    name: 'NDWI',
    title: 'Normalized Difference Water Index (McFeeters 1996)',
    expression: '(green - nir) / (green + nir)',
    rescale: [[-1, 1]],
    colormap_name: 'rdbu',
    formula: '(G - N) / (G + N)',
    reference: 'https://doi.org/10.1080/01431169608948714',
  },
  {
    name: 'NDSI',
    title: 'Normalized Difference Snow Index',
    expression: '(green - swir16) / (green + swir16)',
    rescale: [[-1, 1]],
    colormap_name: 'rdbu',
    formula: '(G - S1) / (G + S1)',
    reference: 'https://doi.org/10.1109/IGARSS.1994.399618',
  },
  {
    name: 'NBR',
    title: 'Normalized Burn Ratio',
    expression: '(nir - swir22) / (nir + swir22)',
    rescale: [[-1, 1]],
    colormap_name: 'rdylgn',
    formula: '(N - S2) / (N + S2)',
    reference: 'https://doi.org/10.3133/ofr0211',
  },
  {
    name: 'EVI',
    title: 'Enhanced Vegetation Index',
    expression: '2.5 * (nir - red) / (nir + 6 * red - 7.5 * blue + 1)',
    rescale: [[-1, 1]],
    colormap_name: 'rdylgn',
    formula: 'g * (N - R) / (N + C1 * R - C2 * B + L)',
    reference: 'https://doi.org/10.1016/S0034-4257(96)00112-5',
  },
];
