// "auto-scale": the one button that puts a suggested range in the fields of the settings of a picture — measured from the
// source in the view of scenes, taken from the statistics of the job in the settings of a result. The same name, the same
// size and the same look in both places (Otto, 30.10.2026, zu #234).
export default function AutoScaleButton({ title, busy = false, onClick }: { title: string; busy?: boolean; onClick: () => void }) {
  return (
    <button type="button" className="ghost-btn vc-auto" disabled={busy} title={title} onClick={onClick}>
      auto-scale
    </button>
  );
}
