// Where the user has put each band (the movable strip at the bottom of the map: the block of the selection bar and the
// timeline (NM4-66); the settings bar of a view or a result stands at a fixed place, UI-03a): the place on the screen, the top left corner of the band in px. A
// place belongs to the band, not to the place it is drawn at, and it is a place on the screen, not a shift from where
// the stack of bands would put it: a band that was put somewhere stays there while other bands come, go or change
// their height (Otto, 27.10.2026). Bands that were not moved stack from the bottom edge as before. Kept for the session.

import { create } from 'zustand';

export type BandId = 'selection';
export interface Place {
  x: number;
  y: number;
}

interface BandPlaces {
  places: Partial<Record<BandId, Place>>;
  move: (id: BandId, place: Place) => void;
}

export const useBandPositions = create<BandPlaces>((set) => ({
  places: {},
  move: (id, place) => set((s) => ({ places: { ...s.places, [id]: place } })),
}));
