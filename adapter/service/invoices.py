"""Invoices database operations and curated fields."""

from __future__ import annotations

from typing import Any
from .base import BaseDatabaseService


#: Table holding invoices (sales documents) in the BAZAMS schema.
INVOICES_TABLE = "FAKTURA"

#: Columns exposed by ``GET /invoices`` (keys: lower-cased column names).
#:
#: The invoice header of ``FAKTURA`` is wide and mostly bookkeeping, so the
#: projection keeps document identity, links, the contractor snapshot, dates,
#: the PLN and foreign-currency totals and the correction amounts; the
#: per-VAT-rate matrix (``NETTO1``-``NETTO8``, ``VAT1``-``VAT5``,
#: ``BRUTTO1``-``BRUTTO8``), the pre-correction block (``PRKOR_*``, ``ZALICZKA_*``
#: variants), the ``F_*`` marker flags and the ``ALIENSYNCH*``/``WERSJA``/
#: ``EDITCNT``/``TEMP`` bookkeeping columns stay out of the payload.  The
#: invoice lines live in the separate ``FPOZYCJA`` table and are not exposed.
INVOICE_COLUMNS: tuple[str, ...] = (
    "ID_FAKTURA_TABLE",
    "ID_ODDZIAL",
    "ID_FIRMA",
    "ID_MAGAZYN",
    "ID_KLIENT",
    "ID_ODBIORCA",
    "ID_MASZYNA",
    "ID_ZLECENIE",
    "ROK_ZLECENIA",
    "ID_KOSZTORYS",
    "ID_WZ",
    "ID_UMOWA",
    "ID_UMOWACPC",
    "ID_ZAMOWIENIE",
    "ID_PACZKA",
    "ID_ACCOUNT",
    "ID_CURR",
    "NAZWA",
    "ADRES",
    "KOD",
    "POCZTA",
    "NIP",
    "KOD_KRAJU",
    "RODZAJ_DOK",
    "NUMER",
    "NR_KORY",
    "KOREKTA",
    "NR_PAR",
    "CCODE",
    "MIEJSCE_WYST",
    "WYSTAWIL",
    "ODEBRAL",
    "DATA_SPRZ",
    "DATA_WYST",
    "DATA_PLAT",
    "DATA_ZAPL",
    "DATA_KORY",
    "DATA_ZAM",
    "DNI_PLAT",
    "PLATNOSC",
    "WAL_KURS",
    "SUMA_NETTO",
    "SUMA_VAT",
    "SUMA_BRUTTO",
    "ZAPLACONO",
    "ZALICZKA",
    "DO_ZAPLATY",
    "POKOR_NETTO",
    "POKOR_VAT",
    "POKOR_BRUTTO",
    "WAL_NETTO",
    "WAL_VAT",
    "WAL_BRUTTO",
    "WAL_ZAPLACONO",
    "WAL_DO_ZAPLATY",
    "STAN",
    "UWAGI",
    "ZAMOWIENIE",
    "DOUMOWY",
)

#: Columns matched by the ``search`` parameter of ``GET /invoices``.
INVOICE_SEARCH_COLUMNS: tuple[str, ...] = (
    "NUMER",
    "NR_KORY",
    "KOREKTA",
    "NR_PAR",
    "RODZAJ_DOK",
    "CCODE",
    "NAZWA",
    "NIP",
    "ADRES",
    "KOD",
    "POCZTA",
    "PLATNOSC",
    "WYSTAWIL",
    "MIEJSCE_WYST",
    "UWAGI",
    "ZAMOWIENIE",
    "DOUMOWY",
    "STAN",
)


class InvoicesService(BaseDatabaseService):
    """Invoices operations sharing the database service state."""

    def fetch_invoices(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of invoices (sales documents) from ``FAKTURA``.

        ``FAKTURA`` is the invoice header, not the document: the positions live
        in ``FPOZYCJA`` and are not exposed.  :data:`INVOICE_COLUMNS` therefore
        keeps document identity, links, the contractor snapshot, dates and the
        PLN/foreign-currency totals, while the per-VAT-rate matrix and the
        bookkeeping columns are skipped.

        Ordering is by issue date and surrogate key, so paging stays stable
        when several invoices share a date.
        """
        page = self._projection_page(
            INVOICES_TABLE,
            INVOICE_COLUMNS,
            INVOICE_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("DATA_WYST", "ID_FAKTURA_TABLE"),
            label="invoice",
        )
        page["invoices"] = page.pop("rows")
        return page
