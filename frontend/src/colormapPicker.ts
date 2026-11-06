// The list of all colormaps (UI-03d, Otto, 2.11.2026): a bar of its own at the right edge, opened by "More…" of a dropdown "Colormap"
// wherever it is, over the settings or the processing panel, which stay as they are and come back when it is left. Who opened it says
// what is chosen; a choice closes it.

import { create } from 'zustand';

interface PickerState {
  // The colormap chosen now (`''` none) and where a choice goes; `null` while the list is closed.
  request: { value: string; onPick: (name: string) => void; opening: number } | null;
  open: (value: string, onPick: (name: string) => void) => void;
  close: () => void;
}

export const useColormapPicker = create<PickerState>((set) => ({
  request: null,
  open: (value, onPick) => set((s) => ({ request: { value, onPick, opening: (s.request?.opening ?? 0) + 1 } })),
  close: () => set({ request: null }),
}));
