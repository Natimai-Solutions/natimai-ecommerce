"""Unit tests for the carrier tracking-URL builder (storefront link)."""

from app.api.routes.orders_me import _carrier_tracking_url

_TPL = "https://www.dhl.com/track?id={ref}"


def test_builds_url_from_template_and_ref() -> None:
    assert (
        _carrier_tracking_url(_TPL, "ABC123") == "https://www.dhl.com/track?id=ABC123"
    )


def test_url_encodes_the_reference() -> None:
    # A ref with URL-significant chars must be percent-encoded, not break the URL.
    assert (
        _carrier_tracking_url(_TPL, "A B&C") == "https://www.dhl.com/track?id=A%20B%26C"
    )


def test_none_when_no_template() -> None:
    assert _carrier_tracking_url(None, "ABC123") is None


def test_none_when_no_ref() -> None:
    assert _carrier_tracking_url(_TPL, None) is None
    assert _carrier_tracking_url(_TPL, "") is None


def test_rejects_non_https_template() -> None:
    # Guards against javascript:/http: templates being turned into a clickable link.
    assert _carrier_tracking_url("javascript:alert(1)//{ref}", "x") is None
    assert _carrier_tracking_url("http://insecure.example/{ref}", "x") is None
