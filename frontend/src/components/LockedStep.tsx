// A step that came with a result (NM4-05b, adr/0019): shown as it stands in the order of the job, read only, folded to
// its title. It can be neither changed, moved nor removed; the steps the person adds follow it.

import { stepName } from '../processingBands';
import type { Operator } from '../processingOrder';
import type { FieldValue } from '../schemaForm';

export default function LockedStep({
  index,
  operator,
  values,
}: {
  index: number;
  operator: Operator | undefined;
  values: Record<string, FieldValue>;
}) {
  // What the step was given, by the title of the field; a field left empty says nothing.
  const given = (operator?.form.supported ? operator.form.fields : []).flatMap((field) => {
    const value = values[field.name];
    const text = typeof value === 'boolean' ? (value ? 'yes' : 'no') : typeof value === 'string' ? value : '';
    return field.kind === 'const' || text === '' ? [] : [{ name: field.name, title: field.title, text }];
  });
  return (
    <li className="pp-step pp-locked" aria-label={`Step ${index + 1}: ${operator?.title ?? 'unknown operator'} (locked)`}>
      <details>
        <summary className="pp-step-title">
          <span aria-hidden="true">🔒 </span>
          {index + 1}. {stepName(operator, values, index)}
          {operator && <span className="pp-step-op"> {operator.title.toLowerCase()}</span>}
        </summary>
        <dl className="pp-given">
          {given.map((entry) => (
            <div key={entry.name}>
              <dt>{entry.title}</dt>
              <dd>{entry.text}</dd>
            </div>
          ))}
        </dl>
      </details>
    </li>
  );
}
