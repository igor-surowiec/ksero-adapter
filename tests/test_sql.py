"""Tests for the SQL guard and filter builder."""

from __future__ import annotations

import pytest

from ks_adapter.errors import ColumnNotFound, InvalidRequest, QueryNotAllowed
from ks_adapter.sql import (
    LIKE_PARAMETER_BYTES,
    MAX_MESSAGE_BYTES,
    MAX_SEARCH_COLUMNS,
    Filter,
    build_insert,
    build_search,
    build_where,
    ensure_read_only,
    parse_filters,
    quote_identifier,
    strip_sql_literals,
)

COLUMNS = {"ID": "ID", "NAME": "NAME", "TYP": "TYP"}


def test_quote_identifier() -> None:
    assert quote_identifier("APPUSER") == '"APPUSER"'
    assert quote_identifier('we"ird') == '"we""ird"'


def test_quote_identifier_rejects_empty() -> None:
    with pytest.raises(InvalidRequest):
        quote_identifier("")


def test_build_insert_quotes_identifiers_and_binds_values() -> None:
    assert build_insert("KLIENT", ["NAZWA"]) == (
        'INSERT INTO "KLIENT" ("NAZWA") VALUES (?)'
    )
    assert build_insert('we"ird', ["A", "B"], returning=["A"]) == (
        'INSERT INTO "we""ird" ("A", "B") VALUES (?, ?) RETURNING "A"'
    )


def test_build_insert_requires_a_column() -> None:
    with pytest.raises(InvalidRequest):
        build_insert("KLIENT", [])


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1 FROM RDB$DATABASE",
        "  select * from APPUSER  ",
        "SELECT * FROM APPUSER;",
        "WITH x AS (SELECT 1 AS a FROM RDB$DATABASE) SELECT * FROM x",
        "SELECT * FROM APPUSER WHERE NAME = 'delete me'",
        "/* delete */ SELECT * FROM APPUSER",
        "SELECT * FROM APPUSER -- delete everything\nWHERE ID = 1",
    ],
)
def test_ensure_read_only_accepts_selects(sql: str) -> None:
    assert ensure_read_only(sql)


def test_ensure_read_only_strips_trailing_semicolon() -> None:
    assert ensure_read_only("SELECT 1 FROM RDB$DATABASE;") == "SELECT 1 FROM RDB$DATABASE"


@pytest.mark.parametrize(
    "sql",
    [
        "",
        "   ",
        "DELETE FROM APPUSER",
        "UPDATE APPUSER SET NAME = 'x'",
        "INSERT INTO APPUSER (ID) VALUES (1)",
        "SELECT 1 FROM RDB$DATABASE; DROP TABLE APPUSER",
        "EXECUTE BLOCK AS BEGIN END",
        "RECREATE TABLE T (ID INTEGER)",
        "SET GENERATOR G TO 10",
        "COMMIT",
    ],
)
def test_ensure_read_only_rejects_writes(sql: str) -> None:
    with pytest.raises(QueryNotAllowed):
        ensure_read_only(sql)


def test_ensure_read_only_rejects_unterminated_literal() -> None:
    with pytest.raises(QueryNotAllowed):
        ensure_read_only("SELECT * FROM APPUSER WHERE NAME = 'oops")


def test_strip_sql_literals() -> None:
    assert strip_sql_literals("SELECT 'a''b' FROM t -- note").strip() == "SELECT   FROM t"
    assert strip_sql_literals('SELECT "COL" FROM t') == "SELECT   FROM t"
    with pytest.raises(QueryNotAllowed):
        strip_sql_literals("SELECT /* unterminated")


def test_parse_filters_empty() -> None:
    assert parse_filters(None) == []
    assert parse_filters("  ") == []
    assert parse_filters("null") == []


def test_parse_filters_plain_value_is_equality() -> None:
    filters = parse_filters('{"NAME": "ACME"}')
    assert filters == [Filter(column="NAME", operator="eq", value="ACME")]


def test_parse_filters_with_operators() -> None:
    filters = parse_filters('{"ID": {"op": "GT", "value": 5}, "TYP": {"op": "in"}}')
    assert filters[0] == Filter(column="ID", operator="gt", value=5)
    assert filters[1].operator == "in"
    assert filters[1].value is None


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[1, 2]",
        '{"ID": {"value": 1}}',
        '{"ID": {"op": "nope", "value": 1}}',
        '{"ID": {"op": "eq", "value": 1, "extra": true}}',
    ],
)
def test_parse_filters_rejects_bad_input(raw: str) -> None:
    with pytest.raises(InvalidRequest):
        parse_filters(raw)


def test_build_where_returns_empty_clause_without_filters() -> None:
    assert build_where([], COLUMNS) == ("", [])


@pytest.mark.parametrize(
    ("filters", "expected_sql", "expected_params"),
    [
        ([Filter("NAME", "eq", "ACME")], ' WHERE "NAME" = ?', ["ACME"]),
        ([Filter("ID", "ne", 3)], ' WHERE "ID" <> ?', [3]),
        ([Filter("ID", "ge", 3)], ' WHERE "ID" >= ?', [3]),
        ([Filter("ID", "lt", 3)], ' WHERE "ID" < ?', [3]),
        ([Filter("ID", "eq", None)], ' WHERE "ID" IS NULL', []),
        ([Filter("ID", "ne", None)], ' WHERE "ID" IS NOT NULL', []),
        ([Filter("ID", "notnull")], ' WHERE "ID" IS NOT NULL', []),
        ([Filter("TYP", "in", [1, 2])], ' WHERE "TYP" IN (?, ?)', [1, 2]),
        (
            [Filter("NAME", "like", "a%")],
            ' WHERE "NAME" LIKE CAST(? AS VARCHAR(1024))',
            ["a%"],
        ),
        (
            [Filter("NAME", "contains", "bc")],
            ' WHERE "NAME" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\'',
            ["%bc%"],
        ),
        (
            [Filter("NAME", "startswith", "ab")],
            ' WHERE "NAME" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\'',
            ["ab%"],
        ),
        (
            [Filter("NAME", "endswith", "ab")],
            ' WHERE "NAME" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\'',
            ["%ab"],
        ),
    ],
)
def test_build_where_fragments(filters, expected_sql, expected_params) -> None:
    sql, params = build_where(filters, COLUMNS)
    assert sql == expected_sql
    assert params == expected_params


def test_build_where_combines_and_quotes_identifiers() -> None:
    sql, params = build_where(
        [Filter("name", "eq", "ACME"), Filter("ID", "gt", 1)], COLUMNS
    )
    assert sql == ' WHERE "NAME" = ? AND "ID" > ?'
    assert params == ["ACME", 1]


def test_build_where_escapes_like_wildcards() -> None:
    _, params = build_where([Filter("NAME", "contains", "50%_x")], COLUMNS)
    assert params == ["%50\\%\\_x%"]


def test_build_where_unknown_column() -> None:
    with pytest.raises(ColumnNotFound):
        build_where([Filter("NOPE", "eq", 1)], COLUMNS)


@pytest.mark.parametrize(
    "filter_",
    [
        Filter("ID", "gt", None),
        Filter("ID", "in", []),
        Filter("ID", "in", "abc"),
        Filter("NAME", "contains", 5),
        Filter("ID", "eq", {"a": 1}),
    ],
)
def test_build_where_rejects_invalid_values(filter_) -> None:
    with pytest.raises(InvalidRequest):
        build_where([filter_], COLUMNS)


def test_build_search_builds_or_of_like_clauses() -> None:
    sql, params = build_search("ACME", COLUMNS, ["NAME", "TYP", "NOPE"])
    assert sql == (
        ' WHERE ("NAME" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\' '
        'OR "TYP" LIKE CAST(? AS VARCHAR(1024)) ESCAPE \'\\\')'
    )
    assert params == ["%ACME%", "%ACME%"]


@pytest.mark.parametrize("term", [None, "", "   "])
def test_build_search_ignores_blank_terms(term) -> None:
    assert build_search(term, COLUMNS, ["NAME"]) == ("", [])


def test_build_search_escapes_wildcards_and_trims() -> None:
    _, params = build_search("  50%_x ", COLUMNS, ["NAME"])
    assert params == ["%50\\%\\_x%"]


def test_build_search_without_known_columns_is_empty() -> None:
    assert build_search("ACME", COLUMNS, ["NOPE"]) == ("", [])


def test_build_search_rejects_non_strings() -> None:
    with pytest.raises(InvalidRequest):
        build_search(5, COLUMNS, ["NAME"])


def test_like_parameter_budget_matches_firebird_message_limit() -> None:
    """Firebird allows 63 ``VARCHAR(1024)`` predictors, not 64."""
    assert LIKE_PARAMETER_BYTES == 1026
    assert MAX_SEARCH_COLUMNS == 63
    assert MAX_SEARCH_COLUMNS * LIKE_PARAMETER_BYTES <= MAX_MESSAGE_BYTES
    assert (MAX_SEARCH_COLUMNS + 1) * LIKE_PARAMETER_BYTES > MAX_MESSAGE_BYTES


def test_build_search_refuses_too_many_columns() -> None:
    wide = {f"COL{i}": f"COL{i}" for i in range(MAX_SEARCH_COLUMNS + 1)}

    with pytest.raises(InvalidRequest) as excinfo:
        build_search("ACME", wide, sorted(wide))

    assert str(MAX_SEARCH_COLUMNS) in str(excinfo.value)


def test_build_search_accepts_exactly_the_budgeted_number_of_columns() -> None:
    wide = {f"COL{i}": f"COL{i}" for i in range(MAX_SEARCH_COLUMNS)}

    sql, params = build_search("ACME", wide, sorted(wide))

    assert len(params) == MAX_SEARCH_COLUMNS
    assert sql.count("LIKE CAST(? AS VARCHAR(1024))") == MAX_SEARCH_COLUMNS


def test_build_update_quotes_identifiers_and_requires_assignments() -> None:
    from ks_adapter.sql import build_update

    assert build_update('we"ird', ["NAME"], key="ID", returning=["ID"]) == (
        'UPDATE "we""ird" SET "NAME" = ? WHERE "ID" = ? RETURNING "ID"'
    )
    with pytest.raises(InvalidRequest):
        build_update("KLIENT", [], key="ID_KLIENT_TABLE")


def test_build_delete_quotes_identifiers_and_binds_the_key() -> None:
    from ks_adapter.sql import build_delete

    assert build_delete('we"ird', key='I"D') == (
        'DELETE FROM "we""ird" WHERE "I""D" = ? RETURNING "I""D"'
    )
