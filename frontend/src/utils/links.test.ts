import { describe, expect, it } from 'vitest';

import { isInternalLink, linkAttrs } from './links';

describe('links written in the back-office', () => {
  it('routes a storefront path and opens another site in a new tab', () => {
    expect(linkAttrs('/catalogue?cat=1')).toEqual({ to: '/catalogue?cat=1' });
    expect(linkAttrs('https://example.com').target).toBe('_blank');
  });

  it('never takes a protocol-relative address for a storefront path', () => {
    expect(isInternalLink('//evil.example')).toBe(false);
    expect(isInternalLink('/\\evil.example')).toBe(false);
  });
});
