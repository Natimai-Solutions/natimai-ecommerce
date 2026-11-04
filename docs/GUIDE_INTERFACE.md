# Guide d'interface

> Les choix durables de l'interface, vitrine et admin. Court, pour être lu.
> La compétence `design-taste-frontend` (`.claude/skills/`, copie figée de
> [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill), la même que
> natimai-paie) donne la direction esthétique ; ce guide dit ce qui, chez nous,
> prime sur elle. La charte des écrans de l'admin (en-tête, icônes d'action,
> dialogues, confirmations) est dans [`admin-frontend/README.md`](../admin-frontend/README.md).

## Ce qui prime sur tout

1. **Thème clair et sombre automatiques** (`Dark` en `auto`, choix mémorisé :
   cookie sur la vitrine, lu par le rendu serveur ; localStorage dans l'admin ;
   logique commune dans `shared/ui/src/theme.ts`). Toute couleur passe par une
   variable `--n-*` (`shared/ui/src/css/tokens.scss`), redéfinie en sombre.
   Jamais de couleur en dur dans un composant (une valeur de repli dans
   `var(--n-danger, …)` exceptée), ni `bg-white`, ni `bg-<teinte>-<n>`, ni de
   ternaire `$q.dark.isActive` pour choisir une couleur (il ne sert qu'à
   l'icône et au libellé du bouton de thème).
2. **Composants Quasar** avant tout composant maison ; un composant maison
   existe pour une règle métier (`MarginPreviewPanel`, `WeightBandsEditor`),
   pas pour un style.
3. **Deux langues** : tout texte vient de `src/i18n/fr.ts` et `en.ts` (mêmes
   clés, triées par bloc). Pas de chaîne dans un template.
4. **Vitrine sobre, admin dense** : la vitrine montre le produit, le prix et
   le délai, rien qui ne serve pas l'achat ; l'admin est un outil de gestion
   (tableaux denses, formulaires longs acceptés, une aide repliable par écran).

## Palette, forme et typographie

- « Précision » : neutres zinc, l'encre comme couleur principale
  (`$primary` #18181b), un seul accent, orange signal (`--n-accent`, #c2410c en
  clair, #f2742f en sombre) pour le focus, le badge panier et les filtres actifs.
  Les couleurs d'état (`--n-ok`, `--n-warn`, `--n-danger`) ne portent qu'une
  information réelle : un stock, un statut, une erreur.
- Variables Sass de Quasar : une seule source,
  `shared/ui/src/css/quasar.variables.scss` ; le fichier de chaque application
  ne fait que l'importer.
- Rayons : `--n-radius` (8 px : cartes, champs, boutons), `--n-radius-sm`,
  `--n-radius-lg`, `--n-radius-pill`. Espacements : l'échelle de Quasar
  (`q-pa-md`, `q-gutter-sm`…) et, en CSS, `--n-space-xs` à `--n-space-xl`
  (4, 8, 16, 24, 48 px). Une valeur hors échelle se justifie en commentaire.
- Geist Variable pour le texte, Geist Mono (`font-mono`) pour les références,
  quantités et montants alignés. Une seule `h1` par page.
- Icônes : Phosphor seulement, par le préfixe `ph:` (`icon="ph:trash"`) ; les
  noms Material encore présents sont traduits par `shared/ui/src/icons.ts`.

## Mise en page

- **Points de rupture de Quasar seulement** : 600, 1024 et 1440 px
  (`max-width: 599px` téléphone, `1023px` tablette, `1439px` petit portable).
  Les classes `lt-md`, `gt-sm`… et `$q.screen` suivent la même échelle.
- Quand la place dépend du menu latéral de l'admin (248 px, affiché dès
  1024 px), une requête de conteneur (`@container`) remplace le point de
  rupture : la mise en page suit la largeur disponible, pas celle de l'écran
  (détail de commande, navigation des paramètres).
- Classes communes (`shared/ui/src/css/components.scss`) : `app-section`,
  `app-panel`, `app-rows`, `app-kv`, `app-form`, `app-dialog`, `app-empty`,
  `app-result`, `text-link`, `prose`. Une nouvelle page les reprend avant
  d'écrire son propre style.
- État d'écran qui se partage (vue, catégorie, filtre) : dans l'URL
  (`?view=zones`, `?category=legal`), il survit au rechargement.

## Formats

- Montants : `formatMoney(montant, devise)` de `@app/utils` (décimales de la
  devise, espace insécable, suffixe) ; jamais de formateur local.
- Dates : `formatDate`, `formatDateTime`, `todayLocal`, `toShopDateTimeInput`
  de `@app/utils`, toujours dans le fuseau de la boutique, jamais celui du
  navigateur ni UTC.
- Erreurs d'API : `extractApiError(err) ?? t('…')` dans l'admin,
  `apiErrorMessage(err, …)` sur la vitrine : le message du serveur, sinon une
  phrase qui dit ce qui a échoué. Jamais un code brut.

## États

- **Chargement** : squelette (`q-skeleton`) à la place du contenu ; spinner
  réservé aux actions (`:loading` sur le bouton). Jamais de spinner plein écran.
- **Vide** : `app-empty`, une phrase, une action si elle existe.
- **Erreur, succès, contexte** : `AppNotice` (`error`, `success`, `info`,
  `warning`) sous l'en-tête ; pas de modale pour une réussite.
- **Statut** : `StatusTag` avec un `tone` (`ok`, `warn`, `danger`,
  `neutral`), jamais une couleur Quasar brute (`color="green"`).

## Formulaires et accessibilité

- Chaque champ a un libellé : `label` (flottant) en formulaire ; dans une
  cellule de tableau, `aria-label` formé de la colonne et de la ligne
  (« Acompte (%) — Professionnels ») ; une recherche, `aria-label` repris du
  placeholder. Un placeholder n'est jamais un libellé.
- Bouton icône seule : `aria-label` et une `q-tooltip`.
- Saisie non enregistrée : `useFormSnapshot` + `useDialogGuard` pour un
  dialogue, `useUnsavedGuard` pour un écran (`src/composables/useUnsavedGuard.ts`).
- Dialogue : il tient sur un téléphone (`app-dialog`, 520 px au plus, jamais
  plus large que l'écran moins 32 px).
- Éléments manipulés par un test de bout en bout : `data-testid` en
  kebab-case, préfixé par l'écran.

## Garde-fou

`shared/ui/src/design-guard.test.ts` (Vitest, `pnpm test`) parcourt les deux
applications et `shared/ui` et refuse, fichier et ligne à l'appui :

- une couleur Material (`bg-grey-2`, `text-green-7`, `color="orange"`, `'teal'`
  renvoyé par une fonction) : un ton `StatusTag` ou une couleur de marque ;
- `bg-white`, `bg-black`, une couleur choisie selon `$q.dark.isActive` ;
- une couleur en dur (`#hex`, `rgb()`) ou un `!important` hors des fichiers de
  jetons (`tokens.scss`, `quasar.variables.scss`) ;
- un point de rupture hors de l'échelle Quasar.

Les seuls `!important` restants sont dans `tokens.scss` : les utilitaires
sémantiques (`text-muted`…, comme ceux de Quasar), le texte d'un bouton sur fond
de marque en sombre (Quasar pose `text-white` en `!important`) et le mouvement
réduit. Pour battre un style Quasar ailleurs : une classe de plus
(`.q-card__section.app-dialog__head`) ou la variable qu'il lit
(`--q-negative`), jamais `!important`.
