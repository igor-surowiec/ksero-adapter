"""Transaction reservation tests without a live driver connection."""

from __future__ import annotations

from typing import Any

import fdb
import pytest

from ks_adapter.config import DatabaseSettings
from ks_adapter.pool import ConnectionPool


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
