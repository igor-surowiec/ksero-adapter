"""Machines API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, status

from ..config import AppSettings
from ..errors import InvalidRequest
from ..schemas.machines import (
    Machine,
    MachineCreate,
    MachinePage,
    MachineUpdate,
)
from ..service import DatabaseService
from .common import get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the machines routes."""
    router = APIRouter()

    @router.get(
        "/machines",
        response_model=MachinePage,
        tags=["data"],
        summary="List machines (installed devices)",
        description=(
            "Returns a page of machines from the MASZYNA table, keyed by the "
            "lower-cased column names (id_maszyna, marka, model, serial, "
            "licznik, ...). 'search' matches marka, model, grupa, typ, "
            "rodzaj_us, serial, serial2, ewidencja, miejscowosc and technik "
            "(case sensitive substring)."
        ),
    )
    def list_machines(
        limit: int | None = page_limit(settings, "Machines"),
        offset: int = Query(default=0, ge=0, description="Number of machines to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against marka, model, serial, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_machines(limit=limit, offset=offset, search=search)


    @router.post(
        "/machines",
        response_model=Machine,
        status_code=status.HTTP_201_CREATED,
        tags=["data"],
        summary="Create a machine (installed device)",
        description=(
            "Inserts one row into the MASZYNA table and returns the stored row "
            "in the same shape as GET /machines (keys are the lower-cased "
            "column names). All fields are optional; an omitted or null "
            "id_klient is stored as 0 (unassigned). The "
            "INS_MASZYNA_RECORD trigger fills ID_MASZYNA_TABLE and ID_MASZYNA "
            "from their generators. Legacy defaults fill omitted fields: branch, "
            "company, VAT and sync flags 0; grupa Druk; aktywna TAK; kolorowa NIE; "
            "rodzaj_us Platne; expected empty text fields. Supplied values "
            "override those defaults. Unknown fields are rejected with "
            "422. Requires 'api.allow_writes' (otherwise 403) and, when "
            "configured, the X-API-Key header."
        ),
    )
    def create_machine(
        payload: MachineCreate,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.create_machine(payload.model_dump(exclude_none=True))


    @router.post(
        "/machines/{id_klient}",
        response_model=Machine,
        status_code=status.HTTP_201_CREATED,
        tags=["data"],
        summary="Create a machine for a client",
        description=(
            "Creates a machine with id_klient from the URL. The body is optional "
            "and accepts the same details and legacy defaults as POST /machines. "
            "A conflicting body id_klient returns 400. Client ID 0 means "
            "unassigned. Requires api.allow_writes and the configured X-API-Key."
        ),
    )
    def create_client_machine(
        id_klient: int = Path(ge=0),
        payload: MachineCreate | None = None,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        values = payload.model_dump(exclude_none=True) if payload else {}
        if values.get("id_klient", id_klient) != id_klient:
            raise InvalidRequest("Body 'id_klient' must match the URL client ID")
        return service.create_machine({**values, "id_klient": id_klient})


    @router.patch(
        "/machines/{id_maszyna}",
        response_model=Machine,
        tags=["data"],
        summary="Update a machine (installed device)",
        description=(
            "Updates only supplied fields, identified by ID_MASZYNA. "
            "Omitted fields stay unchanged. Null clears nullable fields; "
            "blank strings clear text fields. Set id_klient to 0 to unassign "
            "the owner; null is invalid for non-nullable columns. "
            "Generated keys and derived fields cannot be changed. Returns "
            "404 if missing, 409 if the business ID matches multiple records. "
            "Requires api.allow_writes and the configured X-API-Key."
        ),
    )
    def update_machine(
        payload: MachineUpdate,
        id_maszyna: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.update_machine(
            id_maszyna, payload.model_dump(exclude_unset=True)
        )


    return router
