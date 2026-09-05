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


def test_orm_listeners_stamp_identity_key_on_write() -> None:
    from app.features.product.models.product import Product, _stamp_identity_key

    product = Product(name="Clavier", ean="0036000291452")
    assert product.identity_key is None  # nothing until the flush

    _stamp_identity_key(None, None, product)
    assert product.identity_key == "gtin:36000291452"

    # The barcode goes away: the key follows the manufacturer part number…
    product.ean = None
    product.manufacturer = "Logi"
    product.vendor_part_number = "K120"
    _stamp_identity_key(None, None, product)
    assert product.identity_key == "mpn:logi|k120"

    # …and is cleared when nothing identifies the item any more.
    product.vendor_part_number = None
    _stamp_identity_key(None, None, product)
    assert product.identity_key is None
