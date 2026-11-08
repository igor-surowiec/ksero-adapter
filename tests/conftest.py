"""Shared pytest fixtures: fake service and an in-process API client."""

from __future__ import annotations

from typing import Any, Mapping

import pytest
from fastapi.testclient import TestClient

from ks_adapter.app import create_app
from ks_adapter.config import (
    ApiSettings,
    AppSettings,
    DatabaseSettings,
    ServerSettings,
)
from ks_adapter.errors import ColumnNotFound, TableNotFound
from ks_adapter.serialization import to_jsonable


def make_settings(**api_kwargs: Any) -> AppSettings:
    """Build application settings without touching a real database."""
    api_kwargs.setdefault("prefix", "/api/v1")
    return AppSettings(
        database=DatabaseSettings(path="C:/fake/baza.fdb", check_path=False),
        server=ServerSettings(),
        api=ApiSettings(**api_kwargs),
    )


class FakeService:
    """In-memory stand-in for :class:`ks_adapter.service.DatabaseService`."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.tables = [
            {"name": "APPUSER", "kind": "table", "column_count": 2},
            {"name": "V_USERS", "kind": "view", "column_count": 1},
        ]

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "database": {
                "dsn": "C:/fake/baza.fdb",
                "charset": "WIN1250",
                "server_version": "Firebird 2.5",
            },
            "pool": {"created": 1, "idle": 1, "capacity": 5},
            "latency_ms": 1.5,
        }

    def list_tables(self) -> list[dict[str, Any]]:
        return self.tables

    def describe_table(self, table: str) -> dict[str, Any]:
        if table.upper() != "APPUSER":
            raise TableNotFound(f"Table or view '{table}' does not exist")
        return {
            "name": "APPUSER",
            "kind": "table",
            "column_count": 2,
            "columns": [
                {"name": "ID", "position": 0, "type": "INTEGER", "nullable": False},
                {"name": "NAME", "position": 1, "type": "VARCHAR(50)", "nullable": True},
            ],
        }

    def refresh_schema(self) -> int:
        self.calls.append({"action": "refresh"})
        return len(self.tables)

    def fetch_rows(
        self,
        table: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        filters: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "action": "fetch_rows",
                "table": table,
                "limit": limit,
                "offset": offset,
                "order_by": order_by,
                "filters": filters,
            }
        )
        if table.upper() == "MISSING":
            raise TableNotFound(f"Table or view '{table}' does not exist")
        if filters and "BAD" in filters:
            raise ColumnNotFound("Unknown column 'BAD'")
        return {
            "table": table,
            "columns": ["ID", "NAME"],
            "rows": [{"ID": offset + 1, "NAME": "ACME"}],
            "row_count": 1,
            "total": 10,
            "limit": limit or 50,
            "offset": offset,
        }

    def fetch_clients(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "action": "fetch_clients",
                "limit": limit,
                "offset": offset,
                "search": search,
            }
        )
        return {
            "total": 12,
            "count": 1,
            "limit": limit or 50,
            "offset": offset,
            "clients": [
                {
                    "id_klient_table": offset + 1,
                    "id_klient": offset + 1,
                    "nazwa": "ACME",
                    "nip": "1234567890",
                }
            ],
        }

    def create_client(self, values: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": "create_client", "values": dict(values)})
        row: dict[str, Any] = {
            "id_klient_table": 1001,
            "id_klient": 42,
            "nazwa": values.get("nazwa"),
            "nip": None,
            "ostatnio": None,
        }
        for key, value in values.items():
            row[key] = value
        return row

    def update_client(
        self, id_klient: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({
            "action": "update_client",
            "id_klient": id_klient,
            "values": dict(values),
        })
        return {
            "id_klient_table": 1001, "id_klient": id_klient,
            "nazwa": "ACME", **values,
        }

    def delete_client(self, id_klient: int) -> None:
        self.calls.append({"action": "delete_client", "id_klient": id_klient})

    def create_machine(self, values: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": "create_machine", "values": dict(values)})
        return {
            "id_maszyna_table": 2001,
            "id_maszyna": 84,
            "id_klient": values.get("id_klient", 0),
            "id_oddzial": 1,
            "marka": values.get("marka"),
            "serial": values.get("serial"),
        }

    def fetch_agreements(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "action": "fetch_agreements",
                "limit": limit,
                "offset": offset,
                "search": search,
            }
        )
        return {
            "total": 4,
            "count": 1,
            "limit": limit or 50,
            "offset": offset,
            "agreements": [
                {
                    "id_umowacpc_table": offset + 1,
                    "id_umowacpc": offset + 1,
                    "umowa": "CPC/2024/001",
                    "id_klient": 7,
                }
            ],
        }

    def create_agreement(self, values: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": "create_agreement", "values": dict(values)})
        return to_jsonable({"id_umowacpc_table": 3001, "id_umowacpc": 1, **values})

    def fetch_machines(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "action": "fetch_machines",
                "limit": limit,
                "offset": offset,
                "search": search,
            }
        )
        return {
            "total": 6,
            "count": 1,
            "limit": limit or 50,
            "offset": offset,
            "machines": [
                {
                    "id_maszyna_table": offset + 1,
                    "id_maszyna": offset + 1,
                    "marka": "KONICA",
                    "serial": "SN-0001",
                    "id_klient": 7,
                }
            ],
        }

    def fetch_orders(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "action": "fetch_orders",
                "limit": limit,
                "offset": offset,
                "search": search,
            }
        )
        return {
            "total": 9,
            "count": 1,
            "limit": limit or 50,
            "offset": offset,
            "orders": [
                {
                    "id_zlecenie_table": offset + 1,
                    "id_zlecenie": offset + 1,
                    "nazwa": "ACME",
                    "stan": "O",
                    "id_klient": 7,
                }
            ],
        }

    def fetch_invoices(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "action": "fetch_invoices",
                "limit": limit,
                "offset": offset,
                "search": search,
            }
        )
        return {
            "total": 3,
            "count": 1,
            "limit": limit or 50,
            "offset": offset,
            "invoices": [
                {
                    "id_faktura_table": offset + 1,
                    "numer": "FV/2026/11/001",
                    "nazwa": "ACME",
                    "suma_brutto": 1230.0,
                    "id_klient": 7,
                }
            ],
        }

    def run_query(
        self, sql: str, *, limit: int | None = None, parameters: Any = None
    ) -> dict[str, Any]:
        self.calls.append(
            {"action": "query", "sql": sql, "limit": limit, "parameters": parameters}
        )
        return {
            "columns": ["ONE"],
            "rows": [{"ONE": 1}],
            "row_count": 1,
            "truncated": False,
        }


@pytest.fixture
def fake_service() -> FakeService:
    return FakeService()


@pytest.fixture
def settings() -> AppSettings:
    return make_settings()


@pytest.fixture
def client(settings: AppSettings, fake_service: FakeService) -> TestClient:
    app = create_app(settings, service=fake_service)
    with TestClient(app) as test_client:
        yield test_client
