import { createContext, useContext } from 'react';

// What the bar does so as not to scroll (UI-12 (12), `inspectorFit.ts`): the sections it folds, and the rows of "Quick processing" a page.
export interface InspectorFitState {
  folded: ReadonlySet<string>;
  toggle: (title: string) => void;
  quickRows: number;
}

export const InspectorFitContext = createContext<InspectorFitState>({ folded: new Set(), toggle: () => {}, quickRows: Number.POSITIVE_INFINITY });

export const useInspectorFit = (): InspectorFitState => useContext(InspectorFitContext);
