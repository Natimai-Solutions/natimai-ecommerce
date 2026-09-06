"""Identité d'un article au-delà de la référence fournisseur.

Un même produit physique peut arriver sous une référence différente (le
fournisseur renumérote, un fichier tape la référence autrement) ; ce qui ne
change pas, c'est le code-barres (EAN-13 / UPC-A) et, à défaut, le couple
marque + référence fabricant. Ces helpers normalisent ces clés pour que le
rapprochement à l'import (voir ``supplier_sync_orchestrator``) et, plus tard,
un regroupement vitrine « autres offres » comparent la même chose.
"""

from __future__ import annotations

import re

_DIGITS_RE = re.compile(r"\D+")
#: « 3,66397E+12 » : Excel a converti le code-barres en nombre et perdu des
#: chiffres ; le comparer ferait rapprocher n'importe quoi.
_SCIENTIFIC_RE = re.compile(r"\d[.,]?\d*[eE][+-]?\d+")
#: En dessous, ce n'est pas un GTIN (EAN-8 est le plus court) mais du bruit.
_MIN_GTIN_LENGTH = 8


def normalize_gtin(value: str | None) -> str | None:
    """Ne garder que les chiffres ; ``None`` si trop court pour être un code-barres."""
    if not value:
        return None
    if _SCIENTIFIC_RE.search(str(value)):
        return None
    digits = _DIGITS_RE.sub("", str(value))
    if len(digits) < _MIN_GTIN_LENGTH:
        return None
    return digits


def gtin_variants(value: str | None) -> set[str]:
    """Toutes les écritures équivalentes d'un code-barres.

    Un UPC-A (12 chiffres) est l'EAN-13 de même valeur précédé d'un zéro ;
    les exports Excel perdent souvent les zéros de tête. On compare donc la
    valeur brute, sans ses zéros de tête, et avec un zéro devant.
    """
    digits = normalize_gtin(value)
    if digits is None:
        return set()
    variants = {digits}
    stripped = digits.lstrip("0")
    if len(stripped) >= _MIN_GTIN_LENGTH:
        variants.add(stripped)
    if len(digits) == 12:
        variants.add("0" + digits)
    return variants


def normalize_text_key(value: str | None) -> str | None:
    """Clé de comparaison insensible à la casse et aux espaces autour."""
    if value is None:
        return None
    key = str(value).strip().casefold()
    return key or None


def canonical_gtin(value: str | None) -> str | None:
    """Forme canonique d'un code-barres : chiffres sans zéros de tête.

    Deux écritures équivalentes (UPC-A, EAN-13 à zéro de tête, zéros perdus
    par Excel) donnent la même clé.
    """
    digits = normalize_gtin(value)
    if digits is None:
        return None
    stripped = digits.lstrip("0")
    return stripped if len(stripped) >= _MIN_GTIN_LENGTH else digits


def product_identity_key(product: object) -> str | None:
    """Clé « même produit physique », tous fournisseurs confondus.

    Le code-barres d'abord (EAN puis UPC), sinon marque + référence
    fabricant ; ``None`` quand l'article n'a rien de tout cela — il ne se
    regroupe alors avec personne.
    """
    for attr in ("ean", "upc"):
        key = canonical_gtin(getattr(product, attr, None))
        if key:
            return f"gtin:{key}"
    maker = normalize_text_key(getattr(product, "manufacturer", None))
    part = normalize_text_key(getattr(product, "vendor_part_number", None))
    if maker and part:
        return f"mpn:{maker}|{part}"
    return None
