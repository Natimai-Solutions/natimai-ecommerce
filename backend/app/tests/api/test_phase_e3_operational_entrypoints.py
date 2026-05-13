from app.main import app


def test_e3_operational_entrypoints_exposed_in_openapi() -> None:
    schema = app.openapi()
    paths = schema.get("paths", {})

    expected_paths: dict[str, set[str]] = {
        "/api/v1/suppliers": {"get"},
        "/api/v1/suppliers/{supplier_name}/sync/products": {"post"},
        "/api/v1/suppliers/{supplier_name}/sync/inventory": {"post"},
        "/api/v1/suppliers/{supplier_name}/health": {"get"},
        "/api/v1/icecat/enrich": {"post"},
        "/api/v1/icecat/enrich/batch": {"post"},
        "/api/v1/icecat/status": {"get"},
        "/api/v1/payzen/ipn": {"post"},
        "/api/v1/utils/observability/dashboard": {"get"},
    }

    for path, methods in expected_paths.items():
        assert path in paths, f"Missing API path: {path}"
        for method in methods:
            assert method in paths[path], (
                f"Missing method '{method.upper()}' for path: {path}"
            )
