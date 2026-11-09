"""Orders database operations and curated fields."""

from __future__ import annotations

from typing import Any
from .base import BaseDatabaseService


#: Table holding service orders (jobs) in the BAZAMS schema.
ORDERS_TABLE = "ZLECENIE"

#: Columns exposed by ``GET /orders`` (keys: lower-cased column names).
#:
#: ``ZLECENIE`` is the widest table of the schema, so this is a hand-picked
#: projection rather than ``SELECT *``: it keeps the response shape stable and
#: the fetch message small (Firebird caps a statement message at 64 KB, which a
#: ``SELECT *`` of a very wide table would eventually blow).
ORDER_COLUMNS: tuple[str, ...] = (
    "ID_ZLECENIE_TABLE",
    "ID_ZLECENIE",
    "ROK",
    "STAN",
    "ID_FIRMA",
    "ID_ODDZIAL",
    "ID_KLIENT",
    "ID_MASZYNA",
    "NAZWA",
    "ADRES",
    "KOD",
    "POCZTA",
    "TELEFON",
    "E_MAIL",
    "STOI",
    "MARKA",
    "MODEL",
    "SERIAL",
    "EWIDENCJA",
    "DATA",
    "TERMIN",
    "DATA_Z",
    "GODZINA_PLAN",
    "DATA_PRZY",
    "DATA_WYDA",
    "DATA_START",
    "DATA_STOP",
    "RODZAJ_US",
    "USZKODZENIE",
    "PROBLEM",
    "DIAGNOZA",
    "WYKONANIE",
    "ZALECENIA",
    "UWAGI",
    "TECHNIK",
    "ZGLASZA",
    "OPERATOR",
    "SIGNWHO",
    "SIGNWHEN",
    "LICZNIK",
    "LICZNIKA3",
    "LICZNIK_TOTAL",
    "ROBOCIZNA",
    "DOJAZD",
    "CZESCI",
    "MATERIALY",
    "NETTO",
    "VAT",
    "BRUTTO",
    "ZALICZKA",
    "PLATNOSC",
    "FAKTURA",
    "PLIK",
)

#: Columns matched by the ``search`` parameter of ``GET /orders``.
#:
#: Deliberately a subset: Firebird sizes the parameter message from the number
#: of ``LIKE`` predicates and rejects more than
#: :data:`adapter.sql.MAX_SEARCH_COLUMNS` of them, so "every text column"
#: (which ``ZLECENIE`` has plenty of) could never be searched in one statement.
ORDER_SEARCH_COLUMNS: tuple[str, ...] = (
    "NAZWA",
    "ADRES",
    "POCZTA",
    "TELEFON",
    "E_MAIL",
    "STOI",
    "MARKA",
    "MODEL",
    "SERIAL",
    "EWIDENCJA",
    "RODZAJ_US",
    "USZKODZENIE",
    "PROBLEM",
    "DIAGNOZA",
    "WYKONANIE",
    "ZALECENIA",
    "UWAGI",
    "TECHNIK",
    "ZGLASZA",
    "STAN",
    "FAKTURA",
    "PLIK",
)


class OrdersService(BaseDatabaseService):
    """Orders operations sharing the database service state."""

    def fetch_orders(
        self,
        *,
        limit: int | None = None,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Return a page of service orders (jobs) from the ``ZLECENIE`` table.

        ``ZLECENIE`` is the widest table of the schema and Firebird caps a
        statement message at 64 KB, so this endpoint avoids both traps:

        * :data:`ORDER_COLUMNS` is a hand-picked projection instead of
          ``SELECT *``, which keeps the fetch message small;
        * :data:`ORDER_SEARCH_COLUMNS` holds fewer columns than
          :data:`adapter.sql.MAX_SEARCH_COLUMNS`, because every ``search``
          predicate is bound as a ``VARCHAR(1024)`` parameter and Firebird
          rejects a wider parameter message with "Implementation limit
          exceeded".

        The budgets are asserted in the test-suite, so extending either list
        too far fails the build instead of the request.
        """
        page = self._projection_page(
            ORDERS_TABLE,
            ORDER_COLUMNS,
            ORDER_SEARCH_COLUMNS,
            limit=limit,
            offset=offset,
            search=search,
            order_columns=("DATA", "ID_ZLECENIE_TABLE"),
            label="order",
        )
        page["orders"] = page.pop("rows")
        return page
