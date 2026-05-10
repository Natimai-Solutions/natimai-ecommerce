# Plan de refonte — Support multi-fournisseurs

> Document de référence pour une implémentation future.
> État actuel : intégration Ingram Micro uniquement.
> Objectif : permettre l'ajout de fournisseurs supplémentaires (TechData, Also, etc.) sans dupliquer la stack.

---

## 1. Évaluation de l'existant

**Difficulté actuelle d'ajouter un fournisseur : moyenne.** La moitié du travail est déjà faite, l'autre moitié demande une vraie abstraction.

### Ce qui est déjà supplier-agnostic ✅

- **Modèle `Product`** ([backend/app/features/product/models/product.py:25-158](backend/app/features/product/models/product.py#L25-L158))
  - Champs génériques déjà présents : `supplier_sku`, `supplier_name`, `supplier_price`, `supplier_price_currency`, `supplier_quantity`, `supplier_category`, `supplier_subcategory`, `last_supplier_sync`, `is_supplier_managed`, `vendor_part_number`, `manufacturer`
  - Pas de colonne Ingram-spécifique
- **Lookup CRUD** : `crud_product.get_by_supplier_sku(supplier_sku, supplier_name, ...)` accepte déjà un `supplier_name` en paramètre
- **Schémas de tracking** : `IngramSyncLog` et `IngramProductMapping` ne contiennent rien d'intrinsèquement Ingram dans leurs colonnes (juste le nommage)
- **Infrastructure ARQ** (cron, dedup Redis) : générique
- **Normalisation prix/quantité** (`normalize_supplier_snapshot()`) : générique

### Ce qui est couplé à Ingram ❌

| Couche | Fichier | Problème |
|---|---|---|
| Service HTTP | [backend/app/services/ingram_micro_service.py](backend/app/services/ingram_micro_service.py) | Endpoints, OAuth, headers (`IM-CustomerNumber`, `IM-CountryCode`…) hardcodés |
| Orchestrateur | [backend/app/features/integrations/services/ingram_sync_orchestrator.py:34-219](backend/app/features/integrations/services/ingram_sync_orchestrator.py#L34-L219) | `_convert_ingram_to_product_data()` mappe directement `IngramProductData → Product` |
| Tâches ARQ | [backend/app/tasks/ingram_micro_tasks.py](backend/app/tasks/ingram_micro_tasks.py) | 3 fonctions dédiées Ingram (`sync_ingram_products_task`, etc.) |
| Routes | [backend/app/api/routes/ingram_micro.py](backend/app/api/routes/ingram_micro.py) | Router dédié, supplier_name "Ingram Micro" en dur |
| Settings | [backend/app/core/config.py:134-143](backend/app/core/config.py#L134-L143) | Préfixe `INGRAM_*` sans namespace fournisseur |

---

## 2. Architecture cible

### 2.1 Interface `SupplierAdapter` (ABC)

Nouveau fichier : `backend/app/services/suppliers/base.py`

```python
from abc import ABC, abstractmethod

class SupplierAdapter(ABC):
    name: str                       # "ingram_micro", "techdata"
    display_name: str               # "Ingram Micro"
    default_categories: list[str]
    batch_size: int                 # taille de batch pour price/availability

    @abstractmethod
    async def fetch_catalog(
        self, category: str, **filters
    ) -> list[NormalizedProductData]: ...

    @abstractmethod
    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, NormalizedPricing]: ...

    @abstractmethod
    async def health_check(self) -> bool: ...
```

### 2.2 DTO commun `NormalizedProductData`

**Pièce centrale manquante.** Aujourd'hui le mapping Ingram → Product est direct ; demain :

```
IngramAdapter   → NormalizedProductData ─┐
TechDataAdapter → NormalizedProductData ─┼─→ Product (via orchestrateur générique)
AlsoAdapter     → NormalizedProductData ─┘
```

Chaque adapter porte la responsabilité de sa normalisation. L'orchestrateur ne voit plus que le DTO commun.

### 2.3 Orchestrateur générique

Renommer `IngramSyncOrchestrator` → `SupplierSyncOrchestrator(adapter: SupplierAdapter)`. Le code devient :

```python
class SupplierSyncOrchestrator:
    def __init__(self, adapter: SupplierAdapter):
        self.adapter = adapter

    async def sync_products(self, categories: list[str]):
        for cat in categories:
            normalized = await self.adapter.fetch_catalog(category=cat)
            for item in normalized:
                await self._upsert_product(item, supplier_name=self.adapter.name)
```

### 2.4 Migration Alembic des modèles de tracking

| Avant | Après |
|---|---|
| `ingram_sync_log` | `supplier_sync_log` (+ colonne `supplier_name` indexée) |
| `ingram_product_mapping` | `supplier_product_mapping` (+ colonne `supplier_name` indexée) |
| `IngramSyncLog` | `SupplierSyncLog` |
| `IngramProductMapping` | `SupplierProductMapping` |

**⚠️ Risque principal de la refonte.** À faire **avant** d'avoir trop de données en prod.

### 2.5 Registry et configuration

```python
# backend/app/services/suppliers/__init__.py
SUPPLIERS: dict[str, type[SupplierAdapter]] = {
    "ingram_micro": IngramMicroAdapter,
    "techdata": TechDataAdapter,
}
```

**Settings imbriqués (Pydantic `BaseSettings`)** :

```
SUPPLIER__INGRAM__CLIENT_ID=...
SUPPLIER__INGRAM__CLIENT_SECRET=...
SUPPLIER__TECHDATA__API_KEY=...
```

### 2.6 Routes paramétrées

Remplacer le router `/ingram/*` par un router générique :

```
POST  /suppliers/{supplier_name}/sync/products
POST  /suppliers/{supplier_name}/sync/inventory
GET   /suppliers/{supplier_name}/health
GET   /suppliers/{supplier_name}/config
GET   /suppliers                              # liste des fournisseurs enregistrés
```

### 2.7 Tâches ARQ paramétrées

Une seule fonction par type de sync :

```python
async def sync_supplier_products_task(ctx, supplier_name: str, categories: list[str]): ...
async def sync_supplier_inventory_task(ctx, supplier_name: str, skus: list[str] | None): ...
async def check_supplier_health_task(ctx, supplier_name: str): ...
```

La planification cron itère sur `SUPPLIERS.keys()`.

---

## 3. Plan d'exécution suggéré

### Phase 1 — Préparation (sans casser l'existant)
1. Créer `app/services/suppliers/base.py` (ABC + DTOs `NormalizedProductData`, `NormalizedPricing`)
2. Wrapper `IngramMicroAdapter(SupplierAdapter)` autour du service existant — pas de modification de comportement
3. Tests unitaires sur l'adapter

### Phase 2 — Migration des modèles
4. Migration Alembic : renommer tables, ajouter colonnes `supplier_name`, backfiller `"ingram_micro"` sur les lignes existantes
5. Renommer modèles SQLModel + CRUD
6. Mettre à jour les imports

### Phase 3 — Orchestrateur générique
7. Créer `SupplierSyncOrchestrator` paramétré
8. Remplacer `_convert_ingram_to_product_data()` par la normalisation portée par l'adapter
9. Garder l'ancien orchestrateur en deprecation warning pendant 1 release

### Phase 4 — Routes & tâches
10. Nouveau router `/suppliers/{supplier_name}/*`
11. Ancien router `/ingram/*` redirige vers le nouveau (deprecated)
12. Refactor des tâches ARQ vers les versions paramétrées
13. Mise à jour de la planification cron

### Phase 5 — Ajout d'un 2ᵉ fournisseur (preuve de fonctionnement)
14. Implémenter `TechDataAdapter` (ou autre)
15. Settings, registration, premier sync end-to-end

### Phase 6 — Nettoyage
16. Suppression du router deprecated
17. Suppression de l'ancien orchestrateur
18. Documentation contributeurs

---

## 4. Tradeoff — Quand faire la refonte ?

| Situation | Recommandation |
|---|---|
| Un seul fournisseur supplémentaire prévu, jamais plus | **Copier-coller** Ingram → X (~1 jour). La refonte n'en vaut pas la peine. |
| 2 fournisseurs supplémentaires ou plus prévus | **Refonte ABC justifiée.** ROI à partir du 2ᵉ adapter. |
| Frontend admin doit lister/gérer les fournisseurs de façon générique | **Refonte nécessaire** dès maintenant. |
| Beaucoup de données en prod sur les tables `ingram_*` | **Repousser la migration** ou prévoir un downtime de maintenance. |

---

## 5. Points d'attention

- **Idempotence des syncs** — vérifier que `_resolve_existing_product()` (lookup par mapping puis fallback `supplier_sku + supplier_name`) reste correct quand plusieurs fournisseurs partagent un même SKU vendor (ex : même `vendor_part_number` Lenovo chez Ingram et TechData → 2 entrées Product distinctes attendues, ou fusion ? **Décision produit à prendre.**)
- **Conflits de prix** — si un même produit (même MPN) est référencé chez 2 fournisseurs, lequel sert de source de vérité pour `base_price` ? Politique "best price" ? "preferred supplier" ? Champ `preferred_supplier_id` à ajouter ?
- **OAuth/auth par fournisseur** — chaque adapter encapsule sa propre stratégie d'auth (OAuth 2.0 client credentials pour Ingram, API Key pour d'autres, JWT signé pour d'autres encore)
- **Rate limiting** — propriété `requests_per_minute` sur l'adapter, gérée par un middleware/throttler partagé
- **Observabilité** — étiquetage métriques/logs par `supplier_name` (Prometheus labels)

---

## 6. Inventaire des fichiers impactés

### À créer
- `backend/app/services/suppliers/__init__.py` (registry)
- `backend/app/services/suppliers/base.py` (ABC + DTOs)
- `backend/app/services/suppliers/ingram_micro.py` (adapter wrapping)
- `backend/app/services/suppliers/<nouveau>.py` (futurs adapters)
- `backend/app/api/routes/suppliers.py` (router générique)
- Migration Alembic de renommage

### À modifier
- [backend/app/features/integrations/models/ingram_sync.py](backend/app/features/integrations/models/ingram_sync.py) → renommer
- [backend/app/features/integrations/crud/ingram_sync.py](backend/app/features/integrations/crud/ingram_sync.py) → renommer
- [backend/app/features/integrations/services/ingram_sync_orchestrator.py](backend/app/features/integrations/services/ingram_sync_orchestrator.py) → généraliser
- [backend/app/tasks/ingram_micro_tasks.py](backend/app/tasks/ingram_micro_tasks.py) → paramétrer
- [backend/app/core/config.py:134-143](backend/app/core/config.py#L134-L143) → settings imbriqués
- [backend/app/api/__init__.py:77](backend/app/api/__init__.py#L77) → wiring routes

### À déprécier puis supprimer
- [backend/app/api/routes/ingram_micro.py](backend/app/api/routes/ingram_micro.py)
- [backend/app/services/ingram_micro_service.py](backend/app/services/ingram_micro_service.py) (logique migrée dans l'adapter)
