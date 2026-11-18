"""Back-office team roles (chantier accueil et messagerie, lot ROLE).

A superuser does everything. A team member who is not one has a
``staff_role`` that opens a few screens, by an explicit allow-list (a route
that does not name the role refuses it):

==================  =========================================  ===========
Role                Messaging channels                         Other
==================  =========================================  ===========
customer_service    customer service, technical support        orders (read)
sales               sales                                      orders (read),
                                                               quote requests
==================  =========================================  ===========

No role ever sees costs, supplier prices or margins (only superusers reveal
the internal fields), refunds, settings or suppliers. A team member signs in
to the back-office like a superuser: two-factor authentication, admin
network, admin origin, audit of the sign-ins.
"""

from __future__ import annotations

from typing import Any

from app.features.messaging.models import CHANNELS

STAFF_ROLES: dict[str, tuple[str, ...]] = {
    "customer_service": ("customer_service", "technical"),
    "sales": ("sales",),
}


def is_back_office(user: Any) -> bool:
    """A superuser or a team member with a role."""
    return bool(getattr(user, "is_superuser", False)) or (
        getattr(user, "staff_role", None) in STAFF_ROLES
    )


def staff_channels(user: Any) -> tuple[str, ...]:
    """The messaging channels a back-office user works on."""
    if getattr(user, "is_superuser", False):
        return CHANNELS
    return STAFF_ROLES.get(getattr(user, "staff_role", None) or "", ())


def has_role(user: Any, *roles: str) -> bool:
    """A superuser, or a team member with one of ``roles``."""
    return bool(getattr(user, "is_superuser", False)) or (
        getattr(user, "staff_role", None) in roles
    )


__all__ = ["STAFF_ROLES", "has_role", "is_back_office", "staff_channels"]
