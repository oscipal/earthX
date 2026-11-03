// "Copy original scene name" (Otto, 3.11.2026, zu #282): the name of a scene as its source gives it is the id of its item. A click
// puts the names of the scenes of a view or a layer on the clipboard, one to a line, and nowhere else: not into an address, not into a
// log, not into storage. Nothing is asked of the network.

import type { Order } from './processing';

export const COPY_LABEL = 'Copy original scene name';
export const COPIED_LABEL = 'Copied';
export const COPY_FAILED_LABEL = 'Could not copy';

// The names as they are copied: each once, one to a line.
export const textOfNames = (names: readonly string[]): string => [...new Set(names)].join('\n');

// What the tooltip says: how many scenes the click copies, or what it copies for one.
export const copyTip = (count: number): string => (count > 1 ? `${count} scenes` : 'Copy the name of the original scene');

// The scenes a job was ordered for, in the order of the order: from its copy of the order. None where the copy is gone.
export function sceneNamesOfOrder(order: Order | null | undefined): string[] {
  const groups = order?.inputs?.flatMap((input) => input.groups ?? []) ?? [];
  return [...new Set(groups.flat().filter((id): id is string => typeof id === 'string' && id !== ''))];
}

// Puts the names on the clipboard; `false` where the browser does not let the page.
export async function copyNames(names: readonly string[], write: (text: string) => Promise<void> = (text) => navigator.clipboard.writeText(text)): Promise<boolean> {
  try {
    await write(textOfNames(names));
    return true;
  } catch {
    return false;
  }
}
