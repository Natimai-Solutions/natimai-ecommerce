# Audit fonctionnel natimai-ecommerce : solidité et manques (novembre 2026)

> Audit du 15/11/2026, sur la branche de la PR 191 (commit `45d56b2`). Il
> complète [`AUDIT_2026-11.md`](AUDIT_2026-11.md) (sécurité, bugs, UI/UX) sans
> le refaire : la question est ici « les fonctionnalités tiennent-elles, et
> lesquelles manquent ». Les actions retenues sont reprises dans
> [`PLAN_DE_TRAVAIL.md`](PLAN_DE_TRAVAIL.md) (identifiants D·, Z·, M·).
>
> Les chemins backend sans préfixe sont relatifs à `backend/app/`.

## Méthode

- **Trois relectures parallèles :** parcours client, back-office et exploitation, moteur métier et qualité du code.
- **Lecture du code uniquement :** rien n'a été exécuté de bout en bout (ni serveurs, ni prestataires de paiement réels). Les constats de concurrence et de performance sont déduits du code.
- **Constats revérifiés à la main :** D1, D3, D4.

## 1. Ce qui est solide

- **Factures et avoirs :** compteur par exercice sous verrou, contenu figé, chaîne d'intégrité, API en lecture seule (`features/invoice/services/numbering.py:51-86`).
- **Checkout :** un seul commit couvre commande, lignes, réservation de stock, coupon, paiement et événement `order.created` (`api/routes/cart.py`, `checkout_my_cart`).
- **Recherche et filtres du catalogue**, compte client, catégories et caractéristiques, contenus, réglages et modules.
- **Migrations :** 108 révisions, une seule tête, toutes réversibles.
- **Reprise de la synchro fournisseurs :** par lots de 50, délai de grâce avant de désactiver un produit disparu, champs édités par l'admin préservés.

## 2. Défauts à corriger avant l'ouverture

| # | Constat | Où | Correctif |
|---|---|---|---|
| D1 | **Le fret d'import n'est facturé nulle part.** La fiche produit affiche le prix du mode choisi, fret inclus ; la liste, le panier et la commande calculent le prix sans route, donc sans fret ; le checkout exclut le tronçon d'import des frais parce qu'il serait « déjà dans le prix ». Le coût de revient, donc la marge affichée, ignore aussi le fret. | `cart.py` (`_price_for_customer`), `features/product/crud/product.py:169,233`, `product_catalog.py:205`, `cart.py:361-363` | « Pas de route » = route d'import par défaut ; mode d'import porté par la ligne de panier et la ligne de commande ; test de parité fiche / panier / commande. |
| D2 | **Une commande impayée ne peut pas être repayée.** Après un refus de carte, un abandon PayPal ou un rechargement pendant le formulaire, la commande existe et le panier est vidé ; aucun écran ne propose de payer. `POST /payments/initiate` l'accepte pourtant. L'e-mail `payment_rejected` n'a pas de lien. | `frontend/src/pages/PaymentReturnPage.vue:43-62`, `OrderTrackingPage.vue`, `BalancePaymentPage.vue` | Bouton « Payer » sur la fiche commande et la page de retour, lien dans l'e-mail, rappel des instructions de virement. |
| D3 | **Le devis est inaccessible au client.** Store, API, page de confirmation, admin, PDF et e-mail existent ; aucun composant n'appelle `sendQuoteByEmail`. | `frontend/src/stores/cart.ts:334`, `router/routes.ts:35` | Bouton « Demander un devis » dans le panier. |
| D4 | **Sauvegardes sans copie hors site.** Le cron pose `BACKUP_REMOTE`, le script lit `OFFSITE_RCLONE_REMOTE` ; le cron pointe `/opt/fastapi-ecommerce`, la doc `/opt/natimai-ecommerce`. En stockage S3, seul le volume local (vide) est archivé. | `scripts/backup/ecommerce-backup.cron:17`, `scripts/backup/backup.sh:33,76-78` | Aligner cron, script et doc ; couvrir le cas S3 ; signal « dernière sauvegarde réussie ». |
| D5 | **Checkout sans protection contre la double soumission.** Aucune clé d'idempotence, panier lu sans verrou : deux POST simultanés créent deux commandes. Les verrous de stock sont tenus pendant l'appel au prestataire de paiement (30 s). | `cart.py` (`checkout_my_cart`), `features/cart/crud/cart.py:33-48` | Verrou du panier, clé d'idempotence, appel prestataire hors de la section verrouillée. |
| D6 | **Taux de change manquant ou expiré : erreur 500** sur la fiche produit et le panier ; le produit reste publiable. | `features/product/crud/product.py:134`, `cart.py` | Produit non vendable et bloqué à la publication tant que le taux manque. |
| D7 | **Erreurs de checkout brutes.** Une rupture affiche « Insufficient stock for product <uuid> » ; 68 des 121 codes d'erreur des routes client n'ont pas de message. | `cart.py:239-247`, `core/error_messages.py`, `frontend/src/pages/CheckoutPage.vue:1199` | Messages en français et en anglais, ligne désignée, quantité ajustable. |

## 3. Zones fragiles

### Exploitation
- **Z1. Pannes silencieuses.** Seule la synchro catalogue alerte. La synchro prix et stock renvoie « success » avec des erreurs (`tasks/supplier_tasks.py:441-466`), le recalcul nocturne des prix n'est que journalisé (`tasks/pricing_tasks.py:112`), aucun seuil d'alerte sur les e-mails en échec (`features/notification/mailer.py`). 12 tâches planifiées sans journal d'exécution.
- **Z2. Outbox.** `DONE` veut dire « mis en file » : un handler abandonné après 8 essais ne laisse qu'un log (`outbox/consumer.py:55-112`). Chaque écriture CRUD publie un événement, même sans handler ; une synchro de 10^5 produits peut retarder un `payment.captured`. Purge jamais planifiée.
- **Z3. Supervision.** `/healthz/ready` ne teste que la base et Redis ; un poller arrêté n'alerte pas ; un worker « unhealthy » n'est pas redémarré.
- **Z4. Déploiement.** Pas de dump avant migration ; une version en échec de santé reste en service (`scripts/release/deploy.sh:57-81`).
- **Z5. Rétention.** `email_log` garde destinataires et corps sans purge ; `cleanup_old_logs` n'est jamais appelé.

### Back-office
- **Z6. Statuts de commande.** Aucune table de transitions : `Delivered → Pending` ou `Cancelled → Paid` passent (`features/order/services/status.py:161-212`). Le sélecteur applique sans confirmation ni motif ; « Étape suivante » d'un départ écrit à tous ses clients en un clic.
- **Z7. Factures dans l'admin.** Liste limitée aux 100 dernières, sans recherche ; export FEC sans bouton ; émission ratée non rattrapable sans shell (`admin_invoices.py:85-105,169`).
- **Z8. Synchro fournisseurs.** Pas d'historique à l'écran, endpoints Icecat et maintenances sans écran, aucun garde-fou sur un saut de coût.
- **Z9. Stock.** Pas de journal des mouvements à l'écran, recherche sans SKU, aucun test sur `admin_inventory`.
- **Z10.** Créer ou supprimer un groupe de prix passe par la base ; une commande fournisseur en erreur ne peut qu'être relancée.

### Moteur
- **Z11. Départs groupés.** Pas de clôture automatique à la date limite : entre-temps `get_next_open` renvoie `None` et les commandes partent sans départ (`features/departure/services.py:197`). Le délai annoncé ignore le transit d'import et le délai fournisseur.
- **Z12. Exercice fiscal en UTC.** Une facture émise le 31/12 après 14 h à Tahiti prend le numéro de l'année suivante (`invoice_service.py:397-407`).
- **Z13. Commande modifiable après facturation** par le PUT générique (`features/order/models/order.py:183-199`).
- **Z14. Montée en charge.** Recherche : tolérance aux fautes sans index utilisable, CTE rejouée pour le total, la page et chaque facette (`features/product/crud/product.py:764-1010`). Synchro : tous les produits chargés en mémoire, `job_timeout` de 600 s.
- **Z15. Cache des prix.** Pas rafraîchi sur la marge d'un groupe de prix, le pays ou le régime douanier d'un lieu ; rattrapage au cron de 00:05.

### Parcours client
- **Z16.** Un échec de chargement des modes de livraison laisse partir la commande sans mode (`CheckoutPage.vue:1068`).
- **Z17.** L'adresse n'a ni destinataire, ni téléphone, ni société ; pas d'adresse de facturation.
- **Z18.** `order_created` ne contient que numéro, total et nombre d'articles. Pas d'e-mail pour un retard de départ, une décision de groupe tarifaire ou une demande de devis reçue.
- **Z19.** Pages catégorie non indexables (canonical unique `/catalogue`, absentes du sitemap), pas de `hreflang`.

### Tests
- **Z20.** Le seuil de 68 % exclut de la mesure `services/suppliers/ingram_micro.py` (750 lignes) et `services/icecat_service.py`. 70 modules ne sont référencés par aucun test. Aucun e2e sur un paiement carte, l'acompte puis le solde, les codes promo, l'anglais ou le mobile ; aucun test de charge.

## 4. Fonctionnalités à ajouter

Aucune n'était au plan. Taille : S ≤ 1 jour, M 2 à 5 jours, L > 5 jours.

| # | Fonctionnalité | Pourquoi ici | Taille |
|---|---|---|---|
| M1 | Page « État du système » et alertes d'exploitation | À une ou deux personnes, une panne ne s'apprend que par un client | M |
| M2 | Suivi des encours (soldes dus, virements en attente), relance et annulation automatiques | L'acompte immobilise de la trésorerie sur de la marchandise importée | S à M |
| M3 | Identité de facturation B2B (raison sociale, n° TAHITI, adresse distincte) | Facture d'un professionnel difficilement exploitable sans elle | M |
| M4 | E-mail de confirmation complet ; notification de retard d'un départ | Pièce de référence du client pendant des semaines d'attente | S + M |
| M5 | Commande et devis créés par l'admin (comptoir, téléphone) | Usage courant d'un revendeur informatique local | L |
| M6 | Rupture partielle après commande (annuler ou substituer une ligne, remboursement et avoir par ligne) | Les manques sont détectés à la clôture d'un départ, rien ne les traite | M à L |
| M7 | Garde-fou sur les coûts fournisseur (saut de plus de X %, coût à 0) | Un coût divisé par dix est appliqué tel quel | M |
| M8 | Destinataire et téléphone sur l'adresse ; page contact | Nécessaires au transporteur et aux livraisons dans les îles | S |
| M9 | Pages catégorie et marque indexables | La recherche locale se gagne sur ces pages | M |
| M10 | Export des paiements, rapport de ventes par taux de TVA | Besoin mensuel du comptable | M |
| M11 | Historique des synchros, écran Icecat, boutons de maintenance | Le catalogue se pilote aujourd'hui en curl | S à M |
| M12 | Journal des mouvements de stock, filtre stock bas, inventaire par import | Aucun outil pour vérifier un retour en stock manuel | M |
| M13 | Outils RGPD côté admin, purges planifiées | Demandes reçues par courrier ou d'un invité | S à M |
| M14 | Demande d'avis après livraison ; e-mail de décision de groupe tarifaire ; carte cadeau saisissable au checkout | Petits ajouts à forte visibilité | S chacun |

## 5. Maintenabilité

- **Taille :** 87 632 lignes d'application, 56 399 de tests.
- **Fichiers les plus lourds :** `api/routes/cart.py` (3 792 lignes, `checkout_my_cart` 530), `api/routes/payments.py` (1 459), `handlers/payment.py` (1 058), `features/product/services/pricing.py` (1 041). Le découpage de `cart.py` (plan §8) mérite de monter en priorité.
- **Doublons :** formule de prix en deux exemplaires (`calculate_sale_price`, `PricingContext.price`), 9 fonctions `get_or_create_*status`, deux pollers d'outbox.
- **Code mort :** `features/analytic`, `features/partner`, `user/crud/notification.py` (≈ 1 000 lignes sans appelant), `utils/price.py`, handler `create.product` vide, `example_handler`.
- **Modules désactivables :** `logistics_multileg`, `suppliers`, `customs`, `currencies` et `price_groups` masquent des écrans mais leur moteur reste actif.

## 6. Non vérifié

- Comportement réel de PayZen, PayPal et Ingram (la sandbox de paiement n'a jamais été jouée).
- Constats de concurrence et de performance : déduits du code, sans mesure.
- État du serveur : cron de sauvegarde, rclone, webhook d'alerte, sonde externe.
- Rendu des e-mails et des PDF, version anglaise, mobile, hydratation SSR.
