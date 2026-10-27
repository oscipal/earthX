// Where the user has moved each band (the movable strips at the bottom of the map: the bar of the selection, the time
// line, the view of scenes, the view of a result). A position belongs to the band, not to the place it is drawn at: a
// band that goes (the bar of the selection when nothing is ticked, the view after "Change image") and comes back stands
// where it was left, and what is done in one band moves no other (Otto, 27.10.2026). Kept for the session.

import { create } from 'zustand';

export type BandId = 'selection' | 'timeline' | 'view' | 'result';
export interface Offset {
  x: number;
  y: number;
}

export const NOT_MOVED: Offset = { x: 0, y: 0 };

interface BandPositions {
  offsets: Partial<Record<BandId, Offset>>;
  move: (id: BandId, offset: Offset) => void;
}

export const useBandPositions = create<BandPositions>((set) => ({
  offsets: {},
  move: (id, offset) => set((s) => ({ offsets: { ...s.offsets, [id]: offset } })),
}));
