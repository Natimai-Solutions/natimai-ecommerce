# Chantier — personnalisation de l'accueil et messagerie client

Document de travail du 18/11/2026, relu contre le code le même jour. Rien
n'est livré : ce document sert à **décider** puis à découper. Un lot livré
sort d'ici et du plan de travail ; git garde l'historique.

Deux sujets :

1. **Accueil de la vitrine** : état des lieux, recommandations, architecture
   proposée (§1 à §3).
2. **Messagerie** entre un client et la boutique (service client, service
   commercial), sur le modèle de FenuaPro et de Natimai Paie (§4 à §9).

Les décisions attendues sont au §10, le découpage en lots au §11. Trois
défauts du code actuel, trouvés pendant la relecture, sont au §12 et inscrits
au plan de travail : ils se corrigent indépendamment de ce chantier.

---

## 1. Accueil — ce qui existe

**Vitrine** (`frontend/src/pages/IndexPage.vue`, store `frontend/src/stores/home.ts`),
dans cet ordre fixe :

| Section | Source | Réglable dans l'admin ? |
|---|---|---|
| Héros (titre, texte, bouton, image) | `homepage_blocks`, `kind = hero`, un seul publié par période (409 `homepage.hero.conflict`) | Oui, *Accueil du site* |
| Bannières | `homepage_blocks`, `kind = banner`, triées par `position` | Oui |
| Catégories (8 tuiles) | `GET /category`, choix **automatique** : premier niveau, celles qui ont une image d'abord, puis l'alphabet (`frontend/src/utils/categories.ts`) | Non (seulement l'image de la catégorie) |
| « Nos coups de cœur » (8) | `GET /product/featured` : `is_featured`, `featured_position`, `featured_until` | Indirectement, produit par produit (`ProductFormDialog.vue`) |
| « Les plus consultés » (8, 30 jours) | `GET /product/popular` (`product_view_daily`), vedettes retirées | Non |
| Bandeau du prochain départ | `NextDepartureBanner`, dans `q-page-container`, **sous** l'en-tête, sur toutes les pages (`MainLayout.vue:266`), affiché s'il existe un départ | Non (dérivé des départs) |

Socle déjà en place, à réutiliser :

- blocs datés (`starts_at` / `ends_at`), publiés ou non, traduits
  (`translations`, `HOMEPAGE_BLOCK_FIELDS`, R9 / T3), image de la médiathèque
  (`media_id`, WebP en plusieurs largeurs, `srcset`) ;
- contrôle des liens (`/chemin` ou `https://`, jamais `javascript:` ni `//`) ;
- rendu SSR via `onServerPrefetch` + store Pinia (pas de refetch à
  l'hydratation), chaque section échoue seule (U8) ;
- SEO : `useMeta` émet déjà canonical, `og:image` (l'image du héros) et les
  JSON-LD `WebSite` (avec `SearchAction` vers `/catalogue?q=`) et
  `Organization` minimal (`IndexPage.vue:208-248`) ; titre et description
  viennent de l'i18n de la vitrine ;
- écran admin `admin-frontend/src/pages/HomepagePage.vue` (liste par type,
  monter / descendre, dialogue d'édition, statut publié / programmé / expiré).
  Monter / descendre envoie aujourd'hui **un PUT complet par bloc** en
  parallèle (`HomepagePage.vue:609-617`) : un échec laisse l'ordre à moitié
  appliqué.

**Ce qui limite aujourd'hui** :

- l'ordre et la présence des sections sont **codés en dur** : impossible de
  masquer « Les plus consultés », de mettre les catégories avant les
  bannières, ou d'ajouter une deuxième sélection de produits ;
- les titres des sections (« Nos coups de cœur »…) viennent des fichiers
  i18n de la vitrine, pas de l'admin ;
- les catégories de l'accueil ne se **choisissent** pas ;
- une seule sélection manuelle de produits (les vedettes), réglée fiche par
  fiche, sans vue d'ensemble ni ordre visible ;
- rien pour la réassurance (livraison dans les îles, paiement sécurisé,
  départs groupés), les marques, une promotion en cours, un texte libre ;
- aucun ciblage : un client professionnel connecté voit le même accueil
  qu'un visiteur, **y compris les prix** (défaut, §12.1) ;
- pas d'aperçu avant publication ; titre et description SEO non réglables.

---

## 2. Accueil — recommandations

Classées par rapport valeur / effort. Les trois premières font l'essentiel
de la demande « personnaliser l'accueil ».

### R1. Sections ordonnables et masquables — **à faire en premier** (M)

Chaque section de l'accueil devient une ligne ordonnée, activable, avec un
titre et un sous-titre saisis dans l'admin (traduits). Le héros reste en
tête (LCP, une seule image `fetchpriority="high"`). L'admin glisse les
sections dans l'ordre voulu, en masque, en duplique certaines. L'ordre
s'enregistre en **un seul appel** (§3).

### R2. Sélections de produits nommées (M)

Remplacer l'unique « coups de cœur » par autant de **sélections** que voulu,
chacune avec son titre, son nombre d'articles et sa source :

- **manuelle** : liste ordonnée de produits choisis dans un sélecteur (avec
  recherche par nom / SKU). Les vedettes actuelles deviennent la première
  sélection manuelle, reprise par migration ;
- **par règle** : catégorie (sous-catégories comprises), fabricant (voir
  R6), « nouveautés » (date d'arrivée), « en promotion », « plus consultés »
  (l'existant), « meilleures ventes » ;
- tri et plafond (4 à 24), affichage carrousel ou grille.

Précisions de mise en œuvre :

- « **En promotion** » se résout par jointure sur les remises actives
  (`Discount` de type promotion, cible article ou catégorie avec ses
  sous-catégories, dates vérifiées), pas sur une colonne de prix barré : le
  prix barré (`regular_price`, `promotion_name`) est **calculé** client par
  client dans `group_pricing`. Conséquence acceptée : pour un client dont le
  prix de groupe est déjà plus bas, une carte de la sélection peut ne
  montrer aucune remise.
- Les tris par prix suivent le **prix de référence** (`sale_price_cached`),
  comme la recherche, pas le prix du groupe.
- Les produits non publiables (taux de douane non résolu, hors stock masqué)
  restent exclus par le même filtre que le catalogue : une sélection ne
  montre jamais un produit que la recherche cache.

### R3. Catégories choisies (S)

Section « Catégories » en mode **automatique** (comportement actuel) ou
**manuel** : liste ordonnée de catégories, avec une image et un libellé
propres à l'accueil si voulu (sinon ceux de la catégorie).

### R4. Bandeau d'annonce (S)

Texte court + lien, daté, traduit, fermable par le visiteur (mémorisé en
`localStorage` sous try/catch, clé = id + version). Usage : « Départ bateau
le 3/12, commandez avant le 28/11 », soldes, fermeture exceptionnelle.

Emplacement : `NextDepartureBanner` occupe déjà une bande sous l'en-tête.
Trois options (§10.1) : l'annonce remplace la bande du départ pendant sa
période, **dans le même emplacement à hauteur réservée** (recommandé : une
seule bande, un seul niveau) ; ou les deux s'empilent ; ou l'annonce passe
au-dessus de l'en-tête — l'en-tête est fixe (`view="hHh"`), elle doit alors
vivre dans `q-header` et le décalage se vérifie au rendu SSR.

### R5. Réassurance (S)

Bande de 3 à 4 pictogrammes + texte court (« Livraison dans les îles »,
« Paiement sécurisé », « Prix douane comprise », « Un conseiller vous
répond » → messagerie, §6). Icônes prises dans une **liste fermée** des
icônes de la vitrine (pas de saisie d'URL d'icône).

### R6. Fabricants / marques (S, après une décision)

Bande de logos choisis (ordre manuel), chaque logo menant au catalogue
filtré. Prérequis à trancher (§10.9) : aujourd'hui **aucun produit n'est
rattaché à une marque** — le catalogue filtre et calcule ses facettes sur la
chaîne libre `Product.manufacturer` — et `Brand` n'a qu'un `image_url`
externe, sans lien à la médiathèque (`features/product/models/brand.py`).
Deux voies :

- **légère** : la bande référence des valeurs de `manufacturer` et mène à
  `/catalogue?manufacturer=…` ; le logo est un `media_id` posé ligne par
  ligne dans la section ;
- **complète** : `Product.brand_id` (reprise depuis `manufacturer`, avec
  normalisation des variantes de casse) et `Brand.media_id`.

### R7. Bloc de contenu libre (S)

Texte riche + image facultative, gauche / droite : présentation de la
boutique, extrait de « Comment ça marche », texte SEO de bas de page. Rendu
par le même `DOMPurify.sanitize` que `DbContentPage.vue` (le serveur ne
nettoie pas `body_html` aujourd'hui) ; tout autre consommateur (aperçu
admin) le nettoie aussi.

### R8. Ciblage par audience (M)

Chaque section porte une **audience** : tous, visiteurs, clients connectés,
un ou plusieurs **groupes tarifaires** (`price_group_id` : les pros voient
« Commander en volume / Demander un devis », les particuliers une
promotion). Plus une **langue** facultative pour un bloc qui n'a de sens
qu'en une langue.

Impact SSR : le rendu serveur est toujours **anonyme** (la session n'est
restaurée que dans le navigateur, `boot/auth.ts`). Règle proposée : le
serveur rend la version **visiteur** ; les sections ciblées « connecté » /
« groupe » et les **prix du client** arrivent **après hydratation** par une
seconde requête authentifiée, dans un emplacement de hauteur réservée (pas
de saut de mise en page), rechargée à la connexion **et** à la déconnexion.

### R9. Sections personnelles (M, après R8)

Pour un client connecté uniquement, chargées côté navigateur, jamais rendues
en SSR ni mises en cache :

- « **Vus récemment** » : **aucune donnée par client n'existe** —
  `product_view_daily` ne tient que des compteurs anonymes par produit et
  par jour. V1 recommandée : historique **local au navigateur**
  (`localStorage`, N derniers identifiants, sous try/catch), sans serveur ni
  donnée personnelle. Sinon une table par client, avec purge, export et
  effacement RGPD ;
- « **Racheter** » : articles des dernières commandes ;
- « **Votre liste de souhaits** » (tables `wishlists` / `wishlist_items`) ;
- « **Votre commande en cours** » : statut + départ.

### R10. Aperçu et programmation (S à M)

- **Aperçu** depuis l'admin : la vitrine ouverte avec un jeton d'aperçu qui
  montre les brouillons et accepte une date simulée (« voir l'accueil du
  1/12 ») et une audience simulée (visiteur, groupe X).
  - Brouillons, `preview_at` et `preview_audience` ne sont pris en compte
    qu'avec un jeton valide, **vérifié côté serveur** ; sans jeton, ils sont
    ignorés (réponse visiteur normale).
  - Jeton d'un type dédié (`homepage_preview`, refusé comme jeton d'accès et
    réciproquement : `api/deps.py` ne contrôle que `type == "access"`), qui
    porte le `security_stamp` d'un superuser encore actif, 15 min.
  - Une réponse d'aperçu ne lit ni n'écrit le cache (§3), répond
    `Cache-Control: no-store`, et le jeton n'apparaît pas dans l'état SSR
    sérialisé.
- Calendrier : vue des sections programmées sur les 30 prochains jours.

### R11. SEO de l'accueil (S)

Les JSON-LD `WebSite` / `SearchAction` et `Organization` existent déjà. Reste :
titre et description de l'accueil saisis dans l'admin (traduits), à la place
de `home.meta_title` / `home.meta_description` ; un `Organization` plus
complet (logo, `sameAs`, `contactPoint` vers la messagerie).

### À éviter

- **Carrousel de héros** : mauvais pour le LCP et peu cliqué ; garder un
  seul héros par période, éventuellement un héros par **audience** (R8).
- **Constructeur de page libre** (colonnes, marges, couleurs saisies) : la
  vitrine perdrait sa cohérence (dark mode, mobile 390 px) ; des types de
  sections fermés, chacun bien dessiné, suffisent.
- Tests A/B : pas assez de trafic pour conclure.

---

## 3. Accueil — architecture proposée

Généraliser `homepage_blocks` plutôt que créer une seconde table : le socle
(dates, publication, traductions, médias, écran admin) est déjà là.

```
homepage_blocks
  kind            hero | banner | announcement | category_grid
                  | product_collection | manufacturer_strip | reassurance | rich_text
                  | builtin (featured, popular… = sections d'aujourd'hui)
  title, subtitle, cta_label, cta_link, media_id, image_url, alt   (existants)
  position, is_published, starts_at, ends_at, translations         (existants)
  config          JSONB — validé par un schéma Pydantic par `kind`
  audience        JSONB — {"scope": "all|guest|customer", "price_group_ids": [...], "locales": [...]}
  is_active                                                        (existant)

homepage_block_items          (lignes ordonnées des sections manuelles)
  block_id, position, product_id | category_id | manufacturer, label?, media_id?
```

- `config` validé **par type** (union discriminée) : une règle de sélection
  ne référence que des champs déclarés (`category_id`, `manufacturer`,
  `sort ∈ {newest, popular, price_asc…}`), jamais un filtre libre venu du
  client. Un **seul validateur de lien** pour `cta_link`, les liens de
  `config` et des items ; il refuse aussi `/\…` (lu comme relatif au
  protocole par les navigateurs, accepté aujourd'hui) et les caractères de
  contrôle.
- `GET /homepage` renvoie **les sections ordonnées et résolues** (produits,
  catégories compris) en une requête, au lieu des quatre appels actuels du
  store. Il **ne lit aucune identité** (pas de `CurrentUserOptional`) et
  tarife au **groupe par défaut**.
- `GET /homepage/personal` (authentifié, `Cache-Control: no-store`, jamais
  en cache) renvoie les sections ciblées et personnelles et les **prix du
  client** pour les cartes de l'accueil (R8 / R9).
- `PUT /admin/homepage-blocks/order` : liste ordonnée des ids, positions
  renumérotées en **une transaction** sans revalider chaque bloc ; 409 si
  la liste ne correspond plus aux blocs actifs. Le glisser-déposer l'appelle
  une fois ; le tri de `GET /admin/homepage-blocks` passe à `position` seul.
- **Migration de reprise** : les sections d'aujourd'hui deviennent des
  lignes `builtin` dans l'ordre actuel ; les produits `is_featured` une
  sélection manuelle. Rien ne change à l'écran au déploiement.
- **Cache** : l'outil est à écrire (`core/cache.py` n'ouvre qu'une
  connexion). Clé `homepage:v{n}:{locale}` sur le client Redis partagé,
  **fail-open** (ce n'est pas une barrière), écrite seulement pour une
  requête sans aperçu. L'invalidation à l'écriture admin ne couvre que la
  **structure** : prix, promotions datées, stock, `featured_until` et
  classement des plus consultés changent sans écriture admin. Donc soit un
  TTL court écrit noir sur blanc (60 s), soit ne mettre en cache que la
  structure (sections et ids) et résoudre les produits à chaque requête.
  Les URL d'images en cache ne dépendent pas de l'en-tête `Host` (elles en
  dépendent quand `MEDIA_PUBLIC_BASE_URL` est vide) : exiger ce réglage hors
  local, ou mettre l'origine dans la clé.
- `_refuse_second_live_hero` s'étend : un héros par période **et par
  audience**.
- Codes d'erreur : nouveaux codes (`homepage.config`, `homepage.audience`,
  `homepage.item_not_found`, `homepage.order_conflict`…) dans **les deux**
  catalogues `shared/utils/src/apiErrors/{en,fr}.json`. Réécrire aussi
  `homepage.kind`, dont le texte liste en dur « hero or banner » : texte
  générique ou `{kind}` / `{kinds}` dans `details`, et le message de
  `homepage.py` aligné mot pour mot sur le catalogue (il diffère déjà).
- Admin : l'écran *Accueil du site* devient une liste unique ordonnable, un
  dialogue par type de section, un sélecteur de produits / catégories, et
  le bouton **Aperçu** (R10).

Tests : intégration sur base réelle pour la résolution des sélections
(produit masqué exclu, promotion par catégorie), l'audience (un visiteur ne
reçoit jamais une section de groupe), **un client d'un groupe qui appelle
`/homepage` avec son jeton reçoit exactement la réponse visiteur**, un
brouillon demandé en aperçu n'apparaît pas dans la réponse visiteur
suivante, la migration de reprise (upgrade / downgrade) ; Vitest sur le
rendu de chaque type, les deux thèmes, le rechargement des prix à la
connexion et à la déconnexion.

---

## 4. Messagerie — besoin

Un client doit pouvoir **écrire facilement** à la boutique et retrouver la
réponse au même endroit, en distinguant :

- **Service client** : une commande, une livraison, un paiement, un retour,
  un produit reçu ;
- **Service commercial** : un devis, un achat en volume, une demande
  professionnelle, une question avant achat.

Ce qui existe :

- **Demande de devis** (`quote_requests`) : le retour **formel** existe —
  la boutique émet un devis chiffré (numéro `DEV-`, validité, message au
  client, PDF par e-mail ; `features/cart/services/quote.py`,
  `admin_quote_requests.py`), que le client voit dans *Mon compte → Devis*
  (`AccountQuotes.vue`) et accepte, ce qui le convertit. Ce qui manque,
  c'est **l'échange libre** avant et autour du devis ; `admin_comment` reste
  interne.
- **Demande de changement de groupe** (`group_upgrade_request`) : son
  `admin_comment` est, lui, **le motif montré au client** dans *Mon groupe*
  (`AccountGroup.vue:81`).
- **Adresses** : `email_support` (affichée dans les e-mails, destinataire
  des demandes de devis et des notifications de paiement), `email_contact`
  (« destinataire du formulaire de contact », **lue nulle part** : il n'y a
  pas de formulaire, M8 de l'audit fonctionnel) et `legal_support_email`
  (CGV). Il faudra dire laquelle la page contact affiche.
- **Notifications en application** : un modèle `notifications` /
  `user_notifications` (`features/user/models/notification.py`, types
  fermés, `is_read` / `read_at`) existe **sans route ni écran**, seulement
  dans l'export RGPD. À trancher (§10.10) : il porte le badge de non-lus de
  la messagerie, ou il est retiré — pas deux mécanismes.
- **Modules activables** (`features/system/modules.py`, `module_required`
  → 404 sur un module coupé, `SECTION_MODULES` dans `MyAccountPage.vue`) :
  la messagerie sera un module.

Les échanges libres partent donc aujourd'hui en e-mail et sortent de
l'outil.

---

## 5. Ce que font FenuaPro et Paie

| | FenuaPro (`features/contact`) | Natimai Paie (`features/support`) |
|---|---|---|
| Fil | `contact` + `contact_message` ; un fil de support **par utilisateur**, rattachable à un contexte (`context_type` / `context_id`) | `support_conversation` + `support_message`, un **canal** par conversation (`support`, `payroll`, `accounting`, `cabinet`) |
| Statuts | `NEW` / `PROGRESS` / `COMPLETE` | `open` (attend l'éditeur) / `pending` (attend le client) / `resolved` |
| Lu / non lu | un booléen `is_read` par message + notifications génériques | horodatages par côté (`customer_read_at`, `staff_read_at`) |
| Temps réel | WebSocket (ticket Redis à usage unique, pub/sub), badge en sondage 30 s | **aucun** : sondage 4 s sur le fil ouvert, 30 s sur la file, 60 s pour le badge |
| E-mail | digest différé : non lu depuis 10 min → e-mail **sans le contenu** ; préférence `message` | idem (10 min, une fois par vague, sans contenu ni sujet), conversations actives depuis 7 j seulement |
| Pièces jointes | 10 Mo, ClamAV en tâche arq, S3, servies seulement une fois saines | PDF / PNG / JPEG, 5 Mo, type détecté sur les octets, 20 par fil |
| Équipe | « À traiter / Mes conversations / Traitées / Toutes », prise en charge par UPDATE conditionnel (409 `already_claimed`, `force`), 1ʳᵉ réponse = prise en charge, libération auto après 3 j, transfert, **support prioritaire** calculé à la lecture | mêmes onglets + « En attente », agents limités à des canaux, présence (`last_seen_at`), file des demandes du formulaire public |
| Conservation | — | échéance par canal depuis le dernier message, préavis par e-mail, « garder un an de plus », export texte du fil, purge des seules conversations réglées |
| Formulaire public | `POST /contact`, 10/h par IP ; un connecté qui a déjà un fil y voit son message ajouté | `POST /public/contact`, Turnstile, pot de miel, 5/h par IP et 200/h au total, réponse **toujours 202** |
| Manques communs | pas de réponses types, pas de notes internes, pas de vrai SLA | idem, pas de canal commercial |

Pièges déjà payés ailleurs, à ne pas refaire :

- **WebSocket** : jamais de `SessionDep` sur la route (4 onglets ont vidé le
  pool de FenuaPro) ; tests sur la **même boucle** que l'app (le
  `TestClient` synchrone bloque) ; client Redis **dédié** sans
  `socket_timeout` pour le pub/sub ; revalider la session pendant la
  connexion.
- Un PATCH de message sans liste blanche de champs a permis de réécrire
  `file_id` / `is_read` (FenuaPro SEC-57) : le serveur pose tout ce qui
  n'est pas le texte.
- **Champs de rattachement non gardés** (`context_id`…) : récidivé plusieurs
  fois dans FenuaPro ; garde à la création, 404 sur ce qui n'est pas à soi.
- Une préférence de notification doit être **lue** par l'envoi. Le piège
  existe **déjà ici** : `notification_email_enabled` (interrupteur
  « commandes » de `AccountPreferences.vue`) n'est lu par aucun envoi
  (§12.3).
- **Mailer de ce dépôt** : à l'inverse de FenuaPro (où une mise en file
  sans `commit` n'envoie rien), `send_email` / `queue_email`
  (`features/notification/mailer.py`) valident leur journal `EmailLog` dans
  **leur propre transaction** et envoient aussitôt, sans clé de
  dédoublonnage : l'e-mail part même si la transaction de l'appelant est
  annulée ensuite. On met en file **après** le commit de l'état qui le
  déclenche.
- Le texte d'un tiers dans un gabarit HTML passe par l'échappement ; les
  gabarits `.subject.txt` / `.txt` ne sont pas échappés
  (`email_renderer.py`).

---

## 6. Messagerie — proposition fonctionnelle

### Côté client (vitrine)

- **Point d'entrée visible partout** : un bouton « Nous écrire » dans
  l'en-tête (icône + badge de non-lus pour un connecté) et en pied de page,
  plus des **raccourcis contextuels** qui ouvrent le fil pré-rempli :
  - fiche produit → « Une question sur ce produit ? » (canal *commercial*,
    produit joint) ;
  - *Mes commandes* → « Un problème avec cette commande ? » (canal
    *client*, commande jointe) ;
  - panier → « Demander un devis » (canal *commercial*, panier joint ; exige
    aussi le module `quotes`) ;
  - *Mon groupe* (`AccountGroup.vue`) → « Parler à un commercial ».
- **Onglet « Messages » dans *Mon compte*** (`MyAccountPage.vue`, clé
  `?tab=messages`) : liste des conversations (sujet, canal, dernier
  message, statut, non lu), fil de discussion, envoi de texte et de pièces
  jointes, « Ma question est réglée », « Télécharger la conversation »
  (texte), « Garder un an de plus » (§7, conservation).
- **Visiteur non connecté** : page **`/contact`** (comble M8 de l'audit)
  avec le choix « Service client » / « Service commercial », nom, e-mail,
  téléphone et société facultatifs, sujet, message ; Turnstile si configuré
  + pot de miel + limites de fréquence.
  - **Aucun e-mail n'est envoyé à l'adresse saisie** (ni accusé de
    réception, ni copie) : le 202 est la seule confirmation, sinon la
    boutique devient un relais de spam vers une adresse non prouvée (même
    raison que S8, paniers invités). Le premier e-mail au visiteur est la
    **réponse d'un membre de l'équipe**, déclenchée à la main ; son sujet
    vient du gabarit (« Votre demande C-… »), jamais du sujet saisi, et il
    ne cite pas le message du visiteur.
  - **Rattachement à un compte** : écrire `customer_id`, jamais lire « par
    e-mail ». Seulement pour un compte `is_verified AND NOT is_guest`, et
    seulement au moment où l'adresse est **prouvée** (code de l'inscription,
    reprise d'un compte invité, lien de réinitialisation). Une session
    invitée (`POST /signup/guest`) ne prouve rien (§12.2).
- Horaires et délai de réponse affichés (« réponse sous 1 jour ouvré, du
  lundi au vendredi, 8 h – 17 h, heure de Tahiti »), réglables.
- **Module `messaging`** (Admin → Modules) : coupé, l'onglet, le bouton de
  l'en-tête et les raccourcis disparaissent (`useShopModulesStore().isOn`).

### Côté boutique (admin)

- Écran **Messagerie** : onglets « À traiter », « Mes conversations », « En
  attente du client », « Réglées », « Toutes » ; filtre par canal ;
  recherche (numéro de commande, nom, e-mail) ; pagination **serveur** ;
  compteur dans le menu.
- Dans le fil : panneau client (groupe tarifaire, dernières commandes,
  avoir) — **le même composant** que la « Fiche client » du §4 du plan, à
  construire une fois — et **objet rattaché** (commande, produit, panier,
  demande de devis) cliquable vers sa fiche admin.
- **Prise en charge et clôture** :
  - prise par UPDATE conditionnel (409, `force`) ; la **première réponse**
    prend en charge par le même UPDATE `WHERE assigned_to_id IS NULL`, sans
    jamais écraser une prise concurrente ; un dépôt de pièce jointe aussi ;
  - libérer, régler ou transférer une conversation tenue par un autre exige
    `force` (tout membre de l'équipe est superuser : « titulaire ou
    superuser » n'exclurait personne) ;
  - régler une conversation libre la rattache à qui la règle ; le titulaire
    est **conservé** à la résolution, par l'équipe comme par le client ;
    régler une conversation réglée ne fait rien ;
  - transfert vers un superuser **actif** seulement (400
    `messaging.invalid_assignee`) ;
  - un message du client sur une conversation réglée la **rouvre sans
    titulaire** et la renvoie dans « À traiter » (Paie et FenuaPro font de
    même : le titulaire peut être absent) ; une réponse de l'équipe ne
    rouvre jamais ;
  - **libération automatique** : seulement les conversations `open`, tenues
    depuis plus de N jours, dont le titulaire n'a pas répondu depuis le
    dernier message du client ; elle remet `staff_notified_at` à NULL pour
    prévenir de nouveau.
- **Notes internes** (invisibles du client) et **réponses types** traduites
  (fr / en, variables `{prenom}`, `{commande}`) — les deux projets n'en ont
  pas, c'est le premier manque relevé côté équipe. Ces notes portent sur la
  conversation ; ce ne sont pas les notes de commande du plan (§4,
  historique de la commande).
- **Option priorité** (§10.11) : pastille « prioritaire » et tri en tête de
  « À traiter » pour les clients d'un groupe tarifaire marqué prioritaire,
  calculée **à la lecture** en une requête par page (modèle FenuaPro), sans
  colonne écrite : un changement de groupe se prend en compte de lui-même.
- **Canaux** affectables aux membres de l'équipe. Tant que l'admin n'a que
  `is_superuser` (rôles fins = §4 du plan), tout superuser voit tout ; la
  table d'agents sert seulement au routage des notifications. `staff_read_at`
  est **commun à l'équipe** : une conversation lue par un membre l'est pour
  tous (choix assumé, comme Paie).
- Depuis une conversation commerciale rattachée à une demande de devis :
  **« Émettre le devis »** ouvre la fiche admin de la demande, où l'émission
  (`/issue`) existe déjà ; sans demande, il attend le devis créé par l'admin
  (M5 de l'audit). Depuis une conversation client : **« Ouvrir un retour »**
  (futur RMA, §3 du plan).

### Notifications

- **Client connecté** : e-mail « Vous avez une réponse » **sans le
  contenu**, si le message reste non lu 10 min, une fois par vague ; lien
  vers le fil. Langue : `user_preferences.locale` au moment de l'envoi.
  Préférence : nouvelle clé `notification_messages` (colonne de
  `user_preferences`, migration, interrupteur dans `AccountPreferences.vue`,
  i18n fr / en), **lue** par l'envoi et testée (envoi coupé quand elle est à
  false).
- **Visiteur sans compte** : la réponse part **avec** le contenu (il n'a pas
  d'autre accès), ou avec un lien vers le fil (§10.4). Cet e-mail part en
  `resendable=False` quand il porte un lien (c'est un secret, comme les
  liens de réinitialisation et d'invitation) ; son corps reste 90 jours dans
  `email_log` (`EMAIL_BODY_DAYS`) — à dire dans la politique de
  confidentialité ou à ne pas journaliser.
- **Équipe** : e-mail au titulaire, sinon aux membres du canal, sinon à
  l'adresse du canal (*client* → `email_support`, *commercial* →
  `email_contact`, enfin utilisée), sinon aux superusers ; jamais pour une
  conversation réglée. Digest du matin (compteurs seuls). Le tout dans la
  **langue de l'opérateur** (`operator_messages.py`, `operator_locale`) ;
  facultatif : alerte Slack (fournisseur déjà présent).
- **Règles de vague** (Paie) : ne lire que les conversations dont le dernier
  message a moins de 7 jours ; une nouvelle vague = un `last_*_message_at`
  postérieur à la fois à `*_read_at` et à `*_notified_at`.
- **Demandes de devis** : une demande **ouvre une conversation**
  commerciale rattachée à la `quote_request`, sans la remplacer
  (`QuoteRequestStatus`, filet `EMAIL_FAILED`, `/issue`, `…/accept`
  inchangés) ; `admin_comment` devient une note interne. Ferme le volet
  « devis » de Z18 (accusé de réception et réponse).
- **Demandes de groupe** (si voulu, §10.5) : `admin_comment` y est déjà la
  réponse montrée au client ; il devient un **message visible** de la
  conversation, jamais une note, et reste affiché dans *Mon groupe*. Le
  message de décision tient lieu de l'e-mail de décision (M14, volet
  groupe). Le volet « retard de départ » de Z18 reste à M4 de l'audit.

---

## 7. Messagerie — proposition technique

### Modèle (`backend/app/features/messaging/`)

```
conversations
  id, number (C-2026-00042, lisible au téléphone ; jamais un moyen d'accès)
  channel           customer_service | sales           (liste fermée)
  status            open | pending | resolved
  subject
  customer_id       FK users, NULL pour un visiteur
  guest_name, guest_email, guest_phone, guest_company, guest_locale   (visiteur seulement)
  guest_token_hash, guest_token_expires_at             (si lien visiteur, §10.4)
  context_type      order | product | cart | quote_request | group_request | NULL
  context_id        UUID
  assigned_to_id, assigned_at
  last_message_at, last_customer_message_at, last_staff_message_at
  customer_read_at, staff_read_at
  customer_notified_at, staff_notified_at
  resolved_at, retain_until, deletion_notice_at
  created_at, created_by_id …                          (socle)

conversation_messages
  id, conversation_id, author_id (NULL = visiteur), side customer | staff
  kind              message | note | event   (note = interne ; event = « pris en charge par… »)
  body              texte brut, 4 000 caractères max
  created_at

conversation_attachments
  id, message_id, filename, mime, size, sha256, object_key, av_scanned, av_clean

messaging_agents     (routage des notifications, pas des droits)
  user_id, channels[], is_active, last_seen_at

canned_replies
  id, channel?, title, body, translations, position
```

- **Lu / non lu** par horodatage de côté (modèle Paie) : plus simple et juste
  qu'un booléen par message, un seul `UPDATE` pour « marquer lu ».
- **Notes et événements** : seul `kind = message` modifie `status`,
  `resolved_at`, `last_*_message_at`, `*_read_at`, `*_notified_at` et vaut
  prise en charge. Une note ne déclenche jamais l'e-mail « Vous avez une
  réponse ». (Paie fait avancer ces champs pour **tout** message de
  l'équipe : il n'a pas de notes, le cas n'y est pas traité.)
- **Une note et ses pièces jointes sont filtrées de tout chemin client** :
  fil, `?after=`, compteur de non-lus, aperçu dans la liste, export RGPD,
  e-mail, téléchargement d'une pièce par son id.
- `context_type` / `context_id` : **garde à la création** — le client ne
  rattache que **sa** commande, **son** panier, **sa** demande
  (`user_id == current_user.id`, sans réutiliser `_my_quote_or_404` ni
  `check_convertible`, §12.2) ; un produit doit être publié. Sinon 404.
- Langue : `user_preferences.locale` pour un client connecté, `guest_locale`
  pour un visiteur.
- Pas de chiffrement applicatif (pas de DEK ici, contrairement à Paie) ;
  **pas de contenu dans les journaux**.

### Conservation et RGPD

- **Échéance** = `last_message_at` + durée du canal (§10.6) ; `retain_until`
  = prolongation choisie par le client (« Garder un an de plus »), retenue
  si elle est plus tardive. Seules les conversations `resolved` sont
  purgées. Un e-mail de préavis **sans contenu** part 30 jours avant
  (`deletion_notice_at`) ; la suppression attend la fin du préavis. Fils de
  visiteurs jamais réglés (spam compris) : durée courte à part.
- **Purge** : objets des pièces jointes dans le stockage d'abord, puis
  pièces, messages, conversation.
- **Export** (`privacy.py`, qui exclut des champs par leur nom — une note
  est une **ligne**, l'exclusion par nom ne l'arrête pas) : seulement les
  messages `kind = message`, sans `note` ni `event` ni champs d'affectation ;
  pièces jointes en métadonnées (nom, type, taille, date), sans URL.
- **Effacement** : conversations `customer_id = uid` **et** conversations de
  visiteur rattachées par une adresse prouvée ; anonymiser les `guest_*` et
  le texte écrit par le client, supprimer les objets stockés ; pour une
  conversation liée à une commande encore conservée, garder le fil en
  anonymisant l'auteur. Supprimer aussi les lignes `EmailLog` d'un visiteur
  sans compte par adresse (`privacy.py` ne couvre aujourd'hui que les
  comptes).
- Test qui échoue si une table `messaging_*` n'est pas classée dans l'export.

### API

Toutes les routes derrière `Depends(module_required("messaging"))`.

- **Client** (`CurrentUser`) : `GET/POST /me/conversations`,
  `GET /me/conversations/{id}?after=`, `POST …/messages`,
  `POST …/attachments`, `POST …/read`, `POST …/resolve`, `POST …/keep`,
  `GET …/export`, `GET /me/conversations/unread` ; une conversation d'un
  autre client → **404**. Limites : 10 conversations / h, 60 messages /
  10 min par compte.
- **Public** : `POST /contact` (Turnstile via `core/captcha.py`, pot de
  miel, `core/rate_limit.py` par IP et global). **202 identique** que
  l'adresse existe ou non ; la recherche d'un compte et tout rattachement se
  font dans une **tâche arq**, pas dans la requête, pour un temps de réponse
  identique ; aucun e-mail au titulaire du compte. (L'énumération reste
  possible ailleurs : `/signup/send-otp` et `/signup/guest` disent qu'une
  adresse a un compte — hors périmètre.)
- **Lien visiteur** (si retenu, §10.4) : jeton aléatoire
  (`secrets.token_urlsafe(32)`), stocké en condensat SHA-256 sur la
  conversation, expiration (30 j), **remplacé à chaque e-mail de l'équipe**
  (un seul lien valide) et effacé à la résolution. Ce n'est pas un JWT (non
  révocable). Il donne accès à **cette seule** conversation — lecture,
  réponse, pièces jointes saines, jamais les notes, jamais un compte — et
  reste limité en fréquence par conversation et par IP. Le numéro `C-…`
  n'ouvre jamais rien, ni sur le site ni au téléphone.
- **Admin** (`CurrentSuperUser`, 2FA déjà exigée) : `/admin/conversations`
  (onglets, filtres, recherche, pagination serveur), `claim`, `release`,
  `transfer`, `resolve`, `notes`, `canned-replies` (CRUD), `summary`
  (compteurs du menu, sert aussi de présence).
- Codes d'erreur `messaging.*` (dont `messaging.attachment.*`,
  `messaging.already_claimed`, `messaging.invalid_assignee`) dans les deux
  catalogues ; messages API en anglais ; textes de succès dans l'i18n de
  chaque frontend ; messages à l'équipe par `operator_messages.py`.

### Temps réel : commencer par le sondage

**Sondage** comme Paie (fil ouvert : 5 s ; badge : 60 s, suspendu quand
l'onglet est caché), sans WebSocket. Le volume d'une boutique ne le
justifie pas, et le WebSocket de FenuaPro a coûté deux incidents (pool
vidé, CI bloquée). Le passage au WebSocket (ticket Redis + pub/sub, recette
FenuaPro) reste possible si la charge l'exige ; l'API `?after=` est conçue
pour ne pas changer.

### Pièces jointes

`features/attachment` est **lié aux paiements** (`PaymentAttachment`, clés
`payments/{payment_id}/…`, réglages `PAYMENT_ATTACHMENT_*` : 10 Mo,
PDF / JPEG / PNG). À faire :

- réutiliser tels quels `storage/` et `antivirus/` ; extraire de
  `service.py` la vérification par signature (`_MAGIC`,
  `content_matches_mime`) et le scan, paramétrés **par usage** (préfixe,
  liste MIME, taille ; réglages `MESSAGING_ATTACHMENT_*`, 5 Mo) ;
- clé `messaging/{conversation_id}/…`, préfixe vérifié à l'enregistrement
  (comme `attachment.key_mismatch` dans `payments.py`) ; nom de fichier
  hors de la clé et assaini dans `Content-Disposition` (ASCII +
  `filename*`) ;
- WebP : ajouter sa signature (`RIFF….WEBP`) à `_MAGIC`, et **refuser un
  type sans signature connue** (aujourd'hui « no opinion » = accepté) ;
  HEIC (photos d'iPhone) : refus 415 explicite ou conversion (§10.12) ;
- l'URL présignée PUT ne borne pas la taille : supprimer l'objet refusé
  (taille, type) du stockage ;
- téléchargement seulement si `av_scanned and av_clean` (409 scan en
  cours, 403 en quarantaine, comme `admin_payments.py`).

Photos d'un colis abîmé = cas d'usage n° 1 du service client.

### Tâches arq

- `task_messaging_notify` (5 min) : e-mails de non-lus (client, équipe)
  selon les règles de vague ; poser `*_notified_at` et **valider avant**
  d'appeler `queue_email` (qui écrit son journal et envoie de lui-même) ;
- `task_messaging_digest` (matin, heure de Tahiti) : libération des
  conversations tenues sans réponse (règles du §6), digest de l'équipe ;
- `task_messaging_purge` (nuit) : préavis, puis purge (§ conservation) ;
- rattachement des demandes `/contact` à un compte (§ API).

### Garde-fous et tests

- Intégration sur **base réelle** : un client ne lit ni n'écrit dans la
  conversation d'un autre (404), ne rattache pas la commande ou la demande
  d'un autre, ne voit jamais une note (fil, `?after=`, compteur, export,
  pièce jointe par id) ; une note ne change ni le statut ni
  `last_staff_message_at` et ne provoque aucun e-mail au client ; deux
  agents qui prennent la même conversation (409) ; régler une conversation
  libre la rattache à qui la règle ; transfert vers un compte inactif refusé ;
  une tâche annulée après l'étape d'e-mail ne **renvoie** pas l'e-mail au
  passage suivant ; `POST /contact` ne met aucun e-mail en file vers
  `guest_email` et répond pareil pour une adresse connue ou non ; une pièce
  non saine n'est pas téléchargeable ; l'envoi est coupé quand
  `notification_messages` est à false.
- Vitest : fil, badge, deux thèmes, mobile 390 px, module coupé.
- `pnpm gen:types` et migration Alembic (upgrade **et** downgrade).

---

## 8. Ce qu'on prend, ce qu'on laisse

| Repris de | Élément |
|---|---|
| Paie | canaux, statuts à trois états, lu par horodatage, sondage, e-mail différé sans contenu et règles de vague, formulaire public 202 + pot de miel, présence, libération après 3 j, conservation avec préavis / export / prolongation |
| Paie et FenuaPro | réouverture sans titulaire quand le client réécrit, prise par UPDATE conditionnel |
| FenuaPro | rattachement à un contexte (commande, produit…), transfert, liste blanche des champs modifiables, support prioritaire calculé à la lecture (option) |
| Nouveau | canal **commercial**, **notes internes**, **réponses types**, panneau client et objet rattaché dans le fil, demande de devis = conversation rattachée |
| Laissé | WebSocket, réactions emoji, indicateur « en train d'écrire », assistant IA de premier niveau (Paie), quotas payants par canal |

---

## 9. Hors périmètre (pour mémoire)

- Chat en direct avec widget flottant.
- WhatsApp / Messenger / SMS entrants (le SMS sortant est au §3 du plan).
- Réponse au client **par retour d'e-mail** qui revient dans le fil (boîte
  à relever, analyse MIME, anti-spam) : à rouvrir seulement si les clients
  répondent massivement aux e-mails.
- Fermer l'énumération de comptes de `/signup/send-otp` et `/signup/guest`.

---

## 10. Décisions attendues

1. **Bandeau d'annonce et prochain départ** : même emplacement (l'annonce
   remplace le départ pendant sa période, recommandé), empilés, ou annonce
   au-dessus de l'en-tête ?
2. **Ciblage par groupe tarifaire** (R8) : dès le premier lot, ou après ?
3. **Canaux** : *client* et *commercial* seulement, ou aussi *retours* /
   *comptabilité* (factures, avoirs) ?
4. **Visiteur sans compte** : réponse par e-mail seulement (contenu dans
   l'e-mail), ou lien vers le fil pour continuer sur le site ?
5. **Demandes de devis et de groupe** : leur rattacher une conversation
   (devis : `admin_comment` → note interne ; groupe : `admin_comment` →
   message visible) — oui / non, et pour lesquelles ?
6. **Durée de conservation** des conversations réglées, par canal
   (proposition : 3 ans, à valider avec la relecture juridique), et mention
   dans la politique de confidentialité.
7. **Horaires et délai de réponse** affichés : lesquels ?
8. **Qui répond** : tous les superusers, ou des personnes nommées par canal
   (table d'agents) ? Et quelle adresse la page contact affiche-t-elle
   (`email_support`, `email_contact`, `legal_support_email`) ?
9. **Marques** (R6) : voie légère (`manufacturer`) ou rattachement des
   produits à `Brand` ?
10. **Notifications en application** (`notifications` /
    `user_notifications`, dormantes) : support du badge de la messagerie, ou
    retrait ?
11. **Priorité** : des groupes tarifaires prioritaires dans la file ?
12. **HEIC** (photos d'iPhone) : refus explicite ou conversion ?

---

## 11. Découpage proposé

Les lots de messagerie sont nommés **MSG·** pour ne pas les confondre avec
les identifiants M· de l'audit fonctionnel.

| Lot | Contenu | Taille |
|---|---|---|
| **A1** | Accueil : sections ordonnables / masquables / titrées (R1), route d'ordre en une transaction, migration de reprise, endpoint unique `GET /homepage` + `GET /homepage/personal` (prix du client) | M |
| **A2** | Sélections de produits nommées (R2) et catégories choisies (R3), sélecteur admin | M |
| **A3** | Annonce, réassurance, fabricants, bloc libre (R4 à R7) | M |
| **A4** | Aperçu et programmation (R10), SEO de l'accueil (R11) | S à M |
| **A5** | Ciblage par audience et sections personnelles (R8, R9) | M |
| **MSG1** | Messagerie, socle : module, modèle, API client et admin, onglet « Messages », écran admin, sondage, e-mails de non-lus et préférence, pièces jointes (service générique), conservation et RGPD | L |
| **MSG2** | Page `/contact` publique (M8 de l'audit), anti-spam, rattachement à un compte par adresse prouvée, lien visiteur si retenu | S à M |
| **MSG3** | Raccourcis contextuels (produit, commande, panier, groupe), panneau client et objet rattaché dans le fil | M |
| **MSG4** | Notes internes, réponses types, transfert, libération automatique, digest, priorité si retenue | M |
| **MSG5** | Demandes de devis et de groupe rattachées à une conversation (Z18 volet devis, M14 volet groupe) ; « Émettre le devis » / « Ouvrir un retour » | M |

Ordre conseillé : correctifs du §12 d'abord, puis **A1 → MSG1 → MSG2 → A2 →
MSG3 → MSG4**, puis le reste selon les retours. A1 et MSG1 sont
indépendants et peuvent avancer en parallèle.

---

## 12. Défauts du code actuel trouvés pendant la relecture

Inscrits au plan de travail ; à corriger **sans attendre** ce chantier.

1. **Prix visiteur sur l'accueil pour un client d'un groupe tarifaire.** Les
   routes `/product/featured` et `/product/popular` tarifent bien au groupe
   du client (`product_catalog.py:592-609, 667-678`), mais le rendu serveur
   est anonyme, le store `home` est transmis au navigateur et `load()`
   s'arrête puisque `loaded` est vrai (`stores/home.ts:37`) ; seul un
   changement de langue recharge (`IndexPage.vue:290-293`), ni la connexion
   ni la déconnexion (`stores/auth.ts`), et `ProductCard` affiche le prix
   reçu tel quel. Un pro qui arrive sur `/` voit les prix visiteur (le
   panier, lui, est au bon prix) ; après une déconnexion dans le même
   onglet, les prix du groupe restent affichés. Remède : recharger les
   produits de l'accueil quand l'utilisateur connecté change ; test Vitest
   (connexion → prix du groupe, déconnexion → prix visiteur). — S
2. **Devis d'un visiteur lisibles par une session invitée de même
   adresse.** `POST /signup/guest` ouvre une session pour toute adresse sans
   compte, sans preuve (`signup.py:225-268`, compte `is_verified=False`).
   `list_my_quotes` lit `user_id == moi OR email == mon e-mail`
   (`cart.py:2519-2536`), `_my_quote_or_404` et `check_convertible`
   (`quote.py:216`) donnent une demande sans compte à quiconque a la même
   adresse : nom, téléphone, adresse de livraison et PDF du devis d'un
   visiteur se lisent, et le devis s'accepte, depuis une session invitée
   ouverte à son adresse. Remède : la correspondance par e-mail exige un
   compte vérifié et non invité, et `list_my_quotes` ajoute `user_id IS
   NULL` à sa branche e-mail. — S
3. **Préférence « commandes » jamais lue.** `notification_email_enabled`
   (interrupteur de `AccountPreferences.vue`) n'est consulté par aucun envoi ;
   seuls `notification_shipping_steps` et `marketing_email_enabled` le sont.
   La brancher sur les e-mails de commande non obligatoires, ou la retirer.
   — S
