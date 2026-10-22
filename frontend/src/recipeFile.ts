// Reads a `recipe.json` the user picked (M4-19d, plan §3.4). It is the user's own
// file: fields the panel has no use for (`resolved`, `provenance`, `recipe_id`)
// are left out, not refused. What the file claims is checked here only as far as
// the panel needs to take it up; the operators and their parameters are checked
// against the process description (`processingOrder.ts::draftFromOrder`), and the
// server decides on the order itself.

import { orderAoi } from './processingOrder';
import type { CropOutput, Order, OrderInput, OrderStep, RasterOutput } from './processing';

// The size the job route takes (`MAX_BODY_BYTES`).
export const MAX_RECIPE_BYTES = 1_048_576;

export type RecipeRead = { ok: true; order: Order } | { ok: false; reason: string };

const isObject = (value: unknown): value is Record<string, unknown> =>
  !!value && typeof value === 'object' && !Array.isArray(value);

const fail = (reason: string): RecipeRead => ({ ok: false, reason });

// Nested arrays of `depth` levels around finite numbers (a position is depth 1).
function isCoordinates(value: unknown, depth: number): boolean {
  if (!Array.isArray(value)) return false;
  if (depth === 1) return value.length >= 2 && value.every((n) => typeof n === 'number' && Number.isFinite(n));
  return value.length > 0 && value.every((inner) => isCoordinates(inner, depth - 1));
}

function readInput(raw: unknown): OrderInput | string {
  if (!isObject(raw) || typeof raw.dataset !== 'string' || raw.dataset === '') return 'an input names no dataset';
  const { groups, assets } = raw;
  if (!Array.isArray(groups) || groups.length === 0 || !groups.every((g) => Array.isArray(g) && g.length > 0 && g.every((id) => typeof id === 'string'))) {
    return 'an input has no scenes';
  }
  if (!Array.isArray(assets) || !assets.every((a) => typeof a === 'string')) return 'an input has no list of assets';
  return { name: typeof raw.name === 'string' ? raw.name : 'input', dataset: raw.dataset, groups: groups as string[][], assets: assets as string[] };
}

function readStep(raw: unknown, index: number): OrderStep | string {
  if (!isObject(raw) || typeof raw.op !== 'string' || typeof raw.op_version !== 'number') return `step ${index + 1} names no operator`;
  if (raw.params !== undefined && !isObject(raw.params)) return `step ${index + 1} has no parameters object`;
  return { op: raw.op, op_version: raw.op_version, params: (raw.params as Record<string, unknown> | undefined) ?? {} };
}

export function readRecipe(text: string): RecipeRead {
  if (new TextEncoder().encode(text).length > MAX_RECIPE_BYTES) return fail('The file is larger than 1 MB.');
  let json: unknown;
  try {
    json = JSON.parse(text);
  } catch {
    return fail('The file is not valid JSON.');
  }
  if (!isObject(json) || json.recipe_version === undefined) return fail('This is not a recipe (no recipe_version).');
  if (json.recipe_version !== 1) return fail(`Recipe version ${String(json.recipe_version)} is not supported.`);
  if (!Array.isArray(json.inputs) || json.inputs.length === 0) return fail('The recipe has no inputs.');
  if (!Array.isArray(json.steps)) return fail('The recipe has no steps list.');
  const inputs: OrderInput[] = [];
  for (const raw of json.inputs) {
    const input = readInput(raw);
    if (typeof input === 'string') return fail(`The recipe is incomplete: ${input}.`);
    inputs.push(input);
  }
  if (new Set(inputs.map((i) => i.dataset)).size > 1) return fail('The recipe uses more than one dataset.');
  if (inputs.length > 1) return fail('The recipe has more than one input.');
  const steps: OrderStep[] = [];
  for (const [index, raw] of json.steps.entries()) {
    const step = readStep(raw, index);
    if (typeof step === 'string') return fail(`The recipe is incomplete: ${step}.`);
    steps.push(step);
  }
  const { aoi, output } = json;
  if (aoi !== undefined && !(isObject(aoi) && ((aoi.type === 'Polygon' && isCoordinates(aoi.coordinates, 3)) || (aoi.type === 'MultiPolygon' && isCoordinates(aoi.coordinates, 4))))) {
    return fail('The recipe has an AOI that is not a polygon.');
  }
  if (!isObject(output) || (output.kind !== 'raster' && output.kind !== 'crop')) return fail('The recipe has no known output.');
  if (output.kind === 'raster' && typeof output.dtype !== 'string') return fail('The recipe names no output data type.');
  return {
    ok: true,
    order: {
      recipe_version: 1,
      inputs,
      ...(aoi ? { aoi: orderAoi(aoi as unknown as GeoJSON.Polygon | GeoJSON.MultiPolygon) } : {}),
      steps,
      output: output as unknown as RasterOutput | CropOutput,
    },
  };
}
