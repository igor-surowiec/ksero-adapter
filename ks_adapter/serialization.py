"""Conversion of Firebird values into JSON-serialisable structures.

``fdb`` returns Python objects such as ``decimal.Decimal``, ``datetime.datetime``,
``datetime.date``, ``datetime.time``, ``str`` (text BLOBs) and ``bytes`` (binary
BLOBs).  FastAPI cannot serialise some of them directly, so every row is passed
through :func:`to_jsonable` before it is returned to the client.
"""

from __future__ import annotations

import base64
import datetime as dt
import math
from decimal import Decimal
from typing import Any, Iterable, Sequence


def to_jsonable(
    value: Any,
    *,
    decimal_as_string: bool = False,
    blob_encoding: str = "utf-8",
) -> Any:
    """Convert a single Firebird value to a JSON-compatible object."""
    if value is None or isinstance(value, (bool, int, str)):
        return value

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, Decimal):
        if not value.is_finite():
            return str(value) if decimal_as_string else None
        return str(value) if decimal_as_string else float(value)

    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()

    if isinstance(value, dt.timedelta):
        return value.total_seconds()

    if isinstance(value, (bytes, bytearray, memoryview)):
        data = bytes(value)
        try:
            return data.decode(blob_encoding)
        except UnicodeDecodeError:
            return {
                "base64": base64.b64encode(data).decode("ascii"),
                "length": len(data),
            }

    if isinstance(value, (list, tuple)):
        return [
            to_jsonable(item, decimal_as_string=decimal_as_string, blob_encoding=blob_encoding)
            for item in value
        ]

    if isinstance(value, dict):
        return {
            str(key): to_jsonable(
                item, decimal_as_string=decimal_as_string, blob_encoding=blob_encoding
            )
            for key, item in value.items()
        }

    return str(value)


def unique_column_names(
    description: Sequence[Sequence[Any]] | None, *, fallback: str = "column"
) -> list[str]:
    """Return cursor column names, disambiguating duplicates (``NAME_2``, ...)."""
    names: list[str] = []
    seen: dict[str, int] = {}
    for index, entry in enumerate(description or ()):
        raw_name = entry[0] if entry and entry[0] is not None else None
        name = str(raw_name) if raw_name is not None else f"{fallback}_{index + 1}"
        count = seen.get(name, 0) + 1
        seen[name] = count
        names.append(name if count == 1 else f"{name}_{count}")
    return names


def row_to_dict(
    row: Sequence[Any],
    names: Sequence[str],
    *,
    decimal_as_string: bool = False,
    blob_encoding: str = "utf-8",
) -> dict[str, Any]:
    """Turn a row tuple into a dict with JSON-compatible values."""
    return {
        name: to_jsonable(
            value, decimal_as_string=decimal_as_string, blob_encoding=blob_encoding
        )
        for name, value in zip(names, row)
    }


def serialize_rows(
    description: Sequence[Sequence[Any]] | None,
    rows: Iterable[Sequence[Any]],
    *,
    decimal_as_string: bool = False,
    blob_encoding: str = "utf-8",
) -> tuple[list[str], list[dict[str, Any]]]:
    """Serialise a cursor result set into column names and list of row dicts."""
    names = unique_column_names(description)
    serialized = [
        row_to_dict(
            row,
            names,
            decimal_as_string=decimal_as_string,
            blob_encoding=blob_encoding,
        )
        for row in rows
    ]
    return names, serialized
