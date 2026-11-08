"""Opt-in integration tests against a real Firebird database.

Set ``KS_TEST_DB_PATH`` (optionally ``KS_TEST_DB_USER``, ``KS_TEST_DB_PASSWORD``,
``KS_TEST_DB_CHARSET`` and ``KS_TEST_DB_CLIENT``) to enable them::

    KS_TEST_DB_PATH="BAZAMS.FDB" pytest tests/test_integration.py

The write tests additionally need ``KS_TEST_DB_WRITABLE=1``: they insert a
disposable contractor and machine and delete them again, so they are never run
by accident against a production database.
"""

from __future__ import annotations

import dataclasses
import json
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
from ks_adapter.errors import QueryNotAllowed, RecordNotFound, WritesDisabled
from ks_adapter.service import DatabaseService

DB_PATH = os.environ.get("KS_TEST_DB_PATH")
WRITABLE = os.environ.get("KS_TEST_DB_WRITABLE")

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not DB_PATH, reason="set KS_TEST_DB_PATH to run integration tests"
    ),
]

requires_writable = pytest.mark.skipif(
    not (DB_PATH and WRITABLE),
    reason="set KS_TEST_DB_PATH and KS_TEST_DB_WRITABLE=1 to run write tests",
)


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
    assert all({"id_klient_table", "nazwa"} <= set(client) for client in page["clients"])


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
    assert all({"id_umowacpc_table", "umowa"} <= set(agreement) for agreement in page["agreements"])


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
        {"id_maszyna_table", "marka", "serial"} <= set(machine) for machine in page["machines"]
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
    assert all({"id_zlecenie_table", "id_zlecenie", "stan"} <= set(order) for order in page["orders"])


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
    from ks_adapter.service import ORDER_COLUMNS, ORDERS_TABLE, ORDER_SEARCH_COLUMNS

    columns = service.describe_table(ORDERS_TABLE)["columns"]
    names = {column["name"].upper() for column in columns}
    assert set(ORDER_SEARCH_COLUMNS) <= names
    assert set(ORDER_COLUMNS) <= names

    page = service.fetch_orders(search="a", limit=2)
    assert page["count"] == len(page["orders"])


def test_invoices_endpoint_lists_invoices(service: DatabaseService) -> None:
    page = service.fetch_invoices(limit=5)
    assert page["limit"] == 5
    assert page["offset"] == 0
    assert page["count"] == len(page["invoices"])
    assert page["total"] >= page["count"]
    assert all(
        {"id_faktura_table", "numer", "suma_brutto", "do_zaplaty"} <= set(invoice)
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
        INVOICE_COLUMNS,
        INVOICES_TABLE,
        INVOICE_SEARCH_COLUMNS,
    )

    columns = service.describe_table(INVOICES_TABLE)["columns"]
    names = {column["name"].upper() for column in columns}
    assert set(INVOICE_SEARCH_COLUMNS) <= names
    assert set(INVOICE_COLUMNS) <= names

    page = service.fetch_invoices(search="a", limit=2)
    assert page["count"] == len(page["invoices"])



@pytest.fixture(scope="module")
def write_service(service: DatabaseService) -> Iterator[DatabaseService]:
    """A second service on the same database with ``api.allow_writes`` on."""
    settings = dataclasses.replace(
        service.settings,
        api=dataclasses.replace(service.settings.api, allow_writes=True),
    )
    instance = DatabaseService(settings)
    try:
        yield instance
    finally:
        instance.close()


def delete_client(service: DatabaseService, surrogate_key: int) -> None:
    """Remove a test client again (the adapter itself has no delete route)."""
    with service.pool.write_session() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                'DELETE FROM "KLIENT" WHERE "ID_KLIENT_TABLE" = ?', [surrogate_key]
            )
        finally:
            cursor.close()


def test_create_client_is_refused_without_allow_writes(
    service: DatabaseService,
) -> None:
    with pytest.raises(WritesDisabled):
        service.create_client({"nazwa": "KS ADAPTER TEST"})


@requires_writable
def test_create_client_stores_the_supplied_fields(
    write_service: DatabaseService,
) -> None:
    name = f"KS ADAPTER TEST {os.getpid()}"
    created = write_service.create_client(
        {
            "nazwa": f"  {name}  ",
            "nip": "1234567890",
            "adres": "ul. Testowa 1",
            "kod": "00-001",
            "poczta": "Warszawa",
            "telefon": "600100200",
            "termin": 14,
        }
    )
    try:
        assert created["nazwa"] == name
        assert created["id_klient_table"]
        assert created["id_klient"]
        assert created["nip"] == "1234567890"
        assert created["adres"] == "ul. Testowa 1"
        assert created["kod"] == "00-001"
        assert created["poczta"] == "Warszawa"
        assert created["telefon"] == "600100200"
        assert created["termin"] == 14
        # Untouched text columns carry the legacy application's empty strings,
        # not NULL, because its forms always fill them in.
        assert created["regon"] == ""
        assert created["nazwa_s"] == ""
        page = write_service.fetch_clients(search=name, limit=5)
        assert [client["id_klient_table"] for client in page["clients"]] == [
            created["id_klient_table"]
        ]
    finally:
        delete_client(write_service, created["id_klient_table"])


@requires_writable
def test_create_client_matches_the_legacy_row_profile(
    write_service: DatabaseService,
) -> None:
    """A bridged client must look exactly like one the program created.

    The program filters its client list by ``ID_FIRMA`` and leans on the other
    columns of :data:`ks_adapter.service.CLIENT_INSERT_DEFAULTS`, so this test
    reads them straight from the stored row, outside the curated projection.
    """
    from ks_adapter.service import CLIENT_INSERT_DEFAULTS

    name = f"KS ADAPTER PROFILE {os.getpid()}"
    created = write_service.create_client({"nazwa": name})
    try:
        with write_service.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    'SELECT "ID_FIRMA", "ID_KLIENT", "ID_ODDZIAL", "TYP", '
                    '"PLATNOSC", "KOD_KRAJU", "IDW", "AKTYWNY", "NAZWA_S", '
                    '"STATUS", "OSTZAPIS" FROM "KLIENT" '
                    'WHERE "ID_KLIENT_TABLE" = ?',
                    [created["id_klient_table"]],
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        stored = dict(
            zip(
                (
                    "ID_FIRMA",
                    "ID_KLIENT",
                    "ID_ODDZIAL",
                    "TYP",
                    "PLATNOSC",
                    "KOD_KRAJU",
                    "IDW",
                    "AKTYWNY",
                    "NAZWA_S",
                    "STATUS",
                    "OSTZAPIS",
                ),
                row,
            )
        )
        for column, expected in CLIENT_INSERT_DEFAULTS.items():
            if column in stored and column != "ID_ODDZIAL":
                assert stored[column] == expected, column
        assert stored["ID_FIRMA"] == 0
        assert stored["ID_ODDZIAL"] == 1
        assert stored["ID_KLIENT"] == created["id_klient"]
    finally:
        delete_client(write_service, created["id_klient_table"])


@requires_writable
def test_create_client_endpoint_over_http(write_service: DatabaseService) -> None:
    name = f"KS ADAPTER HTTP {os.getpid()}"
    app = create_app(write_service.settings, service=write_service)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/clients",
            json={"nazwa": name, "nip": "1234567890", "poczta": "Warszawa"},
        )
    body = response.json()
    try:
        assert response.status_code == 201
        assert body["nazwa"] == name
        assert body["nip"] == "1234567890"
        assert body["poczta"] == "Warszawa"
        assert body["id_klient_table"]
    finally:
        if response.status_code == 201:
            delete_client(write_service, body["id_klient_table"])



def delete_machine(service: DatabaseService, surrogate_key: int) -> None:
    """Remove a test machine again (the adapter itself has no delete route)."""
    with service.pool.write_session() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                'DELETE FROM "MASZYNA" WHERE "ID_MASZYNA_TABLE" = ?', [surrogate_key]
            )
        finally:
            cursor.close()


def test_create_machine_is_refused_without_allow_writes(
    service: DatabaseService,
) -> None:
    with pytest.raises(WritesDisabled):
        service.create_machine({"id_klient": 1, "marka": "KS ADAPTER TEST"})


@requires_writable
def test_create_machine_stores_the_supplied_fields(
    write_service: DatabaseService,
) -> None:
    import datetime as dt

    owner = write_service.create_client(
        {"nazwa": f"KS ADAPTER MACHINE {os.getpid()}"}
    )
    serial = f"KS-MASZYNA-{os.getpid()}"
    machine: dict[str, object] = {}
    try:
        machine = write_service.create_machine(
            {
                "id_klient": owner["id_klient"],
                "marka": "KS ADAPTER TEST",
                "model": "TEST-1",
                "serial": serial,
                "instalacja": dt.date(2026, 1, 2),
                "uwagi": "  wpis testowy  ",
            }
        )
        assert machine["id_maszyna_table"]
        assert machine["id_maszyna"]
        assert machine["id_klient"] == owner["id_klient"]
        assert machine["marka"] == "KS ADAPTER TEST"
        assert machine["serial"] == serial
        assert machine["instalacja"] == "2026-01-02"
        assert machine["uwagi"] == "wpis testowy"
        assert machine["aktywna"] is None

        page = write_service.fetch_machines(search=serial, limit=5)
        assert [row["id_maszyna_table"] for row in page["machines"]] == [
            machine["id_maszyna_table"]
        ]
    finally:
        if machine:
            delete_machine(write_service, machine["id_maszyna_table"])
        delete_client(write_service, owner["id_klient_table"])


@requires_writable
def test_create_machine_endpoint_over_http(write_service: DatabaseService) -> None:
    owner = write_service.create_client(
        {"nazwa": f"KS ADAPTER MACHINE HTTP {os.getpid()}"}
    )
    serial = f"KS-MASZYNA-HTTP-{os.getpid()}"
    app = create_app(write_service.settings, service=write_service)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/machines",
            json={"id_klient": owner["id_klient"], "serial": serial, "marka": "KS"},
        )
    body = response.json()
    try:
        assert response.status_code == 201
        assert body["serial"] == serial
        assert body["id_maszyna_table"]
    finally:
        if response.status_code == 201:
            delete_machine(write_service, body["id_maszyna_table"])
        delete_client(write_service, owner["id_klient_table"])



@requires_writable
def test_update_client_endpoint_preserves_omitted_fields(
    write_service: DatabaseService,
) -> None:
    created = write_service.create_client({"nazwa": "KS ADAPTER UPDATE TEST"})
    key = created["id_klient"]
    try:
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            url = f"/api/v1/clients/{key}"
            response = client.patch(url, json={"nip": "123", "adres": " "})
            assert response.status_code == 200
            updated = response.json()
            assert updated["nip"] == "123"
            assert updated["adres"] == ""
            for field in created.keys() - {"nip", "adres"}:
                assert updated[field] == created[field]
            response = client.patch(url, json={"nip": None})
            assert response.status_code == 200
            assert response.json()["nip"] is None
        stored = write_service.fetch_rows(
            "KLIENT", filters=json.dumps({"ID_KLIENT": key})
        )["rows"][0]
        assert stored["NIP"] is None
        assert stored["ID_FIRMA"] == 0
        assert stored["NAZWA"] == created["nazwa"]
    finally:
        delete_client(write_service, created["id_klient_table"])
    with pytest.raises(RecordNotFound):
        write_service.update_client(key, {"nip": "123"})


@requires_writable
def test_delete_client_endpoint_removes_client_and_trigger_managed_machine(
    write_service: DatabaseService,
) -> None:
    owner = write_service.create_client({"nazwa": "KS ADAPTER DELETE TEST"})
    other = None
    machine = None
    try:
        other = write_service.create_client({"nazwa": "KS ADAPTER KEEP TEST"})
        machine = write_service.create_machine({"id_klient": owner["id_klient"]})
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            url = f"/api/v1/clients/{owner['id_klient']}"
            response = client.delete(url)
            assert response.status_code == 204
            assert response.content == b""
            assert client.delete(url).status_code == 404
        assert write_service.fetch_rows(
            "KLIENT", filters=json.dumps({"ID_KLIENT": owner["id_klient"]})
        )["total"] == 0
        assert write_service.fetch_rows(
            "MASZYNA", filters=json.dumps({"ID_KLIENT": owner["id_klient"]})
        )["total"] == 0
        assert write_service.fetch_rows(
            "KLIENT", filters=json.dumps({"ID_KLIENT": other["id_klient"]})
        )["total"] == 1
    finally:
        if machine is not None:
            delete_machine(write_service, machine["id_maszyna_table"])
        if other is not None:
            delete_client(write_service, other["id_klient_table"])
        delete_client(write_service, owner["id_klient_table"])


def test_delete_client_is_refused_without_allow_writes(
    service: DatabaseService,
) -> None:
    with pytest.raises(WritesDisabled):
        service.delete_client(1)


@requires_writable
@pytest.mark.parametrize("payload", [{}, {"id_klient": None}, {"id_klient": 0},
                                     {"marka": "KS ADAPTER UNASSIGNED TEST"}])
def test_create_machine_endpoint_without_owner(
    write_service: DatabaseService, payload: dict[str, object],
) -> None:
    app = create_app(write_service.settings, service=write_service)
    with TestClient(app) as client:
        response = client.post("/api/v1/machines", json=payload)
    assert response.status_code == 201
    machine = response.json()
    try:
        assert machine["id_klient"] == 0
        assert machine["id_maszyna"]
        stored = write_service.fetch_rows(
            "MASZYNA", filters=json.dumps({
                "ID_MASZYNA_TABLE": machine["id_maszyna_table"],
            }),
        )["rows"][0]
        assert stored["ID_KLIENT"] == 0
    finally:
        delete_machine(write_service, machine["id_maszyna_table"])
