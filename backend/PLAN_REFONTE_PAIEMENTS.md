# Plan de refonte — Architecture multi-providers de paiement

> Document de référence — phases 1, 2, 3, 4, 5, 6 et 7 implémentées et testées.
> Outbox paiement: événements métier + audit webhook (`payment.webhook_received`) + notifications email/Slack branchés.
> Reste : appliquer en production les migrations de cleanup `payzen_*`, providers Stripe/PayPal.

---

## 0. État d'avancement (2026-05-15)

### Vue d'ensemble

| Phase | Statut | Notes |
|---|---|---|
| 1 — Refonte du modèle | ✅ DONE | `provider_code`/`provider_reference`/`provider_data` + tables `payment_validations` et `payment_attachments` créés. Cleanup `payzen_*` implémenté via migrations (`payments` + `payment_logs`), reste l'application en production |
| 2 — Abstractions | ✅ DONE | `PaymentProvider`, `ApiPaymentProvider`, `ManualPaymentProvider`, `DocumentValidatedProvider` + DTOs + registry |
| 3 — Paiements manuels | ✅ DONE | `ManualCheckProvider`, `ManualTransferProvider` + routes admin + outbox + seeds |
| 4 — Module Attachment | ✅ DONE | `FileStorage` (S3/local) + `AntivirusScanner` (clamd/noop) + service upload + scan AV async |
| 5 — Bons de commande publics | ✅ DONE | `PublicPurchaseOrderProvider` + routes upload/confirm/download + handler AV |
| 6 — Outbox | ✅ DONE | Câblé pour paiements manuels, documents, et IPN Payzen (`payment.captured`/`payment.rejected`) + audit `payment.webhook_received` et handlers notifications email/Slack |
| 7 — Routes génériques | ✅ DONE | `POST /payments/initiate`, `POST /payments/webhooks/{provider_code}`, routes legacy `/payzen/*` retirées |
| 8 — Stripe / PayPal | ❌ NOT DONE | À planifier |

### Inventaire des fichiers produits

**Modèles & migrations**

- [backend/app/features/payment/models/payment_validation.py](backend/app/features/payment/models/payment_validation.py)
- [backend/app/features/payment/models/payment_attachment.py](backend/app/features/payment/models/payment_attachment.py)
- Migration phase 1 — [a6b3d4e5f901_add_payment_provider_fields_phase1.py](backend/app/alembic/versions/a6b3d4e5f901_add_payment_provider_fields_phase1.py)
- Migration phase 3 — [b8c4f2a9d317_add_payment_validations_table.py](backend/app/alembic/versions/b8c4f2a9d317_add_payment_validations_table.py)
- Migration phase 4 — [c9e1f3a82b46_add_payment_attachments_table.py](backend/app/alembic/versions/c9e1f3a82b46_add_payment_attachments_table.py)
- Migration cleanup `payments` — [1a2c9e5f7b31_drop_legacy_payzen_columns_from_payments.py](backend/app/alembic/versions/1a2c9e5f7b31_drop_legacy_payzen_columns_from_payments.py)
- Migration cleanup `payment_logs` — [2d7f4b8c9e11_rename_payment_log_payzen_columns.py](backend/app/alembic/versions/2d7f4b8c9e11_rename_payment_log_payzen_columns.py)
- [backend/app/features/payment/crud/payment_validation.py](backend/app/features/payment/crud/payment_validation.py)
- [backend/app/features/payment/crud/payment_attachment.py](backend/app/features/payment/crud/payment_attachment.py)

**Providers**

- [backend/app/features/payment/providers/base.py](backend/app/features/payment/providers/base.py) — ABCs + DTOs
- [backend/app/features/payment/providers/__init__.py](backend/app/features/payment/providers/__init__.py) — registry `SUPPORTED_PROVIDERS`
- [backend/app/features/payment/providers/payzen.py](backend/app/features/payment/providers/payzen.py) — wrapper Payzen
- [backend/app/features/payment/providers/manual.py](backend/app/features/payment/providers/manual.py) — `ManualCheckProvider`, `ManualTransferProvider`
- [backend/app/features/payment/providers/document_validated.py](backend/app/features/payment/providers/document_validated.py) — `PublicPurchaseOrderProvider`

**Services**

- [backend/app/features/payment/services/provider_dispatch.py](backend/app/features/payment/services/provider_dispatch.py) — résolution provider depuis payment_method
- [backend/app/features/payment/services/manual_payment.py](backend/app/features/payment/services/manual_payment.py) — orchestration manuel + outbox
- [backend/app/features/payment/services/document_payment.py](backend/app/features/payment/services/document_payment.py) — orchestration documents + outbox

**Module Attachment**

- [backend/app/features/attachment/storage/base.py](backend/app/features/attachment/storage/base.py) — interface `FileStorage`, DTOs presigned
- [backend/app/features/attachment/storage/s3.py](backend/app/features/attachment/storage/s3.py) — backend S3 (boto3, lazy import)
- [backend/app/features/attachment/storage/local.py](backend/app/features/attachment/storage/local.py) — backend filesystem + tokens HMAC pour dev/tests
- [backend/app/features/attachment/storage/factory.py](backend/app/features/attachment/storage/factory.py) — sélection par `FILE_STORAGE_BACKEND`
- [backend/app/features/attachment/antivirus/base.py](backend/app/features/attachment/antivirus/base.py) — interface `AntivirusScanner`
- [backend/app/features/attachment/antivirus/clamd_scanner.py](backend/app/features/attachment/antivirus/clamd_scanner.py) — clamd via `run_in_executor`
- [backend/app/features/attachment/antivirus/noop.py](backend/app/features/attachment/antivirus/noop.py) — fallback `CLAMAV_ENABLED=false`
- [backend/app/features/attachment/antivirus/factory.py](backend/app/features/attachment/antivirus/factory.py)
- [backend/app/features/attachment/service.py](backend/app/features/attachment/service.py) — upload + validation MIME/taille + scan

**Routes**

- [backend/app/api/routes/payments.py](backend/app/api/routes/payments.py) — `/payments/initiate`, `/payments/{id}/upload-document`, `/payments/{id}/document-uploaded`, `/payments/webhooks/{provider_code}`
- [backend/app/api/routes/admin_payments.py](backend/app/api/routes/admin_payments.py) — `/admin/payments/pending-validation`, `/{id}/approve`, `/{id}/reject`, `/{id}/validations`, `/{id}/attachments`, `/{id}/attachments/{att_id}/download`
- [backend/app/api/routes/internal_storage.py](backend/app/api/routes/internal_storage.py) — `PUT/GET /internal/storage/{token}` pour backend local

**Outbox handlers**

- [backend/app/handlers/payment.py](backend/app/handlers/payment.py) — events :
  - `payment.awaiting_validation` → Order `AwaitingPayment`
  - `payment.document_required` → Order `AwaitingPayment`
  - `payment.document_uploaded` → scan AV, marquage `av_scanned`, quarantine si infecté
  - `payment.captured` → Order `Paid`
  - `payment.rejected` → Order `PaymentFailed`
  - `payment.document_infected` → Order `PaymentFailed`

**Infrastructure**

- [docker-compose.yml](../docker-compose.yml) — container `clamav` (image `clamav/clamav:stable`, port 3310, volume cache signatures)
- [backend/pyproject.toml](backend/pyproject.toml) — ajout `boto3>=1.34.0` et `clamd>=1.0.2`
- [backend/app/core/config.py](backend/app/core/config.py) — settings `FILE_STORAGE_BACKEND`, `FILE_STORAGE_LOCAL_ROOT`, `PAYMENT_ATTACHMENT_MAX_BYTES`, `PAYMENT_ATTACHMENT_ALLOWED_MIME`, `CLAMAV_ENABLED`, `CLAMAV_HOST`, `CLAMAV_PORT`, `S3_REGION`
- [backend/app/features/initial_data.py](backend/app/features/initial_data.py) — seeds statuts (`Pending`, `AwaitingValidation`, `DocumentRequired`, `DocumentUploaded`, `UnderReview`, `Completed`, `Failed`) et méthodes (Chèque, Virement bancaire, Bon de commande)

### Couverture de tests

220 tests verts au total. Pour la refonte paiement :

| Fichier de test | Cas |
|---|---|
| [test_payment_providers.py](backend/app/tests/test_payment_providers.py) | 6 |
| [test_payment_provider_fields.py](backend/app/tests/test_payment_provider_fields.py) | 2 |
| [test_payment_provider_dispatch_service.py](backend/app/tests/test_payment_provider_dispatch_service.py) | 4 |
| [test_manual_payment_providers.py](backend/app/tests/test_manual_payment_providers.py) | 6 |
| [test_provider_dispatch_manual.py](backend/app/tests/test_provider_dispatch_manual.py) | 4 |
| [test_manual_payment_service.py](backend/app/tests/test_manual_payment_service.py) | 5 |
| [test_payment_outbox_handlers.py](backend/app/tests/test_payment_outbox_handlers.py) | 6 |
| [test_document_payment_provider.py](backend/app/tests/test_document_payment_provider.py) | 6 |
| [test_document_payment_service.py](backend/app/tests/test_document_payment_service.py) | 6 |
| [test_local_file_storage.py](backend/app/tests/test_local_file_storage.py) | 7 |
| [test_attachment_service.py](backend/app/tests/test_attachment_service.py) | 7 |
| [test_antivirus_scanner.py](backend/app/tests/test_antivirus_scanner.py) | 5 |
| [test_payment_document_handlers.py](backend/app/tests/test_payment_document_handlers.py) | 6 |
| [api/test_payments_initiate_manual.py](backend/app/tests/api/test_payments_initiate_manual.py) | 2 |
| [api/test_payments_document_routes.py](backend/app/tests/api/test_payments_document_routes.py) | 6 |
| [api/test_internal_storage_route.py](backend/app/tests/api/test_internal_storage_route.py) | 6 |
| [api/test_admin_payments_routes.py](backend/app/tests/api/test_admin_payments_routes.py) | 6 |
| [api/test_admin_payments_attachments.py](backend/app/tests/api/test_admin_payments_attachments.py) | 6 |
| [api/test_phase_d1..d4*.py](backend/app/tests/api/) | 11 |

### Reste à faire

1. **Suppression/renommage colonnes `payzen_*`** (phase 1 cleanup) : migrations implémentées (`payments` + `payment_logs`, avec backfill `payments` vers `provider_data`), reste à appliquer en production.
2. **Providers Stripe & PayPal** (phase 8) : implémenter `StripeProvider` et `PaypalProvider` comme `ApiPaymentProvider`. Le squelette est en place.
3. **UI admin** (frontend) : table paiements en attente + boutons approve/reject + prévisualisation du document. Sortie du périmètre backend de cette refonte.
4. **Antivirus en production** : container `clamav` actuellement requis par `api` et `arq-worker` via healthcheck. Le scan AV des documents tourne dans le worker outbox.

### Procédure de mise en service

```bash
# 1. Installer les nouvelles dépendances
cd backend && uv sync

# 2. Appliquer les migrations
uv run alembic upgrade head

# 3. Seeder statuts + méthodes de paiement
uv run python -m app.initial_data

# 4. Configuration .env (production)
FILE_STORAGE_BACKEND=s3
S3_BUCKET_NAME=...
S3_ACCESS_KEY_ID=...
S3_SECRET_KEY_ID=...
S3_REGION=eu-west-3
CLAMAV_ENABLED=true
CLAMAV_HOST=clamav
CLAMAV_PORT=3310

# 5. Lancer la stack
docker compose up -d
```

En dev local, `FILE_STORAGE_BACKEND=local` suffit (fichiers dans `/tmp/fastapi_ecommerce_storage`, presigned URLs servies par `/internal/storage/{token}`). `CLAMAV_ENABLED=false` par défaut.

---

## 1. Évaluation de l'existant (avant refonte — historique)

### Ce qui est déjà en place ✅

| Composant | Fichier | Statut |
|---|---|---|
| Modèle `Payment` | [backend/app/features/payment/models/payment.py:40-98](backend/app/features/payment/models/payment.py#L40-L98) | Existe, mais couplé Payzen |
| Modèle `PaymentMethod` | [backend/app/features/payment/models/payment_method.py:35-37](backend/app/features/payment/models/payment_method.py#L35-L37) | Générique, manque `provider_code` |
| Modèle `PaymentStatus` | [backend/app/features/payment/models/payment_status.py:26-28](backend/app/features/payment/models/payment_status.py#L26-L28) | Table-driven, OK |
| Modèle `PaymentLog` | [backend/app/features/payment/models/payment_log.py:61-68](backend/app/features/payment/models/payment_log.py#L61-L68) | Audit trail Payzen |
| Service Payzen | [backend/app/features/payment/utils/payzen.py](backend/app/features/payment/utils/payzen.py) | OAuth, IPN signature HMAC-SHA256 |
| Routes Payzen | [backend/app/api/routes/payzen.py](backend/app/api/routes/payzen.py) | `/payzen/form-token`, `/payzen/ipn` |
| Pattern Outbox | [backend/app/outbox/](backend/app/outbox/) | **Prêt mais non utilisé pour les paiements** |
| Settings Payzen | [backend/app/core/config.py:158-182](backend/app/core/config.py#L158-L182) | TEST/PROD modes, IPN URL |
| Settings S3 | [backend/app/core/config.py:152-156](backend/app/core/config.py#L152-L156) | **Configuré mais aucun code d'intégration** |

### Ce qui est couplé à Payzen ❌

- **Modèle `Payment`** contient 7 colonnes Payzen-spécifiques :
  `payzen_trans_id`, `payzen_order_id`, `payzen_payment_method`, `payzen_status`, `payzen_error_code`, `payzen_form_token`, `payzen_data`
- **Routes** : `/payzen/*` au lieu de `/payments/*` génériques
- **Logique inline** dans [backend/app/api/routes/payzen.py:151-186](backend/app/api/routes/payzen.py#L151-L186) qui met à jour Payment + Order dans la même requête (fragile, pas de retry sur échec partiel)

### Ce qui manque complètement ❌

- Aucune abstraction provider (pas d'ABC `PaymentProvider`)
- Aucun support Stripe/PayPal
- Aucun upload de document (S3 configuré mais aucun code)
- Aucun workflow de validation manuelle (chèques, virements)
- Aucune route admin pour approuver/rejeter un paiement
- Aucun usage de l'outbox pour les événements de paiement

---

## 2. Architecture cible

### 2.1 Trois archétypes → hiérarchie d'ABC

Les 3 types de paiement ont des cycles de vie fondamentalement différents — une seule ABC ne suffit pas.

```
PaymentProvider (ABC racine)
│
├── ApiPaymentProvider             → Payzen, Stripe, Paypal
│   ├─ async initiate_payment(payment) -> InitiationResult
│   ├─ async handle_webhook(payload, signature) -> WebhookResult
│   ├─ async refund(payment, amount) -> RefundResult
│   └─ verify_signature(payload, signature) -> bool
│
├── ManualPaymentProvider          → Chèque, Virement bancaire
│   ├─ async register_intent(payment) -> InitiationResult
│   ├─ async confirm_received(payment, admin_user, reference) -> ValidationResult
│   └─ async reject(payment, admin_user, reason) -> ValidationResult
│
└── DocumentValidatedProvider      → Bon de commande public
    ├─ async register_intent(payment) -> InitiationResult
    ├─ async attach_document(payment, file) -> AttachmentResult
    ├─ async approve(payment, admin_user, comment) -> ValidationResult
    └─ async reject(payment, admin_user, reason) -> ValidationResult
```

### 2.2 State machines par archétype

| Archétype | États |
|---|---|
| **API** | `pending → processing → captured \| failed \| cancelled` (transitions automatiques via webhook) |
| **Manuel** | `pending → awaiting_funds → confirmed \| rejected` (transitions manuelles par admin) |
| **Document** | `pending → document_uploaded → under_review → approved \| rejected` |

Chaque adapter déclare les transitions valides et la logique de garde (`can_transition_to(state)`).

### 2.3 Refonte du modèle `Payment`

**Sortir tous les champs `payzen_*` de la table principale** :

```python
# Table payment (générique)
class Payment(SQLModel, table=True):
    id: UUID
    amount: Decimal
    currency: str
    order_id: UUID | None    = FK
    user_id: UUID            = FK
    payment_method_id: int   = FK
    payment_status_id: int   = FK
    provider_code: str       # "payzen" | "manual_check" | "manual_transfer" | "po_public"
    provider_reference: str | None  # ID externe (trans_id Payzen, n° BC, n° chèque…)
    provider_data: dict      # JSONB libre — payload spécifique provider
    created_at, updated_at
```

```python
# Table payment_attachment (nouveau)
class PaymentAttachment(SQLModel, table=True):
    id: UUID
    payment_id: UUID = FK
    file_key: str           # clé S3
    filename: str
    mimetype: str
    size: int
    document_type: str      # "purchase_order" | "transfer_proof" | "check_image"
    uploaded_by_user_id: UUID = FK
    uploaded_at: datetime
    av_scanned: bool
    av_clean: bool | None
```

```python
# Table payment_validation (audit des décisions admin)
class PaymentValidation(SQLModel, table=True):
    id: UUID
    payment_id: UUID = FK
    action: str             # "approve" | "reject" | "request_info"
    admin_user_id: UUID = FK
    reason: str | None
    metadata: dict          # ref bancaire confirmée, n° chèque, etc.
    created_at: datetime
```

### 2.4 Enrichir `PaymentMethod`

Ajouter 3 colonnes :

```python
class PaymentMethod(SQLModel, table=True):
    # existant : id, name, description, fee
    provider_code: str                       # mapping vers SUPPORTED_PROVIDERS registry
    requires_admin_validation: bool = False  # True pour manuel + document
    requires_document_upload: bool = False   # True pour BC public
    is_active: bool = True
    sort_order: int = 0
```

### 2.5 Registry des providers

```python
# backend/app/features/payment/providers/__init__.py
SUPPORTED_PROVIDERS: dict[str, type[PaymentProvider]] = {
    "payzen":          PayzenProvider,         # ApiPaymentProvider
    "manual_check":    ManualCheckProvider,    # ManualPaymentProvider
    "manual_transfer": ManualTransferProvider, # ManualPaymentProvider
    "po_public":       PublicPurchaseOrderProvider,  # DocumentValidatedProvider
    # futurs :
    # "stripe":  StripeProvider,
    # "paypal":  PaypalProvider,
}

def get_provider(code: str) -> PaymentProvider:
    if code not in SUPPORTED_PROVIDERS:
        raise UnknownProviderError(code)
    return SUPPORTED_PROVIDERS[code]()
```

### 2.6 Routes paramétrées

```
# Client
POST   /payments/initiate
       body: { order_id, payment_method_id, ... }
       → résolution provider via payment_method.provider_code
       → dispatch vers adapter.initiate_payment()
       → retourne soit redirect_url (API), soit instructions (manuel), soit upload_url (doc)

POST   /payments/{id}/upload-document      # archétype Document uniquement
GET    /payments/{id}/status

POST   /payments/webhooks/{provider_code}  # endpoint générique
                                            # remplace /payzen/ipn
                                            # signature vérifiée par provider.verify_signature()

# Admin
GET    /admin/payments/pending-validation
GET    /admin/payments/{id}
GET    /admin/payments/{id}/attachments/{att_id}/download  # presigned URL S3
POST   /admin/payments/{id}/approve
       body: { reason?, reference? }
POST   /admin/payments/{id}/reject
       body: { reason }
POST   /admin/payments/{id}/request-info
       body: { message }
```

### 2.7 Module Attachment / Upload

Nouveau module `backend/app/features/attachment/` :

- **Storage** : wrapper S3 (`boto3` ou `aioboto3`) — utilise les settings S3 existants
- **Upload** : 2 stratégies
  - Direct via `UploadFile` FastAPI (simple, mais charge le serveur)
  - Presigned URL (recommandé pour gros documents > 5 MB)
- **Validation** : MIME whitelist (`application/pdf`, `image/jpeg`, `image/png`), taille max configurable
- **Antivirus** : ClamAV via clamd async (optionnel mais **fortement recommandé** pour PDF d'origine externe)
- **Lien polymorphe vs table dédiée** : préférer `payment_attachment` dédié (typage SQL fort) plutôt qu'un lien polymorphe générique

### 2.8 Outbox pour la fiabilité

L'infrastructure `app/outbox/` est en place et utilisée pour les paiements manuels, documents, et les issues terminales IPN Payzen (`payment.captured` / `payment.rejected`).

Compléments à ajouter pour finaliser la phase 6 :

| Événement | Type | Consommateur |
|---|---|---|
| Webhook Payzen reçu | `payment.webhook_received` | Persiste payload brut + traite après commit (replay safe) |
| Paiement manuel initié | `payment.awaiting_validation` | Notif email/Slack admin |
| Paiement validé | `payment.captured` | Sync Order status, email confirmation client |
| Paiement rejeté | `payment.rejected` | Email client, libération stock |
| Document uploadé | `payment.document_uploaded` | Notif admin pour review |
| Antivirus négatif | `payment.document_infected` | Alerte admin + suppression fichier |

Le flux IPN actuel dans [backend/app/api/routes/payments.py](backend/app/api/routes/payments.py) met à jour `Payment`, puis publie les événements outbox terminaux ; la synchronisation `Order` est faite côté handlers outbox.

---

## 3. Plan d'exécution

### Phase 1 — Refonte du modèle ✅ DONE (sauf cleanup)
1. ✅ Migration Alembic [a6b3d4e5f901](backend/app/alembic/versions/a6b3d4e5f901_add_payment_provider_fields_phase1.py) : `provider_code`, `provider_reference`, `provider_data` sur `payment` + enrichissement `payment_method`
2. ⚠️ **Backfill non requis** : les colonnes `provider_data` sont nullables et `provider_code` a une valeur par défaut `"payzen"`. Pour la prod, prévoir tout de même un script de copie `payzen_*` → `provider_data` avant suppression
3. ✅ Migration de drop des colonnes `payzen_*` implémentée avec backfill vers `provider_data` (déploiement prod restant)
4. ✅ Tables [payment_validations](backend/app/alembic/versions/b8c4f2a9d317_add_payment_validations_table.py) et [payment_attachments](backend/app/alembic/versions/c9e1f3a82b46_add_payment_attachments_table.py) créées
5. ✅ Colonnes `provider_code`, `requires_admin_validation`, `requires_document_upload`, `sort_order` ajoutées sur `payment_method`

### Phase 2 — Abstractions ✅ DONE
6. ✅ ABCs dans [providers/base.py](backend/app/features/payment/providers/base.py)
7. ✅ DTOs `InitiationRequest`, `InitiationResult`, `WebhookResult`, `ValidationResult`, `AttachmentResult`
8. ✅ Registry [SUPPORTED_PROVIDERS](backend/app/features/payment/providers/__init__.py)
9. ✅ Wrapper [PayzenProvider](backend/app/features/payment/providers/payzen.py)
10. ✅ Tests dans [test_payment_providers.py](backend/app/tests/test_payment_providers.py) et [test_payment_provider_dispatch_service.py](backend/app/tests/test_payment_provider_dispatch_service.py)

### Phase 3 — Paiements manuels ✅ DONE (backend)
11. ✅ [ManualCheckProvider, ManualTransferProvider](backend/app/features/payment/providers/manual.py)
12. ✅ Routes [admin_payments.py](backend/app/api/routes/admin_payments.py) : `/admin/payments/pending-validation`, `/approve`, `/reject`, `/validations`
13. ✅ Seeds [Chèque, Virement bancaire](backend/app/features/initial_data.py) avec `requires_admin_validation=True`
14. ❌ **UI admin** (frontend hors périmètre backend)

### Phase 4 — Module Attachment ✅ DONE
15. ✅ Module [app/features/attachment/](backend/app/features/attachment/)
16. ✅ Wrapper S3 avec presigned URLs natives + fallback local pour dev/tests
17. ✅ Validation MIME (`application/pdf`, `image/jpeg`, `image/png`) + taille max (10 MB par défaut) dans [service.py](backend/app/features/attachment/service.py)
18. ✅ ClamAV via [clamd_scanner.py](backend/app/features/attachment/antivirus/clamd_scanner.py) + container Docker dédié
19. ✅ Tests [test_local_file_storage.py](backend/app/tests/test_local_file_storage.py), [test_attachment_service.py](backend/app/tests/test_attachment_service.py), [test_antivirus_scanner.py](backend/app/tests/test_antivirus_scanner.py), [api/test_internal_storage_route.py](backend/app/tests/api/test_internal_storage_route.py)

### Phase 5 — Bons de commande publics ✅ DONE (backend)
20. ✅ [PublicPurchaseOrderProvider](backend/app/features/payment/providers/document_validated.py)
21. ✅ Routes `POST /payments/{id}/upload-document` (presigned URL) + `POST /payments/{id}/document-uploaded` (confirm + scan AV asynchrone)
22. ❌ **UI client** (frontend hors périmètre)
23. ❌ **UI admin** (frontend hors périmètre) — la route admin de download est en place ([GET /admin/payments/{id}/attachments/{att_id}/download](backend/app/api/routes/admin_payments.py))

### Phase 6 — Outbox pour fiabilité ⚠️ PARTIEL
24. ✅ IPN Payzen branché outbox pour les issues terminales (`payment.captured` / `payment.rejected`) via [payzen_ipn()](backend/app/api/routes/payments.py)
25. ✅ Idempotence préservée pour Payzen via `payzen_trans_id` ([test_phase_c6_payzen_ipn_idempotency.py](backend/app/tests/api/test_phase_c6_payzen_ipn_idempotency.py))
26. ❌ **À faire** : event `payment.webhook_received` (payload brut) + handlers email/Slack (uniquement logs aujourd'hui)
27. ✅ Sync Order status via outbox pour manuel, document, et IPN Payzen terminal ([handlers/payment.py](backend/app/handlers/payment.py))

Events publiés et consommés actuellement :

| Event | Producteur | Handler |
|---|---|---|
| `payment.awaiting_validation` | `register_intent` (manuel) | Order → `AwaitingPayment` |
| `payment.document_required` | `register_intent` (document) | Order → `AwaitingPayment` |
| `payment.document_uploaded` | `mark_document_uploaded` | Scan AV → quarantine si infecté |
| `payment.captured` | `approve_manual_payment` / `approve_document_payment` / `payzen_ipn` | Order → `Paid` |
| `payment.rejected` | `reject_manual_payment` / `reject_document_payment` / `payzen_ipn` | Order → `PaymentFailed` |
| `payment.document_infected` | `mark_document_infected` | Order → `PaymentFailed` |

### Phase 7 — Routes génériques ✅ DONE
28. ✅ [POST /payments/initiate](backend/app/api/routes/payments.py) dispatch via `payment_method.provider_code` (gère API, manuel, document)
29. ✅ [POST /payments/webhooks/{provider_code}](backend/app/api/routes/payments.py) générique
30. ✅ Routes legacy `/payzen/*` retirées d'OpenAPI ([test_phase_d1_payzen_provider_bridge.py](backend/app/tests/api/test_phase_d1_payzen_provider_bridge.py))

### Phase 8 — Providers futurs ❌ NOT DONE
31. ❌ `StripeProvider` (~2j) — extension d'`ApiPaymentProvider`, vérification signature `Stripe-Signature` + event ID
32. ❌ `PaypalProvider` (~2j) — extension d'`ApiPaymentProvider`

---

## 4. Tradeoffs et points d'attention

### 4.1 Choix d'architecture

| Question | Décision recommandée | Justification |
|---|---|---|
| Hiérarchie d'ABC vs Provider unique avec `capabilities` | **Hiérarchie** (`ApiPaymentProvider`, `ManualPaymentProvider`, `DocumentValidatedProvider`) | Les workflows sont trop différents — un Provider unique avec `if self.is_manual` est un anti-pattern |
| `provider_data` JSONB vs colonnes typées par provider | **JSONB** + Pydantic schema par provider pour validation | Évite l'explosion de colonnes ; typage côté Python |
| Webhook : route par provider vs route générique | **Route générique** `/webhooks/{provider}` | Symétrique avec architecture suppliers ; plus facile à proxifier |
| Upload : direct vs presigned URL | **Direct pour PDF < 5MB** (suffit pour BC), **presigned pour gros fichiers** futurs | Simplicité d'abord |
| Lien Order ↔ Payment : 1-to-1 ou 1-to-N | **1-to-N** (déjà le cas, à conserver) | Permet paiement échelonné, retry après échec |

### 4.2 Risques

- **Migration des colonnes `payzen_*`** : risque de perte de données si mal faite. Prévoir : migration en 2 étapes (ajout JSONB + backfill, puis suppression colonnes séparément), backup pré-migration, rollback testé.
- **Webhooks et idempotence** : Payzen retry 3 fois sur échec — la déduplication actuelle ([backend/app/api/routes/payzen.py:369-399](backend/app/api/routes/payzen.py#L369-L399)) doit être préservée et étendue à Stripe (uses `Stripe-Signature` + event ID) et PayPal.
- **Validation manuelle = audit légal** : tracer **toutes** les décisions admin dans `payment_validation` — qui, quand, pourquoi. Ne jamais permettre la modification rétroactive.
- **Antivirus sur uploads** : un BC public en PDF malveillant qui infecte l'ordinateur d'un comptable serait un incident sérieux. ClamAV ou équivalent **non négociable** en prod.
- **Conflits de devise** : Payzen est configuré XPF par défaut ([backend/app/core/config.py:158-182](backend/app/core/config.py#L158-L182)). Stripe/PayPal devront gérer leur propre devise ; vérifier que `payment.currency` est bien la source de vérité, pas la config provider.

### 4.3 Sécurité

- **Webhook signature** : chaque `ApiPaymentProvider` implémente sa propre vérification (HMAC pour Payzen, signing secret pour Stripe, certif pour PayPal IPN legacy). **Refuser tout webhook sans signature valide** sans exception.
- **Permissions admin** : routes `/admin/payments/*` exigent `CurrentSuperUser` ou un nouveau rôle `payment_validator`.
- **Presigned URLs** : durée de vie courte (5 min max), un seul usage si possible.
- **Logs** : ne **jamais** logger les `provider_data` bruts (peuvent contenir tokens, IBAN, etc.). Whitelist des champs loggables.

---

## 5. Inventaire des fichiers impactés

### Créés ✅
- [backend/app/features/payment/providers/__init__.py](backend/app/features/payment/providers/__init__.py) — registry
- [backend/app/features/payment/providers/base.py](backend/app/features/payment/providers/base.py) — ABCs + DTOs
- [backend/app/features/payment/providers/payzen.py](backend/app/features/payment/providers/payzen.py) — wrapper
- [backend/app/features/payment/providers/manual.py](backend/app/features/payment/providers/manual.py) — manual providers
- [backend/app/features/payment/providers/document_validated.py](backend/app/features/payment/providers/document_validated.py) — `PublicPurchaseOrderProvider`
- [backend/app/features/payment/models/payment_validation.py](backend/app/features/payment/models/payment_validation.py)
- [backend/app/features/payment/models/payment_attachment.py](backend/app/features/payment/models/payment_attachment.py)
- [backend/app/features/payment/crud/payment_validation.py](backend/app/features/payment/crud/payment_validation.py)
- [backend/app/features/payment/crud/payment_attachment.py](backend/app/features/payment/crud/payment_attachment.py)
- [backend/app/features/payment/services/provider_dispatch.py](backend/app/features/payment/services/provider_dispatch.py)
- [backend/app/features/payment/services/manual_payment.py](backend/app/features/payment/services/manual_payment.py)
- [backend/app/features/payment/services/document_payment.py](backend/app/features/payment/services/document_payment.py)
- [backend/app/features/attachment/](backend/app/features/attachment/) — module complet (storage + antivirus + service)
- [backend/app/api/routes/payments.py](backend/app/api/routes/payments.py) — router générique
- [backend/app/api/routes/admin_payments.py](backend/app/api/routes/admin_payments.py) — routes admin
- [backend/app/api/routes/internal_storage.py](backend/app/api/routes/internal_storage.py) — endpoints signés pour backend local
- [backend/app/handlers/payment.py](backend/app/handlers/payment.py) — handlers outbox
- 4 migrations Alembic ([a6b3d4e5f901](backend/app/alembic/versions/a6b3d4e5f901_add_payment_provider_fields_phase1.py), [b8c4f2a9d317](backend/app/alembic/versions/b8c4f2a9d317_add_payment_validations_table.py), [c9e1f3a82b46](backend/app/alembic/versions/c9e1f3a82b46_add_payment_attachments_table.py), [1a2c9e5f7b31](backend/app/alembic/versions/1a2c9e5f7b31_drop_legacy_payzen_columns_from_payments.py))

### Modifiés ✅
- [backend/app/features/payment/models/payment.py](backend/app/features/payment/models/payment.py) — ajout `provider_code`, `provider_reference`, `provider_data` (colonnes `payzen_*` conservées temporairement)
- [backend/app/features/payment/models/payment_method.py](backend/app/features/payment/models/payment_method.py) — ajout `provider_code`, `requires_admin_validation`, `requires_document_upload`, `sort_order`
- [backend/app/core/config.py](backend/app/core/config.py) — settings `FILE_STORAGE_BACKEND`, `CLAMAV_*`, MIME whitelist, taille max
- [backend/app/api/__init__.py](backend/app/api/__init__.py) — wiring `admin_payments_router`, `internal_storage_router`
- [backend/app/features/initial_data.py](backend/app/features/initial_data.py) — seeds payment statuses + methods
- [backend/pyproject.toml](backend/pyproject.toml) — ajout `boto3`, `clamd`
- [docker-compose.yml](../docker-compose.yml) — container `clamav`

### À créer (futur)
- `backend/app/features/payment/providers/stripe.py`
- `backend/app/features/payment/providers/paypal.py`

### À supprimer (cleanup phase 1)
- Colonnes `payzen_*` du modèle `Payment` après backfill prod et validation que `provider_data` couvre tous les usages

### Déjà retirés ✅
- Routes legacy `/payzen/form-token`, `/payzen/ipn` retirées d'OpenAPI (remplacées par `/payments/initiate` et `/payments/webhooks/payzen`)

---

## 6. Symétrie avec l'architecture suppliers

Cette refonte suit **exactement le même pattern** que [PLAN_REFONTE_MULTI_FOURNISSEURS.md](PLAN_REFONTE_MULTI_FOURNISSEURS.md) :

| Concept | Suppliers | Payments |
|---|---|---|
| ABC racine | `SupplierAdapter` | `PaymentProvider` |
| Registry | `SUPPLIERS` dict | `SUPPORTED_PROVIDERS` dict |
| DTO commun | `NormalizedProductData` | `InitiationResult`, `WebhookResult`, etc. |
| Routes paramétrées | `/suppliers/{name}/*` | `/payments/webhooks/{provider}` |
| Tâches paramétrées | `sync_supplier_*_task(supplier_name, ...)` | Handlers outbox par event_type |
| Settings imbriqués | `SUPPLIER__INGRAM__*` | `PAYMENT__PAYZEN__*` (à standardiser) |

Les deux refontes peuvent être menées en parallèle ; idéalement aligner le style (nommage, structure de dossiers, conventions de tests) pour faciliter la maintenance.
