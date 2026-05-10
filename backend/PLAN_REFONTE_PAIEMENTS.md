# Plan de refonte — Architecture multi-providers de paiement

> Document de référence pour une implémentation future.
> État actuel : intégration Payzen uniquement, modèle `Payment` couplé à Payzen.
> Objectif : supporter 3 archétypes de paiement (API, manuel, document validé) avec ajout futur facile (Stripe, PayPal).

---

## 1. Évaluation de l'existant

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

L'infrastructure `app/outbox/` est déjà en place et inutilisée pour les paiements. À câbler pour :

| Événement | Type | Consommateur |
|---|---|---|
| Webhook Payzen reçu | `payment.webhook_received` | Persiste payload brut + traite après commit (replay safe) |
| Paiement manuel initié | `payment.awaiting_validation` | Notif email/Slack admin |
| Paiement validé | `payment.captured` | Sync Order status, email confirmation client |
| Paiement rejeté | `payment.rejected` | Email client, libération stock |
| Document uploadé | `payment.document_uploaded` | Notif admin pour review |
| Antivirus négatif | `payment.document_infected` | Alerte admin + suppression fichier |

Ça remplace la logique inline actuelle dans [backend/app/api/routes/payzen.py:151-186](backend/app/api/routes/payzen.py#L151-L186) où la mise à jour Payment + Order est dans la même requête HTTP (si Order update échoue, Payment reste désynchronisé).

---

## 3. Plan d'exécution

### Phase 1 — Refonte du modèle (BLOQUANT pour le reste)
1. Migration Alembic : créer `provider_code`, `provider_reference`, `provider_data` sur `payment`
2. Backfill : tous les paiements existants → `provider_code = "payzen"`, déplacer `payzen_*` vers `provider_data` JSONB
3. Migration de suppression des colonnes `payzen_*` (en deuxième temps, après validation)
4. Création tables `payment_attachment` et `payment_validation`
5. Ajout colonnes sur `payment_method`

⚠️ **À faire tôt, avant d'avoir trop de données en prod.**

### Phase 2 — Abstractions
6. ABC `PaymentProvider` + sous-ABCs (`ApiPaymentProvider`, `ManualPaymentProvider`, `DocumentValidatedProvider`)
7. DTOs : `InitiationResult`, `WebhookResult`, `ValidationResult`, `AttachmentResult`
8. Registry `SUPPORTED_PROVIDERS`
9. Wrapper `PayzenProvider` autour du code existant — **comportement identique**, juste packaging
10. Tests unitaires sur l'adapter Payzen

### Phase 3 — Premier besoin : paiements manuels
11. `ManualCheckProvider` + `ManualTransferProvider`
12. Routes `/admin/payments/pending-validation`, `/approve`, `/reject`
13. Seed `payment_method` : "Chèque", "Virement bancaire" avec `requires_admin_validation=True`
14. UI admin minimale (table + boutons approve/reject)

### Phase 4 — Module Attachment
15. Module `app/features/attachment/`
16. Wrapper S3 (upload + presigned URL download)
17. Validation MIME / taille
18. (Optionnel) intégration ClamAV
19. Tests d'intégration upload/download

### Phase 5 — Deuxième besoin : Bons de commande publics
20. `PublicPurchaseOrderProvider`
21. Route `POST /payments/{id}/upload-document`
22. UI client : formulaire d'upload après initiation
23. UI admin : prévisualisation document + approve/reject

### Phase 6 — Outbox pour fiabilité
24. Migration de la logique inline payzen IPN → événements outbox
25. Handler `payment.webhook_received` avec idempotence sur `provider_reference`
26. Handlers de notification email/Slack
27. Handler de sync Order status

### Phase 7 — Routes génériques
28. `POST /payments/initiate` (dispatch via `payment_method.provider_code`)
29. `POST /payments/webhooks/{provider_code}` générique
30. Deprecation `/payzen/*` avec redirection 6 mois

### Phase 8 — Providers futurs
31. `StripeProvider` (~2j)
32. `PaypalProvider` (~2j)

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

### À créer
- `backend/app/features/payment/providers/__init__.py` (registry)
- `backend/app/features/payment/providers/base.py` (ABCs + DTOs)
- `backend/app/features/payment/providers/payzen.py` (wrapper)
- `backend/app/features/payment/providers/manual.py` (`ManualCheckProvider`, `ManualTransferProvider`)
- `backend/app/features/payment/providers/document_validated.py` (`PublicPurchaseOrderProvider`)
- `backend/app/features/payment/providers/stripe.py` (futur)
- `backend/app/features/payment/providers/paypal.py` (futur)
- `backend/app/features/payment/models/payment_attachment.py`
- `backend/app/features/payment/models/payment_validation.py`
- `backend/app/features/attachment/` (module complet)
- `backend/app/api/routes/payments.py` (router générique)
- `backend/app/api/routes/admin/payments.py` (routes admin)
- `backend/app/features/payment/handlers/` (handlers outbox)
- Plusieurs migrations Alembic (cf. Phase 1)

### À modifier
- [backend/app/features/payment/models/payment.py](backend/app/features/payment/models/payment.py) → suppression colonnes `payzen_*`, ajout `provider_*`
- [backend/app/features/payment/models/payment_method.py](backend/app/features/payment/models/payment_method.py) → ajout colonnes
- [backend/app/api/routes/payzen.py](backend/app/api/routes/payzen.py) → refactor logique IPN vers outbox + provider
- [backend/app/core/config.py](backend/app/core/config.py) → settings Stripe/PayPal, MIME whitelist, AV config
- [backend/app/api/__init__.py](backend/app/api/__init__.py) → wiring nouveaux routers

### À déprécier puis supprimer (après 6 mois)
- Routes `/payzen/form-token`, `/payzen/ipn` → redirigent vers `/payments/initiate` et `/payments/webhooks/payzen`

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
