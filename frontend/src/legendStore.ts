// What the legends remember for the session (M5-62, A23): which layer the legend over the map shows, whether it is folded, and the
// legends hidden in the layer manager. Not part of the saved work state.

import { create } from 'zustand';

import { NO_CHOICE, type LegendChoice } from './mapLegend';

interface LegendState {
  choice: LegendChoice;
  folded: boolean;
  // The layers whose legend is hidden in the layer manager with their button; every other one shows it.
  hidden: Record<string, true>;
  setChoice: (choice: LegendChoice) => void;
  choose: (id: string) => void;
  toggleFolded: () => void;
  toggleHidden: (id: string) => void;
}

export const useLegendStore = create<LegendState>((set) => ({
  choice: NO_CHOICE,
  folded: false,
  hidden: {},
  setChoice: (choice) => set({ choice }),
  choose: (id) => set((s) => ({ choice: { ...s.choice, chosen: id } })),
  toggleFolded: () => set((s) => ({ folded: !s.folded })),
  toggleHidden: (id) =>
    set((s) => {
      const { [id]: was, ...rest } = s.hidden;
      return { hidden: was ? rest : { ...rest, [id]: true } };
    }),
}));
