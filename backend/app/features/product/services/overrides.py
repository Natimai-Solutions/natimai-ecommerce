"""Verrous par champ sur les produits synchronisés (A14).

Un produit fournisseur est réécrit à chaque synchronisation Ingram et à chaque
enrichissement Icecat. Pour qu'un admin puisse corriger un titre, une
description ou une image sans être écrasé, ``Product.overridden_fields`` liste
les champs qu'il a posés à la main : les deux flux d'écriture automatiques
**doivent** retirer ces clés de ce qu'ils appliquent. Ce module est le seul
endroit qui connaît la règle — l'admin y ajoute des verrous, la sync et
l'enrichissement les respectent, l'admin peut en retirer.

Le choix (b) « verrous » plutôt que (a) « colonnes d'override » signifie que
la valeur fournisseur n'est pas conservée à côté : libérer un champ ne la
restaure pas sur-le-champ, c'est la prochaine synchronisation (toutes les
2 h) ou le prochain enrichissement qui la ramène.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: Drapeaux et tenue de livre : jamais des « contenus » qu'un admin verrouille.
LOCK_EXEMPT_FIELDS = frozenset({"is_active", "is_admin_active", "overridden_fields"})


def merge_locks(existing: Iterable[str] | None, edited: Iterable[str]) -> list[str]:
    """Ajouter les champs édités aux verrous existants (trié, sans doublon)."""
    locks = set(existing or ()) | {f for f in edited if f not in LOCK_EXEMPT_FIELDS}
    return sorted(locks)


def release_lock(existing: Iterable[str] | None, field: str) -> list[str]:
    """Retirer un verrou ; renvoie la liste restante (trié)."""
    return sorted(f for f in (existing or ()) if f != field)


def strip_locked(
    data: Mapping[str, Any], locked: Iterable[str] | None
) -> dict[str, Any]:
    """Copie de ``data`` sans les champs verrouillés.

    Omettre une clé d'une mise à jour partielle laisse la valeur persistée
    intacte : c'est ainsi que la sync et l'enrichissement « respectent » un
    verrou, sans avoir à connaître la valeur de l'admin.
    """
    locks = set(locked or ())
    if not locks:
        return dict(data)
    return {key: value for key, value in data.items() if key not in locks}
