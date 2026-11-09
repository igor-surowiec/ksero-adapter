"""Transaction reservation tests without a live driver connection."""

from __future__ import annotations

import ctypes
from typing import Any

import fdb
import pytest
from fdb import ibase

from adapter.config import DatabaseSettings
from adapter.pool import ConnectionPool, _configure_macos_transactions


class _ClientAPI:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.isc_start_transaction: Any = None

    def isc_start_multiple(
        self, status: Any, transaction: Any, count: int, teb_pointer: Any
    ) -> int:
        teb = ctypes.cast(teb_pointer, ctypes.POINTER(ibase.ISC_TEB)).contents
        tpb_pointer = ctypes.c_void_p.from_address(
            ctypes.addressof(teb) + ibase.ISC_TEB.tpb_ptr.offset
        ).value
        self.calls.append((
            status, transaction, count, teb.db_ptr.contents.value,
            teb.tpb_len, ctypes.string_at(tpb_pointer, teb.tpb_len),
        ))
        return 0


def test_macos_transaction_binding_preserves_handles_and_tpb() -> None:
    api = _ClientAPI()
    _configure_macos_transactions(api)
    status = ibase.ISC_STATUS_ARRAY()
    transaction = ibase.isc_tr_handle(0)
    database = ibase.isc_db_handle(123)
    tpb = b"\x03\x00\x09"

    result = api.isc_start_transaction(
        status, transaction, 1, database, len(tpb), tpb
    )

    assert result == 0
    assert api.calls == [(status, transaction, 1, 123, len(tpb), tpb)]
    binding = api.isc_start_transaction
    _configure_macos_transactions(api)
    assert api.isc_start_transaction is binding


def test_macos_transaction_binding_rejects_multiple_database_arguments() -> None:
    api = _ClientAPI()
    _configure_macos_transactions(api)
    with pytest.raises(fdb.ProgrammingError, match="single database"):
        api.isc_start_transaction(None, None, 2, None, 0, b"")
    assert not api.calls


class _Connection:
    def __init__(self) -> None:
        self.events: list[str] = []
        self.tpb: Any = None

    def rollback(self) -> None:
        self.events.append("rollback")

    def begin(self, *, tpb: Any) -> None:
        self.events.append("begin")
        self.tpb = tpb

    def commit(self) -> None:
        self.events.append("commit")


class _Pool(ConnectionPool):
    def __init__(self) -> None:
        super().__init__(DatabaseSettings(path="unused.fdb", check_path=False))
        self.connection = _Connection()

    def _acquire(self) -> _Connection:
        return self.connection

    def _release(self, connection: Any) -> None:
        connection.events.append("release")


def test_reserved_write_starts_after_rollback_and_commits() -> None:
    pool = _Pool()
    with pool.write_session(reserve_table="UMOWACPC") as connection:
        assert connection.events == ["rollback", "begin"]
        tpb = connection.tpb
        assert tpb.isolation_level == (
            fdb.isc_tpb_read_committed, fdb.isc_tpb_rec_version
        )
        assert tpb.table_reservation["UMOWACPC"] == [(
            fdb.isc_tpb_protected, fdb.isc_tpb_lock_write
        )]
        assert tpb.lock_timeout == 10
    assert connection.events == ["rollback", "begin", "commit", "release"]


def test_reserved_write_failure_rolls_back() -> None:
    pool = _Pool()
    with pytest.raises(ValueError):
        with pool.write_session(reserve_table="UMOWACPC"):
            raise ValueError("Allocation failed")
    assert pool.connection.events == ["rollback", "begin", "rollback", "release"]
