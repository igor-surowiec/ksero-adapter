"""Opt-in integration tests against a real Firebird database.

Set ``KS_TEST_DB_PATH`` (optionally ``KS_TEST_DB_USER``, ``KS_TEST_DB_PASSWORD``,
``KS_TEST_DB_CHARSET`` and ``KS_TEST_DB_CLIENT``) to enable them::

    KS_TEST_DB_PATH="BAZAMS.FDB" pytest tests/test_integration.py
"""

from __future__ import annotations

import os
from typing import Iterator

import pytest
from fastapi.testclient import TestClient

from ks_adapter.app import create_app
from ks_adapter.config import (
    ApiSettings,
    AppSettings,
    DatabaseSettings,
    ServerSettings,
    resolve_database_path,
)
from ks_adapter.errors import QueryNotAllowed
from ks_adapter.service import DatabaseService

DB_PATH = os.environ.get("KS_TEST_DB_PATH")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DB_PATH, reason="set KS_TEST_DB_PATH to run integration tests"
    ),
]


@pytest.fixture(scope="module")
def service() -> Iterator[DatabaseService]:
    database = DatabaseSettings(
        path=resolve_database_path(str(DB_PATH)),
        user=os.environ.get("KS_TEST_DB_USER", "SYSDBA"),
        password=os.environ.get("KS_TEST_DB_PASSWORD", "masterkey"),
        charset=os.environ.get("KS_TEST_DB_CHARSET", "WIN1250"),
        client_library=os.environ.get("KS_TEST_DB_CLIENT") or None,
    )
    instance = DatabaseService(
        AppSettings(
            database=database, server=ServerSettings(), api=ApiSettings()
        )
    )
    try:
        yield instance
    finally:
        instance.close()


def first_table(service: DatabaseService) -> str:
    tables = service.list_tables()
    assert tables, "the database has no user tables"
    return tables[0]["name"]


def test_health_reports_firebird_version(service: DatabaseService) -> None:
    payload = service.health()
    assert payload["status"] == "ok"
    assert "FIREBIRD" in payload["database"]["server_version"].upper()


def test_schema_lists_user_tables(service: DatabaseService) -> None:
    tables = service.list_tables()
    assert all(table["kind"] in {"table", "view"} for table in tables)
    assert all(table["column_count"] >= 1 for table in tables)


def test_describe_table_returns_columns(service: DatabaseService) -> None:
    name = first_table(service)
    detail = service.describe_table(name)
    assert detail["name"] == name
    assert detail["columns"]
    assert all("type" in column for column in detail["columns"])


def test_fetch_rows_respects_page_size(service: DatabaseService) -> None:
    name = first_table(service)
    page = service.fetch_rows(name, limit=3)
    assert page["table"] == name
    assert page["limit"] == 3
    assert page["offset"] == 0
    assert page["row_count"] <= 3
    assert page["row_count"] == len(page["rows"])
    assert page["total"] >= page["row_count"]


def test_fetch_rows_order_by_first_column(service: DatabaseService) -> None:
    name = first_table(service)
    detail = service.describe_table(name)
    column = detail["columns"][0]["name"]
    page = service.fetch_rows(name, limit=2, order_by=f"{column} DESC")
    assert [row[column] for row in page["rows"]] == sorted(
        (row[column] for row in page["rows"]), reverse=True, key=str
    )


def test_query_round_trip(service: DatabaseService) -> None:
    result = service.run_query("SELECT 1 AS ONE FROM RDB$DATABASE")
    assert result["rows"] == [{"ONE": 1}]
    assert result["truncated"] is False


def test_query_rejects_writes(service: DatabaseService) -> None:
    with pytest.raises(QueryNotAllowed):
        service.run_query("DELETE FROM RDB$DATABASE")


def test_api_serves_live_data(service: DatabaseService) -> None:
    app = create_app(service.settings, service=service)
    with TestClient(app) as client:
        tables = client.get("/api/v1/tables")
        assert tables.status_code == 200
        name = tables.json()["tables"][0]["name"]
        rows = client.get(f"/api/v1/tables/{name}/rows", params={"limit": 2})
        assert rows.status_code == 200
        assert rows.json()["table"] == name


def test_clients_endpoint_lists_contractors(service: DatabaseService) -> None:
    page = service.fetch_clients(limit=5)
    assert page["limit"] == 5
    assert page["offset"] == 0
    assert page["count"] == len(page["clients"])
    assert page["total"] >= page["count"]
    assert all({"id", "name"} <= set(client) for client in page["clients"])


def test_clients_endpoint_over_http(service: DatabaseService) -> None:
    app = create_app(service.settings, service=service)
    with TestClient(app) as client:
        response = client.get("/api/v1/clients", params={"limit": 3})
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 3
        assert isinstance(body["clients"], list)
        assert body["count"] == len(body["clients"])
        empty = client.get("/api/v1/clients", params={"search": "zzz-nobody-zzz"})
        assert empty.status_code == 200
        assert empty.json()["clients"] == []


def test_agreements_endpoint_lists_contracts(service: DatabaseService) -> None:
    page = service.fetch_agreements(limit=5)
    assert page["limit"] == 5
    assert page["offset"] == 0
    assert page["count"] == len(page["agreements"])
    assert page["total"] >= page["count"]
    assert all({"id", "number"} <= set(agreement) for agreement in page["agreements"])


def test_agreements_endpoint_over_http(service: DatabaseService) -> None:
    app = create_app(service.settings, service=service)
    with TestClient(app) as client:
        response = client.get("/api/v1/agreements", params={"limit": 3})
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 3
        assert isinstance(body["agreements"], list)
        assert body["count"] == len(body["agreements"])
        empty = client.get("/api/v1/agreements", params={"search": "zzz-nobody-zzz"})
        assert empty.status_code == 200
        assert empty.json()["agreements"] == []


def test_machines_endpoint_lists_devices(service: DatabaseService) -> None:
    page = service.fetch_machines(limit=5)
    assert page["limit"] == 5
    assert page["offset"] == 0
    assert page["count"] == len(page["machines"])
    assert page["total"] >= page["count"]
    assert all(
        {"id", "brand", "serial"} <= set(machine) for machine in page["machines"]
    )


def test_machines_endpoint_over_http(service: DatabaseService) -> None:
    app = create_app(service.settings, service=service)
    with TestClient(app) as client:
        response = client.get("/api/v1/machines", params={"limit": 3})
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 3
        assert isinstance(body["machines"], list)
        assert body["count"] == len(body["machines"])
        empty = client.get("/api/v1/machines", params={"search": "zzz-nobody-zzz"})
        assert empty.status_code == 200
        assert empty.json()["machines"] == []


def test_orders_endpoint_lists_service_orders(service: DatabaseService) -> None:
    page = service.fetch_orders(limit=5)
    assert page["limit"] == 5
    assert page["offset"] == 0
    assert page["count"] == len(page["orders"])
    assert page["total"] >= page["count"]
    assert all({"id", "order_id", "status"} <= set(order) for order in page["orders"])


def test_orders_endpoint_over_http(service: DatabaseService) -> None:
    app = create_app(service.settings, service=service)
    with TestClient(app) as client:
        response = client.get("/api/v1/orders", params={"limit": 3})
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 3
        assert isinstance(body["orders"], list)
        assert body["count"] == len(body["orders"])
        empty = client.get("/api/v1/orders", params={"search": "zzz-nobody-zzz"})
        assert empty.status_code == 200
        assert empty.json()["orders"] == []


def test_orders_search_spans_many_columns_without_hitting_the_limit(
    service: DatabaseService,
) -> None:
    """Every curated column must exist and still prepare together."""
    from ks_adapter.service import ORDER_FIELDS, ORDERS_TABLE, ORDER_SEARCH_COLUMNS

    columns = service.describe_table(ORDERS_TABLE)["columns"]
    names = {column["name"].upper() for column in columns}
    assert set(ORDER_SEARCH_COLUMNS) <= names
    assert {column for column, _alias in ORDER_FIELDS} <= names

    page = service.fetch_orders(search="a", limit=2)
    assert page["count"] == len(page["orders"])


def test_invoices_endpoint_lists_invoices(service: DatabaseService) -> None:
    page = service.fetch_invoices(limit=5)
    assert page["limit"] == 5
    assert page["offset"] == 0
    assert page["count"] == len(page["invoices"])
    assert page["total"] >= page["count"]
    assert all(
        {"id", "number", "gross", "amount_due"} <= set(invoice)
        for invoice in page["invoices"]
    )


def test_invoices_endpoint_over_http(service: DatabaseService) -> None:
    app = create_app(service.settings, service=service)
    with TestClient(app) as client:
        response = client.get("/api/v1/invoices", params={"limit": 3})
        assert response.status_code == 200
        body = response.json()
        assert body["limit"] == 3
        assert isinstance(body["invoices"], list)
        assert body["count"] == len(body["invoices"])
        empty = client.get("/api/v1/invoices", params={"search": "zzz-nobody-zzz"})
        assert empty.status_code == 200
        assert empty.json()["invoices"] == []


def test_invoice_columns_match_the_live_schema(service: DatabaseService) -> None:
    """Every curated column must exist and still prepare in one statement."""
    from ks_adapter.service import (
        INVOICE_FIELDS,
        INVOICES_TABLE,
        INVOICE_SEARCH_COLUMNS,
    )

    columns = service.describe_table(INVOICES_TABLE)["columns"]
    names = {column["name"].upper() for column in columns}
    assert set(INVOICE_SEARCH_COLUMNS) <= names
    assert {column for column, _alias in INVOICE_FIELDS} <= names

    page = service.fetch_invoices(search="a", limit=2)
    assert page["count"] == len(page["invoices"])

