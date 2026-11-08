"""Meta API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from ..config import AppSettings
from ..schemas import HealthResponse, ServiceInfo
from ..service import DatabaseService
from .common import get_service


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
