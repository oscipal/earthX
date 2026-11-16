// The answer "Remove" of the question that comes before a layer is removed (UI-09): the dialog lies in `document.body`, not in the container
// of a test. Call it inside the test after the click on the bin.
import { act } from 'react';

export function confirmRemoval(): void {
  const dialog = document.body.querySelector('[role="alertdialog"]');
  const answer = [...(dialog?.querySelectorAll('button') ?? [])].find((b) => b.textContent === 'Remove');
  if (!answer) throw new Error('No question about removing a layer is open');
  act(() => answer.click());
}
