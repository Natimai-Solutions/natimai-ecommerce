import { describe, expect, it } from 'vitest';

import { mediaIdFromUrl } from './media';

describe('mediaIdFromUrl', () => {
  it('reads the asset id of a media-library URL', () => {
    expect(
      mediaIdFromUrl(
        'https://api.exemple.pf/api/v1/media/A4BD7347-3E74-409A-B025-BBF1C2B1B624/1600.webp',
      ),
    ).toBe('a4bd7347-3e74-409a-b025-bbf1c2b1b624');
  });

  it('ignores external URLs and empty values', () => {
    expect(mediaIdFromUrl('https://cdn.exemple.pf/photo.jpg')).toBeNull();
    expect(mediaIdFromUrl('')).toBeNull();
    expect(mediaIdFromUrl(null)).toBeNull();
  });
});
