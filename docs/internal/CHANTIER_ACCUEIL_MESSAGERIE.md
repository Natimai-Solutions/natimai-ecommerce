# Chantier — personnalisation de l'accueil et messagerie client

Document de travail du 18/11/2026. Rien n'est livré : ce document sert à
**décider** puis à découper. Quand un lot est livré, il sort d'ici (et du
plan de travail), git garde l'historique.

Deux sujets :

1. **Accueil de la vitrine** : état des lieux, recommandations, proposition
   d'architecture (§1 à §3).
2. **Messagerie** entre un client et la boutique (support, service
   commercial), sur le modèle de FenuaPro et de Natimai Paie (§4 à §9).

Les décisions attendues du propriétaire sont regroupées au §10, le
découpage en lots au §11.

---

## 1. Accueil — ce qui existe

**Vitrine** (`frontend/src/pages/IndexPage.vue`, store `frontend/src/stores/home.ts`),
dans cet ordre fixe :

| Section | Source | Réglable dans l'admin ? |
|---|---|---|
| Héros (titre, texte, bouton, image) | `homepage_blocks`, `kind = hero`, un seul publié par période (409 `homepage.hero.conflict`) | Oui — *Accueil du site* |
| Bannières | `homepage_blocks`, `kind = banner`, triées par `position` | Oui |
| Catégories (8 tuiles) | `GET /category`, choix **automatique** : premier niveau, celles qui ont une image d'abord, puis l'alphabet (`frontend/src/utils/categories.ts`) | Non (seulement l'image de la catégorie) |
| « Nos coups de cœur » (8) | `GET /product/featured` : `is_featured`, `featured_position`, `featured_until` | Indirectement, produit par produit (fiche produit) |
| « Les plus consultés » (8, 30 jours) | `GET /product/popular` (`product_view_daily`), vedettes retirées | Non |
| Bandeau du prochain départ | `NextDepartureBanner`, dans le layout (toutes les pages) | Non (dérivé des départs) |

Socle déjà en place, à réutiliser :

- blocs datés (`starts_at` / `ends_at`), publiés ou non, traduits
  (`translations`, `HOMEPAGE_BLOCK_FIELDS`, R9 / T3), image de la médiathèque
  (`media_id`, WebP en plusieurs largeurs, `srcset`) ;
- contrôle des liens (`/chemin` ou `https://`, jamais `javascript:` ni `//`) ;
- rendu SSR via `onServerPrefetch` + store Pinia (pas de refetch à
  l'hydratation), chaque section échoue seule (U8) ;
- écran admin `admin-frontend/src/pages/HomepagePage.vue` (liste par type,
  monter / descendre, dialogue d'édition, statut publié / programmé / expiré).

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
  qu'un visiteur ;
- pas d'aperçu avant publication ni de titre / description SEO propres à
  l'accueil.

---

## 2. Accueil — recommandations

Classées par rapport valeur / effort. Les trois premières font l'essentiel
de la demande « personnaliser l'accueil ».

### R1. Sections ordonnables et masquables — **à faire en premier** (M)

Chaque section de l'accueil devient une ligne ordonnée, activable, avec un
titre et un sous-titre saisis dans l'admin (traduits). Le héros reste en
tête (LCP, une seule image `fetchpriority="high"`). L'admin glisse les
sections dans l'ordre voulu, en masque, en duplique certaines.

### R2. Sélections de produits nommées (M)

Remplacer l'unique « coups de cœur » par des **sélections** autant que voulu,
chacune avec son titre, son nombre d'articles et sa source :

- **manuelle** : liste ordonnée de produits choisis dans un sélecteur (avec
  recherche par nom / SKU) — les vedettes actuelles deviennent la première
  sélection manuelle, reprise par migration ;
- **par règle** : catégorie (et ses sous-catégories), marque, « nouveautés »
  (date d'arrivée), « en promotion » (prix barré / remise active),
  « plus consultés » (l'existant), « meilleures ventes » ;
- tri et plafond (4 à 24), affichage carrousel ou grille.

Les produits non publiables (taux de douane non résolu, hors stock masqué)
restent exclus par le même filtre que le catalogue : une sélection ne doit
jamais montrer un produit que la recherche cache.

### R3. Catégories choisies (S)

Section « Catégories » en mode **automatique** (comportement actuel) ou
**manuel** : liste ordonnée de catégories, avec une image et un libellé
propres à l'accueil si voulu (sinon ceux de la catégorie).

### R4. Bandeau d'annonce (S)

Barre fine au-dessus de l'en-tête : texte court + lien, datée, traduite,
fermable par le visiteur (mémorisé en `localStorage`, clé = id + version).
Usage : « Départ bateau le 3/12 — commandez avant le 28/11 », soldes,
fermeture exceptionnelle. Articuler avec `NextDepartureBanner` : soit
l'annonce le remplace pendant sa période, soit les deux s'empilent (à
décider, §10).

### R5. Réassurance (S)

Bande de 3 à 4 pictogrammes + texte court (« Livraison dans les îles »,
« Paiement sécurisé PayZen », « Prix TTC douane comprise », « Un conseiller
vous répond » → messagerie, §4). Icônes prises dans la liste fermée des
icônes de la vitrine (pas de saisie d'URL d'icône).

### R6. Marques (S)

Bande de logos de marques choisies (ordre manuel), chaque logo menant au
catalogue filtré par marque. Dépend d'un logo par marque dans la
médiathèque (à vérifier sur le modèle `Brand`).

### R7. Bloc de contenu libre (S)

Texte riche + image facultative, gauche / droite : présentation de la
boutique, extrait de « Comment ça marche », texte SEO de bas de page. Même
assainissement HTML que les pages de contenu (`ContentPage.body_html`).

### R8. Ciblage par audience (M)

Chaque section porte une **audience** : tous, visiteurs, clients connectés,
un ou plusieurs **groupes tarifaires** (`price_group_id` : les pros voient
« Commander en volume / Demander un devis », les particuliers une
promotion). Plus une **langue** facultative pour un bloc qui n'a de sens
qu'en français.

⚠️ Impact SSR : le rendu serveur est aujourd'hui fait **sans compte**
(l'accueil précharge en anonyme, `Cache-Control` public sur les réponses
SEO). Règle proposée : le serveur rend la version **visiteur** ; les
sections ciblées « connecté » / « groupe » sont chargées **après
hydratation** par une seconde requête authentifiée, dans un emplacement de
hauteur réservée (pas de saut de mise en page). Même remarque pour les
**prix** des sélections : un client d'un groupe tarifaire doit voir ses
prix, ce qui impose de recharger les cartes produits une fois connecté —
**à vérifier dès maintenant sur l'existant** (le store ne recharge qu'au
changement de langue, `IndexPage.vue`).

### R9. Sections personnelles (M, après R8)

Pour un client connecté uniquement, chargées côté navigateur :
« Vus récemment » (`product_view` a déjà la donnée), « Racheter » (articles
des dernières commandes), « Votre liste de souhaits » (`user_wishlist`),
« Votre commande en cours » (statut + départ). Aucune de ces sections n'est
rendue en SSR ni mise en cache.

### R10. Aperçu et programmation (S à M)

- **Aperçu** depuis l'admin : la vitrine ouverte avec un jeton d'aperçu
  signé, court (15 min), qui montre les brouillons et accepte une date
  simulée (« voir l'accueil du 1/12 ») et une audience simulée (visiteur,
  groupe X).
- Calendrier : vue des sections programmées sur les 30 prochains jours.

### R11. SEO de l'accueil (S)

Titre et description de l'accueil saisis dans l'admin (traduits), au lieu
des valeurs par défaut ; données structurées `Organization` / `WebSite`
(`SearchAction` vers la recherche).

### À éviter

- **Carrousel de héros** : mauvais pour le LCP et peu cliqué ; garder un
  seul héros par période, éventuellement un héros par **audience** (R8).
- **Constructeur de page libre** (colonnes, marges, couleurs saisies) : la
  vitrine perdrait sa cohérence (dark mode, mobile 390 px) ; des types de
  sections fermés, chacun bien dessiné, suffisent.
- Tests A/B : pas de trafic suffisant pour conclure.

---

## 3. Accueil — architecture proposée

Généraliser `homepage_blocks` plutôt que créer une seconde table : le socle
(dates, publication, traductions, médias, écran admin) est déjà là.

```
homepage_blocks
  kind            hero | banner | announcement | category_grid
                  | product_collection | brand_strip | reassurance | rich_text
                  | builtin (featured, popular, recent… = sections d'aujourd'hui)
  title, subtitle, cta_label, cta_link, media_id, image_url, alt   (existants)
  position, is_published, starts_at, ends_at, translations         (existants)
  config          JSONB — validé par un schéma Pydantic par `kind`
  audience        JSONB — {"scope": "all|guest|customer", "price_group_ids": [...], "locales": [...]}
  is_active                                                        (existant)

homepage_block_items          (lignes ordonnées des sections manuelles)
  block_id, position, product_id | category_id | brand_id, label?, media_id?
```

- `config` validé **par type** (union discriminée) : une règle de sélection
  ne référence que des colonnes déclarées (`category_id`, `brand_id`,
  `sort ∈ {newest, popular, price_asc…}`), jamais un filtre libre venu du
  client.
- `GET /homepage` renvoie **les sections ordonnées, résolues** (produits,
  catégories, marques compris) en une requête, au lieu des quatre appels
  actuels du store ; un `GET /homepage/personal` (authentifié) renvoie les
  sections ciblées et personnelles (R8 / R9).
- **Migration de reprise** : les sections d'aujourd'hui deviennent des
  lignes `builtin` dans l'ordre actuel ; les produits `is_featured` une
  sélection manuelle. Rien ne change à l'écran au déploiement.
- **Cache** : la réponse visiteur se met en cache Redis par langue (TTL
  court, invalidé à chaque écriture admin) ; la réponse personnelle jamais.
- `_refuse_second_live_hero` s'étend : un héros par période **et par
  audience**.
- Nouveaux codes d'erreur (`homepage.config`, `homepage.audience`,
  `homepage.item_not_found`…) dans **les deux** catalogues
  `shared/utils/src/apiErrors/{en,fr}.json`.
- Admin : l'écran *Accueil du site* devient une liste unique ordonnable
  (glisser-déposer), un dialogue par type de section, un sélecteur de
  produits / catégories / marques, et le bouton **Aperçu** (R10).

Tests : intégration sur base réelle pour la résolution des sélections
(produit masqué exclu, prix du groupe), l'audience (un visiteur ne reçoit
jamais une section de groupe), la migration de reprise (upgrade /
downgrade) ; Vitest sur le rendu de chaque type et les deux thèmes.

---

## 4. Messagerie — besoin

Un client doit pouvoir **écrire facilement** à la boutique et retrouver la
réponse au même endroit, en distinguant :

- **Support / service client** : une commande, une livraison, un paiement,
  un retour, un produit reçu ;
- **Service commercial** : un devis, un achat en volume, une demande
  professionnelle, une question avant achat.

Aujourd'hui il n'existe qu'un fil à sens unique : la **demande de devis**
(`quote_requests`, un e-mail au support, un `admin_comment` que le client
ne voit pas), l'adresse `email_support` affichée dans les e-mails, et le
réglage `email_contact` (« destinataire du formulaire de contact ») **sans
formulaire de contact** (M8 de l'audit fonctionnel). Les échanges partent
donc en e-mail et sortent de l'outil.

---

## 5. Ce que font FenuaPro et Paie

| | FenuaPro (`features/contact`) | Natimai Paie (`features/support`) |
|---|---|---|
| Fil | `contact` + `contact_message` ; un fil de support **par utilisateur**, rattachable à un contexte (`context_type` / `context_id`) | `support_conversation` + `support_message`, un **canal** par conversation (`support`, `payroll`, `accounting`, `cabinet`) |
| Statuts | `NEW` / `PROGRESS` / `COMPLETE` | `open` (attend l'éditeur) / `pending` (attend le client) / `resolved` |
| Lu / non lu | un booléen `is_read` par message + notifications génériques | horodatages par côté (`customer_read_at`, `staff_read_at`) |
| Temps réel | WebSocket (ticket Redis à usage unique, pub/sub), badge en sondage 30 s | **aucun** : sondage 4 s sur le fil ouvert, 30 s sur la file, 60 s pour le badge |
| E-mail | digest différé : non lu depuis 10 min → e-mail **sans le contenu** ; préférence `message` | idem (10 min, une fois par vague, sans contenu ni sujet) |
| Pièces jointes | 10 Mo, ClamAV en tâche arq, S3, servies seulement une fois saines | PDF / PNG / JPEG, 5 Mo, type détecté sur les octets, 20 par fil |
| Équipe | file « À traiter / Mes conversations / Traitées / Toutes », prise en charge par UPDATE conditionnel (409 `already_claimed`, `force`), 1ʳᵉ réponse = prise en charge, libération auto après 3 j, transfert | mêmes onglets + « En attente », agents limités à des canaux, présence (`last_seen_at`), file de demandes du formulaire public |
| Formulaire public | `POST /contact`, 10/h par IP ; un connecté qui a déjà un fil y voit son message ajouté | `POST /public/contact`, Turnstile, pot de miel, 5/h par IP et 200/h au total, réponse **toujours 202** |
| Manques communs | pas de réponses types, pas de notes internes, pas de vrai SLA | idem, pas de canal commercial |

Pièges déjà payés ailleurs, à ne pas refaire :

- **WebSocket** : jamais de `SessionDep` sur la route (4 onglets ont vidé le
  pool de FenuaPro) ; tests sur la **même boucle** que l'app (le
  `TestClient` synchrone bloque) ; client Redis **dédié** sans
  `socket_timeout` pour le pub/sub ; revalider la session (stamp) pendant
  la connexion.
- Un PATCH de message sans liste blanche de champs a permis de réécrire
  `file_id` / `is_read` (FenuaPro SEC-57) : le serveur pose tout ce qui
  n'est pas le texte.
- Une mise en file d'e-mail sans `commit` n'envoie rien, et les tests (une
  session partagée) ne le voient pas.
- Une préférence de notification doit être **lue** par l'envoi (FenuaPro :
  clé présente dans le profil, jamais consultée).
- Le texte d'un tiers dans un gabarit d'e-mail passe par l'échappement
  avant la mise en file.

---

## 6. Messagerie — proposition fonctionnelle

### Côté client (vitrine)

- **Point d'entrée visible partout** : un bouton « Nous écrire » dans
  l'en-tête (icône + badge de non-lus pour un connecté) et en pied de page,
  plus des **raccourcis contextuels** qui ouvrent le fil pré-rempli :
  - fiche produit → « Une question sur ce produit ? » (canal *commercial*,
    produit joint) ;
  - « Mes commandes » → « Un problème avec cette commande ? » (canal
    *support*, commande jointe) ;
  - panier → « Demander un devis » (canal *commercial*, panier joint) ;
  - « Mon groupe » (`AccountGroup.vue`) → « Parler à un commercial ».
- **Onglet « Messages » dans « Mon compte »** (`MyAccountPage.vue`, clé
  `?tab=messages`) : liste des conversations (sujet, canal, dernier
  message, statut, non lu), fil de discussion, envoi de texte et de pièces
  jointes, bouton « Ma question est réglée ».
- **Visiteur non connecté** : page **`/contact`** (comble M8) avec le choix
  « Service client » / « Service commercial », nom, e-mail, téléphone
  facultatif, société facultative, sujet, message ; Turnstile si configuré
  + pot de miel + limites de fréquence ; réponse toujours identique. La
  réponse de l'équipe part **par e-mail** (aucun compte créé d'office) ;
  si l'adresse correspond à un compte, la demande est rattachée à ce compte
  et apparaît dans son onglet « Messages » une fois connecté **avec
  vérification de l'adresse** (jamais sur la simple saisie d'un e-mail).
- Horaires et délai de réponse affichés (« réponse sous 1 jour ouvré, du
  lundi au vendredi, 8 h – 17 h, heure de Tahiti »), réglables.

### Côté boutique (admin)

- Écran **Messagerie** (`admin-frontend`) : onglets « À traiter », « Mes
  conversations », « En attente du client », « Réglées », « Toutes » ;
  filtre par canal ; recherche (numéro de commande, nom, e-mail) ; compteur
  dans le menu.
- Dans le fil : fiche du client à droite (groupe tarifaire, dernières
  commandes, avoir) et **objet rattaché** (commande, produit, panier,
  demande de devis) cliquable vers sa fiche admin.
- **Prise en charge** (UPDATE conditionnel, 409, `force`), la première
  réponse prend en charge, **libération automatique** après N jours sans
  réponse, **transfert** à un collègue, réouverture si le client réécrit.
- **Notes internes** (invisibles du client) et **réponses types** traduites
  (fr / en, variables `{prenom}`, `{commande}`) — les deux projets n'en ont
  pas, c'est le premier manque relevé côté équipe.
- **Canaux** affectables aux membres de l'équipe (support, commercial).
  Tant que l'admin n'a que `is_superuser` (rôles fins = §4 du plan), tout
  superuser voit tout ; la table d'agents sert seulement au routage des
  notifications.
- Depuis une conversation commerciale : **« Créer un devis »** (lien vers
  la demande de devis / la future commande admin M5) et, depuis une
  conversation support, **« Ouvrir un retour »** (futur RMA §3 du plan).

### Notifications

- Client : e-mail « Vous avez une réponse » **sans le contenu**, envoyé si
  le message reste non lu 10 min, une fois par vague ; lien vers le fil
  (connecté) ; préférence dans `AccountPreferences.vue`, **effectivement
  lue** par l'envoi. Visiteur sans compte : la réponse part **avec** le
  contenu (il n'a pas d'autre accès) — même choix que FenuaPro pour les
  projets déposés pour un tiers.
- Équipe : e-mail au membre qui a pris en charge, sinon aux membres du
  canal, sinon aux superusers ; digest du matin (compteurs seuls), dans la
  **langue de l'opérateur** (`operator_messages.py`, `operator_locale`) ;
  facultatif : alerte Slack (fournisseur déjà présent).
- Une demande de devis (`quote_requests`) **ouvre une conversation**
  commerciale au lieu d'un e-mail isolé : le client voit la réponse, le
  `admin_comment` devient une note interne. Idem pour une demande de
  changement de groupe tarifaire (`group_upgrade_request`) si voulu.

---

## 7. Messagerie — proposition technique

### Modèle (`backend/app/features/messaging/`)

```
conversations
  id, number (C-2026-00042, lisible au téléphone)
  channel           support | sales                 (liste fermée, config)
  status            open | pending | resolved
  subject
  customer_id       FK users, NULL pour un visiteur
  guest_name, guest_email, guest_phone, guest_company   (visiteur seulement)
  context_type      order | product | cart | quote_request | group_request | NULL
  context_id        UUID
  assigned_to_id, assigned_at
  last_message_at, last_customer_message_at, last_staff_message_at
  customer_read_at, staff_read_at
  customer_notified_at, staff_notified_at
  resolved_at, retain_until
  locale            langue du client (e-mails, réponses types)
  created_at, created_by_id …                       (socle)

conversation_messages
  id, conversation_id, author_id (NULL = visiteur), side customer | staff
  kind              message | note | event           (note = interne, event = « pris en charge par… »)
  body              texte brut, 4 000 caractères max
  created_at

conversation_attachments
  id, message_id, filename, mime, size, sha256, object_key, scan_status

messaging_agents     (routage des notifications, pas des droits)
  user_id, channels[], is_active, last_seen_at

canned_replies
  id, channel?, title, body, translations, position
```

- Le **lu / non lu** se tient par horodatage de côté (modèle Paie) : plus
  simple et juste qu'un booléen par message, un seul `UPDATE` pour
  « marquer lu ».
- `context_type` / `context_id` : **garde à la création** — le client ne
  peut rattacher que **sa** commande, **son** panier, **sa** demande ; un
  produit doit être publié. Sinon 404 (piège « champs de rattachement non
  gardés », FenuaPro, récidivé plusieurs fois).
- Pas de chiffrement applicatif (pas de DEK ici, contrairement à Paie), mais
  **pas de contenu dans les journaux**, purge à `retain_until`
  (durée à décider, §10) et inclusion dans l'export / l'effacement RGPD
  (`features/user/services/privacy.py`).

### API

- Client (`CurrentUser`) : `GET/POST /me/conversations`,
  `GET /me/conversations/{id}?after=`, `POST …/messages`,
  `POST …/attachments`, `POST …/read`, `POST …/resolve`,
  `GET /me/conversations/unread` ; une conversation d'un autre client →
  **404**. Limites : 10 conversations / h, 60 messages / 10 min par compte.
- Public : `POST /contact` (Turnstile via `core/captcha.py`, pot de miel,
  `core/rate_limit.py` par IP et global, **202 identique** que l'adresse
  existe ou non : pas d'énumération de comptes).
- Visiteur qui répond à l'e-mail de l'équipe : **lien signé** vers le fil
  (jeton à durée limitée, révocable), pas de compte requis — ou, version
  minimale, réponse par e-mail seulement (§10).
- Admin (`CurrentSuperUser`, 2FA déjà exigée) : `/admin/conversations`
  (onglets, filtres, recherche, pagination **serveur**), `claim`,
  `release`, `transfer`, `resolve`, `notes`, `canned-replies` (CRUD),
  `summary` (compteurs du menu, sert aussi de présence).
- Codes d'erreur `messaging.*` dans les deux catalogues ; messages API en
  anglais ; textes de succès dans l'i18n de chaque frontend.

### Temps réel : commencer par le sondage

Recommandation : **sondage** comme Paie (fil ouvert : 5 s ; badge : 60 s,
suspendu quand l'onglet est caché), sans WebSocket. Le volume d'une
boutique ne le justifie pas, et le WebSocket de FenuaPro a coûté deux
incidents (pool vidé, CI bloquée). Le passage au WebSocket (ticket Redis +
pub/sub, recette FenuaPro) reste une option si la charge l'exige ; l'API
`?after=` est conçue pour ne pas changer.

### Pièces jointes

Réutiliser `features/attachment` (stockage privé, URL présignées, scan
antivirus déjà utilisé pour les bons de commande) : PDF / PNG / JPEG / WebP,
5 Mo, type détecté sur les octets, **téléchargeable seulement une fois
sain**, 20 par conversation. Photos d'un colis abîmé = cas d'usage n° 1 du
support.

### Tâches arq

- `task_messaging_notify` (5 min) : e-mails de non-lus (client, équipe),
  `commit` après la mise en file ;
- `task_messaging_digest` (matin, heure de Tahiti) : libération des
  conversations tenues sans réponse, digest de l'équipe ;
- `task_messaging_purge` (nuit) : purge à `retain_until`.

### Garde-fous et tests

- Intégration sur **base réelle** : un client ne lit ni n'écrit dans la
  conversation d'un autre (404), ne rattache pas la commande d'un autre, ne
  voit jamais une note interne ; deux agents qui prennent la même
  conversation (409) ; e-mail relu depuis une **connexion indépendante**
  (le commit, pas la session partagée) ; la réponse de `/contact` est
  identique pour une adresse connue ou non.
- Vitest : fil, badge, deux thèmes, mobile 390 px.
- `pnpm gen:types` et migration Alembic (upgrade **et** downgrade).

---

## 8. Ce qu'on prend, ce qu'on laisse

| Repris de | Élément |
|---|---|
| Paie | canaux, statuts à trois états, lu par horodatage, sondage, e-mail différé sans contenu, formulaire public 202 + pot de miel, présence, libération après 3 j |
| FenuaPro | rattachement à un contexte (commande, produit…), réouverture quand le client réécrit, transfert, liste blanche des champs modifiables |
| Nouveau | canal **commercial**, **notes internes**, **réponses types**, fiche client et objet rattaché dans le fil, devis = conversation |
| Laissé | WebSocket, réactions emoji, indicateur « en train d'écrire », assistant IA de premier niveau (Paie), quotas payants par canal |

---

## 9. Hors périmètre (pour mémoire)

- Chat en direct temps réel avec widget flottant façon Intercom.
- WhatsApp / Messenger / SMS entrants (le SMS sortant est au §3 du plan).
- Réponse au client **par retour d'e-mail** qui revient dans le fil
  (boîte de réception à relever, analyse MIME, anti-spam) : coûteux, à
  rouvrir seulement si les clients répondent massivement aux e-mails.

---

## 10. Décisions attendues

1. **Bandeau d'annonce et prochain départ** : l'un remplace l'autre pendant
   sa période, ou les deux s'empilent ?
2. **Ciblage par groupe tarifaire** (R8) : voulu dès le premier lot, ou
   après ?
3. **Canaux** : seulement *support* et *commercial*, ou aussi *retours* /
   *comptabilité* (factures, avoirs) ?
4. **Visiteur sans compte** : réponse par e-mail seulement, ou lien signé
   pour continuer la conversation sur le site ?
5. **Demandes de devis** : les transformer en conversations (le client voit
   la réponse) — oui / non ?
6. **Durée de conservation** des conversations réglées (proposition :
   3 ans, durée de prescription commerciale du code de la consommation pour
   un litige — **à valider avec la relecture juridique**), et mention dans
   la politique de confidentialité.
7. **Horaires et délai de réponse** affichés : lesquels ?
8. **Qui répond** : tous les superusers, ou des personnes nommées par canal
   (table d'agents) ?

---

## 11. Découpage proposé

| Lot | Contenu | Taille |
|---|---|---|
| **A1** | Accueil : sections ordonnables / masquables / titrées (R1), migration de reprise, endpoint unique `GET /homepage` | M |
| **A2** | Sélections de produits nommées (R2) et catégories choisies (R3), sélecteur admin | M |
| **A3** | Annonce, réassurance, marques, bloc libre (R4 à R7) | M |
| **A4** | Aperçu et programmation (R10), SEO de l'accueil (R11) | S à M |
| **A5** | Ciblage par audience et sections personnelles (R8, R9), prix du groupe dans les sélections | M |
| **M1** | Messagerie, socle : modèle, API client et admin, onglet « Messages », écran admin, sondage, e-mails de non-lus, pièces jointes | L |
| **M2** | Page `/contact` publique (M8), anti-spam, rattachement vérifié à un compte | S à M |
| **M3** | Raccourcis contextuels (produit, commande, panier, groupe), fiche client et objet rattaché dans le fil | M |
| **M4** | Notes internes, réponses types, transfert, libération automatique, digest | M |
| **M5** | Demandes de devis et de groupe en conversations ; « Créer un devis » / « Ouvrir un retour » | M |

Ordre conseillé : **A1 → M1 → M2 → A2 → M3 → M4**, puis le reste selon les
retours. A1 et M1 sont indépendants et peuvent avancer en parallèle.

Avant A1 : vérifier que les prix des cartes de l'accueil suivent le groupe
tarifaire d'un client connecté (R8) — si non, c'est un défaut à corriger
indépendamment de ce chantier.
