"""Agreements API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status

from ..config import AppSettings
from ..schemas import (
    Agreement,
    AgreementCreate,
    AgreementPage,
    AgreementUpdate,
)
from ..service import DatabaseService
from .common import get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the agreements routes."""
    router = APIRouter()

    @router.get(
        "/agreements",
        response_model=AgreementPage,
        tags=["data"],
        summary="List service agreements (contracts)",
        description=(
            "Returns a page of service agreements from the UMOWACPC table, "
            "keyed by the lower-cased column names (id_umowacpc, umowa, typ, "
            "id_klient, ...). 'search' matches umowa, typ, handlowiec, "
            "opiekun, opiekunmail, fraemail and plik (case sensitive "
            "substring)."
        ),
    )
    def list_agreements(
        limit: int | None = page_limit(settings, "Agreements"),
        offset: int = Query(
            default=0, ge=0, description="Number of agreements to skip"
        ),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against umowa, typ, handlowiec, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_agreements(limit=limit, offset=offset, search=search)


    @router.post(
        "/agreements/{id_klient}",
        response_model=Agreement,
        status_code=status.HTTP_201_CREATED,
        tags=["data"],
        summary="Create a service agreement (UMOWACPC)",
        description=(
            "Creates an agreement for id_klient from the URL path. The optional "
            "body contains agreement details. The adapter "
            "assigns id_umowacpc as the lowest unused positive integer, "
            "reusing gaps. The database generates id_umowacpc_table. "
            "Both identifiers are read-only. Optional fields "
            "use legacy defaults, including aktywna=TAK and u_start set to the "
            "database current date, plus umowa=generated ID/current year when "
            "omitted or blank; supplied values override defaults. "
            "An optional machines array links those ID_MASZYNA records to "
            "the new agreement in the same transaction. Missing or ambiguous "
            "machine IDs roll back everything. Omitted preserves links; empty clears. "
            "Returns the same projection as GET /agreements. Generated table "
            "keys and financial totals cannot be supplied. Requires "
            "api.allow_writes and the configured X-API-Key."
        ),
    )
    def create_agreement(
        id_klient: int = Path(ge=1),
        payload: AgreementCreate | None = None,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        values = (
            payload.model_dump(exclude_unset=True, exclude_none=True) if payload else {}
        )
        return service.create_agreement({"id_klient": id_klient, **values})


    @router.patch(
        "/agreements/{id_umowacpc}",
        response_model=Agreement,
        tags=["data"],
        summary="Update a service agreement and optionally link machines",
        description=(
            "Updates only supplied agreement fields, identified by ID_UMOWACPC. "
            "The optional machines array contains ID_MASZYNA values to link. "
            "Omitted arrays preserve links. Supplied arrays replace the complete "
            "list: empty clears all links, removed machines are unassigned. "
            "Existing links on listed machines are reassigned. "
            "Agreement updates and links commit together; missing records "
            "return 404 and ambiguous IDs 409 with rollback. Requires "
            "api.allow_writes and the configured X-API-Key."
        ),
    )
    def update_agreement(
        payload: AgreementUpdate,
        id_umowacpc: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.update_agreement(
            id_umowacpc, payload.model_dump(exclude_unset=True)
        )


    return router
