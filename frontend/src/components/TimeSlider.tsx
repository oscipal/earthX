import { useEffect, useState } from 'react';

import { stepLabel, runPlayback, STEP_LATE_AFTER_MS } from '../playback';
import { useAppStore } from '../store';

export default function TimeSlider() {
  const groups = useAppStore((s) => s.groups);
  const activeGroupIndex = useAppStore((s) => s.activeGroupIndex);
  const setActiveGroupIndex = useAppStore((s) => s.setActiveGroupIndex);
  const playing = useAppStore((s) => s.playing);
  const setPlaying = useAppStore((s) => s.setPlaying);
  const resultsOnMap = useAppStore((s) => s.resultsOnMap);
  const toggleResultsOnMap = useAppStore((s) => s.toggleResultsOnMap);
  const shownGroupIndex = useAppStore((s) => s.shownGroupIndex);
  const revealNotBefore = useAppStore((s) => s.revealNotBefore);
  // The step asked for is not on the map yet; it is late once the picture there has had its time and a little more.
  const behind = playing && shownGroupIndex !== null && shownGroupIndex !== activeGroupIndex;
  const [late, setLate] = useState(false);

  // Auto-advance through mosaic groups while playing, left to right along
  // the slider — oldest to newest, starting wherever the slider already is
  // (V-9), each step once it is on the map (`playback.ts`). `groups` is
  // newest-first (index 0 = newest = the slider's right end, see
  // `sliderValue` below), so moving right means *decreasing*
  // `activeGroupIndex`; wrapping that below 0 back to `groups.length - 1`
  // is also what makes pressing play at the default, rightmost position
  // (the newest scene) restart from the leftmost (oldest) one.
  useEffect(() => {
    if (!playing || groups.length < 2) return;
    return runPlayback();
  }, [playing, groups]);

  useEffect(() => {
    setLate(false);
    if (!behind) return;
    const id = window.setTimeout(() => setLate(true), Math.max(0, revealNotBefore - Date.now()) + STEP_LATE_AFTER_MS);
    return () => window.clearTimeout(id);
  }, [behind, activeGroupIndex, revealNotBefore]);

  if (groups.length === 0) return null;

  // groups are newest-first; show oldest→newest left→right.
  const sliderValue = groups.length - 1 - activeGroupIndex;
  // A step is named by the date of its pass, never by the scene (Otto, 30.10.2026). Playing, the pass on the map names
  // the step, and the slider is ahead of it while the next one loads.
  const name = (index: number) => stepLabel(groups[index]);
  const loading = behind && late;

  return (
    <div className="time-slider">
      <button
        type="button"
        className="play-btn"
        onClick={() => {
          // Playing shows the steps on the map: with the results hidden, "Play" shows them again (Otto, 30.10.2026).
          if (!playing && !resultsOnMap) toggleResultsOnMap();
          setPlaying(!playing);
        }}
        aria-label={playing ? 'Pause' : 'Play'}
        disabled={groups.length < 2}
      >
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="time-track">
        <div className="time-labels">
          <span>{name(groups.length - 1)}</span>
          <strong>{name(playing && shownGroupIndex !== null ? shownGroupIndex : activeGroupIndex)}</strong>
          <span>{name(0)}</span>
        </div>
        <input
          type="range"
          min={0}
          max={groups.length - 1}
          step={1}
          value={sliderValue}
          onChange={(e) => setActiveGroupIndex(groups.length - 1 - Number(e.target.value))}
          aria-label="Timeline (mosaic groups)"
        />
      </div>
      <span className="time-count" title={loading ? 'Waiting for the next step to load; the picture stays until it has' : undefined}>
        {loading ? 'Loading…' : `${activeGroupIndex + 1}/${groups.length}`}
      </span>
    </div>
  );
}
