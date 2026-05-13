from fastapi.testclient import TestClient


def test_payments_webhooks_route_is_exposed_in_openapi(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json().get("paths", {})

    assert "/api/v1/payments/webhooks/{provider_code}" in paths
    assert "post" in paths["/api/v1/payments/webhooks/{provider_code}"]
