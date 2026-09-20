import { useEffect } from 'react';

import { useAppStore } from '../store';

export default function TimeSlider() {
  const groups = useAppStore((s) => s.groups);
  const activeGroupIndex = useAppStore((s) => s.activeGroupIndex);
  const setActiveGroupIndex = useAppStore((s) => s.setActiveGroupIndex);
  const selectAllInActiveGroup = useAppStore((s) => s.selectAllInActiveGroup);
  const addCurrentToLayers = useAppStore((s) => s.addCurrentToLayers);
  const playing = useAppStore((s) => s.playing);
  const setPlaying = useAppStore((s) => s.setPlaying);

  // Auto-advance through mosaic groups while playing.
  useEffect(() => {
    if (!playing || groups.length < 2) return;
    const id = window.setInterval(() => {
      const s = useAppStore.getState();
      s.setActiveGroupIndex((s.activeGroupIndex + 1) % s.groups.length);
    }, 1400);
    return () => window.clearInterval(id);
  }, [playing, groups.length]);

  if (groups.length === 0) return null;

  const active = groups[activeGroupIndex];
  // groups are newest-first; show oldest→newest left→right.
  const sliderValue = groups.length - 1 - activeGroupIndex;
  const frameCount = active?.items.length ?? 0;

  return (
    <div className="panel time-slider">
      <button
        type="button"
        className="play-btn"
        onClick={() => setPlaying(!playing)}
        aria-label={playing ? 'Pause' : 'Play'}
        disabled={groups.length < 2}
      >
        {playing ? '❚❚' : '▶'}
      </button>
      <div className="time-track">
        <div className="time-labels">
          <span>{groups[groups.length - 1]?.label}</span>
          <strong>{active?.label}</strong>
          <span>{groups[0]?.label}</span>
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
        <div className="mosaic-info">
          <span>
            {frameCount} image{frameCount === 1 ? '' : 's'}
            {frameCount > 1 && ' covering ROI'}
          </span>
          {frameCount > 0 && (
            <button type="button" className="link-btn" onClick={() => selectAllInActiveGroup()}>
              + select all frames
            </button>
          )}
          <button
            type="button"
            className="link-btn"
            title="Pin the selected scenes (or this group) into the layer manager"
            onClick={() => addCurrentToLayers()}
          >
            + add to layers
          </button>
        </div>
      </div>
      <span className="time-count">
        {activeGroupIndex + 1}/{groups.length}
      </span>
    </div>
  );
}
