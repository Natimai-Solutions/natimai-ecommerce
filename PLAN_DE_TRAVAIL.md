# Plan de déploiement par paliers

Document de travail établi à partir de la vérification fonctionnelle (cf. [PLAN_VERIFICATION_FONCTIONNEMENT.md](backend/docs/development/done/PLAN_VERIFICATION_FONCTIONNEMENT.md)). Chaque phase est conçue pour être déployable en production de façon autonome, le frontend pouvant s'enrichir au même rythme.

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

> ⚠️ Reste à traiter en **Phase 2** (cf. item *Taxonomie interne & facettes specs*) : dropdown Catégorie vide et filtre par spec (CPU…) inopérants — cause racine : les produits fournisseurs ne sont jamais rattachés à une `Category` interne (`category_id = None`), alors que les facettes catégorie ET le panneau `spec-facets` en dépendent.

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| Catalogue + recherche FTS | ✅ | ✅ `CataloguePage.vue` | — |
| Specs filtrables (facettes) | ✅ | ⏳ filtres specs (report P2) | 🔲 édition specs (API en P3, UI à faire) |
| Fiche produit + modes transport (CAF) | ✅ | ✅ `ProductPage.vue` + dropdown niveau de service | — |
| Panier | ✅ | ✅ `CartPage.vue` | — |
| Demande de devis | ✅ | ✅ `CartQuoteConfirmationPage.vue` | 🔲 consultation des `QuoteRequest` |
| Produits mis en avant | ✅ | ✅ `GET /product/featured` consommé | 🔲 toggle featured dans `ProductsPage.vue` |
| Pricing / TVA / devises (socle) | ✅ | — | 🔲 écrans config (taux → P2, devises → P4) |

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
- ✅ **Documentation ops** : [OPS_ENV_ET_CHECKS.md](backend/docs/development/OPS_ENV_ET_CHECKS.md) — variables d'environnement par catégorie, checklist premier déploiement, checks ARQ/outbox/taux FX en prod.
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
   - ✅ Seed 3 taux PF (`TGC_NORMAL 16%`, `TGC_REDUIT 5%`, `TGC_EXONERE 0%`).
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
   - ✅ [OPS_ENV_ET_CHECKS.md](backend/docs/development/OPS_ENV_ET_CHECKS.md) : variables d'environnement par catégorie, checklist premier déploiement, checks ARQ/outbox/taux FX en prod.

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
| Adresses self-service + validation | ✅ | ✅ `MyAccountPage.vue` (onglet Adresses, CRUD) | 🔲 validation des adresses |
| Demande d'upgrade de groupe | ✅ | 🔲 formulaire upgrade (justificatif) | 🔲 écran validation des demandes |
| TVA / TGC — admin CRUD | ✅ `/admin/tax-rates` | — | 🔲 écran taux |
| Paiement CB (Payzen) | ✅ | ✅ `CheckoutPage.vue` + `PaymentReturnPage.vue` | — |
| Emails commande / paiement | ✅ | — (transactionnel) | — |
| Commande auto Ingram (SUPPLIER_DIRECT) | ✅ | — | 🔲 écran `supplier-orders` + retry |
| Taxonomie / catégories internes | ✅ | ⏳ dropdown catégorie | 🔲 fusion / renommage catégories |

### Avancement vitrine (19/06/2026)

- ✅ **Espace « Mon compte »** (`MyAccountPage.vue`, route `/mon-compte` name `account`, entrée nav toolbar + drawer visible si connecté ; redirection `login?redirect=/mon-compte` si anonyme).
  - ✅ Onglet **Préférences** : `GET/PUT /users/me/preferences` — toggles notifications (email, suivi expédition) + selects niveau de service import, préférence livraison, langue, devise. Bannières succès/erreur (Quasar `Notify` non activé dans ce projet).
  - ✅ Onglet **Adresses** : CRUD `/users/me/addresses` (liste cartes + badge `is_validated`, dialog création/édition, confirmation suppression).
  - Modules API : [frontend/src/api/account.ts](frontend/src/api/account.ts) · [frontend/src/api/addresses.ts](frontend/src/api/addresses.ts). Typecheck (`vue-tsc`) + lint verts.
- 🔲 **Reste vitrine P2** : formulaire **demande d'upgrade de groupe** (nécessite un endpoint public de liste des `PriceGroup` + lecture du groupe courant — ajouts backend à prévoir).
- 🔲 **Reste vitrine P3** : page **suivi de commande** (`OrderTrackingPage.vue` → `GET /orders/me/{id}/tracking`).

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
   - Code erreur `address.already_validated` enregistré dans ERROR_CODES.md (non levé actuellement — l'endpoint est idempotent).
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
   - Résolution adoptée : option (b) — `get_or_create` par `supplier_subcategory`, fusion/renommage admin a posteriori.
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
| Éligibilité paiement ↔ groupe | ✅ | ✅ méthodes filtrées au checkout | 🔲 écran éligibilité (`/admin/payment-methods/{id}/groups`) |
| Notifications tracking (expédié / livré) | ✅ | — (email) | — |
| Suivi de commande client | ✅ `/orders/me/{id}/tracking` + `GET /orders/me` | ✅ `MyAccountPage.vue` (onglet Commandes) + `OrderTrackingPage.vue` | — |
| Webhook Ingram — statut fournisseur | ✅ | — | 🔲 visible via écran `supplier-orders` (backlog P2) |
| **Catalogue specs éditable (multi-cat.)** | ✅ `/admin/spec-definitions` | — | 🔲 **écran CRUD specs + alias** |
| Devises — display setting | ✅ `/system/settings` | 🔲 toggle devise (→ P4) | 🔲 écran `system-settings` |

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

### Travaux admin-frontend (à faire)

> Les endpoints sont livrés (✅ backend) mais aucun écran ne les pilote encore (`admin-frontend` = `LoginPage` + `ProductsPage` seulement). Modèle de découpage à répliquer pour les autres phases :
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

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| Permission logistique (`logistics_admin`) | 🔲 | — | 🔲 |
| Endpoints ship / deliver / consolidate | 🔲 | — | 🔲 écran logistique + consolidation bulk |
| Devises — auto + multi-affichage | 🔲 | 🔲 sélecteur de devise | 🔲 écran taux FX + alerte > 30 j |
| Remboursement total / partiel | 🔲 | 🔲 statut remboursement (compte) | 🔲 écran remboursement |

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
| M1 — produits les plus vus | 🔲 | 🔲 section accueil / carrousel | — |
| M3 — factures PDF (**WeasyPrint**) + export FEC | 🔲 | 🔲 téléchargement facture (compte) | 🔲 écran factures + export comptable |
| Z2 — avoir comptable | 🔲 | 🔲 affichage avoir | 🔲 écran avoir |
| Z3 — relance paniers abandonnés | 🔲 | — | 🔲 dashboard relances |
| Z4 — recherche IA | 🔲 | 🔲 UI recherche sémantique | — |

### Périmètre

| ID | Fonctionnalité | Notes |
|----|----------------|-------|
| M1 | Produits les plus vus | Tracking de vues + endpoint top-N |
| M2 | Déploiement Kubernetes | Helm chart à partir du `docker-compose.prod.yml` |
| M3 | Factures + export comptable | Modèle Invoice + numérotation + PDF **WeasyPrint** (avec ventilation TVA par taux via `OrderLine.tax_rate_id`) + export FEC/CSV Sage — cf. *Note technique — génération PDF des factures* ci-dessous |
| M4 | Alerting actif | Job ARQ surveille dashboard → Slack/email sur seuils |
| Z1 | Paiement en plusieurs fois | Dépend Phase 4 (tokenisation Payzen) |
| Z2 | Avoir comptable | Dépend M3 (facture) + Phase 4 (refund) |
| Z3 | Relance paniers abandonnés | Cron horaire + handler outbox `cart.abandoned` |
| Z4 | Recherche IA | Refonte du draft `ia_search_agent.py` (placeholders à remplacer) ; pgvector recommandé |

### Note technique — génération PDF des factures (M3)

**Bibliothèque retenue : WeasyPrint** (rendu HTML/CSS → PDF), cohérent avec l'approche HTML déjà utilisée pour les emails (`_build_quote_email_html` dans `cart.py`) et avec Jinja2 déjà présent dans les dépendances. Un template Jinja2 de facture (HTML + CSS print) sera rendu puis converti en PDF.

⚠️ **État actuel à corriger en début de Phase 5a** : les dépendances **système** de WeasyPrint sont déjà installées dans le [Dockerfile](backend/Dockerfile) (libpango, libpangocairo, libgdk-pixbuf, libffi, shared-mime-info), **mais le paquet Python `weasyprint` n'est ni dans `pyproject.toml` ni dans `uv.lock`**, et aucun code ne l'importe encore. Prérequis M3 :

1. Ajouter `weasyprint` aux `dependencies` de `pyproject.toml`, puis `uv lock` / `uv sync`.
2. Vérifier la disponibilité des libs système hors Docker (dev Windows : WeasyPrint nécessite GTK/Pango — documenter dans le runbook, ou rendre la génération PDF dépendante du worker conteneurisé).
3. Templates Jinja2 facture + ventilation TVA par taux via le snapshot `OrderLine.tax_rate_id` (cf. jalon TVA *5a*).

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
