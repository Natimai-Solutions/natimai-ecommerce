/**
 * SEO helpers shared by the pages (R8 / U6): the public site URL, absolute
 * URLs for canonical links and JSON-LD, the `robots` tag of private pages.
 */

/** Public storefront origin, from the build (`VITE_PUBLIC_SITE_URL`); '' when unset. */
export function publicSiteUrl(): string {
  return import.meta.env.VITE_PUBLIC_SITE_URL?.replace(/\/$/, '') ?? '';
}

/** `https://shop.example.com/catalogue`, or null when the site URL is unknown. */
export function absoluteUrl(path: string): string | null {
  const base = publicSiteUrl();
  return base ? `${base}${path.startsWith('/') ? path : `/${path}`}` : null;
}

/** `<meta name="robots">` of a page search engines must not index. */
export const NOINDEX = { robots: { name: 'robots', content: 'noindex, nofollow' } };

/**
 * A `<script type="application/ld+json">` for Quasar's `useMeta` (`script`
 * entry). `</script>` sequences in the data are escaped so a product
 * description cannot close the tag.
 */
export function jsonLd(data: Record<string, unknown>): Record<string, string> {
  return {
    type: 'application/ld+json',
    innerHTML: JSON.stringify(data).replace(/</g, '\\u003c'),
  };
}

/** One BreadcrumbList item list for JSON-LD (`absoluteUrl` applied to paths). */
export function breadcrumbList(
  items: { name: string; path: string }[],
): Record<string, unknown> | null {
  if (!publicSiteUrl() || items.length === 0) return null;
  return {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: items.map((item, index) => ({
      '@type': 'ListItem',
      position: index + 1,
      name: item.name,
      item: absoluteUrl(item.path),
    })),
  };
}
