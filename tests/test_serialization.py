"""Tests for value serialisation."""

from __future__ import annotations

import base64
import datetime as dt
import math
from decimal import Decimal

from adapter.serialization import (
    row_to_dict,
    serialize_rows,
    to_jsonable,
    unique_column_names,
)


def test_scalars_are_returned_unchanged() -> None:
    for value in (None, True, False, 0, 42, 1.5, "Zażółć gęślą jaźń"):
        assert to_jsonable(value) == value


def test_decimal_conversion() -> None:
    assert to_jsonable(Decimal("12.34")) == 12.34
    assert to_jsonable(Decimal("12.34"), decimal_as_string=True) == "12.34"


def test_non_finite_numbers_become_null() -> None:
    assert to_jsonable(math.nan) is None
    assert to_jsonable(math.inf) is None
    assert to_jsonable(Decimal("NaN")) is None
    assert to_jsonable(Decimal("Infinity"), decimal_as_string=True) == "Infinity"


def test_datetime_conversion() -> None:
    assert to_jsonable(dt.datetime(2024, 1, 2, 3, 4, 5)) == "2024-01-02T03:04:05"
    assert to_jsonable(dt.date(2024, 1, 2)) == "2024-01-02"
    assert to_jsonable(dt.time(3, 4, 5)) == "03:04:05"
    assert to_jsonable(dt.timedelta(hours=1, seconds=30)) == 3630.0


def test_bytes_are_decoded_with_configured_encoding() -> None:
    raw = "Zażółć".encode("cp1250")
    assert to_jsonable(raw, blob_encoding="cp1250") == "Zażółć"


def test_binary_blob_falls_back_to_base64() -> None:
    raw = b"\xff\xfe\x00\x01"
    result = to_jsonable(raw, blob_encoding="utf-8")
    assert isinstance(result, dict)
    assert base64.b64decode(result["base64"]) == raw
    assert result["length"] == len(raw)


def test_bytearray_and_memoryview_are_supported() -> None:
    assert to_jsonable(bytearray(b"abc")) == "abc"
    assert to_jsonable(memoryview(b"abc")) == "abc"


def test_nested_containers() -> None:
    result = to_jsonable([1, {"d": Decimal("1.5"), "b": b"ok"}])
    assert result == [1, {"d": 1.5, "b": "ok"}]


def test_unknown_objects_are_stringified() -> None:
    class Custom:
        def __str__(self) -> str:
            return "custom"

    assert to_jsonable(Custom()) == "custom"


def test_unique_column_names_disambiguates_duplicates() -> None:
    description = [("ID",), ("NAME",), ("NAME",), (None,)]
    assert unique_column_names(description) == ["ID", "NAME", "NAME_2", "column_4"]
    assert unique_column_names(None) == []


def test_row_to_dict_uses_column_names() -> None:
    row = (1, Decimal("2.5"), None)
    assert row_to_dict(row, ["A", "B", "C"]) == {"A": 1, "B": 2.5, "C": None}


def test_serialize_rows_returns_names_and_dicts() -> None:
    description = [("A",), ("B",)]
    names, rows = serialize_rows(description, [(1, Decimal("2.5")), (2, Decimal("3"))])
    assert names == ["A", "B"]
    assert rows == [{"A": 1, "B": 2.5}, {"A": 2, "B": 3.0}]
