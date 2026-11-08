"""Connection pooling on top of the ``fdb`` Firebird DB-API driver."""

from __future__ import annotations

import logging
import queue
import threading
import time
from contextlib import contextmanager
from typing import Any, Iterator

import fdb

from .config import DatabaseSettings
from .errors import DatabaseUnavailable

logger = logging.getLogger(__name__)


def connect(settings: DatabaseSettings) -> Any:
    """Open a new Firebird connection based on ``settings``."""
    kwargs: dict[str, Any] = {
        "dsn": settings.dsn,
        "user": settings.user,
        "password": settings.password,
        "charset": settings.charset,
        "sql_dialect": 3,
    }
    if settings.client_library:
        kwargs["fb_library_name"] = settings.client_library
    logger.debug("Opening Firebird connection to %s", settings.dsn)
    return fdb.connect(**kwargs)


class ConnectionPool:
    """Small thread-safe pool of Firebird connections.

    Connections are never shared between threads at the same time.  Every
    connection borrowed through :meth:`session` is rolled back before it is
    returned to the pool so no transaction state leaks between requests;
    :meth:`write_session` commits instead and is the only way data is persisted.
    """

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._capacity = max(1, settings.pool_size)
        self._queue: queue.LifoQueue[Any] = queue.LifoQueue(maxsize=self._capacity)
        self._lock = threading.Lock()
        self._created = 0
        self._closed = False

    @property
    def stats(self) -> dict[str, int]:
        return {
            "created": self._created,
            "idle": self._queue.qsize(),
            "capacity": self._capacity,
        }

    @contextmanager
    def session(self) -> Iterator[Any]:
        """Borrow a connection, always returning or discarding it afterwards."""
        connection = self._acquire()
        try:
            yield connection
        finally:
            self._release(connection)

    @contextmanager
    def write_session(self) -> Iterator[Any]:
        """Borrow a connection for a write and commit when the block succeeds.

        The transaction is committed only after the ``with`` block returns; an
        exception during the block (or during the commit itself) rolls it back,
        so a failed request never leaves half-written rows behind.  This is the
        only place in the adapter that commits - ``session()`` keeps reading
        requests read-only.
        """
        connection = self._acquire()
        discarded = False
        try:
            yield connection
            connection.commit()
        except BaseException:
            try:
                connection.rollback()
            except Exception:  # pragma: no cover - broken connection
                self._discard(connection)
                discarded = True
            raise
        finally:
            if not discarded:
                self._release(connection)

    def ping(self) -> str:
        """Execute a trivial query and return the server version string."""
        with self.session() as connection:
            self._execute_ping(connection)
            return str(connection.server_version)

    def close(self) -> None:
        """Close all idle connections; further acquisitions are rejected."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
        while True:
            try:
                connection = self._queue.get_nowait()
            except queue.Empty:
                break
            self._close_quietly(connection)
        logger.debug("Firebird connection pool closed")

    def _acquire(self) -> Any:
        if self._closed:
            raise DatabaseUnavailable("The Firebird connection pool is closed")

        deadline = time.monotonic() + self._settings.acquire_timeout
        while True:
            connection = self._take_idle()
            if connection is not None:
                if self._is_healthy(connection):
                    return connection
                self._discard(connection)
                continue

            if self._try_reserve_slot():
                try:
                    return self._new_connection()
                except BaseException:
                    self._release_slot()
                    raise

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DatabaseUnavailable(
                    "Timed out waiting for a free Firebird connection "
                    f"(pool_size={self._capacity})"
                )
            try:
                connection = self._queue.get(timeout=remaining)
            except queue.Empty:
                raise DatabaseUnavailable(
                    "Timed out waiting for a free Firebird connection "
                    f"(pool_size={self._capacity})"
                ) from None
            if self._is_healthy(connection):
                return connection
            self._discard(connection)

    def _take_idle(self) -> Any | None:
        try:
            return self._queue.get_nowait()
        except queue.Empty:
            return None

    def _try_reserve_slot(self) -> bool:
        with self._lock:
            if self._created >= self._capacity:
                return False
            self._created += 1
            return True

    def _release_slot(self) -> None:
        with self._lock:
            if self._created > 0:
                self._created -= 1

    def _new_connection(self) -> Any:
        try:
            return connect(self._settings)
        except Exception as exc:
            raise DatabaseUnavailable(
                f"Unable to connect to Firebird database '{self._settings.dsn}': {exc}"
            ) from exc

    def _release(self, connection: Any) -> None:
        if self._closed:
            self._close_quietly(connection)
            self._release_slot()
            return
        try:
            if getattr(connection, "closed", False):
                raise fdb.Error("connection is closed")
            connection.rollback()
        except Exception:
            self._discard(connection)
            return
        try:
            self._queue.put_nowait(connection)
        except queue.Full:
            self._discard(connection)

    def _discard(self, connection: Any) -> None:
        self._close_quietly(connection)
        self._release_slot()

    def _close_quietly(self, connection: Any) -> None:
        try:
            connection.close()
        except Exception:  # pragma: no cover - closing a dead connection is best effort
            pass

    def _is_healthy(self, connection: Any) -> bool:
        if getattr(connection, "closed", False):
            return False
        if not self._settings.health_check:
            return True
        try:
            self._execute_ping(connection)
            return True
        except Exception:
            return False

    @staticmethod
    def _execute_ping(connection: Any) -> None:
        cursor = connection.cursor()
        try:
            cursor.execute("SELECT 1 FROM RDB$DATABASE")
            cursor.fetchone()
        finally:
            cursor.close()

