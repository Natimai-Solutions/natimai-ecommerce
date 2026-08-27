"""Identité légale stockée en base (L1).

Les valeurs sont de la donnée de déploiement — ce dépôt est un modèle — donc
elles vivent dans ``system_settings``. Deux surfaces les lisent : les pages
légales de la vitrine et l'en-tête des factures. Ce qui doit être verrouillé,
c'est que ces deux surfaces parlent bien des mêmes lignes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.api.routes.system_settings import _PUBLIC_KEYS
from app.core.config import settings
from app.features.system.legal_identity import (
    LEGAL_SETTING_KEYS,
    LEGAL_SETTINGS,
    REQUIRED_FOR_INVOICING,
    missing_for_invoicing,
    seed_value_for,
)

# backend/app/tests/… → racine du dépôt
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_CONFIG = _REPO_ROOT / "frontend" / "src" / "config" / "legalEntity.ts"

#: Clés utiles à la facture seule ; la vitrine ne les affiche pas.
_INVOICE_ONLY_KEYS = {"legal_tax_id", "legal_payment_terms", "legal_late_penalty_terms"}


def test_keys_are_unique_and_namespaced() -> None:
    keys = [spec.key for spec in LEGAL_SETTINGS]
    assert len(keys) == len(set(keys))
    # Le préfixe est ce qui permet à l'endpoint public et au script de release
    # de les reconnaître sans les énumérer.
    assert all(key.startswith("legal_") for key in keys)


def test_every_key_is_readable_without_authentication() -> None:
    """Publier ces informations est une obligation légale : la vitrine les rend
    sans connexion."""
    assert LEGAL_SETTING_KEYS <= _PUBLIC_KEYS


def test_the_storefront_and_the_backend_agree_on_the_keys() -> None:
    """Une coquille côté vitrine ferait disparaître un champ en silence.

    Le mapping TypeScript est lu tel quel : c'est la seule façon de détecter
    une divergence introduite d'un seul côté.
    """
    if not _FRONTEND_CONFIG.is_file():
        # Le backend peut être testé seul (image sans la vitrine montée). En CI
        # le dépôt est complet, donc la divergence y est bien attrapée.
        pytest.skip(f"vitrine absente de cette arborescence ({_FRONTEND_CONFIG})")

    source = _FRONTEND_CONFIG.read_text(encoding="utf-8")
    frontend_keys = set(re.findall(r"key: '(legal_[a-z_]+)'", source))

    assert frontend_keys, "aucune clé trouvée — le format du mapping a changé"
    assert frontend_keys == {
        spec.key for spec in LEGAL_SETTINGS if spec.key not in _INVOICE_ONLY_KEYS
    }


def test_descriptions_guide_whoever_fills_the_form() -> None:
    """Ce sont les libellés de l'écran admin : vides ou recopiés d'une clé à
    l'autre, personne ne sait quoi saisir dans ``legal_mediation_scheme``."""
    descriptions = [spec.description.strip() for spec in LEGAL_SETTINGS]

    assert all(descriptions), "une description vide laisse un champ sans libellé"
    # Pas de seuil de longueur — « Téléphone » est un libellé valable. Ce qui
    # trahit un copier-coller, c'est la répétition.
    assert len(set(descriptions)) == len(descriptions)


def test_seeding_reuses_the_existing_environment_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Un déploiement qui avait renseigné les INVOICE_SELLER_* ne repart pas
    de zéro."""
    monkeypatch.setattr(settings, "INVOICE_SELLER_NAME", "  Natimai Solutions  ")
    by_key = {spec.key: spec for spec in LEGAL_SETTINGS}

    assert seed_value_for(by_key["legal_trading_name"]) == "Natimai Solutions"
    # Un champ sans équivalent dans l'environnement démarre vide.
    assert seed_value_for(by_key["legal_publication_director"]) == ""


def test_invoicing_blockers_are_reported() -> None:
    assert set(REQUIRED_FOR_INVOICING) <= LEGAL_SETTING_KEYS

    assert missing_for_invoicing({}) == list(REQUIRED_FOR_INVOICING)
    complete = dict.fromkeys(REQUIRED_FOR_INVOICING, "valeur")
    assert missing_for_invoicing(complete) == []
    # Une valeur blanche est un manque, pas une saisie.
    assert missing_for_invoicing({**complete, "legal_trading_name": "  "}) == [
        "legal_trading_name"
    ]
