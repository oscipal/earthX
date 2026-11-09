// DS-04c: the notices of a dataset (`earthx:notices`, DS-04 plan §4.4), read entry by entry. Synthetic collections only.

import { describe, expect, it } from 'vitest';

import { noticesOf } from './datasets';
import type { Collection } from './types';

const radar = (extra: Partial<Collection> = {}): Collection => ({ id: 'radar', title: 'Radar', ...extra }) as Collection;

describe('noticesOf', () => {
  const notice = { code: 'uncalibrated_dn', label: 'Uncalibrated (DN)', tooltip: 'Values are digital numbers.' };

  it('reads the notices in the order the registry gives them', () => {
    const second = { code: 'approximate_geolocation', label: 'Approximate geolocation', tooltip: 'Placed by GCPs.' };
    expect(noticesOf(radar({ 'earthx:notices': [notice, second] }))).toEqual([notice, second]);
  });

  it('has none where the field is absent, null or not a list', () => {
    expect(noticesOf(radar())).toEqual([]);
    expect(noticesOf(radar({ 'earthx:notices': null }))).toEqual([]);
    expect(noticesOf(radar({ 'earthx:notices': 'Approximate geolocation' as never }))).toEqual([]);
  });

  it('leaves out an entry that is not a whole notice instead of showing half of it', () => {
    const broken = [null, 'text', { code: 'a', label: 'A' }, { code: 'b', label: '', tooltip: 'x' }, { code: 'c', label: 3, tooltip: 'x' }, notice];
    expect(noticesOf(radar({ 'earthx:notices': broken }))).toEqual([notice]);
  });

  it('shows a code given twice once, the first time', () => {
    const again = { ...notice, label: 'Again' };
    expect(noticesOf(radar({ 'earthx:notices': [notice, again] }))).toEqual([notice]);
  });
});
