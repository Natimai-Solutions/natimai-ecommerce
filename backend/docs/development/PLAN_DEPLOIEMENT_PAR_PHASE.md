# Plan de déploiement par paliers

Document de travail établi à partir de la vérification fonctionnelle (cf. [PLAN_VERIFICATION_FONCTIONNEMENT.md](PLAN_VERIFICATION_FONCTIONNEMENT.md)). Chaque phase est conçue pour être déployable en production de façon autonome, le frontend pouvant s'enrichir au même rythme.

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
- L'ancienne formule (douane sur coût seul) est **caduque** ; `calculate_sale_price()` et `shared/utils/src/pricing.ts` sont à reprendre.

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

### Jalons par phase

| Phase | Livrable fret import |
|-------|----------------------|
| **1** | CAF dans `calculate_sale_price()` (part variable + assurance) ; **poids taxable** (max poids/volume) dans `calculate_shipping_for_routes` + `dim_factor_kg_per_m3`/`billing_basis` lus depuis `route_metadata` ; capture des **dimensions physiques** à l'enrichissement Icecat (+ fallback poids) ; champs `customer_label` + `is_default_import` + `service_level` sur `ShippingRoute` + migration ; **corridor unique France→Papeete** seedé ; payload `shipping_modes` + `default_mode` sur la fiche produit ; `pricing.ts` étendu CAF ; dropdown front + persistance du choix (`localStorage` anonyme) ; `preferred_shipping_mode` lu s'il est présent |
| **2** | `preferred_shipping_mode` éditable dans les préférences utilisateur (cf. item *Préférences utilisateur* P2) ; snapshot `service_level` / `import_route_id` / `fret_import_snapshot` figé sur `OrderLine` au checkout |
| **3** | **Mapping multi-fournisseurs** : `Product.supplier_partner_id` (ou table de correspondance) ; corridors multiples (US, Asie…) ; résolution `service_level → route` par corridor + fallback nearest-tier ; cohérent avec la refonte route auto-sélection (B8) |

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

## Phase 0 — Stabilisation des bugs critiques

**Objectif** : pouvoir déployer sereinement les phases suivantes sans dette qui se propage.

**Statut** : ✅ Réalisée (18/05/2026)

### Bugs identifiés

| # | Bug | Localisation | Sévérité | Statut |
|---|-----|--------------|----------|--------|
| B1 | `_collect_email_targets` utilise des UUIDs comme adresses email → aucun email client n'arrive | [notifications.py](../../app/features/payment/services/notifications.py) | 🔴 Bloquant | ✅ Corrigé |
| B2 | Specs / features / gallery Icecat fetchées puis jetées | [icecat_tasks.py](../../app/tasks/icecat_tasks.py) + migration [3b5d9a1c7e42](../../app/alembic/versions/3b5d9a1c7e42_add_icecat_payload_columns_to_products.py) | 🔴 Bloquant Phase 1 | ✅ Corrigé |
| B3 | `last_supplier_sync` typé `datetime` mais stocké en ISO string | [product.py CRUD](../../app/features/product/crud/product.py) vs modèle | 🟠 Risque comparaison | ✅ Corrigé |
| B4 | `filter: str` du BaseRouter passé brut à SQLAlchemy `.where()` | [base_router.py](../../app/api/base_router.py) + [crud.py](../../app/features/base/crud.py) | 🟠 Audit sécurité | ✅ Corrigé |
| B5 | Endpoints tracking/consolidation sans gating admin | [tracking.py](../../app/api/routes/shipping/tracking.py) | 🟠 | ✅ Corrigé |
| B6 | Création produit ouverte à tout user authentifié au lieu de superuser | [product.py](../../app/api/routes/product.py) | 🟠 | ✅ Corrigé |
| B7 | `CheckoutMetricsStore` in-memory incompatible multi-replicas | [observability.py:137](../../app/core/observability.py#L137) | 🟡 | ⏸ Reporté Phase 2 |
| B8 | Auto-sélection routes shipping greedy par segment ≠ optimum global | [cart.py:271-305](../../app/api/routes/cart.py#L271-L305) | 🟡 | ⏸ Reporté Phase 3 |
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

**Statut** : 🟡 En cours (backend + correction CAF/fret import complets le 28/05/2026 ; validation d'intégration + régénération `schema.ts` restantes)

### Avancement backend (22/05/2026)

- ✅ Pricing runtime : modèles `PriceGroup` / `TaxRate`, résolution taxe + calcul prix, adaptation sync fournisseur sur `cost_amount`.
- ✅ API catalogue Phase 1 : `POST /product/search`, `GET /product/featured`, `POST/DELETE /product/{id}/feature` (admin).
- ✅ Demande de devis : `POST /cart/quote-request` avec persistance `QuoteRequest` + envoi email support.
- ✅ Checkout : snapshot `OrderLine.tax_rate_id` ajouté.
- ✅ Readiness/liveness : endpoints `/healthz/liveness` et `/healthz/ready` (DB + Redis).
- ✅ **Devises** : modèle `CurrencyRate` + migration `d1e5c3f8a294` + helper `convert_to_xpf()` intégré dans `calculate_sale_price()` + snapshots FX sur `CartItem`/`OrderLine` + endpoints admin `GET/PUT /admin/currency-rates`.
- ✅ **Dé-localisation devise de référence** (pré-prod, 28/05/2026) : `REFERENCE_CURRENCY` en config (défaut XPF) ; `convert_to_xpf→convert_to_reference_currency` ; colonne `rate_to_xpf→rate_to_reference` (migration `c5d9e2f1a8b4`, suivi de `d1e5c3f8a294`) ; `costAmountXpf/costXpf→costInReference` (`pricing.ts` + `schema.ts`) ; checks `=="XPF"` → `settings.REFERENCE_CURRENCY`. 362 tests OK. ⚠️ `alembic upgrade head` à passer en intégration ; `schema.ts` édité à la main (à régénérer depuis l'OpenAPI).
- ✅ **Catalogue specs filtrables** : table `product_spec` + migration `e3b7a1c9d5f2` + `spec_definitions.yaml` (10 specs Ordinateur/Serveur) + projection dans `enrich_product_with_icecat_task` + `upsert_product_specs()` + endpoint `GET /product/categories/{id}/spec-facets` + job ARQ `reproject_product_specs_task`.
- ✅ **Filtre `is_enriched=True`** sur endpoints publics (`search`, `featured`, `GET /products`, `GET /product/{id}` → 404 si non enrichi sauf superuser).
- ✅ **Enqueue auto enrichment** à la création d'un produit supplier_managed dans `SupplierSyncOrchestrator.sync_products_to_database` (post-commit).
- ✅ **Recherche avancée PostgreSQL** : extension `pg_trgm` + index GIN FTS (`ix_products_search_fts`) + index GIN trgm sur `name` (`ix_products_name_trgm`) — migration `f2a4b8c1d9e3` ; `search_products()` utilise `to_tsvector @@ plainto_tsquery` avec classement `ts_rank`.
- ✅ **Seed CurrencyRate** USD/EUR automatique via `initial_data.py` (plus de config manuelle nécessaire au premier déploiement).
- ✅ **`meets_sync_thresholds` — conversion XPF** : `supplier_tasks.py` appelle `convert_to_xpf()` avant le check ; `meets_sync_thresholds()` reçoit `price_in_xpf` (fallback sur prix brut si `CurrencyRateMissing`). `SUPPLIER_SYNC_MIN_PRICE` est désormais interprété en XPF quelle que soit la devise fournisseur.
- ✅ **Documentation ops** : [OPS_ENV_ET_CHECKS.md](OPS_ENV_ET_CHECKS.md) — variables d'environnement par catégorie, checklist premier déploiement, checks ARQ/outbox/taux FX en prod.
- ✅ **Fret import / CAF** (28/05/2026) : `calculate_sale_price()` calcule désormais la douane sur l'assiette CAF (`cost_in_reference + price_per_kg×billable_weight + assurance`) ; champs `service_level`/`customer_label`/`is_default_import` sur `ShippingRoute` (migration `a3b1c7e2d9f5`) + config `INSURANCE_RATE_PCT` (défaut 0) ; **poids taxable** `resolve_billable_weight()` = `max(poids, volume×dim_factor)` avec `dim_factor_kg_per_m3`/`billing_basis` lus depuis `route_metadata` (défauts avion 167 / mer 1000) intégré à `calculate_shipping_for_routes` (param `total_volume_m3`, fallback poids réel) ; **dimensions physiques Icecat** mappées vers `Product.dimensions_*`/`weight` (`icecat_service.py` + `icecat_tasks.py`) ; `calculate_price_by_mode()` → `list[ShippingModePrice]` ; **corridor France→Papeete** seedé (`initial_data.py` : places `FR_SUPPLIERS`/`PPT_CUSTOMS_WAREHOUSE` + routes avion/bateau) ; endpoint `GET /product/{id}/shipping-modes` (`shipping_modes` + `default_mode`) ; `pricing.ts` étendu CAF (`freightInReference`/`insuranceInReference`) ; dropdown niveau de service dans `ProductPage.vue` + `ProductDetailsDialog.vue` (recalcul local, persistance `localStorage`). 23 tests CAF/shipping verts (`test_product_pricing_caf.py`, `test_pricing.py`). Résidu reporté P2 : câblage `preferred_shipping_mode` (le champ `User`/`UserPreference` est créé en P2).
- 🟡 Migration/seed Phase 1 : à valider en environnement d'intégration. **Têtes alembic** : `a3b1c7e2d9f5` (unique head, chaîne `…→f2a4b8c1d9e3→c5d9e2f1a8b4→a3b1c7e2d9f5`). `alembic upgrade head` + seed `initial_data` à passer en intégration (upgrade/downgrade + non-régression). `schema.ts` édité à la main → à régénérer depuis l'OpenAPI.

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

1bis. **Fret import & assiette douane (CAF)** — cf. *Décision transverse : fret import & assiette douane (CAF)*.
   - Migration : `customer_label`, `is_default_import`, `service_level` sur `shipping_routes` ; config `insurance_rate_pct`.
   - Refonte `calculate_sale_price()` : assiette CAF = `cost_in_xpf + price_per_kg(route)×billable_weight + assurance`, douane appliquée sur la CAF (et non sur le coût seul).
   - **Poids taxable** : helper `resolve_billable_weight(weight_kg, volume_m3, route)` = `max(poids, volume × dim_factor)` ; `dim_factor_kg_per_m3` + `billing_basis` lus depuis `route_metadata` (fallback défaut par mode en config) ; intégration dans `calculate_shipping_for_routes` (étendu pour accepter le volume) ; fallback poids réel si dimensions absentes/incomplètes.
   - **Enrichissement** : mapper les dimensions physiques + poids Icecat vers `Product.dimensions_*`/`weight` dans `icecat_service.py` (aujourd'hui seules les dims d'images sont mappées).
   - Fonction `calculate_price_by_mode(product, group, import_routes)` → tableau `{ service_level: { freight, sale_price, eta_days, carbon } }`.
   - Seed du **corridor unique France→Papeete** : routes import avion/bateau avec `service_level` + `customer_label` + `is_default_import`.
   - Fiche produit : exposer `shipping_modes` + `default_mode`.
   - `shared/utils/src/pricing.ts` : étendre `PricingInput` (`freightXpf`, `insuranceXpf`) → `afterCustoms = (cost + freight + insurance) × (1 + customs%)`.
   - Frontend : dropdown niveau de service (recalcul **local**, pas de refetch) + persistance `localStorage` (anonyme) / `preferred_shipping_mode` (connecté).
   - Mise à jour des tests pricing produit pour la CAF.

2. **TVA / TGC**
   - Migration : modèle `TaxRate` (`code`, `label`, `rate_pct`, `territory_code`, `valid_from`, `valid_until`).
   - Migration : `Category.default_tax_rate_id` (FK nullable) + `Product.tax_rate_id` (FK nullable).
   - Migration : `OrderLine.tax_rate_id` (FK, snapshot figé au checkout).
   - Seed des 3 taux PF (`TGC_NORMAL 16%`, `TGC_REDUIT 5%`, `TGC_EXONERE 0%`).
   - Service `resolve_tax_rate(product, territory) -> TaxRate` dans `pricing.py`.
   - En Phase 1 : toutes les catégories héritent de `TGC_NORMAL` par défaut ; ajustement manuel possible en admin pour les catégories alimentaires.

2. **Persistance Icecat (corrigé en Phase 0)**
   - ✅ Livré : colonnes `technical_specifications`, `features`, `icecat_images` sur `products` + activation du mapping dans [icecat_tasks.py](../../app/tasks/icecat_tasks.py).
   - Action résiduelle Phase 1 : activer le cron Icecat hebdomadaire (re-sync release/EOL).

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

5. **Devises**
   - Migration : table `currency_rates` (`currency_code`, `rate_to_xpf`, `valid_from`, `valid_until`, `source`, `updated_by_user_id`).
   - Migration : snapshots FX sur `CartItem` (`fx_rate_used`, `fx_source_currency`) et `OrderLine` (`cost_amount_snapshot`, `cost_currency_snapshot`, `fx_rate_used`, `customs_rate_pct_snapshot`, `margin_rate_pct_snapshot`, `price_group_id_snapshot`).
   - Helper `convert_to_xpf(amount, currency, at_date)` dans `pricing.py`.
   - Intégration dans `calculate_sale_price()` (conversion **avant** la formule douane × marge × TVA) et dans `_meets_sync_thresholds()` (`SUPPLIER_SYNC_MIN_PRICE` en XPF).
   - Snapshot du `fx_rate_used` à la création de `CartItem` (et propagation au checkout dans `OrderLine`).
   - Seed initial : `USD→XPF` et `EUR→XPF` (valeurs à figer manuellement avant déploiement).
   - Endpoints admin : `GET /admin/currency-rates`, `PUT /admin/currency-rates/{code}` (crée un nouveau taux, clôture l'ancien).
   - Garde-fou `calculate_sale_price` : `CurrencyRateMissing` si aucun taux actif trouvé pour la devise du produit.

6. **Catalogue de specs filtrables**
   - Migration : table `product_spec` (`product_id`, `spec_key`, `value_text`, `value_numeric`, `unit`) + 3 indices.
   - Fichier `app/features/product/spec_definitions.yaml` avec 10 specs Ordinateur/Serveur (cf. décision transverse).
   - Logique de projection JSONB → `product_spec` ajoutée dans `enrich_product_with_icecat_task` (et `batch_enrich_products_task`).
   - Enqueue automatique de `trigger_product_enrichment` à la création d'un nouveau `is_supplier_managed=True` dans [supplier_sync_orchestrator.py](../../app/features/integrations/services/supplier_sync_orchestrator.py).
   - Filtre `is_enriched=True` sur les endpoints publics catalogue (search, featured, list, fiche → 404 si non enrichi).
   - Endpoint `GET /categories/{id}/spec-facets` (specs disponibles + valeurs + counts pour la catégorie).
   - `POST /product/search` interprète `specs: {memory_gb_min: 16, cpu_family: ["i7","i9"]}` → JOIN `product_spec` avec filtres numériques/énumérés.
   - Job ARQ `reproject_product_specs(category_id=None)` pour re-projeter après modification du YAML.

7. **Demande de devis**
   - Endpoint `POST /cart/quote-request` (utilisateur connecté) :
     - Lit le panier actif.
     - Envoie un email via Mailgun à `EMAIL_SUPPORT` avec : détail panier (produits, qté, prix calculés), coordonnées client (email, phone, full_name), shipping_address optionnelle, notes.
     - Crée un `QuoteRequest` en BDD pour audit.
   - Pré-requis : bug B1 (email) corrigé en Phase 0.

8. **Préparatifs déploiement**
   - Health-check profond `/healthz/ready` (DB + Redis).
   - Vérification que ARQ worker + outbox poller tournent en prod.
   - Documentation des variables d'environnement (`MAILGUN_*`, `INGRAM_*`, `ICECAT_*`, `SUPPLIER_SYNC_MIN_PRICE` en XPF).

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

1. **TVA / TGC — admin CRUD**
   - `GET /admin/tax-rates` (liste avec filtres `territory_code`, `valid`).
   - `POST /admin/tax-rates` (créer un nouveau taux, ne remplace pas l'ancien).
   - `PUT /admin/tax-rates/{id}` (modifier `label` ou fixer `valid_until` pour clôturer).
   - `PUT /admin/products/{id}/tax-rate` et `PUT /admin/categories/{id}/tax-rate`.
   - Garde-fou : interdire la modification de `rate_pct` sur un taux existant (créer un nouveau avec `valid_from` à la place).

2. **Groupes pricing actifs**
   - Activation des 4 `PriceGroup`.
   - Endpoint admin `POST /admin/users/{id}/assign-price-group` + workflow de **validation admin systématique** (pas d'auto-validation) :
     - User soumet une demande (`POST /users/me/upgrade-group` avec `business_registration_number` + attestation libre + groupe cible).
     - Status `PENDING` → admin valide ou rejette via `/admin/group-upgrade-requests/{id}/approve|reject`.
     - À l'approbation, `User.price_group_id` est mis à jour.
     - Le champ d'identification entreprise reste générique (`business_registration_number`) pour porter aussi bien le numéro TAHITI que d'autres formats si on étend ailleurs.
   - Endpoint public `GET /product/{id}` calcule le prix selon le groupe du `current_user` (anonyme = groupe `default=True`).

3. **RBAC — activation des permissions par groupe**
   - Seed des groupes de sécurité initiaux : `support`, `logistics_admin`, `payment_admin` (chacun avec `group_type='security'`).
   - Pour chaque groupe, créer les règles `GroupSecurity` par table (ex. `payment_admin` : can_read + can_update sur `payments`).
   - Passer `ENABLE_GROUP_PERMISSIONS=true` en prod **après** avoir vérifié que le superuser et les users existants fonctionnent correctement (le superuser bypass est inconditionnel ; les users sans groupe de sécurité ne sont pas restreints).
   - Assigner les groups de sécurité aux membres de l'équipe admin concernés.
   - Note : `CrudBase.check_user_permission()` est déjà implémenté et contrôlé par ce flag.

4. **OAuth Google + Microsoft**
   - Lib : `authlib` (recommandé, supporte les deux providers).
   - Config : `GOOGLE_CLIENT_ID/SECRET`, `MICROSOFT_CLIENT_ID/SECRET/TENANT`.
   - Modèle `UserOAuthLink(user_id, provider, provider_user_id, email_at_link, created_at)`.
   - Endpoints :
     - `GET /auth/{provider}/login` → redirige vers OAuth.
     - `GET /auth/{provider}/callback` → échange code, récupère email/profile, lie ou crée le `User`, émet JWT comme login classique.
   - Email = clé de jonction par défaut ; si conflit (email déjà pris par compte password), exiger confirmation manuelle.

5. **Préférences utilisateur**
   - Modèle `UserPreference(user_id, notification_email_enabled, notification_shipping_steps, default_shipping_preference, locale, currency_pref)`.
   - Endpoints `GET/PUT /users/me/preferences`.
   - Au checkout : si `shipping_preference` absent de `CheckoutRequest`, fallback sur `user.preference.default_shipping_preference` (`fastest|cheapest|eco_friendly`).

6. **Email notifications commande/paiement**
   - Handlers outbox :
     - `order.created` (publish dans `checkout_my_cart` après commit) → email client « Commande reçue ».
     - `payment.captured` (déjà publié) → email client « Paiement validé ».
     - `payment.rejected` (déjà publié) → email client « Paiement échoué ».
   - Réutiliser l'infra [payment/services/notifications.py](../../app/features/payment/services/notifications.py) **avec bug B1 corrigé** : résoudre `user_id` → `user.email` avant l'appel Mailgun.
   - Templates HTML simples (Jinja2) avec branding minimal.

7. **Adresses validées**
   - Workflow `Address.is_validated` (déjà partiellement présent) — exposer endpoints pour valider/lister/supprimer.

8. **Commande automatique chez Ingram Micro (SUPPLIER_DIRECT)**
   - **Déclencheur** : handler outbox sur `payment.captured` — pas sur `create.order` (évite de commander si le paiement échoue). Pour les paiements différés (BC, chèque), la commande Ingram est émise à la validation admin.
   - **Modèle** `SupplierOrder` (nouveau) : `local_order_id`, `supplier_name`, `supplier_order_id` (PO Ingram), `status`, `estimated_delivery`, `raw_response JSONB`, `created_at`, `last_sync_at`.
   - **Méthode** `IngramMicroService.create_purchase_order(order, lines)` :
     - Filtre les `OrderLine` avec segment `SUPPLIER_DIRECT` et `product.supplier_name == "ingram_micro"`.
     - Mappe vers le format attendu par l'API Ingram (endpoint + payload — **doc API requise avant dev**, cf. point d'attention ci-dessous).
     - Stocke la réponse dans `SupplierOrder`.
   - **Retry** : 3 tentatives avec backoff exponentiel (ARQ) ; en cas d'échec définitif, alerte email admin + statut `SupplierOrder.status = "failed"`.
   - **Endpoint admin** `GET /admin/supplier-orders` (liste + filtres `status`, `supplier_name`) + `POST /admin/supplier-orders/{id}/retry` (relance manuelle).
   - **Point d'attention** : la doc Ingram pour la création d'ordre (endpoint `POST /resellers/v6/orders` ou équivalent, format payload, gestion du PO number, auth webhook retour) doit être obtenue **avant** de démarrer ce chantier. Le stock est déjà décrémenter au checkout — le risque n'est pas la double-réservation mais la commande Ingram manquée.

9. **Paiement CB en production**
   - Validation end-to-end : initiate → form-token → IPN → outbox → order status.
   - Tests de charge légers sur l'IPN.
   - Page de retour client (frontend) qui poll `GET /payments/{id}` jusqu'à statut terminal.

### Hors périmètre Phase 2

- Chèque / virement / BC, tracking, remboursement, factures.
- Webhook Ingram de suivi statut commande fournisseur (reporté Phase 3).

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

4. **Webhook Ingram — suivi statut commande fournisseur**
   - Endpoint `POST /webhooks/ingram/order-status` (auth par signature ou token Ingram).
   - Met à jour `SupplierOrder.status` + `estimated_delivery` à chaque callback.
   - Publish outbox `supplier_order.shipped` → alimente le tracking interne (transition vers statut `shipped` sur la consolidation concernée).
   - Pré-requis : doc Ingram webhook obtenue en Phase 2.

5. **Bug B5 corrigé** (Phase 0) — confirmer que les endpoints `update_tracking_status` exigent bien admin/logistique.

6. **Catalogue de specs — extension multi-catégories**
   - Migration : table `spec_definition(id, key, label_i18n, type, unit, category_ids[], aliases[])` éditable via admin.
   - Migration progressive du YAML `spec_definitions.yaml` vers la table (script one-shot + suppression du YAML).
   - Endpoints admin `GET/POST/PUT/DELETE /admin/spec-definitions`.
   - UI admin pour gérer specs + aliases par catégorie (incluant test de match contre un produit donné).
   - Étendre le seed aux nouvelles catégories Ingram à syncer en P3 (à définir selon priorités produit).
   - Re-projection automatique déclenchée par chaque modification de spec.

7. **Devises — préparation P4**
   - Champ système `default_display_currency` (admin, default `XPF`).
   - Endpoint `GET /system/settings` exposant la devise par défaut au frontend (pour préparer le toggle multi-devises P4).

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

### Périmètre

| ID | Fonctionnalité | Notes |
|----|----------------|-------|
| M1 | Produits les plus vus | Tracking de vues + endpoint top-N |
| M2 | Déploiement Kubernetes | Helm chart à partir du `docker-compose.prod.yml` |
| M3 | Factures + export comptable | Modèle Invoice + numérotation + PDF (avec ventilation TVA par taux via `OrderLine.tax_rate_id`) + export FEC/CSV Sage |
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
