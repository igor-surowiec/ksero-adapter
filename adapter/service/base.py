"""Shared database lifecycle, queries and transaction helpers."""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence

from ..config import AppSettings
from ..errors import (
    ColumnNotFound,
    DatabaseUnavailable,
    InvalidRequest,
    RecordNotFound,
    WritesDisabled,
)
from ..pool import ConnectionPool
from ..schema import SchemaCache, TableInfo
from ..serialization import row_to_dict, serialize_rows
from ..sql import (
    build_search,
    build_where,
    ensure_read_only,
    parse_filters,
    quote_identifier,
)


def _insert_plan(
    prepared: Mapping[str, Any],
    defaults: Mapping[str, Any],
    column_map: Mapping[str, Any],
) -> tuple[list[str], list[Any]]:
    """Merge a prepared write payload with the legacy default profile.

    The caller's columns come first, in the order
    :meth:`DatabaseService._prepared_write_values` produced them, followed by
    the default columns the payload did not touch.  Columns the connected
    database does not have are dropped, so a snapshot of an older catalog still
    produces a valid statement.  Returns the column names and the matching
    parameter values, both in statement order.
    """
    merged = {**defaults, **prepared}
    ordered = dict.fromkeys((*prepared, *defaults))
    columns = [column for column in ordered if column in column_map]
    return columns, [merged[column] for column in columns]


class BaseDatabaseService:
    """Own the shared pool/cache and generic query, write and paging helpers."""

    def __init__(
        self, settings: AppSettings, pool: ConnectionPool | None = None
    ) -> None:
        self.settings = settings
        self.pool = pool if pool is not None else ConnectionPool(settings.database)
        self.schema = SchemaCache(self.pool, settings.api.schema_cache_ttl)

    def close(self) -> None:
        self.pool.close()

    def health(self) -> dict[str, Any]:
        """Ping the database and report pool statistics."""
        started = time.perf_counter()
        version = self.pool.ping()
        return {
            "status": "ok",
            "database": {
                "dsn": self.settings.database.dsn,
                "charset": self.settings.database.charset,
                "server_version": version,
            },
            "pool": self.pool.stats,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }

    def list_tables(self) -> list[dict[str, Any]]:
        tables = self.schema.tables()
        return [tables[name].to_dict() for name in sorted(tables, key=str.upper)]

    def describe_table(self, table: str) -> dict[str, Any]:
        return self.schema.get(table).to_dict(include_columns=True)

    def refresh_schema(self) -> int:
        """Drop the cached metadata and reload it, returning the table count."""
        self.schema.invalidate()
        return len(self.schema.tables())

    def fetch_rows(
        self,
        table: str,
        *,
        limit: int | None = None,
        offset: int = 0,
        order_by: str | None = None,
        filters: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of rows with optional ordering and JSON filters."""
        info = self.schema.get(table)
        limit = self.check_limit(limit)
        if offset < 0:
            raise InvalidRequest("'offset' must not be negative")

        where_sql, params = build_where(parse_filters(filters), info.column_map)
        order_sql = self._order_clause(order_by, info)
        table_sql = quote_identifier(info.name)
        count_sql = f"SELECT COUNT(*) FROM {table_sql}{where_sql}"
        page_sql = (
            f"SELECT * FROM {table_sql}{where_sql}{order_sql} "
            f"ROWS {offset + 1} TO {offset + limit}"
        )

        with self.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(count_sql, params or None)
                row = cursor.fetchone()
                total = int(row[0]) if row and row[0] is not None else 0
                cursor.execute(page_sql, params or None)
                columns, rows = serialize_rows(
                    cursor.description,
                    cursor.fetchall(),
                    decimal_as_string=self.settings.api.decimal_as_string,
                    blob_encoding=self.settings.api.blob_encoding,
                )
            finally:
                cursor.close()

        return {
            "table": info.name,
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def _projection_page(
        self,
        table: str,
        columns: Sequence[str],
        search_columns: Sequence[str],
        *,
        limit: int | None,
        offset: int,
        search: str | None,
        order_columns: Sequence[str],
        label: str,
        filters: str | None = None,
    ) -> dict[str, Any]:
        """Page through a stable projection of ``table``.

        Shared implementation of ``/clients``, ``/cpc-agreements``,
        ``/machines``, ``/orders`` and ``/invoices``: selects only the
        ``columns`` that exist in the database,
        applies the optional ``search`` substring, orders by ``order_columns``
        (first available wins) and returns ``total``/``count``/``limit``/
        ``offset`` plus ``rows`` keyed by the lower-cased column names, so the
        JSON speaks the same Polish vocabulary as the database.
        """
        info = self.schema.get(table)
        limit = self.check_limit(limit)
        if offset < 0:
            raise InvalidRequest("'offset' must not be negative")

        selected = [column for column in columns if column.upper() in info.column_map]
        if not selected:
            raise InvalidRequest(
                f"Table '{info.name}' does not contain the expected {label} columns"
            )

        where_sql, params = build_search(search, info.column_map, search_columns)
        filter_sql, filter_params = build_where(parse_filters(filters), info.column_map)
        if filter_sql:
            where_sql += (" AND " + filter_sql[7:]) if where_sql else filter_sql
            params.extend(filter_params)
        select_sql = ", ".join(quote_identifier(column) for column in selected)
        table_sql = quote_identifier(info.name)
        order_sql = self._default_order_clause(info, order_columns)
        count_sql = f"SELECT COUNT(*) FROM {table_sql}{where_sql}"
        page_sql = (
            f"SELECT {select_sql} FROM {table_sql}{where_sql}{order_sql} "
            f"ROWS {offset + 1} TO {offset + limit}"
        )

        with self.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(count_sql, params or None)
                row = cursor.fetchone()
                total = int(row[0]) if row and row[0] is not None else 0
                cursor.execute(page_sql, params or None)
                raw_rows = cursor.fetchall()
            finally:
                cursor.close()

        keys = [column.lower() for column in selected]
        rows = [self._serialize_row(keys, row) for row in raw_rows]
        return {
            "total": total,
            "count": len(rows),
            "limit": limit,
            "offset": offset,
            "rows": rows,
        }

    def run_query(
        self,
        sql: str,
        *,
        limit: int | None = None,
        parameters: Sequence[Any] | None = None,
    ) -> dict[str, Any]:
        """Execute a single read-only statement and return at most ``limit`` rows."""
        statement = ensure_read_only(sql)
        limit = self.check_limit(
            limit,
            maximum=self.settings.api.max_query_rows,
            default=self.settings.api.max_query_rows,
        )
        params = self._check_parameters(parameters)

        with self.pool.session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, params)
                if cursor.description is None:
                    return {
                        "columns": [],
                        "rows": [],
                        "row_count": 0,
                        "truncated": False,
                    }
                fetched = cursor.fetchmany(limit + 1)
                truncated = len(fetched) > limit
                if truncated:
                    fetched = fetched[:limit]
                columns, rows = serialize_rows(
                    cursor.description,
                    fetched,
                    decimal_as_string=self.settings.api.decimal_as_string,
                    blob_encoding=self.settings.api.blob_encoding,
                )
            finally:
                cursor.close()

        return {
            "columns": columns,
            "rows": rows,
            "row_count": len(rows),
            "truncated": truncated,
        }

    @staticmethod
    def _check_client_id(id_klient: int) -> None:
        if (
            not isinstance(id_klient, int)
            or isinstance(id_klient, bool)
            or id_klient < 1
        ):
            raise InvalidRequest("'id_klient' must be a positive integer")

    def _require_writes(self) -> None:
        if not self.settings.api.allow_writes:
            raise WritesDisabled(
                "Writes are disabled; enable 'api.allow_writes' (KS_ALLOW_WRITES)"
            )

    def _write_row(
        self,
        table: str,
        selected: Sequence[str],
        statement: str,
        params: Sequence[Any],
        *,
        not_found: RecordNotFound | None = None,
    ) -> dict[str, Any]:
        """Execute a curated write and serialise RETURNING before committing."""
        with self.pool.write_session() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(statement, params)
                raw_row = cursor.fetchone()
                # Firebird 2.5 returns a NULL-filled RETURNING row for no match.
                if not_found is not None and (
                    raw_row is None or all(value is None for value in raw_row)
                ):
                    raise not_found
                if raw_row is None:
                    raise DatabaseUnavailable(
                        f"Firebird did not return the row written to '{table}'"
                    )
                return self._serialize_row([c.lower() for c in selected], raw_row)
            finally:
                cursor.close()

    def _serialize_row(
        self, names: Sequence[str], row: Sequence[Any]
    ) -> dict[str, Any]:
        return row_to_dict(
            row, names,
            decimal_as_string=self.settings.api.decimal_as_string,
            blob_encoding=self.settings.api.blob_encoding,
        )

    @staticmethod
    def _prepared_write_values(
        values: Mapping[str, Any],
        allowed: Sequence[str],
        lengths: Mapping[str, int],
        *,
        preserve_empty: bool = False,
    ) -> dict[str, Any]:
        """Validate and normalise the fields of a curated write payload.

        Keys are matched case-insensitively against ``allowed``, strings are
        trimmed and a blank string counts as "not supplied", so the calling write
        falls back to its own default for that column (the legacy profile of
        :data:`CLIENT_INSERT_DEFAULTS`, or the database default).  The result
        follows the order of ``allowed``, which keeps the generated statement
        stable, and a field outside that list is refused instead of being dropped
        silently. With ``preserve_empty``, explicit nulls and blanks are kept
        for partial updates instead of invoking insert defaults.
        """
        if not isinstance(values, Mapping):
            raise InvalidRequest("Fields must be a JSON object")

        supplied: dict[str, Any] = {}
        for key, value in values.items():
            column = str(key).strip().upper()
            if column not in allowed:
                raise InvalidRequest(f"Unknown field '{key}'")
            supplied[column] = value

        prepared: dict[str, Any] = {}
        for column in allowed:
            if column not in supplied:
                continue
            value = supplied[column]
            if value is None and not preserve_empty:
                continue
            if isinstance(value, str):
                value = value.strip()
                maximum = lengths.get(column)
                if maximum is not None and len(value) > maximum:
                    raise InvalidRequest(
                        f"'{column.lower()}' must not be longer than "
                        f"{maximum} characters"
                    )
                if not value and not preserve_empty:
                    continue
            prepared[column] = value
        return prepared

    def check_limit(
        self, limit: int | None, *,
        maximum: int | None = None, default: int | None = None
    ) -> int:
        """Validate a requested page size against the configured limits."""
        api = self.settings.api
        bound = api.max_limit if maximum is None else maximum
        fallback = api.default_limit if default is None else default
        value = fallback if limit is None else int(limit)
        if value < 1:
            raise InvalidRequest("'limit' must be at least 1")
        if value > bound:
            raise InvalidRequest(f"'limit' must not exceed {bound}")
        return value

    @staticmethod
    def _default_order_clause(info: TableInfo, columns: Sequence[str]) -> str:
        """Order by the first available of ``columns``, so pages stay stable."""
        parts = [
            quote_identifier(info.column_map[column])
            for column in columns
            if column in info.column_map
        ]
        return f" ORDER BY {', '.join(parts)}" if parts else ""

    def _order_clause(self, order_by: str | None, info: TableInfo) -> str:
        if not order_by or not order_by.strip():
            return ""
        parts: list[str] = []
        for token in order_by.split(","):
            token = token.strip()
            if not token:
                continue
            pieces = token.split()
            if len(pieces) > 2:
                raise InvalidRequest(
                    f"Invalid 'order_by' entry '{token}', expected 'COLUMN [ASC|DESC]'"
                )
            direction = "ASC"
            if len(pieces) == 2:
                direction = pieces[1].upper()
                if direction not in {"ASC", "DESC"}:
                    raise InvalidRequest(
                        f"Invalid sort direction '{pieces[1]}' in 'order_by'"
                    )
            canonical = info.column_map.get(pieces[0].upper())
            if canonical is None:
                raise ColumnNotFound(f"Unknown column '{pieces[0]}' in 'order_by'")
            parts.append(f"{quote_identifier(canonical)} {direction}")
        return f" ORDER BY {', '.join(parts)}" if parts else ""

    @staticmethod
    def _check_parameters(parameters: Sequence[Any] | None) -> list[Any] | None:
        if parameters is None:
            return None
        if not isinstance(parameters, (list, tuple)):
            raise InvalidRequest("'parameters' must be a JSON array")
        for index, value in enumerate(parameters):
            if value is None or isinstance(value, (str, bool, int, float)):
                continue
            raise InvalidRequest(
                f"Parameter {index} must be a string, number, boolean or null"
            )
        return list(parameters) or None
