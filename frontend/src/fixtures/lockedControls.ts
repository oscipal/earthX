// UI-04 §7.5 no. 8: a locked control says why in its tooltip. Lists every locked button, field and choice under `root` that has no
// reason: no `title` or `data-tip` on it or on its label, or one that only repeats what the control says.
export function lockedWithoutReason(root: ParentNode): string[] {
  const controls = [...root.querySelectorAll<HTMLElement>('button, input, select, textarea, [role="button"]')];
  return controls.flatMap((control) => {
    const locked = control.hasAttribute('disabled') || control.getAttribute('aria-disabled') === 'true';
    if (!locked || (control instanceof HTMLInputElement && control.type === 'hidden')) return [];
    const label = control.closest('label');
    const reason = (control.getAttribute('title') ?? control.getAttribute('data-tip') ?? label?.getAttribute('title') ?? '').trim();
    const says = (control.textContent ?? '').trim();
    return reason === '' || reason === says ? [control.getAttribute('aria-label') ?? (says || control.outerHTML.slice(0, 80))] : [];
  });
}
