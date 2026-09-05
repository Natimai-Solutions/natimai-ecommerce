"""Unit tests for the product identity keys (barcodes, manufacturer part)."""

from app.features.product.services.identity import (
    gtin_variants,
    normalize_gtin,
    normalize_text_key,
)


def test_normalize_gtin_keeps_digits_only() -> None:
    assert normalize_gtin(" 3663-9700 12345 ") == "3663970012345"
    assert normalize_gtin("3.6639700123E+12") is None  # garbage from Excel
    assert normalize_gtin("") is None
    assert normalize_gtin(None) is None
    assert normalize_gtin("12345") is None  # too short to be a barcode


def test_gtin_variants_equate_upc_a_and_ean_13() -> None:
    assert gtin_variants("036000291452") == {
        "036000291452",
        "36000291452",
        "0036000291452",
    }
    assert gtin_variants("0036000291452") == {"0036000291452", "36000291452"}
    assert gtin_variants("abc") == set()


def test_text_key_ignores_case_and_surrounding_spaces() -> None:
    assert normalize_text_key("  HP Inc. ") == "hp inc."
    assert normalize_text_key("   ") is None
    assert normalize_text_key(None) is None


def test_canonical_gtin_and_identity_key() -> None:
    from decimal import Decimal
    from types import SimpleNamespace

    from app.features.product.services.identity import (
        canonical_gtin,
        product_identity_key,
    )

    assert canonical_gtin("0036000291452") == "36000291452"
    assert canonical_gtin("036000291452") == "36000291452"
    assert canonical_gtin(None) is None

    by_ean = SimpleNamespace(
        ean="0036000291452", upc=None, manufacturer="HP", vendor_part_number="X"
    )
    by_upc = SimpleNamespace(
        ean=None, upc="036000291452", manufacturer=None, vendor_part_number=None
    )
    by_mpn = SimpleNamespace(
        ean="", upc=None, manufacturer=" Hp ", vendor_part_number="k120 "
    )
    nothing = SimpleNamespace(
        ean=None, upc=None, manufacturer="HP", vendor_part_number=None
    )

    assert (
        product_identity_key(by_ean)
        == product_identity_key(by_upc)
        == "gtin:36000291452"
    )
    assert product_identity_key(by_mpn) == "mpn:hp|k120"
    assert product_identity_key(nothing) is None
    del Decimal


def test_group_offers_keeps_the_cheapest_and_counts_siblings() -> None:
    from decimal import Decimal
    from types import SimpleNamespace
    from uuid import uuid4

    from app.features.product.crud.product import ProductCrud

    def _p(
        price: str, qty: str = "1", ean: str | None = "3663970012345"
    ) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid4(),
            ean=ean,
            upc=None,
            manufacturer=None,
            vendor_part_number=None,
            base_price=Decimal(price),
            supplier_quantity=Decimal(qty),
        )

    lonely = _p("500", ean=None)
    dear = _p("1000")
    cheap_out = _p("800", qty="0")
    cheap_in = _p("800", qty="3")
    other = _p("300", ean="5099206020276")

    kept, counts = ProductCrud.group_offers([lonely, dear, cheap_out, cheap_in, other])  # type: ignore[list-item]

    assert [p.id for p in kept] == [lonely.id, cheap_in.id, other.id]
    assert counts == {str(cheap_in.id): 3}
