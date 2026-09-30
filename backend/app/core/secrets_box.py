"""Supplier credentials encrypted at rest (R4 / S3).

The integration secrets of the historical suppliers (Ingram, Icecat) stay in
the environment. A supplier fed by a **file URL** (Foxway, Picata…) is
declared from the admin, with its portal login: those credentials are
stored in ``suppliers.credentials_encrypted``, encrypted with Fernet
(AES-128-CBC + HMAC-SHA256) under ``SUPPLIER_SECRETS_KEY``.

* The API never returns them: it only says whether some are stored.
* Without the key nothing can be stored (explicit error), and stored values
  read as absent (logged) rather than crashing a sync.
* Rotating the key: decrypt with the old one, re-encrypt with the new one —
  :func:`encrypt_json` accepts a ``MultiFernet`` ring through
  ``SUPPLIER_SECRETS_KEY`` holding several comma-separated keys, the first
  one encrypting.

Generate a key: ``python -c "from cryptography.fernet import Fernet;
print(Fernet.generate_key().decode())"``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)


class SecretsKeyMissing(RuntimeError):
    """``SUPPLIER_SECRETS_KEY`` is not set (or not a valid Fernet key)."""


def _fernet() -> Any:
    from cryptography.fernet import Fernet, MultiFernet

    raw = (settings.SUPPLIER_SECRETS_KEY or "").strip()
    keys = [k.strip() for k in raw.split(",") if k.strip()]
    if not keys:
        raise SecretsKeyMissing("SUPPLIER_SECRETS_KEY is not set")
    try:
        return MultiFernet([Fernet(key.encode()) for key in keys])
    except (ValueError, TypeError) as exc:
        raise SecretsKeyMissing(f"SUPPLIER_SECRETS_KEY is invalid: {exc}") from exc


def secrets_key_configured() -> bool:
    try:
        _fernet()
    except SecretsKeyMissing:
        return False
    return True


def encrypt_json(values: dict[str, str]) -> str:
    """Encrypt a small dict of secrets. Raises :class:`AppError` without key."""
    try:
        box = _fernet()
    except SecretsKeyMissing as exc:
        raise AppError(
            code="supplier.credentials.no_key",
            status_code=400,
            message=(
                "Les identifiants ne peuvent pas être enregistrés : "
                "SUPPLIER_SECRETS_KEY n'est pas configurée sur le serveur"
            ),
            details={"setting": "SUPPLIER_SECRETS_KEY"},
        ) from exc
    token: bytes = box.encrypt(json.dumps(values).encode())
    return token.decode()


def decrypt_json(token: str | None) -> dict[str, str]:
    """Decrypt stored secrets; ``{}`` when absent or unreadable (logged)."""
    if not token:
        return {}
    from cryptography.fernet import InvalidToken

    try:
        data = json.loads(_fernet().decrypt(token.encode()))
    except SecretsKeyMissing:
        logger.error(
            "Stored supplier credentials cannot be read: no SUPPLIER_SECRETS_KEY"
        )
        return {}
    except (InvalidToken, ValueError):
        logger.error("Stored supplier credentials cannot be read with the current key")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


__all__ = [
    "SecretsKeyMissing",
    "decrypt_json",
    "encrypt_json",
    "secrets_key_configured",
]
