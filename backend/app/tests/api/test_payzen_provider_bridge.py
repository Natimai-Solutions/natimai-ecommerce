from fastapi.testclient import TestClient


def test_legacy_payzen_routes_are_not_exposed_in_openapi(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json().get("paths", {})

    assert "/api/v1/payzen/form-token" not in paths
    assert "/api/v1/payzen/ipn" not in paths
