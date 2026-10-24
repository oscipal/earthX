// "Share" (M4-19e, plan §3.5): keeps the order and the view of the map under a link of its own,
// good for 30 days. Whoever opens the link gets the dataset, the scenes, the area and the steps back,
// and starts the job themselves; the link holds no job and no result (Q9).

import { useState } from 'react';

import { createPermalink, permalinkAddress, rememberKey, removePermalink, viewOf, type Created } from '../permalink';
import type { OrderView } from '../processingStore';
import { useProcessingStore } from '../processingStore';
import { handRange } from '../resultLayer';
import { useAppStore } from '../store';
import CopyButton from './CopyButton';

export default function ShareLink({ view }: { view: OrderView }) {
  const bbox = useAppStore((s) => s.viewportBbox);
  const zoom = useAppStore((s) => s.mapZoom);
  const range = useProcessingStore((s) => s.range);
  const [busy, setBusy] = useState(false);
  const [made, setMade] = useState<Created | null>(null);
  const [note, setNote] = useState<{ ok: boolean; text: string } | null>(null);

  const order = view.runAs === 'one' ? view.built?.order : undefined;
  const blocked = !order ? (view.runAs === 'one' ? 'Complete the order first.' : 'A link holds one order: choose “One job”.') : null;

  const share = async () => {
    if (!order || !bbox) return;
    setBusy(true);
    setNote(null);
    try {
      const created = await createPermalink(order, viewOf(bbox, zoom, handRange(range)));
      rememberKey(created);
      setMade(created);
    } catch (error) {
      setNote({ ok: false, text: `The link could not be made: ${error instanceof Error ? error.message : String(error)}` });
    }
    setBusy(false);
  };

  // Without a question: the link is deleted at once, and the panel says so.
  const remove = async (id: string) => {
    setBusy(true);
    try {
      const deleted = await removePermalink(id);
      setMade(null);
      setNote({ ok: true, text: deleted ? 'Link deleted.' : 'This browser has no key for the link; it expires on its own.' });
    } catch (error) {
      setNote({ ok: false, text: `The link could not be deleted: ${error instanceof Error ? error.message : String(error)}` });
    }
    setBusy(false);
  };

  return (
    <div className="pp-share" aria-label="Share">
      {made ? (
        <>
          <div className="pp-share-link">
            <input type="text" readOnly value={permalinkAddress(made.id)} aria-label="Link" onFocus={(e) => e.currentTarget.select()} />
            <CopyButton text={permalinkAddress(made.id)} title="Copy link" label="Copy link" />
            <button
              type="button"
              className="delete-btn"
              title="Delete link"
              aria-label="Delete link"
              disabled={busy}
              onClick={() => void remove(made.id)}
            >
              ✕
            </button>
          </div>
          <p className="pp-help">Good until {new Date(made.expiresAt).toLocaleDateString()}. Anyone with the link sees your area.</p>
        </>
      ) : (
        <>
          <button
            type="button"
            className="ghost-btn"
            disabled={busy || !!blocked || !bbox}
            title={blocked ?? 'Keep this order and the map view under a link for 30 days'}
            onClick={() => void share()}
          >
            {busy ? 'Sharing…' : 'Share'}
          </button>
        </>
      )}
      {note && (
        <p className={note.ok ? 'pp-help' : 'hint-text error'} role="status">
          {note.text}
        </p>
      )}
    </div>
  );
}
