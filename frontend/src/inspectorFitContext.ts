import { createContext, useContext } from 'react';

// The rows a page of "Quick processing" has in the settings bar (UI-12 (4), `inspectorFit.ts`); `Infinity` for all.
export const QuickRowsContext = createContext<number>(Number.POSITIVE_INFINITY);

export const useQuickRows = (): number => useContext(QuickRowsContext);
