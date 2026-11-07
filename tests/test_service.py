"""Service-level tests using a scripted fake connection pool."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

import pytest

from ks_adapter.config import ApiSettings, AppSettings, DatabaseSettings, ServerSettings
from ks_adapter.errors import (
    ColumnNotFound,
    InvalidRequest,
    QueryNotAllowed,
    TableNotFound,
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

    @contextmanager
    def session(self) -> Iterator[_Connection]:
        cursor = _Cursor(self.responses)
        yield _Connection(cursor)
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
            "id": 2,
            "client_id": 1,
            "name": "ACME",
            "nip": "1234567890",
            "last_contact": "2024-05-01",
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

    assert page["clients"] == [{"id": 7, "name": "ACME"}]
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
            "id": 5,
            "agreement_id": 5,
            "number": "CPC/2024/001",
            "supervisor": "Kowalski",
            "start_date": "2024-01-01",
            "costs": 1500.5,
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

    assert page["agreements"] == [{"costs": "1500.5000"}]


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

    assert page["agreements"] == [{"id": 3, "number": "CPC/2024/002"}]
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
            "id": 3,
            "machine_id": 2,
            "brand": "KONICA",
            "serial": "SN-0001",
            "install_date": "2024-03-01",
            "technician": "Nowak Anna",
            "costs": 120.0,
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

    assert page["machines"] == [{"fee": "0.1200"}]


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

    assert page["machines"] == [{"id": 3, "brand": "KONICA"}]
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
            "id": 2,
            "order_id": 2,
            "status": "O",
            "client_name": "ACME",
            "brand": "KONICA",
            "order_date": "2026-11-07",
            "technician": "Nowak Anna",
            "gross": 120.5,
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

    assert page["orders"] == [{"gross": "120.5000"}]


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

    assert page["orders"] == [{"id": 2, "status": "O"}]
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
