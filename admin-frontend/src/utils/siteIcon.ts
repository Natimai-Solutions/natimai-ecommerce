/**
 * Swap the document's favicon links for the site icon chosen in the
 * back-office (`GET /system/config` → `branding.icon`): the storefront and
 * the admin then share one tab icon. Only the sizes the API derives are
 * declared (16, 32 as favicon, 180 for Apple); nothing is touched when no
 * icon is configured, so the bundled icons of index.html stay.
 */
export interface SiteIcon {
  base: string;
  sizes: number[];
}

const FAVICON_SIZES = [16, 32];
const APPLE_SIZE = 180;

export function applySiteIcon(icon: SiteIcon | null | undefined): void {
  if (!icon || typeof document === 'undefined') return;
  const head = document.head;
  for (const link of Array.from(
    head.querySelectorAll('link[rel="icon"], link[rel="apple-touch-icon"]'),
  )) {
    link.remove();
  }
  for (const size of FAVICON_SIZES.filter((s) => icon.sizes.includes(s))) {
    const link = document.createElement('link');
    link.rel = 'icon';
    link.type = 'image/png';
    link.sizes.add(`${size}x${size}`);
    link.href = `${icon.base}/icon-${size}.png`;
    head.appendChild(link);
  }
  if (icon.sizes.includes(APPLE_SIZE)) {
    const link = document.createElement('link');
    link.rel = 'apple-touch-icon';
    link.sizes.add(`${APPLE_SIZE}x${APPLE_SIZE}`);
    link.href = `${icon.base}/icon-${APPLE_SIZE}.png`;
    head.appendChild(link);
  }
}
