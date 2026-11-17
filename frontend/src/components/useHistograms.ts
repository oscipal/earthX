// The histograms of the bands a picture draws, asked once per question (`key`) and kept for the page: the statistics are the same
// every time (the tiler caches them as well). `null` while they are on their way, where there are none, or where the question failed.
//
// With a `family` (the same picture with other values of its parameters, M5-14, Otto, 17.11.2026) a new question of the same family keeps
// the histograms of the last answer until its own come, and is asked only once the question rests: a dial turned through many degrees asks
// once, and the panel does not jump.

import { useEffect, useRef, useState } from 'react';

import type { Histogram } from '../histogram';

const asked = new Map<string, Promise<Histogram[] | null>>();

// How long a question of the same family rests before it is asked.
export const HISTOGRAM_REST_MS = 400;

type Answer = { key: string; family: string | null; histograms: Histogram[] | null };

export function useHistograms(key: string | null, load: () => Promise<Histogram[] | null>, family: string | null = null): Histogram[] | null {
  const [answer, setAnswer] = useState<Answer | null>(null);
  // `load` belongs to `key`: a new key is a new question, a new function for the same key is not.
  const loader = useRef(load);
  loader.current = load;
  const last = useRef(answer);
  last.current = answer;
  useEffect(() => {
    if (key === null) return undefined;
    let current = true;
    const ask = () => {
      let pending = asked.get(key);
      if (!pending) {
        // A failure is asked again with the next question of the same key; statistics without histograms are an answer.
        pending = loader.current().catch(() => {
          asked.delete(key);
          return null;
        });
        asked.set(key, pending);
      }
      void pending.then((histograms) => current && setAnswer({ key, family, histograms }));
    };
    const held = last.current;
    const rests = family !== null && held !== null && held.family === family && held.key !== key && !asked.has(key);
    const timer = rests ? setTimeout(ask, HISTOGRAM_REST_MS) : undefined;
    if (!rests) ask();
    return () => {
      current = false;
      clearTimeout(timer);
    };
  }, [key, family]);
  if (!answer) return null;
  return answer.key === key || (family !== null && answer.family === family) ? answer.histograms : null;
}

// For the tests: forget every answer.
export function forgetHistograms(): void {
  asked.clear();
}
