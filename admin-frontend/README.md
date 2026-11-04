# Back-office (admin-frontend)

Application Quasar (Vue 3, TypeScript) du back-office. Socle partagé avec la
vitrine : jetons `--n-*`, thème clair / sombre, icônes Phosphor, `AppNotice` et
`StatusTag` (`shared/ui`), formats (`shared/utils`), types de l'API
(`shared/api-types`, regénérés avec `pnpm gen:types`).

```bash
pnpm --filter admin dev        # développement (http://localhost:3001)
pnpm --filter admin lint       # eslint
pnpm --filter admin typecheck  # vue-tsc
pnpm --filter admin build      # build SPA
```

Sans Python : `make dev-front` démarre Postgres, Redis et l'API depuis l'image
publiée (`ghcr.io/natimai-solutions/natimai-ecommerce/api:main`), puis
`pnpm dev:admin` sert l'application sur le port libre suivant (9001 quand la
vitrine tourne déjà sur 9000). Détail des trois
configurations possibles : [`CONTRIBUTING.md`](../CONTRIBUTING.md).

## Charte des écrans (R9 / T8)

Les règles communes à la vitrine (couleurs, thème, points de rupture, formats,
états) sont dans [`docs/GUIDE_INTERFACE.md`](../docs/GUIDE_INTERFACE.md).

Courte, pour que les 37 écrans se lisent de la même façon. Quand un cas n'est
pas prévu ici, copier l'écran le plus proche plutôt qu'inventer.

### Structure d'un écran

- `PageHeader` : titre, aide (`#hint`), actions à droite (`#actions`).
- Actions d'en-tête, de gauche à droite : **Actualiser** (`flat`,
  `ph:arrow-clockwise`), les actions secondaires (`outline`), puis l'action
  de création (`color="primary" unelevated`, `ph:plus`, « Nouveau … »). Toujours
  `no-caps`.
- Les messages de l'écran (`AppNotice`) vont dans `.admin-notices`, sous
  l'en-tête : `error` pour un échec, `success` pour une confirmation,
  `info` pour un contexte, `warning` pour un état à surveiller. Un message
  d'erreur dit ce qui a échoué, pas un code.
- Les listes sont des `q-table` `flat bordered` ; la colonne d'actions est à
  droite, sans titre, avec des boutons `flat round dense` et une `q-tooltip`.

### Icônes d'action (Phosphor)

| Action               | Icône                           | Forme                                                           |
| -------------------- | ------------------------------- | --------------------------------------------------------------- |
| Modifier             | `ph:pencil-simple`              | bouton rond, tooltip « Modifier »                               |
| Supprimer            | `ph:trash`                      | bouton rond `color="negative"`, **toujours** une confirmation   |
| Activer / désactiver | `ph:eye` / `ph:eye-slash`       | bouton rond ; désactiver en `negative`                          |
| Actualiser           | `ph:arrow-clockwise`            | en-tête, `flat`                                                 |
| Créer                | `ph:plus`                       | en-tête, `primary unelevated`                                   |
| Fermer un dialogue   | `ph:x`                          | bouton rond en tête du dialogue (dialogues maximisés seulement) |
| Monter / descendre   | `ph:arrow-up` / `ph:arrow-down` | ordre manuel                                                    |
| Fusionner            | `ph:git-merge`                  |                                                                 |
| Télécharger          | `ph:download-simple`            |                                                                 |

Les statuts ne sont jamais une couleur Quasar brute (`color="green"`) :
`StatusTag` avec un `tone` (`ok`, `warn`, `danger`, `neutral`).

### Suppressions et confirmations

- Toute suppression côté serveur passe par `useConfirm().confirmDelete(nom)` :
  même titre (« Supprimer « … » ? »), même avertissement, Annuler à gauche,
  **Supprimer** en rouge à droite. Retirer une ligne d'un formulaire non
  enregistré ne demande rien.
- Une action lourde mais réversible (vider des identifiants, livrer un lot)
  passe par `useConfirm().ask({ title, okLabel })`.
- Après l'action : `notice` de succès et rechargement de la liste.

### Dialogues

- `q-card.app-dialog` (ou `app-dialog--xl`, `maximized` pour les éditeurs),
  `app-dialog__head` avec un `h2.app-dialog__title`, corps dans une
  `q-card-section`, actions dans `q-card-actions.app-dialog__actions`
  **alignées à droite** : **Annuler** (`flat`) puis l'action principale
  (`color="primary" unelevated`, « Enregistrer » ou « Créer »), avec
  `:loading` pendant l'enregistrement. Une action destructrice optionnelle
  (Supprimer) se place à gauche, séparée par `q-space`.
- Le formulaire est un `q-form @submit.prevent` : le bouton principal est
  `type="submit"`, les règles vont sur les champs (`:rules`).
- Modifications non enregistrées : `useFormSnapshot` + `useDialogGuard`
  (dialogue persistant tant qu'il est modifié, confirmation à la fermeture),
  `useUnsavedGuard` pour un écran qui enregistre sans dialogue.
- Champs traduisibles : `ContentLanguageTabs` + `useContentTranslations`
  au-dessus des champs ; les règles de saisie ne s'appliquent qu'à la langue
  source.

### Formulaires

- Champs `outlined dense`, `bottom-slots` quand ils ont une aide ou une
  règle ; sous-titres de section en `h3.admin-subtitle` ; lignes en colonnes
  avec `row q-col-gutter-sm` et `col-*`.
- Les montants s'affichent avec `formatMoney(montant, devise)` ; les champs
  numériques en `inputmode="decimal"`, l'unité en `suffix`.
- Les libellés viennent de `i18n/fr.ts` et `i18n/en.ts` (mêmes clés, clés
  triées par bloc) ; jamais d'entité HTML dans un message.

### Sélecteurs de test

`data-testid` en kebab-case préfixé par l'écran (`homepage-delete`,
`product-cancel`, `currency-add`) ; les tests e2e ne ciblent pas un libellé
quand un test id existe.
