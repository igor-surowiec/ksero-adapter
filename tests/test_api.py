"""HTTP level tests using a fake service (no database required)."""

from __future__ import annotations

from typing import Any, Mapping

import pytest
from fastapi.testclient import TestClient

from ks_adapter.app import create_app
from ks_adapter.errors import (
    InvalidRequest,
    RecordConflict,
    RecordNotFound,
    WritesDisabled,
)

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
    assert "post" in paths["/api/v1/clients"]
    assert "/api/v1/agreements" in paths
    assert "/api/v1/machines" in paths
    assert "post" in paths["/api/v1/machines"]
    assert "/api/v1/orders" in paths
    assert "/api/v1/invoices" in paths
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
    assert body["clients"][0]["nazwa"] == "ACME"
    assert body["clients"][0]["id_klient_table"] == 6
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
    assert body["agreements"][0]["umowa"] == "CPC/2024/001"
    assert body["agreements"][0]["id_umowacpc_table"] == 6
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
            "agreements": [
                {"id_umowacpc_table": 1, "koszty": "1500.5000", "przychody": 10.5}
            ],
        }

    fake_service.fetch_agreements = fake_fetch  # type: ignore[method-assign]

    response = client.get("/api/v1/agreements")

    assert response.status_code == 200
    agreement = response.json()["agreements"][0]
    assert agreement["koszty"] == "1500.5000"
    assert agreement["przychody"] == 10.5
    assert agreement["umowa"] is None


def test_machines_endpoint(client: TestClient, fake_service: FakeService) -> None:
    response = client.get(
        "/api/v1/machines", params={"limit": 10, "offset": 5, "search": "konica"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 6
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["machines"][0]["marka"] == "KONICA"
    assert body["machines"][0]["id_maszyna_table"] == 6
    assert fake_service.calls[-1] == {
        "action": "fetch_machines",
        "limit": 10,
        "offset": 5,
        "search": "konica",
    }


def test_machines_endpoint_defaults(client: TestClient, fake_service: FakeService) -> None:
    response = client.get("/api/v1/machines")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    call = fake_service.calls[-1]
    assert call["limit"] is None
    assert call["search"] is None


def test_machines_rejects_out_of_range_limit(client: TestClient) -> None:
    assert client.get("/api/v1/machines", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/machines", params={"limit": 5000}).status_code == 422
    assert client.get("/api/v1/machines", params={"offset": -1}).status_code == 422
    assert (
        client.get("/api/v1/machines", params={"search": "x" * 101}).status_code == 422
    )


def test_machines_requires_api_key() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.get("/api/v1/machines").status_code == 401
        allowed = client.get("/api/v1/machines", headers={"X-API-Key": "secret"})
        assert allowed.status_code == 200


def test_machines_accepts_decimal_strings(
    client: TestClient, fake_service: FakeService
) -> None:
    """``api.decimal_as_string`` turns DECIMAL columns into strings."""

    def fake_fetch(**_kwargs: object) -> dict[str, object]:
        return {
            "total": 1,
            "count": 1,
            "limit": 50,
            "offset": 0,
            "machines": [{"id_maszyna_table": 1, "oplata": "0.1200", "koszty": 30.5}],
        }

    fake_service.fetch_machines = fake_fetch  # type: ignore[method-assign]

    response = client.get("/api/v1/machines")

    assert response.status_code == 200
    machine = response.json()["machines"][0]
    assert machine["oplata"] == "0.1200"
    assert machine["koszty"] == 30.5
    assert machine["marka"] is None


def test_orders_endpoint(client: TestClient, fake_service: FakeService) -> None:
    response = client.get(
        "/api/v1/orders", params={"limit": 10, "offset": 5, "search": "acme"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 9
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["orders"][0]["nazwa"] == "ACME"
    assert body["orders"][0]["id_zlecenie_table"] == 6
    assert fake_service.calls[-1] == {
        "action": "fetch_orders",
        "limit": 10,
        "offset": 5,
        "search": "acme",
    }


def test_orders_endpoint_defaults(client: TestClient, fake_service: FakeService) -> None:
    response = client.get("/api/v1/orders")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    call = fake_service.calls[-1]
    assert call["limit"] is None
    assert call["search"] is None


def test_orders_rejects_out_of_range_limit(client: TestClient) -> None:
    assert client.get("/api/v1/orders", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/orders", params={"limit": 5000}).status_code == 422
    assert client.get("/api/v1/orders", params={"offset": -1}).status_code == 422
    assert (
        client.get("/api/v1/orders", params={"search": "x" * 101}).status_code == 422
    )


def test_orders_requires_api_key() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.get("/api/v1/orders").status_code == 401
        allowed = client.get("/api/v1/orders", headers={"X-API-Key": "secret"})
        assert allowed.status_code == 200


def test_orders_accepts_decimal_strings(
    client: TestClient, fake_service: FakeService
) -> None:
    """``api.decimal_as_string`` turns DECIMAL columns into strings."""

    def fake_fetch(**_kwargs: object) -> dict[str, object]:
        return {
            "total": 1,
            "count": 1,
            "limit": 50,
            "offset": 0,
            "orders": [{"id_zlecenie_table": 1, "brutto": "120.5000", "robocizna": 10.5}],
        }

    fake_service.fetch_orders = fake_fetch  # type: ignore[method-assign]

    response = client.get("/api/v1/orders")

    assert response.status_code == 200
    order = response.json()["orders"][0]
    assert order["brutto"] == "120.5000"
    assert order["robocizna"] == 10.5
    assert order["nazwa"] is None


def test_invoices_endpoint(client: TestClient, fake_service: FakeService) -> None:
    response = client.get(
        "/api/v1/invoices", params={"limit": 10, "offset": 5, "search": "acme"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert body["count"] == 1
    assert body["limit"] == 10
    assert body["offset"] == 5
    assert body["invoices"][0]["numer"] == "FV/2026/11/001"
    assert body["invoices"][0]["id_faktura_table"] == 6
    assert fake_service.calls[-1] == {
        "action": "fetch_invoices",
        "limit": 10,
        "offset": 5,
        "search": "acme",
    }


def test_invoices_endpoint_defaults(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.get("/api/v1/invoices")
    assert response.status_code == 200
    body = response.json()
    assert body["limit"] == 50
    assert body["offset"] == 0
    call = fake_service.calls[-1]
    assert call["limit"] is None
    assert call["search"] is None


def test_invoices_rejects_out_of_range_limit(client: TestClient) -> None:
    assert client.get("/api/v1/invoices", params={"limit": 0}).status_code == 422
    assert client.get("/api/v1/invoices", params={"limit": 5000}).status_code == 422
    assert client.get("/api/v1/invoices", params={"offset": -1}).status_code == 422
    assert (
        client.get("/api/v1/invoices", params={"search": "x" * 101}).status_code == 422
    )


def test_invoices_requires_api_key() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.get("/api/v1/invoices").status_code == 401
        allowed = client.get("/api/v1/invoices", headers={"X-API-Key": "secret"})
        assert allowed.status_code == 200


def test_invoices_accepts_decimal_strings(
    client: TestClient, fake_service: FakeService
) -> None:
    """``api.decimal_as_string`` turns DECIMAL columns into strings."""

    def fake_fetch(**_kwargs: object) -> dict[str, object]:
        return {
            "total": 1,
            "count": 1,
            "limit": 50,
            "offset": 0,
            "invoices": [
                {"id_faktura_table": 1, "suma_brutto": "1230.0000", "do_zaplaty": 0.0}
            ],
        }

    fake_service.fetch_invoices = fake_fetch  # type: ignore[method-assign]

    response = client.get("/api/v1/invoices")

    assert response.status_code == 200
    invoice = response.json()["invoices"][0]
    assert invoice["suma_brutto"] == "1230.0000"
    assert invoice["do_zaplaty"] == 0.0
    assert invoice["numer"] is None



def test_create_client_returns_the_stored_row(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.post("/api/v1/clients", json={"nazwa": "ACME Sp. z o.o."})

    assert response.status_code == 201
    body = response.json()
    assert body["nazwa"] == "ACME Sp. z o.o."
    assert body["id_klient_table"] == 1001
    assert body["id_klient"] == 42
    assert body["nip"] is None
    assert fake_service.calls[-1] == {
        "action": "create_client",
        "values": {"nazwa": "ACME Sp. z o.o."},
    }


def test_create_client_forwards_every_optional_field(
    client: TestClient, fake_service: FakeService
) -> None:
    payload = {
        "nazwa": "ACME Sp. z o.o.",
        "nip": "1234567890",
        "adres": "ul. Testowa 1",
        "kod": "00-001",
        "poczta": "Warszawa",
        "wojewodztwo": 7,
        "termin": 14,
    }

    response = client.post("/api/v1/clients", json=payload)

    assert response.status_code == 201
    assert fake_service.calls[-1] == {"action": "create_client", "values": payload}
    assert response.json()["nip"] == "1234567890"


def test_create_client_requires_a_name(client: TestClient) -> None:
    assert client.post("/api/v1/clients", json={}).status_code == 422
    assert client.post("/api/v1/clients", json={"nazwa": ""}).status_code == 422
    assert client.post("/api/v1/clients", json={"nazwa": "x" * 501}).status_code == 422
    assert client.post("/api/v1/clients", json={"name": "ACME"}).status_code == 422
    assert client.post("/api/v1/clients", json={"nip": "1234567890"}).status_code == 422
    assert client.post("/api/v1/clients").status_code == 422


def test_create_client_rejects_unknown_and_overlong_fields(client: TestClient) -> None:
    assert (
        client.post(
            "/api/v1/clients", json={"nazwa": "ACME", "id_klient": 1}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/clients", json={"nazwa": "ACME", "nip": "1" * 21}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/clients", json={"nazwa": "ACME", "kod": "00-0001"}
        ).status_code
        == 422
    )


def test_create_client_requires_api_key() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.post("/api/v1/clients", json={"nazwa": "ACME"}).status_code == 401
        allowed = client.post(
            "/api/v1/clients",
            json={"nazwa": "ACME"},
            headers={"X-API-Key": "secret"},
        )
        assert allowed.status_code == 201


def test_create_client_reports_disabled_writes_as_403() -> None:
    """``api.allow_writes: false`` must answer 403, not 500."""

    class ReadOnlyService(FakeService):
        def create_client(self, values: Mapping[str, Any]) -> dict[str, object]:
            raise WritesDisabled("Writes are disabled")

    app = create_app(make_settings(), service=ReadOnlyService())
    with TestClient(app) as client:
        response = client.post("/api/v1/clients", json={"nazwa": "ACME"})

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Writes are disabled",
        "error": "WritesDisabled",
    }


def test_create_machine_returns_the_stored_row(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.post(
        "/api/v1/machines",
        json={"id_klient": 7, "marka": "KONICA", "serial": "SN-0001"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["id_maszyna_table"] == 2001
    assert body["id_maszyna"] == 84
    assert body["id_klient"] == 7
    assert body["marka"] == "KONICA"
    assert fake_service.calls[-1] == {
        "action": "create_machine",
        "values": {"id_klient": 7, "marka": "KONICA", "serial": "SN-0001"},
    }


def test_create_machine_sends_only_the_supplied_fields(
    client: TestClient, fake_service: FakeService
) -> None:
    """``null`` fields are dropped, so the insert keeps the column defaults."""

    response = client.post(
        "/api/v1/machines",
        json={"id_klient": 7, "marka": "KONICA", "serial": None, "uwagi": None},
    )

    assert response.status_code == 201
    assert fake_service.calls[-1] == {
        "action": "create_machine",
        "values": {"id_klient": 7, "marka": "KONICA"},
    }


@pytest.mark.parametrize("payload", [{}, {"marka": "KONICA"}, {"id_klient": None},
                                     {"id_klient": 0}])
def test_create_machine_owner_is_optional(
    client: TestClient, fake_service: FakeService, payload: dict[str, Any],
) -> None:
    response = client.post("/api/v1/machines", json=payload)
    assert response.status_code == 201
    assert response.json()["id_klient"] == 0
    assert fake_service.calls[-1]["values"] == {
        key: value for key, value in payload.items() if value is not None
    }


def test_create_machine_rejects_invalid_owner(client: TestClient) -> None:
    assert client.post("/api/v1/machines", json={"id_klient": -1}).status_code == 422
    assert client.post("/api/v1/machines", json={"id_klient": "x"}).status_code == 422
    assert client.post("/api/v1/machines").status_code == 422


def test_create_machine_rejects_unknown_fields(client: TestClient) -> None:
    """A typo must not be dropped silently, the machine table is wide."""

    response = client.post(
        "/api/v1/machines", json={"id_klient": 7, "markaa": "KONICA"}
    )

    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", "markaa"]


def test_create_machine_rejects_over_long_text_and_bad_dates(
    client: TestClient,
) -> None:
    assert (
        client.post(
            "/api/v1/machines", json={"id_klient": 7, "marka": "x" * 101}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/machines", json={"id_klient": 7, "aktywna": "TAK!"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/v1/machines", json={"id_klient": 7, "instalacja": "not-a-date"}
        ).status_code
        == 422
    )


def test_create_machine_requires_api_key() -> None:
    settings = make_settings(api_key="secret")
    app = create_app(settings, service=FakeService())
    with TestClient(app) as client:
        assert client.post("/api/v1/machines", json={"id_klient": 7}).status_code == 401
        allowed = client.post(
            "/api/v1/machines",
            json={"id_klient": 7},
            headers={"X-API-Key": "secret"},
        )
        assert allowed.status_code == 201


def test_create_machine_reports_disabled_writes_as_403() -> None:
    class ReadOnlyService(FakeService):
        def create_machine(self, values: Any) -> dict[str, object]:
            raise WritesDisabled("Writes are disabled")

    app = create_app(make_settings(), service=ReadOnlyService())
    with TestClient(app) as client:
        response = client.post("/api/v1/machines", json={"id_klient": 7})

    assert response.status_code == 403
    assert response.json() == {
        "detail": "Writes are disabled",
        "error": "WritesDisabled",
    }



def test_update_client_forwards_only_supplied_fields(
    client: TestClient, fake_service: FakeService
) -> None:
    response = client.patch("/api/v1/clients/42", json={"nip": None})
    assert response.status_code == 200
    assert response.json()["id_klient"] == 42
    assert fake_service.calls[-1] == {
        "action": "update_client", "id_klient": 42,
        "values": {"nip": None},
    }


@pytest.mark.parametrize("payload", [
    {"id_klient": 1}, {"ostatnio": "2026-01-02"}, {"nip": "x" * 21},
])
def test_update_client_rejects_invalid_payload(
    client: TestClient, payload: dict[str, object]
) -> None:
    assert client.patch("/api/v1/clients/1", json=payload).status_code == 422


def test_update_client_authentication() -> None:
    app = create_app(make_settings(api_key="secret"), service=FakeService())
    with TestClient(app) as client:
        url = "/api/v1/clients/1"
        assert client.patch(url, json={"nip": "123"}).status_code == 401
        assert client.patch(
            url, json={"nip": "123"}, headers={"X-API-Key": "secret"}
        ).status_code == 200
        assert client.patch(
            "/api/v1/clients/0", json={"nip": "123"},
            headers={"X-API-Key": "secret"},
        ).status_code == 422


@pytest.mark.parametrize("error, status", [
    (WritesDisabled("Writes are disabled"), 403),
    (RecordNotFound("Client not found"), 404),
    (InvalidRequest("Supply at least one field"), 400),
])
def test_update_client_reports_domain_errors(error: Exception, status: int) -> None:
    class FailingService(FakeService):
        def update_client(
            self, id_klient: int, values: Mapping[str, Any]
        ) -> dict[str, Any]:
            raise error

    app = create_app(make_settings(), service=FailingService())
    with TestClient(app) as client:
        response = client.patch("/api/v1/clients/1", json={"nip": "123"})
    assert response.status_code == status
    assert response.json()["error"] == type(error).__name__


def test_cors_allows_client_patch() -> None:
    origin = "https://example.com"
    app = create_app(make_settings(cors_origins=(origin,)), service=FakeService())
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/clients/42",
            headers={
                "Origin": origin,
                "Access-Control-Request-Method": "PATCH",
                "Access-Control-Request-Headers": "Content-Type, X-API-Key",
            },
        )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "PATCH" in response.headers["access-control-allow-methods"]


def test_delete_client_returns_no_content(
    client: TestClient, fake_service: FakeService,
) -> None:
    response = client.delete("/api/v1/clients/42")
    assert response.status_code == 204
    assert response.content == b""
    assert fake_service.calls[-1] == {"action": "delete_client", "id_klient": 42}


@pytest.mark.parametrize("key", ["0", "-1", "invalid", "42 OR 1=1"])
def test_delete_client_rejects_invalid_path(client: TestClient, key: str) -> None:
    assert client.delete(f"/api/v1/clients/{key}").status_code == 422


def test_delete_client_requires_api_key() -> None:
    app = create_app(make_settings(api_key="secret"), service=FakeService())
    with TestClient(app) as client:
        url = "/api/v1/clients/42"
        assert client.delete(url).status_code == 401
        assert client.delete(
            url, headers={"X-API-Key": "wrong"}
        ).status_code == 401
        assert client.delete(
            url, headers={"X-API-Key": "secret"}
        ).status_code == 204


@pytest.mark.parametrize("error, status", [
    (WritesDisabled("Writes are disabled"), 403),
    (RecordNotFound("Client not found"), 404),
])
def test_delete_client_reports_domain_errors(error: Exception, status: int) -> None:
    class FailingService(FakeService):
        def delete_client(self, id_klient: int) -> None:
            raise error

    app = create_app(make_settings(), service=FailingService())
    with TestClient(app) as client:
        response = client.delete("/api/v1/clients/42")
    assert response.status_code == status
    assert response.json()["error"] == type(error).__name__


def test_cors_allows_client_delete() -> None:
    origin = "https://example.com"
    app = create_app(make_settings(cors_origins=(origin,)), service=FakeService())
    with TestClient(app) as client:
        response = client.options(
            "/api/v1/clients/42", headers={
                "Origin": origin, "Access-Control-Request-Method": "DELETE",
            },
        )
    assert response.status_code == 200
    assert "DELETE" in response.headers["access-control-allow-methods"]


def test_create_agreement_returns_stored_projection(
    client: TestClient, fake_service: FakeService,
) -> None:
    payload = {
        "umowa": "CPC/2026/001",
        "u_start": "2026-11-08", "rabat": "2.5000", "uwagi": None,
    }
    response = client.post("/api/v1/agreements/7", json=payload)
    assert response.status_code == 201
    assert response.json()["id_umowacpc_table"] == 3001
    assert response.json()["id_umowacpc"] == 1
    import datetime as dt
    from decimal import Decimal

    assert fake_service.calls[-1] == {
        "action": "create_agreement", "values": {
            "id_klient": 7, "umowa": "CPC/2026/001",
            "u_start": dt.date(2026, 11, 8), "rabat": Decimal("2.5000"),
        },
    }


@pytest.mark.parametrize("payload", [
    {"id_klient": None}, {"id_klient": 7}, {"id_umowacpc": 51},
    {"id_umowacpc_table": 1}, {"koszty": 1},
    {"umowa": "x" * 101}, {"u_start": "invalid"},
])
def test_create_agreement_rejects_invalid_fields(
    client: TestClient, payload: dict[str, Any],
) -> None:
    assert client.post("/api/v1/agreements/7", json=payload).status_code == 422


def test_create_agreement_requires_api_key() -> None:
    app = create_app(make_settings(api_key="secret"), service=FakeService())
    payload = {}
    with TestClient(app) as client:
        assert client.post("/api/v1/agreements/7", json=payload).status_code == 401
        assert client.post(
            "/api/v1/agreements/7", json=payload,
            headers={"X-API-Key": "secret"},
        ).status_code == 201


def test_create_agreement_reports_disabled_writes() -> None:
    class ReadOnlyService(FakeService):
        def create_agreement(self, values: Mapping[str, Any]) -> dict[str, Any]:
            raise WritesDisabled("Writes are disabled")

    app = create_app(make_settings(), service=ReadOnlyService())
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/agreements/7", json={}
        )
    assert response.status_code == 403
    assert response.json()["error"] == "WritesDisabled"


@pytest.mark.parametrize("with_body", [False, True])
def test_create_agreement_needs_only_client_path(
    client: TestClient, fake_service: FakeService, with_body: bool,
) -> None:
    response = client.post(
        "/api/v1/agreements/42", **({"json": {}} if with_body else {})
    )
    assert response.status_code == 201
    assert fake_service.calls[-1] == {
        "action": "create_agreement", "values": {"id_klient": 42},
    }


@pytest.mark.parametrize("key", ["0", "-1", "invalid"])
def test_create_agreement_validates_client_path(client: TestClient, key: str) -> None:
    assert client.post(f"/api/v1/agreements/{key}").status_code == 422


def test_create_agreement_old_post_route_is_removed(client: TestClient) -> None:
    assert client.post("/api/v1/agreements", json={"id_klient": 42}).status_code == 405


def test_update_machine_returns_stored_projection(
    client: TestClient, fake_service: FakeService,
) -> None:
    response = client.patch("/api/v1/machines/4", json={"serial": None})
    assert response.status_code == 200
    assert response.json()["id_maszyna"] == 4
    assert fake_service.calls[-1] == {
        "action": "update_machine", "id_maszyna": 4, "values": {"serial": None},
    }


@pytest.mark.parametrize("payload", [
    {"id_maszyna": 1}, {"synwp": 1}, {"licznik_total": 1},
    {"serial": "x" * 101}, {"instalacja": "invalid"}, {"id_klient": -1},
])
def test_update_machine_rejects_invalid_payload(
    client: TestClient, payload: dict[str, Any],
) -> None:
    assert client.patch("/api/v1/machines/4", json=payload).status_code == 422


def test_update_machine_authentication() -> None:
    app = create_app(make_settings(api_key="secret"), service=FakeService())
    with TestClient(app) as client:
        url = "/api/v1/machines/4"
        assert client.patch(url, json={"marka": "KONICA"}).status_code == 401
        assert client.patch(
            url, json={"marka": "KONICA"}, headers={"X-API-Key": "secret"},
        ).status_code == 200
        assert client.patch(
            "/api/v1/machines/0", json={"marka": "KONICA"},
            headers={"X-API-Key": "secret"},
        ).status_code == 422


@pytest.mark.parametrize("error, status", [
    (WritesDisabled("Writes disabled"), 403),
    (InvalidRequest("Empty update"), 400),
    (RecordNotFound("Machine not found"), 404),
    (RecordConflict("Multiple machines"), 409),
])
def test_update_machine_reports_domain_errors(error: Exception, status: int) -> None:
    class FailingService(FakeService):
        def update_machine(
            self, id_maszyna: int, values: Mapping[str, Any],
        ) -> dict[str, Any]:
            raise error

    app = create_app(make_settings(), service=FailingService())
    with TestClient(app) as client:
        response = client.patch("/api/v1/machines/4", json={"marka": "KONICA"})
    assert response.status_code == status
    assert response.json()["error"] == type(error).__name__


def test_create_agreement_forwards_optional_machines(
    client: TestClient, fake_service: FakeService,
) -> None:
    response = client.post("/api/v1/agreements/7", json={"machines": [4, 9]})
    assert response.status_code == 201
    assert fake_service.calls[-1] == {
        "action": "create_agreement", "values": {"id_klient": 7, "machines": [4, 9]},
    }


def test_update_agreement_forwards_only_supplied_fields(
    client: TestClient, fake_service: FakeService,
) -> None:
    response = client.patch("/api/v1/agreements/51", json={
        "machines": [4, 9], "uwagi": None,
    })
    assert response.status_code == 200
    assert response.json()["id_umowacpc"] == 51
    assert fake_service.calls[-1] == {
        "action": "update_agreement", "id_umowacpc": 51,
        "values": {"machines": [4, 9], "uwagi": None},
    }


@pytest.mark.parametrize("machines", [None, "4", [0], [-1], [True], ["4"],
                                      [2147483648], [1] * 1001])
def test_agreement_routes_validate_machine_arrays(
    client: TestClient, machines: Any,
) -> None:
    for method in (client.post, client.patch):
        assert method(
            "/api/v1/agreements/7", json={"machines": machines}
        ).status_code == 422


def test_update_agreement_requires_api_key_and_valid_path() -> None:
    app = create_app(make_settings(api_key="secret"), service=FakeService())
    with TestClient(app) as client:
        assert client.patch(
            "/api/v1/agreements/51", json={"machines": [4]}
        ).status_code == 401
        assert client.patch(
            "/api/v1/agreements/51", json={"machines": [4]},
            headers={"X-API-Key": "secret"},
        ).status_code == 200
        assert client.patch(
            "/api/v1/agreements/0", json={"machines": [4]},
            headers={"X-API-Key": "secret"},
        ).status_code == 422


@pytest.mark.parametrize("error, status", [
    (InvalidRequest("Empty update"), 400), (WritesDisabled("Disabled"), 403),
    (RecordNotFound("Missing record"), 404), (RecordConflict("Ambiguous ID"), 409),
])
def test_update_agreement_reports_domain_errors(error: Exception, status: int) -> None:
    class FailingService(FakeService):
        def update_agreement(
            self, id_umowacpc: int, values: Mapping[str, Any],
        ) -> dict[str, Any]:
            raise error

    with TestClient(create_app(make_settings(), service=FailingService())) as client:
        response = client.patch("/api/v1/agreements/51", json={"machines": [4]})
    assert response.status_code == status
    assert response.json()["error"] == type(error).__name__


CPC_REQUEST = {"id_klient": 7, "id_maszyna": 9, "id_umowacpc": 3,
               "rok": 2026, "miesiac": 11}


def test_cpc_routes_return_records_and_forward_inputs(
    client: TestClient, fake_service: FakeService,
) -> None:
    response = client.get("/api/v1/cpc-settlement", params={
        "limit": 5, "offset": 2, "search": "TEST", "filters": '{"rok":2026}',
    })
    assert response.status_code == 200
    assert response.json()["cpc"][0]["id_cpc_table"] == 101
    assert fake_service.calls[-1] == {"action": "fetch_cpc", "limit": 5,
        "offset": 2, "search": "TEST", "filters": '{"rok":2026}'}
    assert client.get("/api/v1/cpc-settlement/101").json()["id_cpc_table"] == 101
    response = client.post(
        "/api/v1/cpc-settlement", json={**CPC_REQUEST, "oplata_suma": "12.34"}
    )
    assert response.status_code == 201
    assert float(response.json()["oplata_suma"]) == 12.34
    response = client.patch("/api/v1/cpc-settlement/101", json={"uwagi": None})
    assert response.status_code == 200
    assert fake_service.calls[-1]["values"] == {"uwagi": None}
    response = client.delete("/api/v1/cpc-settlement/101")
    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.parametrize("change", [
    {"id_klient": 0}, {"id_maszyna": None}, {"miesiac": 13}, {"rok": 10000},
    {"id_cpc_table": 101}, {"uwagi": "x" * 501},
    {"oplata_suma": "1.12345"}, {"oplata_suma": "1000000"},
])
def test_create_cpc_validates_input(client: TestClient, change: dict[str, Any]) -> None:
    assert client.post(
        "/api/v1/cpc-settlement", json={**CPC_REQUEST, **change}
    ).status_code == 422


def test_create_cpc_requires_parents(client: TestClient) -> None:
    for missing in ("id_klient", "id_maszyna", "id_umowacpc"):
        assert client.post("/api/v1/cpc-settlement", json={
            key: value for key, value in CPC_REQUEST.items() if key != missing
        }).status_code == 422


@pytest.mark.parametrize("payload", [
    {"id_klient": 8}, {"id_maszyna": 10}, {"id_umowacpc": 4},
    {"id_cpc_table": 2}, {"miesiac": 0}, {"faktura": "x" * 51},
])
def test_update_cpc_rejects_invalid_fields(
    client: TestClient, payload: dict[str, Any],
) -> None:
    assert client.patch("/api/v1/cpc-settlement/101", json=payload).status_code == 422


def test_all_cpc_routes_require_api_key() -> None:
    app = create_app(make_settings(api_key="secret"), service=FakeService())
    with TestClient(app) as client:
        for method, path, body in [
            ("GET", "/cpc-settlement", None), ("GET", "/cpc-settlement/101", None),
            ("POST", "/cpc-settlement", CPC_REQUEST),
            ("PATCH", "/cpc-settlement/101", {"uwagi": "X"}),
            ("DELETE", "/cpc-settlement/101", None),
        ]:
            assert client.request(
                method, "/api/v1" + path, json=body
            ).status_code == 401
            assert client.request(method, "/api/v1" + path, json=body,
                headers={"X-API-Key": "secret"}).status_code in (200, 201, 204)


@pytest.mark.parametrize("error, status", [(WritesDisabled("Disabled"), 403),
                                         (RecordNotFound("Missing"), 404)])
def test_cpc_write_errors_are_rendered(error: Exception, status: int) -> None:
    class FailingService(FakeService):
        def update_cpc(
            self, id_cpc_table: int, values: Mapping[str, Any],
        ) -> dict[str, Any]:
            raise error

    with TestClient(create_app(make_settings(), service=FailingService())) as client:
        response = client.patch("/api/v1/cpc-settlement/101", json={"uwagi": "TEST"})
    assert response.status_code == status
    assert response.json()["error"] == type(error).__name__


@pytest.mark.parametrize("period", [{}, {"rok": 2027}, {"miesiac": 2},
                                    {"rok": None, "miesiac": None}])
def test_create_cpc_accepts_optional_period(
    client: TestClient, fake_service: FakeService, period: dict[str, Any],
) -> None:
    parents = {"id_klient": 7, "id_maszyna": 9, "id_umowacpc": 3}
    response = client.post("/api/v1/cpc-settlement", json={**parents, **period})
    assert response.status_code == 201
    assert fake_service.calls[-1]["values"] == {
        **parents, **{key: value for key, value in period.items() if value is not None},
    }


@pytest.mark.parametrize("payload", [None, {}, {"marka": "KONICA"},
                                     {"id_klient": 7}, {"id_klient": None}])
def test_create_machine_with_client_in_path(
    client: TestClient, fake_service: FakeService, payload: Any,
) -> None:
    response = client.post(
        "/api/v1/machines/7", **({"json": payload} if payload is not None else {})
    )
    assert response.status_code == 201
    assert response.json()["id_klient"] == 7
    assert fake_service.calls[-1] == {"action": "create_machine", "values": {
        **{k: v for k, v in (payload or {}).items() if v is not None}, "id_klient": 7,
    }}


def test_machine_client_path_rejects_conflicting_body(client: TestClient) -> None:
    response = client.post("/api/v1/machines/7", json={"id_klient": 8})
    assert response.status_code == 400
    assert response.json()["error"] == "InvalidRequest"


def test_machine_client_path_validates_id_and_body(client: TestClient) -> None:
    assert client.post("/api/v1/machines/-1").status_code == 422
    assert client.post("/api/v1/machines/invalid").status_code == 422
    assert client.post("/api/v1/machines/0").status_code == 201
    assert client.post("/api/v1/machines/7", json={"markaa": "X"}).status_code == 422


def test_machine_client_path_requires_api_key() -> None:
    app = create_app(make_settings(api_key="secret"), service=FakeService())
    with TestClient(app) as client:
        assert client.post("/api/v1/machines/7").status_code == 401
        assert client.post(
            "/api/v1/machines/7", headers={"X-API-Key": "secret"}
        ).status_code == 201


def test_machine_client_path_respects_write_gate() -> None:
    class ReadOnlyService(FakeService):
        def create_machine(self, values: Any) -> dict[str, Any]:
            raise WritesDisabled("Writes are disabled")

    with TestClient(create_app(make_settings(), service=ReadOnlyService())) as client:
        assert client.post("/api/v1/machines/7").status_code == 403
