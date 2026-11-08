"""Cpc settlement API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from ..config import AppSettings
from ..schemas.cpc_settlement import (
    Cpc,
    CpcCreate,
    CpcPage,
    CpcUpdate,
)
from ..service import DatabaseService
from .common import FILTERS_DESCRIPTION, get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the cpc settlement routes."""
    router = APIRouter()

    @router.get(
        "/cpc-settlement", response_model=CpcPage, tags=["data"],
        summary="List CPC settlements",
    )
    def list_cpc(
        limit: int | None = page_limit(settings, "CPC records"),
        offset: int = Query(default=0, ge=0),
        search: str | None = Query(default=None, max_length=100),
        filters: str | None = Query(default=None, description=FILTERS_DESCRIPTION),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_cpc(
            limit=limit, offset=offset, search=search, filters=filters
        )


    @router.get(
        "/cpc-settlement/{id_cpc_table}", response_model=Cpc, tags=["data"],
        summary="Get one CPC settlement",
    )
    def get_cpc(
        id_cpc_table: int = Path(ge=0),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.get_cpc(id_cpc_table)


    @router.post(
        "/cpc-settlement", response_model=Cpc, status_code=status.HTTP_201_CREATED,
        tags=["data"], summary="Create a CPC settlement",
        description=(
            "Requires id_maszyna and id_umowacpc. id_klient is derived from the "
            "agreement; if supplied, it must match. Missing agreements return 404 "
            "and ambiguous IDs return 409. Omitted/null rok "
            "and miesiac default independently to the database current year "
            "and month. Explicit values are preserved. "
            "The database generates id_cpc_table. Readings and recorded charges "
            "are stored as supplied; no charge formula is inferred. Legacy "
            "defaults fill omitted fields. Triggers recalculate machine and "
            "agreement totals. Requires api.allow_writes."
        ),
    )
    def create_cpc(
        payload: CpcCreate,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.create_cpc(payload.model_dump(exclude_none=True))


    @router.patch(
        "/cpc-settlement/{id_cpc_table}", response_model=Cpc, tags=["data"],
        summary="Update a CPC settlement",
        description=(
            "Updates supplied fields only. Parent client/machine/agreement "
            "links and the generated key cannot change. Null clears nullable "
            "fields. Database triggers recalculate parent totals. Requires "
            "api.allow_writes; missing records return 404."
        ),
    )
    def update_cpc(
        payload: CpcUpdate,
        id_cpc_table: int = Path(ge=0),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.update_cpc(
            id_cpc_table, payload.model_dump(exclude_unset=True)
        )


    @router.delete(
        "/cpc-settlement/{id_cpc_table}", status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response, tags=["data"], summary="Delete a CPC settlement",
        description=(
            "Deletes one settlement and recalculates parent totals through "
            "database triggers. Requires api.allow_writes; missing records "
            "return 404."
        ),
    )
    def delete_cpc(
        id_cpc_table: int = Path(ge=0),
        service: DatabaseService = Depends(get_service),
    ) -> Response:
        service.delete_cpc(id_cpc_table)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


    return router
