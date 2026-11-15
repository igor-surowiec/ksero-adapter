"""Read-only routes for the separate machine-data database."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..config import AppSettings
from ..schemas.machines_database import DatabaseMachinePage
from ..service import DatabaseService
from .common import FILTERS_DESCRIPTION, get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the secondary machine database routes."""
    router = APIRouter()

    @router.get(
        "/machines-database",
        response_model=DatabaseMachinePage,
        tags=["MACHINES_DATABASE"],
        summary="List MASZYNY from the machines database",
        description=(
            "Reads MASZYNY from machines_database, independently of the primary "
            "database. Returns the explicit machine projection with lower-case "
            "column names. Search matches serial, MAC, manufacturer, model, "
            "device type, location, IP, group, inventory number and technician. "
            "Returns 503 if machines_database is not configured or unavailable."
        ),
    )
    def list_database_machines(
        limit: int | None = page_limit(settings, "Machines"),
        offset: int = Query(default=0, ge=0),
        search: str | None = Query(default=None, max_length=100),
        filters: str | None = Query(default=None, description=FILTERS_DESCRIPTION),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_database_machines(
            limit=limit, offset=offset, search=search, filters=filters
        )

    return router
