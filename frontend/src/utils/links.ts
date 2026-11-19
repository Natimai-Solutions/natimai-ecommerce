/** A storefront path (`/catalogue…`), not an address of another site. */
export function isInternalLink(link: string): boolean {
  return link.startsWith('/') && !link.startsWith('//') && !link.startsWith('/\\');
}

/** Attributes of a link written in the back-office: a router link for a
 *  storefront path, a new tab for another site. */
export function linkAttrs(link: string): Record<string, string> {
  return isInternalLink(link)
    ? { to: link }
    : { href: link, target: '_blank', rel: 'noopener noreferrer' };
}
