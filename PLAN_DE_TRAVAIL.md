# Plan de déploiement par paliers

Document de travail établi à partir de la vérification fonctionnelle. Chaque phase est conçue pour être déployable en production de façon autonome, le frontend pouvant s'enrichir au même rythme.

---

## Convention — périmètre monorepo & suivi par surface

Ce plan couvre **tout le monorepo**, pas seulement le backend. Trois surfaces sont livrées par phase :

| Surface | Package | Rôle |
|---------|---------|------|
| **Backend** | `backend/` (FastAPI) | API, modèles, migrations, tâches |
| **Vitrine** | `frontend/` (Quasar/Vue) | site public client |
| **Admin** | `admin-frontend/` (Quasar/Vue) | back-office (édition catalogues, taux, commandes…) |
| *(transverse)* | `shared/*` | utils partagés (`pricing.ts`…) |

**Règle** : une phase = une tranche verticale déployable. Chaque phase porte donc (1) une **« Matrice livrables par surface »** — 1 ligne par feature, colonnes Backend / Vitrine / Admin — et (2) au besoin des sous-sections détaillées **Travaux backend**, **Travaux vitrine**, **Travaux admin**.

**Légende statut** : ✅ livré · ⏳ partiel / à confirmer · 🔲 non démarré · — non concerné.

> ⚠️ **État au 08/06/2026 (audit des fronts)** : le **backend est nettement en avance**. La **vitrine** couvre catalogue / fiche / panier / checkout / retour paiement. L'**`admin-frontend` ne contient à ce jour que `LoginPage` + `ProductsPage`** — tous les écrans d'administration livrés côté API (taux TVA, devises, catalogue specs, demandes de groupe, éligibilité paiement, commandes fournisseurs, system-settings, consolidation, remboursement) **restent à construire**. Les matrices par phase rendent ce backlog explicite.

> 🔍 **État au 25/08/2026 (audit de production complet — sécurité, tests/CI, infra, complétude)** : Phases 0–4 **vérifiées livrées** conformes au plan (le code est même en avance : desserte par île, stock/inventaire, devis invité). Le reste à faire avant mise en production est consolidé dans la section **« Chantier pré-production — audit du 25/08/2026 »** (bloquants sécurité S1-S4, légal L1-L3, facturation, exploitation I1-I8, qualité Q1-Q4, fonctionnel F). La fiscalité douanière fine (TDL, positions tarifaires, défauts `customs_rate_pct`) est traitée dans la décision transverse **fret import & assiette douane (CAF)**, sous-section *Vérification implémentation & écarts fiscalité*.

> 🧭 **État au 30/09/2026 (revue complète : dépôt, documents, refonte graphique, questions du propriétaire)** : `main` vert, aucune PR ouverte, aucun gros chantier fonctionnel ouvert. **Priorité 1 : la refonte graphique « Précision » (vitrine, puis admin) et une vraie page d'accueil** — la refonte, livrée en quatre lots le 29/09, n'était documentée nulle part. L'ordre de travail, les décisions du propriétaire et le backlog chiffré sont dans la section **« Feuille de route au 30/09/2026 »** ci-dessous ; les lignes périmées des phases (matrices, backlog admin, dettes) ont été corrigées le même jour.

---

## Feuille de route au 30/09/2026 — revue complète, priorités et backlog chiffré

Section issue de la revue du 30/09/2026 (état du dépôt, documents de travail, refonte graphique, et réponses aux questions du propriétaire). Elle **prime sur les matrices des phases** pour l'ordre de travail ; les lignes périmées des phases ont été corrigées le même jour et renvoient ici. Estimations en jours (j) pour une personne qui connaît la base.

**État du dépôt** : `main` vert en CI (run 136), aucune PR ouverte, dernier commit `45dd837` (sqlmodel 0.0.47, datetimes UTC). Aucun gros chantier fonctionnel n'est ouvert dans le plan : ce qui reste est (1) la refonte graphique, (2) des valeurs à saisir et des validations externes, (3) l'exploitation avant production, (4) le backlog ci-dessous.

### Ordre de travail décidé par le propriétaire (30/09/2026)

| Priorité | Chantier | Effort | Section |
|---|---|---|---|
| **1** ✅ | **Refonte « Précision » — vitrine** : accueil, espace client, checkout, paiement, devis, pages légales — **livrée le 30/09/2026** | 8 à 12 j | R1 |
| **1 bis** ✅ | **Page d'accueil + médias publics** (blocs pilotés par l'admin, téléversement d'images) — **livrée le 30/09/2026** | 5 à 7 j | R2 |
| **2** ✅ | Refonte « Précision » — **admin-frontend** (lot séparé, après la vitrine) — **livrée le 30/09/2026** | 8 à 12 j | R1-admin |
| **3** ✅ | Paiements : espèces, versements partiels (`payment_receipts`), acompte pour tous les moyens, PSP activables en base, **PayPal** — **livrée le 30/09/2026** ; **Stripe (P6) reporté** à la demande du propriétaire | 14 à 18 j | R3 |
| 4 | Fournisseurs : seuil de quantité à l'import fichier, **mappage catégories fournisseur → boutique** (fichier et Ingram), mode simple avec Ingram / Icecat désactivés par défaut et réactivables, **modules activables en base**, rattachement immédiat d'un article manuel, flux fichier automatisé (Foxway, Picata) avec identifiants chiffrés | 15 à 20 j | R4 |
| 5 | Configuration en base (version complète) | 12 à 16 j | R5 |
| 6 | Bloquants production (sécurité, sauvegardes, images, sandbox PayZen, juridique, comptable) | 5 à 8 j + validations externes | R6 |
| 7 | Version publique : multilingue FR + EN et devises (périmètre minimal) | 20 à 30 j | R7 |
| 8 | Ajouts à forte valeur et confort | à arbitrer | R8 |

### Décisions du propriétaire (30/09/2026)

| Question | Décision |
|---|---|
| Périmètre de la refonte « toutes les pages » | **Vitrine d'abord, puis l'admin** en lot séparé |
| Images de la page d'accueil | **Blocs pilotés par l'admin + téléversement d'images** (service de médias publics réutilisable pour produits et catégories) |
| Identifiants des fournisseurs sans API | **Chiffrés en base** (Fernet, clé dans l'environnement, écriture seule). Exception assumée à la règle « jamais d'identifiants en base » (décision du 05/09), limitée aux fournisseurs `file_feed` |
| Prestataire de paiement | **Stripe et PayPal**, chacun **activable / désactivable en base**, PayZen compris |
| Espèces | **Proposées dans tous les cas** (pas seulement au retrait) : localement, des clients n'ont pas de carte ; ils commandent puis passent au bureau régler ou verser un acompte |
| Acompte | **Doit pouvoir être défini pour tous les moyens de paiement**, manuels compris |
| Versements partiels | **Table `payment_receipts`** (un reçu par versement) |
| Multilingue / devises | **Périmètre minimal FR + EN**, contenu monolingue par déploiement, devise pivot configurable avec conversion d'affichage |
| Configuration en base | **Version complète** (registre typé, cache, ~45 réglages, crons en ticks, écran admin par catégorie) |
| Catégories à l'import (demande du propriétaire : sélection des catégories d'un fichier + mappage boutique ↔ fournisseur) | **Mappage par fournisseur** valable pour le fichier **et** Ingram (table `supplier_category_mappings`), qui remplace la liste blanche globale ; sélection à l'import via le tableau des catégories du fichier (S5) |
| Mode simple | **Ingram et Icecat désactivés par défaut**, réactivables depuis l'admin **sans redémarrage** ; l'état réel vit en base, `SHOP_MODE` ne pilote plus que les défauts et l'affichage (S6) |
| Masquer davantage en mode simple (import CSV, etc.), réactivable au besoin | **Modules activables en base** (S7) : `SHOP_MODE` devient un préréglage appliqué au premier démarrage, un écran « Modules » active / désactive chaque fonction sans redémarrage, les deux fronts lisent la liste dans `GET /system/config` |
| Article manuel rattaché ensuite à un fournisseur API ou fichier | **Déjà possible** (adoption à l'import / sync, cf. *Reconnaissance des articles à l'import*) ; à compléter par « Rattacher maintenant » et « Détacher » (S8), et le bloc « Approvisionnement » suit le module Fournisseurs |

---

### R1 — Refonte graphique « Précision » (priorité 1)

La refonte n'était documentée nulle part ; elle existe dans l'historique git sous quatre commits du 29/09/2026, tous limités à `frontend/` : `28625e9` (lot 1, fondations), `74c4451` (lot 2, en-tête / catalogue), `49a10e6` (lot 3, fiche produit), `f11835a` (lot 4, panier, et « Checkout, Mon compte, Suivi : titres et gouttières **sans recomposition** »). Support de conception : les skills « Taste » de `.agents/skills` (ajoutés le 28/09, `skills-lock.json`).

**Fondations livrées (lot 1)** : palette zinc, encre `#18181b`, accent orange `#C2410C`, mode sombre persistant en cookie (SSR), polices Geist / Geist Mono auto-hébergées, icônes Phosphor via `iconMapFn`, rayon 8 px, focus visible, `AppNotice` (remplace 35 `q-banner`), `StatusTag`. Jetons : [quasar.variables.scss](frontend/src/css/quasar.variables.scss), variables `--n-*` dans [app.scss](frontend/src/css/app.scss) (dont une règle transitoire qui ramène `.text-grey-*` sur l'échelle zinc — « les pages passent progressivement aux classes sémantiques »).

**État par page (mesuré : `var(--n-*)` vs classes Quasar héritées)**

| Page | État | Reste |
|---|---|---|
| `MainLayout.vue`, `CataloguePage.vue`, `ProductPage.vue`, `CartPage.vue`, composants (`ProductCard`, `CartDrawer`, `ProductImage`, `ProductOffers`, `NextDepartureBanner`), `ErrorNotFound.vue` | ✅ refondus | — |
| `LoginPage`, `RegisterPage`, `ForgotPasswordPage`, `ResetPasswordPage` | ⏳ partiel (classes `.auth-*`, 1 à 6 couleurs héritées) | finir |
| **`MyAccountPage.vue`** (1 532 lignes), **`OrderTrackingPage.vue`**, **`BalancePaymentPage.vue`** | 🔲 non recomposés (0 variable, 7 à 8 couleurs héritées) | lot R1-B |
| **`CheckoutPage.vue`** (1 058 lignes), `PaymentReturnPage.vue`, `OAuthCallbackPage.vue`, `CartQuoteConfirmationPage.vue` | 🔲 non recomposés | lot R1-C |
| `pages/legal/*` (CGV, confidentialité, mentions) | 🔲 volontairement non touchées au lot 4 | lot R1-D |
| `IndexPage.vue` | 🔲 placeholder de 14 lignes, **non routé** (`/` redirige vers le catalogue) | R2 |
| `admin-frontend` (31 pages, thème Quasar par défaut, 102 `q-banner`) | ✅ refondu le 30/09/2026 (socle partagé `shared/ui`, coquille, tableau de bord, 31 pages) | R1-admin |

**Lots vitrine**

- **R1-A — Accueil** (avec R2) : route `/` → `IndexPage.vue` (aujourd'hui `redirect` dans [routes.ts](frontend/src/router/routes.ts)), logo de l'en-tête pointant dessus, hero + blocs admin + « coups de cœur » (`GET /product/featured`) + « les plus consultés » (`GET /product/popular`) — `getFeaturedProducts` / `getPopularProducts` existent dans [products.ts](frontend/src/api/products.ts) et ne sont appelés nulle part —, tuiles catégories avec `Category.image_url` (déjà éditable dans l'admin, jamais affiché en vitrine), `useMeta` + `og:image`. La page d'accueil écrite au commit `99935bf` puis abandonnée à la fusion `8ead9e0` sert de point de départ.
- **R1-B — Espace client** (`MyAccountPage`, `OrderTrackingPage`, `BalancePaymentPage`) : recomposition (navigation latérale ou onglets refondus, résumé en tête, `StatusTag` partout, suppression des `text-grey-*` et des `color="green|orange|…"`), **et** corrections fonctionnelles relevées :
  - titre du suivi = `order_number` (`CMD-…`) et non l'UUID tronqué ([OrderTrackingPage.vue](frontend/src/pages/OrderTrackingPage.vue) l.6) ;
  - statut `PaymentReview` absent de `PAYMENT_BADGE` / `ORDER_STATUS_LABELS` ([MyAccountPage.vue](frontend/src/pages/MyAccountPage.vue) l.1418-1467) → affiché brut en anglais ;
  - texte « une adresse doit être validée par notre équipe avant de pouvoir être utilisée au paiement » (l.168) **faux** depuis la décision du 02/07 (validation indicative) ;
  - préférence « Langue : English » sans effet (i18n vide, cf. R7) : masquer ou brancher ;
  - options « Écologique / Le plus écologique » proposées sans offre documentée ;
  - `getMyOrder` recharge **toute la liste** pour trouver une commande ([orders.ts](frontend/src/api/orders.ts) l.89-92) ;
  - liste des commandes **sans pagination ni filtre** ; détail sans adresse de livraison, ni moyen de paiement, ni lien / image produit, ni facture téléchargeable depuis le suivi ;
  - **pas d'onglet Profil** (nom, e-mail, téléphone, changement de mot de passe connecté, suppression de compte RGPD) : le backend n'a **aucun endpoint `/users/me`** (seulement préférences, adresses, commandes, factures, devis, avoir, alertes, upgrade, wishlist) → ajout backend `GET/PATCH /users/me` + `POST /users/me/password` + export / suppression (cf. R8) ;
  - l'en-tête n'affiche pas le nom du client ;
  - wishlist (`/user_wishlist/me`), avis et notifications internes existent au backend, pas en vitrine → exposer la wishlist dans ce lot, avis et notifications en R8 ;
  - e2e : aucun test de l'espace client alors que des `data-testid` sont posés (`account-*`, `order-*`, `balance-*`) → un spec Playwright « compte » (connexion, liste, suivi, facture PDF, solde).
- **R1-C — Checkout et paiement** (`CheckoutPage`, `PaymentReturnPage`, `CartQuoteConfirmationPage`, `OAuthCallbackPage`) : recomposition en étapes lisibles, récapitulatif collant, `formatMoney(amount, currency)` à la place de `formatXpf` (cf. R7), et la correction du **bug de capture différée** : `Authorized` n'est pas terminal pour la page de retour ([payments.py](backend/app/api/routes/payments.py) l.87-89, [PaymentReturnPage.vue](frontend/src/pages/PaymentReturnPage.vue) l.139) → timeout après 2 min dès que `PAYZEN_MANUAL_VALIDATION=True`.
- **R1-D — Pages légales et divers** : CGV / confidentialité / mentions en `DbContentPage` (contenu en base, cf. A-pages) plutôt qu'en `.vue` codé en dur (l.686) ; reliquats de gabarit Quasar à supprimer (`stores/example-store.ts`, `i18n/en-US`, `test.html` à la racine) ; `<html lang>` manquant dans `index.html`.

**✅ Livré le 30/09/2026 (R1-A à R1-D, commits `2be3a00` et `8896f34`)**

- **Accueil (R1-A)** : `/` affiche `IndexPage.vue` (route `home`) au lieu de rediriger vers le catalogue ; accroche, tuiles catégories (`Category.image_url`, actives et non fusionnées, illustrées d'abord ; rangée défilante sur mobile), « Nos coups de cœur » et « Les plus consultés ». Données dans le store `home` (transmis du rendu serveur au navigateur). Grille produits et squelettes rendus globaux (`app.scss`).
- **Espace client (R1-B)** : `MyAccountPage.vue` devient une coquille (navigation latérale, onglets défilants sur mobile) et huit composants `components/account/*` : vue d'ensemble (« À faire » : solde demandé, paiement attendu ; dernières commandes ; raccourcis), commandes paginées (« Voir plus », facture et avoirs par commande, avoir client), devis, **favoris et alertes** (liste de favoris enfin exposée + bouton « Ajouter aux favoris » sur la fiche produit), adresses, **profil et sécurité** (nom, téléphone, e-mail en lecture seule, changement de mot de passe), préférences, groupe tarifaire. `?tab=` reste la clé d'URL. Backend : `GET/PATCH /users/me`, `POST /users/me/password` (mot de passe actuel exigé, limité en fréquence, **toutes les sessions révoquées**), `GET /orders/me/{id}` (avec `payment_method_name`), lignes de commande avec `image_url`, `manufacturer`, `product_available`. Suivi de commande recomposé (titre `CMD-…`, articles illustrés et liés, récapitulatif latéral, paiement, adresse, facture téléchargeable, étapes d'acheminement, rechargement quand l'id change). Corrections : `PaymentReview` et statuts inconnus jamais affichés bruts (`utils/orderStatus.ts`), texte « adresse à valider » retiré, langue masquée, options « écologiques » gardées seulement si déjà choisies, `getMyOrder` ne recharge plus toute la liste. e2e `customer-account.spec.ts`.
- **Checkout et paiement (R1-C)** : étapes numérotées (adresse, livraison, règlement, paiement) avec le composant commun `ChoiceList`, récapitulatif collant, confirmation pleine largeur, libellé « Payer X » seulement pour la carte ; page de solde, retour de paiement, confirmation de devis et retour OAuth sur la même grammaire (`.app-result`). **Bug de capture différée corrigé** : `Authorized` est terminal pour le polling (`payments.py`) et affiché comme un succès. Montants « qui font foi » via `orderMoney(montant, devise de la commande)` au lieu de `formatXpf`.
- **Divers (R1-D)** : typographie de lecture `.prose` ; mentions légales et confidentialité éditables comme les CGV (`DbContentPage`, texte actuel en repli) ; pages d'authentification (icônes Phosphor, message après changement de mot de passe) ; `<html lang="fr">` ; suppression de `stores/example-store.ts` et `test.html`. Socle : `utils/errors.ts` (extraction d'erreur unique), `utils/money.ts`, `utils/categories.ts`, classes `app-*` partagées ; le test d'icônes vérifie aussi les noms `ph:` directs.
- **Restes R1 vitrine** : nom du client dans l'en-tête (non fait) ; export et suppression de compte RGPD (R8) ; décalage d'hydratation de `QPage` (`min-height` calculé 100 px côté serveur, 50 px côté client) **antérieur à la refonte**, présent aussi sur le catalogue ; `quasar dev -m ssr` crée `frontend/src-ssr/pnpm-lock.yaml` et `pnpm-workspace.yaml` (à ignorer dans `.gitignore` ou à comprendre) ; l'i18n (dossier `i18n/`) est gardée pour R7.

**R1-admin — admin-frontend (priorité 2, après la vitrine)** : même socle (jetons `--n-*`, sombre/clair, Phosphor, `AppNotice` / `StatusTag` partagés via `shared/`), `AdminLayout` + tableau de bord (aujourd'hui 7 lignes sans KPI, cf. R8), puis les 37 pages par familles (catalogue, commandes, paiements, logistique, système). Estimation 8 à 12 j. À documenter dans le *Chantier admin-frontend*.

**✅ R1-admin livré le 30/09/2026**
- **Socle partagé `shared/ui` (`@app/ui`)** : jetons clair / sombre et base (`css/tokens.scss`), grammaire des écrans d'application (`css/components.scss` : `app-section`, `app-panel`, `app-kv`, `app-empty`, `app-dialog`, `prose`…), correspondance Material → Phosphor (`icons.ts`, fabrique `createPhosphorIconMapFn`), `AppNotice`, `StatusTag`, `toneOf` / `toneIcon`. La vitrine l'importe désormais (fichiers déplacés, pas copiés). Alias `@app/ui` dans Vite, TypeScript et vitest ; `vue` et `quasar` dédupliqués (les SFC de `shared/` se résolvent depuis l'app) ; styles des composants partagés en CSS simple (Quasar injecte ses variables Sass dans chaque bloc SCSS, introuvables depuis `shared/`). Le test d'icônes couvre les deux apps et le jeu interne de Quasar (éditeur, tableaux, dates).
- **Coquille** : polices Geist et Phosphor (Roboto et Material Icons retirés du build), thème Système / Clair / Sombre mémorisé dans le navigateur, barre latérale regroupée (Ventes, Catalogue, Logistique, Clients, Tarifs et paiement, Site et système ; mode simple signalé), menu de compte (`GET /users/me`), `PageHeader` (titre, aide, retour, actions), connexion et 404 refaites, fichiers du gabarit Quasar supprimés.
- **Tableau de bord** (`/`, auparavant une redirection vers les produits) : « À traiter » (commandes payées à préparer, paiements à valider, devis ouverts, demandes de groupe, commandes fournisseurs non envoyées, produits en brouillon — les deux derniers masqués en mode simple), activité (commandes du jour et sur 7 jours, CA 7 et 30 jours convertis dans la devise de référence, journée à l'heure de Tahiti), prochain départ groupé. Backend `GET /admin/dashboard` (agrégats uniquement ; le filtre « paiements à valider » est partagé avec l'écran de validation), 4 tests.
- **31 pages** converties par familles : `PageHeader`, `AppNotice` (plus aucun `q-banner`), `StatusTag` pour les états, couleurs Material retirées (filet de sécurité dans `app.scss`), références et montants en chasse fixe, dialogues `app-dialog` (`--wide` 760 px, `--xl` 1080 px), fiche commande en deux colonnes avec son numéro `CMD-…` (`order_number` ajouté à `AdminOrderDetail`).
- **Restes** : KPI avancés (panier moyen, conversion, stocks bas) → R8 ; ~~e2e du parcours admin~~ (✅ 30/09/2026 : 7 tests Playwright dans `e2e/tests/admin/`, lancés en CI avec l'admin, le worker ARQ et le poller) ; quelques tableaux larges défilent horizontalement (fournisseurs, paramètres) ; couleurs Quasar encore passées en JS (`$q.dialog` de livraison, `q-timeline` en `primary`) ; interrupteurs « actif » gardés en vert.

### R2 — Page d'accueil et médias publics (priorité 1 bis)

**Constat** : aucun téléversement d'image n'existe dans l'admin. Produits (`image_url`, `supplier_image_url`), catégories (`Category.image_url`) et rappels de départ sont des **URL**. Le stockage de fichiers ([attachment/storage](backend/app/features/attachment/storage/)) est **privé** : URL signées 300 s, `Content-Disposition: attachment`, MIME codé en dur pour les pièces de paiement, pas de Pillow, pas de route `/media`. L'éditeur de pages (`PagesPage.vue`) n'a pas de bouton image. Décision du propriétaire : **blocs admin + téléversement**.

| # | Livrable | Backend | Vitrine | Admin | Effort |
|---|---|---|---|---|---|
| H1 | **Service de médias publics** | table `media_assets` (clé, MIME, dimensions, variantes, auteur), `POST /admin/media` multipart (modèle [suppliers.py](backend/app/api/routes/suppliers.py) l.469) : liste blanche jpeg/png/webp, taille max 5 Mo, **Pillow** (ré-encodage webp, EXIF retiré, 2-3 tailles), scan ClamAV, clé `media/{kind}/{uuid}.webp` ; **route publique `GET /media/{key}`** (`Content-Type` réel, `Cache-Control: public, immutable`) sur le volume partagé `storage_data` (2 réplicas API) ou bucket S3 public derrière CDN ; `DELETE` si plus référencé | — | sélecteur d'images réutilisable (`MediaPicker.vue`) | 3 à 4 j |
| H2 | **Blocs d'accueil** | table `homepage_blocks` (kind `hero` / `banner` / `tile`, `media_id` ou `image_url`, `alt`, `title`, `subtitle`, `cta_label`, `cta_link`, `position`, `is_active`, `starts_at` / `ends_at`), `GET /homepage` public (SSR-friendly, filtré par dates), CRUD admin sur le modèle `content_pages` / `crud_content_page` | `IndexPage.vue` (R1-A) avec `<img>` natif, `width`/`height` ou `aspect-ratio`, `srcset`, `loading="eager"` + `fetchpriority="high"` pour le hero ; `onServerPrefetch` + `onMounted` comme `DbContentPage.vue` | écran « Accueil » avec aperçu, ordre, dates | 1,5 à 2 j |
| H3 | **Réutilisation** : image produit et catégorie via `MediaPicker` (les URL restent acceptées), bouton image dans l'éditeur de pages | résolution `media_id` → URL dans `CategoryPublic` / `ProductPublic` | — | `ProductFormDialog`, `CategoriesPage`, `PagesPage` | 1 j |

**✅ Livré le 30/09/2026** :
- **H1 médias publics** : table `media_assets` (migration `a7m3e9d1h5b2`), service `features/media/service.py` : plafond de taille (`MEDIA_MAX_UPLOAD_BYTES`, 8 Mo), scan antivirus, décodage Pillow limité à JPEG / PNG / WebP avec plafond de 40 Mpx, orientation EXIF appliquée puis **toutes les métadonnées supprimées** par le ré-encodage, variantes WebP 480 / 960 / 1600 px (jamais agrandies), original non conservé. Routes : `POST/GET/PATCH/DELETE /admin/media` (suppression refusée en 409 tant qu'un bloc d'accueil, un produit, une catégorie ou une page l'utilise) et **`GET /media/{id}/{largeur}.webp` public** (`Cache-Control: public, max-age=31536000, immutable`, seules les clés enregistrées sont servies). URL absolues construites depuis `MEDIA_PUBLIC_BASE_URL` (origine publique de l'API, **à renseigner en production**). Pillow déclaré dans `pyproject.toml` (déjà présent via WeasyPrint).
- **H2 blocs d'accueil** : table `homepage_blocks` (`hero` / `banner`, titre, texte, bouton, lien — chemin du site ou `https://` seulement —, image de la médiathèque ou URL externe, ordre, publication, fenêtre de dates) ; `GET /homepage` public (premier hero publié + bannières dans leur fenêtre) ; CRUD `/admin/homepage-blocks`. Vitrine : hero avec image (`srcset`, `fetchpriority="high"`) sinon texte par défaut, bannières en 1 / 2 / 3 colonnes. Admin : écran **« Accueil du site »** (Système), statuts Brouillon / Programmé / En ligne / Expiré, ordre par flèches, dates.
- **H3 réutilisation** : composant admin `MediaPicker` (envoi, filtre par usage, sélection, suppression) branché sur l'image produit (`ProductFormDialog`), l'image de catégorie (tuile d'accueil) et l'éditeur de pages (bouton « Image » qui insère `<img srcset>`).
- Tests : 9 unitaires (formats, EXIF, largeurs, transparence, bombe de pixels) et 7 d'intégration (envoi → service → accueil → suppression bloquée puis permise).
- **Restes R2** : le type de bloc `tile` n'a pas été créé (les tuiles catégories le couvrent) ; les images passent par l'API — derrière un CDN ou un bucket S3 public si le trafic le demande ; pas de recadrage dans l'admin (l'image est affichée en `object-fit: cover`).

Contraintes : SSR (`frontend/public` est servi avec `maxAge` 30 j, donc noms versionnés pour tout statique), CSP à construire le jour où elle existe (aucune aujourd'hui), le composant `ProductImage.vue` (`mix-blend-mode: multiply`, `padding: 10 %`) ne convient pas à une photo de bannière → composant dédié.

### R3 — Paiements : espèces, versements partiels, acompte généralisé, PSP (priorité 3) — ✅ livré le 30/09/2026, sauf Stripe (P6, reporté)

**Livré (30/09/2026)**
- ✅ **P1 Espèces** : `ManualCashProvider` (`manual_cash`), seed « Espèces », instructions de règlement **en base** (`payment_instructions_<code>` dans `system_settings`, seedées, surchargent le texte du fournisseur) et envoyées dans l'e-mail de commande avec le montant dû maintenant.
- ✅ **P2 Versements partiels** : table `payment_receipts`, `POST /admin/payments/{id}/receipts`, annulation d'un reçu (« chèque impayé »), `POST /admin/orders/{id}/payments` (encaissement au comptoir sans intention préalable), `amount_paid` / `amount_due` / historique sur la fiche commande (admin) et `amount_paid` / `amount_due` côté client, statut de commande `PartiallyPaid`, e-mail « Versement reçu, reste X », dialogue d'encaissement (montant pré-rempli au reste, date, mode, référence) ; « remboursée » jugé sur le net encaissé de **toute la commande** (`fully_refunded` au niveau commande, `payment_fully_refunded` au niveau paiement).
- ✅ **P3 Acompte pour tous les moyens** : `payment_methods.deposit_allowed` (défaut vrai, interrupteur dans « Règles de paiement »), refus `payment.method.deposit_not_allowed`, filtrage au checkout ; acompte en espèces puis solde par virement au comptoir couvert par un test d'intégration.
- ✅ **P4 Chantier commun PSP** : `ProviderOutcome` normalisé (`completed` / `authorized` / `failed` / `refunded`, montant, devise, `event_id`, `transaction_id`) ; `parse_webhook(raw_body, headers)` asynchrone et `confirm_payment` sur `ApiPaymentProvider` ; pipeline générique ([webhook_pipeline.py](backend/app/features/payment/services/webhook_pipeline.py)) : déduplication par `event_id` (table `payment_webhook_events`), aucun passage d'un statut terminal à un autre, contrôle du montant (y compris montant converti via `charged_amount_minor` / `charged_currency`), `provider_data` enrichi **sans écraser `payment.amount`**, outbox identique à PayZen ; `POST /payments/webhooks/{code}` ne répond plus 501 pour un fournisseur qui le gère ; `POST /payments/me/{id}/confirm` (idempotent, réservé au client) ; `capture_reference` / `refund_reference` par fournisseur (plus de `trans_uuid` codé en dur) ; `redirect_url` branché dans `CheckoutPage` et `BalancePaymentPage`, page de retour : confirmation serveur, état « Paiement annulé » ; **`cancelOrRefund` PayZen branché** derrière `PAYZEN_API_REFUND_ENABLED` (faux par défaut, à valider en sandbox).
- ✅ **P5 Activation en base** : interrupteur par fournisseur `payment_provider_<code>_enabled` dans `system_settings` (PayZen actif, PayPal et Stripe inactifs par défaut) ; un fournisseur n'est proposé que s'il est activé, implémenté **et** que ses identifiants sont présents ; moyens masqués au checkout, initiation refusée (`payment.provider.disabled`), notifications des paiements en cours toujours traitées ; section « Prestataires de paiement » dans l'admin (`GET/PUT /admin/payment-providers`).
- ✅ **P7 PayPal** ([paypal.py](backend/app/features/payment/providers/paypal.py)) : Orders API v2 par redirection (`payer-action`), `intent` `CAPTURE` ou `AUTHORIZE` (`PAYPAL_INTENT`), capture / autorisation serveur au retour, `authorization_id` / `capture_id` en `provider_data`, webhook vérifié par `verify-webhook-signature` (`PAYPAL_WEBHOOK_ID` obligatoire), capture différée depuis l'admin, remboursements par l'API ; **XPF facturé en EUR** à la parité fixe 1 000 XPF = 8,38 € (montant débité enregistré et contrôlé, remboursements convertis) ; clé d'idempotence `PayPal-Request-Id` ; moyen « PayPal » seedé, masqué tant que PayPal est inactif. Tests : API PayPal simulée (`httpx.MockTransport`), [test_paypal_payments.py](backend/app/tests/integration/test_paypal_payments.py) ; e2e : interrupteur admin, retour annulé.

- ✅ **Moyens de paiement éditables depuis l'admin** (30/09/2026, suite de R3) : les *types* restent dans le code (carte, PayPal, espèces, chèque, virement, bon de commande) ; les *moyens* se créent sur un type, se renomment, se décrivent, prennent des frais, un plafond, un ordre, s'activent et se suppriment s'ils n'ont servi à aucun paiement (sinon on les désactive) — dialogue sur « Moyens de paiement », routes `GET/POST /admin/payment-methods`, `PATCH/DELETE /admin/payment-methods/{id}`, `GET /admin/payment-methods/types`. **Instructions par moyen** (`payment_methods.instructions`) : priorité moyen → type (Paramètres système) → texte par défaut du fournisseur ; deux virements vers deux banques envoient chacun leur IBAN. Correctif : le plugin `Dialog` de Quasar n'était pas activé dans l'admin (la confirmation « Livrer le lot » des expéditions ne s'ouvrait pas).

**Écarts assumés**
- `PartiallyPaid` n'est **pas** ajouté à `DEPARTURE_FOLLOWER_STATUSES` : une commande partiellement payée ne suit pas le départ tant qu'elle n'est pas payée (ou acompte payé).
- L'IPN PayZen garde sa route historique (`payzen_ipn`) : il n'est pas migré sur le pipeline générique (comportement éprouvé, tests existants) ; seuls les nouveaux fournisseurs l'utilisent.
- Non faits du P4 : `render_mode` / `client_secret` (utiles à Stripe Elements, reportés avec P6), flag de capture différée générique (PayZen garde `PAYZEN_MANUAL_VALIDATION`, PayPal a `PAYPAL_INTENT`), transition de remboursement `pending → completed` par webhook, CSP, `PaymentMethod.currencies`.
- PayPal : si le client approuve mais ne revient jamais sur la boutique, la commande PayPal reste non capturée (l'événement `CHECKOUT.ORDER.APPROVED` n'est pas exploité) ; à revoir si le cas se présente.
- **À valider** : PayPal en sandbox (identifiants + webhook déclarés), PayZen `CancelOrRefund` en sandbox, et la question comptable « facture en XPF, encaissement en EUR » pour PayPal.

**Plan initial**

**Existant** : moyens de paiement en table `payment_methods` reliés par `provider_code` à une classe Python ([providers/__init__.py](backend/app/features/payment/providers/__init__.py) : `payzen`, `manual_check`, `manual_transfer`, `po_public`) ; plusieurs paiements par commande, `Payment.kind ∈ full | deposit | balance`, couverture d'une part par plusieurs paiements (`part_coverage`, `PARTIAL`) introduite par l'avoir-crédit ; validation admin qui encaisse **tout** le montant, sans champ montant ni date ([manual_payment.py](backend/app/features/payment/services/manual_payment.py) l.131-184) ; un encaissement plus court bascule la commande en `PaymentReview`. Aucun IBAN nulle part (instructions codées en dur dans [manual.py](backend/app/features/payment/providers/manual.py), jamais envoyées par e-mail).

| # | Livrable | Détail | Effort |
|---|---|---|---|
| P1 | **Espèces** | `ManualCashProvider(_ManualProviderBase)`, code `manual_cash` (le préfixe `manual_` est testé par `approve_manual_payment` l.140 et `list_pending_validation`), enregistrement dans `SUPPORTED_PROVIDERS`, seed « Espèces » (`requires_admin_validation=True`), libellés dans `PaymentValidationsPage.vue` l.258 et `OrderDetailPage.vue` l.699, tests copiés de `test_manual_payment_providers.py`. **Proposé dans tous les cas** (décision) ; `max_amount` disponible pour plafonner. Instructions « règlement au bureau » + IBAN / coordonnées en base (cf. R5) envoyés dans l'e-mail de commande | 0,5 à 1 j |
| P2 | **Versements partiels — `payment_receipts`** | table `payment_receipts` (`payment_id`, `amount`, `received_at`, `reference` (n° de chèque), `method` (espèces / chèque / virement), `recorded_by_id`, `note`) ; `POST /admin/payments/{id}/receipts` ; le paiement passe `Completed` quand Σ reçus ≥ montant (sinon reste `AwaitingValidation`, la part est `PARTIAL` : ni facture, ni BC, ni `PaymentReview`) ; `POST /admin/orders/{id}/payments` pour enregistrer un encaissement au comptoir **sans intention préalable du client** ; `AdminOrderDetail` expose `amount_paid` / `amount_due` (calculés via `settled_by_kind`) ; statut de commande `PartiallyPaid` (à ajouter à `PAYMENT_STATUSES` et `DEPARTURE_FOLLOWER_STATUSES`) ; e-mail « Versement reçu, reste X » au lieu de « Paiement validé » tant que `PARTIAL` ([handlers/order.py](backend/app/handlers/order.py) l.305) ; `fully_refunded` jugé sur le net encaissé de la commande ([refund_service.py](backend/app/features/payment/services/refund_service.py) l.133, [handlers/payment.py](backend/app/handlers/payment.py) l.433) ; action « chèque impayé » qui annule un reçu ; UI admin : dialogue d'approbation avec montant (pré-rempli au reste) + date + référence, bloc « Encaissé / Reste dû » et historique des reçus sur `OrderDetailPage.vue` | 3 à 4 j |
| P3 | **Acompte pour tous les moyens de paiement** | vérifier et garantir que le sélecteur « Payer intégralement / Verser un acompte » du checkout et `POST /payments/orders/{id}/balance` fonctionnent avec **chaque** moyen (CB, chèque, virement, espèces, BC), y compris un acompte en espèces au bureau (P2) et un solde réglé par un autre moyen que l'acompte ; `PaymentMethod.deposit_allowed` (bool, défaut vrai) pour exclure un moyen au besoin ; facture d'acompte : option (a) maintenue, **à valider par le comptable** | 1 j |
| P4 | **Chantier commun PSP** (prérequis Stripe / PayPal, corrige aussi PayZen) | contrat `parse_webhook_notification` **asynchrone** sur `(raw_body, headers)` ; `WebhookResult.payment_status` normalisé (`completed` / `authorized` / `failed` / `refunded`) + `amount_minor`, `transaction_id`, `event_id` ; `InitiationResult.client_secret` + `render_mode` (`embedded_payzen` / `stripe_elements` / `redirect`) ; clé d'idempotence ; pipeline webhook générique extrait de `payzen_ipn` (déduplication par `event_id`, état terminal contradictoire, contrôle du montant, outbox) appelé par `POST /payments/webhooks/{provider_code}` — aujourd'hui **501** pour tout fournisseur autre que PayZen ([payments.py](backend/app/api/routes/payments.py) l.1101) ; correspondance des statuts déplacée dans le fournisseur (dupliquée aujourd'hui l.59-64 / l.201-221 et [crud/payment.py](backend/app/features/payment/crud/payment.py) l.221-232, qui **écrase `payment.amount`**) ; `capture_service` sur une référence fournie par le fournisseur (plus `trans_uuid`) ; flag de capture différée par fournisseur (plus `PAYZEN_MANUAL_VALIDATION`) ; transition remboursement `pending → completed / failed` par webhook ; front : `redirect_url` branché (`window.location.assign`) dans `CheckoutPage` et `BalancePaymentPage`, loader par fournisseur, clé localStorage renommée, `Authorized` = succès sur la page de retour (bug R1-C) ; CSP avec domaines PayZen / Stripe / PayPal ; `PaymentMethod.currencies` (éligibilité par devise, l.1400) ; brancher `cancelOrRefund` PayZen (l.1385) | 2 à 3 j |
| P5 | **Activation en base** (décision) | l'activation par moyen existe déjà (`payment_methods.is_active` / `is_admin_active`, CRUD superadmin) ; ajouter un **interrupteur par fournisseur** dans le registre de configuration (R5) : `payment_provider.{payzen,stripe,paypal}.enabled` ; `get_provider` refuse un fournisseur désactivé, `list_payment_methods` masque les moyens dont le fournisseur est éteint, l'admin affiche « fournisseur désactivé » et « identifiants présents / absents » ; PayZen désactivable comme les autres | 0,5 j |
| P6 | **Stripe** (Payment Intents + webhook signé sur corps brut, `capture_method` manuel / automatique, `POST /v1/refunds`, mode redirection Checkout recommandé, Stripe Elements en option) | valable pour un déploiement **FR / EUR** seulement (Stripe n'accepte pas de marchand établi en PF, l.1945) ; XPF est « zero-decimal » chez Stripe, cohérent avec [money.py](backend/app/utils/money.py) ; `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` en env ; tests calqués sur `test_payment_providers.py`, `test_payzen_signature.py`, `api/test_payzen_ipn_*.py` (adapter `test_only_payzen_supports_in_app_refund` et le test du 501) | 3 à 4 j |
| P7 | **PayPal** (Orders API v2, `intent=CAPTURE\|AUTHORIZE`, étape serveur `POST /payments/{id}/confirm` après approbation — modèle absent aujourd'hui —, `authorization_id` / `capture_id` en `provider_data`, webhook vérifié par `verify-webhook-signature`, boutons SDK ou redirection `approve`) | **XPF non supporté** → facturation en EUR (parité fixe 1 000 XPF = 8,38 €) ou USD : taux et montant EUR en `provider_data`, contrôle de montant adapté, remboursement partiel converti, question comptable (facture XPF / encaissement EUR) ; montants décimaux PayPal jamais passés à `parse_minor_units` ; durée d'autorisation 3 j honorée / 29 j | 5 à 7 j |

Total R3 : 14 à 18 j (P1-P5 : 7 à 9 j ; P6 + P7 : 8 à 11 j). Dépendance : P5 sur R5 (registre) — en attendant, un `Literal` env par fournisseur suffit.

### Prix, marge, TVA et prix par groupe (demandes du 30/09/2026) — ✅ livré le 30/09/2026

- ✅ **Coût d'achat saisissable en « Prix TTC fixé »** (il était masqué) ; le prix fixé reste libre et n'est jamais recalculé ni écrasé par une synchro.
- ✅ **Marge en direct dans le formulaire article** : prix TTC, TVA, prix HT, commission de paiement, coût de revient HT, marge HT, taux de marque (marge / prix HT) et taux de marge (marge / coût), calculés par le serveur (`POST /admin/products/margin-preview`, même formule que le catalogue) ; alerte « vendu à perte ».
- ✅ **Liste des produits** : colonnes Prix TTC, Coût HT, Marge HT (+ taux de marque), tri par marge, taux de marque, prix ou coût (`products.unit_cost_cached` / `margin_cached` / `margin_pct_cached`, matérialisés avec `sale_price_cached`). Coût de revient = coût converti (sans le coussin de change), + assurance et douane en mode import.
- ✅ **Marge des commandes** : `order_lines.unit_cost_snapshot` figé au checkout ; le détail de commande admin donne par ligne HT, coût et marge, et la marge brute des articles (lignes sans coût signalées). Les lignes antérieures utilisent le coût converti (sans douane).
- ✅ **TVA librement paramétrable** : les taux se créent dans l'admin (code, libellé, %, territoire, dates) ; le **taux par défaut** et le **taux des frais** se choisissent aussi dans l'admin (`GET/PUT /admin/tax-settings`, `system_settings` `tax_default_code` / `tax_fees_code`), l'environnement n'est plus qu'un point de départ — une boutique hors Polynésie définit son propre jeu de taux sans redéploiement.
- ✅ **Polynésie** : taux renommés TVA (codes `TVA_NORMALE` / `TVA_REDUITE` / `TVA_EXONEREE`, migration des `TGC_*` ; les anciens codes d'environnement restent compris) et **taux intermédiaire 13 %** ajouté. ⚠️ Barème à confirmer par le comptable.
- ✅ **TVA par catégorie** dans l'écran Catégories (colonne + sélecteur).
- ✅ **Vitrine** : « TTC » affiché à côté des prix (fiche, cartes) et sur les totaux (panier, tiroir, checkout).
- ✅ **Confidentialité (faille corrigée)** : les API publiques renvoyaient le coût d'achat, le prix fournisseur et les taux de marge / douane des articles, et le coût des lignes à leur client ; ces champs ne sont plus sérialisés que pour une requête de super-administrateur.
- ✅ Correctif : le contexte de prix gardait des lignes `TaxRate` de l'ORM, expirées après un commit (MissingGreenlet dans les écritures en série).
- ✅ **Prix par groupe de clients** (décision du 30/09/2026 : remise en % sur le prix de référence) : le prix de référence est celui du groupe par défaut (Particulier) ; chaque autre groupe paie ce prix moins sa **remise** (`price_groups.discount_pct`, page admin « Groupes tarifaires »), sur tous les articles — Ingram, CSV, coût + marge ou prix fixé ; un **prix TTC saisi pour un groupe sur un article** (`product_group_prices`, grille « Prix par groupe » du formulaire article, avec la marge de chaque groupe) passe avant. Le client connecté voit et paie son prix partout (liste, fiche, recherche, variantes, offres, modes de transport, panier, commande) ; visiteur = prix de référence ; recherche et tri restent sur la référence. Auparavant le groupe du client ne changeait **aucun** prix (tout était calculé avec le groupe par défaut) ; la marge mémorisée sur la ligne de commande est désormais celle du prix de référence. Le groupe par défaut ne peut pas avoir de remise ; sa marge (repli des prix calculés) se règle sur la même page.
- ✅ **Promotions datées — décision du 30/09/2026 : « le meilleur prix gagne »** (principe Magento / Adobe Commerce). Une promotion (page admin « Promotions » : un article ou une catégorie, un % ou un montant, dates de début et de fin) baisse le prix de référence pour tous les clients ; **elle ne se cumule pas** avec la remise ou le prix saisi d'un groupe : chaque client paie le **plus bas** des deux. La vitrine affiche le prix habituel du client barré, le pourcentage obtenu et la date de fin (liste, fiche, modes de transport), le panier et la commande facturent le meilleur prix. Les promotions reposent sur les remises de type « promotion » (déjà dans le modèle, jamais appliquées jusque-là). Codes promo : option « s'applique aussi aux articles en promotion » (`discounts.applies_to_promoted`, vraie par défaut) ; décochée, les articles concernés par une promotion en cours sont exclus du code.

#### Politique de prix — autres possibilités, non retenues pour l'instant
À implémenter un jour si le besoin se présente (aucune n'est engagée) :
1. **Cumul promotion + remise de groupe**, réglable par promotion (« cumulable avec les remises de groupe ») : la promotion s'applique alors sur le prix du groupe (−10 % Pro puis −20 % = −28 %).
2. **Promotions réservées à certains groupes** (ex. soldes Particulier uniquement, promo « Administration » en fin d'exercice), ou exclusion de certains groupes.
3. **Priorités et arrêt des règles** (Magento « discard subsequent rules », PrestaShop priorités) : plusieurs promotions ordonnées, la première qui s'applique arrête les suivantes, au lieu du « meilleur prix ».
4. **Prix promo fixe** (« 9 900 F au lieu de… ») en plus du % et du montant, et **prix spécifiques par groupe datés** (PrestaShop « prix spécifiques » avec dates, par groupe / client / pays).
5. **Prix dégressifs par quantité** (Magento « tier price », PrestaShop « à partir de N unités »), éventuellement par groupe.
6. **Prix par client** (un client donné, contrats négociés) en plus des groupes.
7. **Promotions « panier »** automatiques sans code : X achetés = Y offert, lot / bundle, livraison offerte dès un montant, remise dès un montant de panier (« cart rules » PrestaShop / Magento).
8. **Promotion sur tout le catalogue** ou sur un fabricant / une marque, et exclusions d'articles d'une promotion de catégorie.
9. **Quota de promotion** (N premières unités, stock dédié) et affichage d'un compte à rebours.
10. **Prix barré de référence réglementaire** (en métropole : prix le plus bas des 30 derniers jours, directive Omnibus) à partir du journal des prix existant.
11. **Recherche et tri sur le prix du client** (aujourd'hui sur le prix de référence) : prix matérialisés par groupe ou calcul à la volée.
12. **Arrondi commercial** des prix remisés et promotionnels (à 10 / 100 F, prix psychologiques en …90).

- 🔲 Reste : arrondi commercial des prix calculés (à 10 / 100 F) ; prix par groupe saisissables sur les variantes (elles suivent la remise du groupe) ; un prix saisi pour un groupe vaut pour tous les modes de transport d'un article importé.

### R4 — Fournisseurs (priorité 4)

**Réponses de la revue** :
- **Désactiver Ingram** : bouton « Désactiver » dans Admin → Fournisseurs (`DELETE /admin/suppliers/ingram_micro` → `is_active=False`, `sync_enabled=False`) **et** vider `INGRAM_CLIENT_ID / SECRET / CUSTOMER_NUMBER` : les valeurs `changeme-…` du `.env.example` comptent comme « configuré » (`credentials_present()`, [ingram_micro.py](backend/app/services/suppliers/ingram_micro.py) l.567-576). Les articles déjà synchronisés gardent une `supplier_quantity` figée **vendable** ([availability.py](backend/app/features/inventory/services/availability.py) l.35-51) : à désactiver ou remettre à zéro.
- **Désactiver Icecat** : `ICECAT_ENABLED=false` **et** identifiants vides ; l'enrichissement enfilé après un import ne teste pas le flag ([supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py) l.679-700, [icecat_tasks.py](backend/app/tasks/icecat_tasks.py) l.246-419). Un article synchronisé reste masqué tant qu'il n'est pas enrichi sauf `published_without_enrichment` (case cochée par défaut à l'import fichier ; `POST /admin/products/publish` pour les articles API). `SHOP_MODE=simple` n'est **pas** le bon levier aujourd'hui (il masque la page Fournisseurs) — corrigé par **S6**.
- **Ajouter une API fournisseur** : la base est générique (contrat `SupplierAdapter`, registre `ADAPTERS`, orchestrateur, tâches, re-vérification au checkout, écran admin avec `settings_keys`, `FakeAdapter` de test) ; un fournisseur = un fichier de 150 à 400 lignes + enregistrement + secrets en config. Seuls la **commande fournisseur automatique**, `INGRAM_SHIP_TO_*` et le webhook de statut sont câblés Ingram (déjà noté l.492).

| # | Livrable | Détail | Effort |
|---|---|---|---|
| S1 ✅ | **Correctifs désactivation** — *livré le 01/10/2026 : `_enqueue_enrichment`, `enrich_product_with_icecat_task` et `batch_enrich_products_task` testent l'interrupteur Icecat ; le checkout ne consulte plus un fournisseur dont les synchros sont coupées ; `.env.example` à identifiants vides et `secret_is_set()` (une valeur `changeme-…` ne compte plus comme configurée, Ingram et Icecat) ; désactivation d'un fournisseur avec choix du sort des articles (`DELETE …?products=keep\|zero_stock\|hide`, dialogue admin)* | `_enqueue_enrichment` et `batch_enrich_products_task` respectent `ICECAT_ENABLED` ; [checkout_availability.py](backend/app/features/integrations/services/checkout_availability.py) l.90 teste `is_sync_enabled()` / `is_active` en plus de `is_configured()` ; `.env.example` avec identifiants **vides** plutôt que `changeme-…` ; action admin « désactiver les articles d'un fournisseur » | 0,5 à 1 j |
| S2 ✅ | **Quantité minimale à l'import fichier** — *livré le 01/10/2026 : `Supplier.min_quantity` / `min_price` (migration `d9e3f6a8b1c5`), surcharge par import (`min_quantity` / `min_price` en Form, 0 = aucun seuil, transmis à la tâche de fond), ligne nouvelle sous le seuil non créée, article existant mis à jour puis `is_active=False` et **réactivé** quand il repasse au-dessus ; une ligne sans quantité (ou sans prix) n'est pas jugée sur cette valeur ; prix minimal dans la devise du fichier ; la simulation compte `below_threshold`, `filtered`, `deactivated` (filtres et liste blanche évalués) ; champs dans le formulaire fournisseur et le dialogue d'import* | aujourd'hui `SUPPLIER_SYNC_MIN_QUANTITY` / `MIN_PRICE` sont **globaux** et ne s'appliquent qu'à la synchro d'inventaire des fournisseurs API ([supplier_tasks.py](backend/app/tasks/supplier_tasks.py) l.376) ; l'import CSV / Excel les ignore ([file_import.py](backend/app/services/suppliers/file_import.py) `rows_to_products` sans filtre). Ajouter `min_quantity` / `min_price` sur `Supplier` (migration, `SupplierUpdate`, `SupplierConfig.from_row`), surcharge optionnelle dans `POST /import-file` et la tâche de fond, filtrage avant `import_items` (ligne nouvelle sous le seuil → ignorée + compteur ; article existant sous le seuil → quantité mise à jour **et** `is_active=False`), compteur dans la simulation, champ « Quantité minimale » dans le formulaire fournisseur et le dialogue d'import ; décider le cas d'une ligne sans colonne quantité. ⚠️ Piège : `SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST` par défaut = ordinateurs → tout autre article est créé **désactivé** ; mettre `[]` pour un fichier de smartphones (à porter sur la ligne fournisseur en R5) | 1 à 1,5 j |
| S3 | **Flux fichier automatisé** (Foxway, Picata) | adapter générique `services/suppliers/file_feed.py` (`adapter_key="file_feed"`, fournisseurs en `kind=api` pour hériter des ticks et de `sync_interval_hours`), `settings_keys` = `feed_url`, `login_url`, `auth_mode` (aucune / basic / formulaire + cookies), `file_format`, `sheet_name` ; `fetch_catalog` = téléchargement `httpx` avec `request_with_retry`, `read_tabular_file`, `rows_to_products` avec `config.column_mapping`, pages ; **identifiants chiffrés** : colonne `suppliers.credentials_encrypted` (Fernet, dépendance `cryptography` à ajouter, clé `SUPPLIER_SECRETS_KEY` en env), API en écriture seule (`has_credentials`), champs mot de passe dans l'admin, `is_configured()` devient une méthode d'instance ; `supports_live_availability = False` testé par `checkout_availability` (sinon un flux qui renvoie `{}` met le stock à 0) ; seuils S2 appliqués ; sécurité : https obligatoire, IP privées bloquées (SSRF), taille max, statut de dernière récupération + alerte ; limites : portail exigeant JavaScript ou captcha → hors périmètre (Playwright non installé), `.xls` refusé. Vérifier d'abord si Foxway / Picata offrent lien direct, SFTP ou API | 3 à 5 j |
| S4 | **Commande fournisseur généralisée** | méthode optionnelle `create_purchase_order` sur le contrat, `supplier_order_service` et le handler `payment.captured` indépendants du fournisseur, `INGRAM_SHIP_TO_*` remplacé par l'entrepôt principal (`Place`) — reprend le « Reste à faire » fournisseurs | 2 j |
| S5 | **Mappage catégories fournisseur → boutique** (demande du 30/09) | **Rappel de ce qui était prévu** : taxonomie interne livrée le 08/06 (Phase 2, item 10) en option (b) — chaque **sous-catégorie** fournisseur devient une catégorie boutique par `get_or_create_by_name` ([crud/category.py](backend/app/features/product/crud/category.py) l.63-87, appelé par [supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py) l.505-512), fusion / renommage a posteriori (A12, A17). **Aucune table de mappage** ; seul alias implicite : `merged_into_id` (nom identique). Curation par `SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST` **globale, en env, sans UI, appliquée aussi aux fichiers** (hors « Ordinateur de Bureau/Tour » / « Ordinateur Portable » → créé **désactivé**). `Supplier.default_categories` (textarea libre) ne filtre que l'appel au catalogue Ingram. Constats : taxonomie **plate** ; la colonne `category` d'un fichier n'est jamais utilisée si la sous-catégorie est vide (produit sans `category_id`, invisible dans le filtre vitrine) ; `supplier_category` / `supplier_subcategory` limités à **50 caractères** ; Icecat ne touche pas à la catégorie (la projection des specs compare des mots-clés à `supplier_category` brut, pas à `category_id`) ; la simulation d'import n'évalue **pas** les filtres ; **l'admin ne peut pas créer de catégorie** (`CategoriesPage.vue` = liste / patch / fusion) ; `GET /category` public ne filtre ni `is_active` ni `merged_into_id` (à vérifier en vitrine). **Conception** : table `supplier_category_mappings` (`supplier_id`, `source_category`, `source_subcategory`, `source_key` normalisée UNIQUE par fournisseur, `category_id` nullable, `action ∈ import \| draft \| deactivate \| skip`) + `Supplier.unmapped_category_action ∈ auto \| draft \| deactivate \| skip` (`auto` = comportement actuel) ; résolution dans `upsert_product` : règles `skip` globales → `sku_allowlist` → mappage exact (cat\|sous-cat) → mappage catégorie seule → action par défaut ; cible passée par `resolve_merged` ; repli `get_or_create_by_name(subcategory or category)` ; **la liste blanche globale est ignorée pour un fournisseur qui a un mappage** (sinon contradiction) ; `merge_category` met à jour les mappages ; action « **Réappliquer le mappage** » (UPDATE des produits du couple hors verrous + `schedule_price_refresh`) qui permet la « scission de catégorie » recommandée par DEPLOYMENT.md §douane. **Import fichier** : `inspect` et la simulation renvoient les couples distincts (catégorie, sous-catégorie) sur **toutes** les lignes avec compte, mappage existant, catégorie proposée et effet des filtres (`filtered` / `deactivated` dans `preview_items`) ; tableau « Catégories du fichier » dans le dialogue d'import (sélecteur : existante / « Créer X » / brouillon / ignorer), mémorisé comme `column_mapping` ; champ « Catégorie pour tout le fichier » (`default_category_id`, Form + tâche ARQ) pour les fichiers sans colonne. **Ingram** : pas de découverte de taxonomie avant sync → `GET /admin/suppliers/{code}/observed-categories` (GROUP BY `supplier_category`, `supplier_subcategory` avec comptes) + écran « Catégories » par fournisseur ; `default_categories` en puces éditables. Divers : création de catégorie dans `CategoriesPage.vue`, champs bruts élargis à 255 (migration), tests. | 5 à 6,5 j (MVP fichier seul : catégorie unique + tableau des valeurs + mappage mémorisé + filtres en simulation : 2,5 à 3 j) |
| S6 ✅ | **Mode simple : Ingram / Icecat désactivés par défaut, réactivables** — *livré le 01/10/2026 : registre `features/system/modules.py` (interrupteurs `module.<clé>` en base, préréglage `SHOP_MODE` au premier démarrage, cache 15 s invalidé à l'écriture), module `icecat` sous le coupe-circuit `ICECAT_ENABLED`, écran Admin → Modules, `GET /system/config` expose `modules` ; crons fournisseurs et Icecat toujours planifiés ; `ingram_micro` créé inactif en mode simple, et un site simple existant voit sa ligne désactivée **une seule fois** (marqueur `seed.simple_mode_suppliers_switched_off`) ; page Fournisseurs visible en mode simple, bouton « Réactiver »* | (demande du 30/09) | Aujourd'hui `SHOP_MODE=simple` masque le menu ([AdminLayout.vue](admin-frontend/src/layouts/AdminLayout.vue) l.61-72, routes accessibles par URL) et retire les crons **au démarrage du worker** ([arq_worker.py](backend/app/core/arq_worker.py) l.134-137), mais `_seed_suppliers` ([initial_data.py](backend/app/features/initial_data.py) l.882-919) crée quand même `ingram_micro` **active, synchro autorisée**, les routes de sync manuelle restent opérantes, `_enqueue_enrichment` / `batch_enrich_products_task` ignorent `ICECAT_ENABLED`, aucun bouton « Réactiver » (`SuppliersPage.vue` l.133-140, pas de champ `is_active` au formulaire) ni interrupteur Icecat dans l'admin, et repasser en `full` impose un redémarrage. **Cible** : `SHOP_MODE` ne pilote que les **défauts et l'affichage**, l'état réel vit en base : (1) seed de `ingram_micro` en `is_active=False`, `sync_enabled=False` en mode simple, **à la création seulement** ; (2) crons fournisseurs toujours planifiés (`_due_suppliers` est déjà sans effet sans ligne active, configurée et autorisée) → réactivation **sans redémarrage** ; (3) réglage Icecat en base (`integrations.icecat_enabled`, défaut faux en simple, vrai en full, sous `ICECAT_ENABLED`) testé dans `_enqueue_enrichment`, `batch_enrich_products_task`, le cron (planifié en permanence, sans effet) et `icecat.py` — règle S1 ; (4) admin : page Fournisseurs visible en mode simple (au minimum pour l'import CSV, ou sous « Avancé »), bouton **« Réactiver »** (`PATCH is_active / sync_enabled`), interrupteur Icecat dans les Paramètres ; (5) `checkout_availability.py` teste `is_active` / `is_sync_enabled()` (S1). Dépend de R5 pour le réglage en base (en attendant : `system_settings` clé simple). | 1 à 1,5 j (S1 compris) |
| S7 | **Modules activables en base** (demande du 30/09 : masquer davantage en mode simple, réactivable) | Aujourd'hui le mode simple est **binaire** : six entrées de menu codées en dur (`FULL_MODE_ONLY` dans [AdminLayout.vue](admin-frontend/src/layouts/AdminLayout.vue) l.61-72), le bloc « Approvisionnement » de `ProductFormDialog.vue` (l.62-63), les crons au démarrage du worker ; la vitrine ne lit pas le mode. **Cible** : un interrupteur par module dans le registre R5 — `modules.suppliers`, `modules.file_import` (bouton « Importer un catalogue »), `modules.supplier_orders`, `modules.customs`, `modules.currencies`, `modules.specs`, `modules.logistics_multileg`, `modules.grouped_departures`, `modules.quotes`, `modules.price_groups`, `modules.deposits`, `modules.abandoned_carts` (Ingram et Icecat : S6). `SHOP_MODE` devient un **préréglage** appliqué au premier démarrage seulement (`simple` = tout à faux sauf le socle ; `full` = tout à vrai), l'état vit ensuite en base. Écran **« Modules »** (Système) avec description et avertissement quand des données existent (devis en cours, départ ouvert) — jamais de suppression. `GET /system/config` renvoie `modules` ; **admin** : menu, routes (redirection vers l'accueil admin si module éteint), sections de formulaire et boutons ; **vitrine** : bandeau `NextDepartureBanner`, bouton devis, sélecteur d'acompte, onglet « Groupe tarifaire », niveau de service import, « autres offres » si un seul fournisseur. **Backend** : crons inertes (tick + test du module), routes admin du module en 404 explicite, checkout qui ignore l'acompte / le devis si éteint ; réactivation sans redémarrage. Remplace `FULL_MODE_ONLY` et `is_simple_shop` côté fronts (le backend garde `is_simple_shop` pour le seed). | 2 à 3 j après R5 (1 à 1,5 j avec des clés `system_settings` simples en attendant) + 1 j vitrine |
| S8 ✅ | **Rattachement immédiat d'un article manuel à un fournisseur** (question du 30/09) — *livré le 01/10/2026 : `POST /admin/products/{id}/attach-supplier` (API : adoption immédiate coût / devise / stock / mapping, contenu saisi verrouillé, article laissé en vente ; fichier : lien enregistré, adoption au prochain import ; référence inconnue 404, déjà portée par un autre article 409) et `POST …/detach-supplier` (article manuel, mapping supprimé, stock fournisseur à 0, verrous conservés) ; boutons dans le bloc Approvisionnement. Non fait : inclusion des articles manuels rattachés dans la sync d'inventaire (option)* | **Déjà possible, passivement** : bloc « Approvisionnement » (fournisseur + référence) sur un article manuel ; au prochain import fichier ou à la prochaine sync catalogue portant cette référence, l'article est **adopté** (`is_supplier_managed`, contenu verrouillé par `adoption_locks`, [supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py) l.139-160, l.475-477) ; reconnaissance aussi par EAN / UPC ou marque + référence fabricant sans rattachement préalable (règle du 05/09). **Limites** : (1) le bloc est **masqué en mode simple** → suivra `modules.suppliers` (S7) ; (2) l'adoption n'arrive que si le fournisseur **renvoie** la référence : pour Ingram la sync catalogue ne parcourt que `default_categories` et la sync d'inventaire ne rafraîchit que `is_supplier_managed=True` ([supplier_tasks.py](backend/app/tasks/supplier_tasks.py) l.282, [crud/product.py](backend/app/features/product/crud/product.py) l.358) → un article rattaché à une référence hors catégories synchronisées n'est **jamais** adopté ; (3) aucune action « Détacher » (le sélecteur de fournisseur est verrouillé une fois l'article géré, `ProductFormDialog.vue` l.74). **À faire** : bouton **« Rattacher maintenant »** (`POST /admin/products/{id}/attach-supplier` → `adapter.fetch_price_and_availability([sku])`, adoption immédiate avec coût / devise / stock, erreur claire si la référence est inconnue ; pour un fournisseur fichier, adoption au prochain import, message explicite), bouton **« Détacher »** (`is_supplier_managed=False`, `supplier_name=None`, verrous conservés, stock fournisseur remis à la main), et inclusion des articles manuels rattachés dans la sync d'inventaire (option). | 1 j |

### R5 — Configuration en base, version complète (priorité 5)

Inventaire de [config.py](backend/app/core/config.py) : **148 réglages**. À garder en env : 81 d'infrastructure et secrets techniques, 11 identifiants d'intégration (Ingram, Icecat, PayZen — règle du 05/09, exception S3 pour les `file_feed`), 7 structurels (`TERRITORY_PROFILE`, `SHOP_MODE`, `REFERENCE_CURRENCY`, `SHOP_COUNTRY_CODE`, `TAX_TERRITORY_CODE`, `SEED_FRENCH_POLYNESIA_LOGISTICS`, `PAYZEN_CURRENCY`). **À migrer : ~45** — 22 paramètres de synchro fournisseur / Icecat (dont une partie sur la ligne `Supplier`), 16 métier modifiables (`INSURANCE_RATE_PCT`, `CGV_VERSION`, `STOCK_RESERVATION_TTL_HOURS`, `CART_ABANDONMENT_*`, `SHOP_NAME`, `INVOICE_FEES_TAX_CODE`, `DEFAULT_TAX_CODE`, `INVOICE_LEGAL_FOOTER`, `EMAIL_SUPPORT / CONTACT`, IBAN et instructions de paiement manuel), 11 flags (`INGRAM_SYNC_ENABLED`, `INGRAM_ORDER_CREATION_ENABLED`, `CHECKOUT_SUPPLIER_AVAILABILITY_CHECK`, `ICECAT_ENABLED`, `ICECAT_USE_OPEN`, `PAYMENT_NOTIFICATIONS_*`, `ENABLE_GROUP_PERMISSIONS`, capture différée par fournisseur, activation des PSP P5).

**Existant** : `system_settings` clé / valeur texte (≤ 1 000 caractères, sans type ni auteur), `PUT /admin/system-settings/{key}` qui accepte **n'importe quelle clé**, trois mini-registres lus à chaque appel sans cache (`pricing_parameters.py`, `legal_identity.py`, clés isolées `customs_free_countries`, `social_webhook_url` — quasi-secret en clair), aucune couche de cache applicatif (`RedisCache` ouvre une connexion par requête ; `rate_limit.py` a le bon modèle de client partagé), crons figés au démarrage du worker ([arq_worker.py](backend/app/core/arq_worker.py) l.135-143 : Icecat, réservation, paniers abandonnés) et singletons capturés à l'import (`icecat_service`, `MAX_ROWS`, `_VALID_CURRENCIES`). Précédent à généraliser : la ligne `Supplier` (cache d'adaptateur invalidé par `updated_at`, ticks qui relisent la table).

| # | Étape | Effort |
|---|---|---|
| C1 | `core/runtime_settings.py` : registre `SettingSpec` (type via `TypeAdapter`, `env_fallback`, `category`, `description`, `public`, bornes, `on_change`, `restart_required`), résolution **base → env → défaut**, validation à l'écriture (400) et à la lecture (retour au défaut), snapshot par processus avec TTL 30-60 s + invalidation locale + compteur Redis `settings:version` ; absorbe `PRICING_SETTINGS` et `LEGAL_SETTINGS` ; fixture de reset pour les 133 `monkeypatch.setattr(settings, …)` | 2 à 3 j |
| C2 | API durcie : liste blanche des clés, `source: db\|env\|default`, hooks (`schedule_price_refresh`), `updated_by_id` + journal, migration (`value` en `Text`), amorçage générique qui ne réécrit jamais une valeur saisie | 1 à 1,5 j |
| C3 | Migration des ~40 appels (`pricing.py`, `cart.py`, `invoice_service.py`, `checkout_availability.py`, `handlers/ingram_micro.py`, `notifications.py`, `abandonment.py`, `admin_carts.py`…) ; injection en paramètre dans les fonctions synchrones (`meets_sync_thresholds`, `calculate_sale_price`, `PricingContext`) | 2 j |
| C4 | Paramètres propres à un fournisseur sur la ligne `Supplier` (`settings_schema` Pydantic par adaptateur à la place de `settings_keys`, seuils S2, filtres, liste blanche de sous-catégories, ship-to, création de BC) | 2 à 3 j |
| C5 | Crons convertis en ticks (Icecat, réservation, paniers abandonnés) ; suppression des singletons capturés à l'import | 1 j |
| C6 | Écran admin typé et groupé par catégorie (remplace le tableau clé / valeur de `SystemSettingsPage.vue`), badges « source » et « redémarrage requis » ; formulaire fournisseur | 2 à 3 j |
| C7 | Tests (registre, cache, invalidation ; adaptation des tests qui insèrent des `SystemSetting`) ; `DEPLOYMENT.md` §3.7 et `.env.example` (variables devenues « amorçage seulement ») | 1,5 à 2,5 j |

Nettoyages au passage : `INVOICE_SELLER_*` et `INGRAM_SYNC_INTERVAL_HOURS` ne servent plus qu'à l'amorçage (à retirer plutôt qu'à migrer) ; le `deposit_enabled` global mentionné l.809 **n'existe pas** dans le code (l'acompte est piloté par `PriceGroup` seul, l.723). Risques : priorité base > env silencieuse (d'où `source`), fenêtre d'incohérence entre réplicas jusqu'au TTL (lecture sans cache sur le chemin du checkout pour `CGV_VERSION` et `INSURANCE_RATE_PCT`), recalcul des prix matérialisés, `Literal` strict conservé pour les fournisseurs de notifications (N13).

### R6 — Bloquants avant production (priorité 6, chiffrage de la revue du 30/09)

Reprend et précise le « Reste à faire (non couvert le 02/09/2026) » et PP-*. Ordre conseillé :

1. ✅ **OAuth — liaison automatique par e-mail** (corrigé le 30/09/2026) : e-mail retenu seulement s'il est garanti par le fournisseur (`email_verified` Google ; compte Microsoft personnel, tenant de la boutique ou claim `xms_edov`), sinon ni création ni liaison ; aucun superuser lié ni connecté par OAuth, même par un lien antérieur ; un lien vers un compte désactivé ne retombe plus sur la recherche par e-mail ; **bug découvert au passage** : la création de compte par OAuth échouait toujours (`hashed_password` NULL, même piège que l'inscription), corrigée. 20 tests (unitaires, intégration, routes). Constat initial : [oauth.py](backend/app/api/routes/oauth.py) l.279-280) : un compte existant, **superuser compris**, est lié dès que l'e-mail du fournisseur correspond ; tenant Microsoft `common` avec e-mail lu dans `mail` / `userPrincipalName` (classe « nOAuth »), `email_verified` Google non vérifié. Exiger `email_verified`, refuser la liaison automatique sur un superuser, restreindre le tenant — ou laisser l'OAuth désactivé en prod. 0,5 j.
2. **Protéger l'admin** : 2FA TOTP pour les superusers, ou au minimum restriction IP / basic-auth sur `admin.{$DOMAIN}` ([Caddyfile](infra/caddy/Caddyfile) l.75) ; journal d'audit des actions admin (inexistant). 2 à 3 j.
3. **Sauvegardes réelles** : cron, copie hors site, restauration testée, `ALERT_WEBHOOK_URL` renseigné (`.env` et cron). Sur le serveur.
4. **Sandbox PayZen** : paiement, capture différée, remboursement, IPN `AUTHORISED` (jamais testés).
5. **Juridique et facturation** : relecture des CGV / mentions / confidentialité, formulaire de rétractation, `INVOICE_SELLER_*` → `legal_*` complets, validation du comptable (facture d'acompte, TVA d'import F7, code taxe des frais). Externe.
6. **Durcir les images** : `USER` non-root (backend et runner SSR), `uv sync --frozen --no-dev` (le groupe dev part en prod ; `pytest-asyncio` / `pytest-mock` sont en dépendances runtime), retirer `build-essential`, `uv` 0.4.15 figé, lockfile dans le runner SSR (`npm install --omit=dev` sans lockfile), **aligner CI et prod** (Python 3.12 en CI contre 3.14 en image ; Node 22 contre 24). 1 j.
7. **Stockage S3 imposé en prod** pour `FILE_STORAGE_BACKEND` (garde au démarrage comme ClamAV). 0,5 j.
8. **Données catalogue** : taux de douane par catégorie, frais par déclaration, assurance, `publication-report` à zéro (PP-F).

### R7 — Version publique : multilingue FR + EN et devises, périmètre minimal (priorité 7)

**Constat** : `vue-i18n` installé et chargé dans les deux fronts, **0 appel de traduction** ; ~510 chaînes françaises en dur dans la vitrine (25 fichiers), ~1 010 dans l'admin (34 fichiers) ; dictionnaire `shared/utils/src/i18n/fr.ts` orphelin ; `date.ts` figé sur `Pacific/Tahiti` / `fr-PF`, ~15 `toLocale*('fr-FR')` ; préférence `locale` stockée (`user_preference.locale`) mais lue par personne ; e-mails résolus par dossier `templates/email/<lang>/` avec repli `fr` (mécanisme prêt, 21 appels `render_email` sans `lang=`, seul `fr/` existe), PDF avec `lang=` sans repli ; 363 `AppError` à code stable (63 messages en français) ; contenu monolingue (`Product`, `Category`, `ContentPage`, `SpecDefinition.label_fr`, `ICECAT_LANGUAGE`) ; CGV codées en dur avec « Polynésie française » ; `TerritoryProfile` (PF, FR) sans locale, fuseau ni langues. Devises : pivot configurable, taux datés, conversion d'affichage, **mais** `formatXpf` sur 16 écrans « argent faisant foi » (une commande de 19,90 € s'affiche « 20 F » en profil FR), `'XPF'` en défaut dans ~10 modèles, `_VALID_CURRENCIES` codé, décimales divergentes front / backend, `default_display_currency` lu par aucun front, aucune contrainte moyen de paiement × devise.

| # | Chantier | Effort |
|---|---|---|
| L1 | Interface vitrine FR + EN : extraction, locale par préférence → cookie → `Accept-Language` (SSR), `<html lang>`, pack Quasar, `date.ts` / `currency.ts` paramétrés, un seul `extractError` partagé traduisant par `code`, pages légales en `DbContentPage` | 6 à 9 j |
| L2 | Interface admin FR + EN | 7 à 10 j |
| L3 | Backend : `Order.locale` figé au checkout, `lang` passé aux e-mails et PDF, `templates/email/en` (57 fichiers) et `invoice/en` (3) avec repli, filtres Jinja localisés (Babel) pour montants et dates, textes Python de `handlers/order.py` l.61-71 dans les templates, 63 messages `AppError` en anglais, amorçage dépendant du profil, `label_fr` → `label`, `CONTENT_LANGUAGE` relié à `ICECAT_LANGUAGE` | 6 à 9 j |
| L4 | Nettoyage devises : `formatMoney(amount, currency)` partout, défauts `XPF` → devise de référence, décimales alignées (exposer les décimales dans `/currency/display-rates`), `default_display_currency` lu, `_VALID_CURRENCIES` depuis `CurrencyRate`, `kr-language` PayZen dérivé de la locale | 2 à 3 j |
| L5 | `TerritoryProfile` enrichi (`default_locale`, `timezone`, `available_locales`), exposé par `/system/config`, déclarable en YAML / env sans toucher au code | 1 à 2 j |

Hors périmètre, documenté comme feuille de route : contenu multilingue en base (12 à 18 j) et paiement réel dans la devise du client avec factures, avoirs et export dans la devise payée (15 à 25 j, l.1400).

### R8 — Ajouts à forte valeur et confort (priorité 8, à arbitrer)

**Forte valeur** : scans de sécurité en CI (Trivy sur les images, `pip-audit`, `pnpm audit`, CodeQL, gitleaks) et `docker build` des trois images sur PR ; vérification de dérive de `shared/api-types` ; Sentry sur la vitrine et l'admin, logs JSON unifiés (retirer les `logging.basicConfig` au niveau module et les `print` du lifespan), endpoint `/metrics` (latence, erreurs, file ARQ, âge de l'outbox), `SENTRY_TRACES_SAMPLE_RATE` 0.1, uptime externe ; CSP (Caddy et API) ; rate limiting sur alertes stock, devis, checkout + captcha (Turnstile) sur les formulaires publics ; SEO (`sitemap.xml`, `robots.txt` servis par le SSR, JSON-LD Product / Offer / Breadcrumb, `useMeta` sur toutes les pages) ; **tableau de bord admin avec KPI** (✅ 30/09/2026 : files « À traiter », commandes et CA 7 / 30 jours, prochain départ ; reste panier moyen, conversion, stocks bas — routes `analytics_*` existantes) ; **RGPD en libre-service** (export JSON, suppression / anonymisation du compte, la page confidentialité annonce ces droits) ; **panier invité serveur** avec fusion à la connexion (débloque les relances pour les visiteurs) ; tests : e2e inscription / OTP / login / reset / CB sandbox (parcours admin ✅ 30/09/2026 : accès, tableau de bord, tous les écrans du menu, validation d'un virement jusqu'à la commande payée, bannière d'accueil), premiers tests unitaires de l'admin-frontend, mesurer `app/tasks/*` (exclu de la coverage avec `ingram_micro.py`, `icecat_service.py`) ; déploiement reproductible (images GHCR réellement consommées avec `VITE_API_URL` par environnement, rollback par tag, staging) ; **A19** liste générale des paiements.

**Confort** : avis (avec modération) et notifications internes en vitrine ; newsletter double opt-in ; analytics sans cookie (Plausible / Matomo) ; vouchers, cartes cadeaux, cross-sell, comparateur, fidélité ; auto-capture à l'expédition, void d'autorisation, alerte d'expiration des autorisations ; DX : Makefile / justfile, `.pre-commit-config.yaml` (ruff, eslint, prettier), `.editorconfig`, seed « démo » avec catalogue d'exemple, README des fronts (encore les README Quasar génériques), réhabiliter ou supprimer `infra/k8s` (marqué obsolète) ; dette : garde de longueur sur `SECRET_KEY`, comparaison en temps constant du bearer Ingram ([webhooks.py](backend/app/api/routes/webhooks.py) l.94), docstrings OAuth périmées (« tokens appended as query params »), bornes hautes Python, httpx2.

---

## Décision transverse : tarification par groupe utilisateur

**Approche retenue** : coût stocké en base + prix de vente calculé à la volée selon le groupe du client.

### Modèle de données

| Entité | Champs à ajouter |
|--------|------------------|
| `Product` | `cost_amount: Decimal`, `cost_currency: str`, `customs_rate_pct: Decimal` |
| `PriceGroup` (nouveau, ou extension de `Group`) | `margin_rate_pct: Decimal`, `default: bool`, `requires_validation: bool`, `label: str` |
| `User` | `price_group_id: UUID` (FK, nullable → fallback `default=True`) |
| `OrderLine` | `price_group_applied_id: UUID` (snapshot pour audit) |
| `PriceOverride` (Phase 5 optionnelle) | `product_id | category_id`, `group_id`, `override_margin_pct`, `valid_from`, `valid_until` |

### Formule unique

```python
sale_price = cost × (1 + customs_rate_pct/100) × (1 + margin_rate_pct/100) × (1 + tax_rate.rate_pct/100)
# tax_rate résolu : product.tax_rate → category.default_tax_rate → TaxRate(code="TGC_NORMAL", territory="PF")
```

> ⚠️ **Amendée** par la section *Décision transverse : fret import & assiette douane (CAF)* ci-dessous : la douane porte sur la valeur CAF (coût + assurance + **fret import**), pas sur le coût seul. La formule ci-dessus reste valable une fois `cost` remplacé par la CAF.

- Anonymes / non connectés → groupe `default=True` (typiquement « Particulier »).
- Snapshot figé dans `CartItem.unit_price` (déjà existant) puis `OrderLine.unit_price` au checkout : la commande n'est pas affectée par un changement de marge ultérieur.
- Sync Ingram met à jour `cost_amount`, pas `base_price`.

### Groupes prévus

| Groupe | Marge | TVA | Validation admin |
|--------|-------|-----|------------------|
| Particulier (default) | 30% | via `TaxRate` produit/catégorie | Non |
| Professionnel | 25% | via `TaxRate` produit/catégorie | Oui (justificatif d'entreprise) |
| Revendeur | 12% | via `TaxRate` produit/catégorie | Oui (justificatif d'entreprise) |
| Public / Établissements | 18% | via `TaxRate` produit/catégorie | Oui (justificatif) |

**Notes** :
- En Polynésie française, la taxe (TGC) s'applique à tous les groupes, mais son taux dépend du **produit/catégorie**, pas du groupe client. Le groupe client pilote uniquement la marge. Voir section *Décision transverse : gestion des taux de TVA/TGC*.
- Pas de SIRET en PF — le justificatif d'entreprise repose sur le **numéro TAHITI** (ou équivalent local). Le champ doit donc être nommé de façon générique (`business_registration_number` plutôt que `siret`) pour rester portable.
- **Flexibilité géographique** : le champ `territory_code` sur `TaxRate` permet de gérer plusieurs zones fiscales. La résolution du taux (product → category → default du territoire) est centralisée dans `pricing.py` pour ne jamais ferrer le code sur « TVA PF » comme constante.
- Valeurs gérables via endpoint admin, pas de constantes en dur.

---

## Décision transverse : gestion des taux de TVA / TGC

**Contexte** : en Polynésie française, la taxe sur la consommation (TGC) dépend de la **nature du produit**, pas du groupe client. Le taux est donc une propriété du produit ou de sa catégorie, pas de `PriceGroup`.

### Modèle de données

| Entité | Champs à ajouter |
|--------|------------------|
| `TaxRate` (nouveau) | `id`, `code: str` (ex. `TGC_NORMAL`), `label: str`, `rate_pct: Decimal`, `territory_code: str` (ex. `PF`), `valid_from: date`, `valid_until: date \| null` |
| `Category` | `default_tax_rate_id: UUID \| null` (FK → `TaxRate`) |
| `Product` | `tax_rate_id: UUID \| null` (FK → `TaxRate`, nullable → fallback sur `Category.default_tax_rate_id`, puis taux standard du territoire) |
| `OrderLine` | `tax_rate_id: UUID` (snapshot figé au checkout pour historique fiscal) |

### Taux PF à seeder (Phase 1)

| Code | Taux | Usage typique |
|------|------|---------------|
| `TGC_NORMAL` | 16 % | Électronique, informatique, services |
| `TGC_REDUIT` | 5 % | Alimentaire, médicaments, livres |
| `TGC_EXONERE` | 0 % | Produits exonérés (eau, certains intrants) |

### Résolution du taux dans `pricing.py`

```python
def resolve_tax_rate(product, territory="PF") -> TaxRate:
    return (
        product.tax_rate
        or product.category.default_tax_rate
        or TaxRate.get(code="TGC_NORMAL", territory=territory)
    )
```

### Invariants

- Un `TaxRate` n'est jamais modifié rétroactivement : on crée un nouveau taux avec `valid_from` et on clôture l'ancien via `valid_until`. Les `OrderLine` gardent leur snapshot.
- Pas de constante `TVA_RATE = 0.16` dans le code — toujours résolu depuis la BDD.
- Extension multi-territoire : ajouter un `TaxRate` avec `territory_code="NC"` (Nouvelle-Calédonie) sans toucher à la logique de résolution.

### Jalons par phase

| Phase | Livrable TVA |
|-------|-------------|
| **1** | Modèle `TaxRate` + migration + seed 3 taux PF ; champ `Category.default_tax_rate_id` + `Product.tax_rate_id` ; service `resolve_tax_rate()` utilisé dans `calculate_sale_price()` |
| **2** | Admin CRUD : `GET/POST /admin/tax-rates`, `PUT /admin/tax-rates/{id}` (valid_until only), `PUT /admin/products/{id}/tax-rate`, `PUT /admin/categories/{id}/tax-rate` |
| **5a** | Facture : ligne HT + code taux + montant TVA ; sous-total TVA regroupé par taux ; snapshot `OrderLine.tax_rate_id` exposé dans le PDF |

---

## Décision transverse : gestion des devises

**Contexte** : les fournisseurs renvoient les prix dans leur devise d'origine (USD pour Ingram, EUR potentiellement pour d'autres), la vitrine PF affiche en XPF et PayZen facture en XPF. Sans conversion explicite, `cost_amount` est multiplié par douane × marge × TVA tel quel — un coût USD donnerait un prix de vente ~100× sous-évalué (1 USD ≈ 119 XPF).

### Devise de référence (pivot) paramétrable

Trois devises distinctes, à ne pas confondre :

| Devise | Rôle | Statut |
|--------|------|--------|
| **Référence / pivot** | Normalisation des coûts, calcul, facturation PayZen. **Une par déploiement**. | À **dé-localiser** : `REFERENCE_CURRENCY` en `.env` (défaut `XPF`) |
| **Source** | Devise du coût fournisseur (USD/EUR) | `Product.cost_currency` — déjà générique |
| **Affichage** | Présentationnel, par utilisateur | `default_display_currency` (P3/P4) — distinct de la référence |

**Décision (P1, tant qu'on est pré-prod)** : sortir la devise de référence du code en dur — renommer **tout** ce qui fige `xpf` :

- `convert_to_xpf()` → `convert_to_reference_currency()` (lit `settings.REFERENCE_CURRENCY`, court-circuit si `from_currency == REFERENCE_CURRENCY`).
- `CurrencyRate.rate_to_xpf` → `rate_to_reference` (migration, **gratuite en pré-prod**, coûteuse après mise en prod).
- `pricing.ts` : `costAmountXpf` / `costXpf` → `costInReference`.
- Variable interne `cost_in_xpf` → `cost_in_reference`.

**Hors périmètre** : pas de machinerie multi-territoire (résolution de la référence par territoire, conversions en cascade) tant qu'un 2ᵉ territoire n'existe pas — YAGNI. Le `.env` suffit ; chemin BDD (`system_settings`) laissé ouvert, non construit.

### Modèle de données

| Entité | Champs |
|--------|--------|
| `CurrencyRate` (nouveau) | `id`, `currency_code: str` (ex. `USD`, `EUR`), `rate_to_reference: Decimal` (taux vers la devise de référence), `valid_from: date`, `valid_until: date \| null`, `source: enum('manual','auto')`, `updated_by_user_id: UUID \| null`, `created_at` |
| `CartItem` | `fx_rate_used: Decimal \| null`, `fx_source_currency: str \| null` (snapshot pour audit) |
| `OrderLine` | `cost_amount_snapshot`, `cost_currency_snapshot`, `fx_rate_used`, `customs_rate_pct_snapshot`, `margin_rate_pct_snapshot`, `price_group_id_snapshot` (en plus de `tax_rate_id` déjà prévu) |

### Formule mise à jour

```python
cost_in_reference, fx_rate = convert_to_reference_currency(product.cost_amount, product.cost_currency, at_date=today)
sale_price = cost_in_reference × (1 + customs_rate_pct/100) × (1 + margin_rate_pct/100) × (1 + tax_rate.rate_pct/100)
```

Si `cost_currency == REFERENCE_CURRENCY`, `fx_rate_used = NULL` et pas d'appel de conversion.

### Résolution du taux

```python
def convert_to_reference_currency(amount, from_currency, at_date=None) -> tuple[Decimal, Decimal]:
    if from_currency == settings.REFERENCE_CURRENCY:
        return amount, Decimal("1")
    rate = CurrencyRate.get_active(code=from_currency, at=at_date or today)
    if rate is None:
        raise CurrencyRateMissing(from_currency)
    return amount * rate.rate_to_reference, rate.rate_to_reference
```

### Invariants

- Un `CurrencyRate` n'est jamais modifié rétroactivement : créer un nouveau taux avec `valid_from` et clôturer l'ancien via `valid_until`. Les `CartItem`/`OrderLine` gardent leur snapshot FX.
- Pas de constante `USD_TO_XPF = 119` dans le code — toujours résolu depuis la BDD.
- Devise absente → `calculate_sale_price` lève `CurrencyRateMissing` explicitement (pas de fallback silencieux à 1).
- Seuil `SUPPLIER_SYNC_MIN_PRICE` documenté **en XPF** ; conversion appliquée avant comparaison dans `_meets_sync_thresholds`.

### Devises supportées initiales

`REFERENCE_CURRENCY` (défaut `XPF`), USD, EUR. Ajout d'autres devises = créer un `CurrencyRate`, pas de migration.

### Jalons par phase

| Phase | Livrable devises |
|-------|------------------|
| **1** | `REFERENCE_CURRENCY` en `.env` (défaut `XPF`) ; modèle `CurrencyRate` + migration + seed initial USD/EUR→référence ; helper `convert_to_reference_currency()` intégré à `calculate_sale_price()` et `_meets_sync_thresholds()` ; snapshots FX sur `CartItem` et `OrderLine` ; endpoint admin `PUT /admin/currency-rates/{code}` + `GET /admin/currency-rates`. **Dé-localisation pré-prod** : renommer `convert_to_xpf→convert_to_reference_currency`, colonne `rate_to_xpf→rate_to_reference`, `costAmountXpf/costXpf→costInReference` (`pricing.ts`) |
| **3** | Préparation P4 : champ système `default_display_currency` (admin) |
| **4** | Cron quotidien **optionnel** (`CURRENCY_AUTO_UPDATE_ENABLED`) avec source externe (ECB / exchangerate.host) ; alerte admin si dernier taux > 30 jours ; affichage multi-devises selon `user.preference.currency_pref` (XPF/USD/EUR) |

---

## Décision transverse : fret import & assiette douane (CAF)

**Contexte** : en Polynésie française, les droits de douane portent sur la **valeur CAF** (Coût + Assurance + **Fret**), pas sur le coût seul. Le fret du tronçon *origine → entrepôt de dédouanement (Papeete)* fait donc partie de l'assiette taxable. Comme ce fret dépend du mode de transport (avion = rapide, bateau = économique/écologique), **le prix de vente d'un produit dépend du mode de transport import choisi**. La formule de la section *tarification par groupe* est corrigée en conséquence.

### Deux familles de tronçons

| | Tronçon **import** (origine → entrepôt Papeete) | Tronçon **distribution** (entrepôt → client) |
|---|---|---|
| Frontière | route dont `to_place.customs_clearance = True` | après dédouanement, intérieur PF |
| Dans l'assiette douane (CAF) ? | **Oui** | Non |
| Où dans le prix ? | **Inclus dans le prix produit affiché** | Frais séparés ajoutés au panier |
| Choix client | niveau de service (rapide/éco/économique) | mode de livraison île/domicile |

### Formule corrigée

```python
caf        = cost_in_xpf + fret_import_variable(route) + assurance
landed     = caf × (1 + customs_rate_pct/100)
sale_price = landed × (1 + margin_rate_pct/100) × (1 + tax_rate.rate_pct/100)
```

- `fret_import_variable` = **part variable uniquement** : `route.price_per_kg × billable_weight` (voir *Poids taxable* ci-dessous). Le forfait par envoi (`route.base_price`) et le handling restent des frais d'expédition au niveau du panier (non attribuables à l'unité).
- `assurance` = `insurance_rate_pct × cost_in_xpf` (config globale, défaut 0 → n'empêche pas de démarrer).
- L'ancienne formule (douane sur coût seul) est **caduque** ; `calculate_sale_price()` et `shared/utils/src/pricing.ts` ont été repris (✅ livré P1, conformité vérifiée à l'audit du 25/08/2026 — voir *Vérification implémentation & écarts fiscalité* ci-dessous).

### Poids taxable : poids réel vs volume (poids volumétrique)

Le fret se facture sur le **plus cher** du poids réel et du poids volumétrique (standard transport). S'applique à tout le calcul de fret (`calculate_shipping_for_routes`), import comme distribution.

```python
volume_m3            = (length_cm × width_cm × height_cm) / 1_000_000   # None si une dim manque
volumetric_weight_kg = volume_m3 × dim_factor_kg_per_m3                 # 0 si volume indisponible
billable_weight_kg   = max(actual_weight_kg, volumetric_weight_kg)
fee                  = route.price_per_kg × billable_weight_kg
```

- **Facteur dépendant du mode**, jamais en dur : `route_metadata.dim_factor_kg_per_m3` (le JSON `route_metadata` porte déjà `value_rate`/`min_total`/`max_total`/`weight_unit`). Fallback sur un défaut par mode en config — avion ≈ 167 kg/m³, mer/LCL ≈ 1000 kg/m³.
- **Fallback** : dimensions absentes ou incomplètes (il faut les 3) → `volumetric_weight = 0` → on retombe sur le poids réel.
- **Stratégie enfichable** : `route_metadata.billing_basis` ∈ `volumetric_max` (défaut si dims présentes) | `actual_weight` | (formule future). `calculate_shipping_for_routes` reste *strategy-driven* : nouvelle formule = nouvelle stratégie, sans toucher aux appelants.
- **Attribution** : prix unitaire (CAF) → `billable_weight` calculé **par produit**. Forfait panier (envoi consolidé) → ne pas sommer les billables unitaires ; sommer poids et volumes séparément puis `max(Σpoids, Σvolume × facteur)`.
- Le champ `billable_weight` de `RouteShippingCostBreakdown` (aujourd'hui = poids converti) prend son vrai sens.
- **Prérequis enrichissement** : peupler `Product.dimensions_length/width/height` + `weight` à l'enrichissement Icecat (aujourd'hui seules les dims d'**images** sont mappées dans `icecat_service.py`). Fallback poids réel si Icecat ne fournit pas les dimensions physiques.

### Le choix client = UN niveau de service, appliqué à tous les corridors

Point clé pour éviter l'explosion de complexité multi-fournisseurs : **le client choisit un seul *niveau de service*** (rapide / économique / écologique), **jamais une route par fournisseur**. Le système résout, pour chaque corridor, la route import correspondant à ce niveau.

- Panier mono-fournisseur (cas courant France→Papeete) → 1 corridor → cas simple.
- Panier multi-fournisseurs (France + US + Asie) → **toujours un seul choix client** ; en coulisses N expéditions distinctes, gérées par la machinerie consolidation / `sequence_order` existante. Invisible pour le client.
- Chaque produit embarque déjà le fret de **son** corridor pour chaque niveau → le recalcul client (dropdown) reste trivial : on indexe le même `service_level` pour tous les produits du panier.
- Corridor sans le niveau demandé (ex. pas d'avion) → fallback vers le niveau disponible le plus proche, avec ETA réel affiché.

Résolution du niveau effectif : param requête → `User.preferred_shipping_mode` → défaut système (`rapide`).

### Recalcul côté client

Le backend renvoie, par produit, un tableau indexé par niveau de service :

```jsonc
"shipping_modes": {
  "rapide":     { "freight": 3750, "sale_price": 165900, "eta_days": 5,  "carbon": 12.4 },
  "economique": { "freight": 750,  "sale_price": 161100, "eta_days": 35, "carbon": 1.1 }
},
"default_mode": "rapide"
```

Le dropdown bascule **en local** via `shared/utils/src/pricing.ts` (étendu pour la CAF), **sans refetch**. Le backend reste autoritaire : recalcul + snapshot au panier/checkout.

### Modèle de données

| Entité | Champs à ajouter |
|--------|------------------|
| `ShippingRoute` | `customer_label: str \| null` (libellé dropdown), `is_default_import: bool`, `service_level: str` (clé stable cross-corridor : `rapide`/`economique`/`ecologique`) |
| `ShippingRoute.route_metadata` (JSON existant) | `dim_factor_kg_per_m3`, `billing_basis` (poids taxable) — **pas de migration** |
| `Product` (champs existants) | peupler `dimensions_length/width/height` + `weight` à l'enrichissement (volume = L×l×h) |
| `User` (ou `UserPreference`) | `preferred_shipping_mode: str \| null` (niveau de service) |
| Config système | `insurance_rate_pct: Decimal` (défaut 0) |
| `CartItem` / `OrderLine` | snapshot `service_level` + `import_route_id` + `fret_import_snapshot` (assiette douane figée pour audit) |

- Identification import : **pas de flag dédié** — une route est « import » si `to_place.customs_clearance = True` (`Place` l'a déjà).
- **Mapping produit → corridor** (évolution multi-fournisseurs) : un produit doit savoir de quel corridor il dépend. Aujourd'hui `Product.supplier_name` est un texte libre — prévoir un FK `Product.supplier_partner_id` (ou table `supplier_name → from_place_id`) reliant le produit à un `Partner`/`Place` d'origine. **Reporté Phase 3** (cf. jalons).

### Vérification implémentation & écarts fiscalité (audit + discussion du 25/08/2026)

**Vérifié conforme au plan** (lecture du code, 25/08/2026) :
- Formule CAF opérationnelle dans [pricing.py](backend/app/features/product/services/pricing.py) (`calculate_sale_price`) : coût converti au taux actif + fret import variable + assurance → × (1 + douane) × (1 + marge du groupe) × (1 + TGC résolue produit → catégorie → défaut territoire). Prix **par mode de transport** via `calculate_price_by_mode` → payload `shipping_modes`, bascule locale côté front sans refetch.
- Poids volumétrique : `resolve_billable_weight` = max(poids réel, volume × facteur), défauts 167 kg/m³ (air, IATA) / 1000 kg/m³ (mer, W/M), `dim_factor_kg_per_m3` / `billing_basis` lus de `route_metadata`, fallback poids réel si dimensions incomplètes — conforme.
- Linéarité panier : part fixe des tronçons au niveau expédition (une fois par envoi), poids et volumes **totaux** consolidés dans `calculate_shipping_for_routes` — pas de sur-facturation des paniers multiples.

**Écarts à corriger** (bloquants avant vente réelle, sauf F3/F7 à instruire).

> ✅ **28/08/2026** : les trois écarts qui produisaient un **prix faux en silence** (F1 douane par défaut, F5 poids absent, F6 double comptage du fret import) sont corrigés et testés — voir le détail dans les lignes ci-dessous. Restent F2/F3/F4/F7, qui ne sont pas des bugs de code mais des **paramètres fiscaux et assurantiels à établir** (simulateur des douanes PF, comptable, assureur) puis à saisir : le mécanisme qui les accueille (taux par catégorie, taux effectif, `INSURANCE_RATE_PCT`) existe désormais.

> ✅ **31/08/2026** : la part *code* de F3 et F4 est livrée — les frais dus par déclaration sont modélisés au niveau expédition (`Place.customs_declaration_fee`, facturés une fois par envoi) et l'assurance porte enfin sur l'assiette CAF (coût **+ fret**) et non sur le coût seul. Il ne reste donc, sur F2/F3/F4/F7, **que des nombres à établir puis à saisir** : taux effectif par catégorie (DEPLOYMENT §15), montant par déclaration et taux d'assurance (DEPLOYMENT §16), arbitrage TVA d'import. Le rapport d'ouverture (`app.scripts.release_readiness`) affiche désormais l'état des deux derniers, un paramètre à zéro ne se voyant pas autrement.

| # | Écart | Détail / correctif |
|---|-------|--------------------|
| F1 ✅⚠️ | `customs_rate_pct` = **0,00 par défaut**, jamais renseigné par la sync fournisseur — corrigé le 28/08/2026 | `Product.customs_rate_pct` devient **nullable** (NULL = « hérite de la catégorie »), `Category.default_customs_rate_pct` ajouté, résolution produit → catégorie dans `resolve_customs_rate_pct` ([pricing.py](backend/app/features/product/services/pricing.py)) sur le modèle de `resolve_tax_rate`. **Un taux non résolu vaut « inconnu », jamais 0** : le produit devient non publiable ([publication.py](backend/app/features/product/services/publication.py)), invisible de la vitrine et refusé au panier. Migration `a9c4e1f7b3d2` avec **backfill** : les `0,00` posés par la sync repassent à NULL (un 0 explicite = exonération se re-saisit à la main). Admin : `PUT /admin/categories/{id}/customs-rate`, `PUT /admin/products/{id}/customs-rate`, champ « Douane » du formulaire produit vidé = héritage. ⚠️ **Prérequis d'exploitation** : tant qu'aucun taux n'est saisi par catégorie, le catalogue synchronisé est **entièrement masqué** — c'est voulu (mieux vaut vide que sous-facturé). Utiliser `GET /admin/catalog/publication-report` pour dimensionner le travail avant ouverture |
| F2 🔲 | Pas de position tarifaire, pas de TDL en cascade | Fiscalité PF réelle = droits de douane + **TDL** (assiette = **CAF + droits**, non déductible, très variable par position tarifaire) + TVA d'import 16 % (déductible si assujetti). Encoder un **taux effectif** par catégorie/position — jamais un forfait global. ⚙️ Le **réceptacle existe depuis F1** (`Category.default_customs_rate_pct`) et la **procédure est écrite depuis le 29/08/2026** : DEPLOYMENT.md **§15**. Deux corrections y sont apportées à la formule notée ici à l'audit : ① `dd + tdl × (1 + dd)` décrit bien la cascade TDL (assiette = CAF + droits, vérifié) mais **ignore les autres prélèvements** de la position (PID, TS, TEAP, PEAGE, SETIL, CPS…) — d'où une dérivation **empirique** depuis le [simulateur officiel](https://simulateur-douane-polynesie.com/), qui applique la vraie cascade ; ② **retirer la TVA du total du simulateur**, sinon elle est comptée deux fois (l'app l'applique déjà via `TaxRate`) — ce qui suppose F7 tranché *avant* la saisie. Reste à faire : la saisie elle-même |
| F3 ✅⚠️ | Frais fixes par déclaration non modélisés — mécanisme livré le 31/08/2026 | Les redevances, participations et frais de dossier du transitaire sont dus **par déclaration**, pas par article. Ils sont désormais portés par le **lieu de dédouanement** (`Place.customs_declaration_fee`, [place/models.py](backend/app/features/place/models.py), migration `b3f7d1e6c8a4`) et non par la route : plusieurs corridors (France, US, Asie) franchissant la **même** frontière restent **une seule** déclaration, le dédoublonnage se faisant par lieu. Facturés **une fois par expédition** dans `calculate_shipping_for_routes` ([shipping/services/pricing.py](backend/app/features/shipping/services/pricing.py)) — jamais mis à l'échelle du poids, de la valeur ni du nombre de lignes — et remontés **à part** (`customs_declaration_fees`) dans le snapshot `shipping_cost_breakdown`, pour qu'une commande dise ce qui a été facturé au titre du transport et ce qui l'a été au titre de la déclaration. Facturés **même quand aucun tronçon ne l'est** : le fret d'import est déjà dans le prix unitaire (F6), la déclaration ne l'est pas. Affichés au checkout vitrine (`customs_declaration_fee` de `/cart/me/last-leg-options`) pour que la charge ne surgisse pas à la page de paiement. ⚠️ Reste : **saisir le montant** (barème transitaire + charges d'une déclaration réelle, DEPLOYMENT **§16.1**) — NULL/0 ne facture rien, c'est le défaut livré. Limites connues, toutes deux du côté de la **sur**-facturation (visible et remboursable, contrairement à la sous-facturation) : une commande servie entièrement depuis le stock local ne franchit aucune douane mais paie les frais (l'affectation ligne → segment n'est décidée qu'après le figeage du total), et plusieurs commandes consolidées sous une même déclaration en portent chacune la totalité → saisir la **quote-part par commande** jusqu'à la phase logistique |
| F4 ✅⚠️ | Assurance : assiette corrigée le 31/08/2026, taux toujours à 0 | La prime était calculée sur le **coût seul** alors qu'une police ad valorem couvre la valeur CAF : `insurance = (cost_in_reference + freight_variable) × INSURANCE_RATE_PCT` ([pricing.py](backend/app/features/product/services/pricing.py)), miroir front documenté ([shared/utils/src/pricing.ts](shared/utils/src/pricing.ts)). L'écart portait exactement sur les articles où le fret pèse le plus — les lourds et les lointains. ⚠️ Reste, **hors code** : souscrire la police ad valorem (les plafonds de responsabilité transitaires au kilo n'indemnisent presque rien sur du dense/cher — GPU = article le plus volé du fret aérien) puis saisir son taux réel dans `INSURANCE_RATE_PCT` (DEPLOYMENT **§16.2**). À 0, aucune assurance n'entre dans le prix : la prime est payée et jamais récupérée sur les ventes |
| F5 ✅ | Produit **sans poids** → fret variable = 0, silencieusement — corrigé le 28/08/2026 | Poids présent **et > 0** est désormais un critère de publication ([publication.py](backend/app/features/product/services/publication.py)), au même titre que le taux de douane. **Les dimensions restent non bloquantes** : sans elles le poids volumétrique retombe sur le poids réel (sous-facturation du volumineux/léger, jamais un zéro inventé) — c'est le comportement déjà acté dans la table des risques, et l'exiger viderait le catalogue là où Icecat ne fournit pas les dimensions. Le durcissement « dimensions requises » reste au backlog *Whitelist catalogue*, à trancher une fois la couverture Icecat mesurée sur le catalogue réel |
| F6 ✅ | Double comptage du tronçon import au checkout — corrigé le 28/08/2026 | Helper `_import_route_ids` ([cart.py](backend/app/api/routes/cart.py)) : une route est « import » si sa destination dédouane (`to_place.customs_clearance`). Deux chemins étaient touchés, pas un seul — ① route passée explicitement par le client : rejet 400 `shipping.route.import_not_billable` ; ② **sélection automatique par préférence**, celle qu'utilise réellement la vitrine (elle n'envoie aucun `shipping_route_ids`) : `get_intermediary_routes` renvoie toutes les routes non-client, **corridor d'import compris** — il est désormais filtré avant l'arbitrage. C'était le double comptage effectif en production, l'attaque cliente n'étant que le cas théorique décrit à l'audit |
| F7 🔲 | TVA d'import supposée déductible | Le modèle applique la TGC une seule fois sur le prix de vente : correct **si** l'entreprise est assujettie et récupère la TVA d'import à la douane. À valider avec le comptable ; sinon, l'intégrer au taux effectif F2 |

### Jalons par phase

| Phase | Livrable fret import |
|-------|----------------------|
| **1** | CAF dans `calculate_sale_price()` (part variable + assurance) ; **poids taxable** (max poids/volume) dans `calculate_shipping_for_routes` + `dim_factor_kg_per_m3`/`billing_basis` lus depuis `route_metadata` ; capture des **dimensions physiques** à l'enrichissement Icecat (+ fallback poids) ; champs `customer_label` + `is_default_import` + `service_level` sur `ShippingRoute` + migration ; **corridor unique France→Papeete** seedé ; payload `shipping_modes` + `default_mode` sur la fiche produit ; `pricing.ts` étendu CAF ; dropdown front + persistance du choix (`localStorage` anonyme) ; `preferred_shipping_mode` lu s'il est présent |
| **2** | `preferred_shipping_mode` éditable dans les préférences utilisateur (cf. item *Préférences utilisateur* P2) ; snapshot `service_level` / `import_route_id` / `fret_import_snapshot` figé sur `OrderLine` au checkout |
| **3** | **Mapping multi-fournisseurs** : `Product.supplier_partner_id` (ou table de correspondance) ; corridors multiples (US, Asie…) ; résolution `service_level → route` par corridor + fallback nearest-tier ; cohérent avec la refonte route auto-sélection (B8) |

---

## Décision transverse : fournisseurs en base, modes de prix et articles hors synchronisation (05/09/2026)

**Contexte.** Jusqu'ici un fournisseur était une classe Python plus un jeu de
variables `INGRAM_*`, et tout article passait par la formule CAF : impossible de
vendre un article de l'entrepôt à un prix TTC décidé à la main, impossible de
déclarer un distributeur local (Tahiti) sans lui appliquer douane et fret
import, et rien pour un fournisseur qui envoie un CSV/Excel.

### Trois modes de prix (`Product.pricing_mode`)

| Mode | Formule | Gardes-fous de publication | Usage |
|------|---------|----------------------------|-------|
| `import` (défaut, comportement historique) | CAF = coût + fret import + assurance → douane → marge → taxe | taux de douane résolu **et** poids > 0 | distributeur hors territoire douanier (Ingram, fournisseur générique en France…) |
| `domestic` | coût → marge → taxe (ni douane, ni fret import, pas de niveaux de service) | aucun | entrepôt local, distributeur du même territoire douanier |
| `fixed` | `base_price` **est** le prix TTC saisi ; rien n'est recalculé | `base_price > 0` | article de l'entrepôt vendu à un prix décidé à la main, promo, lot |

- La **marge** se résout `Product.margin_rate_pct` → `Category.default_margin_rate_pct` → `PriceGroup.margin_rate_pct` (défaut 30 %). Réponse à la question « la marge se définit dans la catégorie ? » : oui par défaut, surchargeable article par article ; à défaut des deux c'est le groupe tarifaire du client, comme avant.
- `calculate_price_by_mode` (dropdown rapide/économique) ne renvoie des niveaux de service que pour le mode `import` : un article local ou à prix fixe n'a pas de tronçon import, la vitrine affiche `base_price`.
- Toutes les lignes existantes sont migrées en `import` : **zéro changement de prix** sans action admin.

### Table `suppliers` (remplace la config `.env` par fournisseur)

Colonnes : `code` (clé de rapprochement = `Product.supplier_name`, immuable),
`name`, `kind` ∈ `manual | file | api`, `adapter_key` (kind=api : clé de
l'intégration dans le code, ex. `ingram_micro`), `origin_place_id` (entrepôt
d'expédition → `Product.supplier_place_id`, premier tronçon et suivi),
`is_domestic` (même territoire douanier → articles créés en `domestic`),
`sync_enabled`, `sync_interval_hours`, `default_categories`, `price_currency`,
`column_mapping` (kind=file), `settings` (JSON non secret propre à
l'intégration : `environment`, `country_code`…), contact, notes.

- **Les identifiants restent dans l'environnement** (`INGRAM_CLIENT_ID`…) : une base compromise ne livre pas les secrets ; l'admin voit seulement « identifiants présents / absents ». Les autres `INGRAM_*` ne servent plus qu'à amorcer la ligne `ingram_micro` (migration + `initial_data`) et de repli ; `INGRAM_SYNC_ENABLED` reste un coupe-circuit global.
- **Trois méthodes** : `manual` (fournisseur générique : articles saisis à la main, `supplier_quantity` tenu par l'admin) ; `file` (CSV / `.xlsx` téléversé depuis Admin → Fournisseurs, mapping de colonnes mémorisé sur la ligne, simulation avant import, mêmes garde-fous que la sync : verrous admin, catégorie interne depuis la sous-catégorie, enrichissement Icecat des nouveautés) ; `api` (intégration du code, registre `ADAPTERS`).
- **Planification** : plus un cron par fournisseur figé au démarrage du worker, mais trois *ticks* (`supplier_catalog_sync_tick` horaire, `supplier_inventory_sync_tick` toutes les 2 h, `supplier_api_health_check_tick` quotidien) qui relisent la table et enfilent un job par fournisseur dû. Créer, suspendre ou recadencer un fournisseur ne demande aucun redéploiement.
- Un article manuel peut être rattaché à un fournisseur déclaré : `POST /admin/products` recopie l'entrepôt d'origine et le régime douanier (mode de prix) du fournisseur si le payload ne les fixe pas. Le stock fournisseur compte au checkout pour tout article qui a un fournisseur, synchronisé ou non.
- La sync catalogue ne remet plus à zéro le coût et le stock d'un article quand la source ne les porte pas (le catalogue Ingram ne renvoie ni prix ni dispo) ; elle n'écrit ces champs que lorsqu'ils sont fournis (fichier, API prix/dispo).

### Reconnaissance des articles à l'import (question du 05/09/2026)

**Règle : un article = une source.** Un même produit physique proposé par deux
fournisseurs donne deux articles (deux prix, le client choisit). Le rapprochement
ne cherche donc que **dans le périmètre du fournisseur importé** (`supplier_name`),
par ordre de fiabilité, le premier résultat non ambigu gagne :

1. la ligne `SupplierProductMapping` (fournisseur, référence) ;
2. un article du fournisseur portant la même **référence** — synchronisé *ou saisi à
   la main et rattaché à ce fournisseur* (celui-ci est alors **adopté**) ;
3. le **code-barres** EAN/UPC (chiffres seuls ; UPC-A à 12 chiffres et EAN-13 avec zéro
   de tête équivalents ; une valeur en notation scientifique — Excel a converti la
   colonne en nombre — est ignorée) contre `Product.ean` **et** `Product.upc` ;
4. **marque + référence fabricant**, sans tenir compte de la casse ni des espaces.

- *(30/09/2026 : l'adoption reste passive — elle n'arrive que si le fournisseur renvoie la référence ; « Rattacher maintenant » / « Détacher » prévus en Feuille de route R4 / S8.)*
- Reconnu par 3 ou 4 sous une nouvelle référence : la référence est réalignée sur le
  fichier et la ligne de mapping existante est re-clée (pas de doublon de mapping).
- **Adoption d'un article manuel** : il passe `is_supplier_managed`, le fichier apporte
  référence, coût, devise, stock ; son contenu (nom, descriptions, image, mode de prix,
  prix fixé, marge, douane, catégorie, poids, dimensions, origine) est **verrouillé**
  (`overridden_fields`) au moment de l'adoption, donc jamais écrasé par cet import ni
  par les suivants.
- **Ambigu** (plusieurs articles du fournisseur pour une même clé) : ni création ni mise
  à jour ; la ligne est rapportée (simulation et import) avec les candidats.
- La **simulation** (« Simuler » dans Admin → Fournisseurs) affiche par ligne : nouveau /
  mise à jour / adopté / ambigu, et la clé qui a reconnu l'article. Mêmes règles pour la
  sync API (Ingram fournit UPC, marque et référence fabricant).
- Index ajoutés sur `products.ean`, `products.upc`, `products.vendor_part_number`.
- **Vitrine « autres offres »** (livré le 05/09/2026) : les doublons inter-fournisseurs
  restent des articles distincts en base, mais la vitrine les présente comme un seul
  produit. Clé de regroupement (`product_identity_key`) : code-barres canonique (EAN
  puis UPC, zéros de tête ignorés), sinon marque + référence fabricant.
  - `POST /product/search` regroupe par défaut (`group_offers=true`) derrière l'offre
    la moins chère (à prix égal, celle en stock) et renvoie `offers_count` ; la carte
    catalogue affiche « N offres ».
  - `GET /product/{id}/offers` liste toutes les offres du même article (fournisseur,
    régime local/import, prix au niveau de service par défaut, stock) triées par prix ;
    la page produit et le dialogue de détail affichent la section « Autres offres »
    avec « Meilleur prix ». Un article dont le code-barres diffère n'est jamais une
    autre offre, même à référence fabricant égale.

### Origine (`Place`) et modes de prix : hiérarchie (fusion du 06/09/2026)

La branche « entrepôt principal / régime douanier d'origine » (`a7f12ba`, `Place.customs_regime`,
`customs_free_countries`, `shipping/services/origin.py`) et la branche « fournisseurs en base /
modes de prix » disaient la même chose par deux chemins. Règle retenue, appliquée partout
(`calculate_sale_price`, `PricingContext.price`, `publication_conditions` / `publication_blockers`,
snapshot de ligne et frais de déclaration du panier via `product_applies_customs`) :

1. `pricing_mode = fixed` gagne toujours : `base_price` TTC, ni douane, ni marge, ni taxe, jamais
   de frais de déclaration.
2. `pricing_mode = domestic` : override produit — coût × marge × taxe, quel que soit le lieu
   fournisseur.
3. `pricing_mode = import` (défaut de schéma, donc **pas** une décision) : le **lieu fournisseur**
   (`Product.supplier_place_id` → `Place`) tranche via `resolve_origin_regime` — même pays que
   l'entrepôt principal, pays exempté ou `customs_regime = 'domestic'` ⇒ prix et publication
   **locaux** ; sinon CAF + douane ; origine inconnue ⇒ douane (comportement historique).
   Le `PricingContext` précharge les lieux et l'entrepôt principal (deux requêtes par contexte),
   donc `sale_price_cached` et la recherche donnent le même prix que le panier.
4. `Supplier.is_domestic` reste un pré-remplissage de `pricing_mode` à la création d'un article
   (admin, import fichier, sync) ; la vérité douanière d'un article `import` est son `Place`.

Alembic : la révision `e1f7a3c9b5d2` a été **re-parentée** sur `a7d2e9f4b1c6` (les deux côtés
avaient fusionné les trois mêmes têtes du 04/09 ; celle de main, `e2b7c4d9a1f3`, fait foi).
Chaîne : `… → e2b7c4d9a1f3 → f3c8d5e2b7a4 → a7d2e9f4b1c6 → e1f7a3c9b5d2 → f2b8d4a6c1e3 → a7c3e9f1b2d4`.
**Toute base de développement qui avait déjà appliqué `e1f7a3c9b5d2` avant cette fusion doit être
recréée** (`alembic upgrade head` la croirait à jour sans les colonnes `places.*` /
`shipping_routes.*` de main).

### Recherche vitrine à l'échelle (livré le 05/09/2026)

**Constat.** `POST /product/search` chargeait toutes les lignes passant le filtre SQL,
tarifait chacune à la volée (3 à 5 requêtes par produit : catégorie, taxe, change),
filtrait prix et specs en Python, regroupait les « autres offres » en mémoire, calculait
les facettes sur l'ensemble, puis découpait la page : un coût proportionnel au nombre de
produits filtrés, pas à la page (plusieurs secondes vers 3 000 produits). Trois niveaux,
livrés ensemble :

1. **Référentiels préchargés — `PricingContext`** (`product/services/pricing.py`).
   Groupe tarifaire, taxes, taux de change et catégories lus en quatre requêtes, puis
   même formule et même ordre de résolution que `calculate_sale_price` (qui reste la
   référence : parité vérifiée au centime par un test d'intégration). Un contexte par
   requête ou par sync (`for_session`, cache d'une minute sur la session) : `read`,
   `read_multi`, `get_featured`, `GET /product/{id}/offers` et les hooks d'écriture
   passent par lui.
2. **Clé d'identité en colonne — `products.identity_key`** (indexée). Posée par des
   écouteurs ORM `before_insert` / `before_update` (`product_identity_key`), donc tenue
   à jour par toutes les voies d'écriture ; remplie pour l'existant par la migration
   `a7c3e9f1b2d4` (lots de 1 000). `find_offers` et le regroupement de la recherche
   lisent la colonne.
3. **Prix vitrine matérialisé — `products.sale_price_cached` (+ `_at`)** et recherche
   100 % SQL. Sémantique : le prix de liste (sans tronçon import ; la fiche produit
   garde ses niveaux de service à la volée, le checkout recalcule et reste autoritaire).
   - Posé à **chaque écriture produit** par `ProductCrud.after_create` / `after_update`
     (sync inventaire, import fichier, sync catalogue, écrans admin, affectation
     taxe/douane à un produit — qui passe désormais par le CRUD).
   - **Quand un paramètre change** : `app/tasks/pricing_tasks.py` — tâche
     `refresh_sale_prices_task` (lots de 500, un contexte, un commit par lot), enfilée
     avec dédup Redis par `schedule_price_refresh` (best-effort : une panne de file
     ne fait jamais échouer l'édition) depuis création/clôture d'une taxe, nouveau taux
     de change (tout le catalogue), taxe / douane / marge par défaut d'une catégorie et
     fusion de catégories (catégorie ciblée). Cron `sale_price_nightly_refresh` à
     00:05 : les `valid_from` / `valid_until` changent le prix sans aucune écriture.
   - **Repli** : une ligne encore à `NULL` qui atterrit dans la page est tarifée à la
     volée (≤ 24 produits) et persistée par une connexion séparée (la transaction de la
     requête n'est pas touchée) ; en SQL elle trie en dernier.
   - **Recherche** : filtres (dont `sale_price_cached BETWEEN`, specs par `EXISTS` sur
     `product_specs`), `DISTINCT ON (coalesce(identity_key, id))` trié prix croissant /
     en stock d'abord pour ne garder que l'offre la moins chère, `count() over
     (partition by …)` pour `offers_count`, `count(*)` puis page `ORDER BY rank,
     created_at LIMIT/OFFSET`, facettes en trois agrégats (fabricants regroupés par
     `lower(trim())`, catégories, tranches de prix par `CASE`). Contrat de
     `POST /product/search` inchangé (`data`, `count`, `facets`, `offers_count`).
   - Endpoint de maintenance `POST /suppliers/admin/refresh-prices?category_id=`
     (inline, superuser) : **à lancer une fois après le déploiement** pour le premier
     remplissage — tant que les prix ne sont pas matérialisés, le filtre prix et le
     choix de l'offre la moins chère ne voient que des `NULL`.

**Changements assumés.**
- Un produit sans code-barres (clé `mpn:`) ne se regroupe qu'avec des produits sans
  code-barres ; à code-barres égal, la clé ne regarde plus la référence fabricant.
- Fin de la recherche floue dans le JSON brut Icecat (`_matches_specs`) : les filtres
  `specs` lisent la projection `product_specs` (mêmes clés que `spec-facets`) ; un
  produit non projeté n'est pas filtrable par spec (`POST /suppliers/admin/reproject-specs`).
- Le prix de liste peut retarder d'au plus une minute (cache du contexte) après la
  modification d'un taux, et jusqu'au passage de la tâche de rafraîchissement pour les
  produits non réécrits.

**Tests.** Unitaires : `test_pricing_context.py` (modes, chaîne de résolution, devise,
cache), `test_pricing_tasks.py` (dédup, best-effort, hooks admin), écouteurs
`identity_key` ; la suite tourne sans Redis grâce à la file ARQ factice autouse
(`tests/utils/fake_arq.py`). Intégration : `test_sale_price_cache.py` (parité, hooks
CRUD, tâche après changement de taux), `test_product_search_sql.py` (filtres prix /
stock / specs, regroupement, pagination, facettes, repli `NULL`), `test_product_offers.py`
adapté.

### Ajouter un fournisseur

| Cas | Marche à suivre |
|-----|-----------------|
| Générique (Europe, sans API) | Admin → Fournisseurs → nouveau, méthode *Générique*, entrepôt d'origine `FR_SUPPLIERS`, régime import. Puis articles saisis à la main avec coût + devise (la douane part du coût, comme aujourd'hui). |
| Distributeur local (Tahiti) | Même écran, régime **local** (`is_domestic`), lieu = son dépôt. Articles en `domestic` (coût + marge) ou `fixed` (prix TTC). |
| Fichier CSV / Excel | Méthode *Fichier*, puis bouton *Importer* : le fichier est lu, les colonnes proposées, la correspondance enregistrée, *Simuler* puis *Importer*. |
| Nouvelle API | Implémenter `SupplierAdapter` (`app/services/suppliers/<nom>.py`), l'enregistrer dans `ADAPTERS`, déclarer ses secrets dans `config.py`, puis créer la ligne `kind=api` avec cet `adapter_key`. |

### Reste à faire

> Chiffré et complété le 30/09/2026 dans *Feuille de route 30/09*, **R4** (seuil de quantité à l'import fichier S2, flux fichier automatisé S3, correctifs de désactivation S1, commande fournisseur généralisée S4).

- Adresse « ship-to » des bons de commande Ingram : toujours `INGRAM_SHIP_TO_*` ; à déplacer vers l'entrepôt principal (`Place`) quand la commande fournisseur sera généralisée aux autres fournisseurs (`supplier_order_service` reste spécifique Ingram).
- Stratification du rafraîchissement des prix (voir *Rafraîchissement stratifié*) : le tick inventaire enfile tous les fournisseurs à la même cadence.
- ✅ Import fichier volumineux (10/09/2026) : au-delà de `SUPPLIER_FILE_IMPORT_INLINE_MAX_ROWS` (2 000 lignes) le fichier est déposé dans le stockage et importé par le job ARQ `import_supplier_file_task` ; l'admin suit le journal de synchronisation (`GET /suppliers/{code}/import-file/{sync_log_id}`). Plafond `SUPPLIER_FILE_IMPORT_MAX_ROWS` (250 000).

---

## Décision transverse : catalogue de spécifications filtrables

**Contexte** : Icecat renvoie les spécifications techniques dans une structure JSONB hétérogène (`name` varie selon le produit et la langue : « Mémoire installée », « RAM », « System Memory »…). Une requête frontend « memory_gb ≥ 16 » ne peut pas pointer directement vers une clé Icecat fiable. Une couche de normalisation backend est nécessaire — le frontend ne devine rien, il consomme un endpoint de facettes.

### Modèle de données

| Source | Rôle |
|--------|------|
| `spec_definitions.yaml` (versionné dans le code) | Catalogue P1 : clé canonique + label_fr + type + unit + aliases Icecat + catégories applicables |
| `product_spec` (table normalisée) | `id`, `product_id: UUID` (FK), `spec_key: str`, `value_text: str \| null`, `value_numeric: Decimal \| null`, `unit: str \| null` |
| `Product.technical_specifications` (JSONB existant) | Conservé pour affichage fiche produit (liste complète, ordre d'origine, libellés bruts) |

### Indices

- `idx_product_spec_key_numeric` sur `(spec_key, value_numeric)` — filtres numériques.
- `idx_product_spec_key_text` sur `(spec_key, value_text)` — filtres énumérés.
- `idx_product_spec_product` sur `product_id` — fetch par produit.

### Catalogue P1 — catégorie « Ordinateur/Serveur »

10 specs canoniques :

| Key | Type | Unit | Aliases Icecat (exemples) |
|-----|------|------|---------------------------|
| `cpu_brand` | enum | — | Marque du processeur, Processor Brand |
| `cpu_family` | enum | — | Famille de processeur, Processor Family |
| `cpu_cores` | numeric | — | Nombre de cœurs, Number of Cores |
| `memory_gb` | numeric | GB | Mémoire installée, RAM, System Memory |
| `storage_gb` | numeric | GB | Capacité du SSD, Capacité du HDD, Total Storage |
| `storage_type` | enum | — | Type de disque, Storage Drive Type |
| `screen_inches` | numeric | inch | Taille de l'écran, Display Size |
| `gpu_brand` | enum | — | Marque carte graphique, Graphics Adapter Brand |
| `os` | enum | — | Système d'exploitation, Operating System |
| `form_factor` | enum | — | Type de châssis, Form Factor |

### Projection

À chaque enrichissement Icecat d'un produit (`enrich_product_with_icecat_task`) :

1. Parse `technical_specifications` JSONB.
2. Match insensitive de `name` contre les `aliases` du YAML.
3. Normaliser la valeur :
   - **numeric** : extraire la partie chiffrée (`"16 GB"` → `16`), convertir l'unit si nécessaire.
   - **enum** : appliquer la fonction de normalisation par spec (`"Intel® Core™ i7-1260P"` → `i7`).
4. Upsert ligne `product_spec(product_id, spec_key, value_numeric|value_text, unit)`.
5. Specs non reconnues : ignorées au filtre mais conservées dans le JSONB pour la fiche produit.

### Affichage public

- Produit **non enrichi** (`is_enriched=False`) → **exclu** de la vitrine. Filtre `is_enriched=True` appliqué dans tous les endpoints catalogue publics : `POST /product/search`, `GET /product/featured`, `GET /products`, `GET /product/{id}` (404 si non enrichi).
- Produit enrichi sans spec reconnue → affiché, mais non filtrable par spec.
- Enrichissement enqueué **automatiquement** à la création d'un nouveau `is_supplier_managed=True` dans `SupplierSyncOrchestrator.upsert_product` (en plus du batch hebdo).

### Re-projection

Job ARQ `reproject_product_specs(category_id=None)` qui re-applique le YAML sur tous les produits enrichis. À déclencher après chaque ajout/modification d'alias.

### Jalons par phase

| Phase | Livrable specs |
|-------|----------------|
| **1** | Table `product_spec` + indices ; `spec_definitions.yaml` (10 specs Ordinateur/Serveur) ; projection au sein de `enrich_product_with_icecat_task` ; endpoint `GET /categories/{id}/spec-facets` ; `POST /product/search` interprète le payload `specs:` ; filtre `is_enriched=True` sur endpoints publics ; enqueue auto à la création d'un produit supplier_managed ; job `reproject_product_specs` |
| **3** | Extension multi-catégories ; migration YAML → table DB `spec_definition` éditable via admin (UI) ; gestion alias par catégorie |
| **5** | (Optionnel Z4) recherche sémantique IA sur la même couche normalisée |

---

## Décision transverse : précommande, départs groupés et acompte (24/09/2026)

**Contexte.** Le document « Spécifications site : précommande et commande groupée » (24/09/2026) décrit un modèle « vendre avant d'acheter » : paiement à la commande, regroupement des commandes par vague (date de clôture → une commande fournisseur → un groupage → une livraison), aucun stock spéculatif. Il liste 12 points bloquants pour la première vague et 10 points souhaitables. Le propriétaire a demandé (1) un état des lieux fonction par fonction, (2) la faisabilité d'un **acompte à la commande** (50 % / 30 % selon le type de client, frais optionnels), (3) une **date de prochaine livraison affichée en vitrine** servant à regrouper les commandes, (4) des **rappels automatiques sur les réseaux sociaux** avant un départ, le tout **regroupé au maximum** pour rester simple à administrer.

Tout ce qui suit a été vérifié dans le code (tête = merge de PR #98), pas seulement dans ce document.

### État des lieux — points bloquants de la spec

| # | Point bloquant | État | Constat |
|---|---|---|---|
| B1 | Produit vendable à stock 0 (précommande) | ❌ | Le produit à `supplier_quantity = 0` reste visible et affiche « Sur commande », mais la vitrine grise le bouton ([ProductCard.vue](frontend/src/components/ProductCard.vue), [ProductPage.vue](frontend/src/pages/ProductPage.vue)) et le checkout renvoie 409 `cart.stock.insufficient` ([cart.py](backend/app/api/routes/cart.py), `_reserve_stock_for_checkout`). Aucun flag de précommande. |
| B2 | Quantité fixe qui se décrémente (lot reconditionné) | 🟡 | `Inventory` (produit × lieu), mouvements, réservation au checkout, confirmation au paiement, libération à 48 h ([features/inventory](backend/app/features/inventory), [inventory_tasks.py](backend/app/tasks/inventory_tasks.py)). Mais le checkout ne lit que la ligne `place_id=None` ([inventory_crud.py](backend/app/features/inventory/crud/inventory_crud.py)), pas de notion de lot (grade, garantie, coût du lot), et la vitrine ignore le stock local. |
| B3 | Prix de vente calculé par règle depuis le coût | ✅ | [pricing.py](backend/app/features/product/services/pricing.py) : 3 modes (`import` CAF → douane → marge → taxe, `domestic`, `fixed`), prix matérialisé `sale_price_cached`, recalcul en masse ([pricing_tasks.py](backend/app/tasks/pricing_tasks.py)) sur changement FX / taxe / marge catégorie / douane, nuit, `POST /admin/refresh-prices`. |
| B4 | Encaissement à la commande (CB + virement validé) | ✅ | PayZen (capture immédiate ou différée), virement / chèque / bon de commande avec validation admin ([manual_payment.py](backend/app/features/payment/services/manual_payment.py), [document_payment.py](backend/app/features/payment/services/document_payment.py), [admin_payments.py](backend/app/api/routes/admin_payments.py)). |
| B5 | Commandes regroupables par vague, ou filtrables par date | ❌ | Aucun objet vague / clôture. `GET /admin/orders` n'a aucun filtre ([admin_orders.py](backend/app/api/routes/admin_orders.py) : `skip`/`limit`). Le seul regroupement est logistique, par tronçon (`ShippingRouteTrackingConsolidation`), sans date de clôture. |
| B6 | Statuts de commande personnalisables | 🟡 | `OrderStatus` est une table (créée à la volée par nom), CRUD générique. Mais aucune machine à états commande, pas d'écran admin, et le backend ne pose que `Pending / AwaitingPayment / Paid / PaymentFailed / PaymentReview / Refunded / PartiallyRefunded` ([handlers/payment.py](backend/app/handlers/payment.py)). `Processing / Shipped / Delivered / Cancelled` n'existent que comme libellés admin. |
| B7 | E-mail à chaque changement de statut | 🟡 | E-mails sur `order.created`, `payment.captured/rejected/refunded`, `invoice.issued` ([handlers/order.py](backend/app/handlers/order.py)) et `tracking.status_changed` ([handlers/shipping.py](backend/app/handlers/shipping.py)). Rien sur un statut de commande générique. Modèles Jinja statiques ([templates/email/fr](backend/app/templates/email/fr)), non éditables en admin. |
| B8 | Remboursement total depuis le back-office | ✅ | Total / partiel + avoir automatique ([refund_service.py](backend/app/features/payment/services/refund_service.py), [credit_note.py](backend/app/features/invoice/models/credit_note.py)). ⚠️ PayZen : remboursement `pending`, API `cancelOrRefund` non branchée ni testée en sandbox. |
| B9 | Export des commandes d'une période agrégé par SKU | ❌ | Aucun export commandes ni agrégation. Seuls exports : factures / avoirs CSV, FEC. |
| B10 | Ingram : pas de publication de tout le catalogue, n'écrase pas le prix de vente | 🟡 | N'écrit que coût / prix fournisseur / stock ✅. Filtrage par catégorie + allowlist sous-catégories (env, pas d'UI) ; liste blanche de SKU par fournisseur ✅ (26/09, Lot D : `Supplier.sku_allowlist`, voir l'avancement plus bas) ; import en brouillon ✅ (26/09, Lot D : `Supplier.import_as_draft`, publication depuis la page Articles). |
| B11 | Import CSV : mapping par fournisseur, pas de doublons | 🟡 | Mapping mémorisé sur `Supplier.column_mapping` ✅, simulation ✅, unicité sur `supplier_product_mappings` ✅ mais pas sur `products` ; lignes rejetées renvoyées dans la réponse HTTP seulement, non journalisées. |
| B12 | CGV et « Comment ça marche » modifiables | ❌ | Pages Vue codées en dur ([frontend/src/pages/legal](frontend/src/pages/legal)). Pas de page « Comment ça marche », pas de contenu éditable. |

**Bilan : 3 ✅, 5 🟡, 4 ❌.** La spec admet une première vague en mode manuel (tableur, e-mails) si l'encaissement et le calcul du prix rendu sont automatiques — ce sont précisément les deux ✅.

### État des lieux — points souhaitables et ajouts du propriétaire

| Point | État | Constat |
|---|---|---|
| Objet « vague » natif | ❌ | Rien ; `ShippingRoute.frequency_days` / `departure_time` existent mais ne sont lus nulle part. Devient l'objet unique « Départ groupé » ci-dessous. |
| Date de prochaine livraison en vitrine (ajout) | ❌ | Aucune date de départ ni bandeau ; seul `ShippingRoute.eta_days` au checkout. Le mécanisme de clés publiques de [system_settings.py](backend/app/api/routes/system_settings.py) est réutilisable pour l'exposer. |
| Rappels réseaux sociaux (ajout) | ❌ | Aucune intégration sociale. Briques : webhook Slack-like ([alerting.py](backend/app/core/alerting.py)), provider Slack ([slack_webhook.py](backend/app/features/notification/providers/slack_webhook.py)), crons ARQ. |
| Acompte + solde, lien de paiement | ❌ | Voir plus bas : faisable, mais trois gardes imposent « montant payé = total ». |
| Devis PDF depuis le panier (B2B) | 🟡 | `QuoteRequest` + écran admin ✅ ; pas de PDF, de numérotation, ni de conversion en commande. Moyen « Bon de commande » avec pièce jointe ✅. |
| Changement de statut en masse | ❌ | Seulement `ship-all / advance-all / deliver-all` sur une consolidation logistique. |
| Remboursement partiel et avoir | ✅ / 🟡 | Partiel ✅, avoir comptable ✅ ; avoir-crédit utilisable sur une prochaine commande ❌. |
| Réception, pointage par SKU, n° de série | ❌ | Aucun modèle de réception ni numéro de série. |
| Tableau de bord de marge par vague | ❌ | Tables `analytics_*` sans logique. Base utilisable : snapshots `cost_amount_snapshot`, `fx_rate_used`, `customs_rate_pct_snapshot`, `margin_rate_pct_snapshot` sur `OrderLine`. ⚠️ bug : `margin_rate_pct_snapshot` stocke la marge du groupe, pas celle appliquée produit → catégorie → groupe ([cart.py](backend/app/api/routes/cart.py), snapshot des lignes). |
| SMS / WhatsApp, « me prévenir », suivi sans compte | ❌ | Rien. |
| Recalcul des prix en masse | ✅ | Manque un déclencheur sur modification d'une `ShippingRoute` ou d'un `PriceGroup`. |

Autres écarts relevés : commission paiement en % intégrée au prix (aujourd'hui `PaymentMethod.fee` fixe ajouté au panier), marge de sécurité FX, frais fixes par vague répartis, journal des prix, arrondi commercial ; la sync prix/dispo Ingram ignore `overridden_fields` ([supplier_tasks.py](backend/app/tasks/supplier_tasks.py)) contrairement à la sync catalogue ; la fiche commande admin renvoie le statut du dernier paiement à la place de celui de la commande (`status_name` écrasé dans [admin_orders.py](backend/app/api/routes/admin_orders.py)) ; `add_tracking_to_consolidation` ne décrémente pas `total_orders` de l'ancien lot.

### Décision : un objet unique « Départ groupé »

**Principe** : regrouper au maximum. Un seul objet, **`GroupedDeparture`** (= la « vague » de la spec), porte la date affichée en vitrine, le rattachement des commandes, les rappels réseaux sociaux et le statut propagé aux commandes. Un seul écran admin « Départs groupés » (nav Commandes) remplace quatre écrans possibles (vague, filtre commandes, statuts en masse, publications). Aucun réglage dispersé dans « Paramètres ».

| Champ | Rôle |
|---|---|
| `name` | « Départ d'octobre » |
| `order_cutoff_at` | date limite de commande — **la date affichée en vitrine** (« Commandez avant le 15/10 ») |
| `estimated_delivery_at` | date de remise estimée, mise à jour à chaque changement de statut |
| `departure_at` (optionnel) | départ physique si différent de la clôture (ancre des rappels « plus que N jours ») |
| `status` | `draft → open → closed → ordered → in_transit → at_customs → received → distributed` |
| `is_published` | visible en vitrine ; un seul départ publié et ouvert à la fois (index unique partiel) |
| `min_amount`, `min_units` | seuil de report (optionnels) |
| `recurrence_days` | à la clôture, crée automatiquement le départ suivant, publié, rappels recopiés |
| `notes`, `consolidation_id` | lien vers la `ShippingRouteTrackingConsolidation` existante pour le transport |

- `Order.grouped_departure_id` (FK nullable). `ShippingRoute.frequency_days` / `departure_time` sont remplacés par ce modèle.
- **Rattachement** : automatique au checkout sur le départ ouvert et publié à la clôture la plus proche (bascule sur le suivant passé la clôture) ; aucun départ ouvert = commande non rattachée, boutique classique inchangée. Manuel : « Rattacher / déplacer vers… » (sélection multiple) depuis la fiche commande et l'écran du départ ; `GET /admin/orders?departure_id&from&to` pour filtrer par départ **ou** par dates si l'admin préfère rester manuel. Virement non validé à la clôture : signalé dans un onglet « à arbitrer » (exclure / reporter).
- **Vitrine** : `GET /grouped-departures/next` public → bandeau accueil et catalogue (« Prochain départ : commandes jusqu'au 15/10, livraison estimée semaine du 10/11 », compte à rebours), fiche produit (« Sur commande — livraison estimée le JJ/MM »), panier, checkout, e-mail de confirmation, espace client.
- **Écran admin**, trois onglets par départ : **Fiche** (dates, publication, seuil, récurrence, bouton « étape suivante » qui propage le statut à toutes les commandes → e-mails, pattern `advance-all` de [admin_shipping.py](backend/app/api/routes/admin_shipping.py)) ; **Commandes** (liste, déplacer, exclure, export CSV brut, récap agrégé fournisseur × SKU = bon de commande, bouton « Créer la consolidation logistique ») ; **Rappels** (ci-dessous).

**Rappels automatiques sur les réseaux sociaux** (non essentiel, utile pour les départs récurrents) :
- `DepartureReminder(grouped_departure_id, offset_days, anchor ∈ cutoff|departure, channel, message_template, image_url, status ∈ scheduled|sent|failed, scheduled_at, sent_at, error)`. Gabarits avec `{name}`, `{cutoff_date}`, `{days_left}`, `{delivery_date}`, `{shop_url}`. Défauts à la création d'un départ : J-7, J-2, dernier jour, désactivables.
- Cron ARQ `publish_due_departure_reminders` toutes les 15 min, idempotent sur `status`.
- Canaux par étapes : (1) **webhook générique** vers Make / Zapier / Buffer / IFTTT (`{text, image_url, link}`) qui publient sur Facebook, Instagram, WhatsApp Business — pas de revue d'application Meta ni de jeton à renouveler, l'admin colle une URL ; (2) **e-mail** aux clients ayant opté (préférences `notification_*` existantes, provider Mailgun) ; (3) plus tard, API Graph Facebook/Instagram directe comme provider supplémentaire du même registre.
- Onglet « Rappels » : liste avec aperçu du texte rendu, « Publier maintenant », historique envoyé / échec, configuration du canal au même endroit. Garde-fous : jamais de publication pour un départ `draft` ou non publié, pas d'envoi rétroactif, échec → alerte admin via `send_alert`.

### Ordre de construction

**Lot A — première vague** : (0) socle Départ groupé (modèle, migration, rattachement au checkout, endpoint public, bandeau + fiche produit + checkout, écran admin onglets Fiche et Commandes avec filtre, déplacement, export CSV, récap par SKU — couvre B5 et B9) ; (1) précommande B1 : `Product.availability_mode ∈ on_demand | lot | continuous`, bouton actif, `_plan_checkout_fulfillment_segments` accepte le manque de stock pour ces modes (garde : stock fournisseur > 0 au dernier refresh pour `on_demand`) ; (2) lot reconditionné B2 : stock `Inventory` sur un `Place` « transit », checkout lisant tous les lieux entrepôt, « X exemplaires restants » en vitrine, champs `condition_grade`, `battery_health`, `os_licence`, `warranty_months`, colonnes CSV correspondantes + option d'import « lot » ; (3) statuts B6/B7 : seed des statuts métier (`AwaitingDeparture`, `OrderedFromSupplier`, `InTransit`, `AtCustoms`, `Received`, `ReadyForPickup`, `Backordered`), `POST /admin/orders/{id}/status` pour le cas isolé, bouton « étape suivante » du départ pour la masse, événement `order.status_changed` + e-mail par statut ; (4) pages éditables B12 (`ContentPage`, ou a minima page « Comment ça marche » statique) ; (5) corrections : `margin_rate_pct_snapshot`, verrous admin dans la sync prix/dispo, `status_name` écrasé, journal des rejets CSV.

#### ✅ Avancement — Lot A item 0 : socle « Départ groupé » (24/09/2026)

- **Backend** : modèle `GroupedDeparture` + table `grouped_departures` ([departure/models.py](backend/app/features/departure/models.py) : nom, `order_cutoff_at`, `estimated_delivery_at`, `departure_at`, statut validé parmi `DEPARTURE_STATUSES`, `is_published`, seuils, `recurrence_days`, `consolidation_id`) ; `Order.grouped_departure_id` (FK nullable, migration `b9e4d2c7a1f5`, réversible). CRUD + résolveur `get_next_open` (départ ouvert, publié, clôture future la plus proche) et `assign_orders` ([departure/crud.py](backend/app/features/departure/crud.py)).
- **Checkout** : la commande est rattachée au départ ouvert au moment de sa création ([cart.py](backend/app/api/routes/cart.py)) ; `CheckoutResponse.grouped_departure_id`. Sans départ ouvert : `null`, comportement inchangé.
- **Public** : `GET /grouped-departures/next` et `GET /grouped-departures/{id}` (publiés seulement, schéma `GroupedDepartureSummary` sans colonnes d'audit) ([grouped_departures.py](backend/app/api/routes/grouped_departures.py)).
- **Admin** : `GET/POST /admin/grouped-departures`, `PATCH/DELETE /{id}` (suppression refusée tant que des commandes sont rattachées), `POST /assign-orders` (rattacher / déplacer / détacher) ([admin_grouped_departures.py](backend/app/api/routes/admin_grouped_departures.py)). Les commandes d'un départ passent par les endpoints commandes **filtrés** : `GET /admin/orders?departure_id|unassigned|status|date_from|date_to`, `GET /admin/orders/export.csv` (brut) et `GET /admin/orders/sku-summary[.csv]` (agrégation fournisseur × SKU = bon de commande, item **B9**) — même clause `_order_filters` pour les trois ([admin_orders.py](backend/app/api/routes/admin_orders.py)) ; helper CSV réutilisable [utils/csv_export.py](backend/app/utils/csv_export.py). Couvre **B5**.
- **Vitrine** : store `departure` chargé par le layout ; bandeau « Prochain départ groupé » ([NextDepartureBanner.vue](frontend/src/components/NextDepartureBanner.vue)), rappel sur la fiche produit, la carte produit, le récapitulatif et la confirmation du checkout, carte « Départ groupé » sur le suivi de commande. Libellés partagés dans [shared/utils/src/departure.ts](shared/utils/src/departure.ts) (compte à rebours, statuts, étape suivante).
- **Admin front** : page **Départs groupés** ([GroupedDeparturesPage.vue](admin-frontend/src/pages/GroupedDeparturesPage.vue)) — liste (statut, publication, nb et total des commandes, bouton « étape suivante » sur le statut du départ), fiche en dialogue, commandes du départ avec déplacement multiple, export CSV, tableau et CSV du bon de commande par SKU ; filtre « Départ groupé » + numéro de commande sur la liste des commandes ; sélecteur de départ sur la fiche commande.
- **Tests** : 7 tests (4 unitaires sans base : parité AST du checkout, validateur de statut, helpers CSV ; 3 d'intégration : résolveur, cycle admin + rattachement, filtres / export / récap SKU / endpoints publics) + 4 tests vitest des libellés partagés. Les tests mockés du checkout patchent désormais `crud_grouped_departure.get_next_open` comme `resolve_default_price_group`. Types OpenAPI régénérés.
- **Reste pour l'item 0** : la propagation du statut du départ aux commandes rattachées (et ses e-mails) relève de l'item 3 (statuts commande + `order.status_changed`) — aujourd'hui le bouton « étape suivante » ne change que le statut du départ.

#### ✅ Avancement — Lot A item 1 : précommande à stock zéro (25/09/2026)

- **Modèle** : `Product.availability_mode` ∈ `stock` (défaut, comportement historique : le stock local + fournisseur doit couvrir la quantité et est réservé) · `on_demand` (« sur commande » : commandable tant que le fournisseur affiche du stock au dernier rafraîchissement, **sans réservation**, acheté à la clôture du départ groupé) · `continuous` (toujours commandable, sans contrôle de stock). Enum non natif comme `pricing_mode`, migration `c2f7a9d4e6b1` (défaut `'stock'` pour tout l'existant, réversible) ([product.py](backend/app/features/product/models/product.py)).
- **Checkout** ([cart.py](backend/app/api/routes/cart.py)) : `_plan_checkout_fulfillment_segments(backorder=…)` laisse le segment fournisseur prendre ce que le stock local ne couvre pas ; `_reserve_stock_for_checkout` ne décrémente pas `supplier_quantity` et n'écrit aucun mouvement pour ces modes (une libération de commande impayée aurait gonflé un instantané que la sync réécrit) ; garde `cart.stock.unavailable` (409) pour `on_demand` à stock fournisseur nul. La vérification temps réel de la dispo fournisseur au checkout s'applique toujours. **Couvre B1.**
- **Vitrine** : util [availability.ts](frontend/src/utils/availability.ts) (`orderable`, `preorder`, libellé) partagé par la carte, la fiche et le dialogue produit : « Sur commande » avec bouton **actif** pour `on_demand` (stock > 0) et `continuous` ; « N en stock » sinon ; « Indisponible » et bouton grisé pour un produit `stock` à zéro (le libellé « Sur commande » sur un bouton grisé disparaît).
- **Admin** : groupe d'options « Disponibilité » dans le formulaire produit ([ProductFormDialog.vue](admin-frontend/src/components/ProductFormDialog.vue)) avec aide par mode. La sync fournisseur ne porte pas ce champ, elle ne l'écrase donc pas.
- **Tests** : 5 unitaires backend ([test_checkout_backorder.py](backend/app/tests/api/test_checkout_backorder.py) : planification avec/sans backorder, `on_demand` au-delà du stock sans réservation, garde stock nul, `continuous` sans stock, mode `stock` inchangé) + 4 vitest de l'util vitrine. Types OpenAPI régénérés.
- **Reste** : réglage du mode **par catégorie** (défaut hérité) et colonne dans l'import CSV — à faire avec l'item 2 (lot reconditionné) qui ajoute les colonnes fichier ; le filtre vitrine `in_stock` reste « stock fournisseur > 0 ».

#### ✅ Avancement — Lot A item 2 : lot reconditionné, neuf vs reconditionné (25/09/2026)

- **Modèle** ([product.py](backend/app/features/product/models/product.py)) : `Product.condition` ∈ `new` (défaut, tout l'existant) | `refurbished` (enum non natif, indexé) + `condition_grade`, `battery_health_pct`, `os_licence`, `warranty_months` ; `availability_mode` gagne **`lot`**. Migration `d4a8c1e7f2b9` (réversible).
- **Décision (écart au plan, moins de code)** : le lot n'utilise pas l'inventaire par lieu mais **`supplier_quantity` comme taille du lot** — c'est déjà la quantité exposée en vitrine, réservée au checkout, confirmée au paiement et libérée si impayé ([stock_release.py](backend/app/features/inventory/services/stock_release.py)). Au checkout, `lot` suit la règle de `stock` (doit couvrir, réservé, 409 sinon). Saisie en admin, la quantité est verrouillée (`overridden_fields`) donc jamais écrasée par une synchronisation. La lecture de l'inventaire de tous les entrepôts au checkout reste à faire (bug distinct, `place_id=None`).
- **Recherche vitrine** : filtre `condition` dans `ProductSearchRequest` → `search_products(condition=…)` ([product crud](backend/app/features/product/crud/product.py)).
- **Import fichier** : cibles de mapping `condition`, `condition_grade`, `battery_health_pct`, `os_licence`, `warranty_months`, `availability_mode` ([supplier.py](backend/app/features/integrations/models/supplier.py)) ; valeurs normalisées (« Reconditionné », « neuf », « lot »…) et rejets motivés ([file_import.py](backend/app/services/suppliers/file_import.py)) ; l'orchestrateur ne pose ces champs que si le fichier les porte, un catalogue sans ces colonnes ne réinitialise rien.
- **Vitrine** : badge **« Reconditionné · Grade A »** (orange) sur la carte, la fiche et le dialogue produit, badge discret « Neuf » sur fiche/dialogue ; bloc de détails (grade, batterie, licence, garantie) ; libellé de lot « X exemplaires restants sur ce lot » / « Lot épuisé » (bouton grisé) ; **filtre Tous / Neuf / Reconditionné** dans le catalogue, persisté dans l'URL (`cond=`). Helpers dans [availability.ts](frontend/src/utils/availability.ts).
- **Admin** : groupe « État » + champs reconditionné (affichés seulement si reconditionné) et option « Lot (quantité fixe) » dans le formulaire produit.
- **Tests** : import fichier (colonnes normalisées, valeurs refusées), filtre `condition` en intégration SQL, mode `lot` au checkout, 2 vitest (lot, condition). Types OpenAPI régénérés. **Couvre B2.**
- **Reste** : « Me prévenir pour le prochain lot » (Lot D), photos réelles téléversées (aujourd'hui URL), mode/état par défaut hérités de la catégorie. ~~Facettes de comptage neuf/reconditionné~~ ✅ 30/09/2026 (ci-dessous).

#### ✅ Stock « chez nous » / « chez le fournisseur » et neuf / reconditionné, visibles et filtrables (30/09/2026)

- **Demande** : la vitrine doit dire clairement si un article est en stock dans notre entrepôt ou seulement chez le fournisseur, et permettre de filtrer la recherche sur ce critère comme sur neuf / reconditionné.
- **API** : `ProductPublic` porte `stock_local` (ligne d'inventaire entrepôt, variantes comprises) et `stock_supplier` (stock fournisseur vendable, compté seulement si l'article a un fournisseur, variantes comprises) ; `available_quantity` = leur somme, inchangé ([availability.py](backend/app/features/inventory/services/availability.py), [variants.py](backend/app/features/product/services/variants.py) : `ChildrenStock`). Recherche : `ProductSearchRequest.stock` ∈ `local` | `supplier` (un article présent aux deux endroits sort dans les deux) ; facettes `stock` {local, supplier} et `conditions` {new, refurbished}, calculées sur les résultats filtrés (même règle que fabricants/catégories).
- **Vitrine** : carte et fiche affichent « En stock chez nous (N) » (point vert, + « + N chez le fournisseur » s'il y en a) ou « En stock chez le fournisseur (N) » (point orange, « Délai de livraison plus long ») ; la date du départ groupé n'est plus affichée pour un article servi depuis notre stock. La carte affiche toujours l'état (« Neuf » discret, « Reconditionné · Grade A » appuyé). Catalogue : filtre **Disponibilité** (Tous / En stock chez nous / En stock chez le fournisseur) avec compteurs, compteurs sur le filtre **État**, puces retirables, URL `stock=` ; correctif : le choix d'état ne mettait pas à jour la puce ni l'URL. Bloc « Autres offres » : même vocabulaire.
- **Tests** : intégration (filtre `stock`, facettes, variantes, `stock_local`/`stock_supplier`), 3 vitest, e2e `catalogue-stock.spec.ts` (seed : « Portable reconditionné E2E », stock fournisseur seul).
- **Limite** : le délai « plus long » n'est pas chiffré par article (il dépend du fournisseur et du départ) ; à brancher sur un délai par fournisseur si besoin.

#### ✅ Avancement — Lot A item 3 : statuts de commande métier, e-mails, propagation depuis le départ (25/09/2026)

- **Service** [order/services/status.py](backend/app/features/order/services/status.py) : catalogue des statuts (`PAYMENT_STATUSES` posés par le flux de paiement, `FULFILLMENT_STATUSES` posés par l'admin : `OrderedFromSupplier`, `InTransit`, `AtCustoms`, `Received`, `ReadyForPickup`, `Delivered`, `Backordered`, `Cancelled`), tous **seedés** de façon idempotente par `initial_data` ; `set_order_status` (no-op si identique, publie **`order.status_changed`** : ancien/nouveau statut, départ, motif, auteur) ; `propagate_departure_status` (statut du départ → statut des commandes : `ordered→OrderedFromSupplier`, `in_transit→InTransit`, `at_customs→AtCustoms`, `received→Received`, `distributed→ReadyForPickup`) qui ne touche que les commandes **payées ou déjà en route** — jamais les impayées, remboursées, livrées ou annulées. **Couvre B6.**
- **Endpoints** : `GET /admin/orders/statuses`, `POST /admin/orders/{id}/status` (cas isolé) ; le `PATCH /admin/grouped-departures/{id}` propage un changement de statut et renvoie `orders_updated` (cas de masse, un clic sur « étape suivante »). Les statuts d'exécution sont ajoutés aux statuts **non payables** de l'initiation de paiement.
- **E-mail client** ([handlers/order.py](backend/app/handlers/order.py), gabarits `order_status_changed.*`) : un gabarit, un titre et un message par statut d'exécution (`ORDER_STATUS_MESSAGES`), avec le nom du départ et la livraison estimée ; les statuts de paiement, déjà couverts par leurs propres e-mails, sont ignorés. **Couvre B7** pour les étapes du départ.
- **Admin** : sélecteur « Changer le statut » sur la fiche commande ; la page Départs groupés indique le nombre de commandes mises à jour. **Vitrine** : libellés et badges des nouveaux statuts dans l'espace client.
- **Tests** : 3 d'intégration (service + événement outbox, endpoint, propagation sélective et étapes sans effet), 3 unitaires du handler (contenu avec départ, un message par statut, silence sur les statuts de paiement). Types OpenAPI régénérés.
- **Reste** : modèles d'e-mail éditables en admin (Lot D), statut « rupture / report » à relier à la clôture assistée (Lot B), `Delivered` posé automatiquement par la livraison du dernier tronçon (aujourd'hui à la main ou via le suivi logistique).

#### ✅ Avancement — Lot A item 4 : pages éditables « Comment ça marche » et CGV (25/09/2026)

- **Modèle** `ContentPage(slug unique, title, body_html, is_published)` ([content/models.py](backend/app/features/content/models.py)), migration `e5b3d7a9c4f1`. Endpoints : `GET /pages/{slug}` (publié seulement, sans auth), `GET /admin/pages`, `PUT /admin/pages/{slug}` (création ou remplacement, slug validé), `DELETE /admin/pages/{slug}` ([content_pages.py](backend/app/api/routes/content_pages.py)).
- **Seed** : la page `comment-ca-marche` (principe des départs, paiement à la commande, étapes, délai 3 à 5 semaines, reconditionné signalé) est créée publiée une seule fois et **jamais réécrite** par un déploiement.
- **Vitrine** : composant [DbContentPage.vue](frontend/src/components/DbContentPage.vue) (préchargé en SSR, HTML assaini par DOMPurify, slot de repli) ; route `/comment-ca-marche` ; lien dans le bandeau « prochain départ » et dans le pied de page ; la page CGV codée en dur devient le **repli** d'une page `cgv` publiée depuis l'admin (supprimer la page rétablit le texte par défaut). **Couvre B12.**
- **Admin** : écran « Pages du site » (Système) avec éditeur riche `q-editor` (titres, listes, liens), brouillon / publiée, suppression.
- **Tests** : règle de slug, cycle création → brouillon invisible → publiée → suppression, seed idempotent qui respecte le texte du propriétaire. Types OpenAPI régénérés.
- **Reste** : mentions légales et confidentialité restent codées en dur (même mécanisme applicable : slugs `mentions-legales`, `confidentialite`) ; pas de téléversement d'images dans l'éditeur (URL seulement).

#### ✅ Avancement — Lot A item 5 : corrections relevées à l'audit (25/09/2026)

- **Snapshot de marge** : `OrderLine.margin_rate_pct_snapshot` reçoit désormais la marge **réellement appliquée** (produit → catégorie → groupe, via `resolve_margin_rate_pct`) et non celle du groupe tarifaire ([cart.py](backend/app/api/routes/cart.py)) — prérequis du tableau de bord de marge réelle (Lot C).
- **Verrous admin dans la sync prix/stock** : `sync_supplier_inventory_task` passe sa mise à jour par `strip_locked` comme la sync catalogue ([supplier_tasks.py](backend/app/tasks/supplier_tasks.py)) : une quantité de lot ou un coût saisis en admin ne sont plus écrasés toutes les deux heures.
- **Statut de commande écrasé** : la fiche commande admin renvoyait le statut du **dernier paiement** à la place de celui de la commande (variable réutilisée dans la boucle des paiements) ; corrigé ([admin_orders.py](backend/app/api/routes/admin_orders.py)).
- **Journal des rejets d'import** : les lignes refusées (numéro, motif) et les erreurs de sync sont conservées dans `SupplierSyncLog.statistics` (`row_errors`, `sync_errors`, 100 premières) et non plus seulement comptées ([suppliers.py](backend/app/api/routes/suppliers.py)) ; sans migration (colonne JSON existante).
- **Tests** : verrou respecté par la sync, statut de la fiche admin avec un paiement encaissé, journal des rejets sur l'import fichier ; suites checkout existantes au vert avec le nouveau snapshot.
- **Lot A terminé** : les 12 points bloquants de la spec sont couverts ou levés (B1, B2, B5, B6, B7, B9, B12 livrés ici ; B3, B4, B8 déjà en place ; B10/B11 partiels : liste blanche de SKU Ingram et import en brouillon restent au Lot D).

**Lot B — départ groupé, suite** : clôture assistée (`POST /admin/grouped-departures/{id}/close` → vérification stock fournisseur via [checkout_availability.py](backend/app/features/integrations/services/checkout_availability.py), onglet « à arbitrer », report si seuil non atteint) ; `SupplierOrder` par départ (`grouped_departure_id`, `total_amount`, `ordered_at`, lignes multi-commandes, export CSV/PDF ; le handler [ingram_micro.py](backend/app/handlers/ingram_micro.py) ignore les commandes rattachées à un départ) ; rappels réseaux sociaux ; récurrence.

#### ✅ Avancement — Lot B : clôture assistée, bons de commande, rappels réseaux sociaux, récurrence (25/09/2026)

- **Clôture assistée** (`POST /admin/grouped-departures/{id}/close`, service [departure/services.py](backend/app/features/departure/services.py)) : rafraîchit la dispo fournisseur en direct de chaque article commandé (réutilise `refresh_supplier_availability` du checkout) et renvoie les **ruptures** (quantité commandée vs disponible, commandes concernées), les **commandes impayées** encore rattachées, le respect des **seuils** (`min_amount`, `min_units`) ; en dessous d'un seuil le départ reste ouvert sauf `force`. Un départ clôturé est dépublié. Admin : bouton « Clôturer le départ », dialogue d'arbitrage avec « Marquer en rupture » (statut `Backordered` + e-mail aux clients) et « Forcer la clôture ».
- **Récurrence** : à la clôture d'un départ à `recurrence_days`, le suivant est créé **ouvert et publié**, dates décalées, seuils et rappels recopiés.
- **Bons de commande fournisseur** : saisis sur le départ (`supplier_orders` JSON : fournisseur, numéro, date, montant, devise, notes — `POST/DELETE /{id}/supplier-orders`) ; le premier passe le départ en `ordered` et les commandes en « commandée au fournisseur ». Le handler Ingram **ignore** désormais les commandes rattachées à un départ (plus de BC automatique par commande client). L'envoi API Ingram agrégé par départ n'est pas câblé (commande passée à la main dans le portail, cf. stratégie de lancement) ; le récap SKU en CSV en tient lieu.
- **Rappels réseaux sociaux** : modèle `DepartureReminder` (jours avant la clôture ou le départ, gabarit avec `{name} {cutoff_date} {days_left} {delivery_date} {shop_url}`, image, statut), **J-7 / J-2 / dernier jour** créés avec chaque départ, replanifiés si la date change, annulés si le départ se ferme. Cron ARQ `publish_departure_reminders` toutes les 15 min ([departure_tasks.py](backend/app/tasks/departure_tasks.py)) → **webhook générique** JSON `{text, link, image_url, departure}` ([core/webhook.py](backend/app/core/webhook.py), https seulement) vers Make / Zapier / Buffer…, URL dans le réglage `social_webhook_url` (seedé vide, éditable dans l'onglet). Admin : liste avec le texte rendu, ajout / modification, « Publier maintenant », historique et erreurs.
- **Migration** `f6c2e8b4a7d3` (réversible). **Tests** : 5 d'intégration (clôture avec ruptures / impayés / récurrence, seuil et forçage, BC + propagation, rappels planifiés / replanifiés / rendus / publiés, cron avec annulation sur départ fermé) + handler Ingram. Types OpenAPI régénérés.
- **Reste** : canal e-mail opt-in des rappels et API Meta directe (Lot D) ; report automatique des commandes impayées vers le départ suivant (aujourd'hui signalées, déplacement manuel) ; BC Ingram agrégé par API.

**Lot C — réception et tableau de bord** : onglet « Réception » du départ (`GoodsReceipt` / `GoodsReceiptLine` avec quantités, état, numéros de série), rapprochement servi / partiel / non servi, `OrderLine.serial_numbers`, espace client (lignes, n° de série, fin de garantie), tableau de bord par départ (encaissé, payé fournisseur, fret / douane réels, marge brute).

#### ✅ Avancement — Lot C : réception, rapprochement, numéros de série, tableau de bord (25/09/2026)

- **Pointage par SKU** ([departure/reception.py](backend/app/features/departure/reception.py)) : une seule table `departure_receipt_lines` (départ × produit : reçu, endommagé, numéros de série des exemplaires conformes, notes, date de réception) plutôt que le couple `GoodsReceipt` / `GoodsReceiptLine` prévu — la quantité **attendue** n'est jamais stockée, c'est la somme des lignes des commandes payées du départ. `GET /admin/grouped-departures/{id}/reception` rend le pointage et le rapprochement ; `PUT …/reception/{product_id}` enregistre ou corrige une ligne (idempotent).
- **Rapprochement** : les exemplaires conformes sont attribués aux commandes **par ordre d'arrivée** (date de commande), ligne par ligne → chaque commande est `served` / `partial` / `unserved` ; les manquants par article sont affichés. Les **numéros de série** du pointage sont recopiés dans le même ordre sur `OrderLine.serial_numbers` à chaque enregistrement.
- **Espace client** : `GET /orders/me/{id}/lines` (articles, n° de série, `warranty_until` = date de réception + `warranty_months` du produit, calendrier réel) ; page de suivi de commande : bloc « Articles ».
- **Tableau de bord** (`GET /admin/grouped-departures/{id}/dashboard`) : CA (commandes payées ou en cours), **encaissé** (Σ paiements capturés − Σ remboursements effectués), coût marchandises **réel** (Σ bons de commande saisis, convertis en XPF par les taux actifs ; devises sans taux signalées) sinon **estimé** (snapshots `cost_amount_snapshot × fx_rate_used` des lignes), **fret / douane / autres frais réels** saisis sur le départ (`freight_cost`, `customs_cost`, `other_costs`), marge brute et taux. Admin : tuiles + saisie des coûts dans la même page « Départs groupés ».
- **Migration** `g7d3f9a1b5c2` (réversible). **Tests** : 3 (pointage → rapprochement → serials côté client avec garantie, correction idempotente et refus des doublons ; tableau de bord snapshots → BC réels → devise sans taux ; calcul de mois calendaires). Types OpenAPI régénérés.
- **Reste** : état par exemplaire (aujourd'hui « reçu / endommagé » par article, pas par numéro de série) ; report automatique des manquants sur le départ suivant (aujourd'hui : « Marquer en rupture » depuis la clôture, ou déplacement manuel) ; entrée en stock `Inventory` des exemplaires reçus non affectés (surplus).

**Lot D — souhaitables restants** : acompte + solde (ci-dessous), devis PDF → commande, avoir-crédit client, « me prévenir », SMS / WhatsApp, suivi sans compte par lien signé, whitelist SKU Ingram, import en brouillon, commission paiement en % dans le prix, marge de sécurité FX, journal des prix.

#### ✅ Avancement — Lot D, acompte à la commande et solde (25/09/2026)

- **Politique par groupe tarifaire** (`PriceGroup.deposit_pct` null = pas d'acompte, `deposit_fee_pct`, `deposit_fee_fixed`, `deposit_required`) : `PATCH /admin/price-groups/{id}`, réglée dans la page « Éligibilité paiement » de l'admin (section « Acompte à la commande »). Aucun réglage global : un groupe sans pourcentage n'a pas l'option.
- **Checkout** ([cart.py](backend/app/api/routes/cart.py), module pur [payment/services/deposit.py](backend/app/features/payment/services/deposit.py)) : le groupe **du client** (puis le défaut) est résolu — il porte aussi le snapshot de marge, corrigeant l'emploi du groupe par défaut. Devis et commande acceptent `payment_plan` ; les frais de l'option (`% × total hors option + fixe`) entrent dans `total_fees_amount` et le total ; `deposit_amount = total × %`, solde = reste (les deux s'additionnent exactement). Un acompte imposé s'applique sans choix ; demandé hors politique → 400 `checkout.deposit.unavailable`. Le paiement initié au checkout porte l'acompte (`Payment.kind = deposit`). Vitrine : choix « Payer la totalité / Verser un acompte de N % » ou bandeau si imposé, récap « acompte à payer maintenant / solde à la réception ».
- **Gardes adaptées par `kind`** (`full | deposit | balance`) : `_validate_order_for_initiation` renvoie le kind attendu (`next_payment_kind` : acompte non réglé → `deposit` ; réglé → `balance` ; solde encaissé → 409 `already_paid`), le montant attendu est celui de la part, et un solde reste payable pendant l'acheminement (seuls `Refunded`, `PartiallyRefunded`, `PaymentReview`, `Cancelled` le refusent). `_captured_amount_mismatch` compare au montant de la part. Garde IPN inchangée (par paiement).
- **Handlers** : acompte capturé → statut **`DepositPaid`** (suit le départ groupé comme `Paid`), stock confirmé, e-mail « Acompte reçu » avec le solde, **pas de facture** (option a) ; solde capturé → `balance_paid_at`, `DepositPaid → Paid` (statut d'acheminement conservé sinon), **facture unique** avec frais de l'option et lignes « acompte déjà versé / solde encaissé » ; solde refusé → rien n'est annulé (le client réessaie) ; le handler Ingram ignore la capture du solde (le BC part sur l'acompte).
- **Demande de solde** : au passage en `Received` (départ reçu ou fiche commande), handler `order.balance_due` → e-mail avec montants et lien `/mon-compte/commandes/{id}/solde` (page vitrine : moyens de paiement éligibles sur le solde, SmartForm ou instructions, réutilise `POST /payments/initiate` avec le kind résolu côté serveur) ; envoyée une fois, **renvoyable** depuis la fiche commande admin (`POST /admin/orders/{id}/request-balance`). Espace client : bloc « Commande avec acompte » (acompte, solde, « à régler » / « réglé », bouton de règlement dès l'acompte encaissé). Loader SmartForm partagé dans [utils/payzen.ts](frontend/src/utils/payzen.ts).
- **Migration** `h8e4a2c6d9f1` (réversible, défauts `full` / 0). **Tests** : 5 unitaires (politique, frais, découpe, kind attendu, frais dans les totaux) + 3 d'intégration (parcours acompte → solde à travers les gardes et les handlers, demande de solde à la réception et renvoi admin, édition de la politique). Types OpenAPI régénérés.
- **Reste / décisions** : facture d'acompte (option b) si le comptable l'exige ; relance automatique du solde non payé (cron) et arbitrage « report / remboursement acompte − frais » ; remboursement jugé par paiement (un remboursement total de l'acompte passe la commande en `Refunded` : correct avant le solde, à revoir après) ; lien de paiement sans compte (avec le suivi sans compte).

#### ✅ Avancement — Lot D, devis PDF → commande (26/09/2026)

- **Émission du devis** ([cart/services/quote.py](backend/app/features/cart/services/quote.py)) : la demande reste intacte ; l'admin émet le **devis** depuis la fiche de la demande (lignes pré-remplies depuis le panier, prix unitaire et quantité modifiables, lignes libres hors catalogue, livraison TTC, validité — 30 jours par défaut —, message client). Numéro **`DEV-AAAA-NNNNN`** (compteur `quote_counters`, même mécanisme verrouillé que les factures, conservé à la ré-émission), snapshot figé (`quote_snapshot` : lignes, référence fabricant, totaux, vendeur, client, validité, message) ; statut `quoted`. `POST /admin/quote-requests/{id}/issue`, `GET …/pdf`.
- **PDF** : gabarit [quote.html](backend/app/templates/invoice/fr/quote.html) rendu par le même moteur que les factures (WeasyPrint, import paresseux) ; **e-mail au client avec le PDF en pièce jointe** (`NotificationMessage.attachments`, provider Mailgun) et lien vers « Mes devis » pour un client inscrit ; sans moteur PDF l'e-mail part quand même (montants + lien).
- **Client** : onglet **« Devis »** de l'espace client (`GET /cart/quote-requests/me`, PDF, statut, validité), bouton **« Commander ce devis »** (`POST …/{id}/accept` charge le panier serveur aux **prix du devis**), puis checkout en mode devis (`?quote=` → `quote_request_id`) : le panier est **rebâti côté serveur depuis le devis**, la revalidation des prix catalogue est sautée, la **livraison du devis** remplace le tarif des tronçons (les tronçons restent résolus pour le suivi), la commande créée est rattachée au devis (`order_id`, statut `won`). Un devis se commande s'il est émis, en date, non converti et composé de produits catalogue ; une demande faite avant l'inscription est reconnue par l'e-mail du compte.
- **Migration** `i9f5b3d7e1a2` (réversible). **Tests** : 3 d'intégration (émission → numéro, snapshot, e-mail avec PDF `%PDF`, ré-émission à numéro constant, PDF admin / client / étranger ; acceptation aux prix du devis, expiré / gagné refusés ; e-mail sans moteur PDF et devis hors catalogue non commandable). Types OpenAPI régénérés.
- **Reste** : remise globale (aujourd'hui par ligne, via le prix unitaire) ; devis pour un visiteur sans compte commandable par lien signé (avec le suivi sans compte) ; conversion d'un devis en commande par l'admin (paiement par virement / BC) ; relance avant expiration.

#### ✅ Avancement — Lot D, avoir-crédit client (26/09/2026)

- **Grand livre** ([payment/models/store_credit.py](backend/app/features/payment/models/store_credit.py)) : `store_credit_entries` (montant signé, `grant | use | revoke`, motif, commande liée, paiement lié) ; le solde est la somme des entrées, jamais une colonne. Distinct de l'avoir comptable (`CreditNote`) qui documente un remboursement.
- **Admin** : depuis la fiche commande, bouton « Avoir-crédit » (montant, motif ; négatif = reprise, jamais sous zéro), solde et historique du client (`GET/POST /admin/users/{id}/store-credit`). Usage typique : compenser une rupture ou un retard sans rembourser.
- **Client** : solde et historique dans l'onglet Commandes (`GET /store-credit/me`) ; au checkout, bandeau « Vous disposez d'un avoir de X » avec bascule « L'utiliser sur cette commande » ; récap « Avoir utilisé − X / Reste à payer maintenant » ; si l'avoir couvre tout, aucun moyen de paiement n'est demandé et la commande est réglée d'emblée.
- **Mécanique** ([payment/services/store_credit.py](backend/app/features/payment/services/store_credit.py)) : l'avoir utilisé devient un **paiement `store_credit` réglé** (kind de la part payée maintenant : total ou acompte) à côté du paiement d'argent pour le reste, plus une entrée `use` ; son événement `payment.captured` pilote la commande comme tout paiement. Les gardes raisonnent désormais par **couverture de la part** : `next_payment_kind` / `remaining_amount` sur des montants réglés par kind (le paiement d'argent attendu = part − avoir), et `on_payment_captured` n'agit qu'une fois la part exactement couverte — en attente (`PARTIAL`) tant qu'un autre paiement de la part est en cours, `PaymentReview` si un encaissement court n'a rien en attente derrière lui (comportement inchangé), facture et BC Ingram différés de même. L'e-mail « paiement validé » n'est pas envoyé pour un paiement `store_credit`.
- **Migration** `j1a7c4e8b2d5` (réversible). **Tests** : 3 d'intégration (octroi / reprise / solde client et admin ; avoir + carte sur une même commande à travers la garde d'initiation et les handlers, attente puis `Paid` ; encaissement court sans paiement en attente → `PaymentReview`) + tests unitaires adaptés (montants par kind). Types OpenAPI régénérés.
- **Reste** : expiration des avoirs ; remboursement en avoir directement depuis le dialogue de remboursement (aujourd'hui deux actions : remboursement partiel ou avoir) ; avoir utilisé sur le solde d'une commande à acompte (aujourd'hui sur la part payée à la commande) ; remboursement d'une commande réglée en partie par avoir (l'avoir n'est pas recrédité automatiquement).

#### ✅ Avancement — Lot D, alerte « me prévenir » (26/09/2026)

- **Inscription** ([product/services/stock_alert.py](backend/app/features/product/services/stock_alert.py), `stock_alerts`) : sur une fiche produit non commandable, bouton **« Me prévenir »** → e-mail (pré-rempli pour un client connecté, saisi pour un visiteur) ; `POST /stock-alerts`, idempotent par produit et e-mail, refusé si le produit est déjà commandable. La règle de commandabilité est celle de la vitrine (`utils/availability.ts`) : stock > 0, ou mode `continuous`, ou `on_demand` avec stock fournisseur > 0.
- **Notification** : cron ARQ horaire `notify_stock_alerts` ([stock_alert_tasks.py](backend/app/tasks/stock_alert_tasks.py), à h + 20 pour passer après la sync prix / stock fournisseur) : chaque alerte en attente dont le produit est redevenu commandable reçoit **un** e-mail (`stock_alert`, lien vers la fiche) et passe `sent` ; les produits désactivés sont ignorés.
- **Espace client** : liste des alertes (en attente / prévenu le …) dans l'onglet Préférences, annulation d'une alerte en attente (`GET /stock-alerts/me`, `DELETE /stock-alerts/{id}`) ; une alerte prise en visiteur est reconnue par l'e-mail du compte.
- **Migration** `k2b8d5f9a3e6` (réversible). **Tests** : règle de commandabilité ; parcours inscription (client, visiteur, doublon, produit disponible refusé) → passe à vide → retour en stock → deux e-mails une seule fois → liste et annulation.
- **Reste** : nombre d'alertes en attente par produit dans l'admin (signal de demande pour le prochain départ) ; alerte « baisse de prix » ; canal SMS / WhatsApp quand il existera.

#### ✅ Avancement — Lot D, suivi sans compte par lien signé (26/09/2026)

- **Lien** ([order/services/tracking_link.py](backend/app/features/order/services/tracking_link.py)) : `{FRONTEND_HOST}/suivi/{order_id}?t=<jeton>`, le jeton étant un HMAC-SHA256 de l'id de commande sous `SECRET_KEY` (32 caractères URL-safe). Rien n'est stocké, rien n'expire : comme un numéro de colis, le lien ouvre **cette** commande en lecture seule ; changer `SECRET_KEY` invalide tous les liens.
- **Endpoint public** `GET /orders/track/{id}?t=` ([orders_me.py](backend/app/api/routes/orders_me.py)) : commande (statut, montants, acompte / solde), suivi agrégé (même calcul que `GET /orders/me/{id}/tracking`, factorisé dans `_tracking_for`) et articles (n° de série, garantie). Jeton absent, forgé ou d'une autre commande → 404 `order.not_found`, indiscernable d'une commande inexistante.
- **E-mails** : la ligne « Suivre ma commande : … » est ajoutée à `order_created`, `order_status_changed`, `shipping_shipped` et `shipping_progress` (texte et HTML), calculée depuis l'id du payload par `tracking_url_from_payload` (aucun lien si l'id est inutilisable, l'e-mail part quand même).
- **Vitrine** : route `/suivi/:id` sur la même page `OrderTrackingPage.vue` en mode visiteur (pas de redirection vers la connexion, bandeau « vous suivez depuis le lien reçu par e-mail », pas de bouton « Mes commandes ») ; le règlement du solde reste réservé à l'espace client (invitation à se connecter).
- **Tests** : jeton lié à la commande (autre commande, altéré, vide, espaces tolérés) ; parcours signé (commande, statut, suivi, articles) puis refus des jetons absents / forgés / étrangers et d'une commande inexistante ; l'e-mail de changement de statut contient le lien.
- **Reste** : réutiliser le jeton pour le devis d'un visiteur sans compte et le paiement du solde par lien (demande du §5) ; option d'expiration si l'on veut des liens à durée limitée (ajouter une date au message signé).

#### ✅ Avancement — Lot D, liste blanche de références (SKU) par fournisseur (26/09/2026)

- **Principe** : `Supplier.sku_allowlist` (JSON, migration `l3c9e6a1b4f7`, réversible) porte les références que la boutique vend chez ce fournisseur. Vide : tout le catalogue synchronisé est suivi (comportement inchangé). Renseignée : la sync catalogue ne crée ni ne touche une référence hors liste (comptée `filtered`, [supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py)), la sync prix / stock ne demande que les références listées ([supplier_tasks.py](backend/app/tasks/supplier_tasks.py)), et l'enregistrement de la liste retire de la vitrine les articles gérés par ce fournisseur hors liste (`is_active=False` ; un article saisi à la main n'est pas concerné). Une référence listée mais inconnue est créée par la prochaine sync catalogue ; une référence listée masquée revient d'elle-même au prochain rafraîchissement prix / stock (seuils). Couvre le point B10 « pas de publication automatique de tout le catalogue ».
- **Service** [sku_allowlist.py](backend/app/features/integrations/services/sku_allowlist.py) : normalisation (trim, dédoublonnage, ordre conservé), `allowed_sku` / `restrict_skus` partagés par les deux syncs, `save_allowlist` + `allowlist_view` (connues / à créer / hors liste / retirées). La liste vaut aussi pour un fournisseur fichier (CSV) : l'import n'écrit que les références listées.
- **Admin** : `GET` / `PUT /admin/suppliers/{code}/sku-allowlist` ; page Fournisseurs → bouton « Références suivies » (fournisseurs API et fichier) : zone de saisie une référence par ligne, compteurs, détail par référence (article, en vitrine / masqué / à créer), badge « N réf. suivie(s) » sur la ligne. Le cache d'adaptateur est invalidé à l'enregistrement.
- **Tests** : helpers ; parcours réel (enregistrement normalisé, connues / inconnues, article hors liste masqué, article manuel épargné, relecture, sync catalogue filtrée / créée, vidage) ; sync prix / stock n'interrogeant que les références listées.
- **Reste** : `SupplierProductMapping.sync_enabled` reste inutilisé (la liste est le mécanisme, pas de bascule par article) ; la sync catalogue Ingram parcourt toujours les catégories entières avant de filtrer (une recherche par référence côté API épargnerait des appels) ; import de la liste depuis un fichier.

#### ✅ Avancement — Lot D, import en brouillon (26/09/2026)

- **Principe** : réglage par fournisseur « Nouveaux articles en brouillon » (`Supplier.import_as_draft`, fournisseurs API et fichier). Un article **créé** par une synchronisation ou un import de ce fournisseur porte `Product.is_draft=True` ([supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py), à la création seulement : un article déjà publié n'est jamais remis en brouillon par une sync). Le brouillon est enrichi (Icecat) et rafraîchi (prix / stock) comme les autres, mais `publication_conditions()` l'exclut de la vitrine, de la recherche et des mises en avant, et `publication_blockers()` renvoie `draft` (garde panier, fiche). Migration `m4d1f7b2c8e9` (réversible, défaut `false` : rien ne change pour l'existant). Lève la réserve B10 « un produit enrichi est publié automatiquement ».
- **Publication** : `POST /admin/products/publish` `{product_ids}` sort les articles du brouillon (compte publiés / déjà publiés / inconnus) sans forcer le reste : la vitrine applique ensuite ses conditions habituelles (actif, enrichi, tarifable). `is_draft` est exempt des verrous admin. Liste admin : filtre `status=draft`.
- **Admin** : page Fournisseurs → bascule dans le formulaire ; page Articles → filtre « Brouillons (à publier) », badge « Brouillon », bouton publier sur la ligne et sélection multiple + « Publier N brouillon(s) ».
- **Tests** : unitaire (création en brouillon, mise à jour sans re-brouillon, fournisseur sans réglage) ; parcours réel (import en brouillon → invisibles + bloqueur `draft` → réimport sans publication → publication unitaire puis en masse avec inconnus / déjà publiés → visibles → réglage désactivé, nouvel article publié d'emblée).
- **Reste** : ~~compteur de brouillons en attente sur le tableau de bord admin~~ (✅ 30/09/2026, tuile « Produits à relire ») ; publication automatique conditionnelle (ex. dès qu'un article est enrichi et tarifable) si l'admin préfère ne relire que les exceptions.

#### ✅ Avancement — Lot D, commission de paiement en % dans le prix rendu (26/09/2026)

- **Principe** : la commission du prestataire de paiement (CB) est intégrée dans le prix de vente au lieu d'être un frais fixe au checkout : `prix = prix hors commission ÷ (1 − c)`, appliqué au prix TTC final des modes `domestic` et `import` (un prix `fixed` reste ce que l'admin a tapé). La boutique encaisse donc bien le prix que la formule a calculé, commission déduite. Réglage unique `pricing_payment_commission_pct` dans **Paramètres système** (défaut 0 = aucun changement), avec aide de saisie ; seedé au démarrage sans jamais réécrire une valeur saisie.
- **Code** : [pricing_parameters.py](backend/app/features/product/services/pricing_parameters.py) (spécification des paramètres de prix éditables, lecture, validation, `apply_payment_commission`) ; `calculate_sale_price` et `PricingContext.price` ([pricing.py](backend/app/features/product/services/pricing.py)) appliquent le même terme ; `PUT /admin/system-settings/{clé}` valide une clé de prix (nombre, 0 ≤ c < 100, 400 `system_setting.invalid_value` sinon) et déclenche le **recalcul de tout le catalogue** (`schedule_price_refresh`, dédoublonné) — même mécanisme que les taux de taxe et de change.
- **Tests** : maths et analyse (« 1,5 % » accepté, `abc` / `-1` / `100` refusés) ; parcours réel : défaut sans réglage, valeur invalide refusée, valeur enregistrée + recalcul planifié, parité `calculate_sale_price` / `PricingContext`, prix matérialisé mis à jour par la tâche.
- **Reste** : mettre `PaymentMethod.fee` à 0 sur la CB quand la commission est dans le prix (les deux mécanismes coexistent, l'admin choisit) ; commission par moyen de paiement (un seul taux aujourd'hui, celui du moyen dominant) ; snapshot du taux sur la ligne de commande pour le tableau de bord de marge.

#### ✅ Avancement — Lot D, marge de sécurité sur le change (26/09/2026)

- **Principe** : un coût fournisseur en devise étrangère (USD, EUR…) est majoré de `pricing_fx_safety_margin_pct` **après conversion et avant la formule** (CAF, douane, marge, taxe), pour qu'une variation du taux entre la vente et le règlement du fournisseur n'entame pas la marge. Un coût déjà en XPF ne porte aucun risque de change et n'est pas touché. Même module que la commission ([pricing_parameters.py](backend/app/features/product/services/pricing_parameters.py)) : réglage dans **Paramètres système**, défaut 0, validation 0 ≤ m < 100, recalcul de tout le catalogue à l'enregistrement, seed sans réécriture. Appliqué à l'identique par `calculate_sale_price` et `PricingContext.price`.
- **Périmètre** : seule la **formule de prix** est majorée. La conversion « vraie » reste inchangée partout ailleurs : `fx_rate_used` figé sur la ligne de commande, coût des bons de commande dans le tableau de bord de marge du départ, seuil de prix minimum de la sync fournisseur.
- **Tests** : deux articles au même coût (100 USD à 110, 11 000 XPF) tarifés pareil sans réglage ; à 3 %, seul le coût en USD est majoré ; parité des deux chemins de prix.
- **Reste** : marge par devise si le risque diffère (USD vs EUR).

#### ✅ Avancement — Lot D, journal des prix (26/09/2026)

- **Principe** : table `product_price_history` ([price_history.py](backend/app/features/product/models/price_history.py), migration `n5e2a8c3d9f1`, réversible) : une ligne par **changement** du prix de vente matérialisé (`sale_price_cached`) — ancien prix, nouveau prix, cause, date. Écrite aux deux endroits où le prix est écrit : le hook d'enregistrement d'un article (création, édition admin, synchronisation fournisseur → cause `product_write`) et le rafraîchissement en masse ([pricing_tasks.py](backend/app/tasks/pricing_tasks.py), qui transmet désormais sa cause : `currency_rate:EUR`, `tax_rate_created:…`, `category_merge`, `system_setting:pricing_…`, `nightly`, `admin_inline`). Une valeur inchangée n'écrit rien : le balayage nocturne ne remplit pas la table.
- **Admin** : `GET /admin/products/{id}/price-history` (du plus récent au plus ancien, 50 par défaut) ; page Articles → bouton « Journal des prix » sur chaque ligne, dialogue avec date, ancien / nouveau prix et cause en clair.
- **Tests** : helper (pas de ligne sans changement) ; parcours réel : création (rien → 1 500), édition (1 500 → 1 990), édition sans effet sur le prix (aucune ligne), rafraîchissement manuel puis changement de taux EUR (deux lignes avec leurs causes), article non concerné sans ligne.
- **Reste** : purge des lignes anciennes (rétention) ; le comblement à la volée des prix `NULL` en lecture vitrine (`_price_and_persist_now`) n'est pas journalisé (chemin de secours, hors session) ; export CSV du journal.

**Lot D terminé** : les onze souhaitables sont livrés (acompte, devis, avoir-crédit, « me prévenir », suivi sans compte, liste blanche SKU, import en brouillon, commission dans le prix, marge FX, journal des prix) ; seul **SMS / WhatsApp** reste ouvert (aucun prestataire choisi).

### Faisabilité de l'acompte à la commande (50 % / 30 % selon type de client, frais optionnels)

**Verdict : faisable sans refonte, mais pas un simple paramètre.** Le modèle accepte déjà plusieurs paiements par commande (`Payment.order_id` non unique ; l'IPN PayZen identifie le paiement par `payment.id`, [payment_initiation.py](backend/app/features/payment/services/payment_initiation.py)) et le montant initié est libre. Le groupe tarifaire (`PriceGroup` : PARTICULIER par défaut, PROFESSIONNEL, REVENDEUR, PUBLIC) fait office de type de client, et l'éligibilité des moyens de paiement est déjà par groupe ([eligibility.py](backend/app/features/payment/services/eligibility.py)). Mais la logique métier suppose « un paiement = le total » : un acompte de 30 % encaissé aujourd'hui donne une commande bloquée en `PaymentReview`, aucune facture, un stock réservé mais non confirmé, un **BC Ingram quand même envoyé**, un e-mail « Paiement validé » et une alerte admin. Il n'existe ni lien de paiement ni page vitrine « payer une commande existante ».

**Conception** :
- **Politique par type de client** sur `PriceGroup` : `deposit_pct` (null = pas d'acompte), `deposit_fee_pct`, `deposit_fee_fixed`, `deposit_mode ∈ optional | required` ; ~~interrupteur global `deposit_enabled` dans `system_settings`~~ *(non construit : l'acompte est piloté par `PriceGroup` seul, cf. Lot D l.723 — constaté le 30/09/2026)* ; écran admin « Groupes tarifaires » (aujourd'hui GET seulement). Exemple : PARTICULIER 50 % + 2 %, PROFESSIONNEL / PUBLIC 30 % + frais fixe, REVENDEUR sans acompte.
- **Commande** : `payment_plan ∈ full | deposit`, `deposit_amount`, `deposit_fee_amount` (inclus dans `total_fees_amount` et `total_amount`), `price_group_id` snapshoté — le checkout utilise aujourd'hui le groupe **par défaut** et non celui du client (`resolve_default_price_group` dans [cart.py](backend/app/api/routes/cart.py)) : première règle de checkout qui dépend vraiment du groupe, à corriger. `amount_paid` calculé (Σ paiements `Completed` − Σ remboursements) plutôt que stocké. Un champ `Order.payment_state` séparé du statut logistique est recommandé plutôt que de nouveaux statuts (`Paid` est utilisé dans les gardes, le balayage stock ne regarde que `Pending`).
- **Paiement** : `kind ∈ full | deposit | balance`, `expected_amount`, `link_token` + `link_expires_at` (empreinte SHA-256, comme [password_reset.py](backend/app/api/routes/password_reset.py)).
- **Checkout** (`_quote_checkout` / `checkout_my_cart`) : résolution du groupe → politique ; `deposit_fee = total × fee_pct + fee_fixed`, `total += deposit_fee`, `deposit_amount = round(total × pct)`, paiement initié pour `deposit_amount` ; `CheckoutQuoteResponse` expose acompte / solde / frais ; vitrine : sélecteur « Payer intégralement / Verser un acompte » et lignes « Acompte à payer maintenant / Solde à régler à la réception ».
- **Gardes à adapter** : `_validate_order_for_initiation` ([payments.py](backend/app/api/routes/payments.py)) accepte un `balance` en `AwaitingBalance` avec montant attendu = total − encaissé, devise lue sur `order.currency` ; garde IPN inchangée (déjà par paiement) ; `_captured_amount_mismatch` ([handlers/payment.py](backend/app/handlers/payment.py)) compare à `expected_amount` — acompte capturé → `DepositPaid` + `confirm_order_stock`, solde → `Paid` quand encaissé ≥ total ; `on_payment_captured_create_ingram_order` n'a aucune vérification de montant → décider si l'acompte déclenche le BC (probable) et ne pas re-déclencher au solde ; `payment.rejected` d'un solde ne doit ni passer en `PaymentFailed` ni libérer le stock ; `on_payment_refunded` juge `fully_refunded` sur le net encaissé de la commande, pas sur un seul paiement.
- **Solde et lien de paiement** : sur `order.status_changed` → `Received` (donc en un clic pour tout un départ groupé), création de la demande de solde, `AwaitingBalance`, e-mail `balance_due` avec lien → route vitrine `/paiement/solde/:orderId?token=…` → `POST /payments/orders/{id}/balance` qui crée le paiement `balance` et renvoie un form token PayZen **frais** (les form tokens expirent vite, le lien ne peut pas en contenir un) → `PaymentReturnPage.vue`. Relances par cron ARQ. Virement / chèque : `register_intent` réutilisé, **coordonnées bancaires à ajouter** (aucun IBAN nulle part, instructions codées en dur dans [manual.py](backend/app/features/payment/providers/manual.py), jamais envoyées par e-mail). Une autorisation CB prise au checkout expire en ~7 j : le solde encaissé des semaines plus tard est obligatoirement un nouveau paiement.
- **Admin** `OrderDetailPage.vue` : acompte / encaissé / solde dû, colonne kind, « Envoyer / renvoyer le lien de solde ».
- **Facture — point délicat** : une facture par commande (`Invoice.order_id` unique), émise à la capture, refusée si ≠ `order.total_amount` ([invoice_service.py](backend/app/features/invoice/services/invoice_service.py)) ; avoir = prorata de « la » facture. Option (a), recommandée pour démarrer : pas de facture à l'acompte (reçu par e-mail), facture unique au solde — ⚠️ un acompte encaissé appelle normalement une **facture d'acompte**, à valider avec le comptable (TGC PF). Option (b) : `Invoice.kind ∈ deposit | final`, levée de l'unicité, facture finale déduisant les acomptes ; impacte snapshot, PDF, exports CSV / FEC et le ciblage des avoirs. Rembourser un acompte avant facture ne produit aujourd'hui aucun avoir.
- **Frais** : `PaymentMethod.fee` est fixe ; le % demandé passe par `deposit_fee_pct`. Le frais rejoint le groupe de taxe « frais » de la facture (`INVOICE_FEES_TAX_CODE`).

**Effort** : politique + checkout + gardes + statuts 3-4 j ; lien de paiement + page + e-mails + relance 2-3 j ; admin 1-2 j ; facture d'acompte (option b) +2-3 j. Dépend du Lot A item 3 (`order.status_changed`) pour le déclenchement automatique du solde.

### Décisions du propriétaire à trancher (défaut retenu à défaut de réponse)

| Question | Défaut retenu |
|---|---|
| Date affichée en vitrine | Les deux : limite de commande (pivot) et livraison estimée |
| Rattachement des commandes au départ | Automatique au checkout, déplaçable à la main |
| Canal des rappels sociaux | Webhook générique (Make / Zapier / Buffer) d'abord ; API Meta directe plus tard |
| Rappels par défaut | J-7, J-2, dernier jour, désactivables |
| Acompte au choix du client ou imposé par groupe | `optional` pour tous, réglable par groupe |
| L'acompte déclenche-t-il la commande fournisseur | Oui |
| Statut déclencheur du solde | `Received`, configurable |
| Facture d'acompte | Option (a), à valider par le comptable |
| Frais d'acompte facturés | Avec l'acompte |
| Solde impayé après N relances | `Backordered` → arbitrage admin (report / remboursement acompte − frais) |

---

## Phase 0 — Stabilisation des bugs critiques

**Objectif** : pouvoir déployer sereinement les phases suivantes sans dette qui se propage.

*Surfaces : correctifs backend uniquement — aucune livraison vitrine / admin-frontend.*

**Statut** : ✅ Réalisée (18/05/2026)

### Bugs identifiés

| # | Bug | Localisation | Sévérité | Statut |
|---|-----|--------------|----------|--------|
| B1 | `_collect_email_targets` utilise des UUIDs comme adresses email → aucun email client n'arrive | [notifications.py](backend/app/features/payment/services/notifications.py) | 🔴 Bloquant | ✅ Corrigé |
| B2 | Specs / features / gallery Icecat fetchées puis jetées | [icecat_tasks.py](backend/app/tasks/icecat_tasks.py) + migration [3b5d9a1c7e42](backend/app/alembic/versions/3b5d9a1c7e42_add_icecat_payload_columns_to_products.py) | 🔴 Bloquant Phase 1 | ✅ Corrigé |
| B3 | `last_supplier_sync` typé `datetime` mais stocké en ISO string | [product.py CRUD](backend/app/features/product/crud/product.py) vs modèle | 🟠 Risque comparaison | ✅ Corrigé |
| B4 | `filter: str` du BaseRouter passé brut à SQLAlchemy `.where()` | [base_router.py](backend/app/api/base_router.py) + [crud.py](backend/app/features/base/crud.py) | 🟠 Audit sécurité | ✅ Corrigé |
| B5 | Endpoints tracking/consolidation sans gating admin | [tracking.py](backend/app/api/routes/shipping/tracking.py) | 🟠 | ✅ Corrigé |
| B6 | Création produit ouverte à tout user authentifié au lieu de superuser | [product.py](backend/app/api/routes/product.py) | 🟠 | ✅ Corrigé |
| B7 | `CheckoutMetricsStore` in-memory incompatible multi-replicas | [observability.py:137](backend/app/core/observability.py#L137) | 🟡 | ⏳ Phase 2 (en attente) |
| B8 | Auto-sélection routes shipping greedy par segment ≠ optimum global | [cart.py:271-305](backend/app/api/routes/cart.py#L271-L305) | 🟡 | ⏸ Reporté Phase 3 |
| B9 | Mapping `last_supplier_sync` String/Datetime à harmoniser dans la migration | alembic | 🟡 | ⏸ Reporté (suivi migration) |

### Périmètre Phase 0

- ✅ B1, B2, B3, B4, B5, B6 livrés.
- ⏸ B7, B8, B9 conservés au backlog des phases ultérieures.

### Validation Phase 0

- Tests ciblés API mis à jour pour les nouveaux garde-fous de sécurité (tracking superuser, création produit superuser, filtre brut rejeté).
- Régression Icecat couverte par l'activation de la persistance des payloads dans `update_product_with_icecat_data()`.
- Migration dédiée ajoutée pour la persistance JSON des données Icecat sur `products`.

---

## Phase 1 — Vitrine catalogue + demande de devis

**Objectif** : un site consultable, un panier, et un bouton « Demander un devis » qui envoie un email à l'admin. Pas de paiement en ligne.

**Statut** : ✅ Réalisée (01/06/2026) — backend + CAF/fret import complets ; validation d'intégration (migration/seed) OK testée ; `schema.ts` régénéré ; vitrine minimale OK testée.

**Polish post-P1 (01/06/2026)** : 2 quick wins livrés sur le catalogue —
- **Curation par sous-catégorie** : `SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST` (config, seedée `["Ordinateur de Bureau/Tour", "Ordinateur Portable"]`, surchargeable par env) intégrée à `evaluate_product_filters` (action `deactivate` pour purger l'existant au prochain sync ; les règles `skip` priment). Réduit la pollution (garanties, accessoires) sans toucher au code à chaque ajustement.
- **Facette fabricant insensible à la casse** : `_build_search_facets` regroupe désormais sur `casefold` (« HP Inc. » / « HP INC. » → une seule entrée), libellé = première graphie vue.

> ✅ **Résolu** : la cause racine (`category_id = None`) a été corrigée en Phase 2 (item *Taxonomie interne & facettes specs* : `get_or_create_by_name` + backfill). La vitrine câble désormais le **sélecteur Catégorie** et les **filtres par spec** (20/06/2026, cf. *Avancement vitrine — filtres specs* ci-dessous). Prérequis d'exploitation : avoir lancé le backfill `category_id` pour que les catégories/specs remontent.

### Avancement vitrine — mode de livraison & devise (22/06/2026)

- ✅ **Sélecteur de mode de livraison retiré** de `ProductPage.vue` + `ProductDetailsDialog.vue`. Le prix affiché est celui du **mode par défaut** (résolu côté backend : préférence utilisateur `preferred_shipping_mode` → défaut). Motif : le fret import variable est nul pour les produits sans poids/dimensions Icecat → le choix par produit ne changeait pas le prix et prêtait à confusion. **Décision** : le mode de livraison est un choix **par commande** (défaut préf utilisateur → rapide).
- ✅ **Sélecteur de mode au checkout** *(périmé le 30/09/2026 : remplacé par `delivery_type` au checkout, livré le 05/09/2026)*. Historique : reporté à la phase logistique. Le checkout vitrine actuel paie le total panier sans étape shipping (ne câble pas `checkout_my_cart`, qui sait pourtant calculer le shipping selon `shipping_preference`). À câbler quand l'étape commande+shipping sera intégrée au checkout.
- ✅ **Option « Devise d'affichage » masquée** dans les préférences (`MyAccountPage.vue`) tant que l'affichage multi-devises (conversion XPF→devise + endpoint taux public) n'est pas livré — **Phase 4**. La préférence `currency_pref` reste stockée, simplement non exposée.

### Avancement vitrine — filtres specs (20/06/2026)

- ✅ **Sélecteur Catégorie** dans `CataloguePage.vue` (depuis `GET /category`).
- ✅ **Filtres par caractéristique** pilotés par `GET /product/categories/{id}/spec-facets` : facettes **enum** (cases à cocher `value_text (count)`) et **numériques** (sélecteur « ≥ minimum » à partir des valeurs disponibles). Payload `specs` envoyé à `POST /product/search` (`{cpu_family: ["i7"], memory_gb_min: 16}`). Sync URL (`cat`), reset, SSR prefetch.
- Modules : [frontend/src/api/products.ts](frontend/src/api/products.ts) (`getCategorySpecFacets`) · [frontend/src/stores/products.ts](frontend/src/stores/products.ts) (`specFacets`/`loadSpecFacets`). Typecheck + lint verts.

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| Catalogue + recherche FTS | ✅ | ✅ `CataloguePage.vue` | — |
| Specs filtrables (facettes) | ✅ | ✅ `CataloguePage.vue` (catégorie + filtres specs enum/num.) | ✅ édition specs (A3, 20/06/2026) |
| Fiche produit + modes transport (CAF) | ✅ | ✅ `ProductPage.vue` (prix du mode par défaut ; sélecteur de mode retiré — choix au niveau commande) | — |
| Panier | ✅ | ✅ `CartPage.vue` | — |
| Demande de devis | ✅ | ✅ `CartQuoteConfirmationPage.vue` | ✅ `QuoteRequestsPage.vue` (A11) |
| Produits mis en avant | ✅ | ✅ « Nos coups de cœur » sur l'accueil (reconstruit le 30/09/2026, R1-A) | ✅ toggle « Produit en vedette » dans `ProductFormDialog.vue` (A8) |
| Pricing / TVA / devises (socle) | ✅ | — | ✅ écrans taux (A1) et devises (A2), 20/06/2026 |

### Avancement backend (22/05/2026)

- ✅ Pricing runtime : modèles `PriceGroup` / `TaxRate`, résolution taxe + calcul prix, adaptation sync fournisseur sur `cost_amount`.
- ✅ API catalogue Phase 1 : `POST /product/search`, `GET /product/featured`, `POST/DELETE /product/{id}/feature` (admin).
- ✅ Demande de devis : `POST /cart/quote-request` avec persistance `QuoteRequest` + envoi email support.
- ✅ Checkout : snapshot `OrderLine.tax_rate_id` ajouté.
- ✅ Readiness/liveness : endpoints `/healthz/liveness` et `/healthz/ready` (DB + Redis).
- ✅ **Devises** : modèle `CurrencyRate` + migration `d1e5c3f8a294` + helper `convert_to_xpf()` intégré dans `calculate_sale_price()` + snapshots FX sur `CartItem`/`OrderLine` + endpoints admin `GET/PUT /admin/currency-rates`.
- ✅ **Dé-localisation devise de référence** (pré-prod, 28/05/2026) : `REFERENCE_CURRENCY` en config (défaut XPF) ; `convert_to_xpf→convert_to_reference_currency` ; colonne `rate_to_xpf→rate_to_reference` (migration `c5d9e2f1a8b4`, suivi de `d1e5c3f8a294`) ; `costAmountXpf/costXpf→costInReference` (`pricing.ts` + `schema.ts`) ; checks `=="XPF"` → `settings.REFERENCE_CURRENCY`. ✅ Migration validée en intégration et `schema.ts` régénéré depuis l'OpenAPI (01/06/2026).
- ✅ **Catalogue specs filtrables** : table `product_spec` + migration `e3b7a1c9d5f2` + `spec_definitions.yaml` (10 specs Ordinateur/Serveur) + projection dans `enrich_product_with_icecat_task` + `upsert_product_specs()` + endpoint `GET /product/categories/{id}/spec-facets` + job ARQ `reproject_product_specs_task`.
- ✅ **Filtre `is_enriched=True`** sur endpoints publics (`search`, `featured`, `GET /products`, `GET /product/{id}` → 404 si non enrichi sauf superuser).
- ✅ **Enqueue auto enrichment** à la création d'un produit supplier_managed dans `SupplierSyncOrchestrator.sync_products_to_database` (post-commit).
- ✅ **Recherche avancée PostgreSQL** : extension `pg_trgm` + index GIN FTS (`ix_products_search_fts`) + index GIN trgm sur `name` (`ix_products_name_trgm`) — migration `f2a4b8c1d9e3` ; `search_products()` utilise `to_tsvector @@ plainto_tsquery` avec classement `ts_rank`.
- ✅ **Seed CurrencyRate** USD/EUR automatique via `initial_data.py` (plus de config manuelle nécessaire au premier déploiement).
- ✅ **`meets_sync_thresholds` — conversion XPF** : `supplier_tasks.py` appelle `convert_to_xpf()` avant le check ; `meets_sync_thresholds()` reçoit `price_in_xpf` (fallback sur prix brut si `CurrencyRateMissing`). `SUPPLIER_SYNC_MIN_PRICE` est désormais interprété en XPF quelle que soit la devise fournisseur.
- ✅ **Documentation ops** : [DEPLOYMENT.md](DEPLOYMENT.md) §10-11 — variables d'environnement par catégorie, checklist premier déploiement, checks ARQ/outbox/taux FX en prod.
- ✅ **Fret import / CAF** (28/05/2026) : `calculate_sale_price()` calcule désormais la douane sur l'assiette CAF (`cost_in_reference + price_per_kg×billable_weight + assurance`) ; champs `service_level`/`customer_label`/`is_default_import` sur `ShippingRoute` (migration `a3b1c7e2d9f5`) + config `INSURANCE_RATE_PCT` (défaut 0) ; **poids taxable** `resolve_billable_weight()` = `max(poids, volume×dim_factor)` avec `dim_factor_kg_per_m3`/`billing_basis` lus depuis `route_metadata` (défauts avion 167 / mer 1000) intégré à `calculate_shipping_for_routes` (param `total_volume_m3`, fallback poids réel) ; **dimensions physiques Icecat** mappées vers `Product.dimensions_*`/`weight` (`icecat_service.py` + `icecat_tasks.py`) ; `calculate_price_by_mode()` → `list[ShippingModePrice]` ; **corridor France→Papeete** seedé (`initial_data.py` : places `FR_SUPPLIERS`/`PPT_CUSTOMS_WAREHOUSE` + routes avion/bateau) ; endpoint `GET /product/{id}/shipping-modes` (`shipping_modes` + `default_mode`) ; `pricing.ts` étendu CAF (`freightInReference`/`insuranceInReference`) ; dropdown niveau de service dans `ProductPage.vue` + `ProductDetailsDialog.vue` (recalcul local, persistance `localStorage`). 23 tests CAF/shipping verts (`test_product_pricing_caf.py`, `test_pricing.py`). Résidu reporté P2 : câblage `preferred_shipping_mode` (le champ `User`/`UserPreference` est créé en P2).
- ✅ Migration/seed Phase 1 : validés en environnement d'intégration (01/06/2026) — `alembic upgrade head` + seed `initial_data` (upgrade/downgrade + non-régression) OK. **Têtes alembic** : `a3b1c7e2d9f5` (unique head, chaîne `…→f2a4b8c1d9e3→c5d9e2f1a8b4→a3b1c7e2d9f5`). `schema.ts` régénéré depuis l'OpenAPI. Vitrine minimale OK testée.

### Périmètre fonctionnel

- Synchro Ingram Micro + Icecat opérationnelle (déjà partiellement présent).
- Catalogue avec prix calculés via la formule (groupe par défaut « Particulier »).
- Recherche par caractéristiques (specs Icecat) + filtres prix, marque, catégorie.
- Panier (déjà présent).
- « Demander un devis » → email au support avec détail panier + coordonnées.
- Produits mis en avant : flag manuel admin.

### Travaux backend

1. ✅ **Pricing**
   - ✅ Migration : ajout `cost_amount`, `cost_currency`, `customs_rate_pct` sur `Product`.
   - ✅ Modèle `PriceGroup` + seed (4 groupes ; en Phase 1 seul « Particulier » utilisé).
   - ✅ Service `pricing.py::calculate_sale_price(product, group)`.
   - ✅ `supplier_tasks.py` : stocker `cost_amount` au lieu d'écraser `base_price`.
   - ✅ Snapshot pricing dans `CartItem`.

1bis. ✅ **Fret import & assiette douane (CAF)** — cf. *Décision transverse : fret import & assiette douane (CAF)*.
   - ✅ Migration : `customer_label`, `is_default_import`, `service_level` sur `shipping_routes` (`a3b1c7e2d9f5`) ; config `INSURANCE_RATE_PCT` (défaut 0).
   - ✅ Refonte `calculate_sale_price()` : assiette CAF = `cost_in_reference + price_per_kg×billable_weight + assurance`, douane sur la CAF.
   - ✅ Helper `resolve_billable_weight()` = `max(poids, volume × dim_factor)` ; `dim_factor_kg_per_m3` + `billing_basis` lus depuis `route_metadata` (défauts avion 167 / mer 1000) ; fallback poids réel si dims absentes.
   - ✅ Enrichissement Icecat : dimensions physiques + poids mappés vers `Product.dimensions_*`/`weight` (`icecat_service.py` + `icecat_tasks.py`).
   - ✅ `calculate_price_by_mode(product, group, import_routes)` → `list[ShippingModePrice]`.
   - ✅ Corridor France→Papeete seedé (`initial_data.py` : places `FR_SUPPLIERS`/`PPT_CUSTOMS_WAREHOUSE` + routes avion/bateau).
   - ✅ Fiche produit : endpoint `GET /product/{id}/shipping-modes` (`shipping_modes` + `default_mode`).
   - ✅ `pricing.ts` étendu CAF (`freightInReference` / `insuranceInReference`).
   - ✅ Frontend : dropdown niveau de service (`ProductPage.vue` + `ProductDetailsDialog.vue`), recalcul local, persistance `localStorage`.
   - ✅ 23 tests CAF/shipping verts (`test_product_pricing_caf.py`, `test_pricing.py`).

2. ✅ **TVA / TGC**
   - ✅ Migration : modèle `TaxRate` (`code`, `label`, `rate_pct`, `territory_code`, `valid_from`, `valid_until`).
   - ✅ Migration : `Category.default_tax_rate_id` (FK nullable) + `Product.tax_rate_id` (FK nullable).
   - ✅ Migration : `OrderLine.tax_rate_id` (FK, snapshot figé au checkout).
   - ✅ Seed 3 taux PF (`TGC_NORMAL 16%`, `TGC_REDUIT 5%`, `TGC_EXONERE 0%`) — renommés TVA et complétés du 13 % le 30/09/2026 (voir « Prix, marge et TVA »).
   - ✅ Service `resolve_tax_rate(product, territory) -> TaxRate` dans `pricing.py`.
   - ✅ Toutes les catégories héritent de `TGC_NORMAL` par défaut.

2bis. ✅ **Persistance Icecat** *(socle corrigé en Phase 0, complété en Phase 1)*
   - ✅ Colonnes `technical_specifications`, `features`, `icecat_images` sur `products` + mapping activé dans `icecat_tasks.py`.
   - ✅ Cron Icecat récurrent : `icecat_batch_enrichment` toutes les `ICECAT_ENRICHMENT_CRON_INTERVAL_HOURS`=1 h, draine le backlog indépendamment des syncs fournisseur.
   - ✅ `batch_enrich_products_task` se ré-enqueue tant qu'un batch plein est trouvé ; cooldown `ICECAT_ENRICHMENT_RETRY_COOLDOWN_DAYS`=7 sur les SKU `not_found`/erreur.
   - ✅ Projection `product_spec` effectuée dans le batch (auparavant seul le single-produit la faisait).

3. ✅ **Recherche**
   - ✅ Migration `f2a4b8c1d9e3` : index GIN FTS (`ix_products_search_fts`) sur `tsvector(name || description || manufacturer || vendor_part_number)`.
   - ✅ Index GIN `gin_trgm_ops` sur `name` (`ix_products_name_trgm`) pour recherche tolérante aux fautes.
   - ✅ Index GIN sur `technical_specifications` JSONB.
   - ✅ `POST /product/search` : `q`, `category_id`, `manufacturer`, `price_min/max`, `specs`, `in_stock`, `limit/offset` ; `search_products()` utilise `to_tsvector @@ plainto_tsquery` + `ts_rank`.
   - ✅ Retour : produits + facettes (counts marque, tranche prix, valeur spec).

4. ✅ **Produits mis en avant**
   - ✅ Migration : `is_featured: bool`, `featured_position: int | null`, `featured_until: datetime | null` sur `Product`.
   - ✅ Endpoints admin `POST /product/{id}/feature` + `DELETE /product/{id}/feature`.
   - ✅ Endpoint public `GET /product/featured?limit=10`.

5. ✅ **Devises**
   - ✅ Migration `d1e5c3f8a294` : table `currency_rates` (`currency_code`, `rate_to_reference`, `valid_from`, `valid_until`, `source`, `updated_by_user_id`). *(colonne initialement `rate_to_xpf`, renommée `rate_to_reference` en migration `c5d9e2f1a8b4` — dé-localisation pré-prod)*
   - ✅ Migration snapshots FX : `CartItem` (`fx_rate_used`, `fx_source_currency`) + `OrderLine` (`cost_amount_snapshot`, `cost_currency_snapshot`, `fx_rate_used`, `customs_rate_pct_snapshot`, `margin_rate_pct_snapshot`, `price_group_id_snapshot`).
   - ✅ Helper `convert_to_reference_currency(amount, currency, at_date)` dans `pricing.py`. *(renommé depuis `convert_to_xpf`)*
   - ✅ Intégration dans `calculate_sale_price()` + `meets_sync_thresholds()` (`SUPPLIER_SYNC_MIN_PRICE` en devise de référence).
   - ✅ Snapshot `fx_rate_used` à la création de `CartItem`, propagé au checkout dans `OrderLine`.
   - ✅ Seed automatique USD/EUR via `initial_data.py` (plus de saisie manuelle nécessaire).
   - ✅ Endpoints admin `GET /admin/currency-rates` + `PUT /admin/currency-rates/{code}`.
   - ✅ Garde-fou : `CurrencyRateMissing` levée explicitement si aucun taux actif (pas de fallback silencieux).

6. ✅ **Catalogue de specs filtrables**
   - ✅ Migration `e3b7a1c9d5f2` : table `product_spec` (`product_id`, `spec_key`, `value_text`, `value_numeric`, `unit`) + 3 indices.
   - ✅ `spec_definitions.yaml` : 10 specs Ordinateur/Serveur (cf. décision transverse).
   - ✅ Projection JSONB → `product_spec` dans `enrich_product_with_icecat_task` et `batch_enrich_products_task`.
   - ✅ Enqueue auto `trigger_product_enrichment` à la création d'un `is_supplier_managed=True` dans `SupplierSyncOrchestrator`.
   - ✅ Filtre `is_enriched=True` sur tous les endpoints publics catalogue (search, featured, list, fiche → 404 si non enrichi, sauf superuser).
   - ✅ Endpoint `GET /product/categories/{id}/spec-facets`.
   - ✅ `POST /product/search` interprète `specs: {memory_gb_min: 16, cpu_family: ["i7","i9"]}`.
   - ✅ Job ARQ `reproject_product_specs_task(category_id=None)`.

7. ✅ **Demande de devis**
   - ✅ `POST /cart/quote-request` : lit le panier actif, envoie email Mailgun à `EMAIL_SUPPORT` (détail panier + coordonnées client), crée `QuoteRequest` en BDD.

8. ✅ **Préparatifs déploiement**
   - ✅ Endpoints `/healthz/liveness` + `/healthz/ready` (DB + Redis).
   - ✅ ARQ worker + outbox poller vérifiés opérationnels.
   - ✅ [DEPLOYMENT.md](DEPLOYMENT.md) §10-11 : variables d'environnement par catégorie, checklist premier déploiement, checks ARQ/outbox/taux FX en prod.

### Hors périmètre Phase 1

- Paiement en ligne, OAuth, groupes multiples actifs, tracking client, notifications email post-commande (puisqu'il n'y a pas de commande).

---

## Phase 2 — Compte client complet + CB + Groupes

**Objectif** : commande + paiement en ligne CB de bout en bout, gestion des comptes pros/revendeurs/public avec marges distinctes, login social.

**Statut** : ✅ Complète (08/06/2026) — 10 items sur 10 livrés.

**Chaîne Alembic** : `a3b1c7e2d9f5` → `b4c2d8e1f5a6` (user_preference) → `c5e3f9a2b7d1` (group_upgrade_request) → `d6f4a2e8b1c3` (user_oauth_links) → `e7a5b3c9d1f2` (address_is_validated) — head actuel : `e7a5b3c9d1f2`.

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| Inscription / login + OAuth Google/MS | ✅ | ✅ `LoginPage.vue` + `OAuthCallbackPage.vue` | ✅ `LoginPage.vue` (admin) |
| Profil + préférences utilisateur | ✅ `/users/me/preferences` | ✅ `MyAccountPage.vue` (onglet Préférences) | — |
| Adresses self-service + validation | ✅ | ✅ `MyAccountPage.vue` (onglet Adresses, CRUD) | ✅ `AddressesPage.vue` (02/07/2026) — validation **indicative, non bloquante** au checkout ; le texte de l'onglet Adresses dit encore le contraire (à corriger, R1-B) |
| Demande d'upgrade de groupe | ✅ | ✅ onglet « Groupe tarifaire » de `MyAccountPage.vue` | ✅ A6 (20/06/2026) |
| TVA / TGC — admin CRUD | ✅ `/admin/tax-rates` | — | ✅ A1 (20/06/2026) |
| Paiement CB (Payzen) | ✅ | ✅ `CheckoutPage.vue` + `PaymentReturnPage.vue` | — |
| Emails commande / paiement | ✅ | — (transactionnel) | — |
| Commande auto Ingram (SUPPLIER_DIRECT) | ✅ | — | ✅ A4 (20/06/2026) |
| Taxonomie / catégories internes | ✅ | ✅ sélecteur catégorie (`CataloguePage.vue`) | ✅ A12 / A17 (04/09/2026) |

### Avancement vitrine (19/06/2026)

- ✅ **Espace « Mon compte »** (`MyAccountPage.vue`, route `/mon-compte` name `account`, entrée nav toolbar + drawer visible si connecté ; redirection `login?redirect=/mon-compte` si anonyme).
  - ✅ Onglet **Préférences** : `GET/PUT /users/me/preferences` — toggles notifications (email, suivi expédition) + selects niveau de service import, préférence livraison, langue, devise. Bannières succès/erreur (Quasar `Notify` non activé dans ce projet).
  - ✅ Onglet **Adresses** : CRUD `/users/me/addresses` (liste cartes + badge `is_validated`, dialog création/édition, confirmation suppression).
  - Modules API : [frontend/src/api/account.ts](frontend/src/api/account.ts) · [frontend/src/api/addresses.ts](frontend/src/api/addresses.ts). Typecheck (`vue-tsc`) + lint verts.
- ✅ **Reste vitrine P2** *(périmé le 30/09/2026 : livré, onglet « Groupe tarifaire »)* : formulaire **demande d'upgrade de groupe**.
- ✅ **Reste vitrine P3** *(périmé le 30/09/2026 : livré, `OrderTrackingPage.vue`)* : page **suivi de commande**.

### Périmètre fonctionnel

- Inscription / connexion classique + OAuth Google + Microsoft.
- Profil utilisateur avec préférences (notification, livraison par défaut).
- Validation admin pour groupes « Professionnel », « Revendeur », « Public ».
- Pricing par groupe (les 4 groupes actifs).
- Paiement CB via Payzen (déjà câblé).
- Emails client : « Commande créée », « Paiement validé », « Paiement échoué ».
- Produits mis en avant (continuité Phase 1).

### Travaux backend

1. ✅ **TVA / TGC — admin CRUD** *(livré 08/06/2026)*
   - ✅ `GET /admin/tax-rates` (liste avec filtres `territory_code`, `valid`).
   - ✅ `POST /admin/tax-rates` (créer un nouveau taux, ne remplace pas l'ancien).
   - ✅ `PUT /admin/tax-rates/{id}` (modifier `label` ou fixer `valid_until` pour clôturer).
   - ✅ `PUT /admin/products/{id}/tax-rate` et `PUT /admin/categories/{id}/tax-rate`.
   - ✅ Garde-fou : `rate_pct` immutable sur un taux existant — modification bloquée avec `tax_rate.invalid_valid_until` (400).
   - Fichier : [app/api/routes/admin_tax_rates.py](backend/app/api/routes/admin_tax_rates.py)

2. ✅ **Groupes pricing actifs** *(livré 08/06/2026)*
   - ✅ Modèle `GroupUpgradeRequest` + migration `c5e3f9a2b7d1` (`status: PENDING/APPROVED/REJECTED`, `business_registration_number`, `attestation_notes`, `admin_comment`, `reviewed_by_id`).
   - ✅ `POST /users/me/upgrade-group` (bloque doublon PENDING, exige `requires_validation=True`).
   - ✅ `GET /users/me/upgrade-group` (liste propres demandes).
   - ✅ `GET /admin/group-upgrade-requests` (filtres `pending_only`, `user_id`).
   - ✅ `POST /admin/group-upgrade-requests/{id}/approve` → met à jour `User.price_group_id`.
   - ✅ `POST /admin/group-upgrade-requests/{id}/reject` (avec commentaire).
   - ✅ `POST /admin/users/{user_id}/assign-price-group` (affectation directe).
   - Fichier : [app/api/routes/group_upgrade.py](backend/app/api/routes/group_upgrade.py)

3. ✅ **RBAC — activation des permissions par groupe** *(livré 08/06/2026)*
   - ✅ Seed idempotent `_seed_security_groups()` dans `initial_data.py` : 3 groupes `group_type='security'` créés automatiquement au démarrage.
   - ✅ Groupe `support` (priority=10) : can_read sur `users`, `orders`, `order_lines`, `payments`, `payment_logs`.
   - ✅ Groupe `logistics_admin` (priority=20) : can_read+can_update sur `shipping_route_trackings`, `shipping_route_tracking_consolidations`, `delivery_tasks`.
   - ✅ Groupe `payment_admin` (priority=30) : can_read+can_update sur `payments`, `payment_validations`, `payment_attachments`.
   - Activation : passer `ENABLE_GROUP_PERMISSIONS=true` en prod **après** vérification que le superuser et les users existants fonctionnent (superuser bypass inconditionnel ; users sans groupe de sécurité non restreints).
   - Note : `CrudBase.check_user_permission()` est déjà implémenté et contrôlé par ce flag.
   - Fichier : [app/features/initial_data.py](backend/app/features/initial_data.py)

4. ✅ **OAuth Google + Microsoft** *(livré 08/06/2026)*
   - ✅ Modèle `UserOAuthLink(user_id, provider, provider_user_id, email_at_link, created_at)` + contrainte unique `(provider, provider_user_id)`.
   - ✅ Migration `d6f4a2e8b1c3` : table `user_oauth_links` avec FK CASCADE sur `users.id`, 3 index, contrainte `uq_oauth_provider_uid`.
   - ✅ Config : `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `MICROSOFT_CLIENT_ID`, `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`, `OAUTH_REDIRECT_BASE_URL`, `FRONTEND_OAUTH_REDIRECT_URL` ajoutés dans `settings`.
   - ✅ `GET /auth/{provider}/login` : génère state CSRF stocké en Redis (TTL 5 min, clé `oauth:state:{state}`), redirige vers la page d'autorisation du provider.
   - ✅ `GET /auth/{provider}/callback` : vérifie + consomme le state (`GETDEL`), échange le code via httpx, récupère le profil, find-or-create `User`, upsert `UserOAuthLink`, émet JWT identique au login classique, redirige vers `FRONTEND_OAUTH_REDIRECT_URL?access_token=...&refresh_token=...`.
   - ✅ Gestion erreurs : provider non configuré (503), state invalide, email/uid vide, erreur provider → redirection `?oauth_error=...` côté frontend (pas de 500 exposé).
   - ✅ Stratégie conflit email : si un compte password partage le même email, le compte OAuth y est rattaché automatiquement (pas de confirmation manuelle requise — décision simplifiée Phase 2).
   - ✅ Durcissement (Codex) : garde-fou compte inactif — un user `is_active=False` est bloqué (`session.rollback()` + redirection `?oauth_error=user_inactive`) **avant** émission de tout JWT, en parité avec le login password.
   - Implémentation httpx native (pas d'`authlib`).
   - Tests : `app/tests/api/test_oauth_routes.py` (provider non supporté, state invalide, blocage user inactif sans token, login actif avec tokens).
   - Fichiers : [app/api/routes/oauth.py](backend/app/api/routes/oauth.py) · [app/features/user/models/oauth_link.py](backend/app/features/user/models/oauth_link.py) · [app/alembic/versions/d6f4a2e8b1c3_phase2_user_oauth_link.py](backend/app/alembic/versions/d6f4a2e8b1c3_phase2_user_oauth_link.py)

5. ✅ **Préférences utilisateur** *(livré 08/06/2026)*
   - ✅ Modèle `UserPreference` + migration `b4c2d8e1f5a6` (`notification_email_enabled`, `notification_shipping_steps`, `default_shipping_preference`, `locale`, `currency_pref`, `preferred_shipping_mode`).
   - ✅ CRUD `get_preference_for_user` / `upsert_preference_for_user` (upsert, caller commit).
   - ✅ `GET /users/me/preferences` (renvoie défauts si pas encore de ligne).
   - ✅ `PUT /users/me/preferences` (validation enum-like : `default_shipping_preference` ∈ `{fastest,cheapest,eco_friendly}`, etc.).
   - ✅ Câblage `preferred_shipping_mode` dans `GET /product/{id}/shipping-modes` : priorité user preference > `is_default_import` > première route.
   - Fichiers : [app/features/user/models/user_preference.py](backend/app/features/user/models/user_preference.py) · [app/api/routes/user_preferences.py](backend/app/api/routes/user_preferences.py)

6. ✅ **Email notifications commande/paiement** *(livré 08/06/2026)*
   - ✅ `order.created` publié dans `checkout_my_cart` (avant `session.commit()`, outbox pattern).
   - ✅ Handler `on_order_created` → email « Commande reçue » (text + HTML Jinja2) au client.
   - ✅ Handler `on_payment_captured_customer` → email « Paiement validé » (text + HTML Jinja2, bouton vert) au client.
   - ✅ Handler `on_payment_rejected_customer` → email « Paiement échoué » (text + HTML Jinja2, motif affiché) au client.
   - ✅ `notifications.py` mis à jour : `_collect_email_targets` n'inclut plus `user_id` (client notifié uniquement par les handlers dédiés ci-dessus ; admin/support reçoivent le message technique sans doublon).
   - Templates compilés au chargement du module (Jinja2 inline, pas de fichiers séparés).
   - Auto-découverte par `outbox/loader.py` au démarrage, aucune registration manuelle.
   - Fichier : [app/handlers/order.py](backend/app/handlers/order.py)

7. ✅ **Adresses validées** *(livré 08/06/2026)*
   - ✅ Champ `is_validated: bool = False` ajouté au modèle `Address` + exposé dans `AddressPublic`.
   - ✅ Migration `e7a5b3c9d1f2` : colonne `is_validated BOOLEAN DEFAULT FALSE NOT NULL` sur `addresses`.
   - ✅ `GET /users/me/addresses` — liste les adresses de l'utilisateur connecté (avec `skip`/`limit`).
   - ✅ `POST /users/me/addresses` — crée une adresse pour soi-même (`is_validated=False` par défaut).
   - ✅ `GET /users/me/addresses/{id}` — lecture d'une adresse propre.
   - ✅ `PATCH /users/me/addresses/{id}` — mise à jour (champs adresse uniquement, `is_validated` non modifiable par l'utilisateur).
   - ✅ `DELETE /users/me/addresses/{id}` — suppression.
   - ✅ `POST /admin/addresses/{id}/validate` (superuser) — valide une adresse ; idempotent si déjà validée.
   - ✅ CRUD `validate_address(session, address)` — mutation directe + commit.
   - ✅ Durcissement (Codex) : payloads dédiés `AddressMeCreate` / `AddressMeUpdate` (sans `user_id` ni `is_validated`) ; la route admin `/users/{user_id}/addresses/{id}` ignore toute mutation de `user_id`.
   - 🐛 **Correctif ordre des routes (08/06/2026)** : les routes `/users/me/addresses[...]` étaient déclarées *après* `/users/{user_id}/addresses[...]` dans le même routeur ; Starlette liait `user_id="me"` → 422, rendant les endpoints self-service inatteignables. Déplacées **avant** le bloc `{user_id}`. Couvert par `test_address_me_routes.py`.
   - Les routes admin existantes `/users/{user_id}/addresses` sont conservées pour la gestion admin.
   - Code erreur `address.already_validated` réservé (non levé actuellement — l'endpoint est idempotent).
   - Tests : `app/tests/api/test_address_me_routes.py` (self-service + validation admin), `test_address_error_http_contract.py` (contrat d'erreur).
   - Fichiers : [app/features/user/models/address.py](backend/app/features/user/models/address.py) · [app/features/user/crud/address.py](backend/app/features/user/crud/address.py) · [app/api/routes/address.py](backend/app/api/routes/address.py) · [app/alembic/versions/e7a5b3c9d1f2_phase2_address_is_validated.py](backend/app/alembic/versions/e7a5b3c9d1f2_phase2_address_is_validated.py)

8. ✅ **Commande automatique chez Ingram Micro (SUPPLIER_DIRECT)** *(livré 08/06/2026)*
   - ✅ **Déclencheur** : handler outbox `on_payment_captured_create_ingram_order` sur `payment.captured` (cohabite avec le sync statut et la notif client sur le même event). Garde sur le flag `INGRAM_ORDER_CREATION_ENABLED`.
   - ✅ **Modèle** `SupplierOrder` + migration `f4a2b7c9d1e3` (table `supplier_orders`, dans la lignée Alembic, tête unique confirmée) : `local_order_id`, `supplier_name`, `customer_order_number`, `supplier_order_number`, `status` (`pending/submitted/error/skipped`), `lines_snapshot JSON`, `supplier_response JSON`, `error_message`, `attempts`, `created_at`, `updated_at`.
   - ✅ **Service** `process_ingram_purchase_order(session, order_id, *, reraise_on_api_error)` (extrait dans `supplier_order_service.py`, réutilisé par le handler ET le retry admin) :
     - Filtre les lignes dont `product.supplier_name == "ingram_micro"` et `supplier_sku` présent ; mappe vers `ingramPartNumber/quantity/unitPrice/vendorPartNumber`.
     - `IngramMicroService.create_purchase_order` → `POST /resellers/v6/orders` (déjà implémenté).
     - Persiste le `SupplierOrder` ; statut `SKIPPED` (pas de ligne Ingram), `ERROR` (ship-to non configuré ou API en échec), `SUBMITTED` (PO accepté).
   - ✅ **Idempotence** : `customerOrderNumber` = UUID commande locale (dédup Ingram) ; court-circuit si un `SupplierOrder` `SUBMITTED` existe déjà.
   - ✅ **Retry** : sur échec API, le handler **re-raise** (l'outbox rejoue avec backoff) ; le `SupplierOrder` est marqué `ERROR` avant le re-raise et `attempts` incrémenté.
   - ✅ **Endpoints admin** (`CurrentSuperUser`) : `GET /admin/supplier-orders` (filtres `status`, `supplier_name`, pagination `skip`/`limit`), `GET /admin/supplier-orders/{id}`, `POST /admin/supplier-orders/{id}/retry` (idempotent si `SUBMITTED` ; `reraise_on_api_error=False` → renvoie le `SupplierOrder` `ERROR` en 200 avec `error_message` plutôt qu'un 5xx).
   - ✅ Ship-to = entrepôt (settings `INGRAM_SHIP_TO_*`), jamais l'adresse client.
   - Code erreur `supplier_order.not_found` (404).
   - Tests : `app/tests/test_supplier_order_service.py` (skip/error/submitted/short-circuit/re-raise), `app/tests/test_ingram_payment_handler.py` (garde flag, order_id invalide, délégation), `app/tests/api/test_admin_supplier_orders.py` (liste/filtre/404/retry).
   - Fichiers : [app/handlers/ingram_micro.py](backend/app/handlers/ingram_micro.py) · [app/features/integrations/services/supplier_order_service.py](backend/app/features/integrations/services/supplier_order_service.py) · [app/features/integrations/models/supplier_order.py](backend/app/features/integrations/models/supplier_order.py) · [app/api/routes/admin_supplier_orders.py](backend/app/api/routes/admin_supplier_orders.py) · [app/services/suppliers/ingram_micro.py](backend/app/services/suppliers/ingram_micro.py) · [app/alembic/versions/f4a2b7c9d1e3_add_supplier_orders_table.py](backend/app/alembic/versions/f4a2b7c9d1e3_add_supplier_orders_table.py)
   - ⚠️ **Activation prod** : passer `INGRAM_ORDER_CREATION_ENABLED=true` **après** avoir renseigné `INGRAM_SHIP_TO_ADDRESS_LINE1` + `INGRAM_SHIP_TO_CITY` (sinon les PO partent en `ERROR`).

   #### 🧪 Tester la création auto en dev sur la **sandbox Ingram**

   Le mécanisme est livré ; il suffit de le **configurer + déclencher**. Le service bascule seul sur l'URL sandbox (`https://api.ingrammicro.com/sandbox`) quand `INGRAM_ENVIRONMENT=sandbox` (déjà la valeur par défaut). Le handler s'exécute dans l'**arq-worker** → la config doit être présente sur le **worker** (et le **backend** pour le retry admin), pas seulement en local.

   **Pré-requis externe** : obtenir des identifiants **sandbox** sur le portail développeur Ingram (`CLIENT_ID`, `CLIENT_SECRET`, `CUSTOMER_NUMBER` de test) + au moins un **part number valide dans le catalogue sandbox**.

   1. **Config** (env des services `backend` + `arq-worker` + `outbox-poller` dans `docker-compose.yml`) :
      - `INGRAM_ENVIRONMENT=sandbox`
      - `INGRAM_CLIENT_ID=…`, `INGRAM_CLIENT_SECRET=…`, `INGRAM_CUSTOMER_NUMBER=…`, `INGRAM_COUNTRY_CODE=FR`
      - `INGRAM_ORDER_CREATION_ENABLED=true`
      - Ship-to (entrepôt) : `INGRAM_SHIP_TO_CONTACT`, `INGRAM_SHIP_TO_COMPANY_NAME`, `INGRAM_SHIP_TO_ADDRESS_LINE1`, `INGRAM_SHIP_TO_CITY`, `INGRAM_SHIP_TO_POSTAL_CODE`, `INGRAM_SHIP_TO_COUNTRY_CODE` (défaut `PF`), `INGRAM_SHIP_TO_PHONE`.
   2. **Recréer** les conteneurs (la config est lue au démarrage ; worker/poller **ne hot-reloadent pas**) : `docker compose up -d backend arq-worker outbox-poller`.
   3. **Produit Ingram** : avoir un `Product` avec `supplier_name="ingram_micro"` et un `supplier_sku` = un **part number sandbox valide** (via une sync `INGRAM_SYNC_ENABLED`, ou inséré à la main). Un SKU inconnu de la sandbox → `SupplierOrder` en `ERROR`.
   4. **Déclencher `payment.captured`** (le plus simple en dev, sans CB) : passer une commande avec ce produit, payer par **Bon de commande** ou **Virement/Chèque**, puis **valider le paiement dans l'admin** → `manual_payment`/`document_payment` émettent `payment.captured` → l'outbox enchaîne sur le handler. (En CB, la capture PayZen sandbox émet le même event.)
   5. **Vérifier** : écran admin **Commandes fournisseurs** (`/supplier-orders`) → statut `SUBMITTED` (PO accepté, `supplier_order_number` dans `supplier_response`) / `ERROR` (voir `error_message`) / `SKIPPED` (aucune ligne Ingram). Logs `arq-worker` + `outbox-poller`. En cas d'`ERROR`, rejouer via le bouton/route `POST /admin/supplier-orders/{id}/retry`.

   ⚠️ Pièges : la config doit être sur le **worker** (sinon le flag/credentials manquent au moment du handler) ; `INGRAM_ORDER_CREATION_ENABLED` par défaut `False` ; ship-to incomplet → `ERROR`.

   - 💡 **(Optionnel — plus tard) Durcir la dédup anti-doublon** : la protection actuelle est solide (court-circuit si `SUBMITTED` + réutilisation de la ligne + **dédup Ingram via `customerOrderNumber` = UUID commande**, qui empêche le vrai double-PO côté fournisseur). Seule faille théorique : pas de **contrainte d'unicité DB** sur `local_order_id` → une concurrence vraie pourrait créer 2 lignes `SupplierOrder` locales (doublon cosmétique, pas de double commande chez Ingram). Pour fermer définitivement la fenêtre : **index unique partiel sur `(local_order_id, supplier_name)`** (hors états d'échec) + migration Alembic. Non prioritaire.

9. ✅ **Paiement CB en production** *(livré 08/06/2026)*
   - ✅ `PAYZEN_STATIC_URL` externalisé en config (plus de `"https://static.osb.pf"` codé en dur dans `payzen.py`).
   - ✅ `_TERMINAL_PAYMENT_STATUS_NAMES: frozenset[str]` ajouté dans `payments.py` pour classifier les statuts terminaux.
   - ✅ `GET /payments/me/{payment_id}` : vérification ownership (`payment.user_id == current_user.id`), résolution du nom de statut via `session.get(PaymentStatus, ...)`, flag `is_terminal`, modèle `PaymentStatusResponse`.
   - ✅ Frontend `src/api/payments.ts` : `listPaymentMethods()`, `initiatePayment()`, `getMyPaymentStatus()`.
   - ✅ `CheckoutPage.vue` : résumé panier, sélection auto de la première méthode Payzen, appel `POST /payments/initiate`, stockage `payment_id` dans `localStorage['payzen.pending_payment_id']`, injection dynamique du script SmartForm depuis `{server_url}/static/js/krypton-client/V4.0/ext/smartform.min.js` avec `kr-public-key` + `kr-form-token` + `kr-post-url-success`.
   - ✅ `PaymentReturnPage.vue` : lit `payment_id` depuis localStorage, poll `GET /payments/me/{id}` toutes les 2 s jusqu'à `is_terminal`, affiche succès/refus/timeout (2 min), nettoie localStorage en cas de statut terminal.
   - ✅ Routes : `/checkout` (name: `checkout`) + `/paiement/retour` (name: `payment-return`) ajoutées dans `routes.ts`.
   - Tests : `app/tests/api/test_payments_me_status.py` (404 not_found, 403 not_owned, `is_terminal` True/False selon statut).
   - Fichiers : [app/api/routes/payments.py](backend/app/api/routes/payments.py) · [frontend/src/api/payments.ts](frontend/src/api/payments.ts) · [frontend/src/pages/CheckoutPage.vue](frontend/src/pages/CheckoutPage.vue) · [frontend/src/pages/PaymentReturnPage.vue](frontend/src/pages/PaymentReturnPage.vue) · [frontend/src/router/routes.ts](frontend/src/router/routes.ts)

10. ✅ **Taxonomie interne & facettes specs** *(livré 08/06/2026 — remonté du polish P1)*

   ✅ **Problème résolu** : `Product.category_id` restait `None` pour tous les produits fournisseurs, bloquant dropdown Catégorie et filtres specs côté vitrine.

   - ✅ `get_or_create_by_name(session, *, name)` sur `crud_category` : lookup insensible à la casse (`ILIKE`), crée la `Category` si absente, `is_active=True`, retourne `(category, created: bool)`.
   - ✅ Câblage dans `SupplierSyncOrchestrator.upsert_product` : `category_id` renseigné depuis `item.subcategory` à chaque sync.
   - ✅ Task ARQ `backfill_product_categories_task(batch_size=200)` : sélectionne les produits `supplier_subcategory IS NOT NULL AND category_id IS NULL`, traite par batch, commit par batch, idempotent.
   - ✅ `POST /suppliers/admin/backfill-product-categories` (superuser) : déclenche le backfill inline pour maintenance.
   - Résolution adoptée : option (b) — `get_or_create` par `supplier_subcategory`, fusion/renommage admin a posteriori. *(30/09/2026 : complétée par un mappage explicite par fournisseur, cf. Feuille de route R4 / S5.)*
   - Cohérence P3 : ce socle prépare l'extension specs multi-catégories (migration YAML → table `spec_definition` éditable).
   - Fichiers : [app/features/product/crud/category.py](backend/app/features/product/crud/category.py) · [app/features/integrations/services/supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py) · [app/tasks/supplier_tasks.py](backend/app/tasks/supplier_tasks.py)

### Hors périmètre Phase 2

- Chèque / virement / BC, tracking, remboursement, factures.
- Webhook Ingram de suivi statut commande fournisseur (reporté Phase 3).

---

## Phase 3 — Modes de paiement étendus + tracking simple

**Objectif** : couvrir tous les modes de paiement (chèque, virement, BC) avec contrôle d'éligibilité par groupe, et notifier le client des étapes de livraison.

**Statut** : ✅ Complète (08/06/2026) — 7 items sur 7 livrés.

**Chaîne Alembic** : `e7a5b3c9d1f2` → `a8b4c2f1e6d9` (payment_eligibility) → `b9c5d3e2f7a1` (supplier_order_webhook) → `c1d6e4f3a8b2` (spec_definitions) → `d2e7f5a4b9c3` (system_settings) — head actuel : `d2e7f5a4b9c3`.

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| Éligibilité paiement ↔ groupe | ✅ | ✅ **choix du type de paiement au checkout** (CB / chèque / virement / BC), filtré par éligibilité | ✅ écran éligibilité (`PaymentEligibilityPage.vue`) |
| Notifications tracking (expédié / livré) | ✅ | — (email) | — |
| Suivi de commande client | ✅ `/orders/me/{id}/tracking` + `GET /orders/me` | ✅ `MyAccountPage.vue` (onglet Commandes) + `OrderTrackingPage.vue` | — |
| Webhook Ingram — statut fournisseur | ✅ | — | 🔲 visible via écran `supplier-orders` (backlog P2) |
| **Catalogue specs éditable (multi-cat.)** | ✅ `/admin/spec-definitions` | — | 🔲 **écran CRUD specs + alias** |
| Devises — display setting | ✅ `/system/settings` | 🔲 toggle devise (→ P4) | 🔲 écran `system-settings` |

### Avancement vitrine — choix du moyen de paiement (23/06/2026)

- ✅ **`CheckoutPage.vue` refondu** : le checkout affiche désormais **la liste des moyens de paiement éligibles** (filtrés par groupe + `max_amount` via `GET /payments/me/methods`) et laisse le client **choisir** — auparavant il auto-sélectionnait uniquement la CB Payzen. Dispatch par provider à l'initiation (`POST /payments/initiate`) :
  - **CB (Payzen, provider API)** → SmartForm (flux existant) ;
  - **Manuel (chèque / virement)** + **Document (BC)** → affichage des **`instructions`** renvoyées + confirmation « commande enregistrée, en attente de validation », bouton « Voir mes commandes ».
- ✅ **Upload de pièce (BC)** *(23/06/2026)* : pour un provider `document`, l'UI propose le **téléversement du bon de commande** (`q-file`) puis exécute le flux presigned en 3 temps — `POST /payments/{id}/upload-document` → `PUT` du fichier vers l'URL presignée → `POST /payments/{id}/document-uploaded` — avec confirmation « document reçu, en cours de vérification ». Garde-fou : l'URL presignée locale (`LocalFileStorage`) est construite côté backend sur `FRONTEND_HOST` (mauvais hôte en multi-origine) → le front la reconstruit sur `VITE_API_URL` quand elle vise `/internal/storage/` ; les URL S3 sont utilisées telles quelles. Fonctions : [frontend/src/api/payments.ts](frontend/src/api/payments.ts) (`issueDocumentUploadUrl` / `uploadFileToPresignedUrl` / `confirmDocumentUploaded`).
- ⚠️ Le checkout vitrine ne calcule toujours pas de frais de port (étape shipping reportée, cf. *Avancement vitrine — mode de livraison*) ; le `fee` du moyen de paiement est affiché à titre indicatif mais non ajouté au montant débité (comportement existant conservé).

#### 🐛 Correctif — création de commande au checkout (23/06/2026)

**Bug** : choisir un paiement non‑CB (chèque…) ne créait **aucune commande**, ne vidait pas le panier, et n'affichait pas les instructions. **Cause racine** : le panier de la vitrine était **100 % `localStorage`** (le store n'appelait jamais le backend) et le checkout appelait `POST /payments/initiate` **directement** — or `initiate` crée seulement un *paiement*, pas la commande, et `checkout_my_cart` (`POST /cart/checkout`, qui crée order + lignes + stock + vide le panier + publie `order.created`) lit le **panier backend** inexistant.

**Correctif** (`CheckoutPage.vue` + `frontend/src/api/cart.ts`) — au clic « Procéder » : (1) **synchro panier local → backend** (`clearMyCart` puis `addCartItem` par ligne), (2) **`POST /cart/checkout`** (crée la commande, vide le panier backend) → `{order_id, total_amount}`, (3) **vidage du panier local**, (4) **`POST /payments/initiate`** lié à `order_id` (montant = total backend autoritaire) → SmartForm / instructions. La commande apparaît désormais dans *Mon compte → Commandes*, le panier se vide, les instructions s'affichent. Le vidage local **après** checkout empêche les commandes en double sur retry (un retry retombe sur « panier vide »).

- ⚠️ **Persistance panier** : la synchro n'a lieu **qu'au checkout** (le panier reste `localStorage` pour la navigation/invité). Migrer le store vers le panier backend (auth) est un chantier distinct.

#### 🐛 Correctifs `MissingGreenlet` révélés par le checkout (23/06/2026)

Une fois le checkout réellement atteint, **3 bugs latents** sont apparus : des attributs ORM lus **après** un `session.commit()` (qui expire les instances) déclenchaient un lazy‑load **synchrone** → `sqlalchemy.exc.MissingGreenlet`. Correctif systématique : **capturer les valeurs avant le commit**.
- `DELETE /cart/items` + `POST /cart/items` : `cart.id` relu après `clear_cart`/`add_or_increment` (qui committent) → capture `cart_id` en tête.
- `POST /cart/checkout` : `current_user.id` relu dans le logging post‑commit → capture `user_id` en tête.
- `POST /cart/checkout` : `[route.id for route in selected_routes]` (routes non refresh) lus à la construction de `CheckoutResponse` après commit → capture avant commit.

#### Refactor paiement unique (P1)

- ✅ **Service partagé extrait** : `app/features/payment/services/payment_initiation.py::initiate_payment_for_method` encapsule résolution provider + éligibilité + création paiement + dispatch (API SmartForm / manuel / document), **sans commit** (le caller possède la transaction). `POST /payments/initiate` l'utilise désormais (comportement préservé ; patches de tests redirigés vers le service).
- ✅ **Unification câblée (paiement unique)** *(23/06/2026)* : `CheckoutRequest` reçoit `payment_method_id` + `return_url` ; `checkout_my_cart` appelle `initiate_payment_for_method` **dans la même transaction** que la création de commande (plus de placeholder), et `CheckoutResponse` expose `provider_code`/`form_token`/`server_url`/`public_key`/`instructions`. Le front [CheckoutPage.vue](frontend/src/pages/CheckoutPage.vue) n'appelle **plus** `/payments/initiate` : un seul appel `POST /cart/checkout` → **une commande, un paiement**, dispatch SmartForm/instructions sur la réponse. Fallback placeholder conservé si `payment_method_id` absent (compat). Atomicité : un moyen de paiement invalide (éligibilité, etc.) annule toute la commande (rollback). Test : `test_checkout_with_payment_method_runs_single_payment_initiation`. `cart.ts` étend les types en attendant la régénération de `schema.ts`.

#### 🐛 Lot de correctifs post‑checkout (23/06/2026)

Retours utilisateur après que le checkout fonctionne :
1. **Adresse de livraison au checkout** *(Issue 1)* — le checkout ne demandait pas d'adresse (`shipping_address` toujours `null`). Ajout d'un **sélecteur d'adresse validée** dans [CheckoutPage.vue](frontend/src/pages/CheckoutPage.vue) (chargée via `listMyAddresses`, filtrée `is_validated`), bouton « Procéder » désactivé tant qu'aucune adresse n'est choisie, snapshot envoyé en `shipping_address` à `/cart/checkout`. État vide → renvoi vers *Mon compte → Adresses*.
2. **Étapes de suivi illisibles** *(Issue 2)* — `OrderTrackingPage.vue` affichait `segment.notes` brut, or le backend y stockait des métadonnées internes (`origin=checkout_selected_routes;sequence=1`). Backend : `notes=None` sur les `ShippingRouteTracking` (champ **public**). Front : `customerNote()` masque toute note au format interne `clé=valeur` (couvre les commandes existantes).
3. **Statut de commande invisible** *(Issue 3c)* — le storefront n'affichait jamais le statut de commande (`order_status_id` opaque) ; le « en attente » visible était le **statut d'expédition** du suivi (inchangé par le paiement, c'est normal). Backend : `/orders/me` expose désormais `order_status_name` (modèle `MyOrderPublic`). Front : **chip de statut** par commande dans *Mes commandes* (Pending→En attente, AwaitingPayment→En attente de paiement, Paid→Payée, PaymentFailed→Paiement refusé) ; le titre du suivi devient « Statut d'expédition » pour lever la confusion. *(Côté backend l'approbation publiait déjà `payment.captured` → `on_payment_captured` met l'order à « Paid ».)*
4. **Référence non pertinente pour le PO** *(Issue 3b)* — dans l'admin, le champ « Référence (n° de chèque…) » s'affichait pour tous ; masqué pour les providers **document** (`isDocumentProvider`), remplacé par un rappel « vérifiez la pièce jointe ».
5. **BC joint non visible** *(Issue 3a)* — la liaison pièce↔paiement est **correcte côté code** (`confirm_document_uploaded` → `register_uploaded_attachment(payment_id=…)`), et l'admin a un bouton « Pièces » (providers document) tant que le paiement est en attente. ⏳ À confirmer côté usage (le BC a‑t‑il bien été téléversé ?) + **gap connu** : une fois le paiement approuvé, il sort de la file et la pièce n'est plus consultable (pas encore d'historique paiements admin) ; **wart presigned** (`LocalFileStorage` construit l'URL sur `FRONTEND_HOST`) pouvant faire échouer silencieusement le PUT en dev.

#### 🐛 Storage des pièces jointes éphémère / non partagé (23/06/2026)

**Symptômes** : BC bloqué sur « analyse… » + `GET /internal/storage/{token}` → **500 `StorageError: Object … not found`** alors que la ligne attachment existe. **Cause racine** (pas S3 en soi) : `FILE_STORAGE_LOCAL_ROOT = /tmp/fastapi_ecommerce_storage` n'était **monté dans aucun volume** → (1) le fichier vivait dans le `/tmp` **éphémère** du conteneur `api` et disparaissait à chaque restart/rebuild ; (2) le **scan AV tourne dans `arq-worker`** (conteneur séparé) qui lisait son **propre** `/tmp` vide → `get_bytes` échoue → le handler `on_payment_document_uploaded` retourne sans poser `av_scanned=True` → « analyse… » éternel (`CLAMAV_ENABLED=true`). **Fix** ([docker-compose.yml](docker-compose.yml)) : **named volume `storage_data` partagé** monté sur `/tmp/fastapi_ecommerce_storage` dans `api` **et** `arq-worker` → fichiers persistants et visibles par le worker. L'`override` (dev) ajoute ses bind-mounts `./backend/app` ; Compose concatène les volumes (cibles distinctes) → cohabitation OK. ⚠️ Les BC déjà uploadés sont **perdus** (ancien `/tmp`) → re-téléverser. *(proxy/prod : à doter du même volume lors d'un déploiement réel.)*

#### 🐛 Téléchargement BC : nom + scan AV bloqué « analyse… » (23/06/2026)

- **Nom de fichier = token** : `GET /internal/storage/{token}` ne posait pas de `Content-Disposition` → le navigateur nommait le fichier d'après le token. Fix : l'endpoint lit le param `?filename=` et pose `Content-Disposition: attachment; filename="…"; filename*=UTF-8''…` (accents OK), avec repli sur le basename de la clé.
- **« analyse… » figé** (`av_scanned=False`) : le scan AV tourne dans **`arq-worker`** (le poller enqueue des jobs ARQ → `execute_outbox_handler`). Le handler `on_payment_document_uploaded` **avalait** l'échec scan/storage (`return`) → vu comme succès (clé d'idempotence posée) → **jamais réessayé**. Fix : le handler **`raise`** désormais sur échec → ARQ réessaie (`max_tries=5`). ⚠️ Le BC déjà bloqué ne s'auto-répare pas (clé d'idempotence) → **re-téléverser une fois**. Échappatoire dev : `CLAMAV_ENABLED=false` (NoOp → « sain » instantané).
- **Visibilité / diagnostic** : poller, consumer et dispatch loguent en **DEBUG** → invisibles à `LOG_LEVEL=INFO` (donc « rien dans les logs » ≠ « ne marche pas »). Ajout de logs **INFO** dans le handler de scan (« AV scan starting/complete/failed »). ⚠️ **Annulé** l'idée de `arq-worker depends_on clamav` : le worker traite **tous** les events (statut commande, emails…) → ne doit pas être bloqué si clamav est lent/instable ; le retry du handler couvre le cas « scanner pas prêt ».

#### 🐛🔥 ROOT CAUSE — Poller bouché par des events sans handler (23/06/2026)

**LE** vrai problème derrière « scan jamais fait » **et** « statut commande inchangé après validation » : les logs poller montraient en boucle `No handlers found for event type: update.product` (tentative 150+). Le CRUD générique publie des events `update.{entity}` (ex. `update.product`) que **personne ne handle** (`product.py` n'a qu'un handler `create.product`). Or le poller, sur « no handler », **rescheduleait en retry** (backoff plafonné 900s) **au lieu de marquer terminal**. Ces vieux events (les plus anciens → priorité `order_by(created_at)`) **monopolisaient** le poller (1 event/cycle) → les `payment.captured` / `payment.document_uploaded` n'étaient **jamais atteints**. **Fix** ([poller.py](backend/app/outbox/poller.py)) : si `outbox_registry.get_handlers(type)` est vide → event marqué **`DONE` (skipped)**, plus de retry infini → la file se draine et les events utiles passent. Tests : `test_poll_outbox_once_skips_event_without_handler`. ⚠️ Recréer le **poller** (`docker compose up -d` — pas de `--reload`).

**+ Vitesse de drainage** : la boucle `run_continuous` dormait `interval` (5s) après **chaque** event, même skippé → un gros backlog se vidait à 1 event/5s (des dizaines de minutes), affamant quand même `payment.*`. Fix ([outbox_poller.py](backend/app/scripts/outbox_poller.py)) : `continue` (pas de sleep) tant qu'un event a été traité ; on ne temporise que quand la file est **vide**. ⚡ Purge immédiate du backlog existant (via adminer:8080) : `UPDATE outbox_event SET status='DONE' WHERE status='PENDING' AND attempts > 20;` — débloque sans attendre le drainage.

#### 🐛 Admin — file de validation des paiements (23/06/2026)

D'après le screenshot d'une ligne `po_public` :
- **Bouton « Pièces » jamais affiché** *(vrai bug 3a)* : `isDocumentProvider('po_public')` testait `startsWith('document')` → `false`. Backend : `pending-validation` renvoie désormais un flag **`is_document`** (= `provider_code in DOCUMENT_PROVIDER_CODES`) ; la page l'utilise pour le bouton « Pièces » **et** pour masquer le champ Référence. Fallback front : `isDocumentProvider` reconnaît aussi `po_*`.
- **Nom du client** : `PaymentPendingValidationItem` expose `user_name`/`user_email` (résolus en une requête `User`) ; la colonne « Client » affiche le nom (fallback email, puis id court).
- **Type lisible** : `providerLabel` mappe `po_*`/`document*` → **« Bon de commande »**.
- ✅ **A18 — Page « Commandes clients » admin** *(23/06/2026)* : nouveau module backend `admin_orders.py` (superuser) — `GET /admin/orders` (liste enrichie : nom client + nom statut + total, récents d'abord) et `GET /admin/orders/{id}` (détail : client, statut, **lignes** avec nom produit, **paiements** — tous, avec statut/provider/référence, adresse, notes). Front admin : `OrdersPage.vue` (liste) + `OrderDetailPage.vue` (détail) + routes `/orders` & `/orders/:id` + entrée nav « Commandes clients ». La file de validation des paiements **lie** désormais la colonne Commande vers `/orders/:id`. Helpers statut FR partagés dans `api/orders.ts`.

### Périmètre fonctionnel

- Modes de paiement chèque / virement / BC (déjà câblés providers).
- Éligibilité par groupe : ex. BC réservé à « Public » + « Revendeur ».
- Limites monétaires par mode.
- Notifications client `shipping_started` / `shipping_delivered`.
- Endpoint client de suivi de commande.

### Travaux backend

1. ✅ **Éligibilité PaymentMethod ↔ PriceGroup** *(livré 08/06/2026)*
   - ✅ Migration `a8b4c2f1e6d9` : table `payment_method_eligibility(payment_method_id, price_group_id)` + champ `max_amount` sur `payment_methods`.
   - ✅ Modèle `PaymentMethodEligibility` + service `eligibility.py` (`get_eligible_payment_methods`, `check_payment_method_eligible`).
   - ✅ Sémantique open-default : aucune ligne → méthode disponible à tous les groupes ; au moins une ligne → restreint aux groupes listés.
   - ✅ Endpoint `GET /payments/me/methods` (auth) filtré par groupe + `cart_total` vs `max_amount` ; le frontend checkout l'utilise pour les clients connectés (fallback public pour les invités).
   - ✅ Garde-fou dans `POST /payments/initiate` : résolution de méthode d'abord (404 `not_found` / 400 `inactive`), puis `payment.method.not_eligible` (403) si non éligible.
   - ✅ Admin : `GET/POST/DELETE /admin/payment-methods/{id}/groups/{group_id}`.
   - Fichiers : [app/features/payment/models/payment_method_eligibility.py](backend/app/features/payment/models/payment_method_eligibility.py) · [app/features/payment/services/eligibility.py](backend/app/features/payment/services/eligibility.py) · [app/api/routes/admin_payment_eligibility.py](backend/app/api/routes/admin_payment_eligibility.py)

2. ✅ **Notifications tracking** *(livré 08/06/2026)*
   - ✅ `POST /{tracking_id}/update-status` publie `tracking.status_changed` (outbox) avec `{tracking_id, order_id, status_code, status_name, tracking_ref, estimated_delivery}`.
   - ✅ Handler `on_tracking_status_changed` dans `handlers/shipping.py` : détecte codes `shipped` / `delivered`, charge le user via l'order, vérifie `UserPreference.notification_shipping_steps`, envoie l'email.
   - ✅ Templates Jinja2 inline pour « expédiée » (bleu) et « livrée » (vert).
   - Fichier : [app/handlers/shipping.py](backend/app/handlers/shipping.py)

3. ✅ **Endpoint client de tracking** *(livré 08/06/2026)*
   - ✅ `GET /orders/me/{order_id}/tracking` : vérifie ownership (`order.user_id == current_user.id`), retourne `CustomerOrderTrackingResponse` (trackings, statut global, scénarios d'exception, consolidations).
   - Réutilise `_derive_order_overall_status` / `_derive_order_exception_scenarios` existants.
   - Fichier : [app/api/routes/orders_me.py](backend/app/api/routes/orders_me.py)

4. ✅ **Webhook Ingram — suivi statut commande fournisseur** *(livré 08/06/2026)*
   - ✅ Migration `b9c5d3e2f7a1` : colonne `estimated_delivery TIMESTAMP WITH TIME ZONE` sur `supplier_orders`.
   - ✅ Config `INGRAM_WEBHOOK_SECRET` (Bearer token auth).
   - ✅ `POST /webhooks/ingram/order-status` : valide le token, trouve `SupplierOrder` par `supplier_order_number` ou `customer_order_number`, met à jour `supplier_status_label` + `estimated_delivery`, publie `supplier_order.shipped` si statut shipped.
   - ✅ Handler `on_supplier_order_shipped` : tente d'avancer les trackings de la commande vers le statut `shipped` (best-effort, log warning si transition invalide).
   - Fichiers : [app/api/routes/webhooks.py](backend/app/api/routes/webhooks.py) · [app/handlers/supplier_order.py](backend/app/handlers/supplier_order.py)

5. ✅ **B5 confirmé** (Phase 0) — `update_tracking_status` exige `CurrentSuperUser`.

6. ✅ **Catalogue de specs — extension multi-catégories** *(livré 08/06/2026)*
   - ✅ Migration `c1d6e4f3a8b2` : table `spec_definitions(id, key, label_fr, type, unit, categories JSON, aliases JSON, is_active)` + seed des 10 specs YAML Phase 1.
   - ✅ Modèle `SpecDefinition` + `SpecDefinitionPublic/Create/Update`.
   - ✅ `upsert_product_specs` charge d'abord les defs DB (fallback YAML si DB vide ou erreur).
   - ✅ `project_specs_from_payload` accepte `alias_index` / `raw_defs` en surcharge.
   - ✅ `enqueue_reproject_product_specs(category_id)` ajouté dans `icecat_tasks.py`.
   - ✅ Endpoints admin `GET/POST/PUT/DELETE /admin/spec-definitions` + re-projection automatique en background.
   - Soft-delete (`is_active=False`) préserve l'historique.
   - Fichiers : [app/features/product/models/spec_definition.py](backend/app/features/product/models/spec_definition.py) · [app/api/routes/admin_spec_definitions.py](backend/app/api/routes/admin_spec_definitions.py)

7. ✅ **Devises — préparation P4** *(livré 08/06/2026)*
   - ✅ Migration `d2e7f5a4b9c3` : table `system_settings(id, key, value, description, updated_at)` + seed `default_display_currency = "XPF"`.
   - ✅ Modèle `SystemSetting` + routes :
     - `GET /system/settings` (public, whitelist `default_display_currency`) → prépare le toggle multi-devises P4.
     - `GET/PUT /admin/system-settings[/{key}]` (superuser) → upsert complet.
   - Fichiers : [app/features/system/models/system_setting.py](backend/app/features/system/models/system_setting.py) · [app/api/routes/system_settings.py](backend/app/api/routes/system_settings.py)

### Travaux admin-frontend ✅ (périmé le 30/09/2026 : écrans A3, A5, A7 livrés le 20/06/2026)

> *(Texte historique.)* Les endpoints sont livrés (✅ backend) mais aucun écran ne les pilote encore (`admin-frontend` = `LoginPage` + `ProductsPage` seulement). Modèle de découpage à répliquer pour les autres phases :
>
> - **Écran « Catalogue de specs »** (`/admin/spec-definitions`) : table CRUD (`key`, `label_fr`, `type`, `unit`, `categories`, `aliases`), toggle `is_active` (soft-delete), action « re-projeter » (déclenche `reproject_product_specs`). ← *ton exemple*
> - Écran « Éligibilité paiement » : matrice méthode × groupe + `max_amount` (`/admin/payment-methods/{id}/groups`).
> - Écran « System settings » : édition `default_display_currency` (prépare le toggle multi-devises P4).
>
> Côté **vitrine** : ✅ livré (cf. *Avancement vitrine* ci-dessous).

### Avancement vitrine (20/06/2026)

- ✅ **Suivi de commande client** :
  - Backend : ajout `GET /orders/me` (liste des commandes du client connecté, tri `created_at` desc, scope JWT) — complète le namespace `/orders/me` aux côtés de `/orders/me/{id}/tracking`. Tests : [app/tests/api/test_orders_me_routes.py](backend/app/tests/api/test_orders_me_routes.py) (scope user + liste vide).
  - Vitrine : onglet **Commandes** dans `MyAccountPage.vue` (liste + bouton « Suivre ») et page **`OrderTrackingPage.vue`** (route `/mon-compte/commandes/:id` name `order-tracking`) consommant `GET /orders/me/{id}/tracking` : statut global mappé en libellés FR, scénarios d'exception (`supplier_delay`/`parcel_split`/`segment_failure`), timeline des tronçons (`q-timeline`), envois consolidés. Gestion 403/404.
  - Module API : [frontend/src/api/orders.ts](frontend/src/api/orders.ts). Typecheck (`vue-tsc`) + lint verts.

### Hors périmètre Phase 3

- Regroupement de colis avancé, paiement en plusieurs fois, remboursement.

---

## Phase 4 — Logistique avancée + remboursement

**Objectif** : outiller l'admin logistique pour grouper les colis et gérer les remboursements clients.

#### ✅ Avancement — Logistique : endpoints + écran admin (23/06/2026)

Sous-chantier **logistique** livré (devises + remboursement restent à faire) :
- **Backend** [admin_shipping.py](backend/app/api/routes/admin_shipping.py) (`/admin/shipping`, superuser) réutilisant le CRUD shipping existant :
  - `GET /pending-grouping` (tronçons sans consolidation, enrichis statut),
  - `GET /consolidations`, `POST /consolidations` (création + code auto), `POST /consolidations/{id}/add-trackings` (bulk), `POST /consolidations/{id}/ship-all` (réf. transporteur → tous les tronçons),
  - `POST /trackings/{id}/ship` (réf. requise) + `POST /trackings/{id}/deliver`.
  - Chaque transition statut **get_or_create** le `StatusDefinition` (non seedés), force la transition (pas de dépendance à la table de transitions), pose la réf, et **publie `tracking.status_changed`** (→ email client) avec commit explicite (l'event est bien persisté). Tests : [test_admin_shipping.py](backend/app/tests/api/test_admin_shipping.py).
- **Admin front** : [ShippingPage.vue](admin-frontend/src/pages/ShippingPage.vue) (« Logistique ») — table des colis à grouper (sélection → créer consolidation), actions Expédier/Livrer par tronçon, table consolidations avec « Expédier tout » ; nav « Commandes → Logistique », route `/shipping`, API [shipping.ts](admin-frontend/src/api/shipping.ts). Le lien commande pointe vers la fiche `/orders/:id`.
- ✅ **Phase 4 complète** : logistique multi-tronçons, permission `logistics_admin`, **remboursement** — tous livrés. *(Devises auto déprioritisé → « Optionnel / différé » en fin de document.)*

#### ✅ Avancement — Remboursement total / partiel (26/06/2026)

- **Modèle** `Refund` ([refund.py](backend/app/features/payment/models/refund.py)) : `payment_id`, `order_id`, `amount`, `currency`, `reason`, `status` (`completed/pending/failed`), `provider_reference`, `processed_at`, `created_by_id`. Migration `e3f9a1c7b2d4` (table `refunds`, **validée par `alembic upgrade head` sur DB fraîche**). Statuts paiement `Refunded`/`PartiallyRefunded` seedés.
- **Providers** : méthode `refund()` sur l'abstraction ([base.py](backend/app/features/payment/providers/base.py)) — **manuel / BC = `completed`** immédiat (décision / écriture comptable), **PayZen = `pending`** (enregistré, à finaliser au back-office ; l'appel API PayZen `cancelOrRefund` reste un suivi).
- **Service** [refund_service.py](backend/app/features/payment/services/refund_service.py) : calcule le remboursable (montant − déjà remboursé, **pending compris** → pas de fenêtre de double-remboursement), **rejette** ≤ 0 ou > remboursable, crée le `Refund` + un `PaymentValidation` (action `refund`), et si `completed` pose le statut paiement (Refunded/PartiallyRefunded) + publie `payment.refunded`.
- **Endpoint** `POST /admin/payments/{id}/refund` (`amount` optionnel = total, `reason`) — superuser.
- **Handlers** : statut commande `Refunded`/`PartiallyRefunded` ([payment.py](backend/app/handlers/payment.py)) + **email client « remboursement effectué »** ([order.py](backend/app/handlers/order.py)).
- **Admin** : bouton **« Rembourser »** + dialogue (montant optionnel / motif) sur la fiche commande ([OrderDetailPage.vue](admin-frontend/src/pages/OrderDetailPage.vue)), API [paymentValidations.ts](admin-frontend/src/api/paymentValidations.ts). Le client voit le statut « Remboursée » sur sa commande (déjà câblé) + l'email.
- Tests : 4 tests d'intégration ([test_refund_flow.py](backend/app/tests/integration/test_refund_flow.py)) — total / partiel-puis-reste / sur-montant rejeté / PayZen pending. **467 tests backend** au vert.
- ⏳ **Suivi** : brancher l'**API PayZen `cancelOrRefund`** pour automatiser le remboursement CB (aujourd'hui `pending` → action back-office).

#### ✅ Avancement — Robustesse logistique : greenlet, outbox, tests d'intégration DB (26/06/2026)

- **Bugs `MissingGreenlet` corrigés** sur ship-all/ship/deliver : `crud.update_status` lisait `old/new_status_obj.id` **après** son commit interne (instances expirées) ; et `admin_shipping` réutilisait dans la boucle des objets ORM partagés (`StatusDefinition`, lignes de tracking, **`admin`**) expirés par chaque commit. → capture des **valeurs simples** (id/code/name + tracking_ids + admin_id) **avant** la boucle ; `_advance_tracking`/`_publish` ne touchent plus l'ORM `StatusDefinition`.
- ✅ **Bug latent outbox résolu** : `/shipping/tracking/{id}/update-status` publiait l'event `tracking.status_changed` **sans commit** (perdu) → ajout du `commit` (réponse construite avant, car le commit expire la ligne).
- **Tests d'intégration DB** (Postgres réel) : [conftest.py](backend/app/tests/integration/conftest.py) (schéma recréé par test, skip si DB injoignable), [factories.py](backend/app/tests/integration/factories.py), [test_shipping_flow.py](backend/app/tests/integration/test_shipping_flow.py) (ship-all/ship/deliver + assertion events outbox committés). CI : service `postgres:16-alpine` + `TEST_DATABASE_URL` dans [ci.yml](.github/workflows/ci.yml). Suite : **454 passed**, coverage **66 %**.

#### ✅ Avancement — Devises : affichage multi-devises (côté client) (23/06/2026)

Décision : **conversion côté client** (l'affichage est purement présentationnel, checkout figé XPF) plutôt que `{amount, currency}` serveur (trop invasif). Volet **affichage** livré ; **auto-update + alerte** restent à faire.
- **Backend** : endpoint **public** [currency.py](backend/app/api/routes/currency.py) `GET /currency/display-rates` → taux actifs (dernier par devise) + devise de référence. Tests [test_currency_display_rates.py](backend/app/tests/api/test_currency_display_rates.py).
- **Shared** : `formatMoney(amount, currency)` ([currency.ts](shared/utils/src/currency.ts)) — XPF (0 déc., « F ») / autres via `Intl` (2 déc.) ; tests.
- **Vitrine** : store Pinia [currency.ts](frontend/src/stores/currency.ts) (taux + sélection persistée localStorage + sync `currency_pref` si connecté ; `format(xpf)` = convertit puis formate). **Sélecteur** dans le header (MainLayout) + dans *Mon compte → Préférences* (démasqué). Affichages convertis : **ProductCard / ProductDetailsDialog / ProductPage / CartPage**. **Checkout + commandes restent en XPF** (montants de paiement autoritaires). Conversion : `montant_devise = xpf / rate_to_reference`.
- 💤 **Devises auto-update + alerte FX : déprioritisé** (non prioritaire) → déplacé dans « Optionnel / différé » en fin de document. Les taux restent maintenus à la main dans l'admin.
- ⚠️ **CONTRAINTE devise × moyen de paiement** (à traiter avant toute facturation hors XPF) : **certains moyens de paiement sont liés à une devise précise** (ex. PayZen facturé en `PAYZEN_CURRENCY=XPF` ; un gateway international pourrait n'accepter que EUR/USD). Aujourd'hui `PaymentMethod` **n'a aucune notion de devise** et l'**éligibilité ne filtre pas par devise** ([eligibility.py](backend/app/features/payment/services/eligibility.py)) — c'est sans risque **uniquement parce que la facturation est figée en XPF** (l'affichage multi-devises est présentationnel). Dès qu'un paiement sera réellement facturé dans une autre devise, il faudra : (1) ajouter `supported_currencies`/`billing_currency` à `PaymentMethod`, (2) **filtrer l'éligibilité par la devise de facturation** de la commande, (3) passer la bonne devise au provider à l'initiation, (4) garde-fou : ne pas proposer un moyen de paiement incompatible avec la devise choisie.

#### 🔎 Audit logistique multi-tronçons — gestion des trajets & progression (26/06/2026)

**Demande** : permettre à l'admin de **créer des trajets/tronçons** (fournisseur→entrepôt, puis entrepôt→client) et de faire **avancer un colis / un regroupement de tronçon en tronçon** jusqu'au tronçon final. Aujourd'hui l'écran admin se limite à **regrouper + Expédier/Livrer à plat**.

**✅ En place (backend)**
- **Modèles complets** : `ShippingRoute` (tronçon réutilisable : `from_place_id`/`to_place_id`, `from_partner_id`/`to_partner_id`, `mode`, prix, `service_level`, `customer_label`, `is_to_customer`, `allow_consolidation`), `Place` (warehouse/airport/seaport/island…, `customs_clearance`, `consolidation_service`), `ShippingRouteTracking` (**1 ligne par tronçon par commande**, `sequence_order` 1..N, `status_id`, `consolidation_id`), `ShippingRouteTrackingConsolidation`, `StatusDefinition`/`StatusTransition` (table de transitions avec `auto_advance`/`requires_confirmation`/`requires_scan`), `ShippingRouteTrackingLogs` (audit : `change_type`, `was_auto_advance`).
- **Création des tronçons** : faite **au checkout**, tous les tronçons d'un coup. Deux chemins dans [cart.py](backend/app/api/routes/cart.py) : `_link_selected_routes_to_tracking` (routes choisies par le client → 1 tracking/route, `sequence_order` incrémenté) et `_link_fulfillment_segments_to_tracking` (segments LOCAL / SUPPLIER_DIRECT / CONSOLIDATION_PF → 1 tracking/segment + consolidation si PF). → le modèle **supporte déjà** fournisseur→entrepôt→client.
- **CRUD REST existants** (BaseRouter, superuser) : **routes** `GET/POST/PATCH/DELETE /shipping/route` (+ `quote`, `paths/{from}/{to}`, `optimal/{from}/{to}`) et **lieux** `GET/POST/PATCH/DELETE /place`. → on **peut** créer trajets/lieux par API.
- **Progression séquentielle** côté CRUD : `get_trackings_by_order_sequence`, `get_current_route_for_order`, `get_next_route_for_order`, `activate_next_route` (marque le tronçon courant `completed` puis active le suivant en `in_progress`, log `auto_advance`).

**✅ Livré (26/06/2026) — multi-tronçons de bout en bout**
1. **🐞→✅ Bug « tronçon suivant » corrigé** : `activate_next_route` ([route_tracking.py:360](backend/app/features/shipping/crud/route_tracking.py#L360)) refait — signature `(session, current_tracking_id, changed_by)`, dérive `order_id`/`sequence` **avant** les commits (greenlet-safe), `force=True`, renvoie l'instance rafraîchie. Endpoint `/shipping/tracking/{id}/activate-next-route` aligné. Test d'intégration `test_activate_next_route_advances_sequence`.
2. **✅ Harmonisation + seed des statuts** : `_seed_shipping_statuses` ([initial_data.py](backend/app/features/initial_data.py)) — catalogue `route_tracking` (`pending`/`in_progress`/`shipped`/`completed`/`delivered`) + `consolidation` + 9 transitions (idempotent). Rend le `/update-status` (force=False) utilisable. Test `test_shipping_status_seed.py`.
3. **✅ Endpoints admin « tronçon suivant »** : `POST /admin/shipping/trackings/{id}/advance` + `POST /admin/shipping/consolidations/{id}/advance-all` ([admin_shipping.py](backend/app/api/routes/admin_shipping.py), captures avant boucle). Tests d'intégration des deux.
4. **✅ UI admin** : page **Trajets & Lieux** ([LogisticsRoutesPage.vue](admin-frontend/src/pages/LogisticsRoutesPage.vue) + [api/logistics.ts](admin-frontend/src/api/logistics.ts), nav + route) — CRUD `Place` et `ShippingRoute`. Boutons **« Tronçon suivant »** (par colis **et** par consolidation) sur [ShippingPage.vue](admin-frontend/src/pages/ShippingPage.vue).

**✅ Finitions livrées (26/06/2026)**
- **Vue « parcours du colis »** : endpoint `GET /admin/shipping/orders/{order_id}/journey` (legs 1..N avec noms de statut + lieux résolus, `is_current`) + **timeline** dans [ShippingPage.vue](admin-frontend/src/pages/ShippingPage.vue) (bouton « Parcours » → `q-timeline`). Tests d'intégration.
- **Notifications à l'avance de tronçon** : les endpoints `advance`/`advance-all` publient désormais `tracking.status_changed` (`in_progress`) ; le handler [shipping.py](backend/app/handlers/shipping.py) envoie un email « votre colis progresse » (nouveau palier, gardé par la préférence `notification_shipping_steps`).

**✅ Permission logistique livrée (26/06/2026)**
- Dépendance **allow-list** `CurrentLogisticsAdmin` ([deps.py](backend/app/api/deps.py)) : superuser **toujours** ; sinon (et seulement si `ENABLE_GROUP_PERMISSIONS=true`) un membre d'un groupe sécurité avec `can_update` sur `shipping_route_trackings` (groupe `logistics_admin` seedé). **Jamais** d'accès aux users sans groupe (contrairement au modèle deny-list de `check_user_permission`). Tous les endpoints `admin_shipping` basculés de `CurrentSuperUser` → `CurrentLogisticsAdmin`. 4 tests d'intégration (superuser / flag off / sans-groupe / membre logistique).
- ⚙️ **Activation** : mettre `ENABLE_GROUP_PERMISSIONS=true` **et** rattacher les users concernés au groupe `logistics_admin` (sinon comportement inchangé = superuser only).

#### 🔎 Retour propriétaire — souplesse du suivi & finitions logistique (29/06/2026)

**Rappel objectif cible** : suivi d'articles simple et souple. Une commande peut mêler articles fournisseur 1 + articles en stock entrepôt. Les articles fournisseur peuvent être affectés à une **consolidation**. Quand tous les articles atteignent l'**entrepôt principal**, on exécute le mode **last-leg** choisi par le client (retrait magasin / livraison domicile / fret aérien). Première étape (périmètre courant) : le client choisit **rapide(avion) vs économique(bateau)** pour le tronçon international (impacte le prix), puis **le mode last-leg au checkout** ; les tronçons sont déduits de ces choix + de la localisation des articles. *Le propriétaire précise : « pas encore prêts » pour le flux complet.*

**Sémantique du bouton « Expédier » (point 3 — clarification)** : « Expédier » fait 3 choses sur le **tronçon courant** — (1) statut → `shipped` (non terminal), (2) enregistre le **n° de suivi transporteur** (`tracking_ref`), (3) publie `tracking.status_changed` → **email client « colis expédié »**. Il **ne fait PAS avancer** au tronçon suivant : c'est le bouton dédié **« Tronçon suivant »** (`activate_next_route`) qui marque le tronçon `completed` et active le suivant. → Intuition du propriétaire (« indiquer un numéro de suivi ») correcte. Tooltip ajouté ✅.

##### ✅ Quick wins livrés (29/06/2026)

- [x] **Point 1 — Boutons grisés sur statut terminal** : dans [ShippingPage.vue](admin-frontend/src/pages/ShippingPage.vue), `:disable` sur **Livrer** / **Tronçon suivant** quand `status_code ∈ {completed, delivered}`, et sur **Expédier** / **Expédier tout** quand terminal **ou** déjà `shipped` (helpers `isTerminal` / `isShipped`). *(Reste possible : garde-fou backend HTTP 409 sur transition d'un tracking déjà terminal — cf. design.)*
- [x] **Point 3 — Clarifier « Expédier »** : `q-tooltip` explicatif ajouté sur les deux boutons Expédier.
- [x] **Point 4b — 🐞 Bug consolidations vitrine** : [orders_me.py](backend/app/api/routes/orders_me.py) renvoyait **toutes** les consolidations de la route (`get_consolidations_for_route`, sans filtre commande, + doublons). Corrigé : on ne garde que les consolidations liées aux trackings de **cette** commande (via `tracking.consolidation`, dédupliquées), avec eager-load.
- [x] **Point 4a — Infos transport vitrine enrichies** : `ShippingRouteTrackingPublic` enrichi (`from_place_name`/`to_place_name`/`mode`/`route_label`, eager-load `route` dans `get_trackings_by_order_sequence`) ; la vitrine ([OrderTrackingPage.vue](frontend/src/pages/OrderTrackingPage.vue)) affiche désormais **« France → Papeete (avion) »** par tronçon (mapping mode FR : air→avion, sea→bateau, road→route, pickup→retrait).
- [x] **Point 5 (1re tranche) — N° de suivi optionnel** : `ShipRequest.tracking_ref` rendu **optionnel** ([admin_shipping.py](backend/app/api/routes/admin_shipping.py)) + rule UI retirée + envoi `null` si vide. Couvre le cas « suivi géré en interne, pas de numéro ».
- [x] **Point 2/3 (libellé) — Renommage** : bouton « Expédier » → **« Remettre au transporteur »** (et « Tout remettre au transporteur » pour le lot) + dialogue « Remise au transporteur ».

##### 🧭 Conception (phase logistique avancée — « pas encore prêts »)

- [x] **Point 2 — Dégroupage au passage du lot : popup + défaut intelligent (✅ PHASE 2 LIVRÉE 29/06/2026)**
  - `advance_consolidation` ([admin_shipping.py](backend/app/api/routes/admin_shipping.py)) accepte `ungroup: bool` : si `true` → **par colis** `remove_tracking_from_consolidation` (détacher) **puis** `activate_next_route` (avancer individuellement) ; si `false` → lot ensemble (comportement existant).
  - Nouveau `POST /consolidations/{id}/deliver-all` → **dégroupage forcé** + chaque colis marqué **livré** (terminal) + lot marqué livré.
  - Nouveau `GET /consolidations/{id}/ungroup-hint` → **défaut intelligent** `suggest_ungroup` (`suggest_ungroup_for_consolidation`, [crud/route_tracking.py](backend/app/features/shipping/crud/route_tracking.py)) : vrai si le prochain tronçon est le **last-leg** (`is_to_customer`), si un colis n'a plus de tronçon, ou si les colis **divergent**.
  - Admin ([ShippingPage.vue](admin-frontend/src/pages/ShippingPage.vue)) : « Tronçon suivant » du lot → **popup *Garder / Dégrouper*** pré-cochée via le hint ; nouveau bouton **« Livrer »** (confirmation → dégroupage forcé + livraison).
  - 🐞 Au passage : corrigé un **bug greenlet latent** dans `remove_tracking_from_consolidation` (lecture de `consolidation.total_orders` après commit — la méthode n'était jamais appelée jusqu'ici). 4 tests d'intégration (keep, ungroup, deliver, hint).
- [x] **Point 5 — Transporteur + lien de suivi (✅ PHASE 1 LIVRÉE 29/06/2026)**
  - Modèle **`Carrier`** (`name`, `code`, `tracking_url_template` avec placeholder `{ref}`) + `carrier_id` (FK nullable) sur `ShippingRouteTracking` **et** la consolidation. Migration `f7a1c3e9d2b5` (table + colonnes, réversible) + seed (DHL, Colissimo, Chronopost, OPT).
  - Admin : sélecteur **Transporteur** (+ « — Suivi interne — ») dans le dialogue « Remise au transporteur » ; `carrier_id` + n° stampés à l'expédition. Endpoint `GET /admin/shipping/carriers`.
  - Vitrine : `carrier_name` + **lien « Suivre le colis »** cliquable construit côté backend (`tracking_url`, **https-only** + ref URL-encodée, garde anti-`javascript:`). Affiché dans [OrderTrackingPage.vue](frontend/src/pages/OrderTrackingPage.vue). Test unitaire du builder d'URL.
  - **Pas** d'intégration API transporteur (YAGNI) — saisie manuelle. *(Le `tracking_mode` explicite {externe/auto/sans} n'a pas été nécessaire : carrier présent = externe + lien ; absent = suivi interne.)*
  - Reste (futur) : `PATCH /admin/shipping/trackings/{id}/tracking-ref` pour corriger un n° après coup (ré-notification client : à décider) ; petite UI de gestion des transporteurs (URLs éditables).
- [ ] **Modèle de tronçons unifié (✅ décision : last-leg = tronçon)** : le **last-leg** (entrepôt → client final) devient un **tronçon `ShippingRouteTracking`** comme les autres, et **non** un `DeliveryTask` séparé. Bénéfice : un parcours unique et homogène (mêmes statuts, même suivi, même « tronçon suivant »), du simple (1 tronçon entrepôt→client) au complexe (fournisseur → étape 1 → douane → étape 2 → entrepôt → client). Le last-leg peut être un **transporteur classique** (la Poste/DHL) avec lien de suivi (cf. point 5) **ou** géré en interne. → `DeliveryTask` ([delivery_task.py](backend/app/features/shipping/models/delivery_task.py)) à **résorber/migrer** vers un tronçon (ou conserver seulement comme détail de tâche admin, à trancher).
- [ ] **Modèle de prix par zones (✅ cadrage propriétaire)** :
  - **Zone A — fournisseur → douane** (tronçons internationaux) : **incluse dans le prix de l'article** (mode rapide/éco choisi au catalogue → CAF, déjà livré P1).
  - **Zone C — entrepôt → client final** (last-leg) : **choisie par le client au checkout**, tarifée à part. *(Futur, optionnel — généralisation : tarif au **poids/volume** par tranches, ex. 1–2 kg = X XPF, 2–5 kg = Y… par transporteur/zone.)*
  - **Zone B — douane → entrepôt principal** : ✅ **incluse dans la zone A** (décision propriétaire). Le prix article couvre tout jusqu'à l'entrepôt principal ; **seul le last-leg** est choisi/payé par le client (évite de multiplier les choix au checkout).
  - ✅ **Sélection last-leg au checkout vitrine (29/06/2026)** : enum `DeliveryType` (retrait magasin / livraison domicile / fret aérien) + champ `CheckoutRequest.delivery_type` + colonne `Order.delivery_type` (migration `a3b8d1f6c4e2`) + sélecteur dans [CheckoutPage.vue](frontend/src/pages/CheckoutPage.vue). **Le choix est enregistré** sur la commande. Reste (flux cible) : s'en servir pour **déterminer/tarifer** le tronçon last-leg (la machinerie `sequence_order` + consolidation existe déjà dans [cart.py](backend/app/api/routes/cart.py) mais n'exploite pas encore `delivery_type`).

##### Décisions

- [x] **Grisage** : `completed`+`delivered`, + re-grisage « Expédier » sur `shipped`. ✅
- [x] **Libellé** : « Remettre au transporteur ». ✅
- [x] **N° de suivi** : optionnel. ✅
- [x] **Dégroupage** : « Tronçon suivant » du lot → **popup Garder/Dégrouper** avec défaut intelligent (Dégrouper si prochain = last-leg ou colis divergents) ; **« Livrer » → dégroupage forcé**. ✅
- [x] **Suivi** : transporteur + gabarit d'URL → lien de suivi cliquable côté client (+ `tracking_mode`). ✅
- [x] **Modèle last-leg** : tronçon `ShippingRouteTracking` unifié (pas `DeliveryTask` séparé). ✅
- [x] **Lien fournisseur → 1er tronçon** : nouveau champ `Product.supplier_place_id` (lieu d'origine quand produit sourcé fournisseur — migration `b5c9e2a7f1d3`). Au checkout, chaque allocation porte son `origin_place_id` (`FulfillmentAllocation`), les segments sont agrégés par **`(segment, origine)`** (donc un tracking par origine distincte), et le 1er tronçon est résolu par **pathfinding** `origine → entrepôt principal` (`get_optimal_route_between_places`, `is_to_customer=False`) — l'entrepôt principal = destination de la route `is_default_import`, sinon 1er `Place.is_warehouse`. Fallback heuristique quand l'origine est absente. Tests d'intégration `test_supplier_origin_routing.py` (3) + d2/e1 alignés. ✅
- [x] **Peuplement de `supplier_place_id`** (les deux voies) : ✅
  - **UI admin** — colonne **« Origine (fournisseur) »** dans [ProductsPage.vue](admin-frontend/src/pages/ProductsPage.vue) : `q-select` inline des `Place` (auto-sauvegarde au changement, comme le toggle « Actif admin »), via `store.updateOriginPlace` → `PUT /product/{id}` (`supplier_place_id`).
  - **Sync fournisseur** — l'adaptateur expose `origin_place_code` (Ingram → `settings.INGRAM_ORIGIN_PLACE_CODE`, défaut `"FR_SUPPLIERS"` déjà seedé par `initial_data`) ; l'orchestrateur ([supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py)) le résout en `Place.id` (`crud_place.get_by_code`, idempotent, mémoïsé/run) et l'estampille à l'upsert — **sans écraser un override admin** (posé seulement à la création ou si origine absente). Tests `test_ingram_supplier_place_sync.py` (create / no-clobber / code inconnu).
- [x] **Zone B (douane → entrepôt principal)** : incluse dans la zone A (prix article jusqu'à l'entrepôt). ✅
- [ ] Détails secondaires : MAJ d'un n° de suivi → email client ou silencieux ? Vitrine : tous les tronçons ou seulement courant + franchis ? Tarif last-leg au poids/volume (futur, optionnel).

#### 🔧 Lot de corrections & outils admin (02/07/2026)

Six chantiers demandés par le propriétaire, tous livrés + vérifiés (ruff/mypy/alembic tête unique ; eslint/vue-tsc admin & vitrine ; 252 tests backend de non-régression verts).

- [x] **1. Duplication d'adresse au checkout** : cause = rapprochement par **texte** (`street, city, country`) qui ne matche jamais le format vitrine (`street, "CP ville", state, country`) → adresse recréée à chaque commande. Corrigé : la vitrine envoie `shipping_address_id` ([CheckoutRequest](backend/app/features/cart/models/cart.py)), le backend lie le tronçon **par id** avec vérif de propriété ([`_resolve_tracking_address_for_checkout`](backend/app/api/routes/cart.py)) ; le texte reste snapshot de commande. ✅
- [x] **2. Vérification d'adresse (indicative) + page admin** : décision propriétaire = garder, **non bloquante** au checkout. Nouvel endpoint `GET /admin/addresses` (paginé, filtre validé/non-validé, email client joint) + page admin **« Adresses »** ([AddressesPage.vue](admin-frontend/src/pages/AddressesPage.vue), section Clients) avec badge + bouton **Valider** (→ endpoint existant). ✅
- [x] **3. Outils création/édition produit admin + overrides génériques** : nouveau champ `Product.overridden_fields` (JSON, migration `c7d2f4a9e5b1`). Tout champ édité en admin est enregistré et **le sync ne l'écrase plus** ([`upsert_product`](backend/app/features/integrations/services/supplier_sync_orchestrator.py)). Endpoints `POST/PUT /admin/products` ([admin_product.py](backend/app/api/routes/admin_product.py)) — create force `is_supplier_managed=False` (produit manuel), update verrouille les champs modifiés. UI : bouton **Nouveau** + action **Modifier** + [ProductFormDialog.vue](admin-frontend/src/components/ProductFormDialog.vue) (lookups catégorie/TVA/origine, envoi du **diff** en édition, coût+devise pilotant le prix CAF). ✅
- [x] **4. Bouton panier** : « Payer » → **« Passer commande »** (icône `shopping_cart_checkout`) — c'est une navigation vers le checkout, pas un paiement ([CartPage.vue](frontend/src/pages/CartPage.vue)). ✅
- [x] **5. Tronçons last-leg + tarif appliqué** : décision = outils admin **+ application au checkout**. `base_price` (forfait) désormais éditable sur les routes + nouveau champ `ShippingRoute.last_leg_delivery_type` (migration `d8e3f5b2a6c4`) taggant la route par mode (retrait/domicile/fret aérien) dans [LogisticsRoutesPage.vue](admin-frontend/src/pages/LogisticsRoutesPage.vue). Au checkout, [`_resolve_last_leg_route`](backend/app/api/routes/cart.py) résout la route last-leg du `delivery_type` choisi et la **price avec les autres tronçons** (`base_price + prix/kg × poids`) → **le tarif last-leg est enfin ajouté au total + breakdown**. **Affichage vitrine** : endpoint `GET /cart/me/last-leg-options` (price chaque mode pour le panier courant) → prix montré à côté de chaque mode dans [CheckoutPage.vue](frontend/src/pages/CheckoutPage.vue) (« Offert » si 0). *(Reste optionnel : tranches poids/volume via `route_metadata`.)* ✅
- [x] **6. Moyens de paiement** : **CB absente** = aucun `PaymentMethod` `provider_code="payzen"` seedé → ajout **« Carte bancaire »** au seed idempotent ([initial_data.py](backend/app/features/initial_data.py)). **Désactivation globale** : `is_admin_active` existait déjà (modèle + filtrage éligibilité) — ajout d'un toggle **« Activé »** par méthode dans [PaymentEligibilityPage.vue](admin-frontend/src/pages/PaymentEligibilityPage.vue) (→ `PUT /payment_method/{id}`). ✅

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| Permission logistique (`logistics_admin`) | ✅ `CurrentLogisticsAdmin` (allow-list, opt-in `ENABLE_GROUP_PERMISSIONS`) | — | — |
| Endpoints ship / deliver / consolidate | ✅ | — | ✅ écran logistique + consolidation bulk |
| Gestion trajets / lieux | ✅ CRUD REST | — | ✅ écran Trajets & Lieux |
| Progression multi-tronçons (next-leg) | ✅ endpoints + harmonisation | — | ✅ boutons « tronçon suivant » (colis + lot) |
| Statuts logistiques (seed + harmonisation) | ✅ seed StatusDefinition/Transition | — | — |
| Vue « parcours du colis » détaillée | ✅ endpoint journey | — | ✅ timeline tronçons 1..N |
| Notifications avance de tronçon | ✅ publish + email « progresse » | — | — |
| Devises — multi-affichage | ✅ | ✅ sélecteur de devise | 🔲 (taux gérés ailleurs) |
| Devises — auto-update + alerte FX | 💤 différé (optionnel, fin de doc) | — | — |
| Remboursement total / partiel | ✅ modèle + service + endpoint + handlers | ✅ statut « Remboursée » + email | ✅ bouton « Rembourser » (fiche commande) |

### Périmètre fonctionnel

- Endpoints sémantiques admin pour ship / deliver / consolidate.
- Regroupement bulk de plusieurs commandes en une consolidation.
- Remboursement total / partiel (CB via Payzen, manuel pour chèque/virement/BC).
- Permission `logistics_admin` distincte de `superuser`.

### Travaux backend

1. **Permission logistique**
   - Utiliser le système `Group` + `GroupSecurity` existant : créer un groupe `logistics_admin` avec permissions read/create/update sur `shipping_*`.
   - Remplacer les gating naïfs par `current_user.has_permission("shipping.update")` ou équivalent.

2. **Endpoints sémantiques admin**
   - `POST /admin/shipping/consolidation/{id}/add-trackings` (bulk : `[tracking_id, ...]`) — expose la méthode CRUD existante `add_tracking_to_consolidation` ([route_tracking.py:534-570](backend/app/features/shipping/crud/route_tracking.py#L534-L570)).
   - `POST /admin/shipping/consolidation/{id}/ship-all` (transition tous les trackings rattachés vers statut `shipped` + propage `tracking_ref` de la consolidation).
   - `POST /admin/shipping/tracking/{id}/ship` (require `tracking_ref` dans le body) → statut shipped + publish outbox.
   - `POST /admin/shipping/tracking/{id}/deliver` → statut delivered.
   - Vue admin `GET /admin/shipping/pending-grouping` (trackings sans consolidation, prêts à grouper).

3. **Devises — automatisation et multi-affichage**
   - Variable `CURRENCY_AUTO_UPDATE_ENABLED: bool = False` (opt-in).
   - Cron quotidien ARQ qui appelle une source externe (ECB API ou exchangerate.host) et crée un nouveau `CurrencyRate` avec `source='auto'`.
   - Politique : ne pas écraser un taux `source='manual'` récent (< 24h) sans confirmation admin.
   - Alerte email admin si le dernier taux actif a > 30 jours.
   - Champ `User.preference.currency_pref` actif : si renseigné, `calculate_sale_price` retourne le prix dans la devise demandée (conversion inverse XPF → devise au taux courant).
   - Frontend reçoit la devise d'affichage avec chaque prix (`{amount, currency}` au lieu d'un Decimal nu).
   - Garde-fou paiement : PayZen est facturé en XPF, l'affichage multi-devises est purement présentationnel — au checkout, le total final est figé en XPF.

4. **Remboursement**
   - Méthode `refund(amount, reason)` sur :
     - `PayzenProvider` (API Payzen `cancelOrRefund`).
     - `ManualPaymentProvider` (chèque/virement : écriture comptable + log validation, pas d'API).
     - `DocumentValidatedProvider` (BC : décision admin pure).
   - Modèle `Refund(id, payment_id, order_id, amount, currency, reason, status, provider_reference, created_by, processed_at)` avec contrainte `sum(refunds.amount) ≤ payment.amount`.
   - Endpoint `POST /admin/payments/{id}/refund` (avec `amount` optionnel = total si omis).
   - Outbox `payment.refunded` → handler → email client.
   - Mise à jour statut `Order` : `Refunded` ou `PartiallyRefunded`.
   - Préparation tokenisation Payzen pour Phase 5 (Z1 paiement en plusieurs fois).

### Hors périmètre Phase 4

- Factures comptables, paiement en plusieurs fois, recherche IA.

---

## Phase 5 — Fonctionnalités restantes

**Objectif** : compléter le périmètre du document de vérification fonctionnelle.

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| M1 — produits les plus vus | ✅ (10/09/2026) compteur journalier + `GET /product/popular` | ✅ accueil reconstruite le 30/09/2026 : vedettes + « les plus consultés » + blocs admin (R1-A / R2) | — |
| M3 — factures PDF (**WeasyPrint**) + export comptable | ✅ (25/08/2026) | ✅ téléchargement facture (compte) | ✅ écran factures + export CSV |
| M5 — numéro de commande séquentiel | ✅ (25/08/2026) | ✅ affichage (compte) | ✅ affichage (factures) |
| Z2 — avoir comptable | ✅ (N10 + e-mail d'envoi 10/09/2026) | ✅ téléchargement des avoirs (compte, par commande) | ✅ écran Avoirs + export CSV |
| Z3 — relance paniers abandonnés | ✅ (10/09/2026) balayage horaire + `cart.abandoned` + e-mail | ✅ miroir serveur du panier, opt-out marketing | ✅ page Paniers abandonnés (compteurs ouverts / relancés / récupérés) |
| Z4 — recherche IA | 🔲 | 🔲 UI recherche sémantique | — |

### Périmètre

| ID | Fonctionnalité | Notes |
|----|----------------|-------|
| M1 ✅ | Produits les plus vus | `POST /product/{id}/view` (page produit, côté client seulement) → `product_view_daily` ; `GET /product/popular?days&limit` ; accueil vitrine (reconstruit le 30/09/2026) |
| M2 | Déploiement Kubernetes | Helm chart à partir du `docker-compose.prod.yml` |
| M3 ✅ | Factures + export comptable | **Livré 25/08/2026** (cf. PP-C). Modèle Invoice + numérotation + PDF **WeasyPrint** (avec ventilation TVA par taux via `OrderLine.tax_rate_id`) + export FEC/CSV Sage — cf. *Note technique — génération PDF des factures* ci-dessous |
| M4 | Alerting actif | Job ARQ surveille dashboard → Slack/email sur seuils |
| Z1 | Paiement en plusieurs fois | Dépend Phase 4 (tokenisation Payzen) |
| Z2 ✅ | Avoir comptable | **Livré** : backend (N10), e-mail `credit_note.issued`, écran admin Avoirs, téléchargement client (10/09/2026) |
| Z3 ✅ | Relance paniers abandonnés | Livré : `remind_abandoned_carts_task` (horaire), `carts.last_activity_at` / `abandonment_reminded_at`, `user_preferences.marketing_email_enabled`, handler `cart.abandoned` |
| Z4 | Recherche IA | Refonte du draft `ia_search_agent.py` (placeholders à remplacer) ; pgvector recommandé |
| M5 ✅ | Numéro de commande séquentiel | **Livré 25/08/2026** (cf. PP-C). Cf. *Note technique — numéro de commande séquentiel (M5)* ci-dessous |

### Note technique — génération PDF des factures (M3)

**Bibliothèque retenue : WeasyPrint** (rendu HTML/CSS → PDF), cohérent avec l'approche HTML déjà utilisée pour les emails (`_build_quote_email_html` dans `cart.py`) et avec Jinja2 déjà présent dans les dépendances. Un template Jinja2 de facture (HTML + CSS print) sera rendu puis converti en PDF.

✅ **Fait le 25/08/2026** : `weasyprint` ajouté aux `dependencies` + `uv.lock` (les libs système étaient déjà dans le [Dockerfile](backend/Dockerfile)). L'import est **paresseux** dans [pdf.py](backend/app/features/invoice/services/pdf.py) : un poste dev Windows sans GTK n'empêche ni l'émission des factures ni les tests, seuls les endpoints PDF renvoient 503. Prérequis initiaux (pour mémoire) :

1. Ajouter `weasyprint` aux `dependencies` de `pyproject.toml`, puis `uv lock` / `uv sync`.
2. Vérifier la disponibilité des libs système hors Docker (dev Windows : WeasyPrint nécessite GTK/Pango — documenter dans le runbook, ou rendre la génération PDF dépendante du worker conteneurisé).
3. Templates Jinja2 facture + ventilation TVA par taux via le snapshot `OrderLine.tax_rate_id` (cf. jalon TVA *5a*).

### Note technique — numéro de commande séquentiel (M5)

**Contexte (07/07/2026)** : les emails transactionnels affichent désormais une référence courte dérivée de l'UUID (filtre Jinja `short_ref` → `#e090fee1`). Solution suffisante pour la communication client, mais **non garantie unique** (8 hex ≈ 1 collision pour ~65 000 commandes) et inutilisable comme référence comptable. M5 la remplace par un vrai numéro.

**Modèle** :

| Élément | Décision |
|---------|----------|
| Champ | `Order.order_number: str` — unique, indexé, immuable, **nullable** (les commandes antérieures n'en ont pas ; pas de backfill rétroactif) |
| Format | `CMD-{YYYY}-{NNNNN}` (ex. `CMD-2026-00042`) — année + compteur, lisible au téléphone |
| Génération | **Séquence PostgreSQL** dédiée (`CREATE SEQUENCE order_number_seq`) consommée à la création de la commande — jamais de `MAX()+1` (course sous concurrence) ; trous acceptés (rollback = numéro perdu, sans conséquence) |
| Clé technique | L'UUID reste la PK et la clé d'API partout ; `order_number` est purement une référence humaine |

**Surfaces** :

- **Backend** : migration (colonne + séquence), génération au checkout, exposé dans `OrderPublic` et le payload outbox `order.created` ; les emails basculent de `{{ order_id \| short_ref }}` vers `{{ order_number }}` (fallback `short_ref` pour les commandes sans numéro).
- **Vitrine** : affichage compte / suivi de commande / confirmation checkout.
- **Admin** : colonnes commandes + logistique (remplace `#uuid8` tronqué), recherche par numéro.

**Distinct de la numérotation de facture (M3)** : la facture a ses contraintes légales propres (séquence continue sans trous, par exercice) — les deux compteurs ne doivent pas être fusionnés.

### Sous-phases possibles

- **Phase 5a** : M3 (factures) + M5 (numéro de commande) — ✅ **livrés le 25/08/2026** (cf. *Chantier pré-production*, PP-C).
- **Phase 5b** : M4 (alerting actif) + M2 (K8s) — fiabilité prod.
- **Phase 5c** : Z3 (relance panier) + M1 (produits populaires) — leviers commerciaux.
- **Phase 5d** : Z1 + Z2 (paiement N×, avoir).
- **Phase 5e** : Z4 (recherche IA, optionnel).

---

## Chantier admin-frontend (transverse)

Les Phases 0–3 ont livré les **endpoints admin** mais l'`admin-frontend` ne comptait que `LoginPage` + `ProductsPage`. Ce chantier construit les écrans back-office qui pilotent ces endpoints. Convention reprise du storefront : `api` axios (`src/boot/api`), stores Pinia, `q-table` pour les listes, bannières inline (Quasar `Notify`/`Dialog` non activés), guard d'auth global déjà en place.

### Backlog par écran

| # | Écran | Endpoints | Phase | État |
|---|-------|-----------|-------|------|
| A1 | **Taux TVA/TGC** | `GET/POST/PUT /admin/tax-rates` | 2 | ✅ livré (20/06/2026) |
| A2 | **Taux de change** | `GET /admin/currency-rates`, `PUT /admin/currency-rates/{code}` | 1/4 | ✅ livré (20/06/2026) |
| A3 | **Catalogue de specs** | `GET/POST/PUT/DELETE /admin/spec-definitions` | 3 | ✅ livré (20/06/2026) |
| A4 | **Commandes fournisseurs** | `GET /admin/supplier-orders[/{id}]`, `POST .../{id}/retry` | 2 | ✅ livré (20/06/2026) |
| A5 | **System settings** | `GET /admin/system-settings`, `PUT .../{key}` | 3 | ✅ livré (20/06/2026) |
| A6 | **Demandes d'upgrade de groupe** | `GET /admin/group-upgrade-requests`, `POST .../{id}/approve\|reject` | 2 | ✅ livré (20/06/2026) |
| A7 | **Éligibilité paiement** | `GET/POST/DELETE /admin/payment-methods/{id}/groups`, `GET /payment_method`, `GET /admin/price-groups` *(nouveau)* | 3 | ✅ livré (20/06/2026) |
| A8 | Toggle « mis en avant » sur `ProductsPage` | `POST/DELETE /product/{id}/feature` | 1 | ✅ livré — case « Produit en vedette » dans [ProductFormDialog.vue](admin-frontend/src/components/ProductFormDialog.vue) (constaté le 30/09/2026) |
| A9 | Affectation directe de groupe à un user | `POST /admin/users/{id}/assign-price-group` + recherche user | 2 | ✅ livré (04/09/2026) via l'écran A15 (le PATCH porte aussi `price_group_id`) |
| A10 | **Validation des adresses** | *manque un endpoint listant les adresses à valider* (`POST /admin/addresses/{id}/validate` existe déjà) | 2 | ✅ tranché le 02/07/2026 : validation **indicative** (non bloquante) + écran [AddressesPage.vue](admin-frontend/src/pages/AddressesPage.vue). Reste : la mention « doit être validée » dans `MyAccountPage.vue` (R1-B) |
| A11 | Consultation des `QuoteRequest` | `GET /admin/quote-requests` | 1 | ✅ livré — [QuoteRequestsPage.vue](admin-frontend/src/pages/QuoteRequestsPage.vue) (constaté le 30/09/2026) |
| A12 | Fusion / renommage de catégories | `POST /admin/categories/{id}/merge` ; renommage vitrine via `display_name` (le `name` reste la clé de sync) | 2 | ✅ livré (04/09/2026) — écran Catégories (A17) |
| A13 | **Validation des paiements** | `GET /admin/payments/pending-validation`, `.../approve\|reject`, `.../attachments[/{id}/download]` | 3 | ✅ livré (23/06/2026) |
| A14 | **Édition produit** (titre, description, images…) avec **champs d'override** préservés de la sync | `PUT /admin/products/{id}` (verrouille les champs édités), `DELETE /admin/products/{id}/overrides/{field}` (libère un verrou) ; sync **et** enrichissement Icecat respectent `overridden_fields` | 2/3 | ✅ livré (04/09/2026) — verrous visibles et libérables dans `ProductFormDialog` |
| A15 | **Liste des utilisateurs** (compte + groupe) + **création de compte** avec email d'invitation | `GET/POST /admin/users`, `PATCH /admin/users/{id}`, `POST .../{id}/resend-invitation` ([admin_users.py](backend/app/api/routes/admin_users.py)). Inclut A9 (affectation de groupe). | 2 | ✅ livré (04/09/2026) |
| A16 | **Logistique : regroupement / consolidation / suivi d'expédition** | `POST /admin/shipping/consolidation/...`, ship/deliver, `pending-grouping` (Phase 4) | 4 | ✅ livré (05/09/2026) — [ShippingPage.vue](admin-frontend/src/pages/ShippingPage.vue) + transporteurs / routes. Distinct d'A4 (PO fournisseur). |
| A17 | **Catégories** : liste + **titre / description / image vitrine personnalisés** (préservés de l'enrichissement) ; fusion/renommage (A12) | `GET/PATCH /admin/categories`, `Category.display_name` + `CategoryPublic.title` ([admin_categories.py](backend/app/api/routes/admin_categories.py)) | 2/3 | ✅ livré (04/09/2026) — [CategoriesPage](admin-frontend/src/pages/CategoriesPage.vue) |
| A18 | **Commandes clients** (liste + statut) | `GET /admin/orders`, `GET /admin/orders/{id}` | 2 | ✅ livré — [OrdersPage.vue](admin-frontend/src/pages/OrdersPage.vue) + [OrderDetailPage.vue](admin-frontend/src/pages/OrderDetailPage.vue) (constaté le 30/09/2026) |
| A19 | **Paiements** (liste + statut, au-delà de la validation A13) | *endpoint de liste générale des paiements à ajouter* | 2/3 | 🔲 à faire (écran + endpoint de liste) — seul écran du backlog encore ouvert au 30/09/2026 (R8) |
| A20 | **Refonte « Précision » de l'admin** | `GET /admin/dashboard` | — | ✅ livrée le 30/09/2026 — *Feuille de route 30/09*, R1-admin |
| A21 | **Accueil vitrine : blocs + médias** (écran « Accueil du site », `MediaPicker`) | `/admin/homepage-blocks`, `/admin/media` | — | ✅ livré le 30/09/2026 — [HomepagePage.vue](admin-frontend/src/pages/HomepagePage.vue), [MediaPicker.vue](admin-frontend/src/components/MediaPicker.vue) |
| A22 | **Réglages typés par catégorie** (remplace le tableau clé / valeur de `SystemSettingsPage.vue`) | registre R5 | — | 🔲 — R5 (C6) |

### Décision transverse — personnalisation préservée de la synchronisation

Les **produits** (sync Ingram `SupplierSyncOrchestrator.upsert_product` + enrichissement Icecat) et les **catégories** (`get_or_create_by_name` au sync) sont **réécrits à chaque synchronisation**. Pour qu'un admin puisse personnaliser des informations (titre, description, images produit ; titre / description / image de catégorie pour la vitrine) **sans être écrasé**, deux approches :

- **(a) Champs d'override dédiés** — colonnes séparées non touchées par la sync, ex. `Product.name_override` / `description_override` / `image_override`, `Category.display_title` / `display_description` / `display_image_url`. L'API publique renvoie l'override s'il existe, sinon la valeur synchronisée (résolution centralisée). La valeur fournisseur reste visible/auditable.
- **(b) Verrous par champ** — un flag `is_manually_edited` ou une liste `locked_fields` que `upsert_product` et l'enrichissement **respectent** (ne réécrivent pas les champs verrouillés).

> **Recommandation : (a)** — plus simple et traçable (l'override est explicite, la valeur fournisseur n'est jamais perdue). **À acter avant A14 (produit) et A17 (catégorie)** ; ces deux écrans en dépendent. Concerne aussi l'image catégorie (nouveau champ, pas de source fournisseur → simple ajout) et le *featured* (A8, déjà non écrasé).

> ✅ **Acté le 04/09/2026 — deux réponses différentes selon l'objet.** **Produit : (b) verrous**, parce que le code les avait déjà (`Product.overridden_fields`, migration `c7d2f4a9e5b1`, respectés par `upsert_product`) : la règle est désormais centralisée dans [overrides.py](backend/app/features/product/services/overrides.py) et l'**enrichissement Icecat la respecte aussi** (il réécrivait description et image à chaque passage — l'admin corrigeait, Icecat effaçait). Un verrou se libère champ par champ ; la valeur fournisseur **n'est pas conservée à côté** : elle revient à la prochaine sync (2 h) ou au prochain enrichissement, pas sur-le-champ — c'est le prix de (b), assumé. **Catégorie : (a) colonne dédiée** `display_name`, parce que `name` est la clé de rapprochement de la sync et ne peut pas être renommé ; `description` et `image_url` n'ont pas de source fournisseur, la sync ne les touche pas. La vitrine lit **`CategoryPublic.title`** (`display_name` ou `name`), seul point de résolution. **Fusion (A12)** : la catégorie absorbée reste en base, inactive, avec `merged_into_id` — `get_or_create_by_name` suit le pointeur (chaînes comprises), sinon la sync recréerait la catégorie au prochain passage. Au passage, une catégorie **inactive** est désormais retrouvée par la sync au lieu d'être dupliquée en actif.

### Avancement (20/06/2026)

- ✅ **Shell admin** : `AdminLayout.vue` doté d'un `q-drawer` de navigation (sections Catalogue / Tarification / Commandes / Clients / Système) ; routes ajoutées dans `admin-frontend/src/router/routes.ts`.
- ✅ **Backend** : `GET /admin/price-groups` (superuser, lecture seule) ajouté dans [admin_payment_eligibility.py](backend/app/api/routes/admin_payment_eligibility.py) — débloque A7 (et préparera A9). Test : [test_admin_price_groups.py](backend/app/tests/api/test_admin_price_groups.py).
- ✅ **Écrans A1→A7** livrés (cf. tableau). Modules API dédiés sous `admin-frontend/src/api/`.
- ✅ **A13 — Validation des paiements** *(23/06/2026)* : `PaymentValidationsPage.vue` (route `/payment-validations`, section nav « Paiements ») — liste des paiements manuels (chèque/virement) et bons de commande en attente (`GET /admin/payments/pending-validation`), **approbation** (référence + commentaire) / **rejet** (motif requis), et pour les BC consultation + **téléchargement des pièces** (`/attachments` + `/attachments/{id}/download`, avec rewrite de l'URL presignée locale sur `VITE_API_URL` + état antivirus). API : [admin-frontend/src/api/paymentValidations.ts](admin-frontend/src/api/paymentValidations.ts).
- ~~🔲 **Restent** : A8 (featured), A9 (assign group — fusionné dans A15), A10 (adresses — **décision** désactiver/écran), A11–A12 (devis, fusion catégories — backend requis), et les nouveaux **A14 produit (override), A15 users + création de compte, A16 logistique (P4), A17 catégories (override + image), A18 commandes clients, A19 paiements**.~~ *(Mis à jour le 30/09/2026 : tout est livré sauf **A19**, cf. tableau ; nouveaux A20-A22.)*

### Avancement (04/09/2026) — A15 utilisateurs

- ✅ **A15 / A9 — Utilisateurs** : [admin_users.py](backend/app/api/routes/admin_users.py) (liste paginée avec recherche email/nom, filtres groupe / actif / invitation en attente ; création ; PATCH nom / téléphone / groupe / activation ; renvoi d'invitation) + [UsersPage](admin-frontend/src/pages/UsersPage.vue) (route `/users`, section nav « Clients »). Trois choix à connaître :
  - **L'invitation réutilise le flux « mot de passe oublié »** ([invitation.py](backend/app/features/user/services/invitation.py)) : même colonne `password_reset_token` (condensat SHA-256), même page vitrine `/reinitialiser` (avec `mode=invitation` pour le vocabulaire), même endpoint `POST /login/reset-password`. Seule différence : le lien vaut **72 h** au lieu de 30 min. Le compte est créé avec une empreinte de mot de passe aléatoire jetée aussitôt : rien ne l'ouvre avant le lien. Suivre le lien pose **`is_verified`** (l'adresse est prouvée) — ce que `reset_password` fait désormais pour tout compte.
  - **`last_login` est enfin écrit** (connexion mot de passe, OAuth, inscription — `mark_logged_in`, [crud/user.py](backend/app/features/user/crud/user.py)) : c'est ce qui permet de distinguer « invitation en attente » (ni vérifié, ni jamais connecté) d'un compte ouvert, et de **refuser le renvoi d'invitation** sur un compte activé — sinon un admin pourrait reprendre la main sur n'importe quel compte client.
  - **Désactiver un compte révoque ses refresh tokens** ; un admin ne peut pas se désactiver lui-même.
  - Tests : [test_admin_users.py](backend/app/tests/api/test_admin_users.py) (unitaires), [test_admin_users_flow.py](backend/app/tests/integration/test_admin_users_flow.py) (parcours réel création → lien → activation, renvoi qui invalide le premier lien, filtres), [test_admin_users_http.py](backend/app/tests/api/test_admin_users_http.py) (garde superuser, `last_login` posé par une vraie connexion). Au passage, la fixture `normal_user_token_headers` (jamais utilisée jusqu'ici) était cassée : l'insert partait sans empreinte — corrigée dans [tests/utils/user.py](backend/app/tests/utils/user.py).
### Avancement (04/09/2026) — A14 / A17 / A12 personnalisation vs sync

- ✅ **A14 produit** : [overrides.py](backend/app/features/product/services/overrides.py) (`merge_locks`, `release_lock`, `strip_locked`) consommé par [admin_product.py](backend/app/api/routes/admin_product.py), la sync ([supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py)) et l'enrichissement ([icecat_tasks.py](backend/app/tasks/icecat_tasks.py), `enrichment_payload`, tâche unitaire et batch). Nouveau `DELETE /admin/products/{id}/overrides/{field}`. Admin : puces de verrous dans la fiche produit (libération au clic) + cadenas dans la liste.
- ✅ **A17 / A12 catégories** : migration `b7e2d9c4a1f6` (`display_name`, `merged_into_id`), [admin_categories.py](backend/app/api/routes/admin_categories.py) (liste avec compte de produits, PATCH titre/description/image/activation, fusion qui déplace produits **et remises**), `CategoryPublic.title` consommé par la vitrine (`CataloguePage`) et les listes admin. Écran [CategoriesPage](admin-frontend/src/pages/CategoriesPage.vue) (section Catalogue). TVA et douane par catégorie restent sur leurs pages.
- Tests : [test_product_overrides.py](backend/app/tests/test_product_overrides.py) (règle + enrichissement + résolution du titre), [test_category_merge_flow.py](backend/app/tests/integration/test_category_merge_flow.py) (titre sans toucher la clé, fusion, refus self/cible fusionnée, chaîne de fusions suivie par la sync).

### Avancement (05/09/2026) — shipping classique « entrepôt → client » (DHL, Chronopost…)

**Question du propriétaire** : le projet sert-il un besoin e-commerce classique (un entrepôt, transporteurs avec n° de suivi saisi à la main, frais de port calculés), tout en restant capable du flux complexe fournisseur → étapes → entrepôt → client ? **Constat** : le socle existait (transporteurs + gabarit de lien, last-leg tarifé, page Logistique), mais un bug de sélection au checkout et deux manques l'empêchaient d'être « simple ». Quatre points livrés :

1. ✅ **Checkout piloté par `delivery_type`** ([cart.py](backend/app/api/routes/cart.py), [CheckoutPage.vue](frontend/src/pages/CheckoutPage.vue)). La vitrine envoyait `shipping_preference=fastest` **en plus** du mode choisi : le backend ajoutait la route client la plus rapide puis la route choisie → **deux derniers tronçons facturés** et suivi créé sur le mauvais transporteur dès qu'ils différaient ; et la branche « parcours par segments » (fournisseur → entrepôt) n'était jamais atteinte depuis la vitrine. Désormais : plus de préférence côté vitrine ; une préférence (clients API) ne choisit jamais de route client quand `delivery_type` est présent ; le parcours est construit depuis les segments — aucun tronçon amont pour le stock local, **tous les sauts** du chemin fournisseur → entrepôt principal pour les articles fournisseur, puis **un** tronçon final sur la route choisie. `applied_shipping_route_ids` reflète les routes réellement tarifées. Tests : [test_checkout_delivery_type_journey.py](backend/app/tests/integration/test_checkout_delivery_type_journey.py).
2. ✅ **Grille par tranches de poids + franco** sur `ShippingRoute` (migration `f3c8d5e2b7a4` : `weight_bands` JSON `[{max_kg, price}]`, `free_shipping_threshold`). La grille remplace `prix/kg × poids` (dernière tranche ouverte `max_kg: null`, sinon excédent au prix/kg ; le forfait s'ajoute) ; le franco met le tronçon à 0 dès que la valeur expédiée atteint le seuil (prime sur `min_total`, ne libère que ce tronçon). Snapshot `shipping_cost_breakdown` enrichi (`weight_band_max_kg`, `free_shipping_applied`). Éditeur de grille + champ franco dans [LogisticsRoutesPage.vue](admin-frontend/src/pages/LogisticsRoutesPage.vue). Doc : [shipping/README.md](backend/app/features/shipping/README.md) § *Tariff of a route*. Au passage : **fusion des trois têtes Alembic** laissées par les merges du 04/09 (`e2b7c4d9a1f3`) — `alembic upgrade head` refusait de s'exécuter.
3. ✅ **Transporteurs administrables + transport sur la fiche commande** : `POST/PATCH/DELETE /admin/shipping/carriers` (code slug unique, gabarit validé https + `{ref}`, retrait *soft*), page [CarriersPage.vue](admin-frontend/src/pages/CarriersPage.vue) (nav Commandes → Transporteurs) ; carte **Transport** sur [OrderDetailPage.vue](admin-frontend/src/pages/OrderDetailPage.vue) (tronçons, statut, transporteur, n° + lien, actions *Remettre au transporteur* / *Tronçon suivant* / *Livrer*) — une commande classique s'expédie depuis sa fiche. `GET /orders/{id}/journey` enrichi (transporteur, lien, `is_final_leg`, `is_terminal`) ; constructeur d'URL de suivi partagé ([tracking_url.py](backend/app/features/shipping/services/tracking_url.py)). Tests : [test_admin_carriers.py](backend/app/tests/integration/test_admin_carriers.py).
4. ✅ **Seed polynésien optionnel** : `SEED_FRENCH_POLYNESIA_LOGISTICS` (défaut `true`, comportement inchangé) ; à `false`, `initial_data` ne crée que transporteurs, statuts et données génériques — une boutique classique démarre avec son entrepôt et ses routes entrepôt → client. Documenté dans DEPLOYMENT.

**Reste (non livré)** : le total affiché au checkout vitrine n'inclut toujours pas les frais de port (affichés « + X » par option) ; l'heuristique d'adresse polynésienne de `cart.py` reste codée en dur (une adresse absente est traitée comme PF). `shared/api-types/src/schema.ts` a été régénéré depuis l'OpenAPI courant (il rattrape aussi les endpoints admin users / overrides livrés le 04/09).

#### ✅ Livré (05/09/2026, 2e tranche) — total du checkout, origine des marchandises, dropshipping

**S1 — Total du checkout vitrine = montant débité.** Helper `_quote_checkout` ([cart.py](backend/app/api/routes/cart.py)) partagé par `GET /cart/me/checkout-quote` et `POST /cart/checkout` : routes, frais de déclaration, frais du moyen de paiement et montants sont calculés une seule fois, le devis ne peut pas diverger de la commande. Vitrine ([CheckoutPage.vue](frontend/src/pages/CheckoutPage.vue)) : panier miroir côté backend dès l'ouverture, récapitulatif *Articles / Livraison (« Offerte » sous franco) / Dédouanement / Frais de paiement / **Total à payer*** rechargé à chaque changement d'adresse, de mode ou de moyen ; moyens de paiement filtrés sur le montant à payer hors frais de paiement ; bouton grisé tant que le devis n'est pas là. Tests : [test_checkout_quote.py](backend/app/tests/integration/test_checkout_quote.py).

**S2 — L'origine des marchandises se lit en base, plus dans le texte de l'adresse** (décisions propriétaire du 05/09) :
- **Entrepôt principal défini en base** : `Place.is_main_warehouse` (index unique partiel, un seul), `POST /place/{id}/set-main-warehouse` déflagge l'ancien ; étoile + action « Définir comme entrepôt principal » dans [LogisticsRoutesPage.vue](admin-frontend/src/pages/LogisticsRoutesPage.vue). Le seed polynésien flagge l'entrepôt de Papeete si aucun ne l'est. Repli historique (destination de la route d'import par défaut, puis premier entrepôt) conservé pour les bases non migrées.
- **Régime douanier par pays d'origine** ([origin.py](backend/app/features/shipping/services/origin.py)) : un fournisseur du **même pays** que l'entrepôt principal est **local** (ni douane, ni fret d'import, ni assurance : prix = coût × marge × taxe) ; un fournisseur d'un **autre pays** est **import** (formule CAF inchangée). Souplesse demandée : réglage système `customs_free_countries` (codes ISO, éditable dans *Paramètres*) pour traiter des pays comme locaux (union douanière…), et `Place.customs_regime` (*Automatique / Local / Import*) pour forcer un lieu. Origine non configurée = comportement antérieur (douane appliquée : sur-facturation visible plutôt que sous-facturation silencieuse). Effets : taux effectif figé sur la ligne de commande (`resolve_effective_customs_rate_pct`), publication sans taux de douane possible pour un produit local (porte SQL `customs_rate_condition` étendue), frais de déclaration facturés seulement si un article franchit la douane. Migration `a7d2e9f4b1c6`.
- **Fulfillment depuis les données** : l'heuristique « PF / TAHITI / PAPEETE » de `cart.py` est supprimée. Les articles fournisseur **regroupent à l'entrepôt principal** (`FulfillmentSegment.VIA_MAIN_WAREHOUSE`, valeur stockée `consolidation_pf` conservée) sauf si le lieu fournisseur est en **dropshipping** (`Place.dropship_enabled`) → `SUPPLIER_DIRECT`. Tests : [test_origin_regime.py](backend/app/tests/shipping/test_origin_regime.py), [test_origin_and_main_warehouse.py](backend/app/tests/integration/test_origin_and_main_warehouse.py), [test_checkout_delivery_type_journey.py](backend/app/tests/integration/test_checkout_delivery_type_journey.py).

#### Dropshipping — conception et périmètre livré

**Principe** : les colis partent **directement du fournisseur chez le client**, sans transiter par l'entrepôt principal. Se décide **par fournisseur** (`Place.dropship_enabled`, écran Trajets & Lieux), donc par produit via `Product.supplier_place_id`.

**Livré (05/09/2026)** :
- Au checkout, un article d'un fournisseur dropship donne un segment `SUPPLIER_DIRECT` ; le parcours créé est **un seul tronçon fournisseur → client** : la route `is_to_customer` **partant du lieu fournisseur** si l'admin en a créé une, sinon la route du mode de livraison choisi par le client. Une commande mixte (stock + dropship) a deux tronçons finaux en parallèle ; une commande 100 % dropship n'a pas de tronçon « entrepôt → client ».
- Le régime douanier s'applique comme ailleurs (fournisseur local = sans douane ; étranger = import).

**Reste à concevoir (non livré)** :
1. **Tarification par expédition** : aujourd'hui le client paie **une fois** le mode de livraison choisi, quel que soit le nombre de colis (un par fournisseur dropship + un pour le stock). À terme : un tronçon fournisseur → client porte son propre tarif (grille/franco de sa route) et le devis somme les expéditions — ou l'admin choisit d'absorber le surcoût. Décision propriétaire à prendre.
2. **Commande fournisseur automatique** : la remise au transporteur d'un colis dropship est faite **par le fournisseur** ; il faut lui transmettre l'adresse client (bon de commande fournisseur avec adresse de livraison = celle du client, cf. `supplier_orders`) et récupérer son n° de suivi (saisie manuelle dans la fiche commande, ou plus tard par API/email).
3. **Douane en dropshipping import** : un colis étranger livré directement au client est dédouané **à l'arrivée par le client ou le transporteur** (DDU) ou pris en charge par le vendeur (DDP). Aujourd'hui le prix inclut la douane (DDP implicite) ; le cas DDU (prix hors douane + avertissement client) n'est pas modélisé.
4. **Retours et SAV** : adresse de retour = fournisseur ou entrepôt ; à cadrer avec les CGV.

**Reste (non livré, hors dropshipping)** : `_get_main_warehouse_place_id` garde ses replis historiques — à retirer quand toutes les bases ont un entrepôt flaggé ; la liste `customs_free_countries` n'entre pas dans la porte SQL de publication (un produit d'un pays exempté sans taux de douane doit avoir son lieu forcé en *Local*, ou un taux 0).

---

## Dépendances inter-phases

```
Phase 0 (bugs)
  ├─→ Phase 1 (catalogue) → B1+B2+B6 corrigés requis
  └─→ Phase 2 (CB+OAuth)  → B1 corrigé requis pour les emails

Phase 1 → Phase 2 (groupes activés sur le pricing posé en P1)
Phase 1 → Phase 3 (specs YAML migrées vers table DB ; default_display_currency posé en P3)
Phase 1 → Phase 3 (corridor import unique posé en P1 ; mapping multi-fournisseurs + corridors multiples en P3, avec B8)
Phase 1 → Phase 4 (snapshots FX et CurrencyRate posés en P1, automatisation et multi-devises utilisateur en P4)
Phase 2 → Phase 3 (les emails P2 servent aussi tracking P3)
Phase 2 → Phase 3 (SupplierOrder P2 étendu par webhook Ingram P3)
Phase 3 → Phase 4 (les hooks de transition statut sont étendus)
Phase 4 → Phase 5d (tokenisation préparée en P4 pour Z1/Z2)
M3 (P5a) doit précéder Z2 (P5d)

Doc API Ingram ordre (endpoint + payload + webhook) : pré-requis externe à obtenir
avant de démarrer l'item 8 de Phase 2.
```

---

## Chantier pré-production — audit du 25/08/2026

Audit complet (sécurité, tests/CI, infra, complétude) mené le 25/08/2026. Phases 0–4 vérifiées livrées ; les items ci-dessous sont le **reste à faire avant mise en production**, groupés par jalon de lancement. Stratégie de lancement retenue : ouvrir d'abord avec un **catalogue restreint** et des commandes fournisseur passées **à la main dans le portail Ingram** (pas besoin de l'API prod pour les premières ventes — on demande l'accès prod ensuite, chiffres à l'appui, en se présentant comme revendeur à adresse de livraison unique, sans parler de dropshipping).

### PP-A — Bloquants sécurité (avant toute exposition publique)

| # | Item | Détail |
|---|------|--------|
| S1 ✅ | **Revalidation serveur de `POST /payments/initiate`** — livré 25/08/2026 | Faille d'origine : montant et `order_id` client acceptés tels quels (sous-paiement + rattachement à la commande d'autrui). Correctif en **3 couches** : ① `_validate_order_for_initiation` ([payments.py](backend/app/api/routes/payments.py)) — commande existante et appartenant à l'appelant (404 indistinct sinon), statut payable (409 `payment.order.not_payable` si Paid/Refunded/PartiallyRefunded), devise = celle du paiement checkout (409 `payment.currency.mismatch`), montant = total commande quantifié (409 `payment.amount.mismatch`) ; ② garde IPN — un IPN PAID/AUTHORISED dont le montant ≠ `payment.amount` n'est jamais complété : anomalie `amount_mismatch` posée dans `provider_data`, aucun event `payment.captured`, réponse 200 status=error (stoppe les retries PayZen) ; ③ `_captured_amount_covers_order` ([handlers/payment.py](backend/app/handlers/payment.py)) — le handler refuse de passer la commande à « Paid » (et de consommer le stock) si le paiement ne couvre pas le total. Tests : [test_payments_initiate_order_guard.py](backend/app/tests/api/test_payments_initiate_order_guard.py) (6 cas), [test_payzen_ipn_amount_guard.py](backend/app/tests/api/test_payzen_ipn_amount_guard.py) (PAID + AUTHORISED), mismatch handler dans [test_payment_outbox_handlers.py](backend/app/tests/test_payment_outbox_handlers.py). **Renforcé le 28/08/2026** : `_captured_amount_covers_order` est devenue `_captured_amount_mismatch` — une commande dont l'encaissement ne couvre pas le total passe désormais en statut **`PaymentReview`** avec **alerte admin** (auparavant le handler sortait en silence, laissant le stock réservé sans que personne ne le sache) ; la couche ① rejette en plus toute commande portant déjà un paiement **réglé** (409 `payment.order.already_paid` — le statut de commande ne bascule qu'en asynchrone, d'où une fenêtre de double débit) et **refuse** au lieu de passer outre quand aucun paiement de référence ne permet de contrôler la devise (409 `payment.order.no_reference`) |
| S2 ✅ | Ré-authentifier les 3 endpoints Icecat — livré 25/08/2026 | Dépendance `get_current_active_superuser` **restaurée** sur `/icecat/test`, `/icecat/search/upc/{upc}`, `/icecat/search/ean/{ean}` ([icecat.py](backend/app/api/routes/icecat.py)), même pattern que `/icecat/status`. Test 401 sans token ajouté dans [test_icecat_error_http_contract.py](backend/app/tests/api/test_icecat_error_http_contract.py) |
| S3 ✅ | ClamAV effectif hors local — livré 25/08/2026 | Garde de démarrage `_check_clamav_enabled` dans [config.py](backend/app/core/config.py) (même modèle que les secrets) : `CLAMAV_ENABLED=False` → warning en local, **refus de démarrer** en staging/prod. Compose et k8s le forçaient déjà à `true` ; la garde couvre les déploiements hors Docker / mal configurés. `.env.example` documenté (`CLAMAV_ENABLED=true`), DEPLOYMENT.md §3.10 et checklist prod mis à jour. Tests : [test_config_guards.py](backend/app/tests/test_config_guards.py) |
| S4 ✅ | Durcissements auth — livré 25/08/2026 | ① `SECRET_KEY` vide → **refus de démarrer** hors local (warning + génération en local ; [config.py](backend/app/core/config.py), tests dans test_config_guards.py). ② **Dummy-verify bcrypt** sur email inconnu ([crud/user.py](backend/app/features/user/crud/user.py)) — le temps de réponse ne révèle plus l'existence du compte. ③ `GET /group/{id}/users` **admin only** (403 `group.admin_required`, tests contract). ④ XFF : la **dernière** entrée (posée par notre proxy) est utilisée, plus la première (forgeable → contournement du throttle) — [rate_limit.py](backend/app/core/rate_limit.py), test mis à jour, doc CLIENT_IP_HEADER précisée |

### PP-B — Bloquants légaux (avant ouverture vitrine, jalon Phase 1)

| # | Item | Détail |
|---|------|--------|
| L1 ✅⚠️ | CGV + mentions légales + politique de confidentialité — squelettes livrés 25/08/2026 | 3 pages vitrine ([CgvPage](frontend/src/pages/legal/CgvPage.vue), [MentionsLegalesPage](frontend/src/pages/legal/MentionsLegalesPage.vue), [ConfidentialitePage](frontend/src/pages/legal/ConfidentialitePage.vue)) + routes `/cgv`, `/mentions-legales`, `/confidentialite` + **footer** avec liens ([MainLayout](frontend/src/layouts/MainLayout.vue)) + **case d'acceptation des CGV obligatoire au checkout** ([CheckoutPage](frontend/src/pages/CheckoutPage.vue)). ⚠️ Reste : compléter les `[À COMPLÉTER : …]` (grep-able) — identité société, RC/TAHITI, hébergeur, régime de rétractation PF — et **faire valider le tout par un conseil juridique** avant ouverture |
| L2 ✅ | Cookies — livré 25/08/2026 | Politique cookies documentée dans la page confidentialité (tableau refresh_token + stockage local). **Pas de bandeau** : seuls des cookies/stockages strictement nécessaires existent → exemptés de consentement. Si des cookies de mesure d'audience ou pub sont ajoutés un jour, un consentement PRÉALABLE devient obligatoire (noté dans la page) |
| L3 🔲 | Achat Ingram HT export — **action commerciale (hors code)** | Vérifier avec le commercial la facturation **hors TVA française** (exportation) — sinon 20 % de coût pour rien. Verrouiller aussi le paiement à la commande (virement/CB) en l'absence d'encours |

### PP-C — Facturation ✅⚠️ livrée le 25/08/2026 (M3 + M5)

**M5 — numéro de commande séquentiel ✅**
- `Order.order_number` (`CMD-AAAA-NNNNN`), alloué au checkout depuis la **séquence PostgreSQL** `order_number_seq` — trous acceptés, c'est une référence de communication. Champ **hors `OrderCreate`** (pas d'affectation de masse) ; séquence déclarée dans les métadonnées SQLModel pour exister aussi sous `create_all` (tests d'intégration).
- Ajout de **`Order.currency`** (figée au checkout) — prérequis facturation, la commande ne portait aucune devise.
- Exposé dans `OrderPublic` + payload outbox `order.created` ; les **emails** basculent sur `order_ref` (`resolve_order_ref` partagé handlers commande/expédition, repli `short_ref` pour les commandes antérieures) ; affiché dans la vitrine (compte) et l'admin.

**M3 — factures ✅**
- Modèle **`Invoice` immuable** (pas de `Base`, pas de CRUD générique → ni PATCH ni DELETE) + `snapshot` JSON figé à l'émission (vendeur, client, lignes, ventilation) : re-rendre une vieille facture reproduit le document d'origine.
- **Numérotation légale sans trou** : `invoice_counters` verrouillée `SELECT … FOR UPDATE` dans la transaction d'émission (`FAC-AAAA-NNNNN`, remise à 1 par exercice) — un rollback rend le numéro au lieu de le brûler, contrairement à la séquence de M5.
- **Ventilation TVA/TGC** : les prix stockés étant TTC, la facture remonte `HT = TTC / (1+taux)` **par groupe de taux**, la taxe étant le reste → `HT + taxe == total commande` exactement. Refus d'émettre si le total ne tombe pas juste.
- **Émission** sur `payment.captured` via un **handler outbox dédié** (`on_payment_captured_issue_invoice`), idempotent (contrainte unique `order_id`) et protégé par la même garde de montant que S1.
- **PDF WeasyPrint** (dépendance ajoutée + `uv.lock`), template Jinja2 A4 avec ventilation et typographie française. Import **paresseux** : sans les libs système, la facture est quand même émise et stockée, seuls les endpoints PDF renvoient 503.
- **Endpoints** : client `GET /invoices/me`, `/me/by-order/{id}`, `/me/{id}/pdf` (contrôle d'appartenance, 404 indistinct) ; admin `GET /admin/invoices[?fiscal_year]`, `/{id}`, `/{id}/pdf` et **`/export.csv`** (export comptable trié par numéro pour vérifier la continuité).
- **Surfaces** : vitrine = n° de commande + bouton de téléchargement de facture par commande (compte) ; admin = page **Factures** (filtre exercice, PDF, export CSV).
- **Tests** : 16 unitaires (ventilation, équilibre des totaux, idempotence, formats, rendu HTML, échappement XSS) + 4 d'intégration (continuité de la numérotation, unicité par commande, séquence) — ces derniers s'exécutent en CI (base requise).

**⚠️ Reste avant la première facture réelle**
- Renseigner `INVOICE_SELLER_*` (adresse, RC/TAHITI, mentions) — l'émission loggue un warning tant qu'ils sont vides, et le document n'est pas conforme.
- Faire **confirmer par le comptable** le traitement de taxe des frais (`INVOICE_FEES_TAX_CODE`, cf. écart F3) et la conservation/archivage légal.
- **Validation sandbox PayZen** (capture manuelle + refund implémentés mais jamais testés contre la sandbox — cf. backlog *Capture CB à l'expédition*).
- Backlog associé : avoir comptable (**Z2**) désormais débloqué par M3 ; export FEC strict si l'expert-comptable l'exige (le CSV actuel couvre le besoin courant).

### PP-D — Bloquants exploitation / infra

| # | Item | Détail |
|---|------|--------|
| I1 ✅⚠️ | Sauvegardes — outillage livré 25/08/2026 | [scripts/backup/backup.sh](scripts/backup/backup.sh) (`pg_dump -Fc` + tar du volume uploads + vérif magic + rotation 14 j) + **DEPLOYMENT.md §12** (quoi sauvegarder, cron, procédure de restore pas-à-pas + répétition à blanc). ⚠️ Reste **sur le serveur** : planifier le cron, configurer la copie hors site (rclone/scp), et **exécuter un restore réel** avant la première commande |
| I2 ✅ | `restart: unless-stopped` postgres/redis — livré 25/08/2026 | Ajouté dans [docker-compose.prod.yml](docker-compose.prod.yml) |
| I3 ✅ | Chaîne de déploiement **tranchée : compose sur serveur** — 25/08/2026 | **DEPLOYMENT.md §8 réécrit** : voie unique = build sur le serveur, `run --rm migrate` (upgrade + seed) avant `up -d`, rollback par git sha (la divergence §8 vs service migrate est résolue). [infra/DEPLOY.md](infra/DEPLOY.md) marqué **OBSOLÈTE** (manifests k8s cassés, détail en bannière), `deploy.yml` annoté (images GHCR génériques non consommées — gating CI = Q1). Réhabilitation k8s = backlog si besoin futur |
| I4 ✅ | `ARG VITE_API_URL` — livré 25/08/2026 | `ARG`/`ENV` dans les 2 Dockerfiles frontends + `build.args` câblés dans [docker-compose.yml](docker-compose.yml) depuis `VITE_API_URL` du `.env` racine (documenté `.env.example` + DEPLOYMENT §4/§6) |
| I5 ✅⚠️ | Retries ARQ — livré 25/08/2026 | [consumer.py](backend/app/outbox/consumer.py) : toute exception d'un handler outbox → `Retry(defer=backoff expo 10→300 s)`, 8 tentatives max (`max_tries` porté par la fonction, cf. `OUTBOX_HANDLER_MAX_TRIES`) — les commentaires « ARQ retries it » sont désormais vrais. ⚠️ Un échec **après 8 tentatives (~15 min)** reste un event `DONE` non rejoué (log error) : le filet final = alerting (reste I8) + `--mode retry` du runbook |
| I6 ✅ | Healthchecks réels — livré 25/08/2026 | `/healthz/ready` renvoie **503** si db/redis KO ([health.py](backend/app/api/routes/health.py) + test) ; healthcheck compose de l'api → `/healthz/liveness` (au lieu du `/utils/health-check` factice) ; **healthcheck `arq --check` sur le worker**. ⚠️ Corrigé le 28/08/2026 : la clé de santé arq est dérivée du **nom de queue seul**, si bien qu'avec `replicas: 2` une réplique vivante rafraîchissait celle d'une réplique morte et la panne restait invisible → clé désormais **par conteneur** (`arq:queue:health-check:$hostname`), et `health_check_interval` ramené de 60 à **20 s** (le TTL vaut `intervalle + 1` s : à 60 s la marge était d'une seconde, d'où des « unhealthy » fantômes sous charge). Poller : pas de healthcheck propre — couvert par le service outbox-health-checker |
| I7 ✅ | Caddy durci — livré 25/08/2026 | [Caddyfile](infra/caddy/Caddyfile) : snippet `security_headers` (HSTS, nosniff, X-Frame-Options DENY, Referrer-Policy) sur vitrine + admin, `request_body max_size 16MB` sur l'API. CSP volontairement absente (SmartForm PayZen injecte scripts/iframes) → backlog |
| I8 ✅⚠️ | Divers exploitation — livré 25/08/2026 | Rotation des logs Docker (anchor `x-app-logging` sur api/worker/poller, prod) ; timeouts `aiohttp` explicites (60 s total / 10 s connect) Ingram + Icecat ; `adminer` derrière `--profile debug` en prod ; « poller = 1 réplique max » documenté dans les 2 compose ; ordre migrate→rollout documenté §8. **Alerting minimal livré** : [core/alerting.py](backend/app/core/alerting.py) (webhook `ALERT_WEBHOOK_URL` façon Slack, fail-safe, testé) câblé sur le health-checker outbox (alerte sur **changement d'état** dégradé/erreur/rétabli — anti-spam) et sur l'**abandon définitif d'un job ARQ** après 8 tentatives ; healthcheck du health-checker corrigé (exit 1 sur statut error — avant toujours 0). ✅⚠️ **31/08/2026** : rotation du `outbox_poller.log` livrée (`RotatingFileHandler`, 5 Mo × 3) — et en la testant, le vrai défaut est apparu : `logging.basicConfig` du poller était un **no-op silencieux**, `features/base/crud` configurant déjà le root logger à l'import. Ni le niveau, ni le format, ni le fichier ne s'appliquaient : le fichier était créé **vide puis jamais écrit**, et les logs du poller sortaient au format d'un autre module. `force=True` ajouté, comme le worker ARQ le fait déjà. Le bump des images de base est fait par ailleurs (`node:24-alpine`, `nginx:1.31-alpine`, `python:3.13-slim`). ⚠️ Reste : **`logging.basicConfig()` au niveau module dans [features/base/crud.py](backend/app/features/base/crud.py)** — un module de bibliothèque n'a pas à configurer le root logger ; tant qu'il est là, tout point d'entrée qui oublie `force=True` voit sa configuration silencieusement ignorée |

### PP-E — Qualité / CI

| # | Item | Détail |
|---|------|--------|
| Q1 ✅ | `deploy.yml` gaté sur la CI verte — livré 25/08/2026 | Déclencheur passé en `workflow_run` (fin du workflow CI sur main) + `if: conclusion == 'success'` ; checkout et tags d'images sur `workflow_run.head_sha` (le commit exactement validé par la CI, pas la tête de main au moment du build) |
| Q2 ✅ | `fail_under = 60` réactivé — livré 25/08/2026 | Décommenté dans [backend/pyproject.toml](backend/pyproject.toml) (mesuré ~64,8 % au périmètre d'omission actuel → marge ; à remonter progressivement). ⚠️ Si la CI passe au rouge sur ce seuil, prioriser Q3 plutôt que de le redescendre |
| Q3 ✅ | Tests sur les modules critiques les moins couverts — livré 31/08/2026 | Les cinq modules visés passent de 19-23 % à **100 %** (97 % puis 100 % pour `cart/crud`), mesuré sur la suite unitaire seule : [test_payment_eligibility.py](backend/app/tests/test_payment_eligibility.py) (défaut ouvert vs restriction par groupe, plafond `max_amount` inclusif, tri, garde d'initiation), [test_discount_crud.py](backend/app/tests/test_discount_crud.py) (les quatre refus de `validate_coupon`, qui renvoient tous `False` — une confusion entre eux passait inaperçue), [test_cart_crud.py](backend/app/tests/test_cart_crud.py) (quantification du total dans la devise du panier, snapshot de change posé seulement s'il y a eu conversion, refus de re-totaliser un panier déjà commandé, scope d'appartenance de la ligne), [test_supplier_order_shipped_handler.py](backend/app/tests/test_supplier_order_shipped_handler.py) (handler qui **n'échoue jamais** par conception : sans test, plus rien ne dit qu'il avance ce qu'il doit avancer) et l'extension de [test_payment_payzen_utils.py](backend/app/tests/test_payment_payzen_utils.py) (chemin nominal jamais couvert, clé publique TEST vs PROD, `manualValidation` de la capture différée, réponse non-JSON, PSP_610, erreur HTTP, exception inattendue). **Trois chiffres de l'audit étaient périmés** : les webhooks Ingram côté route étaient déjà à 99 % — le vrai trou était [handlers/supplier_order.py](backend/app/handlers/supplier_order.py) (22 %), c'est lui qui a été couvert ; `utils/payzen.py` était à 83 % et non 48 % ; et l'éligibilité ne filtre pas par devise mais par **groupe tarifaire × plafond**. Seuil `fail_under` relevé 60 → **65** (Q2) |
| Q4 ✅ | Un e2e minimal du checkout — livré 28/08/2026 | Parcours Playwright catalogue → panier → checkout → commande ([e2e/tests/checkout.spec.ts](e2e/tests/checkout.spec.ts)), paiement par virement manuel donc aucune passerelle réelle dans la boucle. `data-testid` posés sur les pages traversées, seed dédié ([e2e/seed_e2e_data.py](e2e/seed_e2e_data.py)), et **job CI** qui le fait tourner sur le stack compose |

### PP-F — Fonctionnel minimal de lancement

- ✅ **Écran admin des demandes de devis (A11)** — livré 28/08/2026 : [admin_quote_requests.py](backend/app/api/routes/admin_quote_requests.py) + [QuoteRequestsPage](admin-frontend/src/pages/QuoteRequestsPage.vue) + migration `e5f9c3a7b2d8` (statuts, commentaire interne, clôture). Les demandes de **visiteurs non connectés** sont désormais persistées **avant** l'envoi de l'email : auparavant un échec d'envoi les perdait définitivement alors que l'endpoint répondait 201.
- ✅ **Endpoint « mot de passe oublié »** — livré 28/08/2026 : [password_reset.py](backend/app/api/routes/password_reset.py), emails dédiés, pages `/mot-de-passe-oublie` et `/reinitialiser`. Réponse identique que l'adresse existe ou non, stockage du seul SHA-256 du jeton, révocation des refresh tokens au changement.
- 🔲 Vérifications prévues au plan, à tracer faites avant ouverture : taux d'enrichissement Icecat sur le catalogue réel (filtre `is_enriched`), backfill `category_id`, check mensuel des taux FX manuels, volumétrie storage en prod.
- 🔲 **Saisir les frais par déclaration et le taux d'assurance** (suite de F3/F4, DEPLOYMENT §16) : deux paramètres qui, laissés à zéro, sortent silencieusement de la marge — le rapport d'ouverture affiche leur état courant. Zéro reste un choix légitime (frais inclus par le transitaire, aucune police souscrite), à condition qu'il soit fait sciemment.
- 🔲 **Saisir les taux de douane par catégorie** (suite de F1/F2) : depuis le 28/08/2026 un produit dont le taux ne se résout pas est **masqué**, donc `GET /admin/catalog/publication-report` doit tomber à zéro produit bloqué avant d'ouvrir. Le même rapport chiffre les produits sans poids (F5) — deux compteurs à ramener à 0, catégorie par catégorie.

---

## Chantier production-ready — audit et livraison du 02/09/2026

Audit code (et non documentaire) des trois chantiers dont dépend l'ouverture :
synchros Ingram/Icecat/stock, parcours client complet, infra. Les items
ci-dessous ont été **livrés le 02/09/2026**, un commit par sujet.

### PR-A — Synchronisation & stock

| # | Item | Détail |
|---|------|--------|
| N1 ✅ | **Rate limits Ingram & Icecat** | Les deux clients levaient une `Exception` nue sur tout statut ≠ 200 : un seul 429 en pagination perdait la catégorie, et le retry ARQ repartait aussitôt sur le même endpoint. `requests_per_minute` était déclaré dans le contrat `SupplierAdapter` et **jamais lu**. Ajout de [core/http_retry.py](backend/app/core/http_retry.py) : limiteur de débit par processus (120 req/min Ingram, 60 Icecat) + backoff exponentiel à jitter complet respectant `Retry-After`, plafonné à 120 s. Seuls 429 et 5xx sont rejoués. **Les POST de commande fournisseur ne rejouent que sur 429**, jamais sur 5xx ni coupure : ces cas sont ambigus, la commande a pu partir, et la passer deux fois coûte de l'argent |
| N2 ✅ | **Fuite de stock sur commandes non payées** | `release_order_stock` n'était appelé que sur `payment.rejected` : un panier abandonné sur la page de paiement retenait son stock indéfiniment. Balayage ARQ horaire ([tasks/inventory_tasks.py](backend/app/tasks/inventory_tasks.py)) libérant les commandes restées « Pending » au-delà de `STOCK_RESERVATION_TTL_HOURS` (48 h). `AwaitingPayment` (virement en validation) et `PaymentReview` sont **épargnés** : un humain ou un événement les pilote encore. Libération ajoutée aussi sur `payment.refunded` intégral (cas autorisation-puis-remboursement, fonds jamais capturés) |
| N3 ✅ | **Delisting** | Une référence retirée du catalogue Ingram restait active avec son dernier prix et son dernier stock connus. Nouvelle colonne `products.supplier_missing_since` (migration `b7d4e9a2c518`) : la première absence est **enregistrée**, la désactivation n'intervient qu'au-delà de `SUPPLIER_DELISTING_GRACE_HOURS` (72 h). Un lot entier revenant vide est traité comme un incident d'API, pas comme cinquante disparitions |
| N4 ✅ | **Disponibilité temps réel au checkout** | La dispo vérifiée était l'instantané local, vieux de 0 à 2 h. Appel prix/dispo synchrone avant réservation ([checkout_availability.py](backend/app/features/integrations/services/checkout_availability.py)), une requête par commande. **Asymétrie assumée** : un fournisseur qui répond « plus de stock » change l'issue, un fournisseur injoignable n'en change aucune (l'instantané fait foi) — refuser toutes les commandes pendant une panne Ingram coûterait plus cher que le risque réduit. Délai court (8 s), on est sur le chemin critique |
| N5 ✅ | **Icecat : UPC absent du lot** | La tâche unitaire passait `upc`, le lot non. Le même produit trouvait sa fiche à la main et la ratait dans le cron horaire. Enjeu réel : la publication exige un poids qu'Ingram ne fournit jamais et qu'Icecat seul apporte, donc le taux de correspondance décide de la taille du catalogue vendable. Test de parité par AST des deux appels |

### PR-B — Parcours client

| # | Item | Détail |
|---|------|--------|
| N6 ✅ | **Prix non revalidé au checkout** | `CartItem.unit_price` est figé à l'ajout, mais la synchro réécrit le coût toutes les 2 h. Le checkout résolvait le prix courant puis **jetait le résultat** et facturait l'instantané. Toute dérive, dans un sens comme dans l'autre, arrête désormais le checkout (409 `cart.price.changed`), le panier étant mis à jour **avant** de lever l'erreur pour que le client relise le prix qu'on lui demande d'accepter. La vitrine adopte ces prix (`applyServerPrices`) avant d'afficher le message |
| N7 ✅ | **Frais de paiement pilotés par le client** | `payment_fee_amount` arrivait dans le corps de la requête et était pris au pied de la lettre. Le montant est lu sur `PaymentMethod.fee` ; le champ de requête devient optionnel et documenté comme ignoré |
| N8 ✅ | **Panier : recopie N+1 non transactionnelle** | Le checkout faisait `DELETE` puis un `POST` par ligne. Un échec au milieu laissait un panier serveur tronqué, commandé ensuite comme s'il était complet — et le `DELETE` détruisait ce que le compte contenait déjà (pas une fusion). Nouveau `PUT /cart/items` atomique : tous les produits résolus et validés d'abord, écriture en une transaction, identifiants répétés fusionnés. Deux pièges corrigés au passage : `get_or_create_active_cart` commite (donc périme les produits résolus avant lui, et jetait le prix calculé), et `(cart_id, product_id)` étant unique, une désactivation logique ne libère pas la clé — les lignes sont réutilisées |
| N9 ✅ | **Facture jamais envoyée** | Émise, numérotée, stockée, et jamais délivrée. Événement `invoice.issued` + handler dédié + templates. L'email porte les montants et un lien vers l'espace client, **pas le PDF** : son rendu dépend des bibliothèques système de WeasyPrint, et une police manquante ne doit pas coûter au client l'information qu'il a été facturé. Colonne `invoices.emailed_at` pour l'idempotence (l'outbox livre au moins une fois) ; un envoi non délivré lève, pour que le retry ARQ reprenne |
| N10 ✅ | **Avoirs (Z2)** | Un remboursement déplaçait de l'argent sans produire de document rectificatif. Modèle `CreditNote` (`AV-AAAA-NNNNN`) avec **son propre compteur** — les deux séquences sont légalement distinctes — émis sur `payment.refunded`, idempotent sur `refund_id` unique. Ventilation reprise de la facture d'origine, **jamais recalculée** (créditer au taux d'aujourd'hui une vente taxée au taux de l'an dernier ne tomberait pas juste), appliquée au prorata sur un remboursement partiel, le dernier groupe absorbant l'arrondi. Un cumul dépassant le total de la facture est refusé. PDF + endpoints client et admin + export CSV |
| N11 ✅ | **Facture sans identité légale** | `_seller_identity` se contentait d'un warning. Le coût est asymétrique : ne pas émettre est réversible, émettre un document non conforme ne l'est pas (numéro consommé dans une séquence sans trou, facture immuable). Raison sociale, adresse et immatriculation deviennent bloquantes hors `local`, avec alerte opérationnelle |
| N12 ✅ | **Retour 3-D Secure perdu** | L'identifiant du paiement ne vivait que dans le `localStorage` de l'onglet d'origine. Le 3-D Secure se terminant souvent dans l'app de la banque, un paiement réussi s'affichait « Aucune transaction en attente ». L'identifiant passe par l'URL de retour, le `localStorage` restant en repli |
| N13 ✅ | **Emails jetés en silence** | `PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER` était une chaîne libre ; une valeur inconnue retombait sur `noop`, qui déclare réussir et jette le message. Une coquille dans le `.env` supprimait donc toutes les notifications transactionnelles. Le réglage devient un `Literal` refusé par pydantic au démarrage, avec un test comparant l'ensemble accepté au registre des fournisseurs |

### PR-C — Infra

| # | Item | Détail |
|---|------|--------|
| N14 ✅ | **Mot de passe Postgres en dur** | `postgres` était codé en dur sur le service base **et** dans l'environnement de api/worker/poller/migrate, sans être réécrit par `docker-compose.prod.yml` : la production tournait dessus en ignorant le `.env`, et `outbox-health-checker` (qui lisait `${POSTGRES_PASSWORD}`) n'aurait plus pu se connecter dès qu'une vraie valeur y était mise. Interpolation partout, et garde de démarrage refusant les mots de passe de développement connus hors `local` |

### Reste à faire (non couvert le 02/09/2026)

> Toujours ouvert au 30/09/2026 ; ordre conseillé, chiffrage et compléments (OAuth, images, S3, CI/prod) dans *Feuille de route 30/09*, **R6**.

- 🔲 **Sauvegardes non branchées** : le script existe, le cron et un restore réel restent à faire **sur le serveur**.
- 🔲 **`ALERT_WEBHOOK_URL` vide** : sans lui, perte d'un event outbox, health-check en erreur et échec de sauvegarde ne notifient personne. Devenu plus important avec N11, qui alerte sur identité légale incomplète.
- 🔲 **Pas de 2FA back-office** et `ENABLE_GROUP_PERMISSIONS=False` (tout utilisateur authentifié passe les contrôles ; seul `is_superuser` protège l'admin).
- 🔲 **Relecture juridique** des CGV / mentions / confidentialité, et formulaire de rétractation côté client.
- 🔲 **Validation sandbox PayZen** de la capture différée et du refund, toujours jamais testés contre la sandbox.
- 🔲 **Panier invité serveur** : le panier vitrine reste en `localStorage` (N8 rend sa recopie atomique, mais ne crée pas de panier invité persistant ni de fusion à la connexion).
- 🔲 Conteneurs en root, pas de CSP, aucune métrique exportée, déploiement manuel sans rollback par image.

---

## Risques / points d'attention transverses

| Risque | Mitigation |
|--------|------------|
| Le `CheckoutMetricsStore` in-memory rendra les métriques incohérentes en multi-replicas (B7) | Migrer vers Redis en Phase 2 (avant scale-out) |
| Auto-sélection routes shipping non globalement optimale (B8) | Acceptable pour Phase 1-2 (devis manuel) ; à corriger avant Phase 3 |
| OAuth : conflit email password/social | Décider en Phase 2 : refus + message vs liaison après validation par email |
| Sync Ingram = écrasement du `cost_amount` côté pricing | Vérifier qu'aucune logique métier ne s'appuie sur le `base_price` pré-Phase 1 |
| Prix dépendant du mode de transport import (couplage pricing × logistique) | Choix client = **un seul niveau de service** appliqué à tous les corridors (jamais une route par fournisseur) ; corridor unique en P1, mapping multi-fournisseurs reporté P3 ; backend autoritaire au panier |
| Dimensions physiques absentes d'Icecat → poids volumétrique non calculable (fret sous-estimé sur produits volumineux/légers) | Fallback poids réel (jamais de blocage) ; mesurer la couverture dimensions sur le catalogue réel ; saisie/override admin possible pour les cas critiques |
| Migrations alembic destructrices sur `Product` (B9 + ajouts cost_amount, customs_rate, JSONB specs) | Une seule migration de fond début Phase 1, plutôt que plusieurs accumulées |
| Hypothèse « PF only » figée dans le code (TVA, marges, libellés) | Taux stockés dans `TaxRate.territory_code`, jamais en constante ; résolution centralisée dans `resolve_tax_rate()` |
| Identification entreprise non-portable si extension hors PF | Champ générique `business_registration_number` (jamais `siret`) dès la Phase 2 |
| Templates email manquants | Préparer les 4 templates (commande, payé, échec, livré) en Phase 2 pour ne pas bloquer le déploiement |
| Données Icecat dépendantes de credentials Open vs Full | Vérifier que le périmètre P1 fonctionne en Open Icecat (gratuit) |
| Prix de vente faux si conversion devise manquante (cost USD multiplié comme s'il était la référence) | Helper `convert_to_reference_currency` obligatoire dès P1 ; `CurrencyRateMissing` levée explicitement (pas de fallback silencieux) |
| Devise de référence figée en dur (`xpf` dans noms de fonctions/colonnes) → migration coûteuse si extension hors PF après mise en prod | Dé-localiser en **pré-prod (P1)** : `REFERENCE_CURRENCY` (.env), `convert_to_reference_currency`, colonne `rate_to_reference`. Pas de machinerie multi-territoire tant qu'inutile (YAGNI) |
| Taux manuel oublié (USD/XPF figé pendant des mois) | Notification admin si > 30 j (P4) ; en P1 documenter dans le runbook un check mensuel |
| Filtre `is_enriched=True` exclut tout le catalogue si Icecat a peu de matches | Avant déploiement : mesurer le taux d'enrichissement sur le catalogue Ingram réel ; si < 80%, prévoir un fallback (afficher sans specs filtrables) ou élargir Icecat Full |
| Aliases YAML incomplets → specs non projetées | Job `reproject_product_specs` idempotent + monitoring du % de produits enrichis qui ont au moins 5 specs projetées |
| Bouclage projection × volume catalogue Ingram | Mesurer le temps de re-projection sur le catalogue cible avant déploiement ; si > 30 min, paralléliser par batch ARQ |
| Prix volatils (GPU/mémoire, marché à ±15 %/trimestre) : écart entre prix affiché (sync 2 h) et coût réel à la commande ; juridiquement le prix affiché engage envers un particulier | Refresh **stratifié** (cf. backlog) ; **re-vérification P&A synchrone au checkout** ; pour les références très volatiles, basculer en **flux devis** (prix ferme 24-48 h, autorisation CB sans capture — déjà livrée —, commande fournisseur immédiate) ; cibler ces références vers le **B2B pro** (RTX PRO / stations), canal fort d'Ingram, plutôt que le gamer |
| Rupture entre deux syncs : la dispo vérifiée au checkout est le **snapshot local** ([cart.py](backend/app/api/routes/cart.py) `_plan_checkout_fulfillment_segments`), aucun appel Ingram temps réel | Appel P&A synchrone au checkout (1 appel/commande, négligeable vs quota) ; demander au commercial l'activation de la **réservation d'inventaire** Ingram |
| SAV/garantie : l'importateur est le garant légal ; un RMA Tahiti → Europe coûte souvent plus que la marge du produit, fenêtres RMA courtes | Provisionner **2-3 % du CA** en réserve garantie ; privilégier les marques à **garantie constructeur internationale** (Dell/HP/Lenovo pro) ; critère whitelist |
| Compte Ingram neuf = dernier servi sur les allocations (stocks faibles affichés → course perdue) | Ne pas exposer les références à allocation ; flux devis + paiement d'avance ; construire l'historique de volume avant d'élargir |

---

## Estimation effort (rough order of magnitude)

| Phase | Effort backend | Effort frontend (vitrine) | Total |
|-------|----------------|---------------------------|-------|
| 0 | S (3-5 j) | — | S |
| 1 | L+ (4-5 sem, incluant devises + specs filtrables) | M (2 sem vitrine) | L+ |
| 2 | XL (5-7 sem) | L (3 sem) | XL |
| 3 | M+ (3 sem, +extension specs DB + champ devise par défaut) | M (1-2 sem) | M+ |
| 4 | L (3-4 sem, +cron forex et multi-devises utilisateur) | M (2 sem admin) | L |
| 5 | XL (à découper en 5a-5e) | variable | XL |

S = ≤1 sem, M = 1-3 sem, L = 3-6 sem, XL = >6 sem.

Ces estimations sont des ordres de grandeur pour un dev expérimenté seul ; à recalibrer selon ressources et taille des templates email/PDF.

---

## Optionnel / différé (non prioritaire)

Items sortis du périmètre actif sur décision produit — à reconsidérer plus tard.

### Devises — auto-update FX + alerte (déprioritisé le 26/06/2026)

**Pas une priorité.** Le volet **affichage multi-devises** est livré (sélecteur + conversion côté client, endpoint `GET /currency/display-rates`) ; les taux restent **saisis/maintenus à la main** dans l'admin (`CurrencyRatesPage`). Reste, si un jour utile :
- Variable `CURRENCY_AUTO_UPDATE_ENABLED: bool = False` (opt-in).
- Cron quotidien ARQ → source externe (ECB API / exchangerate.host) → nouveau `CurrencyRate` `source='auto'` ; **ne pas écraser** un taux `manual` récent (< 24 h).
- **Alerte email** admin si le dernier taux actif a > 30 jours (taux périmé).
- (Éventuel) écran admin dédié au suivi des taux auto vs manuels.

---

## Profil de territoire et mode « boutique simple » ✅ (11/09/2026)

`TERRITORY_PROFILE` (`PF` par défaut, `FR`) résout devise de référence, pays, territoire fiscal, taux par défaut (produits et frais), devise PayZen et données de démarrage (taux de taxe et de change du profil, arbre des îles ou simple nœud pays) — chaque réglage reste surchargeable individuellement (`app/core/territory.py`). Plus aucun « PF » / « XPF » / « TGC_NORMAL » codé en dur sur le chemin de vente : le pricing, le panier, les préférences, la facture et l'identité légale lisent les réglages. `SHOP_MODE=simple` masque dans l'admin fournisseurs, douane, taux de change, catalogue de specs et trajets multi-tronçons, passe la fiche produit en prix fixe par défaut et ne planifie ni la synchro fournisseur ni Icecat. `GET /system/config` expose profil, mode et devise aux deux frontends.

> 🔲 **Évolution décidée le 30/09/2026** : en mode simple, Ingram et Icecat sont **désactivés par défaut mais réactivables depuis l'admin sans redémarrage** (état en base, `SHOP_MODE` ne pilote que les défauts et l'affichage ; page Fournisseurs visible pour l'import CSV) — *Feuille de route 30/09*, R4 / S6.

## Backlog e-commerce — fonctionnalités classiques (à planifier)

Idées de fonctionnalités e-commerce standard à instruire plus tard. État de l'existant noté pour ne pas refaire.

### Variantes d'articles ✅ (10/09/2026)
Une variante est une ligne `products` rattachée à son parent (`parent_product_id`, `variant_options`) : SKU, prix, coût, stock, image, poids, mapping fournisseur, panier, commande, facture et mouvements de stock inchangés. Le parent (`has_variants`) est l'entrée boutique, affiche « à partir de » (prix de la variante la moins chère, remonté à chaque changement et par le rafraîchissement des prix), n'est jamais vendu tel quel (409 `cart.product.has_variants`) ; les variantes ne sont jamais listées seules. Vitrine : sélecteurs par option sur la page produit (`GET /product/{id}/variants`), « Choisir » sur les cartes. Admin : panneau Variantes dans la fiche produit (`/admin/products/{id}/variants`). Conception initiale :
- Modèle **`ProductVariant`** (SKU, options ex. taille/couleur, **prix/coût**, **stock** propres, image), rattaché au `Product` parent.
- Sélection de variante côté **vitrine** (sélecteurs d'options) ; **panier/commande** référencent la variante.
- Mapping **sync fournisseur** (Ingram renvoie-t-il des variantes ? sinon variantes « manuelles »).
- Impact pricing (le runtime pricing s'applique par variante) et logistique (poids/volume par variante).

### Réductions / codes promo / vouchers ✅ codes promo livrés (10/09/2026) — vouchers nominatifs à instruire
Le feature **`discount`** existe déjà ([models.py](backend/app/features/discount/models.py)) : `DiscountType`, `DiscountTarget`, champ **`code`**, CRUD. Reste à **câbler le parcours client** :
- ✅ Saisie d'un **code promo au checkout** → validation serveur (existence insensible à la casse, dates, minimum d'articles concernés, quotas global **et par client**, cible commande / produit / catégorie), remise en % ou en montant, ventilée par ligne (`OrderLine.discount_amount`), figée sur la commande (`discount_id` / `discount_code` / `discount_amount`), quota pris atomiquement à la commande, remise portée sur la facture.
- **Vouchers / bons d'achat** (montant prépayé nominatif) si distinct des remises % / montant.
- ✅ **Écran admin** « Codes promo » (création, conditions, suivi d'usage, activation).
- Cohérence avec **groupes de prix** (cumul ou exclusivité ?) et **devise** (remise en XPF).

### PayPal (intégration standard) ✅ livré le 30/09/2026 (R3-P7, reste la validation sandbox) — décision du 30/09/2026 : **Stripe et PayPal**, activables en base (*Feuille de route 30/09*, R3 : P4 chantier commun, P5 activation, P6 Stripe, P7 PayPal)
Stripe **indisponible en PF** → cible **PayPal** comme moyen CB alternatif. À intégrer dans l'**abstraction provider existante** (comme PayZen / manual) :
- Provider `PayPalProvider` (init paiement, capture, **refund** — à brancher sur le chantier remboursement), webhooks de statut.
- Config (client id/secret, sandbox/prod), éligibilité (cf. **contrainte devise × moyen de paiement** — PayPal facture en EUR/USD, pas XPF → à traiter sérieusement, pas seulement présentationnel).

### Capture CB à l'expédition — autorisation au checkout, débit à l'envoi 🟡 (capture manuelle livrée le 26/06/2026)
**Objectif** : pour les paiements **CB (PayZen)**, ne **débiter le client qu'à l'expédition**. Au checkout, la CB est **autorisée** (réservation des fonds) ; au moment de l'**envoi**, on déclenche la **capture** → le règlement est prélevé. Option (flag), pas le défaut.

**✅ Livré**
- **Flag** `PAYZEN_MANUAL_VALIDATION` ([config.py](backend/app/core/config.py)) → le form token PayZen est créé avec `manualValidation: "YES"` ([payzen.py](backend/app/features/payment/utils/payzen.py)) → autorisation seule.
- **Webhook** : `trans_status = AUTHORISED` → statut paiement **`Authorized`** (seedé), **sans** publier `payment.captured` ([payments.py](backend/app/api/routes/payments.py)).
- **Capture** : `capture()` sur l'abstraction provider ([base.py](backend/app/features/payment/providers/base.py)) ; PayZen appelle `Transaction/Validate` (util `capture_payzen_transaction`). Service `capture_payment` ([capture_service.py](backend/app/features/payment/services/capture_service.py)) : vérifie le statut `Authorized`, capture, puis pose **`Completed`** + publie l'event **`payment.captured`** existant (→ statut commande « Paid », commande Ingram, email — **réutilisation sans modifier l'aval**).
- **Endpoint** `POST /admin/payments/{id}/capture` + **bouton « Capturer »** sur la fiche commande ([OrderDetailPage.vue](admin-frontend/src/pages/OrderDetailPage.vue)) pour les paiements `Authorized`. Tests : [test_capture_flow.py](backend/app/tests/integration/test_capture_flow.py) + mapping webhook.

**⏳ Reste / suivi**
- ⚠️ **Valider l'intégration PayZen en sandbox** : le param `manualValidation`, le statut IPN `AUTHORISED`, et l'appel `Transaction/Validate` (capture) sont implémentés mais **non testés contre la sandbox** (comme le refund). À vérifier avant prod.
- **Auto-capture à l'expédition** : aujourd'hui la capture est **manuelle** (l'admin clique « Capturer » au moment d'expédier). Câbler la capture **automatique** sur l'action ship (best-effort, par commande) — non fait pour éviter le couplage logistique↔paiement + la question de la **capture partielle** (livraisons multi-tronçons).
- **Void d'autorisation** (annulation d'empreinte avant capture, distinct du refund) + **alerte** si l'autorisation approche de l'expiration (≈ 7 j) sans expédition.
- **Capture partielle** (une partie de la commande expédiée).

### Whitelist catalogue & éligibilité automatique 🔲 (discussion du 25/08/2026) — complété le 30/09/2026 par le **mappage catégories par fournisseur** (*Feuille de route 30/09*, R4 / S5), qui remplace la liste blanche globale de sous-catégories
Ne jamais exposer le catalogue Ingram brut (~centaines de milliers de SKU) : viser 3 000–8 000 références via des **critères d'éligibilité automatiques** câblés dans la sync :
- dispo > 0 sur les entrepôts pertinents ; **poids ET dimensions présents** (sans eux le fret est incalculable → inéligible par définition — corrige aussi l'écart F5 de la section CAF) ; pas de flag EOL/discontinued ; marques whitelistées ; match Icecat de qualité suffisante.
- **Règle valeur/poids (XPF/kg)** comme seuil d'éligibilité automatique : exclure sans état d'âme les catégories jamais compétitives au fret (écrans, boîtiers, imprimantes), même si Ingram les propose.
- En faire une fonctionnalité produit : flux **« nouveautés »** alimenté par les entrées récentes du catalogue — différenciant face aux revendeurs locaux. L'argument vitrine n° 1 reste toutefois « **prix final rendu, taxes et livraison comprises, avant de commander** » (personne ne fait ça localement) — à mettre en avant sur la page d'accueil.

### Rafraîchissement stratifié des prix 🔲 (discussion du 25/08/2026)
Aujourd'hui : cron toutes les 2 h, balayage **uniforme** de tout ce qui a > 1 h de retard, par lots au rate-limit ([supplier_tasks.py](backend/app/tasks/supplier_tasks.py)). La fraîcheur réelle par SKU dépend de la durée d'un cycle complet. À budget d'appels constant, stratifier : références **haute valeur / stock faible** toutes les heures, ventre du catalogue quotidien, longue traîne hebdomadaire (tri par `last_supplier_sync` + score valeur/volatilité).

### Commandes groupées cadencées 🔲 (discussion du 25/08/2026)
Annoncer un **départ consolidé hebdomadaire ou bimensuel** : les clients commandent d'ici la date, un seul envoi → le fret unitaire s'effondre et le délai devient une promesse claire au lieu d'un aléa. S'appuie sur la machinerie consolidation existante (P4) ; le chantier restant est surtout vitrine (affichage de la prochaine date de départ, compte à rebours) + process interne.

→ **Cadré le 24/09/2026** : devient l'objet unique « Départ groupé » (date en vitrine, rattachement des commandes, rappels réseaux sociaux, statut propagé) — voir la section *Décision transverse : précommande, départs groupés et acompte (24/09/2026)*, qui porte aussi l'état des lieux de la spec précommande et la faisabilité de l'acompte.

### Déjà présents (à finir / exposer si besoin)
- **Avis produits** (`Review` + CRUD + route `user_review`) 🟡 — vérifier modération / affichage vitrine.
- **Wishlist / favoris** (`wishlist` + CRUD + route `user_wishlist`) 🟡 — vérifier l'exposition vitrine.

### Autres pistes classiques (à arbitrer)
- **Stock / inventaire** réel (aujourd'hui flag `in_stock` ; gestion fine différée — cf. commit « Remove on Stock at this time »), réservation au panier.
- **Paniers abandonnés** + relance email.
- **Recommandations / cross-sell / up-sell / produits similaires**.
- **Cartes cadeaux** (gift cards).
- **Comparateur de produits**.
- **Programme de fidélité / points**.

---

## Évolutions techniques à prévoir (dettes et veille)

Points **techniques** différés en connaissance de cause, avec le déclencheur qui
doit les faire remonter en priorité. À distinguer des deux backlogs ci-dessus,
qui portent sur le produit.

### httpx → httpx2 🔲 (relevé le 28/08/2026)

`starlette` 1.6 déprécie l'usage de `httpx` par son `TestClient` au profit de
**`httpx2`**, repris par Pydantic sous [pydantic/httpx2](https://github.com/pydantic/httpx2).
Ce n'est pas une refonte : l'API reste compatible, l'objectif affiché est la
maintenance et les correctifs de sécurité.

**Pourquoi ça compte ici.** `httpx` n'a rien publié depuis le **6 décembre
2024** (0.28.1), alors qu'il porte les appels **PayZen, Mailgun, Slack et
OAuth** — [payzen.py](backend/app/features/payment/utils/payzen.py),
[mailgun.py](backend/app/features/notification/providers/mailgun.py),
[slack_webhook.py](backend/app/features/notification/providers/slack_webhook.py),
[oauth.py](backend/app/api/routes/oauth.py). Une faille sur le client HTTP du
chemin de paiement n'attendrait pas 20 mois son correctif.

**Pourquoi ne pas migrer tout de suite.** L'extra `standard` de FastAPI 0.141
exige toujours `httpx<1.0.0,>=0.23.0` ; `starlette[full]` accepte les deux.
Basculer le code applicatif dès maintenant reviendrait donc à **embarquer deux
piles HTTP** dans l'image — l'inverse du nettoyage de dépendances mené les
27–28/08. L'avertissement ne vise par ailleurs que `TestClient`, donc les tests,
pas le code de production.

**Déclencheurs :** FastAPI bascule son extra `standard` vers httpx2 (la
migration devient alors mécanique, 5 fichiers), **ou** un avis de sécurité sur
`httpx` sans correctif publié — auquel cas on migre en acceptant le doublon.

⚠️ **Point de vigilance au moment de migrer :** httpx2 remplace `certifi` par
`truststore`, c'est-à-dire le magasin de certificats du **système** au lieu d'un
bundle CA embarqué. Plus sain sur le fond (une révocation prend effet
immédiatement), mais l'image `python:3.12-slim` devra avoir `ca-certificates` à
jour, sans quoi **toutes** les connexions TLS sortantes tomberont.

### Trois majeures JS bloquées en amont 🔲 (relevé le 28/08/2026) — `@quasar/app-vite` 3 ✅ (30/09/2026)

**`typescript` 6 → 7** — la 6 est en place, la 7 est bloquée par l'outillage et
non par notre code :

```
Error [ERR_PACKAGE_PATH_NOT_EXPORTED]: './lib/tsc' is not defined by
"exports" in typescript/package.json          (vue-tsc 3.3.11)
Error: typescript-eslint does not support TS 7.0.
```

`vue-tsc` résout `typescript/lib/tsc`, sous-chemin que TS 7 n'exporte plus, et
`typescript-eslint` refuse explicitement la 7.0 ; typecheck, lint et les deux
builds tombent. **Déclencheur :** ces deux paquets annoncent la prise en charge
de TS 7.

**`@quasar/app-vite` 2 → 3** ✅ **fait le 30/09/2026** (commit `85ff0bf`, vitrine et admin ; `#q-app`, alias `@/`, `import.meta.env.QUASAR_*`, SSR réécrit, `frontend/src-ssr/package.json`). Texte historique : la v3 supprime l'alias `#q-app`, que la v2
injecte dans la configuration du bundler (`lib/quasar-config-file.js:317`), et
retire l'export `./wrappers`. Le build s'arrête net :

```
[RESOLVE_ERROR] Could not resolve '#q-app/wrappers' in quasar.config.ts
```

L'alias est utilisé dans **une dizaine d'endroits** — les deux `quasar.config.ts`,
les boots, le router, les stores, et la couche SSR (`declare module '#q-app'`,
type `RenderError`). `defineConfig` et consorts existent toujours en v3, mais à
la racine du paquet. La migration est donc mécanique mais large, et se ferait en
déduisant le comportement de la v3 depuis son code source. À reprendre avec la
documentation de migration officielle sous les yeux.

**`express` 4 → 5** — inutile en l'état, et surtout **trompeur**. Quasar génère
son propre `dist/ssr/package.json` et y recopie sa propre dépendance
(`lib/modes/ssr/ssr-builder.js:118` → `express: cliPkg.dependencies.express`),
soit `^4.0.0`. Vérifié en démarrant le conteneur SSR construit : il tourne bien
en **express 4.22.2** alors que `frontend/package.json` déclarait la 5. Monter
express côté source ne change donc que le typage et le dev local, pas le runtime
déployé — ça ferait croire à une mise à jour qui n'a pas lieu. Cette montée
n'aura de sens qu'une fois `@quasar/app-vite` en v3, si elle y passe à express 5.

À noter au passage : `@types/express` est en **5** alors que le runtime est en
**4**. Ça typecheck parce que la couche SSR n'utilise que des API basiques, mais
les types décrivent une API qui n'est pas celle qui s'exécute.

### Surveillance des dépendances — ce qui reste à câbler 🔲 (28/08/2026)

Le chantier dépendances du 27–28/08 a fermé **35 vulnérabilités** (23 hautes en
JavaScript, 12 paquets côté Python) et posé un
[`dependabot.yml`](.github/dependabot.yml) pour quatre écosystèmes. Ce qui reste
tient en quatre points, dont le premier n'est pas du code.

**① Activer les *Dependabot security updates* — sur le dépôt AMONT.** Le
`dependabot.yml` ne pilote que les mises à jour de version, à cadence
hebdomadaire. Les *security updates* réagissent à la publication d'un avis,
immédiatement, et ne montent que le minimum. C'est le réglage qui manquait
quand les 35 vulnérabilités ont dormi sans que rien ne les signale.

⚠️ Le réglage est à faire sur **`Natimai-Solutions/fastapi-ecommerce`**
(`Settings → Code security`, ou directement `.../settings/security_analysis`),
pas sur le fork `jburckel/fastapi-ecommerce` : les PR Dependabot proviennent de
branches `Natimai-Solutions/dependabot/*`, et Dependabot est désactivé par
défaut sur un fork. Penser aussi à *Grouped security updates*, qui évite
l'avalanche de PR.

**② Les majeures de Node sont redevenues un arbitrage manuel.** Dependabot
proposait node 25 — une ligne « Current » au support court, les LTS étant les
majeures **paires**. Il n'y a pas moyen de le lui apprendre, d'où la règle
d'exclusion posée dans `dependabot.yml`. Contrepartie : **la prochaine LTS (26,
attendue fin 2026) ne sera pas proposée non plus** — il faudra y penser. Les
images python et nginx gardent leurs majeures, elles n'ont pas cette
distinction.

**③ Onze dépendances Python sont déclarées sans borne haute.** `sentry-sdk`,
`aiohttp`, `boto3`, `weasyprint`, `arq`, `clamd`, `pyyaml`, plus l'outillage.
Aucune n'est en conflit aujourd'hui, mais c'est exactement ce qui a fait échouer
Dependabot sur redis : notre `redis>=5.0.0` sans plafond laissait viser la 8
alors qu'arq exige `<6`. Poser des bornes hautes partout protège des surprises
mais fige aussi les mises à jour — **c'est un choix de politique à trancher**,
pas une correction évidente.

**④ Python 3.14.** ✅ **Fait le 30/09/2026** (commit `7d13bf3` : image `python:3.14-slim`, uvloop 0.22.1). ⚠️ Reste un écart : la **CI teste en Python 3.12** ([ci.yml](.github/workflows/ci.yml) l.66) et en **Node 22** contre `node:24` dans les Dockerfiles — à aligner (R6, point 6). Texte historique : l'image est passée en 3.13 ; la 3.14 existe et Dependabot la proposera.

### Autres points différés

- **`session.execute()` dans [order_number.py](backend/app/features/order/services/order_number.py)** 🔲 — sqlmodel 0.0.39 suggère `session.exec()`. L'usage y est pourtant légitime (une séquence SQL brute `nextval`, pas un modèle) ; laissé tel quel pour ne pas retoucher l'allocation des numéros de commande au détour d'une montée de version. À trancher si l'avertissement devient une erreur.
- **Longueur minimale de `SECRET_KEY`** 🔲 — `pyjwt` avertit désormais sous 32 octets (HMAC/SHA-256). [config.py](backend/app/core/config.py) vérifie que la valeur n'est pas le placeholder, mais pas sa longueur : une clé courte passe en production sans un mot. Un garde-fou serait cohérent avec ceux déjà en place.
- **Troncature bcrypt à 72 octets** 🔲 — héritée de passlib et **conservée volontairement** lors de son retrait (28/08), sans quoi les comptes concernés auraient été enfermés dehors. Conséquence assumée et testée : deux mots de passe partageant leurs 72 premiers octets sont équivalents. La corriger (pré-hachage SHA-256 avant bcrypt) changerait **toutes** les empreintes et imposerait une réinitialisation générale — donc seulement dans le cadre d'une opération prévue pour ça.
- **Seuil de couverture `fail_under`** ✅ — relevé de 60 à **68** le 04/09/2026 (Q3) après mesure sur `main` fusionné : 71 % avant les tests Q3, 73 % après. Jamais à baisser pour faire passer une PR ; à remonter à nouveau quand la mesure le permet.
