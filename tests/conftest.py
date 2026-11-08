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

    def update_machine(
        self, id_maszyna: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({
            "action": "update_machine", "id_maszyna": id_maszyna,
            "values": dict(values),
        })
        return to_jsonable({
            "id_maszyna_table": 2001, "id_maszyna": id_maszyna, **values,
        })

    def fetch_cpc(
        self, *, limit: int | None = None, offset: int = 0,
        search: str | None = None, filters: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append({"action": "fetch_cpc", "limit": limit, "offset": offset,
                           "search": search, "filters": filters})
        return {"total": 1, "count": 1, "limit": limit or 50, "offset": offset,
                "cpc": [{"id_cpc_table": 101, "rok": 2026, "miesiac": 11}]}

    def get_cpc(self, id_cpc_table: int) -> dict[str, Any]:
        self.calls.append({"action": "get_cpc", "id_cpc_table": id_cpc_table})
        return {"id_cpc_table": id_cpc_table, "rok": 2026, "miesiac": 11}

    def create_cpc(self, values: Mapping[str, Any]) -> dict[str, Any]:
        self.calls.append({"action": "create_cpc", "values": dict(values)})
        return to_jsonable({"id_cpc_table": 101, **values})

    def update_cpc(
        self, id_cpc_table: int, values: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.calls.append({"action": "update_cpc", "id_cpc_table": id_cpc_table,
                           "values": dict(values)})
        return to_jsonable({"id_cpc_table": id_cpc_table, **values})

    def delete_cpc(self, id_cpc_table: int) -> None:
        self.calls.append({"action": "delete_cpc", "id_cpc_table": id_cpc_table})

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

    def update_agreement(
        self, id_umowacpc: int, values: Mapping[str, Any]
    ) -> dict[str, Any]:
        self.calls.append({
            "action": "update_agreement", "id_umowacpc": id_umowacpc,
            "values": dict(values),
        })
        return to_jsonable({"id_umowacpc": id_umowacpc, **values})

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
