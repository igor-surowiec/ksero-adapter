"""Settlement synchronization uses exact identities and a single primary write."""

from __future__ import annotations

from dataclasses import replace
from datetime import date
import re
from typing import Any

import pytest
from fastapi.testclient import TestClient

from adapter.app import create_app
from adapter.config import DatabaseSettings
from adapter.errors import (
    DatabaseUnavailable, InvalidRequest, RecordConflict, RecordNotFound, WritesDisabled,
)
from adapter.schema import ColumnInfo, TableInfo
from adapter.service import DatabaseService
from adapter.service.cpc_settlement import CPC_COLUMNS, CPC_UPDATE_COLUMNS
from adapter.service.cpc_sync import CPC_MACHINE_FIELD_MAP
from adapter.service.machines_database import DATABASE_MACHINE_COLUMNS

from .conftest import FakeService, make_settings
from .test_service import _Pool, _StubSchema

URL = "/api/v1/cpc-settlement/machines/9/sync"
DATES = {"start_date": date(2026, 11, 1), "end_date": date(2026, 11, 30)}
PARAMS = {key: value.isoformat() for key, value in DATES.items()}
SOURCE = {
    "DATA_LICZNIKA": "2026-11-15",
    "MODEL": "Test model", "ID_NR_SERYJNY": "SN-TEST",
    "LICZNIK_MONO": 1500, "LICZNIK_KOLOR": 250, "LICZNIK_SKAN": 75,
    "LICZ_M_OSTATN_ROZL": 1000, "LICZ_K_OSTATN_ROZL": 100, "UWAGI": " notes ",
}
MACHINE = TableInfo("MASZYNA", "table", None, tuple(
    ColumnInfo(name, i, "VARCHAR(100)", True)
    for i, name in enumerate(("ID_MASZYNA", "MODEL", "SERIAL", "ID_UMOWACPC"))
))
CPC = TableInfo("CPC", "table", None, tuple(
    ColumnInfo(name, i, "INTEGER", True)
    for i, name in enumerate(("ID_CPC_TABLE", "ID_MASZYNA", "ID_KLIENT",
                             "ID_UMOWACPC", "ROK", "MIESIAC", "OPLATA_SUMA",
                             *CPC_MACHINE_FIELD_MAP.values()))
))


def make_sync_service(
    *, identity: list[tuple[Any, ...]] | None = None,
    agreements: list[tuple[int]] | None = None,
    source_total: int = 1, source: dict[str, Any] | None = None,
) -> tuple[DatabaseService, _Pool, _Pool]:
    source = dict(SOURCE) if source is None else source
    source_names = [name for name in DATABASE_MACHINE_COLUMNS if name in source]
    selected = [name for name in CPC_COLUMNS if name in CPC.column_map]
    result = {"ID_CPC_TABLE": 101, "ID_MASZYNA": 9, "ID_KLIENT": 7,
              "ID_UMOWACPC": 3, "ROK": 2027, "MIESIAC": 2, "LICZNIK_MONO_END": 1500}
    primary = _Pool([
        (None, [("Test model", "SN-TEST", 3)] if identity is None else identity),
        (None, [(7,)] if agreements is None else agreements),
        (None, [(date(2027, 2, 3),)]),
        (None, [tuple(result.get(name) for name in selected)]),
    ])
    secondary = _Pool([
        (None, [(source_total,)]),
        (None, [tuple(source[name] for name in source_names)] if source_total else []),
    ])
    settings = replace(
        make_settings(allow_writes=True, max_limit=1, default_limit=1),
        machines_database=DatabaseSettings(path="secondary.fdb", check_path=False),
    )
    service = DatabaseService(settings, pool=primary, machines_pool=secondary)
    service.schema = _StubSchema(MACHINE, CPC, TableInfo(
        "UMOWACPC", "table", None, (
            ColumnInfo("ID_UMOWACPC", 0, "INTEGER", False),
            ColumnInfo("ID_KLIENT", 1, "INTEGER", False),
        ),
    ))
    assert service._machines_database_service is not None
    service._machines_database_service.schema = _StubSchema(TableInfo(
        "MASZYNY", "table", None, tuple(
            ColumnInfo(name, i, "INTEGER", True)
            for i, name in enumerate(source_names)
        ),
    ))
    return service, primary, secondary


def test_sync_uses_exact_source_match_and_curated_insert() -> None:
    service, primary, secondary = make_sync_service()
    record = service.sync_cpc_from_machine(9, **DATES)
    assert record["id_cpc_table"] == 101
    assert record["id_maszyna"] == 9
    assert primary.executed[:3] == [
        ('SELECT FIRST 2 "MODEL", "SERIAL", "ID_UMOWACPC" FROM "MASZYNA" '
         'WHERE "ID_MASZYNA" = ?', [9]),
        ('SELECT FIRST 2 "ID_KLIENT" FROM "UMOWACPC" '
         'WHERE "ID_UMOWACPC" = ?', [3]),
        ("SELECT CURRENT_DATE FROM RDB$DATABASE", None),
    ]
    statement, params = primary.executed[-1]
    assert statement.startswith('INSERT INTO "CPC" (')
    names = re.findall(r'"([^"\n]+)"', statement.split("VALUES")[0])[1:]
    inserted = dict(zip(names, params))
    assert inserted == {
        "ID_KLIENT": 7, "ID_MASZYNA": 9, "ID_UMOWACPC": 3,
        "LICZNIK_MONO_START": 1000, "LICZNIK_KOLOR_START": 100,
        "LICZNIK_MONO_END": 1500, "LICZNIK_KOLOR_END": 250,
        "LICZNIK_SKAN_END": 75, "UWAGI": "notes", "ROK": 2027,
        "MIESIAC": 2, "OPLATA_SUMA": 0,
    }
    assert secondary.executed[0] == (
        'SELECT COUNT(*) FROM "MASZYNY" WHERE "MODEL" = ? AND "ID_NR_SERYJNY" = ?',
        ["Test model", "SN-TEST"],
    )
    assert not any('FROM "CPC"' in sql or sql.startswith("UPDATE")
                   for sql, _ in primary.executed)
    assert primary.committed == 1 and primary.rolled_back == 0
    assert secondary.committed == 0


@pytest.mark.parametrize("kwargs, error", [
    ({"identity": []}, RecordNotFound),
    ({"identity": [("M", "S", 3), ("M", "S", 3)]}, RecordConflict),
    ({"identity": [(None, "S", 3)]}, InvalidRequest),
    ({"identity": [("M", " ", 3)]}, InvalidRequest),
    ({"agreements": []}, RecordNotFound),
    ({"agreements": [(1,), (2,)]}, RecordConflict),
    ({"identity": [("M", "S", None)]}, InvalidRequest),
    ({"identity": [("M", "S", 0)]}, InvalidRequest),
    ({"source_total": 0}, RecordNotFound),
    ({"source_total": 2}, RecordConflict),
    ({"source": {"MODEL": "M", "ID_NR_SERYJNY": "S",
                 "DATA_LICZNIKA": "2026-11-15"}}, InvalidRequest),
    ({"source": {**SOURCE, "LICZNIK_MONO": -1}}, InvalidRequest),
    ({"source": {**SOURCE, "LICZNIK_MONO": True}}, InvalidRequest),
    ({"source": {**SOURCE, "UWAGI": "x" * 501}}, InvalidRequest),
])
def test_sync_failures_roll_back_without_insert(
    kwargs: dict[str, Any], error: type[Exception],
) -> None:
    service, primary, secondary = make_sync_service(**kwargs)
    with pytest.raises(error):
        service.sync_cpc_from_machine(9, **DATES)
    assert primary.committed == 0 and primary.rolled_back == 1
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in primary.executed)
    assert secondary.committed == 0


def test_sync_uses_defaults_for_missing_values_and_copies_zero() -> None:
    service, primary, _ = make_sync_service(source={
        "MODEL": "M", "ID_NR_SERYJNY": "S", "LICZNIK_MONO": 0,
        "LICZNIK_KOLOR": None, "UWAGI": " ", "DATA_LICZNIKA": "2026-11-15",
    })
    service.sync_cpc_from_machine(9, **DATES)
    statement, params = primary.executed[-1]
    names = re.findall(r'"([^"\n]+)"', statement.split("VALUES")[0])[1:]
    inserted = dict(zip(names, params))
    assert inserted["LICZNIK_MONO_END"] == 0
    assert "LICZNIK_KOLOR_END" not in inserted
    assert inserted["UWAGI"] == ""



def test_sync_serialization_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, primary, _ = make_sync_service()

    def fail(*args: Any) -> None:
        raise ValueError("serialization failed")

    monkeypatch.setattr(service, "_serialize_row", fail)
    with pytest.raises(ValueError, match="serialization failed"):
        service.sync_cpc_from_machine(9, **DATES)
    assert primary.committed == 0 and primary.rolled_back == 1


def test_sync_source_database_failure_rolls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, primary, _ = make_sync_service()

    def fail(**kwargs: Any) -> None:
        raise DatabaseUnavailable("secondary offline")

    monkeypatch.setattr(service, "fetch_database_machines", fail)
    with pytest.raises(DatabaseUnavailable):
        service.sync_cpc_from_machine(9, **DATES)
    assert primary.committed == 0 and primary.rolled_back == 1
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in primary.executed)


def test_sync_write_gate_and_optional_configuration() -> None:
    service, primary, secondary = make_sync_service()
    service.settings = replace(service.settings, api=replace(service.settings.api,
                                                           allow_writes=False))
    with pytest.raises(WritesDisabled):
        service.sync_cpc_from_machine(9, **DATES)
    assert primary.executed == secondary.executed == []
    service = DatabaseService(make_settings(allow_writes=True), pool=primary)
    with pytest.raises(DatabaseUnavailable):
        service.sync_cpc_from_machine(9, **DATES)
    assert primary.executed == []


def test_sync_mapping_only_targets_writable_settlement_fields() -> None:
    assert set(CPC_MACHINE_FIELD_MAP.values()) <= set(CPC_UPDATE_COLUMNS)


def test_sync_http_contract_and_authentication() -> None:
    fake = FakeService()
    with TestClient(create_app(make_settings(api_key="secret"), fake)) as client:
        assert client.post(URL).status_code == 401
        response = client.post(URL, headers={"X-API-Key": "secret"}, params=PARAMS)
        assert response.status_code == 201
        assert response.json()["id_maszyna"] == 9
        assert fake.calls == [{
            "action": "sync_cpc_from_machine", "id_maszyna": 9, **DATES,
        }]
        assert client.patch(URL, headers={"X-API-Key": "secret"},
                            params=PARAMS).status_code == 405
        for identity in ("0", "-1", "invalid"):
            assert client.post(URL.replace("/9/", f"/{identity}/"), headers={
                "X-API-Key": "secret",
            }, params=PARAMS).status_code == 422


@pytest.mark.parametrize("start, end", [
    (date(2026, 11, 15), date(2026, 11, 30)),
    (date(2026, 11, 1), date(2026, 11, 15)),
    (date(2026, 11, 15), date(2026, 11, 15)),
])
def test_sync_accepts_inclusive_date_boundaries(start: date, end: date) -> None:
    service, primary, _ = make_sync_service()
    service.sync_cpc_from_machine(9, start_date=start, end_date=end)
    assert primary.committed == 1


@pytest.mark.parametrize("reading_date", [
    "2026-10-31", "2026-12-01", None, "", "not-a-date", "2026-02-30", 123,
])
def test_sync_rejects_ineligible_reading_date_without_writing(
    reading_date: Any,
) -> None:
    service, primary, _ = make_sync_service(source={
        **SOURCE, "DATA_LICZNIKA": reading_date,
    })
    with pytest.raises(InvalidRequest, match="data_licznika"):
        service.sync_cpc_from_machine(9, **DATES)
    assert primary.committed == 0 and primary.rolled_back == 1
    assert not any(sql.startswith(("INSERT", "UPDATE")) for sql, _ in primary.executed)


def test_sync_rejects_missing_reading_date_without_writing() -> None:
    source = {key: value for key, value in SOURCE.items() if key != "DATA_LICZNIKA"}
    service, primary, _ = make_sync_service(source=source)
    with pytest.raises(InvalidRequest, match="data_licznika"):
        service.sync_cpc_from_machine(9, **DATES)
    assert primary.committed == 0 and primary.rolled_back == 1


def test_sync_rejects_reversed_range_before_database_access() -> None:
    service, primary, secondary = make_sync_service()
    with pytest.raises(InvalidRequest, match="start_date"):
        service.sync_cpc_from_machine(
            9, start_date=DATES["end_date"], end_date=DATES["start_date"],
        )
    assert primary.executed == secondary.executed == []
    assert primary.committed == 0


@pytest.mark.parametrize("params", [
    {}, {"start_date": "2026-11-01"}, {"end_date": "2026-11-30"},
    {"start_date": "not-a-date", "end_date": "2026-11-30"},
    {"start_date": "2026-11-01", "end_date": "2026-02-30"},
])
def test_sync_requires_valid_dates_in_http_query(params: dict[str, str]) -> None:
    fake = FakeService()
    with TestClient(create_app(make_settings(), fake)) as client:
        assert client.post(URL, params=params).status_code == 422
        operation = client.get("/openapi.json").json()["paths"][
            "/api/v1/cpc-settlement/machines/{id_maszyna}/sync"
        ]["post"]
        parameters = {p["name"]: p for p in operation["parameters"]}
        for name in ("start_date", "end_date"):
            assert parameters[name]["required"] is True
            assert parameters[name]["schema"]["format"] == "date"
    assert fake.calls == []


def test_sync_reversed_date_range_http_error() -> None:
    service, primary, _ = make_sync_service()
    with TestClient(create_app(service.settings, service)) as client:
        response = client.post(URL, params={
            "start_date": "2026-11-30", "end_date": "2026-11-01",
        })
    assert response.status_code == 400
    assert primary.executed == []


@pytest.mark.parametrize("error, status", [
    (WritesDisabled("disabled"), 403), (RecordNotFound("missing"), 404),
    (RecordConflict("ambiguous"), 409), (DatabaseUnavailable("offline"), 503),
    (InvalidRequest("invalid readings"), 400),
])
def test_sync_http_errors(error: Exception, status: int) -> None:
    class FailingService(FakeService):
        def sync_cpc_from_machine(
            self, id_maszyna: int, *, start_date: date, end_date: date,
        ) -> dict[str, Any]:
            raise error

    with TestClient(create_app(make_settings(), FailingService())) as client:
        assert client.post(URL, params=PARAMS).status_code == status
