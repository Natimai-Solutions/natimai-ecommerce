/**
 * `robots.txt` and `sitemap.xml`, served by the SSR server (R8 / U6).
 *
 * The sitemap lists the public pages and every product the API shows on the
 * storefront (`GET /product/sitemap`: id, name, last change); it is rebuilt
 * at most once an hour. The site origin is `PUBLIC_SITE_URL` (runtime) or
 * `VITE_PUBLIC_SITE_URL` (build), else the request's own host behind the
 * proxy. Private pages (account, cart, checkout, sign-in…) are disallowed.
 */
import { type Request, type Response } from 'express';
import { defineSsrMiddleware } from '#q-app';

const PRIVATE_PATHS = [
  '/mon-compte',
  '/panier',
  '/checkout',
  '/connexion',
  '/inscription',
  '/mot-de-passe-oublie',
  '/reinitialiser',
  '/oauth/',
  '/paiement/',
  '/suivi/',
];

const STATIC_PATHS: { path: string; changefreq: string; priority: string }[] = [
  { path: '/', changefreq: 'daily', priority: '1.0' },
  { path: '/catalogue', changefreq: 'daily', priority: '0.9' },
  { path: '/comment-ca-marche', changefreq: 'monthly', priority: '0.5' },
  { path: '/cgv', changefreq: 'yearly', priority: '0.2' },
  { path: '/mentions-legales', changefreq: 'yearly', priority: '0.2' },
  { path: '/confidentialite', changefreq: 'yearly', priority: '0.2' },
];

const SITEMAP_TTL_MS = 60 * 60 * 1000;
const FETCH_TIMEOUT_MS = 15_000;

interface SitemapEntry {
  id: string;
  name: string;
  modify_at?: string | null;
}

function siteOrigin(req: Request): string {
  const configured = process.env.PUBLIC_SITE_URL || import.meta.env.VITE_PUBLIC_SITE_URL || '';
  if (configured) return configured.replace(/\/$/, '');
  const proto = (req.headers['x-forwarded-proto'] as string | undefined)?.split(',')[0]?.trim();
  const host = (req.headers['x-forwarded-host'] as string | undefined)?.split(',')[0]?.trim();
  return `${proto || req.protocol}://${host || req.get('host') || 'localhost'}`;
}

/** Same rule as `slugifyProductName` in the app (kept in sync by hand). */
function slugify(name: string): string {
  return name
    .toLowerCase()
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 90);
}

function escapeXml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;');
}

async function fetchProducts(): Promise<SitemapEntry[]> {
  const apiUrl = (process.env.API_URL || import.meta.env.VITE_API_URL || '').replace(/\/$/, '');
  if (!apiUrl) return [];
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);
  try {
    const response = await fetch(`${apiUrl}/api/v1/product/sitemap`, { signal: controller.signal });
    if (!response.ok) return [];
    const payload = (await response.json()) as { items?: SitemapEntry[] };
    return payload.items ?? [];
  } catch {
    return []; // the static pages still ship; the next request retries
  } finally {
    clearTimeout(timer);
  }
}

function buildSitemap(origin: string, products: SitemapEntry[]): string {
  const urls: string[] = STATIC_PATHS.map(
    ({ path, changefreq, priority }) =>
      `<url><loc>${escapeXml(origin + path)}</loc><changefreq>${changefreq}</changefreq><priority>${priority}</priority></url>`,
  );
  for (const product of products) {
    const slug = slugify(product.name);
    const path = `/produit/${product.id}${slug ? `/${slug}` : ''}`;
    const lastmod = product.modify_at ? product.modify_at.slice(0, 10) : null;
    urls.push(
      `<url><loc>${escapeXml(origin + path)}</loc>${lastmod ? `<lastmod>${lastmod}</lastmod>` : ''}<changefreq>weekly</changefreq><priority>0.7</priority></url>`,
    );
  }
  return `<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n${urls.join('\n')}\n</urlset>\n`;
}

export default defineSsrMiddleware(({ app, resolve }) => {
  let cache: { origin: string; body: string; builtAt: number } | null = null;

  app.get(resolve.urlPath('/robots.txt'), (req: Request, res: Response) => {
    const origin = siteOrigin(req);
    const lines = [
      'User-agent: *',
      ...PRIVATE_PATHS.map((path) => `Disallow: ${path}`),
      'Allow: /',
      '',
      `Sitemap: ${origin}/sitemap.xml`,
      '',
    ];
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=3600');
    res.send(lines.join('\n'));
  });

  app.get(resolve.urlPath('/sitemap.xml'), async (req: Request, res: Response) => {
    const origin = siteOrigin(req);
    if (!cache || cache.origin !== origin || Date.now() - cache.builtAt > SITEMAP_TTL_MS) {
      const products = await fetchProducts();
      cache = { origin, body: buildSitemap(origin, products), builtAt: Date.now() };
    }
    res.setHeader('Content-Type', 'application/xml; charset=utf-8');
    res.setHeader('Cache-Control', 'public, max-age=3600');
    res.send(cache.body);
  });
});
