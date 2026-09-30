"""Convention temporelle du backend : UTC conscient du fuseau, partout.

Depuis sqlmodel 0.0.45, les colonnes `datetime` sont des `timestamptz` : une
valeur écrite doit porter un fuseau, une valeur lue revient en UTC conscient.
Les datetimes naïfs qui entrent encore (paramètres de requête, charges utiles
JSON sans fuseau, données antérieures à la migration) sont de l'UTC horloge
murale : on les déclare tels quels plutôt que de les rejeter.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Maintenant, en UTC conscient du fuseau."""
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Ramène `value` en UTC conscient ; une valeur naïve est lue comme UTC."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
