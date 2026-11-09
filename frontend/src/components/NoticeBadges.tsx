// The notices of a dataset (`earthx:notices`, DS-04 plan §4.4, §4.6): one badge each, in English, the explanation in
// its tooltip and no text beside it. The same marks in the Data catalogue, in the results and on the view or layer.

import { noticesOf } from '../datasets';
import type { Collection } from '../types';
import Badge from './Badge';

export default function NoticeBadges({ collection }: { collection: Collection | null | undefined }) {
  if (!collection) return null;
  return (
    <>
      {noticesOf(collection).map((notice) => (
        <Badge key={notice.code} tip={notice.tooltip} tipLevel="simple">
          {notice.label}
        </Badge>
      ))}
    </>
  );
}
