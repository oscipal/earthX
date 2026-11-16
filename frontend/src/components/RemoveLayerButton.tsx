// The bin of a layer, in the row of the layer manager and in the settings bar (UI-09, Otto, 16.11.2026): it asks before the layer is removed.
// "Cancel" (the focused answer, so that a slip of the Enter key removes nothing), Escape and a click beside the dialog keep the layer.

import { useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';

import type { MapLayer } from '../layers';
import { useAppStore } from '../store';
import { TrashIcon } from './icons';

export const REMOVE_TIP = 'Remove layer';
export const REMOVE_TITLE = 'Remove this layer?';

// Through a portal into `.app`, as the popovers: a row is moved with `transform`, which would pin a fixed backdrop to it, and `.app` carries the
// theme tokens the colours come from.
function RemoveDialog({ host, name, onRemove, onCancel }: { host: Element; name: string; onRemove: () => void; onCancel: () => void }) {
  const cancel = useRef<HTMLButtonElement>(null);
  const remove = useRef<HTMLButtonElement>(null);
  useEffect(() => cancel.current?.focus(), []);
  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      onCancel();
    } else if (event.key === 'Tab') {
      // Two buttons: the focus stays between them.
      event.preventDefault();
      (document.activeElement === cancel.current ? remove.current : cancel.current)?.focus();
    }
  };
  return createPortal(
    <div className="dialog-backdrop" onClick={onCancel}>
      <div
        className="panel dialog-panel"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="remove-layer-title"
        aria-describedby="remove-layer-body"
        onClick={(event) => event.stopPropagation()}
        onKeyDown={onKeyDown}
      >
        <div className="results-head">
          <h2 id="remove-layer-title">{REMOVE_TITLE}</h2>
        </div>
        <div className="dialog-body" id="remove-layer-body">
          <p>{name}</p>
          <p className="hint">The layer leaves the map and the list.</p>
        </div>
        <div className="dialog-actions">
          <button type="button" className="btn" ref={cancel} onClick={onCancel}>
            Cancel
          </button>
          <button type="button" className="btn danger" ref={remove} onClick={onRemove}>
            Remove
          </button>
        </div>
      </div>
    </div>,
    host,
  );
}

interface Props {
  layer: MapLayer;
  className: string;
  col?: string;
  iconSize?: 14;
}

export default function RemoveLayerButton({ layer, className, col, iconSize }: Props) {
  const remove = useAppStore((s) => s.removeLayer);
  const [asking, setAsking] = useState(false);
  const button = useRef<HTMLButtonElement>(null);
  return (
    <>
      <button type="button" ref={button} className={className} data-col={col} data-tip-level="advanced" data-tip={REMOVE_TIP} aria-label={REMOVE_TIP} onClick={() => setAsking(true)}>
        <TrashIcon size={iconSize} />
      </button>
      {asking && (
        <RemoveDialog
          host={button.current?.closest('.app') ?? document.body}
          name={layer.name}
          onCancel={() => setAsking(false)}
          onRemove={() => {
            setAsking(false);
            remove(layer.id);
          }}
        />
      )}
    </>
  );
}
