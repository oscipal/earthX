// The kind of a full-resolution view, as short as it goes, for its head: "AOI crop", "whole scene", and with several
// scenes how many are merged (Otto, 27.10.2026).

export function viewKind(cropToAoi: boolean, scenes: number): string {
  const kind = cropToAoi ? 'AOI crop' : 'whole scene';
  return scenes > 1 ? `${cropToAoi ? 'AOI crop · ' : ''}${scenes} scenes merged` : kind;
}
