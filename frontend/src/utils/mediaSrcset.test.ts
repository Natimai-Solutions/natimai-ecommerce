import { describe, expect, it } from 'vitest';

import { mediaSrcset } from './mediaSrcset';

const BASE = 'https://api.shop.test/api/v1/media/0b9a1c2e-3f4d-4a5b-8c6d-7e8f9a0b1c2d/';

describe('srcset of an uploaded image', () => {
  it('lists every stored width up to the largest', () => {
    expect(mediaSrcset(`${BASE}1600.webp`)).toBe(
      `${BASE}480.webp 480w, ${BASE}960.webp 960w, ${BASE}1600.webp 1600w`,
    );
  });

  it('stops at a narrower original', () => {
    expect(mediaSrcset(`${BASE}700.webp`)).toBe(`${BASE}480.webp 480w, ${BASE}700.webp 700w`);
  });

  it('gives nothing for a single width or a foreign photo', () => {
    expect(mediaSrcset(`${BASE}300.webp`)).toBeUndefined();
    expect(mediaSrcset('https://cdn.supplier.test/photo/123.jpg')).toBeUndefined();
    expect(mediaSrcset(null)).toBeUndefined();
  });
});
