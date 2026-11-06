// A count with its noun in the singular or the plural (UI-04 §7.4): "1 scene", "3 scenes", never "scene(s)".
export function counted(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`;
}
