"""Verrous par champ (A14) — la règle et ses deux consommateurs.

La sync fournisseur respectait déjà ``overridden_fields`` ; l'enrichissement
Icecat, lui, réécrivait description et image à chaque passage — l'admin
corrigeait, Icecat effaçait. Les deux flux passent désormais par la même
fonction ``strip_locked``.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from app.features.integrations.models.icecat_sync import IcecatProductData
from app.features.product.models.category import CategoryPublic
from app.features.product.services.overrides import (
    merge_locks,
    release_lock,
    strip_locked,
)
from app.tasks.icecat_tasks import enrichment_payload


def test_strip_locked_leaves_the_locked_keys_out() -> None:
    incoming = {"name": "Nom fournisseur", "description": "Desc", "weight": 1.2}

    assert strip_locked(incoming, ["description"]) == {
        "name": "Nom fournisseur",
        "weight": 1.2,
    }
    # Sans verrou : copie intacte, et bien une copie.
    copy = strip_locked(incoming, None)
    assert copy == incoming and copy is not incoming


def test_merge_locks_accumulates_and_ignores_bookkeeping_flags() -> None:
    """Désactiver un produit ou reposer la liste des verrous n'est pas une
    correction de contenu à protéger de la sync."""
    locks = merge_locks(["name"], ["description", "is_active", "overridden_fields"])

    assert locks == ["description", "name"]
    assert merge_locks(None, []) == []
    assert merge_locks(["b", "a"], ["a"]) == ["a", "b"]  # trié, sans doublon


def test_release_lock_removes_one_field_only() -> None:
    assert release_lock(["name", "image_url"], "image_url") == ["name"]
    assert release_lock(["name"], "absent") == ["name"]
    assert release_lock(None, "name") == []


def _product(**overrides: Any) -> Any:
    product = SimpleNamespace(overridden_fields=None)
    for key, value in overrides.items():
        setattr(product, key, value)
    return product


def _icecat() -> IcecatProductData:
    return IcecatProductData(
        icecat_id="12345",
        brand="ACME",
        product_name="Laptop",
        description="Description Icecat",
        long_description="Longue description Icecat",
        image_url="https://icecat.example/img.jpg",
        weight_kg=2.5,
    )


def test_enrichment_respects_admin_locks() -> None:
    """Le cas qui manquait : une description corrigée par l'admin survivait à
    la sync mais pas à l'enrichissement."""
    payload = enrichment_payload(
        _product(overridden_fields=["description", "image_url"]), _icecat()
    )

    assert "description" not in payload
    assert "image_url" not in payload
    # Le reste passe, marqueurs d'enrichissement compris.
    assert payload["long_description"] == "Longue description Icecat"
    assert payload["weight"] == 2.5
    assert payload["is_enriched"] is True
    assert payload["last_enrichment_sync"] is not None


def test_enrichment_without_locks_applies_everything() -> None:
    payload = enrichment_payload(_product(), _icecat())

    assert payload["description"] == "Description Icecat"
    assert payload["image_url"] == "https://icecat.example/img.jpg"
    assert payload["enrichment_supplier_id"] == "12345"


def test_category_title_falls_back_to_the_sync_name() -> None:
    """Le titre vitrine est résolu à un seul endroit : display_name si l'admin
    en a posé un, sinon le nom fournisseur."""
    raw = CategoryPublic.model_validate(
        {"id": "7b2c1a1e-1111-4bbb-8ccc-000000000001", "name": "NOTEBOOKS"}
    )
    custom = CategoryPublic.model_validate(
        {
            "id": "7b2c1a1e-1111-4bbb-8ccc-000000000002",
            "name": "NOTEBOOKS",
            "display_name": "Ordinateurs portables",
        }
    )

    assert raw.title == "NOTEBOOKS"
    assert custom.title == "Ordinateurs portables"
    assert "title" in custom.model_dump()  # sérialisé vers la vitrine
