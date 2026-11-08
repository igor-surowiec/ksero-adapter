"""Clients API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Path, Query, Response, status

from ..config import AppSettings
from ..schemas.clients import (
    Client,
    ClientCreate,
    ClientPage,
    ClientUpdate,
)
from ..service import DatabaseService
from .common import get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the clients routes."""
    router = APIRouter()

    @router.get(
        "/clients",
        response_model=ClientPage,
        tags=["data"],
        summary="List contractors (clients)",
        description=(
            "Returns a page of contractors from the KLIENT table, keyed by the "
            "lower-cased column names (nazwa, id_klient, nip, regon, adres, "
            "kod, poczta, telefon, e_mail, ...). 'search' matches nazwa, "
            "nazwa_s, nip, regon, e_mail, telefon, kod and poczta (case "
            "sensitive substring)."
        ),
    )
    def list_clients(
        limit: int | None = page_limit(settings, "Clients"),
        offset: int = Query(default=0, ge=0, description="Number of clients to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against nazwa, nip, e_mail, telefon, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_clients(limit=limit, offset=offset, search=search)


    @router.post(
        "/clients",
        response_model=Client,
        status_code=status.HTTP_201_CREATED,
        tags=["data"],
        summary="Create a contractor (client)",
        description=(
            "Inserts one row into the KLIENT table and returns the stored row "
            "in the same shape as GET /clients (keys are the lower-cased "
            "column names). 'nazwa' (NAZWA) is the only required value; every "
            "other field is optional. Columns the payload omits get the "
            "defaults the legacy application itself writes (ID_FIRMA 0, TYP "
            "'Odbiorca', PLATNOSC 'Gotowka', KOD_KRAJU 'PL', IDW -1, empty "
            "strings instead of null, zeroed flags), because a row that keeps "
            "the raw Firebird defaults never shows up in that program. The "
            "INS_KLIENT_RECORD trigger fills ID_KLIENT_TABLE and ID_KLIENT "
            "from their generators and ID_ODDZIAL falls back to its column "
            "default. Unknown fields are rejected with 422 instead of being "
            "ignored. Requires 'api.allow_writes' (otherwise 403) and, when "
            "configured, the X-API-Key header."
        ),
    )
    def create_client(
        payload: ClientCreate,
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.create_client(payload.model_dump(exclude_none=True))


    @router.patch(
        "/clients/{id_klient}",
        response_model=Client,
        tags=["data"],
        summary="Update a contractor (client)",
        description=(
            "Updates only supplied fields, identified by the unique "
            "id_klient from GET /clients. Omitted fields stay unchanged. "
            "Null clears optional fields; blank strings clear text fields. "
            "The name cannot be cleared. Returns 404 for an unknown record. "
            "Requires api.allow_writes and the configured X-API-Key."
        ),
    )
    def update_client(
        payload: ClientUpdate,
        id_klient: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.update_client(
            id_klient, payload.model_dump(exclude_unset=True)
        )


    @router.delete(
        "/clients/{id_klient}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
        tags=["data"],
        summary="Delete a contractor (client)",
        description=(
            "Permanently deletes the client identified by ID_KLIENT. "
            "The database DEL_KLIENT_RECORD trigger also deletes the client's "
            "machines and contacts. Returns 204 with no body on success, or "
            "404 when the client does not exist. Requires api.allow_writes "
            "and the configured X-API-Key."
        ),
    )
    def delete_client(
        id_klient: int = Path(ge=1),
        service: DatabaseService = Depends(get_service),
    ) -> Response:
        service.delete_client(id_klient)
        return Response(status_code=status.HTTP_204_NO_CONTENT)


    return router
