"""FastAPI routes exposing the read-only Firebird data."""

from __future__ import annotations

import hmac
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, Query, Request

from .config import AppSettings
from .errors import AuthenticationError
from .schemas import (
    AgreementPage,
    ClientPage,
    HealthResponse,
    QueryRequest,
    QueryResponse,
    RowPage,
    SchemaRefreshResponse,
    ServiceInfo,
    TableDetail,
    TableListResponse,
)
from .service import DatabaseService

FILTERS_DESCRIPTION = (
    "JSON object with column filters, e.g. "
    '{"NAZWA": "Kowalski", "TYP": {"op": "in", "value": [1, 2]}}. '
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


def create_router(settings: AppSettings) -> APIRouter:
    """Create the API router for ``settings``."""
    api = settings.api
    protected = [Depends(require_api_key(settings))]
    router = APIRouter(prefix=api.prefix)

    @router.get(
        "/",
        response_model=ServiceInfo,
        tags=["meta"],
        summary="Service information",
    )
    def service_info() -> ServiceInfo:
        from . import __version__

        return ServiceInfo(
            name="ks-adapter",
            version=__version__,
            api_prefix=api.prefix,
            docs_url="/docs",
        )

    @router.get(
        "/health",
        response_model=HealthResponse,
        tags=["meta"],
        summary="Check database connectivity",
    )
    def health(
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.health()

    @router.get(
        "/tables",
        response_model=TableListResponse,
        tags=["schema"],
        summary="List tables and views",
        dependencies=protected,
    )
    def list_tables(
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        tables = service.list_tables()
        return {"count": len(tables), "tables": tables}

    @router.get(
        "/tables/{table}",
        response_model=TableDetail,
        tags=["schema"],
        summary="Describe a table or view",
        dependencies=protected,
    )
    def describe_table(
        table: str,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.describe_table(table)

    @router.post(
        "/schema/refresh",
        response_model=SchemaRefreshResponse,
        tags=["schema"],
        summary="Reload cached table metadata",
        dependencies=protected,
    )
    def refresh_schema(
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return {"refreshed": True, "table_count": service.refresh_schema()}

    @router.get(
        "/tables/{table}/rows",
        response_model=RowPage,
        tags=["data"],
        summary="Read a page of rows from a table or view",
        dependencies=protected,
    )
    def read_rows(
        table: str,
        limit: int | None = Query(
            default=None,
            ge=1,
            le=api.max_limit,
            description=f"Rows per page (default {api.default_limit}, max {api.max_limit})",
        ),
        offset: int = Query(default=0, ge=0, description="Number of rows to skip"),
        order_by: str | None = Query(
            default=None,
            description="Comma separated sort keys, e.g. 'NAZWA ASC, ID DESC'",
        ),
        filters: str | None = Query(default=None, description=FILTERS_DESCRIPTION),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_rows(
            table, limit=limit, offset=offset, order_by=order_by, filters=filters
        )

    @router.get(
        "/clients",
        response_model=ClientPage,
        tags=["data"],
        summary="List contractors (clients)",
        description=(
            "Returns a page of contractors from the KLIENT table with the most "
            "useful fields (id, name, NIP/REGON, address, contacts, payment "
            "terms). 'search' matches the name, short name, NIP, REGON, email, "
            "phone, postcode and city (case sensitive substring)."
        ),
        dependencies=protected,
    )
    def list_clients(
        limit: int | None = Query(
            default=None,
            ge=1,
            le=api.max_limit,
            description=f"Clients per page (default {api.default_limit}, max {api.max_limit})",
        ),
        offset: int = Query(default=0, ge=0, description="Number of clients to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against name, NIP, email, phone, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_clients(limit=limit, offset=offset, search=search)

    @router.get(
        "/agreements",
        response_model=AgreementPage,
        tags=["data"],
        summary="List service agreements (contracts)",
        description=(
            "Returns a page of service agreements from the UMOWACPC table with "
            "the most useful fields (ids, number, type, parties, dates, "
            "financial summary, contact person, printing volumes). 'search' "
            "matches the agreement number, type, salesperson, supervisor, "
            "supervisor e-mail, invoice e-mail and linked file (case sensitive "
            "substring)."
        ),
        dependencies=protected,
    )
    def list_agreements(
        limit: int | None = Query(
            default=None,
            ge=1,
            le=api.max_limit,
            description=(
                f"Agreements per page (default {api.default_limit}, "
                f"max {api.max_limit})"
            ),
        ),
        offset: int = Query(default=0, ge=0, description="Number of agreements to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against number, type, salesperson, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_agreements(limit=limit, offset=offset, search=search)

    @router.post(
        "/query",
        response_model=QueryResponse,
        tags=["data"],
        summary="Run a read-only SQL query",
        dependencies=protected,
    )
    def run_query(
        payload: QueryRequest,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.run_query(
            payload.sql, limit=payload.limit, parameters=payload.parameters
        )

    return router
