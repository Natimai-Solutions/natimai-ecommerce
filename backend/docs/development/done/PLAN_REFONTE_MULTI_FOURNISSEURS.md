# Architecture multi-fournisseurs

> **État : implémenté.** L'ancienne intégration mono-fournisseur (Ingram Micro)
> a été refondue derrière une abstraction `SupplierAdapter`. Ce document décrit
> l'architecture en place et **comment ajouter un nouveau fournisseur**.

---

## 1. Vue d'ensemble

```
IngramMicroAdapter ─┐
TechDataAdapter  ───┼─→ NormalizedProductData / NormalizedPricing ─→ SupplierSyncOrchestrator ─→ Product
AlsoAdapter      ───┘                                                        │
                                                                             ├─→ supplier_sync_logs
                                                                             └─→ supplier_product_mappings
```

- Chaque adapter encapsule **son** API : auth (OAuth, API key, JWT…), endpoints,
  pagination, rate limiting, et la **normalisation** de ses payloads.
- L'orchestrateur, les tâches ARQ et les routes HTTP ne voient que l'interface
  `SupplierAdapter` et les DTO communs — jamais une forme propre à un vendor.
- Une seule paire de tables (`supplier_sync_logs`, `supplier_product_mappings`)
  sert tous les distributeurs ; la colonne `supplier_name` (indexée) porte le
  *nom machine* de l'adapter (`"ingram_micro"`, `"techdata"`, …).

---

## 2. Fichiers clés

| Rôle | Fichier |
|---|---|
| Interface + DTO | [backend/app/services/suppliers/base.py](backend/app/services/suppliers/base.py) — `SupplierAdapter`, `NormalizedProductData`, `NormalizedPricing`, `SupplierHealth` |
| Registry | [backend/app/services/suppliers/__init__.py](backend/app/services/suppliers/__init__.py) — `SUPPLIERS`, `get_adapter()`, `all_adapters()`, `supplier_names()` |
| Adapter Ingram | [backend/app/services/suppliers/ingram_micro.py](backend/app/services/suppliers/ingram_micro.py) — `IngramMicroService` (client REST) + `IngramMicroAdapter` |
| Orchestrateur | [backend/app/features/integrations/services/supplier_sync_orchestrator.py](backend/app/features/integrations/services/supplier_sync_orchestrator.py) — `SupplierSyncOrchestrator(adapter)` |
| Modèles tracking | [backend/app/features/integrations/models/supplier_sync.py](backend/app/features/integrations/models/supplier_sync.py) — `SupplierSyncLog`, `SupplierProductMapping` |
| CRUD tracking | [backend/app/features/integrations/crud/supplier_sync.py](backend/app/features/integrations/crud/supplier_sync.py) — scopé par `supplier_name` |
| Tâches ARQ | [backend/app/tasks/supplier_tasks.py](backend/app/tasks/supplier_tasks.py) — `sync_supplier_products_task`, `sync_supplier_inventory_task`, `check_supplier_health_task`, `get_supplier_sync_cron_jobs()` |
| Routes HTTP | [backend/app/api/routes/suppliers.py](backend/app/api/routes/suppliers.py) — router générique `/suppliers/*` |
| Normalisation prix/stock | [backend/app/features/integrations/services/supplier_data_normalization.py](backend/app/features/integrations/services/supplier_data_normalization.py) |

### Routes exposées (`/api/v1`)

```
GET   /suppliers                                # liste des fournisseurs enregistrés + état
POST  /suppliers/{supplier_name}/sync/products  # enqueue un sync catalogue
POST  /suppliers/{supplier_name}/sync/inventory # enqueue un refresh prix/stock
GET   /suppliers/{supplier_name}/health         # connectivité + dernier sync réussi
GET   /suppliers/{supplier_name}/config         # configuration (sans secrets)
GET   /suppliers/{supplier_name}/categories     # catégories synchronisées par défaut
```

### Tâches ARQ / cron

`get_supplier_sync_cron_jobs()` itère sur `all_adapters()` et planifie, pour chaque
fournisseur **sync activé**, trois jobs : `{name}_product_sync` (toutes les
`sync_interval_hours()` h), `{name}_inventory_sync` (toutes les 2 h),
`{name}_api_health_check` (quotidien). arq ne sachant pas passer d'arguments à un
cron, chaque job est une petite closure liée au `supplier_name` (`_bind_supplier`).

---

## 3. Ajouter un nouveau fournisseur

1. **Créer l'adapter** `backend/app/services/suppliers/<nom>.py` :

   ```python
   from app.services.suppliers.base import (
       NormalizedPricing, NormalizedProductData, SupplierAdapter, SupplierHealth,
   )

   class TechDataAdapter(SupplierAdapter):
       name = "techdata"
       display_name = "TechData"
       price_batch_size = 100

       def is_configured(self) -> bool: ...
       def is_sync_enabled(self) -> bool: ...
       def sync_interval_hours(self) -> int: ...      # optionnel (0 = pas de cron)

       async def fetch_catalog(self, category, **filters):   # async generator
           ...
           yield [NormalizedProductData(...), ...]            # une page par yield

       async def fetch_price_and_availability(self, skus) -> dict[str, NormalizedPricing]:
           ...

       async def health_check(self) -> SupplierHealth:
           ...
   ```

   L'adapter porte la responsabilité de **toute** sa normalisation : c'est lui
   qui transforme la réponse de son API en `NormalizedProductData` /
   `NormalizedPricing`.

2. **Enregistrer l'adapter** dans `backend/app/services/suppliers/__init__.py` :

   ```python
   from app.services.suppliers.techdata import TechDataAdapter
   SUPPLIERS = {
       IngramMicroAdapter.name: IngramMicroAdapter,
       TechDataAdapter.name: TechDataAdapter,
   }
   ```

3. **Ajouter sa configuration** dans `backend/app/core/config.py` (préfixe propre
   au fournisseur, ex. `TECHDATA_API_KEY`, `TECHDATA_SYNC_ENABLED`,
   `TECHDATA_SYNC_CATEGORIES`, …) — l'adapter lit `settings.TECHDATA_*` dans ses
   méthodes `is_configured()` / `default_categories` / etc.

C'est tout : routes, tâches ARQ, planification cron, table de tracking et CRUD
fonctionnent automatiquement pour le nouveau fournisseur.

---

## 4. Décisions produit encore ouvertes

- **SKU vendor partagé** — si deux fournisseurs référencent le même
  `vendor_part_number` (ex. un Lenovo chez Ingram et chez TechData), le système
  crée aujourd'hui **deux `Product` distincts** (résolution par
  `supplier_sku` + `supplier_name`, jamais de fusion). Une éventuelle fusion /
  `preferred_supplier_id` reste à arbitrer.
- **Conflit de prix** — quelle source de vérité pour `base_price` si le même
  produit (même MPN) existe chez deux fournisseurs ? Politique « best price » ?
  « preferred supplier » ? Champ à ajouter le cas échéant.
- **Rate limiting** — la propriété `requests_per_minute` existe sur l'adapter
  mais n'est pas encore consommée par un throttler partagé.
- **Observabilité** — les logs sont déjà étiquetés par `supplier_name` ; reste à
  câbler les labels Prometheus.

---

## 5. Migration de base de données

Migration Alembic `e8c4a2d6f1b0_rename_ingram_to_supplier` :
`ingram_sync_logs` → `supplier_sync_logs`, `ingram_product_mappings` →
`supplier_product_mappings` (colonne `ingram_sku` renommée `supplier_sku`),
ajout des colonnes `supplier_name` indexées (back-fill `"ingram_micro"`),
`vendor_part_number`/`manufacturer` passés nullable.
