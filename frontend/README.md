# Vitrine (frontend)

Application Quasar (Vue 3, TypeScript) rendue côté serveur (SSR, Express) :
catalogue, fiche produit, panier, checkout, espace client, pages de contenu.
Socle partagé avec le back-office : jetons `--n-*`, thème clair / sombre,
icônes Phosphor, `AppNotice` / `StatusTag` (`shared/ui`), formats
(`shared/utils`), types de l'API (`shared/api-types`, regénérés avec
`pnpm gen:types`).

```bash
pnpm --filter frontend dev        # développement SSR (http://localhost:3000)
pnpm --filter frontend lint       # eslint
pnpm --filter frontend typecheck  # vue-tsc
pnpm --filter frontend build      # build SSR → dist/ssr (node index.js)
```

## Variables de build

Figées par Vite au moment du build (`frontend/.env`, `docker compose` ou
`deploy.yml`, voir `DEPLOYMENT.md` § Storefront) :

| Variable                                                         | Rôle                                                                    |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `VITE_API_URL`                                                   | URL de l'API sans `/api/v1` (le client l'ajoute)                        |
| `VITE_PUBLIC_SITE_URL`                                           | Origine publique : liens canoniques, Open Graph, JSON-LD, `sitemap.xml` |
| `VITE_OAUTH_ENABLED`                                             | `true` affiche les boutons Google / Microsoft                           |
| `VITE_SENTRY_DSN`, `VITE_SENTRY_ENVIRONMENT`, `VITE_APP_RELEASE` | Sentry navigateur (vide = désactivé)                                    |

## Organisation

- `src/pages/` — une page par route (`src/router/routes.ts`) ; chaque page
  déclare son titre et ses balises avec `useMeta` ou le composable
  `usePageMeta` (canonical, Open Graph, `noindex` sur les pages privées).
- `src/components/` — composants de la vitrine ; `src/components/account/`
  les sections de « Mon compte ».
- `src/stores/` — Pinia : `auth` (jeton en mémoire, cookie de rafraîchissement
  HttpOnly), `cart` (panier local reflété sur le serveur, panier invité fusionné
  à la connexion), `products`, `currency`, `shopModules` (`GET /system/config`).
- `src/api/` — appels à l'API, un module par domaine, typés par
  `@app/api-types`.
- `src/i18n/` — `fr.ts` et `en.ts` ; toute chaîne visible passe par `$t`.
- `src/composables/` — `useLocale`, `useTranslate`, `useTurnstile` (captcha
  des formulaires publics), `usePageMeta`.
- `src-ssr/` — serveur Express : `middlewares/seo.ts` sert `robots.txt` et
  `sitemap.xml`, `render.ts` rend les pages.

## Conventions

- Les textes et libellés sont dans `src/i18n/`, jamais en dur dans les
  composants.
- Les éléments des parcours testés portent un `data-testid` (voir
  `e2e/README.md`) : un libellé peut changer, pas l'identifiant.
- Le rendu serveur est anonyme : rien de spécifique à un utilisateur ne doit
  être lu pendant `onServerPrefetch`.
