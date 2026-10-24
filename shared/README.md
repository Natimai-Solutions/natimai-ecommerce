# Paquets partagés (shared/)

Quatre paquets TypeScript privés du workspace pnpm (`workspace:*`), consommés
par la vitrine et l'admin. Ils ne sont pas publiés sur npm : les deux fronts
vivent dans ce dépôt et c'est ce qui permet de changer une route de l'API, ses
types et l'écran qui l'utilise dans une seule PR.

| Paquet | Rôle | Généré ? |
|---|---|---|
| `@app/api-types` | Types de l'API, produits depuis le schéma OpenAPI du backend | **Oui** : `pnpm gen:types`, jamais édité à la main |
| `@app/api-client` | Client axios : URL de base (`VITE_API_URL` + `/api/v1`), jeton en mémoire, rafraîchissement par cookie | non |
| `@app/ui` | Socle visuel « Précision » : jetons `--n-*`, thème clair / sombre, icônes Phosphor, `AppNotice`, `StatusTag` | non |
| `@app/utils` | Monnaie, dates au fuseau de la boutique (`todayLocal`, `dayBounds`, `formatDate`…), i18n partagée | non |

```bash
pnpm gen:types        # regénère api-types depuis le backend (uv sync fait)
pnpm check:types      # échoue si le fichier commité a dérivé (comme la CI)
pnpm test             # vitest : tests unitaires de shared/* (et des fronts)
pnpm test:coverage    # couverture de @app/utils (badge « Frontend coverage »)
```

`shared/api-types/src/schema.ts` est **commité** : un contributeur front n'a
pas besoin de Python pour avoir les types à jour, et la CI (`api-types`)
vérifie qu'il correspond toujours à l'application.

## Et si quelqu'un veut un autre frontend ?

Le jour où un front hors de ce dépôt doit consommer l'API, `@app/api-types`
(et sans doute `@app/api-client`) deviennent des paquets publiés et versionnés
(`@natimai/api-types`), et l'API gagne une politique de version. Rien n'y
oblige avant : voir « Why one repository » dans
[`CONTRIBUTING.md`](../CONTRIBUTING.md).
