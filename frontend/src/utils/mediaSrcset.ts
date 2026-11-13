/**
 * `srcset` of an image uploaded to the shop (audit 2026-11).
 *
 * The API re-encodes every upload as WebP at 480, 960 and 1600 px (never
 * upscaled: a narrower original is its own last width) and the catalogue
 * stores the largest one, `…/media/{asset}/{width}.webp`. The smaller
 * widths are therefore known from that URL alone — a phone no longer
 * downloads the 1600 px file for a 180 px card. Any other URL (supplier
 * photo, external host) gets no `srcset`.
 */
const VARIANT_WIDTHS = [480, 960, 1600] as const;
const MEDIA_URL = /^(.*\/media\/[0-9a-fA-F-]{36}\/)(\d+)\.webp$/;

export function mediaSrcset(url: string | null | undefined): string | undefined {
  const match = url ? MEDIA_URL.exec(url) : null;
  if (!match) return undefined;
  const base = match[1]!;
  const largest = Number(match[2]);
  if (!Number.isInteger(largest) || largest <= 0) return undefined;
  const widths = [...VARIANT_WIDTHS.filter((w) => w < largest), largest];
  if (widths.length < 2) return undefined;
  return widths.map((w) => `${base}${w}.webp ${w}w`).join(', ');
}
