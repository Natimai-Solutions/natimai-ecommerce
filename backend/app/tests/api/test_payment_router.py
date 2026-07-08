from fastapi.testclient import TestClient


def test_payment_router_is_exposed_in_openapi(client: TestClient) -> None:
    response = client.get("/api/v1/openapi.json")

    assert response.status_code == 200
    paths = response.json().get("paths", {})

    assert "/api/v1/payment/" in paths
    assert "/api/v1/payment/{id}" in paths
