"""Compatibilité des empreintes de mots de passe après le retrait de passlib.

Ces empreintes ont été produites par l'implémentation précédente
(passlib 1.7.4 + bcrypt 4.0.1, `CryptContext(schemes=["bcrypt"])`) et copiées
telles quelles. Ce sont les empreintes qui dorment en base : si l'une d'elles
cesse de se vérifier, les comptes correspondants sont enfermés dehors.

Les deux derniers cas sont les plus importants. passlib tronquait silencieusement
à 72 octets, alors que bcrypt >= 5 lève une ValueError : sans reproduction exacte
de cette troncature, tout mot de passe plus long devenait invérifiable.
"""

import pytest

from app.core.security import get_password_hash, verify_password

# (mot de passe en clair, empreinte produite par passlib avant migration)
LEGACY_HASHES: list[tuple[str, str]] = [
    # 28 octets
    (
        "correct horse battery staple",
        "$2b$12$bgcKJtZlolRSYXEXiQP6MeZz6H7z8z6EQZ.7wVzLupHCWevNzbQzC",
    ),
    # 30 octets
    (
        "Motdepasse-Élève-Tahiti-2026",
        "$2b$12$S5FV6FeFaWSd5zK5VP1dOeKCIM5QpDs8kYXCYnwkHtN21pguaLXBi",
    ),
    # 28 octets
    (
        "🔐-clé-très-longue-ç-ü",
        "$2b$12$xLhbQekluboWae9YCPkX8uj0EmwZY6CxwO8ITjdO.7vHQ20.VaHPi",
    ),
    # 1 octets
    ("a", "$2b$12$pQghzOsKsXFSUM6FdhPvpuMCjZhc470L5qQAL0KJ1IbNWgRVJgEkK"),
    # 72 octets
    (
        "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "$2b$12$ECBumhAnhi1FLakVbitdVe7/TPRCd.GZmeixA6UkFqvUyOGE7vhHe",
    ),
    # 100 octets
    (
        "yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",
        "$2b$12$tF5SzoflbnOf4pcF2AqFQukYhRqPwybLgsB8jDinZzWgocs0/JmQq",
    ),
    # 80 octets
    (
        "éééééééééééééééééééééééééééééééééééééééé",
        "$2b$12$9/SbGwTD5wS4KNlvCbm8CuYdEHfQgA0bKmEncIbUas34KXD3WGyHm",
    ),
]


@pytest.mark.parametrize(("plain", "hashed"), LEGACY_HASHES)
def test_legacy_passlib_hashes_still_verify(plain: str, hashed: str) -> None:
    assert verify_password(plain, hashed) is True


@pytest.mark.parametrize(("plain", "hashed"), LEGACY_HASHES)
def test_legacy_hashes_reject_a_wrong_password(plain: str, hashed: str) -> None:
    # La variante fautive est préfixée, pas suffixée : au-delà de 72 octets un
    # suffixe tombe dans la partie tronquée et donne le MÊME mot de passe.
    assert verify_password("faux-" + plain, hashed) is False


def test_new_hashes_use_the_same_cost_as_before() -> None:
    """Coût 12 : le baisser affaiblirait silencieusement tous les comptes créés
    après la migration."""
    assert get_password_hash("x").startswith("$2b$12$")


def test_round_trip() -> None:
    pwd = "Motdepasse-Élève-2026"
    assert verify_password(pwd, get_password_hash(pwd)) is True
    assert verify_password("autre", get_password_hash(pwd)) is False


def test_a_password_over_72_bytes_is_truncated_not_rejected() -> None:
    """Comportement hérité de passlib, conservé volontairement.

    bcrypt >= 5 refuse au-delà de 72 octets ; sans troncature explicite, la
    vérification lèverait au lieu de répondre.
    """
    long_pwd = "z" * 100
    hashed = get_password_hash(long_pwd)
    assert verify_password(long_pwd, hashed) is True
    # Conséquence directe de la troncature : les 72 premiers octets suffisent.
    assert verify_password("z" * 72, hashed) is True


def test_a_malformed_hash_is_a_failure_not_an_exception() -> None:
    """Une colonne vide ou corrompue doit répondre « non », pas planter en 500."""
    for bad in ("", "pas-une-empreinte", "$2b$12$trop-court"):
        assert verify_password("peu importe", bad) is False


def test_two_passwords_sharing_their_first_72_bytes_are_equivalent() -> None:
    """Conséquence assumée de la troncature, héritée de l'implémentation
    précédente et documentée ici plutôt que découverte un jour en production.

    C'est une faiblesse réelle : au-delà de 72 octets, la fin du mot de passe
    n'apporte aucune entropie. La corriger (pré-hachage SHA-256 avant bcrypt)
    changerait toutes les empreintes et exigerait une réinitialisation générale
    — donc pas au détour de cette migration.
    """
    base = "m" * 72
    hashed = get_password_hash(base + "-fin-A")
    assert verify_password(base + "-fin-B", hashed) is True
