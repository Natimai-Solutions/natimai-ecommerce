# Registre des codes d'erreur — fastapi-ecommerce

Ce document est le **contrat API** entre le backend et le frontend pour la
gestion des erreurs. Un code listé ici est considéré **stable** : le renommer
ou le supprimer est un breaking change. Toute modification doit être versionnée
ici avant d'être déployée.

---

## Format du payload d'erreur

Toutes les erreurs applicatives retournées par l'API suivent cette enveloppe :

```json
{
  "error": {
    "code": "payment.not_manual",
    "message": "Payment provider 'payzen' is not manual",
    "details": { "provider_code": "payzen", "payment_id": "..." }
  }
}
```

| Champ         | Type                  | Description                                                |
|---------------|-----------------------|------------------------------------------------------------|
| `code`        | `string` (stable)     | Identifiant machine-readable. Contrat avec le frontend.    |
| `message`     | `string` (debug only) | En anglais. Destiné aux devs/logs. **Ne pas afficher à l'utilisateur.** |
| `details`     | `object` (optionnel)  | Variables d'interpolation pour la traduction i18n (`{{provider_code}}`, `{{max_bytes}}`). |

### Cas particuliers

- **Validation Pydantic (HTTP 422)** : le format FastAPI standard est conservé
  (`{"detail": [...]}`) — les librairies UI savent le parser.
- **Erreurs 500 inattendues** : retournent `{ "error": { "code": "internal.server_error" } }`
  sans détail (sécurité — pas d'info sensible en prod).

---

## Convention de nommage des codes

```
<domain>.<subdomain>.<what>
```

- Tout en **snake_case**, séparateurs `.`, maximum **3 segments**.
- `domain` = périmètre métier (`payment`, `attachment`, `order`, `user`…).
- `subdomain` = sous-périmètre si nécessaire (`provider`, `method`, `webhook`).
- `what` = ce qui s'est passé (`not_found`, `inactive`, `invalid_signature`).

---

## Infrastructure backend

### `AppError`

```python
# app/core/errors.py
class AppError(Exception):
    def __init__(
        self,
        *,
        code: str,
        status_code: int = 400,
        message: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.code = code
        self.status_code = status_code
        self.message = message or code
        self.details = details or {}
```

### Handler global (enregistré dans `main.py`)

```python
@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
            }
        },
    )
```

### Lever une erreur

```python
raise AppError(
    code="payment.not_manual",
    status_code=400,
    message=f"Payment provider '{payment.provider_code}' is not manual",
    details={"provider_code": payment.provider_code, "payment_id": str(payment.id)},
)
```

### Mapper une exception existante

Pour migrer progressivement sans tout refactorer d'un coup, un second handler
mappe les exceptions métier existantes vers `AppError` :

```python
@app.exception_handler(RecordNotFoundError)
async def record_not_found_handler(_req: Request, exc: RecordNotFoundError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {
        "code": "internal.record_not_found", "message": str(exc), "details": {}
    }})
```

---

## Registre des codes

### Domaine `payment`

| Code                                          | HTTP | Déclencheur                                                        | `details` exposés                       |
|-----------------------------------------------|------|--------------------------------------------------------------------|------------------------------------------|
| `payment.not_found`                           | 404  | `crud_payment.read` lève `RecordNotFoundError`                     | `payment_id`                             |
| `payment.not_owned`                           | 403  | `payment.user_id != current_user.id`                               | `payment_id`                             |
| `payment.not_manual`                          | 400  | Approve/reject sur un payment non-manuel                           | `payment_id`, `provider_code`            |
| `payment.not_document_validated`              | 400  | Upload document sur un payment non document-validé                 | `payment_id`, `provider_code`            |
| `payment.provider.unknown`                    | 400  | `get_provider()` ne trouve pas le code                             | `provider_code`                          |
| `payment.provider.unsupported_for_initiation` | 400  | Provider connu mais sans `initiate_payment`                        | `provider_code`                          |
| `payment.provider.api_resolution_failed`      | 400  | Erreur de config du provider API                                   | `provider_code`                          |
| `payment.method.not_found`                    | 404  | `payment_method_id` inconnu                                        | `payment_method_id`                      |
| `payment.method.inactive`                     | 400  | Méthode de paiement désactivée                                     | `payment_method_id`                      |
| `payment.method.resolution_failed`            | 400  | Erreur lors du résolution du provider pour la méthode              | `payment_method_id`                      |
| `payment.webhook.invalid_signature`           | 400  | `validate_ipn_signature` échoue (signature IPN incorrecte)         | `provider_code`                          |
| `payment.webhook.payment_not_found`           | 400  | IPN reçue pour un `order_id` / `provider_reference` inconnu       | `provider_code`, `provider_reference`    |
| `payment.webhook.missing_order_id`            | 400  | IPN reçue sans `order_id` dans le payload                         | `provider_code`                          |

### Domaine `attachment`

| Code                              | HTTP | Déclencheur                                          | `details` exposés              |
|-----------------------------------|------|------------------------------------------------------|--------------------------------|
| `attachment.mimetype_unsupported` | 400  | MIME non dans la whitelist                           | `mimetype`, `allowed`          |
| `attachment.too_large`            | 400  | Taille déclarée > max_bytes                         | `max_bytes`                    |
| `attachment.validation_failed`    | 400  | `AttachmentValidationError` générique               | `reason`                       |
| `attachment.key_mismatch`         | 400  | Le `file_key` du `document-uploaded` ne correspond pas à l'intent | `file_key`  |

### Domaine `order`

| Code                    | HTTP | Déclencheur                          | `details` exposés |
|-------------------------|------|--------------------------------------|-------------------|
| `order.not_found`       | 404  | Commande introuvable                 | `order_id`        |
| `order.not_owned`       | 403  | Commande appartenant à un autre user | `order_id`        |
| `order.status.not_found`| 404  | Statut de commande inconnu           | `status_name`     |
| `order.admin_required`  | 403  | Endpoint Order réservé aux admins    | `resource`        |

### Domaine `internal`

| Code                     | HTTP | Déclencheur                                                | `details` exposés |
|--------------------------|------|------------------------------------------------------------|-------------------|
| `internal.server_error`  | 500  | Exception inattendue (catch-all)                           | *(aucun en prod)*  |
| `internal.record_not_found` | 404 | `RecordNotFoundError` non capturé plus haut             | *(optionnel)*      |
| `internal.unavailable`   | 503  | Service tiers indisponible (provider API, stockage, etc.)  | `service`          |

---

## Côté frontend

### Utilitaire de traduction

```ts
// src/lib/errors.ts

export type ApiError = {
  code: string;
  message: string;
  details: Record<string, unknown>;
};

export type ApiErrorResponse = { error: ApiError };

export function extractApiError(response: unknown): ApiError | null {
  if (
    response &&
    typeof response === "object" &&
    "error" in response &&
    typeof (response as ApiErrorResponse).error?.code === "string"
  ) {
    return (response as ApiErrorResponse).error;
  }
  return null;
}

export function translateApiError(
  error: ApiError,
  t: (key: string, opts?: Record<string, unknown>) => string
): string {
  const key = `errors.${error.code}`;
  const translated = t(key, error.details);
  // Si la clé n'existe pas, t() retourne la clé elle-même → fallback générique
  return translated === key ? t("errors.internal.server_error") : translated;
}
```

### Fichiers i18n (exemple `fr`)

```json
// locales/fr/errors.json
{
  "payment": {
    "not_found": "Paiement introuvable.",
    "not_owned": "Vous n'êtes pas autorisé à accéder à ce paiement.",
    "not_manual": "Ce paiement ne peut pas être validé manuellement.",
    "not_document_validated": "Ce paiement ne nécessite pas de document.",
    "provider": {
      "unknown": "Fournisseur de paiement inconnu : {{provider_code}}.",
      "unsupported_for_initiation": "Le fournisseur {{provider_code}} ne supporte pas l'initiation en ligne.",
      "api_resolution_failed": "Erreur de configuration du fournisseur de paiement."
    },
    "method": {
      "not_found": "Méthode de paiement introuvable.",
      "inactive": "Cette méthode de paiement est désactivée.",
      "resolution_failed": "Impossible de résoudre le fournisseur pour cette méthode de paiement."
    },
    "webhook": {
      "invalid_signature": "Signature du webhook invalide.",
      "payment_not_found": "Paiement introuvable pour cette notification.",
      "missing_order_id": "Notification reçue sans référence de commande."
    }
  },
  "attachment": {
    "mimetype_unsupported": "Type de fichier non supporté. Types autorisés : {{allowed}}.",
    "too_large": "Fichier trop volumineux (maximum {{max_bytes}} octets).",
    "validation_failed": "Fichier invalide : {{reason}}.",
    "key_mismatch": "Le fichier téléversé ne correspond pas à l'intention déclarée."
  },
  "order": {
    "not_found": "Commande introuvable.",
    "not_owned": "Vous n'êtes pas autorisé à accéder à cette commande.",
    "admin_required": "Accès réservé aux administrateurs.",
    "status": {
      "not_found": "Statut de commande inconnu."
    }
  },
  "internal": {
    "server_error": "Une erreur inattendue s'est produite. Veuillez réessayer.",
    "unavailable": "Le service {{service}} est temporairement indisponible."
  }
}
```

---

## Cycle de vie d'un code

1. **Ajout** : ajouter la ligne dans le registre + implémenter dans le backend + ajouter la clé i18n sur tous les fichiers de langue front.
2. **Modification du libellé** : uniquement côté i18n frontend — le `code` et les `details` ne changent pas.
3. **Dépréciation** : marquer la ligne `⚠️ deprecated` dans le registre + émettre le nouveau code en parallèle du vieux pendant une release.
4. **Suppression** : possible seulement après que les deux parties (back + front) n'utilisent plus l'ancien code.

---

## Plan de migration (roll-out progressif)

| Étape | Périmètre                          | Fichiers backend touchés                        |
|-------|------------------------------------|-------------------------------------------------|
| 1     | Infrastructure                     | `app/core/errors.py`, `app/main.py`             |
| 2     | Domaine `payment`                  | `api/routes/payments.py`, `api/routes/admin_payments.py` |
| 3     | Domaine `attachment`               | `api/routes/payments.py` (upload endpoints)     |
| 4     | Domaine `order` + reste            | À planifier                                     |

Les domaines non encore migrés continuent à retourner des `HTTPException`
brutes — le frontend les traite via le fallback `internal.server_error`.
