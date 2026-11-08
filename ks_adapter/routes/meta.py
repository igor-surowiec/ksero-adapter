"""Meta API routes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from ..config import AppSettings
from ..schemas.meta import HealthResponse, ServiceInfo
from ..service import DatabaseService
from .common import get_service


def api_tester() -> FileResponse:
    """Serve the buildless API tester without accessing the database."""
    path = Path(__file__).resolve().parent.parent / "static" / "api_tester.html"
    return FileResponse(
        path, media_type="text/html", headers={"Cache-Control": "no-store"}
    )


def create_router(settings: AppSettings) -> APIRouter:
    """Build the meta routes."""
    api = settings.api
    router = APIRouter()

    @router.get(
        "/",
        response_model=ServiceInfo,
        tags=["meta"],
        summary="Service information",
    )
    def service_info() -> ServiceInfo:
        from .. import __version__

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


    return router
