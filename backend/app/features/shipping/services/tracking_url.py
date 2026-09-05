"""Customer-facing carrier tracking links built from a ``{ref}`` template."""

from __future__ import annotations

from urllib.parse import quote

TRACKING_REF_PLACEHOLDER = "{ref}"


def carrier_tracking_url(template: str | None, ref: str | None) -> str | None:
    """Build a carrier tracking URL from a ``{ref}`` template, URL-encoding the ref.

    Returns None unless the template is a real https URL and a ref is present
    (https-only guards against a malicious ``javascript:`` template).
    """
    if template and ref and template.startswith("https://"):
        return template.replace(TRACKING_REF_PLACEHOLDER, quote(ref, safe=""))
    return None


def validate_tracking_url_template(template: str | None) -> str | None:
    """Admin-side guard: a template is https and carries the ``{ref}`` placeholder.

    Empty strings are stored as None (carrier without a public tracking page).
    Raises ``ValueError`` with a human-readable reason otherwise.
    """
    if template is None:
        return None
    cleaned = template.strip()
    if not cleaned:
        return None
    if not cleaned.startswith("https://"):
        raise ValueError("Le gabarit de suivi doit commencer par https://")
    if TRACKING_REF_PLACEHOLDER not in cleaned:
        raise ValueError(
            "Le gabarit de suivi doit contenir {ref} (emplacement du numéro)"
        )
    return cleaned
