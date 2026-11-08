"""Compose the resource routers under the configured API prefix."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from .config import AppSettings
from .routes import (
    agreements,
    clients,
    cpc_settlement,
    database,
    invoices,
    machines,
    meta,
    orders,
)
from .routes.common import FILTERS_DESCRIPTION as FILTERS_DESCRIPTION
from .routes.common import get_service as get_service
from .routes.common import require_api_key as require_api_key


def create_router(settings: AppSettings) -> APIRouter:
    """Compose public metadata and authenticated resource routers."""
    router = APIRouter(prefix=settings.api.prefix)
    router.include_router(meta.create_router(settings))
    protected = [Depends(require_api_key(settings))]
    for resource in (database, clients, agreements, machines,
                     cpc_settlement, orders, invoices):
        router.include_router(resource.create_router(settings), dependencies=protected)
    return router
