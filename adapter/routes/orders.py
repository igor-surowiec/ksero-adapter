"""Orders API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..config import AppSettings
from ..schemas.orders import OrderPage
from ..service import DatabaseService
from .common import get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the orders routes."""
    router = APIRouter()

    @router.get(
        "/orders",
        response_model=OrderPage,
        tags=["data"],
        summary="List service orders (jobs)",
        description=(
            "Returns a page of service orders from the ZLECENIE table, keyed "
            "by the lower-cased column names (id_zlecenie, nazwa, stan, "
            "marka, model, ...). ZLECENIE is the widest table of the schema, "
            "so the columns are a curated subset: Firebird caps a statement "
            "message at 64 KB, which a full-width SELECT or a LIKE over every "
            "text column would exceed. 'search' matches nazwa, adres, poczta, "
            "telefon, e_mail, stoi, marka, model, serial, ewidencja, "
            "rodzaj_us, uszkodzenie, problem, diagnoza, wykonanie, zalecenia, "
            "uwagi, technik, zglasza, stan, faktura and plik (case sensitive "
            "substring)."
        ),
    )
    def list_orders(
        limit: int | None = page_limit(settings, "Orders"),
        offset: int = Query(default=0, ge=0, description="Number of orders to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against nazwa, marka, uszkodzenie, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_orders(limit=limit, offset=offset, search=search)


    return router
