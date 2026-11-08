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
from typing import Any, Iterator

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
        assert machine["aktywna"] == "TAK"

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


def delete_agreement(service: DatabaseService, key: int) -> None:
    """Remove only the disposable agreement identified by its table key."""
    with service.pool.write_session() as connection:
        cursor = connection.cursor()
        try:
            cursor.execute(
                'DELETE FROM "UMOWACPC" WHERE "ID_UMOWACPC_TABLE" = ?', [key]
            )
        finally:
            cursor.close()


@requires_writable
def test_create_agreement_endpoint_stores_fields_and_legacy_defaults(
    write_service: DatabaseService,
) -> None:
    owner = write_service.create_client({"nazwa": "KS ADAPTER AGREEMENT TEST"})
    agreement = None
    try:
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            response = client.post(f"/api/v1/agreements/{owner['id_klient']}", json={
                "umowa": " KS ADAPTER AGREEMENT TEST ", "u_start": "2026-11-08",
                "rabat": "2.5000", "termin": 14, "aktywna": "TAK",
            })
        assert response.status_code == 201
        agreement = response.json()
        assert agreement["id_umowacpc"] >= 1
        assert agreement["id_umowacpc_table"]
        assert agreement["umowa"] == "KS ADAPTER AGREEMENT TEST"
        assert agreement["u_start"] == "2026-11-08"
        assert float(agreement["rabat"]) == 2.5
        assert agreement["platnosc"] == "$_$"
        assert agreement["termin"] == 14
        stored = write_service.fetch_rows("UMOWACPC", filters=json.dumps({
            "ID_UMOWACPC_TABLE": agreement["id_umowacpc_table"],
        }))["rows"][0]
        assert stored["ID_KLIENT"] == owner["id_klient"]
        assert stored["AUTOCPC"] == 0
        assert stored["OPIEKUN"] == ""
        assert stored["FRAPAR1"] == 0
        assert stored["FRANAZ1"] == ""
    finally:
        if agreement is not None:
            delete_agreement(write_service, agreement["id_umowacpc_table"])
        delete_client(write_service, owner["id_klient_table"])


def test_create_agreement_is_refused_without_allow_writes(
    service: DatabaseService,
) -> None:
    with pytest.raises(WritesDisabled):
        service.create_agreement({"id_klient": 7})


@requires_writable
def test_create_agreement_reuses_a_deleted_gap(write_service: DatabaseService) -> None:
    owner = write_service.create_client({"nazwa": "KS ADAPTER GAP TEST"})
    agreements = []
    try:
        for _ in range(3):
            agreements.append(write_service.create_agreement({
                "id_klient": owner["id_klient"],
            }))
        removed = agreements.pop(1)
        delete_agreement(write_service, removed["id_umowacpc_table"])
        replacement = write_service.create_agreement({"id_klient": owner["id_klient"]})
        agreements.append(replacement)
        assert replacement["id_umowacpc"] == removed["id_umowacpc"]
    finally:
        for agreement in agreements:
            delete_agreement(write_service, agreement["id_umowacpc_table"])
        delete_client(write_service, owner["id_klient_table"])


@requires_writable
def test_concurrent_agreement_allocation_across_services(
    write_service: DatabaseService,
) -> None:
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    owner = write_service.create_client({"nazwa": "KS ADAPTER CONCURRENT TEST"})
    peer = DatabaseService(write_service.settings)
    agreements = []
    errors = []
    start = Barrier(4)

    def create(instance: DatabaseService) -> dict[str, Any]:
        start.wait(timeout=10)
        return instance.create_agreement({"id_klient": owner["id_klient"]})

    try:
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(create, instance) for instance in (
                write_service, peer, write_service, peer,
            )]
            for future in futures:
                try:
                    agreements.append(future.result(timeout=20))
                except Exception as exc:
                    errors.append(exc)
        assert not errors, errors
        assert len({a["id_umowacpc"] for a in agreements}) == 4
    finally:
        peer.close()
        for agreement in agreements:
            delete_agreement(write_service, agreement["id_umowacpc_table"])
        delete_client(write_service, owner["id_klient_table"])


@requires_writable
def test_create_agreement_defaults_match_legacy_reference(
    write_service: DatabaseService,
) -> None:
    reference = write_service.fetch_rows(
        "UMOWACPC", filters=json.dumps({"ID_UMOWACPC": 1})
    )["rows"]
    if len(reference) != 1:
        pytest.skip("requires one legacy agreement with ID_UMOWACPC=1")
    owner = write_service.create_client({"nazwa": "KS ADAPTER DEFAULTS TEST"})
    agreement = None
    try:
        before = write_service.run_query(
            "SELECT CURRENT_DATE AS TODAY FROM RDB$DATABASE"
        )
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            response = client.post(f"/api/v1/agreements/{owner['id_klient']}")
        assert response.status_code == 201
        agreement = response.json()
        after = write_service.run_query(
            "SELECT CURRENT_DATE AS TODAY FROM RDB$DATABASE"
        )
        assert agreement["u_start"] in {
            before["rows"][0]["TODAY"], after["rows"][0]["TODAY"],
        }
        assert agreement["aktywna"] == "TAK"
        assert agreement["umowa"] in {
            f"{agreement['id_umowacpc']}/{value[:4]}"
            for value in (before["rows"][0]["TODAY"], after["rows"][0]["TODAY"])
        }
        stored = write_service.fetch_rows("UMOWACPC", filters=json.dumps({
            "ID_UMOWACPC_TABLE": agreement["id_umowacpc_table"],
        }))["rows"][0]
        excluded = {"ID_UMOWACPC_TABLE", "ID_UMOWACPC", "ID_KLIENT",
                    "UMOWA", "TYP", "U_START", "KOSZTY", "PRZYCHODY", "WYNIK"}
        assert all(stored[name] is None for name in ("KOSZTY", "PRZYCHODY", "WYNIK"))
        differences = [name for name in stored if name not in excluded
                       and stored[name] != reference[0][name]]
        # Report only column names, never customer record values.
        assert not differences, differences
    finally:
        if agreement is not None:
            delete_agreement(write_service, agreement["id_umowacpc_table"])
        delete_client(write_service, owner["id_klient_table"])


@requires_writable
def test_update_machine_endpoint_preserves_omitted_fields(
    write_service: DatabaseService,
) -> None:
    owner = write_service.create_client({"nazwa": "KS ADAPTER MACHINE PATCH TEST"})
    machine = None
    try:
        machine = write_service.create_machine({
            "id_klient": owner["id_klient"], "marka": "KS ADAPTER PATCH TEST",
            "model": "BEFORE", "serial": "SN TEST",
        })
        app = create_app(write_service.settings, service=write_service)
        url = f"/api/v1/machines/{machine['id_maszyna']}"
        with TestClient(app) as client:
            response = client.patch(url, json={"model": " AFTER ", "serial": " "})
            assert response.status_code == 200
            updated = response.json()
            assert updated["model"] == "AFTER"
            assert updated["serial"] == ""
            for field in machine.keys() - {"model", "serial"}:
                assert updated[field] == machine[field]
            response = client.patch(url, json={"id_klient": 0, "serial": None})
            assert response.status_code == 200
            assert response.json()["id_klient"] == 0
            assert response.json()["serial"] is None
            assert client.patch(url, json={"id_klient": None}).status_code == 400
            assert client.patch(url, json={"id_oddzial": None}).status_code == 400
            assert client.patch(url, json={}).status_code == 400
        stored = write_service.fetch_rows("MASZYNA", filters=json.dumps({
            "ID_MASZYNA_TABLE": machine["id_maszyna_table"],
        }))["rows"][0]
        assert stored["MODEL"] == "AFTER"
        assert stored["SERIAL"] is None
        assert stored["ID_KLIENT"] == 0
    finally:
        if machine is not None:
            delete_machine(write_service, machine["id_maszyna_table"])
        delete_client(write_service, owner["id_klient_table"])
    with pytest.raises(RecordNotFound):
        write_service.update_machine(machine["id_maszyna"], {"model": "MISSING"})


@requires_writable
def test_update_machine_rejects_ambiguous_id_over_http(
    write_service: DatabaseService,
) -> None:
    from ks_adapter.sql import build_update

    machines = []
    try:
        for model in ("FIRST", "SECOND"):
            machines.append(write_service.create_machine({"model": model}))
        with write_service.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(build_update(
                    "MASZYNA", ["ID_MASZYNA"], key="ID_MASZYNA_TABLE",
                ), [machines[0]["id_maszyna"], machines[1]["id_maszyna_table"]])
            finally:
                cursor.close()
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/machines/{machines[0]['id_maszyna']}",
                json={"model": "SHOULD NOT CHANGE"},
            )
        assert response.status_code == 409
        assert response.json()["error"] == "RecordConflict"
        for machine in machines:
            stored = write_service.fetch_rows("MASZYNA", filters=json.dumps({
                "ID_MASZYNA_TABLE": machine["id_maszyna_table"],
            }))["rows"][0]
            assert stored["MODEL"] == machine["model"]
    finally:
        for machine in machines:
            delete_machine(write_service, machine["id_maszyna_table"])


def test_update_machine_is_refused_without_allow_writes(
    service: DatabaseService,
) -> None:
    with pytest.raises(WritesDisabled):
        service.update_machine(1, {"model": "BLOCKED"})


@requires_writable
def test_agreement_machine_links_are_optional_exact_and_atomic(
    write_service: DatabaseService,
) -> None:
    owner = write_service.create_client({"nazwa": "KS ADAPTER MACHINE LINKS TEST"})
    machines = []
    agreements = []
    single = DatabaseService(dataclasses.replace(
        write_service.settings,
        database=dataclasses.replace(write_service.settings.database, pool_size=1),
    ))

    def stored(machine: dict[str, Any]) -> dict[str, Any]:
        return write_service.fetch_rows("MASZYNA", filters=json.dumps({
            "ID_MASZYNA_TABLE": machine["id_maszyna_table"],
        }))["rows"][0]

    try:
        original = write_service.create_agreement({"id_klient": owner["id_klient"]})
        agreements.append(original)
        for _ in range(3):
            machines.append(write_service.create_machine({
                "id_klient": owner["id_klient"],
                "id_umowacpc": original["id_umowacpc"], "model": "LINK TEST",
            }))
        missing = 2147483647
        assert write_service.fetch_rows(
            "MASZYNA", filters=json.dumps({"ID_MASZYNA": missing})
        )["total"] == 0
        app = create_app(single.settings, service=single)
        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/agreements/{owner['id_klient']}", json={
                    "machines": [m["id_maszyna"] for m in machines[:2]],
                },
            )
            assert response.status_code == 201
            linked = response.json()
            agreements.append(linked)
            for machine in machines[:2]:
                assert stored(machine)["ID_UMOWACPC"] == linked["id_umowacpc"]
            assert stored(machines[2])["ID_UMOWACPC"] == original["id_umowacpc"]
            url = f"/api/v1/agreements/{linked['id_umowacpc']}"
            response = client.patch(url, json={
                "uwagi": "UPDATED", "machines": [machines[2]["id_maszyna"]],
            })
            assert response.status_code == 200
            assert response.json()["uwagi"] == "UPDATED"
            for machine in machines[:2]:
                assert stored(machine)["ID_UMOWACPC"] is None
            assert stored(machines[2])["ID_UMOWACPC"] == linked["id_umowacpc"]
            assert client.patch(url, json={"typ": "TEST"}).status_code == 200
            assert stored(machines[2])["ID_UMOWACPC"] == linked["id_umowacpc"]
            # An empty list alone is a valid request to remove all links.
            assert client.patch(url, json={"machines": []}).status_code == 200
            for machine in machines:
                row = stored(machine)
                assert row["ID_UMOWACPC"] is None
                assert row["ID_KLIENT"] == owner["id_klient"]
                assert row["MODEL"] == "LINK TEST"
            assert client.patch(url, json={
                "machines": [machines[0]["id_maszyna"]],
            }).status_code == 200
            # Clearing one agreement must not touch another agreement's links.
            assert client.patch(
                f"/api/v1/agreements/{original['id_umowacpc']}",
                json={"machines": []},
            ).status_code == 200
            assert stored(machines[0])["ID_UMOWACPC"] == linked["id_umowacpc"]
            # A failure restores removed links as well as newly assigned ones.
            response = client.patch(url, json={
                "uwagi": "SHOULD ROLLBACK",
                "machines": [machines[1]["id_maszyna"], missing],
            })
            assert response.status_code == 404
            old = write_service.fetch_rows("UMOWACPC", filters=json.dumps({
                "ID_UMOWACPC_TABLE": linked["id_umowacpc_table"],
            }))["rows"][0]
            assert old["UWAGI"] == "UPDATED"
            assert stored(machines[0])["ID_UMOWACPC"] == linked["id_umowacpc"]
            assert stored(machines[1])["ID_UMOWACPC"] is None
            count_before = write_service.fetch_rows("UMOWACPC")["total"]
            response = client.post(
                f"/api/v1/agreements/{owner['id_klient']}", json={
                    "machines": [machines[0]["id_maszyna"], missing],
                },
            )
            assert response.status_code == 404
            assert write_service.fetch_rows("UMOWACPC")["total"] == count_before
            assert stored(machines[0])["ID_UMOWACPC"] == linked["id_umowacpc"]
    finally:
        single.close()
        for machine in machines:
            delete_machine(write_service, machine["id_maszyna_table"])
        for agreement in agreements:
            delete_agreement(write_service, agreement["id_umowacpc_table"])
        delete_client(write_service, owner["id_klient_table"])


@requires_writable
def test_agreement_links_reject_duplicate_machine_business_ids(
    write_service: DatabaseService,
) -> None:
    from ks_adapter.sql import build_update

    owner = write_service.create_client({"nazwa": "KS ADAPTER AMBIGUOUS LINK TEST"})
    machines = []
    agreement = None
    try:
        agreement = write_service.create_agreement({"id_klient": owner["id_klient"]})
        for _ in range(2):
            machines.append(write_service.create_machine({
                "id_klient": owner["id_klient"],
            }))
        with write_service.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(build_update(
                    "MASZYNA", ["ID_MASZYNA"], key="ID_MASZYNA_TABLE",
                ), [machines[0]["id_maszyna"], machines[1]["id_maszyna_table"]])
            finally:
                cursor.close()
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            response = client.patch(
                f"/api/v1/agreements/{agreement['id_umowacpc']}",
                json={"machines": [machines[0]["id_maszyna"]]},
            )
            assert response.status_code == 409
            response = client.post(
                f"/api/v1/agreements/{owner['id_klient']}",
                json={"machines": [machines[0]["id_maszyna"]]},
            )
            assert response.status_code == 409
    finally:
        for machine in machines:
            delete_machine(write_service, machine["id_maszyna_table"])
        if agreement is not None:
            delete_agreement(write_service, agreement["id_umowacpc_table"])
        delete_client(write_service, owner["id_klient_table"])


@requires_writable
def test_cpc_crud_and_native_parent_aggregate_triggers(
    write_service: DatabaseService,
) -> None:
    owner = write_service.create_client({"nazwa": "KS ADAPTER CPC TEST"})
    agreement = None
    machine = None
    settlements = []

    def totals(table: str, key: str, value: int) -> dict[str, Any]:
        return write_service.fetch_rows(
            table, filters=json.dumps({key: value})
        )["rows"][0]

    try:
        agreement = write_service.create_agreement({"id_klient": owner["id_klient"]})
        machine = write_service.create_machine({
            "id_klient": owner["id_klient"], "id_umowacpc": agreement["id_umowacpc"],
        })
        payload = {"id_klient": owner["id_klient"],
            "id_maszyna": machine["id_maszyna"],
            "id_umowacpc": agreement["id_umowacpc"], "rok": 2026, "miesiac": 11}
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            response = client.post("/api/v1/cpc-settlement", json={**payload,
                "licznik_mono_start": 1000, "oplata_suma": "100.00",
                "koszty": "20.00", "wynik": "80.00", "uwagi": " CPC TEST ",
            })
            assert response.status_code == 201
            created = response.json()
            settlements.append(created["id_cpc_table"])
            url = f"/api/v1/cpc-settlement/{created['id_cpc_table']}"
            assert created["uwagi"] == "CPC TEST"
            assert created["idvat"] == 0
            assert created["oplata_kolor"] == 0
            assert client.get(url).json() == created
            response = client.get("/api/v1/cpc-settlement", params={
                "filters": json.dumps({"ID_MASZYNA": machine["id_maszyna"]}),
                "search": "CPC TEST",
            })
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert response.json()["cpc"][0]["id_cpc_table"] == created["id_cpc_table"]
            for table, key, value in (
                ("MASZYNA", "ID_MASZYNA_TABLE", machine["id_maszyna_table"]),
                ("UMOWACPC", "ID_UMOWACPC_TABLE", agreement["id_umowacpc_table"]),
            ):
                row = totals(table, key, value)
                assert row["PRZYCHODY"] == 100
                assert row["KOSZTY"] == 20
                assert row["WYNIK"] == 80
            parents = {key: payload[key] for key in (
                "id_klient", "id_maszyna", "id_umowacpc",
            )}
            before = write_service.run_query(
                "SELECT CURRENT_DATE AS TODAY FROM RDB$DATABASE"
            )["rows"][0]["TODAY"]
            response = client.post("/api/v1/cpc-settlement", json={**parents,
                "oplata_suma": 200, "koszty": 50, "wynik": 150,
            })
            assert response.status_code == 201
            second = response.json()
            settlements.append(second["id_cpc_table"])
            after = write_service.run_query(
                "SELECT CURRENT_DATE AS TODAY FROM RDB$DATABASE"
            )["rows"][0]["TODAY"]
            assert (second["rok"], second["miesiac"]) in {
                (int(value[:4]), int(value[5:7])) for value in (before, after)
            }
            response = client.patch(url, json={"licznik_mono_end": 1500,
                "oplata_suma": "150.00", "koszty": "25.00", "wynik": "125.00",
                "uwagi": None,
            })
            assert response.status_code == 200
            updated = response.json()
            assert updated["licznik_mono_start"] == 1000
            assert updated["licznik_mono_end"] == 1500
            assert updated["uwagi"] is None
            assert client.patch(url, json={}).status_code == 400
            assert client.patch(url, json={"idvat": None}).status_code == 400
            for table, key, value in (
                ("MASZYNA", "ID_MASZYNA_TABLE", machine["id_maszyna_table"]),
                ("UMOWACPC", "ID_UMOWACPC_TABLE", agreement["id_umowacpc_table"]),
            ):
                row = totals(table, key, value)
                assert row["PRZYCHODY"] == 350
                assert row["KOSZTY"] == 75
                assert row["WYNIK"] == 275
            response = client.delete(url)
            assert response.status_code == 204
            assert response.content == b""
            settlements.remove(created["id_cpc_table"])
            assert client.get(url).status_code == 404
            assert client.patch(url, json={"uwagi": "X"}).status_code == 404
            assert client.delete(url).status_code == 404
            for table, key, value in (
                ("MASZYNA", "ID_MASZYNA_TABLE", machine["id_maszyna_table"]),
                ("UMOWACPC", "ID_UMOWACPC_TABLE", agreement["id_umowacpc_table"]),
            ):
                row = totals(table, key, value)
                assert row["PRZYCHODY"] == 200
                assert row["KOSZTY"] == 50
                assert row["WYNIK"] == 150
    finally:
        for key in settlements:
            write_service.delete_cpc(key)
        if machine is not None:
            delete_machine(write_service, machine["id_maszyna_table"])
        if agreement is not None:
            delete_agreement(write_service, agreement["id_umowacpc_table"])
        delete_client(write_service, owner["id_klient_table"])


def test_cpc_reads_work_without_writes_enabled(service: DatabaseService) -> None:
    page = service.fetch_cpc(limit=1)
    assert page["count"] <= 1
    if page["cpc"]:
        record = page["cpc"][0]
        assert service.get_cpc(record["id_cpc_table"]) == record


@requires_writable
def test_create_machine_matches_recent_legacy_native_row_profile(
    write_service: DatabaseService,
) -> None:
    # Select a native blank machine profile without copying device/customer data
    # into fixtures. Branch 0 is what recent native entries actually store.
    reference = write_service.fetch_rows("MASZYNA", filters=json.dumps({
        "AKTYWNA": "TAK", "SYNWP": 0, "ID_ODDZIAL": 0,
        "RODZAJ_US": "P\u0142atne", "MODEL": "",
    }), order_by="ID_MASZYNA_TABLE DESC", limit=1)["rows"]
    if not reference:
        pytest.skip("requires a recent native machine profile")
    app = create_app(write_service.settings, service=write_service)
    machine = None
    try:
        with TestClient(app) as client:
            response = client.post("/api/v1/machines", json={
                "marka": "KS ADAPTER LEGACY PROFILE TEST",
            })
        assert response.status_code == 201
        machine = response.json()
        assert machine["id_klient"] == 0
        assert machine["id_oddzial"] == 0
        assert machine["id_firma"] == 0
        assert machine["aktywna"] == "TAK"
        assert machine["kolorowa"] == "NIE"
        assert machine["grupa"] == "Druk"
        assert machine["rodzaj_us"] == "P\u0142atne"
        stored = write_service.fetch_rows("MASZYNA", filters=json.dumps({
            "ID_MASZYNA_TABLE": machine["id_maszyna_table"],
        }))["rows"][0]
        # The reference may have been assigned to an agreement since creation.
        assert stored["ID_UMOWACPC"] is None
        excluded = {"ID_MASZYNA_TABLE", "ID_MASZYNA", "ID_KLIENT",
                    "ID_UMOWACPC", "MARKA"}
        differences = [name for name in stored if name not in excluded
                       and stored[name] != reference[0][name]]
        # Fail with column names only, never expose native record values.
        assert not differences, differences
    finally:
        if machine is not None:
            delete_machine(write_service, machine["id_maszyna_table"])


@requires_writable
def test_create_machine_caller_can_override_legacy_flags(
    write_service: DatabaseService,
) -> None:
    created = write_service.create_machine({
        "marka": "KS ADAPTER OVERRIDE TEST", "id_oddzial": 1,
        "aktywna": "NIE", "kolorowa": "TAK", "rodzaj_us": "CPC", "grupa": "Komp",
    })
    try:
        assert created["id_oddzial"] == 1
        assert created["aktywna"] == "NIE"
        assert created["kolorowa"] == "TAK"
        assert created["rodzaj_us"] == "CPC"
        assert created["grupa"] == "Komp"
    finally:
        delete_machine(write_service, created["id_maszyna_table"])


@requires_writable
def test_create_machine_client_path_uses_legacy_defaults(
    write_service: DatabaseService,
) -> None:
    owner = write_service.create_client({"nazwa": "KS ADAPTER MACHINE PATH TEST"})
    machine = None
    try:
        app = create_app(write_service.settings, service=write_service)
        with TestClient(app) as client:
            response = client.post(f"/api/v1/machines/{owner['id_klient']}")
        assert response.status_code == 201
        machine = response.json()
        assert machine["id_klient"] == owner["id_klient"]
        assert machine["id_maszyna_table"]
        assert machine["id_maszyna"]
        assert machine["aktywna"] == "TAK"
        assert machine["grupa"] == "Druk"
        assert machine["id_oddzial"] == 0
    finally:
        if machine is not None:
            delete_machine(write_service, machine["id_maszyna_table"])
        delete_client(write_service, owner["id_klient_table"])
