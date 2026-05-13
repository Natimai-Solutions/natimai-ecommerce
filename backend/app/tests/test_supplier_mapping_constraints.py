from sqlmodel import UniqueConstraint

from app.features.integrations.models.supplier_sync import SupplierProductMapping


def test_supplier_product_mapping_unique_constraint_on_supplier_identity() -> None:
    table = getattr(SupplierProductMapping, "__table__", None)
    assert table is not None

    unique_constraints = [
        constraint
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    ]

    assert any(
        set(constraint.columns.keys()) == {"supplier_name", "supplier_sku"}
        for constraint in unique_constraints
    )
