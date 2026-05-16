# Plan de déploiement par paliers

Document de travail établi à partir de la vérification fonctionnelle (cf. [PLAN_VERIFICATION_FONCTIONNEMENT.md](PLAN_VERIFICATION_FONCTIONNEMENT.md)). Chaque phase est conçue pour être déployable en production de façon autonome, le frontend pouvant s'enrichir au même rythme.

---

## Décision transverse : tarification par groupe utilisateur

**Approche retenue** : coût stocké en base + prix de vente calculé à la volée selon le groupe du client.

### Modèle de données

| Entité | Champs à ajouter |
|--------|------------------|
| `Product` | `cost_amount: Decimal`, `cost_currency: str`, `customs_rate_pct: Decimal` |
| `PriceGroup` (nouveau, ou extension de `Group`) | `margin_rate_pct: Decimal`, `vat_rate_pct: Decimal`, `default: bool`, `requires_validation: bool`, `label: str` |
| `User` | `price_group_id: UUID` (FK, nullable → fallback `default=True`) |
| `OrderLine` | `price_group_applied_id: UUID` (snapshot pour audit) |
| `PriceOverride` (Phase 5 optionnelle) | `product_id | category_id`, `group_id`, `override_margin_pct`, `valid_from`, `valid_until` |

### Formule unique

```python
sale_price = cost × (1 + customs_rate_pct/100) × (1 + margin_rate_pct/100) × (1 + vat_rate_pct/100)
```

- Anonymes / non connectés → groupe `default=True` (typiquement « Particulier »).
- Snapshot figé dans `CartItem.unit_price` (déjà existant) puis `OrderLine.unit_price` au checkout : la commande n'est pas affectée par un changement de marge ultérieur.
- Sync Ingram met à jour `cost_amount`, pas `base_price`.

### Groupes prévus

| Groupe | Marge | TVA | Validation admin |
|--------|-------|-----|------------------|
| Particulier (default) | 30% | TVA PF | Non |
| Professionnel | 25% | TVA PF | Oui (justificatif d'entreprise) |
| Revendeur | 12% | TVA PF | Oui (justificatif d'entreprise) |
| Public / Établissements | 18% | TVA PF | Oui (justificatif) |

**Notes** :
- En Polynésie française, tous les groupes sont soumis à la TVA. Le taux exact (et le code) est stocké sur `PriceGroup.vat_rate_pct` pour rester ajustable côté admin.
- Pas de SIRET en PF — le justificatif d'entreprise repose sur le **numéro TAHITI** (ou équivalent local). Le champ doit donc être nommé de façon générique (`business_registration_number` plutôt que `siret`) pour rester portable.
- **Flexibilité géographique** : si à terme on livre hors PF, prévoir un mécanisme de TVA/marge par territoire (extension à un champ `territory_code` sur `PriceGroup`, ou table `PriceGroupTerritoryOverride`). Ne pas ferrer le code sur « TVA PF » comme constante.
- Valeurs gérables via endpoint admin, pas de constantes en dur.

---

## Phase 0 — Stabilisation des bugs critiques

**Objectif** : pouvoir déployer sereinement les phases suivantes sans dette qui se propage.

### Bugs identifiés

| # | Bug | Localisation | Sévérité |
|---|-----|--------------|----------|
| B1 | `_collect_email_targets` utilise des UUIDs comme adresses email → aucun email client n'arrive | [notifications.py:53-65](../../app/features/payment/services/notifications.py#L53-L65) | 🔴 Bloquant |
| B2 | Specs / features / gallery Icecat fetchées puis jetées | [icecat_tasks.py:42-49](../../app/tasks/icecat_tasks.py#L42-L49) | 🔴 Bloquant Phase 1 |
| B3 | `last_supplier_sync` typé `datetime` mais stocké en ISO string | [product.py CRUD:114](../../app/features/product/crud/product.py#L114) vs modèle | 🟠 Risque comparaison |
| B4 | `filter: str` du BaseRouter passé brut à SQLAlchemy `.where()` | [base_router.py:135-145](../../app/api/base_router.py#L135-L145) + [crud.py:454-455](../../app/features/base/crud.py#L454-L455) | 🟠 Audit sécurité |
| B5 | Endpoints tracking/consolidation sans gating admin | [tracking.py](../../app/api/routes/shipping/tracking.py) | 🟠 |
| B6 | Création produit ouverte à tout user authentifié au lieu de superuser | [product.py:28-32](../../app/api/routes/product.py#L28-L32) | 🟠 |
| B7 | `CheckoutMetricsStore` in-memory incompatible multi-replicas | [observability.py:137](../../app/core/observability.py#L137) | 🟡 |
| B8 | Auto-sélection routes shipping greedy par segment ≠ optimum global | [cart.py:271-305](../../app/api/routes/cart.py#L271-L305) | 🟡 |
| B9 | Mapping `last_supplier_sync` String/Datetime à harmoniser dans la migration | alembic | 🟡 |

### Périmètre Phase 0

- ✅ Corriger B1, B2, B3, B4, B5, B6.
- ⏸ B7, B8, B9 peuvent attendre Phase 2/3 si pas bloquant.

---

## Phase 1 — Vitrine catalogue + demande de devis

**Objectif** : un site consultable, un panier, et un bouton « Demander un devis » qui envoie un email à l'admin. Pas de paiement en ligne.

### Périmètre fonctionnel

- Synchro Ingram Micro + Icecat opérationnelle (déjà partiellement présent).
- Catalogue avec prix calculés via la formule (groupe par défaut « Particulier »).
- Recherche par caractéristiques (specs Icecat) + filtres prix, marque, catégorie.
- Panier (déjà présent).
- « Demander un devis » → email au support avec détail panier + coordonnées.
- Produits mis en avant : flag manuel admin.

### Travaux backend

1. **Pricing**
   - Migration : ajout `cost_amount`, `cost_currency`, `customs_rate_pct` sur `Product`.
   - Modèle `PriceGroup` + seed (4 groupes ci-dessus, mais en Phase 1 seul « Particulier » utilisé).
   - Service `app/features/product/services/pricing.py::calculate_sale_price(product, group)`.
   - Adapter [supplier_tasks.py:194-211](../../app/tasks/supplier_tasks.py#L194-L211) : stocker `cost_amount` au lieu d'écraser `base_price`. Calculer `base_price` côté présentation.
   - Snapshot pricing dans `CartItem` (déjà) — pas de modification immédiate côté `OrderLine`.

2. **Persistance Icecat (corrigé en Phase 0)**
   - Migration : `technical_specifications JSONB`, `features JSONB`, table `product_images(product_id, url, role, position, width, height)` ou JSONB `images`.
   - Décommenter [icecat_tasks.py:42-49](../../app/tasks/icecat_tasks.py#L42-L49).
   - Cron Icecat hebdomadaire (re-sync release/EOL).

3. **Recherche**
   - Migration : `tsvector` PostgreSQL sur `name || description || manufacturer || vendor_part_number` + index GIN.
   - Index GIN `gin_trgm_ops` pour la recherche tolérante aux fautes.
   - Index GIN sur `technical_specifications` JSONB pour filtre `WHERE specs @> '{"cpu": "i7"}'`.
   - Endpoint `POST /product/search` avec schéma Pydantic :
     ```json
     {
       "q": "ordinateur portable i7",
       "category_id": "...",
       "manufacturer": "Dell",
       "price_min": 50000, "price_max": 200000,
       "specs": {"memory_gb_min": 16, "cpu": ["i7","i9"]},
       "in_stock": true,
       "limit": 24, "offset": 0
     }
     ```
   - Retour : produits + facettes (counts par marque, par tranche de prix, par valeur de spec).

4. **Produits mis en avant**
   - Migration : `is_featured: bool`, `featured_position: int | null`, `featured_until: datetime | null` sur `Product`.
   - Endpoint admin `POST /product/{id}/feature` + `DELETE`.
   - Endpoint public `GET /product/featured?limit=10`.

5. **Demande de devis**
   - Endpoint `POST /cart/quote-request` (utilisateur connecté) :
     - Lit le panier actif.
     - Envoie un email via Mailgun à `EMAIL_SUPPORT` avec : détail panier (produits, qté, prix calculés), coordonnées client (email, phone, full_name), shipping_address optionnelle, notes.
     - Crée un `QuoteRequest` en BDD pour audit.
   - Pré-requis : bug B1 (email) corrigé en Phase 0.

6. **Préparatifs déploiement**
   - Health-check profond `/healthz/ready` (DB + Redis).
   - Vérification que ARQ worker + outbox poller tournent en prod.
   - Documentation des variables d'environnement (`MAILGUN_*`, `INGRAM_*`, `ICECAT_*`).

### Hors périmètre Phase 1

- Paiement en ligne, OAuth, groupes multiples actifs, tracking client, notifications email post-commande (puisqu'il n'y a pas de commande).

---

## Phase 2 — Compte client complet + CB + Groupes

**Objectif** : commande + paiement en ligne CB de bout en bout, gestion des comptes pros/revendeurs/public avec marges distinctes, login social.

### Périmètre fonctionnel

- Inscription / connexion classique + OAuth Google + Microsoft.
- Profil utilisateur avec préférences (notification, livraison par défaut).
- Validation admin pour groupes « Professionnel », « Revendeur », « Public ».
- Pricing par groupe (les 4 groupes actifs).
- Paiement CB via Payzen (déjà câblé).
- Emails client : « Commande créée », « Paiement validé », « Paiement échoué ».
- Produits mis en avant (continuité Phase 1).

### Travaux backend

1. **Groupes pricing actifs**
   - Activation des 4 `PriceGroup`.
   - Endpoint admin `POST /admin/users/{id}/assign-price-group` + workflow de **validation admin systématique** (pas d'auto-validation) :
     - User soumet une demande (`POST /users/me/upgrade-group` avec `business_registration_number` + attestation libre + groupe cible).
     - Status `PENDING` → admin valide ou rejette via `/admin/group-upgrade-requests/{id}/approve|reject`.
     - À l'approbation, `User.price_group_id` est mis à jour.
     - Le champ d'identification entreprise reste générique (`business_registration_number`) pour porter aussi bien le numéro TAHITI que d'autres formats si on étend ailleurs.
   - Endpoint public `GET /product/{id}` calcule le prix selon le groupe du `current_user` (anonyme = groupe `default=True`).

2. **OAuth Google + Microsoft**
   - Lib : `authlib` (recommandé, supporte les deux providers).
   - Config : `GOOGLE_CLIENT_ID/SECRET`, `MICROSOFT_CLIENT_ID/SECRET/TENANT`.
   - Modèle `UserOAuthLink(user_id, provider, provider_user_id, email_at_link, created_at)`.
   - Endpoints :
     - `GET /auth/{provider}/login` → redirige vers OAuth.
     - `GET /auth/{provider}/callback` → échange code, récupère email/profile, lie ou crée le `User`, émet JWT comme login classique.
   - Email = clé de jonction par défaut ; si conflit (email déjà pris par compte password), exiger confirmation manuelle.

3. **Préférences utilisateur**
   - Modèle `UserPreference(user_id, notification_email_enabled, notification_shipping_steps, default_shipping_preference, locale, currency_pref)`.
   - Endpoints `GET/PUT /users/me/preferences`.
   - Au checkout : si `shipping_preference` absent de `CheckoutRequest`, fallback sur `user.preference.default_shipping_preference` (`fastest|cheapest|eco_friendly`).

4. **Email notifications commande/paiement**
   - Handlers outbox :
     - `order.created` (publish dans `checkout_my_cart` après commit) → email client « Commande reçue ».
     - `payment.captured` (déjà publié) → email client « Paiement validé ».
     - `payment.rejected` (déjà publié) → email client « Paiement échoué ».
   - Réutiliser l'infra [payment/services/notifications.py](../../app/features/payment/services/notifications.py) **avec bug B1 corrigé** : résoudre `user_id` → `user.email` avant l'appel Mailgun.
   - Templates HTML simples (Jinja2) avec branding minimal.

5. **Adresses validées**
   - Workflow `Address.is_validated` (déjà partiellement présent) — exposer endpoints pour valider/lister/supprimer.

6. **Paiement CB en production**
   - Validation end-to-end : initiate → form-token → IPN → outbox → order status.
   - Tests de charge légers sur l'IPN.
   - Page de retour client (frontend) qui poll `GET /payments/{id}` jusqu'à statut terminal.

### Hors périmètre Phase 2

- Chèque / virement / BC, tracking, remboursement, factures.

---

## Phase 3 — Modes de paiement étendus + tracking simple

**Objectif** : couvrir tous les modes de paiement (chèque, virement, BC) avec contrôle d'éligibilité par groupe, et notifier le client des étapes de livraison.

### Périmètre fonctionnel

- Modes de paiement chèque / virement / BC (déjà câblés providers).
- Éligibilité par groupe : ex. BC réservé à « Public » + « Revendeur ».
- Limites monétaires par mode.
- Notifications client `shipping_started` / `shipping_delivered`.
- Endpoint client de suivi de commande.

### Travaux backend

1. **Éligibilité PaymentMethod ↔ PriceGroup**
   - Migration : table `payment_method_eligibility(payment_method_id, price_group_id)` (many-to-many).
   - Champ `max_amount: Decimal | null` sur `PaymentMethod`.
   - Endpoint admin pour configurer.
   - Endpoint `GET /users/me/payment-methods` → filtré par éligibilité du groupe du user + montant du panier courant.
   - Garde-fou dans `POST /payments/initiate` : vérifier éligibilité avant d'initier.

2. **Notifications tracking**
   - Handlers outbox sur transitions de `StatusDefinition` (cf. [status.py](../../app/api/routes/shipping/status.py)) :
     - Statut `shipped` → publish `tracking.shipped` → email client (si préférence active).
     - Statut `delivered` → publish `tracking.delivered` → email client.
   - Hook dans `update_tracking_status` ([tracking.py:326-356](../../app/api/routes/shipping/tracking.py#L326-L356)).
   - Respect de `user.preference.notification_shipping_steps`.

3. **Endpoint client de tracking**
   - `GET /orders/me/{order_id}/tracking` (déjà partiellement : `get_order_tracking` mais à filtrer par `current_user`).
   - Expose `tracking_ref`, `estimated_delivery`, `current_status`, segments, scénarios d'exception.

4. **Bug B5 corrigé** (Phase 0) — confirmer que les endpoints `update_tracking_status` exigent bien admin/logistique.

### Hors périmètre Phase 3

- Regroupement de colis avancé, paiement en plusieurs fois, remboursement.

---

## Phase 4 — Logistique avancée + remboursement

**Objectif** : outiller l'admin logistique pour grouper les colis et gérer les remboursements clients.

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
   - `POST /admin/shipping/consolidation/{id}/add-trackings` (bulk : `[tracking_id, ...]`) — expose la méthode CRUD existante `add_tracking_to_consolidation` ([route_tracking.py:534-570](../../app/features/shipping/crud/route_tracking.py#L534-L570)).
   - `POST /admin/shipping/consolidation/{id}/ship-all` (transition tous les trackings rattachés vers statut `shipped` + propage `tracking_ref` de la consolidation).
   - `POST /admin/shipping/tracking/{id}/ship` (require `tracking_ref` dans le body) → statut shipped + publish outbox.
   - `POST /admin/shipping/tracking/{id}/deliver` → statut delivered.
   - Vue admin `GET /admin/shipping/pending-grouping` (trackings sans consolidation, prêts à grouper).

3. **Remboursement**
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

### Périmètre

| ID | Fonctionnalité | Notes |
|----|----------------|-------|
| M1 | Produits les plus vus | Tracking de vues + endpoint top-N |
| M2 | Déploiement Kubernetes | Helm chart à partir du `docker-compose.prod.yml` |
| M3 | Factures + export comptable | Modèle Invoice + numérotation + PDF + export FEC/CSV Sage |
| M4 | Alerting actif | Job ARQ surveille dashboard → Slack/email sur seuils |
| Z1 | Paiement en plusieurs fois | Dépend Phase 4 (tokenisation Payzen) |
| Z2 | Avoir comptable | Dépend M3 (facture) + Phase 4 (refund) |
| Z3 | Relance paniers abandonnés | Cron horaire + handler outbox `cart.abandoned` |
| Z4 | Recherche IA | Refonte du draft `ia_search_agent.py` (placeholders à remplacer) ; pgvector recommandé |

### Sous-phases possibles

- **Phase 5a** : M3 (factures) — bloque la facturation B2B Polynésie.
- **Phase 5b** : M4 (alerting actif) + M2 (K8s) — fiabilité prod.
- **Phase 5c** : Z3 (relance panier) + M1 (produits populaires) — leviers commerciaux.
- **Phase 5d** : Z1 + Z2 (paiement N×, avoir).
- **Phase 5e** : Z4 (recherche IA, optionnel).

---

## Dépendances inter-phases

```
Phase 0 (bugs)
  ├─→ Phase 1 (catalogue) → B1+B2+B6 corrigés requis
  └─→ Phase 2 (CB+OAuth)  → B1 corrigé requis pour les emails

Phase 1 → Phase 2 (groupes activés sur le pricing posé en P1)
Phase 2 → Phase 3 (les emails P2 servent aussi tracking P3)
Phase 3 → Phase 4 (les hooks de transition statut sont étendus)
Phase 4 → Phase 5d (tokenisation préparée en P4 pour Z1/Z2)
M3 (P5a) doit précéder Z2 (P5d)
```

---

## Risques / points d'attention transverses

| Risque | Mitigation |
|--------|------------|
| Le `CheckoutMetricsStore` in-memory rendra les métriques incohérentes en multi-replicas (B7) | Migrer vers Redis en Phase 2 (avant scale-out) |
| Auto-sélection routes shipping non globalement optimale (B8) | Acceptable pour Phase 1-2 (devis manuel) ; à corriger avant Phase 3 |
| OAuth : conflit email password/social | Décider en Phase 2 : refus + message vs liaison après validation par email |
| Sync Ingram = écrasement du `cost_amount` côté pricing | Vérifier qu'aucune logique métier ne s'appuie sur le `base_price` pré-Phase 1 |
| Migrations alembic destructrices sur `Product` (B9 + ajouts cost_amount, customs_rate, JSONB specs) | Une seule migration de fond début Phase 1, plutôt que plusieurs accumulées |
| Hypothèse « PF only » figée dans le code (TVA, marges, libellés) | Stocker TVA et marges dans `PriceGroup`, jamais en constante ; prévoir un `territory_code` futur sur `PriceGroup` |
| Identification entreprise non-portable si extension hors PF | Champ générique `business_registration_number` (jamais `siret`) dès la Phase 2 |
| Templates email manquants | Préparer les 4 templates (commande, payé, échec, livré) en Phase 2 pour ne pas bloquer le déploiement |
| Données Icecat dépendantes de credentials Open vs Full | Vérifier que le périmètre P1 fonctionne en Open Icecat (gratuit) |

---

## Estimation effort (rough order of magnitude)

| Phase | Effort backend | Effort frontend (vitrine) | Total |
|-------|----------------|---------------------------|-------|
| 0 | S (3-5 j) | — | S |
| 1 | L (3-4 sem) | M (2 sem vitrine) | L |
| 2 | XL (5-7 sem) | L (3 sem) | XL |
| 3 | M (2-3 sem) | M (1-2 sem) | M |
| 4 | L (3-4 sem) | M (2 sem admin) | L |
| 5 | XL (à découper en 5a-5e) | variable | XL |

S = ≤1 sem, M = 1-3 sem, L = 3-6 sem, XL = >6 sem.

Ces estimations sont des ordres de grandeur pour un dev expérimenté seul ; à recalibrer selon ressources et taille des templates email/PDF.
