"""ShippingRoute payload validation of the weight grid."""

import pytest

from app.features.shipping.models.route import (
    ShippingRouteUpdate,
    normalize_weight_bands,
)


def test_normalize_sorts_and_keeps_open_band_last() -> None:
    bands = normalize_weight_bands(
        [
            {"max_kg": None, "price": 20},
            {"max_kg": 3, "price": "8"},
            {"max_kg": "1", "price": 5},
        ]
    )
    assert bands == [
        {"max_kg": "1", "price": "5"},
        {"max_kg": "3", "price": "8"},
        {"max_kg": None, "price": "20"},
    ]


def test_normalize_empty_is_none() -> None:
    assert normalize_weight_bands([]) is None
    assert normalize_weight_bands(None) is None


@pytest.mark.parametrize(
    "bands",
    [
        [{"max_kg": 0, "price": 5}],
        [{"max_kg": 1, "price": -1}],
        [{"max_kg": 1, "price": 5}, {"max_kg": 1, "price": 6}],
        [{"max_kg": None, "price": 5}, {"max_kg": None, "price": 6}],
        [{"max_kg": "x", "price": 5}],
        "not-a-list",
    ],
)
def test_normalize_rejects_invalid_grids(bands: object) -> None:
    with pytest.raises(ValueError):
        normalize_weight_bands(bands)


def test_update_payload_runs_the_validator() -> None:
    payload = ShippingRouteUpdate.model_validate(
        {"weight_bands": [{"max_kg": 2, "price": 7}, {"max_kg": 1, "price": 4}]}
    )
    assert payload.weight_bands == [
        {"max_kg": "1", "price": "4"},
        {"max_kg": "2", "price": "7"},
    ]
    with pytest.raises(ValueError):
        ShippingRouteUpdate.model_validate(
            {"weight_bands": [{"max_kg": -1, "price": 1}]}
        )
