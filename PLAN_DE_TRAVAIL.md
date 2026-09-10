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
- 🔲 **Sélecteur de mode au checkout** : reporté à la phase logistique. Le checkout vitrine actuel paie le total panier sans étape shipping (ne câble pas `checkout_my_cart`, qui sait pourtant calculer le shipping selon `shipping_preference`). À câbler quand l'étape commande+shipping sera intégrée au checkout.
- ✅ **Option « Devise d'affichage » masquée** dans les préférences (`MyAccountPage.vue`) tant que l'affichage multi-devises (conversion XPF→devise + endpoint taux public) n'est pas livré — **Phase 4**. La préférence `currency_pref` reste stockée, simplement non exposée.

### Avancement vitrine — filtres specs (20/06/2026)

- ✅ **Sélecteur Catégorie** dans `CataloguePage.vue` (depuis `GET /category`).
- ✅ **Filtres par caractéristique** pilotés par `GET /product/categories/{id}/spec-facets` : facettes **enum** (cases à cocher `value_text (count)`) et **numériques** (sélecteur « ≥ minimum » à partir des valeurs disponibles). Payload `specs` envoyé à `POST /product/search` (`{cpu_family: ["i7"], memory_gb_min: 16}`). Sync URL (`cat`), reset, SSR prefetch.
- Modules : [frontend/src/api/products.ts](frontend/src/api/products.ts) (`getCategorySpecFacets`) · [frontend/src/stores/products.ts](frontend/src/stores/products.ts) (`specFacets`/`loadSpecFacets`). Typecheck + lint verts.

### Matrice livrables par surface

| Feature | Backend | Vitrine (`frontend`) | Admin (`admin-frontend`) |
|---------|---------|----------------------|--------------------------|
| Catalogue + recherche FTS | ✅ | ✅ `CataloguePage.vue` | — |
| Specs filtrables (facettes) | ✅ | ✅ `CataloguePage.vue` (catégorie + filtres specs enum/num.) | 🔲 édition specs (API en P3, UI à faire) |
| Fiche produit + modes transport (CAF) | ✅ | ✅ `ProductPage.vue` (prix du mode par défaut ; sélecteur de mode retiré — choix au niveau commande) | — |
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
| M1 — produits les plus vus | ✅ (10/09/2026) compteur journalier + `GET /product/popular` | ✅ accueil : vedettes + « les plus consultés » | — |
| M3 — factures PDF (**WeasyPrint**) + export comptable | ✅ (25/08/2026) | ✅ téléchargement facture (compte) | ✅ écran factures + export CSV |
| M5 — numéro de commande séquentiel | ✅ (25/08/2026) | ✅ affichage (compte) | ✅ affichage (factures) |
| Z2 — avoir comptable | ✅ (N10 + e-mail d'envoi 10/09/2026) | ✅ téléchargement des avoirs (compte, par commande) | ✅ écran Avoirs + export CSV |
| Z3 — relance paniers abandonnés | ✅ (10/09/2026) balayage horaire + `cart.abandoned` + e-mail | ✅ miroir serveur du panier, opt-out marketing | ✅ page Paniers abandonnés (compteurs ouverts / relancés / récupérés) |
| Z4 — recherche IA | 🔲 | 🔲 UI recherche sémantique | — |

### Périmètre

| ID | Fonctionnalité | Notes |
|----|----------------|-------|
| M1 ✅ | Produits les plus vus | `POST /product/{id}/view` (page produit, côté client seulement) → `product_view_daily` ; `GET /product/popular?days&limit` ; accueil vitrine |
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
| A8 | Toggle « mis en avant » sur `ProductsPage` | `POST/DELETE /product/{id}/feature` | 1 | 🔲 à faire |
| A9 | Affectation directe de groupe à un user | `POST /admin/users/{id}/assign-price-group` + recherche user | 2 | ✅ livré (04/09/2026) via l'écran A15 (le PATCH porte aussi `price_group_id`) |
| A10 | **Validation des adresses** | *manque un endpoint listant les adresses à valider* (`POST /admin/addresses/{id}/validate` existe déjà) | 2 | ⛔ **décision requise** : (1) **désactiver la validation** (les adresses self-service deviennent utilisables directement) — la mention « doit être validée » est aujourd'hui dans `MyAccountPage.vue` mais n'était **pas** une exigence explicite du plan ; ou (2) **ajouter l'écran admin** (nécessite un endpoint `GET /admin/addresses?validated=false`) |
| A11 | Consultation des `QuoteRequest` | *manque un endpoint admin de listing des devis* | 1 | ⛔ bloqué (ajout backend requis) |
| A12 | Fusion / renommage de catégories | `POST /admin/categories/{id}/merge` ; renommage vitrine via `display_name` (le `name` reste la clé de sync) | 2 | ✅ livré (04/09/2026) — écran Catégories (A17) |
| A13 | **Validation des paiements** | `GET /admin/payments/pending-validation`, `.../approve\|reject`, `.../attachments[/{id}/download]` | 3 | ✅ livré (23/06/2026) |
| A14 | **Édition produit** (titre, description, images…) avec **champs d'override** préservés de la sync | `PUT /admin/products/{id}` (verrouille les champs édités), `DELETE /admin/products/{id}/overrides/{field}` (libère un verrou) ; sync **et** enrichissement Icecat respectent `overridden_fields` | 2/3 | ✅ livré (04/09/2026) — verrous visibles et libérables dans `ProductFormDialog` |
| A15 | **Liste des utilisateurs** (compte + groupe) + **création de compte** avec email d'invitation | `GET/POST /admin/users`, `PATCH /admin/users/{id}`, `POST .../{id}/resend-invitation` ([admin_users.py](backend/app/api/routes/admin_users.py)). Inclut A9 (affectation de groupe). | 2 | ✅ livré (04/09/2026) |
| A16 | **Logistique : regroupement / consolidation / suivi d'expédition** | `POST /admin/shipping/consolidation/...`, ship/deliver, `pending-grouping` (Phase 4) | 4 | 🔲 **Phase 4** — distinct d'A4 : A4 = PO fournisseur (Ingram), A16 = expéditions/consolidation. Endpoints à livrer en P4. |
| A17 | **Catégories** : liste + **titre / description / image vitrine personnalisés** (préservés de l'enrichissement) ; fusion/renommage (A12) | `GET/PATCH /admin/categories`, `Category.display_name` + `CategoryPublic.title` ([admin_categories.py](backend/app/api/routes/admin_categories.py)) | 2/3 | ✅ livré (04/09/2026) — [CategoriesPage](admin-frontend/src/pages/CategoriesPage.vue) |
| A18 | **Commandes clients** (liste + statut) | `GET /order/...` (scoping admin à relire ; `GET /order/status/{id}` existe pour superuser) | 2 | 🔲 à faire (écran ; endpoint de liste admin à confirmer) |
| A19 | **Paiements** (liste + statut, au-delà de la validation A13) | *endpoint de liste générale des paiements à confirmer/ajouter* | 2/3 | 🔲 à faire (écran + endpoint de liste) |

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
- 🔲 **Restent** : A8 (featured), A9 (assign group — fusionné dans A15), A10 (adresses — **décision** désactiver/écran), A11–A12 (devis, fusion catégories — backend requis), et les nouveaux **A14 produit (override), A15 users + création de compte, A16 logistique (P4), A17 catégories (override + image), A18 commandes clients, A19 paiements**. La plupart nécessitent des **ajouts backend** (champs override, endpoints de liste users/orders/payments, endpoint adresses à valider).

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

### PayPal (intégration standard) 🔲
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

### Whitelist catalogue & éligibilité automatique 🔲 (discussion du 25/08/2026)
Ne jamais exposer le catalogue Ingram brut (~centaines de milliers de SKU) : viser 3 000–8 000 références via des **critères d'éligibilité automatiques** câblés dans la sync :
- dispo > 0 sur les entrepôts pertinents ; **poids ET dimensions présents** (sans eux le fret est incalculable → inéligible par définition — corrige aussi l'écart F5 de la section CAF) ; pas de flag EOL/discontinued ; marques whitelistées ; match Icecat de qualité suffisante.
- **Règle valeur/poids (XPF/kg)** comme seuil d'éligibilité automatique : exclure sans état d'âme les catégories jamais compétitives au fret (écrans, boîtiers, imprimantes), même si Ingram les propose.
- En faire une fonctionnalité produit : flux **« nouveautés »** alimenté par les entrées récentes du catalogue — différenciant face aux revendeurs locaux. L'argument vitrine n° 1 reste toutefois « **prix final rendu, taxes et livraison comprises, avant de commander** » (personne ne fait ça localement) — à mettre en avant sur la page d'accueil.

### Rafraîchissement stratifié des prix 🔲 (discussion du 25/08/2026)
Aujourd'hui : cron toutes les 2 h, balayage **uniforme** de tout ce qui a > 1 h de retard, par lots au rate-limit ([supplier_tasks.py](backend/app/tasks/supplier_tasks.py)). La fraîcheur réelle par SKU dépend de la durée d'un cycle complet. À budget d'appels constant, stratifier : références **haute valeur / stock faible** toutes les heures, ventre du catalogue quotidien, longue traîne hebdomadaire (tri par `last_supplier_sync` + score valeur/volatilité).

### Commandes groupées cadencées 🔲 (discussion du 25/08/2026)
Annoncer un **départ consolidé hebdomadaire ou bimensuel** : les clients commandent d'ici la date, un seul envoi → le fret unitaire s'effondre et le délai devient une promesse claire au lieu d'un aléa. S'appuie sur la machinerie consolidation existante (P4) ; le chantier restant est surtout vitrine (affichage de la prochaine date de départ, compte à rebours) + process interne.

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

### Trois majeures JS bloquées en amont 🔲 (relevé le 28/08/2026)

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

**`@quasar/app-vite` 2 → 3** — la v3 supprime l'alias `#q-app`, que la v2
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

**④ Python 3.14.** L'image est passée en 3.13 (possible depuis le retrait de
passlib) ; la 3.14 existe et Dependabot la proposera. Saut d'une version
supplémentaire, non testé — à traiter comme une montée à part entière.

### Autres points différés

- **`session.execute()` dans [order_number.py](backend/app/features/order/services/order_number.py)** 🔲 — sqlmodel 0.0.39 suggère `session.exec()`. L'usage y est pourtant légitime (une séquence SQL brute `nextval`, pas un modèle) ; laissé tel quel pour ne pas retoucher l'allocation des numéros de commande au détour d'une montée de version. À trancher si l'avertissement devient une erreur.
- **Longueur minimale de `SECRET_KEY`** 🔲 — `pyjwt` avertit désormais sous 32 octets (HMAC/SHA-256). [config.py](backend/app/core/config.py) vérifie que la valeur n'est pas le placeholder, mais pas sa longueur : une clé courte passe en production sans un mot. Un garde-fou serait cohérent avec ceux déjà en place.
- **Troncature bcrypt à 72 octets** 🔲 — héritée de passlib et **conservée volontairement** lors de son retrait (28/08), sans quoi les comptes concernés auraient été enfermés dehors. Conséquence assumée et testée : deux mots de passe partageant leurs 72 premiers octets sont équivalents. La corriger (pré-hachage SHA-256 avant bcrypt) changerait **toutes** les empreintes et imposerait une réinitialisation générale — donc seulement dans le cadre d'une opération prévue pour ça.
- **Seuil de couverture `fail_under`** ✅ — relevé de 60 à **68** le 04/09/2026 (Q3) après mesure sur `main` fusionné : 71 % avant les tests Q3, 73 % après. Jamais à baisser pour faire passer une PR ; à remonter à nouveau quand la mesure le permet.
