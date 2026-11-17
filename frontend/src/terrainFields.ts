// The form of a "Terrain" step (M5-10): what to compute from a band of heights, and the fields of that product only. The
// fields depend on the product, which the schema cannot say (each is optional there), so the panel lays them out, as for
// `normalize` of version 4. The defaults of the hillshade are those of gdaldem. The server decides (`422`); this is the help
// while typing. Pure functions.

import type { Field, FieldValue, ParamsForm } from './schemaForm';

export type Product = 'slope' | 'aspect' | 'hillshade';

export const PRODUCTS: ReadonlyArray<{ value: Product; help: string }> = [
  { value: 'slope', help: 'Steepness of the ground, in degrees or percent.' },
  { value: 'aspect', help: 'Direction the ground faces, in degrees from north; flat ground has none.' },
  { value: 'hillshade', help: 'Light and shadow of the relief, from 1 (in shadow) to 255 (facing the light).' },
];

// The fields of each product besides the product, the band, the name and the method.
const OF_PRODUCT: Readonly<Record<Product, readonly string[]>> = {
  slope: ['slope_unit'],
  aspect: [],
  hillshade: ['multidirectional', 'azimuth', 'altitude', 'z_factor'],
};

const COMMON = ['product', 'bands', 'name', 'method'];

const isObject = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

const isProduct = (value: unknown): value is Product => PRODUCTS.some((p) => p.value === value);

export function terrainForm(schema: unknown): ParamsForm {
  const properties = isObject(schema) && isObject(schema.properties) ? schema.properties : {};
  const product = properties.product;
  const offered = isObject(product) && Array.isArray(product.enum) ? product.enum : [];
  if (offered.length !== PRODUCTS.length || !PRODUCTS.every((p) => offered.includes(p.value))) {
    return { supported: false, reason: 'not supported by this panel: the products of terrain' };
  }
  const missing = [...COMMON, ...Object.values(OF_PRODUCT).flat()].find((name) => !(name in properties));
  if (missing) return { supported: false, reason: `not supported by this panel: ${missing} of terrain` };
  const text = (name: string): { description?: string; unit?: string } => {
    const own = isObject(properties[name]) ? properties[name] : {};
    return {
      ...(typeof own.description === 'string' ? { description: own.description } : {}),
      ...(typeof own['x-earthx-unit'] === 'string' ? { unit: own['x-earthx-unit'] } : {}),
    };
  };
  const field = (name: string, title: string, kind: Field['kind'], extra: Partial<Field> = {}): Field => ({
    name,
    kind,
    title,
    required: false,
    ...text(name),
    ...extra,
  });
  return {
    supported: true,
    fields: [
      field('product', 'Product', 'enum', {
        required: true,
        default: 'slope',
        options: PRODUCTS.map((p) => p.value),
        optionHelp: Object.fromEntries(PRODUCTS.map((p) => [p.value, p.help])),
      }),
      field('bands', 'Band', 'names', { required: true, minItems: 1, maxItems: 1 }),
      field('name', 'Name', 'string', { required: true }),
      field('method', 'Method', 'enum', { required: true, default: 'horn', options: ['horn', 'zevenbergen_thorne'] }),
      field('slope_unit', 'Unit', 'enum', { default: 'degrees', options: ['degrees', 'percent'] }),
      field('multidirectional', 'Four lights', 'boolean', { default: false }),
      field('azimuth', 'Azimuth', 'number', { default: 315, minimum: 0, exclusiveMaximum: 360 }),
      field('altitude', 'Altitude', 'number', { default: 45, minimum: 0, maximum: 90 }),
      field('z_factor', 'Z-factor', 'number', { default: 1, exclusiveMinimum: 0 }),
    ],
  };
}

// The fields a step of this product takes: the common ones and its own; with four lights no azimuth.
export function fieldsOfProduct(fields: readonly Field[], values: Readonly<Record<string, FieldValue>>): Field[] {
  const product = isProduct(values.product) ? values.product : null;
  const own = new Set(product ? OF_PRODUCT[product] : []);
  if (values.multidirectional === true) own.delete('azimuth');
  return fields.filter((field) => COMMON.includes(field.name) || own.has(field.name));
}
