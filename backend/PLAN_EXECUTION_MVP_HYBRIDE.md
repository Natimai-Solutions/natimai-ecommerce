# Plan de reprise MVP ecommerce hybride

Date: 2026-05-07

Objectif cible (MVP utile):
- Import automatique fournisseur (Ingram) + enrichissement (Icecat)
- Produits manuels vendables au meme titre
- Commande + paiement fonctionnels
- Fulfillment hybride (fournisseur, local, consolidation Polynesie)
- Tracking client lisible de bout en bout

Hors scope immediat (a geler):
- Reductions/coupons
- Wishlist
- Features marketing et IA non critiques

---

## 1) Etat actuel en une page

Ce qui est deja en place:
- Endpoints integration Ingram et Icecat exposes
- Worker ARQ + cron Ingram + taches Icecat actives
- Modele produit etat hybride (supplier fields + champs enrichissement)
- Paiement PayZen present avec IPN
- Briques shipping/tracking avancees presentes

Points bloquants majeurs pour le MVP:
- Incoherences de contrats CRUD entre routes/services et base CRUD
- Modeles avec champs a casse mixte, doublons, ou incomplets (plantent au demarrage ou a l'execution)
- Pipeline sync Ingram non finalise (historique sync non persiste)
- Flux checkout coeur manquant (pas de panier/checkout dedie)
- Quelques signatures incoherentes dans tracking/paiement
- Securite d'acces objet desactivee (check_user_permission retourne toujours True)

---

## 2) Cible d'architecture (simple et maintenable)

Principe de repartition de logique:
- Routes API: validation HTTP, auth, reponses
- Services metier: orchestration cas d'usage
- Services integration externe: appels API Ingram/Icecat uniquement
- CRUD: acces DB atomique, sans logique de workflow
- Tasks ARQ: declenchement async de services metier, pas de logique metier riche

Changements d'emplacement recommandes:
- Garder les appels HTTP Ingram dans [backend/app/services/ingram_micro_service.py](app/services/ingram_micro_service.py).
- Sortir la logique de sync DB et upsert produit de [backend/app/services/ingram_micro_service.py](app/services/ingram_micro_service.py) vers un orchestrateur metier integration (service dedie) qui pilote:
  - lecture API fournisseur
  - mapping donnees
  - upsert produit
  - sync log
- Faire des tasks Ingram/Icecat des wrappers minces autour des services metier, au lieu de contenir du workflow.
- Centraliser la logique checkout (commande + lignes + paiement + routing fulfilment) dans un service unique de cas d'usage.
- Garder [backend/app/features/integrations/crud/ingram_sync.py](app/features/integrations/crud/ingram_sync.py) comme acces persistance des logs/mappings, sans logique d'orchestration.

---

## 3) Ecarts techniques critiques a traiter en premier

### 3.1 Contrats CRUD incoherents
Statut: RESOLU le 2026-05-07 (routes alignees sur read/update/delete).

- La base CRUD expose read/create/update/delete:
  - [backend/app/features/base/crud.py#L359](app/features/base/crud.py#L359)
  - [backend/app/features/base/crud.py#L622](app/features/base/crud.py#L622)
  - [backend/app/features/base/crud.py#L840](app/features/base/crud.py#L840)
  - [backend/app/features/base/crud.py#L1063](app/features/base/crud.py#L1063)
- Mais des routes appellent get/remove (10 occurrences confirmees par recherche exhaustive `crud_*.(get|remove)\(`):
  - [backend/app/api/routes/address.py#L91](app/api/routes/address.py#L91)
  - [backend/app/api/routes/address.py#L134](app/api/routes/address.py#L134)
  - [backend/app/api/routes/address.py#L160](app/api/routes/address.py#L160)
  - [backend/app/api/routes/address.py#L167](app/api/routes/address.py#L167) (remove)
  - [backend/app/api/routes/user_review.py#L91](app/api/routes/user_review.py#L91)
  - [backend/app/api/routes/user_review.py#L143](app/api/routes/user_review.py#L143)
  - [backend/app/api/routes/user_review.py#L167](app/api/routes/user_review.py#L167)
  - [backend/app/api/routes/user_review.py#L174](app/api/routes/user_review.py#L174) (remove)
  - [backend/app/api/routes/user_notification.py#L126](app/api/routes/user_notification.py#L126)
  - [backend/app/api/routes/user_notification.py#L195](app/api/routes/user_notification.py#L195) (remove)

Action:
- Uniformiser tous les appels sur read/update/delete de la base CRUD.
- Refaire la recherche `crud_\w+\.(get|remove)\(` avant merge pour valider qu'il n'en reste aucun.

### 3.2 CRUD integrations avec signatures incorrectes
Statut: RESOLU le 2026-05-07 (ingram_sync aligne sur read/update(id=...)).

- Appels update avec record_id + get inexistant (la base CRUD attend `id=`):
  - [backend/app/features/integrations/crud/ingram_sync.py#L83](app/features/integrations/crud/ingram_sync.py#L83)
  - [backend/app/features/integrations/crud/ingram_sync.py#L110](app/features/integrations/crud/ingram_sync.py#L110)
  - [backend/app/features/integrations/crud/ingram_sync.py#L124](app/features/integrations/crud/ingram_sync.py#L124)
  - [backend/app/features/integrations/crud/ingram_sync.py#L372](app/features/integrations/crud/ingram_sync.py#L372)

Action:
- Corriger les signatures pour utiliser read + update(id=..., data=...).

### 3.3 Paiement: signature create incoherente
Statut: RESOLU le 2026-05-07 (create_payment_with_log aligne sur create_draft + commit explicite).

- Appel create avec commit=False non supporte par base CRUD:
  - [backend/app/features/payment/crud/payment.py#L103](app/features/payment/crud/payment.py#L103)
- Utilise depuis PayZen form-token:
  - [backend/app/api/routes/payzen.py#L81](app/api/routes/payzen.py#L81)

Action:
- Aligner create_payment_with_log sur create_draft + commit explicite, ou adapter a l'API CRUD standard.

### 3.4 Tracking: mismatch de parametres
Statut: RESOLU le 2026-05-08 (contrat update_status harmonise: support new_status_id cote CRUD, mapping changed_by/reason cote route, compatibilite conservee pour new_status interne).

- CRUD attend new_status string:
  - [backend/app/features/shipping/crud/route_tracking.py#L85](app/features/shipping/crud/route_tracking.py#L85)
  - [backend/app/features/shipping/crud/route_tracking.py#L89](app/features/shipping/crud/route_tracking.py#L89)
- Route envoie new_status_id, user_id, reason:
  - [backend/app/api/routes/shipping/tracking.py#L202](app/api/routes/shipping/tracking.py#L202)
  - [backend/app/api/routes/shipping/tracking.py#L203](app/api/routes/shipping/tracking.py#L203)
  - [backend/app/api/routes/shipping/tracking.py#L204](app/api/routes/shipping/tracking.py#L204)

Action:
- Harmoniser le contrat update_status entre route et service CRUD.

### 3.5 Securite d'acces objet trop permissive
- Permission par defaut toujours vraie:
  - [backend/app/features/base/crud.py#L328](app/features/base/crud.py#L328)
  - [backend/app/features/base/crud.py#L335](app/features/base/crud.py#L335)

Action:
- Implementer check_user_permission par domaine sensible (order, payment, address, review, notification).

### 3.6 Modeles avec champs a casse mixte
Statut: RESOLU le 2026-05-07 (Partner/Place alignes en minuscules + migration de renommage conditionnelle).

Champs declares avec une majuscule cote modele mais accedes en minuscule cote CRUD: SQLAlchemy/Python est case-sensitive, ces requetes plantent au premier appel.

- Partner:
  - Modele: [backend/app/features/partner/models.py#L24](app/features/partner/models.py#L24) declare `Email`
  - CRUD: [backend/app/features/partner/crud.py#L24](app/features/partner/crud.py#L24) utilise `Partner.email`
- Place:
  - Modele: [backend/app/features/place/models.py#L28](app/features/place/models.py#L28) declare `Latitude`
  - Modele: [backend/app/features/place/models.py#L29](app/features/place/models.py#L29) declare `Longitude`
  - CRUD: [backend/app/features/place/crud.py#L154](app/features/place/crud.py#L154) utilise `Place.latitude`
  - CRUD: [backend/app/features/place/crud.py#L155](app/features/place/crud.py#L155) utilise `Place.longitude`

Action:
- Renommer les champs modele en minuscule (`email`, `latitude`, `longitude`) pour aligner sur le reste du codebase et la convention Python.
- Generer une migration Alembic pour renommer les colonnes en base si elles ont deja ete creees.

### 3.7 Doublons dans le modele Review
Statut: RESOLU le 2026-05-07 (champ doublons supprimes + classe ReviewUpdate unique avec validator).

Champs et classes redefinis dans le meme module: comportement non deterministe (la derniere definition gagne, mais tout outil de typage signalera l'erreur).

- [backend/app/features/user/models/review.py#L17](app/features/user/models/review.py#L17) `rating` declare une 1ere fois
- [backend/app/features/user/models/review.py#L21](app/features/user/models/review.py#L21) `rating` redeclare (perd `default`/`description` du 1er)
- [backend/app/features/user/models/review.py#L18](app/features/user/models/review.py#L18) `comment` declare une 1ere fois
- [backend/app/features/user/models/review.py#L22](app/features/user/models/review.py#L22) `comment` redeclare
- [backend/app/features/user/models/review.py#L37](app/features/user/models/review.py#L37) `class ReviewUpdate` definie une 1ere fois (avec field_validator)
- [backend/app/features/user/models/review.py#L55](app/features/user/models/review.py#L55) `class ReviewUpdate` redefinie (sans validator) -- ecrase la precedente

Action:
- Garder une seule declaration de chaque champ et une seule classe `ReviewUpdate` (celle qui inclut le validator de rating).

### 3.8 Modele Brand incomplet
Statut: RESOLU le 2026-05-07 (option retenue: completion Brand, table/schemas/CRUD/route coherents).

Le module brand ne contient que `BrandProductBase`: pas de table SQL, pas de schemas `BrandCreate`/`BrandUpdate`/`BrandPublic`, donc impossible a manipuler via CRUD ou exposer en API.

- [backend/app/features/product/models/brand.py](app/features/product/models/brand.py) (23 lignes seulement)

Action:
- Decider du scope: si brand est dans le MVP, completer le modele (table, schemas, CRUD, route auto) ; sinon supprimer le fichier pour ne pas laisser de code mort.

### 3.9 Outbox: champ correlation_id non declare
Statut: RESOLU le 2026-05-07 (champ ajoute au modele + migration).

Le registre persiste un champ que le modele de table ne possede pas. Plantera au flush de la session.

- Registre passe `correlation_id`: [backend/app/outbox/registry.py#L93](app/outbox/registry.py#L93)
- Modele OutboxEvent ne le declare pas: [backend/app/outbox/models.py](app/outbox/models.py)

Action:
- Ajouter `correlation_id: UUID | None = Field(default=None, index=True)` au modele OutboxEvent.
- Generer la migration Alembic correspondante.

### 3.10 Migration Alembic vide (corps a passe)
Statut: RESOLU le 2026-05-07 (22abd completee et migration suivante ajustee pour eviter les doublons).

La migration de fields PayZen ne fait rien. Le schema n'a donc jamais ete applique formellement, alors que le modele Payment les utilise.

- [backend/app/alembic/versions/22abd6580004_add_payzen_fields_to_payments.py#L20](app/alembic/versions/22abd6580004_add_payzen_fields_to_payments.py#L20)

Action:
- Soit ecrire le contenu reel (op.add_column pour chaque champ PayZen ajoute au modele Payment), soit supprimer cette revision et regenerer une migration via `alembic revision --autogenerate`.

### 3.11 Endpoint refresh token absent
Statut: RESOLU le 2026-05-08 (endpoint POST /login/refresh-token ajoute, rotation systematique activee, revocation persistante en DB via user_refresh_tokens).

Le modele de requete existe mais aucune route ne le consomme. Le refresh token genere au login devient inutile cote client.

- Modele present: [backend/app/features/user/models/user.py#L160](app/features/user/models/user.py#L160) (`RefreshTokenRequest`)
- Login: [backend/app/api/routes/login.py](app/api/routes/login.py) (47 lignes, aucune route `/refresh`)

Action:
- Ajouter `POST /login/refresh-token` qui valide le refresh token et emet un nouveau access token (et eventuellement rote le refresh token).
- Definir une strategie de revocation (table de tokens revoques OU rotation systematique avec invalidation cote DB).

---

## 4) Plan d'execution detaille (8 a 10 semaines)

## Phase A0 - Correctifs modeles bloquants (Semaine 1, jours 1-2)

A faire avant tout le reste: ces bugs cassent l'execution ou la coherence du schema. Tant qu'ils ne sont pas corriges, A1-A4 risquent de masquer ou aggraver les symptomes.

Livrable phase A0:
- L'application peut demarrer, les modeles sont coherents, le schema DB est aligne.

Checklist:
- [x] A0.1 Renommer Partner.Email -> partner.email et Place.Latitude/Longitude -> place.latitude/longitude (modeles + migration de renommage).
- [x] A0.2 Nettoyer review.py: supprimer doublons rating/comment et la 2eme classe ReviewUpdate.
- [x] A0.3 Decider sort de Brand: completer (table + schemas + CRUD + route) OU supprimer brand.py.
- [x] A0.4 Ajouter correlation_id au modele OutboxEvent + migration.
- [x] A0.5 Reecrire ou regenerer la migration vide 22abd6580004 pour les champs PayZen.
- [x] A0.6 Verifier en local: `alembic upgrade head` from-scratch passe sans erreur (valide via docker compose sur DB temporaire fastapi_ecommerce_a0_check).

Definition of Done phase A0:
- L'app demarre sans erreur de modele.
- `alembic upgrade head` from-scratch fonctionne sur une base vide.
- Aucun champ modele n'utilise de casse mixte non-conventionnelle.

---

## Phase A - Stabilisation socle (Semaines 1-2)

Livrable phase A:
- Backend coherent, routes executables, signatures alignees, migration propre.

Checklist:
- [x] A1 Corriger les 10 appels get/remove vers read/delete dans routes user/address/review/notification (liste exhaustive en 3.1).
- [x] A2 Corriger signatures dans CRUD integrations Ingram (read/update standards, plus de record_id).
- [x] A3 Corriger le flux create_payment_with_log pour qu'il respecte la base CRUD.
- [x] A4 Harmoniser route tracking et CRUD update_status (signature commune).
- [x] A5 Ajouter tests de non-regression minimum sur routes corrigees.
- [x] A6 Ajouter endpoint refresh token + strategie de rotation/revocation (cf. 3.11).
- [x] A7 Reactiver le routeur paiement principal commente dans [backend/app/api/__init__.py#L32](app/api/__init__.py#L32) une fois A3 valide.
- [x] A8 Rejouer migration from-scratch en local et verifier seed initial (valide sur DB temporaire fastapi_ecommerce_a8_check).

Definition of Done phase A:
- Aucun endpoint critique ne plante sur mismatch de signature.
- Lint + tests backend passent sur le socle corrige.
- Refresh token utilisable cote client.

---

## Phase B - Catalogue hybride fiable (Semaines 3-4)

Livrable phase B:
- Import Ingram robuste + enrichissement Icecat + produits manuels coherents.

Checklist:
- [x] B1 Finaliser les sync logs Ingram (plus de TODO) et exposer dernier sync dans health.
- [x] B2 Sortir la logique d'upsert et de commit par produit du service API vers orchestrateur metier integration.
  - Orchestrateur metier: [backend/app/features/integrations/services/ingram_sync_orchestrator.py](app/features/integrations/services/ingram_sync_orchestrator.py)
  - Appel depuis la tache: [backend/app/tasks/ingram_micro_tasks.py](app/tasks/ingram_micro_tasks.py)
- [x] B3 Implementer idempotence stricte par supplier_name + supplier_sku + mapping persiste.
- [x] B4 Verifier creation/edition de produits manuels sans ecrasement par sync fournisseur.
- [x] B5 Normaliser et valider les champs prix/stock fournisseur avant publication produit.
- [x] B6 Aligner le modele de prix sur Decimal (ou montants entiers en centimes) de maniere coherente: produit, commande, paiement.
  - Statut: RESOLU le 2026-05-08. `payments.amount` et `payment_logs.amount` passent de INTEGER (centimes) a NUMERIC(12,2), alignes sur Order/OrderLine/Product. Conversion en centimes confinee a la frontiere PayZen (decimal_to_minor_units / minor_units_to_decimal).
  - Migration: [backend/app/alembic/versions/7d4c2e1a9b30_payments_amount_to_decimal.py](app/alembic/versions/7d4c2e1a9b30_payments_amount_to_decimal.py)
  - Tests de non-regression: [backend/app/tests/api/test_phase_b6_payment_amount_decimal.py](app/tests/api/test_phase_b6_payment_amount_decimal.py)

Definition of Done phase B:
- Un import complet Ingram + enrichissement Icecat peut tourner sans intervention manuelle.
- Produit manuel et produit fournisseur cohabitent avec statuts clairs.
- Aucun champ prix ne melange float et Decimal entre couches.

---

## Phase C - Checkout et paiement essentiels (Semaines 5-7)

Livrable phase C:
- Flux vente complet client: panier -> checkout -> paiement -> confirmation.

Checklist:
- [x] C1 Ajouter panier persistant (cart et cart items).
- [x] C2 Ajouter endpoint checkout transactionnel unique (creation commande + lignes + total + reservation stock + creation paiement).
- [x] C3 Figer les montants au checkout (snapshot lignes + frais).
- [x] C4 Verifier disponibilite stock fournisseur/local au checkout.
- [x] C5 Relier commande et paiement proprement (etats coherents).
- [x] C6 Durcir IPN PayZen (idempotence + gestion retries).
  - Form token: [backend/app/api/routes/payzen.py#L56](app/api/routes/payzen.py#L56)
  - Lookup paiement: [backend/app/api/routes/payzen.py#L176](app/api/routes/payzen.py#L176)
- [x] C7 Solidifier outbox: aligner schema evenement / modele / registry / handlers, ajouter idempotence cote consommateur.
  - Statut: COMPLETE le 2026-05-09. correlation_id desormais propage par la base CRUD (create_draft / update_draft / delete_draft) avec record.id comme valeur par defaut, permettant le tracage du cycle de vie par entite.
  - Sites de propagation: [backend/app/features/base/crud.py#L630](app/features/base/crud.py#L630), [backend/app/features/base/crud.py#L834](app/features/base/crud.py#L834), [backend/app/features/base/crud.py#L1056](app/features/base/crud.py#L1056)
  - Tests de non-regression: [backend/app/tests/api/test_phase_c7_outbox_consumer_idempotency.py](app/tests/api/test_phase_c7_outbox_consumer_idempotency.py) (3 tests verifient correlation_id == record.id pour create/update/delete)

Definition of Done phase C:
- Un client peut aller jusqu'au paiement sans blocage technique.
- Toute transaction a un etat commande/paiement coherent et retracable.
- Les evenements outbox sont publies et consommes de maniere idempotente.

---

## Phase D - Fulfillment hybride Polynesie + tracking (Semaines 8-9)

Livrable phase D:
- Routage fulfillment hybride + suivi client comprehensible.

Checklist:
- [x] D1 Definir et implementer regles d'orchestration:
  - segment fournisseur direct
  - segment local
  - segment consolidation PF
  - Statut: COMPLETE le 2026-05-09. Orchestration appliquee au checkout avec segmentation explicite local/supplier_direct/consolidation_pf et persistence de la synthese par ligne de commande (notes).
  - Implementation: [backend/app/api/routes/cart.py](app/api/routes/cart.py)
  - Tests: [backend/app/tests/api/test_phase_d1_fulfillment_orchestration.py](app/tests/api/test_phase_d1_fulfillment_orchestration.py)
- [x] D2 Relier ces segments aux objets tracking existants.
  - Statut: COMPLETE le 2026-05-09. Les segments agreges au checkout sont relies aux objets tracking existants via creation de ShippingRouteTracking par segment (sequence ordonnee), resolution route/statut/adresse, et creation de ShippingRouteTrackingConsolidation pour le segment consolidation_pf.
  - Implementation: [backend/app/api/routes/cart.py](app/api/routes/cart.py)
  - Tests: [backend/app/tests/api/test_phase_d2_tracking_segment_linkage.py](app/tests/api/test_phase_d2_tracking_segment_linkage.py)
- [x] D3 Exposer un statut global commande derive des segments.
  - Statut: COMPLETE le 2026-05-09. Endpoint tracking commande calcule un overall_status derive des segments via StatusDefinition route_tracking (priorite erreur, sinon premier segment non terminal par sequence_order, sinon dernier terminal), et expose current_route_sequence coherent.
  - Implementation: [backend/app/api/routes/shipping/tracking.py](app/api/routes/shipping/tracking.py)
  - Tests: [backend/app/tests/api/test_phase_d3_order_global_status.py](app/tests/api/test_phase_d3_order_global_status.py)
- [x] D4 Ajouter scenarios d'exception (retard fournisseur, split colis, echec segment).
  - Statut: COMPLETE le 2026-05-09. Endpoint order tracking expose des `exception_scenarios` derives des segments: `supplier_delay` (retard fournisseur), `parcel_split` (split colis: sequence duplicate ou marqueur note), `segment_failure` (statut erreur hors retard fournisseur).
  - Implementation: [backend/app/api/routes/shipping/tracking.py](app/api/routes/shipping/tracking.py)
  - Tests: [backend/app/tests/api/test_phase_d4_tracking_exception_scenarios.py](app/tests/api/test_phase_d4_tracking_exception_scenarios.py)

Definition of Done phase D:
- Une commande hybride affiche des etats utiles cote client et admin.

Points d'attention Phase D (releves a la verification du 2026-05-09, non bloquants):
- [cart.py#L218](app/api/routes/cart.py#L218): `postal_code="00000"` code en dur dans le fallback d'adresse (`_resolve_tracking_address_for_checkout`). Acceptable MVP, mais pourrait surprendre une validation downstream (carriers, exports comptables). A revoir si le client saisit une adresse de livraison structuree.
- [cart.py#L796](app/api/routes/cart.py#L796): les erreurs du linkage tracking sont avalees (log warning + continue) dans `checkout_my_cart`. Choix delibere (tracking non critique), mais une commande peut exister sans tracking. Prevoir un job de reconciliation ou alerte cote E2 (logs/dashboards) pour detecter ces cas.
- [cart.py#L322](app/api/routes/cart.py#L322): `_get_or_create_tracking_status` pour `entity="consolidation"` est appele meme sans segment PF. Inefficacite mineure (un get + create one-shot), pas un bug. A inliner sous condition `if FulfillmentSegment.CONSOLIDATION_PF in segment_totals`.
- [cart.py#L86-L94](app/api/routes/cart.py#L86-L94): le marker `"PF"` (2 caracteres) est matche en substring sur l'adresse upper-case. Risque theorique de faux positif sur des chaines contenant "PF" hors contexte Polynesie. Considerer un match a frontiere de mot (split sur virgule + comparaison de tokens) si des cas reels remontent.

---

## Phase E - Fiabilisation exploitation (Semaine 10)

Livrable phase E:
- Produit exploitable sans suivi quotidien.

Checklist:
- [ ] E1 Tests integration E2E des parcours critiques (login -> catalogue -> panier -> checkout -> paiement -> tracking -> historique).
- [ ] E2 Logs structures et tableaux de bord minimaux (jobs, erreurs, delais, metriques paiement/commande, alertes erreurs checkout).
- [ ] E3 Runbook operationnel (relance sync, relance job, traitement IPN en echec).
- [ ] E4 Checklist pre-prod et plan rollback.

Definition of Done phase E:
- Tu peux laisser tourner plusieurs jours et reprendre rapidement avec vision claire.

---

## 5) Ordre de priorite strict (si temps limite)

Priorite 0 (bloquant go-live):
- A0.1 A0.2 A0.4 A0.5 A0.6
- A1 A2 A3 A4 A5 A7 A8
- B1 B3 B4
- C1 C2 C3 C5 C6
- D1 D2 D3

Priorite 1 (juste apres):
- A0.3 (selon decision scope Brand)
- A6 (refresh token)
- B2 B5 B6
- C4 C7
- D4
- E1

Priorite 2 (confort exploitation):
- E2 E3 E4

---

## 6) Cadence de travail si tu n'es pas dessus chaque jour

Rythme minimal viable (2 a 3 sessions par semaine):
- Session 1 (60-90 min): execution d'une tache atomique + commit
- Session 2 (60-90 min): test/regression + correction
- Session 3 (30-45 min): revue board + plan de la prochaine tache

Regle anti-derive:
- Ne jamais ouvrir plus de 1 chantier P0 a la fois.
- Une tache = un critere de fini testable.
- Toujours finir par une note de reprise dans ce document.

Template de note de reprise:
- Date:
- Tache en cours:
- Ce qui est termine:
- Ce qui bloque:
- Prochaine action (max 1h):

---

## 7) Checkpoints hebdomadaires (15 min)

Questions a valider chaque semaine:
- Les modeles sont-ils tous coherents (casse, doublons, completude)?
- Les signatures routes/services/CRUD sont-elles coherentes?
- Le sync Ingram a-t-il un historique fiable et consultable?
- Le flux commande->paiement est-il testable sans mock lourd?
- Le tracking client est-il comprehensible sans support humain?

Si reponse non sur un point P0:
- geler les nouvelles features
- corriger immediatement le point bloquant

---

## 8) Carte des points d'entree actuels (utile pour reprendre vite)

API active integrations et coeur:
- [backend/app/api/__init__.py#L37](app/api/__init__.py#L37)
- [backend/app/api/__init__.py#L42](app/api/__init__.py#L42)
- [backend/app/api/__init__.py#L53](app/api/__init__.py#L53)
- [backend/app/api/__init__.py#L59](app/api/__init__.py#L59)
- [backend/app/api/__init__.py#L62](app/api/__init__.py#L62)

Routes disponibles aujourd'hui (sans cart/checkout dedies):
- voir les routeurs inclus dans [backend/app/api/__init__.py](app/api/__init__.py)

Routeur paiement principal commente (a reactiver apres A3):
- [backend/app/api/__init__.py#L32](app/api/__init__.py#L32)

---

## 9) Prochaine action immediate recommandee

Demarrer par la phase A0 (correctifs modeles) avant tout le reste.

Premier pas concret: A0.1 (renommer Partner.Email et Place.Latitude/Longitude en minuscule).

Temps cible A0 complet:
- 0.5 a 1 jour si Brand est supprime
- 1 a 2 jours si Brand est complete

Risques:
- regression silencieuse si des seeds/fixtures referencent les anciens noms de champs
- migration de renommage qui echoue sur une base avec donnees existantes

Mitigation:
- recherche globale sur les anciens noms (`Email`, `Latitude`, `Longitude`) avant le rename
- tester `alembic upgrade head` puis `alembic downgrade -1` puis `alembic upgrade head` sur une copie de base avec donnees representatives
