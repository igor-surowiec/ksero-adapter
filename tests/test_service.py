"""Service-level tests using a scripted fake connection pool."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator

import pytest

from ks_adapter.config import ApiSettings, AppSettings, DatabaseSettings, ServerSettings
from ks_adapter.errors import (
    ColumnNotFound,
    InvalidRequest,
    QueryNotAllowed,
    RecordConflict,
    RecordNotFound,
    TableNotFound,
    WritesDisabled,
)
from ks_adapter.schema import ColumnInfo, TableInfo
from ks_adapter.service import DatabaseService

APPUSER = TableInfo(
    name="APPUSER",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID", 0, "INTEGER", False),
        ColumnInfo("NAME", 1, "VARCHAR(50)", True),
    ),
)

KLIENT = TableInfo(
    name="KLIENT",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID_KLIENT_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_KLIENT", 1, "INTEGER", False),
        ColumnInfo("NAZWA", 2, "VARCHAR(500)", True),
        ColumnInfo("NIP", 3, "VARCHAR(20)", True),
        ColumnInfo("OSTATNIO", 4, "DATE", True),
    ),
)

UMOWACPC = TableInfo(
    name="UMOWACPC",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID_UMOWACPC_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_UMOWACPC", 1, "INTEGER", False),
        ColumnInfo("UMOWA", 2, "VARCHAR(100)", True),
        ColumnInfo("OPIEKUN", 3, "VARCHAR(100)", True),
        ColumnInfo("U_START", 4, "DATE", True),
        ColumnInfo("KOSZTY", 5, "DECIMAL(10,4)", True),
    ),
)

MASZYNA = TableInfo(
    name="MASZYNA",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_MASZYNA", 1, "INTEGER", False),
        ColumnInfo("MARKA", 2, "VARCHAR(100)", True),
        ColumnInfo("SERIAL", 3, "VARCHAR(100)", True),
        ColumnInfo("INSTALACJA", 4, "DATE", True),
        ColumnInfo("TECHNIK", 5, "VARCHAR(100)", True),
        ColumnInfo("KOSZTY", 6, "DECIMAL(10,4)", True),
    ),
)


ZLECENIE = TableInfo(
    name="ZLECENIE",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID_ZLECENIE_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_ZLECENIE", 1, "INTEGER", False),
        ColumnInfo("STAN", 2, "VARCHAR(3)", True),
        ColumnInfo("NAZWA", 3, "VARCHAR(500)", True),
        ColumnInfo("MARKA", 4, "VARCHAR(100)", True),
        ColumnInfo("DATA", 5, "DATE", True),
        ColumnInfo("TECHNIK", 6, "VARCHAR(100)", True),
        ColumnInfo("BRUTTO", 7, "DECIMAL(10,4)", True),
    ),
)

FAKTURA = TableInfo(
    name="FAKTURA",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID_FAKTURA_TABLE", 0, "INTEGER", False),
        ColumnInfo("NUMER", 1, "VARCHAR(30)", True),
        ColumnInfo("NAZWA", 2, "VARCHAR(500)", True),
        ColumnInfo("DATA_WYST", 3, "DATE", True),
        ColumnInfo("STAN", 4, "VARCHAR(5)", True),
        ColumnInfo("SUMA_BRUTTO", 5, "DECIMAL(10,4)", True),
    ),
)


def make_settings(**api_kwargs: Any) -> AppSettings:
    return AppSettings(
        database=DatabaseSettings(path="C:/fake/baza.fdb", check_path=False),
        server=ServerSettings(),
        api=ApiSettings(**api_kwargs),
    )


def make_service(pool: Any, **api_kwargs: Any) -> DatabaseService:
    service = DatabaseService(make_settings(**api_kwargs), pool=pool)
    service.schema = _StubSchema(APPUSER)
    return service


def make_projection_service(
    pool: Any, *infos: TableInfo, **api_kwargs: Any
) -> DatabaseService:
    """Service wired to a stub schema holding the given tables (KLIENT by default)."""
    service = DatabaseService(make_settings(**api_kwargs), pool=pool)
    service.schema = _StubSchema(*(infos or (KLIENT,)))
    return service


class _StubSchema:
    def __init__(self, *infos: TableInfo) -> None:
        self._infos = {info.name: info for info in infos}
        self.invalidated = 0

    def tables(self) -> dict[str, TableInfo]:
        return dict(self._infos)

    def get(self, name: str) -> TableInfo:
        for key, info in self._infos.items():
            if key.upper() == name.strip().upper():
                return info
        raise TableNotFound(f"Table or view '{name}' does not exist")

    def invalidate(self) -> None:
        self.invalidated += 1


class _Cursor:
    def __init__(self, responses: list[tuple[Any, list[tuple[Any, ...]]]]) -> None:
        self._responses = list(responses)
        self.description: Any = None
        self._rows: list[tuple[Any, ...]] = []
        self.executed: list[tuple[str, Any]] = []
        self.fetch_sizes: list[int] = []

    def execute(self, sql: str, params: Any = None) -> None:
        self.executed.append((sql, params))
        self.description, self._rows = self._responses.pop(0)

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._rows)

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]:
        self.fetch_sizes.append(size)
        return list(self._rows)[:size]

    def close(self) -> None:
        return None


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor

    def cursor(self) -> _Cursor:
        return self._cursor

    def close(self) -> None:
        return None


class _Pool:
    def __init__(self, responses: list[tuple[Any, list[tuple[Any, ...]]]]) -> None:
        self.responses = responses
        self.executed: list[tuple[str, Any]] = []
        self.fetch_sizes: list[int] = []
        self.committed = 0
        self.rolled_back = 0
        self.reserved_tables: list[str | None] = []

    @contextmanager
    def session(self) -> Iterator[_Connection]:
        cursor = _Cursor(self.responses)
        yield _Connection(cursor)
        self.executed.extend(cursor.executed)
        self.fetch_sizes.extend(cursor.fetch_sizes)

    @contextmanager
    def write_session(
        self, *, reserve_table: str | None = None
    ) -> Iterator[_Connection]:
        self.reserved_tables.append(reserve_table)
        cursor = _Cursor(self.responses)
        try:
            yield _Connection(cursor)
        except BaseException:
            self.rolled_back += 1
            raise
        else:
            self.committed += 1
        finally:
            self.executed.extend(cursor.executed)
            self.fetch_sizes.extend(cursor.fetch_sizes)

    def ping(self) -> str:
        return "Firebird 2.5.9"

    @property
    def stats(self) -> dict[str, int]:
        return {"created": 1, "idle": 1, "capacity": 5}

    def close(self) -> None:
        return None


def test_list_tables_is_sorted() -> None:
    pool = _Pool([])
    service = make_service(pool)
    service.schema = _StubSchema(
        APPUSER,
        TableInfo("V_USERS", "view", "Registered users", (ColumnInfo("ID", 0, "INTEGER", True),)),
    )
    assert [table["name"] for table in service.list_tables()] == ["APPUSER", "V_USERS"]


def test_describe_table_includes_columns() -> None:
    service = make_service(_Pool([]))
    payload = service.describe_table("appuser")
    assert payload["name"] == "APPUSER"
    assert payload["columns"][1] == {
        "name": "NAME",
        "position": 1,
        "type": "VARCHAR(50)",
        "nullable": True,
    }


def test_refresh_schema_invalidates_cache() -> None:
    service = make_service(_Pool([]))
    assert service.refresh_schema() == 1
    assert service.schema.invalidated == 1


def test_health_reports_pool_statistics() -> None:
    service = make_service(_Pool([]))
    payload = service.health()
    assert payload["status"] == "ok"
    assert payload["database"]["server_version"] == "Firebird 2.5.9"
    assert payload["pool"]["capacity"] == 5
    assert payload["latency_ms"] >= 0


def test_fetch_rows_builds_count_and_page_queries() -> None:
    pool = _Pool(
        [
            (None, [(42,)]),
            ([("ID",), ("NAME",)], [(1, "ACME"), (2, None)]),
        ]
    )
    service = make_service(pool)

    page = service.fetch_rows(
        "appuser", limit=5, offset=10, order_by="id desc", filters='{"NAME": "ACME"}'
    )

    assert page["table"] == "APPUSER"
    assert page["total"] == 42
    assert page["limit"] == 5
    assert page["offset"] == 10
    assert page["columns"] == ["ID", "NAME"]
    assert page["rows"] == [{"ID": 1, "NAME": "ACME"}, {"ID": 2, "NAME": None}]
    assert page["row_count"] == 2

    count_sql, count_params = pool.executed[0]
    page_sql, page_params = pool.executed[1]
    assert count_sql == 'SELECT COUNT(*) FROM "APPUSER" WHERE "NAME" = ?'
    assert count_params == ["ACME"]
    assert page_sql == (
        'SELECT * FROM "APPUSER" WHERE "NAME" = ? ORDER BY "ID" DESC ROWS 11 TO 15'
    )
    assert page_params == ["ACME"]


def test_fetch_rows_uses_default_limit() -> None:
    pool = _Pool([(None, [(1,)]), ([("ID",)], [(1,)])])
    service = make_service(pool, default_limit=20, max_limit=100)

    page = service.fetch_rows("APPUSER")

    assert page["limit"] == 20
    assert pool.executed[1][0] == 'SELECT * FROM "APPUSER" ROWS 1 TO 20'


def test_fetch_rows_without_filters_passes_no_parameters() -> None:
    pool = _Pool([(None, [(0,)]), ([("ID",)], [])])
    service = make_service(pool)

    page = service.fetch_rows("APPUSER", limit=1)

    assert page["rows"] == []
    assert page["total"] == 0
    assert pool.executed[0] == ('SELECT COUNT(*) FROM "APPUSER"', None)


def test_fetch_rows_validates_limit_and_offset() -> None:
    service = make_service(_Pool([]), default_limit=10, max_limit=100)
    with pytest.raises(InvalidRequest):
        service.fetch_rows("APPUSER", limit=101)
    with pytest.raises(InvalidRequest):
        service.fetch_rows("APPUSER", limit=0)
    with pytest.raises(InvalidRequest):
        service.fetch_rows("APPUSER", offset=-1)
    with pytest.raises(TableNotFound):
        service.fetch_rows("MISSING")


def test_fetch_rows_validates_order_by() -> None:
    service = make_service(_Pool([]))
    with pytest.raises(ColumnNotFound):
        service.fetch_rows("APPUSER", order_by="NOPE")
    with pytest.raises(InvalidRequest):
        service.fetch_rows("APPUSER", order_by="ID SIDEWAYS")
    with pytest.raises(InvalidRequest):
        service.fetch_rows("APPUSER", order_by="ID DESC EXTRA")


def test_fetch_rows_serialises_decimals_and_dates() -> None:
    import datetime as dt
    from decimal import Decimal

    pool = _Pool(
        [
            (None, [(1,)]),
            ([("AMOUNT",), ("CREATED",)], [(Decimal("12.50"), dt.date(2024, 1, 2))]),
        ]
    )
    service = make_service(pool)
    page = service.fetch_rows("APPUSER", limit=1)
    assert page["rows"] == [{"AMOUNT": 12.5, "CREATED": "2024-01-02"}]


def test_run_query_returns_serialised_rows() -> None:
    pool = _Pool([([("ONE",), ("TEXT",)], [(1, "x"), (2, None)])])
    service = make_service(pool)

    result = service.run_query("SELECT ONE, TEXT FROM TEST_TABLE", limit=10)

    assert result == {
        "columns": ["ONE", "TEXT"],
        "rows": [{"ONE": 1, "TEXT": "x"}, {"ONE": 2, "TEXT": None}],
        "row_count": 2,
        "truncated": False,
    }
    assert pool.executed == [("SELECT ONE, TEXT FROM TEST_TABLE", None)]


def test_run_query_marks_truncated_results() -> None:
    pool = _Pool([([("N",)], [(1,), (2,), (3,)])])
    service = make_service(pool)

    result = service.run_query("SELECT N FROM T", limit=2)

    assert result["row_count"] == 2
    assert result["rows"] == [{"N": 1}, {"N": 2}]
    assert result["truncated"] is True


def test_run_query_defaults_to_max_query_rows() -> None:
    pool = _Pool([([("N",)], [])])
    service = make_service(pool, max_query_rows=25)

    service.run_query("SELECT N FROM T")

    assert pool.fetch_sizes == [26]


def test_run_query_rejects_writes() -> None:
    service = make_service(_Pool([]))
    with pytest.raises(QueryNotAllowed):
        service.run_query("DELETE FROM APPUSER")


def test_run_query_validates_parameters() -> None:
    service = make_service(_Pool([]))
    with pytest.raises(InvalidRequest):
        service.run_query("SELECT 1 FROM RDB$DATABASE", parameters="nope")
    with pytest.raises(InvalidRequest):
        service.run_query("SELECT 1 FROM RDB$DATABASE", parameters=[{"a": 1}])


def test_run_query_passes_parameters() -> None:
    pool = _Pool([([("ONE",)], [(1,)])])
    service = make_service(pool)

    service.run_query("SELECT ONE FROM T WHERE ID = ?", parameters=[7])

    assert pool.executed == [("SELECT ONE FROM T WHERE ID = ?", [7])]


def test_fetch_clients_builds_queries_and_maps_fields() -> None:
    import datetime as dt

    pool = _Pool(
        [
            (None, [(3,)]),
            (
                [("ID_KLIENT_TABLE",), ("ID_KLIENT",), ("NAZWA",), ("NIP",), ("OSTATNIO",)],
                [(2, 1, "ACME", "1234567890", dt.date(2024, 5, 1))],
            ),
        ]
    )
    service = make_projection_service(pool)

    page = service.fetch_clients()

    assert page["total"] == 3
    assert page["count"] == 1
    assert page["limit"] == 50
    assert page["offset"] == 0
    assert page["clients"] == [
        {
            "id_klient_table": 2,
            "id_klient": 1,
            "nazwa": "ACME",
            "nip": "1234567890",
            "ostatnio": "2024-05-01",
        }
    ]

    assert pool.executed[0] == ('SELECT COUNT(*) FROM "KLIENT"', None)
    assert pool.executed[1] == (
        'SELECT "ID_KLIENT_TABLE", "ID_KLIENT", "NAZWA", "NIP", "OSTATNIO" '
        'FROM "KLIENT" ORDER BY "NAZWA", "ID_KLIENT_TABLE" ROWS 1 TO 50',
        None,
    )


def test_fetch_clients_uses_configured_default_limit() -> None:
    pool = _Pool([(None, [(0,)]), ([("ID_KLIENT_TABLE",)], [])])
    service = make_projection_service(pool, default_limit=20, max_limit=100)

    page = service.fetch_clients(offset=40)

    assert page["limit"] == 20
    assert page["offset"] == 40
    assert page["clients"] == []
    assert pool.executed[1][0].endswith('ROWS 41 TO 60')


def test_fetch_clients_search_builds_or_clause() -> None:
    pool = _Pool([(None, [(1,)]), ([("ID_KLIENT_TABLE",)], [])])
    service = make_projection_service(pool)

    page = service.fetch_clients(search="  ac%me  ", limit=5)

    count_sql, params = pool.executed[0]
    assert page["total"] == 1
    assert count_sql == (
        'SELECT COUNT(*) FROM "KLIENT" WHERE ("NAZWA" LIKE CAST(? AS VARCHAR(1024)) '
        'ESCAPE \'\\\' OR "NIP" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\')'
    )
    assert params == ["%ac\\%me%", "%ac\\%me%"]
    assert pool.executed[1][1] == params


def test_fetch_clients_blank_search_is_ignored() -> None:
    pool = _Pool([(None, [(0,)]), ([("ID_KLIENT_TABLE",)], [])])
    service = make_projection_service(pool)

    service.fetch_clients(search="   ")

    assert pool.executed[0] == ('SELECT COUNT(*) FROM "KLIENT"', None)


def test_fetch_clients_validates_arguments() -> None:
    service = make_projection_service(_Pool([]), KLIENT, default_limit=10, max_limit=100)
    with pytest.raises(InvalidRequest):
        service.fetch_clients(limit=0)
    with pytest.raises(InvalidRequest):
        service.fetch_clients(limit=101)
    with pytest.raises(InvalidRequest):
        service.fetch_clients(offset=-1)
    with pytest.raises(TableNotFound):
        make_projection_service(_Pool([]), APPUSER).fetch_clients()


def test_fetch_clients_skips_columns_missing_from_schema() -> None:
    table = TableInfo(
        "KLIENT",
        "table",
        None,
        (
            ColumnInfo("ID_KLIENT_TABLE", 0, "INTEGER", False),
            ColumnInfo("NAZWA", 1, "VARCHAR(500)", True),
        ),
    )
    pool = _Pool([(None, [(1,)]), ([("ID_KLIENT_TABLE",), ("NAZWA",)], [(7, "ACME")])])
    service = make_projection_service(pool, table)

    page = service.fetch_clients(limit=1)

    assert page["clients"] == [{"id_klient_table": 7, "nazwa": "ACME"}]
    assert pool.executed[1][0] == (
        'SELECT "ID_KLIENT_TABLE", "NAZWA" FROM "KLIENT" '
        'ORDER BY "NAZWA", "ID_KLIENT_TABLE" ROWS 1 TO 1'
    )


def test_fetch_clients_requires_known_columns() -> None:
    table = TableInfo(
        "KLIENT", "table", None, (ColumnInfo("OTHER", 0, "INTEGER", True),)
    )
    service = make_projection_service(_Pool([]), table)

    with pytest.raises(InvalidRequest):
        service.fetch_clients()


def test_fetch_agreements_builds_queries_and_maps_fields() -> None:
    import datetime as dt
    from decimal import Decimal

    pool = _Pool(
        [
            (None, [(2,)]),
            (
                [
                    ("ID_UMOWACPC_TABLE",),
                    ("ID_UMOWACPC",),
                    ("UMOWA",),
                    ("OPIEKUN",),
                    ("U_START",),
                    ("KOSZTY",),
                ],
                [
                    (
                        5,
                        5,
                        "CPC/2024/001",
                        "Kowalski",
                        dt.date(2024, 1, 1),
                        Decimal("1500.5000"),
                    )
                ],
            ),
        ]
    )
    service = make_projection_service(pool, UMOWACPC)

    page = service.fetch_agreements()

    assert page["total"] == 2
    assert page["count"] == 1
    assert page["limit"] == 50
    assert page["offset"] == 0
    assert page["agreements"] == [
        {
            "id_umowacpc_table": 5,
            "id_umowacpc": 5,
            "umowa": "CPC/2024/001",
            "opiekun": "Kowalski",
            "u_start": "2024-01-01",
            "koszty": 1500.5,
        }
    ]

    assert pool.executed[0] == ('SELECT COUNT(*) FROM "UMOWACPC"', None)
    assert pool.executed[1] == (
        'SELECT "ID_UMOWACPC_TABLE", "ID_UMOWACPC", "UMOWA", "OPIEKUN", '
        '"U_START", "KOSZTY" FROM "UMOWACPC" '
        'ORDER BY "UMOWA", "ID_UMOWACPC_TABLE" ROWS 1 TO 50',
        None,
    )


def test_fetch_agreements_uses_configured_default_limit() -> None:
    pool = _Pool([(None, [(0,)]), ([("ID_UMOWACPC_TABLE",)], [])])
    service = make_projection_service(
        pool, UMOWACPC, default_limit=20, max_limit=100
    )

    page = service.fetch_agreements(offset=40)

    assert page["limit"] == 20
    assert page["offset"] == 40
    assert page["agreements"] == []
    assert pool.executed[1][0].endswith("ROWS 41 TO 60")


def test_fetch_agreements_search_builds_or_clause() -> None:
    pool = _Pool([(None, [(1,)]), ([("ID_UMOWACPC_TABLE",)], [])])
    service = make_projection_service(pool, UMOWACPC)

    page = service.fetch_agreements(search="  cpc%1  ", limit=5)

    count_sql, params = pool.executed[0]
    assert page["total"] == 1
    assert count_sql == (
        'SELECT COUNT(*) FROM "UMOWACPC" '
        'WHERE ("UMOWA" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "OPIEKUN" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\')'
    )
    assert params == ["%cpc\\%1%", "%cpc\\%1%"]
    assert pool.executed[1][1] == params


def test_fetch_agreements_serialises_decimals_as_strings() -> None:
    from decimal import Decimal

    table = TableInfo(
        "UMOWACPC",
        "table",
        None,
        (ColumnInfo("KOSZTY", 0, "DECIMAL(10,4)", True),),
    )
    pool = _Pool(
        [
            (None, [(1,)]),
            ([("KOSZTY",)], [(Decimal("1500.5000"),)]),
        ]
    )
    service = make_projection_service(pool, table, decimal_as_string=True)

    page = service.fetch_agreements(limit=1)

    assert page["agreements"] == [{"koszty": "1500.5000"}]


def test_fetch_agreements_skips_columns_missing_from_schema() -> None:
    table = TableInfo(
        "UMOWACPC",
        "table",
        None,
        (
            ColumnInfo("ID_UMOWACPC_TABLE", 0, "INTEGER", False),
            ColumnInfo("UMOWA", 1, "VARCHAR(100)", True),
        ),
    )
    pool = _Pool(
        [
            (None, [(1,)]),
            ([("ID_UMOWACPC_TABLE",), ("UMOWA",)], [(3, "CPC/2024/002")]),
        ]
    )
    service = make_projection_service(pool, table)

    page = service.fetch_agreements(limit=1)

    assert page["agreements"] == [{"id_umowacpc_table": 3, "umowa": "CPC/2024/002"}]
    assert pool.executed[1][0] == (
        'SELECT "ID_UMOWACPC_TABLE", "UMOWA" FROM "UMOWACPC" '
        'ORDER BY "UMOWA", "ID_UMOWACPC_TABLE" ROWS 1 TO 1'
    )


def test_fetch_agreements_validates_arguments() -> None:
    service = make_projection_service(
        _Pool([]), UMOWACPC, default_limit=10, max_limit=100
    )
    with pytest.raises(InvalidRequest):
        service.fetch_agreements(limit=0)
    with pytest.raises(InvalidRequest):
        service.fetch_agreements(limit=101)
    with pytest.raises(InvalidRequest):
        service.fetch_agreements(offset=-1)
    with pytest.raises(TableNotFound):
        make_projection_service(_Pool([]), APPUSER).fetch_agreements()


def test_fetch_agreements_requires_known_columns() -> None:
    table = TableInfo(
        "UMOWACPC", "table", None, (ColumnInfo("OTHER", 0, "INTEGER", True),)
    )
    service = make_projection_service(_Pool([]), table)

    with pytest.raises(InvalidRequest):
        service.fetch_agreements()


def test_fetch_machines_builds_queries_and_maps_fields() -> None:
    import datetime as dt
    from decimal import Decimal

    pool = _Pool(
        [
            (None, [(1,)]),
            (
                [
                    ("ID_MASZYNA_TABLE",),
                    ("ID_MASZYNA",),
                    ("MARKA",),
                    ("SERIAL",),
                    ("INSTALACJA",),
                    ("TECHNIK",),
                    ("KOSZTY",),
                ],
                [
                    (
                        3,
                        2,
                        "KONICA",
                        "SN-0001",
                        dt.date(2024, 3, 1),
                        "Nowak Anna",
                        Decimal("120.0000"),
                    )
                ],
            ),
        ]
    )
    service = make_projection_service(pool, MASZYNA)

    page = service.fetch_machines()

    assert page["total"] == 1
    assert page["count"] == 1
    assert page["limit"] == 50
    assert page["offset"] == 0
    assert page["machines"] == [
        {
            "id_maszyna_table": 3,
            "id_maszyna": 2,
            "marka": "KONICA",
            "serial": "SN-0001",
            "instalacja": "2024-03-01",
            "technik": "Nowak Anna",
            "koszty": 120.0,
        }
    ]

    assert pool.executed[0] == ('SELECT COUNT(*) FROM "MASZYNA"', None)
    assert pool.executed[1] == (
        'SELECT "ID_MASZYNA_TABLE", "ID_MASZYNA", "MARKA", "SERIAL", '
        '"INSTALACJA", "TECHNIK", "KOSZTY" FROM "MASZYNA" '
        'ORDER BY "ID_MASZYNA", "ID_MASZYNA_TABLE" ROWS 1 TO 50',
        None,
    )


def test_fetch_machines_uses_configured_default_limit() -> None:
    pool = _Pool([(None, [(0,)]), ([("ID_MASZYNA_TABLE",)], [])])
    service = make_projection_service(pool, MASZYNA, default_limit=20, max_limit=100)

    page = service.fetch_machines(offset=40)

    assert page["limit"] == 20
    assert page["offset"] == 40
    assert page["machines"] == []
    assert pool.executed[1][0].endswith("ROWS 41 TO 60")


def test_fetch_machines_search_builds_or_clause() -> None:
    pool = _Pool([(None, [(1,)]), ([("ID_MASZYNA_TABLE",)], [])])
    service = make_projection_service(pool, MASZYNA)

    page = service.fetch_machines(search="  kon%1  ", limit=5)

    count_sql, params = pool.executed[0]
    assert page["total"] == 1
    assert count_sql == (
        'SELECT COUNT(*) FROM "MASZYNA" '
        'WHERE ("MARKA" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "SERIAL" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "TECHNIK" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\')'
    )
    assert params == ["%kon\\%1%", "%kon\\%1%", "%kon\\%1%"]
    assert pool.executed[1][1] == params


def test_fetch_machines_serialises_decimals_as_strings() -> None:
    from decimal import Decimal

    table = TableInfo(
        "MASZYNA",
        "table",
        None,
        (ColumnInfo("OPLATA", 0, "DECIMAL(10,4)", True),),
    )
    pool = _Pool([(None, [(1,)]), ([("OPLATA",)], [(Decimal("0.1200"),)])])
    service = make_projection_service(pool, table, decimal_as_string=True)

    page = service.fetch_machines(limit=1)

    assert page["machines"] == [{"oplata": "0.1200"}]


def test_fetch_machines_skips_columns_missing_from_schema() -> None:
    table = TableInfo(
        "MASZYNA",
        "table",
        None,
        (
            ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
            ColumnInfo("MARKA", 1, "VARCHAR(100)", True),
        ),
    )
    pool = _Pool(
        [
            (None, [(1,)]),
            ([("ID_MASZYNA_TABLE",), ("MARKA",)], [(3, "KONICA")]),
        ]
    )
    service = make_projection_service(pool, table)

    page = service.fetch_machines(limit=1)

    assert page["machines"] == [{"id_maszyna_table": 3, "marka": "KONICA"}]
    assert pool.executed[1][0] == (
        'SELECT "ID_MASZYNA_TABLE", "MARKA" FROM "MASZYNA" '
        'ORDER BY "ID_MASZYNA_TABLE" ROWS 1 TO 1'
    )


def test_fetch_machines_validates_arguments() -> None:
    service = make_projection_service(
        _Pool([]), MASZYNA, default_limit=10, max_limit=100
    )
    with pytest.raises(InvalidRequest):
        service.fetch_machines(limit=0)
    with pytest.raises(InvalidRequest):
        service.fetch_machines(limit=101)
    with pytest.raises(InvalidRequest):
        service.fetch_machines(offset=-1)
    with pytest.raises(TableNotFound):
        make_projection_service(_Pool([]), APPUSER).fetch_machines()


def test_fetch_machines_requires_known_columns() -> None:
    table = TableInfo(
        "MASZYNA", "table", None, (ColumnInfo("OTHER", 0, "INTEGER", True),)
    )
    service = make_projection_service(_Pool([]), table)

    with pytest.raises(InvalidRequest):
        service.fetch_machines()


def test_fetch_orders_builds_queries_and_maps_fields() -> None:
    import datetime as dt
    from decimal import Decimal

    pool = _Pool(
        [
            (None, [(1,)]),
            (
                [
                    ("ID_ZLECENIE_TABLE",),
                    ("ID_ZLECENIE",),
                    ("STAN",),
                    ("NAZWA",),
                    ("MARKA",),
                    ("DATA",),
                    ("TECHNIK",),
                    ("BRUTTO",),
                ],
                [
                    (
                        2,
                        2,
                        "O",
                        "ACME",
                        "KONICA",
                        dt.date(2026, 11, 7),
                        "Nowak Anna",
                        Decimal("120.5000"),
                    )
                ],
            ),
        ]
    )
    service = make_projection_service(pool, ZLECENIE)

    page = service.fetch_orders()

    assert page["total"] == 1
    assert page["count"] == 1
    assert page["limit"] == 50
    assert page["offset"] == 0
    assert page["orders"] == [
        {
            "id_zlecenie_table": 2,
            "id_zlecenie": 2,
            "stan": "O",
            "nazwa": "ACME",
            "marka": "KONICA",
            "data": "2026-11-07",
            "technik": "Nowak Anna",
            "brutto": 120.5,
        }
    ]

    assert pool.executed[0] == ('SELECT COUNT(*) FROM "ZLECENIE"', None)
    assert pool.executed[1] == (
        'SELECT "ID_ZLECENIE_TABLE", "ID_ZLECENIE", "STAN", "NAZWA", "MARKA", '
        '"DATA", "TECHNIK", "BRUTTO" FROM "ZLECENIE" '
        'ORDER BY "DATA", "ID_ZLECENIE_TABLE" ROWS 1 TO 50',
        None,
    )


def test_fetch_orders_uses_configured_default_limit() -> None:
    pool = _Pool([(None, [(0,)]), ([("ID_ZLECENIE_TABLE",)], [])])
    service = make_projection_service(
        pool, ZLECENIE, default_limit=20, max_limit=100
    )

    page = service.fetch_orders(offset=40)

    assert page["limit"] == 20
    assert page["offset"] == 40
    assert page["orders"] == []
    assert pool.executed[1][0].endswith("ROWS 41 TO 60")


def test_fetch_orders_search_builds_or_clause() -> None:
    pool = _Pool([(None, [(1,)]), ([("ID_ZLECENIE_TABLE",)], [])])
    service = make_projection_service(pool, ZLECENIE)

    page = service.fetch_orders(search="  acme%1  ", limit=5)

    count_sql, params = pool.executed[0]
    assert page["total"] == 1
    assert count_sql == (
        'SELECT COUNT(*) FROM "ZLECENIE" '
        'WHERE ("NAZWA" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "MARKA" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "TECHNIK" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "STAN" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\')'
    )
    assert params == ["%acme\\%1%"] * 4
    assert pool.executed[1][1] == params


def test_fetch_orders_serialises_decimals_as_strings() -> None:
    from decimal import Decimal

    table = TableInfo(
        "ZLECENIE",
        "table",
        None,
        (ColumnInfo("BRUTTO", 0, "DECIMAL(10,4)", True),),
    )
    pool = _Pool([(None, [(1,)]), ([("BRUTTO",)], [(Decimal("120.5000"),)])])
    service = make_projection_service(pool, table, decimal_as_string=True)

    page = service.fetch_orders(limit=1)

    assert page["orders"] == [{"brutto": "120.5000"}]


def test_fetch_orders_skips_columns_missing_from_schema() -> None:
    table = TableInfo(
        "ZLECENIE",
        "table",
        None,
        (
            ColumnInfo("ID_ZLECENIE_TABLE", 0, "INTEGER", False),
            ColumnInfo("STAN", 1, "VARCHAR(3)", True),
        ),
    )
    pool = _Pool(
        [(None, [(1,)]), ([("ID_ZLECENIE_TABLE",), ("STAN",)], [(2, "O")])]
    )
    service = make_projection_service(pool, table)

    page = service.fetch_orders(limit=1)

    assert page["orders"] == [{"id_zlecenie_table": 2, "stan": "O"}]
    assert pool.executed[1][0] == (
        'SELECT "ID_ZLECENIE_TABLE", "STAN" FROM "ZLECENIE" '
        'ORDER BY "ID_ZLECENIE_TABLE" ROWS 1 TO 1'
    )


def test_fetch_orders_validates_arguments() -> None:
    service = make_projection_service(
        _Pool([]), ZLECENIE, default_limit=10, max_limit=100
    )
    with pytest.raises(InvalidRequest):
        service.fetch_orders(limit=0)
    with pytest.raises(InvalidRequest):
        service.fetch_orders(limit=101)
    with pytest.raises(InvalidRequest):
        service.fetch_orders(offset=-1)
    with pytest.raises(TableNotFound):
        make_projection_service(_Pool([]), APPUSER).fetch_orders()


def test_fetch_orders_requires_known_columns() -> None:
    table = TableInfo(
        "ZLECENIE", "table", None, (ColumnInfo("OTHER", 0, "INTEGER", True),)
    )
    service = make_projection_service(_Pool([]), table)

    with pytest.raises(InvalidRequest):
        service.fetch_orders()


def test_order_search_list_stays_within_the_firebird_message_limit() -> None:
    """A wider list would fail to prepare with "Implementation limit exceeded"."""
    from ks_adapter.service import ORDER_SEARCH_COLUMNS
    from ks_adapter.sql import LIKE_PARAMETER_BYTES, MAX_MESSAGE_BYTES

    assert len(ORDER_SEARCH_COLUMNS) * LIKE_PARAMETER_BYTES <= MAX_MESSAGE_BYTES
    assert len(set(ORDER_SEARCH_COLUMNS)) == len(ORDER_SEARCH_COLUMNS)


def test_fetch_invoices_builds_queries_and_maps_fields() -> None:
    import datetime as dt
    from decimal import Decimal

    pool = _Pool(
        [
            (None, [(1,)]),
            (
                [
                    ("ID_FAKTURA_TABLE",),
                    ("NAZWA",),
                    ("NUMER",),
                    ("DATA_WYST",),
                    ("SUMA_BRUTTO",),
                    ("STAN",),
                ],
                [
                    (
                        5,
                        "ACME",
                        "FV/2026/11/001",
                        dt.date(2026, 11, 7),
                        Decimal("1230.0000"),
                        "W",
                    )
                ],
            ),
        ]
    )
    service = make_projection_service(pool, FAKTURA)

    page = service.fetch_invoices()

    assert page["total"] == 1
    assert page["count"] == 1
    assert page["limit"] == 50
    assert page["offset"] == 0
    assert page["invoices"] == [
        {
            "id_faktura_table": 5,
            "numer": "FV/2026/11/001",
            "nazwa": "ACME",
            "data_wyst": "2026-11-07",
            "stan": "W",
            "suma_brutto": 1230.0,
        }
    ]

    assert pool.executed[0] == ('SELECT COUNT(*) FROM "FAKTURA"', None)
    assert pool.executed[1] == (
        'SELECT "ID_FAKTURA_TABLE", "NAZWA", "NUMER", "DATA_WYST", '
        '"SUMA_BRUTTO", "STAN" FROM "FAKTURA" '
        'ORDER BY "DATA_WYST", "ID_FAKTURA_TABLE" ROWS 1 TO 50',
        None,
    )


def test_fetch_invoices_search_builds_or_clause() -> None:
    pool = _Pool([(None, [(0,)]), ([("ID_FAKTURA_TABLE",)], [])])
    service = make_projection_service(pool, FAKTURA)

    page = service.fetch_invoices(search="fv/2026", limit=5)

    count_sql, params = pool.executed[0]
    assert page["total"] == 0
    assert count_sql == (
        'SELECT COUNT(*) FROM "FAKTURA" '
        'WHERE ("NUMER" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "NAZWA" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "STAN" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\')'
    )
    assert params == ["%fv/2026%"] * 3
    assert pool.executed[1][1] == params


def test_fetch_invoices_validates_arguments() -> None:
    service = make_projection_service(
        _Pool([]), FAKTURA, default_limit=10, max_limit=100
    )

    with pytest.raises(InvalidRequest):
        service.fetch_invoices(limit=0)
    with pytest.raises(InvalidRequest):
        service.fetch_invoices(limit=101)
    with pytest.raises(InvalidRequest):
        service.fetch_invoices(offset=-1)
    with pytest.raises(TableNotFound):
        make_projection_service(_Pool([]), APPUSER).fetch_invoices()


def test_fetch_invoices_requires_known_columns() -> None:
    table = TableInfo(
        "FAKTURA", "table", None, (ColumnInfo("OTHER", 0, "INTEGER", True),)
    )
    service = make_projection_service(_Pool([]), table)

    with pytest.raises(InvalidRequest):
        service.fetch_invoices()


def test_invoice_search_list_stays_within_the_firebird_message_limit() -> None:
    from ks_adapter.service import INVOICE_SEARCH_COLUMNS
    from ks_adapter.sql import LIKE_PARAMETER_BYTES, MAX_MESSAGE_BYTES

    assert len(INVOICE_SEARCH_COLUMNS) * LIKE_PARAMETER_BYTES <= MAX_MESSAGE_BYTES
    assert len(set(INVOICE_SEARCH_COLUMNS)) == len(INVOICE_SEARCH_COLUMNS)


KLIENT_WRITABLE = TableInfo(
    name="KLIENT",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID_KLIENT_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_KLIENT", 1, "INTEGER", False),
        ColumnInfo("ID_FIRMA", 2, "INTEGER", False),
        ColumnInfo("NAZWA", 3, "VARCHAR(500)", True),
        ColumnInfo("NAZWA_S", 4, "VARCHAR(50)", True),
        ColumnInfo("NIP", 5, "VARCHAR(20)", True),
        ColumnInfo("ADRES", 6, "VARCHAR(250)", True),
        ColumnInfo("TERMIN", 7, "INTEGER", True),
        ColumnInfo("TYP", 8, "VARCHAR(50)", True),
        ColumnInfo("PLATNOSC", 9, "VARCHAR(50)", True),
        ColumnInfo("KOD_KRAJU", 10, "VARCHAR(20)", True),
        ColumnInfo("STATUS", 11, "INTEGER", True),
        ColumnInfo("OSTATNIO", 12, "DATE", True),
    ),
)

KLIENT_RETURNING = [
    ("ID_KLIENT_TABLE",),
    ("ID_KLIENT",),
    ("NAZWA",),
    ("NAZWA_S",),
    ("NIP",),
    ("ADRES",),
    ("TYP",),
    ("PLATNOSC",),
    ("TERMIN",),
    ("OSTATNIO",),
]

#: The columns a ``POST /clients`` insert returns; ``CLIENT_COLUMNS`` filtered by
#: the stub catalog above.
KLIENT_RETURNING_COLUMNS = (
    "ID_KLIENT_TABLE",
    "ID_KLIENT",
    "NAZWA",
    "NAZWA_S",
    "NIP",
    "ADRES",
    "TYP",
    "PLATNOSC",
    "TERMIN",
    "OSTATNIO",
)


def _client_insert(columns: tuple[str, ...]) -> str:
    """The statement ``create_client`` must build for ``columns``."""
    names = ", ".join(f'"{column}"' for column in columns)
    placeholders = ", ".join("?" for _ in columns)
    returning = ", ".join(f'"{column}"' for column in KLIENT_RETURNING_COLUMNS)
    return (
        f'INSERT INTO "KLIENT" ({names}) VALUES ({placeholders}) '
        f"RETURNING {returning}"
    )


def test_create_client_inserts_the_supplied_columns() -> None:
    import datetime as dt

    row = (
        5,
        4,
        "ACME",
        None,
        "1234567890",
        "",
        "Odbiorca",
        "Gotówka",
        14,
        dt.date(2026, 1, 2),
    )
    pool = _Pool([(KLIENT_RETURNING, [row])])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)

    created = service.create_client(
        {
            "nazwa": "  ACME  ",
            "nip": "1234567890",
            "adres": "   ",
            "termin": 14,
        }
    )

    columns = (
        "NAZWA",
        "NIP",
        "TERMIN",
        "ID_FIRMA",
        "NAZWA_S",
        "ADRES",
        "KOD_KRAJU",
        "TYP",
        "PLATNOSC",
        "STATUS",
    )
    assert pool.executed == [
        (
            _client_insert(columns),
            ["ACME", "1234567890", 14, 0, "", "", "PL", "Odbiorca", "Gotówka", 0],
        )
    ]
    assert pool.committed == 1
    assert pool.rolled_back == 0
    assert created == {
        "id_klient_table": 5,
        "id_klient": 4,
        "nazwa": "ACME",
        "nazwa_s": None,
        "nip": "1234567890",
        "adres": "",
        "typ": "Odbiorca",
        "platnosc": "Gotówka",
        "termin": 14,
        "ostatnio": "2026-01-02",
    }


def test_create_client_accepts_upper_cased_field_names() -> None:
    pool = _Pool(
        [(KLIENT_RETURNING, [(5, 4, "ACME", None, None, None, None, None, None, None)])]
    )
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)

    service.create_client({"NAZWA": "ACME", "Nip": "1234567890"})

    columns = (
        "NAZWA",
        "NIP",
        "ID_FIRMA",
        "NAZWA_S",
        "ADRES",
        "KOD_KRAJU",
        "TYP",
        "PLATNOSC",
        "TERMIN",
        "STATUS",
    )
    assert pool.executed == [
        (
            _client_insert(columns),
            ["ACME", "1234567890", 0, "", "", "PL", "Odbiorca", "Gotówka", 0, 0],
        )
    ]


def test_create_client_carries_the_legacy_application_defaults() -> None:
    from ks_adapter.service import CLIENT_INSERT_DEFAULTS, CLIENT_TEXT_LENGTHS

    # The values the program itself writes; a row without them never appears in
    # its client list, so they are part of the contract, not cosmetics.
    assert CLIENT_INSERT_DEFAULTS["ID_FIRMA"] == 0
    assert CLIENT_INSERT_DEFAULTS["IDW"] == -1
    assert CLIENT_INSERT_DEFAULTS["KOD_KRAJU"] == "PL"
    assert CLIENT_INSERT_DEFAULTS["TYP"] == "Odbiorca"
    assert CLIENT_INSERT_DEFAULTS["PLATNOSC"] == "Gotówka"
    assert CLIENT_INSERT_DEFAULTS["AKTYWNY"] == ""
    assert CLIENT_INSERT_DEFAULTS["OSTZAPIS"] == 0
    # The program stamps these from its own clock; the adapter must not invent
    # them, otherwise a bridged row looks older than it is.
    assert "OSTATNIO" not in CLIENT_INSERT_DEFAULTS
    assert "GUSDATA" not in CLIENT_INSERT_DEFAULTS
    # The profile must fit the column widths it is inserted into.
    for column, value in CLIENT_INSERT_DEFAULTS.items():
        maximum = CLIENT_TEXT_LENGTHS.get(column)
        if maximum is not None:
            assert len(value) <= maximum
    # The generator-driven keys stay out: they come from the trigger.
    assert "ID_KLIENT" not in CLIENT_INSERT_DEFAULTS
    assert "ID_KLIENT_TABLE" not in CLIENT_INSERT_DEFAULTS


def test_create_client_prefers_supplied_values_over_the_defaults() -> None:
    pool = _Pool(
        [
            (
                KLIENT_RETURNING,
                [(5, 4, "ACME", None, None, None, "Dostawca", "Przelew", 30, None)],
            )
        ]
    )
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)

    service.create_client(
        {"nazwa": "ACME", "typ": "Dostawca", "platnosc": "Przelew", "termin": 30}
    )

    statement, params = pool.executed[0]
    assert statement == _client_insert(
        (
            "NAZWA",
            "TYP",
            "PLATNOSC",
            "TERMIN",
            "ID_FIRMA",
            "NAZWA_S",
            "ADRES",
            "NIP",
            "KOD_KRAJU",
            "STATUS",
        )
    )
    assert params == ["ACME", "Dostawca", "Przelew", 30, 0, "", "", "", "PL", 0]


def test_create_client_is_rejected_when_writes_are_disabled() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE)

    with pytest.raises(WritesDisabled):
        service.create_client({"nazwa": "ACME"})

    assert pool.executed == []
    assert pool.committed == 0


def test_create_client_requires_a_name() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)

    for values in (
        {},
        {"nip": "1234567890"},
        {"nazwa": None},
        {"nazwa": ""},
        {"nazwa": "   "},
    ):
        with pytest.raises(InvalidRequest):
            service.create_client(values)

    with pytest.raises(InvalidRequest):
        service.create_client([])  # type: ignore[arg-type]

    assert pool.executed == []


def test_create_client_rejects_unknown_and_over_long_values() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)

    with pytest.raises(InvalidRequest):
        service.create_client({"nazwa": "ACME", "id_klient": 1})
    with pytest.raises(InvalidRequest):
        service.create_client({"nazwa": "ACME", "ostatnio": "2026-01-02"})
    with pytest.raises(InvalidRequest):
        service.create_client({"nazwa": "x" * 501})
    with pytest.raises(InvalidRequest):
        service.create_client({"nazwa": "ACME", "nip": "1" * 21})

    assert pool.executed == []


def test_create_client_skips_columns_missing_from_the_schema() -> None:
    narrow = TableInfo(
        name="KLIENT",
        kind="table",
        description=None,
        columns=(
            ColumnInfo("ID_KLIENT_TABLE", 0, "INTEGER", False),
            ColumnInfo("NAZWA", 1, "VARCHAR(500)", True),
        ),
    )
    pool = _Pool([([("ID_KLIENT_TABLE",), ("NAZWA",)], [(7, "ACME")])])
    service = make_projection_service(pool, narrow, allow_writes=True)

    assert service.create_client({"nazwa": "ACME", "nip": "1234567890"}) == {
        "id_klient_table": 7,
        "nazwa": "ACME",
    }
    assert pool.executed[0][0] == (
        'INSERT INTO "KLIENT" ("NAZWA") VALUES (?) RETURNING '
        '"ID_KLIENT_TABLE", "NAZWA"'
    )


def test_create_client_requires_the_name_column() -> None:
    broken = TableInfo(
        name="KLIENT",
        kind="table",
        description=None,
        columns=(
            ColumnInfo("ID_KLIENT_TABLE", 0, "INTEGER", False),
            ColumnInfo("ID_KLIENT", 1, "INTEGER", False),
        ),
    )
    pool = _Pool([])
    service = make_projection_service(pool, broken, allow_writes=True)

    with pytest.raises(InvalidRequest):
        service.create_client({"nazwa": "ACME"})

    assert pool.executed == []


def test_create_client_rolls_back_when_the_insert_fails() -> None:
    pool = _Pool([])  # no scripted response -> the cursor raises
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)

    with pytest.raises(IndexError):
        service.create_client({"nazwa": "ACME"})

    assert pool.committed == 0
    assert pool.rolled_back == 1



MASZYNA_WRITABLE = TableInfo(
    name="MASZYNA",
    kind="table",
    description=None,
    columns=(
        ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_MASZYNA", 1, "INTEGER", False),
        ColumnInfo("ID_KLIENT", 2, "INTEGER", False),
        ColumnInfo("MARKA", 3, "VARCHAR(100)", True),
        ColumnInfo("SERIAL", 4, "VARCHAR(100)", True),
        ColumnInfo("INSTALACJA", 5, "DATE", True),
        ColumnInfo("OPLATA", 6, "DECIMAL(15,4)", True),
    ),
)

MASZYNA_RETURNING = [
    ("ID_MASZYNA_TABLE",),
    ("ID_MASZYNA",),
    ("ID_KLIENT",),
    ("MARKA",),
    ("SERIAL",),
    ("INSTALACJA",),
    ("OPLATA",),
]


def test_create_machine_inserts_the_supplied_columns() -> None:
    import datetime as dt
    from decimal import Decimal

    row = (9, 84, 7, "KONICA", "", dt.date(2026, 1, 2), Decimal("120.5000"))
    pool = _Pool([(MASZYNA_RETURNING, [row])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(pool, KLIENT, MASZYNA_WRITABLE, allow_writes=True)

    created = service.create_machine(
        {
            "id_klient": 7,
            "marka": "  KONICA  ",
            "serial": "   ",
            "instalacja": dt.date(2026, 1, 2),
            "oplata": Decimal("120.5"),
        }
    )

    assert pool.executed[1:] == [
        (
            'INSERT INTO "MASZYNA" ("ID_KLIENT", "MARKA", "INSTALACJA", '
            '"OPLATA", "SERIAL") '
            'VALUES (?, ?, ?, ?, ?) RETURNING "ID_MASZYNA_TABLE", "ID_MASZYNA", '
            '"ID_KLIENT", "MARKA", "SERIAL", "INSTALACJA", "OPLATA"',
            [7, "KONICA", dt.date(2026, 1, 2), Decimal("120.5"), ""],
        )
    ]
    assert pool.committed == 1
    assert pool.rolled_back == 0
    assert created == {
        "id_maszyna_table": 9,
        "id_maszyna": 84,
        "id_klient": 7,
        "marka": "KONICA",
        "serial": "",
        "instalacja": "2026-01-02",
        "oplata": 120.5,
    }



def test_create_machine_accepts_upper_cased_field_names() -> None:
    pool = _Pool([(MASZYNA_RETURNING, [(1, 2, 7, "KONICA", None, None, None)])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(pool, KLIENT, MASZYNA_WRITABLE, allow_writes=True)

    service.create_machine({"ID_KLIENT": 7, "Marka": "KONICA"})

    assert pool.executed[1][0] == (
        'INSERT INTO "MASZYNA" ("ID_KLIENT", "MARKA", "SERIAL") '
        'VALUES (?, ?, ?) RETURNING '
        '"ID_MASZYNA_TABLE", "ID_MASZYNA", "ID_KLIENT", "MARKA", "SERIAL", '
        '"INSTALACJA", "OPLATA"'
    )
    assert pool.executed[1][1] == [7, "KONICA", ""]


def test_create_machine_validates_a_supplied_owner() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)

    for values in (
        {}, {"id_klient": None}, {"id_klient": 0},
        {"id_klient": -3},
        {"id_klient": True},
        {"id_klient": "7"},
    ):
        with pytest.raises(InvalidRequest):
            service.create_machine(values)

    with pytest.raises(InvalidRequest):
        service.create_machine([])  # type: ignore[arg-type]

    assert pool.executed == []


def test_create_machine_rejects_unknown_fields() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)

    with pytest.raises(InvalidRequest):
        service.create_machine({
            "marka": "KS TEST", "id_klient": 7, "serialnumber": "SN-1",
        })
    with pytest.raises(InvalidRequest):
        service.create_machine({"marka": "KS TEST", "id_klient": 7, "koszty": 10.0})

    assert pool.executed == []


def test_create_machine_rejects_over_long_text() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)

    with pytest.raises(InvalidRequest):
        service.create_machine({"id_klient": 7, "marka": "x" * 101})

    assert pool.executed == []


def test_create_machine_is_rejected_when_writes_are_disabled() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE)

    with pytest.raises(WritesDisabled):
        service.create_machine({"marka": "KS TEST", "id_klient": 7})

    assert pool.executed == []
    assert pool.committed == 0



def test_create_machine_skips_columns_missing_from_the_schema() -> None:
    narrow = TableInfo(
        name="MASZYNA",
        kind="table",
        description=None,
        columns=(
            ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
            ColumnInfo("ID_KLIENT", 1, "INTEGER", False),
        ),
    )
    pool = _Pool([([("ID_MASZYNA_TABLE",), ("ID_KLIENT",)], [(11, 7)])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(pool, KLIENT, narrow, allow_writes=True)

    assert service.create_machine({"id_klient": 7, "marka": "KONICA"}) == {
        "id_maszyna_table": 11,
        "id_klient": 7,
    }
    assert pool.executed[1][0] == (
        'INSERT INTO "MASZYNA" ("ID_KLIENT") VALUES (?) RETURNING '
        '"ID_MASZYNA_TABLE", "ID_KLIENT"'
    )


def test_create_machine_requires_the_owner_column() -> None:
    broken = TableInfo(
        name="MASZYNA",
        kind="table",
        description=None,
        columns=(
            ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
            ColumnInfo("MARKA", 1, "VARCHAR(100)", True),
        ),
    )
    pool = _Pool([])
    service = make_projection_service(pool, broken, allow_writes=True)

    with pytest.raises(InvalidRequest):
        service.create_machine({"marka": "KS TEST", "id_klient": 7})

    assert pool.executed == []


def test_create_machine_rolls_back_when_the_insert_fails() -> None:
    pool = _Pool([])  # no scripted response -> the cursor raises
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(pool, KLIENT, MASZYNA_WRITABLE, allow_writes=True)

    with pytest.raises(IndexError):
        service.create_machine({"marka": "KS TEST", "id_klient": 7})

    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_create_machine_reuses_the_curated_column_lists() -> None:
    """The write payload must not reach columns the projection does not serve."""

    from ks_adapter.service import (
        MACHINE_COLUMNS,
        MACHINE_TEXT_LENGTHS,
        MACHINE_WRITE_COLUMNS,
    )

    assert set(MACHINE_WRITE_COLUMNS) <= set(MACHINE_COLUMNS)
    assert set(MACHINE_TEXT_LENGTHS) <= set(MACHINE_WRITE_COLUMNS)
    assert len(set(MACHINE_WRITE_COLUMNS)) == len(MACHINE_WRITE_COLUMNS)



def test_update_client_changes_only_supplied_fields() -> None:
    row = (5, 4, "ACME", None, "123", "", "Odbiorca", "Gotówka", 14, None)
    pool = _Pool([(KLIENT_RETURNING, [row])])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    result = service.update_client(4, {"Nip": " 123 ", "adres": "  "})
    returning = ", ".join(f'"{c}"' for c in KLIENT_RETURNING_COLUMNS)
    assert pool.executed == [(
        'UPDATE "KLIENT" SET "NIP" = ?, "ADRES" = ? '
        f'WHERE "ID_KLIENT" = ? RETURNING {returning}',
        ["123", "", 4],
    )]
    assert result["id_klient_table"] == 5
    assert result["typ"] == "Odbiorca"
    assert pool.committed == 1
    assert pool.rolled_back == 0


def test_update_client_preserves_explicit_null() -> None:
    row = (5, 4, "ACME", None, None, "", "Odbiorca", "Gotówka", 14, None)
    pool = _Pool([(KLIENT_RETURNING, [row])])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    assert service.update_client(4, {"nip": None})["nip"] is None
    assert pool.executed[0][1] == [None, 4]


@pytest.mark.parametrize("row", [None, (None,) * 10])
def test_update_client_missing_record_rolls_back(row: Any) -> None:
    pool = _Pool([(KLIENT_RETURNING, [] if row is None else [row])])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(RecordNotFound):
        service.update_client(999, {"nazwa": "ACME"})
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("values", [
    {}, {"nazwa": None}, {"nazwa": " "}, {"nazwa": "x" * 501},
    {"id_klient": 10}, {"ostatnio": "2026-01-02"}, {"nip": "x" * 21},
])
def test_update_client_rejects_invalid_fields(values: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.update_client(4, values)
    assert pool.executed == []
    assert pool.committed == 0


def test_update_client_refuses_writes_when_disabled() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE)
    with pytest.raises(WritesDisabled):
        service.update_client(4, {"nazwa": "ACME"})
    assert pool.executed == []


@pytest.mark.parametrize("key", [0, -1, True, "5"])
def test_update_client_requires_positive_key(key: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.update_client(key, {"nazwa": "ACME"})
    assert pool.executed == []


def test_update_client_rejects_columns_missing_from_catalog() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(ColumnNotFound):
        service.update_client(4, {"telefon": "123"})
    assert pool.executed == []


def test_update_client_rolls_back_database_failure() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(IndexError):
        service.update_client(4, {"nazwa": "ACME"})
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_create_client_rolls_back_when_serialization_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pool = _Pool([(KLIENT_RETURNING, [(5, 4, "ACME")])])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)

    def fail(names: Any, row: Any) -> dict[str, Any]:
        raise ValueError("Cannot serialize returned row")

    monkeypatch.setattr(service, "_serialize_row", fail)
    with pytest.raises(ValueError, match="Cannot serialize"):
        service.create_client({"nazwa": "ACME"})
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_delete_client_uses_business_identifier_and_commits() -> None:
    pool = _Pool([([("ID_KLIENT",)], [(4,)])])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    assert service.delete_client(4) is None
    assert pool.executed == [(
        'DELETE FROM "KLIENT" WHERE "ID_KLIENT" = ? RETURNING "ID_KLIENT"', [4]
    )]
    assert pool.committed == 1
    assert pool.rolled_back == 0


@pytest.mark.parametrize("row", [None, (None,)])
def test_delete_client_missing_record_rolls_back(row: Any) -> None:
    pool = _Pool([(None, [] if row is None else [row])])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(RecordNotFound):
        service.delete_client(4)
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_delete_client_refuses_disabled_writes() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE)
    with pytest.raises(WritesDisabled):
        service.delete_client(4)
    assert pool.executed == []


@pytest.mark.parametrize("key", [0, -1, True, "4", "4 OR 1=1"])
def test_delete_client_rejects_invalid_identifier(key: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.delete_client(key)
    assert pool.executed == []


def test_delete_client_rolls_back_database_failure() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, KLIENT_WRITABLE, allow_writes=True)
    with pytest.raises(IndexError):
        service.delete_client(4)
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_delete_client_rejects_catalog_without_business_identifier() -> None:
    pool = _Pool([])
    table = TableInfo("KLIENT", "table", None, (
        ColumnInfo("ID_KLIENT_TABLE", 0, "INTEGER", False),
    ))
    service = make_projection_service(pool, table, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.delete_client(4)
    assert pool.executed == []


@pytest.mark.parametrize("matches, error", [
    ([], RecordNotFound), ([(7,), (7,)], RecordConflict),
])
def test_create_machine_checks_client_before_inserting(
    matches: Any, error: Any,
) -> None:
    pool = _Pool([(None, matches)])
    service = make_projection_service(pool, MASZYNA_WRITABLE, KLIENT, allow_writes=True)
    with pytest.raises(error):
        service.create_machine({"marka": "KS TEST", "id_klient": 7})
    assert pool.executed == [(
        'SELECT FIRST 2 "ID_KLIENT" FROM "KLIENT" WHERE "ID_KLIENT" = ?', [7],
    )]
    assert pool.committed == 0
    assert pool.rolled_back == 1


AGREEMENT_WRITABLE = TableInfo("UMOWACPC", "table", None, (
    ColumnInfo("ID_UMOWACPC_TABLE", 0, "INTEGER", False),
    ColumnInfo("ID_UMOWACPC", 1, "INTEGER", False),
    ColumnInfo("ID_KLIENT", 2, "INTEGER", False),
    ColumnInfo("UMOWA", 3, "VARCHAR(100)", True),
    ColumnInfo("OPIEKUN", 4, "VARCHAR(100)", True),
    ColumnInfo("PLATNOSC", 5, "VARCHAR(250)", True),
    ColumnInfo("TERMIN", 6, "INTEGER", True),
))


def test_create_agreement_binds_values_and_merges_legacy_defaults() -> None:
    pool = _Pool([
        (None, [(51,)]), (None, [(12, 51, 7, "CPC TEST", "", "TRANSFER", 0)])
    ])
    pool.responses.append((None, []))
    service = make_projection_service(
        pool, MACHINE_LINKABLE, AGREEMENT_WRITABLE, allow_writes=True,
    )
    result = service.create_agreement({"machines": [],
        "id_klient": 7,
        "umowa": " CPC TEST ", "platnosc": "TRANSFER",
    })
    assert pool.executed[1:2] == [(
        'INSERT INTO "UMOWACPC" ("ID_UMOWACPC", "ID_KLIENT", "UMOWA", '
        '"PLATNOSC", "OPIEKUN", "TERMIN") VALUES (?, ?, ?, ?, ?, ?) '
        'RETURNING "ID_UMOWACPC_TABLE", "ID_UMOWACPC", "ID_KLIENT", "UMOWA", '
        '"OPIEKUN", "PLATNOSC", "TERMIN"',
        [51, 7, "CPC TEST", "TRANSFER", "", 0],
    )]
    assert result["id_umowacpc_table"] == 12
    assert result["id_umowacpc"] == 51
    assert result["platnosc"] == "TRANSFER"
    assert pool.committed == 1
    assert pool.rolled_back == 0


def test_create_agreement_default_payment_profile() -> None:
    pool = _Pool([(None, [(51,)]), (None, [(date(2026, 11, 8),)]),
                  (None, [(12, 51, 7, "51/2026", "", "$_$", 0)])])
    pool.responses.append((None, []))
    service = make_projection_service(
        pool, MACHINE_LINKABLE, AGREEMENT_WRITABLE, allow_writes=True,
    )
    result = service.create_agreement({"machines": [], "id_klient": 7})
    assert result["platnosc"] == "$_$"
    assert pool.executed[2][1] == [51, 7, "", "$_$", 0, "51/2026"]


@pytest.mark.parametrize("payload", [
    {}, {"id_klient": None}, {"id_klient": 0}, {"id_klient": -1},
    {"id_klient": True}, {"id_klient": "7"},
    {"id_umowacpc": 51, "id_klient": 7},
    {"id_klient": 7, "id_umowacpc_table": 1},
    {"id_klient": 7, "koszty": 1},
    {"id_klient": 7, "umowa": "x" * 101},
])
def test_create_agreement_rejects_invalid_payload(payload: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.create_agreement(payload)
    assert pool.executed == []
    assert pool.committed == 0


def test_create_agreement_requires_write_permission() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MACHINE_LINKABLE, AGREEMENT_WRITABLE)
    with pytest.raises(WritesDisabled):
        service.create_agreement({"machines": [], "id_klient": 7})
    assert pool.executed == []


def test_create_agreement_rolls_back_database_failure() -> None:
    pool = _Pool([])
    service = make_projection_service(
        pool, MACHINE_LINKABLE, AGREEMENT_WRITABLE, allow_writes=True,
    )
    with pytest.raises(IndexError):
        service.create_agreement({"machines": [], "id_klient": 7})
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_create_agreement_requires_business_and_client_columns() -> None:
    pool = _Pool([])
    service = make_projection_service(
        pool, MACHINE_LINKABLE, UMOWACPC, allow_writes=True,
    )
    with pytest.raises(InvalidRequest):
        service.create_agreement({"machines": [], "id_klient": 7})
    assert pool.executed == []


def test_create_agreement_reserves_table_before_allocating_id() -> None:
    from ks_adapter.sql import build_next_available_id

    pool = _Pool([(None, [(3,)]), (None, [(date(2026, 11, 8),)]),
                  (None, [(12, 3, 7, "3/2026", "", "$_$", 0)])])
    pool.responses.append((None, []))
    service = make_projection_service(
        pool, MACHINE_LINKABLE, AGREEMENT_WRITABLE, allow_writes=True,
    )
    result = service.create_agreement({"machines": [], "id_klient": 7})
    assert pool.reserved_tables == ["UMOWACPC"]
    assert pool.executed[0] == (
        build_next_available_id("UMOWACPC", "ID_UMOWACPC"), None
    )
    assert pool.executed[2][1][0] == 3
    assert result["id_umowacpc"] == 3
    assert pool.committed == 1


@pytest.mark.parametrize("responses", [
    [(None, [])], [(None, [(None,)])], [(None, [(3,)])],
])
def test_create_agreement_allocation_failure_rolls_back(responses: Any) -> None:
    pool = _Pool(responses)
    service = make_projection_service(
        pool, MACHINE_LINKABLE, AGREEMENT_WRITABLE, allow_writes=True,
    )
    with pytest.raises((InvalidRequest, IndexError)):
        service.create_agreement({"machines": [], "id_klient": 7})
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("start_value", [None, "omitted"])
def test_create_agreement_defaults_start_date_and_active_flag(start_value: Any) -> None:
    import datetime as dt

    today = dt.date(2026, 11, 8)
    table = TableInfo("UMOWACPC", "table", None, (
        ColumnInfo("ID_UMOWACPC_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_UMOWACPC", 1, "INTEGER", False),
        ColumnInfo("ID_KLIENT", 2, "INTEGER", False),
        ColumnInfo("U_START", 3, "DATE", True),
        ColumnInfo("AKTYWNA", 4, "VARCHAR(20)", True),
    ))
    pool = _Pool([(None, [(1,)]), (None, [(today,)]),
                  (None, [(12, 1, 7, today, "TAK")])])
    pool.responses.append((None, []))
    service = make_projection_service(pool, MACHINE_LINKABLE, table, allow_writes=True)
    payload = {"machines": [], "id_klient": 7}
    if start_value is None:
        payload["u_start"] = None
    result = service.create_agreement(payload)
    assert pool.executed[1] == ("SELECT CURRENT_DATE FROM RDB$DATABASE", None)
    assert pool.executed[2] == (
        'INSERT INTO "UMOWACPC" ("ID_UMOWACPC", "ID_KLIENT", "AKTYWNA", '
        '"U_START") VALUES (?, ?, ?, ?) RETURNING "ID_UMOWACPC_TABLE", '
        '"ID_UMOWACPC", "ID_KLIENT", "U_START", "AKTYWNA"',
        [1, 7, "TAK", today],
    )
    assert result["u_start"] == "2026-11-08"
    assert result["aktywna"] == "TAK"
    assert pool.committed == 1


def test_create_agreement_preserves_supplied_date_and_active_flag() -> None:
    import datetime as dt

    start = dt.date(2027, 1, 15)
    table = TableInfo("UMOWACPC", "table", None, (
        ColumnInfo("ID_UMOWACPC_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_UMOWACPC", 1, "INTEGER", False),
        ColumnInfo("ID_KLIENT", 2, "INTEGER", False),
        ColumnInfo("U_START", 3, "DATE", True),
        ColumnInfo("AKTYWNA", 4, "VARCHAR(20)", True),
    ))
    pool = _Pool([(None, [(1,)]), (None, [(12, 1, 7, start, "NIE")])])
    pool.responses.append((None, []))
    service = make_projection_service(pool, MACHINE_LINKABLE, table, allow_writes=True)
    result = service.create_agreement({"machines": [],
        "id_klient": 7, "u_start": start, "aktywna": "NIE",
    })
    assert len(pool.executed) == 3
    assert pool.executed[1][1] == [1, 7, start, "NIE"]
    assert result["u_start"] == "2027-01-15"
    assert result["aktywna"] == "NIE"


def test_update_machine_updates_only_supplied_fields() -> None:
    pool = _Pool([(None, [(1,)]),
                  (MASZYNA_RETURNING, [(11, 4, 0, "KONICA", "", None, None)])])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    result = service.update_machine(4, {"id_klient": 0, "Serial": " "})
    assert pool.executed == [
        ('SELECT FIRST 2 1 FROM "MASZYNA" WHERE "ID_MASZYNA" = ?', [4]),
        ('UPDATE "MASZYNA" SET "ID_KLIENT" = ?, "SERIAL" = ? '
         'WHERE "ID_MASZYNA" = ? RETURNING "ID_MASZYNA_TABLE", "ID_MASZYNA", '
         '"ID_KLIENT", "MARKA", "SERIAL", "INSTALACJA", "OPLATA"', [0, "", 4]),
    ]
    assert result["id_maszyna_table"] == 11
    assert result["id_maszyna"] == 4
    assert result["marka"] == "KONICA"
    assert pool.committed == 1
    assert pool.rolled_back == 0


def test_update_machine_preserves_explicit_null_for_nullable_field() -> None:
    pool = _Pool([(None, [(1,)]),
                  (MASZYNA_RETURNING, [(11, 4, 7, None, None, None, None)])])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    assert service.update_machine(4, {"marka": None})["marka"] is None
    assert pool.executed[1][1] == [None, 4]


@pytest.mark.parametrize("payload", [
    {}, {"id_klient": None}, {"id_klient": -1}, {"id_klient": True},
    {"id_maszyna": 1}, {"licznik_total": 1}, {"synwp": 1},
    {"serial": "x" * 101},
])
def test_update_machine_rejects_invalid_fields(payload: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.update_machine(4, payload)
    assert pool.executed == []


@pytest.mark.parametrize("key", [0, -1, True, "4"])
def test_update_machine_rejects_invalid_identifier(key: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.update_machine(key, {"marka": "KONICA"})
    assert pool.executed == []


@pytest.mark.parametrize("row", [None, (None,) * 7])
def test_update_machine_missing_record_rolls_back(row: Any) -> None:
    pool = _Pool([(None, []), (None, [] if row is None else [row])])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    with pytest.raises(RecordNotFound):
        service.update_machine(4, {"marka": "KONICA"})
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_update_machine_rejects_duplicate_business_ids() -> None:
    pool = _Pool([(None, [(1,), (1,)])])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    with pytest.raises(RecordConflict):
        service.update_machine(4, {"marka": "KONICA"})
    assert len(pool.executed) == 1
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_update_machine_rolls_back_database_failure() -> None:
    pool = _Pool([(None, [(1,)])])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    with pytest.raises(IndexError):
        service.update_machine(4, {"marka": "KONICA"})
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_update_machine_requires_write_permission() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE)
    with pytest.raises(WritesDisabled):
        service.update_machine(4, {"marka": "KONICA"})
    assert pool.executed == []


def test_update_machine_rejects_missing_catalog_field() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE, allow_writes=True)
    with pytest.raises(ColumnNotFound):
        service.update_machine(4, {"model": "C224"})
    assert pool.executed == []


def test_update_machine_rejects_null_for_non_nullable_catalog_column() -> None:
    pool = _Pool([])
    table = TableInfo("MASZYNA", "table", None, (
        *MASZYNA_WRITABLE.columns, ColumnInfo("ID_ODDZIAL", 20, "INTEGER", False),
    ))
    service = make_projection_service(pool, table, allow_writes=True)
    with pytest.raises(InvalidRequest, match="id_oddzial.*must not be null"):
        service.update_machine(4, {"id_oddzial": None})
    assert pool.executed == []


def test_update_machine_requires_business_identifier_column() -> None:
    pool = _Pool([])
    table = TableInfo("MASZYNA", "table", None, (
        ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
        ColumnInfo("MARKA", 1, "VARCHAR(100)", True),
    ))
    service = make_projection_service(pool, table, allow_writes=True)
    with pytest.raises(InvalidRequest, match="no ID_MASZYNA key"):
        service.update_machine(4, {"marka": "KONICA"})
    assert pool.executed == []


MACHINE_LINKABLE = TableInfo("MASZYNA", "table", None, (
    ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
    ColumnInfo("ID_MASZYNA", 1, "INTEGER", False),
    ColumnInfo("ID_UMOWACPC", 2, "INTEGER", True),
))


def test_create_agreement_links_machines_in_same_transaction() -> None:
    pool = _Pool([
        (None, [(51,)]), (None, [(date(2026, 11, 8),)]),
        (None, [(12, 51, 7, None, "", "$_$", 0)]), (None, []),
        (None, [(101,)]), (None, [(101,)]),
        (None, [(102,)]), (None, [(102,)]),
    ])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    service.schema = _StubSchema(AGREEMENT_WRITABLE, MACHINE_LINKABLE)
    result = service.create_agreement({"id_klient": 7, "machines": [4, 9, 4]})
    assert result["id_umowacpc"] == 51
    assert pool.executed[3:] == [
        ('UPDATE "MASZYNA" SET "ID_UMOWACPC" = ? WHERE "ID_UMOWACPC" = ?',
         [None, 51]),
        ('SELECT FIRST 2 "ID_MASZYNA_TABLE" FROM "MASZYNA" '
         'WHERE "ID_MASZYNA" = ?', [4]),
        ('UPDATE "MASZYNA" SET "ID_UMOWACPC" = ? WHERE "ID_MASZYNA_TABLE" = ? '
         'RETURNING "ID_MASZYNA_TABLE"', [51, 101]),
        ('SELECT FIRST 2 "ID_MASZYNA_TABLE" FROM "MASZYNA" '
         'WHERE "ID_MASZYNA" = ?', [9]),
        ('UPDATE "MASZYNA" SET "ID_UMOWACPC" = ? WHERE "ID_MASZYNA_TABLE" = ? '
         'RETURNING "ID_MASZYNA_TABLE"', [51, 102]),
    ]
    assert pool.committed == 1
    assert pool.rolled_back == 0


@pytest.mark.parametrize("matches, error", [([], RecordNotFound),
                                             ([(101,), (102,)], RecordConflict)])
def test_create_agreement_link_failure_rolls_back(matches: Any, error: Any) -> None:
    pool = _Pool([(None, [(51,)]), (None, [(date(2026, 11, 8),)]),
                  (None, [(12, 51, 7, None, "", "$_$", 0)]),
                  (None, []), (None, matches)])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    service.schema = _StubSchema(AGREEMENT_WRITABLE, MACHINE_LINKABLE)
    with pytest.raises(error):
        service.create_agreement({"id_klient": 7, "machines": [4]})
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("machines", [None, "4", [0], [-1], [True], ["4"],
                                      [2147483648], [1] * 1001])
def test_agreement_service_rejects_invalid_machine_arrays(machines: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.create_agreement({"id_klient": 7, "machines": machines})
    with pytest.raises(InvalidRequest):
        service.update_agreement(51, {"machines": machines})
    assert pool.executed == []


def test_update_agreement_can_link_machines_without_changing_columns() -> None:
    pool = _Pool([(None, [(12, 51, 7, "OLD", "", "$_$", 0)]),
                  (None, []), (None, [(101,)]), (None, [(101,)])])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    service.schema = _StubSchema(AGREEMENT_WRITABLE, MACHINE_LINKABLE)
    result = service.update_agreement(51, {"machines": [4]})
    assert result["umowa"] == "OLD"
    assert pool.executed[0][1] == [51]
    assert not any(sql.startswith('UPDATE "UMOWACPC"') for sql, _ in pool.executed)
    assert pool.executed[-1][1] == [51, 101]
    assert pool.committed == 1


def test_update_agreement_updates_supplied_fields_and_links_machines() -> None:
    pool = _Pool([(None, [(12, 51, 7, "OLD", "", "$_$", 0)]),
                  (None, [(12, 51, 7, "NEW", None, "$_$", 0)]),
                  (None, []), (None, [(101,)]), (None, [(101,)])])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    service.schema = _StubSchema(AGREEMENT_WRITABLE, MACHINE_LINKABLE)
    result = service.update_agreement(51, {
        "umowa": " NEW ", "opiekun": None, "machines": [4],
    })
    assert result["umowa"] == "NEW"
    assert pool.executed[1] == (
        'UPDATE "UMOWACPC" SET "UMOWA" = ?, "OPIEKUN" = ? '
        'WHERE "ID_UMOWACPC" = ? RETURNING "ID_UMOWACPC_TABLE", "ID_UMOWACPC", '
        '"ID_KLIENT", "UMOWA", "OPIEKUN", "PLATNOSC", "TERMIN"',
        ["NEW", None, 51],
    )
    assert pool.committed == 1


@pytest.mark.parametrize("payload", [{}, {"id_umowacpc": 2},
                                     {"id_klient": None}, {"koszty": 1}])
def test_update_agreement_rejects_invalid_fields(payload: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.update_agreement(51, payload)
    assert pool.executed == []


@pytest.mark.parametrize("rows, error", [([], RecordNotFound),
    ([(12, 51, 7, "", "", "$_$", 0)] * 2, RecordConflict)])
def test_update_agreement_rejects_missing_or_ambiguous_record(
    rows: Any, error: Any,
) -> None:
    pool = _Pool([(None, rows)])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    with pytest.raises(error):
        service.update_agreement(51, {"umowa": "NEW"})
    assert pool.committed == 0
    assert pool.rolled_back == 1


def test_update_agreement_refuses_disabled_writes() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, AGREEMENT_WRITABLE)
    with pytest.raises(WritesDisabled):
        service.update_agreement(51, {"umowa": "NEW"})
    assert pool.executed == []


def test_update_agreement_empty_machine_array_clears_all_links() -> None:
    pool = _Pool([(None, [(12, 51, 7, "OLD", "", "$_$", 0)]), (None, [])])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    service.schema = _StubSchema(AGREEMENT_WRITABLE, MACHINE_LINKABLE)
    result = service.update_agreement(51, {"machines": []})
    assert result["umowa"] == "OLD"
    assert pool.executed[1:] == [(
        'UPDATE "MASZYNA" SET "ID_UMOWACPC" = ? WHERE "ID_UMOWACPC" = ?',
        [None, 51],
    )]
    assert pool.committed == 1


def test_update_agreement_omitted_machine_array_preserves_links() -> None:
    row = (12, 51, 7, "NEW", "", "$_$", 0)
    pool = _Pool([(None, [row]), (None, [row])])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    service.update_agreement(51, {"umowa": "NEW"})
    assert not any('"MASZYNA"' in sql for sql, _ in pool.executed)
    assert pool.committed == 1


CPC_STUB = TableInfo("CPC", "table", None, (
    ColumnInfo("ID_CPC_TABLE", 0, "INTEGER", False),
    ColumnInfo("ID_KLIENT", 1, "INTEGER", False),
    ColumnInfo("ID_MASZYNA", 2, "INTEGER", False),
    ColumnInfo("ID_UMOWACPC", 3, "INTEGER", False),
    ColumnInfo("LICZNIK_MONO_START", 4, "INTEGER", True),
    ColumnInfo("LICZNIK_MONO_END", 5, "INTEGER", True),
    ColumnInfo("ROK", 6, "INTEGER", True),
    ColumnInfo("MIESIAC", 7, "INTEGER", True),
    ColumnInfo("IDVAT", 8, "INTEGER", False),
    ColumnInfo("OPLATA_SUMA", 9, "DECIMAL(10,4)", True),
    ColumnInfo("KOSZTY", 10, "DECIMAL(10,4)", True),
    ColumnInfo("WYNIK", 11, "DECIMAL(10,4)", True),
    ColumnInfo("UWAGI", 12, "VARCHAR(500)", True),
))
CPC_PAYLOAD = {"id_maszyna": 9, "id_umowacpc": 3,
               "rok": 2026, "miesiac": 11}
CPC_ROW = (101, 7, 9, 3, None, None, 2026, 11, 0, 0, 0, 0, "")
CPC_RETURNING = (
    '"ID_CPC_TABLE", "ID_KLIENT", "ID_MASZYNA", "ID_UMOWACPC", '
    '"LICZNIK_MONO_START", "LICZNIK_MONO_END", "ROK", "MIESIAC", "IDVAT", '
    '"OPLATA_SUMA", "KOSZTY", "WYNIK", "UWAGI"'
)


def test_create_cpc_merges_legacy_profile_and_commits() -> None:
    pool = _Pool([(None, [CPC_ROW])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(
        pool, CPC_STUB, AGREEMENT_WRITABLE, allow_writes=True,
    )
    result = service.create_cpc(CPC_PAYLOAD)
    assert pool.executed[1:] == [(
        'INSERT INTO "CPC" ("ID_KLIENT", "ID_MASZYNA", "ID_UMOWACPC", "ROK", '
        '"MIESIAC", "IDVAT", "OPLATA_SUMA", "KOSZTY", "WYNIK", "UWAGI") '
        f'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING {CPC_RETURNING}',
        [7, 9, 3, 2026, 11, 0, 0, 0, 0, ""],
    )]
    assert result["id_cpc_table"] == 101
    assert pool.committed == 1


def test_create_cpc_supplied_values_override_defaults() -> None:
    pool = _Pool([(None, [CPC_ROW])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(
        pool, CPC_STUB, AGREEMENT_WRITABLE, allow_writes=True,
    )
    service.create_cpc({**CPC_PAYLOAD, "oplata_suma": 100, "uwagi": " TEST "})
    assert pool.executed[1][1] == [7, 9, 3, 2026, 11, 100, "TEST", 0, 0, 0]


@pytest.mark.parametrize("change", [
    {"id_klient": -1}, {"id_maszyna": 0}, {"id_umowacpc": True},
    {"rok": 0}, {"rok": 10000}, {"miesiac": 13},
    {"id_cpc_table": 1}, {"uwagi": "x" * 501},
])
def test_create_cpc_rejects_invalid_input(change: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, CPC_STUB, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.create_cpc({**CPC_PAYLOAD, **change})
    assert pool.executed == []


def test_fetch_cpc_combines_search_filters_and_paging() -> None:
    pool = _Pool([(None, [(1,)]), (None, [CPC_ROW])])
    service = make_projection_service(pool, CPC_STUB)
    result = service.fetch_cpc(limit=2, offset=3, search="test", filters=(
        '{"id_maszyna":9,"rok":2026}'
    ))
    assert result["cpc"][0]["id_cpc_table"] == 101
    assert result["total"] == 1
    assert pool.executed[0][1] == ["%test%", 9, 2026]
    assert ' AND "ID_MASZYNA" = ? AND "ROK" = ?' in pool.executed[0][0]
    assert pool.executed[1][0].endswith('ORDER BY "ID_CPC_TABLE" ROWS 4 TO 5')
    assert pool.committed == 0


def test_get_cpc_uses_generated_key() -> None:
    pool = _Pool([(None, [CPC_ROW])])
    service = make_projection_service(pool, CPC_STUB)
    assert service.get_cpc(101)["id_maszyna"] == 9
    assert pool.executed == [(
        f'SELECT {CPC_RETURNING} FROM "CPC" WHERE "ID_CPC_TABLE" = ?', [101]
    )]


def test_update_cpc_changes_only_supplied_fields() -> None:
    pool = _Pool([(None, [CPC_ROW])])
    service = make_projection_service(pool, CPC_STUB, allow_writes=True)
    service.update_cpc(101, {"licznik_mono_end": 1500, "uwagi": None})
    assert pool.executed == [(
        'UPDATE "CPC" SET "LICZNIK_MONO_END" = ?, "UWAGI" = ? '
        f'WHERE "ID_CPC_TABLE" = ? RETURNING {CPC_RETURNING}',
        [1500, None, 101],
    )]
    assert pool.committed == 1


@pytest.mark.parametrize("payload", [
    {}, {"id_klient": 8}, {"id_maszyna": 10}, {"id_umowacpc": 4},
    {"id_cpc_table": 2}, {"miesiac": 13}, {"rok": None}, {"idvat": None},
])
def test_update_cpc_rejects_invalid_fields(payload: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, CPC_STUB, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.update_cpc(101, payload)
    assert pool.executed == []


def test_delete_cpc_uses_builder_and_commits() -> None:
    pool = _Pool([(None, [(101,)])])
    service = make_projection_service(pool, CPC_STUB, allow_writes=True)
    assert service.delete_cpc(101) is None
    assert pool.executed == [(
        'DELETE FROM "CPC" WHERE "ID_CPC_TABLE" = ? RETURNING "ID_CPC_TABLE"', [101]
    )]
    assert pool.committed == 1


@pytest.mark.parametrize("method", ["update_cpc", "delete_cpc"])
@pytest.mark.parametrize("row", [None, (None,) * 13])
def test_missing_cpc_write_rolls_back(method: str, row: Any) -> None:
    pool = _Pool([(None, [] if row is None else [row])])
    service = make_projection_service(pool, CPC_STUB, allow_writes=True)
    args = (101, {"uwagi": "TEST"}) if method == "update_cpc" else (101,)
    with pytest.raises(RecordNotFound):
        getattr(service, method)(*args)
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("method", ["create_cpc", "update_cpc", "delete_cpc"])
def test_cpc_writes_are_disabled_by_default(method: str) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, CPC_STUB)
    args = (CPC_PAYLOAD,) if method == "create_cpc" else (
        (101, {"uwagi": "TEST"}) if method == "update_cpc" else (101,)
    )
    with pytest.raises(WritesDisabled):
        getattr(service, method)(*args)
    assert pool.executed == []


@pytest.mark.parametrize("method", ["create_cpc", "update_cpc", "delete_cpc"])
def test_cpc_database_failure_rolls_back(method: str) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, CPC_STUB, AGREEMENT_WRITABLE, allow_writes=True)
    args = (CPC_PAYLOAD,) if method == "create_cpc" else (
        (101, {"uwagi": "TEST"}) if method == "update_cpc" else (101,)
    )
    with pytest.raises(IndexError):
        getattr(service, method)(*args)
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("key", [-1, True, "101"])
def test_cpc_validates_record_key(key: Any) -> None:
    service = make_projection_service(_Pool([]), CPC_STUB, allow_writes=True)
    for method, args in [(service.get_cpc, (key,)),
                         (service.update_cpc, (key, {"uwagi": "TEST"})),
                         (service.delete_cpc, (key,))]:
        with pytest.raises(InvalidRequest):
            method(*args)


def test_get_cpc_reports_missing_record() -> None:
    service = make_projection_service(_Pool([(None, [])]), CPC_STUB)
    with pytest.raises(RecordNotFound):
        service.get_cpc(101)


def test_get_cpc_accepts_legacy_zero_record_key() -> None:
    row = (0, *CPC_ROW[1:])
    pool = _Pool([(None, [row])])
    service = make_projection_service(pool, CPC_STUB)
    assert service.get_cpc(0)["id_cpc_table"] == 0
    assert pool.executed[0][1] == [0]


@pytest.mark.parametrize("period, expected", [
    ({}, (2027, 1)), ({"rok": 2025}, (2025, 1)),
    ({"miesiac": 12}, (2027, 12)), ({"rok": None, "miesiac": None}, (2027, 1)),
])
def test_create_cpc_defaults_missing_period_from_database_date(
    period: dict[str, Any], expected: tuple[int, int],
) -> None:
    import datetime as dt
    import re

    row = (*CPC_ROW[:6], *expected, *CPC_ROW[8:])
    pool = _Pool([(None, [(dt.date(2027, 1, 1),)]), (None, [row])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(
        pool, CPC_STUB, AGREEMENT_WRITABLE, allow_writes=True,
    )
    result = service.create_cpc({"id_klient": 7, "id_maszyna": 9,
                               "id_umowacpc": 3, **period})
    assert pool.executed[1] == ("SELECT CURRENT_DATE FROM RDB$DATABASE", None)
    sql, params = pool.executed[2]
    columns = re.findall(r'"([^"]+)"', sql.split("VALUES")[0])[1:]
    inserted = dict(zip(columns, params))
    assert (inserted["ROK"], inserted["MIESIAC"]) == expected
    assert (result["rok"], result["miesiac"]) == expected
    assert pool.committed == 1


def test_create_cpc_rolls_back_when_database_date_is_missing() -> None:
    pool = _Pool([(None, [])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(
        pool, CPC_STUB, AGREEMENT_WRITABLE, allow_writes=True,
    )
    from ks_adapter.errors import DatabaseUnavailable

    with pytest.raises(DatabaseUnavailable):
        service.create_cpc({"id_klient": 7, "id_maszyna": 9, "id_umowacpc": 3})
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("number", [None, "", "   ", "omitted"])
def test_create_agreement_defaults_number_to_generated_id_and_current_year(
    number: str | None,
) -> None:
    table = TableInfo("UMOWACPC", "table", None, (
        *AGREEMENT_WRITABLE.columns, ColumnInfo("U_START", 7, "DATE", True),
    ))
    # An explicitly supplied start date must not determine the numbering year.
    pool = _Pool([(None, [(4,)]), (None, [(date(2027, 1, 1),)]),
                  (None, [(12, 4, 7, "4/2027", "", date(2025, 1, 1), "$_$", 0)])])
    pool.responses.append((None, []))
    service = make_projection_service(pool, MACHINE_LINKABLE, table, allow_writes=True)
    payload = {"machines": [], "id_klient": 7, "u_start": date(2025, 1, 1)}
    if number != "omitted":
        payload["umowa"] = number
    result = service.create_agreement(payload)
    assert result["umowa"] == "4/2027"
    assert pool.executed[1] == ("SELECT CURRENT_DATE FROM RDB$DATABASE", None)
    assert "4/2027" in pool.executed[2][1]
    assert date(2025, 1, 1) in pool.executed[2][1]
    assert pool.committed == 1


def test_create_machine_uses_full_legacy_profile_and_caller_overrides() -> None:
    from ks_adapter.service import MACHINE_INSERT_DEFAULTS, MACHINE_COLUMNS
    import re

    columns = [
        ColumnInfo("ID_MASZYNA_TABLE", 0, "INTEGER", False),
        ColumnInfo("ID_MASZYNA", 1, "INTEGER", False),
        ColumnInfo("ID_KLIENT", 2, "INTEGER", False),
        *[ColumnInfo(name, i + 2, "VARCHAR(2000)", True)
          for i, name in enumerate(MACHINE_INSERT_DEFAULTS)],
    ]
    table = TableInfo("MASZYNA", "table", None, tuple(columns))
    selected = [name for name in MACHINE_COLUMNS if name in table.column_map]
    row = tuple(11 if name == "ID_MASZYNA_TABLE" else 4 if name == "ID_MASZYNA"
                else None for name in selected)
    pool = _Pool([(None, [row])])
    pool.responses.insert(0, (None, [(7,)]))
    service = make_projection_service(pool, KLIENT, table, allow_writes=True)
    service.create_machine({
        "id_klient": 7, "marka": "KONICA", "id_oddzial": 1, "aktywna": "NIE",
        "kolorowa": "TAK", "rodzaj_us": "CPC",
    })
    sql, params = pool.executed[1]
    names = re.findall(r'"([^"]+)"', sql.split("VALUES")[0])[1:]
    inserted = dict(zip(names, params))
    assert inserted == {**MACHINE_INSERT_DEFAULTS, "ID_KLIENT": 7, "MARKA": "KONICA",
        "ID_ODDZIAL": 1, "AKTYWNA": "NIE", "KOLOROWA": "TAK", "RODZAJ_US": "CPC"}
    assert inserted["SYNWP"] == 0
    assert inserted["MKOD"] == ""
    assert pool.committed == 1



def test_delete_agreement_commits_bound_delete() -> None:
    pool = _Pool([(None, [(51,)]), (None, []), (None, [(51,)])])
    service = make_projection_service(
        pool, UMOWACPC, MACHINE_LINKABLE, allow_writes=True
    )
    assert service.delete_agreement(51) is None
    assert pool.executed == [
        ('SELECT FIRST 2 "ID_UMOWACPC" FROM "UMOWACPC" '
         'WHERE "ID_UMOWACPC" = ?', [51]),
        ('SELECT FIRST 1 "ID_UMOWACPC" FROM "MASZYNA" '
         'WHERE "ID_UMOWACPC" = ?', [51]),
        ('DELETE FROM "UMOWACPC" WHERE "ID_UMOWACPC" = ? '
         'RETURNING "ID_UMOWACPC"', [51]),
    ]
    assert pool.reserved_tables == ["UMOWACPC"]
    assert pool.committed == 1
    assert pool.rolled_back == 0


@pytest.mark.parametrize("rows, error", [
    ([], RecordNotFound), ([(51,), (51,)], RecordConflict),
])
def test_delete_agreement_rejects_missing_or_duplicate_ids(
    rows: Any, error: Any,
) -> None:
    pool = _Pool([(None, rows)])
    service = make_projection_service(pool, UMOWACPC, allow_writes=True)
    with pytest.raises(error):
        service.delete_agreement(51)
    assert len(pool.executed) == 1
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("table", ["MASZYNA", "CPC", "FAKTURA", "LOCKT"])
def test_delete_agreement_preserves_referencing_records(table: str) -> None:
    reference = TableInfo(table, "table", None, (
        ColumnInfo("ID_UMOWACPC", 0, "INTEGER", True),
    ))
    pool = _Pool([(None, [(51,)]), (None, [(51,)])])
    service = make_projection_service(pool, UMOWACPC, reference, allow_writes=True)
    with pytest.raises(RecordConflict, match=table):
        service.delete_agreement(51)
    assert not any(sql.startswith("DELETE") for sql, _ in pool.executed)
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("key", [0, -1, True, None, "51"])
def test_delete_agreement_validates_id_before_sql(key: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, UMOWACPC, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.delete_agreement(key)
    assert pool.executed == []


def test_delete_agreement_refuses_disabled_writes() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, UMOWACPC)
    with pytest.raises(WritesDisabled):
        service.delete_agreement(51)
    assert pool.executed == []


@pytest.mark.parametrize("fields", [
    {}, {"marka": None}, {"marka": ""}, {"marka": "   "}, {"marka": 123},
])
def test_create_machine_service_requires_manufacturer(fields: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA_WRITABLE, KLIENT, allow_writes=True)
    with pytest.raises(InvalidRequest, match="marka"):
        service.create_machine({"id_klient": 7, **fields})
    assert pool.executed == []



def test_delete_machine_uses_business_key_and_commits() -> None:
    pool = _Pool([(None, [(4,)]), (None, [(4,)])])
    service = make_projection_service(pool, MASZYNA, allow_writes=True)
    assert service.delete_machine(4) is None
    assert pool.executed == [
        ('SELECT FIRST 2 "ID_MASZYNA" FROM "MASZYNA" '
         'WHERE "ID_MASZYNA" = ?', [4]),
        ('DELETE FROM "MASZYNA" WHERE "ID_MASZYNA" = ? '
         'RETURNING "ID_MASZYNA"', [4]),
    ]
    assert pool.reserved_tables == ["MASZYNA"]
    assert pool.committed == 1
    assert pool.rolled_back == 0


@pytest.mark.parametrize("matches, error", [
    ([], RecordNotFound), ([(4,), (4,)], RecordConflict),
])
def test_delete_machine_missing_or_ambiguous_rolls_back(
    matches: Any, error: Any,
) -> None:
    pool = _Pool([(None, matches)])
    service = make_projection_service(pool, MASZYNA, allow_writes=True)
    with pytest.raises(error):
        service.delete_machine(4)
    assert len(pool.executed) == 1
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("returned", [[], [(None,)]])
def test_delete_machine_missing_returning_rolls_back(returned: Any) -> None:
    pool = _Pool([(None, [(4,)]), (None, returned)])
    service = make_projection_service(pool, MASZYNA, allow_writes=True)
    with pytest.raises(RecordNotFound):
        service.delete_machine(4)
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("key", [0, -1, True, None, "4"])
def test_delete_machine_validates_id_before_sql(key: Any) -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA, allow_writes=True)
    with pytest.raises(InvalidRequest):
        service.delete_machine(key)
    assert pool.executed == []


def test_delete_machine_refuses_disabled_writes() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, MASZYNA)
    with pytest.raises(WritesDisabled):
        service.delete_machine(4)
    assert pool.executed == []



def test_create_agreement_service_requires_machine_list() -> None:
    pool = _Pool([])
    service = make_projection_service(pool, AGREEMENT_WRITABLE, allow_writes=True)
    with pytest.raises(InvalidRequest, match="machines"):
        service.create_agreement({"id_klient": 7})
    assert pool.executed == []


@pytest.mark.parametrize("agreements, error", [
    ([], RecordNotFound), ([(7,), (8,)], RecordConflict),
    ([(None,)], InvalidRequest), ([(0,)], InvalidRequest),
])
def test_create_cpc_rejects_invalid_agreement_before_insert(
    agreements: Any, error: Any,
) -> None:
    pool = _Pool([(None, agreements)])
    service = make_projection_service(
        pool, CPC_STUB, AGREEMENT_WRITABLE, allow_writes=True,
    )
    with pytest.raises(error):
        service.create_cpc(CPC_PAYLOAD)
    assert pool.executed == [(
        'SELECT FIRST 2 "ID_KLIENT" FROM "UMOWACPC" WHERE "ID_UMOWACPC" = ?', [3],
    )]
    assert pool.committed == 0
    assert pool.rolled_back == 1


@pytest.mark.parametrize("client_id", [None, 7, 8])
def test_create_cpc_supplied_client_must_match_agreement(client_id: Any) -> None:
    pool = _Pool([(None, [(7,)]), (None, [CPC_ROW])])
    service = make_projection_service(
        pool, CPC_STUB, AGREEMENT_WRITABLE, allow_writes=True,
    )
    payload = {**CPC_PAYLOAD, "id_klient": client_id}
    if client_id == 8:
        with pytest.raises(InvalidRequest, match="match"):
            service.create_cpc(payload)
        assert len(pool.executed) == 1
        assert pool.committed == 0
        assert pool.rolled_back == 1
    else:
        assert service.create_cpc(payload)["id_klient"] == 7
        assert pool.executed[1][1][0] == 7
        assert pool.committed == 1
