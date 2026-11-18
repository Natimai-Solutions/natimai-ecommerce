"""Messages to the shop's operator, in the operator's language.

Alerts (``ALERT_WEBHOOK_URL``) and the staff notifications are read by the
person who runs the shop, not by customers: they are rendered here, server
side, in the language of the runtime setting ``operator_locale`` — the shop's
default language when it is not set (decision of 18/11/2026: an English
speaker starting a shop must be able to run it).

Each message is a key with an English and a French template; ``{name}``
placeholders take the values given. A new alert adds its key here, in both
languages (``app/tests/test_operator_messages.py`` checks it).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

#: key → (English, French)
MESSAGES: dict[str, tuple[str, str]] = {
    # --- Background tasks -------------------------------------------------
    "tasks.failed": (
        "Task “{name}” failed: {error}",
        "Tâche « {name} » a échoué : {error}",
    ),
    "tasks.partial": (
        "Task “{name}” finished with errors: {error}",
        "Tâche « {name} » s'est terminée avec des erreurs : {error}",
    ),
    "supplier.sync_failed": (
        "Catalogue sync of {supplier} failed: {error}",
        "Synchronisation catalogue {supplier} en échec : {error}",
    ),
    # --- Outbox / workers -------------------------------------------------
    "outbox.stuck": (
        "Event queue stuck: an event has been waiting for {minutes} min "
        "(payments, invoices, e-mails are no longer processed). Check the "
        "outbox-poller service.",
        "File d'événements bloquée : un événement attend depuis {minutes} min "
        "(paiements, factures, e-mails ne sont plus traités). Vérifiez le "
        "service outbox-poller.",
    ),
    "outbox.event_abandoned": (
        "Outbox event {event_type} ({event_id}) abandoned after {tries} "
        "attempts: {error}",
        "Événement outbox {event_type} ({event_id}) abandonné après {tries} "
        "tentatives : {error}",
    ),
    "outbox.handler_abandoned": (
        "Outbox handler {handler} abandoned after {tries} attempts (event "
        "{event_id}, type {event_type}): {error}. Replay it from “System status”.",
        "Traitement outbox {handler} abandonné après {tries} tentatives "
        "(événement {event_id}, type {event_type}) : {error}. Rejouez-le depuis "
        "« État du système ».",
    ),
    "outbox.health_error": (
        "Health check in error: {error}",
        "Contrôle de santé en erreur : {error}",
    ),
    "outbox.degraded": (
        "Outbox degraded: {orphaned} orphaned job(s), {missing} missing job(s) "
        "(recovery {recovery}).",
        "Outbox dégradé : {orphaned} job(s) orphelin(s), {missing} job(s) "
        "manquant(s) (reprise {recovery}).",
    ),
    "outbox.recovery_on": ("on", "active"),
    "outbox.recovery_off": ("OFF", "DÉSACTIVÉE"),
    "outbox.recovered": ("Outbox back to healthy.", "Outbox rétabli."),
    # --- E-mails ----------------------------------------------------------
    "email.abandoned": (
        "E-mail abandoned after {tries} attempts ({event_type}): {error}. "
        "Check the e-mail provider; other e-mails may be failing too (e-mail "
        "log).",
        "E-mail abandonné après {tries} tentatives ({event_type}) : {error}. "
        "Vérifiez le fournisseur d'e-mails ; d'autres envois échouent peut-être "
        "(journal des e-mails).",
    ),
    # --- Departures -------------------------------------------------------
    "departures.below_threshold": (
        "Cut-off passed, threshold not reached: {names}. Close them (forcing) "
        "or push the date back from “Grouped departures”. Until then, new "
        "orders go to the following departure (opened in advance for a "
        "recurring one); with none, to no departure.",
        "Date limite passée, seuil non atteint : {names}. Clôturez (en forçant) "
        "ou repoussez la date depuis « Départs groupés ». D'ici là, les nouvelles "
        "commandes vont au départ suivant (ouvert d'avance pour un départ "
        "récurrent) ; sans départ suivant, à aucun.",
    ),
    # --- Payments ---------------------------------------------------------
    "payments.receipts_kept": (
        "Order {order}: settled by payment {payment}, but {count} pending "
        "payment(s) already carry money received ({amounts}). Settle it by hand "
        "(refund, or move it to the balance) from the order page.",
        "Commande {order} : réglée par le paiement {payment}, mais {count} "
        "paiement(s) en attente portent déjà des versements reçus ({amounts}). À "
        "régler à la main (remboursement ou report sur le solde) depuis la fiche "
        "de la commande.",
    ),
    "payments.auto_capture_refused": (
        "Automatic capture refused for payment {payment} (order {order}): "
        "{error}. Capture it by hand.",
        "Capture automatique refusée pour le paiement {payment} (commande "
        "{order}) : {error}. À capturer à la main.",
    ),
    "payments.void_refused": (
        "Authorisation release refused for payment {payment} (order {order}, "
        "cancelled): {error}. Release it at the provider.",
        "Annulation d'autorisation refusée pour le paiement {payment} (commande "
        "{order} annulée) : {error}. À libérer chez le prestataire.",
    ),
    "payments.authorization_expiring": (
        "Card authorisation of {amount} {currency} (payment {payment}, order "
        "{order}) authorised {age} d ago: it expires within {validity} d "
        "without capture. Capture it from Payments, or cancel the order to "
        "release it.",
        "Autorisation carte de {amount} {currency} (paiement {payment}, commande "
        "{order}) autorisée il y a {age} j : elle expire sous {validity} j sans "
        "capture. Capturer depuis Paiements, ou annuler la commande pour la "
        "libérer.",
    ),
    "stock.paid_without_stock": (
        "Order {order} paid without stock: its reservation had been released "
        "and {count} item(s) are no longer available ({items}). Restock or "
        "refund.",
        "Commande {order} payée sans stock : sa réservation avait été libérée et "
        "{count} article(s) ne sont plus disponibles ({items}). À réapprovisionner "
        "ou à rembourser.",
    ),
    "gift_cards.refund_shortfall": (
        "Order {order} refunded: gift card credit already spent, to recover "
        "by hand — {details}",
        "Commande {order} remboursée : avoir de cartes cadeaux déjà dépensé, à "
        "récupérer manuellement — {details}",
    ),
    "gift_cards.shortfall_item": (
        "{code}: {missing} {currency} (account {account})",
        "{code} : {missing} {currency} (compte {account})",
    ),
    "gift_cards.partial_refund_review": (
        "Order {order} partly refunded: it issued gift cards ({codes}). Cancel "
        "them in “Gift cards” if the refund concerns them.",
        "Commande {order} remboursée en partie : elle a émis des cartes cadeaux "
        "({codes}). À annuler dans « Cartes cadeaux » si le remboursement les "
        "concerne.",
    ),
    "loyalty.points_not_reclaimed": (
        "Refund of order {order}: {points} loyalty point(s) already spent or "
        "converted could not be taken back.",
        "Remboursement de la commande {order} : {points} point(s) de fidélité "
        "déjà dépensés ou convertis n'ont pas pu être repris.",
    ),
    "invoice.identity_incomplete": (
        "Invoice not issued: the seller identity is incomplete ({missing}). "
        "Fill it in Settings → Legal identity.",
        "Facture non émise : l'identité du vendeur est incomplète ({missing}). "
        "Complétez-la dans Réglages → Identité légale.",
    ),
    # --- Staff notifications of payment events (e-mail / Slack) ----------
    "notify.payment.authorized": ("Payment authorised", "Paiement autorisé"),
    "notify.payment.captured": ("Payment validated", "Paiement validé"),
    "notify.payment.completed": ("Payment validated", "Paiement validé"),
    "notify.payment.rejected": ("Payment refused", "Paiement refusé"),
    "notify.payment.failed": ("Payment failed", "Paiement échoué"),
    "notify.payment.refunded": ("Refund done", "Remboursement effectué"),
    "notify.payment.cancelled": ("Payment cancelled", "Paiement annulé"),
    "notify.payment.amount_mismatch": (
        "⚠ Inconsistent amount received — action required",
        "⚠ Montant encaissé incohérent — action requise",
    ),
    "notify.payment.awaiting_validation": (
        "New order to handle — payment to validate",
        "Nouvelle commande à traiter — paiement à valider",
    ),
    "notify.payment.document_required": (
        "New order to handle — purchase order expected",
        "Nouvelle commande à traiter — bon de commande attendu",
    ),
    # --- Messaging: a customer message waits for the team -------------------
    "messaging.staff_subject": (
        "New customer message — {number} ({channel})",
        "Nouveau message client — {number} ({channel})",
    ),
    "messaging.staff_body": (
        "A customer wrote in conversation {number} ({channel}) and nobody has "
        "read it for ten minutes. Open it in the back-office: {url}",
        "Un client a écrit dans la conversation {number} ({channel}) et "
        "personne ne l'a lu depuis dix minutes. Ouvrez-la dans "
        "l'administration : {url}",
    ),
    "messaging.channel.customer_service": ("customer service", "service client"),
    "messaging.channel.technical": ("technical support", "support technique"),
    "messaging.channel.sales": ("sales", "service commercial"),
    # --- Quote requests sent to the support address -----------------------
    "quote.subtitle_account": (
        "Request sent from a customer's cart.",
        "Demande transmise depuis le panier client.",
    ),
    "quote.subtitle_public": (
        "Request sent from the public cart.",
        "Demande transmise depuis le panier public.",
    ),
    "quote.user": ("Account", "Utilisateur"),
    "quote.email": ("E-mail", "Email"),
    "quote.name": ("Name", "Nom"),
    "quote.phone": ("Phone", "Téléphone"),
    "quote.address": ("Delivery address", "Adresse de livraison"),
    "quote.notes": ("Notes", "Notes"),
    "notify.subject": (
        "[Payments] {label} — order {order}",
        "[Paiements] {label} — commande {order}",
    ),
}


def operator_locale() -> str:
    """The operator's language: ``operator_locale``, else the shop's default."""
    from app.core import runtime_settings

    for key in ("operator_locale", "shop_default_locale"):
        try:
            value = runtime_settings.peek(key)
        except Exception:  # noqa: BLE001 - unknown setting / no snapshot
            value = None
        if isinstance(value, str) and value.strip():
            return value.strip().lower()[:2]
    return "fr"


def operator_text(key: str, locale: str | None = None, **params: Any) -> str:
    """The message ``key`` in the operator's language, filled with
    ``params``. An unknown key comes back as is (never a crash in an alert)."""
    templates = MESSAGES.get(key)
    if templates is None:
        logger.warning("Unknown operator message %s", key)
        return key
    lang = (locale or operator_locale())[:2]
    template = templates[1] if lang == "fr" else templates[0]
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        logger.warning("Operator message %s: missing values in %s", key, params)
        return template


async def alert(key: str, *, source: str = "backend", **params: Any) -> bool:
    """Post the operator message ``key`` to the alert webhook."""
    from app.core.alerting import send_alert

    return await send_alert(operator_text(key, **params), source=source)


__all__ = ["MESSAGES", "alert", "operator_locale", "operator_text"]
