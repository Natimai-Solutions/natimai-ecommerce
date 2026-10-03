import type { MediaKind } from '@/api/media';

/**
 * What to upload where (03/10/2026): the storefront crops hero, banner and
 * category images to a fixed ratio (`object-fit: cover`) and shows product
 * pictures whole (`contain`); the media library re-encodes everything in WebP
 * at a few widths, so a large original is what matters, not a small one.
 */
export type ImageFormatKey =
  'hero' | 'banner' | 'category' | 'product' | 'page' | 'logo' | 'icon' | 'other';

/** The i18n key of the recommendation shown next to an upload. */
export function imageFormatLabelKey(format: ImageFormatKey): string {
  return `media.format_${format}`;
}

/** Default recommendation for a media-library usage. */
export function formatForKind(kind: MediaKind): ImageFormatKey {
  switch (kind) {
    case 'homepage':
      return 'banner';
    case 'product':
      return 'product';
    case 'category':
      return 'category';
    case 'page':
      return 'page';
    case 'branding':
      return 'logo';
    default:
      return 'other';
  }
}
