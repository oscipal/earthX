// The histograms of the bands a picture draws, asked once per question (`key`) and kept for the page: the statistics are the same
// every time (the tiler caches them as well). `null` while they are on their way, where there are none, or where the question failed.

import { useEffect, useRef, useState } from 'react';

import type { Histogram } from '../histogram';

const asked = new Map<string, Promise<Histogram[] | null>>();

export function useHistograms(key: string | null, load: () => Promise<Histogram[] | null>): Histogram[] | null {
  const [answer, setAnswer] = useState<{ key: string; histograms: Histogram[] | null } | null>(null);
  // `load` belongs to `key`: a new key is a new question, a new function for the same key is not.
  const loader = useRef(load);
  loader.current = load;
  useEffect(() => {
    if (key === null) return undefined;
    let current = true;
    let pending = asked.get(key);
    if (!pending) {
      // A failure is asked again with the next question of the same key; statistics without histograms are an answer.
      pending = loader.current().catch(() => {
        asked.delete(key);
        return null;
      });
      asked.set(key, pending);
    }
    void pending.then((histograms) => current && setAnswer({ key, histograms }));
    return () => {
      current = false;
    };
  }, [key]);
  return answer && answer.key === key ? answer.histograms : null;
}

// For the tests: forget every answer.
export function forgetHistograms(): void {
  asked.clear();
}
