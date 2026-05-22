# Plan Frontend — Architecture monorepo

Document décrivant la structure des applications frontend et du code partagé pour le projet `fastapi-ecommerce`.

---

## Vue d'ensemble

Deux applications Vue.js / Quasar distinctes, partageant un ensemble de packages internes via **pnpm workspaces** :

| Application | Rôle | Cible | Mode de rendu |
|-------------|------|-------|---------------|
| `frontend/` | Vitrine e-commerce publique (storefront) | Clients finaux (particuliers, pros) | Quasar SSR (SEO, perf mobile Polynésie) |
| `admin-frontend/` | Back-office d'administration | Équipe interne, gestionnaires | SPA Quasar classique |
| `shared/*` | Code commun (types, client API, utils métier) | Consommé par les deux apps | Source TS exportée directement (pas de build) |

### Pourquoi deux apps séparées

- **Profils de bundle différents** : la vitrine doit être légère (LCP mobile, connexions hors Tahiti parfois lentes), l'admin peut être lourd (tables, formulaires complexes).
- **Exigences SEO** : seule la vitrine a besoin de SSR / indexation Google.
- **Surface de sécurité** : l'admin est isolé sur un sous-domaine (`admin.*`) avec règles CORS et auth strictes.
- **Cycles de déploiement** : les itérations admin et vitrine peuvent évoluer indépendamment.

---

## Arborescence

```
fastapi-ecommerce/
├── pnpm-workspace.yaml
├── package.json                    # racine, scripts globaux
├── tsconfig.base.json              # config TS partagée
├── backend/                        # FastAPI (inchangé)
├── frontend/                       # Quasar SSR — storefront public
│   ├── package.json
│   ├── quasar.config.ts
│   └── src/
├── admin-frontend/                 # Quasar SPA — back-office
│   ├── package.json
│   ├── quasar.config.ts
│   └── src/
└── shared/
    ├── api-types/                  # types TS générés depuis OpenAPI
    │   ├── package.json
    │   └── src/
    │       ├── schema.ts           # généré par openapi-typescript
    │       └── index.ts            # réexports utiles
    ├── api-client/                 # client HTTP typé (fetch wrapper)
    │   ├── package.json
    │   └── src/
    │       ├── client.ts
    │       └── index.ts
    └── utils/                      # logique métier réutilisable
        ├── package.json
        └── src/
            ├── pricing.ts          # calcul prix par groupe utilisateur
            ├── currency.ts         # format XPF
            ├── date.ts
            ├── i18n/               # traductions FR/EN partagées
            └── index.ts
```

---

## Configuration racine

### `pnpm-workspace.yaml`

```yaml
packages:
  - "frontend"
  - "admin-frontend"
  - "shared/*"
```

### `package.json` (racine)

```json
{
  "name": "fastapi-ecommerce",
  "private": true,
  "packageManager": "pnpm@9.0.0",
  "scripts": {
    "gen:types": "openapi-typescript http://localhost:8000/openapi.json -o shared/api-types/src/schema.ts",
    "dev:front": "pnpm --filter frontend dev",
    "dev:admin": "pnpm --filter admin-frontend dev",
    "build:front": "pnpm --filter frontend build",
    "build:admin": "pnpm --filter admin-frontend build",
    "typecheck": "pnpm -r typecheck"
  },
  "devDependencies": {
    "openapi-typescript": "^7.0.0",
    "typescript": "^5.5.0"
  }
}
```

### `tsconfig.base.json` (racine)

Config TS partagée, étendue par chaque app et package :

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "paths": {
      "@app/api-types": ["./shared/api-types/src/index.ts"],
      "@app/api-client": ["./shared/api-client/src/index.ts"],
      "@app/utils": ["./shared/utils/src/index.ts"]
    }
  }
}
```

---

## Packages partagés

### `shared/api-types` — types générés depuis OpenAPI

**Objectif** : garantir que les types TS du front collent exactement aux schémas Pydantic du backend, sans rédaction manuelle.

**Génération** : `pnpm gen:types` exécute `openapi-typescript` sur `http://localhost:8000/openapi.json` et produit `schema.ts`. À lancer après toute modification de schéma backend.

**`shared/api-types/package.json`** :
```json
{
  "name": "@app/api-types",
  "version": "0.0.0",
  "private": true,
  "type": "module",
  "main": "./src/index.ts",
  "types": "./src/index.ts"
}
```

**Usage** :
```ts
import type { components } from '@app/api-types'

type Product = components['schemas']['ProductRead']
type OrderLine = components['schemas']['OrderLineRead']
```

### `shared/api-client` — client HTTP typé

**Objectif** : un wrapper fetch (ou axios) qui consomme `@app/api-types` pour offrir une API typée bout en bout, avec gestion centralisée de l'auth, des erreurs, et de la base URL.

**Responsabilités** :
- Attache le token JWT depuis le store local de chaque app
- Gère le refresh token
- Normalise les erreurs (codes d'erreur backend → exceptions typées côté front)
- Sérialise les décimaux et dates correctement (cf. fix récent sur les Decimal côté backend)

**Usage** :
```ts
import { createApiClient } from '@app/api-client'

const api = createApiClient({ baseUrl: import.meta.env.VITE_API_URL })
const products = await api.products.list({ category: 'laptops' })
```

### `shared/utils` — logique métier

**Contient toute logique métier qui doit être identique entre les deux apps** :

- **`pricing.ts`** : calcul du prix de vente selon le groupe utilisateur, en miroir de la formule backend
  ```
  sale_price = cost × (1 + customs_rate_pct/100) × (1 + margin_rate_pct/100) × (1 + tax_rate.rate_pct/100)
  ```
  Permet d'afficher des prix en temps réel côté admin (preview marge) et côté vitrine (recalcul si groupe change).
- **`currency.ts`** : format XPF (Franc Pacifique, sans décimales, séparateur d'espaces : `12 500 F`)
- **`date.ts`** : formats Polynésie (`DD/MM/YYYY`, timezone `Pacific/Tahiti`)
- **`i18n/`** : libellés communs FR/EN (boutons, messages d'erreur, statuts de commande)

**Règle** : ce qui touche au calcul de prix et au format monétaire **doit** vivre ici, jamais dupliqué dans une app.

---

## Configuration des apps

### `frontend/package.json` (extrait)

```json
{
  "name": "frontend",
  "private": true,
  "scripts": {
    "dev": "quasar dev -m ssr",
    "build": "quasar build -m ssr",
    "typecheck": "vue-tsc --noEmit"
  },
  "dependencies": {
    "@app/api-types": "workspace:*",
    "@app/api-client": "workspace:*",
    "@app/utils": "workspace:*",
    "quasar": "^2.16.0",
    "vue": "^3.4.0",
    "pinia": "^2.1.0"
  }
}
```

### `admin-frontend/package.json` (extrait)

```json
{
  "name": "admin-frontend",
  "private": true,
  "scripts": {
    "dev": "quasar dev",
    "build": "quasar build",
    "typecheck": "vue-tsc --noEmit"
  },
  "dependencies": {
    "@app/api-types": "workspace:*",
    "@app/api-client": "workspace:*",
    "@app/utils": "workspace:*",
    "quasar": "^2.16.0",
    "vue": "^3.4.0",
    "pinia": "^2.1.0"
  }
}
```

---

## Conventions

### Pas de build pour les packages internes

Les packages `shared/*` exportent directement leur source TS (`"main": "./src/index.ts"`). Vite / Quasar transpile à la volée. Aucun watcher, aucun build intermédiaire. Si un package doit un jour être publié en externe, on rajoutera `tsup` à ce moment-là.

### Génération des types

`pnpm gen:types` doit être lancé :
- Après toute modification de schéma Pydantic côté backend
- Dans le pipeline CI avant les jobs `typecheck`
- Idéalement dans un hook `pre-commit` côté backend

### Pas de `shared/ui` au démarrage

On **n'extrait pas** de composants UI partagés tant qu'on n'a pas dupliqué le même composant deux fois entre les apps. La sur-abstraction prématurée est plus coûteuse que la duplication ponctuelle. Quand un besoin réel émerge, on crée `shared/ui` avec des composants Quasar enrobés.

### i18n

- Les libellés métier transverses (statuts de commande, codes d'erreur, unités) vivent dans `shared/utils/i18n`.
- Les libellés spécifiques à chaque app (textes vitrine marketing, libellés UI admin) restent dans l'app concernée.

---

## Phasage frontend

En alignement avec [PLAN_DEPLOIEMENT_PAR_PHASE.md](backend/docs/development/PLAN_DEPLOIEMENT_PAR_PHASE.md) :

1. **Phase 0 / 1** : setup monorepo + `shared/api-types` + `shared/utils` (pricing, XPF) + démarrage `frontend/` (vitrine catalogue + panier + checkout).
2. **Phase 2 / 3** : `shared/api-client` consolidé + démarrage `admin-frontend/` (gestion produits, commandes, utilisateurs).
3. **Phase 4 / 5** : extraction éventuelle de `shared/ui` si duplication avérée, i18n complet EN.

---

## Déploiement

| App | Domaine cible | Mode |
|-----|---------------|------|
| `frontend` | `www.example.pf` | SSR Node (ou pré-rendu statique selon volume catalogue) |
| `admin-frontend` | `admin.example.pf` | SPA statique servie par Nginx, derrière auth |

CORS backend configuré pour autoriser les deux origines distinctement.
