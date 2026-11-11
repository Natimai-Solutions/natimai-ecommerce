# Plan de travail — reste à faire

Ce document ne liste que **ce qui reste à faire**. Ce qui est livré en sort :
l'historique (phases, décisions, audits, comptes rendus de livraison) vit dans
git — version complète de ce fichier jusqu'au commit `1fb7095` (24/10/2026).

Légende : **S** ≤ 1 j · **M** 2 à 5 j · **L** > 5 j · **hors code** = action
sur le serveur, chez un tiers ou une décision.

---

## 1. Avant l'ouverture — bloquants de production

### Correctifs de l'audit du 11/11/2026 (code)

Détail, fichiers et scénarios : [`AUDIT_2026-11.md`](AUDIT_2026-11.md) (identifiants S·, B·, F·, U·).


### Exploitation (sur le serveur, hors code)

- **Sauvegardes réelles** : planifier le cron de `scripts/backup/backup.sh`, configurer la copie hors site (rclone / scp), **exécuter une restauration réelle** avant la première commande (DEPLOYMENT.md §12).
- **`ALERT_WEBHOOK_URL`** à renseigner (`.env` et cron) : sans lui, un événement outbox perdu après 8 tentatives, un health-check en erreur, un échec de sauvegarde ou une identité légale incomplète ne préviennent personne.
- **Quota d'artefacts GitHub** atteint : les envois sont devenus non bloquants et leur rétention réduite à 7–14 j ; purger les anciens artefacts (*Settings → Actions → Artifacts* ou l'API) pour retrouver les rapports de couverture.
- **Dependabot security updates** à activer sur le dépôt `Natimai-Solutions/natimai-ecommerce` (*Settings → Code security*), avec *Grouped security updates*.
- Variables GitHub `VITE_PUBLIC_SITE_URL`, `VITE_SENTRY_DSN`, `CODEQL_ENABLED`.
- **CSP en observation sur staging** (`CSP_HEADER=Content-Security-Policy-Report-Only`), puis l'imposer.
- Clés **Turnstile** (Paramètres → Sécurité) si les limites de fréquence ne suffisent plus.
- `ENABLE_GROUP_PERMISSIONS` : décidé le 04/11/2026, gardé désactivé comme base des rôles fins (§4) ; aujourd'hui seul `is_superuser` protège l'admin.
- Commande automatique Ingram : passer `INGRAM_ORDER_CREATION_ENABLED=true` seulement avec l'adresse de livraison complète, réglée **sur le worker**.

### Paiement (identifiants de test à fournir)

- **Sandbox PayZen**, jamais testée : paiement, IPN, autorisation seule (`manualValidation`, statut `AUTHORISED`), capture (`Transaction/Validate`), remboursement et annulation (`Transaction/CancelOrRefund`), alerte d'expiration des autorisations. Idem **sandbox PayPal**.

### Juridique et comptable (hors code)

- **Relecture juridique** des CGV, mentions légales et politique de confidentialité ; identité du vendeur complète (`legal_*`, ex-`INVOICE_SELLER_*`) avant la première facture.
- **Validation du comptable** :
  - facture d'**acompte** : aujourd'hui une seule facture, au solde (reçu par e-mail pour l'acompte) ; sinon `Invoice.kind ∈ deposit | final`, unicité levée, facture finale qui déduit les acomptes (impacte snapshot, PDF, CSV / FEC, avoirs) ;
  - **TVA d'import** supposée déductible (sinon l'intégrer au taux effectif de douane) ;
  - code taxe des frais de livraison et de paiement (`INVOICE_FEES_TAX_CODE`) ;
  - conservation et archivage légal des factures ; export **FEC strict** si l'expert-comptable l'exige (le CSV couvre le besoin courant).
- **Assurance transport** : souscrire une police ad valorem, puis saisir son taux (`INSURANCE_RATE_PCT`, DEPLOYMENT §16.2). À 0, la prime n'est jamais récupérée sur les ventes.

### Données du catalogue

- **Taux de douane par catégorie** (DEPLOYMENT §15) : un produit dont le taux ne se résout pas est masqué. Le taux effectif inclut TDL et autres prélèvements de la position tarifaire (dérivation depuis le simulateur officiel de la douane).
- **Frais par déclaration** (lieu de dédouanement) et taux d'assurance (§16) : zéro est légitime s'il est choisi sciemment.
- `GET /admin/catalog/publication-report` à **zéro produit bloqué** (taux de douane, poids), catégorie par catégorie.
- Vérifications à tracer : taux d'enrichissement Icecat sur le catalogue réel (filtre `is_enriched`), backfill `category_id`, contrôle mensuel des taux de change saisis à la main, volumétrie du stockage.

---

## 2. Sécurité et performance

- **À décider** : refuser (et non accepter) le captcha quand Cloudflare ne répond pas ; chiffrer les codes de cartes cadeaux en base (ils restent en clair pour pouvoir être réimprimés : un chiffrement réversible ou un hachage + code affiché une seule fois).
- Audit du 11/11/2026, gravité moyenne ([`AUDIT_2026-11.md`](AUDIT_2026-11.md) §1) — M au total :
  - **S8** : relance de panier abandonné seulement vers une adresse vérifiée (double opt-in invité) ;
  - **S10** : neutraliser `= + - @` en tête de cellule dans tous les exports CSV admin ;
- Audit, durcissement (gravité basse, liste complète dans l'audit) : limite de fréquence et erreur unique sur les endpoints 2FA ; mot de passe exigé pour supprimer un compte lié à OAuth ; codes de secours en HMAC ; le changement de mot de passe invalide le lien de reset ; `Cancelled` parmi les statuts de paiement terminaux ; limite « 1 coupon par client » et remboursement admin sous verrou ; devise et montant obligatoires dans l'IPN ; quantité panier bornée ; allow-list IP Caddy étendue aux routes superuser hors `/admin` ; webhook sortant et flux fournisseur protégés contre le SSRF ; clé Icecat retirée des logs ; ClamAV et plafond décompressé sur l'import XLSX ; `user_id` retiré des avis et wishlists publics ; alertes stock limitées à l'e-mail du compte ; CI (`GIST_SECRET` limité aux étapes de badge, blocs `permissions:`, actions tierces épinglées par SHA, *required reviewers* sur l'environnement `production`) ; `requirepass` Redis — M.

---

## 3. Fonctionnel — client

- **Retours, RMA et formulaire de rétractation** (obligation légale, c'est du code) : demande depuis « Mes commandes », validation admin, enchaînement sur le remboursement et l'avoir existants — L.
- **SMS** (expédition, solde dû) — M.
- Newsletter double opt-in (outil externe ou intégré, à choisir) ; analytics sans cookie (Plausible / Matomo).
- Bugs vitrine relevés par l'audit du 11/11/2026 ([`AUDIT_2026-11.md`](AUDIT_2026-11.md) §2) :
  - commande d'un devis accepté sans miroir du panier ; fuseau de la boutique appliqué côté client après hydratation ; retour de paiement 3-D Secure dans un autre navigateur (statut signé sans session) ; facture d'une commande via `GET /invoices/me/by-order/{id}` ; filtres du catalogue dans l'URL ; devis rechargé après `cart.price.changed` ; échec du script PayZen rattrapable — M.

---

## 4. Fonctionnel — admin

- **Historique de la commande** (statuts, paiement, expédition, auteur) et notes internes, en chronologie sur la fiche ; sert aussi d'audit par objet — M.
- **Écran du journal des e-mails** (`email_log`, déjà alimenté : statut, erreur, renvoi possible sauf secrets) avec « renvoyer » ; écran des événements outbox en échec — M.
- **Bons de préparation, étiquettes**, changement de statut en masse — M.
- **Fiche client** (commandes, avoir, points), recherche globale (n° de commande, client, SKU) — M.
- **Rôles fins** (préparateur, comptable) à la place du seul superuser — M.
- Pagination serveur sur les autres tableaux (30 fichiers masquent encore la pagination ; 3 seulement paginent côté serveur) — M.
- Audit du 11/11/2026 : `ProductFormDialog` repasse en édition après la création (un second « Enregistrer » ne crée plus de doublon) ; `order_cutoff_at` des départs saisi dans le fuseau de la boutique ; `OrderDetailPage` rechargée après un changement de statut — S.

---

## 5. Paiement et devises

- **Stripe** (P6, reporté) : avec `render_mode` / `client_secret` pour Stripe Elements.
- **Règlement dans la devise du client** : devise de règlement et taux figés sur la commande, distincts de la devise de facturation ; facture, avoir et exports dans la devise payée ; PayPal convertit aujourd'hui en EUR à parité fixe — L.
- Capture **partielle** (une partie de la commande expédiée).
- Remboursement `pending → completed` par webhook.
- Paiement en plusieurs fois (tokenisation PayZen).
- Mise à jour automatique des taux de change (opt-in, source BCE) et alerte sur un taux de plus de 30 jours.

---

## 6. Catalogue, prix et fournisseurs

- **Arrondi commercial** des prix calculés (à 10 / 100 F).
- Prix par groupe saisissables sur les **variantes** (elles suivent aujourd'hui la remise du groupe) ; un prix saisi pour un groupe vaut pour tous les modes de transport d'un article importé — à affiner si besoin.
- **Rafraîchissement stratifié des prix** : haute valeur / stock faible toutes les heures, ventre du catalogue chaque jour, longue traîne chaque semaine (tri par `last_supplier_sync` + score valeur / volatilité).
- **Disponibilité et prix Ingram synchrones au checkout** (un appel P&A par commande) ; demander au commercial la réservation d'inventaire.
- **Éligibilité automatique** du catalogue fournisseur : poids **et** dimensions présents, pas de fin de vie, marques retenues, seuil valeur / poids (XPF/kg) ; flux « nouveautés ».
- Icecat en anglais pour la version anglaise ; slugs par langue.
- Sélection automatique des routes : optimum global plutôt que par segment.
- Recherche IA (pgvector) — à concevoir.

---

## 7. Design et interface

- Densité admin : tables `dense`, squelettes plutôt que spinners, `app-empty` partout ; tableaux larges qui défilent (fournisseurs, paramètres) — M.
- Vitrine : vrais **404 en SSR** (aujourd'hui HTTP 200 : la route catch-all court-circuite le 404 de `src-ssr/middlewares/render.ts`), décalage d'hydratation du `min-height` de `QPage`, flash de thème à la première visite, police d'icônes chargée en entier, `srcset` des photos fournisseur, parité fr / en testée — M.
- Médias publics derrière un CDN ou un bucket public si le trafic le demande ; recadrage d'image dans l'admin.
- UX et accessibilité relevées par l'audit du 11/11/2026 ([`AUDIT_2026-11.md`](AUDIT_2026-11.md) §3) — M au total :
  - **U2** (reste) : messages d'erreur de l'admin (`ProductFormDialog`…) par l'enveloppe `{error:{message}}`, jamais le message axios brut — la vitrine (catalogue, panier, fiche produit) est faite ;
  - **U3** : récapitulatif repliable en tête du checkout mobile ; **U4** : dire ce qui manque quand « Payer » est désactivé ;
  - **U5** : `autocomplete` sur `AddressDialog`, « Requis » traduit ;
  - **U6** : panneau de filtres mobile en `q-dialog maximized` ; **U7** : suggestions de recherche en combobox accessible au clavier ;
  - **U8** : erreur d'ajout au panier visible près de l'action ; accueil avec message et « Réessayer » si toutes les API échouent ;
  - rôle des vignettes de galerie ; cibles tactiles de 44 px (« Mot de passe oublié ? », Comparer) ;
  - admin : `aria-label` sur les ~53 boutons icône, `ProductFormDialog` plein écran avec actions collantes sur mobile, `min-width` des toolbars, chaînes en dur ; pages légales en anglais ou mention explicite.

---

## 8. Factorisation

- `CrudBase` + `BaseRouter` → socle de natimai-paie (`Policy`, `sortable_fields`, `Page[T]`), puis migration des routeurs `admin_*` qui paginent à la main — L.
- La commande hors de `api/routes/cart.py` (3 700 lignes) → `features/order/services/checkout.py` ; une seule `get_or_create_status` (3 copies : `admin_shipping`, `manual_payment`, `document_payment`) ; code fournisseurs regroupé dans `features/integrations/` — L.
- Un seul `split_incl_tax(amount, rate, currency)` pour la facture, l'avoir et la marge (la marge arrondit à 0,01 quelle que soit la devise) — M.
- Front : `BaseApi` / `verifyResult` et un extracteur d'erreur unique traduisant le code ; `useResource` et `<CrudPage>` pour l'admin ; `formatDate` / `formatMoney` locaux remplacés par `@app/utils` — M.
- Tests : fabriques partagées (`tests/factories.py`), test générique sur les routeurs (authentification, tri refusé, propriétaire → 404) — M.

---

## 9. Dettes techniques et veille

- **TypeScript 7** : bloqué par `vue-tsc` et `typescript-eslint` ; déclencheur : leur prise en charge annoncée. Dependabot n'en propose plus la majeure (`ignore`), à relever le moment venu.
- **express 5** : le serveur SSR tourne en express 4 (Quasar recopie sa propre dépendance) ; `@types/express` en 5 décrit une autre API — à aligner. Majeure ignorée par Dependabot, comme celles de `@types/node` (aligné sur node 24, la LTS des images).
- **httpx → httpx2** pour le code applicatif quand l'extra `standard` de FastAPI l'accepte ; vérifier alors `ca-certificates` dans l'image (truststore).
- **Bornes hautes des dépendances Python** (sentry-sdk, aiohttp, boto3, weasyprint, arq, clamd, pyyaml…) : politique à trancher.
- **Node 26 LTS** (fin 2026) : Dependabot ne la proposera pas (règle d'exclusion des majeures impaires).
- `session.execute()` dans `order_number.py` : à trancher si l'avertissement devient une erreur.
- Robustesse backend relevée par l'audit du 11/11/2026 ([`AUDIT_2026-11.md`](AUDIT_2026-11.md) §2) — M au total :
  - outbox : reprise des événements restés `RUNNING`, `MAX_ATTEMPTS` appliqué ;
  - avoir émis plus tard si le remboursement précède la facture ; `balance_requested_at` posé seulement si l'e-mail part ; liaison au suivi en `begin_nested()` dans le checkout ; prix quantifiés selon la devise de référence (XPF sans décimales, voir aussi `split_incl_tax` au §8) ; branche `order is None` morte dans `_sync_order_status`.
- Troncature bcrypt à 72 octets : ne corriger (pré-hachage) que dans une opération de réinitialisation générale prévue pour ça.

---

## Risques à surveiller

| Risque | Parade |
|---|---|
| Prix volatils (GPU, mémoire) : écart entre le prix affiché (synchro 2 h) et le coût réel ; le prix affiché engage envers un particulier | Rafraîchissement stratifié, P&A synchrone au checkout, flux devis pour les références très volatiles (§6) |
| Rupture entre deux synchros : la disponibilité vérifiée au checkout est le stock local | P&A synchrone au checkout, réservation d'inventaire Ingram |
| Dimensions absentes d'Icecat : le poids volumétrique retombe sur le poids réel (sous-facturation du volumineux léger) | Comportement voulu, jamais de zéro inventé ; mesurer la couverture, saisie admin pour les cas critiques (§6) |
| Garantie : l'importateur est garant légal, un retour Tahiti → Europe coûte souvent plus que la marge | Réserve de 2 à 3 % du CA, marques à garantie constructeur internationale |
| Compte Ingram neuf, dernier servi sur les allocations | Ne pas exposer les références à allocation, flux devis et paiement d'avance |
| Filtre `is_enriched` qui viderait le catalogue si Icecat trouve peu de correspondances | Mesurer avant l'ouverture ; sinon afficher sans caractéristiques filtrables |
