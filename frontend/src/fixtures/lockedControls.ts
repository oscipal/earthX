// UI-04 §7.5 no. 8: a locked control says why in its tooltip. Lists every locked button, field and choice under `root` that has no
// reason: no `data-tip` on it or on its label, or one that only repeats what the control says. The one tooltip is `data-tip` (UI-04 part 3a).
export function lockedWithoutReason(root: ParentNode): string[] {
  const controls = [...root.querySelectorAll<HTMLElement>('button, input, select, textarea, [role="button"]')];
  return controls.flatMap((control) => {
    const locked = control.hasAttribute('disabled') || control.getAttribute('aria-disabled') === 'true';
    if (!locked || (control instanceof HTMLInputElement && control.type === 'hidden')) return [];
    const label = control.closest('label');
    const reason = (control.getAttribute('data-tip') ?? label?.getAttribute('data-tip') ?? '').trim();
    const says = (control.textContent ?? '').trim();
    return reason === '' || reason === says ? [control.getAttribute('aria-label') ?? (says || control.outerHTML.slice(0, 80))] : [];
  });
}
