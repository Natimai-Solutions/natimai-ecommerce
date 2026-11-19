import { describe, expect, it, vi } from 'vitest';

vi.mock('@/boot/api', () => ({ api: { get: vi.fn() } }));

import { previewFromHash } from './homepage';

describe('homepage preview link', () => {
  it('reads the token, the date and the audience from the fragment', () => {
    expect(
      previewFromHash('#apercu=abc&date=2026-12-01T08:00:00Z&public=client&groupe=g1'),
    ).toEqual({ token: 'abc', at: '2026-12-01T08:00:00Z', scope: 'customer', priceGroupId: 'g1' });
  });

  it('is not a preview without a token, and a group only for customers', () => {
    expect(previewFromHash('#top')).toBeNull();
    expect(previewFromHash('#apercu=abc&groupe=g1')?.priceGroupId).toBeNull();
  });
});
