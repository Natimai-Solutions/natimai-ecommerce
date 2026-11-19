import { describe, expect, it, vi } from 'vitest';

vi.mock('@/boot/api', () => ({ api: {} }));

import { previewUrl } from './homepage';

const link = { token: 't.k.n', expires_at: '', storefront_url: 'https://shop.example' };

describe('homepage preview address', () => {
  it('puts the token in the fragment, never in the query', () => {
    const url = previewUrl(link, { at: '2026-12-01T08:00:00.000Z' });
    expect(url.startsWith('https://shop.example/#apercu=t.k.n')).toBe(true);
    expect(url).not.toContain('?');
    expect(new URLSearchParams(url.split('#')[1]).get('date')).toBe('2026-12-01T08:00:00.000Z');
  });

  it('names the audience and the group of a customer preview only', () => {
    const fragment = new URLSearchParams(
      previewUrl(link, { customer: true, priceGroupId: 'g1' }).split('#')[1],
    );
    expect(fragment.get('public')).toBe('client');
    expect(fragment.get('groupe')).toBe('g1');
    expect(previewUrl(link, { priceGroupId: 'g1' })).not.toContain('groupe');
  });
});
