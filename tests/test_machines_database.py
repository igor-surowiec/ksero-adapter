"""Machine-database HTTP contract and independent pool coverage."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from fastapi.testclient import TestClient

from adapter.app import create_app
from adapter.config import DatabaseSettings
from adapter.errors import DatabaseUnavailable
from adapter.schema import ColumnInfo, TableInfo
from adapter.schemas.machines_database import DatabaseMachine
from adapter.service import DatabaseService
from adapter.service.machines_database import (
    DATABASE_MACHINE_COLUMNS,
    DATABASE_MACHINE_SEARCH_COLUMNS,
)
from adapter.sql import MAX_SEARCH_COLUMNS

from .conftest import FakeService, make_settings
from .test_service import _Pool, _StubSchema

URL = "/api/v1/machines-database/maszyny"


def test_secondary_database_http_contract() -> None:
    fake = FakeService()
    with TestClient(create_app(make_settings(api_key="secret"), fake)) as client:
        assert client.get(URL).status_code == 401
        response = client.get(
            URL,
            headers={"X-API-Key": "secret"},
            params={"limit": 5, "offset": 2, "search": "test",
                    "filters": '{"id_klient": 7}'},
        )
        assert response.status_code == 200
        assert response.json()["machines"][0]["id_tbl_maszyny"] == 1
        assert fake.calls == [{
            "action": "fetch_database_machines", "limit": 5, "offset": 2,
            "search": "test", "filters": '{"id_klient": 7}',
        }]
        schema = client.get("/openapi.json").json()
        assert schema["paths"][URL]["get"]["tags"] == ["MACHINES_DATABASE"]
        assert list(schema["paths"][URL]) == ["get"]
        assert '"machines-database", "MACHINES_DATABASE"' in client.get(
            "/api/v1"
        ).text


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 1001}, {"offset": -1}, {"search": "x" * 101},
])
def test_secondary_database_http_validation(params: dict[str, object]) -> None:
    fake = FakeService()
    with TestClient(create_app(make_settings(), fake)) as client:
        assert client.get(URL, params=params).status_code == 422
    assert not fake.calls


def test_secondary_database_is_optional_and_reports_unavailable() -> None:
    primary = _Pool([])
    service = DatabaseService(make_settings(), pool=primary)
    with pytest.raises(DatabaseUnavailable, match="not configured"):
        service.fetch_database_machines()
    with TestClient(create_app(make_settings(), service)) as client:
        response = client.get(URL)
        assert response.status_code == 503
        assert response.json()["error"] == "DatabaseUnavailable"
    assert primary.executed == []


def test_secondary_database_queries_are_isolated_and_parameterized() -> None:
    primary = _Pool([])
    secondary = _Pool([
        (None, [(1,)]),
        (None, [(11, 7, "Test printer", date(2026, 1, 2))]),
    ])
    settings = replace(
        make_settings(allow_writes=True),
        machines_database=DatabaseSettings(path="secondary.fdb", check_path=False),
    )
    service = DatabaseService(settings, pool=primary, machines_pool=secondary)
    database = service._machines_database_service
    assert database is not None
    assert database.pool is secondary
    assert database.schema is not service.schema
    assert database.settings.database == settings.machines_database
    assert database.settings.api.allow_writes is False
    database.schema = _StubSchema(TableInfo(
        "MASZYNY", "table", None, (
            ColumnInfo("ID_TBL_MASZYNY", 0, "INTEGER", False),
            ColumnInfo("ID_KLIENT", 1, "INTEGER", True),
            ColumnInfo("MARKA", 2, "VARCHAR(50)", True),
            ColumnInfo("DATA_INSTALACJI", 3, "DATE", True),
        ),
    ))
    page = service.fetch_database_machines(
        limit=5, offset=2, search="test%", filters='{"id_klient": 7}'
    )
    assert page == {
        "total": 1, "count": 1, "limit": 5, "offset": 2,
        "machines": [{"id_tbl_maszyny": 11, "id_klient": 7,
                      "marka": "Test printer", "data_instalacji": "2026-01-02"}],
    }
    count, select = secondary.executed
    assert count[0].startswith('SELECT COUNT(*) FROM "MASZYNY" WHERE ')
    assert '"ID_KLIENT" = ?' in count[0]
    assert "test%" not in count[0]
    assert count[1] == ["%test\\%%", 7]
    assert select == (
        'SELECT "ID_TBL_MASZYNY", "ID_KLIENT", "MARKA", "DATA_INSTALACJI" '
        'FROM "MASZYNY"' + count[0].split('FROM "MASZYNY"', 1)[1]
        + ' ORDER BY "ID_TBL_MASZYNY" ROWS 3 TO 7',
        count[1],
    )
    assert primary.executed == []
    assert secondary.committed == 0


def test_secondary_database_pools_close(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[str] = []
    primary, secondary = _Pool([]), _Pool([])
    monkeypatch.setattr(primary, "close", lambda: closed.append("primary"))
    monkeypatch.setattr(secondary, "close", lambda: closed.append("secondary"))
    service = DatabaseService(
        replace(make_settings(), machines_database=DatabaseSettings(
            path="secondary.fdb", check_path=False,
        )),
        pool=primary, machines_pool=secondary,
    )
    service.close()
    assert closed == ["secondary", "primary"]


def test_secondary_database_projection_matches_model_and_search_budget() -> None:
    assert {name.lower() for name in DATABASE_MACHINE_COLUMNS} == set(
        DatabaseMachine.model_fields
    )
    assert len(DATABASE_MACHINE_SEARCH_COLUMNS) <= MAX_SEARCH_COLUMNS
    assert set(DATABASE_MACHINE_SEARCH_COLUMNS) <= set(DATABASE_MACHINE_COLUMNS)
