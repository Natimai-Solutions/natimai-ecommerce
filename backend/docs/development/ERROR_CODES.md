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
| `payment.provider.gateway_error`              | 502  | Provider API (ex. PayZen) retourne une erreur d'initiation         | `provider_code`, `error_code`            |
| `payment.provider.invalid_response`           | 502  | Provider API retourne une réponse invalide/incomplète              | `provider_code`, `reason`                |
| `payment.method.not_found`                    | 404  | `payment_method_id` inconnu                                        | `payment_method_id`                      |
| `payment.method.inactive`                     | 400  | Méthode de paiement désactivée                                     | `payment_method_id`                      |
| `payment.method.resolution_failed`            | 400  | Erreur lors du résolution du provider pour la méthode              | `payment_method_id`                      |
| `payment.webhook.invalid_signature`           | 400  | `validate_ipn_signature` échoue (signature IPN incorrecte)         | `provider_code`                          |
| `payment.webhook.payment_not_found`           | 400  | IPN reçue pour un `order_id` / `provider_reference` inconnu       | `provider_code`, `provider_reference`    |
| `payment.webhook.missing_order_id`            | 400  | IPN reçue sans `order_id` dans le payload                         | `provider_code`                          |

### Domaine `ai_search`

| Code                           | HTTP | Déclencheur                                          | `details` exposés |
|--------------------------------|------|------------------------------------------------------|-------------------|
| `ai_search.search.failed`      | 500  | Echec inattendu de recherche IA                      | `query`, `reason` |
| `ai_search.suggestions.failed` | 500  | Echec inattendu de génération de suggestions IA      | `reason`          |

### Domaine `attachment`

| Code                              | HTTP | Déclencheur                                          | `details` exposés              |
|-----------------------------------|------|------------------------------------------------------|--------------------------------|
| `attachment.mimetype_unsupported` | 400  | MIME non dans la whitelist                           | `mimetype`, `allowed`          |
| `attachment.too_large`            | 400  | Taille déclarée > max_bytes                         | `max_bytes`                    |
| `attachment.validation_failed`    | 400  | `AttachmentValidationError` générique               | `reason`                       |
| `attachment.key_mismatch`         | 400  | Le `file_key` du `document-uploaded` ne correspond pas à l'intent | `file_key`  |

### Domaine `address`

| Code                   | HTTP | Déclencheur                                   | `details` exposés            |
|------------------------|------|-----------------------------------------------|------------------------------|
| `address.not_found`    | 404  | Adresse introuvable                            | `address_id`                 |
| `address.not_owned`    | 403  | Accès à des adresses d'un autre utilisateur    | `user_id`                    |
| `address.type.invalid` | 400  | Type d'adresse invalide                        | `address_type`, `allowed`    |

### Domaine `notification`

| Code                     | HTTP | Déclencheur                                          | `details` exposés |
|--------------------------|------|------------------------------------------------------|-------------------|
| `notification.not_found` | 404  | Notification introuvable pour l'utilisateur          | `notification_id` |
| `notification.not_owned` | 403  | Accès aux notifications d'un autre utilisateur       | `user_id`         |

### Domaine `review`

| Code                   | HTTP | Déclencheur                                        | `details` exposés         |
|------------------------|------|----------------------------------------------------|---------------------------|
| `review.not_found`     | 404  | Avis introuvable                                   | `review_id` / `user_id`, `product_id` |
| `review.not_owned`     | 403  | Accès aux avis d'un autre utilisateur              | `user_id`                 |
| `review.already_exists`| 400  | L'utilisateur a déjà un avis pour ce produit       | `user_id`, `product_id`   |

### Domaine `wishlist`

| Code                              | HTTP | Déclencheur                                 | `details` exposés            |
|-----------------------------------|------|---------------------------------------------|------------------------------|
| `wishlist.not_found`              | 404  | Wishlist introuvable                         | `wishlist_id`                |
| `wishlist.not_owned`              | 403  | Accès aux wishlists d'un autre utilisateur   | `user_id`                    |
| `wishlist.product.not_found`      | 404  | Produit introuvable                          | `product_id`                 |
| `wishlist.product.not_in_wishlist`| 404  | Produit absent de la wishlist                | `product_id`, `wishlist_id`  |

### Domaine `group`

| Code                            | HTTP | Déclencheur                                              | `details` exposés            |
|---------------------------------|------|----------------------------------------------------------|------------------------------|
| `group.authentication_required` | 403  | Endpoint group nécessitant un utilisateur authentifié    | `resource`                   |
| `group.admin_required`          | 403  | Endpoint group réservé aux administrateurs               | `resource`                   |
| `group.not_owned`               | 403  | Accès aux groupes d'un autre utilisateur                 | `user_id`                    |
| `group.user_membership.invalid` | 400  | Requête invalide d'ajout d'utilisateur dans un groupe    | `group_id`, `user_id`, `reason` |
| `group.user_not_in_group`       | 404  | Suppression d'un utilisateur absent du groupe            | `group_id`, `user_id`        |

### Domaine `group_security`

| Code                            | HTTP | Déclencheur                                        | `details` exposés |
|---------------------------------|------|----------------------------------------------------|-------------------|
| `group_security.admin_required` | 403  | Endpoint group_security réservé aux administrateurs| `resource`        |

### Domaine `login`

| Code                          | HTTP | Déclencheur                                               | `details` exposés        |
|-------------------------------|------|-----------------------------------------------------------|--------------------------|
| `login.credentials.invalid`   | 400  | Authentification email/mot de passe invalide              | `reason`                 |
| `login.user.inactive`         | 400  | Utilisateur authentifié mais désactivé                    | `user_id`                |
| `login.refresh_token.invalid` | 401  | Refresh token invalide (decode/payload/user/session)      | `reason`, `user_id`, `jti` |
| `login.refresh_token.revoked` | 401  | Refresh token déjà révoqué (reuse détectée)               | `user_id`, `jti`         |
| `login.refresh_token.expired` | 401  | Refresh token expiré                                      | `user_id`, `jti`         |

### Domaine `auth`

| Code                      | HTTP | Déclencheur                                                          | `details` exposés              |
|---------------------------|------|----------------------------------------------------------------------|--------------------------------|
| `auth.credentials.invalid`| 403  | Token invalide/malformé ou `type` de token non supporté             | `reason`, `token_type` (optionnel) |
| `auth.user.not_found`     | 404  | Utilisateur absent pour le `sub` du token                            | `user_id`                      |
| `auth.user.inactive`      | 400  | Utilisateur authentifié mais inactif                                  | `user_id`                      |
| `auth.user.unverified`    | 400  | Endpoint exigeant un utilisateur vérifié                              | `user_id`                      |
| `auth.superuser.required` | 403  | Endpoint exigeant des privilèges superuser                            | `user_id`                      |

### Domaine `resource`

| Code                             | HTTP | Déclencheur                                                      | `details` exposés                 |
|----------------------------------|------|------------------------------------------------------------------|-----------------------------------|
| `resource.authentication_required` | 403 | Endpoint générique (`BaseRouter`) nécessitant authentification   | `resource`, `permission`          |
| `resource.superuser_required`    | 403  | Endpoint générique (`BaseRouter`) exigeant un superuser          | `resource`, `permission`          |
| `resource.permission_denied`     | 403  | `check_user_permission` refuse l'action demandée                 | `resource`, `permission`, `user_id` |
| `resource.filter.unsupported`    | 400  | Paramètre `filter` brut utilisé sur endpoint non compatible       | `resource`, `filter`              |
| `resource.not_found`             | 404  | Lecture d'une ressource générique introuvable                    | `resource`, `id`                  |

### Domaine `cart`

| Code                            | HTTP | Déclencheur                                                  | `details` exposés                                 |
|---------------------------------|------|--------------------------------------------------------------|---------------------------------------------------|
| `cart.product.not_found`        | 404  | Produit du panier introuvable ou inactif                     | `product_id`                                      |
| `cart.item.not_found`           | 404  | Ligne de panier introuvable pour l'utilisateur               | `item_id`                                         |
| `cart.not_found`                | 404  | Panier introuvable pendant une opération sur item            | `cart_id`                                         |
| `cart.active.not_found`         | 400  | Aucun panier actif pour l'utilisateur                        | `user_id`                                         |
| `cart.empty`                    | 400  | Panier actif sans items                                      | `cart_id`                                         |
| `cart.total.invalid`            | 400  | Total checkout <= 0                                          | `cart_id`, `total_amount`, `currency`             |
| `cart.stock.insufficient`       | 409  | Stock local+fournisseur insuffisant pour la quantité demandée| `product_id`, `requested`, `local_available`, `supplier_available` |
| `cart.quote.unavailable`        | 503  | Service quote indisponible (EMAIL_SUPPORT non configuré)     | `setting`                                         |
| `cart.checkout.failed`          | 500  | Echec inattendu pendant le checkout                          | `reason`                                          |

### Domaine `discount`

| Code                      | HTTP | Déclencheur                                         | `details` exposés        |
|---------------------------|------|-----------------------------------------------------|---------------------------|
| `discount.coupon.invalid` | 400  | Validation d'un coupon invalide/inactif/expiré      | `coupon_code`, `reason`   |
| `discount.not_found`      | 404  | Incrément d'usage sur une réduction introuvable     | `discount_id`             |

### Domaine `currency_rate`

| Code                                        | HTTP | Déclencheur                                                  | `details` exposés |
|---------------------------------------------|------|--------------------------------------------------------------|-------------------|
| `currency_rate.active.not_found`            | 404  | Aucun taux actif trouvé pour une devise demandée             | `currency_code`   |
| `currency_rate.reference_currency.unsupported` | 400 | Tentative d'upsert sur la devise de référence XPF           | `currency_code`   |

### Domaine `product`

| Code                | HTTP | Déclencheur                                                      | `details` exposés               |
|---------------------|------|------------------------------------------------------------------|----------------------------------|
| `product.not_found` | 404  | Produit introuvable ou non exposable publiquement (non enrichi)  | `product_id`, `reason` (optionnel) |

### Domaine `supplier`

| Code                               | HTTP | Déclencheur                                                       | `details` exposés                       |
|------------------------------------|------|-------------------------------------------------------------------|------------------------------------------|
| `supplier.not_found`               | 404  | Fournisseur demandé absent du registre                            | `supplier_name`, `registered`            |
| `supplier.sync.disabled`           | 400  | Synchronisation fournisseur désactivée                            | `supplier_name`                          |
| `supplier.credentials.not_configured` | 500 | Identifiants fournisseur non configurés                          | `supplier_name`                          |
| `supplier.sync.queue_failed`       | 500  | Echec lors de la mise en file d'une synchronisation fournisseur   | `supplier_name`, `sync_type`, `reason`   |

### Domaine `icecat`

| Code                         | HTTP | Déclencheur                                              | `details` exposés                                     |
|------------------------------|------|----------------------------------------------------------|--------------------------------------------------------|
| `icecat.disabled`            | 400  | Intégration Icecat désactivée                           | `setting`                                              |
| `icecat.enrich.queue_failed` | 500  | Echec de mise en file d'un enrichissement unitaire      | `product_id`, `reason`                                 |
| `icecat.batch.queue_failed`  | 500  | Echec de mise en file d'un enrichissement batch         | `limit`, `reason`                                      |
| `icecat.test.failed`         | 500  | Erreur du test de récupération Icecat                   | `vendor_part_number`, `manufacturer`, `ean`, `upc`, `reason` |
| `icecat.search.upc.failed`   | 500  | Erreur de recherche Icecat par UPC                      | `upc`, `reason`                                        |
| `icecat.search.ean.failed`   | 500  | Erreur de recherche Icecat par EAN                      | `ean`, `reason`                                        |

### Domaine `internal_storage`

| Code                                          | HTTP | Déclencheur                                                  | `details` exposés                              |
|-----------------------------------------------|------|--------------------------------------------------------------|-------------------------------------------------|
| `internal_storage.backend.unsupported`        | 404  | Endpoint storage interne appelé hors backend local           | `setting`, `backend`, `expected`               |
| `internal_storage.token.invalid`              | 403  | Token de storage invalide (malformé/signature/expiré)       | `reason`                                        |
| `internal_storage.token.operation_not_allowed`| 403  | Token storage utilisé pour une mauvaise opération            | `expected`, `actual`                            |
| `internal_storage.content_type.invalid`       | 400  | `Content-Type` différent de la valeur autorisée par le token | `expected`, `received`                          |
| `internal_storage.content_length.invalid`     | 400  | En-tête `Content-Length` invalide                            | `content_length`                                |
| `internal_storage.file.too_large`             | 413  | Fichier au-delà de la taille autorisée                       | `max_bytes`, `content_length` ou `received_bytes` |

### Domaine `order`

| Code                    | HTTP | Déclencheur                          | `details` exposés |
|-------------------------|------|--------------------------------------|-------------------|
| `order.not_found`       | 404  | Commande introuvable                 | `order_id`        |
| `order.not_owned`       | 403  | Commande appartenant à un autre user | `order_id`, `user_id` |
| `order.status.not_found`| 404  | Statut de commande inconnu           | `status_name`     |
| `order.admin_required`  | 403  | Endpoint Order réservé aux admins    | `resource`        |

### Domaine `shipping`

| Code                                   | HTTP | Déclencheur                                  | `details` exposés              |
|----------------------------------------|------|----------------------------------------------|--------------------------------|
| `shipping.tracking.not_found`          | 404  | Tracking introuvable                         | `tracking_id`                  |
| `shipping.tracking.invalid_transition` | 400  | Transition de tracking invalide              | `tracking_id`, `reason`        |
| `shipping.route.path_required`         | 400  | Requête de devis sans chemin                 | `field`                        |
| `shipping.route.path_empty`            | 400  | Un chemin de devis ne contient aucune route  | `path_index`                   |
| `shipping.route.unknown_or_inactive`   | 400  | Route inconnue ou inactive dans un devis     | `route_ids`                    |
| `shipping.route.not_found`             | 404  | Aucun chemin optimal entre deux lieux        | `from_place_id`, `to_place_id` |

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
      "api_resolution_failed": "Erreur de configuration du fournisseur de paiement.",
      "gateway_error": "Le fournisseur de paiement a retourné une erreur.",
      "invalid_response": "Réponse invalide du fournisseur de paiement."
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
  "address": {
    "not_found": "Adresse introuvable.",
    "not_owned": "Vous n'êtes pas autorisé à accéder à ces adresses.",
    "type": {
      "invalid": "Type d'adresse invalide."
    }
  },
  "notification": {
    "not_found": "Notification introuvable.",
    "not_owned": "Vous n'êtes pas autorisé à accéder à ces notifications."
  },
  "review": {
    "not_found": "Avis introuvable.",
    "not_owned": "Vous n'êtes pas autorisé à accéder à ces avis.",
    "already_exists": "Vous avez déjà publié un avis pour ce produit."
  },
  "wishlist": {
    "not_found": "Wishlist introuvable.",
    "not_owned": "Vous n'êtes pas autorisé à accéder à ces wishlists.",
    "product": {
      "not_found": "Produit introuvable.",
      "not_in_wishlist": "Ce produit n'est pas dans la wishlist."
    }
  },
  "group": {
    "authentication_required": "Authentification requise.",
    "admin_required": "Accès réservé aux administrateurs.",
    "not_owned": "Vous n'êtes pas autorisé à accéder aux groupes d'un autre utilisateur.",
    "user_membership": {
      "invalid": "La demande d'affectation au groupe est invalide."
    },
    "user_not_in_group": "Cet utilisateur n'appartient pas à ce groupe."
  },
  "group_security": {
    "admin_required": "Accès réservé aux administrateurs."
  },
  "login": {
    "credentials": {
      "invalid": "Email ou mot de passe incorrect."
    },
    "user": {
      "inactive": "Utilisateur désactivé."
    },
    "refresh_token": {
      "invalid": "Refresh token invalide.",
      "revoked": "Refresh token révoqué.",
      "expired": "Refresh token expiré."
    }
  },
  "auth": {
    "credentials": {
      "invalid": "Identifiants d'authentification invalides."
    },
    "user": {
      "not_found": "Utilisateur introuvable.",
      "inactive": "Utilisateur inactif.",
      "unverified": "Utilisateur non vérifié."
    },
    "superuser": {
      "required": "Accès réservé aux superutilisateurs."
    }
  },
  "resource": {
    "authentication_required": "Authentification requise pour cette ressource.",
    "superuser_required": "Accès superutilisateur requis pour cette action.",
    "permission_denied": "Vous n'êtes pas autorisé à effectuer cette action.",
    "filter": {
      "unsupported": "Le filtre demandé n'est pas supporté sur cette ressource."
    },
    "not_found": "Ressource introuvable."
  },
  "ai_search": {
    "search": {
      "failed": "La recherche IA a échoué."
    },
    "suggestions": {
      "failed": "La génération des suggestions IA a échoué."
    }
  },
  "cart": {
    "product": {
      "not_found": "Produit introuvable."
    },
    "item": {
      "not_found": "Article de panier introuvable."
    },
    "not_found": "Panier introuvable.",
    "active": {
      "not_found": "Aucun panier actif trouvé."
    },
    "empty": "Le panier est vide.",
    "total": {
      "invalid": "Le total du panier doit être strictement positif."
    },
    "stock": {
      "insufficient": "Stock insuffisant pour ce produit."
    },
    "quote": {
      "unavailable": "Le service de demande de devis est indisponible."
    },
    "checkout": {
      "failed": "Le checkout a échoué."
    }
  },
  "discount": {
    "coupon": {
      "invalid": "Code coupon invalide."
    },
    "not_found": "R\u00e9duction introuvable."
  },
  "currency_rate": {
    "active": {
      "not_found": "Aucun taux de change actif n'a été trouvé pour cette devise."
    },
    "reference_currency": {
      "unsupported": "XPF est la devise de référence : aucun taux de conversion n'est requis."
    }
  },
  "product": {
    "not_found": "Produit introuvable."
  },
  "supplier": {
    "not_found": "Fournisseur introuvable.",
    "sync": {
      "disabled": "La synchronisation fournisseur est désactivée.",
      "queue_failed": "Impossible de lancer la synchronisation fournisseur."
    },
    "credentials": {
      "not_configured": "Les identifiants du fournisseur ne sont pas configurés."
    }
  },
  "icecat": {
    "disabled": "L'intégration Icecat est désactivée.",
    "enrich": {
      "queue_failed": "Impossible de lancer l'enrichissement Icecat."
    },
    "batch": {
      "queue_failed": "Impossible de lancer l'enrichissement Icecat en lot."
    },
    "test": {
      "failed": "Le test Icecat a échoué."
    },
    "search": {
      "upc": {
        "failed": "La recherche Icecat par UPC a échoué."
      },
      "ean": {
        "failed": "La recherche Icecat par EAN a échoué."
      }
    }
  },
  "internal_storage": {
    "backend": {
      "unsupported": "Le stockage interne est disponible uniquement avec FILE_STORAGE_BACKEND=local."
    },
    "token": {
      "invalid": "Le jeton de stockage est invalide.",
      "operation_not_allowed": "Le jeton de stockage ne permet pas cette opération."
    },
    "content_type": {
      "invalid": "Le type de contenu envoyé n'est pas autorisé."
    },
    "content_length": {
      "invalid": "L'en-tête Content-Length est invalide."
    },
    "file": {
      "too_large": "Le fichier dépasse la taille maximale autorisée."
    }
  },
  "order": {
    "not_found": "Commande introuvable.",
    "not_owned": "Vous n'êtes pas autorisé à accéder à cette commande.",
    "admin_required": "Accès réservé aux administrateurs.",
    "status": {
      "not_found": "Statut de commande inconnu."
    }
  },
  "shipping": {
    "tracking": {
      "not_found": "Suivi introuvable.",
      "invalid_transition": "Transition de suivi invalide."
    },
    "route": {
      "path_required": "Au moins un chemin est requis.",
      "path_empty": "Un chemin doit contenir au moins une route.",
      "unknown_or_inactive": "Une ou plusieurs routes sont inconnues ou inactives.",
      "not_found": "Aucun chemin de livraison n'a été trouvé entre ces deux lieux."
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
