"""Database API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..config import AppSettings
from ..schemas import (
    QueryRequest,
    QueryResponse,
    RowPage,
    SchemaRefreshResponse,
    TableDetail,
    TableListResponse,
)
from ..service import DatabaseService
from .common import FILTERS_DESCRIPTION, get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the database routes."""
    router = APIRouter()

    @router.get(
        "/tables",
        response_model=TableListResponse,
        tags=["schema"],
        summary="List tables and views",
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
    )
    def read_rows(
        table: str,
        limit: int | None = page_limit(settings, "Rows"),
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


    @router.post(
        "/query",
        response_model=QueryResponse,
        tags=["data"],
        summary="Run a read-only SQL query",
    )
    def run_query(
        payload: QueryRequest,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.run_query(
            payload.sql, limit=payload.limit, parameters=payload.parameters
        )


    return router
