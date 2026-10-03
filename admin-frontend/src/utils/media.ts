/**
 * The media-library asset an `image_url` points at (`…/media/<id>/1600.webp`),
 * or null for an external URL typed by hand. Lets a form edit the image's alt
 * text after the upload, next to the URL field.
 */
const ASSET_ID_IN_URL =
  /\/media\/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})\//i;

export function mediaIdFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const match = ASSET_ID_IN_URL.exec(url);
  return match?.[1]?.toLowerCase() ?? null;
}
