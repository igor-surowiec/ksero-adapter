"""Tests for catalog type mapping and the schema cache."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from ks_adapter import schema as schema_module
from ks_adapter.errors import TableNotFound
from ks_adapter.schema import SchemaCache, describe_type

TABLE_ROWS = [
    ("APPUSER", 0, None),
    ("V_USERS", 1, "Registered users"),
]

COLUMN_ROWS = [
    ("APPUSER", "ID", 0, 1, None, 8, 0, 4, None, 0, None),
    ("APPUSER", "NAME", 1, 0, "DEFAULT 'x'", 37, 0, 100, None, 0, "WIN1250"),
    ("V_USERS", "ID", 0, 1, None, 8, 0, 4, None, 0, None),
]

TABLES_DESCRIPTION = [("RELATION_NAME",), ("RELATION_TYPE",), ("DESCRIPTION",)]
COLUMNS_DESCRIPTION = [
    ("RELATION_NAME",),
    ("FIELD_NAME",),
    ("FIELD_POSITION",),
    ("NULL_FLAG",),
    ("DEFAULT_SOURCE",),
    ("FIELD_TYPE",),
    ("FIELD_SUB_TYPE",),
    ("FIELD_LENGTH",),
    ("FIELD_PRECISION",),
    ("FIELD_SCALE",),
    ("CHARACTER_SET_NAME",),
]


def test_describe_type_plain_types() -> None:
    assert describe_type(7, 0, 2, None, 0) == "SMALLINT"
    assert describe_type(8, 0, 4, None, 0) == "INTEGER"
    assert describe_type(16, 0, 8, None, 0) == "BIGINT"
    assert describe_type(12, 0, 4, None, 0) == "DATE"
    assert describe_type(13, 0, 4, None, 0) == "TIME"
    assert describe_type(35, 0, 8, None, 0) == "TIMESTAMP"
    assert describe_type(27, 0, 8, None, 0) == "DOUBLE PRECISION"


def test_describe_type_numerics() -> None:
    assert describe_type(8, 1, 4, 15, -2) == "NUMERIC(15,2)"
    assert describe_type(8, 2, 4, 15, -2) == "DECIMAL(15,2)"
    assert describe_type(16, 1, 8, 18, -4) == "NUMERIC(18,4)"
    assert describe_type(7, 0, 2, 5, -2) == "NUMERIC(5,2)"


def test_describe_type_strings_respect_charset_width() -> None:
    assert describe_type(37, 0, 40, None, 0, "WIN1250") == "VARCHAR(40)"
    assert describe_type(37, 0, 40, None, 0, "UTF8") == "VARCHAR(10)"
    assert describe_type(14, 0, 3, None, 0, None) == "CHAR(3)"


def test_describe_type_blobs() -> None:
    assert describe_type(261, 1, 8, None, 0) == "BLOB SUB_TYPE TEXT"
    assert describe_type(261, 0, 8, None, 0) == "BLOB"


def test_describe_type_unknown() -> None:
    assert describe_type(None, 0, 0, None, 0) == "UNKNOWN"
    assert describe_type(999, 0, 0, None, 0) == "UNKNOWN(999)"


class _FakeCursor:
    def __init__(self, script: dict[str, tuple[Any, Any]]) -> None:
        self._script = script
        self.description: Any = None
        self._rows: Any = []

    def execute(self, sql: str, params: Any = None) -> None:
        try:
            self.description, self._rows = self._script[sql]
        except KeyError:  # pragma: no cover - guards against SQL drift
            raise AssertionError(f"Unexpected SQL: {sql}") from None

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def close(self) -> None:
        return None


class _FakePool:
    def __init__(self) -> None:
        self.sessions = 0

    @property
    def script(self) -> dict[str, tuple[Any, Any]]:
        return {
            schema_module._TABLES_SQL: (TABLES_DESCRIPTION, TABLE_ROWS),
            schema_module._COLUMNS_SQL: (COLUMNS_DESCRIPTION, COLUMN_ROWS),
        }

    @contextmanager
    def session(self) -> Iterator[Any]:
        self.sessions += 1
        yield _FakeConnection(_FakeCursor(self.script))


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _FakeCursor:
        return self._cursor

    def close(self) -> None:
        return None


def test_schema_cache_loads_tables_and_columns() -> None:
    pool = _FakePool()
    cache = SchemaCache(pool, ttl=60)

    tables = cache.tables()
    assert list(tables) == ["APPUSER", "V_USERS"]

    appuser = cache.get("APPUSER")
    assert appuser.kind == "table"
    assert len(appuser.columns) == 2
    assert [c.type_name for c in appuser.columns] == ["INTEGER", "VARCHAR(100)"]
    assert appuser.columns[0].nullable is False
    assert appuser.columns[1].nullable is True
    assert appuser.columns[1].default == "DEFAULT 'x'"
    assert appuser.columns[1].charset == "WIN1250"
    assert appuser.column_map == {"ID": "ID", "NAME": "NAME"}

    view = cache.get("v_users")
    assert view.kind == "view"
    assert view.description == "Registered users"


def test_schema_cache_get_unknown_table() -> None:
    cache = SchemaCache(_FakePool(), ttl=60)
    with pytest.raises(TableNotFound):
        cache.get("NOPE")


def test_schema_cache_is_reused_and_can_be_invalidated() -> None:
    pool = _FakePool()
    cache = SchemaCache(pool, ttl=60)
    cache.tables()
    cache.tables()
    assert pool.sessions == 1

    cache.invalidate()
    cache.tables()
    assert pool.sessions == 2


def test_schema_cache_expires_after_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = {"now": 100.0}
    monkeypatch.setattr(schema_module.time, "monotonic", lambda: clock["now"])
    pool = _FakePool()
    cache = SchemaCache(pool, ttl=10)

    cache.tables()
    clock["now"] += 5
    cache.tables()
    assert pool.sessions == 1

    clock["now"] += 6
    cache.tables()
    assert pool.sessions == 2


def test_schema_cache_serialises_table_metadata() -> None:
    cache = SchemaCache(_FakePool(), ttl=60)
    summary = cache.tables()["APPUSER"].to_dict()
    assert summary == {"name": "APPUSER", "kind": "table", "column_count": 2}

    detail = cache.tables()["APPUSER"].to_dict(include_columns=True)
    assert detail["columns"][0]["name"] == "ID"
    assert detail["columns"][1]["type"] == "VARCHAR(100)"
