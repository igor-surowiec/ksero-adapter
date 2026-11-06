"""Business logic for browsing tables and running read-only queries."""

from __future__ import annotations

import logging
import time
from typing import Any, Sequence

from .config import AppSettings
from .errors import ColumnNotFound, InvalidRequest
from .pool import ConnectionPool
from .schema import SchemaCache, TableInfo
from .serialization import serialize_rows, to_jsonable
from .sql import (
    build_search,
    build_where,
    ensure_read_only,
    parse_filters,
    quote_identifier,
)

logger = logging.getLogger(__name__)

#: Table holding contractors/clients in the BAZAMS schema.
CLIENTS_TABLE = "KLIENT"

#: Columns exposed by ``GET /clients`` mapped to their JSON field names.
CLIENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("ID_KLIENT_TABLE", "id"),
    ("ID_KLIENT", "client_id"),
    ("NAZWA", "name"),
    ("NAZWA_S", "short_name"),
    ("NIP", "nip"),
    ("REGON", "regon"),
    ("ADRES", "address"),
    ("KOD", "postcode"),
    ("POCZTA", "city"),
    ("WOJEWODZTWO", "province"),
    ("TELEFON", "phone"),
    ("E_MAIL", "email"),
    ("WWW", "website"),
    ("TYP", "type"),
    ("AKTYWNY", "active"),
    ("PLATNOSC", "payment_method"),
    ("TERMIN", "payment_days"),
    ("RABAT", "discount"),
    ("OSTATNIO", "last_contact"),
)

#: Columns matched by the ``search`` parameter of ``GET /clients``.
CLIENT_SEARCH_COLUMNS: tuple[str, ...] = (
    "NAZWA",
    "NAZWA_S",
    "NIP",
    "REGON",
    "E_MAIL",
    "TELEFON",
    "KOD",
    "POCZTA",
)

#: Table holding service agreements (contracts) in the BAZAMS schema.
AGREEMENTS_TABLE = "UMOWACPC"

#: Columns exposed by ``GET /agreements`` mapped to their JSON field names.
AGREEMENT_FIELDS: tuple[tuple[str, str], ...] = (
    ("ID_UMOWACPC_TABLE", "id"),
    ("ID_UMOWACPC", "agreement_id"),
    ("ID_ODDZIAL", "branch_id"),
    ("ID_KLIENT", "client_id"),
    ("ID_ODBIORCA", "recipient_id"),
    ("ID_FIRMA", "company_id"),
    ("UMOWA", "number"),
    ("TYP", "type"),
    ("HANDLOWIEC", "salesperson"),
    ("OPIEKUN", "supervisor"),
    ("OPIEKUNMAIL", "supervisor_email"),
    ("OPIEKUNTEL", "supervisor_phone"),
    ("U_START", "start_date"),
    ("U_STOP", "end_date"),
    ("WARUNKI", "terms"),
    ("UWAGI", "notes"),
    ("KOSZTY", "costs"),
    ("PRZYCHODY", "revenue"),
    ("WYNIK", "profit"),
    ("RABAT", "discount"),
    ("PLATNOSC", "payment_method"),
    ("TERMIN", "payment_days"),
    ("AKTYWNA", "active"),
    ("STRONY_MONO", "pages_mono"),
    ("STRONY_KOLOR", "pages_color"),
    ("SKANY", "scans"),
    ("FRAEMAIL", "invoice_email"),
    ("PLIK", "file"),
)

#: Columns matched by the ``search`` parameter of ``GET /agreements``.
AGREEMENT_SEARCH_COLUMNS: tuple[str, ...] = (
    "UMOWA",
    "TYP",
    "HANDLOWIEC",
    "OPIEKUN",
    "OPIEKUNMAIL",
    "FRAEMAIL",
    "PLIK",
)



class DatabaseService:
    """Read-only facade over a Firebird database."""

    def __init__(
        self, settings: AppSettings, pool: ConnectionPool | None = None
    ) -> None:
        self.settings = settings
        self.pool = pool if pool is not None else ConnectionPool(settings.database)
        self.schema = SchemaCache(self.pool, settings.api.schema_cache_ttl)

    def close(self) -> None:
        self.pool.close()

    # -- metadata ---------------------------------------------------------
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

    # -- data -------------------------------------------------------------
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

    def fetch_clients(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of contractors from the ``KLIENT`` table.

        Only :data:`CLIENT_FIELDS` are selected, so the response shape stays
        stable even though the physical table has 61 columns.  Columns missing
        from the database are skipped instead of failing the request.
        """
        page = self._projection_page(
            CLIENTS_TABLE,
            CLIENT_FIELDS,
            CLIENT_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("NAZWA", "ID_KLIENT_TABLE"),
            label="client",
        )
        page["clients"] = page.pop("rows")
        return page

    def fetch_agreements(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of agreements from the ``UMOWACPC`` table.

        Like :meth:`fetch_clients` this is a hand-picked projection
        (:data:`AGREEMENT_FIELDS`) of the 83 physical columns, so the printing
        parameters (``FRAPAR*``, ``FRANAZ*``/``IDMAG*``) and per-item prices stay
        out of the payload unless the endpoint is extended explicitly.
        """
        page = self._projection_page(
            AGREEMENTS_TABLE,
            AGREEMENT_FIELDS,
            AGREEMENT_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("UMOWA", "ID_UMOWACPC_TABLE"),
            label="agreement",
        )
        page["agreements"] = page.pop("rows")
        return page

    def _projection_page(
        self,
        table: str,
        fields: Sequence[tuple[str, str]],
        search_columns: Sequence[str],
        *,
        limit: int | None,
        offset: int,
        search: str | None,
        order_columns: Sequence[str],
        label: str,
    ) -> dict[str, Any]:
        """Page through a stable projection of ``table``.

        Shared implementation of ``/clients`` and ``/agreements``: selects only
        the ``fields`` that exist in the database, applies the optional
        ``search`` substring, orders by ``order_columns`` (first available wins)
        and returns ``total``/``count``/``limit``/``offset`` plus ``rows`` keyed
        by the JSON aliases.
        """
        info = self.schema.get(table)
        limit = self.check_limit(limit)
        if offset < 0:
            raise InvalidRequest("'offset' must not be negative")

        selected = [
            (column, alias)
            for column, alias in fields
            if column.upper() in info.column_map
        ]
        if not selected:
            raise InvalidRequest(
                f"Table '{info.name}' does not contain the expected {label} columns"
            )

        where_sql, params = build_search(search, info.column_map, search_columns)
        select_sql = ", ".join(quote_identifier(column) for column, _ in selected)
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

        aliases = [alias for _, alias in selected]
        rows = [
            {
                alias: to_jsonable(
                    value,
                    decimal_as_string=self.settings.api.decimal_as_string,
                    blob_encoding=self.settings.api.blob_encoding,
                )
                for alias, value in zip(aliases, raw_row)
            }
            for raw_row in raw_rows
        ]
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

    # -- helpers ----------------------------------------------------------
    def check_limit(
        self, limit: int | None, *, maximum: int | None = None, default: int | None = None
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


