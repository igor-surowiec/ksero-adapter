"""Introspection of the Firebird system catalog with a TTL cache."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from .errors import DatabaseUnavailable, TableNotFound
from .pool import ConnectionPool

logger = logging.getLogger(__name__)

# RDB$FIELD_TYPE -> Firebird type name (types that carry no length/scale).
_FIELD_TYPES: dict[int, str] = {
    7: "SMALLINT",
    8: "INTEGER",
    10: "FLOAT",
    12: "DATE",
    13: "TIME",
    14: "CHAR",
    16: "BIGINT",
    23: "BOOLEAN",
    26: "INT128",
    27: "DOUBLE PRECISION",
    35: "TIMESTAMP",
    37: "VARCHAR",
    45: "BLOB",
    261: "BLOB",
}

_INTEGER_PRECISION = {7: 5, 8: 10, 16: 19}
_CHARSET_WIDTH = {"UTF8": 4, "UNICODE_FSS": 3, "ISO8859_1": 1, "WIN1250": 1}

_TABLES_SQL = """
SELECT TRIM(r.RDB$RELATION_NAME) AS RELATION_NAME,
       r.RDB$RELATION_TYPE AS RELATION_TYPE,
       r.RDB$DESCRIPTION AS DESCRIPTION
FROM RDB$RELATIONS r
WHERE COALESCE(r.RDB$SYSTEM_FLAG, 0) = 0
ORDER BY 1
"""

_COLUMNS_SQL = """
SELECT TRIM(rf.RDB$RELATION_NAME) AS RELATION_NAME,
       TRIM(rf.RDB$FIELD_NAME) AS FIELD_NAME,
       rf.RDB$FIELD_POSITION AS FIELD_POSITION,
       rf.RDB$NULL_FLAG AS NULL_FLAG,
       rf.RDB$DEFAULT_SOURCE AS DEFAULT_SOURCE,
       f.RDB$FIELD_TYPE AS FIELD_TYPE,
       f.RDB$FIELD_SUB_TYPE AS FIELD_SUB_TYPE,
       f.RDB$FIELD_LENGTH AS FIELD_LENGTH,
       f.RDB$FIELD_PRECISION AS FIELD_PRECISION,
       f.RDB$FIELD_SCALE AS FIELD_SCALE,
       TRIM(cs.RDB$CHARACTER_SET_NAME) AS CHARACTER_SET_NAME
FROM RDB$RELATION_FIELDS rf
JOIN RDB$FIELDS f ON f.RDB$FIELD_NAME = rf.RDB$FIELD_SOURCE
JOIN RDB$RELATIONS r ON r.RDB$RELATION_NAME = rf.RDB$RELATION_NAME
LEFT JOIN RDB$CHARACTER_SETS cs
       ON cs.RDB$CHARACTER_SET_ID = f.RDB$CHARACTER_SET_ID
WHERE COALESCE(r.RDB$SYSTEM_FLAG, 0) = 0
ORDER BY rf.RDB$RELATION_NAME, rf.RDB$FIELD_POSITION
"""


@dataclass(frozen=True)
class ColumnInfo:
    """A column of a user table or view."""

    name: str
    position: int
    type_name: str
    nullable: bool
    default: str | None = None
    charset: str | None = None
    length: int | None = None
    precision: int | None = None
    scale: int | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "position": self.position,
            "type": self.type_name,
            "nullable": self.nullable,
        }
        if self.default:
            data["default"] = self.default
        if self.charset:
            data["charset"] = self.charset
        if self.length is not None:
            data["length"] = self.length
        if self.precision is not None:
            data["precision"] = self.precision
        if self.scale is not None:
            data["scale"] = self.scale
        return data


@dataclass(frozen=True)
class TableInfo:
    """A user table or view together with its columns."""

    name: str
    kind: str
    description: str | None
    columns: tuple[ColumnInfo, ...]

    @property
    def column_map(self) -> dict[str, str]:
        """Map upper-cased column names to their canonical spelling."""
        return {column.name.upper(): column.name for column in self.columns}

    def to_dict(self, include_columns: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "name": self.name,
            "kind": self.kind,
            "column_count": len(self.columns),
        }
        if self.description:
            data["description"] = self.description
        if include_columns:
            data["columns"] = [column.to_dict() for column in self.columns]
        return data


def describe_type(
    field_type: Any,
    sub_type: Any,
    length: Any,
    precision: Any,
    scale: Any,
    charset: Any = None,
) -> str:
    """Build a readable SQL type description from ``RDB$FIELDS`` values."""
    try:
        type_id = int(field_type)
    except (TypeError, ValueError):
        return "UNKNOWN"
    base = _FIELD_TYPES.get(type_id)
    if base is None:
        return f"UNKNOWN({type_id})"

    sub = int(sub_type or 0)
    if base in {"SMALLINT", "INTEGER", "BIGINT"} and scale:
        kind = "DECIMAL" if sub == 2 else "NUMERIC"
        digits = int(precision) if precision else _INTEGER_PRECISION.get(type_id, 0)
        return f"{kind}({digits},{abs(int(scale))})"
    if base in {"VARCHAR", "CHAR"}:
        return f"{base}({_char_length(length, charset)})"
    if base == "BLOB":
        return "BLOB SUB_TYPE TEXT" if sub == 1 else "BLOB"
    return base


def _char_length(length: Any, charset: Any) -> int:
    """Convert a byte length into a character length for the given charset."""
    try:
        byte_length = int(length or 0)
    except (TypeError, ValueError):
        return 0
    width = _CHARSET_WIDTH.get(str(charset or "").strip().upper(), 1)
    return byte_length // width



def _row_dict(cursor: Any, row: tuple[Any, ...]) -> dict[str, Any]:
    names = [str(entry[0]).strip().upper() for entry in cursor.description or ()]
    return dict(zip(names, row))


class SchemaCache:
    """Cache of user tables/views and their columns, refreshed after ``ttl``."""

    def __init__(self, pool: ConnectionPool, ttl: float = 300.0) -> None:
        self._pool = pool
        self._ttl = max(0.0, float(ttl))
        self._lock = threading.Lock()
        self._tables: dict[str, TableInfo] | None = None
        self._loaded_at = 0.0

    def invalidate(self) -> None:
        with self._lock:
            self._tables = None
            self._loaded_at = 0.0

    def tables(self) -> dict[str, TableInfo]:
        """Return all user tables/views keyed by their canonical name."""
        snapshot = self._fresh_snapshot()
        if snapshot is not None:
            return snapshot
        with self._lock:
            snapshot = self._fresh_snapshot()
            if snapshot is not None:
                return snapshot
            tables = self._load()
            self._tables = tables
            self._loaded_at = time.monotonic()
            return tables

    def get(self, name: str) -> TableInfo:
        tables = self.tables()
        info = tables.get(name)
        if info is None:
            wanted = name.strip().upper()
            for candidate in tables.values():
                if candidate.name.upper() == wanted:
                    info = candidate
                    break
        if info is None:
            raise TableNotFound(f"Table or view '{name}' does not exist")
        return info

    def _fresh_snapshot(self) -> dict[str, TableInfo] | None:
        if self._tables is None:
            return None
        if self._ttl == 0:
            return self._tables
        if time.monotonic() - self._loaded_at >= self._ttl:
            return None
        return self._tables

    def _load(self) -> dict[str, TableInfo]:
        try:
            with self._pool.session() as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(_TABLES_SQL)
                    table_rows = [_row_dict(cursor, row) for row in cursor.fetchall()]
                    cursor.execute(_COLUMNS_SQL)
                    column_rows = [_row_dict(cursor, row) for row in cursor.fetchall()]
                finally:
                    cursor.close()
        except Exception as exc:
            raise DatabaseUnavailable(
                f"Unable to read the Firebird system catalog: {exc}"
            ) from exc

        columns_by_table: dict[str, list[ColumnInfo]] = {}
        for row in column_rows:
            table_name = str(row.get("RELATION_NAME") or "").strip()
            column_name = str(row.get("FIELD_NAME") or "").strip()
            if not table_name or not column_name:
                continue
            position = _optional_int(row.get("FIELD_POSITION"))
            charset = _clean_text(row.get("CHARACTER_SET_NAME"))
            columns_by_table.setdefault(table_name, []).append(
                ColumnInfo(
                    name=column_name,
                    position=position if position is not None else 0,
                    type_name=describe_type(
                        row.get("FIELD_TYPE"),
                        row.get("FIELD_SUB_TYPE"),
                        row.get("FIELD_LENGTH"),
                        row.get("FIELD_PRECISION"),
                        row.get("FIELD_SCALE"),
                        charset,
                    ),
                    nullable=not bool(row.get("NULL_FLAG")),
                    default=_clean_text(row.get("DEFAULT_SOURCE")),
                    charset=charset,
                    length=_optional_int(row.get("FIELD_LENGTH")),
                    precision=_optional_int(row.get("FIELD_PRECISION")),
                    scale=_optional_int(row.get("FIELD_SCALE")),
                )
            )

        tables: dict[str, TableInfo] = {}
        for row in table_rows:
            name = str(row.get("RELATION_NAME") or "").strip()
            if not name:
                continue
            relation_type = _optional_int(row.get("RELATION_TYPE")) or 0
            tables[name] = TableInfo(
                name=name,
                kind="view" if relation_type == 1 else "table",
                description=_clean_text(row.get("DESCRIPTION")),
                columns=tuple(
                    sorted(
                        columns_by_table.get(name, ()), key=lambda item: item.position
                    )
                ),
            )
        logger.debug("Loaded metadata for %d tables/views", len(tables))
        return tables


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


