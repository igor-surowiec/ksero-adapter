"""Shared API authentication, service dependency and query parameters."""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import Header, Query, Request

from ..config import AppSettings
from ..errors import AuthenticationError
from ..service import DatabaseService

FILTERS_DESCRIPTION = (
    "JSON object with column filters, e.g. "
    '{"nazwa": "Kowalski", "typ": {"op": "in", "value": [1, 2]}}. '
    "Column names are matched case-insensitively, so the lower-cased Polish "
    "names of the responses work here too. "
    "Supported operators: eq, ne, gt, ge, lt, le, like, contains, startswith, "
    "endswith, in, isnull, notnull."
)


def get_service(request: Request) -> DatabaseService:
    """Return the service instance stored on the application state."""
    service = getattr(request.app.state, "service", None)
    if service is None:  # pragma: no cover - only possible on misconfiguration
        raise RuntimeError("DatabaseService is not attached to the application")
    return service


def require_api_key(settings: AppSettings) -> Any:
    """Build a dependency that enforces the ``X-API-Key`` header when configured."""
    expected = settings.api.api_key

    def check_api_key(
        x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    ) -> None:
        if expected is None:
            return
        if x_api_key is None:
            raise AuthenticationError("Missing X-API-Key header")
        if not hmac.compare_digest(
            x_api_key.encode("utf-8"), expected.encode("utf-8")
        ):
            raise AuthenticationError("Invalid X-API-Key header")

    return check_api_key


def page_limit(settings: AppSettings, label: str) -> Any:
    """Build a page-size query parameter with configured bounds."""
    api = settings.api
    return Query(
        default=None, ge=1, le=api.max_limit,
        description=(
            f"{label} per page (default {api.default_limit}, "
            f"max {api.max_limit})"
        ),
    )
