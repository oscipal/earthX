import { useEffect, useState } from 'react';

import { loadColormaps, type ColormapGroup } from '../colormaps';

// The groups of the tiler, for the field and the list: `null` until they are here, `'failed'` where they could not be read.
export function useColormapGroups(): ColormapGroup[] | null | 'failed' {
  const [groups, setGroups] = useState<ColormapGroup[] | null | 'failed'>(null);
  useEffect(() => {
    let current = true;
    void loadColormaps().then((read) => current && setGroups(read ?? 'failed'));
    return () => {
      current = false;
    };
  }, []);
  return groups;
}
