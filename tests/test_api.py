"""HTTP level tests using a fake service (no database required)."""

from __future__ import annotations

from fastapi.testclient import TestClient

from ks_adapter.app import create_app

from .conftest import FakeService, make_settings


def test_root_returns_service_info(client: TestClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "ks-adapter"
    assert body["docs"] == "/docs"


def test_service_info_under_prefix(client: TestClient) -> None:
    response = client.get("/api/v1/")
    assert response.status_code == 200
    assert response.json()["api_prefix"] == "/api/v1"


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["database"]["server_version"] == "Firebird 2.5"
    assert body["pool"]["capacity"] == 5


def test_list_tables(client: TestClient) -> None:
    response = client.get("/api/v1/tables")
    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 2
    assert [table["name"] for table in body["tables"]] == ["APPUSER", "V_USERS"]


def test_describe_table(client: TestClient) -> None:
    response = client.get("/api/v1/tables/APPUSER")
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "table"
    assert [column["name"] for column in body["columns"]] == ["ID", "NAME"]


def test_describe_missing_table(client: TestClient) -> None:
    response = client.get("/api/v1/tables/NOPE")
    assert response.status_code == 404
    assert response.json()["error"] == "TableNotFound"


def test_rows_passes_pagination_and_filters(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.get(
        "/api/v1/tables/APPUSER/rows",
        params={
            "limit": 5,
            "offset": 10,
            "order_by": "ID DESC",
            "filters": '{"NAME": "ACME"}',
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 5
    assert body["offset"] == 10
    assert body["rows"] == [{"ID": 11, "NAME": "ACME"}]
    call = fake_service.calls[-1]
    assert call["table"] == "APPUSER"
    assert call["limit"] == 5
    assert call["offset"] == 10
    assert call["order_by"] == "ID DESC"
    assert call["filters"] == '{"NAME": "ACME"}'


def test_rows_rejects_invalid_limit(client: TestClient) -> None:
    response = client.get("/api/v1/tables/APPUSER/rows", params={"limit": 0})
    assert response.status_code == 422


def test_rows_maps_column_errors(client: TestClient) -> None:
    response = client.get(
        "/api/v1/tables/APPUSER/rows", params={"filters": '{"BAD": 1}'}
    )
    assert response.status_code == 400
    assert response.json()["error"] == "ColumnNotFound"


def test_rows_maps_missing_table(client: TestClient) -> None:
    response = client.get("/api/v1/tables/MISSING/rows")
    assert response.status_code == 404
    assert response.json()["detail"] == "Table or view 'MISSING' does not exist"


def test_query_endpoint(client: TestClient, fake_service: FakeService) -> None:
    response = client.post(
        "/api/v1/query",
        json={"sql": "SELECT 1 AS ONE FROM RDB$DATABASE", "limit": 3},
    )
    assert response.status_code == 200
    assert response.json()["rows"] == [{"ONE": 1}]
    call = fake_service.calls[-1]
    assert call["limit"] == 3
    assert call["sql"] == "SELECT 1 AS ONE FROM RDB$DATABASE"


def test_query_requires_sql(client: TestClient) -> None:
    response = client.post("/api/v1/query", json={})
    assert response.status_code == 422


def test_schema_refresh(client: TestClient) -> None:
    response = client.post("/api/v1/schema/refresh")
    assert response.status_code == 200
    assert response.json() == {"refreshed": True, "table_count": 2}


def test_api_key_is_enforced_when_configured() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.get("/api/v1/tables").status_code == 401
        denied = client.get("/api/v1/tables", headers={"X-API-Key": "nope"})
        assert denied.status_code == 401
        assert denied.json()["error"] == "AuthenticationError"
        allowed = client.get("/api/v1/tables", headers={"X-API-Key": "secret"})
        assert allowed.status_code == 200
        # Health checks stay open so orchestrators can probe the process.
        assert client.get("/api/v1/health").status_code == 200


def test_openapi_schema_is_generated(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/tables/{table}/rows" in paths
    assert "/api/v1/clients" in paths
    assert "/api/v1/agreements" in paths
    assert "/api/v1/query" in paths


def test_clients_endpoint(client: TestClient, fake_service: FakeService) -> None:
    response = client.get(
        "/api/v1/clients", params={"limit": 10, "offset": 5, "search": "acme"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 12
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["clients"][0]["name"] == "ACME"
    assert body["clients"][0]["id"] == 6
    assert fake_service.calls[-1] == {
        "action": "fetch_clients",
        "limit": 10,
        "offset": 5,
        "search": "acme",
    }


def test_clients_endpoint_defaults(client: TestClient, fake_service: FakeService) -> None:
    response = client.get("/api/v1/clients")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    call = fake_service.calls[-1]
    assert call["limit"] is None
    assert call["search"] is None


def test_clients_rejects_out_of_range_limit(client: TestClient) -> None:
    assert client.get("/api/v1/clients", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/clients", params={"limit": 5000}).status_code == 422
    assert client.get("/api/v1/clients", params={"offset": -1}).status_code == 422
    assert (
        client.get("/api/v1/clients", params={"search": "x" * 101}).status_code == 422
    )


def test_clients_requires_api_key() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.get("/api/v1/clients").status_code == 401
        allowed = client.get("/api/v1/clients", headers={"X-API-Key": "secret"})
        assert allowed.status_code == 200


def test_agreements_endpoint(client: TestClient, fake_service: FakeService) -> None:
    response = client.get(
        "/api/v1/agreements", params={"limit": 10, "offset": 5, "search": "cpc"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 4
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["agreements"][0]["number"] == "CPC/2024/001"
    assert body["agreements"][0]["id"] == 6
    assert fake_service.calls[-1] == {
        "action": "fetch_agreements",
        "limit": 10,
        "offset": 5,
        "search": "cpc",
    }


def test_agreements_endpoint_defaults(client: TestClient, fake_service: FakeService) -> None:
    response = client.get("/api/v1/agreements")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    call = fake_service.calls[-1]
    assert call["limit"] is None
    assert call["search"] is None


def test_agreements_rejects_out_of_range_limit(client: TestClient) -> None:
    assert client.get("/api/v1/agreements", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/agreements", params={"limit": 5000}).status_code == 422
    assert client.get("/api/v1/agreements", params={"offset": -1}).status_code == 422
    assert (
        client.get("/api/v1/agreements", params={"search": "x" * 101}).status_code
        == 422
    )


def test_agreements_requires_api_key() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.get("/api/v1/agreements").status_code == 401
        allowed = client.get("/api/v1/agreements", headers={"X-API-Key": "secret"})
        assert allowed.status_code == 200


def test_agreements_accepts_decimal_strings(
    client: TestClient, fake_service: FakeService
) -> None:
    """``api.decimal_as_string`` turns DECIMAL columns into strings."""

    def fake_fetch(**_kwargs: object) -> dict[str, object]:
        return {
            "total": 1,
            "count": 1,
            "limit": 50,
            "offset": 0,
            "agreements": [{"id": 1, "costs": "1500.5000", "revenue": 10.5}],
        }

    fake_service.fetch_agreements = fake_fetch  # type: ignore[method-assign]

    response = client.get("/api/v1/agreements")

    assert response.status_code == 200
    agreement = response.json()["agreements"][0]
    assert agreement["costs"] == "1500.5000"
    assert agreement["revenue"] == 10.5
    assert agreement["number"] is None
