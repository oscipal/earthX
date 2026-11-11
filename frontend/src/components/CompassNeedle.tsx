// The needle of the compass (UI-06, Otto F3 and F17): two points like the compass of Google Maps, the north half red. Lucide has no
// needle with a red half, so it is a drawing of its own, the second exception of `docs/ui/leitfaden.md` §3 beside "Settings". The
// colours are tokens (`.compass-north`, `.compass-south` in `index.css`). It points where north is on the screen: turned against the map.

export function CompassNeedle({ bearing }: { bearing: number }) {
  return (
    <svg className="compass-needle" viewBox="0 0 24 24" aria-hidden="true" focusable="false" style={{ transform: `rotate(${-bearing}deg)` }}>
      <path className="compass-north" d="M12 2L16 12H8Z" />
      <path className="compass-south" d="M12 22L8 12H16Z" />
    </svg>
  );
}
