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
