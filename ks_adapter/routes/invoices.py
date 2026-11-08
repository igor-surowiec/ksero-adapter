"""Invoices API routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from ..config import AppSettings
from ..schemas.invoices import InvoicePage
from ..service import DatabaseService
from .common import get_service, page_limit


def create_router(settings: AppSettings) -> APIRouter:
    """Build the invoices routes."""
    router = APIRouter()

    @router.get(
        "/invoices",
        response_model=InvoicePage,
        tags=["data"],
        summary="List invoices (sales documents)",
        description=(
            "Returns a page of invoice headers from the FAKTURA table, keyed "
            "by the lower-cased column names (id_faktura_table, numer, nazwa, "
            "suma_brutto, ...): document links, the contractor snapshot, "
            "type/number and corrections, sale/issue/due/paid dates, payment "
            "terms, issuer, PLN totals with paid and outstanding amounts and "
            "the foreign-currency totals. The positions live in FPOZYCJA and "
            "are not included. 'search' matches numer, nr_kory, korekta, "
            "nr_par, rodzaj_dok, ccode, nazwa, nip, adres, kod, poczta, "
            "platnosc, wystawil, miejsce_wyst, uwagi, zamowienie, doumowy and "
            "stan (case sensitive substring)."
        ),
    )
    def list_invoices(
        limit: int | None = page_limit(settings, "Invoices"),
        offset: int = Query(default=0, ge=0, description="Number of invoices to skip"),
        search: str | None = Query(
            default=None,
            max_length=100,
            description="Substring matched against numer, nazwa, uwagi, ...",
        ),
        service: DatabaseService = Depends(get_service),
    ) -> dict[str, Any]:
        return service.fetch_invoices(limit=limit, offset=offset, search=search)


    return router
