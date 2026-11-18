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


### Audit fonctionnel du 15/11/2026 (code)

Détail : [`AUDIT_FONCTIONNEL_2026-11.md`](AUDIT_FONCTIONNEL_2026-11.md) (identifiants D·, Z·, M·). Les sept défauts D1 à D7 et les zones fragiles Z1 à Z6, Z11, Z12 et Z16 sont corrigés (voir CHANGELOG). Reste :

- **Z3 (reste)** : un worker « unhealthy » n'est pas redémarré automatiquement (pas d'autoheal dans les compose) — S, à décider avec l'hébergement.
- **D1 (suite)** : le délai de livraison affiché ignore encore le mode d'import choisi et le délai fournisseur ; un départ groupé ne porte pas de mode — M.

### Relecture du 17/11/2026 — constats confirmés, non corrigés

Cinq relectures indépendantes des changements de novembre ; ce qui a été corrigé est au CHANGELOG. Reste, par ordre d'importance :

- **Le mode d'import payé n'apparaît nulle part** : `order_lines.import_service_level` est écrit mais lu par aucun écran (fiche commande admin, commande client, e-mail) — la boutique ne sait pas par quel mode expédier. Il se perd aussi à travers un devis (`items_snapshot`, `_install_quote_in_cart`) et un « commander à nouveau » — M.
- **D5, clé d'idempotence** : le verrou du panier ne couvre que les requêtes simultanées ; un nouvel essai après un délai dépassé crée une seconde commande (la vitrine reconstruit un panier). `cart.already_checked_out` n'est traité par aucun frontend. Accepter une clé d'idempotence au checkout et renvoyer la commande existante — M.
- **Paiement manuel en attente avec versements** : quand une part est réglée par un autre paiement, les paiements en attente sans versement sont fermés ; celui qui porte déjà des versements reçus reste à régler à la main (journalisé, pas d'alerte) — S.
- **Adresse figée sur la commande** : le texte (destinataire, société, téléphone compris) sert d'adresse de l'acheteur sur la facture ; il est construit côté vitrine et plafonné à 500 caractères. Le construire côté serveur depuis `shipping_address_id`, destinataire et téléphone dans des colonnes à part — M. Les cartes d'adresse (checkout, compte, admin) n'affichent pas les trois champs ; une adresse d'avant la migration n'a pas de destinataire.
- **Deux définitions de « route d'import »** : le prix lit les routes avec `service_level`, le checkout exclut des frais de port celles dont la destination dédouane. Sans route portant un `service_level`, le fret n'est facturé nulle part, sans alerte ; le `base_price` fixe du tronçon d'import n'est facturé nulle part. Un seul prédicat et un bloquant dans la liste de mise en route — M, **à confirmer** (« le fret d'import n'est pas offert »).
- **Fermeture automatique des départs** : sous le seuil, un départ reste ouvert et les nouvelles commandes ne s'attachent à aucun (une alerte par semaine, rien sur l'écran d'état) ; l'appel au fournisseur précède le test du seuil, toutes les 15 min — S.
- **Écran d'état** : un worker arrêté ou un cron qui ne se déclenche plus laisse tout « ok » (aucun contrôle de fraîcheur) ; les événements FAILED n'ont ni purge ni rejeu ; un travail abandonné par arq sans appel de la fonction ne laisse pas de ligne ; double rejeu possible sur deux clics — M.
- **Alertes** : `check_supplier_health_task` « unhealthy » n'alerte pas ; une tâche par article (Icecat) marque toute la tâche en échec ; `last_alert_at` est posé avant l'envoi — S.
- **Avoir d'une commande sans facture** (écart de montant, puis remboursement) : le handler réessaie jusqu'à l'abandon et alerte à tort ; même chose pour la demande de solde d'un compte effacé — S.
- **Remboursement partiel** : passe la commande à `PartiallyRefunded` quel que soit son avancement (elle ne suit plus son départ) — porter l'état du remboursement sur le paiement — M.
- **Codes promo** : dix refus du même code périmé (le devis se recalcule à chaque changement) bloquent tout code pendant 10 min dans le devis, pas au checkout — compter les codes distincts — S.
- **E-mail de confirmation** : noms de produits non traduits, date estimée en UTC, adresse du client affichée pour un retrait — S.
- **Vitrine** : commande en attente de virement payable en plus par carte (pas de garde côté API) ; restauration de session qui peut écraser le panier local ; messages de repli en français dans `cart.ts` ; le formulaire d'édition d'un départ change le statut sans la confirmation ajoutée à « Étape suivante » — S chacun.
- **PUT générique de commande** : les autres champs peuvent être enregistrés avant le refus du changement de statut — S, à vérifier.
- **Tests manquants** : checkout par carte sur une vraie base (le bug du 17/11 n'était vu par aucun test), parité fiche / panier / ligne de commande / facture du fret, verrou du panier, `GET /admin/system-status` et rejeu, `deploy.sh`.

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

- **Décidé (12/11/2026)** : le captcha reste accepté quand Cloudflare ne répond pas (journalisé ; les limites de fréquence, elles, refusent en cas de panne de Redis), pour ne pas bloquer l'inscription pendant une panne de Cloudflare.
- **À décider** : chiffrer les codes de cartes cadeaux en base (ils restent en clair pour pouvoir être réimprimés : un chiffrement réversible ou un hachage + code affiché une seule fois).
- Audit du 11/11/2026, gravité moyenne ([`AUDIT_2026-11.md`](AUDIT_2026-11.md) §1) — M au total :
  - **S8 (suite, si voulu)** : les paniers invités ne sont plus relancés (adresse non vérifiée) ; pour les relancer à nouveau, un double opt-in de l'adresse saisie (e-mail de confirmation) — M.
- Audit, durcissement restant : *required reviewers* sur l'environnement GitHub `production` (réglage du dépôt, hors code).
- **Relecture des correctifs de l'audit (15/11/2026)** — corrigé : voir CHANGELOG. Laissé en l'état, par choix ou faute de donnée :
  - *Verrouillage à la demande* : 50 échecs depuis une dizaine d'adresses verrouillent encore un compte 15 min (`LOGIN_ACCOUNT_LOCKOUT_MAX_FAILURES`) — c'est la protection contre la force brute distribuée ; un reset de mot de passe le lève. **À décider** si un déverrouillage par e-mail est voulu.
  - *Anciens codes de secours 2FA* (SHA-256) acceptés jusqu'à leur régénération par l'admin.
  - *Stock d'une commande payée puis annulée ou remboursée* : rendu à la main (la marchandise peut être déjà commandée ou partie) ; sous-vente possible quand le fournisseur a déjà décompté nos réservations (B4, côté sûr).
  - *Statuts posés par les gestionnaires de paiement* (`Paid`, `PaymentFailed`, `Refunded`) : pas d'événement `order.status_changed` (les e-mails de paiement existent déjà ; l'ajouter doublerait les notifications) — à reprendre avec l'historique de commande (§4).
  - *PayPal* : clé d'idempotence du remboursement aléatoire (deux remboursements partiels identiques sont légitimes ; le bouton est bloqué pendant l'appel).
  - `ALERT_WEBHOOK_URL` sans garde réseau : variable d'environnement posée par l'exploitant, souvent une adresse interne.
  - `sale_price_cached` en centimes jusqu'au premier recalcul nocturne après déploiement.

---

## 3. Fonctionnel — client

- **Audit fonctionnel du 15/11/2026, manques côté client** (détail dans l'audit, §4) : identité de facturation B2B (M3, M) ; notification de retard d'un départ (M4, M — l'e-mail de confirmation complet est fait) ; page contact (M8, S — destinataire, société et téléphone sur l'adresse faits) ; pages catégorie et marque indexables (M9, M) ; demande d'avis après livraison, e-mail de décision de groupe tarifaire, carte cadeau saisissable au checkout (M14, S chacun) ; rupture partielle après commande (M6, M à L).

- **Retours, RMA et formulaire de rétractation** (obligation légale, c'est du code) : demande depuis « Mes commandes », validation admin, enchaînement sur le remboursement et l'avoir existants — L.
- **SMS** (expédition, solde dû) — M.
- Newsletter double opt-in (outil externe ou intégré, à choisir) ; analytics sans cookie (Plausible / Matomo).
- Bugs vitrine relevés par l'audit du 11/11/2026 : faits (voir CHANGELOG).

---

## 4. Fonctionnel — admin

- **Audit fonctionnel du 15/11/2026, manques côté admin** (détail dans l'audit, §4) : suivi des encours avec relance (M2, S à M) ; commande et devis créés par l'admin (M5, L) ; garde-fou sur les coûts fournisseur (M7, M) ; export des paiements et rapport de ventes par taux de TVA (M10, M) ; historique des synchros, écran Icecat, boutons de maintenance (M11, S à M) ; journal des mouvements de stock (M12, M) ; outils RGPD et purges planifiées (M13, S à M) ; factures : recherche, pagination, bouton FEC, « émettre / renvoyer » (Z7, M).

- **Historique de la commande** (statuts, paiement, expédition, auteur) et notes internes, en chronologie sur la fiche ; sert aussi d'audit par objet — M.
- **Écran du journal des e-mails** (`email_log`, déjà alimenté : statut, erreur, renvoi possible sauf secrets) avec « renvoyer » ; écran des événements outbox en échec — M.
- **Bons de préparation, étiquettes**, changement de statut en masse — M.
- **Fiche client** (commandes, avoir, points), recherche globale (n° de commande, client, SKU) — M.
- **Rôles fins** (préparateur, comptable) à la place du seul superuser — M.
- Pagination serveur sur les autres tableaux (30 fichiers masquent encore la pagination ; 3 seulement paginent côté serveur) — M.

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
- Vitrine : vrais **404 en SSR** (aujourd'hui HTTP 200 : la route catch-all court-circuite le 404 de `src-ssr/middlewares/render.ts`), décalage d'hydratation du `min-height` de `QPage`, flash de thème à la première visite, police d'icônes chargée en entier, `srcset` des photos fournisseur (les médias de la boutique l'ont), parité fr / en testée — M.
- Médias publics derrière un CDN ou un bucket public si le trafic le demande ; recadrage d'image dans l'admin.
- UX et accessibilité de l'audit du 11/11/2026 : faites (voir CHANGELOG). Reste, si voulu : rendre « responsives » les autres `min-width` en ligne des barres d'outils admin (220 à 280 px, ils tiennent aujourd'hui dans 390 px) ; traduire les textes juridiques par défaut (une mention signale qu'ils sont en français).

---

## 8. Factorisation

- `CrudBase` + `BaseRouter` → socle de natimai-paie (`Policy`, `sortable_fields`, `Page[T]`), puis migration des routeurs `admin_*` qui paginent à la main — L.
- La commande hors de `api/routes/cart.py` (3 700 lignes) → `features/order/services/checkout.py` ; une seule `get_or_create_status` (3 copies : `admin_shipping`, `manual_payment`, `document_payment`) ; code fournisseurs regroupé dans `features/integrations/` — L.
- Front : `BaseApi` / `verifyResult` et un extracteur d'erreur unique traduisant le code ; `useResource` et `<CrudPage>` pour l'admin ; `formatDate` / `formatMoney` locaux remplacés par `@app/utils` — M.
- Tests : fabriques partagées (`tests/factories.py`), test générique sur les routeurs (authentification, tri refusé, propriétaire → 404) — M.

---

## 9. Dettes techniques et veille

- **`picomatch` (GHSA-fc5q-39xc-vjpf, ReDoS)** : avis ignoré dans `pnpm audit` (`auditConfig.ignoreGhsas`, `package.json`) le 18/11/2026, faute de version corrigée (4.0.7 est la dernière). Outillage de build seulement (via `vue-router`). **À retirer** dès qu'une version corrigée sort : l'imposer par un `override`, puis supprimer l'exception — S.

- **TypeScript 7** : bloqué par `vue-tsc` et `typescript-eslint` ; déclencheur : leur prise en charge annoncée. Dependabot n'en propose plus la majeure (`ignore`), à relever le moment venu.
- **express 5** : le serveur SSR tourne en express 4 (Quasar recopie sa propre dépendance) ; `@types/express` en 5 décrit une autre API — à aligner. Majeure ignorée par Dependabot, comme celles de `@types/node` (aligné sur node 24, la LTS des images).
- **httpx → httpx2** pour le code applicatif quand l'extra `standard` de FastAPI l'accepte ; vérifier alors `ca-certificates` dans l'image (truststore).
- **Bornes hautes des dépendances Python** (sentry-sdk, aiohttp, boto3, weasyprint, arq, clamd, pyyaml…) : politique à trancher.
- **Node 26 LTS** (fin 2026) : Dependabot ne la proposera pas (règle d'exclusion des majeures impaires).
- `session.execute()` dans `order_number.py` : à trancher si l'avertissement devient une erreur.
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
