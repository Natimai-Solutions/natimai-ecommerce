# Guide d'usage - Providers de notifications

Ce document explique comment utiliser et changer les providers de notifications (email et Slack) pour les evenements paiement.

## 1. Principe

Le systeme de notifications est base sur un registry de providers, comme pour les paiements.

- Canal email: provider configure via `PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER`
- Canal Slack: provider configure via `PAYMENT_NOTIFICATIONS_SLACK_PROVIDER`

Providers disponibles actuellement:

- `mailgun` (email)
- `slack_webhook` (Slack)
- `noop` (aucun envoi, utile en dev/test)

## 2. Variables d'environnement

### 2.1 Email

- `PAYMENT_NOTIFICATIONS_EMAIL_ENABLED` (true/false)
- `PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER` (`mailgun` ou `noop`)

### 2.2 Slack

- `PAYMENT_NOTIFICATIONS_SLACK_ENABLED` (true/false)
- `PAYMENT_NOTIFICATIONS_SLACK_PROVIDER` (`slack_webhook` ou `noop`)
- `PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL` (URL webhook Slack)

### 2.3 Mailgun

- `MAILGUN_API_BASE_URL` (defaut: `https://api.mailgun.net/v3`)
- `MAILGUN_DOMAIN`
- `MAILGUN_API_KEY`
- `MAILGUN_FROM_EMAIL`
- `MAILGUN_FROM_NAME` (optionnel)
- `MAILGUN_TIMEOUT_SECONDS` (optionnel, defaut 10)

## 3. Exemples de configuration

### 3.1 Production (Mailgun + Slack)

```env
PAYMENT_NOTIFICATIONS_EMAIL_ENABLED=true
PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER=mailgun

PAYMENT_NOTIFICATIONS_SLACK_ENABLED=true
PAYMENT_NOTIFICATIONS_SLACK_PROVIDER=slack_webhook
PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL=https://hooks.slack.com/services/XXX/YYY/ZZZ

MAILGUN_API_BASE_URL=https://api.mailgun.net/v3
MAILGUN_DOMAIN=mg.example.com
MAILGUN_API_KEY=key-xxxxxxxxxxxxxxxxxxxx
MAILGUN_FROM_EMAIL=no-reply@example.com
MAILGUN_FROM_NAME=FastAPI Ecommerce
MAILGUN_TIMEOUT_SECONDS=10
```

### 3.2 Dev/Test (pas d'envoi reel)

```env
PAYMENT_NOTIFICATIONS_EMAIL_ENABLED=true
PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER=noop

PAYMENT_NOTIFICATIONS_SLACK_ENABLED=true
PAYMENT_NOTIFICATIONS_SLACK_PROVIDER=noop
```

## 4. Evenements concernes

Les notifications sont declenchees par les evenements outbox paiement, par exemple:

- `payment.webhook_received`
- `payment.awaiting_validation`
- `payment.document_required`
- `payment.captured`
- `payment.rejected`
- `payment.document_infected`

## 5. Conditions de fonctionnement

Pour que les notifications partent:

1. Les variables d'environnement doivent etre configurees.
2. Le service API doit tourner (publication des evenements).
3. Le worker ARQ doit tourner (consommation outbox et execution des handlers).

Si le worker n'est pas lance, aucun envoi n'est effectue meme si l'API publie bien les evenements.

## 6. Basculer rapidement d'un provider a un autre

### Email

- Provider actif via `PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER`
- Exemples:
  - `mailgun` pour envoi reel
  - `noop` pour neutraliser les envois

### Slack

- Provider actif via `PAYMENT_NOTIFICATIONS_SLACK_PROVIDER`
- Exemples:
  - `slack_webhook` pour envoi reel
  - `noop` pour neutraliser les envois

## 7. Ajouter un nouveau provider

Pour ajouter un provider personnalise:

1. Creer un module dans `app/features/notification/providers/`.
2. Implementer la classe qui suit l'interface `NotificationProvider`.
3. Enregistrer le provider dans `SUPPORTED_NOTIFICATION_PROVIDERS`.
4. Configurer la variable d'environnement du canal cible avec le nouveau code provider.

Checklist minimale:

- gerer le succes (`delivered=True`)
- gerer les erreurs (`delivered=False`, `error` renseigne)
- ajouter des tests unitaires provider + service

## 8. Verification rapide

Commandes utiles:

```powershell
uv run ruff check app/features/notification/providers app/features/payment/services/notifications.py
uv run pytest app/tests/test_notification_providers.py app/tests/test_payment_notification_service.py
```

Si besoin, completer avec des tests des handlers outbox paiement:

```powershell
uv run pytest app/tests/test_payment_outbox_handlers.py
```
