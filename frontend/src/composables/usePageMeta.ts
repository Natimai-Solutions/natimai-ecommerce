import { useMeta } from 'quasar';
import { useRoute } from 'vue-router';

import { NOINDEX, absoluteUrl } from '@/utils/seo';

export interface PageMetaInput {
  /** Document title, already suffixed with the shop name when wanted. */
  title: string;
  description?: string | null;
  /** Private or transactional page: `noindex, nofollow`, no canonical. */
  noindex?: boolean;
}

/**
 * Title, description, Open Graph tags, canonical link (when the public site
 * URL is known) and the `robots` tag of a storefront page (R8 / U6). The
 * callback is reactive, like `useMeta`'s.
 */
export function usePageMeta(input: () => PageMetaInput): void {
  const route = useRoute();
  useMeta(() => {
    const { title, description, noindex } = input();
    const meta: Record<string, { name?: string; property?: string; content: string }> = {
      ogTitle: { property: 'og:title', content: title },
      ogType: { property: 'og:type', content: 'website' },
    };
    if (description) {
      meta['description'] = { name: 'description', content: description };
      meta['ogDescription'] = { property: 'og:description', content: description };
    }
    const link: Record<string, { rel: string; href: string }> = {};
    if (noindex) {
      Object.assign(meta, NOINDEX);
    } else {
      const canonical = absoluteUrl(route.path);
      if (canonical) {
        meta['ogUrl'] = { property: 'og:url', content: canonical };
        link['canonical'] = { rel: 'canonical', href: canonical };
      }
    }
    return { title, meta, link };
  });
}
