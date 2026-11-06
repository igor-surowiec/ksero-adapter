"""Domain errors that the API layer translates into HTTP responses."""

from __future__ import annotations


class AdapterError(Exception):
    """Base class for all adapter errors carrying an HTTP status code."""

    status_code = 500

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class InvalidRequest(AdapterError):
    """The client sent a malformed or unsupported request."""

    status_code = 400


class QueryNotAllowed(InvalidRequest):
    """The SQL statement is not a read-only SELECT/WITH query."""

    status_code = 400


class ColumnNotFound(InvalidRequest):
    """A referenced table column does not exist."""

    status_code = 400


class AuthenticationError(AdapterError):
    """The request is missing or has an invalid API key."""

    status_code = 401


class TableNotFound(AdapterError):
    """A referenced table or view does not exist."""

    status_code = 404


class DatabaseUnavailable(AdapterError):
    """The Firebird database could not be reached."""

    status_code = 503
