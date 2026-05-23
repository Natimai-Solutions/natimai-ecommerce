from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.shipping.shipping_route as shipping_route_routes
from app.core.errors import AppError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_quote_shipping_paths_requires_at_least_one_path(client: TestClient) -> None:
    response = client.post(
        "/api/v1/shipping/route/quote",
        json={
            "paths": [],
            "total_weight_kg": "0",
            "declared_value": "0",
            "currency": "EUR",
        },
    )

    assert response.status_code == 400
    payload = response.json()["error"]
    assert payload["code"] == "shipping.route.path_required"
    assert payload["details"] == {"field": "paths"}


def test_quote_shipping_paths_rejects_empty_route_list(client: TestClient) -> None:
    response = client.post(
        "/api/v1/shipping/route/quote",
        json={
            "paths": [{"label": "empty", "route_ids": []}],
            "total_weight_kg": "0",
            "declared_value": "0",
            "currency": "EUR",
        },
    )

    assert response.status_code == 400
    payload = response.json()["error"]
    assert payload["code"] == "shipping.route.path_empty"
    assert payload["details"] == {"path_index": 0}


def test_quote_shipping_paths_returns_unknown_or_inactive_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    route_id = uuid4()

    async def _fake_load_active_routes(
        _session: object,
        _route_ids: list[object],
    ) -> dict[object, object]:
        raise AppError(
            code="shipping.route.unknown_or_inactive",
            status_code=400,
            message="Unknown or inactive shipping routes: " + str(route_id),
            details={"route_ids": [str(route_id)]},
        )

    monkeypatch.setattr(
        "app.api.routes.shipping.shipping_route._load_active_routes",
        _fake_load_active_routes,
    )

    response = client.post(
        "/api/v1/shipping/route/quote",
        json={
            "paths": [{"label": "single", "route_ids": [str(route_id)]}],
            "total_weight_kg": "1",
            "declared_value": "100",
            "currency": "EUR",
        },
    )

    assert response.status_code == 400
    payload = response.json()["error"]
    assert payload["code"] == "shipping.route.unknown_or_inactive"
    assert payload["details"] == {"route_ids": [str(route_id)]}


@pytest.mark.anyio
async def test_load_active_routes_maps_unknown_or_inactive_routes() -> None:
    route_id = uuid4()
    session = AsyncMock()
    session.exec = AsyncMock(return_value=SimpleNamespace(all=lambda: []))

    with pytest.raises(AppError) as exc_info:
        await shipping_route_routes._load_active_routes(
            session=session,
            route_ids=[route_id],
        )

    assert exc_info.value.code == "shipping.route.unknown_or_inactive"
    assert exc_info.value.status_code == 400
    assert exc_info.value.details == {"route_ids": [str(route_id)]}


def test_get_optimal_path_returns_shipping_route_not_found(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from_place_id = uuid4()
    to_place_id = uuid4()

    monkeypatch.setattr(
        shipping_route_routes.shipping_route_router.crud,
        "get_optimal_route_between_places",
        AsyncMock(return_value=None),
    )

    response = client.get(
        f"/api/v1/shipping/route/optimal/{from_place_id}/{to_place_id}"
    )

    assert response.status_code == 404
    payload = response.json()["error"]
    assert payload["code"] == "shipping.route.not_found"
    assert payload["details"] == {
        "from_place_id": str(from_place_id),
        "to_place_id": str(to_place_id),
    }
